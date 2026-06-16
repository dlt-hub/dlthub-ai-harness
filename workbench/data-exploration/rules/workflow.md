# Data exploration workflow

## Workflow Entry
**ALWAYS** start with **Explore data** (`explore-data`) SKILL — connect to a dlt pipeline, understand the data, and plan charts

This toolkit is for quick dashboards to inspect pipeline data — not for deep data modeling or ontology building.

## Core workflow

Infer intent from the user's message — never ask "do you have a specific question?"

**Batch is the default.** If the user named a count or set of questions ("3 charts", "revenue and signups", "all of them"), or the run is non-interactive, plan **all** charts in one `explore-data` pass and build the notebook **once**. Only use the one-chart-at-a-time loop when the user is genuinely exploring live and wants to react to each chart. Each extra invocation/round-trip is the dominant cost of a run, so collapse them.

1. **Explore data** (`explore-data`) — connect to pipeline, plan chart(s), output `<date>_<pipeline>_analysis_plan.md`
   - **High-intent** (user has specific question(s)) — schema scan only, plan chart(s) directly
   - **Low-intent** (user wants to explore) — broad profiling, generate candidate questions, user picks, then plan
   - **Returning** (analysis_plan.md exists) — skip connection and profiling, plan the next chart(s), append to plan
2. **Build notebook** (`build-notebook`) — assemble the whole marimo notebook from analysis_plan.md in one write, statically validate (`marimo check`), install dependencies, run the file end-to-end (`uv run python <file>`) to catch runtime errors, then launch as an app (`marimo run`)
3. **Iterate** (interactive only) — offer to add another chart or stop. If yes, re-invoke `explore-data` (enters **Returning** path). Max ~10 charts.

## Handover to other toolkits

### Outgoing (from data-exploration)

- **rest-api-pipeline** → `find-source` (new data source) or `new-endpoint` (missing column/concept) or `adjust-endpoint` (data exists but looks truncated/stale) — when `explore-data` finds a data gap and the user wants to extend or fix the pipeline
- **transformations** — when the user decides the raw tables need proper modeling before further analysis; pipeline name, dataset, and profiled table structure carry over to `annotate-sources`
- **dlthub-platform** → `setup-runtime` — when the pipeline and notebook are working and the user wants to deploy or schedule

### Incoming (to data-exploration)

- From **rest-api-pipeline** (after `validate-data`, `view-data`, `new-endpoint`, or `adjust-endpoint`) — pipeline name and dataset are already known. `explore-data` should skip `list_pipelines` discovery and go straight to schema discovery (`explore-data` Step 1.2 — `export_schema` or `profile_tables` depending on intent).
- From **sql-database-pipeline** (after `validate-data` or `view-data`) — pipeline name, destination, and loaded table names are already known. `explore-data` should skip `list_pipelines` discovery and go straight to schema discovery (`explore-data` Step 1.2 — `export_schema` or `profile_tables` depending on intent).
- From **filesystem-pipeline** (after `create-filesystem-pipeline`) — pipeline name and dataset are already known. `explore-data` should skip `list_pipelines` discovery and go straight to schema discovery (`explore-data` Step 1.2 — `export_schema` or `profile_tables` depending on intent).
- From **transformations** (after `create-transformation`) — pipeline name and transformed tables are already known. `explore-data` should skip `list_pipelines` discovery and go straight to schema discovery (`explore-data` Step 1.2 — `export_schema` or `profile_tables` depending on intent).
- From **dlthub-platform** (marimo scheduled jobs) — a notebook already exists. `explore-data` picks up from the existing `analysis_plan.md` iteration path.
- From **data-quality** (after `review-data-quality`) — failing table name and metric anomaly are already known; `explore-data` should skip broad profiling and target those specific tables directly.
- From **quick-start** (shortcut path when a pipeline already exists) — pipeline name may be inferred from `dlthub ai status`; if unknown, `explore-data` runs `list_pipelines` as usual. No analysis_plan.md exists yet — use the fresh path (low-intent or high-intent), not Returning.

## Batch mode (the default — see above)

When planning multiple charts at once:
- Plan all charts in one `explore-data` pass; write the whole `analysis_plan.md` in a single Write
- Confirm all chart specs together in one message (one approval for the set)
- Hand off to `build-notebook` once with the full plan
- `build-notebook` writes the entire notebook in one Write and validates once
- Skip the one-at-a-time iteration loop — it exists for interactive exploration only

## Self-check

Critical invariants:
- Connection uses `dlt.attach()` or explicit destination — never raw `duckdb` imports
- Chart queries use GROUP BY / aggregation — never select raw unaggregated rows for charts
- SQL is the default query method; ibis only for complex joins or computed columns
- `analysis_plan.md` is the single source of truth between `explore-data` and `build-notebook`
- **Every `explore-data` run that produces a chart MUST propose `build-notebook`** — never leave the user without a notebook offer
