import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from flask import Blueprint, abort, jsonify, request
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from .auth import require_user
from ..models import ChatConversation, ChatTurn, db
from ..services.llm import LLMClient

bp = Blueprint("llm", __name__, url_prefix="/api/llm")


def identifier(value):
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        abort(400, "会话或请求 ID 无效")


def owned(public_id, user):
    item = ChatConversation.query.filter_by(public_id=identifier(public_id), user_id=user.id).first()
    if not item:
        abort(404)
    return item


def positive_argument(name, default):
    try:
        value = int(request.args.get(name, default))
    except (TypeError, ValueError):
        abort(400, "分页参数无效")
    if not 0 < value <= 9223372036854775807:
        abort(400, "分页参数无效")
    return value


def detail(item):
    before = positive_argument("before", 9223372036854775807)
    rows = ChatTurn.query.filter(ChatTurn.conversation_id == item.id, ChatTurn.sequence < before).order_by(ChatTurn.sequence.desc()).limit(51).all()
    busy = bool(item.active_request and item.active_until and item.active_until > datetime.now(timezone.utc).replace(tzinfo=None))
    return {"conversation": item.to_dict(), "turns": [row.to_dict() for row in reversed(rows[:50])],
            "has_more": len(rows) > 50, "busy": busy}


@bp.get("/conversations")
def list_conversations():
    user = require_user()
    before = positive_argument("before", 9223372036854775807)
    rows = ChatConversation.query.filter(ChatConversation.user_id == user.id, ChatConversation.id < before).order_by(ChatConversation.id.desc()).limit(51).all()
    return jsonify({"conversations": [item.to_dict() for item in rows[:50]],
                    "next_cursor": rows[49].id if len(rows) > 50 else None})


@bp.post("/conversations")
def create_conversation():
    user = require_user()
    user_id = user.id
    for _ in range(5):
        item = ChatConversation(public_id=str(uuid.uuid4()), user_id=user_id)
        db.session.add(item)
        try:
            db.session.commit()
            return jsonify(detail(item)), 201
        except IntegrityError:
            db.session.rollback()  # Collision never reuses an existing conversation.
    return jsonify({"error": "创建会话失败，请重试"}), 503


@bp.get("/conversations/<conversation_id>")
def get_conversation(conversation_id):
    return jsonify(detail(owned(conversation_id, require_user())))


@bp.post("/chat")
def chat():
    user = require_user()
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, "聊天参数须为 JSON 对象")
    item = owned(data.get("conversation_id"), user)
    request_id = identifier(data.get("request_id"))
    content = data.get("message")
    version = data.get("expected_version")
    if not isinstance(content, str) or not content.strip() or len(content) > 8000:
        abort(400, "消息须为 1–8000 字符")
    if isinstance(version, bool) or not isinstance(version, int) or version < 0:
        abort(400, "会话版本无效")
    content = content.strip()
    turn = ChatTurn.query.filter_by(conversation_id=item.id, request_id=request_id).first()
    if turn and turn.user_content != content:
        abort(409, "请求 ID 已用于其他内容，请重新发送")
    if turn and turn.status == "completed":
        return jsonify(detail(item))
    if version != item.version:
        abort(409, "会话已更新，请刷新历史后重试")
    if turn and turn.sequence != item.version:
        abort(409, "此消息后已有新消息，请作为新消息发送")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if item.active_request and item.active_until and item.active_until > now:
        abort(409, "此会话正在生成回复，请稍后刷新")
    # Acquire a database CAS lease before calling the network. No DB write
    # transaction stays open during model generation, and no in-process lock is used.
    client = LLMClient()
    conversation_pk = item.id
    generation = item.generation + 1
    new_version = item.version + (0 if turn else 1)
    changed = ChatConversation.query.filter(
        ChatConversation.id == item.id, ChatConversation.user_id == user.id,
        ChatConversation.version == version, ChatConversation.generation == item.generation,
        or_(ChatConversation.active_request.is_(None), ChatConversation.active_until <= now),
    ).update({"active_request": request_id, "active_until": now + timedelta(seconds=client.timeout + 60),
              "version": new_version, "generation": generation, "updated_at": now}, synchronize_session=False)
    if changed != 1:
        db.session.rollback()
        abort(409, "会话已更新或正在回复，请刷新后重试")
    ChatTurn.query.filter_by(conversation_id=item.id, status="pending").update({"status": "failed"}, synchronize_session=False)
    if turn:
        ChatTurn.query.filter_by(id=turn.id).update({"status": "pending"}, synchronize_session=False)
    else:
        turn = ChatTurn(conversation_id=item.id, request_id=request_id, sequence=new_version,
                        user_content=content, content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest())
        db.session.add(turn)
        if new_version == 1:
            item.title = content[:60]
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        abort(409, "请求重复或会话已更新，请刷新后重试")
    # Assemble context exclusively from this user's stored, completed turns.
    rows = ChatTurn.query.filter(ChatTurn.conversation_id == conversation_pk, ChatTurn.status == "completed").order_by(ChatTurn.sequence.desc()).limit(9).all()
    history = []
    size = len(content)
    for row in rows:
        size += len(row.user_content) + len(row.assistant_content or "")
        if size > 32000:
            break
        history[0:0] = [{"role": "user", "content": row.user_content},
                        {"role": "assistant", "content": row.assistant_content}]
    history.append({"role": "user", "content": content})
    db.session.remove()
    failed = False
    try:
        result = client.chat(history)
        if not isinstance(result.get("message"), str) or not result["message"].strip():
            raise ValueError("Empty model reply")
    except Exception:
        failed = True
        result = {}
    # A late reply from an expired/retried attempt cannot overwrite a newer turn.
    changed = ChatConversation.query.filter_by(id=conversation_pk, active_request=request_id, generation=generation).update(
        {"active_request": None, "active_until": None, "updated_at": datetime.now(timezone.utc).replace(tzinfo=None)}, synchronize_session=False)
    if changed != 1:
        db.session.rollback()
        return jsonify({"error": "该请求已失效，请刷新会话"}), 409
    ChatTurn.query.filter_by(conversation_id=conversation_pk, request_id=request_id).update(
        {"status": "failed" if failed else "completed", "assistant_content": result.get("message"),
         "provider": result.get("provider")}, synchronize_session=False)
    db.session.commit()
    item = db.session.get(ChatConversation, conversation_pk)
    payload = detail(item)
    if failed:
        payload["error"] = "AI 服务调用失败，消息已保存，可重试"
    return jsonify(payload), 502 if failed else 200
