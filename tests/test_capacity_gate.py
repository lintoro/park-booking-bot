"""
測試園區容量控管、入園時間閘門與急單防呆 (test_capacity_gate.py)
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
import pytest

from app.core.capacity_gate import (
    validate_booking,
    get_available_time_slots,
    get_session_type,
    TAIPEI_TZ,
)


def test_session_type_classification():
    """測試上下午場次判定"""
    assert get_session_type("10:00") == "上午場"
    assert get_session_type("11:30") == "上午場"
    assert get_session_type("12:30") == "上午場"
    assert get_session_type("13:00") == "下午場"
    assert get_session_type("15:00") == "下午場"
    assert get_session_type("17:00") == "下午場"


def test_past_date_rejection():
    """測試歷史日期預約嚴格阻擋"""
    mock_now = datetime(2026, 10, 15, 11, 0, tzinfo=TAIPEI_TZ)
    past_date = date(2026, 10, 14)

    result = validate_booking(
        booking_date=past_date,
        booking_time_str="14:00",
        incoming_people=30,
        request_dt=mock_now
    )

    assert result.is_valid is False
    assert result.error_code == "PAST_DATE_ERROR"
    assert "過去的日期" in result.message


def test_after_last_group_cutoff():
    """測試 17:00 以後硬性截止防呆"""
    mock_now = datetime(2026, 10, 15, 9, 0, tzinfo=TAIPEI_TZ)
    future_date = date(2026, 10, 20)

    # 17:30
    res1 = validate_booking(
        booking_date=future_date,
        booking_time_str="17:30",
        incoming_people=25,
        request_dt=mock_now
    )
    assert res1.is_valid is False
    assert res1.error_code == "AFTER_LAST_GROUP_CUTOFF"
    assert "17:00" in res1.message

    # 18:00
    res2 = validate_booking(
        booking_date=future_date,
        booking_time_str="18:00",
        incoming_people=25,
        request_dt=mock_now
    )
    assert res2.is_valid is False
    assert res2.error_code == "AFTER_LAST_GROUP_CUTOFF"


def test_before_opening_hours():
    """測試 10:00 以前營業時間防呆"""
    mock_now = datetime(2026, 10, 15, 9, 0, tzinfo=TAIPEI_TZ)
    future_date = date(2026, 10, 20)

    res = validate_booking(
        booking_date=future_date,
        booking_time_str="09:00",
        incoming_people=20,
        request_dt=mock_now
    )
    assert res.is_valid is False
    assert res.error_code == "BEFORE_OPENING_HOURS"
    assert "10:00 開園" in res.message


def test_same_day_urgent_morning_request():
    """
    測試當日急單 - 上午提出 (< 12:00)：
    僅開放下午場 (>= 13:00)，預約上午場應被拒絕
    """
    today = date(2026, 10, 15)
    mock_now = datetime(2026, 10, 15, 9, 30, tzinfo=TAIPEI_TZ)

    # 預約上午場 11:00 -> 應被拒
    res_morning = validate_booking(
        booking_date=today,
        booking_time_str="11:00",
        incoming_people=25,
        request_dt=mock_now
    )
    assert res_morning.is_valid is False
    assert res_morning.error_code == "MORNING_URGENT_CUTOFF"
    assert "僅能預約下午場次" in res_morning.message

    # 預約下午場 13:30 -> 應通過
    res_afternoon = validate_booking(
        booking_date=today,
        booking_time_str="13:30",
        incoming_people=25,
        request_dt=mock_now
    )
    assert res_afternoon.is_valid is True
    assert res_afternoon.session_type == "下午場"


def test_same_day_urgent_afternoon_request():
    """
    測試當日急單 - 中午/下午提出 (12:00～15:00)：
    僅開放 15:00 以後梯次，預約 13:30 應被拒絕，15:30 應通過
    """
    today = date(2026, 10, 15)
    mock_now = datetime(2026, 10, 15, 12, 30, tzinfo=TAIPEI_TZ)

    # 預約下午早段 13:30 -> 應被拒 (需 >= 15:00)
    res_early = validate_booking(
        booking_date=today,
        booking_time_str="13:30",
        incoming_people=25,
        request_dt=mock_now
    )
    assert res_early.is_valid is False
    assert res_early.error_code == "AFTERNOON_URGENT_CUTOFF"
    assert "僅能預約 15:00 以後之場次" in res_early.message

    # 預約 15:30 -> 應通過
    res_ok = validate_booking(
        booking_date=today,
        booking_time_str="15:30",
        incoming_people=25,
        request_dt=mock_now
    )
    assert res_ok.is_valid is True


def test_same_day_urgent_after_1500_cutoff():
    """
    測試當日急單 - 15:00 以後提出：
    當日所有梯次皆已截止，全面禁止預約當日
    """
    today = date(2026, 10, 15)
    mock_now = datetime(2026, 10, 15, 15, 10, tzinfo=TAIPEI_TZ)

    res = validate_booking(
        booking_date=today,
        booking_time_str="16:00",
        incoming_people=20,
        request_dt=mock_now
    )
    assert res.is_valid is False
    assert res.error_code == "SAME_DAY_CUTOFF"
    assert "15:00 以後不再受理當日預約急單" in res.message


def test_capacity_limit_checks():
    """測試園區場次與每日總承載上限管制"""
    mock_now = datetime(2026, 10, 15, 9, 0, tzinfo=TAIPEI_TZ)
    future_date = date(2026, 10, 20)

    # 1. 上午場上限 400 人 (目前已 380 人，來團 30 人 => 410 超載)
    res_morning = validate_booking(
        booking_date=future_date,
        booking_time_str="10:30",
        incoming_people=30,
        request_dt=mock_now,
        morning_booked=380,
        afternoon_booked=100
    )
    assert res_morning.is_valid is False
    assert res_morning.error_code == "MORNING_CAPACITY_FULL"

    # 2. 下午場上限 600 人 (目前已 580 人，來團 30 人 => 610 超載)
    res_afternoon = validate_booking(
        booking_date=future_date,
        booking_time_str="14:00",
        incoming_people=30,
        request_dt=mock_now,
        morning_booked=200,
        afternoon_booked=580
    )
    assert res_afternoon.is_valid is False
    assert res_afternoon.error_code == "AFTERNOON_CAPACITY_FULL"

    # 3. 全日上限 1,000 人 (上午 390 + 下午 590 = 980，來團 25 人 => 1005 超載)
    res_daily = validate_booking(
        booking_date=future_date,
        booking_time_str="13:30",
        incoming_people=25,
        request_dt=mock_now,
        morning_booked=390,
        afternoon_booked=590
    )
    assert res_daily.is_valid is False
    assert res_daily.error_code == "DAILY_CAPACITY_FULL"


def test_get_available_time_slots_dynamic_filtering():
    """測試梯次動態過濾清單計算"""
    mock_now = datetime(2026, 10, 15, 9, 30, tzinfo=TAIPEI_TZ)
    today = date(2026, 10, 15)

    # 當日急單 (上午提出)：應只剩下下午場 (13:00~17:00)
    slots = get_available_time_slots(
        booking_date=today,
        request_dt=mock_now,
        morning_booked=0,
        afternoon_booked=0,
        incoming_people=20
    )
    assert "10:00" not in slots
    assert "11:30" not in slots
    assert "13:00" in slots
    assert "17:00" in slots

    # 未來日期：上午下午梯次皆在
    future_date = date(2026, 10, 22)
    future_slots = get_available_time_slots(
        booking_date=future_date,
        request_dt=mock_now,
        morning_booked=0,
        afternoon_booked=0,
        incoming_people=20
    )
    assert "10:00" in future_slots
    assert "17:00" in future_slots
    assert len(future_slots) == 15
