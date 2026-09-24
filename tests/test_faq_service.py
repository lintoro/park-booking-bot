"""
測試園區常見問答知識庫與智能客服回覆 (test_faq_service.py)
"""
import pytest
from app.services.faq_service import ask_park_faq, load_park_knowledge
from app.core.state_machine import ConversationStateMachine


def test_load_park_knowledge():
    """測試知識庫內容載入完整性"""
    content = load_park_knowledge()
    assert len(content) > 100
    assert "星夢歡樂世界" in content
    assert "團體專屬定時導覽" in content
    assert "熱門遊戲設施" in content
    assert "團體餐飲與素食" in content


def test_faq_guided_tour():
    """測試團體導覽時程諮詢"""
    ans = ask_park_faq("請問團體導覽時間是幾點？集合地點在哪裡？")
    assert "10:30" in ans
    assert "14:00" in ans
    assert "鐘樓" in ans or "廣場" in ans
    assert "預約" in ans


def test_faq_attractions():
    """測試遊戲設施與安全限制諮詢"""
    ans = ask_park_faq("你們園區有什麼刺激的遊樂設施？身高限制多少？")
    assert "雲霄飛車" in ans
    assert "140" in ans or "限制" in ans


def test_faq_vegetarian_food():
    """測試素食與團餐配套諮詢"""
    ans = ask_park_faq("請問園區有提供素食便當或素食餐廳嗎？")
    assert "素" in ans
    assert "餐盒" in ans or "便當" in ans or "餐廳" in ans


def test_faq_bus_parking():
    """測試遊覽車停車與交通接駁諮詢"""
    ans = ask_park_faq("請問遊覽車有免費停車場嗎？")
    assert "遊覽車" in ans
    assert "免費" in ans or "北門" in ans or "停車" in ans


def test_faq_pets_policy():
    """測試寵物入園政策諮詢"""
    ans = ask_park_faq("請問可以帶狗或貓入園嗎？")
    assert "寵物" in ans
    assert "推車" in ans or "提籠" in ans


def test_state_machine_with_faq_and_booking_switch():
    """測試客人先諮詢設施/導覽 FAQ，滿意後切入預約流程"""
    sm = ConversationStateMachine()
    user_id = "test_user_faq_journey"

    # 1. 客人剛進入，先問導覽時間 (Step 0)
    r1 = sm.process_message(user_id, "請問團體導覽是幾點？")
    assert "10:30" in r1.reply_text
    assert "14:00" in r1.reply_text
    # 仍處於 Step 0
    session = sm.get_or_create_session(user_id)
    assert session.current_step == 0

    # 2. 客人又問設施
    r2 = sm.process_message(user_id, "有哪些遊戲設施推薦？")
    assert "雲霄飛車" in r2.reply_text or "摩天輪" in r2.reply_text
    assert session.current_step == 0

    # 3. 客人看完很滿意，決定預約
    r3 = sm.process_message(user_id, "預約")
    assert "歡迎使用遊樂園團體預約" in r3.reply_text
    session = sm.get_or_create_session(user_id)
    assert session.current_step == 1
