# Data exploration workflow

## Workflow Entry
**ALWAYS** start with **Explore data** (`explore-data`) SKILL — connect to a dlt pipeline, understand the data, and plan charts

This toolkit is for quick dashboards to inspect pipeline data — not for deep data modeling or ontology building.

## Core workflow

Infer intent from the user's message — never ask "do you have a specific question?"

1. **Explore data** (`explore-data`) — connect to pipeline, plan one chart, output `<date>_<pipeline>_analysis_plan.md`
   - **High-intent** (user has a specific question) — schema scan only, plan chart directly
   - **Low-intent** (user wants to explore) — broad profiling, generate candidate questions, user picks one, then plan chart
   - **Returning** (analysis_plan.md exists) — skip connection and profiling, pick next question or ask for a new one, append chart to plan
2. **Build notebook** (`build-notebook`) — assemble marimo notebook from analysis_plan.md, validate, install dependencies, launch
3. **Iterate** — offer to add another chart or stop. If yes, re-invoke `explore-data` (enters **Returning** path). Max ~10 charts.

## Handover to other toolkits

### Outgoing (from data-exploration)

- **rest-api-pipeline** → `find-source` or `new-endpoint` — when `explore-data` identifies a data gap (needed columns don't exist in any table) and the user wants to extend the pipeline
- **dlthub-runtime** → `setup-runtime` — when the pipeline and notebook are production-ready and the user wants to deploy or schedule

### Incoming (to data-exploration)

- From **rest-api-pipeline** (after `validate-data` or `view-data`) — pipeline name and dataset are already known. `explore-data` should skip `list_pipelines` discovery and go straight to `list_tables`.
- From transformation toolkit (after `validate-transformed-data` or `new-endpoint`) — pipeline name and transformed tables are already known. `explore-data` should skip `list_pipelines` discovery and go straight to `list_tables`.
- From **dlthub-runtime** (marimo scheduled jobs) — a notebook already exists. `explore-data` picks up from the existing `analysis_plan.md` iteration path.

## Bulk requests

If the user asks for all questions at once (e.g., "all of them", "do everything"):
- Plan all charts in a single `analysis_plan.md` (mark all `[x]`)
- Hand off to `build-notebook` once with the full plan
- Skip the one-at-a-time iteration loop — it exists for interactive exploration, not batch mode

## Self-check

Critical invariants:
- Connection uses `dlt.attach()` or explicit destination — never raw `duckdb` imports
- Chart queries use GROUP BY / aggregation — never select raw unaggregated rows for charts
- SQL is the default query method; ibis only for complex joins or computed columns
- `analysis_plan.md` is the single source of truth between `explore-data` and `build-notebook`
- **Every `explore-data` run that produces a chart MUST propose `build-notebook`** — never leave the user without a notebook offer
