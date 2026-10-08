"""工程表格日期解析：只解析明确日期，缺少日/年份时不猜测。"""
import re
import unicodedata
from datetime import date, datetime


def chinese_number(value):
    digits = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if "十" in value:
        left, right = value.split("十", 1)
        return (digits[left] if left else 1) * 10 + (digits[right] if right else 0)
    return int("".join(str(digits[c]) for c in value))


def normalize_date(value):
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    try:
        return re.sub(r"[零〇一二两三四五六七八九十]+(?=[年月日号])",
                      lambda m: str(chinese_number(m.group())), text)
    except (ValueError, KeyError) as exc:
        raise ValueError("中文数字日期未识别，请使用明确的年月日") from exc


def parse_business_date(value):
    if isinstance(value, (datetime, date)):
        day = value.date() if isinstance(value, datetime) else value
        return day.isoformat(), day.strftime("%m-%d")
    text = normalize_date(value)
    if not text:
        return None, None
    time_suffix = r"(?:[ T]\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?)?"
    full = re.fullmatch(r"(\d{4})\s*[-/.年]\s*(\d{1,2})\s*[-/.月]\s*(\d{1,2})\s*(?:日|号)?" + time_suffix, text)
    short = re.fullmatch(r"(\d{1,2})\s*[-/.月]\s*(\d{1,2})\s*(?:日|号)?", text)
    if full:
        day = date(*map(int, full.groups()))
        return day.isoformat(), day.strftime("%m-%d")
    if short:
        month, day = map(int, short.groups())
        date(2000, month, day)
        return None, f"{month:02d}-{day:02d}"
    if re.fullmatch(r"\d{4}年\d{1,2}月", text):
        raise ValueError("日期只有年月，缺少具体日，不能用于按日匹配")
    raise ValueError("日期未识别或存在歧义；支持 YYYY-MM-DD、9月9日、9/9、9.9、09-09、中文数字日期，不自动补齐年份或日")


def date_quality(raw):
    if not str(raw or "").strip():
        return None, None, "missing", "日期未登记"
    try:
        full, short = parse_business_date(raw)
        return full, short, "full" if full else "month_day", ""
    except ValueError as exc:
        return None, None, "partial" if "缺少具体日" in str(exc) else "unrecognized", str(exc)


def date_from_label(value):
    text = normalize_date(value)
    pattern = r"(?<!\d)(?:\d{4}[-/年.]\d{1,2}[-/月.]\d{1,2}(?:日|号)?|\d{1,2}月\d{1,2}(?:日|号)|\d{1,2}[-/.]\d{1,2}(?!\d)|\d{4}年\d{1,2}月)"
    found = list(dict.fromkeys(m.group() for m in re.finditer(pattern, text)))
    return found[0] if len(found) == 1 else ("日期上下文包含多个日期：" + "、".join(found) if found else "")
