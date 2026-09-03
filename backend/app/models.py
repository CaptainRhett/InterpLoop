from datetime import datetime, timezone
from sqlalchemy import event
from sqlalchemy.engine import Engine

from flask_sqlalchemy import SQLAlchemy

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

    def to_dict(self):
        return {
            "id": self.id,
            "student_no": self.student_no,
            "name": self.name,
            "role": self.role,
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
        return data


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
        }
