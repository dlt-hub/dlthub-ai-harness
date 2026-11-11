"""Render the Prerequisites block of each public skill from one template.

No marketplace installs `dlt[hub]` or toolkit dependencies, so each public skill
checks them itself, with the dependencies from `toolkit.json`.
Run `uv run python tools/prerequisites.py` to rewrite, `--check` to verify.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AI_DIR = "workbench"
TEMPLATE = "templates/prerequisites.md"
# `init` is circular, and `bootstrap`, `one-shot` and `dlthub-init-skills` set up dlt.
TOOLKITS = (
    "quick-start",
    "rest-api-pipeline",
    "sql-database-pipeline",
    "filesystem-pipeline",
    "data-exploration",
    "transformations",
    "data-quality",
    "dlthub-platform",
    "performance",
)
# the block ends with its "If the user refuses" step
_BLOCK = re.compile(r"^## Prerequisites\n.*?^\d+\. If the user refuses[^\n]*\n", re.M | re.S)


def _toolkit_json(root: Path, toolkit: str) -> dict:
    path = root / AI_DIR / toolkit / ".claude-plugin" / "toolkit.json"
    return json.loads(path.read_text()) if path.exists() else {}


def dependencies(root: Path, toolkit: str) -> list[str]:
    """Return all toolkits that `toolkit` needs, nearest first, without `init`."""
    found: list[str] = []
    queue = list(_toolkit_json(root, toolkit).get("dependencies", []))
    while queue:
        dep = queue.pop(0)
        if dep != "init" and dep not in found:
            found.append(dep)
            queue += _toolkit_json(root, dep).get("dependencies", [])
    return found


def render(root: Path, toolkit: str) -> str:
    """Return the Prerequisites block for the skills of `toolkit`."""
    checks = ""
    for dep in dependencies(root, toolkit):
        entry = _toolkit_json(root, dep)["workflow_entry_skill"]
        checks += f"   - `{entry}` from the `{dep}` toolkit\n"
    return (root / TEMPLATE).read_text().replace("{toolkit_checks}", checks)


def skills(root: Path, toolkit: str) -> list[Path]:
    return sorted((root / AI_DIR / toolkit / "skills").glob("*/SKILL.md"))


def sync(root: Path) -> list[Path]:
    """Rewrite each stale block and return the changed files."""
    changed: list[Path] = []
    for toolkit in TOOLKITS:
        block = render(root, toolkit)
        for skill in skills(root, toolkit):
            text = skill.read_text()
            # a lambda keeps backslashes in the block literal
            new = _BLOCK.sub(lambda _: block, text, count=1)
            if new != text:
                skill.write_text(new)
                changed.append(skill)
    return changed


def main() -> int:
    if "--check" in sys.argv:
        sys.path.insert(0, str(ROOT / "tools"))
        from validate_toolkits import validate_prerequisites  # type: ignore[import-not-found]

        errors = validate_prerequisites(ROOT)
        for e in errors:
            print(e)
        return 1 if errors else 0
    for path in sync(ROOT):
        print(f"updated {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
