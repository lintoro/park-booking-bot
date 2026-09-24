"""
FastAPI 主伺服器與 LINE Webhook 入口 (main.py)
"""
import json
import logging
from typing import Dict, Any
from fastapi import FastAPI, Request, Header, HTTPException, BackgroundTasks, status
from fastapi.responses import JSONResponse

from app.config import PORT, TIMEZONE
from app.services.line_service import verify_signature, send_reply
from app.core.state_machine import state_machine

# 設定日誌
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("main_server")

app = FastAPI(
    title="遊樂園團體預約 LINE 智慧自動化系統",
    description="專為遊樂園團體預約打造之對話機器人，具備容量防呆、當日急單管制、隨隊免票優惠試算與 Flex Message 模板",
    version="1.0.0"
)


@app.get("/", tags=["系統狀態"])
async def root():
    return {
        "status": "online",
        "service": "Amusement Park Group Reservation LINE Bot",
        "timezone": TIMEZONE,
        "version": "1.0.0"
    }


@app.get("/health", tags=["系統狀態"])
async def health_check():
    return {
        "status": "healthy",
        "code": 200,
        "detail": "後端服務正常運作中"
    }


def handle_line_events_background(body_str: str):
    """
    在背景任務中非同步處理 LINE Webhook 事件，避免 LINE 伺服器因耗時作業超時
    """
    try:
        payload = json.loads(body_str)
        events = payload.get("events", [])
        for event in events:
            event_type = event.get("type")
            source = event.get("source", {})
            user_id = source.get("userId", "anonymous_user")
            reply_token = event.get("replyToken")

            if not reply_token:
                continue

            if event_type == "message":
                message = event.get("message", {})
                if message.get("type") == "text":
                    user_text = message.get("text", "")
                    logger.info(f"收到來自 [{user_id}] 訊息：{user_text}")
                    bot_resp = state_machine.process_message(user_id=user_id, message_text=user_text)
                    if bot_resp.reply_text or bot_resp.flex_card:
                        send_reply(
                            reply_token=reply_token,
                            text=bot_resp.reply_text,
                            flex_card=bot_resp.flex_card,
                            quick_replies=bot_resp.quick_replies
                        )

            elif event_type == "follow":
                logger.info(f"收到新用戶加好友/解除封鎖事件：[{user_id}]")
                bot_resp = state_machine.handle_follow_event(user_id=user_id)
                if bot_resp.reply_text:
                    send_reply(
                        reply_token=reply_token,
                        text=bot_resp.reply_text,
                        quick_replies=bot_resp.quick_replies
                    )

            elif event_type == "postback":
                postback = event.get("postback", {})
                postback_data = postback.get("data", "")
                postback_params = postback.get("params", {})
                logger.info(f"收到來自 [{user_id}] Postback：data={postback_data}, params={postback_params}")
                
                # 若為 datetimepicker 日期選擇
                message_from_params = ""
                if isinstance(postback_params, dict) and "date" in postback_params:
                    message_from_params = postback_params["date"]

                bot_resp = state_machine.process_message(
                    user_id=user_id,
                    message_text=message_from_params,
                    postback_data=postback_data
                )
                if bot_resp.reply_text or bot_resp.flex_card:
                    send_reply(
                        reply_token=reply_token,
                        text=bot_resp.reply_text,
                        flex_card=bot_resp.flex_card,
                        quick_replies=bot_resp.quick_replies
                    )

    except Exception as e:
        logger.error(f"背景處理 LINE 事件異常：{e}", exc_info=True)


@app.post("/webhook", tags=["LINE Webhook"])
async def line_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_line_signature: str = Header(default="", alias="X-Line-Signature")
):
    """
    LINE Webhook 回呼端點
    嚴格校驗 X-Line-Signature 簽章，並將事件移至背景處理，1 秒內秒回 HTTP 200
    """
    body_bytes = await request.body()
    body_str = body_bytes.decode("utf-8")

    # 1. 簽章防偽驗證
    if not verify_signature(body_str, x_line_signature):
        logger.warning("收到未通過簽章校驗的非官方 Webhook 請求！")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="LINE 簽章驗證失敗 (Invalid Signature)"
        )

    # 2. 加入背景處理佇列
    background_tasks.add_task(handle_line_events_background, body_str)

    # 3. 立即秒回 HTTP 200 OK
    return JSONResponse(status_code=status.HTTP_200_OK, content={"status": "received"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=PORT, reload=True)
