"""
測試 AI 回應規範：繁體中文（台灣）、台灣日常用語、委婉拒絕無關提問與制式 Flex 回應引導 (test_ai_taiwanese_refusal_and_flex_guidance.py)
"""
import pytest
from app.services.faq_service import (
    ask_park_faq,
    _sanitize_output,
    is_off_topic_query,
)
from app.core.state_machine import ConversationStateMachine
from app.templates.template_renderer import render_guided_menu_card


def test_sanitize_output_blocks_english_refusal():
    """驗證後置消毒器能夠徹底攔截模型輸出的英文拒絕語句並自動轉為台灣繁中日常用語"""
    # 模擬使用者截圖中的 Gemini 英文輸出
    raw_ai_english = "is outside park info. Yes, as an AI I don't have real-time live weather feeds for today."
    cleaned = _sanitize_output(raw_ai_english)

    # 確保無任何英文句子殘留
    assert "outside park info" not in cleaned
    assert "real-time live weather" not in cleaned
    assert "as an AI" not in cleaned

    # 確保為親切道地的台灣繁中說明與雨天備案
    assert "不好意思" in cleaned
    assert "雨天備案" in cleaned or "服務範圍" in cleaned


def test_sanitize_output_fixes_dangling_tail():
    """驗證截圖中斷句（如『...義大利麵與』、『...為您解答園』）被自動修復為完整語句且無懸空詞"""
    raw_dangling_1 = "全天候提供全素（Vegan）及蛋奶素套餐、義大利麵與"
    fixed_1 = _sanitize_output(raw_dangling_1)
    assert not fixed_1.endswith("與")
    assert fixed_1.endswith("。") or fixed_1.endswith("🍽️") or fixed_1.endswith("🎡")

    raw_dangling_2 = "抱歉，身為星夢歡樂世界的客服小助手，我只專注於為您解答園"
    fixed_2 = _sanitize_output(raw_dangling_2)
    assert not fixed_2.endswith("解答園")
    assert fixed_2.endswith("。") or fixed_2.endswith("🎡")


def test_weather_inquiry_taiwanese_daily_phrasing():
    """驗證使用者截圖問題「今天天氣你那邊有下雨嘛」能夠以台灣日常用語親切回覆雨天備案"""
    question = "今天天氣你那邊有下雨嘛"
    reply = ask_park_faq(question)

    assert "不好意思" in reply
    assert "雨天備案" in reply
    assert "室內" in reply
    # 絕無英文殘留
    assert "outside park" not in reply
    assert "live weather" not in reply


def test_step_1_weather_inquiry_guided_flex_card():
    """驗證在 Step 1 填單過程中問天氣（使用者截圖真實情境）：委婉回覆且彈出制式 Flex 卡片並限制 Quick Replies"""
    sm = ConversationStateMachine()
    user_id = "test_user_weather_step1"

    # Step 0 -> Step 1
    sm.process_message(user_id, "預約")
    session = sm.get_or_create_session(user_id)
    assert session.current_step == 1

    # 在 Step 1 問天氣
    res = sm.process_message(user_id, "今天天氣你那邊有下雨嘛")

    # 1. 回覆為繁體中文台灣日常口語
    assert "不好意思" in res.reply_text
    assert "雨天備案" in res.reply_text
    assert "【目前仍在預約流程中】" in res.reply_text

    # 2. 彈出制式 Flex 導引卡片
    assert res.flex_card is not None
    assert res.flex_card["type"] == "bubble"

    # 3. Quick Replies 限制住回應
    assert "取消預約" in res.quick_replies
    assert "📞 專人客服" in res.quick_replies

    # 4. 狀態機未被污染或跳步
    assert session.current_step == 1
    assert not session.data.group_name


def test_step_0_off_topic_guided_flex_and_quick_replies():
    """驗證在 Step 0 詢問無關問題時，委婉拒絕並引導出制式 Flex 卡片，限制住後續回應"""
    sm = ConversationStateMachine()
    user_id = "test_user_off_topic_step0"

    off_topic_q = "請問可以幫我寫一個 Python 爬蟲腳本嗎？"
    res = sm.process_message(user_id, off_topic_q)

    # 1. 委婉拒絕
    assert "客服" in res.reply_text
    assert ("服務範圍" in res.reply_text or "系統安全保護提醒" in res.reply_text or "星夢小助手" in res.reply_text)

    # 2. 引導出制式 Flex 卡片
    assert res.flex_card is not None
    assert res.flex_card["type"] == "bubble"

    # 3. 嚴格限制 Quick Replies 為四大核心功能按鈕
    expected_replies = ["👉 我要預約", "📋 預約查詢", "💰 票價試算", "📞 專人客服"]
    for q in expected_replies:
        assert q in res.quick_replies


def test_render_guided_menu_card_structure():
    """驗證制式 Flex 導引卡片的結構與 4 大按鈕定義"""
    card = render_guided_menu_card()
    assert card["type"] == "bubble"
    assert card["size"] == "mega"

    # 尋找按鈕
    buttons = []
    for item in card["body"]["contents"]:
        if item.get("type") == "box":
            for btn in item.get("contents", []):
                if btn.get("type") == "button":
                    buttons.append(btn["action"]["text"])

    assert "👉 我要預約" in buttons
    assert "📋 預約查詢" in buttons
    assert "💰 票價試算" in buttons
    assert "📞 專人客服" in buttons
