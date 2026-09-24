"""
票價計算與隨隊免票優惠試算模組 (pricing.py)

依據企劃書定義之核心規則：
1. 全票每人 NT$ 280 元
2. 半票每人 NT$ 140 元 (7~12歲學童、65歲以上長者)
3. 免票每人 NT$ 0 元 (6歲以下幼兒)
4. 遊覽車隨隊優惠：每 1 台遊覽車享 2 位免票 (1 司機 + 1 領隊)，免票不計入門票總額
5. 成團門檻：最低 20 人 (未滿 20 人自動導向散客購票管道)
6. 訂金政策：門票總金額之 10% 彈性訂金
"""
from typing import Tuple
from pydantic import BaseModel, Field
from app.config import (
    ADULT_TICKET_PRICE,
    CONCESSION_TICKET_PRICE,
    CHILD_TICKET_PRICE,
    FREE_CREW_PER_BUS,
    MIN_GROUP_SIZE,
    DEPOSIT_RATE,
)


class PricingResult(BaseModel):
    """計費試算結果模型"""
    adult_count: int = Field(default=0, ge=0, description="全票人數")
    concession_count: int = Field(default=0, ge=0, description="半票人數")
    child_count: int = Field(default=0, ge=0, description="幼童免票人數")
    tour_bus_count: int = Field(default=0, ge=0, description="遊覽車台數")
    
    free_crew_count: int = Field(default=0, ge=0, description="隨隊司機與領隊免票總人數")
    group_member_count: int = Field(default=0, ge=0, description="團員總人數 (全+半+幼)")
    total_admission_count: int = Field(default=0, ge=0, description="入園總人數 (含隨隊司領)")
    
    adult_subtotal: int = Field(default=0, ge=0, description="全票小計金額")
    concession_subtotal: int = Field(default=0, ge=0, description="半票小計金額")
    child_subtotal: int = Field(default=0, ge=0, description="幼童小計金額 (0元)")
    total_amount: int = Field(default=0, ge=0, description="門票總金額")
    deposit_amount: int = Field(default=0, ge=0, description="10% 彈性訂金金額")
    
    is_group_threshold_met: bool = Field(default=False, description="是否達到最低成團門檻 (20人)")
    threshold_message: str = Field(default="", description="成團門檻提示訊息")


def check_group_threshold(
    adult_count: int = 0,
    concession_count: int = 0,
    child_count: int = 0
) -> Tuple[bool, str]:
    """
    檢查人數是否符合成團門檻 (最低 20 人)。
    未達 20 人時回傳 False 與友善導引說明。
    """
    total_members = adult_count + concession_count + child_count
    if total_members < MIN_GROUP_SIZE:
        shortfall = MIN_GROUP_SIZE - total_members
        message = (
            f"目前登記人數為 {total_members} 人，距離團體預約最低成團門檻（{MIN_GROUP_SIZE} 人）尚差 {shortfall} 人。\n"
            f"未滿 20 人之參訪請改由現場售票窗口或官方散客線上購票系統購票入園，感謝您的理解與配合！"
        )
        return False, message
    
    return True, f"符合團體成團門檻（目前登記 {total_members} 人，達標 {MIN_GROUP_SIZE} 人）。"


def calculate_pricing(
    adult_count: int = 0,
    concession_count: int = 0,
    child_count: int = 0,
    tour_bus_count: int = 0
) -> PricingResult:
    """
    執行完整的團體門票金額、免票名額與訂金試算。
    """
    if adult_count < 0 or concession_count < 0 or child_count < 0 or tour_bus_count < 0:
        raise ValueError("人數與遊覽車台數不能為負數")

    # 隨隊免票 (每車 1 司機 + 1 領隊)
    free_crew = tour_bus_count * FREE_CREW_PER_BUS
    
    # 團員人數與入園總人數
    group_members = adult_count + concession_count + child_count
    total_admission = group_members + free_crew
    
    # 成團檢核
    is_met, threshold_msg = check_group_threshold(adult_count, concession_count, child_count)
    
    # 金額試算
    adult_sub = adult_count * ADULT_TICKET_PRICE
    concession_sub = concession_count * CONCESSION_TICKET_PRICE
    child_sub = child_count * CHILD_TICKET_PRICE
    total = adult_sub + concession_sub + child_sub
    
    # 10% 彈性訂金 (整數四捨五入)
    deposit = int(round(total * DEPOSIT_RATE))
    
    return PricingResult(
        adult_count=adult_count,
        concession_count=concession_count,
        child_count=child_count,
        tour_bus_count=tour_bus_count,
        free_crew_count=free_crew,
        group_member_count=group_members,
        total_admission_count=total_admission,
        adult_subtotal=adult_sub,
        concession_subtotal=concession_sub,
        child_subtotal=child_sub,
        total_amount=total,
        deposit_amount=deposit,
        is_group_threshold_met=is_met,
        threshold_message=threshold_msg,
    )


def format_pricing_text(result: PricingResult) -> str:
    """
    將計費結果格式化為繁體中文對話文字摘要。
    """
    lines = [
        "📊 【預約費用試算明細】",
        f"▪ 全票（NT$ 280）：{result.adult_count} 位，小計 NT$ {result.adult_subtotal:,} 元",
        f"▪ 半票（NT$ 140）：{result.concession_count} 位，小計 NT$ {result.concession_subtotal:,} 元",
        f"▪ 幼童（免票）：{result.child_count} 位",
        f"▪ 遊覽車輛：{result.tour_bus_count} 台（隨隊贈送司領免票共 {result.free_crew_count} 位）",
        f"▪ 入園總人數：{result.total_admission_count} 位（含團員 {result.group_member_count} 位 + 司領 {result.free_crew_count} 位）",
        "-----------------------------",
        f"💰 門票總金額：NT$ {result.total_amount:,} 元",
        f"💳 10% 彈性訂金：NT$ {result.deposit_amount:,} 元",
    ]
    return "\n".join(lines)
