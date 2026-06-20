"""
Feishu/Lark platform adapter (AtomCollide-智械工坊)

Supports:
- Receiving messages via webhook (Event Subscription)
- Sending messages via Bot API (lark-oapi)
- Card messages for rich interactive responses
- Group and direct message handling

Requires config:
    app_id: Feishu app ID
    app_secret: Feishu app secret
    verification_token: Event subscription verification token
    encrypt_key: (optional) Event encryption key
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from typing import Any, Dict, Optional

import httpx

from .base import PlatformAdapter, PlatformMessage, PlatformResponse, MessageType

logger = logging.getLogger(__name__)


class FeishuAdapter(PlatformAdapter):
    """Feishu/Lark messaging platform adapter."""

    platform_name = "feishu"

    BASE_URL = "https://open.feishu.cn/open-apis"

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self.app_id: str = config.get("app_id", "")
        self.app_secret: str = config.get("app_secret", "")
        self.verification_token: str = config.get("verification_token", "")
        self.encrypt_key: str = config.get("encrypt_key", "")

        self._tenant_access_token: Optional[str] = None
        self._token_expires_at: float = 0
        self._http_client: Optional[httpx.AsyncClient] = None

    async def start(self) -> None:
        await super().start()
        self._http_client = httpx.AsyncClient(timeout=30)
        await self._refresh_token()
        logger.info("Feishu adapter started, tenant token acquired")

    async def stop(self) -> None:
        await super().stop()
        if self._http_client:
            await self._http_client.aclose()

    # ── Token management ──────────────────────────────────────────────

    async def _refresh_token(self) -> str:
        """Obtain or refresh the tenant access token."""
        if self._tenant_access_token and time.time() < self._token_expires_at - 60:
            return self._tenant_access_token

        resp = await self._http_client.post(
            f"{self.BASE_URL}/auth/v3/tenant_access_token/internal",
            json={"app_id": self.app_id, "app_secret": self.app_secret},
        )
        data = resp.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Failed to get Feishu tenant token: {data}")

        self._tenant_access_token = data["tenant_access_token"]
        self._token_expires_at = time.time() + data.get("expire", 7200)
        return self._tenant_access_token

    async def _get_headers(self) -> Dict[str, str]:
        token = await self._refresh_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }

    # ── Receive messages ──────────────────────────────────────────────

    async def receive_message(self, raw_event: Dict[str, Any]) -> Optional[PlatformMessage]:
        """
        Parse a Feishu event callback into a PlatformMessage.

        Handles:
        - URL verification challenges
        - im.message.receive_v1 events
        """
        # URL verification challenge
        if raw_event.get("type") == "url_verification":
            # Caller should respond with {"challenge": ...}
            return None

        # Extract event header and event body
        header = raw_event.get("header", {})
        event = raw_event.get("event", {})
        event_type = header.get("event_type", "")

        if event_type != "im.message.receive_v1":
            logger.debug(f"Ignoring Feishu event type: {event_type}")
            return None

        message = event.get("message", {})
        sender = event.get("sender", {})
        sender_id = sender.get("sender_id", {})

        msg_type = message.get("message_type", "text")
        chat_id = message.get("chat_id", "")
        chat_type = message.get("chat_type", "p2p")
        message_id = message.get("message_id", "")

        # Parse content
        content_str = message.get("content", "{}")
        try:
            content = json.loads(content_str)
        except json.JSONDecodeError:
            content = {"text": content_str}

        text = content.get("text", "")

        # Remove @bot mentions
        mentions = message.get("mentions", [])
        for mention in mentions:
            key = mention.get("key", "")
            if key:
                text = text.replace(key, "").strip()

        # Map message type
        type_map = {
            "text": MessageType.TEXT,
            "image": MessageType.IMAGE,
            "file": MessageType.FILE,
            "audio": MessageType.AUDIO,
            "sticker": MessageType.STICKER,
        }

        return PlatformMessage(
            message_id=message_id,
            platform=self.platform_name,
            chat_id=chat_id,
            user_id=sender_id.get("open_id", ""),
            user_name=sender_id.get("open_id", ""),
            message_type=type_map.get(msg_type, MessageType.TEXT),
            text=text,
            raw_content=raw_event,
            timestamp=time.time(),
            is_group=chat_type == "group",
            metadata={
                "chat_type": chat_type,
                "msg_type": msg_type,
                "root_id": message.get("root_id"),
                "parent_id": message.get("parent_id"),
            },
        )

    # ── Send messages ─────────────────────────────────────────────────

    async def send_message(self, response: PlatformResponse) -> bool:
        """Send a message to a Feishu chat."""
        headers = await self._get_headers()

        if response.card_data:
            content = json.dumps(response.card_data)
            msg_type = "interactive"
        elif response.image_url:
            # Need image_key; for URLs, use post message with image tag
            content = json.dumps({"text": response.text})
            msg_type = "text"
        else:
            content = json.dumps({"text": response.text})
            msg_type = "text"

        payload = {
            "receive_id": response.chat_id,
            "msg_type": msg_type,
            "content": content,
        }

        url = f"{self.BASE_URL}/im/v1/messages"
        params = {"receive_id_type": "chat_id"}

        resp = await self._http_client.post(
            url, headers=headers, json=payload, params=params
        )
        data = resp.json()

        if data.get("code") != 0:
            logger.error(f"Feishu send failed: {data}")
            return False

        return True

    # ── Format response ───────────────────────────────────────────────

    def format_response(
        self, text: str, context: Optional[Dict[str, Any]] = None
    ) -> PlatformResponse:
        """Format agent text output for Feishu (supports basic Markdown)."""
        chat_id = (context or {}).get("chat_id", "")
        reply_to = (context or {}).get("reply_to")

        return PlatformResponse(
            chat_id=chat_id,
            text=text,
            message_type=MessageType.TEXT,
            reply_to=reply_to,
        )

    # ── Webhook handling ──────────────────────────────────────────────

    async def handle_webhook(self, request_body: bytes, headers: Dict[str, str]) -> Dict[str, Any]:
        """
        Process an incoming webhook request from Feishu.
        Returns a dict to be used as the HTTP response.
        """
        try:
            body = json.loads(request_body)
        except json.JSONDecodeError:
            return {"error": "invalid json"}

        # URL verification
        if body.get("type") == "url_verification":
            return {"challenge": body.get("challenge", "")}

        # Decrypt if needed
        if self.encrypt_key and "encrypt" in body:
            body = self._decrypt(body["encrypt"])

        message = await self.receive_message(body)
        if message:
            await self.dispatch_message(message)

        return {"code": 0, "msg": "ok"}

    def _decrypt(self, encrypted: str) -> Dict[str, Any]:
        """Decrypt Feishu encrypted event payload."""
        import base64
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        from cryptography.hazmat.backends import default_backend

        key = hashlib.sha256(self.encrypt_key.encode()).digest()
        enc = base64.b64decode(encrypted)
        iv = enc[:16]
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        dec = cipher.decryptor()
        plaintext = dec.update(enc[16:]) + dec.finalize()
        # Remove PKCS7 padding
        pad_len = plaintext[-1]
        plaintext = plaintext[:-pad_len]
        return json.loads(plaintext.decode("utf-8"))

    async def verify_webhook(self, request_body: bytes, headers: Dict[str, str]) -> bool:
        """Verify that a webhook request is from Feishu."""
        if not self.verification_token:
            return True
        try:
            body = json.loads(request_body)
            token = body.get("header", {}).get("token", "") or body.get("token", "")
            return token == self.verification_token
        except Exception:
            return False
