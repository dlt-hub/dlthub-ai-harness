"""The checker sizes the system prompt and the turns it has to fit in.

Two deployed runs died on `max_tokens` because the turn count, not the ceiling, was the budget.
"""

from pathlib import Path

from tests.utils import REPO_ROOT
from tests.validate_toolkits.test_checker_agrees import check_agent

from tools import validate_toolkits as V


def write_agent(root: Path, body: str = "prompt", **frontmatter) -> Path:
    import yaml

    folder = root / "agents" / "a"
    folder.mkdir(parents=True)
    head = yaml.safe_dump({"name": "a", **frontmatter}, sort_keys=False)
    (folder / "AGENT.md").write_text(f"---\n{head}---\n\n{body}\n", encoding="utf-8")
    return folder / "AGENT.md"


def budget(path: Path) -> tuple[list[str], list[str], tuple]:
    frontmatter, body = check_agent.split_frontmatter(path.read_text())
    errors: list[str] = []
    warnings: list[str] = []
    report = check_agent.check_prompt_budget(path, frontmatter, body, errors, warnings)
    return errors, warnings, report


def test_a_prompt_that_fits_passes(tmp_path: Path) -> None:
    path = write_agent(tmp_path, defaults={"limits": {"max_turns": 5, "max_tokens": 1_000_000}})

    errors, warnings, _ = budget(path)

    assert errors == [] and warnings == []


def test_turns_times_the_prompt_over_the_ceiling_fails(tmp_path: Path) -> None:
    path = write_agent(
        tmp_path, body="x" * 40_000, defaults={"limits": {"max_turns": 40, "max_tokens": 50_000}}
    )

    errors, _, _ = budget(path)

    assert len(errors) == 1
    assert "40 turns" in errors[0] and "50,000" in errors[0]


def test_half_the_ceiling_warns(tmp_path: Path) -> None:
    """History is counted on top of the floor, so half the ceiling leaves little room."""
    path = write_agent(
        tmp_path, body="x" * 4_000, defaults={"limits": {"max_turns": 10, "max_tokens": 15_000}}
    )

    errors, warnings, _ = budget(path)

    assert errors == []
    assert len(warnings) == 1 and "over half" in warnings[0]


def test_no_limits_is_neither(tmp_path: Path) -> None:
    path = write_agent(tmp_path)

    errors, warnings, (_, _, _, max_turns, max_tokens) = budget(path)

    assert errors == [] and warnings == []
    assert max_turns is None and max_tokens is None


def test_an_unresolved_reference_warns(tmp_path: Path) -> None:
    path = write_agent(tmp_path, rules=["nowhere:missing"])

    _, warnings, _ = budget(path)

    assert len(warnings) == 1 and "nowhere:missing" in warnings[0]


def inspector() -> Path:
    return REPO_ROOT / V.AI_DIR / "dlthub-platform" / V._AGENTS_PATH / "job-inspector" / "AGENT.md"


def test_the_shipped_inspector_resolves_every_component() -> None:
    path = inspector()
    frontmatter, _ = check_agent.split_frontmatter(path.read_text())

    errors, warnings, (parts, floor, floor_tokens, _, _) = budget(path)

    assert errors == [] and warnings == []
    # the body plus each listed rule and skill, all found in the repo layout
    assert set(parts) == {"body", *frontmatter["skills"], *frontmatter["rules"]}
    assert floor_tokens == floor // check_agent.CHARS_PER_TOKEN


def test_the_inspector_no_longer_inlines_the_interactive_setup_rule() -> None:
    """`init:dlthub-workspace` is 9.5k of setup, toolkit index and user narration per turn."""
    frontmatter, _ = check_agent.split_frontmatter(inspector().read_text())

    assert "init:dlthub-workspace" not in (frontmatter.get("rules") or [])
