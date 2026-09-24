"""
測試優化後對話狀態機、獨立日期時段、指定單獨修改、15 分鐘逾時與真人接手機制 (test_state_machine.py)
"""
from datetime import datetime, timedelta, date
from unittest.mock import patch
from app.core.state_machine import ConversationStateMachine, state_machine
from app.core.capacity_gate import TAIPEI_TZ


@patch("app.core.state_machine.get_booked_capacity", return_value=(0, 0))
def test_full_booking_flow_step_0_to_9(mock_capacity):
    """測試從 Step 0 啟動至 Step 9 正式送出預約的完整流程（包含獨立日期與時間）"""
    sm = ConversationStateMachine()
    user_id = "test_user_flow_01"

    # Step 0 -> Step 1: 啟動
    r0 = sm.process_message(user_id, "預約")
    assert "歡迎使用遊樂園團體預約" in r0.reply_text
    session = sm.get_or_create_session(user_id)
    assert session.current_step == 1

    # Step 1 -> Step 2: 團體名稱 (寬容提取)
    r1 = sm.process_message(user_id, "團體名稱是 台大校友會健行團")
    assert "已收到團體名稱：【台大校友會健行團】" in r1.reply_text
    assert session.current_step == 2
    assert session.data.group_name == "台大校友會健行團"

    # Step 2 -> Step 3: 窗口姓名與手機
    r2 = sm.process_message(user_id, "王小明 0912-345678")
    assert "聯絡窗口已登錄：【王小明（0912345678）】" in r2.reply_text
    assert session.current_step == 3
    assert session.data.contact_name == "王小明"
    assert session.data.contact_phone == "0912345678"

    # Step 3 -> Step 4: 獨立入園日期
    r3 = sm.process_message(user_id, "2026-11-20")
    assert "已確認入園日期：【2026-11-20】" in r3.reply_text
    assert session.current_step == 4
    assert session.data.booking_date == date(2026, 11, 20)

    # Step 4 -> Step 5: 獨立到達時段 (寬容下午時段)
    r4 = sm.process_message(user_id, "10:30")
    assert "已保留梯次" in r4.reply_text
    assert session.current_step == 5
    assert session.data.booking_time == "10:30"
    assert session.data.session_type == "上午場"

    # Step 5 -> Step 6: 人數明細 (全票30 半票10 幼童2，合計 42 人，達標 20 人)
    r5 = sm.process_message(user_id, "全票30 半票10 幼童2")
    assert "已登記人數" in r5.reply_text
    assert session.current_step == 6
    assert session.data.adult_count == 30
    assert session.data.concession_count == 10
    assert session.data.child_count == 2
    assert session.data.group_member_count == 42

    # Step 6 -> Step 7: 遊覽車台數 (2 台，享有 4 位司領免票)
    r6 = sm.process_message(user_id, "2台")
    assert "已登記遊覽車 2 台" in r6.reply_text
    assert "享有隨隊司領免票 4 位" in r6.reply_text
    assert session.current_step == 7
    assert session.data.tour_bus_count == 2
    assert session.data.free_crew_count == 4
    assert session.data.total_admission_count == 46
    assert session.data.total_amount == (30 * 280) + (10 * 140)  # 9800
    assert session.data.deposit_amount == 980

    # Step 7 -> Step 8: 發票統一編號
    r7 = sm.process_message(user_id, "統編 12345678 國立台灣大學")
    assert "預約確認卡片" in r7.reply_text
    assert r7.flex_card is not None
    assert session.current_step == 8
    assert session.data.invoice_tax_id == "12345678"
    assert "國立台灣大學" in session.data.invoice_title

    # 【指定單獨修改測試】：客人要求「改人數」，不要重頭來過
    r_mod = sm.process_message(user_id, "改人數")
    assert "請輸入修改後的人數明細" in r_mod.reply_text or "人數明細" in r_mod.reply_text
    assert session.editing_step == 5

    # 客人輸入修改後的「50人」
    r_mod_done = sm.process_message(user_id, "50人")
    assert session.data.adult_count == 50
    assert session.current_step == 8  # 秒回 Step 8 確認卡片
    assert session.editing_step is None  # 編輯標記清除
    assert session.data.total_amount == 50 * 280  # 14000
    assert r_mod_done.flex_card is not None  # 重新生成更新後的 Flex 卡片

    # Step 8 -> Step 9: 送出預約
    r8 = sm.process_message(user_id, "確認送出")
    assert "預約申請已成功送出" in r8.reply_text
    assert session.current_step == 9
    assert session.data.reservation_id.startswith("GRP-")
    assert r8.is_session_finished is True


def test_step_5_under_20_headcount_rejection():
    """測試成團人數未滿 20 人被防呆攔截"""
    sm = ConversationStateMachine()
    user_id = "test_user_under_20"
    session = sm.get_or_create_session(user_id)
    session.current_step = 5
    session.data.booking_date = date(2026, 11, 20)
    session.data.booking_time = "10:30"

    r = sm.process_message(user_id, "全票10 半票5 幼童1")
    assert "未達團體成團標準" in r.reply_text
    assert session.current_step == 5  # 停留在 Step 5 重新輸入


def test_step_4_slot_guard_rejection():
    """測試到達時段 17:00 以後嚴格禁止預約"""
    sm = ConversationStateMachine()
    user_id = "test_user_late_slot"
    session = sm.get_or_create_session(user_id)
    session.current_step = 4
    session.data.booking_date = date(2026, 11, 20)

    r = sm.process_message(user_id, "17:30")
    assert "防呆提醒" in r.reply_text
    assert "17:00" in r.reply_text
    assert session.current_step == 4  # 停留在時段題


def test_session_15_minutes_timeout_reset():
    """測試超過 15 分鐘未回應自動重置"""
    sm = ConversationStateMachine()
    user_id = "test_user_timeout"
    session = sm.get_or_create_session(user_id)
    session.current_step = 4
    session.last_active_at = datetime.now(TAIPEI_TZ) - timedelta(minutes=16)

    r = sm.process_message(user_id, "下午2點")
    assert "超過 15 分鐘未回應" in r.reply_text


def test_human_handoff_and_resume():
    """測試真人客服切換與恢復機器人"""
    sm = ConversationStateMachine()
    user_id = "test_user_human"
    session = sm.get_or_create_session(user_id)

    r_handoff = sm.process_message(user_id, "我想找客服專人詢問")
    assert "已為您暫停自動化機器人" in r_handoff.reply_text
    assert r_handoff.flex_card is not None
    assert session.is_human_handoff is True

    # 真人模式下，一般字句不回覆
    r_silent = sm.process_message(user_id, "哈囉有人在嗎？")
    assert r_silent.reply_text is None

    # 輸入恢復
    r_resume = sm.process_message(user_id, "恢復機器人")
    assert "已為您恢復智慧預約機器人" in r_resume.reply_text
    assert session.is_human_handoff is False


def test_cancel_and_interrupt_flow():
    """測試在預約各步驟中隨時輸入『取消』能順利中斷並清空狀態"""
    sm = ConversationStateMachine()
    user_id = "test_user_cancel"

    # 啟動預約進入 Step 1
    sm.process_message(user_id, "想預約")
    session = sm.get_or_create_session(user_id)
    assert session.current_step == 1

    # 輸入取消
    r_cancel = sm.process_message(user_id, "取消預約")
    assert "已為您取消本次預約" in r_cancel.reply_text
    session = sm.get_or_create_session(user_id)
    assert session.current_step == 0
    assert session.data.group_name == ""


def test_step_1_question_interception_not_taken_as_group_name():
    """測試在 Step 1 詢問設施/問題時，不被當作團體名稱，而是智慧回答並保留在流程中"""
    sm = ConversationStateMachine()
    user_id = "test_user_step1_faq"

    # 啟動預約進入 Step 1
    sm.process_message(user_id, "我要預約")
    session = sm.get_or_create_session(user_id)
    assert session.current_step == 1

    # 客人突然問摩天輪設施
    r_faq = sm.process_message(user_id, "請問摩天輪幾點開放？")
    assert "摩天輪" in r_faq.reply_text
    assert "目前仍在預約流程中" in r_faq.reply_text
    # 驗證狀態仍然在 Step 1，且團體名稱沒有被污染
    session = sm.get_or_create_session(user_id)
    assert session.current_step == 1
    assert session.data.group_name == ""

    # 客人打招呼
    r_hello = sm.process_message(user_id, "你好")
    assert "目前仍在預約流程中" in r_hello.reply_text
    assert session.current_step == 1
    assert session.data.group_name == ""

    # 客人輸入真實團體名稱，順利前進 Step 2
    r_name = sm.process_message(user_id, "快樂旅行社")
    assert "已收到團體名稱：【快樂旅行社】" in r_name.reply_text
    assert session.current_step == 2
    assert session.data.group_name == "快樂旅行社"


def test_user_actual_screenshot_case_bento_and_cancel():
    """精確測試使用者實測截圖問題：問『你們有便當嘛』智慧解答，輸入『我不想預約了』乾淨取消"""
    sm = ConversationStateMachine()
    user_id = "test_user_screenshot"

    # 1. 進入預約並到達 Step 2 (請提供主要聯絡人姓名與手機號碼)
    sm.process_message(user_id, "想預約")
    sm.process_message(user_id, "快樂旅遊團")
    session = sm.get_or_create_session(user_id)
    assert session.current_step == 2

    # 2. 客人在 Step 2 輸入「你們有便當嘛」
    r_bento = sm.process_message(user_id, "你們有便當嘛")
    assert "便當" in r_bento.reply_text or "餐盒" in r_bento.reply_text
    assert "未能成功識別台灣手機號碼格式" not in r_bento.reply_text
    assert session.current_step == 2  # 依然保持在 Step 2，未被污染

    # 3. 客人輸入「我不想預約了」
    r_cancel = sm.process_message(user_id, "我不想預約了")
    assert "已為您取消本次預約流程" in r_cancel.reply_text
    assert "歡迎使用遊樂園團體預約" not in r_cancel.reply_text
    session = sm.get_or_create_session(user_id)
    assert session.current_step == 0


def test_step_8_modify_menu_does_not_reset_all_data():
    """測試在 Step 8 點選修改按鈕時，展現微調選單，不直接清空重填"""
    sm = ConversationStateMachine()
    user_id = "test_user_modify_menu"
    session = sm.get_or_create_session(user_id)
    session.current_step = 8
    session.data.group_name = "科技創新公司"
    session.data.contact_name = "張經理"
    session.data.contact_phone = "0988123456"
    session.data.booking_date = datetime.now(TAIPEI_TZ).date() + timedelta(days=5)
    session.data.booking_time = "10:30"
    session.data.adult_count = 30

    # 1. 客人點擊卡片上的修改按鈕 (送出 action=show_modify_menu 或 我想修改預約資料)
    r_menu = sm.process_message(user_id, "我想修改預約資料", postback_data="action=show_modify_menu")
    assert "請選擇要修改的預約項目" in r_menu.reply_text
    assert session.current_step == 8
    assert session.data.group_name == "科技創新公司"  # 資料妥善保留

    # 2. 客人點選「改人數」
    r_mod_count = sm.process_message(user_id, "改人數")
    assert "人數明細" in r_mod_count.reply_text
    assert session.editing_step == 5

    # 3. 輸入修改後的「50人」
    r_done = sm.process_message(user_id, "50人")
    assert session.data.adult_count == 50
    assert session.current_step == 8
    assert "預約確認卡片" in r_done.reply_text or r_done.flex_card is not None
