"""Framework registry for session history providers."""

from __future__ import annotations

from pathlib import Path

from .base import SessionHistoryProvider

_REGISTRY: dict[str, type[SessionHistoryProvider]] = {}


def register(name: str):
    """Decorator for registering session history providers."""

    def _wrapper(cls: type[SessionHistoryProvider]) -> type[SessionHistoryProvider]:
        _REGISTRY[name] = cls
        return cls

    return _wrapper


def get_history_provider(name: str, history_root: Path) -> SessionHistoryProvider:
    """Instantiate the provider for the requested framework."""

    try:
        provider_cls = _REGISTRY[name]
    except KeyError as exc:  # pragma: no cover - defensive
        known = ", ".join(sorted(_REGISTRY)) or "<none>"
        raise ValueError(f"Unsupported framework '{name}'. Known: {known}") from exc

    return provider_cls(history_root)


# Eagerly import provider modules for registration side-effects
from . import codex, copilot  # noqa: E402,F401

