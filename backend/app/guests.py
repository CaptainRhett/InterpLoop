"""Renewable guest identities and deletion of expired temporary data."""
import hashlib
import re
import secrets
import shutil
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import abort, current_app, g, jsonify, request, session

from .models import (
    AuditLog, ChatConversation, ChatTurn, FeedbackContext, FeedbackLog,
    GuestSession, PracticeArchive, PracticeContext, PracticeEvaluationVersion,
    PracticeResult, PracticeSession, User, db,
)


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def guest_upload_dir(key):
    # Never accept a client-supplied path or user identifier here.
    if not re.fullmatch(r"[0-9a-f]{64}", key):
        raise ValueError("Invalid guest storage key")
    return Path(current_app.config["UPLOAD_DIR"]) / "guests" / key


def remove_guest(key, *, expired_only=False):
    """Claim deletion in the DB transaction so concurrent workers cannot reuse it."""
    row = db.session.get(GuestSession, key)
    if not row:
        return False
    user_id = row.user_id
    query = GuestSession.query.filter_by(token_hash=key)
    if expired_only:
        query = query.filter(GuestSession.expires_at <= now())
    if query.delete(synchronize_session=False) != 1:
        db.session.rollback()
        return False
    practices = db.session.query(PracticeSession.id).filter_by(user_id=user_id)
    feedback = db.session.query(FeedbackLog.id).filter_by(user_id=user_id)
    conversations = db.session.query(ChatConversation.id).filter_by(user_id=user_id)
    for model in (PracticeArchive, PracticeEvaluationVersion, PracticeResult, PracticeContext):
        model.query.filter(model.session_id.in_(practices)).delete(synchronize_session=False)
    PracticeSession.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    FeedbackContext.query.filter(FeedbackContext.feedback_log_id.in_(feedback)).delete(synchronize_session=False)
    FeedbackLog.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    ChatTurn.query.filter(ChatTurn.conversation_id.in_(conversations)).delete(synchronize_session=False)
    ChatConversation.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    AuditLog.query.filter_by(actor_id=user_id).delete(synchronize_session=False)
    User.query.filter_by(id=user_id, role="guest").delete(synchronize_session=False)
    db.session.commit()
    # Include superseded recordings and failed uploads, not just DB references.
    remove_guest_files(key)
    return True


def remove_guest_files(key):
    directory = guest_upload_dir(key)
    try:
        shutil.rmtree(directory)
    except FileNotFoundError:
        pass
    except OSError:
        # The next sweep retries orphan directories if a file is temporarily busy.
        current_app.logger.exception("Unable to remove expired guest recordings")


def cleanup_expired_guests():
    keys = [row[0] for row in db.session.query(GuestSession.token_hash).filter(GuestSession.expires_at <= now()).all()]
    count = sum(remove_guest(key, expired_only=True) for key in keys)
    root = Path(current_app.config["UPLOAD_DIR"]) / "guests"
    if root.exists():
        for directory in root.iterdir():
            if re.fullmatch(r"[0-9a-f]{64}", directory.name) and not db.session.get(GuestSession, directory.name):
                remove_guest_files(directory.name)
    return count


def guest_user():
    token = session.get("guest_token")
    if not isinstance(token, str):
        return None
    key = token_hash(token)
    # populate_existing also detects logout/expiry performed by another worker.
    row = GuestSession.query.filter_by(token_hash=key).populate_existing().first()
    if not row or row.expires_at <= now():
        session.clear()
        return None
    user = row.user
    return user if user and user.role == "guest" else None


def start_guest():
    existing = guest_user()
    if existing:
        return existing
    token = secrets.token_urlsafe(32)
    user = User(name="游客", role="guest")
    db.session.add(user)
    db.session.flush()
    db.session.add(GuestSession(
        token_hash=token_hash(token), user_id=user.id,
        expires_at=now() + timedelta(seconds=current_app.config["GUEST_SESSION_SECONDS"]),
    ))
    db.session.commit()
    session.clear()
    session.permanent = False
    session["guest_token"] = token
    g.guest_key = token_hash(token)
    return user


def end_guest():
    token = session.get("guest_token")
    if isinstance(token, str):
        remove_guest(token_hash(token))
    session.clear()
    g.guest_key = None


def renew_guest():
    token = session.get("guest_token")
    if not isinstance(token, str):
        abort(401, "游客会话已结束，请重新进入试用")
    key = token_hash(token)
    timestamp = now()
    expires_at = timestamp + timedelta(seconds=current_app.config["GUEST_SESSION_SECONDS"])
    # Conditional update competes atomically with cleanup; never revive a revoked
    # or expired identity, or shorten a deadline extended by another worker.
    GuestSession.query.filter(
        GuestSession.token_hash == key,
        GuestSession.expires_at > timestamp,
        GuestSession.expires_at < expires_at,
    ).update({"expires_at": expires_at}, synchronize_session=False)
    db.session.commit()
    user = guest_user()
    if not user:
        abort(401, "游客会话已结束，请重新进入试用")
    # Refresh Flask's signed cookie timestamp as well for continuous long trials.
    session.modified = True
    return user


def register_guest_lifecycle(app):
    lock = threading.Lock()
    stop = threading.Event()
    app.extensions["guest_cleanup_stop"] = stop

    def sweep_forever():
        while not stop.wait(1):
            try:
                with app.app_context():
                    cleanup_expired_guests()
            except Exception:
                app.logger.exception("Guest cleanup failed; will retry")

    def start_cleaner():
        worker = app.extensions.get("guest_cleanup_thread")
        if not app.testing and (worker is None or not worker.is_alive()):
            with lock:
                worker = app.extensions.get("guest_cleanup_thread")
                if worker is None or not worker.is_alive():
                    worker = threading.Thread(target=sweep_forever, name="guest-cleanup", daemon=True)
                    app.extensions["guest_cleanup_thread"] = worker
                    worker.start()

    # Clean idle sessions after a restart too; re-create the thread in forked workers.
    start_cleaner()

    @app.before_request
    def prepare_guest():
        start_cleaner()
        cleanup_expired_guests()
        token = session.get("guest_token")
        g.guest_key = token_hash(token) if isinstance(token, str) else None

    @app.after_request
    def finish_guest(response):
        key = getattr(g, "guest_key", None)
        if key:
            db.session.rollback()
            row = GuestSession.query.filter_by(token_hash=key).populate_existing().first()
            if not row or row.expires_at <= now():
                db.session.rollback()
                remove_guest(key)
                remove_guest_files(key)
                session.clear()
                if request.endpoint == "auth.me":
                    response = jsonify({"user": None, "contexts": []})
                elif request.endpoint != "auth.logout":
                    response = jsonify({"error": "游客会话已结束，请重新进入试用", "code": "GUEST_SESSION_EXPIRED"})
                    response.status_code = 401
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.cli.command("cleanup-guests")
    def cleanup_command():
        """Remove expired guests, their records and uploaded recordings."""
        import click
        click.echo(f"Removed {cleanup_expired_guests()} expired guest sessions")
