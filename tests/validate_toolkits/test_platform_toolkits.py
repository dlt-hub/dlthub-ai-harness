"""Platform toolkits are pluggable: the router names none, and no other toolkit names one.

A platform toolkit starts its description with `Platform toolkit`. A toolkit that works only with
one platform says `Requires <platform> Platform` instead. The router reaches both through the
platform toolkit row, and every other toolkit hands over to "the installed platform toolkit".
"""

from pathlib import Path

import pytest

from tests.utils import REPO_ROOT
from tests.validate_toolkits.utils import fake_root, toolkit

from tools import validate_toolkits as V

PLATFORM = f"{V.PLATFORM_LABEL} (dltHub): deploy to the dltHub platform."
REQUIRES = "Deploy a sample pipeline to the dltHub platform. Requires dltHub Platform."


def index_errors(root: Path, names: set[str]) -> list[str]:
    errors: list[str] = []
    V.validate_index_drift(root, names, V.build_component_inventory(root), errors)
    return errors


def agnostic_errors(root: Path) -> list[str]:
    errors: list[str] = []
    V.validate_platform_agnostic(root, V.build_component_inventory(root), errors)
    return errors


def test_shipped_index_and_toolkits_are_agnostic() -> None:
    names = set(V.build_component_inventory(REPO_ROOT))

    assert index_errors(REPO_ROOT, names) == []
    assert agnostic_errors(REPO_ROOT) == []


def test_index_skips_platform_unlisted_and_base_toolkits(tmp_path: Path) -> None:
    root = fake_root(tmp_path, ["rest-api-pipeline"])
    toolkit(root, "init", workflow=False)
    toolkit(root, "rest-api-pipeline")
    toolkit(root, "local-workspace", listed=False)
    toolkit(root, "dlthub-platform", description=PLATFORM)
    toolkit(root, "one-shot", description=REQUIRES)

    names = {"init", "rest-api-pipeline", "local-workspace", "dlthub-platform", "one-shot"}
    assert index_errors(root, names) == []


def test_index_missing_a_workflow_toolkit(tmp_path: Path) -> None:
    root = fake_root(tmp_path, [])
    toolkit(root, "rest-api-pipeline")

    errors = index_errors(root, {"rest-api-pipeline"})

    assert len(errors) == 1 and "missing workflow toolkit 'rest-api-pipeline'" in errors[0]


@pytest.mark.parametrize(
    "name,description", [("dlthub-platform", PLATFORM), ("one-shot", REQUIRES)]
)
def test_index_names_a_toolkit_of_a_platform(tmp_path: Path, name: str, description: str) -> None:
    root = fake_root(tmp_path, [name])
    toolkit(root, name, description=description)

    errors = index_errors(root, {name})

    assert len(errors) == 1 and f"'{name}', which belongs to a platform" in errors[0]


def test_index_without_the_platform_row(tmp_path: Path) -> None:
    root = fake_root(tmp_path, [], platform_row=False)
    toolkit(root, "dlthub-platform", description=PLATFORM)

    errors = index_errors(root, {"dlthub-platform"})

    assert len(errors) == 1 and "a platform toolkit" in errors[0]


def test_generic_toolkit_depends_on_a_platform_toolkit(tmp_path: Path) -> None:
    toolkit(tmp_path, "transformations", dependencies=("dlthub-platform",))
    toolkit(tmp_path, "dlthub-platform", description=PLATFORM)

    errors = agnostic_errors(tmp_path)

    assert len(errors) == 1 and "depends on 'dlthub-platform'" in errors[0]


@pytest.mark.parametrize(
    "body,reason",
    [
        ("hand over to **dlthub-platform**", "names 'dlthub-platform'"),
        ("then run (`setup-runtime`)", "names 'setup-runtime'"),
        ("try it with **one-shot**", "names 'one-shot'"),
        ("schedule it on the dltHub platform", "names the dltHub platform"),
        ("run `uv run dlthub deploy`", "runs a platform command"),
        ("run `dlthub --non-interactive job logs x`", "runs a platform command"),
        ('`uv add "dlt[hub,s3]"`', "installs `dlt[hub]`"),
    ],
)
def test_generic_toolkit_names_the_platform(tmp_path: Path, body: str, reason: str) -> None:
    toolkit(tmp_path, "rest-api-pipeline", skills=("find-source",), skill_body=body + "\n")
    toolkit(tmp_path, "dlthub-platform", skills=("setup-runtime",), description=PLATFORM)
    toolkit(tmp_path, "one-shot", description=REQUIRES)

    errors = agnostic_errors(tmp_path)

    assert len(errors) == 1 and reason in errors[0] and "SKILL.md:5" in errors[0]


@pytest.mark.parametrize(
    "body",
    [
        "follow the workflow entry of the installed platform toolkit, then `deploy`",
        "run the job with `dlthub local run my_job`",
        "**NEVER** add `dlt[hub]` or `dlthub-client` yourself",
        "the dlthub workspace is not initialized",
        "uv add dlthub",
    ],
)
def test_generic_toolkit_may_say(tmp_path: Path, body: str) -> None:
    toolkit(tmp_path, "rest-api-pipeline", skills=("find-source",), skill_body=body + "\n")
    toolkit(tmp_path, "dlthub-platform", skills=("setup-runtime",), description=PLATFORM)

    assert agnostic_errors(tmp_path) == []


def test_toolkit_that_requires_a_platform_names_it(tmp_path: Path) -> None:
    """A toolkit that requires the dltHub Platform may name it and its platform toolkit."""
    toolkit(
        tmp_path,
        "one-shot",
        skills=("deploy-run-sample-pipeline",),
        description=REQUIRES,
        skill_body="`dlthub deploy`, then hand over to **dlthub-platform**\n",
    )
    toolkit(tmp_path, "dlthub-platform", description=PLATFORM)

    assert agnostic_errors(tmp_path) == []
