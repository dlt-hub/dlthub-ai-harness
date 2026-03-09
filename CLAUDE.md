# dltHub AI Workbench

A collection of **toolkits** (compatible with Claude Code plugins) for data engineering with [dlt](https://dlthub.com).

## Structure

```
.claude-plugin/marketplace.json    # Marketplace catalog listing all toolkits
workbench/                                # All toolkits live here
  <toolkit-name>/                  # One directory per toolkit
    .claude-plugin/plugin.json     # Plugin manifest (strict Claude schema, name must match directory)
    .claude-plugin/toolkit.json    # dlt-specific metadata: dependencies, listed (optional)
    skills/                        # Skills (SKILL.md with frontmatter)
    commands/                      # Slash commands (plain .md files)
    rules/                         # Catch-all rules loaded every session
    .mcp.json                      # MCP servers (optional)
  init/                            # Shared rules, secrets handling, and workspace MCP
tools/                             # Dev tooling
  validate_toolkits.py              # Marketplace & plugin consistency checker
  extract_refs.py                  # Extract component map & external URLs from a toolkit
Makefile                           # make validate-toolkits
```

## Toolkit conventions

Every toolkit under `workbench/` must be listed in `marketplace.json`.

A toolkit is a Claude Code plugin. It may contain:

- **Skills** (`skills/<name>/SKILL.md`) — frontmatter required (`name`, `description`). Name must match directory name.
- **Commands** (`commands/<name>.md`) — frontmatter required (`name`, `description`). Name must match filename. User-invoked via `/toolkit:command`.
- **Rules** (`rules/*.md`) — **catch-all only**, no frontmatter allowed. Loaded into every session unconditionally.
- **MCP servers** (`.mcp.json`) — stdio transport, use `${CLAUDE_PLUGIN_ROOT}` for paths.

### Toolkit Workflow (`rules/workflow.md`)
Each toolkit has a **workflow** rule that shows how skills should be used together. It is always loaded so the agent knows the intended skill sequence.

#### Entry skill

Every workflow toolkit MUST have an **entry skill** — the skill where the workflow starts. Declare it in `toolkit.json`:
```json
{"workflow_entry_skill": "find-source"}
```

The entry skill is triggered when:
- The user invokes it explicitly with `/skill-name`
- The user expresses intent matching the skill description (low-intent trigger — the skill's `description` frontmatter field drives matching)

The workflow rule must open with a `## Workflow Entry` section referencing this skill. Example from `rest-api-pipeline`:
```markdown
## Workflow Entry
**ALWAYS** start with **Find source** (`find-source`) SKILL — discover the right dlt source for the user's data provider
```

After install, `dlt ai status` and `dlt ai toolkit <name> install` display: `Use find-source skill to start!`

#### Required sections

1. **Workflow Entry** — declares which skill MUST run first (see above)
2. **Core workflow** — numbered steps with skill references: `N. **Step name** (`skill-name`) — what it does`
3. **Extend and harden** (optional) — additional steps for production readiness, iteration, or advanced use cases
4. **Handover to other toolkits** — when to leave this toolkit. Each entry names the target toolkit, the trigger condition, and which local skill the user was in when the handover applies

#### Linking conventions

- **Internal skills/commands** — reference with backtick-parens: `(`skill-name`)`. The validator checks these resolve to real skill directories.
- **Planned skills** (not yet implemented) — plain text, no `()` link. Add them to the workflow to show intent.
- **Handover to external toolkits** — use `**toolkit-name**` (bold) and describe the trigger. Only reference toolkits that are NOT dependencies (dependencies like `init` are always loaded — their skills are local, not handovers).

### Refer to authoritative docs everywhere
Embed links to authoritative docs (ie. dlt docs) in skills/commands/rules you write. They are useful when skill is used **AND TO AUTOMATICALLY REFRESH SKILLS IF AUTH SOURCE IS UPDATED**.

## New Toolkit
We have `plugin-dev` installed and since all toolkits are also Claude plugins use it to create new plugin. This is interactive
procedure for humans - it will correctly guess marketplace location, duplicate skills etc.

## Validation & Maintenance

### Quick check
Run after any change to skills, rules, commands, or marketplace.json:
```
make validate-toolkits
```
Checks: marketplace ↔ plugin.json name consistency, skill frontmatter, rule format, command files, workflow.md references.

### Maintenance skills
- `/rename-component <toolkit:old-name> <new-name>` — rename a skill, command, or rule and update all cross-references within the toolkit.
- `/validate-toolkits <toolkit-path>` — deep-validate a toolkit: check external doc URLs are live, cross-references resolve, and fix what can be fixed.
- `improve-skills` (per-toolkit, in rest-api-pipeline) — capture session learnings back into skills. Run at the end of a session.

### Helper scripts
- `uv run python tools/extract_refs.py workbench/<toolkit>` — extract component map and external URLs for a toolkit.
- `uv run python tools/dump_session.py` — dump current session for review.
