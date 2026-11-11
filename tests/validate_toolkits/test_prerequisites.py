"""Every public SKILL.md carries its rendered prerequisites block after its first heading."""

import json
from pathlib import Path

from tests.validate_toolkits.utils import write

from tools import prerequisites as P
from tools import validate_toolkits as V

TEMPLATE = "## Prerequisites\nChecks:\n{toolkit_checks}9. If the user refuses, stop.\n"
BODY = "\nBody that stays.\n"


def prerequisites_root(tmp_path: Path, toolkit: str, block: str) -> Path:
    write(tmp_path / P.TEMPLATE, TEMPLATE)
    deps = {"dlthub-platform": ["init"], "data-quality": ["dlthub-platform"]}
    entries = {"dlthub-platform": "setup-runtime", "data-quality": "setup-data-quality"}
    for name, needs in deps.items():
        meta = {"dependencies": needs, "workflow_entry_skill": entries[name]}
        write(tmp_path / P.AI_DIR / name / ".claude-plugin" / "toolkit.json", json.dumps(meta))
    skill = tmp_path / P.AI_DIR / toolkit / "skills" / "s" / "SKILL.md"
    write(skill, f"---\nname: s\ndescription: d\n---\n\n# S\n\n{block}{BODY}")
    return tmp_path


def test_a_skill_with_the_rendered_block_passes(tmp_path: Path) -> None:
    block = TEMPLATE.replace("{toolkit_checks}", "")
    assert V.validate_prerequisites(prerequisites_root(tmp_path, "dlthub-platform", block)) == []


def test_a_skill_whose_block_differs_is_an_error(tmp_path: Path) -> None:
    root = prerequisites_root(tmp_path, "dlthub-platform", "## Prerequisites\nOther.\n")

    errors = V.validate_prerequisites(root)

    assert len(errors) == 1
    assert "stale" in errors[0]


def test_dependencies_are_transitive_and_skip_init(tmp_path: Path) -> None:
    root = prerequisites_root(tmp_path, "data-quality", "")

    assert P.dependencies(root, "data-quality") == ["dlthub-platform"]
    assert "`setup-runtime` from the `dlthub-platform` toolkit" in P.render(root, "data-quality")


def test_sync_replaces_only_the_block(tmp_path: Path) -> None:
    old = "## Prerequisites\nOld.\n7. If the user refuses, stop.\n"
    root = prerequisites_root(tmp_path, "data-quality", old)

    P.sync(root)

    assert V.validate_prerequisites(root) == []
    skill = root / P.AI_DIR / "data-quality" / "skills" / "s" / "SKILL.md"
    assert skill.read_text().endswith("9. If the user refuses, stop.\n" + BODY)
