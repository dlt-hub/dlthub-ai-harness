#!/usr/bin/env python3
"""Extract references from toolkit markdown files for validation.

For each toolkit under workbench/, outputs:
- Component map: skills, commands, rules (for cross-reference resolution)
- Per-file URL extractions with surrounding context lines

Usage:
    python tools/extract_refs.py [toolkit_path]
    python tools/extract_refs.py                     # all toolkits
    python tools/extract_refs.py workbench/rest-api-pipeline  # single toolkit
"""

import json
import re
import sys
from pathlib import Path

CONTEXT_LINES = 2  # lines before/after each URL


def extract_urls_with_context(text: str) -> list[dict]:
    """Extract URLs with surrounding context lines."""
    lines = text.splitlines()
    results = []
    seen = set()
    for i, line in enumerate(lines):
        for match in re.finditer(r'https?://[^\s\)>`\'"]+', line):
            url = match.group().rstrip(".,;:")
            if url in seen:
                continue
            seen.add(url)
            start = max(0, i - CONTEXT_LINES)
            end = min(len(lines), i + CONTEXT_LINES + 1)
            context = "\n".join(lines[start:end])
            results.append({"url": url, "line": i + 1, "context": context})
    return results


def build_component_map(plugin_dir: Path) -> dict:
    """Build map of addressable components in a toolkit."""
    components = {"skills": [], "commands": [], "rules": []}

    skills_dir = plugin_dir / "skills"
    if skills_dir.is_dir():
        for d in sorted(skills_dir.iterdir()):
            if d.is_dir() and (d / "SKILL.md").exists():
                components["skills"].append(d.name)

    commands_dir = plugin_dir / "commands"
    if commands_dir.is_dir():
        for f in sorted(commands_dir.iterdir()):
            if f.suffix == ".md":
                components["commands"].append(f.stem)

    rules_dir = plugin_dir / "rules"
    if rules_dir.is_dir():
        for f in sorted(rules_dir.rglob("*.md")):
            rel = str(f.relative_to(rules_dir))
            components["rules"].append(rel)

    return components


def scan_toolkit(plugin_dir: Path) -> dict:
    """Scan a single toolkit directory."""
    components = build_component_map(plugin_dir)
    files = []

    for md_file in sorted(plugin_dir.rglob("*.md")):
        # skip .claude-plugin/
        rel_parts = md_file.relative_to(plugin_dir).parts
        if any(part.startswith(".") for part in rel_parts):
            continue

        text = md_file.read_text()
        rel = str(md_file.relative_to(plugin_dir))
        urls = extract_urls_with_context(text)

        files.append({"path": rel, "urls": urls})

    return {
        "toolkit": plugin_dir.name,
        "dir": str(plugin_dir),
        "components": components,
        "files": files,
    }


def main():
    root = Path(__file__).resolve().parent.parent
    ai_dir = root / "workbench"

    if len(sys.argv) > 1:
        target = root / sys.argv[1]
        if not target.is_dir():
            print(f"Not a directory: {target}", file=sys.stderr)
            sys.exit(1)
        toolkits = [scan_toolkit(target)]
    else:
        toolkits = []
        for d in sorted(ai_dir.iterdir()):
            if d.is_dir() and not d.name.startswith("_"):
                toolkits.append(scan_toolkit(d))

    print(json.dumps(toolkits, indent=2))


if __name__ == "__main__":
    main()
