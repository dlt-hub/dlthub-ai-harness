"""Check one `AGENT.md` against the rules a provider and dltHub impose on it.

Reports schema size, optional-property count, untyped properties, the `status` and `summary`
contract, and the body placeholders. Exits 1 when something would fail at run time.

Usage: python check_agent.py agents/<name>
"""

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

MAX_OPTIONAL_PROPERTIES = 24
"""Anthropic refuses more optional properties than this, nested ones counted."""

MAX_OUTPUT_CHARS = 8000
"""The model reads the whole output schema on every run, and a large one has stopped a job."""

STATUS_VALUES = ["succeeded", "failed", "aborted"]

REJECTED_KEYWORDS = ("minimum", "maximum", "minLength", "maxLength")
"""Anthropic's structured output rejects these; numeric bounds go in the description."""

PLACEHOLDER = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n?(.*)\Z", re.DOTALL)


def split_frontmatter(text):
    match = FRONTMATTER.match(text)
    if not match:
        return {}, text
    return yaml.safe_load(match.group(1)) or {}, match.group(2)


def walk_properties(schema, path=""):
    """Every property of a schema and its nested objects, as (path, name, definition, required)."""
    props = schema.get("properties")
    if not isinstance(props, dict):
        return
    required = schema.get("required")
    required = set(required) if isinstance(required, (list, tuple)) else set()
    for name, definition in props.items():
        if not isinstance(definition, dict):
            continue
        yield path, name, definition, name in required
        yield from walk_properties(definition, f"{path}{name}.")
        items = definition.get("items")
        if isinstance(items, dict):
            yield from walk_properties(items, f"{path}{name}[].")


def check_schema(label, schema, errors, warnings):
    if not isinstance(schema, dict):
        errors.append(f"{label} is not a JSON Schema mapping")
        return
    optional = []
    for path, name, definition, is_required in walk_properties(schema):
        full = f"{label}.{path}{name}"
        if not is_required:
            optional.append(f"{path}{name}")
        if "type" not in definition and not any(
            key in definition for key in ("anyOf", "oneOf", "allOf")
        ):
            errors.append(f"{full} names no type; the provider rejects the schema")
        if definition.get("type") == "object" and "properties" not in definition:
            errors.append(f"{full} is a bare object; a strict validator refuses it")
        for keyword in REJECTED_KEYWORDS:
            if keyword in definition:
                errors.append(f"{full} carries {keyword!r}; put the bound in the description")
        if not definition.get("description"):
            warnings.append(f"{full} has no description")
    if len(optional) > MAX_OPTIONAL_PROPERTIES:
        errors.append(
            f"{label} declares {len(optional)} optional properties, over the cap of"
            f" {MAX_OPTIONAL_PROPERTIES}. List the ones the model always writes in their"
            f" object's `required` ({', '.join(optional[:6])}, ...)"
        )
    return len(optional)


def check_output_contract(output, errors):
    props = output.get("properties")
    props = props if isinstance(props, dict) else {}
    required = output.get("required")
    required = set(required) if isinstance(required, (list, tuple)) else set()
    for field in ("status", "summary"):
        if field not in props:
            errors.append(f"output does not declare {field!r}")
        elif field not in required:
            errors.append(f"output.required omits {field!r}")
    status = props.get("status")
    if isinstance(status, dict):
        values = list(status.get("enum") or [])
        if values and values != STATUS_VALUES:
            errors.append(f"output.status declares {values} but the contract is {STATUS_VALUES}")
    summary = props.get("summary")
    if isinstance(summary, dict) and summary.get("type") != "string":
        errors.append(f"output.summary declares type {summary.get('type')!r}, not 'string'")


def check_body(body, inputs, errors, warnings):
    declared = set((inputs.get("properties") or {}) if isinstance(inputs, dict) else {})
    used = {name.partition(".")[0] for name in PLACEHOLDER.findall(body)}
    # `run_context` is implicit and never declared
    for name in sorted(used - declared - {"run_context"}):
        errors.append(f"body renders {{{{ {name} }}}} but no input declares it")
    for name in sorted(declared - used):
        warnings.append(f"input {name!r} is declared but the body never names it")


def main():
    parser = argparse.ArgumentParser(description="Check an AGENT.md against the run-time rules.")
    parser.add_argument("target", help="Agent folder, or the AGENT.md inside it")
    args = parser.parse_args()

    path = Path(args.target)
    if path.is_dir():
        path = path / "AGENT.md"
    if not path.is_file():
        print(f"{path} not found", file=sys.stderr)
        return 2

    frontmatter, body = split_frontmatter(path.read_text(encoding="utf-8"))
    errors, warnings = [], []

    if not body.strip():
        errors.append("the body is empty; the body is the system prompt")

    inputs = frontmatter.get("inputs") or {}
    output = frontmatter.get("output")
    if output is None:
        warnings.append("no output declared; dltHub adds `status` and `summary` alone")
        output = {}
    else:
        check_output_contract(output, errors)

    input_optional = check_schema("inputs", inputs, errors, warnings) if inputs else 0
    output_optional = check_schema("output", output, errors, warnings) if output else 0
    check_body(body, inputs, errors, warnings)

    output_chars = len(json.dumps(output))
    if output_chars > MAX_OUTPUT_CHARS:
        errors.append(
            f"output is {output_chars} characters, over the {MAX_OUTPUT_CHARS} a job has"
            " launched with. Keep each item's schema to the fields a reader acts on"
        )

    print(f"{path}")
    print(f"  body: {len(body.splitlines())} lines, {len(PLACEHOLDER.findall(body))} placeholders")
    print(f"  inputs: {len((inputs.get('properties') or {}))} properties, {input_optional} optional")
    print(
        f"  output: {len((output.get('properties') or {}))} properties,"
        f" {output_optional} optional of {MAX_OPTIONAL_PROPERTIES}, {output_chars} characters"
    )
    for warning in warnings:
        print(f"  warning: {warning}")
    for error in errors:
        print(f"  error: {error}")
    print(f"{len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
