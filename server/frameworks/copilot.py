"""GitHub Copilot session history provider."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, List

from . import register
from .base import HistoryEntry, SessionContext, SessionHistoryProvider

logger = logging.getLogger(__name__)


@register("copilot")
class CopilotHistoryProvider(SessionHistoryProvider):
    """Reads GitHub Copilot Chat history from VS Code workspace storage."""

    def load_context(self, session_id: str) -> SessionContext:
        """
        Load the session context.
        
        If session_id is provided and matches a specific file, that file is used.
        Otherwise, we fall back to the most recently modified chat session across
        all discovered workspaces.
        """
        # 1. Find all potential session files
        candidates = self._find_session_files(session_id)
        
        if not candidates:
             raise FileNotFoundError(
                f"No Copilot chat history found. Checked VS Code workspace storage."
            )

        # 2. Sort by modification time (newest first)
        #    If session_id was a specific UUID match, it would have been returned
        #    as the primary candidate if we implemented exact matching logic in _find_session_files.
        #    However, since we want to support "current session" implicitly, we'll just
        #    look at all of them and pick the newest one if we can't find an exact match.
        
        # Check for exact match first
        if session_id:
            exact_matches = [p for p in candidates if p.name == f"{session_id}.json"]
            if exact_matches:
                return self._load_file(exact_matches[0], session_id)

        # Fallback: Sort by mtime and try to load the newest valid one
        candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        
        logger.info(f"Found {len(candidates)} candidate chat sessions. Checking for most recent valid one...")

        for path in candidates:
            try:
                # Use the filename as the session_id for the context
                actual_session_id = path.stem
                logger.info(f"Attempting to load session from: {path}")
                context = self._load_file(path, actual_session_id)
                logger.info(f"Successfully loaded session: {actual_session_id} from {path}")
                return context
            except Exception as e:
                logger.warning(f"Failed to parse session file {path}: {e}")
                continue

        raise FileNotFoundError(
            f"Could not parse any valid history from {len(candidates)} candidates."
        )

    def _load_file(self, path: Path, session_id: str) -> SessionContext:
        entries = self._parse_history_file(path)
        if entries:
            return SessionContext(session_id=session_id, entries=tuple(entries))
        raise ValueError("Empty history file")

    def _find_session_files(self, session_id: str) -> List[Path]:
        """Find all potential history files."""
        
        candidates = []
        
        # If history_root is explicitly set
        if self.history_root.exists():
             if self.history_root.is_file():
                 return [self.history_root]
             # Check recursively for any json files in chatSessions
             candidates.extend(self.history_root.rglob("chatSessions/*.json"))
             # Also check directly if history_root IS a chatSessions dir or contains json files
             candidates.extend(self.history_root.glob("*.json"))

        # Search in standard VS Code locations
        base_paths = [
            Path(os.path.expanduser("~/Library/Application Support/Code/User/workspaceStorage")),
            Path(os.path.expanduser("~/Library/Application Support/Code - Insiders/User/workspaceStorage"))
        ]

        for base in base_paths:
            if not base.exists():
                continue
            
            # We want ALL chat sessions to enable "most recent" fallback
            # This might be expensive if there are thousands of workspaces, 
            # but typically chatSessions are sparse.
            # Using rglob("chatSessions/*.json") is cleaner but might traverse too much.
            # Let's iterate workspaces one level deep.
            logger.debug(f"Scanning for chat sessions in: {base}")
            for workspace_dir in base.iterdir():
                if not workspace_dir.is_dir():
                    continue
                
                chat_dir = workspace_dir / "chatSessions"
                if chat_dir.exists():
                    candidates.extend(chat_dir.glob("*.json"))
        
        # Deduplicate paths
        unique_candidates = list(set(candidates))
        logger.debug(f"Found {len(unique_candidates)} unique chat session files.")
        return unique_candidates

    def _parse_history_file(self, path: Path) -> List[HistoryEntry]:
        """Parse a Copilot chat session JSON file."""
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        entries: List[HistoryEntry] = []
        
        # The root object has a "requests" array
        requests = data.get("requests", [])
        
        for req in requests:
            # User query
            timestamp_ms = req.get("timestamp")
            timestamp = datetime.fromtimestamp(timestamp_ms / 1000.0) if timestamp_ms else None
            
            message = req.get("message", {})
            user_text = message.get("text", "")
            
            if user_text:
                entries.append(HistoryEntry(
                    timestamp=timestamp,
                    kind="message",
                    text=user_text,
                    role="user",
                    metadata={"requestId": req.get("id")}
                ))

            # Assistant response
            response = req.get("response", [])
            for resp_item in response:
                resp_value = resp_item.get("value", "")
                if resp_value:
                     entries.append(HistoryEntry(
                        timestamp=timestamp, # Response usually shares roughly the same time
                        kind="message",
                        text=resp_value,
                        role="assistant",
                        metadata={"requestId": req.get("id")}
                    ))
                
                elif resp_item.get("kind") == "toolInvocationSerialized":
                    tool_id = resp_item.get("toolId")
                    tool_call_id = resp_item.get("toolCallId")
                    result_details = resp_item.get("resultDetails", {})
                    input_args = result_details.get("input")
                    
                    # Create a readable text representation for searchability
                    text_repr = f"Tool Call: {tool_id}\nArguments: {input_args}"
                    
                    entries.append(HistoryEntry(
                        timestamp=timestamp,
                        kind="tool_call",
                        text=text_repr,
                        role="assistant",
                        metadata={
                            "requestId": req.get("id"),
                            "toolCallId": tool_call_id,
                            "toolId": tool_id,
                            "input": input_args,
                            "output": result_details.get("output")
                        }
                    ))
        
        return entries
