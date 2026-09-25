"""
LINE Rich Menu (圖文選單) 視覺圖片動態生成模組 (rich_menu_generator.py)

根據 LINE 官方圖文選單規格，生成 2500 x 1686 (2x2 矩陣版型) 之高解析度專業選單圖片：
- 區域 1 (左上)：👉 我要預約 (立即線上團體預約，滿20人享優惠)
- 區域 2 (右上)：📋 預約查詢 (即時查詢預約狀態與線上取消)
- 區域 3 (左下)：💰 票價試算 (園區門票、優惠與免票說明)
- 區域 4 (右下)：📞 專人客服 (一對一專員接待與電話諮詢)
"""
import io
import os
import logging
from typing import Optional, Tuple
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger("rich_menu_generator")

# LINE 官方建議標準大圖選單尺寸
MENU_WIDTH = 2500
MENU_HEIGHT = 1686

# 4 個區塊定義 (x, y, w, h)
HALF_W = MENU_WIDTH // 2  # 1250
HALF_H = MENU_HEIGHT // 2  # 843

AREAS = [
    {
        "id": "booking",
        "title": "👉 我要預約",
        "subtitle": "20人成團享專屬優惠 ‧ 線上即時填單",
        "badge": "快速通關",
        "bg_color": (230, 81, 0),        # 活力深橘
        "accent_color": (255, 183, 77),   # 淺亮橘
        "icon_symbol": "🎡",
        "rect": (0, 0, HALF_W, HALF_H)
    },
    {
        "id": "query",
        "title": "📋 預約查詢",
        "subtitle": "即時掌握訂單詳情 ‧ 自主改期與取消",
        "badge": "訂單查詢",
        "bg_color": (0, 105, 92),        # 沉穩墨綠
        "accent_color": (128, 203, 196),  # 淺綠色
        "icon_symbol": "📄",
        "rect": (HALF_W, 0, HALF_W, HALF_H)
    },
    {
        "id": "pricing",
        "title": "💰 票價試算",
        "subtitle": "各票種門票費用 ‧ 隨隊司領免票說明",
        "badge": "費用公開",
        "bg_color": (2, 119, 189),       # 湛藍海灣
        "accent_color": (129, 212, 250),  # 天藍色
        "icon_symbol": "🎟️",
        "rect": (0, HALF_H, HALF_W, HALF_H)
    },
    {
        "id": "service",
        "title": "📞 專人客服",
        "subtitle": "專業業務專員接待 ‧ 一對一即時諮詢",
        "badge": "真人專線",
        "bg_color": (69, 39, 160),       # 尊榮深紫
        "accent_color": (179, 157, 219),  # 淺紫色
        "icon_symbol": "🧑‍💼",
        "rect": (HALF_W, HALF_H, HALF_W, HALF_H)
    }
]


def _find_system_font(size: int) -> ImageFont.ImageFont:
    """嘗試載入繁體中文字型，若無則降級為預設字型"""
    font_candidates = [
        # Windows
        "C:/Windows/Fonts/msjhbd.ttc",  # 微軟正黑體 粗體
        "C:/Windows/Fonts/msjh.ttc",    # 微軟正黑體
        "C:/Windows/Fonts/mingliu.ttc", # 細明體
        "C:/Windows/Fonts/simsun.ttc",  # 宋體
        "C:/Windows/Fonts/arial.ttf",
        # Linux (Ubuntu / Debian / Render)
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansTC-Bold.otf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]

    for path in font_candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size=size)
            except Exception as e:
                logger.debug(f"字型載入失敗 ({path}): {e}")

    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def generate_rich_menu_image(output_path: Optional[str] = None) -> bytes:
    """
    動態繪製高品質 2500x1686 2x2 LINE 圖文選單圖片，並回傳 PNG 二進制資料。
    若指定 output_path，同時會儲存至該路徑。
    """
    img = Image.new("RGB", (MENU_WIDTH, MENU_HEIGHT), color=(245, 247, 250))
    draw = ImageDraw.Draw(img)

    # 載入不同尺寸字型
    title_font = _find_system_font(size=86)
    sub_font = _find_system_font(size=44)
    badge_font = _find_system_font(size=36)

    card_padding = 18

    for area in AREAS:
        x, y, w, h = area["rect"]
        bx1 = x + card_padding
        by1 = y + card_padding
        bx2 = x + w - card_padding
        by2 = y + h - card_padding

        # 繪製主卡片背景 (圓角矩形)
        radius = 32
        draw.rounded_rectangle(
            [bx1, by1, bx2, by2],
            radius=radius,
            fill=area["bg_color"],
            outline=(255, 255, 255),
            width=4
        )

        # 頂部裝飾條
        accent_bar_h = 14
        draw.rounded_rectangle(
            [bx1 + 10, by1 + 6, bx2 - 10, by1 + 6 + accent_bar_h],
            radius=6,
            fill=area["accent_color"]
        )

        # 右上方微型標籤徽章 (Badge)
        badge_text = area["badge"]
        badge_box_w = 200
        badge_box_h = 58
        badge_x2 = bx2 - 40
        badge_x1 = badge_x2 - badge_box_w
        badge_y1 = by1 + 40
        badge_y2 = badge_y1 + badge_box_h

        draw.rounded_rectangle(
            [badge_x1, badge_y1, badge_x2, badge_y2],
            radius=16,
            fill=area["accent_color"]
        )
        draw.text(
            (badge_x1 + 25, badge_y1 + 8),
            badge_text,
            fill=(20, 20, 20),
            font=badge_font
        )

        # 主標題位置
        title_text = area["title"]
        title_x = bx1 + 60
        title_y = by1 + 240
        draw.text(
            (title_x, title_y),
            title_text,
            fill=(255, 255, 255),
            font=title_font
        )

        # 副標題位置
        sub_text = area["subtitle"]
        sub_y = title_y + 160
        draw.text(
            (title_x, sub_y),
            sub_text,
            fill=(235, 240, 245),
            font=sub_font
        )

        # 底部裝飾微光進度條指示
        dec_y = by2 - 60
        draw.rounded_rectangle(
            [title_x, dec_y, title_x + 360, dec_y + 8],
            radius=4,
            fill=area["accent_color"]
        )

    # 繪製中央十字分隔微光線
    divider_color = (255, 255, 255, 180)
    draw.line([(HALF_W, 0), (HALF_W, MENU_HEIGHT)], fill=divider_color, width=3)
    draw.line([(0, HALF_H), (MENU_WIDTH, HALF_H)], fill=divider_color, width=3)

    # 輸出為 PNG
    buffer = io.BytesIO()
    img.save(buffer, format="PNG", optimize=True)
    png_bytes = buffer.getvalue()

    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(png_bytes)
        logger.info(f"已成功將 Rich Menu 圖片輸出至：{output_path} (大小：{len(png_bytes):,} bytes)")

    return png_bytes
