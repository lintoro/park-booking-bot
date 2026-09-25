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


def render_reservation_detail_card(record: Dict[str, Any]) -> Dict[str, Any]:
    """渲染單筆預約訂單詳細資訊卡片 (支援線上取消預約按鈕)"""
    res_id = str(record.get("預約編號", "未知"))
    group_name = str(record.get("團體名稱", "未指定"))
    contact_name = str(record.get("聯絡窗口", ""))
    contact_phone = str(record.get("聯絡手機", ""))
    booking_date = str(record.get("入園日期", ""))
    booking_time = str(record.get("入場梯次", ""))
    session_type = str(record.get("場次類型", ""))
    total_admission = str(record.get("入場總人數", 0))
    free_crew = str(record.get("隨隊免票數", 0))
    total_amount = str(record.get("門票總額", 0))
    deposit_amount = str(record.get("10%訂金金額", 0))
    deposit_status = str(record.get("訂金狀態", "待收訂金"))
    show_status = str(record.get("到場狀態", "待履約"))
    case_status = str(record.get("案件狀態", "進行中"))

    is_cancelled = "取消" in show_status or "取消" in case_status

    status_color = "#9E9E9E" if is_cancelled else ("#2E7D32" if "已" in deposit_status else "#FB8C00")
    status_text = "已取消" if is_cancelled else f"{deposit_status} / {show_status}"

    footer_contents = []
    if not is_cancelled:
        footer_contents.append({
            "type": "button",
            "style": "secondary",
            "color": "#D32F2F",
            "height": "sm",
            "action": {
                "type": "postback",
                "label": "❌ 取消此筆預約",
                "data": f"action=cancel_confirmed_booking&res_id={res_id}",
                "displayText": f"我要取消預約 {res_id}"
            }
        })
    else:
        footer_contents.append({
            "type": "text",
            "text": "此筆預約已被取消，若需入園請重新預約",
            "color": "#888888",
            "size": "xs",
            "align": "center"
        })

    bubble = {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#37474F",
            "paddingAll": "18px",
            "contents": [
                {
                    "type": "text",
                    "text": "🎫 預約訂單查詢結果",
                    "weight": "bold",
                    "color": "#FFFFFF",
                    "size": "lg"
                },
                {
                    "type": "text",
                    "text": f"單號：{res_id}",
                    "color": "#B0BEC5",
                    "size": "xs",
                    "margin": "xs"
                }
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "paddingAll": "20px",
            "contents": [
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": "預約狀態", "color": "#888888", "size": "sm", "flex": 2},
                        {"type": "text", "text": status_text, "color": status_color, "size": "sm", "weight": "bold", "flex": 4}
                    ]
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": "團體名稱", "color": "#888888", "size": "sm", "flex": 2},
                        {"type": "text", "text": group_name, "color": "#212121", "size": "sm", "weight": "bold", "flex": 4, "wrap": True}
                    ]
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": "入園梯次", "color": "#888888", "size": "sm", "flex": 2},
                        {"type": "text", "text": f"{booking_date} {booking_time} ({session_type})", "color": "#00897B", "size": "sm", "weight": "bold", "flex": 4, "wrap": True}
                    ]
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": "入場人數", "color": "#888888", "size": "sm", "flex": 2},
                        {"type": "text", "text": f"{total_admission} 位 (含隨隊 {free_crew} 位)", "color": "#212121", "size": "sm", "flex": 4}
                    ]
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": "門票總額", "color": "#888888", "size": "sm", "flex": 2},
                        {"type": "text", "text": f"NT$ {int(float(total_amount or 0)):,} 元", "color": "#E65100", "size": "sm", "weight": "bold", "flex": 4}
                    ]
                },
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": "聯絡窗口", "color": "#888888", "size": "sm", "flex": 2},
                        {"type": "text", "text": f"{contact_name} ({contact_phone})", "color": "#555555", "size": "xs", "flex": 4}
                    ]
                }
            ]
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "spacing": "sm",
            "contents": footer_contents
        }
    }
    return bubble


def render_guided_menu_card(
    title: str = "🎡 智慧服務功能導引",
    message: str = "您好！小幫手專注於為您提供園區熱門設施、門票優惠與團體預約相關服務。請點選下方功能，我們將竭誠為您服務："
) -> Dict[str, Any]:
    """
    渲染【制式服務功能導引卡片 (Flex Message)】
    當遊客提問偏離領域或詢問無關問題時，彈出制式按鈕引導回核心功能，限制住回應範圍。
    """
    return {
        "type": "bubble",
        "size": "mega",
        "header": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": "#1565C0",
            "paddingAll": "16px",
            "contents": [
                {
                    "type": "text",
                    "text": title,
                    "weight": "bold",
                    "size": "lg",
                    "color": "#FFFFFF"
                },
                {
                    "type": "text",
                    "text": "星夢歡樂世界 ‧ 官方專屬服務指南",
                    "size": "xs",
                    "color": "#E3F2FD",
                    "margin": "xs"
                }
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "spacing": "md",
            "paddingAll": "16px",
            "contents": [
                {
                    "type": "text",
                    "text": message,
                    "size": "sm",
                    "color": "#333333",
                    "wrap": True
                },
                {
                    "type": "separator",
                    "margin": "md"
                },
                {
                    "type": "box",
                    "layout": "vertical",
                    "spacing": "sm",
                    "contents": [
                        {
                            "type": "button",
                            "style": "primary",
                            "color": "#E65100",
                            "height": "sm",
                            "action": {
                                "type": "message",
                                "label": "👉 我要預約 (20人以上優惠)",
                                "text": "👉 我要預約"
                            }
                        },
                        {
                            "type": "button",
                            "style": "secondary",
                            "height": "sm",
                            "action": {
                                "type": "message",
                                "label": "📋 預約查詢 (進度與取消)",
                                "text": "📋 預約查詢"
                            }
                        },
                        {
                            "type": "button",
                            "style": "secondary",
                            "height": "sm",
                            "action": {
                                "type": "message",
                                "label": "💰 票價試算 (各票種與免票)",
                                "text": "💰 票價試算"
                            }
                        },
                        {
                            "type": "button",
                            "style": "secondary",
                            "height": "sm",
                            "action": {
                                "type": "message",
                                "label": "📞 專人客服 (業務一對一)",
                                "text": "📞 專人客服"
                            }
                        }
                    ]
                }
            ]
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "💡 亦可直接在聊天室輸入您的需求",
                    "size": "xs",
                    "color": "#888888",
                    "align": "center"
                }
            ]
        }
    }


