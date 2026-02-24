---
name: rename-component
description: Rename a skill, command, or rule within a toolkit and update all references. Use when the user wants to rename a plugin component.
argument-hint: <toolkit:old-name> <new-name>
---

# Rename toolkit component

Rename a skill, command, or rule and update all cross-references within the toolkit.

Parse `$ARGUMENTS`:
- `toolkit:old-name` (required): toolkit and component to rename (e.g. `rest-api-pipeline:debug-pipeline`)
- `new-name` (required): the new name (e.g. `troubleshoot-pipeline`)

## 1. Identify the component

Run `uv run python tools/extract_refs.py workbench/<toolkit>` to get the component map.

Determine what `old-name` is:
- **Skill**: exists in `components.skills` → directory at `workbench/<toolkit>/skills/<old-name>/`
- **Command**: exists in `components.commands` → file at `workbench/<toolkit>/commands/<old-name>.md`
- **Rule**: exists in `components.rules` → file at `workbench/<toolkit>/rules/<old-name>.md`

If `old-name` doesn't match any component, ERROR and stop.

## 2. Rename the file/directory

- **Skill**: rename directory `skills/<old-name>/` → `skills/<new-name>/`, then update `name:` in SKILL.md frontmatter
- **Command**: rename file `commands/<old-name>.md` → `commands/<new-name>.md`
- **Rule**: rename file `rules/<old-name>.md` → `rules/<new-name>.md`

## 3. Update cross-references within the toolkit

Read every .md file in the toolkit and replace references to `old-name` with `new-name`. References appear in many forms — not just backticks:
- backtick: `` `old-name` ``
- bold: `**old-name**`
- parenthetical: `(old-name)`
- prose: "use old-name to ...", "continue with old-name"
- workflow.md step references: `(`old-name`)`

Use the Edit tool with `replace_all: true` for each file that contains the old name. Be careful not to replace partial matches (e.g. don't rename "add-endpoint" when renaming "endpoint").

## 4. Update plugin definitions

If the component is a skill or command referenced in:
- **workflow.md**: update step names and cross-references section
- **marketplace.json**: update description if it mentions the old name
- **plugin.json**: update description if it mentions the old name

## 5. Validate

Run `make validate-toolkits` to confirm everything is consistent after the rename.

## 6. Report

```
Renamed: <toolkit>:<old-name> → <toolkit>:<new-name>
Type: skill | command | rule
Files updated: N
  - <list of files that were modified>
Validation: passed | failed
```
