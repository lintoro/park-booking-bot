import re
from datetime import date, datetime, timedelta
from app.core.capacity_gate import get_current_taipei_time

CHINESE_NUMS = {
    "零": 0, "一": 1, "二": 2, "兩": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    "二十": 20, "三十": 30, "四十": 40, "五十": 50
}

def chinese_to_number(text: str) -> int:
    """轉換常見繁體中文數字為整數"""
    text = text.strip()
    if text.isdigit():
        return int(text)
    if text in CHINESE_NUMS:
        return CHINESE_NUMS[text]
    # 簡單十位數處理，例如 "二十五" -> 25, "三十八" -> 38, "十五" -> 15
    m = re.match(r"^([一二兩三四五六七八九]?)(?:十)([一二兩三四五六七八九]?)$", text)
    if m:
        tens_str, ones_str = m.groups()
        tens = 1 if not tens_str else (2 if tens_str in ["二", "兩"] else CHINESE_NUMS.get(tens_str, 1))
        ones = CHINESE_NUMS.get(ones_str, 0) if ones_str else 0
        return tens * 10 + ones
    return 0

def parse_relaxed_date(text: str) -> date | None:
    """寬容解析入園日期，支援 YYYY-MM-DD、MM/DD、X月X日、今天、明天、本週六等"""
    now = get_current_taipei_time()
    today = now.date()
    t = text.strip().lower()

    if "今天" in t:
        return today
    if "明天" in t:
        return today + timedelta(days=1)
    if "後天" in t:
        return today + timedelta(days=2)

    # 星期處理 (本週六、本週日、下週六、下週日)
    weekday_map = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}
    m_week = re.search(r"(本|下)週([一二三四五六日天])", t)
    if m_week:
        prefix, w_char = m_week.groups()
        target_weekday = weekday_map[w_char]
        current_weekday = today.weekday()
        days_ahead = target_weekday - current_weekday
        if prefix == "本":
            if days_ahead <= 0:
                days_ahead += 7
        elif prefix == "下":
            days_ahead += 7
        return today + timedelta(days=days_ahead)

    # 完整年月日 2026-10-25 或 2026/10/25 或 2026.10.25
    m_full = re.search(r"(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})", t)
    if m_full:
        try:
            return date(int(m_full.group(1)), int(m_full.group(2)), int(m_full.group(3)))
        except ValueError:
            return None

    # 月日 10/25 或 10-25 或 10.25 或 10月25日
    m_short = re.search(r"(\d{1,2})[-/.月](\d{1,2})(?:[日號])?", t)
    if m_short:
        try:
            y = today.year
            parsed = date(y, int(m_short.group(1)), int(m_short.group(2)))
            if parsed < today:
                parsed = date(y + 1, int(m_short.group(1)), int(m_short.group(2)))
            return parsed
        except ValueError:
            return None

    return None

def parse_relaxed_time(text: str) -> str | None:
    """寬容解析入園時段，支援 10:30、1030、10點半、下午2點、14:00 等"""
    t = text.strip()
    # 支援 HH:MM
    m_standard = re.search(r"(\b(?:[01]?\d|2[0-3]):[0-5]\d\b)", t)
    if m_standard:
        val = m_standard.group(1)
        return "0" + val if len(val) == 4 else val

    # 支援 4 位純數字如 1030, 1400
    m_digits = re.search(r"\b([01]?\d|2[0-3])([0-5]\d)\b", t)
    if m_digits:
        h, m = m_digits.groups()
        return f"{int(h):02d}:{m}"

    # 支援中文表達：例如「下午2點」、「下午2點半」、「10點半」、「10點30分」
    is_pm = "下午" in t or "晚上" in t or "pm" in t.lower()
    m_chinese = re.search(r"(\d{1,2}|[一二兩三四五六七八九十]+)點(?:([0-5]?\d)分?|(半))?", t)
    if m_chinese:
        hour_str, min_str, is_half = m_chinese.groups()
        h = chinese_to_number(hour_str) if not hour_str.isdigit() else int(hour_str)
        if is_pm and h < 12:
            h += 12
        if is_half:
            m = 30
        elif min_str:
            m = int(min_str)
        else:
            m = 0
        if 0 <= h <= 23 and 0 <= m <= 59:
            return f"{h:02d}:{m:02d}"

    return None

def parse_relaxed_headcounts(text: str) -> tuple[int, int, int]:
    """寬容解析人數，支援「30大10小2幼」、「全票30 半票10」、「全部40人」等"""
    t = text.strip()
    adult = 0
    concession = 0
    child = 0

    # 1. 關鍵字比對
    # 全票 / 大人
    m_adult = re.search(r"(?:全(?:票)?|大(?:人)?)\s*[:：]?\s*(\d+|[一二兩三四五六七八九十]+)", t)
    # 半票 / 小孩 / 學生 / 敬老
    m_concession = re.search(r"(?:半(?:票)?|小(?:孩)?|童|學(?:生)?|老)\s*[:：]?\s*(\d+|[一二兩三四五六七八九十]+)", t)
    # 幼童 / 免票 (支援幼童、幼兒、免票、免費)
    m_child = re.search(r"(?:幼(?:童|兒|票)?|免(?:費|票)?|童(?:票)?)\s*[:：]?\s*(\d+|[一二兩三四五六七八九十]+)", t)

    has_keyword = False
    if m_adult:
        adult = int(m_adult.group(1)) if m_adult.group(1).isdigit() else chinese_to_number(m_adult.group(1))
        has_keyword = True
    if m_concession:
        concession = int(m_concession.group(1)) if m_concession.group(1).isdigit() else chinese_to_number(m_concession.group(1))
        has_keyword = True
    if m_child:
        child = int(m_child.group(1)) if m_child.group(1).isdigit() else chinese_to_number(m_child.group(1))
        has_keyword = True

    if has_keyword:
        return adult, concession, child

    # 2. 若為多個數字空格或逗號隔開：30 10 2，或單一數字「40人」
    nums = [int(n) for n in re.findall(r"\d+", t)]
    if len(nums) >= 3:
        return nums[0], nums[1], nums[2]
    elif len(nums) == 2:
        return nums[0], nums[1], 0
    elif len(nums) == 1:
        # 只輸入單一數字 (例如 "40人"、"40位"、"40")，自動全部歸為全票！
        return nums[0], 0, 0

    # 3. 中文數字單一總人數，例如 "三十人"、"二十五位"
    m_single_cn = re.search(r"([一二兩三四五六七八九十]+)\s*[人位個]", t)
    if m_single_cn:
        val = chinese_to_number(m_single_cn.group(1))
        if val > 0:
            return val, 0, 0

    return 0, 0, 0

def parse_relaxed_bus(text: str) -> int:
    """寬容解析遊覽車台數"""
    t = text.strip()
    if any(k in t for k in ["無", "沒有", "否", "0", "不用", "沒"]):
        return 0
    m = re.search(r"(\d+|[一二兩三四五六七八九十]+)\s*(?:台|輛|車)?", t)
    if m:
        val_str = m.group(1)
        return int(val_str) if val_str.isdigit() else chinese_to_number(val_str)
    return 0
