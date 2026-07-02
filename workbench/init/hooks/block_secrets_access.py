#!/usr/bin/env python3
"""PreToolUse hook: block Read/Grep/Bash access to dlt secrets and .env files.

Shared entrypoint for Claude Code and Codex — both use the identical
PreToolUse I/O contract (stdin: {tool_name, tool_input}, stdout on deny:
{hookSpecificOutput: {...}}).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _secrets_patterns import DENY_MESSAGE, command_is_blocked, is_blocked_path


def _is_blocked(tool_name: str, tool_input: dict) -> bool:
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


def main() -> None:
    payload = json.load(sys.stdin)
    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {})

    if _is_blocked(tool_name, tool_input):
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
        pass
