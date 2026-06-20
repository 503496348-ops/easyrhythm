"""
Unified Message Router (AtomCollide-智械工坊)

Routes incoming messages to the correct platform adapter and dispatches
agent responses back through the originating platform.

Inspired by LangBot's botmgr pattern: a central router manages multiple
adapter instances, maps platform identifiers, and provides a unified
interface for the agent pipeline.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional

from .base import PlatformAdapter, PlatformMessage, PlatformResponse, MessageType
from .feishu import FeishuAdapter
from .telegram import TelegramAdapter
from .discord import DiscordAdapter
from .wechat import WeChatAdapter

logger = logging.getLogger(__name__)

# Registry of available adapters by platform name
ADAPTER_REGISTRY: Dict[str, type[PlatformAdapter]] = {
    "feishu": FeishuAdapter,
    "telegram": TelegramAdapter,
    "discord": DiscordAdapter,
    "wechat": WeChatAdapter,
}


class MessageRouter:
    """
    Central message router that manages multiple platform adapters.

    Usage:
        router = MessageRouter()
        router.register_adapter("feishu", feishu_config)
        router.register_adapter("telegram", telegram_config)
        router.on_message(my_handler)
        await router.start_all()
    """

    def __init__(self) -> None:
        self._adapters: Dict[str, PlatformAdapter] = {}
        self._message_handlers: List[Callable[[PlatformMessage, "MessageRouter"], Awaitable[None]]] = []
        self._response_handler: Optional[Callable[[PlatformMessage], Awaitable[Optional[str]]]] = None

    # ── Adapter registration ──────────────────────────────────────────

    def register_adapter(
        self, platform: str, config: Dict[str, Any], adapter_class: Optional[type] = None
    ) -> PlatformAdapter:
        """
        Register and instantiate a platform adapter.

        Args:
            platform: Platform identifier (feishu, telegram, discord, wechat)
            config: Platform-specific configuration
            adapter_class: Override the default adapter class

        Returns:
            The created adapter instance
        """
        cls = adapter_class or ADAPTER_REGISTRY.get(platform)
        if cls is None:
            raise ValueError(
                f"Unknown platform '{platform}'. Available: {list(ADAPTER_REGISTRY.keys())}"
            )

        adapter = cls(config)
        adapter.on_message(self._create_dispatch(platform))
        self._adapters[platform] = adapter
        logger.info(f"Registered adapter for platform: {platform}")
        return adapter

    def get_adapter(self, platform: str) -> Optional[PlatformAdapter]:
        """Get an adapter by platform name."""
        return self._adapters.get(platform)

    def get_all_adapters(self) -> Dict[str, PlatformAdapter]:
        """Get all registered adapters."""
        return dict(self._adapters)

    # ── Message handling ──────────────────────────────────────────────

    def on_message(
        self, handler: Callable[[PlatformMessage, "MessageRouter"], Awaitable[None]]
    ) -> None:
        """
        Register a handler for incoming messages from any platform.

        The handler receives:
        - message: PlatformMessage (normalized)
        - router: MessageRouter (for sending responses)
        """
        self._message_handlers.append(handler)

    def set_response_handler(
        self, handler: Callable[[PlatformMessage], Awaitable[Optional[str]]]
    ) -> None:
        """
        Set a handler that generates responses for incoming messages.
        This is a convenience method: the handler takes a message and returns
        a response string (or None to skip).
        """
        self._response_handler = handler

    def _create_dispatch(self, platform: str) -> Callable:
        """Create a dispatch callback for a specific platform."""

        async def dispatch(message: PlatformMessage) -> None:
            logger.debug(f"Received message from {platform}: {message.text[:100]}")
            for handler in self._message_handlers:
                try:
                    await handler(message, self)
                except Exception:
                    logger.exception(f"Error in message handler for {platform}")

            # Auto-respond if response handler is set
            if self._response_handler:
                try:
                    response_text = await self._response_handler(message)
                    if response_text:
                        await self.send_response(message, response_text)
                except Exception:
                    logger.exception(f"Error generating response for {platform}")

        return dispatch

    # ── Sending responses ─────────────────────────────────────────────

    async def send_response(
        self,
        original_message: PlatformMessage,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Send a response back through the same platform the message came from.

        Args:
            original_message: The message being responded to
            text: Response text
            metadata: Additional platform-specific metadata

        Returns:
            True if sent successfully
        """
        adapter = self._adapters.get(original_message.platform)
        if not adapter:
            logger.error(f"No adapter found for platform: {original_message.platform}")
            return False

        context = {
            "chat_id": original_message.chat_id,
            "reply_to": original_message.message_id,
            **(metadata or {}),
        }

        response = adapter.format_response(text, context)
        return await adapter.send_message(response)

    async def broadcast(
        self,
        chat_ids: Dict[str, str],
        text: str,
    ) -> Dict[str, bool]:
        """
        Send a message to multiple platforms.

        Args:
            chat_ids: {platform: chat_id} mapping
            text: Message text

        Returns:
            {platform: success} mapping
        """
        results = {}
        for platform, chat_id in chat_ids.items():
            adapter = self._adapters.get(platform)
            if not adapter:
                results[platform] = False
                continue
            response = adapter.format_response(text, {"chat_id": chat_id})
            results[platform] = await adapter.send_message(response)
        return results

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def start_all(self) -> None:
        """Start all registered adapters."""
        for platform, adapter in self._adapters.items():
            try:
                await adapter.start()
                logger.info(f"Started adapter: {platform}")
            except Exception:
                logger.exception(f"Failed to start adapter: {platform}")

    async def stop_all(self) -> None:
        """Stop all registered adapters."""
        for platform, adapter in self._adapters.items():
            try:
                await adapter.stop()
            except Exception:
                logger.exception(f"Error stopping adapter: {platform}")

    # ── Webhook routing ───────────────────────────────────────────────

    async def handle_webhook(
        self, platform: str, request_body: bytes, headers: Dict[str, str]
    ) -> Dict[str, Any]:
        """
        Route an incoming webhook to the correct adapter.

        Args:
            platform: Platform identifier
            request_body: Raw request body bytes
            headers: HTTP headers

        Returns:
            Response dict to be returned as HTTP response
        """
        adapter = self._adapters.get(platform)
        if not adapter:
            return {"error": f"No adapter registered for platform: {platform}"}

        if not await adapter.verify_webhook(request_body, headers):
            return {"error": "Webhook verification failed"}

        return await adapter.handle_webhook(request_body, headers)

    # ── Status ────────────────────────────────────────────────────────

    def status(self) -> Dict[str, Any]:
        """Get status of all adapters."""
        return {
            platform: {
                "running": adapter.is_running,
                "class": adapter.__class__.__name__,
            }
            for platform, adapter in self._adapters.items()
        }

    def __repr__(self) -> str:
        platforms = ", ".join(self._adapters.keys())
        return f"<MessageRouter adapters=[{platforms}]>"
