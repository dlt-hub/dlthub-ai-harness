# Trigger Evals

Test whether skill descriptions cause Claude to invoke the right skill for the right query.

## Why

A skill's `description` frontmatter is the primary mechanism Claude uses to decide whether to consult a skill. A bad description means:
- **Missed triggers** — the skill exists but Claude doesn't use it
- **False triggers** — the skill fires when a different skill should handle the query
- **Clashes** — a competing skill steals the trigger from the intended skill

Trigger evals measure these systematically.

## Concepts

### Eval workspace

An eval workspace is a fresh dlthub project (`uv venv` + `dlthub ai init` + optional toolkits) created under `evals/.evals/`. It simulates what a real user has after bootstrapping — the same skills, rules, and MCP servers, but in an isolated directory.

Each eval can define **multiple workspaces** with different toolkit combinations. This tests how a skill behaves:
- **Alone** (init-only) — minimal competition, should have high recall
- **With siblings** (with-rest-api) — many competing skills, tests precision and clash resistance

### Isolation

Eval workspaces are self-contained — the agent runner (`claude -p`, `codex exec`, or `cursor-agent -p`) runs from the workspace directory and only sees the skills installed there. This prevents pollution from the dev project's plugins, skills, and commands.

### Agents (Claude, Codex, Cursor)

Evals run on all three agents via `--agent {claude,cursor,codex}` (or `--agent all`). Each agent signals a skill trigger differently, so the runner detects it differently:

| Agent | Headless driver | Trigger signal |
|---|---|---|
| Claude | `claude -p --output-format stream-json` | first `Skill` tool_use in the stream |
| Codex | `codex exec --json -s read-only` | a shell command reading `.agents/skills/<name>/SKILL.md`, excluding always-on `AGENTS.md` skills |
| Cursor | `cursor-agent -p --output-format stream-json --trust` | a `readToolCall` on `.cursor/skills/<name>/SKILL.md` |

Codex and Cursor have no native `Skill` tool — they "activate" a skill by **reading its `SKILL.md`**. **Always-loaded router skills (e.g. `dlthub-router`) are N/A on Codex**: there the routing index lives in the always-loaded `AGENTS.md`, not a skill activation, so there is no discrete trigger event to measure. Opt-in skills (e.g. `find-source`) are measured normally on all three.

Codex and Cursor require their CLIs installed and authenticated (`codex`; and `cursor-agent login` or `CURSOR_API_KEY`).

### Clashes

A clash occurs when a should-trigger query activates a **different** skill instead of the tested one. Clashes are only tracked on should-trigger queries (a should-not-trigger query activating another skill is correct behavior, not a clash).

### Disabled queries

Queries that consistently miss due to **undertriggering** (Claude handles simple requests directly without consulting any skill) can be marked `"disabled": true` with a reason. They remain in the eval set for documentation but are skipped during runs.

## Metrics

| Metric | What it measures | Good value |
|---|---|---|
| **Precision** | Of queries that triggered the skill, how many should have? | 1.0 (no false triggers) |
| **Recall** | Of queries that should trigger, how many did? | 1.0 (never missed) |
| **Clashes** | On should-trigger queries, how many times did another skill fire instead? | 0 |

**Expected tradeoffs**: With more competing skills, recall may drop slightly as more specific skills correctly claim specific queries. This is acceptable when the competing skill is genuinely better suited.

## Directory structure

```git 
evals/
  <toolkit>/
    <skill>/
      config.json          # Workspace definitions
      trigger-eval.json    # Queries with expected outcomes
      README.md            # Notes, findings, known issues (optional)
  .evals/                  # Generated workspaces (gitignored)
    <toolkit>--<skill>--<workspace-id>[--<agent>]/   # --<agent> suffix for cursor/codex; claude unsuffixed
      .venv/
      .claude/skills/...   # claude; cursor -> .cursor/skills, codex -> .agents/skills
      .claude/rules/...    # claude; cursor -> .cursor/rules/*.mdc, codex -> folded into AGENTS.md
```

### config.json

Defines which workspaces to create and test against:

```json
{
  ".eval-workspaces": {
    "init-only": {"toolkits": []},
    "with-rest-api": {"toolkits": ["rest-api-pipeline"]}
  }
}
```

### trigger-eval.json

Array of queries with expected trigger behavior:

```json
[
  {"query": "realistic user prompt", "should_trigger": true},
  {"query": "near-miss prompt", "should_trigger": false},
  {"query": "simple query", "should_trigger": true, "disabled": true, "reason": "undertrigger"}
]
```

## Tools

### Create eval setup

```bash
# Interactive — scaffolds config.json, generates trigger queries, builds workspaces
/create-eval <toolkit> <skill>
```

### Create workspaces

```bash
# Builds all workspaces defined in config.json (default agent: claude)
uv run python tools/create_eval_workspace.py evals/<toolkit>/<skill>

# Build for a specific agent (cursor/codex get a --<agent> workspace suffix)
uv run python tools/create_eval_workspace.py evals/<toolkit>/<skill> --agent codex
```

### Run eval

```bash
# Run against all workspaces
uv run python tools/run_trigger_eval.py evals/<toolkit>/<skill> --verbose

# Single workspace
uv run python tools/run_trigger_eval.py evals/<toolkit>/<skill> --workspace <id> --verbose

# With specific model
uv run python tools/run_trigger_eval.py evals/<toolkit>/<skill> --model claude-sonnet-4-6 --verbose

# Multiple runs for reliability
uv run python tools/run_trigger_eval.py evals/<toolkit>/<skill> --runs-per-query 3 --verbose

# A specific non-Claude agent (CLI must be installed + authenticated)
uv run python tools/run_trigger_eval.py evals/<toolkit>/<skill> --agent codex --verbose

# All agents in one run — reports per-agent results (requires each agent's workspace built)
uv run python tools/run_trigger_eval.py evals/<toolkit>/<skill> --agent all --verbose
```

### Run eval with analysis

```bash
# Interactive — runs eval, analyzes results, proposes description changes
/run-eval <toolkit> <skill>
/run-eval <toolkit> <skill> <workspace>
```

### List skill descriptions

```bash
# From toolkits
uv run python tools/list_skill_descriptions.py workbench/rest-api-pipeline workbench/init

# From eval workspace
uv run python tools/list_skill_descriptions.py evals/.evals/<workspace>

# As JSON
uv run python tools/list_skill_descriptions.py --json workbench/init
```

## Writing good eval queries

**Realistic**: Include personal context, API names, error messages, casual phrasing. Not abstract requests.

**Should-trigger**: Cover different phrasings — formal, casual, implicit need, edge cases, competition boundaries.

**Should-not-trigger**: Focus on **near-misses** — queries sharing keywords with the skill but belonging to a sibling. Avoid obviously irrelevant negatives.

**Undertrigger awareness**: Claude handles simple one-step requests directly without any skill. Queries like "list my secrets files" won't trigger regardless of description quality. Mark these as disabled rather than fighting them.
