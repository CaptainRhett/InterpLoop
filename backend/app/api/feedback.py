import csv
import io
from datetime import datetime

from flask import Blueprint, abort, current_app, jsonify, request, send_file

from ..models import FeedbackContext, FeedbackLog, User, db
from ..permissions import resolve_student_enrollment, scope_feedback_query, scope_user_query
from ..services import parse_feedback_text
from .auth import require_teacher, require_user

feedback_bp = Blueprint("feedback", __name__)


def _json():
    return request.get_json(silent=True) or {}


@feedback_bp.post("/feedback/parse")
def parse_feedback():
    require_user()
    data = _json()
    raw_text = (data.get("raw_text") or "").strip()
    if not raw_text:
        abort(400, "反馈原文不能为空")
    return jsonify(parse_feedback_text(raw_text))


@feedback_bp.post("/feedback-logs")
def create_feedback_log():
    user = require_user()
    data = _json()
    raw_text = (data.get("raw_text") or "").strip()
    if not raw_text:
        abort(400, "反馈原文不能为空")
    if user.role == "student":
        target_user = user
    else:
        target_user_id = data.get("user_id")
        if not target_user_id:
            abort(400, "请选择反馈所属学生")
        target_user = scope_user_query(User.query, user).filter(User.id == target_user_id).first()
        if not target_user or target_user.role != "student":
            abort(403, "无权为该学生创建反馈")
    parsed = parse_feedback_text(raw_text)
    item = FeedbackLog(
        user_id=target_user.id,
        student_no=target_user.student_no,
        student_name=target_user.name,
        task_id=data.get("task_id") or "",
        feedback_type=data.get("feedback_type") or "AI反馈（豆包）",
        raw_text=raw_text,
        pros=data.get("pros", parsed["pros"]),
        cons=data.get("cons", parsed["cons"]),
        suggestions=data.get("suggestions", parsed["suggestions"]),
        overall=data.get("overall", parsed["overall"]),
    )
    db.session.add(item)
    db.session.flush()
    class_id = data.get("class_id")
    course_id = data.get("course_id")
    if class_id or course_id or current_app.config["REQUIRE_PRACTICE_CONTEXT"]:
        enrollment = resolve_student_enrollment(target_user, class_id, course_id)
        item.context = FeedbackContext(
            term_id=enrollment.course.term_id,
            class_id=enrollment.class_id,
            course_id=enrollment.course_id,
        )
    db.session.commit()
    return jsonify({"feedback_log": item.to_dict()}), 201


@feedback_bp.get("/feedback-logs")
def list_feedback_logs():
    user = require_user()
    query = scope_feedback_query(FeedbackLog.query, user).order_by(
        FeedbackLog.created_at.desc()
    )
    if user.role in {"teacher", "admin"} and request.args.get("student_no"):
        query = query.filter(FeedbackLog.student_no == request.args["student_no"])
    rows = query.limit(min(int(request.args.get("limit", "100")), 500)).all()
    return jsonify({"feedback_logs": [row.to_dict() for row in rows]})


@feedback_bp.get("/feedback-logs/export.csv")
def export_feedback_logs():
    user = require_teacher()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["时间", "学号", "姓名", "任务编号", "反馈类型", "优点", "问题", "建议", "总评", "原文"])
    rows = (
        scope_feedback_query(FeedbackLog.query, user)
        .order_by(FeedbackLog.created_at.desc())
        .all()
    )
    for row in rows:
        writer.writerow(
            [
                row.created_at.isoformat() if row.created_at else "",
                row.student_no or "",
                row.student_name or "",
                row.task_id or "",
                row.feedback_type,
                row.pros or "",
                row.cons or "",
                row.suggestions or "",
                row.overall or "",
                row.raw_text,
            ]
        )
    data = io.BytesIO(output.getvalue().encode("utf-8-sig"))
    return send_file(
        data,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"interploop-feedback-{datetime.now().strftime('%Y%m%d')}.csv",
    )
