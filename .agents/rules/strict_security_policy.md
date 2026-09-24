# 嚴格資安與機密保護守則 (Strict Security Policy)

本規範適用於本專案的所有開發、除錯、建置與維護行為：

1. **參考資料隔離防線**：
   - 根目錄下之 `/參考資料勿上傳/`（包含企劃書、定價表、內部運營細則等）嚴格禁止透過 Git 納入追蹤與推送，嚴防營業秘密外洩。
   - 必須透過 `.gitignore` 阻絕追蹤。

2. **金鑰與憑證保護**：
   - `.env`, `.env.*`, `*.pem`, `*.key`, `credentials.json`, `service_account*.json` 等敏感設定檔嚴禁納入 Git 追蹤。
   - 嚴禁在程式碼中硬編碼任何 LINE Channel Secret、Channel Access Token、Google Service Account 金鑰或試算表 ID。
   - 必須提供安全的 `.env.example` 作為替換範本。

3. **LINE Webhook 請求驗證 (Security Verification)**：
   - 伺服器端必須嚴格驗證 LINE 傳入的 `X-Line-Signature` 標頭（使用 Channel Secret 進行 HMAC-SHA256 驗證），阻絕任何偽造之 Webhook 請求。

4. **個資安全防護 (Privacy Protection)**：
   - LINE 聊天室中僅收集單一聯絡窗口姓名、電話與人數，嚴格禁止在聊天室索取團體保險身分證字號與出生年月日等高敏感個資。
