from datetime import datetime, timezone
from sqlalchemy import event
from sqlalchemy.engine import Engine
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()

def utcnow():
    return datetime.now(timezone.utc)


def configure_sqlite(db_obj):
    @event.listens_for(Engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        if dbapi_connection.__class__.__module__ != "sqlite3":
            return
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    student_no = db.Column(db.String(64), unique=True, nullable=True, index=True)
    name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="student")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    last_login_at = db.Column(db.DateTime(timezone=True), nullable=True)

    sessions = db.relationship("PracticeSession", back_populates="user")
    account = db.relationship(
        "UserAccount", back_populates="user", cascade="all, delete-orphan", uselist=False
    )

    def to_dict(self):
        return {
            "id": self.id,
            "student_no": self.student_no,
            "name": self.name,
            "role": self.role,
            "login_id": self.account.login_id if self.account else None,
            "is_active": self.account.is_active if self.account else True,
            "must_change_password": (
                self.account.must_change_password if self.account else False
            ),
        }


class UserAccount(db.Model):
    __tablename__ = "user_accounts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True, index=True
    )
    login_id = db.Column(db.String(120), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(512), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    must_change_password = db.Column(db.Boolean, nullable=False, default=True)
    session_version = db.Column(db.Integer, nullable=False, default=1)
    password_changed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    user = db.relationship("User", back_populates="account")

    def set_password(self, password, must_change=False):
        self.password_hash = generate_password_hash(password)
        self.must_change_password = must_change
        self.password_changed_at = utcnow()
        self.session_version = (self.session_version or 0) + 1

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "login_id": self.login_id,
            "is_active": self.is_active,
            "must_change_password": self.must_change_password,
            "password_changed_at": (
                self.password_changed_at.isoformat() if self.password_changed_at else None
            ),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AcademicTerm(db.Model):
    __tablename__ = "academic_terms"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(80), nullable=False, unique=True, index=True)
    name = db.Column(db.String(160), nullable=False)
    start_date = db.Column(db.Date, nullable=True)
    end_date = db.Column(db.Date, nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "is_active": self.is_active,
        }


class ClassGroup(db.Model):
    __tablename__ = "class_groups"
    __table_args__ = (
        db.UniqueConstraint("term_id", "code", name="uq_class_term_code"),
    )

    id = db.Column(db.Integer, primary_key=True)
    term_id = db.Column(db.Integer, db.ForeignKey("academic_terms.id"), nullable=False)
    code = db.Column(db.String(80), nullable=False, index=True)
    name = db.Column(db.String(160), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    term = db.relationship("AcademicTerm")

    def to_dict(self):
        return {
            "id": self.id,
            "term_id": self.term_id,
            "term": self.term.to_dict() if self.term else None,
            "code": self.code,
            "name": self.name,
            "is_active": self.is_active,
        }


class Course(db.Model):
    __tablename__ = "courses"
    __table_args__ = (
        db.UniqueConstraint("term_id", "code", name="uq_course_term_code"),
    )

    id = db.Column(db.Integer, primary_key=True)
    term_id = db.Column(db.Integer, db.ForeignKey("academic_terms.id"), nullable=False)
    code = db.Column(db.String(80), nullable=False, index=True)
    name = db.Column(db.String(160), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    term = db.relationship("AcademicTerm")

    def to_dict(self):
        return {
            "id": self.id,
            "term_id": self.term_id,
            "term": self.term.to_dict() if self.term else None,
            "code": self.code,
            "name": self.name,
            "is_active": self.is_active,
        }


class CourseEnrollment(db.Model):
    __tablename__ = "course_enrollments"
    __table_args__ = (
        db.UniqueConstraint(
            "student_id", "class_id", "course_id", name="uq_student_class_course"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    class_id = db.Column(
        db.Integer, db.ForeignKey("class_groups.id"), nullable=False, index=True
    )
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    student = db.relationship("User", foreign_keys=[student_id])
    class_group = db.relationship("ClassGroup")
    course = db.relationship("Course")

    def to_dict(self):
        return {
            "id": self.id,
            "student": self.student.to_dict() if self.student else None,
            "class_group": self.class_group.to_dict() if self.class_group else None,
            "course": self.course.to_dict() if self.course else None,
            "is_active": self.is_active,
        }


class TeachingAssignment(db.Model):
    __tablename__ = "teaching_assignments"
    __table_args__ = (
        db.UniqueConstraint(
            "teacher_id", "class_id", "course_id", name="uq_teacher_class_course"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    class_id = db.Column(
        db.Integer, db.ForeignKey("class_groups.id"), nullable=False, index=True
    )
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    teacher = db.relationship("User", foreign_keys=[teacher_id])
    class_group = db.relationship("ClassGroup")
    course = db.relationship("Course")

    def to_dict(self):
        return {
            "id": self.id,
            "teacher": self.teacher.to_dict() if self.teacher else None,
            "class_group": self.class_group.to_dict() if self.class_group else None,
            "course": self.course.to_dict() if self.course else None,
            "is_active": self.is_active,
        }


class PracticeSession(db.Model):
    __tablename__ = "practice_sessions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    direction = db.Column(db.String(20), nullable=False)
    source_text = db.Column(db.Text, nullable=False)
    interval_seconds = db.Column(db.Integer, nullable=False, default=20)
    model_name = db.Column(db.String(120), nullable=False, default="doubao")
    prompt_params = db.Column(db.JSON, nullable=False, default=dict)
    status = db.Column(db.String(30), nullable=False, default="created")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    user = db.relationship("User", back_populates="sessions")
    result = db.relationship(
        "PracticeResult",
        back_populates="session",
        cascade="all, delete-orphan",
        uselist=False,
    )
    evaluation_versions = db.relationship(
        "PracticeEvaluationVersion",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="PracticeEvaluationVersion.version_number.desc()",
    )
    archive = db.relationship(
        "PracticeArchive",
        back_populates="session",
        cascade="all, delete-orphan",
        uselist=False,
    )
    context = db.relationship(
        "PracticeContext",
        back_populates="session",
        cascade="all, delete-orphan",
        uselist=False,
    )

    def to_dict(self, include_result=True):
        data = {
            "id": self.id,
            "user": self.user.to_dict() if self.user else None,
            "direction": self.direction,
            "source_text": self.source_text,
            "interval_seconds": self.interval_seconds,
            "model_name": self.model_name,
            "prompt_params": self.prompt_params or {},
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
        if include_result:
            data["result"] = self.result.to_dict() if self.result else None
        data["archive"] = self.archive.to_summary_dict() if self.archive else None
        data["evaluation_version_count"] = len(self.evaluation_versions)
        data["context"] = self.context.to_dict() if self.context else None
        return data


class PracticeContext(db.Model):
    __tablename__ = "practice_contexts"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.Integer,
        db.ForeignKey("practice_sessions.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    term_id = db.Column(db.Integer, db.ForeignKey("academic_terms.id"), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey("class_groups.id"), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    session = db.relationship("PracticeSession", back_populates="context")
    term = db.relationship("AcademicTerm")
    class_group = db.relationship("ClassGroup")
    course = db.relationship("Course")

    def to_dict(self):
        return {
            "id": self.id,
            "term": self.term.to_dict() if self.term else None,
            "class_group": self.class_group.to_dict() if self.class_group else None,
            "course": self.course.to_dict() if self.course else None,
        }


class PracticeResult(db.Model):
    __tablename__ = "practice_results"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.Integer,
        db.ForeignKey("practice_sessions.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    audio_path = db.Column(db.String(500), nullable=True)
    asr_text = db.Column(db.Text, nullable=True)
    asr_confidence = db.Column(db.Float, nullable=True)
    asr_segments = db.Column(db.JSON, nullable=False, default=list)
    evaluation_json = db.Column(db.JSON, nullable=False, default=dict)
    score = db.Column(db.String(20), nullable=True)
    feedback_text = db.Column(db.Text, nullable=True)
    reference_translation = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    session = db.relationship("PracticeSession", back_populates="result")

    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "audio_path": self.audio_path,
            "asr_text": self.asr_text,
            "asr_confidence": self.asr_confidence,
            "asr_segments": self.asr_segments or [],
            "evaluation_json": self.evaluation_json or {},
            "score": self.score,
            "feedback_text": self.feedback_text,
            "reference_translation": self.reference_translation,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class PracticeEvaluationVersion(db.Model):
    __tablename__ = "practice_evaluation_versions"
    __table_args__ = (
        db.UniqueConstraint("session_id", "version_number", name="uq_practice_version"),
    )

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.Integer,
        db.ForeignKey("practice_sessions.id"),
        nullable=False,
        index=True,
    )
    version_number = db.Column(db.Integer, nullable=False)
    asr_text = db.Column(db.Text, nullable=False)
    score = db.Column(db.String(20), nullable=True)
    feedback_text = db.Column(db.Text, nullable=False)
    reference_translation = db.Column(db.Text, nullable=True)
    evaluation_json = db.Column(db.JSON, nullable=False, default=dict)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    session = db.relationship("PracticeSession", back_populates="evaluation_versions")
    created_by = db.relationship("User", foreign_keys=[created_by_id])

    def to_dict(self):
        return {
            "id": self.id,
            "session_id": self.session_id,
            "version_number": self.version_number,
            "asr_text": self.asr_text,
            "score": self.score,
            "feedback_text": self.feedback_text,
            "reference_translation": self.reference_translation or "",
            "evaluation_json": self.evaluation_json or {},
            "created_by": self.created_by.to_dict() if self.created_by else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class PracticeArchive(db.Model):
    __tablename__ = "practice_archives"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.Integer,
        db.ForeignKey("practice_sessions.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    evaluation_version_id = db.Column(
        db.Integer,
        db.ForeignKey("practice_evaluation_versions.id"),
        nullable=False,
        index=True,
    )
    feedback_log_id = db.Column(
        db.Integer,
        db.ForeignKey("feedback_logs.id"),
        nullable=False,
        index=True,
    )
    source_text = db.Column(db.Text, nullable=False)
    asr_text = db.Column(db.Text, nullable=False)
    score = db.Column(db.String(20), nullable=True)
    feedback_text = db.Column(db.Text, nullable=False)
    reference_translation = db.Column(db.Text, nullable=True)
    evaluation_json = db.Column(db.JSON, nullable=False, default=dict)
    practice_created_at = db.Column(db.DateTime(timezone=True), nullable=False)
    evaluation_created_at = db.Column(db.DateTime(timezone=True), nullable=False)
    archived_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    archived_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    session = db.relationship("PracticeSession", back_populates="archive")
    evaluation_version = db.relationship("PracticeEvaluationVersion")
    feedback_log = db.relationship("FeedbackLog")
    archived_by = db.relationship("User", foreign_keys=[archived_by_id])

    def to_summary_dict(self):
        return {
            "id": self.id,
            "evaluation_version_id": self.evaluation_version_id,
            "version_number": (
                self.evaluation_version.version_number if self.evaluation_version else None
            ),
            "score": self.score,
            "archived_at": self.archived_at.isoformat() if self.archived_at else None,
        }

    def to_dict(self):
        return {
            **self.to_summary_dict(),
            "session_id": self.session_id,
            "feedback_log_id": self.feedback_log_id,
            "source_text": self.source_text,
            "asr_text": self.asr_text,
            "feedback_text": self.feedback_text,
            "reference_translation": self.reference_translation or "",
            "evaluation_json": self.evaluation_json or {},
            "practice_created_at": (
                self.practice_created_at.isoformat() if self.practice_created_at else None
            ),
            "evaluation_created_at": (
                self.evaluation_created_at.isoformat() if self.evaluation_created_at else None
            ),
            "archived_by": self.archived_by.to_dict() if self.archived_by else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class PromptPreset(db.Model):
    __tablename__ = "prompt_presets"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    role_prompt = db.Column(db.Text, nullable=False)
    task_type = db.Column(db.String(120), nullable=False)
    dimensions_json = db.Column(db.JSON, nullable=False, default=list)
    format_prompt = db.Column(db.Text, nullable=False)
    strictness = db.Column(db.Integer, nullable=False, default=4)
    is_default = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)


class FeedbackLog(db.Model):
    __tablename__ = "feedback_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    student_no = db.Column(db.String(64), nullable=True, index=True)
    student_name = db.Column(db.String(120), nullable=True)
    task_id = db.Column(db.String(80), nullable=True, index=True)
    feedback_type = db.Column(db.String(80), nullable=False, default="AI反馈（豆包）")
    raw_text = db.Column(db.Text, nullable=False)
    pros = db.Column(db.Text, nullable=True)
    cons = db.Column(db.Text, nullable=True)
    suggestions = db.Column(db.Text, nullable=True)
    overall = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    user = db.relationship("User")
    context = db.relationship(
        "FeedbackContext",
        back_populates="feedback_log",
        cascade="all, delete-orphan",
        uselist=False,
    )

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "student_no": self.student_no,
            "student_name": self.student_name,
            "task_id": self.task_id,
            "feedback_type": self.feedback_type,
            "raw_text": self.raw_text,
            "pros": self.pros or "",
            "cons": self.cons or "",
            "suggestions": self.suggestions or "",
            "overall": self.overall or "",
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "context": self.context.to_dict() if self.context else None,
        }


class FeedbackContext(db.Model):
    __tablename__ = "feedback_contexts"

    id = db.Column(db.Integer, primary_key=True)
    feedback_log_id = db.Column(
        db.Integer,
        db.ForeignKey("feedback_logs.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    term_id = db.Column(db.Integer, db.ForeignKey("academic_terms.id"), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey("class_groups.id"), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey("courses.id"), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    feedback_log = db.relationship("FeedbackLog", back_populates="context")
    term = db.relationship("AcademicTerm")
    class_group = db.relationship("ClassGroup")
    course = db.relationship("Course")

    def to_dict(self):
        return {
            "term": self.term.to_dict() if self.term else None,
            "class_group": self.class_group.to_dict() if self.class_group else None,
            "course": self.course.to_dict() if self.course else None,
        }


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    action = db.Column(db.String(120), nullable=False, index=True)
    target_type = db.Column(db.String(80), nullable=True)
    target_id = db.Column(db.String(120), nullable=True)
    details = db.Column(db.JSON, nullable=False, default=dict)
    ip_address = db.Column(db.String(80), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)

    actor = db.relationship("User", foreign_keys=[actor_id])

    def to_dict(self):
        return {
            "id": self.id,
            "actor": self.actor.to_dict() if self.actor else None,
            "action": self.action,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "details": self.details or {},
            "ip_address": self.ip_address,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


def backfill_practice_evaluation_versions():
    existing_session_ids = {
        row[0] for row in db.session.query(PracticeEvaluationVersion.session_id).distinct().all()
    }
    results = PracticeResult.query.filter(
        PracticeResult.feedback_text.isnot(None),
        PracticeResult.asr_text.isnot(None),
    ).all()
    created = 0
    for result in results:
        if (
            result.session_id in existing_session_ids
            or not result.feedback_text.strip()
            or not result.asr_text.strip()
        ):
            continue
        version = PracticeEvaluationVersion(
            session_id=result.session_id,
            version_number=1,
            asr_text=result.asr_text,
            score=result.score,
            feedback_text=result.feedback_text,
            reference_translation=result.reference_translation,
            evaluation_json=result.evaluation_json or {},
            created_by_id=result.session.user_id if result.session else None,
            created_at=result.updated_at or result.created_at or utcnow(),
        )
        db.session.add(version)
        existing_session_ids.add(result.session_id)
        created += 1
    if created:
        db.session.commit()
    return created


class ServiceSettings(db.Model):
    __tablename__ = "service_settings"

    id = db.Column(db.Integer, primary_key=True)
    values = db.Column(db.JSON, nullable=False, default=dict)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow)


class ChatConversation(db.Model):
    __tablename__ = "chat_conversations"
    __table_args__ = {"sqlite_autoincrement": True}

    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(36), nullable=False, unique=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    title = db.Column(db.String(120), nullable=False, default="新对话")
    version = db.Column(db.Integer, nullable=False, default=0)
    generation = db.Column(db.Integer, nullable=False, default=0)
    active_request = db.Column(db.String(36), nullable=True)
    active_until = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    def to_dict(self):
        return {"id": self.public_id, "title": self.title, "version": self.version,
                "created_at": self.created_at.isoformat(), "updated_at": self.updated_at.isoformat()}


class ChatTurn(db.Model):
    __tablename__ = "chat_turns"
    __table_args__ = (
        db.UniqueConstraint("conversation_id", "request_id", name="uq_chat_request"),
        db.UniqueConstraint("conversation_id", "sequence", name="uq_chat_sequence"),
        {"sqlite_autoincrement": True},
    )

    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey("chat_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    request_id = db.Column(db.String(36), nullable=False)
    sequence = db.Column(db.Integer, nullable=False)
    content_sha256 = db.Column(db.String(64), nullable=False)
    user_content = db.Column(db.Text, nullable=False)
    assistant_content = db.Column(db.Text, nullable=True)
    provider = db.Column(db.String(80), nullable=True)
    status = db.Column(db.String(16), nullable=False, default="pending")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    def to_dict(self):
        return {"id": self.id, "request_id": self.request_id, "sequence": self.sequence,
                "user_content": self.user_content, "assistant_content": self.assistant_content,
                "status": self.status, "provider": self.provider, "created_at": self.created_at.isoformat()}
