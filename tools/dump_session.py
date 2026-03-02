"""Dump a Claude Code session JSONL file as readable text.

Usage:
    python dump_session.py <session.jsonl> [output.txt]

If output.txt is omitted, prints to stdout.
"""

import json
import sys


def dump_session(input_path, output=sys.stdout):
    with open(input_path, encoding="utf-8") as f:
        lines = f.readlines()

    for line in lines:
        msg = json.loads(line)
        if msg.get("type") not in ("user", "assistant"):
            continue

        inner = msg.get("message", {})
        role = inner.get("role", msg["type"]).upper()
        content = inner.get("content", "")

        parts = []
        if isinstance(content, str):
            if content.strip() and not content.strip().startswith("<system-reminder>"):
                parts.append(content.strip())
        elif isinstance(content, list):
            for block in content:
                if block.get("type") == "text":
                    text = block.get("text", "").strip()
                    if text.startswith("<system-reminder>"):
                        continue
                    if text.startswith("Base directory for this skill:"):
                        parts.append("[Skill instructions loaded]")
                        continue
                    if text:
                        parts.append(text)
                elif block.get("type") == "tool_use":
                    name = block.get("name", "")
                    inp = block.get("input", {})
                    if name == "Bash":
                        parts.append(f"  >>> bash: {inp.get('command', '')[:120]}")
                    elif name == "Write":
                        parts.append(f"  >>> write: {inp.get('file_path', '')}")
                    elif name == "Edit":
                        parts.append(f"  >>> edit: {inp.get('file_path', '')}")
                    elif name == "Read":
                        parts.append(f"  >>> read: {inp.get('file_path', '')}")
                    elif name == "Skill":
                        parts.append(f"  >>> skill: {inp.get('skill', '')} {inp.get('args', '')}")
                    elif name == "WebSearch":
                        parts.append(f"  >>> search: {inp.get('query', '')}")
                    elif name == "WebFetch":
                        parts.append(f"  >>> fetch: {inp.get('url', '')}")
                    else:
                        parts.append(f"  >>> {name}")

        text = "\n".join(parts)
        if text.strip():
            ts = msg.get("timestamp", "")[:19]
            print(f"## {role} [{ts}]\n{text}\n", file=output)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        sys.exit(1)

    input_path = sys.argv[1]
    if len(sys.argv) >= 3:
        with open(sys.argv[2], "w", encoding="utf-8") as out:
            dump_session(input_path, out)
    else:
        dump_session(input_path)
