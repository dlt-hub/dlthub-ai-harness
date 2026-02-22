#!/usr/bin/env python3
"""Validate Claude Code plugin marketplace and verify plugin consistency.

Checks:
- marketplace.json structure
- Each plugin source points to a directory under ./workbench/ with last segment matching plugin name
- plugin.json exists and name matches marketplace entry
- Skills have valid SKILL.md with frontmatter (name, description)
- Skill frontmatter name matches directory name
- Commands have valid frontmatter (name, description), name matches filename
- Rules are catch-all (no frontmatter allowed)
- workflow.md (`skill-name`) references point to real skill directories
- All workbench/ directories (except _init) must be listed in marketplace
- _init toolkit is validated structurally but exempt from marketplace
"""

import json
import re
import sys
from pathlib import Path

AI_DIR = "workbench"
INIT_TOOLKIT = "_init"  # special toolkit: validated but not in marketplace


def parse_frontmatter(path: Path) -> dict:
    """Extract YAML-like frontmatter from a markdown file."""
    text = path.read_text()
    match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not match:
        return {}
    fm = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            fm[key.strip()] = value.strip()
    return fm


def validate_toolkit_content(
    pname: str, plugin_dir: Path, errors: list[str], warnings: list[str]
) -> set[str]:
    """Validate skills, commands, rules, and workflow refs. Returns skill names."""
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
                errors.append(
                    f"[{pname}] {skill_dir.name}/SKILL.md "
                    f"missing 'name' in frontmatter"
                )
            elif fm_name != skill_dir.name:
                errors.append(
                    f"[{pname}] {skill_dir.name}/SKILL.md "
                    f"frontmatter name '{fm_name}' != directory '{skill_dir.name}'"
                )

            if not fm_desc:
                warnings.append(
                    f"[{pname}] {skill_dir.name}/SKILL.md "
                    f"missing 'description' in frontmatter"
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
                errors.append(
                    f"[{pname}] commands/{cmd_file.name} "
                    f"missing 'name' in frontmatter"
                )
            elif fm_name != cmd_file.stem:
                errors.append(
                    f"[{pname}] commands/{cmd_file.name} "
                    f"frontmatter name '{fm_name}' != filename '{cmd_file.stem}'"
                )

            if not fm_desc:
                errors.append(
                    f"[{pname}] commands/{cmd_file.name} "
                    f"missing 'description' in frontmatter"
                )

    # --- rules (must be catch-all, no frontmatter) ---
    rules_dir = plugin_dir / "rules"
    if rules_dir.is_dir():
        for rule_file in sorted(rules_dir.rglob("*.md")):
            fm = parse_frontmatter(rule_file)
            if fm:
                rel = rule_file.relative_to(plugin_dir)
                errors.append(
                    f"[{pname}] {rel} has frontmatter — "
                    f"rules must be catch-all (no frontmatter)"
                )

    # --- workflow.md references ---
    workflow_path = plugin_dir / "rules" / "workflow.md"
    if workflow_path.exists():
        text = workflow_path.read_text()
        workflow_refs = set(re.findall(r"\(`([a-z][\w-]*)`\)", text))
        for ref in sorted(workflow_refs):
            if ref not in skill_names:
                errors.append(
                    f"[{pname}] workflow.md references '{ref}' "
                    f"but no skill directory exists"
                )

    return skill_names


def validate(root: Path) -> tuple[list[str], list[str], dict[str, set[str]]]:
    errors: list[str] = []
    warnings: list[str] = []

    marketplace_path = root / ".claude-plugin" / "marketplace.json"
    if not marketplace_path.exists():
        errors.append(f"Missing {marketplace_path.relative_to(root)}")
        return errors, warnings, {}

    marketplace = json.loads(marketplace_path.read_text())

    all_skills: dict[str, set[str]] = {}

    # --- marketplace plugins ---
    for entry in marketplace.get("plugins", []):
        pname = entry.get("name", "<unnamed>")
        source = entry.get("source", "")
        plugin_dir = root / source

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

        all_skills[pname] = validate_toolkit_content(pname, plugin_dir, errors, warnings)

    # --- _init toolkit (same validation, no marketplace/plugin.json required) ---
    init_dir = root / AI_DIR / INIT_TOOLKIT
    if init_dir.is_dir():
        all_skills[INIT_TOOLKIT] = validate_toolkit_content(
            INIT_TOOLKIT, init_dir, errors, warnings
        )

    # --- all workbench/ dirs (except _init) must be in marketplace ---
    marketplace_names = {e.get("name") for e in marketplace.get("plugins", [])}
    ai_dir = root / AI_DIR
    if ai_dir.is_dir():
        for d in sorted(ai_dir.iterdir()):
            if not d.is_dir() or d.name.startswith("."):
                continue
            if d.name == INIT_TOOLKIT:
                continue
            if d.name not in marketplace_names:
                errors.append(
                    f"[{d.name}] directory exists in {AI_DIR}/ "
                    f"but is not listed in marketplace.json"
                )

    return errors, warnings, all_skills


def main():
    root = Path(__file__).resolve().parent.parent
    print(f"Validating plugins in {root}\n")

    errors, warnings, all_skills = validate(root)

    for w in warnings:
        print(f"  WARN  {w}")
    if errors:
        for e in errors:
            print(f"  ERROR {e}")
    else:
        print("  All checks passed.")

    print()
    for pname, skills in sorted(all_skills.items()):
        if pname == INIT_TOOLKIT:
            print(f"  [{pname}] init toolkit (not in marketplace)")
        elif skills:
            print(f"  [{pname}] {len(skills)} skills: {', '.join(sorted(skills))}")
        else:
            print(f"  [{pname}] no skills (commands only)")

    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
