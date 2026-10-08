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
        return 0
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
            f" {MAX_OPTIONAL_PROPERTIES}. A property listed in its object's `required` does not"
            " count, and a nested `required` binds only when the model writes that object, so"
            " every nested property of a field Python fills belongs in one"
            f" ({', '.join(optional[:6])}, ...)"
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


ACCESS_AXES = ("local", "data", "context")

GROUP_AXES = {
    "jobs": ("context",),
    "logs": ("context",),
    "telemetry": ("context",),
    "config": ("context",),
    "context": ("context",),
    "pipeline": ("data",),
    "workspace": ("local",),
    "secrets": ("local",),
    "restore_pipeline": ("context", "data"),
    "toolkit": (),
}
"""Axes each feature group needs before the server offers any of its tools. See the catalogue in
agent-md-reference.md. A group not listed here is checked against the axes as a whole."""

SELF_SERVING_GROUPS = frozenset(group for group, axes in GROUP_AXES.items() if not axes)
"""Groups whose tools ask for no access. Every other group serves nothing without an axis."""


def check_access(frontmatter, errors):
    """A feature group serves only the tools an `access` axis covers, `toolkit` aside."""
    groups = [g for g in (frontmatter.get("tools") or []) if g not in SELF_SERVING_GROUPS]
    access = frontmatter.get("access") or {}
    known = [g for g in groups if g in GROUP_AXES]
    for group in known:
        missing = [axis for axis in GROUP_AXES[group] if not access.get(axis)]
        if missing:
            errors.append(
                f"tools lists {group} but access grants no"
                f" {' and no '.join(missing)}; none of its tools are served"
            )
    rest = [g for g in groups if g not in GROUP_AXES]
    if rest and not any(access.get(axis) for axis in ACCESS_AXES):
        errors.append(
            f"tools lists {', '.join(rest)} but access grants no"
            f" {', '.join(ACCESS_AXES)} axis; the server then serves the toolkit catalogue"
            " alone and the agent is offered none of those tools"
        )


def check_body(body, inputs, errors, warnings):
    declared = set((inputs.get("properties") or {}) if isinstance(inputs, dict) else {})
    used = {name.partition(".")[0] for name in PLACEHOLDER.findall(body)}
    # `run_context` is implicit and never declared
    for name in sorted(used - declared - {"run_context"}):
        errors.append(f"body renders {{{{ {name} }}}} but no input declares it")
    for name in sorted(declared - used):
        warnings.append(f"input {name!r} is declared but the body never names it")


CHARS_PER_TOKEN = 4
"""Rough across English prose and the markdown an agent is given. Close enough to size turns."""

HOST_DIRS = (".claude", ".cursor", ".agents")
"""Where each host installs the components a definition references."""


def project_root(start):
    """The workspace or repo the agent folder sits in, found by the host folder it holds."""
    for folder in [start, *start.parents]:
        if (folder / ".dlt").is_dir() or any((folder / host).is_dir() for host in HOST_DIRS):
            return folder
    return start


def component_path(root, kind, toolkit, name):
    """An installed component, or the same component in an AI harness checkout."""
    candidates = []
    for host in HOST_DIRS:
        if kind == "rules":
            candidates += [
                root / host / "rules" / f"{toolkit}-{name}.md",
                root / host / "rules" / f"{toolkit}-{name}.mdc",
                # Codex has no rules of its own, so an install writes them as skills
                root / host / "skills" / f"{toolkit}-{name}" / "SKILL.md",
            ]
        else:
            candidates.append(root / host / "skills" / name / "SKILL.md")
    source = "rules" if kind == "rules" else "skills"
    leaf = f"{name}.md" if kind == "rules" else Path(name) / "SKILL.md"
    candidates.append(root / "workbench" / toolkit / source / leaf)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def check_prompt_budget(path, frontmatter, body, errors, warnings):
    """Size the system prompt and the turn budget it has to fit in. Returns a report."""
    root = project_root(path.parent.resolve())
    parts = {"body": len(body)}
    for kind in ("skills", "rules"):
        for ref in frontmatter.get(kind) or []:
            toolkit, _, name = ref.rpartition(":")
            found = component_path(root, kind, toolkit, name)
            if found is None:
                warnings.append(
                    f"{kind[:-1]} {ref!r} does not resolve under {root}; a run skips it with a"
                    " warning and the agent gets less than the file says"
                )
                continue
            parts[ref] = len(found.read_text(encoding="utf-8"))

    floor = sum(parts.values())
    floor_tokens = floor // CHARS_PER_TOKEN
    limits = (frontmatter.get("defaults") or {}).get("limits") or {}
    max_turns, max_tokens = limits.get("max_turns"), limits.get("max_tokens")

    # the floor is the system prompt alone; a turn also resends the whole history
    if max_turns and max_tokens and max_turns * floor_tokens > max_tokens:
        errors.append(
            f"{max_turns} turns of a ~{floor_tokens:,}-token system prompt is"
            f" ~{max_turns * floor_tokens:,} tokens, over the max_tokens of {max_tokens:,},"
            " before a single turn of history. Cut the prompt or cut max_turns"
        )
    elif max_turns and max_tokens and max_turns * floor_tokens > max_tokens // 2:
        warnings.append(
            f"{max_turns} turns of system prompt alone is ~{max_turns * floor_tokens:,} tokens,"
            f" over half the max_tokens of {max_tokens:,}. History is counted on top, so the"
            " run has little room"
        )
    return parts, floor, floor_tokens, max_turns, max_tokens


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
    check_access(frontmatter, errors)

    output_chars = len(json.dumps(output))
    if output_chars > MAX_OUTPUT_CHARS:
        errors.append(
            f"output is {output_chars} characters, over the {MAX_OUTPUT_CHARS} a job has"
            " launched with. Keep each item's schema to the fields a reader acts on"
        )

    parts, floor, floor_tokens, max_turns, max_tokens = check_prompt_budget(
        path, frontmatter, body, errors, warnings
    )

    print(f"{path}")
    print(f"  body: {len(body.splitlines())} lines, {len(PLACEHOLDER.findall(body))} placeholders")
    inlined = ", ".join(f"{ref} {size:,}" for ref, size in parts.items() if ref != "body")
    print(
        f"  prompt floor: {floor:,} characters, ~{floor_tokens:,} tokens"
        f" (body {parts['body']:,}{'; ' + inlined if inlined else ''})"
    )
    if max_turns and max_tokens:
        print(
            f"  turn budget: {max_turns} turns x floor = ~{max_turns * floor_tokens:,} tokens"
            f" of {max_tokens:,}; history is counted on top of this"
        )
    else:
        print("  turn budget: defaults.limits sets no max_turns and max_tokens pair to size")
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
