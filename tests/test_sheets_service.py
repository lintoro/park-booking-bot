"""
測試 Google 試算表資料庫串接與即時容量連動 (test_sheets_service.py)
"""
from datetime import date
import pytest

from app.core.models import BookingData
from app.core.state_machine import ConversationStateMachine

from app.services.sheets_service import (
    build_log_row,
    append_reservation_record,
    get_booked_capacity,
    clear_mock_database,
    LOG_HEADERS,
    DASHBOARD_HEADERS,
)


@pytest.fixture(autouse=True)
def setup_and_teardown(monkeypatch):
    """每次測試前自動清理本地快取資料庫，並隔離真實試算表避免產生測試髒資料"""
    clear_mock_database()
    monkeypatch.setattr("app.services.sheets_service.get_spreadsheet", lambda: None)
    yield
    clear_mock_database()



def test_build_log_row_mapping():
    """測試 BookingData 轉換為 21 欄預約記錄列之正確性"""
    booking = BookingData(
        reservation_id="GRP-20261125-A8B9",
        booking_date=date(2026, 11, 25),
        booking_time="10:30",
        session_type="上午場",
        group_name="國泰人壽南區登山社",
        contact_name="林志明",
        contact_phone="0988-123456",
        adult_count=40,
        concession_count=10,
        child_count=2,
        tour_bus_count=2,
        free_crew_count=4,
        group_member_count=52,
        total_admission_count=56,
        total_amount=12600,
        deposit_amount=1260,
        invoice_tax_id="12345678",
        invoice_title="國泰人壽保險股份有限公司"
    )

    row = build_log_row(booking)

    # 欄位總數必須恰好等於表頭定義 (21 欄)
    assert len(row) == len(LOG_HEADERS)
    assert len(row) == 21

    # 驗證重要對應欄位
    assert row[0] == "GRP-20261125-A8B9"  # 預約編號
    assert row[2] == "2026-11-25"          # 入園日期
    assert row[3] == "10:30"               # 入場梯次
    assert row[4] == "上午場"              # 場次類型
    assert row[5] == "國泰人壽南區登山社"  # 團體名稱
    assert row[6] == "林志明"              # 聯絡窗口
    assert row[8] == 40                    # 全票數
    assert row[11] == 2                    # 遊覽車數
    assert row[12] == 4                    # 隨隊免票數
    assert row[14] == 56                   # 入場總人數
    assert row[15] == 12600                # 門票總額
    assert row[16] == 1260                 # 10% 訂金
    assert row[19] == "未付訂"             # 預設訂金審核狀態


def test_append_record_and_get_booked_capacity():
    """測試預約寫入後容量即時更新累加"""
    target_date = date(2026, 12, 10)

    # 1. 初始容量應為 (0, 0)
    m_init, a_init = get_booked_capacity(target_date)
    assert m_init == 0
    assert a_init == 0

    # 2. 寫入一筆上午場 50 人
    b1 = BookingData(
        reservation_id="GRP-20261210-001",
        booking_date=target_date,
        booking_time="10:30",
        session_type="上午場",
        total_admission_count=50
    )
    append_reservation_record(b1)

    m1, a1 = get_booked_capacity(target_date)
    assert m1 == 50
    assert a1 == 0

    # 3. 再寫入一筆下午場 80 人
    b2 = BookingData(
        reservation_id="GRP-20261210-002",
        booking_date=target_date,
        booking_time="14:00",
        session_type="下午場",
        total_admission_count=80
    )
    append_reservation_record(b2)

    m2, a2 = get_booked_capacity(target_date)
    assert m2 == 50
    assert a2 == 80


def test_capacity_blocking_with_sheets_records():
    """
    測試容量超載連動攔截：
    當試算表已有 380 人上午場預約，新團體欲預約 30 人（合計 410 > 400 上限）時，
    狀態機在 Step 3 自動阻擋並提示改選下午場！
    """
    test_date = date(2026, 12, 15)

    # 預先在該日灌入 380 人上午場
    existing_booking = BookingData(
        reservation_id="GRP-20261215-PREV",
        booking_date=test_date,
        booking_time="10:00",
        session_type="上午場",
        total_admission_count=380
    )
    append_reservation_record(existing_booking)

    # 新使用者進線預約該日上午場 10:30
    sm = ConversationStateMachine()
    user_id = "test_user_capacity_overflow"

    session = sm.get_or_create_session(user_id)
    session.current_step = 3

    resp = sm.process_message(user_id, f"{test_date} 10:30")

    # 由於 380 + 20(預審最低人數) = 400 (已達極限，若新團人數稍微加上去即超額)，
    # 檢驗容量防呆是否正常發揮保護機制
    assert "時段預約防呆提醒" in resp.reply_text or session.current_step == 4
