import csv
import io
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, abort, current_app, jsonify, request, send_file
from sqlalchemy import func
from werkzeug.utils import secure_filename

from ..models import (
    FeedbackLog,
    FeedbackContext,
    PracticeArchive,
    PracticeContext,
    PracticeEvaluationVersion,
    PracticeResult,
    PracticeSession,
    User,
    db,
)
from ..audit import add_audit
from ..permissions import practice_for_user, resolve_student_enrollment, scope_practice_query
from ..services import (
    ASRClient,
    LLMClient,
    SUPPORTED_SPEECH_LANGUAGES,
    TTSClient,
    parse_feedback_text,
)
from .auth import require_teacher, require_user

practice_bp = Blueprint("practice", __name__)
DIRECTION_LANGUAGES = {
    "日→中": {"source": "ja-JP", "target": "zh-CN"},
    "中→日": {"source": "zh-CN", "target": "ja-JP"},
    "英→中": {"source": "en-US", "target": "zh-CN"},
    "中→英": {"source": "zh-CN", "target": "en-US"},
}


def _json():
    return request.get_json(silent=True) or {}


def _session_for_user(session_id, user):
    return practice_for_user(session_id, user)


def _latest_evaluation_version(item):
    return (
        PracticeEvaluationVersion.query.filter_by(session_id=item.id)
        .order_by(PracticeEvaluationVersion.version_number.desc())
        .first()
    )


def _create_legacy_evaluation_version(item, user):
    result = item.result
    if not result or not result.feedback_text or not result.asr_text:
        return None
    version = PracticeEvaluationVersion(
        session_id=item.id,
        version_number=1,
        asr_text=result.asr_text,
        score=result.score,
        feedback_text=result.feedback_text,
        reference_translation=result.reference_translation,
        evaluation_json=result.evaluation_json or {},
        created_by_id=user.id,
        created_at=result.updated_at or result.created_at or datetime.now(timezone.utc),
    )
    db.session.add(version)
    db.session.flush()
    return version


@practice_bp.post("/tts")
def tts():
    require_user()
    data = _json()
    text = (data.get("text") or "").strip()
    if not text:
        abort(400, "文本不能为空")
    lang = data.get("lang") or "zh-CN"
    if lang not in SUPPORTED_SPEECH_LANGUAGES:
        abort(400, "不支持的语种")
    payload = TTSClient().synthesize(
        text=text,
        lang=lang,
        voice=data.get("voice") or "",
        speed=int(data.get("speed") or 50),
    )
    return jsonify(payload)


@practice_bp.post("/practices")
def create_practice():
    user = require_user()
    if user.role != "student":
        abort(403, "只有学生账号可以创建练习")
    data = _json()
    source_text = (data.get("source_text") or "").strip()
    if not source_text:
        abort(400, "源语文本不能为空")
    direction = data.get("direction") or "日→中"
    if direction not in DIRECTION_LANGUAGES:
        abort(400, "不支持的语言方向")

    item = PracticeSession(
        user_id=user.id,
        direction=direction,
        source_text=source_text,
        interval_seconds=int(data.get("interval_seconds") or 20),
        model_name=data.get("model_name") or "doubao",
        prompt_params=data.get("prompt_params") or {},
        status="created",
    )
    db.session.add(item)
    db.session.flush()
    class_id = data.get("class_id")
    course_id = data.get("course_id")
    if class_id or course_id or current_app.config["REQUIRE_PRACTICE_CONTEXT"]:
        enrollment = resolve_student_enrollment(user, class_id, course_id)
        item.context = PracticeContext(
            term_id=enrollment.course.term_id,
            class_id=enrollment.class_id,
            course_id=enrollment.course_id,
        )
    db.session.commit()
    return jsonify({"practice": item.to_dict()}), 201


@practice_bp.get("/practices")
def list_practices():
    user = require_user()
    query = scope_practice_query(PracticeSession.query, user).order_by(
        PracticeSession.created_at.desc()
    )
    if user.role in {"teacher", "admin"}:
        student_no = request.args.get("student_no")
        if student_no:
            query = query.join(User).filter(User.student_no == student_no)
    status = request.args.get("status")
    if status:
        query = query.filter(PracticeSession.status == status)
    limit = min(int(request.args.get("limit", "100")), 500)
    rows = query.limit(limit).all()
    return jsonify({"practices": [row.to_dict() for row in rows]})


@practice_bp.get("/practices/<int:session_id>")
def get_practice(session_id):
    user = require_user()
    item = _session_for_user(session_id, user)
    versions = [version.to_dict() for version in item.evaluation_versions]
    return jsonify(
        {
            "practice": item.to_dict(),
            "archive": item.archive.to_dict() if item.archive else None,
            "evaluation_versions": versions,
            "latest_evaluation": versions[0] if versions else None,
        }
    )


@practice_bp.post("/practices/<int:session_id>/audio")
def upload_audio(session_id):
    user = require_user()
    item = _session_for_user(session_id, user)
    upload = request.files.get("audio")
    if not upload:
        abort(400, "缺少音频文件")
    language_pair = DIRECTION_LANGUAGES.get(item.direction)
    if not language_pair:
        abort(400, "练习记录包含不支持的语言方向")
    expected_lang = language_pair["target"]
    lang = request.form.get("lang") or expected_lang
    if lang != expected_lang:
        abort(400, "ASR 语种与练习方向不一致")

    upload_dir = Path(current_app.config["UPLOAD_DIR"])
    upload_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(secure_filename(upload.filename or "")).suffix or ".webm"
    filename = f"{session_id}-{uuid.uuid4().hex}{ext}"
    audio_path = upload_dir / filename
    upload.save(audio_path)

    asr_payload = ASRClient().transcribe(str(audio_path), lang)
    result = item.result or PracticeResult(session_id=item.id)
    result.audio_path = str(audio_path)
    result.asr_text = asr_payload.get("transcript", "")
    result.asr_confidence = asr_payload.get("confidence")
    result.asr_segments = asr_payload.get("segments") or []
    item.status = "transcribed"
    db.session.add(result)
    db.session.commit()
    return jsonify({"practice": item.to_dict(), "asr": asr_payload})


@practice_bp.post("/practices/<int:session_id>/evaluate")
def evaluate_practice(session_id):
    user = require_user()
    item = _session_for_user(session_id, user)
    data = _json()
    asr_text = (data.get("asr_text") or (item.result.asr_text if item.result else "") or "").strip()
    if not asr_text:
        abort(400, "缺少 ASR 识别文本")

    payload = LLMClient().evaluate(
        source_text=item.source_text,
        asr_text=asr_text,
        direction=item.direction,
        prompt_params=item.prompt_params or {},
    )
    result = item.result or PracticeResult(session_id=item.id)
    result.asr_text = asr_text
    result.score = payload.get("score")
    result.feedback_text = payload.get("feedback_text")
    result.reference_translation = payload.get("reference_translation")
    result.evaluation_json = payload.get("evaluation_json") or {}
    latest_number = (
        db.session.query(func.max(PracticeEvaluationVersion.version_number))
        .filter(PracticeEvaluationVersion.session_id == item.id)
        .scalar()
        or 0
    )
    version = PracticeEvaluationVersion(
        session_id=item.id,
        version_number=latest_number + 1,
        asr_text=asr_text,
        score=payload.get("score"),
        feedback_text=payload.get("feedback_text") or "",
        reference_translation=payload.get("reference_translation"),
        evaluation_json=payload.get("evaluation_json") or {},
        created_by_id=user.id,
    )
    item.status = "evaluated"
    item.completed_at = datetime.now(timezone.utc)
    add_audit(
        user,
        "practice.evaluated",
        "practice_session",
        item.id,
        {"version_number": version.version_number},
    )
    db.session.add(result)
    db.session.add(version)
    db.session.commit()
    return jsonify(
        {
            "practice": item.to_dict(),
            "evaluation": payload,
            "evaluation_version": version.to_dict(),
            "archive": item.archive.to_dict() if item.archive else None,
        }
    )


@practice_bp.post("/practices/<int:session_id>/archive")
def archive_practice(session_id):
    user = require_user()
    item = _session_for_user(session_id, user)
    data = _json()
    version = _latest_evaluation_version(item)
    if not version:
        version = _create_legacy_evaluation_version(item, user)
    if not version:
        abort(400, "请先完成 ASR 识别和 AI 评价")

    requested_version_id = data.get("evaluation_version_id")
    if requested_version_id:
        try:
            requested_version_id = int(requested_version_id)
        except (TypeError, ValueError):
            abort(400, "评价版本参数无效")
        if requested_version_id != version.id:
            abort(400, "评价版本已更新，请刷新后归档最新版本")
    submitted_asr = (data.get("asr_text") or version.asr_text or "").strip()
    if submitted_asr != version.asr_text.strip():
        abort(400, "ASR 文本已修改，请先重新生成评价再归档")

    archive = item.archive
    if archive and archive.evaluation_version_id == version.id:
        item.status = "archived"
        db.session.commit()
        return jsonify({"practice": item.to_dict(), "archive": archive.to_dict()})

    parsed = parse_feedback_text(version.feedback_text)
    feedback_log = FeedbackLog(
        user_id=item.user_id,
        student_no=item.user.student_no if item.user else None,
        student_name=item.user.name if item.user else None,
        task_id=f"LP-{item.id}-V{version.version_number}",
        feedback_type=f"LoopPractice AI评价（第{version.version_number}版）",
        raw_text=version.feedback_text,
        pros=parsed["pros"],
        cons=parsed["cons"],
        suggestions=parsed["suggestions"],
        overall=parsed["overall"],
    )
    db.session.add(feedback_log)
    db.session.flush()
    if item.context:
        feedback_log.context = FeedbackContext(
            term_id=item.context.term_id,
            class_id=item.context.class_id,
            course_id=item.context.course_id,
        )

    now = datetime.now(timezone.utc)
    if not archive:
        archive = PracticeArchive(session_id=item.id)
    archive.evaluation_version_id = version.id
    archive.feedback_log_id = feedback_log.id
    archive.source_text = item.source_text
    archive.asr_text = version.asr_text
    archive.score = version.score
    archive.feedback_text = version.feedback_text
    archive.reference_translation = version.reference_translation
    archive.evaluation_json = version.evaluation_json or {}
    archive.practice_created_at = item.created_at
    archive.evaluation_created_at = version.created_at
    archive.archived_by_id = user.id
    archive.archived_at = now
    item.status = "archived"
    add_audit(
        user,
        "practice.archived",
        "practice_session",
        item.id,
        {"version_number": version.version_number},
    )
    db.session.add(archive)
    db.session.commit()
    return jsonify({"practice": item.to_dict(), "archive": archive.to_dict()}), 201


@practice_bp.get("/practices/export.csv")
def export_practices():
    user = require_teacher()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "练习时间",
            "归档时间",
            "学号",
            "姓名",
            "方向",
            "状态",
            "模型",
            "评价版本数",
            "归档版本",
            "源语",
            "ASR识别文本",
            "评分",
            "AI评价",
            "参考译法",
        ]
    )
    rows = (
        scope_practice_query(PracticeSession.query, user)
        .join(User)
        .order_by(PracticeSession.created_at.desc())
        .all()
    )
    for row in rows:
        result = row.result
        archive = row.archive
        writer.writerow(
            [
                row.created_at.isoformat() if row.created_at else "",
                archive.archived_at.isoformat() if archive and archive.archived_at else "",
                row.user.student_no if row.user else "",
                row.user.name if row.user else "",
                row.direction,
                row.status,
                row.model_name,
                len(row.evaluation_versions),
                (
                    archive.evaluation_version.version_number
                    if archive and archive.evaluation_version
                    else ""
                ),
                archive.source_text if archive else row.source_text,
                archive.asr_text if archive else (result.asr_text if result else ""),
                archive.score if archive else (result.score if result else ""),
                archive.feedback_text if archive else (result.feedback_text if result else ""),
                (
                    archive.reference_translation
                    if archive
                    else (result.reference_translation if result else "")
                ),
            ]
        )
    data = io.BytesIO(output.getvalue().encode("utf-8-sig"))
    return send_file(
        data,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"interploop-practices-{datetime.now().strftime('%Y%m%d')}.csv",
    )


@practice_bp.get("/practices/evaluation-versions/export.csv")
def export_evaluation_versions():
    user = require_teacher()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "评价时间",
            "练习时间",
            "练习ID",
            "学号",
            "姓名",
            "方向",
            "版本",
            "是否正式归档版本",
            "评价人",
            "源语",
            "ASR识别文本",
            "评分",
            "AI评价",
            "参考译法",
        ]
    )
    visible_sessions = scope_practice_query(PracticeSession.query, user).with_entities(
        PracticeSession.id
    )
    versions = (
        PracticeEvaluationVersion.query.filter(
            PracticeEvaluationVersion.session_id.in_(visible_sessions)
        )
        .join(PracticeSession)
        .join(User, PracticeSession.user_id == User.id)
        .order_by(PracticeEvaluationVersion.created_at.desc())
        .all()
    )
    for version in versions:
        session_item = version.session
        archive = session_item.archive
        writer.writerow(
            [
                version.created_at.isoformat() if version.created_at else "",
                session_item.created_at.isoformat() if session_item.created_at else "",
                session_item.id,
                session_item.user.student_no if session_item.user else "",
                session_item.user.name if session_item.user else "",
                session_item.direction,
                version.version_number,
                "是" if archive and archive.evaluation_version_id == version.id else "否",
                version.created_by.name if version.created_by else "",
                session_item.source_text,
                version.asr_text,
                version.score or "",
                version.feedback_text,
                version.reference_translation or "",
            ]
        )
    data = io.BytesIO(output.getvalue().encode("utf-8-sig"))
    return send_file(
        data,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"interploop-evaluation-versions-{datetime.now().strftime('%Y%m%d')}.csv",
    )
