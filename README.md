# sticky-note-mcp

An MCP server built with the FastMCP Python package that lets agents persist sticky notes and surface them when the current session matches predefined context.

## Features

- `create_sticky_note(message, context_regex, note_id?)` persists notes in JSONL format and returns every snippet from the active session whose text matches the supplied regex (returned as plain strings).
- `read_relevant_sticky_notes()` scans the active session history and, for each unseen note whose regex matches, returns `{"message", "trigger_snippets"}` once per session.
- Pluggable session history provider architecture selected through an environment variable (defaults to `codex`).
- Codex implementation reads rollout `.jsonl` history files and normalises content items, reasoning traces, and important events.

## Configuration

Environment variables accepted by the server:

- `MCP_AGENT_FRAMEWORK` – selects which session history provider to use (default: `codex`).
- `STICKY_NOTES_DIR` – directory where the `sticky_notes.jsonl` file is created (default: `<repo>/data/sticky_notes`).
- `SESSION_HISTORY_DIR` – directory containing agent session histories (default: `<repo>/data/history`; when running inside Codex point this to `~/.codex/sessions`).

## Using with Codex

1. Install the server’s runtime dependency (once per Python environment):

   ```bash
   pip install fastmcp
   ```

2. Edit your Codex configuration at `~/.codex/config.toml` and add an entry under `mcp_servers` that launches the server, for example:

   ```toml
   [mcp_servers.sticky_note]
   command = "/Users/<username>/.pyenv/shims/python"
   args = ["-m", "server.main"]
   cwd = "/path/to/sticky-note-mcp"
   env = { "SESSION_HISTORY_DIR" = "/Users/<username>/.codex/sessions" }
   ```

   - To discover your Python path, run `which python` (or `pyenv which python`) and drop that into `command`.
   - Set `cwd` to the directory containing this repository so relative imports and data paths resolve correctly.
   - Point `SESSION_HISTORY_DIR` at the history store you want the server to read; inside Codex this should be `~/.codex/sessions`, but you can substitute another directory if you maintain histories elsewhere.

3. Restart Codex (or run `codex mcp list`) so it picks up the new MCP server. The sticky-note tools—`mcp__sticky_note__create_sticky_note` and `mcp__sticky_note__read_relevant_sticky_notes`—will appear in the tool palette.

## Tests

Run the automated tests with `pytest`:

```bash
pip install -r requirements-dev.txt  # if you capture dependencies separately
pytest
```

The test suite covers sticky note persistence, session tracking, and Codex history parsing.
