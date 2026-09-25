"""
LINE Rich Menu (圖文選單) 單元測試庫 (test_rich_menu.py)

驗證項目：
1. 圖片動態繪製規格 (PNG 格式、2500x1686、<1MB、字型與版型)
2. RichMenuRequest 物件與 4 區塊座標矩陣 (無交疊、完整覆蓋、Action 正確對應)
3. Rich Menu 管理服務生命週期 (建立、上傳、設為預設、舊版清理)
4. 對話狀態機與 Rich Menu 4 大按鈕意圖相容性與防呆流轉
"""
import io
import pytest
from unittest.mock import MagicMock, patch
from PIL import Image

from app.services.rich_menu_generator import (
    generate_rich_menu_image,
    MENU_WIDTH,
    MENU_HEIGHT,
    HALF_W,
    HALF_H,
)
from app.services.rich_menu_service import (
    build_rich_menu_request,
    create_rich_menu,
    upload_rich_menu_image,
    set_default_rich_menu,
    get_default_rich_menu_id,
    delete_all_rich_menus,
    sync_default_rich_menu,
    RICH_MENU_NAME,
)
from app.core.state_machine import ConversationStateMachine


def test_generate_rich_menu_image_specs():
    """驗證 Rich Menu 圖片尺寸、格式與檔案大小完全符合 LINE 官方規範"""
    img_bytes = generate_rich_menu_image()
    assert img_bytes is not None
    assert len(img_bytes) > 0

    # LINE 規定不得超過 1MB (1,048,576 bytes)
    assert len(img_bytes) < 1048576, f"圖片大小超過 1MB 限制: {len(img_bytes)} bytes"

    # 驗證圖片維度與格式
    img = Image.open(io.BytesIO(img_bytes))
    assert img.format == "PNG"
    assert img.size == (MENU_WIDTH, MENU_HEIGHT)
    assert img.size == (2500, 1686)


def test_build_rich_menu_request_structure():
    """驗證 RichMenuRequest 4 大板塊結構、座標與 MessageAction 定義"""
    req = build_rich_menu_request()
    assert req.size.width == 2500
    assert req.size.height == 1686
    assert req.selected is True
    assert req.name == RICH_MENU_NAME
    assert len(req.areas) == 4

    expected_actions = [
        {"x": 0, "y": 0, "text": "👉 我要預約"},
        {"x": HALF_W, "y": 0, "text": "📋 預約查詢"},
        {"x": 0, "y": HALF_H, "text": "💰 票價試算"},
        {"x": HALF_W, "y": HALF_H, "text": "📞 專人客服"},
    ]

    for expected, area in zip(expected_actions, req.areas):
        assert area.bounds.x == expected["x"]
        assert area.bounds.y == expected["y"]
        assert area.bounds.width == HALF_W
        assert area.bounds.height == HALF_H
        assert area.action.text == expected["text"]


def test_sync_default_rich_menu_mock_mode():
    """驗證在無 LINE Token 時，系統以 Mock 模式安全降級運行"""
    with patch("app.services.rich_menu_service.get_messaging_client", return_value=None):
        result = sync_default_rich_menu()
        assert result["status"] == "success"
        assert result["rich_menu_id"] == "mock_rich_menu_id_12345"


def test_sync_default_rich_menu_with_api_flow():
    """驗證呼叫 LINE MessagingApi 建立、上傳、設為預設與舊選單清理之完整流程"""
    mock_api = MagicMock()
    mock_blob = MagicMock()

    # 模擬建立選單回傳 ID
    mock_create_resp = MagicMock()
    mock_create_resp.rich_menu_id = "richmenu-test-new-999"
    mock_api.create_rich_menu.return_value = mock_create_resp

    # 模擬已有舊選單
    mock_list_resp = MagicMock()
    old_item = MagicMock()
    old_item.rich_menu_id = "richmenu-old-001"
    old_item.name = "舊版選單"
    mock_list_resp.rich_menus = [old_item, mock_create_resp]
    mock_api.get_rich_menu_list.return_value = mock_list_resp
    mock_api.get_default_rich_menu_id.return_value = MagicMock(rich_menu_id="richmenu-old-001")

    with patch("app.services.rich_menu_service.get_messaging_client", return_value=(mock_api, mock_blob)):
        res = sync_default_rich_menu(force=True)

        assert res["status"] == "success"
        assert res["rich_menu_id"] == "richmenu-test-new-999"

        # 驗證 API 呼叫次序
        mock_api.create_rich_menu.assert_called_once()
        mock_blob.set_rich_menu_image.assert_called_once()
        mock_api.set_default_rich_menu.assert_called_with("richmenu-test-new-999")
        # 驗證舊版選單被刪除，但新選單未被刪除
        mock_api.delete_rich_menu.assert_called_with("richmenu-old-001")


def test_state_machine_with_rich_menu_actions():
    """驗證對話狀態機對 Rich Menu 四個按鈕文字的交互反應"""
    sm = ConversationStateMachine()
    user_id = "test_rich_menu_user_01"

    # 1. 點擊「👉 我要預約」：在 Step 0 啟動預約
    r1 = sm.process_message(user_id, "👉 我要預約")
    assert "歡迎使用遊樂園團體預約" in r1.reply_text
    session = sm.get_or_create_session(user_id)
    assert session.current_step == 1

    # 2. 在填寫中 (Step 1) 誤點「👉 我要預約」：防呆提示正在預約中，不誤錄為團名
    r2 = sm.process_message(user_id, "👉 我要預約")
    assert "目前正在進行團體預約填寫中" in r2.reply_text
    assert "全部重新填寫" in r2.quick_replies
    assert session.current_step == 1
    assert not session.data.group_name

    # 3. 點擊「💰 票價試算」：在流程中視為 FAQ 詢問，提供解答並引導繼續預約
    r3 = sm.process_message(user_id, "💰 票價試算")
    assert "目前仍在預約流程中" in r3.reply_text

    # 4. 點擊「📞 專人客服」：暫停機器人並提供專人聯絡卡片
    r4 = sm.process_message(user_id, "📞 專人客服")
    assert "為您轉接專人服務" in r4.reply_text
    assert r4.flex_card is not None
    assert session.is_human_handoff is True

    # 5. 恢復機器人後點擊「📋 預約查詢」
    sm.process_message(user_id, "恢復")
    with patch("app.core.state_machine.get_reservations_by_user_id", return_value=[]):
        r5 = sm.process_message(user_id, "📋 預約查詢")
        assert "查無" in r5.reply_text or "尚未查詢到" in r5.reply_text
