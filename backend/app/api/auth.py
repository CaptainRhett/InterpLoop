from datetime import datetime, timezone

from flask import Blueprint, abort, current_app, jsonify, request, session

from ..audit import add_audit
from ..models import User, UserAccount, db
from ..permissions import managed_student_contexts, user_learning_contexts

auth_bp = Blueprint("auth", __name__)


def _json():
    return request.get_json(silent=True) or {}


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    user = db.session.get(User, user_id)
    if not user:
        session.clear()
        return None
    if user.account:
        if not user.account.is_active:
            session.clear()
            return None
        if session.get("account_version") != user.account.session_version:
            session.clear()
            return None
    elif not current_app.config["ALLOW_LEGACY_LOGIN"]:
        session.clear()
        return None
    return user


def require_user():
    user = current_user()
    if not user:
        abort(401, "请先登录")
    if (
        user.account
        and user.account.must_change_password
        and request.endpoint not in {"auth.change_password", "auth.me", "auth.logout"}
    ):
        abort(403, "首次登录必须先修改初始密码")
    return user


def require_teacher():
    user = require_user()
    if user.role not in {"teacher", "admin"}:
        abort(403, "需要教师权限")
    return user


def require_admin():
    user = require_user()
    if user.role != "admin":
        abort(403, "需要管理员权限")
    return user


def _login_user(user):
    session.clear()
    session.permanent = True
    session["user_id"] = user.id
    session["role"] = user.role
    session["account_version"] = user.account.session_version if user.account else None
    user.last_login_at = datetime.now(timezone.utc)
    add_audit(user, "auth.login", "user", user.id)
    db.session.commit()
    return jsonify(
        {
            "user": user.to_dict(),
            "contexts": user_learning_contexts(user),
        }
    )


@auth_bp.post("/login")
def account_login():
    data = _json()
    login_id = (data.get("login_id") or "").strip()
    password = data.get("password") or ""
    if not login_id or not password:
        abort(400, "账号和密码不能为空")

    account = UserAccount.query.filter_by(login_id=login_id).first()
    if not account or not account.check_password(password):
        if account:
            add_audit(
                account.user,
                "auth.login_failed",
                "user",
                account.user_id,
                {"login_id": login_id},
            )
            db.session.commit()
        abort(401, "账号或密码不正确")
    if not account.is_active:
        add_audit(account.user, "auth.login_blocked", "user", account.user_id)
        db.session.commit()
        abort(403, "账号已被禁用，请联系管理员")
    return _login_user(account.user)


@auth_bp.get("/login-config")
def login_config():
    return jsonify({"legacy_login_enabled": current_app.config["ALLOW_LEGACY_LOGIN"]})


@auth_bp.post("/student-login")
def student_login():
    if not current_app.config["ALLOW_LEGACY_LOGIN"]:
        abort(403, "学号和姓名免密登录已关闭")
    data = _json()
    student_no = (data.get("student_no") or "").strip()
    name = (data.get("name") or "").strip()
    if not student_no or not name:
        abort(400, "学号和姓名不能为空")

    user = User.query.filter_by(student_no=student_no, role="student").first()
    if not user:
        user = User(student_no=student_no, name=name, role="student")
        db.session.add(user)
        db.session.flush()
    else:
        user.name = name
    add_audit(user, "auth.legacy_student_login", "user", user.id)
    return _login_user(user)


@auth_bp.post("/teacher-login")
def teacher_login():
    if not current_app.config["ALLOW_LEGACY_LOGIN"]:
        abort(403, "共享教师码登录已关闭")
    data = _json()
    code = (data.get("teacher_code") or "").strip()
    if not code or code != current_app.config["TEACHER_CODE"]:
        abort(401, "教师码不正确")

    user = User.query.filter_by(role="teacher", student_no="teacher").first()
    if not user:
        user = User(student_no="teacher", name="教师", role="teacher")
        db.session.add(user)
        db.session.flush()
    add_audit(user, "auth.legacy_teacher_login", "user", user.id)
    return _login_user(user)


@auth_bp.get("/me")
def me():
    user = current_user()
    return jsonify(
        {
            "user": user.to_dict() if user else None,
            "contexts": user_learning_contexts(user) if user else [],
        }
    )


@auth_bp.get("/me/students")
def managed_students():
    user = require_teacher()
    return jsonify({"student_contexts": managed_student_contexts(user)})


@auth_bp.post("/change-password")
def change_password():
    user = require_user()
    if not user.account:
        abort(400, "当前为兼容登录账号，无法修改密码")
    data = _json()
    current_password = data.get("current_password") or ""
    new_password = data.get("new_password") or ""
    if not user.account.check_password(current_password):
        abort(400, "当前密码不正确")
    if len(new_password) < current_app.config["PASSWORD_MIN_LENGTH"]:
        abort(400, f"新密码至少需要 {current_app.config['PASSWORD_MIN_LENGTH']} 位")
    if current_password == new_password:
        abort(400, "新密码不能与当前密码相同")
    user.account.set_password(new_password, must_change=False)
    session["account_version"] = user.account.session_version
    add_audit(user, "auth.password_changed", "user", user.id)
    db.session.commit()
    return jsonify({"user": user.to_dict()})


@auth_bp.post("/logout")
def logout():
    user = current_user()
    if user:
        add_audit(user, "auth.logout", "user", user.id)
        db.session.commit()
    session.clear()
    return jsonify({"ok": True})
