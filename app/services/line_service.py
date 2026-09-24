"""
LINE Messaging API 服務串接與簽章驗證模組 (line_service.py)
"""
import json
import logging
from typing import Optional, Dict, Any, List

from linebot.v3 import WebhookHandler
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    PushMessageRequest,
    TextMessage,
    FlexMessage,
    FlexContainer,
    QuickReply,
    QuickReplyItem,
    MessageAction,
)

from app.config import LINE_CHANNEL_SECRET, LINE_CHANNEL_ACCESS_TOKEN

logger = logging.getLogger("line_service")
logger.setLevel(logging.INFO)

# Webhook 簽章處理器
handler = WebhookHandler(LINE_CHANNEL_SECRET) if LINE_CHANNEL_SECRET else None


def get_messaging_api() -> Optional[MessagingApi]:
    """取得 LINE MessagingApi 客戶端"""
    if not LINE_CHANNEL_ACCESS_TOKEN:
        logger.warning("尚未配置 LINE_CHANNEL_ACCESS_TOKEN，目前處於本機模擬模式。")
        return None
    configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
    api_client = ApiClient(configuration)
    return MessagingApi(api_client)


def verify_signature(body: str, signature: str) -> bool:
    """校驗 LINE Webhook 簽章 X-Line-Signature"""
    if not LINE_CHANNEL_SECRET:
        # 若本機開發未填金鑰，暫時放行並紀錄
        logger.warning("LINE_CHANNEL_SECRET 為空，略過簽章驗證（本機開發測試模式）。")
        return True
    try:
        handler.parser.signature_validator.validate(body, signature)
        return True
    except Exception as e:
        logger.error(f"LINE 簽章驗證失敗：{e}")
        return False


def send_reply(
    reply_token: str,
    text: Optional[str] = None,
    flex_card: Optional[Dict[str, Any]] = None,
    quick_replies: Optional[List[str]] = None,
    alt_text: str = "遊樂園團體預約通知"
) -> bool:
    """
    發送 Webhook 回覆訊息 (支援純文字、Flex Message 卡片與 QuickReply 捷徑按鈕)
    """
    api = get_messaging_api()
    messages = []

    qr_obj = None
    if quick_replies:
        items = [
            QuickReplyItem(action=MessageAction(label=q[:20], text=q))
            for q in quick_replies[:13]  # LINE 規定上限 13 個
        ]
        qr_obj = QuickReply(items=items)

    if text:
        messages.append(TextMessage(text=text, quick_reply=qr_obj))

    if flex_card:
        try:
            container = FlexContainer.from_dict(flex_card)
            # 若無文字訊息但有 flex_card 與 quick_replies，可掛在 flex 上
            flex_msg = FlexMessage(alt_text=alt_text, contents=container, quick_reply=qr_obj if not text else None)
            messages.append(flex_msg)
        except Exception as e:
            logger.error(f"Flex 卡片轉換為 FlexContainer 失敗：{e}")

    if not messages:
        return False

    if not api:
        logger.info(f"[模擬回覆] reply_token={reply_token}, 訊息則數={len(messages)}")
        return True

    try:
        req = ReplyMessageRequest(reply_token=reply_token, messages=messages)
        api.reply_message(req)
        return True
    except Exception as e:
        logger.error(f"發送 LINE 回覆失敗：{e}")
        return False


def get_user_profile_name(user_id: str) -> str:
    """取得 LINE 用戶暱稱（Profile Display Name），若無法獲取則回傳空字串"""
    if not user_id or user_id in ["anonymous_user", "test_user_id"]:
        return ""
    api = get_messaging_api()
    if not api:
        return ""
    try:
        profile = api.get_profile(user_id)
        return profile.display_name or ""
    except Exception as e:
        logger.debug(f"無法取得 LINE 用戶 profile ({user_id})：{e}")
        return ""

