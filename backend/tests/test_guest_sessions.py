import io
import tempfile
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from backend.app import create_app
from backend.app.config import Config
from backend.app.guests import cleanup_expired_guests, guest_upload_dir, now
from backend.app.models import (
    AuditLog, ChatConversation, ChatTurn, FeedbackLog, GuestSession,
    PracticeArchive, PracticeEvaluationVersion, PracticeResult, PracticeSession,
    User, UserAccount, db,
)


class GuestSessionTestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()

        class TestConfig(Config):
            TESTING = True
            SECRET_KEY = "guest-tests"
            SQLALCHEMY_DATABASE_URI = "sqlite:///" + str(Path(self.directory.name) / "test.sqlite3")
            UPLOAD_DIR = Path(self.directory.name) / "uploads"
            USE_MOCK_SERVICES = True
            REQUIRE_PRACTICE_CONTEXT = True
            GUEST_SESSION_SECONDS = 7200

        self.app = create_app(TestConfig)
        with self.app.app_context():
            user = User(name="正式账号", role="admin")
            db.session.add(user)
            db.session.flush()
            self.admin_id = user.id
            account = UserAccount(user_id=user.id, login_id="admin")
            account.set_password("Password123", must_change=False)
            db.session.add(account)
            db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        self.app.extensions["guest_cleanup_stop"].set()
        worker = self.app.extensions.get("guest_cleanup_thread")
        if worker:
            worker.join(timeout=5)
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        self.directory.cleanup()

    def guest(self, client=None):
        response = (client or self.client).post("/api/auth/guest")
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertTrue((client or self.client).get_cookie("session").http_only)
        return response.get_json()["user"]

    def practice(self, client=None):
        response = (client or self.client).post("/api/practices", json={
            "source_text": "Hello.", "direction": "英→中",
            "class_id": 999, "course_id": 999,
        })
        self.assertEqual(response.status_code, 201, response.get_json())
        self.assertIsNone(response.get_json()["practice"]["context"])
        return response.get_json()["practice"]["id"]

    def conversation(self, client=None):
        response = (client or self.client).post("/api/llm/conversations")
        self.assertEqual(response.status_code, 201)
        return response.get_json()["conversation"]["id"]

    def expire(self):
        with self.app.app_context():
            GuestSession.query.update({"expires_at": now() - timedelta(seconds=1)})
            db.session.commit()

    def assert_empty(self):
        with self.app.app_context():
            for model in (GuestSession, PracticeSession, PracticeResult, PracticeArchive,
                          PracticeEvaluationVersion, FeedbackLog, ChatConversation, ChatTurn):
                self.assertEqual(model.query.count(), 0, model.__name__)
            self.assertEqual(User.query.count(), 1)
            self.assertEqual(UserAccount.query.count(), 1)
            self.assertIsNotNone(db.session.get(User, self.admin_id))
        root = Path(self.directory.name) / "uploads" / "guests"
        self.assertFalse(root.exists() and list(root.iterdir()))

    def test_guest_refresh_and_reentry_keep_fixed_expiry_and_no_account(self):
        self.assertEqual(self.client.get("/api/practices").status_code, 401)
        user = self.guest()
        self.assertTrue(user["is_guest"])
        self.assertEqual(user["role"], "guest")
        self.assertIsNone(user["login_id"])
        self.assertEqual(self.client.get("/api/auth/me").get_json()["user"], user)
        self.assertEqual(self.guest(), user)
        with self.app.app_context():
            row = GuestSession.query.one()
            self.assertAlmostEqual((row.expires_at - now()).total_seconds(), 7200, delta=5)
            self.assertEqual(UserAccount.query.count(), 1)

    def test_all_learning_features_work_and_management_is_denied(self):
        self.guest()
        for url in ("/api/prompt-presets", "/api/stats/summary", "/api/feedback-logs"):
            self.assertEqual(self.client.get(url).status_code, 200)
        for url, payload in (
            ("/api/tts", {"text": "你好", "lang": "zh-CN"}),
            ("/api/prompt/build", {}),
            ("/api/feedback/parse", {"raw_text": "建议：继续练习"}),
        ):
            self.assertEqual(self.client.post(url, json=payload).status_code, 200)
        self.practice()
        response = self.client.post("/api/feedback-logs", json={"raw_text": "建议：继续练习", "user_id": self.admin_id})
        self.assertEqual(response.status_code, 201)
        self.assertNotEqual(response.get_json()["feedback_log"]["user_id"], self.admin_id)
        for url in ("/api/admin/overview", "/api/admin/system/settings", "/api/auth/me/students", "/api/practices/export.csv"):
            self.assertEqual(self.client.get(url).status_code, 403, url)
        self.assertEqual(self.client.post("/api/auth/change-password", json={}).status_code, 403)

    def test_other_guests_and_admin_cannot_read_trial_records(self):
        self.guest()
        practice_id = self.practice()
        conversation_id = self.conversation()
        self.client.post("/api/feedback-logs", json={"raw_text": "private"})
        other = self.app.test_client()
        self.guest(other)
        admin = self.app.test_client()
        admin.post("/api/auth/login", json={"login_id": "admin", "password": "Password123"})
        for client in (other, admin):
            self.assertEqual(client.get("/api/practices").get_json()["practices"], [])
            self.assertEqual(client.get("/api/feedback-logs").get_json()["feedback_logs"], [])
            self.assertEqual(client.get("/api/stats/summary").get_json()["total_practices"], 0)
            self.assertEqual(client.get(f"/api/practices/{practice_id}").status_code, 403)
            self.assertEqual(client.get(f"/api/llm/conversations/{conversation_id}").status_code, 404)
        self.assertEqual(admin.post("/api/auth/guest").status_code, 409)

    def test_expiry_removes_chat_archives_feedback_and_all_recording_versions(self):
        user = self.guest()
        practice_id = self.practice()
        for _ in range(2):
            response = self.client.post(f"/api/practices/{practice_id}/audio", data={
                "audio": (io.BytesIO(b"pcm-data"), "recording.pcm"), "lang": "zh-CN",
            })
            self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.post(f"/api/practices/{practice_id}/evaluate", json={"asr_text": "你好"}).status_code, 200)
        self.assertEqual(self.client.post(f"/api/practices/{practice_id}/archive", json={}).status_code, 201)
        conversation_id = self.conversation()
        response = self.client.post("/api/llm/chat", json={"conversation_id": conversation_id,
            "request_id": str(uuid.uuid4()), "expected_version": 0, "message": "hello"})
        self.assertEqual(response.status_code, 200)
        with self.app.app_context():
            key = GuestSession.query.one().token_hash
            self.assertEqual(len(list(guest_upload_dir(key).iterdir())), 2)
        self.expire()
        response = self.client.get("/api/llm/conversations")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.get_json()["code"], "GUEST_SESSION_EXPIRED")
        self.assert_empty()
        with self.app.app_context():
            self.assertEqual(AuditLog.query.filter_by(actor_id=user["id"]).count(), 0)

    def test_logout_revokes_copied_token_and_new_trial_starts_empty(self):
        self.guest()
        self.practice()
        cookie = self.client.get_cookie("session").value
        self.assertEqual(self.client.post("/api/auth/logout").status_code, 200)
        self.assert_empty()
        replay = self.app.test_client()
        replay.set_cookie("session", cookie)
        self.assertEqual(replay.get("/api/practices").status_code, 401)
        self.guest()
        self.assertEqual(self.client.get("/api/practices").get_json()["practices"], [])

    def test_successful_login_cleans_guest_but_failed_login_preserves_it(self):
        guest = self.guest()
        self.practice()
        self.assertEqual(self.client.post("/api/auth/login", json={"login_id": "admin", "password": "wrong"}).status_code, 401)
        self.assertEqual(self.client.get("/api/auth/me").get_json()["user"]["id"], guest["id"])
        self.assertEqual(self.client.post("/api/auth/login", json={"login_id": "admin", "password": "Password123"}).status_code, 200)
        self.assert_empty()
        self.assertEqual(self.client.get("/api/auth/me").get_json()["user"]["role"], "admin")

    def test_expired_inflight_chat_reply_is_discarded(self):
        self.guest()
        conversation_id = self.conversation()

        def late_reply(*args):
            self.expire()
            return {"message": "must not be saved"}

        with patch("backend.app.api.chat.LLMClient.chat", side_effect=late_reply):
            response = self.client.post("/api/llm/chat", json={"conversation_id": conversation_id,
                "request_id": str(uuid.uuid4()), "expected_version": 0, "message": "hello"})
        self.assertEqual(response.status_code, 401)
        self.assert_empty()

    def test_expired_inflight_audio_is_deleted(self):
        self.guest()
        practice_id = self.practice()

        def late_transcript(*args):
            self.expire()
            return {"transcript": "must not be saved"}

        with patch("backend.app.api.practice.ASRClient.transcribe", side_effect=late_transcript):
            response = self.client.post(f"/api/practices/{practice_id}/audio", data={
                "audio": (io.BytesIO(b"pcm-data"), "recording.pcm"), "lang": "zh-CN",
            })
        self.assertEqual(response.status_code, 401)
        self.assert_empty()

    def test_concurrent_cleanup_and_idle_cleanup_do_not_need_guest_requests(self):
        self.guest()
        self.practice()
        self.expire()

        def sweep():
            with self.app.app_context():
                return cleanup_expired_guests()

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(lambda _: sweep(), range(2))), 1)
        self.assert_empty()
        self.app.testing = False
        self.guest()
        self.expire()
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            with self.app.app_context():
                if GuestSession.query.count() == 0:
                    break
            time.sleep(0.05)
        self.assert_empty()

    def test_forged_guest_token_cannot_claim_another_identity(self):
        user = self.guest()
        with self.client.session_transaction() as cookie:
            cookie["guest_token"] = "forged"
            cookie["user_id"] = user["id"]
        self.assertEqual(self.client.get("/api/practices").status_code, 401)
        with self.app.app_context():
            self.assertEqual(GuestSession.query.count(), 1)

    def test_renewal_extends_deadline_and_preserves_existing_data(self):
        user = self.guest()
        practice_id = self.practice()
        conversation_id = self.conversation()
        timestamp = now()
        with patch("backend.app.guests.now", return_value=timestamp + timedelta(hours=1)):
            response = self.client.post("/api/auth/guest/renew")
        self.assertEqual(response.status_code, 200)
        renewed = response.get_json()["user"]
        self.assertEqual(renewed["id"], user["id"])
        self.assertEqual(renewed["guest_session_id"], user["guest_session_id"])
        self.assertGreater(renewed["guest_expires_at"], user["guest_expires_at"])
        # Passing the old deadline must not delete a successfully renewed session.
        with patch("backend.app.guests.now", return_value=timestamp + timedelta(hours=2, minutes=1)):
            self.assertEqual(self.client.get(f"/api/practices/{practice_id}").status_code, 200)
            self.assertEqual(self.client.get(f"/api/llm/conversations/{conversation_id}").status_code, 200)
        with self.app.app_context():
            self.assertEqual(GuestSession.query.count(), 1)
            self.assertEqual(User.query.count(), 2)

    def test_renewal_cannot_resurrect_expired_or_logged_out_trials(self):
        self.guest()
        self.practice()
        cookie = self.client.get_cookie("session").value
        self.expire()
        self.assertEqual(self.client.post("/api/auth/guest/renew").status_code, 401)
        self.assert_empty()
        self.client.set_cookie("session", cookie)
        self.assertEqual(self.client.post("/api/auth/guest/renew").status_code, 401)
        self.guest()
        cookie = self.client.get_cookie("session").value
        self.client.post("/api/auth/logout")
        self.client.set_cookie("session", cookie)
        self.assertEqual(self.client.post("/api/auth/guest/renew").status_code, 401)
        self.assert_empty()
        self.client.post("/api/auth/login", json={"login_id": "admin", "password": "Password123"})
        self.assertEqual(self.client.post("/api/auth/guest/renew").status_code, 403)

    def test_cleanup_keeps_active_guests_and_regular_account_data(self):
        expired_user = self.guest()
        self.practice()
        active = self.app.test_client()
        active_user = self.guest(active)
        active_practice = self.practice(active)
        with self.app.app_context():
            record = PracticeSession(user_id=self.admin_id, direction="英→中", source_text="formal record")
            db.session.add(record)
            GuestSession.query.filter_by(user_id=expired_user["id"]).update({"expires_at": now() - timedelta(seconds=1)})
            db.session.commit()
            formal_id = record.id
            cleanup_expired_guests()
            self.assertIsNotNone(db.session.get(PracticeSession, formal_id))
            self.assertIsNotNone(db.session.get(User, active_user["id"]))
            self.assertEqual(GuestSession.query.count(), 1)
        self.assertEqual(active.get(f"/api/practices/{active_practice}").status_code, 200)

    def test_failed_uploads_and_orphan_files_are_also_cleaned(self):
        self.guest()
        practice_id = self.practice()
        with self.app.app_context():
            key = GuestSession.query.one().token_hash
        with patch("backend.app.api.practice.ASRClient.transcribe", side_effect=RuntimeError("ASR unavailable")):
            with self.assertRaises(RuntimeError):
                self.client.post(f"/api/practices/{practice_id}/audio", data={
                    "audio": (io.BytesIO(b"pcm-data"), "recording.pcm"), "lang": "zh-CN",
                })
        self.client.post("/api/auth/logout")
        self.assert_empty()
        with self.app.app_context():
            directory = guest_upload_dir(key)
            directory.mkdir(parents=True)
            (directory / "late-recording.pcm").write_bytes(b"old data")
            cleanup_expired_guests()
            self.assertFalse(directory.exists())


if __name__ == "__main__":
    unittest.main()
