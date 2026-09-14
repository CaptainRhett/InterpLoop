import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from flask import Flask

from backend.app import create_app
from backend.app.config import Config
from backend.app.models import User, UserAccount, db, PracticeEvaluationVersion
from backend.app.services.evaluation import EvaluationFormatError, normalize_evaluation, parse_evaluation, feedback_fields
from backend.app.services.feedback_parser import parse_feedback_text
from backend.app.services.llm import LLMClient
from backend.app.api.stats import _average_score


VALUE = {"score": 8.2, "overall": "主干信息准确，有一处遗漏。", "pros": ["总评中提到的术语使用准确。"],
         "cons": ["建议补充原文数字。"], "suggestions": ["问题定位后逐项核对数字。"],
         "reference_translation": "The total is ten."}


class EvaluationContractTestCase(unittest.TestCase):
    def test_fixed_text_and_native_archive_have_identical_fields(self):
        result = normalize_evaluation(VALUE, "test")
        parsed = parse_feedback_text(result["feedback_text"])
        self.assertEqual({key: parsed[key] for key in ("pros", "cons", "suggestions", "overall")},
                         feedback_fields(result["evaluation_json"]))
        self.assertNotIn(VALUE["reference_translation"], parsed["overall"])
        self.assertEqual(result["score"], "8.2")

    def test_invalid_scores_and_shapes_are_rejected_not_defaulted(self):
        for score in ("A", "8/10", 0, 11, True, float("nan"), float("inf"), None):
            with self.subTest(score=score), self.assertRaises(EvaluationFormatError):
                normalize_evaluation({**VALUE, "score": score}, "test")
        for change in ({"pros": []}, {"cons": "wrong"}, {"overall": ""}, {"suggestions": [2]}):
            with self.assertRaises(EvaluationFormatError):
                normalize_evaluation({**VALUE, **change}, "test")
        for text in ("评分：A", "[]", "{}"):
            with self.assertRaises(EvaluationFormatError):
                parse_evaluation(text)
        self.assertEqual(parse_evaluation('```json\n' + json.dumps(VALUE) + '\n```')["score"], "8.2")

    def test_real_model_request_contains_both_texts_and_fixed_scale(self):
        app = Flask(__name__)
        app.config.from_object(Config)
        app.config.update(USE_MOCK_SERVICES=False, DOUBAO_API_KEY="test", DOUBAO_MODEL="test")
        with app.app_context(), patch("backend.app.services.llm.requests.post") as post:
            post.return_value.json.return_value = {"choices": [{"message": {"content": json.dumps(VALUE)}}]}
            result = LLMClient().evaluate("原文材料", "学生识别文本", "中→英", {})
            request = post.call_args.kwargs["json"]
            prompt = request["messages"][1]["content"]
            self.assertIn("原文材料", prompt)
            self.assertIn("学生识别文本", prompt)
            self.assertIn("1–10", prompt)
            self.assertIn('"cons"', prompt)
            self.assertEqual(request["temperature"], 0)
            self.assertEqual(result["score"], "8.2")

    def test_average_normalizes_numeric_and_historical_scores(self):
        rows = [SimpleNamespace(archive=None, result=SimpleNamespace(score=score)) for score in ("8", "B+", "bad")]
        self.assertEqual(_average_score(rows), {"label": "8/10", "numeric": 8.0})


class SegmentedPracticeTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.uploads = tempfile.TemporaryDirectory()
        class TestConfig(Config):
            TESTING = True
            SECRET_KEY = "segment-test"
            SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
            UPLOAD_DIR = Path(cls.uploads.name)
            USE_MOCK_SERVICES = True
            REQUIRE_PRACTICE_CONTEXT = False
        cls.app = create_app(TestConfig)
        with cls.app.app_context():
            user = User(name="逐句测试", role="student", student_no="segment-test")
            db.session.add(user)
            db.session.flush()
            account = UserAccount(user_id=user.id, login_id="segment-test")
            account.set_password("TestPass123", must_change=False)
            db.session.add(account)
            db.session.commit()

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            db.session.remove()
            db.engine.dispose()
        cls.uploads.cleanup()

    def setUp(self):
        self.client = self.app.test_client()
        self.client.post("/api/auth/login", json={"login_id": "segment-test", "password": "TestPass123"})
        response = self.client.post("/api/practices", json={"source_text": "第一句。第二句。", "direction": "中→英",
            "prompt_params": {"source_segments": ["第一句。", "第二句。"]}})
        self.assertEqual(response.status_code, 201)
        self.practice_id = response.get_json()["practice"]["id"]

    def upload(self, index, text):
        with patch("backend.app.api.practice.ASRClient.transcribe", return_value={"transcript": text, "segments": []}):
            return self.client.post(f"/api/practices/{self.practice_id}/audio", data={
                "audio": (io.BytesIO(b"pcm"), "sentence.pcm"), "lang": "en-US", "segment_index": str(index)})

    def test_segments_accumulate_rerecord_replace_and_archive_structured_feedback(self):
        first = self.upload(0, "First.")
        self.assertEqual(first.status_code, 200)
        premature = self.client.post(f"/api/practices/{self.practice_id}/evaluate", json={"asr_text": "First."})
        self.assertEqual(premature.status_code, 400)
        self.upload(0, "First corrected.")
        second = self.upload(1, "Second.")
        result = second.get_json()["practice"]["result"]
        self.assertEqual(result["asr_text"], "First corrected.\nSecond.")
        self.assertEqual(len(result["asr_segments"]), 2)
        self.assertEqual(result["asr_segments"][0]["source_text"], "第一句。")
        self.assertNotEqual(result["asr_segments"][0]["audio_path"], result["asr_segments"][1]["audio_path"])
        evaluation = self.client.post(f"/api/practices/{self.practice_id}/evaluate", json={}).get_json()
        self.assertEqual(evaluation["evaluation_version"]["asr_text"], result["asr_text"])
        self.assertTrue(1 <= float(evaluation["evaluation"]["score"]) <= 10)
        archive = self.client.post(f"/api/practices/{self.practice_id}/archive", json={})
        self.assertEqual(archive.status_code, 201)
        logs = self.client.get("/api/feedback-logs").get_json()["feedback_logs"]
        log = next(row for row in logs if row["task_id"] == f"LP-{self.practice_id}-V1")
        expected = feedback_fields(evaluation["evaluation"]["evaluation_json"])
        for key, value in expected.items():
            self.assertEqual(log[key], value)

    def test_out_of_order_invalid_index_and_mismatched_source_are_rejected(self):
        for index in (1, -1, 2, "bad"):
            self.assertEqual(self.upload(index, "bad").status_code, 400)
        response = self.client.post("/api/practices", json={"source_text": "完整原文。", "prompt_params": {"source_segments": ["不相符。"]}})
        self.assertEqual(response.status_code, 400)

    def test_invalid_ai_response_does_not_create_evaluation_version(self):
        self.upload(0, "First.")
        self.upload(1, "Second.")
        with patch("backend.app.api.practice.LLMClient.evaluate", side_effect=EvaluationFormatError("score")):
            response = self.client.post(f"/api/practices/{self.practice_id}/evaluate", json={})
        self.assertEqual(response.status_code, 502)
        with self.app.app_context():
            self.assertEqual(PracticeEvaluationVersion.query.filter_by(session_id=self.practice_id).count(), 0)
