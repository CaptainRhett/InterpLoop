import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")


def _bool(name, default=False):
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    API_TITLE = "InterpLoop API"
    API_VERSION = "1.0.0"
    OPENAPI_VERSION = "3.0.3"
    OPENAPI_URL_PREFIX = "/api"
    OPENAPI_JSON_PATH = "openapi.json"
    OPENAPI_SWAGGER_UI_PATH = "/docs"
    OPENAPI_SWAGGER_UI_URL = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5.17.14/"
    OPENAPI_SWAGGER_UI_CONFIG = {
        "withCredentials": True,
        "displayRequestDuration": True,
        "validatorUrl": None,
    }

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-change-me")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", f"sqlite:///{ROOT_DIR / 'instance' / 'interploop.sqlite3'}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }

    CORS_ORIGINS = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",")
        if origin.strip()
    ]

    REQUIRE_PRACTICE_CONTEXT = _bool("REQUIRE_PRACTICE_CONTEXT", True)
    PASSWORD_MIN_LENGTH = int(os.getenv("PASSWORD_MIN_LENGTH", "8"))
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)
    GUEST_SESSION_SECONDS = int(os.getenv("GUEST_SESSION_SECONDS", "7200"))
    PERMANENT_SESSION_LIFETIME = timedelta(
        hours=int(os.getenv("SESSION_LIFETIME_HOURS", "12"))
    )
    USE_MOCK_SERVICES = _bool("USE_MOCK_SERVICES", True)

    UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", ROOT_DIR / "var" / "uploads"))
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_UPLOAD_MB", "25")) * 1024 * 1024

    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "doubao")
    ASR_PROVIDER = os.getenv("ASR_PROVIDER", "xunfei")
    ASR_BASE_URL = os.getenv("ASR_BASE_URL", "https://api.openai.com/v1")
    ASR_API_KEY = os.getenv("ASR_API_KEY", "")
    ASR_MODEL = os.getenv("ASR_MODEL", "whisper-1")
    XUNFEI_IAT_DOMAIN = os.getenv("XUNFEI_IAT_DOMAIN", "iat")

    DOUBAO_BASE_URL = os.getenv(
        "DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"
    )
    DOUBAO_API_KEY = os.getenv("DOUBAO_API_KEY", "")
    DOUBAO_MODEL = os.getenv("DOUBAO_MODEL", "")
    LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "45"))

    XUNFEI_APP_ID = os.getenv("XUNFEI_APP_ID", "")
    XUNFEI_API_KEY = os.getenv("XUNFEI_API_KEY", "")
    XUNFEI_API_SECRET = os.getenv("XUNFEI_API_SECRET", "")
    XUNFEI_IAT_HOST = os.getenv("XUNFEI_IAT_HOST", "iat-api.xfyun.cn")
    XUNFEI_TTS_HOST = os.getenv("XUNFEI_TTS_HOST", "tts-api.xfyun.cn")
    XUNFEI_TTS_VOICE_ZH = os.getenv("XUNFEI_TTS_VOICE_ZH", "xiaoyan")
    XUNFEI_TTS_VOICE_JA = os.getenv("XUNFEI_TTS_VOICE_JA", "x2_yumi")
    XUNFEI_TTS_VOICE_EN = os.getenv("XUNFEI_TTS_VOICE_EN", "")
