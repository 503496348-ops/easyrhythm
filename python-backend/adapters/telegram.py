"""
Telegram Bot API adapter (AtomCollide-智械工坊)

Supports:
- Long polling or webhook mode
- Text, photo, document, voice messages
- Markdown/HTML formatting
- Inline keyboards via card_data

Requires config:
    bot_token: Telegram bot token from @BotFather
    webhook_url: (optional) Public URL for webhook mode
    parse_mode: "MarkdownV2" or "HTML" (default: "MarkdownV2")
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

import httpx

from .base import PlatformAdapter, PlatformMessage, PlatformResponse, MessageType

logger = logging.getLogger(__name__)


class TelegramAdapter(PlatformAdapter):
    """Telegram Bot API platform adapter."""

    platform_name = "telegram"
    API_BASE = "https://api.telegram.org"

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self.bot_token: str = config.get("bot_token", "")
        self.webhook_url: str = config.get("webhook_url", "")
        self.parse_mode: str = config.get("parse_mode", "MarkdownV2")
        self._http_client: Optional[httpx.AsyncClient] = None
        self._polling_offset: int = 0
        self._polling_task: Optional[asyncio.Task] = None

    @property
    def api_url(self) -> str:
        return f"{self.API_BASE}/bot{self.bot_token}"

    async def start(self) -> None:
        await super().start()
        self._http_client = httpx.AsyncClient(timeout=60)

        if self.webhook_url:
            await self._set_webhook()
            logger.info(f"Telegram webhook set to {self.webhook_url}")
        else:
            self._polling_task = asyncio.create_task(self._poll_loop())
            logger.info("Telegram long polling started")

    async def stop(self) -> None:
        await super().stop()
        if self._polling_task:
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass
        if self._http_client:
            await self._http_client.aclose()

    # ── Webhook management ────────────────────────────────────────────

    async def _set_webhook(self) -> None:
        resp = await self._http_client.post(
            f"{self.api_url}/setWebhook",
            json={"url": self.webhook_url, "allowed_updates": ["message", "edited_message"]},
        )
        data = resp.json()
        if not data.get("ok"):
            logger.error(f"Failed to set Telegram webhook: {data}")

    # ── Long polling ──────────────────────────────────────────────────

    async def _poll_loop(self) -> None:
        while self._running:
            try:
                resp = await self._http_client.get(
                    f"{self.api_url}/getUpdates",
                    params={"offset": self._polling_offset, "timeout": 30, "allowed_updates": ["message"]},
                )
                data = resp.json()
                if data.get("ok"):
                    for update in data.get("result", []):
                        self._polling_offset = update["update_id"] + 1
                        message = await self.receive_message(update)
                        if message:
                            await self.dispatch_message(message)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Telegram polling error")
                await asyncio.sleep(5)

    # ── Receive messages ──────────────────────────────────────────────

    async def receive_message(self, raw_event: Dict[str, Any]) -> Optional[PlatformMessage]:
        """Parse a Telegram update into a PlatformMessage."""
        msg = raw_event.get("message") or raw_event.get("edited_message")
        if not msg:
            return None

        # Skip bot messages
        from_user = msg.get("from", {})
        if from_user.get("is_bot"):
            return None

        chat = msg.get("chat", {})
        chat_id = str(chat.get("id", ""))
        chat_type = chat.get("type", "private")
        message_id = str(msg.get("message_id", ""))

        # Determine message type and content
        text = msg.get("text", "")
        msg_type = MessageType.TEXT
        image_url = None
        file_url = None
        file_name = None

        if "photo" in msg_type:
            msg_type = MessageType.IMAGE
            # Get the largest photo
            photos = msg.get("photo", [])
            if photos:
                image_url = photos[-1].get("file_id")
        elif "document" in msg:
            msg_type = MessageType.FILE
            doc = msg["document"]
            file_url = doc.get("file_id")
            file_name = doc.get("file_name", "file")
        elif "voice" in msg or "audio" in msg:
            msg_type = MessageType.AUDIO
        elif "sticker" in msg:
            msg_type = MessageType.STICKER

        # Handle photo caption as text
        if not text:
            text = msg.get("caption", "")

        # Parse entities for bot mentions
        entities = msg.get("entities", [])
        for entity in entities:
            if entity.get("type") == "mention":
                offset = entity["offset"]
                length = entity["length"]
                mention = text[offset:offset + length]
                text = text.replace(mention, "").strip()

        # Reply tracking
        reply_to = None
        if "reply_to_message" in msg:
            reply_to = str(msg["reply_to_message"].get("message_id", ""))

        return PlatformMessage(
            message_id=message_id,
            platform=self.platform_name,
            chat_id=chat_id,
            user_id=str(from_user.get("id", "")),
            user_name=from_user.get("username", from_user.get("first_name", "")),
            message_type=msg_type,
            text=text.strip(),
            raw_content=raw_event,
            timestamp=msg.get("date", time.time()),
            is_group=chat_type in ("group", "supergroup"),
            reply_to=reply_to,
            image_url=image_url,
            file_url=file_url,
            file_name=file_name,
            metadata={
                "chat_type": chat_type,
                "language_code": from_user.get("language_code"),
            },
        )

    # ── Send messages ─────────────────────────────────────────────────

    async def send_message(self, response: PlatformResponse) -> bool:
        """Send a message to a Telegram chat."""
        payload: Dict[str, Any] = {
            "chat_id": response.chat_id,
            "text": response.text[:4096],  # Telegram limit
        }

        if response.reply_to:
            payload["reply_to_message_id"] = int(response.reply_to)

        if response.card_data and "reply_markup" in response.card_data:
            payload["reply_markup"] = json.dumps(response.card_data["reply_markup"])

        # Try with parse_mode, fall back to plain text
        if self.parse_mode:
            payload["parse_mode"] = self.parse_mode

        resp = await self._http_client.post(
            f"{self.api_url}/sendMessage", json=payload
        )
        data = resp.json()

        if not data.get("ok"):
            # Retry without parse_mode if formatting fails
            if "parse_mode" in payload:
                del payload["parse_mode"]
                resp = await self._http_client.post(
                    f"{self.api_url}/sendMessage", json=payload
                )
                data = resp.json()

        if not data.get("ok"):
            logger.error(f"Telegram send failed: {data}")
            return False

        return True

    # ── Format response ───────────────────────────────────────────────

    def format_response(
        self, text: str, context: Optional[Dict[str, Any]] = None
    ) -> PlatformResponse:
        """Format agent text for Telegram (MarkdownV2 compatible)."""
        chat_id = (context or {}).get("chat_id", "")
        reply_to = (context or {}).get("reply_to")

        # Escape special MarkdownV2 characters
        if self.parse_mode == "MarkdownV2":
            text = self._escape_markdown_v2(text)

        return PlatformResponse(
            chat_id=chat_id,
            text=text,
            message_type=MessageType.TEXT,
            reply_to=reply_to,
        )

    @staticmethod
    def _escape_markdown_v2(text: str) -> str:
        """Escape special characters for Telegram MarkdownV2."""
        special_chars = r"_*[]()~`>#+-=|{}.!"
        result = []
        in_code = False
        i = 0
        while i < len(text):
            if text[i:i+3] == "```":
                in_code = not in_code
                result.append("```")
                i += 3
                continue
            if text[i] == "`" and not in_code:
                in_code = not in_code
                result.append("`")
                i += 1
                continue
            if not in_code and text[i] in special_chars:
                result.append(f"\\{text[i]}")
            else:
                result.append(text[i])
            i += 1
        return "".join(result)

    # ── Webhook handling ──────────────────────────────────────────────

    async def handle_webhook(self, request_body: bytes, headers: Dict[str, str]) -> Dict[str, Any]:
        """Process an incoming Telegram webhook update."""
        try:
            body = json.loads(request_body)
        except json.JSONDecodeError:
            return {"ok": False, "error": "invalid json"}

        message = await self.receive_message(body)
        if message:
            await self.dispatch_message(message)

        return {"ok": True}

    async def verify_webhook(self, request_body: bytes, headers: Dict[str, str]) -> bool:
        """Verify webhook request (Telegram uses secret_token header)."""
        secret = self.config.get("secret_token", "")
        if not secret:
            return True
        return headers.get("x-telegram-bot-api-secret-token") == secret
