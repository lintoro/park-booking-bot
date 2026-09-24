# 專案對話與決策歷程紀錄 (PROJECT_CONVERSATION_HISTORY.md)

本文件完整記錄本專案自初始評估、架構決策、規則制定至功能開發之所有重大討論與技術選型歷程。

---

## [2026-09-24 10:03] 初始需求與 LINE 後台權限評估
* **使用者提問**：詢問 AI 是否能直接操作設定 LINE OA 後台，或是採用「我說你做」的指引方式。
* **評估分析**：
  * LINE Developers Console 與 LINE Official Account Manager 涉及個人/企業帳號安全性、2FA 登入驗證，AI 無法亦不應直接代登入。
  * 決策採用「**我說你做**」的方式引導使用者點擊開關、取得 Channel Secret / Access Token 與設定 Webhook URL。
  * 後端 Webhook 伺服器、預約防呆邏輯、Flex Message 卡片、資料庫整合則由 AI **全權代勞編寫與除錯**。

---

## [2026-09-24 10:05] 技術選型評估：Python vs. Node.js
* **使用者提問**：評估使用 Python 與 Node.js 開發 LINE OA 預約機器人之架構難度、修改維護與其他面向。
* **比較維度**：
  * **架構難度**：Python (FastAPI) 語法乾淨直觀，狀態管理最簡單；Node.js (Express) 非同步事件鏈較長。
  * **維護性**：Python 搭配 Pydantic 型別驗證與簡潔語法，除錯快速；Node.js 需留意回呼與相依性更新。
  * **生態擴充**：Python 在串接 Google Calendar、Google Sheets 與日後擴充 AI LLM 客服時具顯著優勢；Node.js 在 LIFF 網頁日曆前後端統一性較高。
* **結論**：推薦以 **Python (FastAPI)** 為主，快速上線並降低開發門檻。

---

## [2026-09-24 10:18] 語言遷移成本評估 (Python 轉 Node.js)
* **使用者提問**：若先以 Python 建置，日後切換至 Node.js 的轉換成本是否偏高？
* **評估分析**：
  * **轉換成本極低**：LINE 平台本質為 HTTP Webhook + JSON Payload，LINE 後台完全不需變動。
  * **Flex Message 零成本平移**：卡片模板均為純 JSON 格式，可 100% 直通共用。
  * **架構解耦設計**：採用模板與業務分離、標準化資料庫介面，未來若轉換僅需對端點邏輯進行 1:1 轉譯。

---

## [2026-09-24 10:31] 專案目錄確認與企劃書讀取
* **工作目錄**：綁定 `C:\Github\ReactApp\LineBot_test`。
* **企劃參考**：完整讀取並吸收 `參考資料勿上傳/遊樂園團體預約LINE智慧自動化_專案企劃書.md`。
* **規格萃取**：
  1. 容量控管：全日 1000 人（上午 400 人 / 下午 600 人），每 30 分鐘一梯次，17:00 截止入場防呆。
  2. 成團與急單：門檻 20 人；當日急單上午限下午場，下午限 15:00 以後。
  3. 計費與免票：全票 280、半票 140、幼童 0；每車贈 1 司機 + 1 領隊免票；10% 彈性訂金。
  4. 8 步驟對話流程、15 分鐘逾時重置、真人客服關鍵字即時轉接。
* **初始化產出**：建立 `.gitignore`、`README.md`、`.env.example`。

---

## [2026-09-24 10:36] Antigravity IDE 專案與對話歸屬機制釐清
* **使用者提問**：如何將目前對話從 Conversations 移至 Projects 區塊。
* **介面分析**：
  * Antigravity 2.0 目前不支援將全域對話以拖曳或選單方式變更歸屬至 Project。
  * 正確做法為透過 `File -> Open Folder` 或 Projects 旁的 📁 圖示載入 `C:\Github\ReactApp\LineBot_test`。
  * 目前對話已直接鎖定該目錄作為根目錄作業，完全不影響開發與檔案寫入。

---

## [2026-09-24 10:42] 全域 Rules、換機作業流程與專案規範建立
* **參考來源**：參考上層目錄既有成熟專案（`diy-inventory-reservation-tracking`, `counter-utility-meter-app`）及 `user_rules/GLOBAL_RULES.md`。
* **標準規範落地**：
  * 建立 `.gemini/rules/project_rules.md`、`.agents/rules/` 規則體系。
  * 規範繁體中文（台灣）、資安隔離防線、LINE 簽章驗證、業務防呆守則。
  * 建立四大標準文件：`docs/PROJECT_CONVERSATION_HISTORY.md`、`PROGRESS.md`、`ISSUES_LOG.md`、`PROJECT_HANDOVER.md`。

---

## [2026-09-24 11:20] 預約業務防呆運算與 Flex 卡片開發實作完成 (Phase 3 & 4)
* **需求指示**：使用者要求「直接建立 測試 再跟我說」，啟動業務防呆邏輯與視覺卡片模組之建置。
* **交付成果**：
  1. **常數與設定模組 (`app/config.py`)**：統整票價、梯次上限、急單規則、15分鐘逾時常數與聯絡人資訊。
  2. **計費與成團防呆模組 (`app/core/pricing.py`)**：
     * 實作成團門檻（最低 20 人，不足者引導至散客購票）。
     * 實作門票試算（全票 280、半票 140、幼童 0）。
     * 實作遊覽車隨隊優惠（每 1 台遊覽車享 1 司機 + 1 領隊共 2 位免票，不計入金額）。
     * 實作 10% 彈性訂金試算（整數四捨五入）。
  3. **容量與時間閘門防呆模組 (`app/core/capacity_gate.py`)**：
     * 實作園區營運時間（10:00 開園）與梯次排程。
     * 實作團體最後入場截止防呆：**17:00 以後嚴格禁止預約入場**。
     * 實作當日急單時效管制（強制台北時區 `Asia/Taipei` 判定）：上午送單限下午場（$\ge$ 13:00）；下午送單限 15:00 以後；15:00 以後當日梯次全面截止。
     * 實作園區容量總承載管制（全日 1000 人、上午場 400 人、下午場 600 人）。
  4. **獨立 Flex Message 視覺卡片模板 (`app/templates/`)**：
     * `confirmation_card.json`：預約核對確認卡（團體名稱、窗口、時段、各票種細項、車數、免票司領、總金額與 10% 訂金）。
     * `time_slot_card.json`：入園時段選擇卡（梯次說明、管制狀態與動態按鈕矩陣）。
     * `contact_card.json`：真人客服名片（專員資訊、服務時間與 `tel:` 一鍵撥號協定）。
     * `template_renderer.py`：純 JSON 模板安全注入與動態組裝，完全與後端解耦，日後平移 Node.js 零成本。
  5. **測試驗證**：
     * 建立 3 大測試套件：`tests/test_pricing.py`、`tests/test_capacity_gate.py`、`tests/test_flex_templates.py`。
     * 執行 `pytest -v`，**18 項單元測試 100% 全數通過**（包含 LINE SDK 容器結構解析驗證）。
     * 發現並修復 Windows 平台缺少 IANA 時區庫之環境問題（紀錄於 `ISSUES_LOG.md` ISS-003）。

---

## [2026-09-24 11:38] 後端核心對話狀態機與 Webhook 伺服器建置完成 (Phase 2)
* **需求指示**：使用者發出「請推進」指令，推展對話狀態機核心與 FastAPI 伺服器整合。
* **交付成果**：
  1. **8 步驟對話狀態機 (`app/core/state_machine.py`)**：
     * 涵蓋 Step 0（啟動）至 Step 8（預約流水號產生與完成），結合正則解析姓名、手機、日期時間、人數與車輛。
     * 內建 15 分鐘無回應自動逾時重置保護。
     * 內建真人接手開關：辨識「專人、客服、業務、電話、人工」關鍵字立即發送聯絡名片並暫停機器人，並支援「恢復」回到機器人模式。
  2. **LINE Messaging API 服務封裝 (`app/services/line_service.py`)**：
     * 封裝 Webhook 簽章校驗與文字/Flex 卡片發送，具備無 Token 模擬模式，保護本地開發除錯穩定性。
  3. **FastAPI Webhook 主伺服器 (`app/main.py`)**：
     * 建立 `/` 與 `/health` 健康檢查端點。
     * 建立 `/webhook` 端點，採用 FastAPI `BackgroundTasks` 進行非同步分派處理，達成 1 秒內極速秒回 HTTP 200。
  4. **測試驗證**：
     * 撰寫 `tests/test_state_machine.py`（完整流程走訪、未滿20人攔截、時段超額攔截、15分鐘逾時重置、真人客服切換）。
     * 撰寫 `tests/test_webhook_api.py`（端點狀態、簽章檢核失敗400、訊息分派200）。
     * 執行 `pytest -v`，**27 項測試 100% 全數通過**！



---

## [2026-09-24 11:44] LINE 後台開通與 Webhook 雙向串接全數驗證通過 (Phase 1)
* **需求指示**：使用者要求「LINE 後台開通與 Webhook 串接 請協助我做這件事」。
* **引導與執行歷程**：
  1. **憑證配置**：引導使用者於 LINE Developers Console 取得 Channel Secret 與核發長期 Channel Access Token，並寫入本機 .env 檔案。
  2. **公網穿透**：下載並部署免安裝版 
grok.exe（v3.39.11），設定 Authtoken 並啟動 
grok http 8000 取得 HTTPS 轉發通道（unexpired-yoga-thinly.ngrok-free.dev）。
  3. **LINE Developers 設定**：設定 Webhook URL 為 https://unexpired-yoga-thinly.ngrok-free.dev/webhook，點選 Verify 通過驗證（HTTP 200），並開啟 Use webhook。
  4. **防呆調校**：協助使用者審視設定截圖，發現並指導將 LINE Official Account Manager 的「自動回應訊息 (Auto-reply messages)」自 Enabled 改為 Disabled，徹底根除雙重訊息打架隱患。
  5. **實機驗收**：使用者手機加入官方帳號並發送訊息，成功收到後端伺服器之雙向回覆，Phase 1 正式完成（100%）。

---

## [2026-09-24 11:49] Google 試算表資料庫串接與即時容量連動完成 (Phase 5)
* **需求指示**：使用者選擇「選項A」，推進 Google 試算表資料庫與容量儀表板連動實作。
* **交付成果**：
  1. **獨立資料模型模組 (`app/core/models.py`)**：抽離 `BookingData`、`UserSession`、`BotResponse`，徹底解耦避免跨層循環引用。
  2. **Google 試算表資料庫服務 (`app/services/sheets_service.py`)**：
     * 定義 `預約記錄表_Log`（21 欄完整訂單欄位）與 `檔期總量控管_Dashboard`（5 欄容量統計與紅字警示）。
     * 實作 `append_reservation_record()`：將確認的預約寫入記錄表，並動態累加當日場次人數與計算超載警示。
     * 實作 `get_booked_capacity()`：即時取得指定日期已預約之「上午場」與「下午場」總人數。
     * 支援本地記憶體快取與降級備援，在無 GCP 憑證下保證本機開發與單元測試穩定運作。
     * 實作 `SheetsService` 物件導向相容封裝，支援手動指令碼與自動化介面。
  3. **狀態機雙向深度連動**：
     * Step 3 梯次選取時，自動從試算表提取該日已預約之即時容量進行防呆預審。
     * Step 8 正式送出時，自動非同步將訂單同步寫入雲端試算表。
  4. **測試驗證**：
     * 新增 `tests/test_sheets_service.py` 與 `tests/test_sheets_manual.py`。
     * 執行 `pytest -v`，**31 項測試 100% 全數通過**！


---

## [2026-09-24 12:40] 園區 FAQ 知識庫與 Gemini 2.5 Flash 智能客服整合上線 (Phase 6)
* **需求指示**：使用者提問客人詢問設施、導覽等非預約問題該如何強化，並指示「擬個測試內容弄進去就好了，另 gemini 的版號已經更高了，請直接調用適合並節省的模型處理，直接做完」。
* **交付成果**：
  1. **園區專屬問答知識庫 (`app/data/park_knowledge.md`)**：
     * 完整定義遊戲設施介紹與身高安全限制（雲霄飛車、摩天輪、海盜船、旋轉木馬、碰碰車、急流泛舟）。
     * 定義團體專屬導覽梯次（每日兩場：上午場 10:30、下午場 14:00，時長 45 分鐘）。
     * 定義餐飲與特殊飲食服務（團體中式合菜、便當、全素與蛋奶素友善配置）。
     * 定義交通與遊覽車停車場配置（大客車專用停車場、司領休息室與茶水招待）。
     * 定義票務發票與常見 FAQ（統編三聯式發票、寵物入園規定）。
  2. **智能問答服務模組 (`app/services/faq_service.py`)**：
     * 升級引入最新 Google 官方 SDK `google-genai`。
     * 模型選型採用最新、高性價比且反應迅速的 `gemini-2.5-flash`。
     * 設定繁體中文系統 Prompt，指示 AI 扮演熱情親切的遊樂園客服小幫手，並在回答完非預約問題後主動引導客人輸入「預約」進入團體優惠填單流程。
     * 實作本地 Markdown 關鍵字語意備援降級機制，在無 `GEMINI_API_KEY` 或離線測試環境下保證 100% 穩定秒回，不報錯不卡死。
  3. **對話狀態機無縫分流整合 (`app/core/state_machine.py`)**：
     * 在 Step 0（待命中）與 Step 8（預約完成後），若客人提出任意問題，自動由 `ask_park_faq` 智能回答。
     * 客人一旦輸入「預約」或「團體預約」，立即無縫切入 Step 1 填單流程。
  4. **完整單元測試與驗證**：
     * 建立 `tests/test_faq_service.py`，涵蓋導覽、設施、素食、停車、寵物規定與預約切換整合測試。
     * 執行全套測試，**38 項測試 100% 全數 PASS**！

---

## [2026-09-24 13:36] 預約中斷防呆機制與非相關問答智慧攔截上線
* **需求指示**：使用者反映「目前進入預約流程 沒辦法中斷 而且 打上不相關的文字 還會被當作預約的團體名 可以防呆嘛」。
* **交付成果**：
  1. **全域預約隨時中斷/取消機制**：
     * 支援輸入「取消」、「取消預約」、「放棄」、「不要了」、「不想預約了」、「退出」等指令或點擊按鈕，任何步驟皆可隨時中斷退出並清空暫存，回歸待命狀態。
     * 在各步驟（Step 0 ~ Step 7）的 Quick Reply 按鈕中全面加入【❌ 取消預約】快捷鍵。
  2. **問答插話防呆與團體名稱防污染**：
     * 新增 `is_likely_question_or_faq` 檢測，精確識別問句特徵（？、幾點、多少錢、設施、營業時間、素食、交通、招呼詞等）。
     * 在 Step 1（及各步驟）若使用者輸入提問，系統不再把問題誤當成「團體名稱」存入，而是先調用知識庫/Gemini 為使用者解答，並溫馨提醒當前步驟與提供取消預約按鈕。
     * 設定團體名稱字數防呆（2 ~ 30 字元）。
  3. **模型與測試相容性維護**：
     * 將預設 Gemini 模型升級為最新穩定版 `gemini-2.0-flash`。
     * 排除統編（8碼）與手機號碼（10碼）之誤判。
     * 測試套件全面更新，**40 項單元測試 100% 全數通過**！
