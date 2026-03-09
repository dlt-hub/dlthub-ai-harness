# Data exploration workflow

## Workflow Entry
**ALWAYS** start with **Connect and profile** (`connect-and-profile`) SKILL — discover available dlt pipelines, profile schemas and table stats, flag anomalies

## Core workflow

```
connect-and-profile -> [dashboard type] -> (dlt dashboard | analyze-questions (one chart) -> marimo-notebook -> launch -> [add another chart?] -> ... -> [remove cap?] -> redeploy)
```

1. **Connect + profile** (`connect-and-profile`) — pipeline discovery, schema/stats gathering, anomaly flags
2. **Dashboard routing** (workflow step) — offer quick dlt dashboard vs custom Marimo notebook
3. *Quick path*: `dlt pipeline <name> show` — done
4. *Custom path*: **First chart** (`analyze-questions`) — interview, select questions, plan and confirm **one** chart for the top question
5. *Custom path*: **Notebook generation** (`marimo-notebook`, external) — generates marimo notebook from chart spec
6. *Custom path*: **Launch notebook** (workflow step) — offer to launch in browser
7. *Custom path*: **Add more charts** (workflow step) — offer to add another chart by re-invoking `analyze-questions` for the next question
8. *Custom path*: **Finalize** (workflow step) — offer to remove row cap, regenerate notebook, and relaunch

## Dashboard type selection (MANDATORY after profiling)

After `connect-and-profile` completes, ask the user to choose between:
- **Quick dashboard** — opens the built-in dlt Workspace Dashboard (`dlt pipeline <name> show`) for inspecting the pipeline and the dataset, but not for generating insights from the data. Workflow ends here.
- **Custom notebook** — continue with `analyze-questions` → `marimo-notebook` → launch → iterate.

This routing applies whenever the user asks for a "dashboard", "visualization", "report", or wants to "see the data."

## marimo-notebook dependency check

Before handing off to notebook generation, verify the `marimo-notebook` skill is installed (check `.claude/skills/`, `~/.claude/skills/`, or `.agents/skills/`). If not found, tell the user to install it with `npx skills add marimo-team/skills --skill marimo-notebook` and wait.

## Launch notebook after generation

After the `marimo-notebook` skill completes and a notebook file exists, offer to launch it: `uv run marimo edit <notebook_file>.py --headless --no-token`. Tell the user the URL (localhost:2718).

## Iteration loop

After the notebook is launched (or the user skips launch), offer to add another chart (re-invoke `analyze-questions`) or stop. Recommended maximum: **10 charts total** across all iterations — but do not enforce this as a hard limit if the user wants more.

## Finalize: row-cap removal and redeploy

When the user is done adding charts, offer to remove the 1,000-row development cap. If the user opts to remove it:

1. Strip all `limit(1000)` calls from the ibis queries in the notebook file.
2. Re-invoke `marimo-notebook` to regenerate the notebook with uncapped queries.
3. Relaunch the notebook (same as the launch step above).

## Row-cap policy

Default to **1,000 rows per query output** during development and notebook iteration. Prefer deterministic ordering (`order_by` on timestamp or stable key) before `limit(1000)`. Only remove when the user explicitly opts out at the end of the workflow.

## Handover to other toolkits

- **rest-api-pipeline** — when the user needs to build or fix a dlt pipeline before exploring data
- **dlthub-runtime** — when the pipeline is production-ready and the user wants to deploy, schedule, or run it on the dltHub platform

## Self-check

Critical invariants:
- Connection uses `dlt.attach()` or explicit destination — never raw `duckdb` imports
- Row cap (1,000) is active on all queries unless the user opted out
