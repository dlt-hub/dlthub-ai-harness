#!/usr/bin/env python3
"""Cursor beforeReadFile / beforeShellExecution hook: block secrets/env access.

Cursor's I/O contract differs from Claude/Codex's PreToolUse: fields live at
the top level of stdin (no tool_input wrapper), and the event is identified
by hook_event_name rather than tool_name. Output uses {"permission": ...}
rather than {"hookSpecificOutput": {...}}.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _secrets_patterns import DENY_MESSAGE, command_is_blocked, is_blocked_path


def _is_blocked(event_name: str, payload: dict) -> bool:
    if event_name == "beforeReadFile":
        return is_blocked_path(payload.get("file_path", ""))

    if event_name == "beforeShellExecution":
        return command_is_blocked(payload.get("command", ""))

    return False


def main() -> None:
    payload = json.load(sys.stdin)
    event_name = payload.get("hook_event_name", "")

    if _is_blocked(event_name, payload):
        print(json.dumps({"permission": "deny", "user_message": DENY_MESSAGE}))
    else:
        print(json.dumps({"permission": "allow"}))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(json.dumps({"permission": "allow"}))
