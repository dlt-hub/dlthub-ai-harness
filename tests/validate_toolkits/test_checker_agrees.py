"""The shipped checker and the validator hold agents to the same numbers.

`check_agent.py` travels into a workspace with the skill; `validate_toolkits.py` runs in CI.
Each carries its own copy of the provider limits, so a bump in one has to be a bump in both.
"""

import importlib.util

from tests.utils import REPO_ROOT

from tools import validate_toolkits as V

_PATH = REPO_ROOT / V.AI_DIR / "init" / "skills" / "create-background-agent" / "check_agent.py"
_spec = importlib.util.spec_from_file_location("check_agent", _PATH)
check_agent = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_agent)


def test_the_optional_cap_agrees() -> None:
    assert check_agent.MAX_OPTIONAL_PROPERTIES == V.MAX_OPTIONAL_PROPERTIES


def test_the_output_size_bound_agrees() -> None:
    assert check_agent.MAX_OUTPUT_CHARS == V.MAX_OUTPUT_CHARS


def test_the_rejected_keywords_agree() -> None:
    assert set(check_agent.REJECTED_KEYWORDS) == set(V.REJECTED_KEYWORDS)


def test_the_status_values_agree() -> None:
    assert check_agent.STATUS_VALUES == V._STATUS_VALUES


def test_the_access_axes_agree() -> None:
    assert tuple(check_agent.ACCESS_AXES) == tuple(V.ACCESS_AXES)


def test_the_self_serving_groups_agree() -> None:
    assert check_agent.SELF_SERVING_GROUPS == V.SELF_SERVING_GROUPS


def test_the_group_axes_agree() -> None:
    assert check_agent.GROUP_AXES == V.GROUP_AXES


def test_the_checker_passes_the_shipped_inspector() -> None:
    folder = REPO_ROOT / V.AI_DIR / "dlthub-platform" / V._AGENTS_PATH / "job-inspector"
    frontmatter, body = check_agent.split_frontmatter((folder / "AGENT.md").read_text())
    errors: list[str] = []

    check_agent.check_output_contract(frontmatter["output"], errors)
    check_agent.check_schema("output", frontmatter["output"], errors, [])
    check_agent.check_body(body, frontmatter["inputs"], errors, [])

    assert errors == []


_ADVICE = "every nested property of a field Python fills belongs in one"


def _over_the_cap() -> dict:
    props = {f"f{n}": {"type": "string"} for n in range(V.MAX_OPTIONAL_PROPERTIES + 1)}
    return {"output": {"properties": props}}


def test_the_optional_cap_advice_agrees() -> None:
    """A reader who hits the cap in one tool and then the other is told the same thing."""
    from_validator: list[str] = []
    V._validate_optional_count("tk", "agents/x/AGENT.md", _over_the_cap(), from_validator, [])
    from_checker: list[str] = []
    check_agent.check_schema("output", _over_the_cap()["output"], from_checker, [])

    assert _ADVICE in from_validator[0]
    assert _ADVICE in from_checker[-1]


def test_the_group_axes_check_agrees() -> None:
    """`pipeline` needs `data`, so `context` alone fails in CI as it does in the workspace."""
    frontmatter = {"tools": ["pipeline"], "access": {"context": "read"}}
    from_validator: list[str] = []
    V._validate_tools_access("tk", "agents/x/AGENT.md", frontmatter, from_validator, [])
    from_checker: list[str] = []
    check_agent.check_access(frontmatter, from_checker)

    assert len(from_validator) == 1 and len(from_checker) == 1
    assert "none of its tools are served" in from_validator[0]
    assert "none of its tools are served" in from_checker[0]
