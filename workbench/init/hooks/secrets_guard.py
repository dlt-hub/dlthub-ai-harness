#!/usr/bin/env python3
"""Universal secrets-read guard for Claude Code, Codex, and Cursor hooks.

One stdlib-only file, no sibling imports — safe to copy anywhere. Detects the
calling agent from the stdin payload shape and answers in that agent's dialect:

- Claude Code / Codex (PreToolUse): stdin {"tool_name": ..., "tool_input": {...}},
  deny via {"hookSpecificOutput": {"permissionDecision": "deny", ...}} on stdout,
  allow via silence (exit 0, no output).
- Cursor (beforeReadFile / beforeShellExecution): stdin has "hook_event_name" set
  to one of those event names with "file_path"/"command" at the top level,
  deny via {"permission": "deny", ...}, allow via {"permission": "allow"}.

Blocks reads of dlt secrets (secrets.toml, *.secrets.toml) and dotenv files
(.env, .env.* except .env.example/.env.template/.env.sample).
"""

import json
import os
import shlex
import sys

_CURSOR_EVENTS = {"beforeReadFile", "beforeShellExecution"}
_ALLOWED_ENV_SUFFIXES = {"example", "template", "sample"}

DENY_MESSAGE = (
    "Blocked: direct access to secrets/env files is not allowed. "
    "Use the dlt-workspace-mcp `secrets_view_redacted` tool to inspect values (redacted) "
    "or `secrets_update_fragment` to write placeholders. See the setup-secrets skill."
)


def is_blocked_path(path: str) -> bool:
    """True if the basename of `path` looks like a dlt secrets or dotenv file."""
    name = os.path.basename(path.replace("\\", "/"))

    if name == "secrets.toml" or name.endswith(".secrets.toml"):
        return True

    if name == ".env":
        return True
    if name.startswith(".env."):
        suffix = name.rsplit(".", 1)[-1]
        return suffix not in _ALLOWED_ENV_SUFFIXES

    return False


def command_is_blocked(command: str) -> bool:
    """True if any token in a shell command string looks like a blocked path."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()

    return any(is_blocked_path(token) for token in tokens)


def _claude_codex_blocked(payload: dict) -> bool:
    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}

    if tool_name == "Read":
        return is_blocked_path(tool_input.get("file_path", ""))

    if tool_name == "Grep":
        paths = tool_input.get("paths") or []
        if tool_input.get("path"):
            paths = [*paths, tool_input["path"]]
        return any(is_blocked_path(p) for p in paths)

    if tool_name == "Bash":
        return command_is_blocked(tool_input.get("command", ""))

    return False


def _cursor_blocked(payload: dict) -> bool:
    if payload["hook_event_name"] == "beforeReadFile":
        return is_blocked_path(payload.get("file_path", ""))
    return command_is_blocked(payload.get("command", ""))


def main() -> None:
    payload = json.load(sys.stdin)

    if payload.get("hook_event_name") in _CURSOR_EVENTS:
        if _cursor_blocked(payload):
            print(json.dumps({"permission": "deny", "user_message": DENY_MESSAGE}))
        else:
            print(json.dumps({"permission": "allow"}))
        return

    if _claude_codex_blocked(payload):
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": DENY_MESSAGE,
                    }
                }
            )
        )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Fail open: a bug in this guard must never block normal tool use.
        # For Cursor a reply is expected, but hooks fail open there too when
        # no valid JSON is produced.
        pass
