# 專案交接手冊與換機作業指南 (PROJECT_HANDOVER.md)

本文件定義 **遊樂園團體預約 LINE 官方帳號智慧自動化系統 (LINE OA Reservation Bot)** 之系統架構、外部服務設定、換機/異地接續開發 SOP、資安防護規範與踩坑防護。

---

## 一、 系統正式線上入口與資源清單 (Endpoints & Resources)

* **專案工作目錄**：`C:\Github\ReactApp\LineBot_test`
* **LINE Developers Console**：👉 [https://developers.line.biz/console/](https://developers.line.biz/console/)
* **Google 雲端試算表資料庫 (SSOT)**：請參閱您的 Google 試算表或本機 `.env` 的 `GOOGLE_SPREADSHEET_ID` 設定
* **Google Cloud Console (服務帳戶與 API)**：👉 [https://console.cloud.google.com/](https://console.cloud.google.com/)
* **GitHub 程式碼儲存庫**：（待建立與綁定 remote）

---

## 二、 異地換機接續開發快速啟動指南 (Off-site / New Machine Setup SOP)

若在另一台電腦、工作站或筆電接續開發本專案，請嚴格依照以下 5 步驟進行環境配置：

### Step 1：取得專案原始碼
```bash
git clone <你的-GitHub-Repo-URL>
cd LineBot_test
```

### Step 2：建立 Python 虛擬環境並安裝相依套件
確保該機器已安裝 Python 3.10 以上版本：
```bash
# 建立虛擬環境
python -m venv venv

# 啟動虛擬環境 (Windows PowerShell)
.\venv\Scripts\Activate.ps1
# (若遇權限問題可先執行: Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process)

# 安裝相依套件
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 3：配置環境變數與金鑰檔
1. 複製環境變數範本：
   ```bash
   cp .env.example .env
   ```
2. 編輯 `.env` 填入必要金鑰：
   * `LINE_CHANNEL_SECRET`：自 LINE Developers Console 的 Basic Settings 複製。
   * `LINE_CHANNEL_ACCESS_TOKEN`：自 LINE Developers Console 的 Messaging API 頁面核發複製。
   * `PORT`：預設 `8000`。
   * `GOOGLE_SPREADSHEET_ID`：Google 試算表 ID。
3. 若已設定 Google 試算表串接：
   * 將 Google Cloud 服務帳戶金鑰下載命名為 `credentials.json` 並放置於專案根目錄。
   * **注意**：確認 `.gitignore` 內已有 `credentials.json` 與 `.env`，**切勿上推至 Git**！

### Step 4：啟動本地伺服器與建立測試通道
本機開發需透過 `ngrok` 提供公開 HTTPS 網址給 LINE 伺服器驗證：
```bash
# 終端機視窗 1：啟動 FastAPI 後端服務
uvicorn app.main:app --reload --port 8000

# 終端機視窗 2：啟動 ngrok 通道
ngrok http 8000
```

### Step 5：更新 LINE Webhook URL 並點選驗證
1. 複製 ngrok 產生的 HTTPS 網址（例如：`https://xxxx-xx-xx.ngrok-free.app`）。
2. 在 LINE Developers Console 的 Messaging API 標籤中：
   * 將 Webhook URL 設定為：`https://xxxx-xx-xx.ngrok-free.app/webhook`。
   * 點選 **Verify**，確認回應為 `Success`（HTTP 200）。
   * 開啟 **Use webhook** 開關。

---

## 三、 專案架構與目錄規範 (Architecture Standards)

為確保專案程式碼結構清晰，且具備**日後可低成本 1:1 遷移至 Node.js** 的彈性，架構採用解耦模組化設計：

```
LineBot_test/
├── .agents/rules/               # AI 代理人開發規範
│   ├── project_rules.md         # 專案業務與防呆規範
│   ├── strict_security_policy.md# 嚴格資安守則
│   └── traditional_chinese_policy.md # 繁體中文政策
├── .gemini/rules/               # Antigravity IDE 專用規則
│   └── project_rules.md
├── docs/                        # 專案文件庫
│   └── PROJECT_CONVERSATION_HISTORY.md # 對話與決策歷程
├── app/                         # 後端應用主程式
│   ├── __init__.py
│   ├── main.py                  # FastAPI 主程式入口與 Webhook 端點
│   ├── config.py                # 環境變數與常數載入
│   ├── core/                    # 業務防呆與計費邏輯 (與框架解耦)
│   │   ├── __init__.py
│   │   ├── pricing.py           # 票價、免票、10%訂金試算
│   │   ├── capacity_gate.py     # 1000人/400人/600人與急單時間閘門驗證
│   │   └── state_machine.py     # 8 步驟對話狀態機 (含15分鐘逾時)
│   ├── templates/               # LINE 視覺元件 JSON 模板 (語言無關)
│   │   ├── confirmation_card.json # 預約核對確認卡
│   │   ├── time_slot_card.json    # 梯次選擇卡
│   │   └── contact_card.json      # 真人客服專人名片
│   ├── data/                    # 園區專屬知識庫
│   │   └── park_knowledge.md      # 設施身高、導覽時間、素食、交通停車、常見 FAQ
│   └── services/                # 外部服務串接
│       ├── __init__.py
│       ├── line_service.py      # LINE SDK 封裝 (回覆、推播)
│       ├── sheets_service.py    # Google Sheets 資料庫操作 (雙工作表)
│       └── faq_service.py       # Gemini 2.5 Flash 智能客服 (含本地 Markdown 備援降級)
├── 參考資料勿上傳/              # 本地內部資料 (嚴格禁止 Git 追蹤)
├── .env.example                 # 環境變數範本
├── .gitignore                   # Git 排除清單
├── requirements.txt             # Python 相依套件
├── README.md                    # 專案總覽
├── PROGRESS.md                  # 開發進度追蹤
├── ISSUES_LOG.md                # 問題修復日誌
└── PROJECT_HANDOVER.md          # 換機與交接手冊 (本檔案)
```

---

## 四、 嚴格資安與串接服務防護原則 (Security SOP)

1. **機密資料零外洩防線**：
   * `/參考資料勿上傳/` 目錄嚴禁加入 Git。
   * `.env`、`credentials.json`、`*.key`、`*.pem` 等金鑰憑證嚴禁上傳。
   * 上傳或換機推送前，執行 `git status` 再次檢查是否有敏感檔案被 staging。
2. **LINE Webhook 防偽簽章驗證**：
   * 伺服器端收到 `/webhook` 請求時，必須先取得 Request Header `X-Line-Signature`。
   * 透過 LINE 官方 SDK 或 HMAC-SHA256 結合 `LINE_CHANNEL_SECRET` 驗證簽章，非 LINE 官方合法請求一律回傳 400 阻斷。
3. **個資最小化保護**：
   * 對話中僅登錄「單位名稱」、「聯絡人」、「手機」與「人數/車數」。
   * 團員保險名冊等高機密資料不透過聊天室收集，由業務後續以加密管道交付。
4. **Google Service Account 權限最小化**：
   * 建立專用的服務帳戶，僅將該服務帳戶的 Email（如 `xxx@project.iam.gserviceaccount.com`）共用給專屬的預約 Google 試算表（給予「編輯者」權限），不給予全雲端權限。

---

## 五、 關鍵業務防呆規範與踩坑防護 (Critical Gotchas)

1. **LINE Webhook 必須於 1 秒內回傳 HTTP 200**：
   * LINE 伺服器對 Webhook 有嚴格的逾時要求（通常為 1~2 秒內）。若後端在 Webhook callback 中直接進行耗時的 Google Sheets API 呼叫，可能導致 LINE 判斷超時而反覆重發相同的 Webhook。
   * **解法**：FastAPI 中採用 `BackgroundTasks` 進行非同步寫入試算表與推播，先立即回傳 200 OK 給 LINE。
2. **LINE 後台「自動回應」與「Webhook」衝突**：
   * 若 LINE Official Account Manager 的「自動回應訊息」未關閉，當客人傳訊時，LINE 會同時發送系統預設回覆和我們機器人的回覆，造成「雙重回答」。
   * **解法**：必須在 LINE 官方後台關閉「自動回應訊息」，並開啟「Webhook」。
3. **當日急單時間防呆判定**：
   * 伺服器判斷時間必須強制指定台北時區（`Asia/Taipei`），避免雲端主機預設為 UTC 時區導致當日急單判斷失準 8 小時。
4. **17:00 團體入場硬性截止**：
   * 園區平日 18:00 閉園、假日 19:00 閉園，所有團體預約最後梯次為 17:00，17:00 以後一律不開放預約。
5. **遊覽車免票計算**：
   * 每 1 台遊覽車享 2 位免票（1 司機 + 1 領隊）。
   * 總入場人數 = 全票人數 + 半票人數 + 幼童免票人數 + (遊覽車數 $\times$ 2)。
   * 計費總金額 = (全票人數 $\times$ 280) + (半票人數 $\times$ 140)。
6. **Gemini AI 智能客服高可用防護**：
   * 使用 Google 最新 SDK `google-genai` 與高效節省模型 `gemini-2.5-flash`。
   * 實作本地 Markdown 知識庫（`app/data/park_knowledge.md`）關鍵字備援降級機制，未設定 `GEMINI_API_KEY` 時亦能 100% 穩定秒回，不報錯不卡死。

---

## 六、 本地測試指令 (Testing SOP)
```bash
# 啟動虛擬環境後執行全部單元測試 (含防呆、計費、試算表、Flex 卡片與 FAQ 服務)
pytest -v
```

---

## 七、 對話交接狀態與接續待辦重點 (Handover Checkpoints)

### 1. 最新進度與資產現狀（截至 2026-09-24 12:45）
* **Phase 1（LINE 串接）**：✅ 100% 已開通（Channel Secret、長期 Token 均已填入 `.env`，Webhook Verify 通過，手機傳訊 Echo 成功）。
* **Phase 2（對話狀態機）**：✅ 已完成（8 步驟狀態管理、15分鐘逾時重置、真人轉接名片）。
* **Phase 3（防呆計費）**：✅ 已完成（20人門檻、17:00截止、當日急單管制、隨隊免票、10%訂金）。
* **Phase 4（視覺卡片）**：✅ 已完成（3 大 Flex Message 模板與渲染器）。
* **Phase 5（Google 試算表資料庫）**：✅ 已完成（試算表已上線，雙工作表已自動建立，讀寫即時連動）。
* **Phase 6（園區 FAQ 知識庫與 Gemini AI）**：✅ 已完成（設施、導覽、素食、交通問答知識庫，Gemini 2.5 Flash + 本地降級備援）。
* **單元測試全數覆蓋**：`pytest -v` **38 項單元測試 100% PASS**。

### 2. 接手對話的第一步操作指示
新對話啟動時，只需執行以下動作：
1. 讀取 `PROJECT_HANDOVER.md`、`PROGRESS.md`、`ISSUES_LOG.md`。
2. 啟動 `uvicorn app.main:app --reload --port 8000` 與 `ngrok http 8000` 進行手機端端到端實測或準備雲端部署。



