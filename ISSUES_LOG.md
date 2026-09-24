# 問題排查與修復日誌 (ISSUES_LOG.md)

本文件詳細記錄專案開發、建置與部署期間遭遇之問題、排查過程與最終解決方案。

---

## 問題記錄索引

| 編號 | 發生時間 | 類別 | 問題描述 | 狀態 | 解決方式摘要 |
| :--- | :--- | :--- | :--- | :---: | :--- |
| **ISS-001** | 2026-09-24 10:36 | IDE 介面操作 | Antigravity 2.0 無法將對話拖曳進 Projects 區塊 | **已解決** | 說明底層對話歸屬邏輯，透過 `File -> Open Folder` 載入工作目錄，並確認後端目錄已鎖定。 |
| **ISS-002** | 2026-09-24 10:42 | 開發規範 | 專案初建缺乏全域 Rules 與換機/交接標準 SOP | **已解決** | 參考上層專案體系，建立 `.gemini/rules`、`.agents/rules` 與四大標準管理日誌。 |
| **ISS-003** | 2026-09-24 11:24 | Windows 環境相容 | Windows 執行 `ZoneInfo("Asia/Taipei")` 拋出 `ZoneInfoNotFoundError` | **已解決** | 於 `requirements.txt` 納入 `tzdata` 套件，並在程式中實作 `timezone(timedelta(hours=8))` 容錯機制。 |
| **ISS-004** | 2026-09-24 12:12 | Google Drive API 配額限制 | 服務帳戶主動 `create` 試算表拋出 `The user's Drive storage quota has been exceeded` (403) | **已解決** | Google 政策限制服務帳戶預設配額為 0 MB，標準做法改為由個人 Google Drive 建表後「共用」給服務帳戶 Email，再由程式全自動建立工作表與欄位。 |
| **ISS-005** | 2026-09-24 12:40 | 對話狀態機流轉 | 使用者加好友後回覆團體名稱，系統卡在 Step 0 重複提示第一句 | **已解決** | 1. 補上 LINE `follow` 事件自動初始化 Step 1；2. 增加智慧識別前綴（如「團體名稱是」）與常用組織關鍵字，自動由 Step 0 躍遷至 Step 2；3. 實作 `clean_group_name` 乾淨萃取名稱。 |

---

## 詳細排查歷程

### ISS-001：Antigravity 2.0 無法將對話拖曳進 Projects 區塊
* **現象**：使用者希望將已建立的對話從底層「Conversations」拖曳或設定進「Projects」清單，但選單無對應按鈕。
* **原因分析**：Antigravity 目前未開放全域對話跨區拖曳。由「+ New Conversation」開啟的對話預設隸屬於全域（`outside-of-project`）。
* **處置與建議**：
  1. 使用者在選單列點擊 `File -> Open Folder`（或快捷鍵 `Ctrl + K, Ctrl + O`）選擇 `C:\Github\ReactApp\LineBot_test` 載入專案。
  2. 後續在此專案名稱旁點擊 `+` 開啟的對話將自動收納於該專案底下。
  3. 目前對話已直接鎖定該路徑作為工作根目錄，檔案操作均已精確寫入，不影響任何開發進度。

### ISS-002：專案初建缺乏全域 Rules 與換機/交接標準 SOP
* **現象**：新建立的 `LineBot_test` 尚未具備標準規則與異地換機指南。
* **原因分析**：專案為新建目錄，尚未套用母層專案的開發與資安守則。
* **處置與建議**：
  1. 檢索並遵循 `user_rules/GLOBAL_RULES.md` 及既有專案規則。
  2. 建立繁體中文政策（`traditional_chinese_policy.md`）、嚴格資安守則（`strict_security_policy.md`）、專案專屬防呆規範（`project_rules.md`）。
  3. 產出完備的 `PROJECT_HANDOVER.md`，提供換機接續開發、環境變數與連線設定的標準化 SOP。

### ISS-003：Windows 系統缺乏 IANA 時區資料庫導致 ZoneInfo 報錯
* **現象**：在 Windows 平台上執行包含時區判斷的測試時，`zoneinfo.ZoneInfo("Asia/Taipei")` 拋出 `ZoneInfoNotFoundError: 'No time zone found with key Asia/Taipei'`。
* **原因分析**：Windows 作業系統未預載 Unix/Linux 的 IANA 時區資料庫（`/usr/share/zoneinfo`），Python 3.9+ 的 `zoneinfo` 在 Windows 上需依賴 `tzdata` 套件支援。
* **處置與建議**：
  1. 執行 `pip install tzdata` 並同步更新至 `requirements.txt`。
  2. 於 `app/core/capacity_gate.py` 加入 `try...except` 雙重防護機制：若載入 `ZoneInfo` 失敗，自動平滑降級為 `datetime.timezone(datetime.timedelta(hours=8), name="Asia/Taipei")`，徹底確保無套件環境下仍能 100% 正確判定台北時間。

