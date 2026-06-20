"""
Base platform adapter interface (AtomCollide-智械工坊)

Defines the abstract contract that every platform adapter must implement.
Messages are normalized into PlatformMessage so the agent pipeline can
process them uniformly regardless of origin platform.
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Awaitable, Dict, List, Optional

logger = logging.getLogger(__name__)


class MessageType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    AUDIO = "audio"
    VIDEO = "video"
    STICKER = "sticker"
    LOCATION = "location"
    CARD = "card"
    EVENT = "event"


@dataclass
class PlatformMessage:
    """
    Normalized message representation across all platforms.
    Every adapter converts its native format into this structure.
    """

    # Identity
    message_id: str = ""
    platform: str = ""  # feishu, telegram, discord, wechat
    chat_id: str = ""  # conversation / channel / group id
    user_id: str = ""
    user_name: str = ""

    # Content
    message_type: MessageType = MessageType.TEXT
    text: str = ""
    raw_content: Any = None  # original platform-specific payload

    # Metadata
    timestamp: float = field(default_factory=time.time)
    is_group: bool = False
    reply_to: Optional[str] = None  # message_id being replied to
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Attachments
    image_url: Optional[str] = None
    file_url: Optional[str] = None
    file_name: Optional[str] = None


@dataclass
class PlatformResponse:
    """Response to send back to a platform."""

    chat_id: str = ""
    text: str = ""
    message_type: MessageType = MessageType.TEXT
    reply_to: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    image_url: Optional[str] = None
    file_url: Optional[str] = None
    card_data: Optional[Dict[str, Any]] = None


class PlatformAdapter(ABC):
    """
    Abstract base class for platform adapters.

    Each adapter must implement:
    - `send_message()` - Send a response to the platform
    - `receive_message()` - Normalize an incoming platform event into PlatformMessage
    - `format_response()` - Convert agent output into platform-native format
    - `start()` / `stop()` - Lifecycle hooks for webhook listeners or polling
    """

    platform_name: str = "unknown"

    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config
        self._running = False
        self._message_handlers: List[Callable[[PlatformMessage], Awaitable[None]]] = []
        self._logger = logging.getLogger(f"adapter.{self.platform_name}")

    # ── Abstract methods ──────────────────────────────────────────────

    @abstractmethod
    async def send_message(self, response: PlatformResponse) -> bool:
        """
        Send a message to the platform.
        Returns True on success, False on failure.
        """
        ...

    @abstractmethod
    async def receive_message(self, raw_event: Dict[str, Any]) -> Optional[PlatformMessage]:
        """
        Parse a raw platform event into a normalized PlatformMessage.
        Returns None if the event should be ignored (e.g., bot's own message).
        """
        ...

    @abstractmethod
    def format_response(self, text: str, context: Optional[Dict[str, Any]] = None) -> PlatformResponse:
        """
        Format agent output text into a PlatformResponse suitable for this platform.
        Handles platform-specific formatting (Markdown variants, card layouts, etc.)
        """
        ...

    # ── Lifecycle ─────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the adapter (begin polling or register webhooks)."""
        self._running = True
        self._logger.info(f"Platform adapter [{self.platform_name}] started")

    async def stop(self) -> None:
        """Stop the adapter gracefully."""
        self._running = False
        self._logger.info(f"Platform adapter [{self.platform_name}] stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    # ── Message handler registration ──────────────────────────────────

    def on_message(self, handler: Callable[[PlatformMessage], Awaitable[None]]) -> None:
        """Register a handler to be called when a message is received."""
        self._message_handlers.append(handler)

    async def dispatch_message(self, message: PlatformMessage) -> None:
        """Dispatch a received message to all registered handlers."""
        for handler in self._message_handlers:
            try:
                await handler(message)
            except Exception:
                self._logger.exception(f"Error in message handler for {self.platform_name}")

    # ── Utility ───────────────────────────────────────────────────────

    def get_config_value(self, key: str, default: Any = None) -> Any:
        """Get a configuration value with dot-notation support."""
        keys = key.split(".")
        value = self.config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} platform={self.platform_name} running={self._running}>"
