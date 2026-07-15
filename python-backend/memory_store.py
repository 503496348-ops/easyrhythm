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

# ---------------------------------------------------------------------------
# SQLite-backed persistent store (opt-in)
# ---------------------------------------------------------------------------
import os
import sqlite3
from pathlib import Path as FsPath


class SqliteMemoryStore(MemoryStore):
    """Persistent variant of MemoryStore backed by a local SQLite file."""

    def __init__(self, db_path: str | None = None) -> None:
        super().__init__()
        db_path = db_path or os.getenv("EASYRHYTHM_MEMORY_DB_PATH", "")
        if not db_path:
            raise RuntimeError("EASYRHYTHM_MEMORY_DB_PATH is required for SqliteMemoryStore")
        self.db_path = FsPath(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.db_path.as_posix(), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()
        self._load_from_db()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_threads (
                    thread_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_items (
                    item_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_attachments (
                    attachment_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL
                )
                """
            )

    def _load_from_db(self) -> None:
        self._threads.clear()
        self._attachments.clear()
        rows = self._conn.execute("SELECT thread_id, payload FROM chat_threads").fetchall()
        for row in rows:
            data = json.loads(row["payload"])
            thread = ThreadMetadata(**data)
            self._threads[row["thread_id"]] = _ThreadState(thread=thread, items=[])

        item_rows = self._conn.execute("SELECT thread_id, payload FROM chat_items ORDER BY created_at ASC").fetchall()
        for row in item_rows:
            data = json.loads(row["payload"])
            item = ThreadItem(**data)
            state = self._ensure_thread_exists(self._threads, row["thread_id"])
            state.items.append(item)

        att_rows = self._conn.execute("SELECT attachment_id, payload FROM chat_attachments").fetchall()
        for row in att_rows:
            data = json.loads(row["payload"])
            self._attachments[row["attachment_id"]] = Attachment(**data)

    def _save_thread_db(self, thread: ThreadMetadata) -> None:
        payload = json.dumps(thread.model_dump(mode="json"))
        self._conn.execute("INSERT OR REPLACE INTO chat_threads(thread_id, payload) VALUES (?, ?)", (thread.id, payload))
        self._conn.commit()

    def _save_item_db(self, thread_id: str, item: ThreadItem) -> None:
        payload = json.dumps(item.model_dump(mode="json"))
        created_at = item.created_at.isoformat() if getattr(item, "created_at", None) else None
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO chat_items(item_id, thread_id, payload, created_at) VALUES (?, ?, ?, ?)",
                (item.id, thread_id, payload, created_at),
            )

    def _delete_item_db(self, thread_id: str, item_id: str) -> None:
        self._conn.execute("DELETE FROM chat_items WHERE thread_id = ? AND item_id = ?", (thread_id, item_id))
        self._conn.commit()

    def _delete_thread_db(self, thread_id: str) -> None:
        self._conn.execute("DELETE FROM chat_items WHERE thread_id = ?", (thread_id,))
        self._conn.execute("DELETE FROM chat_threads WHERE thread_id = ?", (thread_id,))
        self._conn.commit()

    async def save_thread(self, thread: ThreadMetadata | dict[str, Any], context: dict[str, Any]) -> None:
        metadata = self._coerce_thread_metadata(thread)
        await super().save_thread(metadata, context)
        self._save_thread_db(metadata)

    async def load_thread(self, thread_id: str, context: dict[str, Any]) -> ThreadMetadata:
        if thread_id in self._threads:
            state = self._threads.get(thread_id)
            if state:
                return state.thread.model_copy(deep=True)
        row = self._conn.execute("SELECT payload FROM chat_threads WHERE thread_id = ?", (thread_id,)).fetchone()
        if not row:
            raise NotFoundError(f"Thread {thread_id} not found")
        state = ThreadMetadata(**json.loads(row["payload"]))
        self._threads[thread_id] = _ThreadState(thread=state, items=[])
        return state.model_copy(deep=True)

    async def delete_thread(self, thread_id: str, context: dict[str, Any]) -> None:
        await super().delete_thread(thread_id, context)
        self._delete_thread_db(thread_id)

    async def add_thread_item(
        self, thread_id: str, item: ThreadItem | dict[str, Any], context: dict[str, Any]
    ) -> None:
        parsed = self._coerce_thread_item(item)
        await super().add_thread_item(thread_id, parsed, context)
        self._save_item_db(thread_id, parsed)

    async def save_item(
        self, thread_id: str, item: ThreadItem | dict[str, Any], context: dict[str, Any]
    ) -> None:
        parsed = self._coerce_thread_item(item)
        await super().save_item(thread_id, parsed, context)
        self._save_item_db(thread_id, parsed)

    async def load_item(self, thread_id: str, item_id: str, context: dict[str, Any]) -> ThreadItem:
        try:
            return await super().load_item(thread_id, item_id, context)
        except NotFoundError:
            row = self._conn.execute(
                "SELECT payload FROM chat_items WHERE thread_id = ? AND item_id = ?",
                (thread_id, item_id),
            ).fetchone()
            if not row:
                raise
            return ThreadItem(**json.loads(row["payload"]))

    async def delete_thread_item(
        self, thread_id: str, item_id: str, context: dict[str, Any]
    ) -> None:
        await super().delete_thread_item(thread_id, item_id, context)
        self._delete_item_db(thread_id, item_id)

    async def save_attachment(self, attachment: Attachment, context: dict[str, Any]) -> None:
        await super().save_attachment(attachment, context)
        payload = json.dumps(attachment.model_dump(mode="json"))
        self._conn.execute(
            "INSERT OR REPLACE INTO chat_attachments(attachment_id, payload) VALUES (?, ?)",
            (attachment.id, payload),
        )
        self._conn.commit()

    async def load_attachment(self, attachment_id: str, context: dict[str, Any]) -> Attachment:
        try:
            return await super().load_attachment(attachment_id, context)
        except NotFoundError:
            row = self._conn.execute(
                "SELECT payload FROM chat_attachments WHERE attachment_id = ?",
                (attachment_id,),
            ).fetchone()
            if not row:
                raise
            return Attachment(**json.loads(row["payload"]))

    async def delete_attachment(self, attachment_id: str, context: dict[str, Any]) -> None:
        await super().delete_attachment(attachment_id, context)
        self._conn.execute("DELETE FROM chat_attachments WHERE attachment_id = ?", (attachment_id,))
        self._conn.commit()
