"""FastMCP bootstrap for the Sticky Note MCP server."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional
from uuid import uuid4

from fastmcp import Context, FastMCP

from .config import ServerConfig, load_config
from .frameworks import get_history_provider
from .session_state import SessionNoteTracker
from .storage import StickyNote, StickyNoteStore

SERVER_NAME = "Sticky Note MCP Server"

logger = logging.getLogger(__name__)


def _compile_regex(pattern: str) -> re.Pattern[str]:
    try:
        return re.compile(pattern, re.MULTILINE)
    except re.error as exc:  # pragma: no cover - validation guard
        raise ValueError(f"Invalid regular expression: {exc}") from exc


def _timestamp_now() -> datetime:
    return datetime.now(timezone.utc)


def _entry_metadata(entry) -> Dict[str, Any]:
    return {
        "timestamp": entry.timestamp.isoformat().replace("+00:00", "Z") if entry.timestamp else None,
        "kind": entry.kind,
        "role": entry.role,
    }


def _collect_snippets(pattern: re.Pattern[str], context) -> List[Dict[str, Any]]:
    snippets: list[Dict[str, Any]] = []
    for entry in context.entries:
        if not entry.text:
            continue
        for match in pattern.finditer(entry.text):
            span = match.span()
            snippet_text = _extract_window(entry.text, span)
            snippets.append({
                "text": snippet_text,
                "metadata": _entry_metadata(entry),
            })
    return snippets


def _extract_window(text: str, span: tuple[int, int], padding: int = 80) -> str:
    start, end = span
    window_start = max(0, start - padding)
    window_end = min(len(text), end + padding)
    prefix = "…" if window_start > 0 else ""
    suffix = "…" if window_end < len(text) else ""
    return f"{prefix}{text[window_start:window_end]}{suffix}"


def build_app(config: Optional[ServerConfig] = None) -> FastMCP:
    """Instantiate and configure the FastMCP server."""

    cfg = config or load_config()

    notes_store = StickyNoteStore(cfg.notes_file)
    history_provider = get_history_provider(cfg.framework, cfg.history_dir)
    note_tracker = SessionNoteTracker()

    mcp = FastMCP(SERVER_NAME)

    @mcp.tool
    def create_sticky_note(
        message: Annotated[
            str,
            "The text that should appear in the sticky note when it triggers. Keep it concise and actionable.",
        ],
        context_regex: Annotated[
            str,
            "Regular expression that determines when the note should display. It is matched against the entire future session context.",
        ],
        ctx: Context,
        note_id: Annotated[
            str | None,
            "Optional stable identifier to reuse an existing sticky note; omit to let the server generate one.",
        ] = None,
    ) -> Dict[str, Any]:
        """Persist a sticky note on a future context. The purpose is to inform future agents in situations you define. The context_regex is evaluated against the entire future session context, so craft it carefully. Typical use case: you made a mistake performing a task—add a sticky note that helps a future agent avoid the mistake. The response will include context snippets from your own context. Make sure it would have been shown at a stage where it brings value"""

        session_id = ctx.session_id
        logger.info("create_sticky_note invoked for session %s", session_id)
        if not session_id:
            raise RuntimeError("FastMCP session_id is required for sticky note creation")

        if not message:
            raise ValueError("Sticky note message cannot be empty")

        pattern = _compile_regex(context_regex)
        try:
            context = history_provider.load_context(session_id)
        except FileNotFoundError as exc:
            raise RuntimeError(f"No session history found for session_id '{session_id}'") from exc
        snippets = _collect_snippets(pattern, context)
        snippet_texts = [snippet["text"] for snippet in snippets]

        generated_id = note_id or uuid4().hex
        note = StickyNote(
            id=generated_id,
            message=message,
            context_regex=context_regex,
            created_at=_timestamp_now(),
            trigger_snippets=snippet_texts or None,
        )
        notes_store.append(note)

        logger.debug("Created sticky note %s with %d snippets", note.id, len(snippets))

        return {
            "id": note.id,
            "trigger_snippets": snippet_texts,
        }

    @mcp.tool(description="Retrieve sticky notes that agents from the past have shared with you. It will return notes that are relevant to the current situation. Call often (a note will only be returned once) to benefit and avoid making the same mistakes again.")
    def read_relevant_sticky_notes(ctx: Context) -> List[Dict[str, Any]]:
        """Return sticky notes relevant to the active session context."""

        session_id = ctx.session_id
        logger.info("read_relevant_sticky_notes invoked for session %s", session_id)
        if not session_id:
            raise RuntimeError("FastMCP session_id is required for reading sticky notes")

        try:
            context = history_provider.load_context(session_id)
        except FileNotFoundError as exc:
            raise RuntimeError(f"No session history found for session_id '{session_id}'") from exc
        results: list[dict[str, Any]] = []

        for note in notes_store.all_notes():
            if note_tracker.has_shown(session_id, note.id):
                continue

            try:
                pattern = _compile_regex(note.context_regex)
            except ValueError as exc:
                logger.warning("Skipping note %s due to invalid regex: %s", note.id, exc)
                continue

            snippets = _collect_snippets(pattern, context)
            if not snippets:
                continue

            note_tracker.mark_shown(session_id, note.id)
            payload = {
                "message": note.message,
                "trigger_snippets": [snippet["text"] for snippet in snippets],
            }
            results.append(payload)

        return results

    return mcp


def main() -> None:
    """Entry point used when launching via CLI."""

    build_app().run()


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()

