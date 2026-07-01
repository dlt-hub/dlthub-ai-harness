# dltHub AI Workbench (lean)

A collection of **toolkits** (compatible with Claude Code plugins) for data engineering with [dlthub](https://dlthub.com).

This is the **lean** workbench: the agent already knows how to use dlt and write pipelines — what it lacks is *direction*. The workbench's job is to provide sequence and orientation, not execution instructions. It covers only OSS dlt (`dlthub.com/docs`); platform features (deploy, transformations, data quality) are out of scope.

## Structure

```
.claude-plugin/marketplace.json    # Marketplace catalog listing all toolkits
workbench/                         # All toolkits + the two always-loaded root files
  SOUL.md                          # Agent identity + guardrails, written as character
  AGENTS.md                        # Routing table: user intent → toolkit → parent skill
  <toolkit-name>/                  # One directory per toolkit
    .claude-plugin/plugin.json     # Plugin manifest (strict Claude schema, name must match directory)
    .claude-plugin/toolkit.json    # dlthub metadata: dependencies, workflow_entry_skill
    skills/<toolkit-name>/SKILL.md # The single parent skill (name matches the toolkit)
tools/                             # Dev tooling
  validate_toolkits.py             # Marketplace & plugin consistency checker
  extract_refs.py                  # Extract component map & external URLs from a toolkit
Makefile                           # make validate-toolkits
```

## The three layers

The lean workbench is exactly three kinds of file. There are **no** rules, commands, sub-skills, or per-toolkit workflow files.

```
SOUL.md          → who the agent is (identity + guardrails as character)   — always loaded
AGENTS.md        → routing table: user intent → parent skill               — always loaded
Parent skills    → one per toolkit: sequence + doc references + done-checks — loaded on match
```

### SOUL.md
The single always-on identity file. Ships with the workbench, same for every project. It defines who the agent is through **character**, not a checklist — operational guardrails (cwd grounding, secrets-as-sacred, sample-before-full-load, prefer dlt built-ins, docs-from-the-source) are written as traits because an agent acting from identity is more consistent than one following rules it might deprioritize under context pressure. It contains no routing logic, no toolkit-specific instructions, and nothing that changes per project.

### AGENTS.md
The routing table, and the agent's first read each session. Its first line points at SOUL.md. It maps user intent → toolkit → parent skill, one row per toolkit, in the format:
```
<intent, in the words a user would type>  → <toolkit>  | <install command>  | <parent skill>
```
Plus a short disambiguation section for overlapping toolkits. Nothing else — no setup steps, no operational detail.

### Parent skills
One per toolkit, named the same as the toolkit (`skills/<toolkit>/SKILL.md`). A parent skill gives *direction* — the sequence, what to read for each step, and what "done" looks like. It never explains *how* to execute; the docs handle that.

A parent skill contains exactly:
1. **Frontmatter** (`name`, `description`) — the description is written as user-intent phrases with **negative triggers** (`DO NOT USE for …`) to disambiguate from adjacent toolkits.
2. **SOUL.md reference** — one line at the top: *"Read SOUL.md before anything else…"*
3. **Before you start** — preconditions; if not met, what to do instead.
4. **Workflow** — ordered steps, each in this shape:
   ```
   ### Step N — <name>
   <one sentence: what the agent does and why>
   → Docs: <specific dlthub.com/docs URL>
   ✓ Done when: <observable, verifiable condition>
   ```
5. **What's next** — what the toolkit produced and where the user can go.

The `✓ Done when` check must be verifiable (a file exists, a run completes without error, the user confirms) — never "when the agent thinks it's done".

## Toolkit conventions

- Every toolkit under `workbench/` must be listed in `marketplace.json`, and `plugin.json.name` must match the toolkit directory name.
- The parent skill's directory and `name` frontmatter must match the toolkit name.
- Declare the entry point in `toolkit.json`: `{"workflow_entry_skill": "<toolkit-name>"}` — for a lean toolkit this is always the parent skill itself. Dependencies are empty (`init` no longer exists; SOUL.md is the shared base).

### Refer to authoritative docs everywhere
Every parent-skill step embeds a link to an authoritative dlt doc (`https://dlthub.com/docs/...`). This is load-bearing: it tells the agent exactly where to learn *how*, **AND automatically refreshes behavior when the upstream doc is updated**. Start from `https://dlthub.com/docs/llms.txt` and link the specific page.

## New toolkit

A lean toolkit is small enough to author by hand: create `workbench/<name>/.claude-plugin/{plugin.json,toolkit.json}` and `skills/<name>/SKILL.md`, add a row to `AGENTS.md`, add the entry to `marketplace.json`, then run `make validate-toolkits`. `plugin-dev` is installed if you prefer a guided flow, but the lean shape rarely needs it.

## Validation & maintenance

### Quick check
Run after any change to a parent skill, `AGENTS.md`, or `marketplace.json`:
```
make validate-toolkits
```
Checks: marketplace ↔ plugin.json name consistency, skill frontmatter, and that the `AGENTS.md` intent index lists exactly the marketplace toolkits.

### Maintenance skills
- `/rename-component <toolkit:old-name> <new-name>` — rename a skill and update all references within the toolkit.
- `/validate-toolkits <toolkit-path>` — deep-validate: check external doc URLs are live and cross-references resolve.

### Helper scripts
- `uv run python tools/extract_refs.py workbench/<toolkit>` — extract component map and external URLs for a toolkit.
