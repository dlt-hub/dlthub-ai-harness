#!/usr/bin/env python3
"""List skill names and descriptions from toolkit(s) or an eval workspace.

Extracts frontmatter (name, description) from all SKILL.md files.

Usage:
    python tools/list_skill_descriptions.py workbench/init
    python tools/list_skill_descriptions.py workbench/rest-api-pipeline workbench/init
    python tools/list_skill_descriptions.py evals/.evals/init--setup-secrets--with-rest-api
    python tools/list_skill_descriptions.py --json workbench/init
"""

import argparse
import json
import re
import sys
from pathlib import Path


def parse_frontmatter(path: Path) -> dict:
    """Extract YAML-like frontmatter from a markdown file."""
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not match:
        return {}
    fm = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fm[key.strip()] = value.strip().strip('"').strip("'")
    return fm


def find_skills(path: Path) -> list[dict]:
    """Find all skills under a path (toolkit dir or eval workspace)."""
    results: list[dict[str, str]] = []

    # Check if it's an eval workspace (.claude/skills/)
    claude_skills = path / ".claude" / "skills"
    # Check if it's a toolkit (skills/)
    toolkit_skills = path / "skills"

    if claude_skills.is_dir():
        skills_dir = claude_skills
    elif toolkit_skills.is_dir():
        skills_dir = toolkit_skills
    else:
        return results

    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        fm = parse_frontmatter(skill_md)
        if fm.get("name"):
            results.append({
                "name": fm["name"],
                "description": fm.get("description", ""),
                "path": str(skill_md),
            })

    return results


def main():
    parser = argparse.ArgumentParser(
        description="List skill descriptions from toolkits or eval workspaces"
    )
    parser.add_argument("paths", nargs="+", help="Toolkit dirs or eval workspace dirs")
    parser.add_argument("--json", action="store_true", dest="as_json", help="Output as JSON")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    all_skills = []

    for p in args.paths:
        path = Path(p)
        if not path.is_absolute():
            path = root / path
        if not path.is_dir():
            print(f"WARNING: {p} is not a directory, skipping", file=sys.stderr)
            continue
        all_skills.extend(find_skills(path))

    if args.as_json:
        print(json.dumps(all_skills, indent=2))
    else:
        for s in all_skills:
            print(f"  {s['name']}: {s['description']}")


if __name__ == "__main__":
    main()
