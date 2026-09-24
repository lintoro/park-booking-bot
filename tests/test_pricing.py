"""
測試計費模組與成團門檻防呆 (test_pricing.py)
"""
import pytest
from app.core.pricing import calculate_pricing, check_group_threshold, format_pricing_text
from app.config import (
    ADULT_TICKET_PRICE,
    CONCESSION_TICKET_PRICE,
    CHILD_TICKET_PRICE,
    FREE_CREW_PER_BUS,
    MIN_GROUP_SIZE,
)


def test_group_threshold_below_20():
    """測試未滿 20 人成團門檻阻擋"""
    is_met, msg = check_group_threshold(adult_count=15, concession_count=4, child_count=0)
    assert is_met is False
    assert "尚未達" in msg or "尚差 1 人" in msg
    assert "未滿 20 人" in msg


def test_group_threshold_exact_20():
    """測試剛好滿 20 人成團門檻通過"""
    is_met, msg = check_group_threshold(adult_count=10, concession_count=8, child_count=2)
    assert is_met is True
    assert "符合團體成團門檻" in msg


def test_calculate_pricing_normal():
    """測試正常預約計費、遊覽車免票與 10% 訂金計算"""
    # 30位全票 (30*280=8400)、10位半票 (10*140=1400)、5位幼童 (0元)
    # 2台遊覽車 (2*2 = 4位司領免票)
    result = calculate_pricing(
        adult_count=30,
        concession_count=10,
        child_count=5,
        tour_bus_count=2
    )

    assert result.adult_count == 30
    assert result.concession_count == 10
    assert result.child_count == 5
    assert result.tour_bus_count == 2
    
    # 司領免票
    assert result.free_crew_count == 4
    # 團員人數 30+10+5 = 45
    assert result.group_member_count == 45
    # 入園總人數 45+4 = 49
    assert result.total_admission_count == 49
    
    # 金額小計
    assert result.adult_subtotal == 30 * 280
    assert result.concession_subtotal == 10 * 140
    assert result.child_subtotal == 0
    assert result.total_amount == 8400 + 1400  # 9800
    
    # 10% 訂金
    assert result.deposit_amount == 980
    assert result.is_group_threshold_met is True


def test_calculate_pricing_deposit_rounding():
    """測試訂金整數四捨五入計算"""
    # 1位全票 280、0位半票 => 總額 280 => 10% 為 28
    result1 = calculate_pricing(adult_count=1, concession_count=0, child_count=0, tour_bus_count=0)
    assert result1.total_amount == 280
    assert result1.deposit_amount == 28

    # 半票 1位 140 => 總額 140 => 10% 為 14
    result2 = calculate_pricing(adult_count=0, concession_count=1, child_count=0, tour_bus_count=0)
    assert result2.total_amount == 140
    assert result2.deposit_amount == 14


def test_calculate_pricing_negative_input():
    """測試負數人數異常防呆"""
    with pytest.raises(ValueError):
        calculate_pricing(adult_count=-5, concession_count=10, child_count=0, tour_bus_count=0)

    with pytest.raises(ValueError):
        calculate_pricing(adult_count=20, concession_count=0, child_count=0, tour_bus_count=-1)


def test_format_pricing_text():
    """測試文字摘要產出完整性"""
    result = calculate_pricing(adult_count=20, concession_count=5, child_count=2, tour_bus_count=1)
    text = format_pricing_text(result)
    assert "預約費用試算明細" in text
    assert "全票（NT$ 280）：20 位" in text
    assert "隨隊贈送司領免票共 2 位" in text
    assert "10% 彈性訂金" in text
