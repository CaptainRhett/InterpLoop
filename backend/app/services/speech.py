import base64
import hashlib
import hmac
import io
import wave
from pathlib import Path

import requests
import json
import time
from email.utils import formatdate
from urllib.parse import urlencode

import websocket

from .settings import service_config


SUPPORTED_SPEECH_LANGUAGES = {"zh-CN", "ja-JP", "en-US"}
ASR_LANGUAGE_CODES = {
    "auto": "zh_cn",
    "zh-CN": "zh_cn",
    "ja-JP": "ja_jp",
    "en-US": "en_us",
}
TTS_VOICE_CONFIG = {
    "zh-CN": "XUNFEI_TTS_VOICE_ZH",
    "ja-JP": "XUNFEI_TTS_VOICE_JA",
    "en-US": "XUNFEI_TTS_VOICE_EN",
}


def asr_language_code(lang):
    try:
        return ASR_LANGUAGE_CODES[lang]
    except KeyError as exc:
        raise ValueError(f"不支持的 ASR 语种：{lang}") from exc


def default_tts_voice(lang):
    try:
        config_key = TTS_VOICE_CONFIG[lang]
    except KeyError as exc:
        raise ValueError(f"不支持的 TTS 语种：{lang}") from exc
    return service_config().get(config_key, "")


class ASRClient:
    def __init__(self, config=None):
        self.config = config if config is not None else service_config()
        self.mock = self.config["USE_MOCK_SERVICES"]

    def transcribe(self, audio_path, lang="auto"):
        if self.mock:
            transcripts = {
                "zh-CN": "这是模拟 ASR 识别文本。配置真实讯飞密钥并关闭 USE_MOCK_SERVICES 后会返回实际识别结果。",
                "ja-JP": "これは模擬 ASR の認識結果です。実際の認識結果を取得するには、音声サービスを設定してください。",
                "en-US": "This is a simulated ASR transcript. Configure the speech service to receive the actual transcript.",
            }
            return {
                "transcript": transcripts.get(lang, transcripts["zh-CN"]),
                "confidence": 0.9,
                "segments": [],
                "provider": "mock",
            }
        if self.config.get("ASR_PROVIDER") == "openai_compatible":
            return self._compatible_transcribe(audio_path, lang)
        return XunfeiIATClient(self.config).transcribe(audio_path, lang)

    def _compatible_transcribe(self, audio_path, lang):
        if not self.config.get("ASR_API_KEY") or not self.config.get("ASR_MODEL"):
            raise ValueError("请配置识别 API Key 和模型 ID")
        content = Path(audio_path).read_bytes()
        name = Path(audio_path).name
        if Path(audio_path).suffix.lower() == ".pcm":
            output = io.BytesIO()
            with wave.open(output, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(content)
            content, name = output.getvalue(), "recording.wav"
        data = {"model": self.config["ASR_MODEL"], "response_format": "json"}
        if lang != "auto":
            data["language"] = lang.split("-")[0]
        response = requests.post(
            self.config["ASR_BASE_URL"].rstrip("/") + "/audio/transcriptions",
            headers={"Authorization": f"Bearer {self.config['ASR_API_KEY']}"},
            files={"file": (name, content)}, data=data,
            timeout=self.config["LLM_TIMEOUT_SECONDS"],
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload.get("text"), str):
            raise ValueError("识别服务返回格式不正确")
        return {"transcript": payload["text"], "confidence": None,
                "segments": payload.get("segments") or [], "provider": "openai_compatible"}


class TTSClient:
    def __init__(self):
        self.mock = service_config()["USE_MOCK_SERVICES"]

    def synthesize(self, text, lang="zh-CN", voice="", speed=50):
        if self.mock:
            return {
                "audio_base64": "",
                "mime_type": "audio/mpeg",
                "provider": "mock",
                "message": "Mock 模式下前端会使用浏览器 speechSynthesis 播放。",
            }
        resolved_voice = voice or default_tts_voice(lang)
        if not resolved_voice:
            return {
                "audio_base64": "",
                "mime_type": "audio/mpeg",
                "provider": "browser-fallback",
                "message": f"未配置 {lang} 的讯飞发音人，前端将使用浏览器语音。",
            }
        return XunfeiTTSClient().synthesize(text, lang, resolved_voice, speed)


class XunfeiAuth:
    def __init__(self, host, path, config=None):
        config = config if config is not None else service_config()
        self.host = host
        self.path = path
        self.api_key = config["XUNFEI_API_KEY"]
        self.api_secret = config["XUNFEI_API_SECRET"]

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
    def __init__(self, config=None):
        self.config = config if config is not None else service_config()

    def transcribe(self, audio_path, lang="auto"):
        app_id = self.config["XUNFEI_APP_ID"]
        if not app_id or not self.config["XUNFEI_API_KEY"] or not self.config["XUNFEI_API_SECRET"]:
            raise RuntimeError("缺少讯飞 ASR 配置")

        host = self.config["XUNFEI_IAT_HOST"]
        url = XunfeiAuth(host, "/v2/iat", self.config).signed_url()
        with open(audio_path, "rb") as fh:
            audio = fh.read()

        ws = websocket.create_connection(url, timeout=20)
        try:
            self._send_audio(ws, app_id, audio, lang)
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

    def _send_audio(self, ws, app_id, audio, lang):
        frame_size = 1280
        frame_count = max(1, (len(audio) + frame_size - 1) // frame_size)
        language = asr_language_code(lang)
        for frame_index in range(frame_count):
            offset = frame_index * frame_size
            frame = audio[offset : offset + frame_size]
            is_first = frame_index == 0
            is_last = frame_index == frame_count - 1
            if frame_count == 1 or is_last:
                status = 2
            elif is_first:
                status = 0
            else:
                status = 1

            payload = {
                "data": {
                    "status": status,
                    "format": "audio/L16;rate=16000",
                    "encoding": "raw",
                    "audio": base64.b64encode(frame).decode("utf-8"),
                }
            }
            if is_first:
                payload["common"] = {"app_id": app_id}
                payload["business"] = {
                    "language": language,
                    "domain": self.config.get("XUNFEI_IAT_DOMAIN", "iat"),
                    "accent": "mandarin",
                    "vad_eos": 5000,
                }
            ws.send(json.dumps(payload, ensure_ascii=False))
            if not is_last:
                time.sleep(0.04)


class XunfeiTTSClient:
    def synthesize(self, text, lang="zh-CN", voice="", speed=50):
        app_id = service_config()["XUNFEI_APP_ID"]
        if not app_id or not service_config()["XUNFEI_API_KEY"] or not service_config()["XUNFEI_API_SECRET"]:
            raise RuntimeError("缺少讯飞 TTS 配置")

        host = service_config()["XUNFEI_TTS_HOST"]
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
                            "vcn": voice,
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
