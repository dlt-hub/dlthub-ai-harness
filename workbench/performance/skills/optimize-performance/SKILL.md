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
| `[normalize] workers` | 1 (serial) | process pool; raise toward CPU-core count                                                                                                                                      |
| `[normalize] start_method = "spawn"` | — | recommended on Linux when resources use threads                                                                                                                                |
| `[data_writer] file_max_items` / `file_max_bytes` | none | rotate stage outputs so normalize and load each get many files to split across workers — **the lever that parallelizes both**. Global `[data_writer]` rotates **both** stages' outputs at once; scope it to target one — `[sources.data_writer]` (extract output → parallelizes normalize), `[normalize.data_writer]` (normalize output → parallelizes load, see [Load](#load-is-slow-destination-io-bound)) |
| `[normalize.data_writer] disable_compression = true` | off (gzip) | trade disk for CPU when CPU-bound                                                                                                                                              |

Note: the extract writer is scoped under **`[sources.data_writer]`** (or global **`[data_writer]`**) — there is no `[extract.data_writer]` scope; dlt **silently ignores** that one (no error, no effect).

Running *out of memory* during normalize is a different problem with a different fix set → [Out of memory](#out-of-memory-ram-or-disk).

### Out of memory (RAM or disk)

A pipeline that dies on a constrained machine fails one of two ways — the **failure mode tells you which**, and the fixes diverge. Don't guess; read how it died:

| Signal | RAM exhaustion | Disk exhaustion |
|---|---|---|
| How it dies | **killed** — exit **137 / SIGKILL**, pod `OOMKilled`, **no Python traceback** | Python exception with traceback: `OSError: [Errno 28] No space left on device` |
| Killed by | the OS / k8s OOM-killer (RSS hit the cgroup/container limit) | dlt/Python writing intermediate, load-package, or staging files |
| Confirm mid-run | the `progress="log"` memory line (needs `psutil` — see Step 1); for the whole picture see [Tracking memory](#tracking-memory-dev-vs-production) below | `df -h` on the working volume and `$DLT_DATA_DIR`; `du -sh ~/.dlt` and the staging path |

With `progress="log"` on, tie a RAM spike to its stage: extract spiking = pulling the source into memory; normalize spiking = buffering items. A traceback that **isn't** `Errno 28` is a different bug → use `debug-pipeline`.

##### Tracking memory (dev vs production)
The `progress="log"` line reports **main-process RSS**, which is complete for the default serial run but undercounts once `[normalize] workers > 1` (the process pool runs in child processes). How to see the whole picture depends on where you can reach:
- **Dev / staging, with a shell** — `docker stats` / `kubectl top pod` / `top` (sorted by RSS) / cgroup `memory.current` vs `memory.max`. These measure the **whole container**, so they already include the normalize pool.
- **Production, no interactive shell** (the agent isn't attached) — don't rely on ad-hoc commands. Read memory from things emitted by the run itself:
  - **dltHub platform logs** — if the pipeline runs on the dltHub platform, read its logs directly: `dlthub job logs <name>` (latest run), `dlthub job runs logs <name> [run#]` (a specific run), or `-f` to stream. The `progress="log"` memory lines show up here. Ref: https://dlthub.com/docs/hub/pipeline-operations/monitoring
  - **From inside the run** — the `progress="log"` memory line lands in your logs; to capture the whole-tree peak with no external tooling, log the container's cgroup peak at the end of the run (cgroup v2: read `/sys/fs/cgroup/memory.peak`; v1: `memory.max_usage_in_bytes`) — it accounts for all processes in the container.
  - **The OOM-kill itself is a signal** — exit 137 / `OOMKilled` in the pod status or orchestrator events confirms RAM was the cause even with no live metrics.

#### **RAM — bound peak memory:**

| Lever | Default | Effect |
|---|---|---|
| `[data_writer] buffer_max_items` | 5000 | items in RAM before flush; **lower to cut memory** (scope per stage: `[sources.data_writer]` for extract, `[normalize.data_writer]` for normalize; `[data_writer]` for both) |
| yield pages / stream input | — | stream the source (see [Extract](#extract-is-slow-io-bound)) so the **extract** side stays bounded — the load and destination still scale with data (see below) |
| `[data_writer] file_max_items` / `file_max_bytes` | none | rotate files (global scope) so less is held in a single file at once |

Gotcha: `buffer_max_items = 1` forces single-item writes and **disables multithreading** — don't. And **don't cut dlt's `workers` to fix memory** — that usually just slows the run; peak memory is bounded by the levers above and by the destination (next), not by dlt's worker count.

**Cap the destination's own memory — dlt's buffers don't reach it.** Streaming and file rotation bound *dlt's* in-flight memory, but the destination loads with its **own** memory and thread/connection settings — often sized to the machine's total RAM — in or beside the same process. When extract is already fully streamed but the run still OOMs on a constrained box, suspect the destination: dlt's `buffer_max_items`/rotation won't touch it. To fix, cap the destination itself, not dlt's `workers`:
- **Memory limit** — set the destination's own max-memory/heap setting below the container/cgroup limit.
- **Threads / connections** — reduce the destination's concurrent thread or connection count (each holds its own buffers).
- **Insert / batch size** — lower the destination's write batch size.

Check the destination's own config for these knobs (they live in the destination, not in dlt). Capping destination memory and threads typically drops peak RSS several-fold versus running the destination at its RAM-sized defaults — often the single change that keeps a streamed load inside its limit.

Only once **all** of the above are in place — buffers lowered, files rotated, destination capped, fresh pipeline per object — is a genuinely undersized runner a possibility: see [Step 4](#step-4-last-resort--raise-the-instance-size-dlthub-platform) (dltHub platform only).

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
- **Scale up** ([Step 4](#step-4-last-resort--raise-the-instance-size-dlthub-platform)) only if the run is on the dltHub platform and you hit that external ceiling **in the runner's own RAM or vCPU** — never before Steps 1–3 are done, and never without the user's explicit approval (Step 4, Gate 0).
- **Repeat** from Step 1 — the bottleneck often *moves* to another stage after a fix. Apply the next lever one at a time. "Fast enough" is the user's call — a minor improvement may already be enough, so confirm before another round rather than chasing micro-gains.

## Step 4: Last resort — raise the instance size (dltHub platform)

Applies **only** to pipelines running on the dltHub platform, and **only** after Steps 1–3 have been done and re-measured. A bigger runner is not a tuning lever: it is a **recurring cost** charged against your organization's run-time budget by a multiplier, so one hour on `large` spends four hours of budget — every run, forever. A config change is free; a tier bump is not. Reach for it when you have **measured** that the machine, not the pipeline, is the ceiling.

**Reference:** https://dlthub.com/docs/hub/pipeline-operations/job-configuration#instance-size 

| Size | vCPU | Memory | Disk | Budget multiplier |
|---|---|---|---|---|
| `small` (default) | 2 | 4 GiB | 500 GB | 1× |
| `medium` | 4 | 8 GiB | 500 GB | 2× |
| `large` | 8 | 16 GiB | 500 GB | 4× |
| `xlarge` | 16 | 32 GiB | 500 GB | 8× |

Note **disk is 500 GB on every tier** — scaling up never buys disk.

### Gate 0: never change it without the user's explicit permission

**This is a spending decision, not a tuning decision — it is the user's to make, every time.**

Your job is to diagnose and **propose**; never edit `require`, deploy a size change, or raise
`execute={"timeout": ...}` on your own initiative — not when the job is OOM-killed, not when it is timing
out, and not when the user asked you to "just make it work". Ask, and put the budget math in the question:

> "`ingest_orders` runs ~50 min/day on `small` (1×) = ~25 charged hours/month. Peak RSS is 3.8 of 4 GiB and
> it was `OOMKilled` twice. Moving to `medium` (4 vCPU / 8 GiB, **2×**) makes that ~50 charged hours/month
> at the same runtime. Shall I apply it?"

Then **wait for an explicit yes**. Approval covers **one** tier change to **one** job — re-ask for the next
tier, another job, or a later session. Never bundle a size or timeout change into a deploy with other edits.

**Budget break-even, tell the user this:** `small` → `medium` doubles the charge, so it only stays
budget-neutral if wall-clock drops by **≥50%**. A bigger box that doesn't roughly halve the run costs more
budget for the same throughput — worth it for an OOM that has no other fix, rarely worth it for "a bit
faster".

### Gate 1: how to know it's really necessary

Bump only when **all five** are true. If you can't answer one with a number, you haven't finished Step 1–3 — go back rather than up.

1. **The bottleneck is known and its levers are applied.** Step 1 named the stage; Step 2's levers for that stage are set and Step 3 re-measured them. The bottleneck is still the same stage.
2. **You have the number, from the run itself.** Peak RSS or CPU% from the `progress="log"` line (needs `psutil`), read out of `dlthub job logs <name>` — see [Tracking memory](#tracking-memory-dev-vs-production). A remembered "it felt slow" is not evidence.
3. **That number sits at the tier's ceiling.** RAM: peak RSS within ~20% of the tier's memory, or exit **137 / `OOMKilled`** (on `small` that means ~3.3+ GiB of 4 GiB). CPU: the CPU line pegged near 100% with `[normalize] workers` **already** at the tier's vCPU count.
4. **There is headroom the extra hardware can actually use.** You measured a *scaling curve* below the ceiling: raising `[normalize] workers` 1 → 2 (or `[load] workers`) gave a real improvement, so 4 vCPU plausibly extends it. If 1 → 2 gained nothing, 4 vCPU gains nothing either — the limit is elsewhere (one un-rotated file, one resource, the source, the destination).
5. **The cheap fixes are exhausted.** `buffer_max_items` lowered, file rotation set, destination memory/threads/batch-size capped, fresh-pipeline-per-object for many-object loops, `DLT_DATA_DIR` / blob staging for disk, and `execute={"timeout": ...}` raised if the job was cut off rather than starved.

### Anti-signals — do **not** bump

| Symptom | Why a bigger instance won't help | Do instead |
|---|---|---|
| `OSError: [Errno 28] No space left on device` | disk is 500 GB on **all** tiers | [Out of memory → Disk](#disk) — staging to blob, `DLT_DATA_DIR`, `delete_completed_jobs` |
| Extract-bound: waiting on network, pagination, or a rate-limited API | CPU/RAM don't make the source answer faster | [Extract](#extract-is-slow-io-bound) + [Source-specific tuning](#source-specific-tuning-separate-toolkits) |
| Load-bound on destination I/O | the ceiling is the destination, not the runner | [Load](#load-is-slow-destination-io-bound), destination-side capacity |
| Job stopped at a time limit (not `OOMKilled`) | it wasn't starved of resources | `execute={"timeout": "6h", "grace_period": 60}` |
| Peak RSS far below the tier limit (e.g. 1.5 GiB on `small`) | memory isn't the constraint | re-diagnose from Step 1 |
| Normalize slow but extract wrote **one** file | the process pool can't split one file across cores | rotate extract output: `[sources.data_writer] file_max_items` |

### Applying it

Step **one** tier at a time, and pair the bump with the lever that consumes it — **size alone changes nothing**, because `[normalize] workers` defaults to 1 and `[load] workers` to 20 regardless of the box. The instance is a *ceiling*, not a lever:

- **RAM-bound** → one tier up; keep the memory levers in place (a bigger box is not a reason to un-tune `buffer_max_items`).
- **CPU-bound** → one tier up **and** raise `[normalize] workers` to the new vCPU count in the same change.

```python
from dlt.hub import run

@run.pipeline(my_pipeline, require={"instance": {"size": "medium"}})
def heavy_sync():
    ...
```

`require` is a **decorator argument only** — there is no `config.toml` or env-var form, and it needs a `__deployment__.py` manifest plus `dlthub deploy` to take effect. **Only with the approval from Gate 0 in hand**, hand over to **dlthub-platform** (`deploy-workspace`) to edit the manifest and deploy; install it if absent: `uv run dlthub --non-interactive ai toolkit install dlthub-platform`. That toolkit's `rules/job-resources.md` carries the full budget reference and the same permission requirement.

Then **verify the spend is earning its multiplier**: re-read `dlthub job logs <name>` and check peak RSS now fits, or that the stage duration dropped roughly in proportion to the extra vCPU. If it didn't, **drop back to the smaller tier** — you are paying the multiplier for nothing — and return to Step 1.

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
- **Every lever applied and the runner itself is the measured ceiling** (dltHub platform only) → [Step 4](#step-4-last-resort--raise-the-instance-size-dlthub-platform) — pass the gates, **get the user's explicit approval with the budget math**, then hand the manifest change to **dlthub-platform** (`deploy-workspace`).
- **Tuned and stable** → hand over to **dlthub-platform** to deploy and schedule the pipeline on dltHub (install if not present: `uv run dlthub --non-interactive ai toolkit install dlthub-platform`).
