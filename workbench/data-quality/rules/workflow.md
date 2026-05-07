# Data quality workflow

## Workflow Entry
**ALWAYS** start with **Setup data quality** (`setup-data-quality`) SKILL — connect to a dlt pipeline and prepare the data quality environment

## Core workflow

1. **Setup data quality** (`setup-data-quality`) — connect to pipeline, inspect schema, prepare data quality environment
2. **Define data quality checks** (`define-data-quality-checks`) — define checks per table/column
3. **Run data quality** (`run-data-quality`) — execute checks against the pipeline data
4. **Review data quality** (`review-data-quality`) — review results, surface failures, suggest fixes

## Extend and harden

5. **Add or refine checks** — return to (`define-data-quality-checks`) after seeing initial results; adjust thresholds, add new checks, or remove over-strict ones

## Handover to other toolkits

### Outgoing (from data-quality)

- **transformations** — from (`review-data-quality`), when data quality failures reveal upstream modeling issues that need fixing; start at `annotate-sources`
- **dlthub-runtime** (Profile A) — from (`review-data-quality`), when the user wants to deploy the pipeline script (with embedded `@dq.with_checks` decorators) as a scheduled job; start at `setup-runtime`
- **dlthub-runtime** (Profile B) — from (`review-data-quality`), when the user wants to schedule `tools/dq_run.py` as a standalone recurring job; start at `setup-runtime`
- **data-exploration** — from (`review-data-quality`), when metric anomalies need deeper interactive investigation; start at `explore-data`

### Incoming (to data-quality)

- From **rest-api-pipeline** (after `validate-data`) — pipeline name and dataset already known; skip discovery in (`setup-data-quality`)
- From **sql-database-pipeline** (after `validate-data`) — pipeline name and dataset already known; skip discovery in (`setup-data-quality`)
- From **transformations** (after `create-transformation`) — transformed tables already known; go straight to (`define-data-quality-checks`)
