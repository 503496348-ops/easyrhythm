"""
EasyRhythm Multi-Platform Adapters (AtomCollide-智械工坊)

Provides a unified interface for receiving and sending messages across
multiple chat platforms (Feishu, Telegram, Discord, WeChat).

Inspired by LangBot's adapter pattern: each platform has a self-contained
adapter that normalizes messages to a common format, and a central router
dispatches to the correct adapter.
"""

from .base import PlatformAdapter, PlatformMessage, MessageType
from .router import MessageRouter

__all__ = [
    "PlatformAdapter",
    "PlatformMessage",
    "MessageType",
    "MessageRouter",
]
