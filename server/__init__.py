"""Sticky Note MCP server package."""

__all__ = ["build_app"]


def __getattr__(name: str):  # pragma: no cover - module-level convenience
    if name == "build_app":
        from .main import build_app

        return build_app
    raise AttributeError(name)

