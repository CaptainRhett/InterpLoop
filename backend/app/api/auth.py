from datetime import datetime, timezone

from flask import Blueprint, abort, current_app, jsonify, request, session

from ..extensions import db
from ..models import User

auth_bp = Blueprint("auth", __name__)


def _json():
    return request.get_json(silent=True) or {}


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return db.session.get(User, user_id)


def require_user():
    user = current_user()
    if not user:
        abort(401, "请先登录")
    return user


def require_teacher():
    user = require_user()
    if user.role != "teacher":
        abort(403, "需要教师权限")
    return user


@auth_bp.post("/student-login")
def student_login():
    data = _json()
    student_no = (data.get("student_no") or "").strip()
    name = (data.get("name") or "").strip()
    if not student_no or not name:
        abort(400, "学号和姓名不能为空")

    user = User.query.filter_by(student_no=student_no, role="student").first()
    if not user:
        user = User(student_no=student_no, name=name, role="student")
        db.session.add(user)
    else:
        user.name = name
    user.last_login_at = datetime.now(timezone.utc)
    db.session.commit()

    session.clear()
    session["user_id"] = user.id
    session["role"] = user.role
    return jsonify({"user": user.to_dict()})


@auth_bp.post("/teacher-login")
def teacher_login():
    data = _json()
    code = (data.get("teacher_code") or "").strip()
    if not code or code != current_app.config["TEACHER_CODE"]:
        abort(401, "教师码不正确")

    user = User.query.filter_by(role="teacher", student_no="teacher").first()
    if not user:
        user = User(student_no="teacher", name="教师", role="teacher")
        db.session.add(user)
    user.last_login_at = datetime.now(timezone.utc)
    db.session.commit()

    session.clear()
    session["user_id"] = user.id
    session["role"] = user.role
    return jsonify({"user": user.to_dict()})


@auth_bp.get("/me")
def me():
    user = current_user()
    return jsonify({"user": user.to_dict() if user else None})


@auth_bp.post("/logout")
def logout():
    session.clear()
    return jsonify({"ok": True})
