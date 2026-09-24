"""
園區常見問答與 Google Gemini AI 智能客服模組 (faq_service.py)

功能職責：
1. 讀取園區官方知識庫 (app/data/park_knowledge.md)
2. 調用官方最新 google-genai SDK (預設 gemini-2.5-flash 節省高效模型)
3. 嚴格落實風控守則 (嚴禁私下給予票價折讓、嚴防幻覺)
4. 支援離線與無金鑰狀態下的關鍵字智慧容錯回覆 (保證系統 100% 穩定不中斷)
"""
import os
import re
import logging
from pathlib import Path
from typing import Optional

from app.config import GEMINI_API_KEY, GEMINI_MODEL

logger = logging.getLogger("faq_service")
logger.setLevel(logging.INFO)

KNOWLEDGE_FILE = Path(__file__).resolve().parent.parent / "data" / "park_knowledge.md"

_CACHED_KNOWLEDGE: Optional[str] = None


def load_park_knowledge() -> str:
    """載入園區官方知識庫文字內容"""
    global _CACHED_KNOWLEDGE
    if _CACHED_KNOWLEDGE is not None:
        return _CACHED_KNOWLEDGE

    if not KNOWLEDGE_FILE.exists():
        logger.warning(f"知識庫檔案不存在：{KNOWLEDGE_FILE}")
        return ""

    with open(KNOWLEDGE_FILE, "r", encoding="utf-8") as f:
        _CACHED_KNOWLEDGE = f.read()
    return _CACHED_KNOWLEDGE


SYSTEM_INSTRUCTION = """
你是由「星夢歡樂世界（遊樂園）」官方推出的 AI 智能客服「星夢小助手」。
你的任務是根據提供的【園區官方指南與常見問題知識庫】，熱情、親切且專業地回答遊客關於遊戲設施、團體導覽時間、餐飲配置、交通停車與入園須知等問題。

【回答守則與風控規範】：
1. 必須 100% 嚴格使用「繁體中文（台灣）」回答，語氣活潑親切且有禮貌。
2. 答案必須嚴格依據知識庫內容作答，不可自行捏造或承諾知識庫未記載的設施、時間或規範（嚴禁 AI 幻覺）。
3. 嚴格風控原則：
   - 團體票優惠固定為「最少需滿 20 人成團」（全票 NT$ 280、半票 NT$ 140、幼童免票，每台遊覽車贈送 2 位司領免票）。
   - 嚴格禁止私下承諾任何額外折扣、折讓或免費招待。
   - 若遊客詢問 100 人以上大宗企業家庭日或契約用印，請親切提醒可在聊天室輸入「專人」或「客服」，將由業務專員一對一對接。
4. 促成導流：在回答完遊客的設施或導覽問題後，於文末親切加上一句導引：「💡 若貴單位預計 20 人以上同行，隨時在聊天室輸入『預約』，我能立即為您啟動專屬團體優惠預約流程喔！」
"""


def _fallback_keyword_answer(question: str) -> str:
    """
    當尚未配置 GEMINI_API_KEY 或網路異常時的關鍵字智能容錯回覆
    """
    q = question.lower()

    if any(k in q for k in ["票價", "門票", "票務", "多少錢", "費用", "收費", "價格", "優惠"]):
        return (
            "🎟️ 【星夢歡樂世界 團體優惠票價細則】\n\n"
            "▪ 成團門檻：最低需滿 20 人同行。\n"
            "▪ 全票：每位 NT$ 280 元 (滿 12 歲以上之成人與學生)。\n"
            "▪ 半票：每位 NT$ 140 元 (7～12 歲學童或 65 歲以上長者)。\n"
            "▪ 幼童票：NT$ 0 元 (6 歲以下幼兒免費入園)。\n"
            "🚌 【遊覽車隨隊優惠】：每 1 台遊覽車享有 1 位司機 ＋ 1 位領隊（共 2 位）隨隊免票入場！\n"
            "📌 【訂金與改期】：繳納 10% 彈性訂金享保證保留名額，入園前 3 天可免費改期一次。\n\n"
            "💡 若貴單位預計 20 人以上同行，隨時在聊天室輸入『預約』，我能立即為您啟動專屬團體預約流程喔！"
        )

    # 1. 設施優先比對
    if any(k in q for k in ["設施", "遊戲", "雲霄飛車", "摩天輪", "旋轉木馬", "泛舟", "4d", "海盜船", "碰碰車"]):
        return (
            "🎡 【星夢歡樂世界 熱門設施介紹】\n\n"
            "1. 🎢【星際極速雲霄飛車】：時速 95km、360 度倒掛俯衝（身高限制 140cm 以上）。\n"
            "2. 🌊【水上疾馳探險泛舟】：雨林激流與 15 公尺瀑布俯衝（身高限制 110cm 以上，建議自備輕便雨衣）。\n"
            "3. 🎡【夢幻璀璨摩天輪】：俯瞰全園與自然山景，每車廂限乘 6 人（全年齡適宜）。\n"
            "4. 🎠【童話雙層旋轉木馬】：歐式復古木馬，夜間有點燈音樂秀（全年齡適宜）。\n"
            "5. 🎬【4D 沉浸式冒險影院】：體感動感座椅與逼真特效（身高限制 100cm 以上）。\n\n"
            "💡 若貴單位預計 20 人以上同行，隨時在聊天室輸入『預約』，我能立即為您啟動專屬團體優惠預約流程喔！"
        )

    # 2. 定時導覽比對
    if any(k in q for k in ["導覽", "解說", "導覽時間", "集合地點"]):
        return (
            "⏰ 【星夢歡樂世界 團體專屬定時導覽】\n\n"
            "園區每日固定開放兩梯次專人導覽（每場約 40 分鐘）：\n"
            "▪ 上午場：10:30 ～ 11:10\n"
            "▪ 下午場：14:00 ～ 14:40\n"
            "▪ 集合地點：園區正門「歡樂城堡前鐘樓廣場」\n"
            "▪ 亮點：專人動線規劃、熱門設施排隊省時秘訣與團體大合照留念！\n\n"
            "💡 若貴單位預計 20 人以上同行，隨時在聊天室輸入『預約』，我能立即為您啟動專屬團體優惠預約流程喔！"
        )

    if any(k in q for k in ["素食", "便當", "吃", "餐飲", "餐廳", "午餐"]):
        return (
            "🍱 【園區餐飲與素食配置】\n\n"
            "▪ 團體便當：提供「經濟餐盒（NT$ 100）」與「豪華雙主菜餐盒（NT$ 150）」，入園前 3 天可確認數量。\n"
            "▪ 素食料理：園區「綠洲庭園餐廳」全天候提供全素（Vegan）及蛋奶素套餐、義大利麵與蔬食便當。\n"
            "▪ 戶外野餐區：設有遮陽長廊，歡迎自備外食團體使用。\n\n"
            "💡 若貴單位預計 20 人以上同行，隨時在聊天室輸入『預約』，我能立即為您啟動專屬團體優惠預約流程喔！"
        )

    if any(k in q for k in ["交通", "捷運", "停車", "公車", "遊覽車", "開車"]):
        return (
            "🚗 【交通抵達與停車指南】\n\n"
            "▪ 遊覽車停泊：園區北門設有「大型遊覽車專用免費停車場」，具備專屬迴轉道與司機休息室。\n"
            "▪ 捷運轉乘：搭至「樂園站」2 號出口，轉乘園區免費接駁專車（每 10~15 分鐘一班）直達正門。\n"
            "▪ 自用小客車：平日 NT$ 100 元/次、假日 NT$ 150 元/次。\n\n"
            "💡 若貴單位預計 20 人以上同行，隨時在聊天室輸入『預約』，我能立即為您啟動專屬團體優惠預約流程喔！"
        )

    if any(k in q for k in ["寵物", "狗", "貓"]):
        return (
            "🐾 【寵物入園須知】\n\n"
            "為維護園區安全與衛生，寵物需全程置於「寵物推車」或「透氣提籠」內，禁止落地漫遊；合格導盲犬則不受此限制，感謝您的配合！\n\n"
            "💡 若貴單位預計 20 人以上同行，隨時在聊天室輸入『預約』，我能立即為您啟動專屬團體優惠預約流程喔！"
        )

    # 一般綜合提示
    return (
        "🎡 您好！我是星夢歡樂世界的 AI 智慧助理「星夢小助手」。\n\n"
        "您可以向我詢問園區熱門設施（如雲霄飛車、摩天輪）、每日定時導覽時段（10:30 / 14:00）、團體便當素食或捷運接駁專車資訊！\n\n"
        "💡 若貴單位預計 20 人以上同行，請隨時在聊天室輸入『預約』，我將立即為您辦理團體門票與遊覽車免票登記！"
    )


def ask_park_faq(question: str) -> str:
    """
    根據使用者提問調用 Google Gemini 生成智能解答。
    若無 API Key 或網路異常，則平滑降級為知識庫語意回覆。
    """
    knowledge = load_park_knowledge()

    if not GEMINI_API_KEY:
        logger.info("未檢測到 GEMINI_API_KEY，使用本機知識庫語意回覆。")
        return _fallback_keyword_answer(question)

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GEMINI_API_KEY)

        prompt = (
            f"【園區官方知識庫內容】：\n{knowledge}\n\n"
            f"【遊客諮詢提問】：\n{question}\n\n"
            "請依據知識庫內容與守則，以繁體中文親切解答："
        )

        candidate_models = [GEMINI_MODEL]
        if "gemini-1.5-flash" not in candidate_models:
            candidate_models.append("gemini-1.5-flash")

        for model_name in candidate_models:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_INSTRUCTION,
                        temperature=0.3,
                    )
                )
                if response and response.text:
                    return response.text.strip()
            except Exception as model_err:
                logger.warning(f"模型 {model_name} 呼叫失敗 ({model_err})，嘗試下一個備援模型...")
                continue

        return _fallback_keyword_answer(question)

    except Exception as e:
        logger.error(f"Gemini API 調用異常：{e}，自動降級為知識庫備援回覆。")
        return _fallback_keyword_answer(question)
