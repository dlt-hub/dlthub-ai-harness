---
name: adjust-endpoint
description: Adjust a working dlt pipeline for production — remove dev limits, verify pagination (including stuck or looping paginators), configure incremental loading, expand date ranges, and handle rate-limit/429 errors with retries, backoff, and request timeouts. Use when the user wants to remove .add_limit(), load more data, fix stuck or looping pagination, set up incremental loading, or make the pipeline retry/back off on 429s. For throughput/concurrency tuning (parallel resources, page size) when a working pipeline is slow, use optimize-rest-api-performance instead. For inspecting loaded data, fixing column types, or flattening nested structures after a load, use validate-data instead.
argument-hint: "[pipeline-name] [adjustments]"
---

# Adjust endpoint for production

Parse `$ARGUMENTS`:
- `pipeline-name` (optional): the dlt pipeline name. If omitted, infer from session context. If ambiguous, ask the user and stop.
- `hints` (optional, after `--`): specific adjustments to make

## Critical rule: removing `.add_limit()` requires verified pagination

`.add_limit(1)` during development masks pagination problems — only one page is fetched, so a broken paginator never loops. Removing it without explicit pagination causes stuck pipelines.

**Before removing `.add_limit()`:**
1. Check every resource has an explicit `"paginator"` config. If any rely on auto-detection, add one first.
2. Use `debug-pipeline` with INFO logging for the first unlimited run to watch pagination progress and catch loops early.

### Real example: OpenAI Usage API

Pipeline worked with `.add_limit(1)`. After removing the limit, it hung forever — dlt's auto-detected paginator looped. Fix: added explicit `"paginator": {"type": "cursor", "cursor_path": "next_page", "cursor_param": "page"}`. Full load then completed in 5 seconds.

## Harden optional endpoints with response_actions

Some endpoints return 404 or an error body for certain parent items (e.g. a repo with no issues, an org with no members). In production this kills the pipeline. Fix with `response_actions` — no custom Python needed. See `new-endpoint` step 3A for syntax and examples.

## Add incremental loading

Load only new or updated records each run instead of re-fetching everything. In `rest_api`, declare an incremental cursor on the query parameter the API filters by:

```python
{
    "name": "issues",
    "endpoint": {
        "path": "repos/{owner}/{repo}/issues",
        "params": {
            "since": {                       # the API's "updated since" query param
                "type": "incremental",
                "cursor_path": "updated_at", # field in each record to track
                "initial_value": "2024-01-01T00:00:00Z",
            },
        },
    },
    "primary_key": "id",
    "write_disposition": "merge",            # upsert on primary_key
}
```

Key decisions:
- **cursor query param** (`since`, `updated_since`, `start_date`…): the API parameter that filters server-side — without it the API returns everything and dlt only filters client-side.
- **`cursor_path`**: the field in each record holding the cursor value (e.g. `updated_at`).
- **`initial_value`**: where the first run starts — also how you **expand or shrink the backfill date range**.
- **`write_disposition: "merge"` + `primary_key`**: required so updated records upsert instead of duplicating.

dlt stores the last cursor value in pipeline state and resumes next run — check it with `uv run dlthub local pipeline info <name> -v` (look for `last_value`).

**Ref:** https://dlthub.com/docs/dlt-ecosystem/verified-sources/rest_api/basic#incremental-loading

## Speed and concurrency

Throughput tuning — parallelizing child/independent resources, page size, running resources concurrently — lives in `optimize-rest-api-performance`. Use it once the pipeline loads correctly and you need it faster.

## Configure retry settings for rate-limited APIs

dlt automatically retries HTTP 429 (Too Many Requests) and respects `Retry-After` response headers. The defaults (5 retries, 60s timeout) work for most APIs. For APIs with strict per-minute limits or high request volume, tune in `.dlt/config.toml`:

```toml
[runtime]
request_max_attempts = 10    # retries per request (default: 5)
request_backoff_factor = 1.5 # steeper backoff so waits grow longer (default: 1)
```

**Per-second vs per-minute limits**: if the API sends `Retry-After` headers, dlt uses those values directly — the backoff config is irrelevant. If it doesn't, raise `request_backoff_factor` so the wait grows with each retry and the window has time to reset.

### Slow or heavy responses: increase request_timeout

`request_timeout` (default: 60s) is how long dlt waits for a single HTTP response. Raise it when:
- The API generates a report or aggregation server-side before responding (e.g. analytics export endpoints)
- The endpoint returns large payloads that take time to stream (e.g. bulk export, wide date ranges)
- You see `requests.exceptions.ReadTimeout` or `ConnectionTimeout` in the trace

```toml
[runtime]
request_timeout = 120   # or higher — match the API's documented response time SLA
```

Ref: https://dlthub.com/docs/dlt-ecosystem/verified-sources/rest_api/advanced.md

## Next steps

*If a quick-start path is active, follow that path's sequence instead — this list is for standalone use.*

- Full load complete → hand over to **data-exploration** (`explore-data`) to chart and analyze the data
- Pipeline works but slow (too many requests, slow endpoints) → use `optimize-rest-api-performance` (parallel resources, page size, concurrency)
- Pipeline is memory-heavy or you need stage-level tuning (extract/normalize/load workers, buffers, file rotation) → hand over to the **performance** toolkit → `optimize-performance` (install if not present: `uv run dlthub --non-interactive ai toolkit install performance`)
