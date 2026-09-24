"""
LINE Flex Message 模板渲染與變數注入模組 (template_renderer.py)

與後端框架完全解耦，讀取獨立 JSON 模板並注入資料，
生成符合 LINE Messaging API 規範之 Flex Message 結構。
未來平移至 Node.js 時，可 100% 沿用相同的 JSON 模板。
"""
import json
import os
from typing import Dict, Any, List, Optional
from pathlib import Path

from app.core.pricing import PricingResult
from app.config import (
    DEFAULT_STAFF_NAME,
    DEFAULT_STAFF_PHONE,
    DEFAULT_STAFF_EXT,
    DEFAULT_SERVICE_HOURS,
)

TEMPLATES_DIR = Path(__file__).resolve().parent


def _load_template_raw(filename: str) -> str:
    """載入指定模板檔案的原始字串內容"""
    file_path = TEMPLATES_DIR / filename
    if not file_path.exists():
        raise FileNotFoundError(f"找不到 Flex 模板檔案：{file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def _replace_placeholders(text: str, context: Dict[str, Any]) -> str:
    """替換字串中所有的 {{key}} 變數佔位符"""
    result = text
    for key, val in context.items():
        placeholder = f"{{{{{key}}}}}"
        result = result.replace(placeholder, str(val))
    return result


def render_confirmation_card(
    group_name: str,
    contact_name: str,
    contact_phone: str,
    booking_date: str,
    booking_time: str,
    session_type: str,
    pricing: PricingResult,
    invoice_title: Optional[str] = None,
    invoice_tax_id: Optional[str] = None,
    session_id: str = "default_session"
) -> Dict[str, Any]:
    """
    渲染【預約核對確認卡 (confirmation_card.json)】
    """
    raw_json = _load_template_raw("confirmation_card.json")

    # 統編與發票抬頭資訊整合
    tax_info = "免開立統一編號"
    if invoice_tax_id and invoice_tax_id.strip() and invoice_tax_id.strip() != "無":
        if invoice_title and invoice_title.strip() and invoice_title.strip() != "無":
            tax_info = f"{invoice_tax_id} ({invoice_title})"
        else:
            tax_info = invoice_tax_id

    context = {
        "group_name": group_name,
        "contact_name": contact_name,
        "contact_phone": contact_phone,
        "booking_date": booking_date,
        "booking_time": booking_time,
        "session_type": session_type,
        "adult_count": f"{pricing.adult_count:,}",
        "adult_subtotal": f"{pricing.adult_subtotal:,}",
        "concession_count": f"{pricing.concession_count:,}",
        "concession_subtotal": f"{pricing.concession_subtotal:,}",
        "child_count": f"{pricing.child_count:,}",
        "tour_bus_count": f"{pricing.tour_bus_count:,}",
        "free_crew_count": f"{pricing.free_crew_count:,}",
        "total_admission_count": f"{pricing.total_admission_count:,}",
        "tax_id_info": tax_info,
        "total_amount": f"{pricing.total_amount:,}",
        "deposit_amount": f"{pricing.deposit_amount:,}",
        "session_id": session_id,
    }

    rendered_str = _replace_placeholders(raw_json, context)
    return json.loads(rendered_str)


def render_time_slot_card(
    booking_date: str,
    available_slots: List[str],
    status_notice: Optional[str] = None
) -> Dict[str, Any]:
    """
    渲染【入園時段選擇卡 (time_slot_card.json)】
    並動態將可選時段按鈕以多欄排版方式注入卡片主體中。
    """
    raw_json = _load_template_raw("time_slot_card.json")

    if not status_notice:
        if available_slots:
            status_notice = f"目前共有 {len(available_slots)} 個可預約梯次："
        else:
            status_notice = "該日所有梯次皆已額滿或已截止，請選擇其他日期。"

    context = {
        "booking_date": booking_date,
        "status_notice": status_notice,
    }

    rendered_str = _replace_placeholders(raw_json, context)
    bubble = json.loads(rendered_str)

    # 動態產生可選梯次按鈕 (以每行 3 個按鈕水平排列)
    if available_slots:
        slot_buttons_box = {
            "type": "box",
            "layout": "vertical",
            "spacing": "xs",
            "margin": "md",
            "contents": []
        }

        # 分批每 3 個梯次一橫排
        chunk_size = 3
        for i in range(0, len(available_slots), chunk_size):
            row_slots = available_slots[i:i + chunk_size]
            row_box = {
                "type": "box",
                "layout": "horizontal",
                "spacing": "xs",
                "contents": []
            }
            for slot in row_slots:
                row_box["contents"].append({
                    "type": "button",
                    "style": "secondary",
                    "height": "sm",
                    "action": {
                        "type": "message",
                        "label": slot,
                        "text": slot
                    }
                })
            # 若末列不足 3 個按鈕，補齊空 filler 維持等寬對齊
            while len(row_box["contents"]) < chunk_size:
                row_box["contents"].append({
                    "type": "filler"
                })
            slot_buttons_box["contents"].append(row_box)

        # 插入至 body contents 末尾
        bubble["body"]["contents"].append(slot_buttons_box)

    return bubble


def render_contact_card(
    staff_name: str = DEFAULT_STAFF_NAME,
    staff_phone: str = DEFAULT_STAFF_PHONE,
    staff_ext: str = DEFAULT_STAFF_EXT,
    service_hours: str = DEFAULT_SERVICE_HOURS,
    phone_dial: Optional[str] = None
) -> Dict[str, Any]:
    """
    渲染【真人客服專人名片 (contact_card.json)】
    """
    raw_json = _load_template_raw("contact_card.json")

    # 去除電話符號以供 tel: 協定使用
    raw_dial = phone_dial or staff_phone.replace("-", "").replace(" ", "").replace("(", "").replace(")", "")

    context = {
        "staff_name": staff_name,
        "staff_phone": staff_phone,
        "staff_ext": staff_ext,
        "service_hours": service_hours,
        "staff_phone_raw": raw_dial,
    }

    rendered_str = _replace_placeholders(raw_json, context)
    return json.loads(rendered_str)


def render_service_menu_carousel() -> Dict[str, Any]:
    """
    渲染【多功能服務選單輪播卡片 (service_menu_carousel.json)】
    包含：團體預約、票務試算、設施導覽、專人餐飲四大視覺入口
    """
    raw_json = _load_template_raw("service_menu_carousel.json")
    return json.loads(raw_json)


def render_tickets_card() -> Dict[str, Any]:
    """
    渲染【票務與團體特惠價格表卡片 (tickets_card.json)】
    """
    raw_json = _load_template_raw("tickets_card.json")
    return json.loads(raw_json)


def render_attractions_card() -> Dict[str, Any]:
    """
    渲染【園區熱門設施與導覽卡片 (attractions_card.json)】
    """
    raw_json = _load_template_raw("attractions_card.json")
    return json.loads(raw_json)


def render_date_picker_card(reference_date: Optional[Any] = None) -> Dict[str, Any]:
    """
    渲染【入園日期快捷選擇卡片 (date_picker_card.json)】
    包含熱門檔期快捷按鈕與原生日曆選擇器
    """
    from datetime import date, timedelta
    ref = reference_date or date.today()

    # 計算未來最近的週末與檔期快捷
    # 0=週一, 5=週六, 6=週日
    days_to_sat = (5 - ref.weekday()) % 7
    if days_to_sat == 0:
        days_to_sat = 7
    next_sat = ref + timedelta(days=days_to_sat)
    next_sun = next_sat + timedelta(days=1)
    following_sat = next_sat + timedelta(days=7)
    following_sun = following_sat + timedelta(days=1)

    tomorrow = ref + timedelta(days=1)
    max_d = ref + timedelta(days=180)

    raw_json = _load_template_raw("date_picker_card.json")
    context = {
        "quick_date_1_label": f"本週六 ({next_sat.strftime('%m/%d')})",
        "quick_date_1_val": str(next_sat),
        "quick_date_2_label": f"本週日 ({next_sun.strftime('%m/%d')})",
        "quick_date_2_val": str(next_sun),
        "quick_date_3_label": f"下週六 ({following_sat.strftime('%m/%d')})",
        "quick_date_3_val": str(following_sat),
        "quick_date_4_label": f"下週日 ({following_sun.strftime('%m/%d')})",
        "quick_date_4_val": str(following_sun),
        "initial_date": str(tomorrow),
        "min_date": str(ref),
        "max_date": str(max_d),
    }
    rendered_str = _replace_placeholders(raw_json, context)
    return json.loads(rendered_str)


def render_headcount_card() -> Dict[str, Any]:
    """
    渲染【入園人數規模快捷卡片 (headcount_card.json)】
    """
    raw_json = _load_template_raw("headcount_card.json")
    return json.loads(raw_json)


def render_bus_card() -> Dict[str, Any]:
    """
    渲染【交通車輛與司領免票登記卡片 (bus_card.json)】
    """
    raw_json = _load_template_raw("bus_card.json")
    return json.loads(raw_json)


def render_invoice_card() -> Dict[str, Any]:
    """
    渲染【發票開立方式選擇卡片 (invoice_card.json)】
    """
    raw_json = _load_template_raw("invoice_card.json")
    return json.loads(raw_json)

