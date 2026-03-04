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
- workflow.md (`skill-name`) references point to real skill directories
- workflow.md has required sections (Core workflow, Handover to other toolkits)
- workflow.md handover references point to real toolkits in marketplace
- All workbench/ directories must be listed in marketplace
"""

import json
import re
import sys
from pathlib import Path

AI_DIR = "workbench"

# Expected plugin.json author and license values
_EXPECTED_AUTHOR = "dltHub, Inc."
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


def parse_frontmatter(path: Path) -> dict:
    """Extract YAML-like frontmatter from a markdown file."""
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not match:
        return {}
    fm = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fm[key.strip()] = value.strip()
    return fm


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
    errors: list[str],
    warnings: list[str],
) -> set[str]:
    """Validate skills, commands, rules, and workflow. Returns skill names."""
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

    # --- rules (must be catch-all, no frontmatter) ---
    rules_dir = plugin_dir / "rules"
    if rules_dir.is_dir():
        for rule_file in sorted(rules_dir.rglob("*.md")):
            fm = parse_frontmatter(rule_file)
            if fm:
                rel = rule_file.relative_to(plugin_dir)
                errors.append(
                    f"[{pname}] {rel} has frontmatter — rules must be catch-all (no frontmatter)"
                )

    # --- workflow.md ---
    validate_workflow(pname, plugin_dir, skill_names, marketplace_names, errors, warnings)

    return skill_names


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

            # author must be {"name": "dltHub, Inc."}
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
            pname, plugin_dir, marketplace_names, errors, warnings
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
