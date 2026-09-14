import re
import tempfile
import unittest
from pathlib import Path

from backend.app import create_app
from backend.app.config import Config
from backend.app.models import User, UserAccount, db
from backend.app.openapi import OPERATIONS


class OpenAPITestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.upload_dir = tempfile.TemporaryDirectory()

        class TestConfig(Config):
            TESTING = True
            SECRET_KEY = "openapi-test"
            SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
            USE_MOCK_SERVICES = True
            UPLOAD_DIR = Path(cls.upload_dir.name)
            SESSION_COOKIE_SECURE = False

        cls.app = create_app(TestConfig)

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            db.session.remove()
            db.engine.dispose()
        cls.upload_dir.cleanup()

    def setUp(self):
        self.client = self.app.test_client()
        response = self.client.get("/api/openapi.json")
        self.assertEqual(response.status_code, 200)
        self.spec = response.get_json()

    def test_documentation_page_and_spec_are_public(self):
        response = self.client.get("/api/docs")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"SwaggerUIBundle", response.data)
        self.assertIn(b"/api/openapi.json", response.data)
        self.assertIn(b'"withCredentials": true', response.data)
        self.assertEqual(self.spec["openapi"], "3.0.3")
        self.assertEqual(self.client.get("/api/health").get_json(),
                         {"ok": True, "service": "interploop"})

    def test_every_business_route_is_documented_with_unique_operation_id(self):
        expected = set()
        endpoints = set()
        for rule in self.app.url_map.iter_rules():
            if not rule.rule.startswith("/api/") or rule.endpoint.startswith("api-docs."):
                continue
            endpoints.add(rule.endpoint)
            path = re.sub(r"<(?:(?:[^:<>]+):)?([^<>]+)>", r"{\1}", rule.rule)
            expected.update((path, method.lower()) for method in rule.methods - {"HEAD", "OPTIONS"})
        actual = {(path, method) for path, methods in self.spec["paths"].items()
                  for method in methods if method != "parameters"}
        self.assertEqual(actual, expected)
        self.assertEqual(endpoints, set(OPERATIONS))
        ids = [operation["operationId"] for path in self.spec["paths"].values()
               for method, operation in path.items() if method != "parameters"]
        self.assertEqual(len(ids), len(set(ids)))

    def test_parameters_uploads_downloads_and_archive_statuses(self):
        paths = self.spec["paths"]
        audio = paths["/api/practices/{session_id}/audio"]
        self.assertIn({"name": "session_id", "in": "path", "required": True,
                       "schema": {"type": "integer", "minimum": 0}}, audio["parameters"])
        for path, field in (("/api/practices/{session_id}/audio", "audio"),
                            ("/api/admin/students/import", "file")):
            body = paths[path]["post"]["requestBody"]
            schema = body["content"]["multipart/form-data"]["schema"]
            self.assertTrue(body["required"])
            self.assertIn(field, schema["required"])
            self.assertEqual(schema["properties"][field]["format"], "binary")
        for path in ("/api/practices/export.csv", "/api/practices/evaluation-versions/export.csv",
                     "/api/feedback-logs/export.csv"):
            self.assertIn("text/csv", paths[path]["get"]["responses"]["200"]["content"])
        archive = paths["/api/practices/{session_id}/archive"]["post"]["responses"]
        self.assertTrue({"200", "201"}.issubset(archive))
        login = paths["/api/auth/login"]["post"]["requestBody"]["content"]["application/json"]["schema"]
        self.assertEqual(set(login["required"]), {"login_id", "password"})

    def test_cookie_login_still_controls_protected_routes(self):
        scheme = self.spec["components"]["securitySchemes"]["sessionCookie"]
        self.assertEqual(scheme["in"], "cookie")
        self.assertEqual(scheme["name"], self.app.config["SESSION_COOKIE_NAME"])
        self.assertEqual(self.spec["security"], [{"sessionCookie": []}])
        for path, method in (("/api/auth/login", "post"), ("/api/auth/me", "get"),
                             ("/api/auth/logout", "post"), ("/api/health", "get")):
            self.assertEqual(self.spec["paths"][path][method]["security"], [])
        self.assertEqual(self.client.get("/api/practices").status_code, 401)
        with self.app.app_context():
            user = User(name="文档测试学生", role="student", student_no="docs-student")
            db.session.add(user)
            db.session.flush()
            account = UserAccount(user_id=user.id, login_id="docs-student")
            account.set_password("DocsTest123", must_change=True)
            db.session.add(account)
            db.session.commit()
        login = self.client.post("/api/auth/login", json={"login_id": "docs-student", "password": "DocsTest123"})
        self.assertEqual(login.status_code, 200)
        self.assertIn("Set-Cookie", login.headers)
        self.assertEqual(self.client.get("/api/practices").status_code, 403)
        changed = self.client.post("/api/auth/change-password", json={
            "current_password": "DocsTest123", "new_password": "ChangedDocs456",
        })
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(self.client.get("/api/practices").status_code, 200)
        self.assertEqual(self.client.get("/api/admin/overview").status_code, 403)
        self.assertEqual(self.client.post("/api/auth/logout").status_code, 200)
        self.assertEqual(self.client.get("/api/practices").status_code, 401)


if __name__ == "__main__":
    unittest.main()
