#!/usr/bin/env python3
"""Validate the plugin marketplace and the skills, commands, rules and agents of each toolkit.

Usage: python tools/validate_toolkits.py [toolkit-name]
"""

import ast
import json
import re
import sys
import typing
from pathlib import Path

import yaml
from dlt._workspace.access import ACCESS_AXES
from dlt._workspace.deployment.agent.exceptions import InvalidAgentSpec
from dlt._workspace.deployment.agent.manifest import (
    VALIDATE_INPUT,
    VALIDATE_OUTPUT,
    load_agent_spec,
)
from dlt._workspace.deployment.agent.typing import (
    TAgentDefaults,
    TAgentJobStatus,
    TAgentLimits,
    TAgentOutput,
)
from dlt._workspace.deployment.exceptions import InvalidJobSchema
from dlt._workspace.deployment.reflection import ENTITY_TYPE_KEY, entity_properties
from dlt._workspace.deployment.typing import THubEntityType
from dlt._workspace.cli.dlthub.ai.agents import COMPONENT_MARKERS, DLTHUB_AGENTS_DIR
from dlt._workspace.cli.formatters import parse_frontmatter
from dlt.common.typing import get_args

AI_DIR = "workbench"

# the intent index lives in the rule (Claude, Cursor) and in AGENTS.md (Codex, where rules
# are opt-in)
_INDEX_FILES = (
    "workbench/init/rules/dlthub-workspace.md",
    "workbench/init/AGENTS.md",
)
# `init` is the base itself and `bootstrap` only scaffolds the environment, so neither is indexed
_NON_WORKFLOW_TOOLKITS = {"init", "bootstrap"}
# an index row: "<intent text> → <toolkit> | <install> | <entry skill>", captures the toolkit
_INDEX_ENTRY = re.compile(r"→\s*([a-z][\w-]*)\s*\|")

# the router indexes the background agents, which the intent index omits
_ROUTER_SKILL = "workbench/init/skills/dlthub-router/SKILL.md"
# a router agent row: "<capability> → <toolkit>:<agent> | <install> | <declare>".
_ROUTER_AGENT_ENTRY = re.compile(r"→\s*([a-z][\w-]*:[a-z][\w-]*)\s*\|")

# Codex drops a skill with a longer description
MAX_DESCRIPTION_CHARS = 1024

_EXPECTED_AUTHOR = "ScaleVector GmbH"
_EXPECTED_LICENSE = "https://github.com/dlt-hub/dlthub-ai-workbench/blob/master/LICENSE"

# argument-hint tokens use the [bracket] convention: "[pipeline-name] [query]"
_ARGUMENT_HINT_TOKEN = re.compile(r"^\[[\w-]+\]$")

# matched case-insensitive
_WORKFLOW_REQUIRED_SECTIONS = ["core workflow"]
_WORKFLOW_OPTIONAL_SECTIONS = ["extend and harden"]
_WORKFLOW_HANDOVER_SECTION = "handover to other toolkits"

# (`skill-name`) or (`agent-name`) references in workflow
_WORKFLOW_SKILL_REF = re.compile(r"\(`([a-z][\w-]*)`\)")

# **toolkit-name** references in handover section
_WORKFLOW_HANDOVER_REF = re.compile(r"\*\*([a-z][\w-]*)\*\*")

# the agent file schema and its vocabularies come from dlt; this file checks only what a
# source toolkit adds
_AGENT_FILE = COMPONENT_MARKERS["agent"]
_AGENTS_PATH = DLTHUB_AGENTS_DIR
# `<toolkit>/agents` holds a host's own subagents, which dlt does not install as agents
_HOST_AGENTS_PATH = "agents"
_AGENT_HOOKS = (VALIDATE_INPUT, VALIDATE_OUTPUT)
_ENTITY_TYPES = get_args(THubEntityType)
_STATUS_VALUES = list(get_args(TAgentJobStatus))
_DEFAULTS_KEYS = set(typing.get_type_hints(TAgentDefaults))
_LIMITS_KEYS = set(typing.get_type_hints(TAgentLimits))
# the standard output props, named by the TypedDict that defines them
_OUTPUT_CONTRACT = tuple(typing.get_type_hints(TAgentOutput))
_SUMMARY_TYPE = "string"
# a component ref: "<toolkit>:<name>" or a bare "<name>" meaning the own toolkit
_AGENT_REF = re.compile(r"^(?:([a-z][\w-]*):)?([a-z][\w-]*)$")
_PLACEHOLDER = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")


def frontmatter_of(path: Path, label: str, pname: str, errors: list[str]) -> dict:
    """Frontmatter of a component file, or `{}` with the YAML error added to `errors`."""
    try:
        fm, _ = split_frontmatter(path)
    except yaml.YAMLError as ex:
        errors.append(f"[{pname}] {label} invalid YAML frontmatter: {ex}")
        return {}
    return fm


def split_frontmatter(path: Path) -> tuple[dict, str]:
    """Split a markdown file into (frontmatter, body), `({}, text)` when it has no frontmatter."""
    # the same parser `load_agent_spec` uses; raises yaml.YAMLError on invalid frontmatter
    return parse_frontmatter(path.read_text(encoding="utf-8"))


def build_component_inventory(root: Path) -> dict[str, dict]:
    """Map each toolkit to its skills, rules, agents, commands and dependencies."""
    inventory: dict[str, dict] = {}
    ai_dir = root / AI_DIR
    if not ai_dir.is_dir():
        return inventory

    for tk_dir in sorted(ai_dir.iterdir()):
        if not tk_dir.is_dir() or tk_dir.name.startswith("."):
            continue

        skills: set[str] = set()
        skills_dir = tk_dir / "skills"
        if skills_dir.is_dir():
            skills = {
                p.name for p in skills_dir.iterdir() if p.is_dir() and (p / "SKILL.md").is_file()
            }

        dependencies: list[str] = []
        tkjson = tk_dir / ".claude-plugin" / "toolkit.json"
        if tkjson.is_file():
            dependencies = list(json.loads(tkjson.read_text()).get("dependencies", []))

        inventory[tk_dir.name] = {
            "skills": skills,
            "rules": _stems(tk_dir / "rules"),
            "agents": _agent_names(tk_dir / _AGENTS_PATH),
            "commands": _stems(tk_dir / "commands"),
            "dependencies": dependencies,
        }
    return inventory


def _agent_names(directory: Path) -> set[str]:
    """Names of the agent folders, those containing an AGENT.md."""
    if not directory.is_dir():
        return set()
    return {p.name for p in directory.iterdir() if (p / _AGENT_FILE).is_file()}


def _stems(directory: Path) -> set[str]:
    """Markdown file stems in a directory, or an empty set when it is absent."""
    if not directory.is_dir():
        return set()
    return {p.stem for p in directory.glob("*.md")}


def _check_ref(ref: object, kind: str, pname: str, inventory: dict[str, dict]) -> str | None:
    """Resolve a `<toolkit>:<name>` component ref. Returns an error message or None."""
    if not isinstance(ref, str):
        return f"{kind} ref must be a string, got {type(ref).__name__}"
    match = _AGENT_REF.match(ref.strip())
    if not match:
        return f"malformed {kind} ref '{ref}' (expected 'name' or 'toolkit:name')"

    toolkit = match.group(1) or pname
    name = match.group(2)
    if toolkit not in inventory:
        return f"{kind} ref '{ref}' points to unknown toolkit '{toolkit}'"
    # a toolkit that is not a declared dependency may not be installed
    if toolkit != pname and toolkit not in inventory[pname]["dependencies"]:
        return (
            f"{kind} ref '{ref}' points to '{toolkit}' "
            f"which is not a declared dependency of '{pname}'"
        )
    if name not in inventory[toolkit][kind]:
        return f"{kind} ref '{ref}' does not resolve to a {kind[:-1]} in toolkit '{toolkit}'"
    return None


def _dlt_reason(ex: Exception) -> str:
    """The reason of a dlt validation error, without the file path."""
    reasons = getattr(ex, "errors", None)
    if isinstance(reasons, list) and reasons:
        return str(reasons[0]).strip()
    return str(ex).strip()


def validate_agents(
    pname: str,
    plugin_dir: Path,
    inventory: dict[str, dict],
    errors: list[str],
    warnings: list[str],
) -> set[str]:
    """Validate the agent files under `dlthub/agents/<name>/AGENT.md`."""
    agent_names: set[str] = set()
    for misplaced in sorted((plugin_dir / _HOST_AGENTS_PATH).glob(f"*/{_AGENT_FILE}")):
        errors.append(
            f"[{pname}] {_HOST_AGENTS_PATH}/{misplaced.parent.name}/{_AGENT_FILE} is not"
            f" installed. dlt installs agents from {_AGENTS_PATH}/. Move the folder there"
        )
    agents_dir = plugin_dir / _AGENTS_PATH
    if not agents_dir.is_dir():
        return agent_names

    for entry in sorted(agents_dir.iterdir()):
        if not entry.is_dir():
            errors.append(
                f"[{pname}] {_AGENTS_PATH}/{entry.name}: agents are folders containing"
                f" {_AGENT_FILE}"
            )
            continue
        manifest = entry / _AGENT_FILE
        rel = f"{_AGENTS_PATH}/{entry.name}/{_AGENT_FILE}"
        if not manifest.is_file():
            errors.append(f"[{pname}] {rel} not found")
            continue

        # keep the raw frontmatter: load_agent_spec fills defaults that hide what the author wrote
        try:
            fm, body = split_frontmatter(manifest)
        except yaml.YAMLError as ex:
            errors.append(f"[{pname}] {rel} invalid YAML frontmatter: {ex}")
            continue

        # dlt raises here for an empty body, a missing name, `inputs.prompt`, or an unknown
        # access axis or verb
        agent_names.add(entry.name)
        try:
            load_agent_spec(str(entry))
        except InvalidAgentSpec as ex:
            errors.append(f"[{pname}] {rel} {_dlt_reason(ex)}")
            continue

        # dlt uses the folder name only when `name` is absent, so a mismatch loads and then
        # does not resolve as <toolkit>:<name>
        if fm.get("name") and fm["name"] != entry.name:
            errors.append(
                f"[{pname}] {rel} frontmatter name {fm['name']!r} != folder {entry.name!r}"
            )

        _validate_agent_body(pname, rel, fm, body, errors, warnings)
        for kind, refs in (("skills", fm.get("skills")), ("rules", fm.get("rules"))):
            for ref in refs or []:
                if msg := _check_ref(ref, kind, pname, inventory):
                    errors.append(f"[{pname}] {rel} {msg}")
        _validate_entity_types(pname, rel, fm, errors, warnings)
        _validate_output(pname, rel, fm, errors, warnings)
        _validate_schema_types(pname, rel, fm, errors, warnings)
        _validate_optional_count(pname, rel, fm, errors, warnings)
        _validate_output_size(pname, rel, fm, errors, warnings)
        _validate_tools_access(pname, rel, fm, errors, warnings)
        _validate_defaults(pname, rel, fm, errors, warnings)
        _validate_agent_code(pname, entry, errors)
        _validate_shipped_files(pname, entry, errors)

    return agent_names


_UNTRACKED_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"}
"""Gitignored tool caches. An install works from a checkout, which never holds them."""


def _validate_shipped_files(pname: str, agent_dir: Path, errors: list[str]) -> None:
    """Check that the agent folder holds only the `AGENT.md` and Python modules."""
    # an install copies the folder verbatim, so a stray file lands in every workspace
    stray = sorted(
        path.name
        for path in agent_dir.iterdir()
        if path.name != _AGENT_FILE
        and path.name not in _UNTRACKED_DIRS
        and not (path.is_file() and path.suffix == ".py")
    )
    if stray:
        errors.append(
            f"[{pname}] {_AGENTS_PATH}/{agent_dir.name} holds {', '.join(stray)}. An install"
            f" copies the folder verbatim. Keep only {_AGENT_FILE} and Python modules"
        )


def _validate_agent_code(pname: str, agent_dir: Path, errors: list[str]) -> None:
    """Check that `agent.py` parses and defines its hooks as functions."""
    for source in sorted(agent_dir.glob("agent.py")):
        rel = f"{_AGENTS_PATH}/{agent_dir.name}/{source.name}"
        # dlt imports `agent.py` only when a job runs, so parse it here without importing
        try:
            tree = ast.parse(source.read_text(encoding="utf-8"))
        except SyntaxError as ex:
            errors.append(f"[{pname}] {rel} does not parse: {ex}")
            continue
        for node in tree.body:
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                names = node.targets if isinstance(node, ast.Assign) else [node.target]
                for name in names:
                    if isinstance(name, ast.Name) and name.id in _AGENT_HOOKS:
                        errors.append(f"[{pname}] {rel} `{name.id}` must be a function")


def _validate_agent_body(
    pname: str, rel: str, fm: dict, body: str, errors: list[str], warnings: list[str]
) -> None:
    """Check that the system prompt names only declared inputs and uses all of them."""
    if not body.strip():
        errors.append(f"[{pname}] {rel} has an empty body — the body is the system prompt")
        return

    declared = (fm.get("inputs") or {}).get("properties")
    declared = set(declared) if isinstance(declared, dict) else set()
    used = set(_PLACEHOLDER.findall(body))

    for placeholder in sorted(used):
        root = placeholder.split(".")[0]
        # `run_context.*` is always available; any other undeclared placeholder renders empty
        if root == "run_context" or placeholder in declared:
            continue
        errors.append(
            f"[{pname}] {rel} body uses '{{{{ {placeholder} }}}}' which is not declared"
            " in inputs.properties"
        )
    for unused in sorted(declared - {u.split(".")[0] for u in used}):
        warnings.append(
            f"[{pname}] {rel} input '{unused}' is declared but no placeholder in the system"
            " prompt names it"
        )


def _validate_entity_types(
    pname: str, rel: str, fm: dict, errors: list[str], warnings: list[str]
) -> None:
    """Check that `entity_type` sits on string properties and agrees between input and output."""
    entity_types: dict[str, dict[str, str]] = {}
    for where, schema in (("inputs", fm.get("inputs")), ("output", fm.get("output"))):
        # dlt rejects an unknown entity type
        try:
            entity_types[where] = dict(entity_properties(schema, rel))
        except InvalidJobSchema as ex:
            errors.append(f"[{pname}] {rel} {where}: {_dlt_reason(ex)}")
            entity_types[where] = {}

    for where, found in entity_types.items():
        props = ((fm.get(where) or {}).get("properties")) or {}
        for name in found:
            declared_type = (props.get(name) or {}).get("type")
            if declared_type not in (None, "string"):
                errors.append(
                    f"[{pname}] {rel} {where}.{name} carries {ENTITY_TYPE_KEY} but is"
                    f" {declared_type!r}; an entity is passed as its bare id, so the"
                    " property must be a string"
                )

    # an output of the same name overwrites the input in the run's `object` list, so the
    # two must name the same kind of thing or the entity silently changes type
    entity_inputs, entity_outputs = entity_types["inputs"], entity_types["output"]
    for name, entity in entity_outputs.items():
        if name in entity_inputs and entity != entity_inputs[name]:
            errors.append(
                f"[{pname}] {rel} output.{name} is {entity!r} but the input of the same"
                f" name is {entity_inputs[name]!r}; the output overwrites the input,"
                " so they must agree"
            )

    # only the first entity-typed input is exposed, and declaration order decides it
    if len(entity_inputs) > 1:
        first, *rest = entity_inputs
        warnings.append(
            f"[{pname}] {rel} has several entity inputs ({', '.join(entity_inputs)});"
            f" only the first, '{first}', becomes expose.object_input. Put {rest[0]!r}"
            " first if the web UI must offer the agent job from that entity"
        )


def _validate_output(
    pname: str, rel: str, fm: dict, errors: list[str], warnings: list[str]
) -> None:
    """Check `status` and `summary` in the output schema."""
    output = fm.get("output")
    if output is None:
        warnings.append(
            f"[{pname}] {rel} declares no output — {', '.join(_OUTPUT_CONTRACT)} will be"
            " added from the standard TypedDict"
        )
        return
    if not isinstance(output, dict):
        errors.append(f"[{pname}] {rel} output must be a JSON Schema mapping")
        return

    props = output.get("properties")
    props = props if isinstance(props, dict) else {}
    required = output.get("required")
    required = required if isinstance(required, list) else []

    # dlt adds a missing field from `TAgentOutput` but overwrites a conflicting declared type
    missing = [f for f in _OUTPUT_CONTRACT if not isinstance(props.get(f), dict)]
    if missing:
        warnings.append(
            f"[{pname}] {rel} output does not declare {', '.join(missing)}"
            " — it will be added from the standard TypedDict"
        )

    status = props.get("status")
    if isinstance(status, dict):
        values = status.get("enum")
        if values is not None and sorted(values) != sorted(_STATUS_VALUES):
            errors.append(
                f"[{pname}] {rel} output.status declares {values} but the contract is"
                f" {_STATUS_VALUES}; give a domain-specific status another name"
                " (for example `verdict`)"
            )
        elif values is None and status.get("type") not in (None, _SUMMARY_TYPE):
            errors.append(
                f"[{pname}] {rel} output.status has type {status.get('type')!r};"
                f" the contract is an enum of {_STATUS_VALUES}"
            )

    summary = props.get("summary")
    if isinstance(summary, dict):
        declared_type = summary.get("type")
        if declared_type not in (None, _SUMMARY_TYPE):
            errors.append(
                f"[{pname}] {rel} output.summary declares type {declared_type!r} but the"
                f" contract is {_SUMMARY_TYPE!r}"
            )

    # `required` and the descriptions are filled in by the TypedDict, so only nudge
    for field in _OUTPUT_CONTRACT:
        spec = props.get(field)
        if isinstance(spec, dict):
            if field not in required:
                warnings.append(
                    f"[{pname}] {rel} output.required omits '{field}'; the TypedDict"
                    " makes it required"
                )
            if not str(spec.get("description", "")).strip():
                warnings.append(
                    f"[{pname}] {rel} output.{field} has no description; the standard"
                    " one will be used"
                )


MAX_OPTIONAL_PROPERTIES = 24
"""Anthropic refuses more optional properties than this, nested ones counted."""

REJECTED_KEYWORDS = frozenset({"minimum", "maximum", "minLength", "maxLength"})
"""Anthropic's structured output rejects these keywords; a bound goes in the description."""

MAX_OUTPUT_CHARS = 8000
"""The model reads the whole output schema on every run, and a large one has stopped a job."""


def _validate_optional_count(
    pname: str, rel: str, fm: dict, errors: list[str], warnings: list[str]
) -> None:
    """Check `output` against the provider's cap. A property in its object's `required` does
    not count, and a nested `required` binds only when the model writes that object."""
    output = fm.get("output")
    if not isinstance(output, dict):
        return
    optional = _optional_properties(output)
    if len(optional) > MAX_OPTIONAL_PROPERTIES:
        errors.append(
            f"[{pname}] {rel} output declares {len(optional)} optional properties, over the"
            f" {MAX_OPTIONAL_PROPERTIES} Anthropic accepts; a property listed in its object's"
            " `required` does not count, and a nested `required` binds only when the model"
            " writes that object, so every nested property of a field Python fills belongs in"
            f" one ({', '.join(optional[:6])}, ...)"
        )


def _optional_properties(schema: dict, path: str = "") -> list[str]:
    optional: list[str] = []
    props = schema.get("properties")
    required = schema.get("required")
    required = set(required) if isinstance(required, list) else set()
    for name, spec in (props if isinstance(props, dict) else {}).items():
        if not isinstance(spec, dict):
            continue
        here = f"{path}.{name}" if path else name
        if name not in required:
            optional.append(here)
        optional += _optional_properties(spec, here)
        items = spec.get("items")
        if isinstance(items, dict):
            optional += _optional_properties(items, f"{here}[]")
    return optional


def _validate_output_size(
    pname: str, rel: str, fm: dict, errors: list[str], warnings: list[str]
) -> None:
    """Check the serialized `output` against the size a job has launched with."""
    output = fm.get("output")
    if not isinstance(output, dict):
        return
    size = len(json.dumps(output))
    if size > MAX_OUTPUT_CHARS:
        errors.append(
            f"[{pname}] {rel} output is {size} characters, over the {MAX_OUTPUT_CHARS} a job"
            " has launched with. Keep each item's schema to the fields a reader acts on"
        )


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
"""Axes each feature group needs before the server offers any of its tools. The catalogue is in
`create-background-agent/agent-md-reference.md`. A group not listed is checked against the axes
as a whole."""

SELF_SERVING_GROUPS = frozenset(group for group, axes in GROUP_AXES.items() if not axes)
"""Groups whose tools carry `RequiresAccess()`. Every other group serves nothing without an axis."""


def _validate_tools_access(
    pname: str, rel: str, fm: dict, errors: list[str], warnings: list[str]
) -> None:
    """Check that a declared feature group has an `access` axis that can serve it."""
    groups = [g for g in (fm.get("tools") or []) if g not in SELF_SERVING_GROUPS]
    access = fm.get("access") or {}
    for group in [g for g in groups if g in GROUP_AXES]:
        missing = [axis for axis in GROUP_AXES[group] if not access.get(axis)]
        if missing:
            errors.append(
                f"[{pname}] {rel} tools lists {group} but access grants no"
                f" {' and no '.join(missing)}; none of its tools are served"
            )
    rest = [g for g in groups if g not in GROUP_AXES]
    if rest and not any(access.get(axis) for axis in ACCESS_AXES):
        errors.append(
            f"[{pname}] {rel} tools lists {', '.join(rest)} but access grants no"
            f" {', '.join(ACCESS_AXES)} axis; the server then serves the toolkit catalogue"
            " alone and the agent is offered none of those tools"
        )


def _validate_schema_types(
    pname: str, rel: str, fm: dict, errors: list[str], warnings: list[str]
) -> None:
    """Check that every property of `inputs` and `output` names a `type`."""
    for field in ("inputs", "output"):
        node = fm.get(field)
        if isinstance(node, dict):
            _walk_properties(pname, f"{rel} {field}", node, errors)


def _walk_properties(pname: str, where: str, schema: dict, errors: list[str]) -> None:
    props = schema.get("properties")
    for name, spec in (props if isinstance(props, dict) else {}).items():
        if not isinstance(spec, dict):
            continue
        # Anthropic refuses an enum without a type; dlt fills the type on `status` only
        if not any(key in spec for key in ("type", "anyOf", "oneOf", "allOf", "$ref")):
            errors.append(
                f"[{pname}] {where}.{name} names no type; a property carrying an enum alone"
                " is refused by Anthropic's structured output. Add `type: string`"
            )
        if spec.get("type") == "object" and "properties" not in spec:
            errors.append(
                f"[{pname}] {where}.{name} is a bare object; a strict validator refuses it and"
                " OpenAI's structured output falls back. Name its `properties`"
            )
        for keyword in sorted(REJECTED_KEYWORDS & set(spec)):
            errors.append(
                f"[{pname}] {where}.{name} carries {keyword!r}, which Anthropic's structured"
                " output rejects. Put the bound in the description"
            )
        _walk_properties(pname, f"{where}.{name}", spec, errors)
        items = spec.get("items")
        if isinstance(items, dict):
            _walk_properties(pname, f"{where}.{name}[]", items, errors)


def _validate_defaults(
    pname: str, rel: str, fm: dict, errors: list[str], warnings: list[str]
) -> None:
    """Check the `defaults` block: known keys and limits, and no `model` or `trigger`."""
    node = fm.get("defaults")
    if node is None:
        warnings.append(f"[{pname}] {rel} has no defaults, so no limits are set")
        return
    if not isinstance(node, dict):
        errors.append(f"[{pname}] {rel} defaults must be a mapping")
        return
    for key in node:
        if key not in _DEFAULTS_KEYS:
            errors.append(
                f"[{pname}] {rel} unknown defaults key '{key}'; expected:"
                f" {', '.join(sorted(_DEFAULTS_KEYS))}"
            )
    # the manifest drops `defaults`, so a trigger declared here does nothing
    if node.get("trigger") is not None:
        errors.append(
            f"[{pname}] {rel} defaults.trigger {node['trigger']!r} is never read; set"
            " trigger= on run.agent, where the workspace names its own jobs"
        )

    # a shipped definition names no provider: the aliases resolve on Anthropic, OpenAI
    # and Google, and an Azure workspace has none. the deployment pins the model.
    if node.get("model") is not None:
        errors.append(
            f"[{pname}] {rel} defaults.model {node['model']!r} pins a provider on every"
            " workspace that installs the toolkit; leave it out and say in the AGENT.md"
            " what to pin"
        )

    limits = node.get("limits") or {}
    if not isinstance(limits, dict):
        errors.append(f"[{pname}] {rel} defaults.limits must be a mapping")
        return
    for key in limits:
        if key not in _LIMITS_KEYS:
            errors.append(
                f"[{pname}] {rel} unknown limit '{key}'; expected:"
                f" {', '.join(sorted(_LIMITS_KEYS))}"
            )


def _extract_sections(text: str) -> dict[str, str]:
    """Split markdown into {heading_lower: body} by ## headings."""
    sections: dict[str, str] = {}
    current_heading = None
    current_lines: list[str] = []

    for line in text.splitlines():
        if line.startswith("## "):
            if current_heading is not None:
                sections[current_heading] = "\n".join(current_lines)
            current_heading = line[3:].strip().lower()
            current_lines = []
        else:
            current_lines.append(line)

    if current_heading is not None:
        sections[current_heading] = "\n".join(current_lines)
    return sections


def validate_workflow(
    pname: str,
    plugin_dir: Path,
    component_names: set[str],
    marketplace_names: set[str],
    errors: list[str],
    warnings: list[str],
) -> None:
    """Validate workflow.md structure, its (`name`) skill and agent refs, and handover refs."""
    workflow_path = plugin_dir / "rules" / "workflow.md"
    if not workflow_path.exists():
        return

    text = workflow_path.read_text()

    workflow_refs = set(_WORKFLOW_SKILL_REF.findall(text))
    for ref in sorted(workflow_refs):
        if ref not in component_names:
            errors.append(
                f"[{pname}] workflow.md references '{ref}' but no skill or agent directory exists"
            )

    sections = _extract_sections(text)

    for required in _WORKFLOW_REQUIRED_SECTIONS:
        if required not in sections:
            errors.append(
                f"[{pname}] workflow.md missing required section: '## {required.title()}'"
            )

    if _WORKFLOW_HANDOVER_SECTION not in sections:
        warnings.append(
            f"[{pname}] workflow.md missing section: '## {_WORKFLOW_HANDOVER_SECTION.title()}'"
        )

    handover_text = sections.get(_WORKFLOW_HANDOVER_SECTION, "")
    if handover_text:
        handover_refs = set(_WORKFLOW_HANDOVER_REF.findall(handover_text))
        for ref in sorted(handover_refs):
            if ref == pname:
                warnings.append(f"[{pname}] workflow.md handover references itself")
            elif ref not in marketplace_names:
                errors.append(
                    f"[{pname}] workflow.md handover references '{ref}' "
                    f"but no such toolkit in marketplace"
                )


_URL_LINK = re.compile(r"\[[^\]]*\]\(https?://[^)]*\)")
_URL = re.compile(r"https?://\S+")
# `README.md` and `CLAUDE.md` are names a skill may legitimately discuss in a user's project
_GENERIC_DOCS = {"README.md", "CLAUDE.md"}


def root_doc_refs(plugin_dir: Path, root: Path) -> list[tuple[str, str]]:
    """(file, document) per repo-root document a toolkit file names outside a URL."""
    # an install copies only the toolkit directory, so a root document is missing there
    docs = {path.name for path in root.glob("*.md")} - _GENERIC_DOCS
    found: list[tuple[str, str]] = []
    for path in sorted(plugin_dir.rglob("*")):
        if path.suffix not in (".md", ".py") or not path.is_file():
            continue
        # a URL resolves anywhere, so drop it together with its link text
        text = _URL.sub("", _URL_LINK.sub("", path.read_text(encoding="utf-8", errors="ignore")))
        found += [(str(path.relative_to(plugin_dir)), doc) for doc in sorted(docs) if doc in text]
    return found


def validate_toolkit_content(
    pname: str,
    plugin_dir: Path,
    marketplace_names: set[str],
    inventory: dict[str, dict],
    errors: list[str],
    warnings: list[str],
) -> set[str]:
    """Validate skills, commands, rules, agents, and workflow. Returns skill names."""
    for naming_file, doc in root_doc_refs(plugin_dir, plugin_dir.parents[1]):
        errors.append(
            f"[{pname}] {naming_file} names '{doc}', which sits at the repo root and no install"
            " brings into a workspace; point at a file in the toolkit or at the document's URL"
        )
    skill_names = _validate_skills(pname, plugin_dir, errors, warnings)
    _validate_commands(pname, plugin_dir, errors, warnings)
    _validate_rules(pname, plugin_dir, errors)
    agent_names = validate_agents(pname, plugin_dir, inventory, errors, warnings)
    validate_workflow(
        pname, plugin_dir, skill_names | agent_names, marketplace_names, errors, warnings
    )
    return skill_names


def _validate_skills(
    pname: str, plugin_dir: Path, errors: list[str], warnings: list[str]
) -> set[str]:
    """Validate `skills/<name>/SKILL.md` files. Returns skill names."""
    skills_dir = plugin_dir / "skills"
    skill_names: set[str] = set()
    if not skills_dir.is_dir():
        return skill_names
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            errors.append(f"[{pname}] {skill_dir.name}/ missing SKILL.md")
            continue

        fm = frontmatter_of(skill_md, f"{skill_dir.name}/SKILL.md", pname, errors)
        fm_name = fm.get("name", "")
        fm_desc = fm.get("description", "")

        if not fm_name:
            errors.append(f"[{pname}] {skill_dir.name}/SKILL.md missing 'name' in frontmatter")
        elif fm_name != skill_dir.name:
            errors.append(
                f"[{pname}] {skill_dir.name}/SKILL.md "
                f"frontmatter name '{fm_name}' != directory '{skill_dir.name}'"
            )

        if not fm_desc:
            warnings.append(
                f"[{pname}] {skill_dir.name}/SKILL.md missing 'description' in frontmatter"
            )
        elif len(fm_desc) > MAX_DESCRIPTION_CHARS:
            warnings.append(
                f"[{pname}] {skill_dir.name}/SKILL.md description is {len(fm_desc)} chars, "
                f"over the {MAX_DESCRIPTION_CHARS} cap"
            )

        _check_argument_hint(pname, f"{skill_dir.name}/SKILL.md", fm, errors)
        skill_names.add(skill_dir.name)
    return skill_names


def _validate_commands(
    pname: str, plugin_dir: Path, errors: list[str], warnings: list[str]
) -> None:
    """Validate `commands/*.md`: a `name` that matches the file name, and a `description`."""
    commands_dir = plugin_dir / "commands"
    if not commands_dir.is_dir():
        return
    for cmd_file in sorted(commands_dir.iterdir()):
        if cmd_file.suffix != ".md":
            warnings.append(f"[{pname}] non-markdown in commands/: {cmd_file.name}")
            continue
        if cmd_file.stat().st_size == 0:
            errors.append(f"[{pname}] empty command: {cmd_file.name}")
            continue

        fm = frontmatter_of(cmd_file, f"commands/{cmd_file.name}", pname, errors)
        fm_name = fm.get("name", "")
        fm_desc = fm.get("description", "")

        if not fm_name:
            errors.append(f"[{pname}] commands/{cmd_file.name} missing 'name' in frontmatter")
        elif fm_name != cmd_file.stem:
            errors.append(
                f"[{pname}] commands/{cmd_file.name} "
                f"frontmatter name '{fm_name}' != filename '{cmd_file.stem}'"
            )

        if not fm_desc:
            errors.append(
                f"[{pname}] commands/{cmd_file.name} missing 'description' in frontmatter"
            )

        _check_argument_hint(pname, f"commands/{cmd_file.name}", fm, errors)


def _check_argument_hint(pname: str, label: str, fm: dict, errors: list[str]) -> None:
    """Check that every token of `argument-hint` uses the [bracket] convention."""
    hint = fm.get("argument-hint", "")
    if not hint:
        return
    tokens = hint.strip('"').strip("'").split()
    bad = [t for t in tokens if not _ARGUMENT_HINT_TOKEN.match(t)]
    if bad:
        errors.append(
            f"[{pname}] {label} "
            f"argument-hint tokens must use [bracket] convention, "
            f"got: {' '.join(bad)}"
        )


def _validate_rules(pname: str, plugin_dir: Path, errors: list[str]) -> None:
    """Check that no rule file has frontmatter, so every rule is catch-all."""
    rules_dir = plugin_dir / "rules"
    if not rules_dir.is_dir():
        return
    for rule_file in sorted(rules_dir.rglob("*.md")):
        rel = rule_file.relative_to(plugin_dir)
        fm = frontmatter_of(rule_file, str(rel), pname, errors)
        if fm:
            errors.append(
                f"[{pname}] {rel} has frontmatter — rules must be catch-all (no frontmatter)"
            )


def validate_index_drift(
    root: Path,
    marketplace_names: set[str],
    errors: list[str],
) -> None:
    """Check that each intent index lists exactly the workflow toolkits of the marketplace."""
    expected = marketplace_names - _NON_WORKFLOW_TOOLKITS

    for rel in _INDEX_FILES:
        path = root / rel
        if not path.exists():
            errors.append(f"index file not found: {rel}")
            continue

        indexed = {
            m.group(1)
            for line in path.read_text().splitlines()
            # data rows carry an install command; this skips the column header
            if "ai toolkit" in line and (m := _INDEX_ENTRY.search(line))
        }
        fname = Path(rel).name
        for name in sorted(expected - indexed):
            errors.append(f"[init] {fname} intent index is missing workflow toolkit '{name}'")
        for name in sorted(indexed - expected):
            errors.append(
                f"[init] {fname} intent index lists '{name}' "
                f"which is not a workflow toolkit in marketplace.json"
            )


def validate_capability_coverage(
    root: Path,
    inventory: dict[str, dict],
    errors: list[str],
) -> None:
    """Check that the router indexes every agent and each workflow.md every skill and agent."""
    router = root / _ROUTER_SKILL
    if not router.exists():
        errors.append(f"router skill not found: {_ROUTER_SKILL}")
        return

    routed = {
        m.group(1)
        for line in router.read_text().splitlines()
        # data rows carry an install command; this skips the column header
        if "ai toolkit" in line and (m := _ROUTER_AGENT_ENTRY.search(line))
    }
    shipped = {
        f"{name}:{agent}"
        for name, components in inventory.items()
        for agent in components["agents"]
    }
    for ref in sorted(shipped - routed):
        errors.append(f"[init] dlthub-router agent index is missing '{ref}'")
    for ref in sorted(routed - shipped):
        errors.append(f"[init] dlthub-router agent index lists '{ref}' which no toolkit ships")

    for name, components in sorted(inventory.items()):
        if name in _NON_WORKFLOW_TOOLKITS:
            continue
        workflow = root / AI_DIR / name / "rules" / "workflow.md"
        if not workflow.exists():
            errors.append(f"[{name}] missing rules/workflow.md, so nothing indexes its skills")
            continue
        refs = set(_WORKFLOW_SKILL_REF.findall(workflow.read_text()))
        # rules need no entry, they are always in context
        for missing in sorted((components["skills"] | components["agents"]) - refs):
            errors.append(f"[{name}] workflow.md does not reference '{missing}'")


def validate(
    root: Path, only: str | None = None
) -> tuple[list[str], list[str], dict[str, set[str]]]:
    """Validate all toolkits, or only `only`. Returns errors, warnings and skills per toolkit."""
    errors: list[str] = []
    warnings: list[str] = []

    marketplace_path = root / ".claude-plugin" / "marketplace.json"
    if not marketplace_path.exists():
        errors.append(f"Missing {marketplace_path.relative_to(root)}")
        return errors, warnings, {}

    marketplace = json.loads(marketplace_path.read_text())
    marketplace_names = {e.get("name") for e in marketplace.get("plugins", [])}

    inventory = build_component_inventory(root)

    all_skills: dict[str, set[str]] = {}

    for entry in marketplace.get("plugins", []):
        pname = entry.get("name", "<unnamed>")
        source = entry.get("source", "")
        plugin_dir = root / source

        if only and pname != only:
            continue

        source_path = Path(source)
        clean = str(source_path).lstrip("./")
        if not clean.startswith("workbench/"):
            errors.append(f"[{pname}] source '{source}' must be under ./workbench/")

        if Path(source).name != pname:
            errors.append(
                f"[{pname}] source last segment '{Path(source).name}' "
                f"must match plugin name '{pname}'"
            )

        if not plugin_dir.is_dir():
            errors.append(f"[{pname}] directory not found: {source}")
            continue

        pjson_path = plugin_dir / ".claude-plugin" / "plugin.json"
        if not pjson_path.exists():
            errors.append(f"[{pname}] missing .claude-plugin/plugin.json")
        else:
            pjson = json.loads(pjson_path.read_text())
            if pjson.get("name") != pname:
                errors.append(
                    f"[{pname}] plugin.json name '{pjson.get('name')}' "
                    f"!= marketplace name '{pname}'"
                )

            author = pjson.get("author", {})
            author_name = author.get("name", "") if isinstance(author, dict) else ""
            if author_name != _EXPECTED_AUTHOR:
                errors.append(
                    f"[{pname}] plugin.json author.name '{author_name}' "
                    f"!= expected '{_EXPECTED_AUTHOR}'"
                )

            license_val = pjson.get("license", "")
            if license_val != _EXPECTED_LICENSE:
                errors.append(
                    f"[{pname}] plugin.json license '{license_val}' "
                    f"!= expected '{_EXPECTED_LICENSE}'"
                )

        all_skills[pname] = validate_toolkit_content(
            pname, plugin_dir, marketplace_names, inventory, errors, warnings
        )

    if only and only not in all_skills:
        errors.append(f"Toolkit '{only}' not found in marketplace.json")

    if not only:
        ai_dir = root / AI_DIR
        if ai_dir.is_dir():
            for d in sorted(ai_dir.iterdir()):
                if not d.is_dir() or d.name.startswith("."):
                    continue
                if d.name not in marketplace_names:
                    errors.append(
                        f"[{d.name}] directory exists in {AI_DIR}/ "
                        f"but is not listed in marketplace.json"
                    )

        validate_index_drift(root, marketplace_names, errors)
        validate_capability_coverage(root, inventory, errors)

    return errors, warnings, all_skills


def main():
    root = Path(__file__).resolve().parent.parent
    only = sys.argv[1] if len(sys.argv) > 1 else None

    if only:
        print(f"Validating toolkit '{only}' in {root}\n")
    else:
        print(f"Validating plugins in {root}\n")

    errors, warnings, all_skills = validate(root, only)

    for w in warnings:
        print(f"  WARN  {w}")
    if errors:
        for e in errors:
            print(f"  ERROR {e}")
    else:
        print("  All checks passed.")

    print()
    for pname, skills in sorted(all_skills.items()):
        if skills:
            print(f"  [{pname}] {len(skills)} skills: {', '.join(sorted(skills))}")
        else:
            print(f"  [{pname}] no skills (commands only)")

    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
