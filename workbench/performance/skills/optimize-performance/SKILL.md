---
name: optimize-performance
description: Make a dlt pipeline faster or lighter on memory. Use when the user says a pipeline is slow, takes too long, runs out of memory, uses too much RAM, or wants to optimize, speed up, parallelize, or increase throughput. Covers source-agnostic levers (parallelism, workers, buffers, file rotation); for source-specific tuning use the pipeline toolkit's own optimize skill.
argument-hint: "[pipeline-name] [symptom]"
---

# Optimize dlt pipeline performance

dlt runs in three stages — **extract → normalize → load** — each with its own parallelism and memory knobs. Tuning the wrong stage wastes effort, so **diagnose the bottleneck first (Step 1), fix that one stage (Step 2), then re-measure (Step 3)**.

**Essential reading:** https://dlthub.com/docs/reference/performance

Parse `$ARGUMENTS`:
- `pipeline-name` (optional): the dlt pipeline. If omitted, infer from session context; if ambiguous, ask and stop.
- `symptom` (optional): what's wrong — "slow extract", "OOM during normalize", "load takes hours", etc.

> Source-specific knobs (DB backends/`chunk_size`, REST async/concurrency, file format/readers) live in a separate pipeline toolkit — see [Source-specific tuning](#source-specific-tuning-separate-toolkits) for the toolkit to install. Apply those **in addition** to the stage levers here.
>
> Knobs below are shown as `config.toml`; each has an env-var equivalent — see [Config forms](#config-forms). Start from dlt's defaults and change **one lever at a time**.

## Step 1: Diagnose the bottleneck stage

Always measure before changing anything. Enable progress logging and read the per-stage timing:

```toml
# .dlt/config.toml
progress = "log"     # or PROGRESS=log, or dlt.pipeline(..., progress="log")
```

Read durations from `pipeline.last_trace` or via `debug-pipeline` (trace + load packages). Benchmark on a real machine on a **representative** run — shared or resource-constrained environments give unreliable numbers, and a tiny `.add_limit(1)` run distorts the stage ratios (fixed overhead dominates, normalize/load barely run), so don't use it to decide *which* stage is slow. Then route to the slowest stage:

| Bottleneck | Bound by | Go to |
|---|---|---|
| Extract slow | network / source I/O | [Extract](#extract-is-slow-io-bound) + [Source-specific tuning](#source-specific-tuning-separate-toolkits) |
| Normalize slow or OOM | CPU / memory | [Normalize](#normalize-is-slow-or-oom-cpumemory-bound) |
| Load slow | destination I/O | [Load](#load-is-slow-destination-io-bound) |

## Step 2: Fix the bottleneck stage

Jump to the **one** stage Step 1 flagged.

### Extract is slow (I/O-bound)

By default dlt extracts **one resource at a time, one item at a time** — N endpoints/tables are fetched sequentially. Parallelism overlaps those I/O waits, but only helps when multiple slow resources can overlap. **Decide before adding workers:**

1. **Count resources.** One resource → cross-resource threading won't help; look at async-within-it, page size, or another stage. Many → candidate.
2. **Measure per-resource time** (`pipeline.last_trace`, or extract them individually). To probe one resource cheaply, cap it with `.add_limit(max_items=N)` or `.add_limit(max_time=seconds)` and time a few pages — don't extrapolate from a single item, and note `.add_limit()` masks pagination (re-verify before removing it; see `adjust-endpoint`/`adjust-table`). If one resource dominates, parallelizing the rest saves nothing — fix the slow one.
3. **Confirm it's I/O, not CPU.** Threading overlaps waits, not Python compute (see [How parallelism works](#how-parallelism-works)).
4. **Size `workers`** ≈ number of slow resources to overlap. Excess workers idle or trip rate limits.

| Lever | Default | Effect |
|---|---|---|
| `@dlt.resource(parallelized=True)` | off | run the (sync) resource's generator in a worker thread, so resources overlap |
| `async def` resource / async `@dlt.transformer` | concurrent | many awaited items in flight on one event loop — no flag needed |
| `[extract] workers` | 5 | thread-pool size for parallelized sync resources |
| `[extract] max_parallel_items` | 20 | max in-flight items for async resources |
| yield pages, not rows | — | `yield list(islice(it, 1000))` cuts per-item overhead; orthogonal to threading |

Group related resources into a `@dlt.source` (`return (r1, r2, r3)`) so dlt schedules them on a shared thread pool. Scopes for the knobs: global, per-source (`[sources.<name>.extract]`), per-resource.

### Normalize is slow or OOM (CPU/memory-bound)

The usual home of OOM. Normalize uses a **process pool** (CPU-bound), and parallelism across files only works if extract produced **many** files — so rotate files first.

| Lever | Default | Effect |
|---|---|---|
| `[normalize] workers` | 1 (serial) | process pool; raise toward CPU-core count |
| `[normalize] start_method = "spawn"` | — | recommended on Linux when resources use threads |
| `[normalize.data_writer] file_max_items` | none | rotate so one big file → many → parallel normalize/load |
| `[normalize.data_writer] file_max_bytes` | none | rotate by size |
| `[data_writer] buffer_max_items` | 5000 | items in RAM before flush; lower to cut memory, raise to cut disk I/O |
| `[normalize.data_writer] disable_compression = true` | off (gzip) | trade disk for CPU when CPU-bound |

Buffers scope per stage (`[extract.data_writer]`, `[normalize.data_writer]`). Gotcha: `buffer_max_items = 1` forces single-item writes and **disables multithreading** — don't.

### Load is slow (destination I/O-bound)

| Lever | Default | Effect |
|---|---|---|
| `[load] workers` | 20 | thread pool, one file per thread; I/O-bound, safe to raise toward destination capacity |

Load chunk size **is** the normalize `file_max_items`/`file_max_bytes` — smaller files mean smaller transactions and less destination memory pressure. Load parallelism needs multiple files (rotate in the Normalize section); one file = one job, no speedup.

## Source-specific tuning (separate toolkits)

The biggest extraction wins are source-specific and live in the pipeline toolkit for your source — **not in this toolkit**. Pick the row for your source. If you arrived here from that toolkit it is already installed; otherwise install it first, then run its optimize skill:

```
uv run dlthub --non-interactive ai toolkit install <toolkit>
```

| Source | Install toolkit | Then run skill |
|---|---|---|
| REST / HTTP API | `rest-api-pipeline` | `optimize-rest-api-performance` |
| SQL database | `sql-database-pipeline` | `optimize-sql-performance` |
| Files (S3 / GCS / Azure / SFTP / local) | `filesystem-pipeline` | `optimize-filesystem-performance` |

Apply source-specific tuning **in addition** to the stage levers above. These skills live in other toolkits, so always install the toolkit before invoking the skill — never assume it is present.

## Step 3: Re-measure

Re-run with `progress="log"` and compare per-stage durations / peak memory against Step 1. Change **one lever at a time** so you can attribute the effect, and use `debug-pipeline` to confirm no new failures (timeouts, type errors) surfaced under higher concurrency.

## Reference

### How parallelism works
- **Extract & load → threads.** I/O-bound (HTTP, file/destination IO), so the GIL isn't the limit; threading overlaps waits. It does **not** speed up CPU-bound work inside a generator — keep generators thin.
- **Normalize → process pool.** CPU-bound (parsing, type inference, compression); processes bypass the GIL for true parallelism.
- **Async resources → single event loop.** Many concurrent awaits, lightweight, no threads. What runs in parallel: across resources; across in-flight items of an async resource; across parallelized child/transformer pages. A plain resource (no flag, not async) stays serial; item order within one resource is preserved.

### Config forms
Every knob can be set in `.dlt/config.toml` under a section, or as an env var by upper-casing and joining the path with double underscores:
- `[extract] workers = 5` ⇄ `EXTRACT__WORKERS=5`
- `[normalize.data_writer] file_max_items = 100000` ⇄ `NORMALIZE__DATA_WRITER__FILE_MAX_ITEMS=100000`

### Constrained disk / environment
- `DLT_DATA_DIR=/path/to/large/or/mounted/volume` — offload load packages off the working disk.
- `delete_completed_jobs` — reclaim disk after each load.
- `DLT_USE_JSON=simplejson` — only if `orjson` (the fast default) causes issues.

### Advanced: split the work
- `source().decompose(strategy="scc")` — returns sub-sources with independent components; run serially or in parallel.
- Multi-pipeline parallelism (ThreadPoolExecutor / `asyncio.gather`): give each pipeline a **unique name** and instantiate generators inside the worker thread. Never run two same-named pipelines in parallel on one machine (state conflicts). See the performance doc above.

## Next steps

- **Source-level tuning still needed** → [Source-specific tuning](#source-specific-tuning-separate-toolkits) — install the matching pipeline toolkit, then run its optimize skill.
- **Tuned and stable** → hand over to **dlthub-platform** to deploy and schedule the pipeline on dltHub.
