import io
import tempfile
import time
import wave
from pathlib import Path

import requests
from flask import Blueprint, abort, jsonify, request

from .auth import require_admin
from ..audit import add_audit
from ..models import db
from ..services.llm import LLMClient
from ..services.speech import ASRClient, SUPPORTED_SPEECH_LANGUAGES
from ..services.settings import public_settings, save_settings, service_config

system_bp = Blueprint("system", __name__)


@system_bp.get("/settings")
def get_settings():
    require_admin()
    return jsonify(public_settings())


@system_bp.put("/settings")
def update_settings():
    actor = require_admin()
    try:
        changed = save_settings(request.get_json(silent=True))
    except ValueError as error:
        abort(400, str(error))
    add_audit(actor, "admin.settings_updated", "service_settings", 1, {"fields": changed})
    db.session.commit()
    return jsonify(public_settings())


@system_bp.post("/test/<service>")
def test_service(service):
    actor = require_admin()
    if service not in {"llm", "asr"}:
        abort(404)
    config = dict(service_config())
    # Tests always probe the real saved endpoint, even when business mock mode is on.
    config["USE_MOCK_SERVICES"] = False
    config["LLM_TIMEOUT_SECONDS"] = min(config["LLM_TIMEOUT_SECONDS"], 30)
    if service == "llm":
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            abort(400, "模型测试参数必须为 JSON 对象")
        text = data.get("text", "请只回复：连接成功")
        if not isinstance(text, str) or not text.strip() or len(text) > 2000:
            abort(400, "测试文本须为 1–2000 字符")
        if not config.get("DOUBAO_API_KEY") or not config.get("DOUBAO_MODEL"):
            abort(400, "请先保存模型 API Key 和模型 ID")
    else:
        lang = request.form.get("lang", "zh-CN")
        if lang not in SUPPORTED_SPEECH_LANGUAGES:
            abort(400, "不支持的测试语种")
        upload = request.files.get("audio")
        if not upload:
            abort(400, "请上传测试录音")
        content = upload.read(1024 * 1024 + 1)
        if not content or len(content) > 1024 * 1024:
            abort(400, "测试录音须为 1 MB 以内的非空文件")
        suffix = Path(upload.filename or "").suffix.lower()
        if config["ASR_PROVIDER"] == "xunfei":
            if not all(config.get(key) for key in ("XUNFEI_APP_ID", "XUNFEI_API_KEY", "XUNFEI_API_SECRET")):
                abort(400, "请先保存讯飞 App ID、API Key 和 API Secret")
            if suffix == ".wav":
                try:
                    with wave.open(io.BytesIO(content), "rb") as wav:
                        if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getcomptype()) != (1, 2, 16000, "NONE"):
                            abort(400, "讯飞测试 WAV 须为 16kHz、16bit、单声道 PCM")
                        content = wav.readframes(wav.getnframes())
                except (wave.Error, EOFError):
                    abort(400, "WAV 文件无效")
            elif suffix != ".pcm":
                abort(400, "讯飞测试仅支持 16kHz、16bit、单声道的 PCM/WAV")
            if not content or len(content) % 2 or len(content) > 16000 * 2 * 30:
                abort(400, "讯飞测试录音须为有效 PCM，且不超过 30 秒")
            suffix = ".pcm"
        elif suffix not in {".pcm", ".wav", ".mp3", ".m4a", ".webm", ".ogg", ".flac", ".mp4", ".mpeg", ".mpga"}:
            abort(400, "不支持的录音格式")
        elif not config.get("ASR_API_KEY") or not config.get("ASR_MODEL"):
            abort(400, "请先保存识别 API Key 和模型 ID")
    started = time.monotonic()
    ok = False
    try:
        if service == "llm":
            result = LLMClient(config).chat([{"role": "user", "content": text}])
        else:
            with tempfile.TemporaryDirectory(prefix="interploop-api-test-") as directory:
                path = Path(directory) / f"test{suffix}"
                path.write_bytes(content)
                result = ASRClient(config).transcribe(str(path), lang)
        ok = True
        payload = {"ok": True, "result": result}
        status = 200
    except Exception as error:
        # Never return upstream exception strings, signed URLs or credentials.
        upstream_status = error.response.status_code if isinstance(error, requests.HTTPError) and error.response is not None else None
        message = "调用失败，请检查服务地址、模型 ID、密钥权限和录音格式"
        if isinstance(error, requests.Timeout):
            message = "服务调用超时，请检查地址及网络后重试"
        elif upstream_status:
            message = f"上游返回 HTTP {upstream_status}，请检查密钥权限、模型 ID 和接口地址"
        payload = {"ok": False, "error": message}
        status = 502
    payload["elapsed_ms"] = round((time.monotonic() - started) * 1000)
    add_audit(actor, "admin.service_tested", "service_settings", 1, {"service": service, "ok": ok})
    db.session.commit()
    return jsonify(payload), status
