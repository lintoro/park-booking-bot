"""
LINE Rich Menu (圖文選單) 生命週期與管理服務 (rich_menu_service.py)

實作 LINE Messaging API v3 Rich Menu 之完整操作：
1. 定義 2500x1686 2x2 矩陣圖文選單結構 (RichMenuRequest)
2. 自動呼叫圖片生成器並上傳 (MessagingApiBlob.set_rich_menu_image)
3. 設為官方全域預設選單 (set_default_rich_menu)
4. 提供自動同步與舊選單清理 (sync_default_rich_menu)
5. 支援本機開發無 Token 模擬模式，保證不中斷系統運行
"""
import logging
from typing import Optional, Dict, Any, List, Tuple

from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    MessagingApiBlob,
    RichMenuRequest,
    RichMenuSize,
    RichMenuArea,
    RichMenuBounds,
    MessageAction,
)

from app.config import LINE_CHANNEL_ACCESS_TOKEN
from app.services.rich_menu_generator import generate_rich_menu_image, MENU_WIDTH, MENU_HEIGHT, HALF_W, HALF_H

logger = logging.getLogger("rich_menu_service")
logger.setLevel(logging.INFO)

RICH_MENU_NAME = "遊樂園團體預約官方選單_v1.0"
RICH_MENU_CHAT_BAR_TEXT = "開啟功能選單"


def get_messaging_client() -> Optional[Tuple[MessagingApi, MessagingApiBlob]]:
    """取得 LINE MessagingApi 與 MessagingApiBlob 客戶端"""
    if not LINE_CHANNEL_ACCESS_TOKEN:
        logger.warning("未配置 LINE_CHANNEL_ACCESS_TOKEN，Rich Menu 管理服務處於本機模擬模式。")
        return None
    configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
    api_client = ApiClient(configuration)
    return MessagingApi(api_client), MessagingApiBlob(api_client)


def build_rich_menu_request() -> RichMenuRequest:
    """
    建構 2500x1686 2x2 四大板塊之 RichMenuRequest 物件：
    - 左上 (0, 0, 1250, 843): 👉 我要預約
    - 右上 (1250, 0, 1250, 843): 📋 預約查詢
    - 左下 (0, 843, 1250, 843): 💰 票價試算
    - 右下 (1250, 843, 1250, 843): 📞 專人客服
    """
    areas = [
        # 1. 我要預約
        RichMenuArea(
            bounds=RichMenuBounds(x=0, y=0, width=HALF_W, height=HALF_H),
            action=MessageAction(label="我要預約", text="👉 我要預約")
        ),
        # 2. 預約查詢
        RichMenuArea(
            bounds=RichMenuBounds(x=HALF_W, y=0, width=HALF_W, height=HALF_H),
            action=MessageAction(label="預約查詢", text="📋 預約查詢")
        ),
        # 3. 票價試算
        RichMenuArea(
            bounds=RichMenuBounds(x=0, y=HALF_H, width=HALF_W, height=HALF_H),
            action=MessageAction(label="票價試算", text="💰 票價試算")
        ),
        # 4. 專人客服
        RichMenuArea(
            bounds=RichMenuBounds(x=HALF_W, y=HALF_H, width=HALF_W, height=HALF_H),
            action=MessageAction(label="專人客服", text="📞 專人客服")
        ),
    ]

    return RichMenuRequest(
        size=RichMenuSize(width=MENU_WIDTH, height=MENU_HEIGHT),
        selected=True,
        name=RICH_MENU_NAME,
        chat_bar_text=RICH_MENU_CHAT_BAR_TEXT,
        areas=areas
    )


def create_rich_menu(api: Optional[MessagingApi] = None) -> Optional[str]:
    """向 LINE 註冊 Rich Menu 並取得生成的 rich_menu_id"""
    req = build_rich_menu_request()
    if not api:
        logger.info(f"[模擬註冊] 已模擬建立 Rich Menu：{RICH_MENU_NAME}")
        return "mock_rich_menu_id_12345"

    try:
        res = api.create_rich_menu(req)
        logger.info(f"成功向 LINE 註冊 Rich Menu，ID: {res.rich_menu_id}")
        return res.rich_menu_id
    except Exception as e:
        logger.error(f"建立 Rich Menu 失敗：{e}")
        return None


def upload_rich_menu_image(rich_menu_id: str, image_bytes: bytes, blob_api: Optional[MessagingApiBlob] = None) -> bool:
    """上傳圖片至指定的 Rich Menu"""
    if not blob_api:
        logger.info(f"[模擬上傳] rich_menu_id={rich_menu_id} 上傳圖片成功 (大小: {len(image_bytes)} bytes)")
        return True

    try:
        blob_api.set_rich_menu_image(
            rich_menu_id=rich_menu_id,
            body=image_bytes,
            _headers={"Content-Type": "image/png"}
        )
        logger.info(f"成功上傳 Rich Menu 圖片至 {rich_menu_id}")
        return True
    except Exception as e:
        logger.error(f"上傳 Rich Menu 圖片失敗：{e}")
        return False


def set_default_rich_menu(rich_menu_id: str, api: Optional[MessagingApi] = None) -> bool:
    """將指定的 Rich Menu 設為官方全域預設選單"""
    if not api:
        logger.info(f"[模擬設為預設] rich_menu_id={rich_menu_id} 已設為全域預設")
        return True

    try:
        api.set_default_rich_menu(rich_menu_id)
        logger.info(f"成功將 {rich_menu_id} 設為官方預設 Rich Menu")
        return True
    except Exception as e:
        logger.error(f"設定預設 Rich Menu 失敗：{e}")
        return False


def get_default_rich_menu_id(api: Optional[MessagingApi] = None) -> Optional[str]:
    """查詢當前官方全域預設的 Rich Menu ID"""
    if not api:
        return "mock_rich_menu_id_12345"
    try:
        res = api.get_default_rich_menu_id()
        return res.rich_menu_id
    except Exception as e:
        logger.debug(f"目前無預設 Rich Menu 或查詢失敗：{e}")
        return None


def delete_all_rich_menus(api: Optional[MessagingApi] = None) -> int:
    """刪除 LINE 後台該 Channel 下所有舊版 Rich Menu"""
    if not api:
        logger.info("[模擬清理] 已清理所有舊版 Rich Menu")
        return 0

    deleted_count = 0
    try:
        menu_list = api.get_rich_menu_list()
        for item in menu_list.rich_menus:
            try:
                api.delete_rich_menu(item.rich_menu_id)
                deleted_count += 1
                logger.info(f"已清理舊版 Rich Menu：{item.rich_menu_id} ({item.name})")
            except Exception as de:
                logger.warning(f"刪除 Rich Menu ({item.rich_menu_id}) 失敗：{de}")
    except Exception as e:
        logger.error(f"取得 Rich Menu 清單失敗：{e}")
    return deleted_count


def sync_default_rich_menu(force: bool = False) -> Dict[str, Any]:
    """
    一鍵同步並設定全域預設圖文選單：
    1. 產生高解析度選單圖
    2. 向 LINE 建立 Rich Menu
    3. 上傳選單圖片
    4. 設為官方全域預設
    5. 清理多餘舊版選單
    """
    client_tuple = get_messaging_client()
    api = client_tuple[0] if client_tuple else None
    blob_api = client_tuple[1] if client_tuple else None

    # 1. 產生圖片二進制內容
    logger.info("正在動態生成 Rich Menu 圖片...")
    img_bytes = generate_rich_menu_image()

    # 2. 若非強制更新，先檢查當前預設選單是否已是最新版本
    if api and not force:
        current_default_id = get_default_rich_menu_id(api)
        if current_default_id:
            try:
                curr_menu = api.get_rich_menu(current_default_id)
                if curr_menu and curr_menu.name == RICH_MENU_NAME:
                    logger.info(f"當前預設 Rich Menu 已為最新版本 ({current_default_id})，略過重新建立。")
                    return {
                        "status": "already_up_to_date",
                        "rich_menu_id": current_default_id,
                        "message": "圖文選單已是最新版"
                    }
            except Exception as e:
                logger.debug(f"檢查當前預設選單資訊失敗，將繼續重新建立：{e}")

    # 3. 建立 Rich Menu
    menu_id = create_rich_menu(api)
    if not menu_id:
        return {"status": "error", "message": "建立 Rich Menu 失敗"}

    # 4. 上傳圖片
    uploaded = upload_rich_menu_image(menu_id, img_bytes, blob_api)
    if not uploaded:
        return {"status": "error", "message": "上傳 Rich Menu 圖片失敗"}

    # 5. 設為官方預設
    set_ok = set_default_rich_menu(menu_id, api)
    if not set_ok:
        return {"status": "error", "message": "設定預設 Rich Menu 失敗"}

    # 6. 清理其餘舊版 Rich Menu (保留剛建立的 menu_id)
    old_deleted = 0
    if api:
        try:
            menu_list = api.get_rich_menu_list()
            for item in menu_list.rich_menus:
                if item.rich_menu_id != menu_id:
                    try:
                        api.delete_rich_menu(item.rich_menu_id)
                        old_deleted += 1
                    except Exception:
                        pass
            logger.info(f"已清理 {old_deleted} 個舊版 Rich Menu")
        except Exception as e:
            logger.debug(f"清理舊版選單時發生小錯誤：{e}")

    logger.info(f"🎉 Rich Menu 全域預設選單同步完成！ID: {menu_id}")
    return {
        "status": "success",
        "rich_menu_id": menu_id,
        "name": RICH_MENU_NAME,
        "deleted_old_count": old_deleted,
        "message": "Rich Menu 建立、圖片上傳並設為預設完成"
    }
