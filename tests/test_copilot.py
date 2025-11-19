"""Tests for the GitHub Copilot history provider."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from server.frameworks.copilot import CopilotHistoryProvider


@pytest.fixture
def history_root(tmp_path):
    return tmp_path / "history"


@pytest.fixture
def provider(history_root):
    return CopilotHistoryProvider(history_root)


def test_load_context_direct_file(provider, history_root):
    """Test loading context from a direct file path in history_root."""
    history_root.mkdir()
    session_id = "test-session"
    session_file = history_root / f"{session_id}.json"
    
    data = {
        "requests": [
            {
                "id": "req1",
                "timestamp": 1678886400000,
                "message": {"text": "Hello Copilot"},
                "response": [{"value": "Hello User"}]
            }
        ]
    }
    
    with session_file.open("w") as f:
        json.dump(data, f)
        
    context = provider.load_context(session_id)
    
    assert context.session_id == session_id
    assert len(context.entries) == 2
    assert context.entries[0].role == "user"
    assert context.entries[0].text == "Hello Copilot"
    assert context.entries[1].role == "assistant"
    assert context.entries[1].text == "Hello User"


@patch("server.frameworks.copilot.os.path.expanduser")
def test_load_context_workspace_discovery(mock_expanduser, provider, tmp_path):
    """Test loading context by discovering it in workspace storage."""
    # Mock the workspace storage location
    workspace_storage = tmp_path / "workspaceStorage"
    mock_expanduser.return_value = str(workspace_storage)
    
    # Create a fake workspace with a chat session
    workspace_dir = workspace_storage / "fake-hash"
    chat_sessions = workspace_dir / "chatSessions"
    chat_sessions.mkdir(parents=True)
    
    session_id = "discovered-session"
    session_file = chat_sessions / f"{session_id}.json"
    
    data = {
        "requests": [
            {
                "id": "req2",
                "timestamp": 1678886400000,
                "message": {"text": "Find me"},
                "response": []
            }
        ]
    }
    
    with session_file.open("w") as f:
        json.dump(data, f)
        
    # The provider's history_root doesn't matter here as it falls back to discovery
    context = provider.load_context(session_id)
    
    assert context.session_id == session_id
    assert len(context.entries) == 1
    assert context.entries[0].text == "Find me"


@patch("server.frameworks.copilot.os.path.expanduser")
def test_load_context_not_found(mock_expanduser, provider, tmp_path):
    """Test that FileNotFoundError is raised when session is not found and no fallback exists."""
    # Point to an empty directory so no standard paths are found
    mock_expanduser.return_value = str(tmp_path / "nonexistent")
    
    with pytest.raises(FileNotFoundError):
        provider.load_context("non-existent-session")
