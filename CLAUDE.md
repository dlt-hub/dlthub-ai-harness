# dltHub AI Workbench

A collection of **toolkits** (compatible with Claude Code plugins) for data engineering with [dlt](https://dlthub.com).

## Structure

```
.claude-plugin/marketplace.json    # Marketplace catalog listing all toolkits
workbench/                                # All toolkits live here
  <toolkit-name>/                  # One directory per toolkit
    .claude-plugin/plugin.json     # Plugin manifest (name must match directory)
    skills/                        # Skills (SKILL.md with frontmatter)
    commands/                      # Slash commands (plain .md files)
    rules/                         # Catch-all rules loaded every session
    .mcp.json                      # MCP servers (optional)
  _init/                           # Special toolkit: shared rules/skills, NOT in marketplace
tools/                             # Dev tooling
  validate_plugins.py              # Marketplace & plugin consistency checker
  extract_refs.py                  # Extract component map & external URLs from a toolkit
Makefile                           # make validate-plugins
```

## Toolkit conventions

Every toolkit under `workbench/` must be listed in `marketplace.json` — except `_init`, which is a special toolkit for shared rules and skills that is not distributed via the marketplace. `_init` follows the same structure and validation rules as any other toolkit but has no `.claude-plugin/plugin.json`.

A toolkit is a Claude Code plugin. It may contain:

- **Skills** (`skills/<name>/SKILL.md`) — frontmatter required (`name`, `description`). Name must match directory name.
- **Commands** (`commands/<name>.md`) — frontmatter required (`name`, `description`). Name must match filename. User-invoked via `/toolkit:command`.
- **Rules** (`rules/*.md`) — **catch-all only**, no frontmatter allowed. Loaded into every session unconditionally.
- **MCP servers** (`.mcp.json`) — stdio transport, use `${CLAUDE_PLUGIN_ROOT}` for paths.

### Toolkit Workflow
Each toolkit has a **workflow** rule that shows how skills should be used together.

### Refer to authoritative docs everywhere
Embed links to authoritative docs (ie. dlt docs) in skills/commands/rules you write. They are useful when skill is used **AND TO AUTOMATICALLY REFRESH SKILLS IF AUTH SOURCE IS UPDATED**.

## New Toolkit
We have `plugin-dev` installed and since all toolkits are also Claude plugins use it to create new plugin. This is interactive
procedure for humans - it will correctly guess marketplace location, duplicate skills etc.

## Validation & Maintenance

### Quick check
Run after any change to skills, rules, commands, or marketplace.json:
```
make validate-plugins
```
Checks: marketplace ↔ plugin.json name consistency, skill frontmatter, rule format, command files, workflow.md references.

### Maintenance skills
- `/rename-component <toolkit:old-name> <new-name>` — rename a skill, command, or rule and update all cross-references within the toolkit.
- `/validate-toolkits <toolkit-path>` — deep-validate a toolkit: check external doc URLs are live, cross-references resolve, and fix what can be fixed.
- `improve-skills` (per-toolkit, in rest-api-pipeline) — capture session learnings back into skills. Run at the end of a session.

### Helper scripts
- `uv run python tools/extract_refs.py workbench/<toolkit>` — extract component map and external URLs for a toolkit.
- `uv run python tools/dump_session.py` — dump current session for review.
