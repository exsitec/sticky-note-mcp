from __future__ import annotations

import json
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

import pytest

from server.config import ServerConfig
from server.frameworks.codex import CodexHistoryProvider


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def test_codex_history_provider_parses_session(tmp_path, monkeypatch):
    history_dir = tmp_path / "history"
    history_dir.mkdir()

    session_file = history_dir / "session.jsonl"
    lines = [
        {
            "timestamp": _iso(datetime(2025, 5, 7, 17, 24, 21, 123000, tzinfo=timezone.utc)),
            "type": "session_meta",
            "payload": {
                "id": "conversation-id",
                "instructions": "Stay focused",
            },
        },
        {
            "timestamp": _iso(datetime(2025, 5, 7, 17, 25, 0, tzinfo=timezone.utc)),
            "type": "response_item",
            "payload": {
                "type": "message",
                "payload": {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "Hello agent"},
                    ],
                },
            },
        },
        {
            "timestamp": _iso(datetime(2025, 5, 7, 17, 26, 0, tzinfo=timezone.utc)),
            "type": "event_msg",
            "payload": {
                "type": "user_message",
                "payload": {
                    "message": "User event text",
                },
            },
        },
    ]

    with session_file.open("w", encoding="utf-8") as handle:
        for line in lines:
            handle.write(json.dumps(line) + "\n")

    provider = CodexHistoryProvider(history_dir)
    context = provider.load_context("conversation-id")

    assert context.session_id == "conversation-id"
    assert len(context.entries) == 2
    assert any(entry.text == "Hello agent" for entry in context.entries)
    assert all(entry.kind != "event:user_message" for entry in context.entries)


def test_codex_history_provider_falls_back_to_latest_session(tmp_path):
    history_dir = tmp_path / "history"
    history_dir.mkdir()

    session_file = history_dir / "session.jsonl"
    lines = [
        {
            "timestamp": _iso(datetime(2025, 5, 7, 17, 24, 21, 123000, tzinfo=timezone.utc)),
            "type": "session_meta",
            "payload": {
                "id": "conversation-id",
                "instructions": "Stay focused",
            },
        },
        {
            "timestamp": _iso(datetime(2025, 5, 7, 17, 25, 0, tzinfo=timezone.utc)),
            "type": "response_item",
            "payload": {
                "type": "message",
                "payload": {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "Hello agent"},
                    ],
                },
            },
        },
    ]

    with session_file.open("w", encoding="utf-8") as handle:
        for line in lines:
            handle.write(json.dumps(line) + "\n")

    provider = CodexHistoryProvider(history_dir)
    context = provider.load_context("handshake-id")

    assert context.session_id == "handshake-id"
    assert any(entry.text == "Hello agent" for entry in context.entries)


def test_codex_history_provider_raises_when_history_empty(tmp_path):
    history_dir = tmp_path / "history"
    history_dir.mkdir()

    other_file = history_dir / "session.jsonl"
    lines = [
        {
            "timestamp": _iso(datetime(2025, 5, 7, 17, 24, 21, tzinfo=timezone.utc)),
            "type": "session_meta",
            "payload": {
                "id": "different-session-id",
                "instructions": None,
            },
        },
    ]

    with other_file.open("w", encoding="utf-8") as handle:
        for line in lines:
            handle.write(json.dumps(line) + "\n")

    provider = CodexHistoryProvider(history_dir)

    with pytest.raises(FileNotFoundError):
        provider.load_context("target-session")


def test_codex_history_provider_accepts_sessions_without_instructions(tmp_path):
    history_dir = tmp_path / "history"
    history_dir.mkdir()

    session_file = history_dir / "rollout-target-session.jsonl"
    lines = [
        {
            "timestamp": _iso(datetime(2025, 5, 7, 17, 24, 21, tzinfo=timezone.utc)),
            "type": "session_meta",
            "payload": {
                "id": "target-session",
                "instructions": None,
            },
        },
        {
            "timestamp": _iso(datetime(2025, 5, 7, 17, 25, 0, tzinfo=timezone.utc)),
            "type": "response_item",
            "payload": {
                "type": "message",
                "payload": {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "Hello again"},
                    ],
                },
            },
        },
    ]

    with session_file.open("w", encoding="utf-8") as handle:
        for line in lines:
            handle.write(json.dumps(line) + "\n")

    provider = CodexHistoryProvider(history_dir)
    context = provider.load_context("target-session")

    assert context.session_id == "target-session"
    assert len(context.entries) == 1
    assert context.entries[0].text == "Hello again"


def test_codex_history_provider_loads_sample_codex_session():
    repo_root = Path(__file__).resolve().parents[1]
    history_dir = repo_root / ".codex" / "sessions"

    provider = CodexHistoryProvider(history_dir)
    context = provider.load_context("019a542a-c7d6-7d42-ba10-6ae0c27b56a3")

    assert context.session_id == "019a542a-c7d6-7d42-ba10-6ae0c27b56a3"
    assert len(context.entries) >= 3
    texts = {entry.text for entry in context.entries}
    assert any("Tiktok" in text for text in texts)
    assert any("ByteDance" in text for text in texts)


def test_codex_history_provider_filters_noise(tmp_path):
    history_dir = tmp_path / "history"
    history_dir.mkdir()

    session_file = history_dir / "session.jsonl"
    lines = [
        {
            "timestamp": _iso(datetime(2025, 5, 7, 17, 24, 21, tzinfo=timezone.utc)),
            "type": "session_meta",
            "payload": {"id": "session-id"},
        },
        {
            "timestamp": _iso(datetime(2025, 5, 7, 17, 25, 0, tzinfo=timezone.utc)),
            "type": "event_msg",
            "payload": {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 1}}},
        },
        {
            "timestamp": _iso(datetime(2025, 5, 7, 17, 25, 1, tzinfo=timezone.utc)),
            "type": "event_msg",
            "payload": {"type": "agent_reasoning", "text": "**Hidden thoughts**"},
        },
        {
            "timestamp": _iso(datetime(2025, 5, 7, 17, 25, 1, 500000, tzinfo=timezone.utc)),
            "type": "event_msg",
            "payload": {"type": "agent_reasoning"},
        },
        {
            "timestamp": _iso(datetime(2025, 5, 7, 17, 25, 2, tzinfo=timezone.utc)),
            "type": "event_msg",
            "payload": {"type": "agent_message", "message": "Duplicate assistant message"},
        },
        {
            "timestamp": _iso(datetime(2025, 5, 7, 17, 25, 3, tzinfo=timezone.utc)),
            "type": "event_msg",
            "payload": {"type": "user_message", "message": "Duplicate user message"},
        },
        {
            "timestamp": _iso(datetime(2025, 5, 7, 17, 26, 0, tzinfo=timezone.utc)),
            "type": "response_item",
            "payload": {
                "type": "message",
                "payload": {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "Useful user text"},
                    ],
                },
            },
        },
        {
            "timestamp": _iso(datetime(2025, 5, 7, 17, 26, 10, tzinfo=timezone.utc)),
            "type": "response_item",
            "payload": {
                "type": "reasoning",
                "summary": [{"type": "summary_text", "text": "**Visible reasoning**"}],
                "payload": {
                    "role": "assistant",
                    "text": "Visible reasoning",
                },
            },
        },
    ]

    with session_file.open("w", encoding="utf-8") as handle:
        for line in lines:
            handle.write(json.dumps(line) + "\n")

    provider = CodexHistoryProvider(history_dir)
    context = provider.load_context("session-id")

    kinds = {entry.kind for entry in context.entries}
    texts = {entry.text for entry in context.entries}

    assert "event:token_count" not in kinds
    assert "event:agent_reasoning" in kinds
    assert "event:agent_message" not in kinds
    assert "event:user_message" not in kinds
    assert any(text == "Useful user text" for text in texts)
    assert any(text == "Visible reasoning" for text in texts)
    assert any(text == "**Hidden thoughts**" for text in texts)



