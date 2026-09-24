"""
園區容量控管、入園時間閘門與急單防呆模組 (capacity_gate.py)

依據企劃書定義之核心規則：
1. 每日總承載上限 1,000 人：
   - 上午場次 (10:00～13:00 入場)：上限 400 人
   - 下午場次 (13:00～17:00 入場)：上限 600 人
2. 營業時間與梯次：
   - 平日 10:00～18:00、假日 10:00～19:00
   - 每 30 分鐘為一梯次 (10:00, 10:30, 11:00 ... 16:30, 17:00)
   - 17:00 以後嚴格禁止團體預約入場
3. 當日急單時效管制 (強制以 Asia/Taipei 台北時區判定)：
   - 當日上午 (12:00 前) 提出：僅開放預約「下午場 (13:00 以後)」
   - 當日下午 (12:00～15:00) 提出：僅開放預約「15:00 以後」之梯次 (15:00～17:00)
   - 當日下午 15:00 以後提出：當日梯次全面截止預約
4. 歷史日期嚴格阻擋
"""
from datetime import datetime, date, time
from typing import List, Tuple, Optional
from zoneinfo import ZoneInfo
from pydantic import BaseModel, Field

from app.config import (
    DAILY_CAPACITY_LIMIT,
    MORNING_CAPACITY_LIMIT,
    AFTERNOON_CAPACITY_LIMIT,
    TIMEZONE,
    SLOT_LAST_GROUP_TIME,
)

try:
    from zoneinfo import ZoneInfo
    TAIPEI_TZ = ZoneInfo(TIMEZONE)
except Exception:
    from datetime import timezone, timedelta
    TAIPEI_TZ = timezone(timedelta(hours=8), name="Asia/Taipei")


# 標準預約梯次清單 (每 30 分鐘一梯次)
ALL_TIME_SLOTS: List[str] = [
    "10:00", "10:30", "11:00", "11:30", "12:00", "12:30",
    "13:00", "13:30", "14:00", "14:30", "15:00", "15:30", "16:00", "16:30", "17:00"
]

MORNING_SLOTS: List[str] = ["10:00", "10:30", "11:00", "11:30", "12:00", "12:30"]
AFTERNOON_SLOTS: List[str] = ["13:00", "13:30", "14:00", "14:30", "15:00", "15:30", "16:00", "16:30", "17:00"]


class CapacityValidationResult(BaseModel):
    """預約時段與容量驗證結果"""
    is_valid: bool = Field(description="是否通過所有防呆檢核")
    error_code: Optional[str] = Field(default=None, description="錯誤代碼")
    message: str = Field(description="驗證說明或錯誤原因 (繁體中文)")
    session_type: Optional[str] = Field(default=None, description="場次類別 (上午場/下午場)")
    available_slots: List[str] = Field(default_factory=list, description="該日期目前仍可選用之梯次清單")


def get_current_taipei_time() -> datetime:
    """取得當前台北時區時間"""
    return datetime.now(TAIPEI_TZ)


def get_session_type(slot_time_str: str) -> str:
    """
    依入場時間判斷屬於上午場還是下午場
    10:00 ~ 12:30 -> 上午場
    13:00 ~ 17:00 -> 下午場
    """
    if slot_time_str in MORNING_SLOTS:
        return "上午場"
    elif slot_time_str in AFTERNOON_SLOTS:
        return "下午場"
    else:
        # 若時間不在預設清單，以 13:00 分界
        slot_t = datetime.strptime(slot_time_str, "%H:%M").time()
        if slot_t < time(13, 0):
            return "上午場"
        return "下午場"


def get_available_time_slots(
    booking_date: date,
    request_dt: Optional[datetime] = None,
    morning_booked: int = 0,
    afternoon_booked: int = 0,
    incoming_people: int = 0
) -> List[str]:
    """
    計算指定日期目前可開放預約的梯次清單。
    會考量：
    1. 當日急單防呆 (上午提單限下午場、下午提單限15:00後、15:00後全面截止)
    2. 上午場與下午場容量上限 (400人 / 600人)
    3. 全日總量上限 (1,000人)
    4. 17:00 硬性截止
    """
    if request_dt is None:
        request_dt = get_current_taipei_time()
    elif request_dt.tzinfo is None:
        request_dt = request_dt.replace(tzinfo=TAIPEI_TZ)

    today = request_dt.date()

    # 1. 歷史日期：無可用梯次
    if booking_date < today:
        return []

    # 2. 每日總量滿額檢核 (1000 人)
    total_booked = morning_booked + afternoon_booked
    if (total_booked + incoming_people) > DAILY_CAPACITY_LIMIT:
        return []

    # 3. 初始可用時段
    candidates = list(ALL_TIME_SLOTS)

    # 4. 當日急單時效管制
    if booking_date == today:
        current_time = request_dt.time()
        if current_time >= time(15, 0):
            # 15:00 以後提出，當日所有梯次皆已截止
            return []
        elif current_time >= time(12, 0):
            # 12:00～15:00 提出，僅能預約 15:00 及以後梯次
            candidates = [s for s in candidates if datetime.strptime(s, "%H:%M").time() >= time(15, 0)]
        else:
            # 12:00 前提出，僅能預約下午場 (13:00 以後)
            candidates = [s for s in candidates if datetime.strptime(s, "%H:%M").time() >= time(13, 0)]

    # 5. 上午場容量管制 (400 人)
    if (morning_booked + incoming_people) > MORNING_CAPACITY_LIMIT:
        candidates = [s for s in candidates if s not in MORNING_SLOTS]

    # 6. 下午場容量管制 (600 人)
    if (afternoon_booked + incoming_people) > AFTERNOON_CAPACITY_LIMIT:
        candidates = [s for s in candidates if s not in AFTERNOON_SLOTS]

    return candidates


def validate_booking(
    booking_date: date,
    booking_time_str: str,
    incoming_people: int,
    request_dt: Optional[datetime] = None,
    morning_booked: int = 0,
    afternoon_booked: int = 0
) -> CapacityValidationResult:
    """
    針對特定預約請求執行全方位防呆驗證。
    """
    if request_dt is None:
        request_dt = get_current_taipei_time()
    elif request_dt.tzinfo is None:
        request_dt = request_dt.replace(tzinfo=TAIPEI_TZ)

    today = request_dt.date()

    # 取得當日所有可用梯次以備後續回傳建議
    available_slots = get_available_time_slots(
        booking_date=booking_date,
        request_dt=request_dt,
        morning_booked=morning_booked,
        afternoon_booked=afternoon_booked,
        incoming_people=incoming_people
    )

    # 規則 1：過去日期不可預約
    if booking_date < today:
        return CapacityValidationResult(
            is_valid=False,
            error_code="PAST_DATE_ERROR",
            message="預約日期不能為過去的日期，請重新選擇未來的入園日期。",
            available_slots=[]
        )

    # 規則 2：時間格式解析與營業時間/17:00 截止檢核
    try:
        slot_time = datetime.strptime(booking_time_str, "%H:%M").time()
    except ValueError:
        return CapacityValidationResult(
            is_valid=False,
            error_code="INVALID_TIME_FORMAT",
            message=f"預約時間格式錯誤（需為 HH:MM 如 10:00），您輸入的是：{booking_time_str}",
            available_slots=available_slots
        )

    last_slot_time = datetime.strptime(SLOT_LAST_GROUP_TIME, "%H:%M").time()
    earliest_slot_time = time(10, 0)

    if slot_time < earliest_slot_time:
        return CapacityValidationResult(
            is_valid=False,
            error_code="BEFORE_OPENING_HOURS",
            message=f"園區早上 10:00 開園，最早可預約梯次為 10:00，您選擇的 {booking_time_str} 尚未開園。",
            available_slots=available_slots
        )

    if slot_time > last_slot_time:
        return CapacityValidationResult(
            is_valid=False,
            error_code="AFTER_LAST_GROUP_CUTOFF",
            message=(
                f"園區規定團體預約最晚入場梯次為 {SLOT_LAST_GROUP_TIME}，"
                f"{SLOT_LAST_GROUP_TIME} 以後一律不開放團體預約入場（您選擇的是 {booking_time_str}）。"
            ),
            available_slots=available_slots
        )

    session_type = get_session_type(booking_time_str)

    # 規則 3：當日急單時效防呆
    if booking_date == today:
        current_time = request_dt.time()
        
        # 15:00 以後當日全面截止
        if current_time >= time(15, 0):
            return CapacityValidationResult(
                is_valid=False,
                error_code="SAME_DAY_CUTOFF",
                message=(
                    "因備餐與現場導覽調度作業，當日 15:00 以後不再受理當日預約急單。"
                    "歡迎您改為預約明日或未來檔期，或聯絡專人協助。"
                ),
                session_type=session_type,
                available_slots=[]
            )
        
        # 下午 (12:00～15:00) 提出，僅限預約 15:00 後
        if current_time >= time(12, 0) and slot_time < time(15, 0):
            return CapacityValidationResult(
                is_valid=False,
                error_code="AFTERNOON_URGENT_CUTOFF",
                message=(
                    "當日中午 12:00 以後提出之急單，僅能預約 15:00 以後之場次（15:00～17:00）。\n"
                    f"目前可選梯次：{', '.join(available_slots) if available_slots else '當日已無梯次'}"
                ),
                session_type=session_type,
                available_slots=available_slots
            )
            
        # 上午 (12:00 前) 提出，僅限預約下午場 (13:00 以後)
        if current_time < time(12, 0) and session_type == "上午場":
            return CapacityValidationResult(
                is_valid=False,
                error_code="MORNING_URGENT_CUTOFF",
                message=(
                    "當日上午提出之當日急單，僅能預約下午場次（13:00 以後）。\n"
                    f"目前下午場可選梯次：{', '.join(available_slots) if available_slots else '已無梯次'}"
                ),
                session_type=session_type,
                available_slots=available_slots
            )

    # 規則 4：總承載量與場次容量管制
    total_booked = morning_booked + afternoon_booked
    if (total_booked + incoming_people) > DAILY_CAPACITY_LIMIT:
        remaining_daily = max(0, DAILY_CAPACITY_LIMIT - total_booked)
        return CapacityValidationResult(
            is_valid=False,
            error_code="DAILY_CAPACITY_FULL",
            message=(
                f"該日園區總承載上限為 {DAILY_CAPACITY_LIMIT} 人，目前累計已預約 {total_booked} 人，"
                f"僅剩餘額度 {remaining_daily} 人，無法容納貴團 {incoming_people} 人。"
            ),
            session_type=session_type,
            available_slots=[]
        )

    if session_type == "上午場":
        if (morning_booked + incoming_people) > MORNING_CAPACITY_LIMIT:
            remaining_morning = max(0, MORNING_CAPACITY_LIMIT - morning_booked)
            return CapacityValidationResult(
                is_valid=False,
                error_code="MORNING_CAPACITY_FULL",
                message=(
                    f"該日上午場（10:00～13:00）額度上限為 {MORNING_CAPACITY_LIMIT} 人，"
                    f"目前已預約 {morning_booked} 人，僅剩餘額度 {remaining_morning} 人，"
                    f"無法容納貴團 {incoming_people} 人。建議改選下午場次！"
                ),
                session_type=session_type,
                available_slots=available_slots
            )
    else:  # 下午場
        if (afternoon_booked + incoming_people) > AFTERNOON_CAPACITY_LIMIT:
            remaining_afternoon = max(0, AFTERNOON_CAPACITY_LIMIT - afternoon_booked)
            return CapacityValidationResult(
                is_valid=False,
                error_code="AFTERNOON_CAPACITY_FULL",
                message=(
                    f"該日下午場（13:00～17:00）額度上限為 {AFTERNOON_CAPACITY_LIMIT} 人，"
                    f"目前已預約 {afternoon_booked} 人，僅剩餘額度 {remaining_afternoon} 人，"
                    f"無法容納貴團 {incoming_people} 人。"
                ),
                session_type=session_type,
                available_slots=available_slots
            )

    # 通過所有檢驗
    return CapacityValidationResult(
        is_valid=True,
        error_code=None,
        message=f"時段檢核通過（{session_type} {booking_time_str}），名額充裕可正常預約！",
        session_type=session_type,
        available_slots=available_slots
    )
