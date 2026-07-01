# dltHub AI Workbench (lean)

A collection of **toolkits** (compatible with Claude Code plugins) for data engineering with [dlthub](https://dlthub.com).

This is the **lean** workbench: the agent already knows how to use dlt and write pipelines — what it lacks is *direction*. The workbench's job is to provide sequence and orientation, not execution instructions. It covers only OSS dlt (`dlthub.com/docs`); platform features (deploy, transformations, data quality) are out of scope.

## Structure

```
.claude-plugin/marketplace.json    # Marketplace catalog listing all toolkits
workbench/                         # All toolkits live here
  init/                            # Shared base toolkit — a dependency of every toolkit
    .claude-plugin/plugin.json     # name: init
    .claude-plugin/toolkit.json    # {"dependencies": []}
    rules/SOUL.md                  # Agent identity + guardrails — installed as an always-on rule
    rules/toolkit-index.md         # Routing table (intent → toolkit → parent skill) — always-on rule
    AGENTS.md                      # Codex always-on surface: SOUL + routing inlined
  <toolkit-name>/                  # One directory per workflow toolkit
    .claude-plugin/plugin.json     # Plugin manifest (strict Claude schema, name must match directory)
    .claude-plugin/toolkit.json    # dlthub metadata: dependencies (["init"]), workflow_entry_skill
    skills/<toolkit-name>/SKILL.md # The single parent skill (name matches the toolkit)
tools/                             # Dev tooling
  validate_toolkits.py             # Marketplace & plugin consistency checker
  extract_refs.py                  # Extract component map & external URLs from a toolkit
Makefile                           # make validate-toolkits
```

## The three layers

The lean workbench is three kinds of content. Two of them — SOUL and the routing index — are **always loaded**, delivered by the `init` base toolkit (see "Delivery" below). The third is the per-toolkit parent skill, loaded on intent match. There are no sub-skills or per-toolkit workflow files.

```
SOUL             → who the agent is (identity + guardrails as character)    — always loaded (via init)
Routing index    → user intent → toolkit → parent skill                     — always loaded (via init)
Parent skills    → one per toolkit: sequence + doc references + done-checks  — loaded on match
```

### SOUL
The agent's identity, shipped as `init/rules/SOUL.md`. Same for every project. It defines who the agent is through **character**, not a checklist — operational guardrails (cwd grounding, secrets-as-sacred, sample-before-full-load, prefer dlt built-ins, docs-from-the-source) are written as traits because an agent acting from identity is more consistent than one following rules it might deprioritize under context pressure. It contains no routing logic, no toolkit-specific instructions, and nothing that changes per project.

### Routing index
The intent→toolkit table, shipped as `init/rules/toolkit-index.md`. It maps user intent → toolkit → parent skill, one row per toolkit, in the format:
```
<intent, in the words a user would type>  → <toolkit>  | <install command>  | <parent skill>
```
Plus a short disambiguation section for overlapping toolkits. Nothing else — no setup steps, no operational detail.

### Delivery — how "always loaded" actually works
SOUL and the routing index are only always-on because the `init` base toolkit installs them onto each agent's always-loaded surface. `init` is a **dependency of every workflow toolkit**, so installing any toolkit pulls it in.
- **Claude / Cursor** — `init/rules/*.md` install as native always-on rules (rules must be catch-all: **no frontmatter**).
- **Codex** — rules become opt-in there, so `init/AGENTS.md` is the always-on surface; it **inlines** both SOUL and the routing index. Keep `AGENTS.md` in sync with the two rule files (the validator checks the routing index matches across both surfaces).

A top-level `SOUL.md`/`AGENTS.md` at the workbench root does **not** ship — it belongs to no plugin, so nothing installs it. Always-on content must live inside `init`.

### Parent skills
One per toolkit, named the same as the toolkit (`skills/<toolkit>/SKILL.md`). A parent skill gives *direction* — the sequence, what to read for each step, and what "done" looks like. It never explains *how* to execute; the docs handle that.

A parent skill contains exactly:
1. **Frontmatter** (`name`, `description`) — the description is written as user-intent phrases with **negative triggers** (`DO NOT USE for …`) to disambiguate from adjacent toolkits.
2. **SOUL reminder** — one line at the top noting the SOUL guardrails are already loaded (via `init`); do not point at a file path, since the parent skill installs separately from `init`.
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
- Declare the entry point in `toolkit.json`: `{"dependencies": ["init"], "workflow_entry_skill": "<toolkit-name>"}` — for a workflow toolkit the entry skill is always the parent skill itself, and `init` is a dependency so SOUL + routing load with it.
- `init` is the base toolkit: `{"dependencies": []}`, no skills, no entry skill. It carries only the always-on rules + `AGENTS.md`.

### Refer to authoritative docs everywhere
Every parent-skill step embeds a link to an authoritative dlt doc (`https://dlthub.com/docs/...`). This is load-bearing: it tells the agent exactly where to learn *how*, **AND automatically refreshes behavior when the upstream doc is updated**. Start from `https://dlthub.com/docs/llms.txt` and link the specific page.

## New toolkit

A lean toolkit is small enough to author by hand: create `workbench/<name>/.claude-plugin/{plugin.json,toolkit.json}` (with `"dependencies": ["init"]`) and `skills/<name>/SKILL.md`, add a row to **both** `init/rules/toolkit-index.md` and `init/AGENTS.md`, add the entry to `marketplace.json`, then run `make validate-toolkits`. `plugin-dev` is installed if you prefer a guided flow, but the lean shape rarely needs it.

## Validation & maintenance

### Quick check
Run after any change to a parent skill, the `init` rules/`AGENTS.md`, or `marketplace.json`:
```
make validate-toolkits
```
Checks: marketplace ↔ plugin.json name consistency, skill frontmatter, rules are frontmatter-free, the intent index lists exactly the workflow toolkits across both always-loaded surfaces (`init/rules/toolkit-index.md` and `init/AGENTS.md`), and that `init/AGENTS.md` inlines every `init/rules/*.md` verbatim so the surfaces can't drift.

### Maintenance skills
- `/rename-component <toolkit:old-name> <new-name>` — rename a skill and update all references within the toolkit.
- `/validate-toolkits <toolkit-path>` — deep-validate: check external doc URLs are live and cross-references resolve.

### Helper scripts
- `uv run python tools/extract_refs.py workbench/<toolkit>` — extract component map and external URLs for a toolkit.
