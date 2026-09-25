"""
對話狀態機與人機協同管理模組 (state_machine.py)

實作優化後之 8 步驟對話問答流程 (Conversational Intake)：
- Step 0: 啟動預約引導 / 園區 FAQ
- Step 1: 詢問團體/學校/公司名稱
- Step 2: 詢問窗口姓名與聯絡手機
- Step 3: 詢問預計入園日期 (獨立題，附今天/明天/週末捷徑按鈕)
- Step 4: 詢問預計到達時段 (獨立題，附可選梯次按鈕，含急單/17:00截止/容量檢核)
- Step 5: 詢問各票種人數 (最低20人成團檢核，寬容支援大人小孩、中文數字、純總人數)
- Step 6: 詢問遊覽車台數 (隨隊司領免票試算，寬容支援中文台數與無)
- Step 7: 詢問發票抬頭與統一編號 (支援無/免/統編抬頭)
- Step 8: 生成結構化 Flex Message 預約核對卡，支援【指定欄位單獨修改】，修改完秒回確認卡
- Step 9: 正式送出預約並生成預約編號流水號，寫入 Google 試算表
"""
import re
import uuid
import logging
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional, Tuple, List

logger = logging.getLogger("state_machine")

from app.config import (
    SESSION_TIMEOUT_MINUTES,
    HUMAN_HANDOFF_KEYWORDS,
    DEFAULT_STAFF_NAME,
    DEFAULT_STAFF_PHONE,
    DEFAULT_STAFF_EXT,
    DEFAULT_SERVICE_HOURS,
    MIN_GROUP_SIZE,
)
from app.core.pricing import (
    calculate_pricing,
    check_group_threshold,
    PricingResult,
)
from app.core.capacity_gate import (
    validate_booking,
    get_available_time_slots,
    TAIPEI_TZ,
    get_current_taipei_time,
)
from app.templates.template_renderer import (
    render_confirmation_card,
    render_time_slot_card,
    render_contact_card,
    render_service_menu_carousel,
    render_tickets_card,
    render_attractions_card,
    render_date_picker_card,
    render_headcount_card,
    render_bus_card,
    render_invoice_card,
    render_reservation_detail_card,
    render_guided_menu_card,
)
from app.services.sheets_service import (
    append_reservation_record,
    get_booked_capacity,
    get_reservations_by_user_id,
    cancel_existing_reservation,
    check_duplicate_booking,
)
from app.services.faq_service import ask_park_faq, is_off_topic_query
from app.core.models import BookingData, UserSession, BotResponse
from app.core.relaxed_parsers import (
    parse_relaxed_date,
    parse_relaxed_time,
    parse_relaxed_headcounts,
    parse_relaxed_bus,
)


# --- 輔助解析工具與防呆判定 ---

# 取消/中斷預約關鍵詞
CANCEL_KEYWORDS = [
    "取消", "取消預約", "放棄", "不要了", "不想預約了", "退出", 
    "中斷", "暫停預約", "結束預約", "不預約了", "不要預約了",
    "不想預約", "不預約", "不要預約", "先不用", "不用了", "算了吧"
]


def is_likely_question_or_faq(text: str) -> bool:
    """
    判斷輸入文字是否為常見問句、園區設施/服務諮詢或打招呼（防止預約流程誤收為填寫資料）
    """
    t = text.strip().lower()
    if not t:
        return False

    # 排除性防呆：若包含 8 碼統編或台灣手機號碼，屬於填單資料而非提問
    if re.search(r"\b\d{8}\b", t) or re.search(r"09\d{2}[-\s]?\d{3}[-\s]?\d{3}", t) or re.search(r"\b09\d{8}\b", t):
        return False

    # 1. 問句特徵標點符號與疑問詞 (含「嗎」、「嘛」、「呢」、「你們有」)
    question_marks = [
        "？", "?", "請問", "想問", "幾點", "多少", "有沒有", "能不能", 
        "可以嗎", "如何", "怎麼", "什麼", "哪裡", "在哪", "為何", "為什麼",
        "可不可以", "是不是", "好玩嗎", "算不算", "嗎", "嘛", "呢",
        "你們有", "有沒有賣", "可以帶", "能帶"
    ]
    if any(q in t for q in question_marks):
        return True

    # 2. 園區業務諮詢實體詞彙
    park_faq_keywords = [
        "營業", "開園", "閉園", "門票", "票價", "多少錢", "費用", "價格",
        "設施", "摩天輪", "雲霄飛車", "海盜船", "旋轉木馬", "碰碰車", "急流泛舟",
        "導覽", "解說", "素食", "便當", "午餐", "餐廳", "野餐", "吃",
        "停車", "遊覽車停車", "捷運", "公車", "接駁", "交通",
        "寵物", "狗", "貓", "雨天", "天氣"
    ]
    if any(k in t for k in park_faq_keywords):
        return True

    # 3. 一般招呼詞
    greetings = ["你好", "您好", "哈囉", "嗨", "早安", "午安", "晚安", "hi", "hello", "hey"]
    if t in greetings:
        return True

    return False


def is_query_reservation_intent(text: str) -> bool:
    """判斷使用者是否表達查詢既有預約或訂單之意圖"""
    t = text.strip()
    if re.search(r"預約.*成功.*[嗎嘛]", t):
        return True
    query_keywords = [
        "預約查詢", "查詢預約", "查預約", "我的預約", "預約紀錄", "預約記錄", 
        "查訂單", "我的訂單", "訂單查詢", "查詢既有預約",
        "預約進度", "查看預約", "查我的預約", "是否有預約成功",
        "有沒有預約成功", "確認預約成功"
    ]
    return any(k in t for k in query_keywords)


def clean_group_name(text: str) -> str:
    """清理並提取團體名稱，去除常見前綴贅字"""
    cleaned = text.strip()
    patterns = [
        r"^團體名稱[：:\s是為]*",
        r"^機構名稱[：:\s是為]*",
        r"^公司名稱[：:\s是為]*",
        r"^學校名稱[：:\s是為]*",
        r"^單位名稱[：:\s是為]*",
        r"^我們是[\s]*",
        r"^我叫[\s]*",
        r"^名稱[：:\s是為]*",
    ]
    for p in patterns:
        cleaned = re.sub(p, "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned


def parse_contact_info(text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    自文字中解析聯絡人姓名與聯絡電話：
    寬容支援「台灣手機 (09XX)」與「全台各縣市家機/市內電話/公司電話 (02~08)」，並支援分機 (#123, ext 123, 分機123)。
    """
    raw = text.strip()

    # 1. 抽取分機號碼 (如 #123, ext 123, 分機123, 轉123)
    ext_part = ""
    ext_match = re.search(r"(?:[#＃]|(?:ext\.?|分機|轉)\s*)(\d{1,6})", raw, re.IGNORECASE)
    if ext_match:
        ext_part = f"#{ext_match.group(1)}"
        raw_without_ext = raw[:ext_match.start()] + " " + raw[ext_match.end():]
    else:
        raw_without_ext = raw

    # 2. 匹配電話號碼
    # A. 台灣手機 (09 開頭 10 碼)
    mobile_pattern = r"(09\d{2}[-\s]?\d{3}[-\s]?\d{3}|09\d{8})"
    # B. 台灣市話 / 家機 (0 開頭區碼 + 本地號碼，如 02, 03, 04, 05, 06, 07, 08, 037, 049, 082 等)
    tel_pattern = r"(\(?0[2-8]\d{0,2}\)?[-—\s]?\d{3,4}[-—\s]?\d{3,4}|\b0[2-8]\d{7,8}\b)"

    matched_phone = None
    name_candidate = raw_without_ext

    m_mobile = re.search(mobile_pattern, raw_without_ext)
    if m_mobile:
        matched_phone = m_mobile.group(1)
        name_candidate = raw_without_ext.replace(m_mobile.group(0), " ").strip()
    else:
        m_tel = re.search(tel_pattern, raw_without_ext)
        if m_tel:
            digits = re.sub(r"\D", "", m_tel.group(1))
            if 8 <= len(digits) <= 11 and digits.startswith("0"):
                matched_phone = m_tel.group(1)
                name_candidate = raw_without_ext.replace(m_tel.group(0), " ").strip()

    if not matched_phone:
        # 備援寬容比對：嘗試尋找連續 8~10 位以 0 開頭之號碼
        alt_match = re.search(r"\b(0\d{7,9})\b", re.sub(r"[-\s()]", "", raw_without_ext))
        if not alt_match:
            return None, None
        digits_phone = alt_match.group(1)
        matched_phone = digits_phone
        name_candidate = raw_without_ext.replace(digits_phone, " ").strip()

    # 格式化輸出電話字串 (保留分機)
    final_phone = f"{matched_phone.strip()}{ext_part}"

    # 清理姓名中的多餘標籤字眼
    name_clean = re.sub(r"(?i)(聯絡人|窗口|聯絡電話|電話|手機|市話|家機)[:：]?", "", name_candidate)
    name_clean = re.sub(r"[^\w\u4e00-\u9fa5a-zA-Z]", "", name_clean).strip()
    if not name_clean or len(name_clean) < 1:
        name_clean = "貴賓聯絡人"

    return name_clean, final_phone



# 快捷日期按鈕
DEFAULT_DATE_QUICK_REPLIES = ["今天", "明天", "本週六", "本週日", "下週六"]

# 常用入園時段按鈕
DEFAULT_TIME_QUICK_REPLIES = [
    "10:00", "10:30", "11:00", "13:00", "13:30", "14:00", "14:30", "15:00"
]

# Step 8 確認卡片的修改快捷按鈕
CONFIRM_QUICK_REPLIES = [
    "✅ 確認送出預約",
    "✏️ 修改預約資料",
    "🏢 改團體名稱",
    "👤 改聯絡電話",
    "📅 改入園日期",
    "⏰ 改到達時段",
    "👥 改人數明細",
    "🚌 改遊覽車數",
    "🧾 改統一編號",
    "🔄 全部重新填寫"
]

# Step 8 微調修改選單按鈕
MODIFY_MENU_QUICK_REPLIES = [
    "🏢 改團體名稱",
    "👤 改聯絡電話",
    "📅 改入園日期",
    "⏰ 改到達時段",
    "👥 改人數明細",
    "🚌 改遊覽車數",
    "🧾 改統一編號",
    "🔙 返回確認卡片",
    "🔄 全部重新填寫"
]


# --- 對話狀態機核心 ---

class ConversationStateMachine:
    """對話狀態機管理核心"""

    def __init__(self):
        self.sessions: Dict[str, UserSession] = {}

    def get_or_create_session(self, user_id: str) -> UserSession:
        """取得或建立使用者 session"""
        now = get_current_taipei_time()
        if user_id not in self.sessions:
            self.sessions[user_id] = UserSession(user_id=user_id, last_active_at=now)
        return self.sessions[user_id]

    def reset_session(self, user_id: str):
        """重置使用者預約對話狀態"""
        now = get_current_taipei_time()
        self.sessions[user_id] = UserSession(user_id=user_id, current_step=0, last_active_at=now)

    def check_timeout(self, session: UserSession) -> bool:
        """檢查是否超過 15 分鐘逾時"""
        now = get_current_taipei_time()
        delta = now - session.last_active_at
        return delta > timedelta(minutes=SESSION_TIMEOUT_MINUTES)

    def handle_follow_event(self, user_id: str) -> BotResponse:
        """處理加好友 (Follow) 事件：自動彈出精美 4 合 1 服務選單 Carousel 輪播卡片"""
        self.reset_session(user_id)
        session = self.get_or_create_session(user_id)
        menu_card = render_service_menu_carousel()
        return BotResponse(
            reply_text="🎡 您好！歡迎加入【星夢歡樂世界】智慧小幫手！\n\n我們提供 20 人以上專屬團體預約特惠、票務試算、設施導覽與專人諮詢。\n請直接在下方卡片點選您需要的服務：",
            flex_card=menu_card,
            quick_replies=["👉 我要預約", "💰 票價試算", "⏰ 導覽時間", "📞 專人客服"]
        )

    def process_message(self, user_id: str, message_text: str, postback_data: Optional[str] = None) -> BotResponse:
        """
        處理來自使用者的文字或 Postback 動作，推動狀態機移轉。
        """
        now = get_current_taipei_time()
        session = self.get_or_create_session(user_id)
        msg = message_text.strip()

        # 0. 服務選單觸發檢測 (支援「選單」、「主選單」、「功能」、「服務」、「你好」等)
        menu_triggers = ["選單", "主選單", "服務", "功能", "menu", "Menu", "MENU", "你好", "您好", "哈囉", "嗨", "hello", "hi", "開始"]
        if (msg in menu_triggers) and (session.current_step in [0, 9] or msg in ["選單", "主選單", "menu", "Menu"]):
            menu_card = render_service_menu_carousel()
            return BotResponse(
                reply_text="🎡 請在下方卡片選擇您需要的服務，亦可直接輸入文字諮詢：",
                flex_card=menu_card,
                quick_replies=["👉 我要預約", "💰 票價試算", "⏰ 導覽時間", "📞 專人客服"]
            )

        # 1. 檢查 15 分鐘逾時防護
        is_timed_out = self.check_timeout(session)
        if is_timed_out and session.current_step > 0:
            self.reset_session(user_id)
            session = self.get_or_create_session(user_id)
            timeout_prefix = "🔔 由於您超過 15 分鐘未回應，系統已自動重置預約對話。\n\n"
        else:
            timeout_prefix = ""

        # 更新最後活躍時間
        session.last_active_at = now

        # 2. 真人接手開關檢測
        if any(keyword in msg for keyword in HUMAN_HANDOFF_KEYWORDS):
            session.is_human_handoff = True
            card = render_contact_card(
                staff_name=DEFAULT_STAFF_NAME,
                staff_phone=DEFAULT_STAFF_PHONE,
                staff_ext=DEFAULT_STAFF_EXT,
                service_hours=DEFAULT_SERVICE_HOURS
            )
            return BotResponse(
                reply_text=f"{timeout_prefix}已為您暫停自動化機器人，為您轉接專人服務！",
                flex_card=card,
                quick_replies=["恢復機器人"]
            )

        if session.is_human_handoff:
            # (A) 使用者表達預約意向：立即自動解除真人接手並啟動預約流程
            if any(k in msg for k in ["預約", "想預約", "我要預約", "開始預約", "團體預約", "我想預約", "報名"]):
                session.is_human_handoff = False
                self.reset_session(user_id)
                session = self.get_or_create_session(user_id)
                start_resp = self._step_0_start(session, timeout_prefix)
                start_resp.reply_text = f"🤖 收到！已為您切回智慧助理，立即啟動團體預約流程。\n\n{start_resp.reply_text}"
                return start_resp

            # (B) 明確輸入恢復關鍵字或點擊按鈕
            elif any(k in msg for k in ["恢復", "返回", "機器人", "繼續"]) or (postback_data and "action=resume_bot" in postback_data):
                session.is_human_handoff = False
                return BotResponse(
                    reply_text="🤖 已為您恢復智慧預約機器人！請輸入「預約」開始填寫資料，或直接向我詢問園區問題。",
                    quick_replies=["我要預約", "園區設施有哪些？", "團體導覽幾點開始？"]
                )

            # (C) 真人接手期間，其餘一般交談維持靜音不干擾真人通話
            else:
                return BotResponse(reply_text=None)

        # 3. Postback 動作處理 (核對確認、微調修改或重新開始)
        if postback_data:
            if "action=confirm_booking" in postback_data:
                return self._handle_confirm_booking(session, timeout_prefix)
            elif "action=show_modify_menu" in postback_data or ("action=restart_booking" in postback_data and session.current_step == 8):
                # 點選卡片上的「✏️ 修改預約資料」按鈕：展示部分微調選單
                return BotResponse(
                    reply_text=(
                        f"{timeout_prefix}✏️ 【請選擇要修改的預約項目】\n\n"
                        f"您無需全部重填！點選下方快捷鍵即可【單獨修改】該項目，其他已填資料都會為您保留：\n"
                        f"（若確定想清空並從頭填寫，可點選「🔄 全部重新填寫」；或點選「🔙 返回確認卡片」）"
                    ),
                    quick_replies=MODIFY_MENU_QUICK_REPLIES
                )
            elif "action=restart_booking" in postback_data or "action=resume_bot" in postback_data:
                self.reset_session(user_id)
                session = self.get_or_create_session(user_id)
                return self._step_0_start(session, timeout_prefix)
            elif "action=cancel_confirmed_booking" in postback_data:
                import urllib.parse
                params = urllib.parse.parse_qs(postback_data)
                res_id = params.get("res_id", [""])[0]
                return self._handle_cancel_confirmed_booking(user_id, res_id, timeout_prefix)
            elif "action=cancel_booking" in postback_data:
                self.reset_session(user_id)
                return BotResponse(
                    reply_text=f"{timeout_prefix}👌 已為您取消本次預約，所有填寫資料均已清空。\n\n若日後需要預約，隨時輸入「預約」即可重新開始，或向我詢問園區設施與導覽資訊！",
                    quick_replies=["我要預約", "園區設施有哪些？", "團體導覽幾點開始？"]
                )

        # 3.1 預約即時查詢 (使用者可隨時輸入「查詢預約」、「我的預約」、「預約成功了嗎」等)
        if is_query_reservation_intent(msg):
            return self._handle_query_reservation(user_id, timeout_prefix)

        # 3.2 取消與中斷預約檢測 (在預約填寫中隨時可輸入「取消」中斷退出)
        if any(k in msg for k in CANCEL_KEYWORDS):
            if session.current_step > 0:
                self.reset_session(user_id)
                return BotResponse(
                    reply_text=f"{timeout_prefix}👌 已為您取消本次預約流程，所有暫存資料均已清空。\n\n若日後需要預約，隨時輸入「預約」即可重新開始，或向我詢問園區各項資訊！",
                    quick_replies=["我要預約", "園區設施有哪些？", "團體導覽幾點開始？"]
                )
            else:
                return BotResponse(
                    reply_text=f"{timeout_prefix}目前沒有進行中的預約喔！隨時輸入「預約」即可開始辦理團體門票預約。",
                    quick_replies=["我要預約", "園區設施有哪些？"]
                )

        # 3.2 Step 8 返回確認卡片指令
        if session.current_step == 8 and any(k in msg for k in ["返回確認卡片", "返回卡片", "看卡片", "查看卡片"]):
            return self._render_confirm_card_response(session, prefix="📋 以下為您的預約確認卡片：")

        # 3.3 Step 8 觸發修改微調選單
        if session.current_step == 8 and any(k in msg for k in ["修改預約資料", "我想修改預約資料", "我想重新填寫預約資料", "修改預約", "改資料", "修改項目"]):
            return BotResponse(
                reply_text=(
                    f"{timeout_prefix}✏️ 【請選擇要修改的預約項目】\n\n"
                    f"您無需全部重填！點選下方快捷鍵即可【單獨修改】該項目，其他已填資料都會為您保留：\n"
                    f"（若確定想清空並從頭填寫，可點選「🔄 全部重新填寫」；或點選「🔙 返回確認卡片」）"
                ),
                quick_replies=MODIFY_MENU_QUICK_REPLIES
            )

        # 4. 關鍵字重啟檢測 (僅在明確要求「全部重新填寫」時清空)
        if any(k in msg for k in ["全部重新填寫", "全部重填", "清空重填", "重頭開始", "重新預約"]):
            self.reset_session(user_id)
            session = self.get_or_create_session(user_id)
            return self._step_0_start(session, timeout_prefix)

        # 預約啟動詞 (僅在 Step 0 尚未進入流程時生效；若已在預約流程中，嚴禁誤重置)
        booking_triggers = ["預約", "想預約", "我要預約", "開始預約", "團體預約", "我想預約", "預約團體", "我要報名"]
        is_negation = any(neg in msg for neg in ["不", "沒", "別", "取消", "放棄", "算"])
        is_asking_how_to = any(k in msg for k in ["如何預約", "怎麼預約", "預約流程", "預約規定", "預約電話"])
        if session.current_step == 0 and any(trigger in msg for trigger in booking_triggers) and not is_negation and not is_asking_how_to:
            self.reset_session(user_id)
            session = self.get_or_create_session(user_id)
            return self._step_0_start(session, timeout_prefix)
        elif session.current_step > 0 and msg.strip() in ["👉 我要預約", "我要預約", "開始預約", "團體預約"]:
            return BotResponse(
                reply_text=(
                    f"{timeout_prefix}📌 您目前正在進行團體預約填寫中（步驟 {session.current_step}）！\n\n"
                    f"• 若想【重新開始填寫】，請點選下方「🔄 全部重新填寫」。\n"
                    f"• 若想【放棄本次預約】，請點選下方「❌ 取消預約」。"
                ),
                quick_replies=["全部重新填寫", "取消預約"]
            )

        # 5. 【指定修改處理】：若處於 Step 8 (確認卡片)，檢查使用者是否發動單獨修改某欄位
        if session.current_step == 8:
            modify_resp = self._check_modify_request(session, msg, timeout_prefix)
            if modify_resp:
                return modify_resp

        # 6. 【單獨修改填寫模式】：若使用者正在單獨修改某個步驟 (editing_step 有值)
        if session.editing_step is not None:
            return self._handle_editing_step_input(session, msg, timeout_prefix)

        # 7. 循序狀態處理
        if session.current_step == 0:
            # 智慧識別：若使用者在未啟動前直接回答了團體名稱（例如「團體名稱是 火山公司」或「XX公司」）
            cleaned_potential_name = clean_group_name(msg)
            if any(k in msg for k in ["團體名稱", "單位名稱", "公司名稱", "學校名稱", "我們是"]) or \
               any(k in cleaned_potential_name for k in ["公司", "國小", "國中", "高中", "大學", "幼兒園", "旅行社", "協會", "教會", "學院", "企業"]):
                session.current_step = 1
                return self._step_1_handle_group_name(session, msg, timeout_prefix)

            # 票務試算 / 票價查詢 ➔ 彈出精美票價 Flex 卡片 + 詳細解答
            if any(k in msg for k in ["票價", "門票", "票務", "多少錢", "費用", "收費", "價格", "優惠"]):
                tickets_card = render_tickets_card()
                faq_reply = ask_park_faq(msg)
                return BotResponse(
                    reply_text=f"{timeout_prefix}{faq_reply}",
                    flex_card=tickets_card,
                    quick_replies=["👉 我要預約", "選單", "專人客服"]
                )

            # 設施導覽 / 導覽時間 ➔ 彈出精美設施 Flex 卡片 + 詳細解答
            if any(k in msg for k in ["設施", "導覽", "摩天輪", "雲霄飛車", "旋轉木馬", "遊樂設施", "遊戲"]):
                attractions_card = render_attractions_card()
                faq_reply = ask_park_faq(msg)
                return BotResponse(
                    reply_text=f"{timeout_prefix}{faq_reply}",
                    flex_card=attractions_card,
                    quick_replies=["👉 我要預約", "選單", "專人客服"]
                )

            faq_reply = ask_park_faq(msg)
            is_off = is_off_topic_query(msg)
            guided_card = render_guided_menu_card(
                title="🎡 園區智慧服務指南" if is_off else "🎡 星夢歡樂世界 服務導覽",
                message="不好意思～小幫手專注於為您解答園區熱門設施、門票優惠與團體預約相關服務。請點選下方功能，我們將竭誠為您服務：" if is_off else "您好！請點選下方功能選單快速辦理，或直接輸入您的預約需求："
            )
            return BotResponse(
                reply_text=f"{timeout_prefix}{faq_reply}",
                flex_card=guided_card,
                quick_replies=["👉 我要預約", "📋 預約查詢", "💰 票價試算", "📞 專人客服"]
            )

        elif session.current_step == 1:
            return self._step_1_handle_group_name(session, msg, timeout_prefix)
        elif session.current_step == 2:
            return self._step_2_handle_contact_info(session, msg, timeout_prefix)
        elif session.current_step == 3:
            return self._step_3_handle_booking_date(session, msg, timeout_prefix)
        elif session.current_step == 4:
            return self._step_4_handle_booking_time(session, msg, timeout_prefix)
        elif session.current_step == 5:
            return self._step_5_handle_ticket_counts(session, msg, timeout_prefix)
        elif session.current_step == 6:
            return self._step_6_handle_bus_count(session, msg, timeout_prefix)
        elif session.current_step == 7:
            return self._step_7_handle_invoice_info(session, msg, timeout_prefix)
        elif session.current_step == 8:
            if any(k in msg for k in ["確認", "送出", "完成", "ok", "OK", "好"]):
                return self._handle_confirm_booking(session, timeout_prefix)
            return BotResponse(
                reply_text=f"{timeout_prefix}請檢視上方預約確認卡片，點選【✅ 確認送出預約】完成預約，或點選下方捷徑修改指定項目：",
                quick_replies=CONFIRM_QUICK_REPLIES
            )
        elif session.current_step == 9:
            faq_reply = ask_park_faq(msg)
            return BotResponse(reply_text=f"{timeout_prefix}{faq_reply}", quick_replies=["我要預約"])

        return self._step_0_start(session, timeout_prefix)

    # --- 各步驟邏輯實作 ---

    def _step_0_start(self, session: UserSession, prefix: str) -> BotResponse:
        session.current_step = 1
        return BotResponse(
            reply_text=(
                f"{prefix}🎡 您好！歡迎使用遊樂園團體預約智慧助理。\n\n"
                f"團體預約享有專屬團體優惠票價（最低 20 人成團），並依遊覽車輛數贈送隨隊免票。\n"
                f"請先告訴我您的【團體／學校／公司名稱】\n"
                f"（隨時可輸入或點選「取消預約」中斷退出）："
            ),
            quick_replies=["取消預約"]
        )

    def _step_1_handle_group_name(self, session: UserSession, msg: str, prefix: str) -> BotResponse:
        # 1. 提問與諮詢防呆：若輸入為園區問題或問句，智慧解答並引導繼續預約或取消
        if is_likely_question_or_faq(msg):
            faq_reply = ask_park_faq(msg)
            is_off = is_off_topic_query(msg)
            card = render_guided_menu_card(
                title="🎡 園區智慧服務指南",
                message="不好意思～小幫手專注於提供園區設施與團體預約服務。您目前正在填寫預約資料，可點選下方功能或繼續填寫："
            ) if is_off else None
            return BotResponse(
                reply_text=(
                    f"{prefix}🤖 關於您的詢問，為您說明如下：\n\n{faq_reply}\n\n"
                    f"───────────────\n"
                    f"📌 【目前仍在預約流程中】\n"
                    f"若要繼續預約，請輸入您的【團體／學校／公司名稱】（例如：快樂旅行社、幸福國小）；\n"
                    f"若暫不預約，可點選下方【❌ 取消預約】。"
                ),
                flex_card=card,
                quick_replies=["取消預約", "📞 專人客服"]
            )

        clean_name = clean_group_name(msg)
        if len(clean_name) < 2 or len(clean_name) > 30:
            return BotResponse(
                reply_text=f"{prefix}團體名稱請輸入 2 ~ 30 個字元的真實團體或機構名稱（例如：快樂旅行社、幸福國小、台灣科技公司）：",
                quick_replies=["取消預約"]
            )

        session.data.group_name = clean_name
        session.current_step = 2
        return BotResponse(
            reply_text=(
                f"{prefix}已收到團體名稱：【{clean_name}】。\n\n"
                f"請提供主要【聯絡人姓名】與【聯絡電話（手機或市話/家機皆可）】\n"
                f"（例如：王小明 0912-345678 或 李主任 02-23456789#123）："
            ),
            quick_replies=["取消預約"]
        )

    def _step_2_handle_contact_info(self, session: UserSession, msg: str, prefix: str) -> BotResponse:
        # 提問防呆
        if is_likely_question_or_faq(msg):
            faq_reply = ask_park_faq(msg)
            is_off = is_off_topic_query(msg)
            card = render_guided_menu_card(
                title="🎡 園區智慧服務指南",
                message="不好意思～小幫手專注於提供園區設施與團體預約服務。您目前正在填寫預約資料，可點選下方功能或繼續填寫："
            ) if is_off else None
            return BotResponse(
                reply_text=(
                    f"{prefix}🤖 關於您的詢問，為您說明如下：\n\n{faq_reply}\n\n"
                    f"───────────────\n"
                    f"📌 【目前預約進度：第 2 步 聯絡資訊】\n"
                    f"若要繼續預約，請提供【聯絡人姓名】與【聯絡電話（手機或家機）】（例如：王小明 0912-345678 或 02-23456789）；\n"
                    f"若暫不預約，可點選下方【❌ 取消預約】。"
                ),
                flex_card=card,
                quick_replies=["取消預約", "📞 專人客服"]
            )

        name, phone = parse_contact_info(msg)
        if not phone:
            return BotResponse(
                reply_text=(
                    f"{prefix}未能成功識別電話號碼格式，請重新輸入聯絡人與聯絡電話（手機或市話/家機皆可）\n"
                    f"（格式範例：王小明 0912-345678 或 李主任 02-23456789#123）："
                ),
                quick_replies=["取消預約"]
            )

        session.data.contact_name = name
        session.data.contact_phone = phone
        session.current_step = 3

        date_card = render_date_picker_card()
        return BotResponse(
            reply_text=(
                f"{prefix}聯絡窗口已登錄：【{name}（{phone}）】。\n\n"
                f"請選擇預計【入園日期】（可點選下方熱門檔期卡片或開啟手機日曆挑選）："
            ),
            flex_card=date_card,
            quick_replies=DEFAULT_DATE_QUICK_REPLIES + ["取消預約"]
        )

    def _step_3_handle_booking_date(self, session: UserSession, msg: str, prefix: str) -> BotResponse:
        """處理第 3 步：獨立入園日期"""
        if is_likely_question_or_faq(msg):
            faq_reply = ask_park_faq(msg)
            return BotResponse(
                reply_text=(
                    f"{prefix}🤖 關於您的詢問，為您說明如下：\n\n{faq_reply}\n\n"
                    f"───────────────\n"
                    f"📌 【目前預約進度：第 3 步 入園日期】\n"
                    f"若要繼續預約，請點選或輸入【預計入園日期】（例如：10/25、明天）；\n"
                    f"若暫不預約，可點選下方【❌ 取消預約】。"
                ),
                quick_replies=DEFAULT_DATE_QUICK_REPLIES + ["取消預約"]
            )

        parsed_date = parse_relaxed_date(msg)
        if not parsed_date:
            date_card = render_date_picker_card()
            return BotResponse(
                reply_text=(
                    f"{prefix}無法辨識日期格式，請點選下方熱門檔期卡片，或輸入如「10/25」或「2026-10-25」："
                ),
                flex_card=date_card,
                quick_replies=DEFAULT_DATE_QUICK_REPLIES + ["取消預約"]
            )

        today = get_current_taipei_time().date()
        if parsed_date < today:
            date_card = render_date_picker_card()
            return BotResponse(
                reply_text=f"{prefix}⚠️ 入園日期不可為過去日期，請點選卡片重新選擇可預約日期：",
                flex_card=date_card,
                quick_replies=DEFAULT_DATE_QUICK_REPLIES + ["取消預約"]
            )

        session.data.booking_date = parsed_date
        session.current_step = 4

        # 取得當日可用梯次並渲染時段卡片
        morning_booked, afternoon_booked = get_booked_capacity(parsed_date)
        available_slots = get_available_time_slots(
            booking_date=parsed_date,
            request_dt=get_current_taipei_time(),
            morning_booked=morning_booked,
            afternoon_booked=afternoon_booked,
            incoming_people=MIN_GROUP_SIZE
        )
        slot_card = render_time_slot_card(str(parsed_date), available_slots)
        qr_slots = (available_slots[:8] if available_slots else DEFAULT_TIME_QUICK_REPLIES) + ["取消預約"]

        return BotResponse(
            reply_text=(
                f"{prefix}已確認入園日期：【{parsed_date}】。\n\n"
                f"請直接點選下方卡片中的【時段梯次按鈕】（亦可手動輸入如「10:30」）："
            ),
            flex_card=slot_card,
            quick_replies=qr_slots
        )

    def _step_4_handle_booking_time(self, session: UserSession, msg: str, prefix: str) -> BotResponse:
        """處理第 4 步：獨立入園時段與容量防呆"""
        # 覆寫/確認追加第二團指令檢測
        if any(k in msg for k in ["確認追加第二團", "確認追加", "追加第二團", "追加新團", "追加預約", "確認追加新團預約", "追加"]):
            session.data.allow_duplicate = True
            if session.data.booking_time:
                session.current_step = 5
                headcount_card = render_headcount_card()
                return BotResponse(
                    reply_text=(
                        f"{prefix}✅ 已確認為同單位【追加第二團】！\n"
                        f"已保留梯次：【{session.data.booking_date} {session.data.booking_time} ({session.data.session_type})】。\n\n"
                        f"請選擇此梯次的【人數規模】（最低滿 20 人成團，可直接點選下方卡片快捷鍵）："
                    ),
                    flex_card=headcount_card,
                    quick_replies=["全票30 半票10 幼童2", "40人", "全票25 半票5", "取消預約"]
                )

        if is_likely_question_or_faq(msg):
            faq_reply = ask_park_faq(msg)
            return BotResponse(
                reply_text=(
                    f"{prefix}🤖 關於您的詢問，為您說明如下：\n\n{faq_reply}\n\n"
                    f"───────────────\n"
                    f"📌 【目前預約進度：第 4 步 到達時段】\n"
                    f"若要繼續預約，請點選下方時段按鈕或輸入時段（如 10:30）；\n"
                    f"若暫不預約，可點選下方【❌ 取消預約】。"
                ),
                quick_replies=DEFAULT_TIME_QUICK_REPLIES + ["取消預約"]
            )

        parsed_time = parse_relaxed_time(msg)
        if not parsed_time:
            return BotResponse(
                reply_text=(
                    f"{prefix}時段格式無法辨識，請點選下方快捷時段，或輸入如「10:30」或「14:00」："
                ),
                quick_replies=DEFAULT_TIME_QUICK_REPLIES + ["取消預約"]
            )

        # 取得該日試算表已預約之即時容量
        morning_booked, afternoon_booked = get_booked_capacity(session.data.booking_date)

        # 調用業務防呆檢核
        validation = validate_booking(
            booking_date=session.data.booking_date,
            booking_time_str=parsed_time,
            incoming_people=MIN_GROUP_SIZE,
            request_dt=get_current_taipei_time(),
            morning_booked=morning_booked,
            afternoon_booked=afternoon_booked
        )

        if not validation.is_valid:
            available_slots = validation.available_slots
            slot_card = render_time_slot_card(
                booking_date=str(session.data.booking_date),
                available_slots=available_slots,
                status_notice=validation.message
            )
            # 準備可用時段 quick replies
            qr_slots = (available_slots[:8] if available_slots else DEFAULT_TIME_QUICK_REPLIES) + ["取消預約"]
            return BotResponse(
                reply_text=f"{prefix}⚠️ 【時段預約防呆提醒】\n{validation.message}\n請重新選擇可預約時段：",
                flex_card=slot_card,
                quick_replies=qr_slots
            )

        # 檢核通過：暫存時段與場次
        session.data.booking_time = parsed_time
        session.data.session_type = validation.session_type or "未定"

        # 避免重複預約檢核 (Duplicate Collision Prevention)
        if not session.data.allow_duplicate:
            dup_rec = check_duplicate_booking(
                booking_date=session.data.booking_date,
                group_name=session.data.group_name or "",
                contact_phone=session.data.contact_phone or ""
            )
            if dup_rec:
                dup_res_id = dup_rec.get("預約編號", "")
                dup_group = dup_rec.get("團體名稱", "")
                dup_time = dup_rec.get("預約時間", "")
                dup_session = dup_rec.get("場次類型", "")
                dup_admission = dup_rec.get("入場總人數", "")
                clean_phone = re.sub(r"\D", "", session.data.contact_phone or "")
                rec_phone = re.sub(r"\D", "", str(dup_rec.get("聯絡手機", "")))

                reason = "聯絡電話相同" if (clean_phone and clean_phone == rec_phone) else "團體名稱相近"
                return BotResponse(
                    reply_text=(
                        f"{prefix}⚠️ 【系統偵測到同日重複預約防呆提醒】\n\n"
                        f"系統比對發現【{session.data.booking_date}】已有一筆相似的預約紀錄（比對原因：{reason}）：\n"
                        f"📋 既有預約單號：【{dup_res_id}】\n"
                        f"🏢 既有團名：{dup_group}\n"
                        f"⏰ 預約梯次：{dup_time} ({dup_session})\n"
                        f"👥 登記人數：{dup_admission} 位\n\n"
                        f"請問您是：\n"
                        f"1. 為不同部門或梯次【追加第二團】？\n"
                        f"2. 欲查詢已成立的預約紀錄？\n\n"
                        f"💡 若確定要為同單位新增第二團，請點選下方【👉 確認追加第二團】即可繼續填寫！"
                    ),
                    quick_replies=["👉 確認追加第二團", "📋 查詢既有預約", "❌ 取消預約"]
                )

        # 檢核通過且無衝突
        session.current_step = 5

        headcount_card = render_headcount_card()
        return BotResponse(
            reply_text=(
                f"{prefix}已保留梯次：【{session.data.booking_date} {parsed_time} ({session.data.session_type})】。\n\n"
                f"請選擇貴團【人數規模】（最低滿 20 人成團，可直接點選下方卡片快捷鍵）："
            ),
            flex_card=headcount_card,
            quick_replies=["全票30 半票10 幼童2", "40人", "全票25 半票5", "取消預約"]
        )

    def _step_5_handle_ticket_counts(self, session: UserSession, msg: str, prefix: str) -> BotResponse:
        """處理第 5 步：人數明細 (寬容解析)"""
        if is_likely_question_or_faq(msg):
            faq_reply = ask_park_faq(msg)
            return BotResponse(
                reply_text=(
                    f"{prefix}🤖 關於您的詢問，為您說明如下：\n\n{faq_reply}\n\n"
                    f"───────────────\n"
                    f"📌 【目前預約進度：第 5 步 人數明細】\n"
                    f"若要繼續預約，請輸入人數明細（最低 20 人成團，例：「全票30 半票10」或「40人」）；\n"
                    f"若暫不預約，可點選下方【❌ 取消預約】。"
                ),
                quick_replies=["40人", "全票25 半票5", "取消預約"]
            )

        adult, concession, child = parse_relaxed_headcounts(msg)
        total_people = adult + concession + child

        if total_people == 0:
            headcount_card = render_headcount_card()
            return BotResponse(
                reply_text=(
                    f"{prefix}未能辨識人數，請點選下方卡片快捷鍵或直接輸入如「40人」："
                ),
                flex_card=headcount_card,
                quick_replies=["全票30 半票10", "40人", "25人", "取消預約"]
            )

        # 成團門檻防呆檢核 (>= 20 人)
        is_met, threshold_msg = check_group_threshold(adult, concession, child)
        if not is_met:
            headcount_card = render_headcount_card()
            return BotResponse(
                reply_text=f"{prefix}⚠️ 【人數未達團體成團標準】\n{threshold_msg}\n\n若您確定有 20 人以上，請點選卡片或重新輸入人數明細：",
                flex_card=headcount_card,
                quick_replies=["40人", "25人", "取消預約"]
            )

        session.data.adult_count = adult
        session.data.concession_count = concession
        session.data.child_count = child
        session.data.group_member_count = total_people
        session.current_step = 6

        bus_card = render_bus_card()
        return BotResponse(
            reply_text=(
                f"{prefix}已登記人數：全票 {adult} 位、半票 {concession} 位、幼童 {child} 位（團員合計 {total_people} 位）。\n\n"
                f"請點選貴團搭乘之【遊覽車台數】（每台享 2 位司領免票）："
            ),
            flex_card=bus_card,
            quick_replies=["無遊覽車", "1台", "2台", "3台", "取消預約"]
        )

    def _step_6_handle_bus_count(self, session: UserSession, msg: str, prefix: str) -> BotResponse:
        """處理第 6 步：遊覽車台數"""
        if is_likely_question_or_faq(msg):
            faq_reply = ask_park_faq(msg)
            return BotResponse(
                reply_text=(
                    f"{prefix}🤖 關於您的詢問，為您說明如下：\n\n{faq_reply}\n\n"
                    f"───────────────\n"
                    f"📌 【目前預約進度：第 6 步 遊覽車台數】\n"
                    f"若要繼續預約，請輸入遊覽車台數（每台享 2 位司領免票，無遊覽車可點下方「無遊覽車」）；\n"
                    f"若暫不預約，可點選下方【❌ 取消預約】。"
                ),
                quick_replies=["無遊覽車", "1台", "2台", "取消預約"]
            )

        bus_count = parse_relaxed_bus(msg)
        session.data.tour_bus_count = bus_count

        pricing = calculate_pricing(
            adult_count=session.data.adult_count,
            concession_count=session.data.concession_count,
            child_count=session.data.child_count,
            tour_bus_count=bus_count
        )
        session.data.free_crew_count = pricing.free_crew_count
        session.data.total_admission_count = pricing.total_admission_count
        session.data.total_amount = pricing.total_amount
        session.data.deposit_amount = pricing.deposit_amount

        session.current_step = 7
        invoice_card = render_invoice_card()
        return BotResponse(
            reply_text=(
                f"{prefix}已登記遊覽車 {bus_count} 台（享有隨隊司領免票 {pricing.free_crew_count} 位）。\n"
                f"入場總人數合計為 {pricing.total_admission_count} 位。\n\n"
                f"請點選【發票開立方式】（若不需統編請點選「免開統編」）："
            ),
            flex_card=invoice_card,
            quick_replies=["免開統編", "取消預約"]
        )

    def _step_7_handle_invoice_info(self, session: UserSession, msg: str, prefix: str) -> BotResponse:
        """處理第 7 步：發票統編並進入 Step 8 確認核對卡片"""
        if is_likely_question_or_faq(msg):
            faq_reply = ask_park_faq(msg)
            return BotResponse(
                reply_text=(
                    f"{prefix}🤖 關於您的詢問，為您說明如下：\n\n{faq_reply}\n\n"
                    f"───────────────\n"
                    f"📌 【目前預約進度：第 7 步 發票與統編】\n"
                    f"若要繼續預約，請輸入統一編號與抬頭（或點下方「免開統編」）；\n"
                    f"若暫不預約，可點選下方【❌ 取消預約】。"
                ),
                quick_replies=["免開統編", "取消預約"]
            )

        if any(k in msg for k in ["統編範例", "範例"]):
            invoice_card = render_invoice_card()
            return BotResponse(
                reply_text=(
                    f"{prefix}🏢 【公司三聯式發票填寫說明】\n\n"
                    f"若貴單位需開立統一編號報帳，請直接在此輸入【8 位數統編】與【公司抬頭】\n"
                    f"範例：「統編 12345678 國立台灣大學」或「24681357 歡樂旅行社」\n\n"
                    f"若不需報帳，可直接點選下方【📄 個人二聯式發票 (免統編)】跳過："
                ),
                flex_card=invoice_card,
                quick_replies=["免開統編", "取消預約"]
            )

        if any(k in msg for k in ["無", "不用", "免", "不需要", "否", "二聯", "個人"]):
            session.data.invoice_tax_id = "無"
            session.data.invoice_title = "無"
        else:
            tax_match = re.search(r"(\d{8})", msg)
            if tax_match:
                session.data.invoice_tax_id = tax_match.group(1)
                title = msg.replace(tax_match.group(0), "").replace("統編", "").strip()
                session.data.invoice_title = title if title else "指定抬頭"
            else:
                session.data.invoice_tax_id = "無"
                session.data.invoice_title = msg

        session.current_step = 8
        return self._render_confirm_card_response(session, prefix="🎉 預約資訊已完整填寫！請核對以下【預約確認卡片】：")

    def _render_confirm_card_response(self, session: UserSession, prefix: str = "") -> BotResponse:
        """重繪並產生 Step 8 結構化預約確認 Flex 卡片與快捷按鈕"""
        pricing = calculate_pricing(
            adult_count=session.data.adult_count,
            concession_count=session.data.concession_count,
            child_count=session.data.child_count,
            tour_bus_count=session.data.tour_bus_count
        )
        session.data.free_crew_count = pricing.free_crew_count
        session.data.total_admission_count = pricing.total_admission_count
        session.data.total_amount = pricing.total_amount
        session.data.deposit_amount = pricing.deposit_amount

        session_token = uuid.uuid4().hex[:8]
        confirmation_card = render_confirmation_card(
            group_name=session.data.group_name,
            contact_name=session.data.contact_name,
            contact_phone=session.data.contact_phone,
            booking_date=str(session.data.booking_date),
            booking_time=session.data.booking_time,
            session_type=session.data.session_type,
            pricing=pricing,
            invoice_title=session.data.invoice_title,
            invoice_tax_id=session.data.invoice_tax_id,
            session_id=session_token
        )

        notice_text = f"{prefix}\n\n若資料無誤請點選【✅ 確認送出預約】；若需微調資料，可點選下方快捷鍵進行【指定修改】，無需重頭再來！"
        return BotResponse(
            reply_text=notice_text,
            flex_card=confirmation_card,
            quick_replies=CONFIRM_QUICK_REPLIES
        )

    # --- 指定單一項目修改機制 ---

    def _check_modify_request(self, session: UserSession, msg: str, prefix: str) -> Optional[BotResponse]:
        """檢查是否在確認步驟發動指定修改"""
        m = msg.strip()

        # 改團名
        if any(k in m for k in ["改團名", "改團體", "改名稱", "修改團體"]):
            session.editing_step = 1
            return BotResponse(reply_text=f"{prefix}請輸入修改後的【團體／學校／公司名稱】：")

        # 改聯絡電話
        if any(k in m for k in ["改電話", "改窗口", "改姓名", "改聯絡人", "修改聯絡"]):
            session.editing_step = 2
            return BotResponse(reply_text=f"{prefix}請輸入修改後的【聯絡人姓名】與【手機號碼】（例如：王小明 0912-345678）：")

        # 改入園日期
        if any(k in m for k in ["改日期", "改入園日", "修改日期"]):
            session.editing_step = 3
            return BotResponse(
                reply_text=f"{prefix}請選擇或輸入修改後的【入園日期】（例如：10/25 或點選下方捷徑）：",
                quick_replies=DEFAULT_DATE_QUICK_REPLIES
            )

        # 改到達時段
        if any(k in m for k in ["改時間", "改時段", "改梯次", "修改時段"]):
            session.editing_step = 4
            return BotResponse(
                reply_text=f"{prefix}請選擇或輸入修改後的【到達時段】（例如：10:30 或點選下方捷徑）：",
                quick_replies=DEFAULT_TIME_QUICK_REPLIES
            )

        # 改人數
        if any(k in m for k in ["改人數", "改票數", "修改人數"]):
            session.editing_step = 5
            return BotResponse(
                reply_text=f"{prefix}請輸入修改後的【人數明細】（例如「全票30 半票10」或直接輸入「40人」）：",
                quick_replies=["全票30 半票10", "40人", "25人"]
            )

        # 改遊覽車
        if any(k in m for k in ["改車數", "改遊覽車", "改車輛", "修改遊覽車"]):
            session.editing_step = 6
            return BotResponse(
                reply_text=f"{prefix}請選擇或輸入修改後的【遊覽車台數】（例如 1台 或 無）：",
                quick_replies=["無遊覽車", "1台", "2台"]
            )

        # 改統編抬頭
        if any(k in m for k in ["改統編", "改發票", "改抬頭", "修改發票"]):
            session.editing_step = 7
            return BotResponse(
                reply_text=f"{prefix}請輸入修改後的【統一編號與發票抬頭】（若不需要請點無）：",
                quick_replies=["無", "免開統編"]
            )

        return None

    def _handle_editing_step_input(self, session: UserSession, msg: str, prefix: str) -> BotResponse:
        """單獨更新被修改的指定欄位，更新後自動跳回 Step 8 重新展示確認卡片"""
        step = session.editing_step
        session.editing_step = None  # 清除修改標記

        if step == 1:
            clean_name = clean_group_name(msg)
            if len(clean_name) >= 2:
                session.data.group_name = clean_name
            return self._render_confirm_card_response(session, prefix="✅ 團體名稱已成功更新！")

        elif step == 2:
            name, phone = parse_contact_info(msg)
            if phone:
                session.data.contact_name = name
                session.data.contact_phone = phone
                return self._render_confirm_card_response(session, prefix="✅ 聯絡人與電話已成功更新！")
            else:
                session.editing_step = 2  # 重新等待正確電話號碼
                return BotResponse(reply_text="⚠️ 電話號碼格式未能識別，請重新輸入聯絡人姓名與聯絡電話（手機或市話/家機皆可，例如：王小明 0912-345678 或 02-23456789）：")

        elif step == 3:
            parsed_date = parse_relaxed_date(msg)
            if parsed_date:
                today = get_current_taipei_time().date()
                if parsed_date >= today:
                    session.data.booking_date = parsed_date
                    return self._render_confirm_card_response(session, prefix="✅ 入園日期已成功更新！")
            session.editing_step = 3
            return BotResponse(
                reply_text="⚠️ 日期格式無法識別或為過去日期，請重新輸入入園日期：",
                quick_replies=DEFAULT_DATE_QUICK_REPLIES
            )

        elif step == 4:
            parsed_time = parse_relaxed_time(msg)
            if parsed_time:
                morning_booked, afternoon_booked = get_booked_capacity(session.data.booking_date)
                validation = validate_booking(
                    booking_date=session.data.booking_date,
                    booking_time_str=parsed_time,
                    incoming_people=session.data.group_member_count or MIN_GROUP_SIZE,
                    request_dt=get_current_taipei_time(),
                    morning_booked=morning_booked,
                    afternoon_booked=afternoon_booked
                )
                if validation.is_valid:
                    session.data.booking_time = parsed_time
                    session.data.session_type = validation.session_type or "未定"
                    return self._render_confirm_card_response(session, prefix="✅ 到達時段已成功更新！")
                else:
                    session.editing_step = 4
                    return BotResponse(
                        reply_text=f"⚠️ {validation.message}\n請重新選擇時段：",
                        quick_replies=validation.available_slots[:8] if validation.available_slots else DEFAULT_TIME_QUICK_REPLIES
                    )
            session.editing_step = 4
            return BotResponse(reply_text="⚠️ 時段格式無法識別，請重新輸入：", quick_replies=DEFAULT_TIME_QUICK_REPLIES)

        elif step == 5:
            adult, concession, child = parse_relaxed_headcounts(msg)
            is_met, threshold_msg = check_group_threshold(adult, concession, child)
            if is_met:
                session.data.adult_count = adult
                session.data.concession_count = concession
                session.data.child_count = child
                session.data.group_member_count = adult + concession + child
                return self._render_confirm_card_response(session, prefix="✅ 人數明細已成功更新，票價已重新試算！")
            else:
                session.editing_step = 5
                return BotResponse(reply_text=f"⚠️ {threshold_msg}\n請重新輸入人數（最低20人）：")

        elif step == 6:
            bus_count = parse_relaxed_bus(msg)
            session.data.tour_bus_count = bus_count
            return self._render_confirm_card_response(session, prefix="✅ 遊覽車台數與隨隊免票已成功更新！")

        elif step == 7:
            if any(k in msg for k in ["無", "不用", "免", "不需要", "否"]):
                session.data.invoice_tax_id = "無"
                session.data.invoice_title = "無"
            else:
                tax_match = re.search(r"(\d{8})", msg)
                if tax_match:
                    session.data.invoice_tax_id = tax_match.group(1)
                    title = msg.replace(tax_match.group(0), "").strip()
                    session.data.invoice_title = title if title else "指定抬頭"
                else:
                    session.data.invoice_tax_id = "無"
                    session.data.invoice_title = msg
            return self._render_confirm_card_response(session, prefix="✅ 發票與統一編號已成功更新！")

        return self._render_confirm_card_response(session, prefix="✅ 已回到預約核對清單！")

    def _handle_confirm_booking(self, session: UserSession, prefix: str) -> BotResponse:
        """客戶點擊確認送出，完成正式預約登記 (Step 9)"""
        if session.current_step < 7:
            return BotResponse(reply_text=f"{prefix}您的預約資料尚未齊全，請依引導依序填寫。")

        # 產生正式預約流水編號 (例如 GRP-20261025-A1B2)
        date_str = session.data.booking_date.strftime("%Y%m%d") if session.data.booking_date else "20260101"
        res_id = f"GRP-{date_str}-{uuid.uuid4().hex[:4].upper()}"
        session.data.reservation_id = res_id
        session.data.user_id = session.user_id
        session.current_step = 9

        # 嘗試取得 LINE 暱稱（若有串接 LINE API）
        display_name = ""
        try:
            from app.services.line_service import get_user_profile_name
            display_name = get_user_profile_name(session.user_id)
        except Exception:
            pass

        # 同步寫入後台試算表資料庫並動態更新檔期容量儀表板與 CRM 顧客歸屬表
        try:
            append_reservation_record(session.data, line_display_name=display_name)
        except Exception as e:
            logger.error(f"寫入預約試算表記錄異常：{e}")

        msg_body = (
            f"{prefix}🎊 【預約申請已成功送出！】\n\n"
            f"▪ 預約編號：{res_id}\n"
            f"▪ 團體名稱：{session.data.group_name}\n"
            f"▪ 窗口姓名：{session.data.contact_name}（{session.data.contact_phone}）\n"
            f"▪ 入園梯次：{session.data.booking_date} {session.data.booking_time} ({session.data.session_type})\n"
            f"▪ 入園總人數：{session.data.total_admission_count} 位 (含隨隊免票 {session.data.free_crew_count} 位)\n"
            f"▪ 門票總金額：NT$ {session.data.total_amount:,} 元\n"
            f"▪ 10% 彈性訂金：NT$ {session.data.deposit_amount:,} 元\n"
            f"▪ 發票抬頭統編：{session.data.invoice_tax_id} ({session.data.invoice_title})\n\n"
            f"📌 【名額保留與入園說明】\n"
            f"1. 繳納 10% 訂金享有【保證保留】名額與專屬遊覽車位。\n"
            f"2. 入園日前 3 天可免費改期一次。\n"
            f"3. 團體保險名冊將由專責業務於近日透過加密電子郵件與您接洽交割。\n\n"
            f"感謝您的預約，期待為您帶來愉快的遊樂園體驗！🎡"
        )

        return BotResponse(reply_text=msg_body, is_session_finished=True, quick_replies=["我要預約", "園區設施有哪些？"])

    def _handle_cancel_confirmed_booking(self, user_id: str, res_id: str, prefix: str) -> BotResponse:
        """處理使用者點選查詢卡片上的「❌ 取消此筆預約」按鈕"""
        if not res_id:
            return BotResponse(reply_text=f"{prefix}⚠️ 無法取得預約單號，請點選「專人客服」為您處理。")

        success, msg = cancel_existing_reservation(reservation_id=res_id, user_id=user_id)
        if success:
            return BotResponse(
                reply_text=(
                    f"{prefix}✅ 【預約取消成功】\n\n"
                    f"預約單號：【{res_id}】已成功取消，系統已即時釋放該梯次入園名額。\n\n"
                    f"若日後有需要，隨時歡迎輸入「預約」重新辦理，或直接諮詢園區資訊！"
                ),
                quick_replies=["👉 我要預約", "📋 查詢預約", "選單"]
            )
        else:
            return BotResponse(
                reply_text=f"{prefix}⚠️ 【取消失敗】\n{msg}\n若有任何疑問，請點選「專人客服」由工作人員為您處理。",
                quick_replies=["📋 查詢預約", "📞 專人客服", "選單"]
            )

    def _handle_query_reservation(self, user_id: str, prefix: str) -> BotResponse:
        """處理預約查詢請求，依 user_id 撈取並渲染 Flex Message 詳情卡片"""
        records = get_reservations_by_user_id(user_id)
        if not records:
            return BotResponse(
                reply_text=(
                    f"{prefix}🔍 查無您近期的有效預約紀錄。\n\n"
                    f"可能原因：\n"
                    f"1. 尚未完成預約或預約已被取消\n"
                    f"2. 先前透過其他 LINE 帳號或電話窗口預約\n\n"
                    f"若您需要辦理新預約，請輸入「預約」；若需確認電話訂單，可點選「專人客服」！"
                ),
                quick_replies=["👉 我要預約", "📞 專人客服", "選單"]
            )

        if len(records) == 1:
            rec = records[0]
            card = render_reservation_detail_card(rec)
            case_status = str(rec.get("案件狀態") or rec.get("case_status") or "已成立")
            attendance_status = str(rec.get("到場狀態") or rec.get("attendance_status") or "")
            is_cancelled = attendance_status == "取消" or "取消" in case_status
            status = "已取消" if is_cancelled else case_status
            notice = "此筆預約已取消，若需入園歡迎隨時重新預約。" if is_cancelled else "若需取消預約，可直接點選卡片下方「❌ 取消此筆預約」按鈕。"
            return BotResponse(
                reply_text=f"{prefix}📋 找到您的預約紀錄如下（狀態：{status}）：\n{notice}",
                flex_card=card,
                quick_replies=["👉 我要預約", "選單", "📞 專人客服"]
            )
        else:
            bubbles = [render_reservation_detail_card(r) for r in records[:5]]
            card = {
                "type": "carousel",
                "contents": bubbles
            }
            return BotResponse(
                reply_text=f"{prefix}📋 找到您近期共 {len(records)} 筆預約紀錄（請左右滑動查看明細）：\n若需取消，可點選各卡片下方的取消按鈕。",
                flex_card=card,
                quick_replies=["👉 我要預約", "選單", "📞 專人客服"]
            )


# 全域狀態機單例
state_machine = ConversationStateMachine()
