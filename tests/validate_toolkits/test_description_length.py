"""A skill description over the length limit is a warning.

Codex drops a skill whose description is longer than 1024 chars.
"""

from pathlib import Path

from tests.utils import REPO_ROOT
from tests.validate_toolkits.utils import fake_root, toolkit

from tools import validate_toolkits as V


def length_warnings(root: Path, name: str) -> list[str]:
    errors: list[str] = []
    warnings: list[str] = []
    V.validate_toolkit_content(
        name,
        root / V.AI_DIR / name,
        {name},
        V.build_component_inventory(root),
        errors,
        warnings,
    )
    return [w for w in warnings if "chars" in w]


def test_description_at_the_cap_is_fine(tmp_path: Path) -> None:
    root = fake_root(tmp_path, [])
    toolkit(root, "one-shot", skills=("deploy",), skill_description="x" * V.MAX_DESCRIPTION_CHARS)

    assert length_warnings(root, "one-shot") == []


def test_description_over_the_cap_warns(tmp_path: Path) -> None:
    root = fake_root(tmp_path, [])
    over = V.MAX_DESCRIPTION_CHARS + 1
    toolkit(root, "one-shot", skills=("deploy",), skill_description="x" * over)

    warnings = length_warnings(root, "one-shot")

    assert len(warnings) == 1
    assert "deploy" in warnings[0] and str(over) in warnings[0]


def test_every_shipped_description_is_within_the_cap() -> None:
    """Run against the workbench, so the rule holds for what ships and not only for a fake.

    `dlthub-router` sat 143 chars over, which cut the clause sending a demo request to
    `quick-start`.
    """
    toolkits = sorted(d.name for d in (REPO_ROOT / V.AI_DIR).iterdir() if d.is_dir())

    over = [warning for name in toolkits for warning in length_warnings(REPO_ROOT, name)]

    assert over == []
