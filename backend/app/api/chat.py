from flask import Blueprint, jsonify, request

from ..services.llm import LLMClient


bp = Blueprint("llm", __name__, url_prefix="/api/llm")


@bp.post("/chat")
def chat():
    data = request.get_json(silent=True) or {}

    messages = data.get("messages")

    if not isinstance(messages, list) or not messages:
        return jsonify({
            "error": "请输入聊天内容"
        }), 400

    if len(messages) > 50:
        return jsonify({
            "error": "聊天上下文过长"
        }), 400

    try:
        client = LLMClient()

        result = client.chat(messages)

        return jsonify(result)

    except Exception:
        return jsonify({
            "error": "AI 服务调用失败"
        }), 500