---
name: create-eval
description: "Create trigger evaluation setup for a toolkit skill. Use when the user wants to test whether a skill's description triggers correctly, set up eval workspaces, or generate trigger test queries for a skill. Use when user says 'create eval', 'test triggers', 'eval skill', or wants to measure skill triggering accuracy."
argument-hint: "[toolkit] [skill]"
---

# Create trigger eval for a skill

Scaffold a trigger eval for `$ARGUMENTS` (format: `toolkit skill` or `toolkit/skill`).

## Step 1: Locate the skill

Parse `$ARGUMENTS` into toolkit and skill name. Find the skill at `workbench/<toolkit>/skills/<skill>/SKILL.md`.
Read the skill's frontmatter (`name`, `description`) and body to understand what it does and when it should trigger.

## Step 2: Create eval directory

Create `evals/<toolkit>/<skill>/` if it doesn't exist.

## Step 3: Determine eval workspaces

Ask the user which workspace configurations to test. Each workspace represents a different set of installed toolkits — this tests how the skill behaves when competing with other skills.

Common patterns:
- **init-only** — just `dlt ai init` (minimum skills: `setup-secrets`, `toolkit-dispatch`). Tests cold-start triggering.
- **with-\<toolkit\>** — init + the skill's own toolkit installed. Tests triggering with competing sibling skills.

Write `config.json`:
```json
{
  ".eval-workspaces": {
    "init-only": {"toolkits": []},
    "with-rest-api": {"toolkits": ["rest-api-pipeline"]}
  }
}
```

Ask the user if they want additional workspace configurations. Each entry adds a workspace with different toolkit combinations.

## Step 4: Generate trigger eval queries

Read the skill's SKILL.md description carefully. Then read all competing skill descriptions from the selected toolkits:
```bash
uv run python tools/list_skill_descriptions.py workbench/<toolkit1> workbench/<toolkit2> ...
```

Use the competing descriptions to understand clash surfaces — which skills have overlapping vocabulary or intent.

Generate 20 eval queries — a mix of should-trigger (10) and should-not-trigger (10).

### Query quality rules

Queries must be **realistic** — what a real user would actually type. Include personal context, specific details, file paths, API names, error messages, casual phrasing. Mix formal and informal, long and short.

**Bad**: `"Format this data"`, `"Build a pipeline"`, `"Deploy something"`

**Good**: `"ok so my boss just sent me this xlsx file (its in my downloads, called something like 'Q4 sales final FINAL v2.xlsx') and she wants me to add a column that shows the profit margin as a percentage. The revenue is in column C and costs are in column D i think"`

### Should-trigger queries (10)

Think about **coverage** — different phrasings of the same intent:
- Some formal, some casual
- Cases where the user doesn't name the skill explicitly but clearly needs it
- Uncommon use cases at the edges of the skill's scope
- Cases where this skill competes with another but should win

### Should-not-trigger queries (10)

The most valuable negatives are **near-misses** — queries that share keywords or concepts with the skill but actually need something different:
- Adjacent domains or overlapping vocabulary
- Ambiguous phrasing where a keyword match would trigger but shouldn't
- Queries that touch on the skill's domain but in a context where another tool is better
- Specific in-progress tasks that belong to sibling skills

**Avoid obviously irrelevant negatives** — "write a fibonacci function" as a negative for a pipeline skill doesn't test anything. The negatives should be genuinely tricky.

### Disabled queries

If during analysis a query turns out to be an undertrigger (Claude handles it directly without any skill), mark it as disabled instead of removing:
```json
{"query": "...", "should_trigger": true, "disabled": true, "reason": "undertrigger — Claude uses MCP directly"}
```

Write `trigger-eval.json`.

## Step 5: Review with user

Present the generated queries grouped by should-trigger/should-not-trigger. Explain the reasoning for tricky cases. Let the user edit, add, or remove queries before finalizing.

## Step 6: Build workspaces

Run:
```bash
uv run python tools/create_eval_workspace.py evals/<toolkit>/<skill>
```

This creates all workspaces defined in config.json.

## Step 7: Continue to run-eval

Ask the user if they want to run the eval now. If yes, hand over to `/run-eval <toolkit> <skill>`. Do not duplicate the eval running and analysis logic here.
