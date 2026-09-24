# dlthub-router (entry skill) trigger eval

## Cross-agent scope

The `dlthub-router` skill must trigger and route correctly on **all three agents** — Claude Code, Cursor, and Codex. `SKILL.md` is a cross-agent standard, so the skill installs natively to `.claude/skills/`, `.cursor/skills/`, and `.agents/skills/` respectively, and the always-loaded toolkit index ships to each agent's always-loaded surface (rule on Claude/Cursor, `AGENTS.md` on Codex).

**What is validated automatically vs. manually today:**

- **Automated trigger eval (all three agents):** the harness below drives each agent headlessly — `claude -p`, `codex exec --json`, `cursor-agent -p` — via `tools/run_trigger_eval.py --agent {claude,cursor,codex}` (or `--agent all`). Claude triggers are detected via the `Skill` tool; Codex/Cursor via a read of the skill's `SKILL.md`. See [EVALS.md](../../../EVALS.md).
- **Cross-agent install + always-loaded surface (all three):** verified via `dlthub ai toolkit install … --strict` for `--agent claude|cursor|codex` and by inspecting the generated rule / `.mdc` / `AGENTS.md` (the index reaches the always-loaded surface on each).
- **`dlthub-router` is N/A for automated trigger measurement on Codex:** it's an always-loaded router, and on Codex the routing index lives in `AGENTS.md` (not a skill activation), so there's no discrete trigger event. (It also currently exceeds Codex's 1024-char skill-description cap and is dropped as a skill — tracked in [#75](https://github.com/dlt-hub/dlthub-ai-workbench-internal/issues/75).) Measure it on Claude/Cursor; on Codex, confirm routing in the final answer manually.

## Status: eval framework bug — skill triggers correctly

### The bug

`run_eval.py` creates a **command** in `.claude/commands/` as a proxy for the skill, then checks if the agent reads that command. But when the real skill exists in the agent's skills dir, the agent invokes the **skill** via the `Skill` tool (not the proxy command). The eval detection misses this because it looks for the command name, not the skill name.

### Proof: `claude -p` triggers the skill

Running `claude -p "how can I build my first pipeline?"` from a clean eval workspace:

1. First action: `Skill(dlthub-router)` — correct trigger
2. The skill routes from the always-loaded toolkit index (no MCP round-trip needed); falls back to `list_toolkits` only for needs not in the index
3. Installs `rest-api-pipeline` and hands over to its entry skill (`find-source`) **in the same session** (no restart)

### How to test (Claude, automated)

```bash
# Create clean workspace
uv run python tools/create_eval_workspace.py evals/init/dlthub-router

# Run claude -p from it
cd evals/.evals/init--dlthub-router--init-only
CLAUDECODE= claude -p "how can I build my first pipeline?" --output-format stream-json
```

Check the stream for `{"name":"Skill","input":{"skill":"dlthub-router"}}`.

### How to check (Cursor / Codex, automated)

Build the workspace for the target agent and run the eval against it:

```bash
uv run python tools/create_eval_workspace.py evals/init/dlthub-router --agent cursor
uv run python tools/run_trigger_eval.py evals/init/dlthub-router --agent cursor --verbose
```

On **Cursor**, `dlthub-router` installs as a skill and triggers via a `readToolCall` on `.cursor/skills/dlthub-router/SKILL.md`. On **Codex** the router is N/A for automated measurement (see above) — routing is served by the always-loaded `AGENTS.md`; confirm it manually by checking the final answer names the right toolkit.

## Measured run, 2026-09-24

`run_trigger_eval.py --agent claude --runs-per-query 3`, 24 queries per workspace, router description at 1167 chars:

| workspace | passed | precision | recall |
|---|---|---|---|
| init-only | 22/24 | 0.923 | 0.923 |
| with-rest-api | 23/24 | 0.909 | 1.0 |
| with-dlthub-platform | 22/24 | 0.889 | 0.889 |

Known misses:

- `can you help me with my python project? I need to parse some CSV files and upload them to S3` triggers in all three workspaces and should not. It fails on `master` too. An explicit `Do NOT use for general python help` guard was tried and reverted: it cut the false positive to 0.0 in `with-dlthub-platform` but took that workspace's recall from 0.889 to 0.333, because paying for it meant shortening the clause that tells the router to fire when no toolkit matches.
- `my deployed job failed last night, what went wrong?` does not trigger in `init-only`. It fires at 0.67 in `with-rest-api` and correctly defers to `debug-deployment` at rate 1.0 in `with-dlthub-platform`.

## Description length

The description is 1167 chars, over the 1024 Codex cap that drops it as a skill there (dlt-hub/dlthub-ai-workbench-internal#75). `validate_toolkits.py` warns above that cap.

Trigger rate does not fall off monotonically with length, so treat the cap as a portability limit rather than a quality one. Measured points, all on this skill: 1122 and 1167 and 1176 behave; 1267 took `init-only` recall to 0.154 with ten cold-start queries silent; 1140 took `with-dlthub-platform` to 0.333. Wording moves the number more than length does. Re-measure after any edit to the description.
