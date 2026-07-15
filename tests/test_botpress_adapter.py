import hmac
import hashlib
from pathlib import Path
import asyncio
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python-backend"))

from adapters.botpress import BotpressAdapter
from adapters.base import MessageType, PlatformResponse


def _run(coro):
    return asyncio.run(coro)


def test_botpress_receive_message_text_payload():
    adapter = BotpressAdapter({"bot_id": "bot-01", "webhook_secret": ""})
    payload: dict[str, Any] = {
        "payload": {
            "type": "text",
            "text": "帮我查询订单",
            "conversationId": "conv-123",
            "messageId": "msg-1",
            "sender": {
                "id": "u-01",
                "name": "Alice",
                "isBot": False,
            },
        }
    }

    msg = _run(adapter.receive_message(payload))
    assert msg is not None
    assert msg.platform == "botpress"
    assert msg.chat_id == "conv-123"
    assert msg.message_type == MessageType.TEXT
    assert msg.user_id == "u-01"
    assert msg.user_name == "Alice"
    assert msg.text == "帮我查询订单"


def test_botpress_webhook_verify_with_hmac_secret():
    secret = "unit-secret"
    body = b'{"type":"text","text":"ok"}'
    signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    adapter = BotpressAdapter({"webhook_secret": secret})
    assert _run(adapter.verify_webhook(body, {"x-botpress-signature": f"sha256={signature}"})) is True
    assert _run(adapter.verify_webhook(body, {"x-botpress-signature": "wrong"})) is False


def test_botpress_format_response():
    adapter = BotpressAdapter({})
    resp = adapter.format_response("测试回复", {"chat_id": "conv-777", "reply_to": "m-1"})
    assert resp.chat_id == "conv-777"
    assert resp.text == "测试回复"
    assert resp.reply_to == "m-1"
    assert resp.message_type == MessageType.TEXT
