import re

import requests
from flask import current_app


DIRECTION_LANGUAGES = {
    "日→中": ("日语", "中文"),
    "中→日": ("中文", "日语"),
    "英→中": ("英语", "中文"),
    "中→英": ("中文", "英语"),
}


class LLMClient:
    def __init__(self):
        self.mock = current_app.config["USE_MOCK_SERVICES"]
        self.base_url = current_app.config["DOUBAO_BASE_URL"].rstrip("/")
        self.api_key = current_app.config["DOUBAO_API_KEY"]
        self.model = current_app.config["DOUBAO_MODEL"] or "doubao-mock"
        self.timeout = current_app.config["LLM_TIMEOUT_SECONDS"]

    def evaluate(self, source_text, asr_text, direction, prompt_params):
        if self.mock or not self.api_key or not current_app.config["DOUBAO_MODEL"]:
            return self._mock_evaluate(source_text, asr_text, direction)

        prompt = self._build_prompt(source_text, asr_text, direction, prompt_params)
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "你是一名严谨的中日及中英口译教学评估助手。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        text = payload["choices"][0]["message"]["content"]
        return {
            "score": self._extract_score(text),
            "feedback_text": text,
            "reference_translation": self._extract_reference_translation(text),
            "evaluation_json": {"provider": "doubao", "raw": payload},
        }

    def _build_prompt(self, source_text, asr_text, direction, prompt_params):
        dimensions = prompt_params.get("dimensions") or []
        dimensions_text = "\n".join(f"{i + 1}. {item}" for i, item in enumerate(dimensions))
        source_language, target_language = DIRECTION_LANGUAGES.get(direction, ("源语", "目标语"))
        return (
            f"方向：{direction}\n"
            f"源语语言：{source_language}\n"
            f"目标语语言：{target_language}\n"
            f"评审角色：{prompt_params.get('role', '严格口译教师')}\n"
            f"严格程度：{prompt_params.get('strictness', 4)}/5\n"
            f"评价维度：\n{dimensions_text}\n\n"
            f"源语原文：\n{source_text}\n\n"
            f"学生口译 ASR 识别文本：\n{asr_text}\n\n"
            f"请严格按照{target_language}的表达规范输出结构化反馈，包含：总体评分、信息完整度、"
            "术语、语法、语域与表达自然度问题、最优先改进的 2-3 个问题、参考译法。"
            "请避免空泛鼓励，并确保参考译法使用目标语。"
        )

    def _extract_score(self, text):
        for score in ("A+", "A-", "A", "B+", "B-", "B", "C+", "C-", "C"):
            if score in text:
                return score
        return "B"

    def _extract_reference_translation(self, text):
        match = re.search(
            r"(?:参考译法|参考译文|标准译法|建议译文)\s*[：:]\s*(.+?)(?=\n\s*(?:[#*\d一二三四五六七八九十、.（）()]+\s*)?[\u4e00-\u9fff]{2,12}\s*[：:]|\Z)",
            text,
            re.DOTALL,
        )
        return match.group(1).strip() if match else ""

    def _mock_evaluate(self, source_text, asr_text, direction):
        short_source = source_text[:80] + ("..." if len(source_text) > 80 else "")
        short_asr = asr_text[:80] + ("..." if len(asr_text) > 80 else "")
        structured = {
            "score": "B+",
            "summary": "信息主干基本完整，表达可懂，但术语稳定性和正式语体仍需加强。",
            "items": [
                {"dimension": "信息完整度", "comment": "核心信息保留较好，少量修饰信息有压缩。"},
                {"dimension": "术语规范", "comment": "专名和固定表达需要统一译法。"},
                {"dimension": "表达自然度", "comment": "部分句子受源语结构影响，目标语不够顺。"},
            ],
            "priority": ["先核对机构名和活动名", "复盘长句切分", "建立高频敬语/正式表达表"],
            "reference_translation": "请结合课堂标准译法补充参考译文。",
        }
        return {
            "score": structured["score"],
            "feedback_text": (
                f"【模拟评价】方向：{direction}\n"
                f"源语摘要：{short_source}\n"
                f"ASR摘要：{short_asr}\n\n"
                "总体评分：B+\n"
                "信息完整度：核心信息基本完整，个别修饰信息略有压缩。\n"
                "术语与语体：活动名称、机构名称和正式语体需要保持一致。\n"
                "优先改进：先处理专名准确性，再处理长句断句和目标语自然度。\n"
                "参考译法：请结合课堂标准译法补充。"
            ),
            "reference_translation": structured["reference_translation"],
            "evaluation_json": {"provider": "mock", "structured": structured},
        }
