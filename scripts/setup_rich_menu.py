"""
LINE Rich Menu (圖文選單) 自動化管理與同步 CLI 工具 (setup_rich_menu.py)

使用方式：
1. 一鍵自動同步與設定預設圖文選單：
   python scripts/setup_rich_menu.py

2. 強制重新生成並覆蓋預設選單：
   python scripts/setup_rich_menu.py --force

3. 僅匯出預覽圖片至本機檔案：
   python scripts/setup_rich_menu.py --export-image [app/static/rich_menu.png]

4. 查詢當前線上所有 Rich Menu 清單：
   python scripts/setup_rich_menu.py --list

5. 清理線上所有 Rich Menu：
   python scripts/setup_rich_menu.py --delete-all
"""
import sys
import os
import argparse
import logging

# 確保可引用根目錄 app 模組
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.rich_menu_generator import generate_rich_menu_image
from app.services.rich_menu_service import (
    sync_default_rich_menu,
    get_messaging_client,
    get_default_rich_menu_id,
    delete_all_rich_menus,
    RICH_MENU_NAME,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("setup_rich_menu")


def main():
    parser = argparse.ArgumentParser(description="遊樂園團體預約 LINE Rich Menu 管理工具")
    parser.add_argument("--force", action="store_true", help="強制重新建立並覆蓋現有預設 Rich Menu")
    parser.add_argument("--export-image", nargs="?", const="app/static/rich_menu.png", help="僅生成並匯出 Rich Menu 圖片至指定路徑")
    parser.add_argument("--list", action="store_true", help="列出 LINE 後台現存的所有 Rich Menu")
    parser.add_argument("--delete-all", action="store_true", help="刪除 LINE 後台現存的所有 Rich Menu")

    args = parser.parse_args()

    # 1. 僅匯出圖片
    if args.export_image:
        output_path = args.export_image
        logger.info(f"🎨 正在繪製 Rich Menu 圖片並匯出至 {output_path}...")
        img_bytes = generate_rich_menu_image(output_path=output_path)
        logger.info(f"✅ 圖片匯出成功！大小：{len(img_bytes):,} bytes")
        return

    client_tuple = get_messaging_client()
    api = client_tuple[0] if client_tuple else None

    # 2. 列出所有選單
    if args.list:
        if not api:
            logger.warning("未配置 LINE_CHANNEL_ACCESS_TOKEN，無法查詢線上 Rich Menu 清單。")
            return
        default_id = get_default_rich_menu_id(api)
        logger.info(f"📌 當前官方預設 Rich Menu ID: {default_id or '無'}")
        menu_list = api.get_rich_menu_list()
        logger.info(f"共查詢到 {len(menu_list.rich_menus)} 個 Rich Menu：")
        for m in menu_list.rich_menus:
            is_def = "(🌟 預設中)" if m.rich_menu_id == default_id else ""
            logger.info(f" - [{m.rich_menu_id}] {m.name} {is_def}")
        return

    # 3. 清理所有選單
    if args.delete_all:
        logger.info("⚠️ 準備清理所有 Rich Menu...")
        deleted = delete_all_rich_menus(api)
        logger.info(f"✅ 已成功刪除 {deleted} 個 Rich Menu。")
        return

    # 4. 預設模式：自動同步圖文選單
    logger.info("🚀 啟動 Rich Menu 自動同步作業...")
    result = sync_default_rich_menu(force=args.force)
    logger.info(f"執行結果：{result}")


if __name__ == "__main__":
    main()
