"""Persistence helpers for sticky notes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


def _dt_to_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat().replace("+00:00", "Z")


def _iso_to_dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt.astimezone(timezone.utc)


@dataclass(slots=True)
class StickyNote:
    """Represents a stored sticky note."""

    id: str
    message: str
    context_regex: str
    created_at: datetime
    creator: str | None = None
    trigger_snippets: list[str] | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "message": self.message,
            "context_regex": self.context_regex,
            "created_at": _dt_to_iso(self.created_at),
            **({"creator": self.creator} if self.creator else {}),
            **({"trigger_snippets": self.trigger_snippets} if self.trigger_snippets else {}),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "StickyNote":
        raw_snippets = payload.get("trigger_snippets")
        trigger_snippets = (
            [str(item) for item in raw_snippets]
            if isinstance(raw_snippets, list)
            else None
        )
        return cls(
            id=str(payload["id"]),
            message=str(payload["message"]),
            context_regex=str(payload["context_regex"]),
            created_at=_iso_to_dt(str(payload["created_at"])),
            creator=str(payload["creator"]) if payload.get("creator") else None,
            trigger_snippets=trigger_snippets,
        )


class StickyNoteStore:
    """JSONL-backed persistence for sticky notes."""

    def __init__(self, notes_file: Path):
        self.notes_file = notes_file
        self.notes_file.parent.mkdir(parents=True, exist_ok=True)
        self.notes_file.touch(exist_ok=True)

    def append(self, note: StickyNote) -> None:
        with self.notes_file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(note.to_dict(), ensure_ascii=False) + "\n")

    def iter_notes(self) -> Iterator[StickyNote]:
        if not self.notes_file.exists():
            return iter(())

        def _generator() -> Iterator[StickyNote]:
            with self.notes_file.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    try:
                        yield StickyNote.from_dict(payload)
                    except (KeyError, ValueError, TypeError):
                        continue

        return _generator()

    def all_notes(self) -> list[StickyNote]:
        return list(self.iter_notes())

