"""Database overrides, with encrypted credentials and per-request snapshots."""
import base64
import hashlib
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from flask import current_app, g, has_request_context

from ..models import ServiceSettings, db

DEFAULTS = {
    "LLM_PROVIDER": "doubao", "ASR_PROVIDER": "xunfei",
    "ASR_BASE_URL": "https://api.openai.com/v1", "ASR_API_KEY": "", "ASR_MODEL": "whisper-1",
    "XUNFEI_IAT_DOMAIN": "iat",
}
FIELDS = {
    **DEFAULTS, "USE_MOCK_SERVICES": True, "DOUBAO_BASE_URL": "", "DOUBAO_API_KEY": "",
    "DOUBAO_MODEL": "", "LLM_TIMEOUT_SECONDS": 45, "XUNFEI_APP_ID": "",
    "XUNFEI_API_KEY": "", "XUNFEI_API_SECRET": "", "XUNFEI_IAT_HOST": "iat-api.xfyun.cn",
}
SECRETS = {"DOUBAO_API_KEY", "ASR_API_KEY", "XUNFEI_API_KEY", "XUNFEI_API_SECRET"}


def cipher():
    key = current_app.config["SECRET_KEY"]
    if isinstance(key, str):
        key = key.encode()
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(key).digest()))


def service_config():
    if has_request_context() and hasattr(g, "service_config"):
        return g.service_config
    config = {**DEFAULTS, **current_app.config}
    row = db.session.get(ServiceSettings, 1) if "sqlalchemy" in current_app.extensions else None
    if row:
        for key, value in row.values.items():
            config[key] = cipher().decrypt(value.encode()).decode() if key in SECRETS and value else value
    if has_request_context():
        g.service_config = config
    return config


def public_settings():
    config = service_config()
    row = db.session.get(ServiceSettings, 1)
    overrides = row.values if row else {}
    return {"settings": {key: config.get(key, default) for key, default in FIELDS.items() if key not in SECRETS},
            "sources": {key: "web" if key in overrides else "environment" for key in FIELDS},
            "secrets_configured": {key: bool(config.get(key)) for key in SECRETS}}


def save_settings(data):
    if not isinstance(data, dict) or set(data) - set(FIELDS):
        raise ValueError("配置字段无效")
    cleaned = {}
    for key, value in data.items():
        if value is None:
            cleaned[key] = None  # Explicitly remove this override and inherit the environment.
            continue
        if key == "USE_MOCK_SERVICES":
            if not isinstance(value, bool):
                raise ValueError("模拟模式必须为布尔值")
        elif key == "LLM_TIMEOUT_SECONDS":
            if isinstance(value, bool) or not isinstance(value, int) or not 5 <= value <= 120:
                raise ValueError("超时必须为 5–120 秒的整数")
        else:
            if not isinstance(value, str) or len(value) > 4096:
                raise ValueError("配置值必须是有效文本")
            value = value.strip()
            if key in SECRETS and not value:
                continue  # Blank password inputs retain the saved/environment secret.
            if key in {"LLM_PROVIDER", "ASR_PROVIDER"}:
                choices = {"doubao", "openai_compatible"} if key == "LLM_PROVIDER" else {"xunfei", "openai_compatible"}
                if value not in choices:
                    raise ValueError("不支持的服务类型")
            if key.endswith("BASE_URL"):
                url = urlsplit(value)
                if url.scheme not in {"https", "http"} or not url.hostname or url.username or url.password or url.query or url.fragment:
                    raise ValueError("API 基础地址须为不含账号、查询参数的 HTTP(S) 地址")
                value = value.rstrip("/")
            if key == "XUNFEI_IAT_HOST" and (not value or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-" for c in value)):
                raise ValueError("讯飞主机只填写域名，不含协议或路径")
        cleaned[key] = value
    row = db.session.get(ServiceSettings, 1)
    if not row:
        row = ServiceSettings(id=1, values={})
        db.session.add(row)
    values = dict(row.values)
    for key, value in cleaned.items():
        if value is None:
            values.pop(key, None)
        else:
            values[key] = cipher().encrypt(value.encode()).decode() if key in SECRETS else value
    row.values = values
    if has_request_context():
        g.pop("service_config", None)
    return sorted(cleaned)
