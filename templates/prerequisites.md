## Prerequisites
Skip this if you already checked it in this session.
1. Run `uv --version`. If it fails, `uv` is missing.
   - Ask the user to allow the `uv` install. Do not install it without approval.
   - On macOS and Linux, run `curl -LsSf https://astral.sh/uv/install.sh | sh`.
   - On Windows, run `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`.
   - Docs: https://docs.astral.sh/uv/getting-started/installation/
   - If `uv` is still not found, tell the user to open a new shell, because the install changes `PATH`.
   - If the user refuses, stop. Do not run other steps of this skill.
2. Run `uv run dlthub ai status`. It fails if `dlt[hub]` is missing.
3. Check that the `setup-secrets` skill and the `dlt-workspace-mcp` tools are available. If not, `init` is missing.
4. If anything is missing, tell the user that this skill does not work without `dlt[hub]` and `init`.
5. Ask the user to allow `uvx dlthub-init@latest`. It installs both in place.
   - On agents other than Claude Code, Cursor and Codex, ask the user to install the `init` plugin from the marketplace they used.
6. After the install, tell the user to restart the session, because rules and MCP load only at session start.
7. If the user refuses, stop. Do not run other steps of this skill.
