---
name: optimize-performance
description: Make a dlt pipeline faster or lighter on memory. Use when the user says a pipeline is slow, takes too long, runs out of memory, uses too much RAM, or wants to optimize, speed up, parallelize, or increase throughput. Covers source-agnostic levers (parallelism, workers, buffers, file rotation); for source-specific tuning use the pipeline toolkit's own optimize skill. Also decides whether a dltHub platform job genuinely needs a larger instance (more memory/CPU) — the last resort after tuning.
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

**Install `psutil` first** (`pip install psutil` or `uv add psutil`) — then `progress="log"` adds a `Memory usage: … MB (…%) | CPU usage: …%` line per stage; without it dlt warns once (`psutil dependency is not installed and memory stats will not be available`) and omits that line. It's one interface across macOS/Windows/Linux, so the same profiling runs in dev and prod.

Read durations from `pipeline.last_trace` or via `debug-pipeline` (trace + load packages; `debug-pipeline` ships with the calling pipeline toolkit — use it only if that toolkit is installed, otherwise read `last_trace` directly). Benchmark on a real machine — shared or resource-constrained environments give unreliable numbers.

**Tune on a representative subset, not the full dataset.** For time tuning a slice (e.g. a few million of tens of millions of rows) reproduces the stage ratios and lever effects while iterating far faster. Size it in a band: big enough that fixed overhead doesn't dominate **and** that enough files/resources exist for parallelism levers to show (too small → a good lever looks useless; a tiny `.add_limit(1)` fails this floor and `.add_limit()` masks pagination), small enough to iterate. **Reduce volume only once you've confirmed the subset is representative** — it reproduces the full-run stage ratios and clears the floor (>1 file, >1 resource); if you can't confirm that, run the full dataset. Memory/OOM work and the final confirmation always run full volume.

Then route to the slowest stage:

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

| Lever | Default | Effect                                                                                                                                                                         |
|---|---|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `[normalize] workers` | 1 (serial) | process pool; raise toward the **CPU quota you actually have** — read it from the cgroup (`cpu.max` on v2, `cpu.cfs_quota_us ÷ cpu.cfs_period_us` on v1), never from `cpu_count()`, which reports visible CPUs, not your allotment |
| `[normalize] start_method = "spawn"` | — | recommended on Linux when resources use threads                                                                                                                                |
| `[data_writer] file_max_items` / `file_max_bytes` | none | rotate stage outputs so normalize and load each get many files to split across workers — **the lever that parallelizes both**. Global `[data_writer]` rotates **both** stages' outputs at once; scope it to target one — `[sources.data_writer]` (extract output → parallelizes normalize), `[normalize.data_writer]` (normalize output → parallelizes load, see [Load](#load-is-slow-destination-io-bound)) |
| `[normalize.data_writer] disable_compression = true` | off (gzip) | trade disk for CPU when CPU-bound                                                                                                                                              |

Note: the extract writer is scoped under **`[sources.data_writer]`** (or global **`[data_writer]`**) — there is no `[extract.data_writer]` scope; dlt **silently ignores** that one (no error, no effect).

Running *out of memory* during normalize is a different problem with a different fix set → [Out of memory](#out-of-memory-ram-or-disk).

### Out of memory (RAM or disk)

A pipeline that runs out of resources on a constrained machine is short of **RAM** or of **disk**, and the fixes diverge. Don't guess; read how it died. Start from the table, then read the two exceptions under it — RAM does not always announce itself as a kill:

| Signal | RAM exhaustion | Disk exhaustion |
|---|---|---|
| How it dies | usually **no Python traceback** (two exceptions below). Exit **137 / SIGKILL** or pod `OOMKilled` on k8s/Docker. On the **dltHub platform, three signatures — all RAM**: `Runner killed (SIGKILL), exit code: 137` with an out-of-memory note (fast climb), `Runner failed with exit code: 247` after a silent stall, or **no kill at all** (see below) | Python exception with traceback: `OSError: [Errno 28] No space left on device` |
| Killed by | the OS / k8s OOM-killer (RSS hit the cgroup/container limit) | dlt/Python writing intermediate, load-package, or staging files |
| Confirm mid-run | the `progress="log"` memory line (needs `psutil` — see Step 1); for the whole picture see [Tracking memory](#tracking-memory-dev-vs-production) below | `df -h` on the working volume and `$DLT_DATA_DIR`; `du -sh ~/.dlt` and the staging path |

**A job can run out of RAM without dying — and that looks like a hang, not a crash.** It sits with memory parked at the tier's limit, unchanging on every sample, emitting **no progress lines at all**, never killed, until the platform job's `execute.timeout` (its wall-clock limit) expires. Progress output stopped **and** memory at the ceiling is RAM exhaustion: cancel it and tune — don't wait for an exit code and don't raise the timeout. The same config can fail either way on different runs, so never key the diagnosis on the exit code alone.

With `progress="log"` on, tie a RAM spike to its stage: extract spiking = pulling the source into memory; normalize spiking = buffering items.

**A traceback can still be a memory problem — read *whose* memory ran out.** Once the destination has its own memory cap, *its* OOM arrives as a normal Python exception naming the limit (e.g. `_duckdb.OutOfMemoryException: Out of Memory Error: could not allocate block of size …`), wrapped by dlt as `DatabaseTransientException`, retried `max_retry_count` times, then `LoadClientJobRetry` and exit 1. That is the cap you set doing its job — an anonymous kill or stall converted into an attributable error. Fix it by raising the cap (keeping `[load] workers × file size` inside the box) or shrinking the files. A traceback that is neither `Errno 28` nor a destination out-of-memory is a different bug → use `debug-pipeline`.

#### Tracking memory (dev vs production)
The `progress="log"` line reports **main-process RSS**, which is complete for the default serial run but undercounts once `[normalize] workers > 1` (the process pool runs in child processes).

> **It is a floor, not a peak — it is sampled at progress ticks, not continuously.** A spike *inside* a stage (parsing a whole payload, materializing a dataframe) happens between two log lines and never appears. In practice it understates the true peak by **2–3×**, and the gap is worst exactly where it matters — in a stage that allocates in bursts, such as load. **Never conclude "memory is fine" from this line**, and never size an instance down on the strength of it; only an OOM kill, or a peak you sample yourself (the runner exposes no cgroup peak counter — see below), gives you the real high-water mark.

> **The percentage is not your process's share** — dlt prints `rss` for the current process but takes the percentage from `psutil.virtual_memory().percent`, i.e. **system-wide** memory in use, so on a busy laptop an alarming percentage can sit next to a few-hundred-MB process. Never read it as "how close am I to the limit".
>
> **On the dltHub runner it does tell you the tier**, because `/proc/meminfo` there is namespaced to the instance — so "system" *is* your instance, `psutil.virtual_memory().total` is the tier's memory, and `MB ÷ pct` off this line recovers it. Use either to confirm which tier a run actually got: `dlthub deploy --show-manifest` only shows the size you **declared**, and prints no `require` block at all on the default tier.

How to see the whole picture depends on where you can reach:
- **Dev / staging, with a shell** — `docker stats` / `kubectl top pod` / `top` (sorted by RSS) / cgroup `memory.current` vs `memory.max`. These measure the **whole container**, so they already include the normalize pool.
- **Production, no interactive shell** (the agent isn't attached) — don't rely on ad-hoc commands. Read memory from things emitted by the run itself:
  - **dltHub platform logs** — if the pipeline runs on the dltHub platform, read its logs directly: `dlthub job logs <name>` (latest run), `dlthub job runs logs <name> [run#]` (a specific run), or `-f` to stream. The `progress="log"` memory lines show up here. Ref: https://dlthub.com/docs/hub/pipeline-operations/monitoring
  - **From inside the run** — the `progress="log"` memory line lands in your logs; to capture the whole-tree peak with no external tooling, log the container's cgroup peak at the end of the run (cgroup v2: read `/sys/fs/cgroup/memory.peak`; v1: `memory.max_usage_in_bytes`) — it accounts for all processes in the container. **On the dltHub runner neither peak file exists** — it mounts cgroup **v1** with only `memory.limit_in_bytes` and `memory.usage_in_bytes`, so there is no kernel high-water mark: sample `memory.usage_in_bytes` **and** RSS from a ~1 s thread and keep both maxima. They agree while dlt does its own Python work, then diverge once a memory-mapping destination (duckdb) loads, where RSS runs well above what the cgroup charges. **RSS is the alarm; the cgroup figure is what gets you killed** — a run peaking "over" the tier in RSS can still finish.
  - **The OOM-kill itself is a signal** — exit 137 / `OOMKilled` in the pod status or orchestrator events confirms RAM was the cause even with no live metrics.

#### **RAM — bound peak memory:**

| Lever | Default | Effect |
|---|---|---|
| `[data_writer] buffer_max_items` | 5000 | items in RAM before flush; **lower to cut memory** (scope per stage: `[sources.data_writer]` for extract, `[normalize.data_writer]` for normalize; `[data_writer]` for both) |
| yield pages / stream input | — | stream the source (see [Extract](#extract-is-slow-io-bound)) so the **extract** side stays bounded — the load and destination still scale with data (see below) |
| `[data_writer] file_max_items` / `file_max_bytes` | none | rotate files (global scope) so less is held in a single file at once |

Gotcha: `buffer_max_items = 1` forces single-item writes and **disables multithreading** — don't. Cutting `[extract] workers` / `[normalize] workers` to fix memory usually just slows the run — those stages are bounded by the buffer levers above. **`[load] workers` is the exception**: load holds one whole file per thread, so its peak scales with `workers × file size` — see [Load](#load-is-slow-destination-io-bound).

**Cap the destination's own memory — dlt's buffers don't reach it.** Streaming and file rotation bound *dlt's* in-flight memory, but the destination loads with its **own** memory and thread/connection settings — often sized to the machine's total RAM — in or beside the same process. When extract is already fully streamed but the run still OOMs on a constrained box, suspect the destination: dlt's `buffer_max_items`/rotation won't touch it. To fix, cap the destination itself, not dlt's `workers`:
- **Memory limit** — set the destination's own max-memory/heap setting below the container/cgroup limit.
- **Threads / connections** — reduce the destination's concurrent thread or connection count (each holds its own buffers).
- **Insert / batch size** — lower the destination's write batch size.

Check the destination's own config for these knobs (they live in the destination, not in dlt). Capping destination memory and threads typically drops peak RSS several-fold versus running the destination at its RAM-sized defaults — often the single change that keeps a streamed load inside its limit.

Only once **all** the levers in this section are in place — buffers lowered, files rotated, destination capped, and the fresh-pipeline-per-object pattern below where it applies — is a genuinely undersized runner a possibility: see [Step 4](#step-4-last-resort--raise-the-instance-size-dlthub-platform) (dltHub platform only).

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
| `[load] workers` | 20 | thread pool, one file per thread; I/O-bound, safe to raise toward destination capacity — but **bounded by memory**: peak ≈ `workers × file size` (see below) |

Load runs **one file per thread**, so parallelism needs **many normalize-output files**: set `[normalize.data_writer] file_max_items` / `file_max_bytes` to rotate them (one file = one load job = no speedup). Smaller files also mean smaller transactions and less destination memory pressure.

**Load-stage peak RAM ≈ `[load] workers` × file size**, held in Python, *plus* whatever the destination allocates. This bites with `insert_values` (duckdb's default loader format), where each job is a file of SQL text. With wide rows both extremes overflow a small box: one un-rotated file is a single huge job, and rotating without touching `workers` just hands the default 20 threads a file each. Rotation is therefore a *time* lever and a *memory* lever in opposite directions — rotate for parallelism, then set `workers` so `workers × file size` fits the box.

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

Re-run with `progress="log"` and compare per-stage durations against Step 1, plus the peak `Memory usage` line it logs (`last_trace` has timings, not RAM). Change **one lever at a time** so you can attribute the effect, and use `debug-pipeline` to confirm no new failures (timeouts, type errors) surfaced under higher concurrency. **If a lever regresses — slower, higher peak memory, or a new failure — roll it back to its previous value before trying the next**; changing one at a time is what makes this a clean revert.

**Iterate on one stage — skip the full `run()`.** dlt exposes each stage as its own method (`pipeline.extract(source)`, `pipeline.normalize()`, `pipeline.load()`), and each consumes the previous stage's packages. So when tuning a lever, **re-run from the changed stage's input forward, up to the stage you're timing** — not the whole pipeline:

| Lever | Re-run |
|---|---|
| extract parallelism / page size | `extract()` |
| `[normalize] workers`, extract-output rotation | `extract()` → `normalize()` |
| `[load] workers`, normalize-output rotation (parallelizes load) | `extract()` → `normalize()` → `load()` |

Two exceptions — **use a full `run()`**: memory/OOM work (peak RSS is cross-stage and the destination loads with its own memory), and the final confirmation run that re-diagnoses whether the bottleneck moved.

**Stop or repeat — check in, don't loop autonomously.** Report the before/after to the user, then:
- **Stop** when it meets the user's goal (fast enough / fits memory), the last lever gave **no meaningful improvement** (diminishing returns), or you've hit an external ceiling (source throughput, destination limits, disk/network bandwidth) that tuning can't move.
- **Scale up** ([Step 4](#step-4-last-resort--raise-the-instance-size-dlthub-platform)) only if the run is on the dltHub platform and you hit that external ceiling **in the runner's own RAM or vCPU** — never before Steps 1–3 are done, and never without the user's explicit approval ([Step 4](#step-4-last-resort--raise-the-instance-size-dlthub-platform)).
- **Repeat** from Step 1 — the bottleneck often *moves* to another stage after a fix. Apply the next lever one at a time. "Fast enough" is the user's call — a minor improvement may already be enough, so confirm before another round rather than chasing micro-gains.

## Step 4: Last resort — raise the instance size (dltHub platform)

Applies **only** to pipelines on the dltHub platform, and **only** once Steps 1–3 are done and re-measured. A bigger runner is not a tuning lever — it is a **recurring cost** charged against your organization's run-time budget by a multiplier, every run, forever.

**Never change it without the user's explicit permission.** This is a spending decision, not a tuning decision: diagnose and **propose**, never edit `require`, deploy a size change, or raise `execute={"timeout": ...}` on your own initiative — not when the job is OOM-killed, not when it is timing out, not when the user asked you to "just make it work".

Two facts that save a wasted trip: **disk is the same on every tier**, so scaling up never fixes `Errno 28`; and each step **doubles** the charge, so it must roughly **halve** wall-clock to break even.

**When Steps 1–3 are genuinely exhausted and the runner itself is the measured ceiling, read [instance-sizing.md](instance-sizing.md)** — gates, anti-signals, the budget-math question to ask, and how to apply the change. Do not read it earlier; "raise the instance size" is not an option until the gates there pass.

**Reference:** https://dlthub.com/docs/hub/pipeline-operations/job-configuration#instance-size

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
- `[data_writer] file_max_items = 100000` ⇄ `DATA_WRITER__FILE_MAX_ITEMS=100000`

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
- **Every lever applied and the runner itself is the measured ceiling** (dltHub platform only) → [Step 4](#step-4-last-resort--raise-the-instance-size-dlthub-platform), then [instance-sizing.md](instance-sizing.md) — pass the gates there, **get the user's explicit approval with the budget math**, then hand the manifest change to **dlthub-platform** (`deploy-workspace`).
- **Tuned and stable** → hand over to **dlthub-platform** to deploy and schedule the pipeline on dltHub (install if not present: `uv run dlthub --non-interactive ai toolkit install dlthub-platform`).
