import io
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from backend.app import create_app
from backend.app.config import Config
from backend.app.models import (
    AcademicTerm,
    ClassGroup,
    Course,
    CourseEnrollment,
    TeachingAssignment,
    User,
    UserAccount,
    db,
)


class AccessControlTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.upload_dir = tempfile.TemporaryDirectory()

        class TestConfig(Config):
            TESTING = True
            SECRET_KEY = "access-control-test"
            SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
            USE_MOCK_SERVICES = True
            UPLOAD_DIR = Path(cls.upload_dir.name)
            REQUIRE_PRACTICE_CONTEXT = True

        cls.app = create_app(TestConfig)
        with cls.app.app_context():
            term = AcademicTerm(code="2026-FALL", name="2026 秋季")
            db.session.add(term)
            db.session.flush()
            class_a = ClassGroup(term_id=term.id, code="A", name="A班")
            class_b = ClassGroup(term_id=term.id, code="B", name="B班")
            course = Course(term_id=term.id, code="INT101", name="基础口译")
            db.session.add_all([class_a, class_b, course])
            db.session.flush()

            cls.ids = {
                "term": term.id,
                "class_a": class_a.id,
                "class_b": class_b.id,
                "course": course.id,
            }
            admin = cls._add_user("admin", "管理员", "admin", "AdminPass123")
            teacher_a = cls._add_user("teacher-a", "甲班教师", "teacher", "TeacherPass123")
            teacher_b = cls._add_user("teacher-b", "乙班教师", "teacher", "TeacherPass123")
            student_a = cls._add_user("student-a", "甲班学生", "student", "StudentPass123")
            student_b = cls._add_user("student-b", "乙班学生", "student", "StudentPass123")
            reset_user = cls._add_user("reset-user", "待重置学生", "student", "StudentPass123")
            cls.ids.update(
                {
                    "admin": admin.id,
                    "teacher_a": teacher_a.id,
                    "teacher_b": teacher_b.id,
                    "student_a": student_a.id,
                    "student_b": student_b.id,
                    "reset_user": reset_user.id,
                }
            )
            db.session.add_all(
                [
                    CourseEnrollment(
                        student_id=student_a.id, class_id=class_a.id, course_id=course.id
                    ),
                    CourseEnrollment(
                        student_id=student_b.id, class_id=class_b.id, course_id=course.id
                    ),
                    CourseEnrollment(
                        student_id=reset_user.id, class_id=class_a.id, course_id=course.id
                    ),
                    TeachingAssignment(
                        teacher_id=teacher_a.id, class_id=class_a.id, course_id=course.id
                    ),
                    TeachingAssignment(
                        teacher_id=teacher_b.id, class_id=class_b.id, course_id=course.id
                    ),
                ]
            )
            db.session.commit()

        cls.practice_a = cls._create_archived_practice(
            "student-a", "StudentPass123", cls.ids["class_a"], "甲班专属练习"
        )
        cls.practice_b = cls._create_archived_practice(
            "student-b", "StudentPass123", cls.ids["class_b"], "乙班专属练习"
        )

    @classmethod
    def tearDownClass(cls):
        cls.upload_dir.cleanup()

    @classmethod
    def _add_user(cls, login_id, name, role, password):
        user = User(
            student_no=login_id if role != "admin" else None,
            name=name,
            role=role,
        )
        db.session.add(user)
        db.session.flush()
        account = UserAccount(user_id=user.id, login_id=login_id)
        account.set_password(password, must_change=False)
        db.session.add(account)
        return user

    @classmethod
    def _login(cls, login_id, password):
        client = cls.app.test_client()
        response = client.post(
            "/api/auth/login", json={"login_id": login_id, "password": password}
        )
        if response.status_code != 200:
            raise AssertionError(response.get_json())
        return client

    @classmethod
    def _create_archived_practice(cls, login_id, password, class_id, source_text):
        client = cls._login(login_id, password)
        practice_response = client.post(
            "/api/practices",
            json={
                "source_text": source_text,
                "direction": "中→英",
                "class_id": class_id,
                "course_id": cls.ids["course"],
            },
        )
        if practice_response.status_code != 201:
            raise AssertionError(practice_response.get_json())
        practice = practice_response.get_json()["practice"]
        evaluated = client.post(
            f"/api/practices/{practice['id']}/evaluate",
            json={"asr_text": f"English transcript for {source_text}"},
        ).get_json()
        version = evaluated["evaluation_version"]
        archive = client.post(
            f"/api/practices/{practice['id']}/archive",
            json={"asr_text": version["asr_text"], "evaluation_version_id": version["id"]},
        )
        if archive.status_code != 201:
            raise AssertionError(archive.get_json())
        return practice

    def test_student_can_only_read_own_practice(self):
        student = self._login("student-a", "StudentPass123")
        self.assertEqual(student.get(f"/api/practices/{self.practice_a['id']}").status_code, 200)
        self.assertEqual(student.get(f"/api/practices/{self.practice_b['id']}").status_code, 403)
        rows = student.get("/api/practices").get_json()["practices"]
        self.assertEqual({row["id"] for row in rows}, {self.practice_a["id"]})

    def test_teacher_list_detail_stats_feedback_and_exports_are_class_scoped(self):
        teacher = self._login("teacher-a", "TeacherPass123")
        rows = teacher.get("/api/practices").get_json()["practices"]
        self.assertEqual({row["id"] for row in rows}, {self.practice_a["id"]})
        managed = teacher.get("/api/auth/me/students").get_json()["student_contexts"]
        self.assertEqual(
            {row["student"]["student_no"] for row in managed},
            {"student-a", "reset-user"},
        )
        self.assertEqual(teacher.get(f"/api/practices/{self.practice_a['id']}").status_code, 200)
        self.assertEqual(teacher.get(f"/api/practices/{self.practice_b['id']}").status_code, 403)

        summary = teacher.get("/api/stats/summary").get_json()
        self.assertEqual(summary["total_practices"], 1)
        feedback_rows = teacher.get("/api/feedback-logs").get_json()["feedback_logs"]
        self.assertEqual({row["student_no"] for row in feedback_rows}, {"student-a"})

        practice_csv = teacher.get("/api/practices/export.csv").data.decode("utf-8-sig")
        self.assertIn("甲班专属练习", practice_csv)
        self.assertNotIn("乙班专属练习", practice_csv)
        version_csv = teacher.get("/api/practices/evaluation-versions/export.csv").data.decode(
            "utf-8-sig"
        )
        self.assertIn("甲班专属练习", version_csv)
        self.assertNotIn("乙班专属练习", version_csv)
        feedback_csv = teacher.get("/api/feedback-logs/export.csv").data.decode("utf-8-sig")
        self.assertIn("student-a", feedback_csv)
        self.assertNotIn("student-b", feedback_csv)

    def test_admin_can_read_all_practices(self):
        admin = self._login("admin", "AdminPass123")
        rows = admin.get("/api/practices").get_json()["practices"]
        self.assertEqual(
            {row["id"] for row in rows}, {self.practice_a["id"], self.practice_b["id"]}
        )

    def test_admin_account_list_excludes_legacy_users_without_credentials(self):
        with self.app.app_context():
            legacy = User(
                student_no="legacy-overview-only",
                name="兼容入口用户",
                role="student",
            )
            db.session.add(legacy)
            db.session.commit()
            legacy_id = legacy.id
        try:
            admin = self._login("admin", "AdminPass123")
            users = admin.get("/api/admin/overview").get_json()["users"]
            self.assertNotIn(legacy_id, {user["id"] for user in users})
            self.assertTrue(all(user["login_id"] for user in users))
        finally:
            with self.app.app_context():
                db.session.delete(db.session.get(User, legacy_id))
                db.session.commit()

    def test_teacher_cannot_create_student_practice(self):
        teacher = self._login("teacher-a", "TeacherPass123")
        response = teacher.post(
            "/api/practices",
            json={"source_text": "not allowed", "direction": "中→英"},
        )
        self.assertEqual(response.status_code, 403)

    def test_password_hash_disable_reset_and_mandatory_change(self):
        with self.app.app_context():
            account = UserAccount.query.filter_by(login_id="reset-user").first()
            self.assertNotEqual(account.password_hash, "StudentPass123")
            self.assertNotIn("StudentPass123", account.password_hash)

        previous_session = self._login("reset-user", "StudentPass123")
        admin = self._login("admin", "AdminPass123")
        reset = admin.post(f"/api/admin/users/{self.ids['reset_user']}/reset-password", json={})
        self.assertEqual(reset.status_code, 200)
        temporary_password = reset.get_json()["initial_password"]
        self.assertEqual(previous_session.get("/api/practices").status_code, 401)

        reset_client = self._login("reset-user", temporary_password)
        blocked = reset_client.get("/api/practices")
        self.assertEqual(blocked.status_code, 403)
        changed = reset_client.post(
            "/api/auth/change-password",
            json={"current_password": temporary_password, "new_password": "NewStudentPass456"},
        )
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(reset_client.get("/api/practices").status_code, 200)

        disabled = admin.patch(
            f"/api/admin/users/{self.ids['reset_user']}", json={"is_active": False}
        )
        self.assertEqual(disabled.status_code, 200)
        relogin = self.app.test_client().post(
            "/api/auth/login",
            json={"login_id": "reset-user", "password": "NewStudentPass456"},
        )
        self.assertEqual(relogin.status_code, 403)

    def test_csv_import_creates_hashed_student_account_and_enrollment(self):
        admin = self._login("admin", "AdminPass123")
        csv_data = (
            "学号,姓名,班级,课程,学期\n"
            "20260001,导入学生,C班,高级口译,2027春季\n"
        ).encode("utf-8-sig")
        response = admin.post(
            "/api/admin/students/import",
            data={"file": (io.BytesIO(csv_data), "students.csv")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["count"], 1)
        password = payload["imported"][0]["initial_password"]
        self.assertTrue(password)
        with self.app.app_context():
            account = UserAccount.query.filter_by(login_id="20260001").first()
            self.assertIsNotNone(account)
            self.assertTrue(account.check_password(password))
            self.assertTrue(account.must_change_password)
            self.assertEqual(CourseEnrollment.query.filter_by(student_id=account.user_id).count(), 1)

    def test_xlsx_import_creates_student_account(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["学号", "姓名", "班级", "课程", "学期"])
        sheet.append([20260002, "Excel导入学生", "D班", "会议口译", "2027春季"])
        content = io.BytesIO()
        workbook.save(content)
        content.seek(0)

        admin = self._login("admin", "AdminPass123")
        response = admin.post(
            "/api/admin/students/import",
            data={"file": (content, "students.xlsx")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["count"], 1)
        with self.app.app_context():
            account = UserAccount.query.filter_by(login_id="20260002").first()
            self.assertIsNotNone(account)

    def test_z_assignment_revocation_removes_teacher_access_immediately(self):
        with self.app.app_context():
            assignment = TeachingAssignment.query.filter_by(
                teacher_id=self.ids["teacher_b"],
                class_id=self.ids["class_b"],
                course_id=self.ids["course"],
            ).first()
            assignment_id = assignment.id

        teacher = self._login("teacher-b", "TeacherPass123")
        self.assertEqual(teacher.get(f"/api/practices/{self.practice_b['id']}").status_code, 200)
        admin = self._login("admin", "AdminPass123")
        response = admin.patch(
            f"/api/admin/teaching-assignments/{assignment_id}",
            json={"is_active": False},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(teacher.get(f"/api/practices/{self.practice_b['id']}").status_code, 403)


if __name__ == "__main__":
    unittest.main()
