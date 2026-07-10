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

Blocks reads of dlt secrets (secrets.toml, *.secrets.toml except
example.secrets.toml/template.secrets.toml/sample.secrets.toml) and dotenv
files (.env, .env.* except .env.example/.env.template/.env.sample). Matching
is case-insensitive — the guarded platforms (macOS, Windows) resolve
SECRETS.TOML and secrets.toml to the same file.

Failure policy:
- stdin is not a JSON object: the operation cannot be identified, so allow —
  but loudly (traceback on stderr, {"permission": "allow"} on stdout, exit 1).
- the payload identifies a guarded operation but evaluating it raises: deny
  (fail closed) in the caller's dialect, traceback on stderr.

The deny channel is always the JSON on stdout, never the exit code: in both
Claude Code and Cursor only exit 2 blocks; exit 1 is a non-blocking error and
the action proceeds.
"""

import json
import os
import shlex
import sys
import traceback

_CURSOR_EVENTS = {"beforeReadFile", "beforeShellExecution"}
_ALLOWED_ENV_SUFFIXES = {"example", "template", "sample"}

DENY_MESSAGE = (
    "Blocked: direct access to secrets/env files is not allowed. "
    "Use the dlt-workspace-mcp `secrets_view_redacted` tool to inspect values (redacted) "
    "or `secrets_update_fragment` to write placeholders. See the setup-secrets skill."
)


def is_blocked_path(path: str) -> bool:
    """True if the basename of `path` looks like a dlt secrets or dotenv file."""
    # lowercase: macOS/Windows resolve SECRETS.TOML and secrets.toml to the same file
    name = os.path.basename(path.replace("\\", "/")).lower()

    if name == "secrets.toml":
        return True
    if name.endswith(".secrets.toml"):
        prefix = name[: -len(".secrets.toml")]
        return prefix not in _ALLOWED_ENV_SUFFIXES

    if name == ".env":
        return True
    if name.startswith(".env."):
        suffix = name.rsplit(".", 1)[-1]
        return suffix not in _ALLOWED_ENV_SUFFIXES

    return False


def command_is_blocked(command: str) -> bool:
    """True if any token in a shell command string looks like a blocked path."""
    # shlex.split(None) silently reads stdin on older pythons instead of
    # raising; force a raise so the caller fails closed on a malformed payload
    if not isinstance(command, str):
        raise TypeError("command is not a string")
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
        raw_paths = tool_input.get("paths")
        if isinstance(raw_paths, str):
            paths = [raw_paths]
        elif isinstance(raw_paths, list):
            paths = list(raw_paths)
        else:
            paths = []
        # grep payload shapes vary across agents; check every path-like field
        for key in ("path", "file_path", "glob"):
            if tool_input.get(key):
                paths.append(tool_input[key])
        return any(is_blocked_path(p) for p in paths)

    if tool_name == "Bash":
        return command_is_blocked(tool_input.get("command", ""))

    return False


def _cursor_blocked(payload: dict) -> bool:
    if payload["hook_event_name"] == "beforeReadFile":
        return is_blocked_path(payload.get("file_path", ""))
    return command_is_blocked(payload.get("command", ""))


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
        if not isinstance(payload, dict):
            raise TypeError("payload is not a JSON object")
    except Exception:
        # unidentifiable input: cannot name the operation, so let it proceed,
        # but never silently — traceback on stderr, exit 1 (a non-blocking
        # error; only exit 2 blocks). {"permission": "allow"} is a universal
        # proceed: cursor honors it, claude/codex ignore output that carries
        # no permissionDecision.
        traceback.print_exc()
        print(json.dumps({"permission": "allow"}))
        return 1

    is_cursor = payload.get("hook_event_name") in _CURSOR_EVENTS

    try:
        blocked = _cursor_blocked(payload) if is_cursor else _claude_codex_blocked(payload)
    except Exception:
        # identified a guarded operation but could not prove it safe
        # (unexpected field types, vendor payload drift): fail closed
        traceback.print_exc()
        blocked = True

    if is_cursor:
        if blocked:
            print(json.dumps({"permission": "deny", "user_message": DENY_MESSAGE}))
        else:
            print(json.dumps({"permission": "allow"}))
    elif blocked:
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
