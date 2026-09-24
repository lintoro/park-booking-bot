"""
Google Sheets 雲端試算表資料庫串接模組 (sheets_service.py)

依據企劃書定義之後台架構：
1. 工作表 1：`預約記錄表_Log` (主要訂單庫)
   - 記錄預約編號、建立時間、日期梯次、團體名稱、窗口資訊、票數、車數、免票、總額、10%訂金、統編與訂金狀態。
2. 工作表 2：`檔期總量控管_Dashboard` (容量警示儀表板)
   - 即時彙總各日期「上午場 (上限 400)」與「下午場 (上限 600)」之累計預約人數。

風控與架構規範：
- 服務帳戶認證憑證由 GOOGLE_CREDENTIALS_FILE 注入，嚴禁硬編碼。
- 支援本機開發與測試的 Mock / 記憶體備援機制，無憑證時不崩潰並記錄日誌。
"""
import os
import logging
from datetime import datetime, date
from typing import Optional, Tuple, Dict, Any, List
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

from app.config import (
    GOOGLE_SPREADSHEET_ID,
    GOOGLE_CREDENTIALS_FILE,
    MORNING_CAPACITY_LIMIT,
    AFTERNOON_CAPACITY_LIMIT,
    DAILY_CAPACITY_LIMIT,
)
from app.core.capacity_gate import get_current_taipei_time
from app.core.models import BookingData

logger = logging.getLogger("sheets_service")
logger.setLevel(logging.INFO)

# Google Sheets API 權限範圍
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# 工作表名稱常數
SHEET_LOG_NAME = "預約記錄表_Log"
SHEET_DASHBOARD_NAME = "檔期總量控管_Dashboard"

# 預約記錄表標準表頭 (21 欄)
LOG_HEADERS = [
    "預約編號", "建立時間", "入園日期", "入場梯次", "場次類型",
    "團體名稱", "聯絡窗口", "聯絡手機", "全票數", "半票數",
    "幼童免票數", "遊覽車台數", "隨隊免票數", "團員人數", "入場總人數",
    "門票總額", "10%訂金金額", "統一編號", "發票抬頭", "訂金狀態", "業務備註"
]

# 檔期總量控管標準表頭 (5 欄)
DASHBOARD_HEADERS = [
    "入園日期",
    f"上午場累計人數 (上限 {MORNING_CAPACITY_LIMIT})",
    f"下午場累計人數 (上限 {AFTERNOON_CAPACITY_LIMIT})",
    f"全日累計人數 (上限 {DAILY_CAPACITY_LIMIT})",
    "狀態警示"
]

# --- 本地記憶體模擬資料庫 (供測試與無憑證時備援) ---
_MOCK_LOG_DB: List[Dict[str, Any]] = []
_MOCK_CAPACITY_CACHE: Dict[str, Dict[str, int]] = {}


def get_gspread_client() -> Optional[gspread.Client]:
    """取得授權之 gspread 客戶端"""
    cred_path = Path(GOOGLE_CREDENTIALS_FILE)
    if not cred_path.exists():
        logger.warning(f"Google 憑證檔案不存在：{GOOGLE_CREDENTIALS_FILE}，切換為本地模擬儲存模式。")
        return None

    try:
        credentials = Credentials.from_service_account_file(
            str(cred_path),
            scopes=SCOPES
        )
        client = gspread.authorize(credentials)
        return client
    except Exception as e:
        logger.error(f"Google 服務帳戶認證失敗：{e}")
        return None


def get_spreadsheet() -> Optional[gspread.Spreadsheet]:
    """取得 Google 試算表物件"""
    client = get_gspread_client()
    if not client or not GOOGLE_SPREADSHEET_ID:
        return None
    try:
        return client.open_by_key(GOOGLE_SPREADSHEET_ID)
    except Exception as e:
        logger.error(f"無法開啟試算表 ID [{GOOGLE_SPREADSHEET_ID}]：{e}")
        return None


def initialize_sheets_structure(spreadsheet: Optional[gspread.Spreadsheet] = None) -> bool:
    """
    初始化試算表結構：若工作表不存在則自動建立，並寫入標準表頭。
    """
    if spreadsheet is None:
        spreadsheet = get_spreadsheet()

    if not spreadsheet:
        logger.info("尚未連線至線上 Google 試算表，略過雲端表頭初始化。")
        return False

    try:
        existing_sheet_titles = [s.title for s in spreadsheet.worksheets()]

        # 1. 建立或檢查 預約記錄表_Log
        if SHEET_LOG_NAME not in existing_sheet_titles:
            ws_log = spreadsheet.add_worksheet(title=SHEET_LOG_NAME, rows=1000, cols=25)
            ws_log.append_row(LOG_HEADERS)
            logger.info(f"已建立工作表：{SHEET_LOG_NAME}")
        else:
            ws_log = spreadsheet.worksheet(SHEET_LOG_NAME)
            if not ws_log.row_values(1):
                ws_log.append_row(LOG_HEADERS)

        # 2. 建立或檢查 檔期總量控管_Dashboard
        if SHEET_DASHBOARD_NAME not in existing_sheet_titles:
            ws_dash = spreadsheet.add_worksheet(title=SHEET_DASHBOARD_NAME, rows=500, cols=10)
            ws_dash.append_row(DASHBOARD_HEADERS)
            logger.info(f"已建立工作表：{SHEET_DASHBOARD_NAME}")
        else:
            ws_dash = spreadsheet.worksheet(SHEET_DASHBOARD_NAME)
            if not ws_dash.row_values(1):
                ws_dash.append_row(DASHBOARD_HEADERS)

        return True
    except Exception as e:
        logger.error(f"初始化 Google 試算表工作表結構失敗：{e}")
        return False


def build_log_row(booking: BookingData) -> List[Any]:
    """將 BookingData 模型轉換為 預約記錄表_Log 的資料列"""
    now_str = get_current_taipei_time().strftime("%Y-%m-%d %H:%M:%S")
    date_str = str(booking.booking_date) if booking.booking_date else ""

    return [
        booking.reservation_id,
        now_str,
        date_str,
        booking.booking_time,
        booking.session_type,
        booking.group_name,
        booking.contact_name,
        booking.contact_phone,
        booking.adult_count,
        booking.concession_count,
        booking.child_count,
        booking.tour_bus_count,
        booking.free_crew_count,
        booking.group_member_count,
        booking.total_admission_count,
        booking.total_amount,
        booking.deposit_amount,
        booking.invoice_tax_id,
        booking.invoice_title,
        "未付訂",      # 預設狀態為未付訂 (彈性意向登記)
        ""            # 業務備註預設空白
    ]


def append_reservation_record(booking: BookingData) -> bool:
    """
    將預約資料寫入 `預約記錄表_Log`，並動態更新 `檔期總量控管_Dashboard`。
    若無雲端金鑰，則同步寫入本機記憶體備援資料庫。
    """
    row_data = build_log_row(booking)
    date_key = str(booking.booking_date) if booking.booking_date else "unknown_date"

    # 1. 寫入本地記憶體模擬庫
    _MOCK_LOG_DB.append(dict(zip(LOG_HEADERS, row_data)))
    if date_key not in _MOCK_CAPACITY_CACHE:
        _MOCK_CAPACITY_CACHE[date_key] = {"morning": 0, "afternoon": 0}

    if booking.session_type == "上午場":
        _MOCK_CAPACITY_CACHE[date_key]["morning"] += booking.total_admission_count
    else:
        _MOCK_CAPACITY_CACHE[date_key]["afternoon"] += booking.total_admission_count

    # 2. 寫入線上 Google 試算表 (若有設定)
    spreadsheet = get_spreadsheet()
    if not spreadsheet:
        logger.info(f"[本地模擬寫入成功] 預約編號={booking.reservation_id}, 入園人數={booking.total_admission_count}")
        return True

    try:
        ws_log = spreadsheet.worksheet(SHEET_LOG_NAME)
        ws_log.append_row(row_data)
        logger.info(f"成功將預約編號 [{booking.reservation_id}] 寫入線上試算表！")

        # 3. 連動更新儀表板容量
        _update_dashboard_sheet(spreadsheet, date_key, booking.session_type, booking.total_admission_count)
        return True
    except Exception as e:
        logger.error(f"寫入 Google 試算表失敗：{e}")
        return False


def _update_dashboard_sheet(
    spreadsheet: gspread.Spreadsheet,
    date_str: str,
    session_type: str,
    new_admission_people: int
):
    """更新線上檔期總量控管儀表板累計人數"""
    try:
        ws_dash = spreadsheet.worksheet(SHEET_DASHBOARD_NAME)
        records = ws_dash.get_all_records()

        row_index = None
        current_morning = 0
        current_afternoon = 0

        for idx, rec in enumerate(records, start=2):
            if str(rec.get("入園日期", "")) == date_str:
                row_index = idx
                current_morning = int(rec.get(DASHBOARD_HEADERS[1], 0) or 0)
                current_afternoon = int(rec.get(DASHBOARD_HEADERS[2], 0) or 0)
                break

        if session_type == "上午場":
            current_morning += new_admission_people
        else:
            current_afternoon += new_admission_people

        total_daily = current_morning + current_afternoon

        # 計算警示狀態
        warning_flags = []
        if current_morning >= MORNING_CAPACITY_LIMIT:
            warning_flags.append("上午額滿")
        if current_afternoon >= AFTERNOON_CAPACITY_LIMIT:
            warning_flags.append("下午額滿")
        if total_daily >= DAILY_CAPACITY_LIMIT:
            warning_flags.append("全日額滿")

        warning_status = "正常" if not warning_flags else " / ".join(warning_flags)

        dash_row = [date_str, current_morning, current_afternoon, total_daily, warning_status]

        if row_index is not None:
            ws_dash.update(values=[dash_row], range_name=f"A{row_index}:E{row_index}")
        else:
            ws_dash.append_row(dash_row)


    except Exception as e:
        logger.error(f"更新檔期總量控管儀表板失敗：{e}")


def get_booked_capacity(booking_date: date) -> Tuple[int, int]:
    """
    取得特定日期已預約之「上午場人數」與「下午場人數」 (morning_booked, afternoon_booked)
    """
    date_key = str(booking_date)

    # 1. 優先查線上試算表
    spreadsheet = get_spreadsheet()
    if spreadsheet:
        try:
            ws_dash = spreadsheet.worksheet(SHEET_DASHBOARD_NAME)
            records = ws_dash.get_all_records()
            for rec in records:
                if str(rec.get("入園日期", "")) == date_key:
                    m = int(rec.get(DASHBOARD_HEADERS[1], 0) or 0)
                    a = int(rec.get(DASHBOARD_HEADERS[2], 0) or 0)
                    return m, a
        except Exception as e:
            logger.warning(f"線上查詢容量失敗，改查本地快取：{e}")

    # 2. 查本地記憶體快取
    if date_key in _MOCK_CAPACITY_CACHE:
        cache = _MOCK_CAPACITY_CACHE[date_key]
        return cache["morning"], cache["afternoon"]

    return 0, 0


def clear_mock_database():
    """清理本機測試用記憶體資料庫"""
    global _MOCK_LOG_DB, _MOCK_CAPACITY_CACHE
    _MOCK_LOG_DB = []
    _MOCK_CAPACITY_CACHE = {}


class SheetsService:
    """提供物件導向與手動測試相容之服務封裝"""
    def __init__(self, credentials_path: str = GOOGLE_CREDENTIALS_FILE, spreadsheet_id: Optional[str] = None):
        self.credentials_path = credentials_path
        self.spreadsheet_id = spreadsheet_id or GOOGLE_SPREADSHEET_ID
        self.client = get_gspread_client()
        self.sheet = get_spreadsheet()

    def append_reservation(self, data: Dict[str, Any]) -> bool:
        """手動字典寫入相容方法"""
        booking = BookingData(
            reservation_id=data.get("reservation_id", ""),
            booking_date=datetime.strptime(data.get("visit_date", "2026-01-01"), "%Y-%m-%d").date() if isinstance(data.get("visit_date"), str) else data.get("visit_date"),
            booking_time=data.get("visit_time", ""),
            session_type="上午場" if "上午" in data.get("visit_time", "") or (data.get("visit_time", "") and data.get("visit_time", "") < "13:00") else "下午場",
            group_name=data.get("group_name", ""),
            contact_name=data.get("contact_name", ""),
            contact_phone=data.get("contact_phone", ""),
            adult_count=data.get("adult_count", 0),
            concession_count=data.get("half_count", 0),
            child_count=data.get("child_free_count", 0),
            tour_bus_count=data.get("bus_count", 0),
            free_crew_count=data.get("crew_free_count", 0),
            total_admission_count=data.get("total_people", 0),
            total_amount=data.get("total_price", 0),
            deposit_amount=data.get("deposit_amount", 0),
            invoice_tax_id=data.get("tax_id", "無"),
        )
        return append_reservation_record(booking)

