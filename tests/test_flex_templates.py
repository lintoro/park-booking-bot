"""
測試 LINE Flex Message 視覺卡片模板渲染與 SDK 相容性 (test_flex_templates.py)
"""
import json
import pytest
from linebot.v3.messaging import FlexContainer

from app.core.pricing import calculate_pricing
from app.templates.template_renderer import (
    render_confirmation_card,
    render_time_slot_card,
    render_contact_card,
)


def test_render_confirmation_card():
    """測試預約核對確認卡渲染完整性與 SDK 容器解析"""
    pricing = calculate_pricing(
        adult_count=35,
        concession_count=15,
        child_count=3,
        tour_bus_count=2
    )

    card_dict = render_confirmation_card(
        group_name="台大校友會秋季健行團",
        contact_name="王小明",
        contact_phone="0912-345-678",
        booking_date="2026-10-25",
        booking_time="10:30",
        session_type="上午場",
        pricing=pricing,
        invoice_title="台灣大學",
        invoice_tax_id="03734000",
        session_id="test_session_123"
    )

    json_str = json.dumps(card_dict, ensure_ascii=False)

    # 1. 確保所有佔位符 {{...}} 皆已被完全替換
    assert "{{" not in json_str

    # 2. 驗證關鍵欄位呈現
    assert "台大校友會秋季健行團" in json_str
    assert "王小明" in json_str
    assert "0912-345-678" in json_str
    assert "2026-10-25" in json_str
    assert "10:30" in json_str
    assert "03734000 (台灣大學)" in json_str
    assert "NT$ 11,900" in json_str  # 35*280=9800 + 15*140=2100 => 11900
    assert "NT$ 1,190" in json_str   # 10% 訂金

    # 3. 驗證 line-bot-sdk FlexContainer 能正常解析該 Bubble
    flex_container = FlexContainer.from_dict(card_dict)
    assert flex_container is not None


def test_render_time_slot_card():
    """測試入園時段選擇卡按鈕動態注入與 SDK 容器解析"""
    available_slots = ["13:00", "13:30", "14:00", "14:30", "15:00"]
    card_dict = render_time_slot_card(
        booking_date="2026-10-18",
        available_slots=available_slots,
        status_notice="當日急單管制中：僅開放下午場次"
    )

    json_str = json.dumps(card_dict, ensure_ascii=False)

    # 確保無殘留佔位符
    assert "{{" not in json_str

    # 驗證時段按鈕皆已注入
    for slot in available_slots:
        assert slot in json_str
        assert f"預約時間 {slot}" in json_str

    # 驗證 SDK 解析
    flex_container = FlexContainer.from_dict(card_dict)
    assert flex_container is not None


def test_render_contact_card():
    """測試真人客服專人名片渲染與一鍵撥號協定"""
    card_dict = render_contact_card(
        staff_name="林經理",
        staff_phone="02-8765-4321",
        staff_ext="999",
        service_hours="平日 08:30 - 17:30"
    )

    json_str = json.dumps(card_dict, ensure_ascii=False)

    # 確保無殘留佔位符
    assert "{{" not in json_str

    assert "林經理" in json_str
    assert "02-8765-4321" in json_str
    assert "分機 999" in json_str
    assert "平日 08:30 - 17:30" in json_str
    # 一鍵撥打 tel 協定
    assert "tel:0287654321" in json_str

    # 驗證 SDK 解析
    flex_container = FlexContainer.from_dict(card_dict)
    assert flex_container is not None
