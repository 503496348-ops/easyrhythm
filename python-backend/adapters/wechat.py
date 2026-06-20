"""
WeChat Official Account adapter (AtomCollide-智械工坊)

Supports:
- Receiving messages via server-side webhook
- Replying via passive response or Customer Service API
- Text, image, voice, video, and event messages
- Token management for API access

Requires config:
    app_id: WeChat Official Account AppID
    app_secret: WeChat Official Account AppSecret
    token: Server verification token (from WeChat admin console)
    encoding_aes_key: (optional) Message encryption key
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import xml.etree.ElementTree as ET
from typing import Any, Dict, Optional
from xml.etree.ElementTree import Element, SubElement

import httpx

from .base import PlatformAdapter, PlatformMessage, PlatformResponse, MessageType

logger = logging.getLogger(__name__)


class WeChatAdapter(PlatformAdapter):
    """WeChat Official Account platform adapter."""

    platform_name = "wechat"
    API_BASE = "https://api.weixin.qq.com/cgi-bin"

    def __init__(self, config: Dict[str, Any]) -> None:
        super().__init__(config)
        self.app_id: str = config.get("app_id", "")
        self.app_secret: str = config.get("app_secret", "")
        self.token: str = config.get("token", "")
        self.encoding_aes_key: str = config.get("encoding_aes_key", "")

        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0
        self._http_client: Optional[httpx.AsyncClient] = None

    async def start(self) -> None:
        await super().start()
        self._http_client = httpx.AsyncClient(timeout=30)
        await self._refresh_token()
        logger.info("WeChat adapter started")

    async def stop(self) -> None:
        await super().stop()
        if self._http_client:
            await self._http_client.aclose()

    # ── Token management ──────────────────────────────────────────────

    async def _refresh_token(self) -> str:
        """Obtain or refresh the access token."""
        if self._access_token and time.time() < self._token_expires_at - 60:
            return self._access_token

        resp = await self._http_client.get(
            f"{self.API_BASE}/token",
            params={
                "grant_type": "client_credential",
                "appid": self.app_id,
                "secret": self.app_secret,
            },
        )
        data = resp.json()
        if "access_token" not in data:
            raise RuntimeError(f"Failed to get WeChat access token: {data}")

        self._access_token = data["access_token"]
        self._token_expires_at = time.time() + data.get("expires_in", 7200)
        return self._access_token

    # ── Receive messages ──────────────────────────────────────────────

    async def receive_message(self, raw_event: Dict[str, Any]) -> Optional[PlatformMessage]:
        """
        Parse a WeChat XML message into a PlatformMessage.

        WeChat sends messages as XML. This method handles both
        raw XML strings and pre-parsed dicts.
        """
        # If raw_event contains xml_str, parse it
        xml_str = raw_event.get("xml_str", "")
        if xml_str:
            return self._parse_xml_message(xml_str)

        # If it's already a dict with message fields
        msg_type = raw_event.get("MsgType", "text")
        from_user = raw_event.get("FromUserName", "")
        to_user = raw_event.get("ToUserName", "")
        msg_id = raw_event.get("MsgId", "")

        text = ""
        image_url = None
        file_url = None
        file_name = None
        parsed_type = MessageType.TEXT

        if msg_type == "text":
            text = raw_event.get("Content", "")
            parsed_type = MessageType.TEXT
        elif msg_type == "image":
            image_url = raw_event.get("PicUrl", "")
            parsed_type = MessageType.IMAGE
        elif msg_type == "voice":
            parsed_type = MessageType.AUDIO
            text = raw_event.get("Recognition", "")  # Speech-to-text result
        elif msg_type == "video" or msg_type == "shortvideo":
            parsed_type = MessageType.VIDEO
        elif msg_type == "location":
            lat = raw_event.get("Location_X", "")
            lng = raw_event.get("Location_Y", "")
            label = raw_event.get("Label", "")
            text = f"Location: {label} ({lat}, {lng})"
            parsed_type = MessageType.LOCATION
        elif msg_type == "event":
            event = raw_event.get("Event", "")
            text = f"event:{event}"
            if event == "subscribe":
                text = "event:subscribe"
            elif event == "unsubscribe":
                text = "event:unsubscribe"
            elif event == "CLICK":
                text = f"event:click:{raw_event.get('EventKey', '')}"
            parsed_type = MessageType.EVENT

        return PlatformMessage(
            message_id=str(msg_id),
            platform=self.platform_name,
            chat_id=from_user,  # WeChat uses openid as chat_id for replies
            user_id=from_user,
            user_name=from_user,
            message_type=parsed_type,
            text=text.strip(),
            raw_content=raw_event,
            timestamp=time.time(),
            is_group=False,  # Official accounts don't have group chats
            image_url=image_url,
            file_url=file_url,
            file_name=file_name,
            metadata={
                "to_user": to_user,
                "msg_type": msg_type,
            },
        )

    def _parse_xml_message(self, xml_str: str) -> Optional[PlatformMessage]:
        """Parse WeChat XML message format."""
        try:
            root = ET.fromstring(xml_str)
            data = {}
            for child in root:
                data[child.tag] = child.text or ""
            return self.receive_message(data)  # Recursive call with parsed dict
        except ET.ParseError:
            logger.error("Failed to parse WeChat XML message")
            return None

    # ── Send messages ─────────────────────────────────────────────────

    async def send_message(self, response: PlatformResponse) -> bool:
        """
        Send a message via WeChat Customer Service API.

        For passive replies within 5 seconds, use format_passive_reply().
        For proactive messages or those exceeding 5s, use the Customer Service API.
        """
        token = await self._refresh_token()

        if response.card_data and response.card_data.get("passive"):
            # Passive reply is handled by the webhook handler returning XML
            return True

        # Customer Service API
        payload: Dict[str, Any] = {
            "touser": response.chat_id,
            "msgtype": "text",
            "text": {"content": response.text[:2048]},
        }

        resp = await self._http_client.post(
            f"{self.API_BASE}/message/custom/send",
            params={"access_token": token},
            json=payload,
        )
        data = resp.json()

        if data.get("errcode", 0) != 0:
            logger.error(f"WeChat send failed: {data}")
            return False

        return True

    # ── Format response ───────────────────────────────────────────────

    def format_response(
        self, text: str, context: Optional[Dict[str, Any]] = None
    ) -> PlatformResponse:
        """Format agent text for WeChat (plain text, no Markdown)."""
        chat_id = (context or {}).get("chat_id", "")

        return PlatformResponse(
            chat_id=chat_id,
            text=text,
            message_type=MessageType.TEXT,
        )

    def format_passive_reply(self, to_user: str, from_user: str, text: str) -> str:
        """
        Format a passive XML reply for WeChat webhook response.
        Must be sent within 5 seconds of receiving the message.
        """
        root = Element("xml")
        SubElement(root, "ToUserName").text = to_user  # CDATA in production
        SubElement(root, "FromUserName").text = from_user
        SubElement(root, "CreateTime").text = str(int(time.time()))
        SubElement(root, "MsgType").text = "text"
        SubElement(root, "Content").text = text
        return ET.tostring(root, encoding="unicode")

    # ── Webhook handling ──────────────────────────────────────────────

    async def handle_webhook(self, request_body: bytes, headers: Dict[str, str]) -> Dict[str, Any]:
        """
        Process an incoming WeChat webhook request.

        WeChat sends GET for verification and POST for messages.
        """
        # The actual HTTP method handling is done by the FastAPI route.
        # This method handles the POST body.
        try:
            body = self._parse_xml_bytes(request_body)
        except Exception:
            return {"error": "invalid xml"}

        if not body:
            return {"error": "empty body"}

        message = await self.receive_message(body)
        if message:
            await self.dispatch_message(message)

        return {"ok": True}

    def verify_webhook_get(
        self, signature: str, timestamp: str, nonce: str, echostr: str
    ) -> Optional[str]:
        """
        Verify WeChat server configuration GET request.
        Returns echostr on success (to be sent as HTTP response), None on failure.
        """
        params = sorted([self.token, timestamp, nonce])
        sha1 = hashlib.sha1("".join(params).encode("utf-8")).hexdigest()
        if sha1 == signature:
            return echostr
        return None

    async def verify_webhook(self, request_body: bytes, headers: Dict[str, str]) -> bool:
        """Verify WeChat webhook signature."""
        signature = headers.get("signature", "")
        timestamp = headers.get("timestamp", "")
        nonce = headers.get("nonce", "")
        params = sorted([self.token, timestamp, nonce])
        sha1 = hashlib.sha1("".join(params).encode("utf-8")).hexdigest()
        return sha1 == signature

    def _parse_xml_bytes(self, data: bytes) -> Optional[Dict[str, str]]:
        """Parse XML bytes into a dict."""
        try:
            root = ET.fromstring(data)
            result = {}
            for child in root:
                result[child.tag] = child.text or ""
            return result
        except ET.ParseError:
            return None
