"""Every shipped skill and agent definition must be reachable from its toolkit's workflow.md.

The chain is router → toolkit → workflow.md → skill or agent definition. A platform toolkit is
reached from the router's platform row, then the same way.
"""

from pathlib import Path

from tests.utils import REPO_ROOT
from tests.validate_toolkits.utils import fake_root, toolkit

from tools import validate_toolkits as V


def coverage_errors(root: Path) -> list[str]:
    errors: list[str] = []
    V.validate_capability_coverage(root, V.build_component_inventory(root), errors)
    return errors


def test_shipped_toolkits_are_fully_covered() -> None:
    assert coverage_errors(REPO_ROOT) == []


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
    root = fake_root(tmp_path, [])
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
