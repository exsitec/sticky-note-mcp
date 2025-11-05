from __future__ import annotations

from datetime import datetime, timezone

from server.session_state import SessionNoteTracker
from server.storage import StickyNote, StickyNoteStore


def test_sticky_note_store_roundtrip(tmp_path):
    notes_file = tmp_path / "notes" / "sticky_notes.jsonl"
    store = StickyNoteStore(notes_file)

    note = StickyNote(
        id="note-1",
        message="Remember to update docs",
        context_regex="docs",
        created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        trigger_snippets=["Docs mention"],
    )
    store.append(note)

    stored = store.all_notes()
    assert len(stored) == 1
    restored = stored[0]
    assert restored.id == note.id
    assert restored.trigger_snippets == note.trigger_snippets
    assert restored.created_at.tzinfo is not None


def test_session_note_tracker_filters_seen():
    tracker = SessionNoteTracker()
    session_id = "session-123"
    tracker.mark_shown(session_id, "note-a")

    assert tracker.has_shown(session_id, "note-a")
    assert tracker.unseen(session_id, ["note-a", "note-b"]) == ["note-b"]

