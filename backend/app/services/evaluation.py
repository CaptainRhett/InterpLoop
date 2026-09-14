"""One validated evaluation contract for real and mock model responses."""
import json
import math
import re


class EvaluationFormatError(ValueError):
    pass


def normalize_evaluation(value, provider):
    if not isinstance(value, dict):
        raise EvaluationFormatError("评价必须为 JSON 对象")
    score = value.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 1 <= score <= 10:
        raise EvaluationFormatError("评价总分必须为 1–10 的数字")
    structured = {"score": round(score, 1)}
    for key in ("overall", "reference_translation"):
        if not isinstance(value.get(key), str) or not value[key].strip():
            raise EvaluationFormatError(f"评价缺少 {key}")
        structured[key] = value[key].strip()
    for key in ("pros", "cons", "suggestions"):
        items = value.get(key)
        if not isinstance(items, list) or not items or any(not isinstance(item, str) or not item.strip() for item in items):
            raise EvaluationFormatError(f"评价字段 {key} 必须为非空字符串数组")
        structured[key] = [item.strip() for item in items]
    score_text = f"{structured['score']:g}"
    # Fixed headings allow text imports to use the same split as native archives.
    text = "\n".join([
        "【总评】", f"总体评分：{score_text}/10", structured["overall"],
        "【优点】", *[f"• {item}" for item in structured["pros"]],
        "【问题】", *[f"• {item}" for item in structured["cons"]],
        "【改进建议】", *[f"• {item}" for item in structured["suggestions"]],
        "【参考译文】", structured["reference_translation"],
    ])
    return {"score": score_text, "feedback_text": text,
            "reference_translation": structured["reference_translation"],
            "evaluation_json": {"provider": provider, "schema_version": 1, "structured": structured}}


def parse_evaluation(text, provider="doubao"):
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    try:
        value = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise EvaluationFormatError("AI 未返回有效的 JSON 评价") from exc
    return normalize_evaluation(value, provider)


def feedback_fields(evaluation_json):
    value = evaluation_json["structured"]
    return {
        **{key: "\n".join(f"• {item}" for item in value[key]) for key in ("pros", "cons", "suggestions")},
        "overall": f"总体评分：{value['score']:g}/10\n{value['overall']}",
    }
