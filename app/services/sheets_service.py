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
import re
import json
import logging
from datetime import datetime, date
from typing import Optional, Tuple, Dict, Any, List
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

from app.config import (
    GOOGLE_SPREADSHEET_ID,
    GOOGLE_CREDENTIALS_FILE,
    GOOGLE_CREDENTIALS_JSON,
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
SHEET_CRM_NAME = "顧客檔案與業務歸屬_CRM"

# 預約記錄表標準表頭 (30 欄) - 涵蓋進件到結案全生命週期與 GRM 追蹤
LOG_HEADERS = [
    "預約編號", "建立時間", "LINE_User_ID", "負責業務員", "入園日期",
    "入場梯次", "場次類型", "團體名稱", "聯絡窗口", "聯絡手機",
    "全票數", "半票數", "幼童免票數", "遊覽車台數", "隨隊免票數",
    "團員人數", "入場總人數", "門票總額", "10%訂金金額", "統一編號",
    "發票抬頭", "訂金狀態", "訂金入帳日與末五碼", "到場狀態", "實到總人數",
    "人數落差備註", "實收尾款", "發票開立狀態", "案件狀態", "業務跟進備註"
]

# 檔期總量控管標準表頭 (5 欄)
DASHBOARD_HEADERS = [
    "入園日期",
    f"上午場累計人數 (上限 {MORNING_CAPACITY_LIMIT})",
    f"下午場累計人數 (上限 {AFTERNOON_CAPACITY_LIMIT})",
    f"全日累計人數 (上限 {DAILY_CAPACITY_LIMIT})",
    "狀態警示"
]

# 顧客檔案與業務歸屬標準表頭 (15 欄) - 專門供業務管理與日後顧客關係資料分析
CRM_HEADERS = [
    "LINE_User_ID", "LINE暱稱", "客戶團體名稱", "主要聯絡人", "聯絡手機",
    "負責業務員", "顧客評級", "首次預約日期", "最近互動日期", "累計預約次數",
    "累計成單次數", "累計到場次數", "爽約次數", "累計消費總額", "業務標籤與備註"
]

# --- 本地記憶體模擬資料庫 (供測試與無憑證時備援) ---
_MOCK_LOG_DB: List[Dict[str, Any]] = []
_MOCK_CAPACITY_CACHE: Dict[str, Dict[str, int]] = {}
_MOCK_CRM_DB: Dict[str, Dict[str, Any]] = {}


def get_gspread_client() -> Optional[gspread.Client]:
    """取得授權之 gspread 客戶端 (支援 GOOGLE_CREDENTIALS_JSON 環境變數或本地憑證檔案)"""
    # 1. 優先支援 Render / 雲端環境變數直接注入 JSON 內容
    if GOOGLE_CREDENTIALS_JSON and GOOGLE_CREDENTIALS_JSON.strip():
        try:
            cred_dict = json.loads(GOOGLE_CREDENTIALS_JSON)
            credentials = Credentials.from_service_account_info(
                cred_dict,
                scopes=SCOPES
            )
            return gspread.authorize(credentials)
        except Exception as e:
            logger.error(f"解析環境變數 GOOGLE_CREDENTIALS_JSON 失敗：{e}")

    # 2. 次要支援本地憑證檔案路徑
    cred_path = Path(GOOGLE_CREDENTIALS_FILE)
    if cred_path.exists():
        try:
            credentials = Credentials.from_service_account_file(
                str(cred_path),
                scopes=SCOPES
            )
            return gspread.authorize(credentials)
        except Exception as e:
            logger.error(f"Google 服務帳戶認證失敗：{e}")
            return None

    logger.warning("未配置有效之 Google 服務帳戶憑證 (無 JSON 環境變數且無憑證檔案)，切換為本地模擬儲存模式。")
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
    初始化試算表結構：
    1. 建立或升級 預約記錄表_Log (30 欄)
    2. 建立 檔期總量控管_Dashboard (5 欄)
    3. 建立 顧客檔案與業務歸屬_CRM (15 欄)
    """
    if spreadsheet is None:
        spreadsheet = get_spreadsheet()

    if not spreadsheet:
        logger.info("尚未連線至線上 Google 試算表，略過雲端表頭初始化。")
        return False

    try:
        existing_sheet_titles = [s.title for s in spreadsheet.worksheets()]

        # 1. 建立或升級 預約記錄表_Log
        if SHEET_LOG_NAME not in existing_sheet_titles:
            ws_log = spreadsheet.add_worksheet(title=SHEET_LOG_NAME, rows=1000, cols=35)
            ws_log.append_row(LOG_HEADERS)
            logger.info(f"已建立工作表：{SHEET_LOG_NAME} (30 欄)")
        else:
            ws_log = spreadsheet.worksheet(SHEET_LOG_NAME)
            current_headers = ws_log.row_values(1)
            if not current_headers:
                ws_log.append_row(LOG_HEADERS)
            elif len(current_headers) < len(LOG_HEADERS):
                # 欄位擴充平滑升級：將首列更新為最新的 30 欄標頭
                ws_log.update(values=[LOG_HEADERS], range_name=f"A1:AD1")
                logger.info(f"已成功將 {SHEET_LOG_NAME} 表頭擴充升級為 {len(LOG_HEADERS)} 欄！")

        # 2. 建立或檢查 檔期總量控管_Dashboard
        if SHEET_DASHBOARD_NAME not in existing_sheet_titles:
            ws_dash = spreadsheet.add_worksheet(title=SHEET_DASHBOARD_NAME, rows=500, cols=10)
            ws_dash.append_row(DASHBOARD_HEADERS)
            logger.info(f"已建立工作表：{SHEET_DASHBOARD_NAME}")
        else:
            ws_dash = spreadsheet.worksheet(SHEET_DASHBOARD_NAME)
            if not ws_dash.row_values(1):
                ws_dash.append_row(DASHBOARD_HEADERS)

        # 3. 建立或檢查 顧客檔案與業務歸屬_CRM
        if SHEET_CRM_NAME not in existing_sheet_titles:
            ws_crm = spreadsheet.add_worksheet(title=SHEET_CRM_NAME, rows=1000, cols=20)
            ws_crm.append_row(CRM_HEADERS)
            logger.info(f"已建立工作表：{SHEET_CRM_NAME} (15 欄)")
        else:
            ws_crm = spreadsheet.worksheet(SHEET_CRM_NAME)
            if not ws_crm.row_values(1):
                ws_crm.append_row(CRM_HEADERS)

        return True
    except Exception as e:
        logger.error(f"初始化 Google 試算表工作表結構失敗：{e}")
        return False


def build_log_row(booking: BookingData) -> List[Any]:
    """將 BookingData 模型轉換為 預約記錄表_Log 的資料列 (精確 30 欄)"""
    now_str = get_current_taipei_time().strftime("%Y-%m-%d %H:%M:%S")
    date_str = str(booking.booking_date) if booking.booking_date else ""

    return [
        booking.reservation_id,                     # 1. 預約編號
        now_str,                                    # 2. 建立時間
        booking.user_id,                            # 3. LINE_User_ID
        booking.sales_rep or "業務專員",             # 4. 負責業務員
        date_str,                                   # 5. 入園日期
        booking.booking_time,                       # 6. 入場梯次
        booking.session_type,                       # 7. 場次類型
        booking.group_name,                         # 8. 團體名稱
        booking.contact_name,                       # 9. 聯絡窗口
        booking.contact_phone,                      # 10. 聯絡手機
        booking.adult_count,                        # 11. 全票數
        booking.concession_count,                   # 12. 半票數
        booking.child_count,                        # 13. 幼童免票數
        booking.tour_bus_count,                     # 14. 遊覽車台數
        booking.free_crew_count,                    # 15. 隨隊免票數
        booking.group_member_count,                 # 16. 團員人數
        booking.total_admission_count,              # 17. 入場總人數
        booking.total_amount,                       # 18. 門票總額
        booking.deposit_amount,                     # 19. 10%訂金金額
        booking.invoice_tax_id,                     # 20. 統一編號
        booking.invoice_title,                      # 21. 發票抬頭
        booking.deposit_status or "待收訂金",         # 22. 訂金狀態
        "",                                         # 23. 訂金入帳日與末五碼 (業務後續確認填寫)
        booking.show_status or "待履約",             # 24. 到場狀態
        booking.actual_admission_count or 0,        # 25. 實到總人數
        booking.headcount_diff_note or "",          # 26. 人數落差備註
        booking.final_payment_amount or 0,          # 27. 實收尾款
        booking.invoice_status or "未開立",          # 28. 發票開立狀態
        booking.case_status or "進行中",             # 29. 案件狀態
        booking.sales_note or ""                    # 30. 業務跟進備註
    ]


def upsert_customer_crm_profile(booking: BookingData, line_display_name: str = "") -> bool:
    """
    依據顧客 LINE_User_ID 新增或更新『顧客檔案與業務歸屬_CRM』表。
    累計預約次數、累計消費總額、最近互動日期、業務歸屬。
    """
    user_id = booking.user_id or "anonymous_user"
    today_str = get_current_taipei_time().strftime("%Y-%m-%d")

    # 1. 本機記憶體模擬庫維護
    if user_id not in _MOCK_CRM_DB:
        _MOCK_CRM_DB[user_id] = {
            "LINE_User_ID": user_id,
            "LINE暱稱": line_display_name,
            "客戶團體名稱": booking.group_name,
            "主要聯絡人": booking.contact_name,
            "聯絡手機": booking.contact_phone,
            "負責業務員": booking.sales_rep or "業務專員",
            "顧客評級": "一般客戶",
            "首次預約日期": today_str,
            "最近互動日期": today_str,
            "累計預約次數": 1,
            "累計成單次數": 0,
            "累計到場次數": 0,
            "爽約次數": 0,
            "累計消費總額": booking.total_amount,
            "業務標籤與備註": "新客入庫登記"
        }
    else:
        profile = _MOCK_CRM_DB[user_id]
        profile["最近互動日期"] = today_str
        profile["累計預約次數"] += 1
        profile["累計消費總額"] += booking.total_amount
        if booking.group_name:
            profile["客戶團體名稱"] = booking.group_name
        if booking.contact_name:
            profile["主要聯絡人"] = booking.contact_name
        if booking.contact_phone:
            profile["聯絡手機"] = booking.contact_phone
        if line_display_name:
            profile["LINE暱稱"] = line_display_name

    # 2. 寫入線上 Google 試算表 (若有設定)
    spreadsheet = get_spreadsheet()
    if not spreadsheet:
        return True

    try:
        ws_crm = spreadsheet.worksheet(SHEET_CRM_NAME)
        records = ws_crm.get_all_records()
        row_index = None
        target_rec = None

        for idx, rec in enumerate(records, start=2):
            if str(rec.get("LINE_User_ID", "")).strip() == user_id.strip():
                row_index = idx
                target_rec = rec
                break

        if row_index is not None and target_rec:
            # 更新既有客戶資料
            prev_booking_count = int(target_rec.get("累計預約次數", 0) or 0)
            prev_total_spend = int(target_rec.get("累計消費總額", 0) or 0)
            first_date = str(target_rec.get("首次預約日期", "")) or today_str
            sales_rep = str(target_rec.get("負責業務員", "")) or booking.sales_rep or "業務專員"
            rating = str(target_rec.get("顧客評級", "一般客戶")) or "一般客戶"

            new_booking_count = prev_booking_count + 1
            new_total_spend = prev_total_spend + (booking.total_amount or 0)

            # 動態客戶評級提升機制
            if new_total_spend >= 100000 or new_booking_count >= 3:
                rating = "VIP大客戶"
            elif new_booking_count >= 2:
                rating = "忠誠熟客"

            updated_row = [
                user_id,
                line_display_name or str(target_rec.get("LINE暱稱", "")),
                booking.group_name or str(target_rec.get("客戶團體名稱", "")),
                booking.contact_name or str(target_rec.get("主要聯絡人", "")),
                booking.contact_phone or str(target_rec.get("聯絡手機", "")),
                sales_rep,
                rating,
                first_date,
                today_str,
                new_booking_count,
                int(target_rec.get("累計成單次數", 0) or 0),
                int(target_rec.get("累計到場次數", 0) or 0),
                int(target_rec.get("爽約次數", 0) or 0),
                new_total_spend,
                str(target_rec.get("業務標籤與備註", ""))
            ]
            ws_crm.update(values=[updated_row], range_name=f"A{row_index}:O{row_index}")
            logger.info(f"成功更新 CRM 顧客資料：user_id={user_id}, 累計預約={new_booking_count}, 評級={rating}")
        else:
            # 新客入庫建立
            new_row = [
                user_id,
                line_display_name or "",
                booking.group_name,
                booking.contact_name,
                booking.contact_phone,
                booking.sales_rep or "業務專員",
                "一般客戶",
                today_str,
                today_str,
                1,
                0,
                0,
                0,
                booking.total_amount or 0,
                "新客入庫登記"
            ]
            ws_crm.append_row(new_row)
            logger.info(f"成功建立 CRM 新客建檔：user_id={user_id}, 團體={booking.group_name}")

        return True
    except Exception as e:
        logger.error(f"更新 CRM 顧客資料庫失敗：{e}")
        return False


def append_reservation_record(booking: BookingData, line_display_name: str = "") -> bool:
    """
    將預約資料寫入 `預約記錄表_Log` (30 欄)，
    並連動更新 `檔期總量控管_Dashboard` 與 `顧客檔案與業務歸屬_CRM` (15 欄)。
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
        upsert_customer_crm_profile(booking, line_display_name=line_display_name)
        logger.info(f"[本地模擬寫入成功] 預約編號={booking.reservation_id}, 入園人數={booking.total_admission_count}")
        return True

    try:
        # 確保工作表與表頭正確存在
        initialize_sheets_structure(spreadsheet)

        ws_log = spreadsheet.worksheet(SHEET_LOG_NAME)
        ws_log.append_row(row_data)
        logger.info(f"成功將預約編號 [{booking.reservation_id}] 寫入線上試算表！")

        # 3. 連動更新儀表板容量
        _update_dashboard_sheet(spreadsheet, date_key, booking.session_type, booking.total_admission_count)

        # 4. 連動更新顧客檔案與業務歸屬 CRM
        upsert_customer_crm_profile(booking, line_display_name=line_display_name)
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
            current_morning = max(0, current_morning + new_admission_people)
        else:
            current_afternoon = max(0, current_afternoon + new_admission_people)

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


def get_reservations_by_user_id(user_id: str) -> List[Dict[str, Any]]:
    """根據 LINE_User_ID 查詢使用者的歷史或進行中預約清單（最新的排前面）"""
    if not user_id:
        return []

    # 1. 優先查線上試算表
    spreadsheet = get_spreadsheet()
    if spreadsheet:
        try:
            ws_log = spreadsheet.worksheet(SHEET_LOG_NAME)
            records = ws_log.get_all_records()
            user_records = []
            for rec in records:
                if str(rec.get("LINE_User_ID", "")).strip() == user_id.strip():
                    user_records.append(rec)
            user_records.reverse()
            return user_records
        except Exception as e:
            logger.error(f"線上查詢使用者預約記錄失敗：{e}")

    # 2. 查本地記憶體模擬庫
    user_records = [
        r for r in _MOCK_LOG_DB
        if str(r.get("LINE_User_ID", "")).strip() == user_id.strip()
    ]
    user_records.reverse()
    return user_records


def get_reservation_by_id(reservation_id: str) -> Optional[Dict[str, Any]]:
    """根據預約流水編號查詢預約詳細資料"""
    if not reservation_id:
        return None

    spreadsheet = get_spreadsheet()
    if spreadsheet:
        try:
            ws_log = spreadsheet.worksheet(SHEET_LOG_NAME)
            records = ws_log.get_all_records()
            for rec in records:
                if str(rec.get("預約編號", "")).strip() == reservation_id.strip():
                    return rec
        except Exception as e:
            logger.error(f"線上查詢單筆預約編號失敗：{e}")

    for r in _MOCK_LOG_DB:
        if str(r.get("預約編號", "")).strip() == reservation_id.strip():
            return r

    return None


def cancel_existing_reservation(reservation_id: str, user_id: str = "") -> Tuple[bool, str]:
    """
    取消已確認之預約：
    1. 狀態更新為「取消」
    2. 自動扣減 Dashboard 檔期人數釋放名額
    3. 業務備註記錄取消時間戳記
    """
    if not reservation_id:
        return False, "無效的預約編號。"

    now_str = get_current_taipei_time().strftime("%Y-%m-%d %H:%M:%S")

    # 本地記憶體模擬取消處理
    for r in _MOCK_LOG_DB:
        if str(r.get("預約編號", "")).strip() == reservation_id.strip():
            if user_id and str(r.get("LINE_User_ID", "")).strip() != user_id.strip():
                return False, "您無權限取消此筆預約。"
            if str(r.get("到場狀態", "")) == "取消":
                return False, "此筆預約先前已取消，無須重複操作。"

            r["到場狀態"] = "取消"
            r["案件狀態"] = "已取消(客戶線上取消)"
            r["業務跟進備註"] = (r.get("業務跟進備註", "") + f" [於 {now_str} 客戶自主取消]").strip()

            date_str = str(r.get("入園日期", ""))
            session_type = str(r.get("場次類型", "上午場"))
            total_count = int(r.get("入場總人數", 0) or 0)
            if date_str in _MOCK_CAPACITY_CACHE:
                field = "morning" if session_type == "上午場" else "afternoon"
                _MOCK_CAPACITY_CACHE[date_str][field] = max(0, _MOCK_CAPACITY_CACHE[date_str][field] - total_count)

    spreadsheet = get_spreadsheet()
    if not spreadsheet:
        return True, "預約已成功取消，名額已釋出。"

    try:
        ws_log = spreadsheet.worksheet(SHEET_LOG_NAME)
        records = ws_log.get_all_records()
        row_idx = None
        target_rec = None

        for idx, rec in enumerate(records, start=2):
            if str(rec.get("預約編號", "")).strip() == reservation_id.strip():
                row_idx = idx
                target_rec = rec
                break

        if not row_idx or not target_rec:
            return False, f"查無預約編號 [{reservation_id}]。"

        if user_id and str(target_rec.get("LINE_User_ID", "")).strip() != user_id.strip():
            return False, "您無權限取消此筆預約。"

        if str(target_rec.get("到場狀態", "")) == "取消":
            return False, "此筆預約先前已取消，無須重複操作。"

        # 更新該列：第 24 欄 (到場狀態)、第 29 欄 (案件狀態)、第 30 欄 (業務備註)
        ws_log.update_cell(row_idx, 24, "取消")
        ws_log.update_cell(row_idx, 29, "已取消(客戶線上取消)")
        prev_note = str(target_rec.get("業務跟進備註", ""))
        new_note = (prev_note + f" [於 {now_str} 客戶自主取消]").strip()
        ws_log.update_cell(row_idx, 30, new_note)

        # 釋放容量
        date_str = str(target_rec.get("入園日期", ""))
        session_type = str(target_rec.get("場次類型", "上午場"))
        total_count = int(target_rec.get("入場總人數", 0) or 0)
        _update_dashboard_sheet(spreadsheet, date_str, session_type, -total_count)

        logger.info(f"成功取消預約 [{reservation_id}] 並扣減容量人數 {total_count} 位")
        return True, "預約已成功取消，名額已為您即時釋出。"
    except Exception as e:
        logger.error(f"線上取消預約失敗：{e}")
        return False, f"取消預約時發生系統異常：{e}"


def _find_lcs_length(s1: str, s2: str) -> int:
    """計算兩字串之最長公共子字串長度"""
    if not s1 or not s2:
        return 0
    m = [[0] * (1 + len(s2)) for _ in range(1 + len(s1))]
    longest = 0
    for x in range(1, 1 + len(s1)):
        for y in range(1, 1 + len(s2)):
            if s1[x - 1] == s2[y - 1]:
                m[x][y] = m[x - 1][y - 1] + 1
                if m[x][y] > longest:
                    longest = m[x][y]
            else:
                m[x][y] = 0
    return longest


def check_duplicate_booking(
    booking_date: date,
    group_name: str,
    contact_phone: str = "",
    current_res_id: str = ""
) -> Optional[Dict[str, Any]]:
    """
    避免重複預約核對（Duplicate / Collision Prevention）：
    若同一日期已有相近團體名稱或相同電話之有效預約，回傳該筆預約資訊以進行防呆提醒。
    """
    if not booking_date:
        return None

    date_str = str(booking_date)
    clean_phone = re.sub(r"\D", "", contact_phone) if contact_phone else ""
    # 提取核心團體名稱 (去除常見公司、學校、福委會、旅行社等詞)
    clean_target_group = re.sub(r"(?i)(股份有限公司|有限公司|科技公司|企業社|企業|公司|國小|國中|高中|大學|幼兒園|幼兒學校|旅行社|福委會|福利會|職工會|協會|教會|健行團|同好會)", "", group_name).strip()

    all_records = []
    spreadsheet = get_spreadsheet()
    if spreadsheet:
        try:
            ws_log = spreadsheet.worksheet(SHEET_LOG_NAME)
            all_records = ws_log.get_all_records()
        except Exception as e:
            logger.error(f"查詢試算表重複預約失敗：{e}")
            all_records = _MOCK_LOG_DB
    else:
        all_records = _MOCK_LOG_DB

    for rec in all_records:
        # 排除已取消的單
        if str(rec.get("到場狀態", "")) == "取消" or "取消" in str(rec.get("案件狀態", "")):
            continue

        res_id = str(rec.get("預約編號", "")).strip()
        if current_res_id and res_id == current_res_id:
            continue

        rec_date = str(rec.get("入園日期", "")).strip()
        if rec_date != date_str:
            continue

        # 檢測 1: 電話相同 (同一個窗口又在同一天預約)
        rec_phone = re.sub(r"\D", "", str(rec.get("聯絡手機", "")))
        if clean_phone and len(clean_phone) >= 7 and rec_phone and clean_phone == rec_phone:
            logger.info(f"偵測到同電話重複預約：{clean_phone} (既有單號: {res_id})")
            return rec

        # 檢測 2: 團體名稱相同或核心名稱高度重疊
        rec_group = str(rec.get("團體名稱", "")).strip()
        clean_rec_group = re.sub(r"(?i)(股份有限公司|有限公司|科技公司|企業社|企業|公司|國小|國中|高中|大學|幼兒園|幼兒學校|旅行社|福委會|福利會|職工會|協會|教會|健行團|同好會)", "", rec_group).strip()

        if rec_group and group_name and (rec_group == group_name):
            logger.info(f"偵測到同團名重複預約：{group_name} (既有單號: {res_id})")
            return rec

        if len(clean_target_group) >= 2 and len(clean_rec_group) >= 2:
            if clean_target_group in clean_rec_group or clean_rec_group in clean_target_group:
                logger.info(f"偵測到相似團名重複預約：{group_name} vs {rec_group} (既有單號: {res_id})")
                return rec

        # 檢測 3: 最長公共子字串 >= 4 (例如「聯發科技軟體處」與「聯發科技硬體處」，重疊「聯發科技」4字)
        lcs_len = _find_lcs_length(group_name, rec_group)
        if lcs_len >= 4:
            logger.info(f"偵測到核心機構重疊重複預約(LCS={lcs_len})：{group_name} vs {rec_group} (既有單號: {res_id})")
            return rec

    return None



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
    global _MOCK_LOG_DB, _MOCK_CAPACITY_CACHE, _MOCK_CRM_DB
    _MOCK_LOG_DB = []
    _MOCK_CAPACITY_CACHE = {}
    _MOCK_CRM_DB = {}



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

