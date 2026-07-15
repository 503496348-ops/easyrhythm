"""
Botpress adapter (AtomCollide-智械工坊).

Supports:
- Incoming webhook payload normalization for Botpress custom integrations
- Outgoing message posting via Botpress HTTP API
- Optional webhook signature verification via secret

The implementation is intentionally conservative and does not assume a single
Botpress deployment shape: it accepts both message-level (`payload`) and event-level
(`event`) envelopes.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from typing import Any, Dict, Optional

import httpx

from .base import MessageType, PlatformAdapter, PlatformMessage, PlatformResponse

logger = logging.getLogger(__name__)


class BotpressAdapter(PlatformAdapter):
    """Botpress bot adapter."""

    platform_name = "botpress"

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self.api_base: str = config.get("api_base", "https://api.botpress.cloud")
        self.bot_id: str = config.get("bot_id", "")
        self.token: str = config.get("token", "")
        self.webhook_secret: str = config.get("webhook_secret", "")
        # Optional override; supports formatting placeholders.
        self.send_url_template: str = config.get(
            "message_send_url",
            "{api_base}/v1/bots/{bot_id}/conversations/{chat_id}/messages",
        )
        self._http_client: Optional[httpx.AsyncClient] = None

    @property
    def auth_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def start(self) -> None:
        await super().start()
        self._http_client = httpx.AsyncClient(timeout=30)

    async def stop(self) -> None:
        await super().stop()
        if self._http_client:
            await self._http_client.aclose()

    # ── Receive messages ──────────────────────────────────────────────

    async def receive_message(self, raw_event: Dict[str, Any]) -> Optional[PlatformMessage]:
        """
        Parse Botpress inbound payload into PlatformMessage.

        Supported examples:
          {"payload": {"type": "text", "text": "Hi", "conversationId": "c1", ...}}
          {"event": {...}}
          {...} direct message payload.
        """
        if not isinstance(raw_event, dict):
            return None

        payload = raw_event.get("payload") or raw_event.get("event") or raw_event
        if not isinstance(payload, dict):
            return None

        # Ignore platform/system events
        if payload.get("type") in {"system", "ack", "status"}:
            return None

        # Botpress sometimes indicates bot-originated messages with explicit field.
        sender = payload.get("sender") or payload.get("from") or {}
        is_bot = False
        if isinstance(sender, dict):
            is_bot = bool(sender.get("isBot", False) or sender.get("is_bot", False))
        elif isinstance(sender, str):
            is_bot = sender == self.bot_id and self.bot_id

        if is_bot:
            return None

        sender_id = ""
        sender_name = ""
        if isinstance(sender, dict):
            sender_id = str(sender.get("id", ""))
            sender_name = str(sender.get("name", "") or sender.get("email", ""))
        elif isinstance(sender, str):
            sender_id = sender

        message_id = str(payload.get("messageId", payload.get("id", "")))
        chat_id = str(payload.get("conversationId", payload.get("conversation_id", "")))
        raw_text = payload.get("text", "")

        # Fallback for payload shape where text is nested in content fields.
        if not raw_text and isinstance(payload.get("payload"), str):
            raw_text = payload.get("payload", "")
        if not raw_text and isinstance(payload.get("content"), dict):
            raw_text = payload.get("content", {}).get("text", "")

        attachments = payload.get("attachments") or []
        msg_type = MessageType.TEXT
        image_url = None
        file_url = None
        file_name = None

        if payload.get("type") == "image" or payload.get("mimeType", "").startswith("image/"):
            msg_type = MessageType.IMAGE
            image_url = payload.get("url")
        elif payload.get("type") in {"audio", "voice"}:
            msg_type = MessageType.AUDIO
            file_url = payload.get("url")
        elif payload.get("type") == "file" or (attachments and not raw_text):
            msg_type = MessageType.FILE
            if attachments:
                file_url = attachments[0].get("url")
                file_name = attachments[0].get("name")

        # Fallback plain text for quick bot replies
        text = str(raw_text).strip()

        ts = payload.get("timestamp")
        if isinstance(ts, (int, float)):
            timestamp = float(ts)
            if timestamp > 10_000_000_000:
                timestamp /= 1000
        else:
            timestamp = time.time()

        return PlatformMessage(
            message_id=message_id,
            platform=self.platform_name,
            chat_id=chat_id,
            user_id=sender_id,
            user_name=sender_name or sender_id,
            message_type=msg_type,
            text=text,
            raw_content=raw_event,
            timestamp=timestamp,
            is_group=payload.get("type") == "group",
            metadata={
                "conversation_id": chat_id,
                "event_type": payload.get("type", "message"),
                "payload_type": payload.get("type", ""),
                "raw_event": raw_event,
            },
            image_url=image_url,
            file_url=file_url,
            file_name=file_name,
        )

    # ── Send messages ─────────────────────────────────────────────────

    async def send_message(self, response: PlatformResponse) -> bool:
        """Send a Botpress message. Returns False when endpoint is unavailable."""
        if not self._http_client:
            self._http_client = httpx.AsyncClient(timeout=30)

        send_url = self.send_url_template.format(
            api_base=self.api_base,
            bot_id=self.bot_id,
            chat_id=response.chat_id,
            conversation_id=response.chat_id,
        )

        if not send_url:
            logger.error("Botpress send URL not configured")
            return False

        payload: Dict[str, Any] = {
            "type": "text",
            "text": response.text[:1200],
            "metadata": response.metadata,
        }
        # Optional card passthrough, mapped to Botpress custom payload when possible.
        if response.card_data:
            payload.update({"type": "cards", "content": response.card_data})

        resp = await self._http_client.post(send_url, headers=self.auth_headers, json=payload)
        if resp.status_code >= 300:
            logger.error(f"Botpress send failed: {resp.status_code} {resp.text}")
            return False
        return True

    # ── Format response ───────────────────────────────────────────────

    def format_response(self, text: str, context: Optional[Dict[str, Any]] = None) -> PlatformResponse:
        """Format agent output for Botpress (plain text by default)."""
        chat_id = (context or {}).get("chat_id", "")
        return PlatformResponse(
            chat_id=chat_id,
            text=text,
            message_type=MessageType.TEXT,
            reply_to=(context or {}).get("reply_to"),
            metadata=(context or {}).copy() if context else {},
        )

    # ── Webhook handling ─────────────────────────────────────────────

    async def handle_webhook(self, request_body: bytes, headers: Dict[str, str]) -> Dict[str, Any]:
        """Process inbound webhook and dispatch message."""
        try:
            body = json.loads(request_body)
        except json.JSONDecodeError:
            return {"error": "invalid json"}

        msg = await self.receive_message(body)
        if msg is not None:
            await self.dispatch_message(msg)
        return {"ok": True}

    async def verify_webhook(self, request_body: bytes, headers: Dict[str, str]) -> bool:
        """Verify webhook signature.

        Botpress custom webhooks commonly include `x-botpress-signature`.
        If secret is absent, verification is skipped for local/dev compatibility.
        """
        if not self.webhook_secret:
            return True

        sent = headers.get("x-botpress-signature") or headers.get("X-Botpress-Signature")
        if not sent:
            return False

        digest = hmac.new(
            self.webhook_secret.encode("utf-8"),
            request_body,
            hashlib.sha256,
        ).hexdigest()

        # Common format is raw hex or `sha256=<hex>`.
        if sent.startswith("sha256="):
            sent = sent.split("=", 1)[1]

        return hmac.compare_digest(sent, digest)
