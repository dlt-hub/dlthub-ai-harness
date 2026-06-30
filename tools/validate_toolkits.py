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
- The only rule is init/rules/intent-index.md (cold-start index); no other rules/ exist
- Every workflow toolkit has a parent skill skills/<toolkit>/SKILL.md (the router)
- Parent skill description carries a 'DO NOT USE' negative trigger
- Every sub-skill has '## Before you start' and '## What's next' blocks
- The intent index (intent-index.md + AGENTS.md) lists exactly the workflow toolkits
- All workbench/ directories must be listed in marketplace
"""

import json
import re
import sys
from pathlib import Path

AI_DIR = "workbench"

# The always-loaded compact intent->toolkit index is duplicated across two
# always-loaded surfaces: the rule (native on Claude/Cursor) and AGENTS.md
# (the only always-loaded surface on Codex, where rules become opt-in skills).
# Both must list the same workflow toolkits.
_INDEX_FILES = (
    "workbench/init/rules/intent-index.md",
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

def parse_frontmatter(path: Path) -> dict:
    """Extract YAML-like frontmatter from a markdown file.

    Folds multi-line (indented continuation) values into the preceding key, so a
    `description:` wrapped across several lines is read in full rather than truncated
    at its first line.
    """
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not match:
        return {}
    fm: dict[str, str] = {}
    current_key: str | None = None
    for line in match.group(1).splitlines():
        # A top-level key starts at column 0 as `key:` (optionally with a value).
        key_match = re.match(r"^([A-Za-z][\w-]*):\s?(.*)$", line)
        if key_match:
            current_key = key_match.group(1).strip()
            fm[current_key] = key_match.group(2).strip()
        elif current_key is not None and line.strip():
            # Indented continuation of a folded scalar value.
            fm[current_key] = f"{fm[current_key]} {line.strip()}".strip()
    return fm


# A sub-skill must carry an explicit start block and end block so it reads
# standalone. Headings matched case-insensitively against the lowercased file.
_SUBSKILL_REQUIRED = ("## before you start", "## what's next")


def validate_parent_skill(
    pname: str,
    plugin_dir: Path,
    errors: list[str],
    warnings: list[str],
) -> None:
    """The parent skill is skills/<toolkit>/SKILL.md. It routes (does not execute)
    and must carry a 'DO NOT USE' negative trigger in its description. Toolkits
    without a parent skill (e.g. init, bootstrap) are not workflow toolkits and are
    skipped here; the "every workflow toolkit has a parent skill" invariant is
    enforced separately in validate_index_drift."""
    parent_md = plugin_dir / "skills" / pname / "SKILL.md"
    if not parent_md.exists():
        return
    fm = parse_frontmatter(parent_md)
    if "do not use" not in fm.get("description", "").lower():
        errors.append(
            f"[{pname}] parent skill description missing a 'DO NOT USE' negative trigger"
        )


def validate_subskill_blocks(
    pname: str,
    plugin_dir: Path,
    errors: list[str],
) -> None:
    """Every sub-skill (a skill dir whose name != toolkit name) needs a start block
    and an end block. Only enforced once the toolkit is converted (parent exists)."""
    skills_dir = plugin_dir / "skills"
    if not skills_dir.is_dir():
        return
    if not (skills_dir / pname / "SKILL.md").exists():
        return  # not converted yet
    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name == pname:
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        text = skill_md.read_text(encoding="utf-8").lower()
        for needed in _SUBSKILL_REQUIRED:
            if needed not in text:
                errors.append(
                    f"[{pname}] {skill_dir.name}/SKILL.md missing section '{needed}'"
                )


def validate_toolkit_content(
    pname: str,
    plugin_dir: Path,
    errors: list[str],
    warnings: list[str],
) -> set[str]:
    """Validate skills, commands, rules, and the parent skill. Returns skill names."""
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

            fm = parse_frontmatter(skill_md)
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

            fm = parse_frontmatter(cmd_file)
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

    # --- rules: the only allowed rule is init/rules/intent-index.md (the cold-start
    # index). Every other toolkit must have no rules/ directory; orchestration now
    # lives in the parent skill, not a workflow rule. Any rule still present must be
    # catch-all (no frontmatter). ---
    rules_dir = plugin_dir / "rules"
    if rules_dir.is_dir():
        for rule_file in sorted(rules_dir.rglob("*.md")):
            rel = rule_file.relative_to(plugin_dir)
            allowed = pname == "init" and rel.as_posix() == "rules/intent-index.md"
            if not allowed:
                errors.append(
                    f"[{pname}] {rel} is not allowed — the only rule is "
                    f"init/rules/intent-index.md; orchestration belongs in the parent skill"
                )
            if parse_frontmatter(rule_file):
                errors.append(
                    f"[{pname}] {rel} has frontmatter — rules must be catch-all (no frontmatter)"
                )

    # --- parent skill + sub-skill start/end blocks (the skill-centric model) ---
    validate_parent_skill(pname, plugin_dir, errors, warnings)
    validate_subskill_blocks(pname, plugin_dir, errors)

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

    # Every workflow toolkit must own a parent skill at skills/<name>/SKILL.md
    # (the router that replaced its workflow.md).
    for name in sorted(expected):
        if not (root / "workbench" / name / "skills" / name / "SKILL.md").exists():
            errors.append(
                f"[{name}] workflow toolkit has no parent skill skills/{name}/SKILL.md"
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

        all_skills[pname] = validate_toolkit_content(pname, plugin_dir, errors, warnings)

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
