# Data quality workflow

## Workflow Entry
**ALWAYS** start with **Setup data quality** (`setup-data-quality`) SKILL — connect to a dlt pipeline and prepare the DQ environment

## Core workflow

TODO — fill in core workflow steps

1. **Setup data quality** (`setup-data-quality`) — connect to pipeline, inspect schema, prepare DQ environment
2. **Define data quality checks** (`define-data-quality-checks`) — define checks per table/column
3. **Run data quality** (`run-data-quality`) — execute checks against the pipeline data
4. **Review data quality** (`review-data-quality`) — review results, surface failures, suggest fixes

## Extend and harden

TODO — fill in advanced steps

## Handover to other toolkits

TODO — fill in handover conditions

### Outgoing (from data-quality)

- **transformations** — when DQ failures reveal modeling issues that need fixing upstream
- **dlthub-runtime** (`setup-runtime`) — when Profile B user wants to schedule `tools/dq_run.py` on the dltHub platform after a successful one-off run

### Incoming (to data-quality)

- From **rest-api-pipeline** (after `validate-data`) — pipeline name and dataset already known; skip discovery
- From **transformations** (after `validate-transformed-data`) — transformed tables already known; go straight to `define-data-quality-checks`