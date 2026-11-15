# dltHub AI Harness

A collection of **toolkits** (compatible with Claude Code plugins) for data engineering with [dlthub](https://dlthub.com).

## Structure

```
.claude-plugin/marketplace.json    # Marketplace catalog listing all toolkits
workbench/                                # All toolkits live here
  <toolkit-name>/                  # One directory per toolkit
    .claude-plugin/plugin.json     # Plugin manifest (strict Claude schema, name must match directory)
    .claude-plugin/toolkit.json    # dlthub-specific metadata: dependencies, listed, agents, mcp_features (optional)
    skills/                        # Skills (SKILL.md with frontmatter)
    commands/                      # Slash commands (plain .md files)
    rules/                         # Catch-all rules loaded every session
    dlthub/agents/<name>/AGENT.md  # Agent definitions (optional)
    .mcp.json                      # MCP servers (optional)
  init/                            # Shared rules, workspace and profiles, secrets handling, and workspace MCP
  local-workspace/                 # Jobs, deployments and local debug runs: adds to the init rules (unlisted, no workflow)
  *-platform/                      # Platform toolkits: deploy and run on one platform (see TOOLKITS.md)
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
- **Agents** (`dlthub/agents/<name>/AGENT.md`) — agent definitions. Frontmatter plus a body that is the system prompt. Name must match the folder. Each declares `access`, `inputs`, `output` (with `status` and `summary`) and `defaults`.
  - `agents/` is the host's own subagents folder; dlt does not install an agent definition from there.
  - The folder holds `AGENT.md`, an optional `agent.py` (`validate_input`, `validate_output`) and the modules it imports. An agent folder imports only its own files.
  - No README in the folder: a document beside a definition drifts from it. What an author or an operator needs is in `create-background-agent`, a skill under `workbench/dlthub-platform/skills/` (background agents run on the dltHub platform).
  - Install path: `.claude/dlthub/agents/<toolkit>/<name>/` on dlt 1.31.0, under `dlthub/` so it never mixes with the host's native agents. dlt 1.30.1a1 wrote it flat, without the `<toolkit>` segment.

### Rules hold only what a skill cannot
Rules are loaded on every turn. A rule **never repeats the procedure of a skill**: no skill steps, commands, checklists, reference detail, or intent → skill tables that restate skill descriptions. It keeps what the agent needs before any skill is open (vocabulary, principles, safety lines, the workflow), with a one-line pointer to the skill for the rest.

- **Not just deduplication.** A rule may repeat a principle that a skill also applies, when the agent needs it before the skill is open or across several skills ("tests never run on a remote profile", "prefer built-in checks"). A rule also shows how the skills form a workflow: their order, the branches between them and what each step is for, even when the skills say it too.
- **Rules are composable.** Every installed toolkit adds its own rules, so a rule never carries upfront information that another toolkit adds when it is installed. The `init` rule does not describe platform toolkits, their folders or their commands: each platform toolkit's rule says that it is the platform toolkit, what it owns in `.dlthub/` and how commands written without a prefix map to its CLI. A location only one toolkit uses is named in that toolkit's rule.
- **Rules say how to use toolkits, not how to write them.** Authoring conventions (artifact locations for new kinds, agnostic wording, handover rules) live here and in TOOLKITS.md, and in the validator where they can be checked.

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
4. **Handover to other toolkits** (optional) — `### Incoming` and `### Outgoing` bullets, only for the situations described below

#### Router vs handovers

Two mechanisms route the user between toolkits — they are complementary, not redundant:

- **Router/index** (the `dlthub-router` skill in `init`, which holds the toolkit index) handles the case where **no matching toolkit is installed**, and every plain change of goal ("now I want charts"): match intent, install the toolkit, enter at its entry skill. Platform toolkits share one index row, "→ a platform toolkit".
- **Handovers** (a toolkit's `workflow.md`) get a bullet **only where parts of the session context are expected by the next toolkit and matter**: what is carried, and what to do or skip because of it ("the failing tables are known: focus on them", "a playground workspace is already connected: skip Step 0", "do not restructure the inline `rest_api_source`"). That context deserves its place in the rule.
- **Everything else is not a handover bullet.** A generic arrival ("the pipeline and tables are already known, skip discovery") is one "Handed over from another toolkit or skill?" paragraph in the entry skill of the receiving toolkit. A handover that a skill already states (a skill's "Next steps") stays only in the skill.

When a handover names a toolkit that is **not installed**, use the index/router to install it, then follow the handover's entry point + context. When the toolkit is installed, the router does not trigger during a workflow. Its `description` excludes that case.

#### Linking conventions

- **Internal skills/commands** — reference with backtick-parens: `(`skill-name`)`. The validator checks these resolve to real skill directories.
- **Planned skills** (not yet implemented) — plain text, no `()` link. Add them to the workflow to show intent.
- **Handover to external toolkits** — use `**toolkit-name**` (bold) and describe the trigger. Only reference toolkits that are NOT dependencies (dependencies like `init` are always loaded — their skills are local, not handovers). The validator accepts `(`skill-name`)` refs to skills of dependencies.
- **Handover to a platform toolkit** — a toolkit that is not a platform toolkit never names one. An installed platform toolkit's own rule takes deploy intents, and `dlthub-router` installs one when none is, so a workflow lists no platform handover; a skill's "Next steps" says "follow the workflow entry of the installed platform toolkit". See "Platform toolkits" in TOOLKITS.md.

### Artifact locations and code paths
Skills write artifacts only to the artifact locations (`.dlthub/schemas/`, `.dlthub/ontology/<name>/`, `.dlthub/explorations/<name>/`, `.dlthub/<platform>/`) and name the path. Code layout is the user's: a concrete path for sources, pipelines or transformations is an example. Throwaway scripts go to the system temp dir. See "Artifact locations" in TOOLKITS.md.

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
- index coverage (each skill and agent definition is in its `workflow.md`; the `dlthub-router` index lists every listed workflow toolkit that is not a platform toolkit, plus the platform toolkit row)
- artifact locations (only the standard `.dlthub/` folders, a platform folder only in its own toolkit, no retired paths)
- platform toolkits (the `Platform toolkit` label in both descriptions, `Requires <platform> Platform` for a toolkit that works only with one platform; no other toolkit depends on one, names one or its skills, names the dltHub platform, runs platform commands or installs `dlt[hub]`)

### Maintenance skills
- `/rename-component <toolkit:old-name> <new-name>` — rename a skill, command, rule, or agent and update all cross-references within the toolkit.
- `/validate-toolkits <toolkit-path>` — deep-validate a toolkit: check external doc URLs are live, cross-references resolve, and fix what can be fixed.

### Helper scripts
- `uv run python tools/extract_refs.py workbench/<toolkit>` — extract component map and external URLs for a toolkit.
- `uv run python tools/dump_session.py` — dump current session for review.
