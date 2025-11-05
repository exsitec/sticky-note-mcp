"""Base interfaces for session history providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Pattern, Sequence


@dataclass(slots=True)
class HistoryEntry:
    """Normalized representation of an item from an agent session history."""

    timestamp: datetime | None
    kind: str
    text: str
    role: str | None = None
    metadata: dict[str, object] | None = None


@dataclass(slots=True)
class SessionContext:
    """Container for the active session's context."""

    session_id: str
    entries: Sequence[HistoryEntry]

    @property
    def full_text(self) -> str:
        """Return the aggregated textual content of the session."""

        return "\n".join(entry.text for entry in self.entries if entry.text)


class SessionHistoryProvider(ABC):
    """Abstract base class for frameworks that expose session history."""

    def __init__(self, history_root: Path):
        self.history_root = history_root

    @abstractmethod
    def load_context(self, session_id: str) -> SessionContext:
        """Return the session context for the given agent session."""

    def search(self, session_id: str, pattern: Pattern[str] | str) -> List[HistoryEntry]:
        """Return history entries whose text matches the provided regex pattern."""

        import re

        compiled = re.compile(pattern) if isinstance(pattern, str) else pattern
        context = self.load_context(session_id)
        matches: list[HistoryEntry] = []
        for entry in context.entries:
            if entry.text and compiled.search(entry.text):
                matches.append(entry)
        return matches

