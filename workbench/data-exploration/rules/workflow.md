# Data exploration workflow

## Workflow Entry
**ALWAYS** start with **Explore data** (`explore-data`) SKILL — connect to a dlt pipeline, understand the data, and plan charts

This toolkit is for quick dashboards to inspect pipeline data — not for deep data modeling or ontology building.

## Core workflow

Infer intent from the user's message — never ask "do you have a specific question?"

1. **Explore data** (`explore-data`) — connect to pipeline, plan one chart, write the plan `.dlthub/explorations/<pipeline>/analysis_plan.md` (committed, independent of the dashboard tool)
   - **High-intent** (user has a specific question) — schema scan only, plan chart directly
   - **Low-intent** (user wants to explore) — broad profiling, generate candidate questions, user picks one, then plan chart
   - **Returning** (analysis_plan.md exists) — skip connection and profiling, pick next question or ask for a new one, append chart to plan
2. **Build notebook** (`build-notebook`) — assemble the marimo notebook from the plan at the path the user chose (recorded in the plan), validate, install dependencies, launch
3. **Iterate** — offer to add another chart or stop. If yes, re-invoke `explore-data` (enters **Returning** path). Max ~10 charts.

## Handover to other toolkits

### Outgoing (from data-exploration)

- **rest-api-pipeline** — when `explore-data` found a data gap (recorded under `## Data Gaps` in the plan) and the user wants the pipeline fixed: a missing column or concept → `new-endpoint`, data that looks truncated or stale → `adjust-endpoint`, a new source → `find-source`. Carry the gap.
