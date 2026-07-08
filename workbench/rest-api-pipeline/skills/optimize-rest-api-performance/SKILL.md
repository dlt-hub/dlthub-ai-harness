---
name: optimize-rest-api-performance
description: Speed up a dlt REST API pipeline. Use when a REST/HTTP API pipeline is slow because of many sequential requests, nested child resources, or large responses, and the user wants higher throughput — parallelize resources, use async, tune page size and concurrency. For removing .add_limit(), fixing pagination, first-time incremental/merge setup, or retry/backoff on 429 / rate-limit errors use adjust-endpoint instead.
argument-hint: "[pipeline-name] [symptom]"
---

# Optimize REST API extraction

Source-specific tuning for `rest_api` pipelines. REST extraction is almost always network-bound, so the wins come from issuing more requests concurrently and fetching fewer, larger pages. Work the loop — **diagnose → pick the fix → apply → measure → repeat**, one change at a time. Combine these with the source-agnostic stage levers in the **performance** toolkit's `optimize-performance` skill.

**Essential reading:** https://dlthub.com/docs/dlt-ecosystem/verified-sources/rest_api/advanced

Parse `$ARGUMENTS`:
- `pipeline-name` (optional): the dlt pipeline. If omitted, infer from session context; if ambiguous, ask and stop.
- `symptom` (optional): e.g. "thousands of sequential requests", "child resources are slow", "large pages time out".

## 1. Diagnose

- **Measure first.** Read per-resource extract time from `pipeline.last_trace` (or `progress="log"`). To probe one resource cheaply, cap it with `.add_limit(max_items=N)` / `.add_limit(max_time=seconds)` and time a few pages — don't extrapolate from a single item.
- **Gate — verify pagination before adding concurrency.** Auto-detected paginators can loop or stall, and more concurrency just stalls faster. Confirm every resource has an explicit `"paginator"` first (see `adjust-endpoint`).
- **Name the bottleneck:** too many sequential requests across endpoints? one request per parent item (a child resource)? many tiny pages? connection/TLS overhead on many small requests? or huge responses where you only need part of the payload?

## 2. Pick the fix

Match the symptom to a lever. They **compose** — apply every one that fits (a pipeline is often slow for several reasons); just don't tune what isn't the bottleneck.

| Symptom | Fix (see Apply) |
|---|---|
| One request per parent item (child/dependent resource dominates) | Parallelize the child resource |
| Many tiny pages / too many round-trips | Increase page size |
| Many independent endpoints run one-after-another | Run resources concurrently |
| Many small requests — per-request connection/TLS overhead | Reuse a shared HTTP session |
| Large responses; you only need part of each, or high parse memory | Extract just that with `data_selector` |

## 3. Apply

**Parallelize a child resource** — fetch children concurrently (transformer pattern, e.g. comments per post):
```python
{
    "name": "comments",
    "endpoint": {"path": "posts/{post_id}/comments", ...},
    "parallelized": True,
}
```
Memory caveat: all child pages for one parent are buffered in memory — skip for parents with very large child sets. See `new-endpoint` step 3A for the transformer syntax.

**Increase page size** — fewer, larger pages = fewer round-trips:
```python
"endpoint": {"params": {"per_page": 100}}   # use the API's documented max
```

**Run resources concurrently** — independent top-level (list) endpoints extract in parallel via the extract thread pool; size it in `optimize-performance` (`[extract] workers`).

For `rest_api`, parallelize top-level resources at the **source level** — the `parallelized=True` kwarg on `rest_api_source(...)`, or `.parallelize()` on each resource:
```python
source = rest_api_source(
    {"client": {"base_url": "https://api.example.com"}, "resources": ["repos", "issues"]},
    parallelized=True,                       # parallelizes the top-level list endpoints
)
# equivalently: src = rest_api_source(cfg); [src.resources[n].parallelize() for n in ("repos", "issues")]
```

For custom Python resources, pick one:
```python
@dlt.resource(parallelized=True)      # sync generator runs in the extract thread pool
def repos(): yield from fetch_repos()

@dlt.resource                         # @dlt.defer: fan out one call per item
def issues():
    @dlt.defer
    def get(repo): return requests.get(repo["issues_url"]).json()
    for repo in repo_list: yield get(repo)

@dlt.resource                         # async: many awaits concurrent on one event loop
async def stars():
    async for page in fetch_pages(): yield page
```

**Reuse a shared HTTP session** — pool connections so each request skips the TCP/TLS handshake; share one session across threads for concurrent resources:
```python
import requests
session = requests.Session()
config = {"client": {"base_url": "<url>", "session": session}}   # rest_api client config
```

**Extract only what you need — `data_selector`** — a JSONPath that pulls just the records from each response, so dlt skips parsing irrelevant fields (less CPU and memory):
```python
"endpoint": {"path": "posts", "data_selector": "results.items"}
```
For rows the API can't filter server-side, drop them early with `processing_steps` (`add_filter`) so they never reach normalize/load.

## 4. Measure, then repeat

- Re-run and compare per-resource time in `pipeline.last_trace` against step 1.
- **Watch rate limits:** more concurrency hits 429s sooner. dlt retries HTTP 429 and respects `Retry-After`; for strict limits tune `[runtime] request_max_attempts` / `request_backoff_factor` / `request_timeout` (see `adjust-endpoint`), and back off concurrency if it 429s persistently.
- **Stop or repeat — check in, don't loop autonomously.** Report the before/after to the user, then:
  - **Stop** when it meets the user's goal (fast enough), the last lever gave **no meaningful improvement** (diminishing returns), or you've hit an external ceiling (API rate limits) that tuning can't move.
  - **Repeat** with the next matching lever, one at a time. "Fast enough" is the user's call — a minor improvement may already be enough, so confirm before another round rather than chasing micro-gains.

## Next steps

- **Stage-level tuning (workers, buffers, normalize/load parallelism, memory)** → hand over to the **performance** toolkit → `optimize-performance` (install if not present: `uv run dlthub --non-interactive ai toolkit install performance`).
- **Loops, stalls, or errors under concurrency** → use `debug-pipeline`.
- **Tuned and stable** → hand over to **dlthub-platform** to deploy (install if not present: `uv run dlthub --non-interactive ai toolkit install dlthub-platform`).
