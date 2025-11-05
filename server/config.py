"""Configuration helpers for the Sticky Note MCP server."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_FRAMEWORK = "codex"
ENV_FRAMEWORK = "MCP_AGENT_FRAMEWORK"
ENV_NOTES_DIR = "STICKY_NOTES_DIR"
ENV_HISTORY_DIR = "SESSION_HISTORY_DIR"


@dataclass(slots=True)
class ServerConfig:
    """Container for runtime configuration loaded from environment variables."""

    framework: str
    notes_dir: Path
    history_dir: Path

    @property
    def notes_file(self) -> Path:
        """Return the path to the JSONL file that stores sticky notes."""

        return self.notes_dir / "sticky_notes.jsonl"


def _read_path(env_key: str, default: Path) -> Path:
    """Read a filesystem path from an environment variable."""

    value = os.getenv(env_key)
    if value:
        return Path(value).expanduser().resolve()
    return default


def load_config() -> ServerConfig:
    """Load server configuration from environment variables."""

    cwd = Path.cwd()
    default_notes = cwd / "data" / "sticky_notes"
    default_history = cwd / "data" / "history"

    framework = os.getenv(ENV_FRAMEWORK, DEFAULT_FRAMEWORK).strip().lower()
    notes_dir = _read_path(ENV_NOTES_DIR, default_notes)
    history_dir = _read_path(ENV_HISTORY_DIR, default_history)

    return ServerConfig(
        framework=framework,
        notes_dir=notes_dir,
        history_dir=history_dir,
    )

