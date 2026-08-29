import io
import tempfile
import unittest
from pathlib import Path

from backend.app import create_app
from backend.app.config import Config
from backend.app.models import (
    PracticeEvaluationVersion,
    PracticeResult,
    PracticeSession,
    User,
    UserAccount,
    backfill_practice_evaluation_versions,
    db,
)
from backend.app.services.llm import LLMClient
from backend.app.services.speech import asr_language_code


class LanguageSupportTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.upload_dir = tempfile.TemporaryDirectory()

        class TestConfig(Config):
            TESTING = True
            SECRET_KEY = "test-secret"
            SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
            USE_MOCK_SERVICES = True
            UPLOAD_DIR = Path(cls.upload_dir.name)
            ALLOW_LEGACY_LOGIN = True
            REQUIRE_PRACTICE_CONTEXT = False

        cls.app = create_app(TestConfig)
        with cls.app.app_context():
            admin = User(name="测试管理员", role="admin")
            db.session.add(admin)
            db.session.flush()
            account = UserAccount(user_id=admin.id, login_id="test-admin")
            account.set_password("AdminPass123", must_change=False)
            db.session.add(account)
            db.session.commit()

    @classmethod
    def tearDownClass(cls):
        cls.upload_dir.cleanup()

    def setUp(self):
        self.client = self.app.test_client()
        response = self.client.post(
            "/api/auth/student-login",
            json={"student_no": "language-test", "name": "语言测试"},
        )
        self.assertEqual(response.status_code, 200)

    def create_practice(self, direction="中→英", source_text="欢迎参加本次会议。"):
        response = self.client.post(
            "/api/practices",
            json={"source_text": source_text, "direction": direction},
        )
        self.assertEqual(response.status_code, 201)
        return response.get_json()["practice"]

    def evaluate_practice(self, practice_id, asr_text):
        response = self.client.post(
            f"/api/practices/{practice_id}/evaluate",
            json={"asr_text": asr_text},
        )
        self.assertEqual(response.status_code, 200)
        return response.get_json()

    def admin_client(self):
        client = self.app.test_client()
        response = client.post(
            "/api/auth/login",
            json={"login_id": "test-admin", "password": "AdminPass123"},
        )
        self.assertEqual(response.status_code, 200)
        return client

    def test_all_translation_directions_can_be_created(self):
        for direction in ("日→中", "中→日", "英→中", "中→英"):
            with self.subTest(direction=direction):
                response = self.client.post(
                    "/api/practices",
                    json={"source_text": "Language test", "direction": direction},
                )
                self.assertEqual(response.status_code, 201)
                self.assertEqual(response.get_json()["practice"]["direction"], direction)

    def test_english_target_uses_english_asr(self):
        practice = self.client.post(
            "/api/practices",
            json={"source_text": "欢迎参加本次会议。", "direction": "中→英"},
        ).get_json()["practice"]

        response = self.client.post(
            f"/api/practices/{practice['id']}/audio",
            data={
                "audio": (io.BytesIO(b"mock pcm audio"), "practice.pcm"),
                "lang": "en-US",
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["asr"]["transcript"].startswith("This is"))

    def test_english_tts_is_accepted(self):
        response = self.client.post(
            "/api/tts",
            json={"text": "Welcome to the conference.", "lang": "en-US"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["provider"], "mock")

    def test_real_service_codes_and_evaluation_prompt_use_english(self):
        self.assertEqual(asr_language_code("en-US"), "en_us")
        with self.app.app_context():
            prompt = LLMClient()._build_prompt(
                "欢迎参加本次会议。",
                "Welcome to the conference.",
                "中→英",
                {"dimensions": ["信息完整度"]},
            )
        self.assertIn("目标语语言：英语", prompt)
        self.assertIn("严格按照英语的表达规范", prompt)

    def test_asr_language_must_match_direction(self):
        practice = self.client.post(
            "/api/practices",
            json={"source_text": "欢迎参加本次会议。", "direction": "中→英"},
        ).get_json()["practice"]

        response = self.client.post(
            f"/api/practices/{practice['id']}/audio",
            data={
                "audio": (io.BytesIO(b"mock pcm audio"), "practice.pcm"),
                "lang": "zh-CN",
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 400)

    def test_unknown_direction_is_rejected(self):
        response = self.client.post(
            "/api/practices",
            json={"source_text": "test", "direction": "法→中"},
        )

        self.assertEqual(response.status_code, 400)

    def test_archive_creates_snapshot_and_feedback_log(self):
        practice = self.create_practice()
        evaluated = self.evaluate_practice(practice["id"], "Welcome to the conference.")
        version = evaluated["evaluation_version"]

        response = self.client.post(
            f"/api/practices/{practice['id']}/archive",
            json={
                "asr_text": version["asr_text"],
                "evaluation_version_id": version["id"],
            },
        )

        self.assertEqual(response.status_code, 201)
        payload = response.get_json()
        self.assertEqual(payload["practice"]["status"], "archived")
        self.assertEqual(payload["archive"]["source_text"], practice["source_text"])
        self.assertEqual(payload["archive"]["asr_text"], version["asr_text"])
        self.assertEqual(payload["archive"]["evaluation_version_id"], version["id"])
        feedback_rows = self.client.get("/api/feedback-logs").get_json()["feedback_logs"]
        linked = [row for row in feedback_rows if row["task_id"] == f"LP-{practice['id']}-V1"]
        self.assertEqual(len(linked), 1)
        self.assertEqual(linked[0]["raw_text"], version["feedback_text"])

        admin = self.admin_client()
        export = admin.get("/api/practices/export.csv")
        self.assertEqual(export.status_code, 200)
        csv_text = export.data.decode("utf-8-sig")
        self.assertIn("归档版本", csv_text)
        self.assertIn(practice["source_text"], csv_text)
        self.assertIn(version["asr_text"], csv_text)

    def test_reevaluation_preserves_history_and_requires_rearchive(self):
        practice = self.create_practice(source_text="本次会议讨论绿色发展。")
        first = self.evaluate_practice(practice["id"], "The meeting discusses green development.")
        first_version = first["evaluation_version"]
        self.client.post(
            f"/api/practices/{practice['id']}/archive",
            json={
                "asr_text": first_version["asr_text"],
                "evaluation_version_id": first_version["id"],
            },
        )

        second = self.evaluate_practice(
            practice["id"], "This meeting focuses on green and sustainable development."
        )
        second_version = second["evaluation_version"]
        self.assertEqual(second_version["version_number"], 2)
        self.assertEqual(second["practice"]["status"], "evaluated")

        detail = self.client.get(f"/api/practices/{practice['id']}").get_json()
        self.assertEqual([row["version_number"] for row in detail["evaluation_versions"]], [2, 1])
        self.assertEqual(detail["archive"]["evaluation_version_id"], first_version["id"])
        self.assertEqual(detail["latest_evaluation"]["id"], second_version["id"])

        response = self.client.post(
            f"/api/practices/{practice['id']}/archive",
            json={
                "asr_text": second_version["asr_text"],
                "evaluation_version_id": second_version["id"],
            },
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["archive"]["version_number"], 2)

        duplicate = self.client.post(
            f"/api/practices/{practice['id']}/archive",
            json={
                "asr_text": second_version["asr_text"],
                "evaluation_version_id": second_version["id"],
            },
        )
        self.assertEqual(duplicate.status_code, 200)
        feedback_rows = self.client.get("/api/feedback-logs").get_json()["feedback_logs"]
        linked = [row for row in feedback_rows if row["task_id"].startswith(f"LP-{practice['id']}-")]
        self.assertEqual(len(linked), 2)

        admin = self.admin_client()
        version_export = admin.get("/api/practices/evaluation-versions/export.csv")
        self.assertEqual(version_export.status_code, 200)
        csv_text = version_export.data.decode("utf-8-sig")
        self.assertIn("是否正式归档版本", csv_text)
        self.assertIn(first_version["asr_text"], csv_text)
        self.assertIn(second_version["asr_text"], csv_text)

    def test_archive_rejects_asr_edits_without_reevaluation(self):
        practice = self.create_practice()
        evaluated = self.evaluate_practice(practice["id"], "Welcome to the conference.")

        response = self.client.post(
            f"/api/practices/{practice['id']}/archive",
            json={
                "asr_text": "Edited after evaluation.",
                "evaluation_version_id": evaluated["evaluation_version"]["id"],
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("重新生成评价", response.get_json()["error"])

    def test_practice_detail_permissions_allow_owner_and_admin_only_without_assignment(self):
        practice = self.create_practice()
        self.assertEqual(self.client.get(f"/api/practices/{practice['id']}").status_code, 200)

        other_student = self.app.test_client()
        other_student.post(
            "/api/auth/student-login",
            json={"student_no": "other-student", "name": "其他学生"},
        )
        self.assertEqual(other_student.get(f"/api/practices/{practice['id']}").status_code, 403)

        teacher = self.app.test_client()
        teacher.post("/api/auth/teacher-login", json={"teacher_code": "teacher-demo"})
        self.assertEqual(teacher.get(f"/api/practices/{practice['id']}").status_code, 403)

        admin = self.admin_client()
        self.assertEqual(admin.get(f"/api/practices/{practice['id']}").status_code, 200)

    def test_legacy_evaluations_are_backfilled_once(self):
        practice = self.create_practice()
        with self.app.app_context():
            item = db.session.get(PracticeSession, practice["id"])
            item.status = "completed"
            db.session.add(
                PracticeResult(
                    session_id=item.id,
                    asr_text="Legacy ASR transcript.",
                    score="B",
                    feedback_text="旧版 AI 评价",
                    reference_translation="Legacy reference translation.",
                )
            )
            db.session.commit()

            self.assertEqual(backfill_practice_evaluation_versions(), 1)
            self.assertEqual(backfill_practice_evaluation_versions(), 0)
            versions = PracticeEvaluationVersion.query.filter_by(session_id=item.id).all()
            self.assertEqual(len(versions), 1)
            self.assertEqual(versions[0].version_number, 1)

        detail = self.client.get(f"/api/practices/{practice['id']}").get_json()
        self.assertEqual(detail["latest_evaluation"]["feedback_text"], "旧版 AI 评价")


if __name__ == "__main__":
    unittest.main()
