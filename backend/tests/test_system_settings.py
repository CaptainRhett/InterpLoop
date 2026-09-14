import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.app import create_app
from backend.app.config import Config
from backend.app.models import ServiceSettings, User, UserAccount, db
from backend.app.services.settings import service_config
from backend.app.services.llm import LLMClient
from backend.app.services.speech import ASRClient


class SystemSettingsTestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        class TestConfig(Config):
            TESTING = True
            SECRET_KEY = "settings-test"
            SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
            UPLOAD_DIR = Path(self.directory.name)
            USE_MOCK_SERVICES = True
            DOUBAO_API_KEY = "environment-secret"
        self.app = create_app(TestConfig)
        with self.app.app_context():
            for role in ("admin", "student"):
                user = User(name=role, role=role)
                db.session.add(user)
                db.session.flush()
                account = UserAccount(user_id=user.id, login_id=role)
                account.set_password("TestPass123", must_change=False)
                db.session.add(account)
            db.session.commit()
        self.client = self.app.test_client()
        self.client.post("/api/auth/login", json={"login_id": "admin", "password": "TestPass123"})

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        self.directory.cleanup()

    def save(self, **values):
        return self.client.put("/api/admin/system/settings", json=values)

    def test_admin_only_and_no_secrets_in_reads(self):
        read = self.client.get("/api/admin/system/settings")
        self.assertEqual(read.status_code, 200)
        self.assertNotIn("environment-secret", read.get_data(as_text=True))
        other = self.app.test_client()
        self.assertEqual(other.get("/api/admin/system/settings").status_code, 401)
        other.post("/api/auth/login", json={"login_id": "student", "password": "TestPass123"})
        for response in (other.get("/api/admin/system/settings"), other.put("/api/admin/system/settings", json={}),
                         other.post("/api/admin/system/test/llm", json={})):
            self.assertEqual(response.status_code, 403)

    def test_encrypted_persistence_blank_retention_and_live_clients(self):
        response = self.save(DOUBAO_API_KEY="saved-secret", DOUBAO_MODEL="model-new", LLM_PROVIDER="openai_compatible",
                             DOUBAO_BASE_URL="https://model.example/v1", USE_MOCK_SERVICES=False)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("saved-secret", response.get_data(as_text=True))
        with self.app.app_context():
            self.assertNotIn("saved-secret", json.dumps(db.session.get(ServiceSettings, 1).values))
        self.save(DOUBAO_API_KEY="")
        with self.app.test_request_context():
            client = LLMClient()
            self.assertEqual(client.api_key, "saved-secret")
            self.assertEqual(client.model, "model-new")
            self.assertFalse(client.mock)
        logs = self.client.get("/api/admin/audit-logs").get_data(as_text=True)
        self.assertNotIn("saved-secret", logs)

    def test_environment_fallback_field_overrides_and_restore(self):
        with self.app.app_context():
            self.app.config.update(ASR_PROVIDER="openai_compatible", ASR_MODEL="env-asr", ASR_API_KEY="env-asr-key")
        initial = self.client.get("/api/admin/system/settings").get_json()
        self.assertEqual(initial["settings"]["ASR_MODEL"], "env-asr")
        self.assertEqual(initial["sources"]["ASR_MODEL"], "environment")
        saved = self.save(ASR_MODEL="web-asr", ASR_API_KEY="web-key").get_json()
        self.assertEqual(saved["sources"]["ASR_MODEL"], "web")
        self.assertEqual(saved["settings"]["ASR_PROVIDER"], "openai_compatible")
        restored = self.save(ASR_MODEL=None, ASR_API_KEY=None).get_json()
        self.assertEqual(restored["settings"]["ASR_MODEL"], "env-asr")
        self.assertEqual(restored["sources"]["ASR_API_KEY"], "environment")
        with self.app.test_request_context():
            self.assertEqual(ASRClient().config["ASR_API_KEY"], "env-asr-key")
        self.assertNotIn("env-asr-key", json.dumps(restored))

    def test_all_service_options_can_be_read_from_environment(self):
        import os
        import runpy
        values = {"LLM_PROVIDER": "openai_compatible", "ASR_PROVIDER": "openai_compatible",
                  "ASR_BASE_URL": "https://asr.example/v1", "ASR_API_KEY": "environment-test-key",
                  "ASR_MODEL": "environment-model", "XUNFEI_IAT_DOMAIN": "test-domain"}
        with patch.dict(os.environ, values):
            config = runpy.run_path(str(Path(__file__).parents[1] / "app" / "config.py"))["Config"]
        for key, value in values.items():
            self.assertEqual(getattr(config, key), value)

    def test_invalid_configuration_is_atomic(self):
        for values in ({"SECRET_KEY": "no"}, {"LLM_TIMEOUT_SECONDS": 0}, {"ASR_PROVIDER": "unknown"},
                       {"DOUBAO_BASE_URL": "https://user:password@example.com/v1"}, {"USE_MOCK_SERVICES": "false"}):
            self.assertEqual(self.save(**values).status_code, 400)
        with self.app.app_context():
            self.assertIsNone(db.session.get(ServiceSettings, 1))

    def test_llm_test_calls_real_saved_provider_in_mock_mode(self):
        self.save(DOUBAO_MODEL="custom", LLM_PROVIDER="openai_compatible")
        with patch("backend.app.services.llm.requests.post") as post:
            post.return_value.json.return_value = {"choices": [{"message": {"content": "连接成功"}}]}
            response = self.client.post("/api/admin/system/test/llm", json={"text": "hello"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["result"]["message"], "连接成功")
            self.assertNotIn("thinking", post.call_args.kwargs["json"])
            self.assertEqual(post.call_args.kwargs["json"]["model"], "custom")
        with self.app.test_request_context():
            self.assertTrue(service_config()["USE_MOCK_SERVICES"])
        with patch("backend.app.services.llm.requests.post", side_effect=RuntimeError("environment-secret")):
            response = self.client.post("/api/admin/system/test/llm", json={})
            self.assertEqual(response.status_code, 502)
            self.assertNotIn("environment-secret", response.get_data(as_text=True))

    def test_asr_test_wav_wraps_pcm_and_removes_temporary_files(self):
        self.save(ASR_PROVIDER="openai_compatible", ASR_MODEL="asr-new", ASR_API_KEY="asr-secret")
        with patch("backend.app.services.speech.requests.post") as post:
            post.return_value.json.return_value = {"text": "recognized"}
            response = self.client.post("/api/admin/system/test/asr", data={
                "audio": (io.BytesIO(b'\x00\x00' * 160), "test.pcm"), "lang": "en-US"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["result"]["transcript"], "recognized")
            kwargs = post.call_args.kwargs
            self.assertTrue(kwargs["files"]["file"][1].startswith(b"RIFF"))
            self.assertEqual(kwargs["data"]["model"], "asr-new")
            self.assertEqual(kwargs["data"]["language"], "en")
        paths = []
        def transcribe(path, lang):
            paths.append(path)
            self.assertTrue(Path(path).exists())
            return {"transcript": "test"}
        with patch.object(ASRClient, "transcribe", side_effect=transcribe):
            self.client.post("/api/admin/system/test/asr", data={"audio": (io.BytesIO(b"pcm"), "test.pcm")})
        self.assertTrue(paths)
        self.assertFalse(Path(paths[0]).exists())

    def test_xunfei_saved_domain_and_missing_upload(self):
        self.save(XUNFEI_APP_ID="test", XUNFEI_API_KEY="key", XUNFEI_API_SECRET="secret", XUNFEI_IAT_DOMAIN="medical")
        from backend.app.services.speech import XunfeiIATClient
        with self.app.test_request_context(), patch("backend.app.services.speech.websocket.create_connection") as connect:
            ws = connect.return_value
            ws.recv.return_value = json.dumps({"code": 0, "data": {"status": 2, "result": {"ws": []}}})
            file = Path(self.directory.name) / "sample.pcm"
            file.write_bytes(b"\0\0")
            XunfeiIATClient().transcribe(str(file), "zh-CN")
            self.assertEqual(json.loads(ws.send.call_args.args[0])["business"]["domain"], "medical")
        self.assertEqual(self.client.post("/api/admin/system/test/asr").status_code, 400)
