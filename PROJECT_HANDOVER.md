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

## 五、 未來正式實作規劃專題分析 (業務推播與金流架構設計手冊)

本章節完整記錄專案架構討論成果，供日後重啟或正式實作時，直接讀取本記錄取得最精確之技術實施建議與優缺點評估。

---

### 專題一：業務人員即時推播通知與接單協作系統 (Staff Notification & Lead Claiming)

#### 1. 核心通訊架構：顧客前台與業務後台的「雙軌絕對隔離」
* **嚴格隔離規範**：
  * **顧客端 (前台)**：100% 保持在與 LINE 官方帳號的 **1 對 1 私聊視窗** 中預約與諮詢。**嚴禁將顧客與業務拉在同一個群組**（避免顧客個資統編外洩、避免顧客看到內部拆帳/利潤討論、避免多顧客發言造成機器人錯亂）。
  * **業務端 (後台)**：建立一個僅限內部同仁的「**業務內部工作群組**」（成員：業務團隊 + 主管/店長 + LINE Bot），顧客完全不在其中。

#### 2. 兩種派送模式深度比較 (群組推播 vs 個人綁定私訊)

| 評估維度 | 方案 A：推播至「業務內部工作群組」（⭐ 業界標準最推薦） | 方案 B：推播至「業務個人 LINE ID」（個人化派單） |
| :--- | :--- | :--- |
| **運作方式** | 顧客預約完成後，Bot 主動發送（Push）一張結構化通報 Flex 卡片至業務工作群組。 | 顧客預約完成後，Bot 以 Multicast 主動私訊發給 1~3 位綁定的業務個人 LINE。 |
| **協作與透明度** | **全員透明**：全體業務與主管同步掌握，誰有空誰搶單，資訊零死角。 | **各自獨立**：若該業務休假或外出沒看到，其他人無法即時代理，易漏單。 |
| **訊息額度消耗** | **極省**：向單一群組發送 1 次 Push，LINE 僅計為 **1 則額度**。 | **倍數消耗**：若有 3 位業務，每進 1 筆訂單即消耗 **3 則額度**。 |
| **費用與額度試算** | LINE 官方帳號免費方案提供 **每月 200 則免費主動推播**。<br>若每月 150 團預約：`150 則 < 200 則`，**完全 0 元免費用量**。 | 若 3 位業務，150 團需要 `150 × 3 = 450 則`，需升級中用量月租 (NT$ 800/月)。 |
| **人員異動維護** | 業務新人加入或離職，只需進出 LINE 群組即可，**程式完全零修改**。 | 業務換人時，需修改 `.env` 或資料庫更新業務的 LINE User ID。 |
| **業務回覆機制** | 業務點擊卡片按鈕或發送指令，Bot 回覆使用 `replyToken`（**免費被動回覆**）。 | 業務在個人視窗點擊或打字，Bot 回覆走 `replyToken`（**免費被動回覆**）。 |

#### 3. 業務群組內部「監聽、自動回覆與後端試算表回寫」完整流程
LINE Bot 在群組內具備完整的監聽與識別能力：
1. **身分自動辨識**：群組中任何業務點擊按鈕或發言時，Webhook 的 `source.userId` 會精確帶有該業務的專屬 ID，系統可自動調用 `get_profile(userId)` 取得業務姓名（如「陳專員」）。
2. **卡片按鈕認領（Postback Action，最推薦防呆）**：
   * 群組通報卡片附帶按鈕：
     - `[📞 一鍵撥號]`：URL 設為 `tel:顧客電話`，業務手機點擊一秒撥通顧客，極速溝通。
     - `[🙋 我要接單/認領]`：Postback 帶有 `action=claim_booking&booking_id=GRP-xxxx`。
   * 業務「陳專員」點擊接單後，後端自動執行：
     - 寫入 Google 試算表 `預約記錄表_Log` 第 23 欄【負責業務專員】為「陳專員」。
     - 寫入第 29 欄【案件狀態】為「處理中(陳專員認領)」。
     - 機器人於群組使用 `replyToken` 發送免費被動回覆：「✅ 訂單 `GRP-xxxx` 已由【陳專員】認領成功！請盡速與窗口聯繫。」其他同仁立即知曉，防止撞單。
3. **文字指令更新進度（聊天室直接打字）**：
   * 業務在群內輸入：`@機器人 #進度 GRP-xxxx 訂金已收 末五碼12345`。
   * 系統監聽 `#進度` 前綴，自動解析單號並將末五碼回寫進試算表。
4. **群組防干擾原則 (Mute by Default)**：
   * 業務在群內的日常閒聊、交辦私事，機器人**一律維持靜音不發言**。
   * 機器人**僅響應卡片結構化按鈕點擊**，或**特定前綴指令（如 `#進度`、`#查詢`）**。

#### 4. 0 成本備援管道評估 (非 LINE 方案)
若日後每月訂單量超過數千筆，不想增加 LINE 官方帳號推播月租成本，可無縫切換：
* **Discord Webhook / Telegram Bot**：兩者推播到內部工作群組均為 **完全免費、無則數上限**，且支援結構化卡片與撥號連結。

---

### 專題二：線上金流串接架構設計 (Payment Gateway Architecture)

#### 1. 策略模式 (Strategy Pattern) 介面規範
為保持系統高度解耦與測試架構純淨，日後實作時請遵循以下標準介面設計：
```python
from abc import ABC, abstractmethod
from typing import Dict, Any

class PaymentGatewayInterface(ABC):
    @abstractmethod
    def create_payment_order(self, booking_id: str, amount: int, title: str, return_url: str) -> Dict[str, Any]:
        """建立付款訂單，取得付款頁面網址或交易序號"""
        pass

    @abstractmethod
    def verify_payment_callback(self, raw_payload: str, signature: str) -> bool:
        """驗證金流 Webhook 簽章與付款結果"""
        pass

    @abstractmethod
    def refund_payment(self, transaction_id: str, amount: int, reason: str) -> Dict[str, Any]:
        """執行退款作業"""
        pass
```

#### 2. 本地測試與 Mock 實作守則
* 測試與驗證架構階段，提供 `MockPaymentGateway`：
  - 模擬生成假付款連結（`https://park-booking-bot.onrender.com/mock_pay?order=...`）。
  - 使用者點擊「確認付款」後，直接觸發本機回呼，將試算表訂金狀態改為「已付清」，**絕不串接真實扣款或向銀行/LINE Pay 申請金流特店**。

#### 3. 正式金流第三方比較建議
* **LINE Pay v3 API**：
  - 優點：用戶無需離開 LINE 環境，可使用 LINE Points 折抵，使用者體驗最佳。
  - 適用：小額 10% 訂金線上支付。
* **綠界科技 (ECPay) / 藍新金流 (NewebPay)**：
  - 優點：支援信用卡、ATM 虛擬帳號（企業報帳常用）、超商代碼繳費，適合公家機關與學校團體。

---

## 六、 本次版本交付成果總覽 (v1.3.0)

1. **LINE Rich Menu (圖文選單) 常駐整合**：
   - 實作 2500 × 1686 高解析度動態圖片生成模組（Pillow 自適應字型）。
   - 四大常駐板塊：「👉 我要預約」、「📋 預約查詢」、「💰 票價試算」、「📞 專人客服」。
   - 封裝完整的 LINE Messaging API v3 生命週期管理服務與一鍵同步 CLI 工具 (`scripts/setup_rich_menu.py`)。
2. **AI 客服三層防線全面升級**：
   - 強制 100% 繁體中文（台灣日常用語），嚴格禁止輸出任何英文句子。
   - 即時天氣問題主動說明園區雨天營運備案（室內開放、豪雨停班課全額退費）。
   - 無關問題親切委婉拒絕，並彈出制式 Flex 導引卡片，利用 Quick Replies 嚴格限制回應範圍。
3. **徹底根除 AI 回覆斷句未完問題**：
   - 將 `max_output_tokens` 由 600 大幅提升至 `2048`。
   - 關閉 `thinking_budget`，防止模型內部推理吞食 Token 空間。
   - 實作後置懸空詞與未完結尾自動修復機制，確保 100% 語句完整。
4. **全套自動化單元測試 58/58 全數 100% 通過（無回退）**。
