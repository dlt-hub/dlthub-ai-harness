# dlthub-router (entry skill) trigger eval

## Cross-agent scope

The `dlthub-router` skill must trigger and route correctly on **all three agents**: Claude Code, Cursor and Codex. `SKILL.md` is a standard for all three agents. The skill installs to `.claude/skills/`, `.cursor/skills/` and `.agents/skills/`. The toolkit index goes into the always-loaded rule on Claude and Cursor, and into `AGENTS.md` on Codex.

**What is validated automatically vs. manually today:**

- **Automated trigger eval, all three agents:** `tools/run_trigger_eval.py --agent {claude,cursor,codex}` (or `--agent all`) runs each agent headless. Claude triggers come from the `Skill` tool. Codex and Cursor triggers come from a read of `SKILL.md`. See [EVALS.md](../../../EVALS.md).
- **Install, all three agents:** `dlthub ai toolkit install … --strict` for each `--agent claude|cursor|codex`. Then read the generated rule, `.mdc` or `AGENTS.md` and check that the index is there.
- **Codex:** the eval does not measure `dlthub-router`. Codex keeps the routing index in `AGENTS.md`, so no skill trigger occurs. Measure it on Claude and Cursor. On Codex, check the routing in the final answer by hand.

## How to run

Claude:

```bash
# Create clean workspace
uv run python tools/create_eval_workspace.py evals/init/dlthub-router

# Run claude -p from it
cd evals/.evals/init--dlthub-router--init-only
CLAUDECODE= claude -p "how can I build my first pipeline?" --output-format stream-json
```

Check the stream for `{"name":"Skill","input":{"skill":"dlthub-router"}}`.

Cursor or Codex: build the workspace for the target agent and run the eval against it:

```bash
uv run python tools/create_eval_workspace.py evals/init/dlthub-router --agent cursor
uv run python tools/run_trigger_eval.py evals/init/dlthub-router --agent cursor --verbose
```

On **Cursor**, `dlthub-router` installs as a skill and triggers with a `readToolCall` on `.cursor/skills/dlthub-router/SKILL.md`.

## Measured run, 2026-11-15

`run_trigger_eval.py --agent claude --runs-per-query 3`, 29 queries per workspace (4 deploy and schedule queries
added), before and after every skill description was rewritten to start with "Use when" (router at 1006 chars):

| workspace | before | after | after precision | after recall |
|---|---|---|---|---|
| init-only | 26/29 | 27/29 | 0.944 | 0.944 |
| with-rest-api | 27/29 | 27/29 | 0.933 | 0.933 |
| with-dlthub-platform | 27/29 | 28/29 | 0.909 | 1.0 |
| with-sql-database | 27/29 | 27/29 | 0.941 | 0.941 |

- Both known misses below remain.
- With `dlthub-platform` installed, the deploy and schedule queries go to `setup-runtime` at 0.67 to 1.0.
- "schedule my stripe pipeline to run every hour" swings between 0.33 and 1.0 across runs, so a single run of 3
  is noise there.
- A flow check, in which a full `claude -p` session goes from the request to the platform entry skill, reached
  `setup-runtime` in 8/9 sessions with no platform toolkit installed and in 9/9 with `rest-api-pipeline` installed.
  The miss was "how do I deploy this pipeline?" in a workspace with no pipeline, where the router asks which
  pipeline is meant.

## Measured run, 2026-09-24

`run_trigger_eval.py --agent claude --runs-per-query 3`, 24 queries per workspace, router description at 1167 chars:

| workspace | passed | precision | recall |
|---|---|---|---|
| init-only | 22/24 | 0.923 | 0.923 |
| with-rest-api | 23/24 | 0.909 | 1.0 |
| with-dlthub-platform | 22/24 | 0.889 | 0.889 |

Known misses:

- `can you help me with my python project? I need to parse some CSV files and upload them to S3` triggers in all three workspaces and should not. It fails on `master` too. We tried and reverted a `Do NOT use for general python help` guard. It removed the false positive in `with-dlthub-platform`. But recall there fell from 0.889 to 0.333, because the guard shortened the clause for the no-match case.
- `my deployed job failed last night, what went wrong?` does not trigger in `init-only`. It fires at 0.67 in `with-rest-api` and correctly defers to `debug-deployment` at rate 1.0 in `with-dlthub-platform`.

## Description length

The description is 1006 chars, under the 1024 Codex cap that drops a skill there. `validate_toolkits.py` warns above that cap.

Trigger rate does not fall off monotonically with length, so treat the cap as a portability limit rather than a quality one. Measured points, all on this skill:

- 1122, 1167, 1176 chars: no change.
- 1267 chars: `init-only` recall 0.154. Ten queries with no matching toolkit installed did not trigger.
- 1140 chars: `with-dlthub-platform` recall 0.333.

Wording moves the number more than length does. Re-measure after any edit to the description.
