# Data quality conventions

## Core rules

**Continuous DQ, not ad-hoc.** This toolkit sets up persistent checks and metrics that run on every pipeline load. For one-off data sanity checks during development, use the **data-exploration** toolkit or the `validate-data` step in **rest-api-pipeline** instead.

**Use the dlt DQ API, not notebooks.** When the user asks to "set up data quality" or "monitor data quality", invoke `setup-data-quality`. Never generate a custom Marimo notebook as a DQ solution.

**License first.** The `dlthub.data_quality` license scope must be present before checks can run. If it is absent, stop and run `dlt license issue dlthub.data_quality` before continuing.

**Prefer built-in checks.** Use `is_unique()`, `is_not_null()`, `is_in()`, `case()` before writing any custom logic. Custom code is a last resort. Do NOT use `is_primary_key()` — it is not yet fully implemented and raises `LineageFailedException` at runtime; use `is_unique()` instead.

**Business intent first.** Ask for the user's data quality requirements in plain language; map them to checks. Do not expose the API surface (`dq.checks.*`, `dq.metrics.*`) until the user's intent is clear.

**Query results incrementally.** In `review-data-quality`, scope all queries to one table at a time. Show aggregated summaries first; load row-level detail only on explicit user request.
