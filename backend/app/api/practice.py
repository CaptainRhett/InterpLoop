import csv
import io
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, abort, current_app, jsonify, request, send_file
from werkzeug.utils import secure_filename

from ..extensions import db
from ..models import PracticeResult, PracticeSession, User
from ..services import ASRClient, LLMClient, TTSClient
from .auth import require_teacher, require_user

practice_bp = Blueprint("practice", __name__)


def _json():
    return request.get_json(silent=True) or {}


def _session_for_user(session_id, user):
    item = db.session.get(PracticeSession, session_id)
    if not item:
        abort(404, "练习记录不存在")
    if user.role != "teacher" and item.user_id != user.id:
        abort(403, "无权访问该练习记录")
    return item


@practice_bp.post("/tts")
def tts():
    require_user()
    data = _json()
    text = (data.get("text") or "").strip()
    if not text:
        abort(400, "文本不能为空")
    payload = TTSClient().synthesize(
        text=text,
        lang=data.get("lang") or "zh-CN",
        voice=data.get("voice") or "",
        speed=int(data.get("speed") or 50),
    )
    return jsonify(payload)


@practice_bp.post("/practices")
def create_practice():
    user = require_user()
    data = _json()
    source_text = (data.get("source_text") or "").strip()
    if not source_text:
        abort(400, "源语文本不能为空")

    item = PracticeSession(
        user_id=user.id,
        direction=data.get("direction") or "日→中",
        source_text=source_text,
        interval_seconds=int(data.get("interval_seconds") or 20),
        model_name=data.get("model_name") or "doubao",
        prompt_params=data.get("prompt_params") or {},
        status="created",
    )
    db.session.add(item)
    db.session.commit()
    return jsonify({"practice": item.to_dict()}), 201


@practice_bp.get("/practices")
def list_practices():
    user = require_user()
    query = PracticeSession.query.order_by(PracticeSession.created_at.desc())
    if user.role != "teacher":
        query = query.filter_by(user_id=user.id)
    else:
        student_no = request.args.get("student_no")
        if student_no:
            query = query.join(User).filter(User.student_no == student_no)
    limit = min(int(request.args.get("limit", "100")), 500)
    rows = query.limit(limit).all()
    return jsonify({"practices": [row.to_dict() for row in rows]})


@practice_bp.get("/practices/<int:session_id>")
def get_practice(session_id):
    user = require_user()
    item = _session_for_user(session_id, user)
    return jsonify({"practice": item.to_dict()})


@practice_bp.post("/practices/<int:session_id>/audio")
def upload_audio(session_id):
    user = require_user()
    item = _session_for_user(session_id, user)
    upload = request.files.get("audio")
    if not upload:
        abort(400, "缺少音频文件")

    upload_dir = Path(current_app.config["UPLOAD_DIR"])
    upload_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(secure_filename(upload.filename or "")).suffix or ".webm"
    filename = f"{session_id}-{uuid.uuid4().hex}{ext}"
    audio_path = upload_dir / filename
    upload.save(audio_path)

    asr_payload = ASRClient().transcribe(str(audio_path), request.form.get("lang") or "auto")
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
    item.status = "completed"
    item.completed_at = datetime.now(timezone.utc)
    db.session.add(result)
    db.session.commit()
    return jsonify({"practice": item.to_dict(), "evaluation": payload})


@practice_bp.get("/practices/export.csv")
def export_practices():
    require_teacher()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        ["时间", "学号", "姓名", "方向", "模型", "源语", "ASR识别文本", "评分", "AI评价"]
    )
    rows = PracticeSession.query.join(User).order_by(PracticeSession.created_at.desc()).all()
    for row in rows:
        result = row.result
        writer.writerow(
            [
                row.created_at.isoformat() if row.created_at else "",
                row.user.student_no if row.user else "",
                row.user.name if row.user else "",
                row.direction,
                row.model_name,
                row.source_text,
                result.asr_text if result else "",
                result.score if result else "",
                result.feedback_text if result else "",
            ]
        )
    data = io.BytesIO(output.getvalue().encode("utf-8-sig"))
    return send_file(
        data,
        mimetype="text/csv",
        as_attachment=True,
        download_name=f"interploop-practices-{datetime.now().strftime('%Y%m%d')}.csv",
    )
