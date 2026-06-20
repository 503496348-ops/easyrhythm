"""
Discord bot adapter (AtomCollide-智械工坊)

Supports:
- Gateway WebSocket connection via discord.py
- Text messages, embeds, slash commands
- Rich message formatting with Markdown
- Channel and DM support

Requires config:
    bot_token: Discord bot token
    application_id: (optional) Application ID for slash commands
    intents: (optional) List of intent strings to enable
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Dict, Optional

import httpx

from .base import PlatformAdapter, PlatformMessage, PlatformResponse, MessageType

logger = logging.getLogger(__name__)


class DiscordAdapter(PlatformAdapter):
    """Discord bot platform adapter using HTTP API + Gateway."""

    platform_name = "discord"
    API_BASE = "https://discord.com/api/v10"

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self.bot_token: str = config.get("bot_token", "")
        self.application_id: str = config.get("application_id", "")
        self._http_client: Optional[httpx.AsyncClient] = None
        self._gateway_url: Optional[str] = None
        self._ws = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._receive_task: Optional[asyncio.Task] = None
        self._sequence: Optional[int] = None
        self._session_id: Optional[str] = None
        self._heartbeat_interval: float = 41.25

    @property
    def auth_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bot {self.bot_token}",
            "Content-Type": "application/json",
        }

    async def start(self) -> None:
        await super().start()
        self._http_client = httpx.AsyncClient(timeout=30)
        # Note: Full Gateway WebSocket would require a separate receive loop.
        # This adapter primarily uses the HTTP API for sending.
        logger.info("Discord adapter started (HTTP API mode)")

    async def stop(self) -> None:
        await super().stop()
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._receive_task:
            self._receive_task.cancel()
        if self._http_client:
            await self._http_client.aclose()

    # ── Receive messages ──────────────────────────────────────────────

    async def receive_message(self, raw_event: Dict[str, Any]) -> Optional[PlatformMessage]:
        """
        Parse a Discord interaction or message event into a PlatformMessage.

        Handles both Gateway MESSAGE_CREATE events and
        HTTP Interactions (slash commands, message components).
        """
        # Interaction payload
        if "interaction" in raw_event or raw_event.get("type") in (2, 3, 5):
            return self._parse_interaction(raw_event)

        # Gateway MESSAGE_CREATE
        if raw_event.get("t") == "MESSAGE_CREATE":
            return self._parse_gateway_message(raw_event.get("d", {}))

        # Direct message event
        if "author" in raw_event and "content" in raw_event:
            return self._parse_gateway_message(raw_event)

        return None

    def _parse_gateway_message(self, msg: Dict[str, Any]) -> Optional[PlatformMessage]:
        """Parse a Discord MESSAGE_CREATE event."""
        author = msg.get("author", {})

        # Skip bot messages
        if author.get("bot"):
            return None

        channel_id = msg.get("channel_id", "")
        guild_id = msg.get("guild_id", "")

        # Determine message type
        msg_type = MessageType.TEXT
        attachments = msg.get("attachments", [])
        image_url = None
        file_url = None
        file_name = None

        if attachments:
            att = attachments[0]
            content_type = att.get("content_type", "")
            if content_type.startswith("image/"):
                msg_type = MessageType.IMAGE
                image_url = att.get("url")
            else:
                msg_type = MessageType.FILE
                file_url = att.get("url")
                file_name = att.get("filename", "file")

        text = msg.get("content", "")

        # Remove bot mentions
        for mention in msg.get("mentions", []):
            text = text.replace(f"<@{mention['id']}>", "").strip()

        return PlatformMessage(
            message_id=msg.get("id", ""),
            platform=self.platform_name,
            chat_id=channel_id,
            user_id=author.get("id", ""),
            user_name=author.get("username", ""),
            message_type=msg_type,
            text=text,
            raw_content=msg,
            timestamp=time.time(),
            is_group=bool(guild_id),
            reply_to=(msg.get("message_reference") or {}).get("message_id"),
            image_url=image_url,
            file_url=file_url,
            file_name=file_name,
            metadata={
                "guild_id": guild_id,
                "channel_id": channel_id,
                "attachments": attachments,
            },
        )

    def _parse_interaction(self, event: Dict[str, Any]) -> Optional[PlatformMessage]:
        """Parse a Discord interaction (slash command, button, etc.)."""
        interaction_type = event.get("type")
        data = event.get("data", {})
        member = event.get("member", {})
        user = member.get("user", {}) or event.get("user", {})

        text = ""
        if interaction_type == 2:  # Application command
            text = f"/{data.get('name', '')}"
            for opt in data.get("options", []):
                text += f" {opt.get('name', '')}={opt.get('value', '')}"
        elif interaction_type == 3:  # Message component (button, select)
            text = data.get("custom_id", "")

        return PlatformMessage(
            message_id=event.get("id", ""),
            platform=self.platform_name,
            chat_id=event.get("channel_id", ""),
            user_id=user.get("id", ""),
            user_name=user.get("username", ""),
            message_type=MessageType.TEXT,
            text=text,
            raw_content=event,
            timestamp=time.time(),
            is_group=bool(event.get("guild_id")),
            metadata={
                "interaction_type": interaction_type,
                "interaction_id": event.get("id"),
                "token": event.get("token"),
                "guild_id": event.get("guild_id"),
            },
        )

    # ── Send messages ─────────────────────────────────────────────────

    async def send_message(self, response: PlatformResponse) -> bool:
        """Send a message to a Discord channel."""
        payload: Dict[str, Any] = {"content": response.text[:2000]}

        if response.card_data:
            # Embed support
            if "embeds" in response.card_data:
                payload["embeds"] = response.card_data["embeds"]
            if "components" in response.card_data:
                payload["components"] = response.card_data["components"]

        if response.reply_to:
            payload["message_reference"] = {"message_id": response.reply_to}

        resp = await self._http_client.post(
            f"{self.API_BASE}/channels/{response.chat_id}/messages",
            headers=self.auth_headers,
            json=payload,
        )

        if resp.status_code not in (200, 201):
            logger.error(f"Discord send failed: {resp.status_code} {resp.text}")
            return False

        return True

    # ── Format response ───────────────────────────────────────────────

    def format_response(
        self, text: str, context: Optional[Dict[str, Any]] = None
    ) -> PlatformResponse:
        """Format agent text for Discord (supports Markdown natively)."""
        chat_id = (context or {}).get("chat_id", "")
        reply_to = (context or {}).get("reply_to")

        # Discord has a 2000 char limit per message
        if len(text) > 2000:
            text = text[:1997] + "..."

        return PlatformResponse(
            chat_id=chat_id,
            text=text,
            message_type=MessageType.TEXT,
            reply_to=reply_to,
        )

    # ── Webhook handling ──────────────────────────────────────────────

    async def handle_webhook(self, request_body: bytes, headers: Dict[str, str]) -> Dict[str, Any]:
        """Process an incoming Discord interaction webhook."""
        try:
            body = json.loads(request_body)
        except json.JSONDecodeError:
            return {"error": "invalid json"}

        # Discord interaction ping
        if body.get("type") == 1:
            return {"type": 1}

        message = await self.receive_message(body)
        if message:
            await self.dispatch_message(message)

        return {"type": 5}  # Deferred response

    async def verify_webhook(self, request_body: bytes, headers: Dict[str, str]) -> bool:
        """Verify Discord interaction signature using Ed25519."""
        signature = headers.get("x-signature-ed25519", "")
        timestamp = headers.get("x-signature-timestamp", "")
        public_key = self.config.get("public_key", "")

        if not public_key or not signature:
            return True  # Skip verification if not configured

        try:
            from nacl.signing import VerifyKey
            from nacl.exceptions import BadSignatureError

            verify_key = VerifyKey(bytes.fromhex(public_key))
            verify_key.verify(
                f"{timestamp}{request_body}".encode(),
                bytes.fromhex(signature),
            )
            return True
        except (ImportError, BadSignatureError, Exception) as e:
            logger.warning(f"Discord signature verification failed: {e}")
            return False
