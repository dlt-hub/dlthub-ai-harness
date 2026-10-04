# dltHub AI Harness

A collection of **toolkits** (compatible with Claude Code plugins) for data engineering with [dlthub](https://dlthub.com).

## Structure

```
.claude-plugin/marketplace.json    # Marketplace catalog listing all toolkits
workbench/                                # All toolkits live here
  <toolkit-name>/                  # One directory per toolkit
    .claude-plugin/plugin.json     # Plugin manifest (strict Claude schema, name must match directory)
    .claude-plugin/toolkit.json    # dlthub-specific metadata: dependencies, listed (optional)
    skills/                        # Skills (SKILL.md with frontmatter)
    commands/                      # Slash commands (plain .md files)
    rules/                         # Catch-all rules loaded every session
    agents/<name>/AGENT.md         # Agent definitions (optional)
    .mcp.json                      # MCP servers (optional)
  init/                            # Shared rules, secrets handling, and workspace MCP
tools/                             # Dev tooling
  validate_toolkits.py             # Marketplace & plugin consistency checker
  extract_refs.py                  # Extract component map & external URLs from a toolkit
  create_eval_workspace.py         # Build trigger eval workspaces (see EVALS.md)
  run_trigger_eval.py              # Run trigger evals
  ...
Makefile                           # make validate-toolkits
```



## Toolkit conventions

Every toolkit under `workbench/` must be listed in `marketplace.json`.

A toolkit is a Claude Code plugin. It can contain:

- **Skills** (`skills/<name>/SKILL.md`) — frontmatter required (`name`, `description`). Name must match directory name.
- **Commands** (`commands/<name>.md`) — frontmatter required (`name`, `description`). Name must match filename. User-invoked via `/toolkit:command`.
- **Rules** (`rules/*.md`) — **catch-all only**, no frontmatter allowed. Loaded into every session unconditionally.
- **MCP servers** (`.mcp.json`) — stdio transport, use `${CLAUDE_PLUGIN_ROOT}` for paths.
- **Agents** (`agents/<name>/AGENT.md`) — agent definitions. Frontmatter plus a body that is the system prompt. Name must match the folder. Each declares `access`, `inputs`, `output` (with `status` and `summary`) and `defaults`.
  - The folder holds `AGENT.md`, an optional `agent.py` (`validate_input`, `validate_output`) and the modules it imports. A file shared with another agent definition is a symlink, never an import across folders.
  - No README in the folder. Author and operator docs go in `BACKGROUND_AGENTS.md`, the reference for agent definitions.
  - Install path: `.claude/dlthub/agents/<name>/`, under `dlthub/` so it never mixes with the host's native agents.

### Toolkit Workflow (`rules/workflow.md`)
Each toolkit has a **workflow** rule that shows the order in which the agent uses the skills. It is always loaded so the agent knows the intended skill sequence.

#### Entry skill

Every workflow toolkit MUST have an **entry skill** — the skill where the workflow starts. Declare it in `toolkit.json`:
```json
{"workflow_entry_skill": "find-source"}
```

The entry skill is triggered when:
- The user invokes it explicitly with `/skill-name`
- The user expresses intent matching the skill description (the skill's `description` field decides the match)

The workflow rule must open with a `## Workflow Entry` section referencing this skill. Example from `rest-api-pipeline`:
```markdown
## Workflow Entry
**ALWAYS** start with **Find source** (`find-source`) SKILL — discover the right dlt source for the user's data provider
```

After install, `dlthub ai status` and `dlthub ai toolkit install <name>` display: `Use find-source skill to start!`

#### Required sections

1. **Workflow Entry** — declares which skill MUST run first (see above)
2. **Core workflow** — numbered steps with skill references: `N. **Step name** (`skill-name`) — what it does`
3. **Extend and harden** (optional) — additional steps for production readiness, iteration, or advanced use cases
4. **Handover to other toolkits** — when to leave this toolkit. Each entry names the target toolkit, the condition and the skill that the user leaves

#### Router vs handovers

Two mechanisms route the user between toolkits — they are complementary, not redundant:

- **Router/index** (`dlthub-router` skill + the always-loaded intent index in `init`) handles the case where **no matching toolkit is installed**: match intent, install the toolkit, enter at its entry skill.
- **Handovers** (a toolkit's `workflow.md`) move the user to another toolkit **during a workflow**. They pass on context, for example the pipeline name, dataset and destination ("skip discovery"). They name one skill and one condition (for example, Early vs Later deploy), which the index cannot do.

When a handover names a toolkit that is **not installed**, use the index/router to install it, then follow the handover's entry point + context. When the toolkit is installed, the router does not trigger during a workflow. Its `description` excludes that case.

#### Linking conventions

- **Internal skills/commands** — reference with backtick-parens: `(`skill-name`)`. The validator checks these resolve to real skill directories.
- **Planned skills** (not yet implemented) — plain text, no `()` link. Add them to the workflow to show intent.
- **Handover to external toolkits** — use `**toolkit-name**` (bold) and describe the trigger. Only reference toolkits that are NOT dependencies (dependencies like `init` are always loaded — their skills are local, not handovers).

### Refer to authoritative docs everywhere
Put links to the authoritative docs (for example, the dlt docs) in each skill, command and rule. The agent reads them at run time. We also use them to **refresh a skill when its source doc changes**.

## New Toolkit
All toolkits are Claude plugins. To create a toolkit, use the installed `plugin-dev` plugin. It is an interactive procedure for humans. It finds the marketplace and copies skill templates.

## Validation & Maintenance

### Quick check
Run after any change to skills, rules, commands, or marketplace.json:
```
make validate-toolkits
```
Checks:
- marketplace and `plugin.json` names
- skill frontmatter
- rule format
- command files
- agent files (access, inputs, agent output, refs, no `defaults.model`)
- `workflow.md` references
- root documents (a toolkit file names one only through its URL)
- index coverage (each skill and agent definition is in its `workflow.md`, each agent definition is in the `dlthub-router` index)

### Maintenance skills
- `/rename-component <toolkit:old-name> <new-name>` — rename a skill, command, rule, or agent and update all cross-references within the toolkit.
- `/validate-toolkits <toolkit-path>` — deep-validate a toolkit: check external doc URLs are live, cross-references resolve, and fix what can be fixed.
- `improve-skills` (in `init`) — capture session learnings back into skills. Run at the end of a session.

### Helper scripts
- `uv run python tools/extract_refs.py workbench/<toolkit>` — extract component map and external URLs for a toolkit.
- `uv run python tools/dump_session.py` — dump current session for review.
