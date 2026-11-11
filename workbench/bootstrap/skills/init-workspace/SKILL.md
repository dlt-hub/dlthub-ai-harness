---
name: init-workspace
description: "Set up dlthub in this project and install the toolkit for the user's task. Use when dlthub is not set up yet (the `setup-secrets` skill of the `init` toolkit is not available) and the user wants to build anything with dlt or dlthub: 'set up dlthub', 'init workspace', 'load data from Stripe', 'build a REST API pipeline', 'ingest from Postgres', 'load CSVs from S3', 'transform my data', 'deploy a pipeline', 'what can I build with dlthub'. Installs uv, dlt[hub] and the init toolkit, then the matching workflow toolkit, with the dlthub CLI. Do NOT use when the `setup-secrets` skill is available: dlthub is set up, use `dlthub-router` or the entry skill of the toolkit. Do NOT use when the user asks to be onboarded or to learn dlthub: point them to `uvx dlthub-start@latest`."
---

# Set up dlthub and install a toolkit

Set up dlthub in the current project, then install the toolkit that the user needs.
Use the `dlthub` CLI for every install, so that each toolkit has only one copy.

Docs:
- dltHub AI workflow: https://dlthub.com/docs/dlt-ecosystem/llm-tooling/llm-native-workflow
- `dlthub-init`: https://pypi.org/project/dlthub-init/
- uv install: https://docs.astral.sh/uv/getting-started/installation/

> **Onboarding exception.** If the user asks to be onboarded, or to learn how to use dltHub, do not run this skill.
> Ask the user to run `uvx dlthub-start@latest` in their own terminal. It creates a separate **playground** workspace.
> Never run `uvx dlthub-start` yourself, and do not use `!` mode for it. It needs interactive authentication.

## Step 1: Check what is installed

Run these checks in order. Do not install or change anything yet.

1. Check that the `setup-secrets` skill is available. If it is, the `init` toolkit is installed.
   - Stop this skill. Use `dlthub-router` or the entry skill of the matching toolkit.
2. Run `uv --version`. If it fails, `uv` is missing.
3. Run `uv run dlthub --version`. If it fails, `dlt[hub]` is missing.
4. Run `uv run dlthub ai status`. It shows the workspace and the installed toolkits.

## Step 2: Find the toolkit for the task

Skip this step if the user only asked to set up dlthub.

Match the user's task to one row of this index. Note the toolkit and its entry skill.

```
intent                                                  → toolkit                | install                                                            | entry skill
ingest from REST / HTTP APIs — production-grade pipeline → rest-api-pipeline     | dlthub --non-interactive ai toolkit install rest-api-pipeline      | find-source
ingest from SQL databases (Postgres, MySQL, Snowflake…) → sql-database-pipeline  | dlthub --non-interactive ai toolkit install sql-database-pipeline  | find-sql-database-source
load files (CSV/Parquet/JSONL) from disk/S3/GCS/Azure/SFTP → filesystem-pipeline | dlthub --non-interactive ai toolkit install filesystem-pipeline    | create-filesystem-pipeline
explore & profile loaded data, build charts & dashboards → data-exploration      | dlthub --non-interactive ai toolkit install data-exploration       | explore-data
transform & model loaded data (dimensional / Kimball)   → transformations        | dlthub --non-interactive ai toolkit install transformations        | annotate-sources
add data quality checks (column expectations, validation rules) → data-quality   | dlthub --non-interactive ai toolkit install data-quality           | setup-data-quality
deploy / schedule pipelines on the dltHub platform      → dlthub-platform        | dlthub --non-interactive ai toolkit install dlthub-platform        | setup-runtime
a deployed job failed: read its logs and find the cause → dlthub-platform        | dlthub --non-interactive ai toolkit install dlthub-platform        | debug-deployment
guided end-to-end tour, ingest to dashboard (uses the real toolkits) → quick-start | dlthub --non-interactive ai toolkit install quick-start          | quick-start
test/try dlthub end-to-end — minimal pipeline + educational test deploy, NOT production → one-shot       | dlthub --non-interactive ai toolkit install one-shot               | deploy-run-sample-pipeline
build and deploy a minimal custom REST API pipeline after uvx dlthub-init setup → dlthub-init-skills | dlthub --non-interactive ai toolkit install dlthub-init-skills     | deploy-minimal-ingestion-pipeline
optimize / speed up a slow or memory-heavy pipeline — parallelism, workers, batching → performance | dlthub --non-interactive ai toolkit install performance            | optimize-performance
```

If no row matches, run `uv run dlthub --non-interactive ai toolkit list` after Step 4, and pick the best match.

## Step 3: Show the plan

Show the user what is missing and what you will run:

```
dlthub setup:
  uv:        ✓ installed (x.y.z) / ✗ missing
  dlt[hub]:  ✓ installed (x.y.z) / ✗ missing
  init:      ✓ installed / ✗ missing
  toolkit:   <toolkit> (for: <task>)

Actions:
  1. Install uv                              (if missing)
  2. uvx dlthub-init@latest                  (if dlt[hub] or init is missing)
  3. dlthub ai toolkit install <toolkit>     (if a toolkit is needed)
```

Ask the user to approve the plan. If the user refuses, stop.

## Step 4: Install

Run only the actions that the user approved.

**1. Install uv** (if missing):
- On macOS and Linux, run `curl -LsSf https://astral.sh/uv/install.sh | sh`.
- On Windows, run `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`.
- If `uv` is still not found, tell the user to open a new shell, because the install changes `PATH`.

**2. Install dlt[hub], the workspace and init:**

```
uvx dlthub-init@latest
```

- It sets up the current folder in place, pins `dlt[hub]`, runs `uv sync` and runs `dlthub ai init`.
- `dlthub ai init` installs the `init` toolkit for the coding assistant it detects.
- If it detects more than one coding assistant, run `uv run dlthub --non-interactive ai init --agent <agent>` (`claude`, `cursor` or `codex`).
- Fallback, if `dlthub-init` is not available or fails:
  1. Run `uvx --from "dlt[hub]" dlthub init`.
  2. Run `uv run dlthub --non-interactive ai init`.

**3. Install the toolkit:**

```
uv run dlthub --non-interactive ai toolkit install <toolkit>
```

- The CLI also installs the toolkits that this toolkit needs.
- The output shows the entry skill of the toolkit, for example `Use find-source skill to start!`.

Then run `uv run dlthub ai status`. If it shows a WARNING about the MCP server, fix it before you continue.

## Step 5: Tell the user how to load the new files

The new skills, rules and MCP server load at session start. The agent cannot reload them itself.
Tell the user the step for their coding assistant:

| Coding assistant | Tell the user |
|---|---|
| Claude Code | "Run `/reload-skills` to use the new skills now. Restart the session later to load the rules and the MCP server." |
| Copilot CLI | "Run `/skills reload` and `/mcp reload`." |
| Codex | "Restart the session to load the rules and the MCP server." |
| Cursor | "Restart the session to load the new skills, rules and MCP server." |

## Step 6: Continue the task

Do not wait for the reload. Continue the user's task in this session:

1. Read the workflow rule and the entry skill of the new toolkit from the project folder of the coding assistant.
   - Claude Code: `.claude/rules/` and `.claude/skills/<entry-skill>/SKILL.md`
   - Cursor: `.cursor/rules/` and `.cursor/skills/<entry-skill>/SKILL.md`
   - Codex: `AGENTS.md` and `.agents/skills/<entry-skill>/SKILL.md`
2. Follow the entry skill with the context that you already have.
3. Until the reload, use the `uv run dlthub ai` CLI instead of the `dlt-workspace-mcp` tools.
