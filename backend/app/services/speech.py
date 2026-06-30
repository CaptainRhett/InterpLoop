import base64
import hashlib
import hmac
import json
from email.utils import formatdate
from urllib.parse import urlencode

import websocket
from flask import current_app


class ASRClient:
    def __init__(self):
        self.mock = current_app.config["USE_MOCK_SERVICES"]

    def transcribe(self, audio_path, lang="auto"):
        if self.mock:
            return {
                "transcript": "这是模拟 ASR 识别文本。配置真实讯飞密钥并关闭 USE_MOCK_SERVICES 后会返回实际识别结果。",
                "confidence": 0.9,
                "segments": [],
                "provider": "mock",
            }
        return XunfeiIATClient().transcribe(audio_path, lang)


class TTSClient:
    def __init__(self):
        self.mock = current_app.config["USE_MOCK_SERVICES"]

    def synthesize(self, text, lang="zh-CN", voice="", speed=50):
        if self.mock:
            return {
                "audio_base64": "",
                "mime_type": "audio/mpeg",
                "provider": "mock",
                "message": "Mock 模式下前端会使用浏览器 speechSynthesis 播放。",
            }
        return XunfeiTTSClient().synthesize(text, lang, voice, speed)


class XunfeiAuth:
    def __init__(self, host, path):
        self.host = host
        self.path = path
        self.api_key = current_app.config["XUNFEI_API_KEY"]
        self.api_secret = current_app.config["XUNFEI_API_SECRET"]

    def signed_url(self):
        date = formatdate(timeval=None, localtime=False, usegmt=True)
        signature_origin = f"host: {self.host}\ndate: {date}\nGET {self.path} HTTP/1.1"
        signature_sha = hmac.new(
            self.api_secret.encode("utf-8"),
            signature_origin.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        signature = base64.b64encode(signature_sha).decode("utf-8")
        authorization_origin = (
            f'api_key="{self.api_key}", algorithm="hmac-sha256", '
            f'headers="host date request-line", signature="{signature}"'
        )
        authorization = base64.b64encode(authorization_origin.encode("utf-8")).decode("utf-8")
        return f"wss://{self.host}{self.path}?{urlencode({'authorization': authorization, 'date': date, 'host': self.host})}"


class XunfeiIATClient:
    def transcribe(self, audio_path, lang="auto"):
        app_id = current_app.config["XUNFEI_APP_ID"]
        if not app_id or not current_app.config["XUNFEI_API_KEY"] or not current_app.config["XUNFEI_API_SECRET"]:
            raise RuntimeError("缺少讯飞 ASR 配置")

        host = current_app.config["XUNFEI_IAT_HOST"]
        url = XunfeiAuth(host, "/v2/iat").signed_url()
        with open(audio_path, "rb") as fh:
            audio = fh.read()

        ws = websocket.create_connection(url, timeout=20)
        try:
            ws.send(
                json.dumps(
                    {
                        "common": {"app_id": app_id},
                        "business": {
                            "language": "zh_cn" if lang != "ja-JP" else "ja_jp",
                            "domain": "iat",
                            "accent": "mandarin",
                            "vad_eos": 5000,
                        },
                        "data": {
                            "status": 2,
                            "format": "audio/L16;rate=16000",
                            "encoding": "raw",
                            "audio": base64.b64encode(audio).decode("utf-8"),
                        },
                    },
                    ensure_ascii=False,
                )
            )
            chunks = []
            while True:
                message = json.loads(ws.recv())
                if message.get("code") != 0:
                    raise RuntimeError(message.get("message", "讯飞 ASR 调用失败"))
                data = message.get("data") or {}
                result = data.get("result") or {}
                for ws_item in result.get("ws", []):
                    chunks.extend(cw.get("w", "") for cw in ws_item.get("cw", []))
                if data.get("status") == 2:
                    break
            return {
                "transcript": "".join(chunks),
                "confidence": None,
                "segments": [],
                "provider": "xunfei",
            }
        finally:
            ws.close()


class XunfeiTTSClient:
    def synthesize(self, text, lang="zh-CN", voice="", speed=50):
        app_id = current_app.config["XUNFEI_APP_ID"]
        if not app_id or not current_app.config["XUNFEI_API_KEY"] or not current_app.config["XUNFEI_API_SECRET"]:
            raise RuntimeError("缺少讯飞 TTS 配置")

        host = current_app.config["XUNFEI_TTS_HOST"]
        url = XunfeiAuth(host, "/v2/tts").signed_url()
        ws = websocket.create_connection(url, timeout=20)
        try:
            ws.send(
                json.dumps(
                    {
                        "common": {"app_id": app_id},
                        "business": {
                            "aue": "lame",
                            "sfl": 1,
                            "auf": "audio/L16;rate=16000",
                            "vcn": voice or ("xiaoyan" if lang.startswith("zh") else "x2_yumi"),
                            "tte": "UTF8",
                            "speed": int(speed),
                        },
                        "data": {
                            "status": 2,
                            "text": base64.b64encode(text.encode("utf-8")).decode("utf-8"),
                        },
                    },
                    ensure_ascii=False,
                )
            )
            audio_parts = []
            while True:
                message = json.loads(ws.recv())
                if message.get("code") != 0:
                    raise RuntimeError(message.get("message", "讯飞 TTS 调用失败"))
                data = message.get("data") or {}
                if data.get("audio"):
                    audio_parts.append(data["audio"])
                if data.get("status") == 2:
                    break
            return {
                "audio_base64": "".join(audio_parts),
                "mime_type": "audio/mpeg",
                "provider": "xunfei",
            }
        finally:
            ws.close()
