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
