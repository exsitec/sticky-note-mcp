"""Codex session history provider."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from . import register
from .base import HistoryEntry, SessionContext, SessionHistoryProvider


logger = logging.getLogger(__name__)


@register("codex")
class CodexHistoryProvider(SessionHistoryProvider):
    """Reads Codex rollout JSONL files to provide session context."""

    def load_context(self, session_id: str) -> SessionContext:
        if not session_id:
            raise ValueError("session_id must be provided to load Codex history")

        candidates = self._candidate_paths(session_id)

        fallback_context: SessionContext | None = None
        fallback_source: Path | None = None

        for path in candidates:
            entries: list[HistoryEntry] = []
            discovered_id: str | None = None
            mismatch = False

            for item in self._iter_jsonl(path):
                item_type = item.get("type")

                if item_type == "turn_context":
                    continue

                entry = None

                if item_type == "session_meta":
                    payload = item.get("payload") or {}
                    meta_id = payload.get("id")
                    if meta_id:
                        discovered_id = discovered_id or meta_id
                    if meta_id and meta_id != session_id:
                        mismatch = True
                    entry = self._entry_from_session_meta(item)
                elif item_type == "response_item":
                    entry = self._entry_from_response_item(item)
                elif item_type == "event_msg":
                    payload = item.get("payload") or {}
                    variant = payload.get("type")
                    if variant in {"token_count", "agent_message", "user_message"}:
                        continue
                    entry = self._entry_from_event_msg(item)
                elif item_type == "compacted":
                    entry = self._entry_from_compacted(item)

                if entry:
                    entries.append(entry)

            if not entries:
                continue

            if discovered_id == session_id:
                return SessionContext(session_id=session_id, entries=tuple(entries))

            if fallback_context is None:
                fallback_context = SessionContext(session_id=session_id, entries=tuple(entries))
                fallback_source = path

        if fallback_context:
            if fallback_source is not None:
                logger.warning(
                    "Session id %s not found; using fallback session from %s",
                    session_id,
                    fallback_source,
                )
            return fallback_context

        raise FileNotFoundError(
            f"Session history for id '{session_id}' not found under {self.history_root}"
        )

    def _candidate_paths(self, session_id: str) -> list[Path]:
        root = self.history_root
        if root.is_file():
            return [root]

        if not root.exists():
            raise FileNotFoundError(
                f"History directory '{root}' does not exist for session '{session_id}'"
            )

        candidates = [p for p in root.rglob("*.jsonl") if p.is_file()]
        if not candidates:
            raise FileNotFoundError(
                f"No history files found under '{root}' for session '{session_id}'"
            )

        def _mtime_key(path: Path) -> float:
            try:
                return path.stat().st_mtime
            except OSError:
                return 0.0

        matched = sorted(
            (p for p in candidates if session_id in p.name),
            key=_mtime_key,
            reverse=True,
        )
        unmatched = sorted(
            (p for p in candidates if session_id not in p.name),
            key=_mtime_key,
            reverse=True,
        )

        return matched + unmatched

    def _iter_jsonl(self, path: Path) -> Iterator[dict[str, Any]]:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                text = line.strip()
                if not text:
                    continue
                try:
                    yield json.loads(text)
                except json.JSONDecodeError:
                    continue

    def _parse_timestamp(self, raw: Any) -> datetime | None:
        if not isinstance(raw, str):
            return None
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _entry_from_session_meta(self, item: dict[str, Any]) -> HistoryEntry | None:
        payload = item.get("payload") or {}
        instructions = payload.get("instructions")
        if not instructions:
            return None
        return HistoryEntry(
            timestamp=self._parse_timestamp(item.get("timestamp")),
            kind="session_meta",
            text=str(instructions),
            role="system",
            metadata=payload,
        )

    def _entry_from_response_item(self, item: dict[str, Any]) -> HistoryEntry | None:
        payload = item.get("payload") or {}
        variant = payload.get("type")
        inner = payload.get("payload")
        view = inner if isinstance(inner, dict) and inner else payload
        timestamp = self._parse_timestamp(item.get("timestamp"))

        if variant == "message":
            content = view.get("content") or []
            text_parts = []
            for element in content:
                if not isinstance(element, dict):
                    continue
                if "text" in element:
                    text_parts.append(str(element["text"]))
            text = "\n".join(part for part in text_parts if part)
            if not text:
                return None
            return HistoryEntry(
                timestamp=timestamp,
                kind="message",
                text=text,
                role=view.get("role"),
                metadata=payload,
            )

        if variant == "reasoning":
            text = str(view.get("text") or "").strip()
            if not text:
                return None
            return HistoryEntry(
                timestamp=timestamp,
                kind="reasoning",
                text=text,
                role=view.get("role"),
                metadata=payload,
            )

        if variant in {"function_call", "custom_tool_call", "local_shell_call"}:
            name = (
                view.get("name")
                or view.get("tool_name")
                or view.get("command")
            )
            arguments = view.get("arguments") or view.get("input")
            text = self._format_call_text(name, arguments)
            if not text:
                return None
            return HistoryEntry(
                timestamp=timestamp,
                kind=variant,
                text=text,
                role=view.get("role") or "assistant",
                metadata=payload,
            )

        return None

    def _entry_from_event_msg(self, item: dict[str, Any]) -> HistoryEntry | None:
        payload = item.get("payload") or {}
        variant = payload.get("type")
        inner = payload.get("payload")
        view = inner if isinstance(inner, dict) and inner else payload
        message = view.get("message") or view.get("text")
        if message is None:
            return None
        return HistoryEntry(
            timestamp=self._parse_timestamp(item.get("timestamp")),
            kind=f"event:{variant}",
            text=str(message),
            role=view.get("role"),
            metadata=payload,
        )

    def _entry_from_compacted(self, item: dict[str, Any]) -> HistoryEntry | None:
        payload = item.get("payload") or {}
        message = payload.get("message")
        if not message:
            return None
        return HistoryEntry(
            timestamp=self._parse_timestamp(item.get("timestamp")),
            kind="compacted",
            text=str(message),
            role="assistant",
            metadata=payload,
        )

    def _format_call_text(self, name: Any, arguments: Any) -> str:
        parts: list[str] = []
        if name:
            parts.append(f"call:{name}")
        if arguments:
            try:
                serialized = json.dumps(arguments, ensure_ascii=False)
            except (TypeError, ValueError):
                serialized = str(arguments)
            parts.append(serialized)
        return " ".join(parts).strip()

