# 專案交接手冊與異機開發指南 (PROJECT_HANDOVER.md)

> **當前系統版本**：`v1.2.0`  
> **最後更新時間**：2026-09-24  
> **託管與線上環境**：GitHub (`lintoro/park-booking-bot.git`) + Render.com 雲端自動持續部署 (PaaS)  
> **線上服務網址**：`https://park-booking-bot.onrender.com`  

本文件定義 **遊樂園團體預約 LINE 官方帳號智慧自動化系統 (LINE OA Reservation Bot)** 之完整系統架構、外部雲端服務設定、異機/換機接續開發 SOP、資安防護規範、重要踩坑防護與後續待辦清單。

---

## 一、 系統正式線上入口與資源清單 (Endpoints & Resources)

| 資源項目 | 位置 / 連結 | 說明 |
| :--- | :--- | :--- |
| **GitHub 儲存庫** | `https://github.com/lintoro/park-booking-bot.git` (主分支: `main`) | 雲端程式碼主庫，推送到 `main` 會自動觸發 Render 部署 |
| **線上生產環境** | `https://park-booking-bot.onrender.com` | Render 雲端 Web Service (Python 3.11.9) |
| **LINE Developers** | 👉 [LINE Developers Console](https://developers.line.biz/console/) | Webhook URL 指向 `https://park-booking-bot.onrender.com/webhook` |
| **Google Cloud Console** | 👉 [Google Cloud Console](https://console.cloud.google.com/) | 服務帳戶憑證與 Google Sheets API 啟用管理 |
| **Google 雲端試算表 (SSOT)** | 請查閱 `.env` 之 `GOOGLE_SPREADSHEET_ID` | 包含 `預約記錄表_Log`、`檔期總量控管_Dashboard`、`顧客檔案與業務歸屬_CRM` |
| **Google AI Studio (Gemini)** | 👉 [Google AI Studio](https://aistudio.google.com/) | 申請與管理現役 `gemini-3.6-flash` 之 API 金鑰 |

---

## 二、 異機 / 換機接續開發快速啟動指南 (New Machine Setup SOP)

若在另一台電腦、工作站或筆電接續開發本專案，請嚴格依照以下 6 步驟進行環境配置：

### Step 1：Clone 專案原始碼
```bash
git clone https://github.com/lintoro/park-booking-bot.git
cd park-booking-bot
```

### Step 2：建立 Python 虛擬環境並安裝套件
建議使用 Python 3.10 ~ 3.11 版本：
```bash
# 建立虛擬環境
python -m venv venv

# 啟動虛擬環境 (Windows PowerShell)
.\venv\Scripts\Activate.ps1
# (若遇執行原則限制，請先執行: Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process)

# macOS / Linux 啟動方式:
# source venv/bin/activate

# 升級 pip 並安裝相依套件
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 3：配置環境變數與金鑰檔
1. 複製環境變數範本：
   ```bash
   cp .env.example .env
   ```
2. 編輯本機 `.env`，填入以下必要設定：
   ```ini
   PORT=8000
   LINE_CHANNEL_SECRET=你的_LINE_CHANNEL_SECRET
   LINE_CHANNEL_ACCESS_TOKEN=你的_LINE_CHANNEL_ACCESS_TOKEN
   GEMINI_API_KEY=你的_GEMINI_API_KEY
   GEMINI_MODEL=gemini-3.6-flash
   GOOGLE_SPREADSHEET_ID=你的_GOOGLE_SPREADSHEET_ID
   # 本機可使用憑證檔案路徑，或直接填入 JSON 字串 (GOOGLE_SERVICE_ACCOUNT_JSON)
   GOOGLE_CREDENTIALS_FILE=credentials.json
   ```
3. 若本機需讀寫線上 Google 試算表：
   * 將 GCP 服務帳戶金鑰放置於根目錄命名為 `credentials.json`。
   * **資安檢查**：確認 `.gitignore` 包含 `.env` 與 `credentials.json`，嚴禁推送到公開儲存庫。

### Step 4：執行單元測試驗證環境
換機後第一時間執行全套自動化測試，確保環境與核心邏輯完全無損：
```bash
pytest -v
```
預期結果：**所有單元測試應 100% 全部通過（PASS）**。

### Step 5：啟動本機開發伺服器（雙軌運行模式）
* **模式 A（本地獨立開發 / 離線模擬）**：
  直接啟動 Uvicorn，即便沒有設定 Google 憑證，系統亦會自動降級至本地記憶體模擬庫（`_MOCK_LOG_DB`），保證不報錯崩潰。
  ```bash
  uvicorn app.main:app --reload --port 8000
  ```
* **模式 B（本地端接管 LINE Webhook 調試）**：
  搭配 `ngrok` 開啟本機通道：
  ```bash
  ngrok http 8000
  ```
  將臨時網址（如 `https://xxxx.ngrok-free.app/webhook`）填入 LINE Developers 後台進行即時除錯。調試結束後記得將 LINE Webhook 改回線上 Render 網址：`https://park-booking-bot.onrender.com/webhook`。

---

## 三、 本日（v1.2.0）已交付之重大功能與成果彙整

1. **雲端接管與安全瘦身 (Cloud Takeover & Security)**：
   * 專案瘦身、清除暫存二進制檔案，建立 `render.yaml`、`Procfile`、`runtime.txt` (Python 3.11.9)。
   * 正式接管線上部署至 Render (`https://park-booking-bot.onrender.com`)，關閉本地長駐伺服器以節省資源。
   * 兼容雙環境變數別名：`GOOGLE_SERVICE_ACCOUNT_JSON` 與 `GOOGLE_CREDENTIALS_JSON`。
2. **AI 客服三層資安防禦體系 (Gemini AI Security & Robustness)**：
   * 前置正則過濾層：防越獄（Jailbreak/Prompt Injection）、防系統提示詞竊取、防程式碼與系統命令攻擊、非遊樂園領域邊界約束。
   * 模型換代升級：淘汰 Google 已退役下線之 1.5/2.0 模型，全面無縫升級為現役官方指定之 `gemini-3.6-flash` / `gemini-3.5-flash`。
   * 伺服器尖峰 503 自動退避重試（Backoff Retry）機制，確保高可用性。
3. **聯絡人寬容解析升級**：
   * 窗口電話全面支援台灣手機（`09XX`）與全台各縣市家機/市內電話（`02~08`），並支援分機格式解析（`#123`、`分機888`、`轉123`）。
4. **預約時段按鈕穩定性修復**：
   * 嚴格限制預約啟動詞僅在 `session.current_step == 0` 有效，修復顧客點擊時段 Flex 卡片誤觸重置回到 Step 1 的重大體驗 Bug。
5. **預約即時查詢功能 (Query Reservation)**：
   * 支援自然語言與關鍵字（「查詢預約」、「我的預約」、「預約紀錄」、「所以這樣就預約成功了嘛」等）。
   * 即時自後台試算表抓取該用戶訂單，透過結構化 Flex Message（單筆或 Carousel 輪播）展示單號、梯次、人數、金額與狀態。
6. **線上取消預約與名額即時釋出 (Cancel Booking & Release Capacity)**：
   * 查詢卡片附帶「❌ 取消此筆預約」按鈕，本人點選後更新試算表到場狀態為「取消」、案件狀態為「已取消(客戶線上取消)」。
   * **連動更新 `檔期總量控管_Dashboard`**，扣減該梯次累計人數，即時釋放入園名額，附帶 `max(0, ...)` 負數防禦。
7. **同日重複預約防呆與追加第二團流轉 (Duplicate & Collision Prevention)**：
   * 同日同電話或相近團名（LCS 最長公共子字串比對）在 Step 4 選擇時段後主動防呆攔截。
   * 提供「👉 確認追加第二團」（標記 `allow_duplicate = True` 推進人數填寫）、「📋 查詢既有預約」與「❌ 取消預約」友善流轉。
8. **GRM 顧客關係管理三表聯動 (Sheets Architecture)**：
   * `預約記錄表_Log`（30 欄）：完整掌握訂金入帳日與末五碼、到場狀態、實到人數落差、尾款、發票開立與結案追蹤。
   * `檔期總量控管_Dashboard`（5 欄）：日/上下午梯次即時人數監控與超載警示。
   * `顧客檔案與業務歸屬_CRM`（15 欄）：顧客消費歷程、忠誠評級與業務專員歸戶。

---

## 四、 核心架構與檔案目錄一覽

```
LineBot_test/
├── .agents/rules/               # AI 協同開發業務規範
├── .gemini/rules/               # IDE 專屬規範
├── app/                         # 應用程式核心代碼
│   ├── __init__.py              # 版本號宣告 (v1.2.0)
│   ├── main.py                  # FastAPI 主程式入口、Webhook 路由與非同步排程
│   ├── config.py                # 環境變數與雙別名載入
│   ├── core/                    # 領域核心業務 (與框架完全解耦)
│   │   ├── models.py            # BookingData (含 allow_duplicate) 與 UserSession
│   │   ├── pricing.py           # 票價試算、滿20人門檻、隨隊司領免票計算
│   │   ├── capacity_gate.py     # 1000/400/600 人數總量、17:00 截止、急單閘門
│   │   ├── state_machine.py     # 8 步驟對話狀態機、單獨修改、查詢/取消/重複防呆
│   │   └── relaxed_parsers.py   # 寬容自然語言解析 (日期、時間、人數、車數、電話)
│   ├── templates/               # Flex Message 視覺渲染器
│   │   ├── template_renderer.py # 預約確認卡、時段卡、人數卡、預約詳情卡等
│   │   └── *.json               # 原始 JSON 視覺範本
│   ├── data/                    # 園區內部知識庫 (Markdown)
│   └── services/                # 外部服務整合
│       ├── line_service.py      # LINE Messaging API SDK 封裝
│       ├── sheets_service.py    # Google Sheets 三表聯動、查詢、取消與重複檢核
│       └── faq_service.py       # Gemini 3.6 Flash 三層資安防禦與客服問答
├── tests/                       # 自動化單元測試庫
│   ├── test_pricing.py          # 計費與門檻測試
│   ├── test_capacity_gate.py    # 容量與急單時間測試
│   └── test_state_machine.py    # 狀態機、查詢、取消、防呆、家機完整測試 (13 項)
├── render.yaml                  # Render Infrastructure as Code 配置
├── Procfile                     # Web 服務啟動命令
├── runtime.txt                  # Python 執行環境版本 (python-3.11.9)
├── requirements.txt             # 專案套件依賴表
├── .env.example                 # 環境變數範本
├── .gitignore                   # 機密與暫存過濾配置
├── PROGRESS.md                  # 開發進度與歷程日誌
├── ISSUES_LOG.md                # 踩坑與錯誤修復記錄
├── PROJECT_HANDOVER.md          # 換機交接手冊 (本檔案)
└── README.md                    # 專案總覽
```

---

## 五、 接手後的後續優化建議清單 (Next Steps)

若日後需要進一步擴充本系統，建議優先考慮以下功能：
1. **業務人員推播通知 (Staff Notification)**：
   * 當顧客送出預約或線上取消預約時，除了寫入試算表外，亦可透過 LINE Notify 或 LINE Bot 推播給業務主管群組。
2. **LINE Rich Menu (圖文選單) 整合**：
   * 將「👉 我要預約」、「📋 預約查詢」、「💰 票價試算」、「📞 專人客服」做成底部常駐圖文選單，進一步提升直覺性。
3. **金流支付串接 (Payment Gateway)**：
   * 目前訂金採用匯款與業務核帳方式（記錄末五碼）。日後若有線上刷卡需求，可串接 LINE Pay 或綠界金流。
