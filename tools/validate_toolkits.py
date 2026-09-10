#!/usr/bin/env python3
"""Validate Claude Code plugin marketplace and verify plugin consistency.

Usage:
    python tools/validate_toolkits.py              # validate all toolkits
    python tools/validate_toolkits.py <name>       # validate one toolkit by name

Checks:
- marketplace.json structure
- Each plugin source points to a directory under ./workbench/ with last segment matching plugin name
- plugin.json exists and name matches marketplace entry
- plugin.json author.name is "dltHub, Inc." and license URL is correct
- Skills have valid SKILL.md with frontmatter (name, description)
- Skill frontmatter name matches directory name
- Commands have valid frontmatter (name, description), name matches filename
- argument-hint uses [bracket] convention per Anthropic docs
- Rules are catch-all (no frontmatter allowed)
- Agents live in dlthub/agents/<name>/AGENT.md; name matches the folder; body is the system prompt
- Agent `access` axes/verbs are known; the body's placeholders are declared inputs
- Agent `entity_type` values are known, sit on string properties, and agree input vs output
- Agent `output` may omit status/summary (warning); a type conflict on them is an error
- Agent `skills` / `rules` refs resolve in the toolkit or a declared dependency
- workflow.md (`skill-name`) references point to real skill directories
- workflow.md has required sections (Core workflow, Handover to other toolkits)
- workflow.md handover references point to real toolkits in marketplace
- All workbench/ directories must be listed in marketplace
"""

import json
import re
import sys
import typing
from pathlib import Path

import yaml
from dlt._workspace.deployment.agent.exceptions import InvalidAgentSpec
from dlt._workspace.deployment.agent.manifest import load_agent_spec
from dlt._workspace.deployment.agent.typing import (
    AGENT_MODEL_ALIASES,
    TAgentDefaults,
    TAgentJobStatus,
    TAgentLimits,
    TAgentOutput,
)
from dlt._workspace.deployment.exceptions import InvalidJobSchema
from dlt._workspace.deployment.reflection import ENTITY_TYPE_KEY, entity_properties
from dlt._workspace.deployment.typing import THubEntityType
from dlt._workspace.cli.dlthub.ai.agents import COMPONENT_MARKERS
from dlt._workspace.cli.formatters import parse_frontmatter
from dlt.common.typing import get_args

AI_DIR = "workbench"

# The always-loaded compact intent->toolkit index is duplicated across two
# always-loaded surfaces: the rule (native on Claude/Cursor) and AGENTS.md
# (the only always-loaded surface on Codex, where rules become opt-in skills).
# Both must list the same workflow toolkits.
_INDEX_FILES = (
    "workbench/init/rules/dlthub-workspace.md",
    "workbench/init/AGENTS.md",
)
# Toolkits that are NOT workflow toolkits, so they don't belong in the intent index:
# `init` is the lean base itself; `bootstrap` only scaffolds the environment.
_NON_WORKFLOW_TOOLKITS = {"init", "bootstrap"}
# An index row: "<intent text> → <toolkit> | <install> | <entry skill>".
# Capture the toolkit name (the token right after the arrow, before the pipe).
_INDEX_ENTRY = re.compile(r"→\s*([a-z][\w-]*)\s*\|")

# Expected plugin.json author and license values
_EXPECTED_AUTHOR = "ScaleVector GmbH"
_EXPECTED_LICENSE = "https://github.com/dlt-hub/dlthub-ai-workbench/blob/master/LICENSE"

# argument-hint must be quoted and use [bracket] convention per Anthropic docs
# valid: "[pipeline-name]", "[filename] [format]", "[pipeline-name] [query]"
# invalid: <angle-brackets>, unquoted values with [, -- separators
_ARGUMENT_HINT_TOKEN = re.compile(r"^\[[\w-]+\]$")

# workflow.md section headings (case-insensitive match)
_WORKFLOW_REQUIRED_SECTIONS = ["core workflow"]
_WORKFLOW_OPTIONAL_SECTIONS = ["extend and harden"]
_WORKFLOW_HANDOVER_SECTION = "handover to other toolkits"

# (`skill-name`) references in workflow
_WORKFLOW_SKILL_REF = re.compile(r"\(`([a-z][\w-]*)`\)")

# **toolkit-name** references in handover section
_WORKFLOW_HANDOVER_REF = re.compile(r"\*\*([a-z][\w-]*)\*\*")

# --- background agents (see BACKGROUND_AGENTS.md) ---
# Agents are folders, like skills, under `dlthub/` so they never mix with a host's
# native agents (`.claude/agents/`, `.codex/agents/`): `dlthub/agents/<name>/AGENT.md`.
#
# dlt owns the contract, so everything below comes from dlt rather than being restated
# here: `load_agent_spec` is the same reader the runtime uses, and the vocabularies are
# the types the runtime enforces. This file adds only what dlt cannot know — that a
# workbench toolkit is a *source* tree, not an installed workspace.
_AGENT_FILE = COMPONENT_MARKERS["agent"]
_AGENTS_DIR = ("dlthub", "agents")
_AGENTS_PATH = "/".join(_AGENTS_DIR)
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
    """Frontmatter of a component file, reporting a YAML error instead of raising.

    Skills, commands and rules used to go through a line-based reader that silently
    returned nothing for malformed YAML. dlt's parser is strict, so the malformed case
    now surfaces — as a finding rather than a traceback.
    """
    try:
        fm, _ = split_frontmatter(path)
    except yaml.YAMLError as ex:
        errors.append(f"[{pname}] {label} invalid YAML frontmatter: {ex}")
        return {}
    return fm


def split_frontmatter(path: Path) -> tuple[dict, str]:
    """Split a markdown file into (frontmatter, body), using dlt's own parser.

    The same reader `load_agent_spec` uses, so this file sees exactly the frontmatter
    the runtime will. A file with no frontmatter comes back as `({}, text)`.

    Raises:
        yaml.YAMLError: When the frontmatter block is not valid YAML.
    """
    return parse_frontmatter(path.read_text(encoding="utf-8"))


def build_component_inventory(root: Path) -> dict[str, dict]:
    """Map every workbench toolkit to the components it exposes and its dependencies.

    Built as a pre-pass because agent manifests reference components across
    toolkit boundaries (into their declared dependencies).
    """
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
            "agents": _agent_names(tk_dir.joinpath(*_AGENTS_DIR)),
            "commands": _stems(tk_dir / "commands"),
            "dependencies": dependencies,
        }
    return inventory


def _agent_names(directory: Path) -> set[str]:
    """Agent folder names — those containing an AGENT.md."""
    if not directory.is_dir():
        return set()
    return {p.name for p in directory.iterdir() if (p / _AGENT_FILE).is_file()}


def _stems(directory: Path) -> set[str]:
    """Markdown file stems in a directory, or an empty set when it is absent."""
    if not directory.is_dir():
        return set()
    return {p.stem for p in directory.glob("*.md")}


def _check_ref(ref: object, kind: str, pname: str, inventory: dict[str, dict]) -> str | None:
    """Resolve a `<toolkit>:<name>` component ref. Returns an error message or None.

    A ref may only point at the own toolkit or one of its declared dependencies —
    anything else would silently degrade when that toolkit is not installed.
    """
    if not isinstance(ref, str):
        return f"{kind} ref must be a string, got {type(ref).__name__}"
    match = _AGENT_REF.match(ref.strip())
    if not match:
        return f"malformed {kind} ref '{ref}' (expected 'name' or 'toolkit:name')"

    toolkit = match.group(1) or pname
    name = match.group(2)
    if toolkit not in inventory:
        return f"{kind} ref '{ref}' points to unknown toolkit '{toolkit}'"
    if toolkit != pname and toolkit not in inventory[pname]["dependencies"]:
        return (
            f"{kind} ref '{ref}' points to '{toolkit}' "
            f"which is not a declared dependency of '{pname}'"
        )
    if name not in inventory[toolkit][kind]:
        return f"{kind} ref '{ref}' does not resolve to a {kind[:-1]} in toolkit '{toolkit}'"
    return None


def _dlt_reason(ex: Exception) -> str:
    """The reason out of a dlt validation error, without repeating the file path.

    dlt's validation errors carry the bare reason in `errors` and prefix the path into
    `str(ex)`; every message here is already prefixed with the file, so take the former.
    """
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
    """Validate dlthub/agents/<name>/AGENT.md manifests. See BACKGROUND_AGENTS.md."""
    agent_names: set[str] = set()
    agents_dir = plugin_dir.joinpath(*_AGENTS_DIR)
    if not agents_dir.is_dir():
        return agent_names

    for entry in sorted(agents_dir.iterdir()):
        if not entry.is_dir():
            errors.append(
                f"[{pname}] {_AGENTS_PATH}/{entry.name}: agents are folders containing"
                f" {_AGENT_FILE} (see BACKGROUND_AGENTS.md)"
            )
            continue
        manifest = entry / _AGENT_FILE
        rel = f"{_AGENTS_PATH}/{entry.name}/{_AGENT_FILE}"
        if not manifest.is_file():
            errors.append(f"[{pname}] {rel} not found")
            continue

        # The raw frontmatter, kept because `load_agent_spec` normalizes: it fills the
        # output from `TAgentOutput` and falls the name back to the folder. Telling an
        # author what dlt would silently change needs what they actually wrote.
        try:
            fm, body = split_frontmatter(manifest)
        except yaml.YAMLError as ex:
            errors.append(f"[{pname}] {rel} invalid YAML frontmatter: {ex}")
            continue

        # dlt's own reader is the contract: empty body, missing name, `inputs.prompt`,
        # unknown access axis or verb all raise here, with the runtime's wording.
        agent_names.add(entry.name)
        try:
            load_agent_spec(str(entry))
        except InvalidAgentSpec as ex:
            errors.append(f"[{pname}] {rel} {_dlt_reason(ex)}")
            continue

        # A stated name that disagrees with the folder: dlt only falls back when the name
        # is absent, so a mismatch loads fine and then fails to resolve as <toolkit>:<name>.
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
        _validate_defaults(pname, rel, fm, errors, warnings)

    return agent_names


def _validate_agent_body(
    pname: str, rel: str, fm: dict, body: str, errors: list[str], warnings: list[str]
) -> None:
    """The body is the system prompt *and* the task, templated against `inputs`.

    Every placeholder must resolve to something the run will have, or it renders empty
    and the task silently loses a parameter. `run_context.*` is implicit and always
    available. A declared input the body never names reaches no model at all.
    """
    if not body.strip():
        errors.append(f"[{pname}] {rel} has an empty body — the body is the system prompt")
        return

    declared = (fm.get("inputs") or {}).get("properties")
    declared = set(declared) if isinstance(declared, dict) else set()
    used = set(_PLACEHOLDER.findall(body))

    for placeholder in sorted(used):
        root = placeholder.split(".")[0]
        if root == "run_context" or placeholder in declared:
            continue
        errors.append(
            f"[{pname}] {rel} body uses '{{{{ {placeholder} }}}}' which is not declared"
            " in inputs.properties"
        )
    for unused in sorted(declared - {u.split(".")[0] for u in used}):
        warnings.append(
            f"[{pname}] {rel} input '{unused}' is declared but never named in the body,"
            " so nothing will read it"
        )


def _validate_entity_types(
    pname: str, rel: str, fm: dict, errors: list[str], warnings: list[str]
) -> None:
    """Check `entity_type` on input and output properties.

    dlt's `entity_properties` rejects an unknown value, so the vocabulary is never
    restated here. What it does not check is the two ways a *valid* value still misleads:
    a non-string property, and an output that renames the kind of an input.

    Worth catching at all because the damage is invisible at runtime.
    `expose.object_input` is built from the first entity-typed input, so a mistake means
    the web UI cannot offer the agent from the entity's page and the run reports the
    wrong `object` — nothing raises.
    """
    entity_types: dict[str, dict[str, str]] = {}
    for where, schema in (("inputs", fm.get("inputs")), ("output", fm.get("output"))):
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
            f" only the first, '{first}', becomes expose.object_input — reorder if"
            f" {rest[0]!r} is what the UI should offer the agent from"
        )


def _validate_output(
    pname: str, rel: str, fm: dict, errors: list[str], warnings: list[str]
) -> None:
    """Check the standard output props without demanding them.

    dlt's TypedDict is the source of truth: it supplies `status` and `summary` (with
    their descriptions, and in `required`) for any manifest that leaves them out. So an
    omission is a warning naming what will be added.

    A **type conflict** is the exception and fails: if the manifest declares `status`
    with different values, or `summary` as something other than a string, the TypedDict
    would silently overwrite the author's intent. That is the one case the generator
    cannot reconcile, and the likely cause is a domain field wearing a reserved name.
    """
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

    missing = [f for f in _OUTPUT_CONTRACT if not isinstance(props.get(f), dict)]
    if missing:
        warnings.append(
            f"[{pname}] {rel} output does not declare {', '.join(missing)}"
            " — it will be added from the standard TypedDict"
        )

    # type conflicts: the generator cannot reconcile these, so fail rather than overwrite
    status = props.get("status")
    if isinstance(status, dict):
        values = status.get("enum")
        if values is not None and sorted(values) != sorted(_STATUS_VALUES):
            errors.append(
                f"[{pname}] {rel} output.status declares {values} but the contract is"
                f" {_STATUS_VALUES}; give a domain-specific status another name"
                " (e.g. `verdict`)"
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


def _validate_defaults(
    pname: str, rel: str, fm: dict, errors: list[str], warnings: list[str]
) -> None:
    """`defaults` holds everything the runtime may override."""
    node = fm.get("defaults")
    if node is None:
        warnings.append(f"[{pname}] {rel} has no defaults — no trigger, model or limits")
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
    model = node.get("model")
    # a `provider:model` id is passed through; only a bare word claims to be an alias
    if isinstance(model, str) and ":" not in model and model not in AGENT_MODEL_ALIASES:
        errors.append(
            f"[{pname}] {rel} defaults.model {model!r} is not an alias; expected one of"
            f" {', '.join(sorted(AGENT_MODEL_ALIASES))}, or a 'provider:model' id"
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
    skill_names: set[str],
    marketplace_names: set[str],
    errors: list[str],
    warnings: list[str],
) -> None:
    """Validate workflow.md structure, skill refs, and handover refs."""
    workflow_path = plugin_dir / "rules" / "workflow.md"
    if not workflow_path.exists():
        return

    text = workflow_path.read_text()

    # --- skill references (across entire file) ---
    workflow_refs = set(_WORKFLOW_SKILL_REF.findall(text))
    for ref in sorted(workflow_refs):
        if ref not in skill_names:
            errors.append(f"[{pname}] workflow.md references '{ref}' but no skill directory exists")

    # --- section structure ---
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

    # --- handover references must point to real toolkits ---
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


def validate_toolkit_content(
    pname: str,
    plugin_dir: Path,
    marketplace_names: set[str],
    inventory: dict[str, dict],
    errors: list[str],
    warnings: list[str],
) -> set[str]:
    """Validate skills, commands, rules, agents, and workflow. Returns skill names."""
    # --- skills ---
    skills_dir = plugin_dir / "skills"
    skill_names: set[str] = set()
    if skills_dir.is_dir():
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

            # argument-hint: must be quoted and use [bracket] tokens
            hint = fm.get("argument-hint", "")
            if hint:
                # strip surrounding quotes from our simple parser
                hint_val = hint.strip('"').strip("'")
                tokens = hint_val.split()
                bad = [t for t in tokens if not _ARGUMENT_HINT_TOKEN.match(t)]
                if bad:
                    errors.append(
                        f"[{pname}] {skill_dir.name}/SKILL.md "
                        f"argument-hint tokens must use [bracket] convention, "
                        f"got: {' '.join(bad)}"
                    )

            skill_names.add(skill_dir.name)

    # --- commands (must have frontmatter with name and description) ---
    commands_dir = plugin_dir / "commands"
    if commands_dir.is_dir():
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

            # argument-hint: must use [bracket] convention
            hint = fm.get("argument-hint", "")
            if hint:
                hint_val = hint.strip('"').strip("'")
                tokens = hint_val.split()
                bad = [t for t in tokens if not _ARGUMENT_HINT_TOKEN.match(t)]
                if bad:
                    errors.append(
                        f"[{pname}] commands/{cmd_file.name} "
                        f"argument-hint tokens must use [bracket] convention, "
                        f"got: {' '.join(bad)}"
                    )

    # --- rules (must be catch-all, no frontmatter) ---
    rules_dir = plugin_dir / "rules"
    if rules_dir.is_dir():
        for rule_file in sorted(rules_dir.rglob("*.md")):
            rel = rule_file.relative_to(plugin_dir)
            fm = frontmatter_of(rule_file, str(rel), pname, errors)
            if fm:
                errors.append(
                    f"[{pname}] {rel} has frontmatter — rules must be catch-all (no frontmatter)"
                )

    # --- agents (see BACKGROUND_AGENTS.md) ---
    validate_agents(pname, plugin_dir, inventory, errors, warnings)

    # --- workflow.md ---
    validate_workflow(pname, plugin_dir, skill_names, marketplace_names, errors, warnings)

    return skill_names


def validate_index_drift(
    root: Path,
    marketplace_names: set[str],
    errors: list[str],
) -> None:
    """Check every always-loaded intent->toolkit index lists exactly the workflow toolkits.

    The compact index is loaded every session, so it can silently go stale when
    toolkits are added or removed. It is duplicated across the rule and AGENTS.md
    (two always-loaded surfaces, see _INDEX_FILES); enforce that each lists exactly
    the marketplace toolkits minus the non-workflow ones (init, bootstrap).

    NOTE: build-time guard only. It keeps the *shipped* index in sync with
    marketplace.json; it does NOT keep a user's *installed* index fresh against the
    live catalog at runtime. That runtime-freshness gap is tracked in
    dlt-hub/dlthub-ai-workbench-internal#71.
    """
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


def validate(
    root: Path, only: str | None = None
) -> tuple[list[str], list[str], dict[str, set[str]]]:
    errors: list[str] = []
    warnings: list[str] = []

    marketplace_path = root / ".claude-plugin" / "marketplace.json"
    if not marketplace_path.exists():
        errors.append(f"Missing {marketplace_path.relative_to(root)}")
        return errors, warnings, {}

    marketplace = json.loads(marketplace_path.read_text())
    marketplace_names = {e.get("name") for e in marketplace.get("plugins", [])}

    # pre-pass: agent manifests reference components in their dependency toolkits,
    # so the full component map must exist before any single toolkit is validated
    inventory = build_component_inventory(root)

    all_skills: dict[str, set[str]] = {}

    # --- marketplace plugins ---
    for entry in marketplace.get("plugins", []):
        pname = entry.get("name", "<unnamed>")
        source = entry.get("source", "")
        plugin_dir = root / source

        # skip if filtering to a single toolkit
        if only and pname != only:
            continue

        # source must live under ./workbench/
        source_path = Path(source)
        clean = str(source_path).lstrip("./")
        if not clean.startswith("workbench/"):
            errors.append(f"[{pname}] source '{source}' must be under ./workbench/")

        # last path segment must match plugin name
        if Path(source).name != pname:
            errors.append(
                f"[{pname}] source last segment '{Path(source).name}' "
                f"must match plugin name '{pname}'"
            )

        # plugin directory must exist
        if not plugin_dir.is_dir():
            errors.append(f"[{pname}] directory not found: {source}")
            continue

        # --- plugin.json ---
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

            # author must be Scalevector
            author = pjson.get("author", {})
            author_name = author.get("name", "") if isinstance(author, dict) else ""
            if author_name != _EXPECTED_AUTHOR:
                errors.append(
                    f"[{pname}] plugin.json author.name '{author_name}' "
                    f"!= expected '{_EXPECTED_AUTHOR}'"
                )

            # license must point to the repo LICENSE
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

    # --- all workbench/ dirs must be in marketplace (skip in single-toolkit mode) ---
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
