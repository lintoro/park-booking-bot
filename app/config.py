"""
專案全域配置與系統常數設定模組 (config.py)
"""
import os
from typing import List
from dotenv import load_dotenv

# 載入 .env 環境變數
load_dotenv()

# --- LINE Messaging API 金鑰 ---
LINE_CHANNEL_SECRET: str = os.getenv("LINE_CHANNEL_SECRET", "")
LINE_CHANNEL_ACCESS_TOKEN: str = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")

# --- 伺服器配置 ---
PORT: int = int(os.getenv("PORT", "8000"))
TIMEZONE: str = os.getenv("TIMEZONE", "Asia/Taipei")

# --- Google 雲端試算表設定 ---
GOOGLE_SPREADSHEET_ID: str = os.getenv("GOOGLE_SPREADSHEET_ID", "")
GOOGLE_CREDENTIALS_FILE: str = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")
GOOGLE_CREDENTIALS_JSON: str = os.getenv("GOOGLE_CREDENTIALS_JSON", "")  # 供 Render 等雲端環境直接注入 JSON 內容


# --- Google Gemini AI 模型設定 ---
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", os.getenv("GOOGLE_API_KEY", ""))
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")


# --- 票價與營運規則常數 (企劃書定義) ---
ADULT_TICKET_PRICE: int = 280       # 全票 NT$ 280 元
CONCESSION_TICKET_PRICE: int = 140  # 半票 NT$ 140 元 (7~12歲學童、65歲以上長者)
CHILD_TICKET_PRICE: int = 0         # 免票 NT$ 0 元 (6歲以下幼兒)
FREE_CREW_PER_BUS: int = 2          # 每 1 台遊覽車享 2 位免票 (1 司機 + 1 領隊)
MIN_GROUP_SIZE: int = 20            # 成團人數最低門檻 20 人
DEPOSIT_RATE: float = 0.10          # 彈性訂金比例 10%

# --- 園區容量與排程限制 ---
DAILY_CAPACITY_LIMIT: int = 1000     # 全日總量上限 1,000 人
MORNING_CAPACITY_LIMIT: int = 400    # 上午場上限 400 人 (10:00~13:00)
AFTERNOON_CAPACITY_LIMIT: int = 600  # 下午場上限 600 人 (13:00~17:00)

SLOT_START_TIME: str = "10:00"       # 每日最早入園梯次
SLOT_LAST_GROUP_TIME: str = "17:00"  # 團體預約最後入場截止時間 (17:00 以後嚴禁預約)

# --- 人機協同與對話狀態常數 ---
SESSION_TIMEOUT_MINUTES: int = 15    # 15 分鐘無回應自動逾時重置
HUMAN_HANDOFF_KEYWORDS: List[str] = ["專人", "客服", "業務", "電話", "人工"]

# --- 真人專人客服預設資訊 ---
DEFAULT_STAFF_NAME: str = "團體業務部專員"
DEFAULT_STAFF_PHONE: str = "02-2345-6789"
DEFAULT_STAFF_EXT: str = "888"
DEFAULT_SERVICE_HOURS: str = "週一至週五 09:00 - 18:00"
