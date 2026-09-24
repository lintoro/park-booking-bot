"""
測試 FastAPI 服務端點與 LINE Webhook (test_webhook_api.py)
"""
import json
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from app.main import app

client = TestClient(app)


def test_root_endpoint():
    """測試根路徑服務狀態"""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "Amusement Park Group Reservation" in data["service"]


def test_health_endpoint():
    """測試健康檢查端點"""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["code"] == 200


def test_webhook_invalid_signature():
    """測試非官方偽造請求簽章驗證失敗 (HTTP 400)"""
    # 模擬 LINE_CHANNEL_SECRET 存在的情境
    with patch("app.main.verify_signature", return_value=False):
        response = client.post(
            "/webhook",
            json={"events": []},
            headers={"X-Line-Signature": "invalid_fake_signature"}
        )
        assert response.status_code == 400
        assert "LINE 簽章驗證失敗" in response.json()["detail"]


def test_webhook_success_message_event():
    """測試合法 Webhook 訊息事件秒回 HTTP 200"""
    payload = {
        "destination": "Uxxxxxxxx",
        "events": [
            {
                "type": "message",
                "message": {
                    "type": "text",
                    "id": "1234567890",
                    "text": "預約"
                },
                "timestamp": 1620000000000,
                "source": {
                    "type": "user",
                    "userId": "Utestuser123"
                },
                "replyToken": "nHuyWiB7yP5Zw52FIkcQobQuGDXCTA",
                "mode": "active"
            }
        ]
    }

    with patch("app.main.verify_signature", return_value=True):
        with patch("app.main.send_reply", return_value=True) as mock_send:
            response = client.post(
                "/webhook",
                json=payload,
                headers={"X-Line-Signature": "valid_signature_dummy"}
            )
            assert response.status_code == 200
            assert response.json() == {"status": "received"}
