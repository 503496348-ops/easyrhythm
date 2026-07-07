from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4
from typing import Any, Dict, List

from chatkit.store import NotFoundError, Store
from chatkit.types import Attachment, Page, Thread, ThreadItem, ThreadMetadata


@dataclass
class _ThreadState:
    thread: ThreadMetadata
    items: List[ThreadItem]


class MemoryStore(Store[dict[str, Any]]):
    """Simple in-memory store compatible with the ChatKit server interface."""

    def __init__(self) -> None:
        self._threads: Dict[str, _ThreadState] = {}
        self._attachments: Dict[str, Attachment] = {}

    def generate_attachment_id(self, mime_type: str, context: dict[str, Any]) -> str:
        """Return a new identifier for an attachment."""
        return f"atc_{uuid4().hex[:8]}"

    @staticmethod
    def _coerce_thread_metadata(thread: ThreadMetadata | Thread | dict[str, Any]) -> ThreadMetadata:
        """Normalize thread input from object or legacy dict payload."""
        if isinstance(thread, dict):
            thread_obj = ThreadMetadata(**thread)
        elif isinstance(thread, Thread):
            thread_obj = thread.model_copy(deep=True)
        else:
            thread_obj = thread.model_copy(deep=True)

        has_items = isinstance(thread_obj, Thread) or "items" in getattr(
            thread_obj, "model_fields_set", set()
        )
        if not has_items:
            return thread_obj

        data = thread_obj.model_dump()
        data.pop("items", None)
        return ThreadMetadata(**data).model_copy(deep=True)

    @staticmethod
    def _coerce_thread_item(item: ThreadItem | dict[str, Any]) -> ThreadItem:
        """Normalize thread item input from object or legacy dict payload."""
        if isinstance(item, ThreadItem):
            return item.model_copy(deep=True)
        if isinstance(item, dict):
            return ThreadItem(**item)
        raise TypeError("thread item must be ThreadItem or dict")

    @staticmethod
    def _ensure_thread_exists(
        state_store: Dict[str, _ThreadState], thread_id: str
    ) -> _ThreadState:
        """Create thread metadata shell if missing (support array/object schema callers)."""
        state = state_store.get(thread_id)
        if state is None:
            state = _ThreadState(
                thread=ThreadMetadata(id=thread_id, created_at=datetime.utcnow()),
                items=[],
            )
            state_store[thread_id] = state
        return state

    # -- Thread metadata -------------------------------------------------
    async def load_thread(self, thread_id: str, context: dict[str, Any]) -> ThreadMetadata:
        state = self._threads.get(thread_id)
        if not state:
            raise NotFoundError(f"Thread {thread_id} not found")
        return state.thread.model_copy(deep=True)

    async def save_thread(self, thread: ThreadMetadata | dict[str, Any], context: dict[str, Any]) -> None:
        metadata = self._coerce_thread_metadata(thread)
        state = self._threads.get(metadata.id)
        if state:
            state.thread = metadata
        else:
            self._threads[metadata.id] = _ThreadState(thread=metadata, items=[])

    async def load_threads(
        self,
        limit: int,
        after: str | None,
        order: str,
        context: dict[str, Any],
    ) -> Page[ThreadMetadata]:
        threads = sorted(
            (state.thread.model_copy(deep=True) for state in self._threads.values()),
            key=lambda t: t.created_at or datetime.min,
            reverse=(order == "desc"),
        )

        if after:
            index_map = {thread.id: idx for idx, thread in enumerate(threads)}
            start = index_map.get(after, -1) + 1
        else:
            start = 0

        slice_threads = threads[start : start + limit + 1]
        has_more = len(slice_threads) > limit
        slice_threads = slice_threads[:limit]
        next_after = slice_threads[-1].id if has_more and slice_threads else None
        return Page(
            data=slice_threads,
            has_more=has_more,
            after=next_after,
        )

    async def delete_thread(self, thread_id: str, context: dict[str, Any]) -> None:
        self._threads.pop(thread_id, None)

    # -- Thread items ----------------------------------------------------
    def _items(self, thread_id: str) -> List[ThreadItem]:
        return self._ensure_thread_exists(self._threads, thread_id).items

    async def load_thread_items(
        self,
        thread_id: str,
        after: str | None,
        limit: int,
        order: str,
        context: dict[str, Any],
    ) -> Page[ThreadItem]:
        items = [item.model_copy(deep=True) for item in self._items(thread_id)]
        items.sort(
            key=lambda item: getattr(item, "created_at", datetime.utcnow()),
            reverse=(order == "desc"),
        )

        if after:
            index_map = {item.id: idx for idx, item in enumerate(items)}
            start = index_map.get(after, -1) + 1
        else:
            start = 0

        slice_items = items[start : start + limit + 1]
        has_more = len(slice_items) > limit
        slice_items = slice_items[:limit]
        next_after = slice_items[-1].id if has_more and slice_items else None
        return Page(data=slice_items, has_more=has_more, after=next_after)

    async def add_thread_item(
        self, thread_id: str, item: ThreadItem | dict[str, Any], context: dict[str, Any]
    ) -> None:
        self._items(thread_id).append(self._coerce_thread_item(item))

    async def save_item(
        self, thread_id: str, item: ThreadItem | dict[str, Any], context: dict[str, Any]
    ) -> None:
        coerced_item = self._coerce_thread_item(item)
        items = self._items(thread_id)
        for idx, existing in enumerate(items):
            if existing.id == coerced_item.id:
                items[idx] = coerced_item
                return
        items.append(coerced_item)

    async def load_item(self, thread_id: str, item_id: str, context: dict[str, Any]) -> ThreadItem:
        for item in self._items(thread_id):
            if item.id == item_id:
                return item.model_copy(deep=True)
        raise NotFoundError(f"Item {item_id} not found")

    async def delete_thread_item(
        self, thread_id: str, item_id: str, context: dict[str, Any]
    ) -> None:
        items = self._items(thread_id)
        self._threads[thread_id].items = [item for item in items if item.id != item_id]

    # -- Files -----------------------------------------------------------

    async def save_attachment(
        self,
        attachment: Attachment,
        context: dict[str, Any],
    ) -> None:
        self._attachments[attachment.id] = attachment.model_copy(deep=True)

    async def load_attachment(
        self,
        attachment_id: str,
        context: dict[str, Any],
    ) -> Attachment:
        att = self._attachments.get(attachment_id)
        if not att:
            raise NotFoundError(f"Attachment {attachment_id} not found")
        return att.model_copy(deep=True)

    async def delete_attachment(self, attachment_id: str, context: dict[str, Any]) -> None:
        self._attachments.pop(attachment_id, None)
