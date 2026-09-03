from flask import Blueprint, jsonify, request

from .auth import require_user

prompt_bp = Blueprint("prompt", __name__)

DEFAULT_DIMENSIONS = [
    "信息完整度",
    "敬语、语域与正式语体",
    "术语和机构名称",
    "句子自然度",
    "优先改进问题",
]

PRESETS = [
    {
        "key": "political",
        "name": "理解当代中国·政治语篇",
        "role": "资深口译评估教师（政府外事方向）",
        "task_type": "汉译日交替传译",
        "dimensions": ["术语规范性", "信息完整性", "句式与语法", "立场表达精准性"],
        "strictness": 4,
    },
    {
        "key": "business",
        "name": "商务口译·研讨会",
        "role": "日语商务口译专家（商务礼仪方向）",
        "task_type": "汉译日交替传译",
        "dimensions": ["句式与语法", "语体匹配度", "表达流畅度", "术语规范性"],
        "strictness": 4,
    },
    {
        "key": "numeric",
        "name": "数字/术语训练",
        "role": "严格的口译考官（CATTI 标准评分）",
        "task_type": "数字口译训练",
        "dimensions": ["信息完整性", "发音准确性", "表达流畅度"],
        "strictness": 5,
    },
    {
        "key": "english_business",
        "name": "中英口译·国际商务",
        "role": "英语商务口译专家（国际商务方向）",
        "task_type": "汉译英交替传译",
        "dimensions": ["信息完整性", "句式与语法", "语体匹配度", "表达流畅度", "术语规范性", "跨文化适配"],
        "strictness": 4,
    },
]


@prompt_bp.get("/prompt-presets")
def prompt_presets():
    require_user()
    return jsonify({"presets": PRESETS, "default_dimensions": DEFAULT_DIMENSIONS})


@prompt_bp.post("/prompt/build")
def build_prompt():
    require_user()
    data = request.get_json(silent=True) or {}
    dimensions = data.get("dimensions") or DEFAULT_DIMENSIONS
    lines = [
        f"你是一名{data.get('role') or '严格口译教师'}。",
        f"任务方向：{data.get('direction') or '日→中'}。",
        f"严格程度：{data.get('strictness') or 4}/5。",
        "请从以下维度评价学生口译：",
    ]
    lines.extend(f"{idx + 1}. {item}" for idx, item in enumerate(dimensions))
    lines.append("请输出总体评分、主要问题、改进建议和参考译法，避免空泛鼓励。")
    return jsonify({"prompt": "\n".join(lines)})
