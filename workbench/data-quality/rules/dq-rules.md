# Data quality conventions

## Core rules

**Continuous DQ, not ad-hoc.** This toolkit sets up persistent checks and metrics that run on every pipeline load. For one-off data sanity checks during development, use the **data-exploration** toolkit or the `validate-data` step in **rest-api-pipeline** instead.

**Use the dlt DQ API, not notebooks.** When the user asks to "set up data quality" or "monitor data quality", invoke `setup-data-quality`. Never generate a custom Marimo notebook as a DQ solution.

**Enable before checking.** Always call `dq.enable_data_quality(pipeline)` before defining or running any checks. If the DQ flag is absent from pipeline state, stop and return to `setup-data-quality`.

**Prefer built-in checks.** Use `is_unique()`, `is_not_null()`, `is_in()`, `case()` before writing any custom logic. Custom code is a last resort. Do NOT use `is_primary_key()` — it is not yet fully implemented and raises `LineageFailedException` at runtime; use `is_unique()` instead.

**Business intent first.** Ask for the user's data quality requirements in plain language; map them to checks. Do not expose the API surface (`dq.checks.*`, `dq.metrics.*`) until the user's intent is clear.

**Query results incrementally.** In `review-data-quality`, scope all queries to one table at a time. Show aggregated summaries first; load row-level detail only on explicit user request.

## Cross-toolkit handoffs

### Inbound — other toolkits recommending data-quality

- **rest-api-pipeline** → after `validate-data` or pipeline completion, suggest: *"Your pipeline is working. To set up continuous data quality monitoring, use `setup-data-quality`."*
- **transformations** → after `annotate-sources` or completing a transformation pipeline, recommend DQ as the next production-readiness step.

### Outbound — data-quality recommending other toolkits

- **`review-data-quality` → data-exploration**: when anomalies are found that need deeper investigation, hand off to `explore-data` with the table name and failing column already in context.
- **`review-data-quality` → dlthub-runtime**: when DQ is fully configured and all checks pass, recommend `setup-runtime` for continuous monitoring on a schedule.

These are recommendations, not hard dependencies. The data-quality toolkit is not a prerequisite for data-exploration or transformations, and neither is a prerequisite for data-quality.