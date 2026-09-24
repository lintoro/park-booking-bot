"""
資料模型定義模組 (models.py)
"""
from datetime import datetime, date
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

from app.core.capacity_gate import get_current_taipei_time


class BookingData(BaseModel):
    """預約資料暫存模型"""
    group_name: str = ""
    contact_name: str = ""
    contact_phone: str = ""
    booking_date: Optional[date] = None
    booking_time: str = ""
    session_type: str = ""
    adult_count: int = 0
    concession_count: int = 0
    child_count: int = 0
    tour_bus_count: int = 0
    free_crew_count: int = 0
    group_member_count: int = 0
    total_admission_count: int = 0
    invoice_title: str = "無"
    invoice_tax_id: str = "無"
    total_amount: int = 0
    deposit_amount: int = 0
    reservation_id: str = ""
    user_id: str = ""
    sales_rep: str = "業務專員"
    deposit_status: str = "待收訂金"
    show_status: str = "待履約"
    actual_admission_count: int = 0
    headcount_diff_note: str = ""
    final_payment_amount: int = 0
    invoice_status: str = "未開立"
    case_status: str = "進行中"
    sales_note: str = ""
    allow_duplicate: bool = False  # 是否已通過重複預約確認旗標



class UserSession(BaseModel):
    """使用者對話階段模型"""
    user_id: str
    current_step: int = 0
    last_active_at: datetime = Field(default_factory=get_current_taipei_time)
    is_human_handoff: bool = False
    editing_step: Optional[int] = None  # 記錄當前正在單獨修改的步驟編號 (若為 None 代表循序問答)
    data: BookingData = Field(default_factory=BookingData)


class BotResponse(BaseModel):
    """機器人回應封裝模型"""
    reply_text: Optional[str] = None
    flex_card: Optional[Dict[str, Any]] = None
    quick_replies: Optional[List[str]] = None
    is_session_finished: bool = False
