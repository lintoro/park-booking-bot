# 系統開發進度與功能完成度對照表 (PROGRESS.md)

本專案追蹤遊樂園團體預約 LINE 官方帳號智慧機器人之各階段里程碑與實作狀態。

---

## 階段進度總覽

| 階段 | 重點目標 | 狀態 | 完成百分比 |
| :--- | :--- | :---: | :---: |
| **Phase 0：企劃與環境初始化** | 規格吸收、目錄確認、全域與專案規則、換機手冊建置 | **已完成** | 100% |
| **Phase 1：LINE 後台與金鑰開通** | 建立 Provider、Channel、取得 Token/Secret、設定 Webhook | **已完成** | 100% |
| **Phase 2：後端核心與對話狀態機** | FastAPI 伺服器、8 步驟對話狀態機、15 分鐘逾時機制 | **已完成** | 100% |
| **Phase 3：防呆運算與計費模組** | 容量檢查、當日急單管制、票價計算、遊覽車免票計算 | **已完成** | 100% |
| **Phase 4：Flex Message 視覺卡片** | 預約核對卡片、時段選擇卡、真人名片 JSON 模板設計 | **已完成** | 100% |
| **Phase 5：資料庫/Google 試算表串接** | 預約表記錄寫入、即時總量管制儀表板連動 | **已完成** | 100% |
| **Phase 6：園區 FAQ 知識庫與 Gemini AI** | 園區知識庫、Gemini 2.5 Flash 智能客服、本地關鍵字備援降級 | **已完成** | 100% |
| **Phase 7：端到端整合測試與驗收** | 邊界條件實測、急單攔截驗證、真人切換、正式上線部署 | 待進行 | 0% |

---

## 詳細工作項目清單 (Task Breakdown)

### Phase 0：企劃與環境初始化 (已完成)
- [x] 完整讀取 `參考資料勿上傳/遊樂園團體預約LINE智慧自動化_專案企劃書.md` 規格。
- [x] 將 `C:\Github\ReactApp\LineBot_test` 設為專案工作目錄。
- [x] 初始化 `.gitignore`、`README.md`、`.env.example`。
- [x] 比照標準專案規範，建立 `.agents/rules/` 與 `.gemini/rules/` 規則體系。
- [x] 建立四大標準文件（`docs/PROJECT_CONVERSATION_HISTORY.md`、`PROGRESS.md`、`ISSUES_LOG.md`、`PROJECT_HANDOVER.md`）。

### Phase 1：LINE 後台與金鑰開通 (已完成)
- [x] 後端 FastAPI Webhook 伺服器基礎架構建立完畢（含簽章驗證與異步處理）。
- [x] Python 虛擬環境 (`venv`) 與相依套件 (`fastapi`, `line-bot-sdk` 等) 安裝就緒。
- [x] 建立本地環境變數範本 `.env` 並配置金鑰憑證。
- [x] 於 LINE Developers Console 建立專案 Provider。
- [x] 建立 Messaging API Channel 並取得 `Channel Secret`。
- [x] 發行長期 `Channel Access Token`。
- [x] 設定 Webhook URL 並開啟 `Use webhook` 開關。
- [x] 關閉 LINE Official Account Manager 的內建「自動回應訊息」，啟用 Webhook 模式。

### Phase 2：後端核心與對話狀態機 (已完成)
- [x] 實作 8 步驟對話狀態管理與資料暫存（`app/core/state_machine.py`）。
- [x] 抽離獨立資料模型（`app/core/models.py`，解耦避免循環引用）。
- [x] 【用戶體驗升級】將「入園日期」與「到達時段」拆分為獨立兩題，分別附帶 Quick Reply 捷徑按鈕。
- [x] 【用戶體驗升級】格式認定全面放寬（`app/core/relaxed_parsers.py`，支援中文數字、大人小孩、單一總人數「40人」、遊覽車「兩台」等）。
- [x] 【用戶體驗升級】最後確認卡片支援【指定修改】單一項目，改完秒回最新 Flex 確認卡，無需重頭來過。
- [x] 實作 15 分鐘無回應自動逾時重置邏輯。
- [x] 實作「真人接手」關鍵字識別與切換開關（無縫轉接名片與恢復機制）。
- [x] 實作 FastAPI 主服務與 Webhook 端點（`app/main.py`，支援背景任務秒回 200）。
- [x] 封裝 LINE SDK 回覆與簽章驗證（`app/services/line_service.py`，原生支援 QuickReply 捷徑按鈕）。
- [x] 完成完整對話狀態機與 Webhook 端點單元測試（`tests/test_state_machine.py`, `tests/test_webhook_api.py`）。

### Phase 3：防呆運算與計費模組 (已完成)
- [x] 實作成團人數門檻驗證（最少 20 人，不足者引導至散客通路，`app/core/pricing.py`）。
- [x] 實作入園時間防呆：17:00 以後嚴格禁止預約（`app/core/capacity_gate.py`）。
- [x] 實作營業時間防呆：10:00 以前非開園時段嚴格攔截。
- [x] 實作當日急單防呆：上午預約限下午場（$\ge$ 13:00）；下午預約限 15:00 以後；15:00 以後當日截止。
- [x] 實作票價試算（全票 280、半票 140、幼童免票 0）。
- [x] 實作遊覽車隨隊優惠計算（每 1 台遊覽車贈送司機 + 領隊共 2 名免票，不計入金額）。
- [x] 實作 10% 彈性訂金試算。
- [x] 完成單元測試覆蓋（`tests/test_pricing.py`, `tests/test_capacity_gate.py` 全部通過）。

### Phase 4：Flex Message 視覺卡片 (已完成)
- [x] 設計預約確認核對卡片 JSON 模板（`app/templates/confirmation_card.json`）。
- [x] 設計當日時段選單卡片 JSON 模板（`app/templates/time_slot_card.json`）。
- [x] 設計真人客服專人聯絡名片 JSON 模板（`app/templates/contact_card.json`）。
- [x] 實作獨立模板渲染與變數注入模組（`app/templates/template_renderer.py`，與後端語言解耦）。
- [x] 完成單元測試與 LINE SDK `FlexContainer` 結構相容性驗證（`tests/test_flex_templates.py` 全部通過）。

### Phase 5：資料庫與試算表串接 (已完成)
- [x] 實作 Google Cloud 服務帳戶憑證與權限範圍載入機制（`app/services/sheets_service.py`）。
- [x] 定義標準化雙工作表架構：`預約記錄表_Log`（21欄結構化訂單）與 `檔期總量控管_Dashboard`（5欄容量警示儀表板）。
- [x] 實作預約成功自動寫入試算表 Log 與即時扣減/累計容量（Step 8 聯動寫入）。
- [x] 實作時段容量即時查詢反饋機制（Step 3 查詢已預約上午/下午總人數）。
- [x] 實作本地記憶體模擬與降級備援機制（無憑證環境下保證不崩潰且支援測試）。
- [x] 完成試算表服務完整單元測試覆蓋（`tests/test_sheets_service.py`, `tests/test_sheets_manual.py`）。


### Phase 6：園區 FAQ 知識庫與 Gemini AI (已完成)
- [x] 撰寫園區完整問答知識庫檔案（`app/data/park_knowledge.md`，涵蓋設施身高限制、團體導覽 10:30/14:00、素食團餐、遊覽車停車與發票規定）。
- [x] 整合 Google 官方最新 `google-genai` SDK，調用具高性價比且反應迅速的 `gemini-2.5-flash` 模型（`app/services/faq_service.py`）。
- [x] 實作無 API Key 或網路異常時的本機 Markdown 關鍵字語意備援降級機制（保證 100% 穩定秒回不報錯）。
- [x] 串接對話狀態機 Step 0（待命中）與 Step 8（預約完成後），非預約問題智能秒回並親切導引輸入「預約」。
- [x] 完成 FAQ 服務與狀態機切換完整單元測試（`tests/test_faq_service.py` 全部通過）。

### Phase 7：端到端整合測試與驗收 (待進行)
- [ ] 啟動 `ngrok` 本地測試 Webhook 通道。
- [ ] 測試正常預約流程（Step 0 $\sim$ Step 8）。
- [ ] 測試各項防呆攔截（人數未滿 20、當日急單超時、17:00 後預約）。
- [ ] 測試 15 分鐘逾時重置與真人客服轉接。
- [ ] 雲端部署（Render / Railway / GCP Cloud Run 擇一）與正式啟用。

