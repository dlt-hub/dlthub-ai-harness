#!/usr/bin/env python3
"""Generate the Codex form of each public toolkit's rules.

Codex plugins ship skills only: no rules, no AGENTS.md. So each toolkit's `rules/*.md` are
concatenated into one skill, `workbench/<toolkit>/codex/skills/<toolkit>-rules/SKILL.md`.
The only command (`quick-start` `/start`) just invokes the `quick-start` skill, which Codex
already has, so commands need no conversion.

    python tools/gen_codex_rules.py           # rewrite the generated files
    python tools/gen_codex_rules.py --check   # exit 1 when they are stale
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLKITS = (
    "init", "quick-start", "rest-api-pipeline", "sql-database-pipeline", "filesystem-pipeline",
    "data-exploration", "transformations", "data-quality", "dlthub-platform", "performance",
)  # fmt: skip
_FRONTMATTER = re.compile(r"\A---\n.*?\n---\n", re.S)


def render(toolkit: str) -> str:
    rules = sorted((ROOT / "workbench" / toolkit / "rules").glob("*.md"))
    bodies = [_FRONTMATTER.sub("", r.read_text(encoding="utf-8")).strip() for r in rules]
    description = (
        f"Always-on rules of the dltHub `{toolkit}` toolkit: workflow order, conventions and"
        f" constraints. Read it at the start of any work with the `{toolkit}` toolkit and"
        " before using its skills. Codex plugins cannot ship always-loaded rules, so this"
        " skill carries them."
    )
    return (
        f"---\nname: {toolkit}-rules\ndescription: {json.dumps(description)}\n---\n\n"
        + "\n\n".join(bodies)
        + "\n"
    )


def target(toolkit: str) -> Path:
    return ROOT / "workbench" / toolkit / "codex" / "skills" / f"{toolkit}-rules" / "SKILL.md"


def stale() -> list[Path]:
    """Generated files that are missing or differ from what `render` gives."""
    return [
        target(t)
        for t in TOOLKITS
        if not target(t).exists() or target(t).read_text(encoding="utf-8") != render(t)
    ]


if __name__ == "__main__":
    if "--check" in sys.argv:
        bad = stale()
        for p in bad:
            print(f"stale: {p.relative_to(ROOT)}; run `python tools/gen_codex_rules.py`")
        sys.exit(1 if bad else 0)
    for t in TOOLKITS:
        target(t).parent.mkdir(parents=True, exist_ok=True)
        target(t).write_text(render(t), encoding="utf-8")
