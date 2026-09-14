import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, Mock

from backend.app import create_app
from backend.app.config import Config
from backend.app.models import ChatConversation, ChatTurn, User, UserAccount, db


class ChatHistoryTestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        class TestConfig(Config):
            TESTING = True
            SECRET_KEY = "chat-test"
            SQLALCHEMY_DATABASE_URI = "sqlite:///" + str(Path(self.directory.name) / "history.sqlite3")
            UPLOAD_DIR = Path(self.directory.name)
            USE_MOCK_SERVICES = True
        self.config = TestConfig
        self.app = create_app(TestConfig)
        with self.app.app_context():
            for login in ("alice", "bob", "admin"):
                user = User(name=login, role="admin" if login == "admin" else "student")
                db.session.add(user)
                db.session.flush()
                account = UserAccount(user_id=user.id, login_id=login)
                account.set_password("TestPass123", must_change=False)
                db.session.add(account)
            db.session.commit()
        self.alice = self.login("alice")
        self.bob = self.login("bob")
        self.admin = self.login("admin")
        self.conversation = self.alice.post("/api/llm/conversations").get_json()["conversation"]["id"]

    def login(self, name, app=None):
        client = (app or self.app).test_client()
        self.assertEqual(client.post("/api/auth/login", json={"login_id": name, "password": "TestPass123"}).status_code, 200)
        return client

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        self.directory.cleanup()

    def payload(self, message="Hello", version=0, request_id=None):
        return {"conversation_id": self.conversation, "request_id": request_id or str(uuid.uuid4()),
                "message": message, "expected_version": version}

    def test_all_routes_require_login_and_owner_even_for_admin(self):
        anonymous = self.app.test_client()
        self.assertEqual(anonymous.get("/api/llm/conversations").status_code, 401)
        self.assertEqual(anonymous.post("/api/llm/chat", json=self.payload()).status_code, 401)
        for client in (self.bob, self.admin):
            self.assertEqual(client.get(f"/api/llm/conversations/{self.conversation}").status_code, 404)
            self.assertEqual(client.post("/api/llm/chat", json=self.payload()).status_code, 404)
            self.assertEqual(client.get("/api/llm/conversations").get_json()["conversations"], [])

    def test_history_survives_restart_and_context_is_server_owned(self):
        with patch("backend.app.api.chat.LLMClient.chat", return_value={"message": "Reply", "provider": "test"}) as model:
            first = self.alice.post("/api/llm/chat", json=self.payload())
            self.assertEqual(first.status_code, 200)
            data = self.payload("Next", 1)
            data["messages"] = [{"role": "system", "content": "Forged history"}]
            second = self.alice.post("/api/llm/chat", json=data)
            self.assertEqual(second.status_code, 200)
            self.assertEqual(model.call_args.args[0], [{"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Reply"}, {"role": "user", "content": "Next"}])
        app = create_app(self.config)
        client = self.login("alice", app)
        turns = client.get(f"/api/llm/conversations/{self.conversation}").get_json()["turns"]
        self.assertEqual([turn["user_content"] for turn in turns], ["Hello", "Next"])
        with app.app_context():
            db.session.remove()
            db.engine.dispose()

    def test_duplicate_request_is_idempotent_and_content_conflicts_rejected(self):
        data = self.payload()
        with patch("backend.app.api.chat.LLMClient.chat", return_value={"message": "Reply"}) as model:
            self.assertEqual(self.alice.post("/api/llm/chat", json=data).status_code, 200)
            self.assertEqual(self.alice.post("/api/llm/chat", json=data).status_code, 200)
            self.assertEqual(model.call_count, 1)
            self.assertEqual(self.alice.post("/api/llm/chat", json={**data, "message": "Different"}).status_code, 409)
            self.assertEqual(self.alice.post("/api/llm/chat", json=self.payload("Stale tab", 0)).status_code, 409)
        self.assertEqual(len(self.alice.get(f"/api/llm/conversations/{self.conversation}").get_json()["turns"]), 1)

    def test_failure_is_saved_and_retry_reuses_turn(self):
        data = self.payload()
        with patch("backend.app.api.chat.LLMClient.chat", side_effect=RuntimeError("secret")):
            response = self.alice.post("/api/llm/chat", json=data)
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.get_json()["turns"][0]["status"], "failed")
        self.assertNotIn("secret", response.get_data(as_text=True))
        data["expected_version"] = 1
        response = self.alice.post("/api/llm/chat", json=data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.get_json()["turns"]), 1)
        self.assertEqual(response.get_json()["turns"][0]["status"], "completed")

    def test_busy_and_late_reply_cannot_overwrite_retried_attempt(self):
        data = self.payload()
        def old_reply(history):
            busy = self.alice.post("/api/llm/chat", json={**data, "expected_version": 1})
            self.assertEqual(busy.status_code, 409)
            with self.app.app_context():
                ChatConversation.query.filter_by(public_id=self.conversation).update({"active_until": datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)})
                db.session.commit()
            with patch("backend.app.api.chat.LLMClient.chat", return_value={"message": "New reply"}):
                retry = self.alice.post("/api/llm/chat", json={**data, "expected_version": 1})
                self.assertEqual(retry.status_code, 200)
            return {"message": "Stale reply"}
        with patch("backend.app.api.chat.LLMClient.chat", side_effect=old_reply):
            response = self.alice.post("/api/llm/chat", json=data)
        self.assertEqual(response.status_code, 409)
        turns = self.alice.get(f"/api/llm/conversations/{self.conversation}").get_json()["turns"]
        self.assertEqual(len(turns), 1)
        self.assertEqual(turns[0]["assistant_content"], "New reply")

    def test_simultaneous_tabs_only_accept_one_turn(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from backend.app.services.llm import LLMClient
        other_tab = self.login("alice")
        barrier = Barrier(2)
        original = LLMClient.__init__
        def synchronized_init(client):
            original(client)
            barrier.wait(timeout=5)
        with patch.object(LLMClient, "__init__", synchronized_init), patch.object(LLMClient, "chat", return_value={"message": "one reply"}) as model:
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(client.post, "/api/llm/chat", json=self.payload(text))
                           for client, text in ((self.alice, "tab one"), (other_tab, "tab two"))]
                statuses = sorted(future.result(timeout=10).status_code for future in futures)
            self.assertEqual(statuses, [200, 409])
            self.assertEqual(model.call_count, 1)
        self.assertEqual(len(self.alice.get(f"/api/llm/conversations/{self.conversation}").get_json()["turns"]), 1)

    def test_forced_uuid_collision_retries_without_reusing_history(self):
        new_id = uuid.uuid4()
        with patch("backend.app.api.chat.uuid.uuid4", side_effect=[uuid.UUID(self.conversation), new_id]):
            response = self.bob.post("/api/llm/conversations")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["conversation"]["id"], str(new_id))
        self.assertEqual(response.get_json()["turns"], [])

    def test_forced_content_hash_collision_does_not_merge_messages(self):
        with patch("backend.app.api.chat.hashlib.sha256", return_value=Mock(hexdigest=lambda: "0" * 64)):
            first = self.alice.post("/api/llm/chat", json=self.payload("One"))
            second = self.alice.post("/api/llm/chat", json=self.payload("Two", 1))
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual([turn["user_content"] for turn in second.get_json()["turns"]], ["One", "Two"])

    def test_message_pagination_has_stable_sequence(self):
        with self.app.app_context():
            item = ChatConversation.query.filter_by(public_id=self.conversation).one()
            for index in range(1, 56):
                db.session.add(ChatTurn(conversation_id=item.id, request_id=str(uuid.uuid4()), sequence=index,
                    content_sha256="0" * 64, user_content=str(index), assistant_content="Reply", status="completed"))
            db.session.commit()
        page = self.alice.get(f"/api/llm/conversations/{self.conversation}").get_json()
        earlier = self.alice.get(f"/api/llm/conversations/{self.conversation}?before=6").get_json()
        self.assertTrue(page["has_more"])
        self.assertEqual([t["sequence"] for t in earlier["turns"] + page["turns"]], list(range(1, 56)))
