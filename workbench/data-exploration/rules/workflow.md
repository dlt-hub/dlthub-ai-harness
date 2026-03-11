# Data exploration workflow

## Workflow Entry
**ALWAYS** start with **Explore data** (`explore-data`) SKILL — connect to a dlt pipeline, understand the data, and plan charts

## Core workflow

```
explore-data → analysis_plan.md → build-notebook → dashboard.py → [add another chart?] → explore-data → ...
```

1. **Explore data** (`explore-data`) — connect to pipeline, plan one chart (high-intent or low-intent path), output `<date>_<pipeline>_analysis_plan.md`
2. **Build notebook** (`build-notebook`) — assemble marimo notebook from analysis_plan.md, validate, launch
3. **Iterate** (workflow step) — offer to add another chart or stop

## Intent detection

`explore-data` handles two paths based on what the user provides:

- **High-intent** — user has a specific question ("What's the revenue trend?"). Schema scan only, no full profiling. Plan chart directly from schema + question.
- **Low-intent** — user wants to explore ("What can I learn?", "Explore my data"). Broad profiling, generate candidate questions, user picks, then plan chart.

The skill detects intent from the user's message. Do not ask "do you have a specific question?" — infer it.

## Iteration via analysis_plan.md

After `build-notebook` launches the notebook, offer to add another chart:

```
question: "Want to add another chart?"
options:
  - label: "Yes — add another chart"
  - label: "No — I'm done"
  - label: "Remove row cap and finalize"
```

If "Yes": re-invoke `explore-data`. The skill detects the existing analysis_plan.md, skips connection and profiling, and asks for the next question. Then re-invoke `build-notebook` to regenerate.

If "Remove row cap": re-invoke `build-notebook` — it strips `.limit(1000)` calls, re-validates, and relaunches.

Recommended maximum: **10 charts total** — but don't enforce as a hard limit.

## Row-cap policy

Default to **1,000 rows per query output** during development. Prefer deterministic ordering (`order_by` on timestamp or stable key) before `limit(1000)`. Only remove when the user opts out at the end of the workflow.

## Handover to other toolkits

### Outgoing (from data-exploration)

- **rest-api-pipeline** → `find-source` or `new-endpoint` — when `explore-data` identifies a data gap (needed columns don't exist in any table) and the user wants to extend the pipeline
- **dlthub-runtime** → `setup-runtime` — when the pipeline and notebook are production-ready and the user wants to deploy or schedule

### Incoming (to data-exploration)

- From **rest-api-pipeline** (after `validate-data` or `view-data`) — pipeline name and dataset are already known. `explore-data` should skip `list_pipelines` discovery and go straight to `list_tables`.
- From transformation toolkit (after `validate-transformed-data` or `new-endpoint`) — pipeline name and transformed tables are already known. `explore-data` should skip `list_pipelines` discovery and go straight to `list_tables`.
- From **dlthub-runtime** (marimo scheduled jobs) — a notebook already exists. `explore-data` picks up from the existing `analysis_plan.md` iteration path.

## Self-check

Critical invariants:
- Connection uses `dlt.attach()` or explicit destination — never raw `duckdb` imports
- Row cap (1,000) is active on all queries unless the user opted out
- `analysis_plan.md` is the single source of truth between `explore-data` and `build-notebook`
