import re


SECTION_PATTERNS = {
    "pros": re.compile(r"(优点|亮点|可取之处|做得好|做的好|强项|核心优点|主要优点|表现良好)"),
    "cons": re.compile(r"(缺点|不足|问题|主要问题|短板|薄弱|弱项|需要改进的地方|改进点|主要不足|可改进点)"),
    "suggestions": re.compile(r"(建议|改进建议|提升方向|针对性提升方向|改进方向|今后方向|后续方向|改进措施|提升路径)"),
    "overall": re.compile(r"(总评|整体评价|综合评价|整体来看|总体来看|整体表现|总结|结论)"),
    "skip": re.compile(r"(标准参考译文|参考译文|标准译法|参考答案|译文对照)"),
}


def _classify_title(line):
    clean = re.sub(r"\*+", "", line)
    clean = re.sub(r"\s+", "", clean).strip()
    if len(clean) > 35:
        return None

    has_chinese_num = re.match(r"^[一二三四五六七八九十]、", clean)
    has_arabic_num = re.match(r"^\d+[\.\、]", clean)
    has_marker = re.match(r"^[【\[（(].{1,15}[】\]）)]", clean)
    is_pure_keyword = len(clean) <= 12 and any(
        pattern.search(clean) for pattern in SECTION_PATTERNS.values()
    )
    is_short_header = (
        len(clean) <= 25
        and not re.search(r"[，,。；;：:]", clean)
        and any(
            SECTION_PATTERNS[name].search(clean)
            for name in ("pros", "cons", "suggestions", "overall")
        )
    )
    if not any([has_chinese_num, has_arabic_num, has_marker, is_pure_keyword, is_short_header]):
        return None

    if SECTION_PATTERNS["skip"].search(clean):
        return "skip"
    if SECTION_PATTERNS["pros"].search(clean) and not SECTION_PATTERNS["cons"].search(clean):
        return "pros"
    if SECTION_PATTERNS["cons"].search(clean):
        return "cons"
    if SECTION_PATTERNS["suggestions"].search(clean):
        return "suggestions"
    if SECTION_PATTERNS["overall"].search(clean):
        return "overall"
    return None


def _clean_line(line):
    line = re.sub(r"\*+", "", line)
    line = re.sub(r"^[\-•·*]\s*", "", line)
    line = re.sub(r"^\d+[\.\、]\s*", "", line)
    return line.strip()


def _merge_short_and_long(items):
    merged = []
    i = 0
    while i < len(items):
        cur = items[i]
        nxt = items[i + 1] if i + 1 < len(items) else None
        if nxt and len(cur) < 22 and len(nxt) > len(cur) * 1.5 and not re.match(r"^[A-Za-z\d]", nxt):
            merged.append(f"{cur}——{nxt}")
            i += 2
        else:
            merged.append(cur)
            i += 1
    return merged


def parse_feedback_text(text):
    headings = {"总评": "overall", "优点": "pros", "问题": "cons", "改进建议": "suggestions", "参考译文": "skip"}
    if all(f"【{heading}】" in text for heading in headings):
        parts = re.split(r"^【(总评|优点|问题|改进建议|参考译文)】\s*$", text, flags=re.MULTILINE)
        fields = {"pros": "", "cons": "", "suggestions": "", "overall": ""}
        for heading, body in zip(parts[1::2], parts[2::2]):
            key = headings[heading]
            if key != "skip":
                fields[key] = body.strip()
        fields["counts"] = {key: len(fields[key].splitlines()) if fields[key] else 0 for key in ("pros", "cons", "suggestions")}
        return fields
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    buckets = {"pros": [], "cons": [], "suggestions": [], "overall": [], "skip": []}
    current = "overall"

    for line in lines:
        title_type = _classify_title(line)
        if title_type is not None:
            current = title_type
            continue
        if current == "skip":
            continue
        cleaned = _clean_line(line)
        if cleaned:
            buckets[current].append(cleaned)

    for key in ("pros", "cons", "suggestions"):
        buckets[key] = _merge_short_and_long(buckets[key])

    if not buckets["pros"] and not buckets["cons"] and not buckets["suggestions"] and buckets["overall"]:
        recovered = {"pros": [], "cons": [], "suggestions": [], "overall": []}
        for item in buckets["overall"]:
            if re.search(r"建议|应该|可以|需要|希望|今后|下次|加强|改善|提升", item):
                recovered["suggestions"].append(item)
            elif re.search(r"不足|偏差|遗漏|混乱|缺失|有待|薄弱|严重|不够|错误", item):
                recovered["cons"].append(item)
            elif re.search(r"良好|准确|到位|不错|完成度|主动|完整|具备|表现稳定", item):
                recovered["pros"].append(item)
            else:
                recovered["overall"].append(item)
        buckets.update(recovered)

    return {
        "pros": "\n".join(f"• {line}" for line in buckets["pros"]),
        "cons": "\n".join(f"• {line}" for line in buckets["cons"]),
        "suggestions": "\n".join(f"• {line}" for line in buckets["suggestions"]),
        "overall": "\n\n".join(buckets["overall"]),
        "counts": {
            "pros": len(buckets["pros"]),
            "cons": len(buckets["cons"]),
            "suggestions": len(buckets["suggestions"]),
        },
    }
