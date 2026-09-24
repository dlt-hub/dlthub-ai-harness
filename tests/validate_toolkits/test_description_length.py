"""A skill description over the cap is a warning.

A description is the whole trigger surface, and Codex drops a skill whose description
passes 1024 chars (dlt-hub/dlthub-ai-workbench-internal#75). Growing one past that point
also cost `dlthub-router` its cold-start recall once, so the length is worth reporting.
"""

from pathlib import Path

from fakes import REPO_ROOT, fake_root, toolkit

import validate_toolkits as V


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


def test_router_is_over_the_cap_today() -> None:
    """The shipped router trips it, so the check is live rather than theoretical."""
    assert len(length_warnings(REPO_ROOT, "init")) == 1
