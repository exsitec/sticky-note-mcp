"""Helpers for tracking per-session note visibility."""

from __future__ import annotations

from collections import defaultdict
from typing import DefaultDict, Iterable, Set


class SessionNoteTracker:
    """Tracks which sticky notes have been shown during a session."""

    def __init__(self) -> None:
        self._shown: DefaultDict[str, Set[str]] = defaultdict(set)

    def mark_shown(self, session_id: str, note_id: str) -> None:
        self._shown[session_id].add(note_id)

    def has_shown(self, session_id: str, note_id: str) -> bool:
        return note_id in self._shown.get(session_id, set())

    def unseen(self, session_id: str, note_ids: Iterable[str]) -> list[str]:
        seen = self._shown.get(session_id, set())
        return [note_id for note_id in note_ids if note_id not in seen]

    def reset(self, session_id: str) -> None:
        self._shown.pop(session_id, None)

