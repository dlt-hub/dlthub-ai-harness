"""Every shipped capability must be reachable from the router skill.

The chain is router → toolkit → workflow.md → skill or agent. A break anywhere in it leaves
a capability the agent never finds.
"""

from pathlib import Path

from fakes import REPO_ROOT, fake_root, toolkit, write

import validate_toolkits as V


def coverage_errors(root: Path) -> list[str]:
    errors: list[str] = []
    V.validate_capability_coverage(root, V.build_component_inventory(root), errors)
    return errors


def test_shipped_toolkits_are_fully_covered() -> None:
    assert coverage_errors(REPO_ROOT) == []


def test_agent_missing_from_router(tmp_path: Path) -> None:
    root = fake_root(tmp_path, [])
    toolkit(root, "dlthub-platform", skills=("setup-runtime",), agents=("job-inspector",))

    errors = coverage_errors(root)

    assert len(errors) == 1
    assert "router" in errors[0] and "dlthub-platform:job-inspector" in errors[0]


def test_router_lists_an_agent_that_no_toolkit_ships(tmp_path: Path) -> None:
    root = fake_root(tmp_path, ["dlthub-platform:job-inspector", "dlthub-platform:gone"])
    toolkit(root, "dlthub-platform", agents=("job-inspector",))

    errors = coverage_errors(root)

    assert len(errors) == 1
    assert "dlthub-platform:gone" in errors[0]


def test_skill_not_referenced_in_workflow(tmp_path: Path) -> None:
    root = fake_root(tmp_path, [])
    toolkit(
        root,
        "rest-api-pipeline",
        skills=("find-source", "debug-pipeline"),
        workflow_refs=("find-source",),
    )

    errors = coverage_errors(root)

    assert len(errors) == 1
    assert "workflow.md" in errors[0] and "debug-pipeline" in errors[0]


def test_agent_not_referenced_in_workflow(tmp_path: Path) -> None:
    root = fake_root(tmp_path, ["dlthub-platform:job-inspector"])
    toolkit(
        root,
        "dlthub-platform",
        skills=("setup-runtime",),
        agents=("job-inspector",),
        workflow_refs=("setup-runtime",),
    )

    errors = coverage_errors(root)

    assert len(errors) == 1
    assert "workflow.md" in errors[0] and "job-inspector" in errors[0]


def test_workflow_toolkit_without_workflow_rule(tmp_path: Path) -> None:
    root = fake_root(tmp_path, [])
    toolkit(root, "rest-api-pipeline", skills=("find-source",), workflow=False)

    errors = coverage_errors(root)

    assert len(errors) == 1
    assert "rules/workflow.md" in errors[0]


def test_non_workflow_toolkits_are_exempt(tmp_path: Path) -> None:
    """`init` and `bootstrap` carry no workflow; their skills are reached another way."""
    root = fake_root(tmp_path, [])
    toolkit(root, "init", skills=("dlthub-router", "setup-secrets"), workflow=False)
    toolkit(root, "bootstrap", workflow=False)

    assert coverage_errors(root) == []


def test_missing_router_skill(tmp_path: Path) -> None:
    toolkit(tmp_path, "dlthub-platform", agents=("job-inspector",))

    assert any(V._ROUTER_SKILL in e for e in coverage_errors(tmp_path))


def test_router_prose_mention_is_not_an_index_row(tmp_path: Path) -> None:
    """Only index rows count; a name dropped in prose leaves the agent unroutable."""
    root = fake_root(tmp_path, [])
    write(root / V._ROUTER_SKILL, "---\nname: dlthub-router\n---\n\ndlthub-platform:job-inspector\n")
    toolkit(root, "dlthub-platform", agents=("job-inspector",))

    errors = coverage_errors(root)

    assert len(errors) == 1
    assert "dlthub-platform:job-inspector" in errors[0]
