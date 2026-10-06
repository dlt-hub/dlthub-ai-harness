"""A property with an enum and no type fails the agent run on its first model call.

Anthropic rejects it with "Schema must have a 'type', 'anyOf', 'oneOf', or 'allOf' field".
"""

from tests.utils import REPO_ROOT

from tools import validate_toolkits as V


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


def test_the_shipped_inspector_carries_its_types() -> None:
    errors: list[str] = []
    path = REPO_ROOT / V.AI_DIR / "dlthub-platform" / V._AGENTS_PATH / "job-inspector" / "AGENT.md"
    frontmatter, _ = V.split_frontmatter(path)
    V._validate_schema_types("dlthub-platform", "job-inspector", frontmatter, errors, [])

    assert errors == []


def optional_errors(fm: dict) -> list[str]:
    errors: list[str] = []
    V._validate_optional_count("tk", "agents/x/AGENT.md", fm, errors, [])
    return errors


def test_a_schema_inside_the_cap_passes() -> None:
    props = {f"f{n}": {"type": "string"} for n in range(V.MAX_OPTIONAL_PROPERTIES)}

    assert optional_errors({"output": {"properties": props}}) == []


def test_a_schema_over_the_cap_fails() -> None:
    """Anthropic answered 400 on a shipped agent that reached 28 optional properties."""
    props = {f"f{n}": {"type": "string"} for n in range(V.MAX_OPTIONAL_PROPERTIES + 1)}

    errors = optional_errors({"output": {"properties": props}})

    assert len(errors) == 1
    assert str(V.MAX_OPTIONAL_PROPERTIES + 1) in errors[0]


def test_a_required_nested_property_does_not_count() -> None:
    """A nested `required` binds only when the model writes that object."""
    nested = {f"n{n}": {"type": "string"} for n in range(30)}
    fm = {
        "output": {
            "properties": {
                "window": {"type": "object", "properties": nested, "required": list(nested)}
            }
        }
    }

    assert optional_errors(fm) == []


def test_the_shipped_inspector_is_inside_the_cap() -> None:
    errors: list[str] = []
    path = REPO_ROOT / V.AI_DIR / "dlthub-platform" / V._AGENTS_PATH / "job-inspector" / "AGENT.md"
    frontmatter, _ = V.split_frontmatter(path)
    V._validate_optional_count("dlthub-platform", "job-inspector", frontmatter, errors, [])

    assert errors == []
