# 遊樂園團體預約 LINE 官方帳號智慧自動化系統 (LINE OA Reservation Bot)

專為遊樂園團體預約打造之全自動化 LINE 官方帳號對話系統。整合 **Google Gemini 3.6 Flash 最新多模態 AI 知識問答**、**容量防超賣管制**、**多票種與隨隊免票試算**、**無損微調確認卡片**、以及 **Google 試算表 GRM 團體顧客關係管理 (三表聯動)**。

---

## 🌟 核心特色功能

1. **AI 園區智慧問答 (Gemini 3.6 Flash)**：
   - 內建園區百寶箱知識庫（營業時間、設施介紹、團體導覽時間、餐飲菜單、雨天備案）。
   - 自然語言對話，若在預約流程中提問（如「你們有便當嗎」）會智慧解答而不打斷預約上下文。
2. **無損微調與全域中斷防呆**：
   - 預約核對卡片支援單項獨立修改（改團名、改電話、改日期、改時段、改人數、改車數、改統編），修改後即時重繪確認卡，不誤清空資料。
   - 支援「我不想預約了」、「取消預約」等中斷防呆指令。
3. **容量管制與防超賣安全閘門**：
   - 全日上限 1,000 人、上午場 (10:00~13:00) 上限 400 人、下午場 (13:00~17:00) 上限 600 人。
   - 每日 17:00 後團體截止入場；當日急單動態梯次限制。
4. **GRM 顧客關係管理與試算表三表聯動**：
   - `預約記錄表_Log`（30 欄）：完整追蹤訂金入帳日與末五碼、到場狀態 (Show / No-Show)、實到人數落差、尾款、發票開立與結案狀態。
   - `檔期總量控管_Dashboard`（5 欄）：上下午梯次累計人數即時容量監控與警示。
   - `顧客檔案與業務歸屬_CRM`（15 欄）：依顧客 `LINE_User_ID` 歸戶，記錄負責業務員、顧客評級、累計預約/成單/到場/爽約次數與總消費金額。

---

## 🚀 部署至 Render.com 雲端平台

本專案已配置完整的 Render 雲端部署支援檔案 (`render.yaml`, `Procfile`, `runtime.txt`)。

### 步驟 1：推送到 GitHub
將專案推送到您的 GitHub 儲存庫：
```bash
git push origin main
```

### 步驟 2：在 Render 建立 Web Service
1. 登入 [Render.com](https://render.com/)，點選 **New +** ➔ **Web Service**（或 Blueprint）。
2. 連接您的 GitHub 專案儲存庫。
3. 部署設定：
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Plan**: `Free`

### 步驟 3：設定 Render 環境變數 (Environment Variables)
在 Render 後台的 **Environment** 頁籤中新增以下環境變數：

| 變數名稱 | 必填 | 說明 |
| :--- | :---: | :--- |
| `LINE_CHANNEL_SECRET` | 是 | LINE Developers Console 取得之 Channel Secret |
| `LINE_CHANNEL_ACCESS_TOKEN` | 是 | LINE Developers Console 取得之長期 Channel Access Token |
| `GEMINI_API_KEY` | 是 | Google AI Studio 取得之 Gemini API Key |
| `GEMINI_MODEL` | 否 | 預設 `gemini-3.6-flash` |
| `GOOGLE_SPREADSHEET_ID` | 是 | Google 試算表網址中的試算表 ID |
| `GOOGLE_CREDENTIALS_JSON` | 是 | 將 GCP 服務帳戶 `service_account.json` 的**完整 JSON 內容**直接複製貼入 |
| `TIMEZONE` | 否 | 預設 `Asia/Taipei` |

### 步驟 4：設定 LINE Webhook URL
Render 部署完成後，複製您的服務網址（例如 `https://linebot-group-reservation.onrender.com`）：
1. 前往 **LINE Developers Console** ➔ 選擇您的 Channel ➔ **Messaging API**。
2. 將 **Webhook URL** 設定為：
   ```
   https://<你的-render-網址>.onrender.com/webhook
   ```
3. 開啟 **Use webhook** 開關。
4. 點選 **Verify** 測試，確認回傳成功！

---

## 💻 本地端開發與測試

```bash
# 1. 建立虛擬環境並啟動
python -m venv venv
.\venv\Scripts\activate   # Windows

# 2. 安裝相依套件
pip install -r requirements.txt

# 3. 複製環境變數範例並設定
copy .env.example .env

# 4. 啟動伺服器
uvicorn app.main:app --reload --port 8000

# 5. 執行單元測試
pytest tests/
```

---

## 🔒 資安防護準則
- **金鑰嚴禁入庫**：`.env`、`credentials.json` 與所有密鑰均已被 `.gitignore` 嚴格排除。
- **雲端變數注入**：在 Render 上直接使用 `GOOGLE_CREDENTIALS_JSON` 與 `GEMINI_API_KEY` 環境變數注入，無須在伺服器上保存靜態金鑰檔案。
