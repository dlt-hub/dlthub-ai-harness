---
name: adjust-endpoint
description: Adjust a working dlt pipeline for production — remove dev limits, verify pagination, configure incremental loading, expand date ranges. Use when the user wants to remove .add_limit(), load more data, fix pagination, or set up incremental loading.
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

## Enable parallelization for dependent resources

If the pipeline has child resources (transformer pattern, e.g. comments per post), add `parallelized: True` to fetch child pages concurrently. Caveat: all child pages for one parent are buffered in memory — skip for parents with very large child sets. See `new-endpoint` step 3A for syntax and the memory caveat.

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
