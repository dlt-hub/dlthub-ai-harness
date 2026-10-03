"""A property carrying an enum and no type fails the agent on its first model call.

Anthropic's schema transformer refuses it with "Schema must have a 'type', 'anyOf', 'oneOf',
or 'allOf' field", which a platform run of a shipped agent hit, so the validator holds the
line here rather than in a job log.
"""

from pathlib import Path

from fakes import REPO_ROOT

import validate_toolkits as V


def type_errors(fm: dict) -> list[str]:
    errors: list[str] = []
    V._validate_schema_types("tk", "agents/x/AGENT.md", fm, errors, [])
    return errors


def test_an_enum_with_a_type_passes() -> None:
    assert type_errors({"output": {"properties": {"v": {"type": "string", "enum": ["a"]}}}}) == []


def test_an_enum_without_a_type_fails() -> None:
    errors = type_errors({"output": {"properties": {"verdict": {"enum": ["a", "b"]}}}})

    assert len(errors) == 1
    assert "output.verdict" in errors[0]


def test_a_property_inside_an_array_item_is_reached() -> None:
    fm = {
        "output": {
            "properties": {
                "rows": {
                    "type": "array",
                    "items": {"type": "object", "properties": {"kind": {"enum": ["p"]}}},
                }
            }
        }
    }

    assert "output.rows[].kind" in type_errors(fm)[0]


def test_an_input_is_checked_too() -> None:
    assert "inputs.mode" in type_errors({"inputs": {"properties": {"mode": {"enum": ["a"]}}}})[0]


def test_anyof_stands_in_for_a_type() -> None:
    fm = {"output": {"properties": {"v": {"anyOf": [{"type": "string"}, {"type": "null"}]}}}}

    assert type_errors(fm) == []


def optional_errors(fm: dict) -> list[str]:
    errors: list[str] = []
    V._validate_optional_count("tk", "agents/x/AGENT.md", fm, errors, [])
    return errors


def test_a_schema_inside_the_cap_passes() -> None:
    props = {f"f{n}": {"type": "string"} for n in range(V.MAX_OPTIONAL_PROPERTIES)}

    assert optional_errors({"output": {"properties": props}}) == []


def test_a_schema_over_the_cap_fails() -> None:
    props = {f"f{n}": {"type": "string"} for n in range(V.MAX_OPTIONAL_PROPERTIES + 1)}

    errors = optional_errors({"output": {"properties": props}})

    assert len(errors) == 1
    assert str(V.MAX_OPTIONAL_PROPERTIES + 1) in errors[0]


def test_a_required_nested_property_does_not_count() -> None:
    """`required` inside an object binds only when the model writes that object, so the nested
    properties of a Python-filled field cost nothing."""
    nested = {f"n{n}": {"type": "string"} for n in range(30)}
    fm = {
        "output": {
            "properties": {
                "window": {"type": "object", "properties": nested, "required": list(nested)}
            }
        }
    }

    assert optional_errors(fm) == []


def test_the_shipped_evaluator_is_inside_the_cap() -> None:
    path = (
        Path(REPO_ROOT) / V.AI_DIR / "dlthub-platform" / "agents" / "job-inspector-eval"
        / "AGENT.md"
    )
    frontmatter, _ = V.split_frontmatter(path)

    assert optional_errors(frontmatter) == []


def test_the_shipped_agents_carry_their_types() -> None:
    errors: list[str] = []
    for agent in ("job-inspector", "job-inspector-eval"):
        path = Path(REPO_ROOT) / V.AI_DIR / "dlthub-platform" / "agents" / agent / "AGENT.md"
        frontmatter, _ = V.split_frontmatter(path)
        V._validate_schema_types("dlthub-platform", agent, frontmatter, errors, [])

    assert errors == []


def size_warnings(fm: dict) -> list[str]:
    warnings: list[str] = []
    V._validate_schema_size("tk", "agents/x/AGENT.md", fm, [], warnings)
    return warnings


def test_a_schema_inside_the_budget_is_quiet() -> None:
    props = {f"f{n}": {"type": "string"} for n in range(V.SCHEMA_PROPERTY_BUDGET)}

    assert size_warnings({"output": {"properties": props}}) == []


def test_a_schema_over_the_property_budget_is_reported() -> None:
    props = {f"f{n}": {"type": "string"} for n in range(V.SCHEMA_PROPERTY_BUDGET + 1)}

    warnings = size_warnings({"output": {"properties": props}})

    assert len(warnings) == 1
    assert str(V.SCHEMA_PROPERTY_BUDGET + 1) in warnings[0]


def test_a_nested_property_counts_toward_the_budget() -> None:
    """The model reads the whole schema, so a required nested field costs what an optional one
    does. This is where the budget differs from the optional-parameter cap."""
    nested = {f"n{n}": {"type": "string"} for n in range(V.SCHEMA_PROPERTY_BUDGET)}
    fm = {
        "output": {
            "properties": {
                "window": {"type": "object", "properties": nested, "required": list(nested)}
            }
        }
    }

    assert len(size_warnings(fm)) == 1


def test_a_long_schema_is_reported_on_its_length() -> None:
    fm = {"output": {"properties": {"f": {"type": "string", "description": "x" * 5_000}}}}

    assert len(size_warnings(fm)) == 1


def test_the_shipped_agents_are_inside_the_budget() -> None:
    for agent in ("job-inspector", "job-inspector-eval"):
        path = Path(REPO_ROOT) / V.AI_DIR / "dlthub-platform" / "agents" / agent / "AGENT.md"
        frontmatter, _ = V.split_frontmatter(path)

        assert size_warnings(frontmatter) == []
