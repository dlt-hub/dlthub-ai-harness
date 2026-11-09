## Prerequisites
Skip this if you already checked it in this session.
1. Run `uv run dlthub ai status`. It fails if `dlt[hub]` is missing.
2. Check that the `setup-secrets` skill and the `dlt-workspace-mcp` tools are available. If not, `init` is missing.
3. If anything is missing, tell the user that this skill does not work without `dlt[hub]` and `init`.
4. Ask the user to allow `uvx dlthub-init@latest`. It installs both in place.
   - On agents other than Claude Code, Cursor and Codex, ask the user to install the `init` plugin from the marketplace they used.
5. After the install, tell the user to restart the session, because rules and MCP load only at session start.
6. If the user refuses, stop. Do not run other steps of this skill.
