import os
from datetime import datetime
from dotenv import load_dotenv
from app.services.sheets_service import SheetsService

load_dotenv()

def test_connection():
    spreadsheet_id = os.getenv("GOOGLE_SPREADSHEET_ID")
    credentials_path = "credentials.json"

    print("=== Google 試算表連線測試 ===")
    print(f"1. 檢查憑證檔案：{credentials_path} -> {'存在' if os.path.exists(credentials_path) else '尚未放置'}")
    print(f"2. 檢查試算表 ID：{spreadsheet_id or '尚未設定'}")

    if not os.path.exists(credentials_path) or not spreadsheet_id:
        print("\n[提示] 請先完成 Google Cloud 金鑰下載與 .env 設定後再執行測試！")
        return

    service = SheetsService(credentials_path=credentials_path, spreadsheet_id=spreadsheet_id)
    if not service.sheet:
        print("\n[錯誤] 無法開啟 Google 試算表，請確認服務帳戶 Email 是否已被加入試算表的「編輯者」權限！")
        return

    print("\n[成功] Google 試算表連線成功！正在寫入一筆測試資料...")
    test_data = {
        "reservation_id": f"TEST-{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "visit_date": "2026-10-15",
        "visit_time": "10:30",
        "group_name": "測試國小",
        "contact_name": "王小明",
        "contact_phone": "0912-345-678",
        "tax_id": "12345678",
        "adult_count": 25,
        "half_count": 10,
        "child_free_count": 2,
        "bus_count": 1,
        "crew_free_count": 2,
        "total_people": 39,
        "total_price": 8400,
        "deposit_amount": 840,
        "payment_status": "未付訂",
        "notes": "系統自動連線測試"
    }
    
    success = service.append_reservation(test_data)
    if success:
        print("[成功] 測試資料寫入成功！請前往 Google 試算表查看「預約記錄表_Log」！")
    else:
        print("[失敗] 資料寫入失敗，請檢查錯誤紀錄。")

if __name__ == "__main__":
    test_connection()
