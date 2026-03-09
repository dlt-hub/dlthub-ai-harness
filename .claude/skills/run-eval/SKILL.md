---
name: run-eval
description: "Run trigger evaluation for a skill and analyze results. Use when the user wants to run evals, check trigger accuracy, analyze clashes, or improve a skill description based on eval results. Use when user says 'run eval', 'test triggers', 'check skill triggering', or 'analyze eval results'."
argument-hint: "[toolkit] [skill] [workspace]"
---

# Run trigger eval and analyze results

Run eval for `$ARGUMENTS` (format: `toolkit skill [workspace]`). The workspace argument is optional — if omitted, run against all workspaces in config.json.

## Step 0: Rebuild workspaces if needed

Check if the skill's SKILL.md is newer than the eval workspace. If the description changed, workspaces have stale copies.

```bash
# Compare timestamps
stat -c %Y workbench/<toolkit>/skills/<skill>/SKILL.md
stat -c %Y evals/.evals/<workspace>/.claude/skills/<skill>/SKILL.md
```

If the source is newer (or workspace doesn't exist), rebuild:
```bash
uv run python tools/create_eval_workspace.py evals/<toolkit>/<skill>
```

## Step 1: Run the eval

Parse `$ARGUMENTS` into toolkit, skill, and optional workspace name.

Run the eval (pass `--model` if the user specified one):
```bash
# All workspaces
uv run python tools/run_trigger_eval.py evals/<toolkit>/<skill> --verbose [--model <model>]

# Single workspace
uv run python tools/run_trigger_eval.py evals/<toolkit>/<skill> --workspace <ws-id> --verbose [--model <model>]
```

## Step 2: Read the results

Parse the JSON output. For each workspace, extract:
- **precision** — false triggers are a serious problem (skill fires when it shouldn't)
- **recall** — missed triggers mean the description isn't catching real use cases
- **clashes** — another skill stole a should-trigger query

Classify results into:
1. **Consistent misses** — queries that fail across all workspaces (description weakness)
2. **Competition losses** — queries that pass in init-only but fail in with-toolkit (clash with sibling skill)
3. **False triggers** — queries that should NOT trigger but did (description too broad)

## Step 3: Analyze clashes and misses

For each failed query, explain **why** it failed by reading the competing skills' descriptions:

```bash
uv run python tools/list_skill_descriptions.py evals/.evals/<workspace>
```

### For competition losses and clashes

For each clash, explain:
- Which skill likely won and why (quote the overlapping description keywords)
- Whether the other skill winning is **correct** (it's more specific for this query) or **wrong** (our skill should have won)

### For consistent misses

These are description weaknesses — the query matches the skill's intent but the description doesn't signal it strongly enough. Identify:
- What keywords or phrases are missing from the description
- Whether the query is a simple request Claude handles directly (undertrigger — can't fix with description alone)

### For false triggers

The description is too broad — it matches queries meant for other skills. Identify:
- Which words in the description cause the false match
- What negative guard ("Do NOT use when...") would prevent it

## Step 4: Propose description changes

Based on the analysis, propose concrete changes. **Always present proposals to the user and wait for approval before editing any SKILL.md.**

### How to write good descriptions

Claude undertriggers by default — it prefers to handle things directly rather than consulting skills. Descriptions need to be **pushy**: include explicit trigger phrases and concrete user utterances, not just abstract capability statements.

**Weak**: "Set up dlt secrets"
**Strong**: "Use when the user needs to set up, check, verify, debug, or read dlt secrets (API keys, database credentials). Also use when writing Python code that needs credentials."

But don't use rigid ALWAYS/NEVER/MUST-in-caps as a crutch. Instead, explain **why** the skill should handle it — Claude has good theory of mind and responds better to reasoning than commands.

### Generalize, don't overfit

The skill will be used across many prompts, not just these eval queries. Don't make fiddly description changes that target one specific eval query. Instead, identify the **pattern** behind the miss and address the pattern.

If a query like "which secrets files does my project have?" misses, don't add that exact phrase. Instead, add the pattern: "list or inspect secrets files".

### Propose new eval queries

When proposing description changes, also propose **new trigger queries** that test the change. This ensures the next eval run validates the improvement. Focus on:
- Queries that probe the exact boundary being adjusted
- Realistic phrasings a user would actually type (with context, detail, casual tone)
- Both positive (should now trigger) and negative (should still not trigger) cases

### Changes to the tested skill

- **Add trigger phrases** for consistent misses — use explicit user utterances the description should match
- **Add negative guards** for false triggers — explain what the skill does NOT handle and why
- **Disambiguate** overlapping keywords for competition losses — find unique vocabulary

### Changes to competing skills (when appropriate)

If a competing skill's description is too broad and incorrectly steals triggers, propose narrowing it too. Fixing clashes often means adjusting both sides.

Format all proposals as:
```
Skill: <skill-name> (path: <path-to-SKILL.md>)
Before: <current description>
After:  <proposed description>
Reason: <why this change helps>

New eval queries:
  + {"query": "...", "should_trigger": true}   # tests the fix
  + {"query": "...", "should_trigger": false}  # ensures no regression
```

### When NOT to change

- **Correct competition losses** — if the competing skill is genuinely more specific for that query, the loss is expected. Don't broaden our description to steal it back.
- **Undertrigger on simple queries** — Claude handles simple one-step requests without consulting any skill. No description change will fix this. Flag as undertrigger and suggest disabling the eval query with `"disabled": true, "reason": "undertrigger — ..."`.

## Step 5: Present to user

Summarize:
1. Overall scores per workspace (table)
2. Each failure with explanation and category (consistent miss / competition loss / false trigger / undertrigger)
3. Proposed description changes with before/after diffs
4. Proposed new eval queries
5. **Ask the user** if they want to apply changes and re-run — do NOT edit descriptions without approval
