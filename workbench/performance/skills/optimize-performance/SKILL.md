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
| Normalize slow (CPU) | CPU | [Normalize](#normalize-is-slow-cpu-bound) |
| Out of memory / killed, or disk full | RAM **or** disk | [Out of memory](#out-of-memory-ram-or-disk) |
| Load slow | destination I/O | [Load](#load-is-slow-destination-io-bound) |

## Step 2: Fix the bottleneck

Jump to the **one** section Step 1 flagged. Memory isn't a stage — it's a separate failure mode with its own section.

### Extract is slow (I/O-bound)

By default dlt extracts **one resource at a time, one item at a time** — N endpoints/tables are fetched sequentially. Parallelism overlaps those I/O waits, but only helps when multiple slow resources can overlap. **Decide before adding workers:**

1. **Count resources.** One resource → cross-resource threading won't help; look at async-within-it, page size, or another stage. Many → candidate.
2. **Measure per-resource time** (`pipeline.last_trace`, or extract them individually). To probe one resource cheaply, cap it with `.add_limit(max_items=N)` or `.add_limit(max_time=seconds)` and time a few pages — don't extrapolate from a single item, and note `.add_limit()` masks pagination (re-verify before removing it; see `adjust-endpoint`/`adjust-table`). If one resource dominates, parallelizing the rest saves nothing — fix the slow one.
3. **Confirm it's I/O, not CPU.** Threading overlaps waits, not Python compute (see [How parallelism works](#how-parallelism-works)).
4. **Size `workers`** ≈ number of slow resources to overlap. Excess workers idle or trip rate limits.

| Lever | Default | Effect |
|---|---|---|
| `@dlt.resource(parallelized=True)` | off | run the (sync) resource's generator in a worker thread, so resources overlap |
| `@dlt.defer` on a per-item fn, then `yield fn(item)` | — | run per-item work (e.g. one HTTP request per item, inside a transformer) concurrently in the extract thread pool — the sync alternative to `async` |
| `async def` resource / async `@dlt.transformer` | concurrent | many awaited items in flight on one event loop — no flag needed |
| `[extract] workers` | 5 | thread-pool size for parallelized sync resources |
| `[extract] max_parallel_items` | 20 | max in-flight items for async resources |
| yield pages, not rows | — | `yield list(islice(it, 1000))` cuts per-item overhead; orthogonal to threading |

Group related resources into a `@dlt.source` (`return (r1, r2, r3)`) so dlt schedules them on a shared thread pool. Scopes for the knobs: global, per-source (`[sources.<name>.extract]`), per-resource.

### Normalize is slow (CPU-bound)

Normalize runs a **process pool with one worker per extract file** — so more workers only help if **extract produced many files**. Key rule: each stage's `data_writer` rotates the files it *writes* (= the next stage's input), so **rotate extract output to parallelize normalize; rotate normalize output to parallelize load**.

| Lever | Default | Effect |
|---|---|---|
| `[normalize] workers` | 1 (serial) | process pool; raise toward CPU-core count |
| `[normalize] start_method = "spawn"` | — | recommended on Linux when resources use threads |
| `[extract.data_writer] file_max_items` / `file_max_bytes` | none | **rotate the _extract_ output** so normalize has many files to split across workers — this is what actually parallelizes normalize (or set it globally under `[data_writer]`) |
| `[normalize.data_writer] disable_compression = true` | off (gzip) | trade disk for CPU when CPU-bound |

> Note: `[normalize.data_writer] file_max_items` rotates normalize's *output*, which parallelizes the **load** stage — **not** normalize. See [Load](#load-is-slow-destination-io-bound).

(Running *out of memory* during normalize is a different problem with a different fix set → [Out of memory](#out-of-memory-ram-or-disk).)

### Out of memory (RAM or disk)

A pipeline that dies on a constrained machine fails one of two ways — the **failure mode tells you which**, and the fixes diverge. Don't guess; read how it died:

| Signal | RAM exhaustion | Disk exhaustion |
|---|---|---|
| How it dies | **killed** — exit **137 / SIGKILL**, pod `OOMKilled`, **no Python traceback** | Python exception with traceback: `OSError: [Errno 28] No space left on device` |
| Killed by | the OS / k8s OOM-killer (RSS hit the cgroup/container limit) | dlt/Python writing intermediate, load-package, or staging files |
| Confirm mid-run | `kubectl top pod` / `docker stats` / RSS in `top`; cgroup `memory.current` vs `memory.max` | `df -h` on the working volume and `$DLT_DATA_DIR`; `du -sh ~/.dlt` and the staging path |

With `progress="log"` on, tie a RAM spike to its stage: extract spiking = pulling the source into memory; normalize spiking = buffering items. A traceback that **isn't** `Errno 28` is a different bug → use `debug-pipeline`.

#### **RAM — bound peak memory:**

| Lever | Default | Effect |
|---|---|---|
| `[data_writer] buffer_max_items` | 5000 | items in RAM before flush; **lower to cut memory** (scope per stage: `[extract.data_writer]`, `[normalize.data_writer]`) |
| yield pages / stream input | — | stream the source (see [Extract](#extract-is-slow-io-bound)) so the **extract** side stays bounded — the load and destination still scale with data (see below) |
| `file_max_items` / `file_max_bytes` | none | rotate extract/normalize output (`[extract.data_writer]` / `[normalize.data_writer]`) so less is held in flight at once |

Gotcha: `buffer_max_items = 1` forces single-item writes and **disables multithreading** — don't. And **don't cut dlt's `workers` to fix memory** — that usually just slows the run; peak memory is bounded by the levers above and by the destination (next), not by dlt's worker count.

**Cap the destination's own memory — dlt's buffers don't reach it.** Streaming and file rotation bound *dlt's* in-flight memory, but the destination loads with its **own** memory and thread/connection settings — often sized to the machine's total RAM — in or beside the same process. On a constrained box this is frequently the real OOM source **even when extract is fully streamed**, and dlt's `buffer_max_items`/rotation won't change it. Cap the destination itself — its memory limit, thread/connection count, or insert/batch size (check the destination's own config) — rather than touching dlt's `workers`. Measured on a constrained run, the *same* streamed load peaked **~1.9 GB with the destination at defaults vs ~0.5 GB after capping the destination's memory and threads** — nearly 4× lower for one setting change.

**Many-object loops — use a fresh pipeline per object.** Reusing one `pipeline` object across many `run()` calls grows its in-memory state (schema deltas, load packages, cursor values) run-over-run, which can OOM a long job. Create a **fresh pipeline per object** and drop it when done:

```python
for obj in objects:
    pipe = dlt.pipeline(pipeline_name=f"load_{obj}", destination=..., dataset_name=...)
    pipe.run(source_for(obj))
    del pipe
```
Caveat: trades away cross-run convenience, and `pipeline.default_schema.tables` keeps every table ever loaded under a given pipeline name — track the object list explicitly.

#### **Disk** 
Stop intermediate/staging files filling the volume: see [Constrained disk / environment](#constrained-disk--environment) — point `DLT_DATA_DIR` at a bigger volume, stage to blob, set `delete_completed_jobs`, and keep compression **on** (don't `disable_compression`).

### Load is slow (destination I/O-bound)

| Lever | Default | Effect |
|---|---|---|
| `[load] workers` | 20 | thread pool, one file per thread; I/O-bound, safe to raise toward destination capacity |

Load runs **one file per thread**, so parallelism needs **many normalize-output files**: set `[normalize.data_writer] file_max_items` / `file_max_bytes` to rotate them (one file = one load job = no speedup). Smaller files also mean smaller transactions and less destination memory pressure.

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

## Step 3: Re-measure, then repeat

Re-run with `progress="log"` and compare per-stage durations / peak memory against Step 1. Change **one lever at a time** so you can attribute the effect, and use `debug-pipeline` to confirm no new failures (timeouts, type errors) surfaced under higher concurrency.

**Stop or repeat — check in, don't loop autonomously.** Report the before/after to the user, then:
- **Stop** when it meets the user's goal (fast enough / fits memory), the last lever gave **no meaningful improvement** (diminishing returns), or you've hit an external ceiling (source throughput, destination limits, disk/network bandwidth) that tuning can't move.
- **Repeat** from Step 1 — the bottleneck often *moves* to another stage after a fix. Apply the next lever one at a time. "Fast enough" is the user's call — a minor improvement may already be enough, so confirm before another round rather than chasing micro-gains.

## Reference

### How parallelism works
- **Extract & load → threads.** I/O-bound (HTTP, file/destination IO), so the GIL isn't the limit; threading overlaps waits. It does **not** speed up CPU-bound work inside a generator — keep generators thin.
- **Normalize → process pool.** CPU-bound (parsing, type inference, compression); processes bypass the GIL for true parallelism.
- **Async resources → single event loop.** Many concurrent awaits, lightweight, no threads. What runs in parallel: across resources; across in-flight items of an async resource; across parallelized child/transformer pages. A plain resource (no flag, not async) stays serial; item order within one resource is preserved.
- **`@dlt.defer` → thread pool (sync alternative to async).** Decorate a per-item function and `yield` its calls so dlt runs them concurrently in the extract thread pool — ideal for per-item I/O in a transformer (e.g. one request per parent) without rewriting to `async`. Sized by `[extract] workers` / `max_parallel_items`, same as `parallelized=True`.

```python
@dlt.transformer
def details(items):
    @dlt.defer                                  # runs in the extract thread pool
    def fetch(item):
        return requests.get(item["url"]).json()
    for item in items:
        yield fetch(item)                       # calls run concurrently
```
See the transformers example: https://dlthub.com/docs/examples/transformers

### Config forms
Every knob can be set in `.dlt/config.toml` under a section, or as an env var by upper-casing and joining the path with double underscores:
- `[extract] workers = 5` ⇄ `EXTRACT__WORKERS=5`
- `[normalize.data_writer] file_max_items = 100000` ⇄ `NORMALIZE__DATA_WRITER__FILE_MAX_ITEMS=100000`

### Constrained disk / environment
- `DLT_DATA_DIR=/path/to/large/or/mounted/volume` — offload load packages off the working disk.
- **If local disk is the constraint** (staging files filling a small pod/local disk alongside the source data, especially with warehouse destinations like Snowflake/BigQuery/Redshift) — suggest pointing the staging destination at remote object storage instead, e.g. `dlt.pipeline(..., staging=dlt.destinations.filesystem(bucket_url="s3://.../stage"))`. Only worth it when disk space is actually the problem.
- `delete_completed_jobs` — reclaim disk after each load.
- `DLT_USE_JSON=simplejson` — only if `orjson` (the fast default) causes issues.

### Advanced: split the work
- `source().decompose(strategy="scc")` — returns sub-sources with independent components; run serially or in parallel.
- Multi-pipeline parallelism (ThreadPoolExecutor / `asyncio.gather`): give each pipeline a **unique name** and instantiate generators inside the worker thread. Never run two same-named pipelines in parallel on one machine (state conflicts). See the performance doc above.

## Next steps

- **Source-level tuning still needed** → [Source-specific tuning](#source-specific-tuning-separate-toolkits) — install the matching pipeline toolkit, then run its optimize skill.
- **Tuned and stable** → hand over to **dlthub-platform** to deploy and schedule the pipeline on dltHub (install if not present: `uv run dlthub --non-interactive ai toolkit install dlthub-platform`).
