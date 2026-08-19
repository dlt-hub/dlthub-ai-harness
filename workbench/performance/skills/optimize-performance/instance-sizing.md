# Last resort: raise the instance size (dltHub platform)

> Read this **only** after Steps 1–3 of [SKILL.md](SKILL.md) are done and re-measured, and only for a pipeline running on the dltHub platform. Every change here is a **spending** decision gated on the user's explicit approval (Gate 0).

A bigger runner is not a tuning lever: it is a **recurring cost** charged against your organization's run-time budget by a multiplier, so one hour on `large` spends four hours of budget — every run, forever. A config change is free; a tier bump is not. Reach for it when you have **measured** that the machine, not the pipeline, is the ceiling.

Tiers step `small` → `medium` → `large` → `xlarge`, doubling vCPU and memory each step and doubling the budget multiplier with them (`small` is the default at 1×). **Read the current numbers from the reference below, or from `deploy-workspace` (`advanced-patterns.md`) if that toolkit is installed — never quote tiers or multipliers from memory**, since instance sizing is in public preview.

**Reference:** https://dlthub.com/docs/hub/pipeline-operations/job-configuration#instance-size

## Gate 0: never change it without the user's explicit permission

Diagnose and **propose**; never edit `require`, deploy a size change, or raise `execute={"timeout": ...}` on your own initiative — not when the job is OOM-killed, not when it is timing out, and not when the user asked you to "just make it work". Ask, and put the budget math in the question:

> "`ingest_orders` runs ~50 min/day on `small` (1×) = ~25 charged hours/month. Peak RSS is 3.8 of 4 GiB and it was `OOMKilled` twice. Moving to `medium` (4 vCPU / 8 GiB, **2×**) makes that ~50 charged hours/month at the same runtime. Shall I apply it?"

Then **wait for an explicit yes**. Approval covers **one** tier change to **one** job — re-ask for the next tier, another job, or a later session. Never bundle a size or timeout change into a deploy with other edits. And say what the multiplier buys: a bump that doesn't roughly halve wall-clock costs more budget for the same throughput — worth it for an OOM with no other fix, rarely worth it for "a bit faster".

## Gate 1: how to know it's really necessary

Bump only when **all five** are true. If you can't answer one with a number, you haven't finished Step 1–3 — go back rather than up.

1. **The bottleneck is known and its levers are applied.** Step 1 named the stage; Step 2's levers for that stage are set and Step 3 re-measured them. The bottleneck is still the same stage.
2. **You have the number, from the run itself.** Peak RSS or CPU% from the `progress="log"` line (needs `psutil`), read out of `dlthub job logs <name>` — see [Tracking memory](SKILL.md#tracking-memory-dev-vs-production). A remembered "it felt slow" is not evidence. **That line is a sampled floor, so a low reading disproves nothing** — for RAM, the kill itself and a peak you sample yourself are the trustworthy signals.
3. **That number sits at the tier's ceiling.** RAM: the job hit the limit — `exit code: 137` with an out-of-memory note, `exit code: 247` after a silent stall, **or a hang with memory pinned at the ceiling and no progress lines** (all three are RAM) — or a self-sampled peak within ~20% of the tier's memory (look that memory up; don't assume it). **Judge it on the cgroup figure, not RSS**: RSS overstates what the limiter charges once a memory-mapping destination like duckdb is loading, so a run can sample an RSS peak apparently *over* its tier and still complete — read a high RSS as "finish the tuning", not "buy a bigger box". How to sample both, and how to confirm which tier the run actually got: [Tracking memory](SKILL.md#tracking-memory-dev-vs-production). CPU: the CPU line pegged near 100% with `[normalize] workers` **already** at the tier's vCPU count.
4. **There is headroom the extra hardware can actually use.**
   - *CPU-bound*: you measured a *scaling curve* below the ceiling — raising `[normalize] workers` 1 → 2 (or `[load] workers`) gave a real improvement, so more vCPU plausibly extends it. If 1 → 2 gained nothing, 4 vCPU gains nothing either — the limit is elsewhere (one un-rotated file, one resource, the source, the destination).
   - *RAM-bound*: there is no scaling curve to measure, so you need the **requirement**, measured on a box comparable to the runner. Two traps: a laptop reading understates it badly (macOS compresses inactive pages, so the same code needs far more on a Linux runner), and an in-memory step **amplifies** the nominal data size severalfold — materialize, then an arrow copy, then a global sort, each holding its own copy. Size from the amplified peak, not from the payload, or the tier you buy will OOM too.
5. **The cheap fixes are exhausted.** `buffer_max_items` lowered, file rotation set, destination memory/threads/batch-size capped, `[load] workers` sized so `workers × file size` fits the box (capping the destination alone does **not** bound the load stage), fresh-pipeline-per-object for many-object loops, `DLT_DATA_DIR` / blob staging for disk, and `execute={"timeout": ...}` raised if the job was cut off rather than starved — that one is **also** permission-gated (Gate 0), so propose it, don't apply it.

## Anti-signals — do **not** bump

| Symptom | Why a bigger instance won't help | Do instead |
|---|---|---|
| `OSError: [Errno 28] No space left on device` | disk is the same on **all** tiers | [Out of memory → Disk](SKILL.md#disk) — staging to blob, `DLT_DATA_DIR`, `delete_completed_jobs` |
| Extract-bound: waiting on network, pagination, or a rate-limited API | CPU/RAM don't make the source answer faster | [Extract](SKILL.md#extract-is-slow-io-bound) + [Source-specific tuning](SKILL.md#source-specific-tuning-separate-toolkits) |
| Load-bound on destination I/O | the ceiling is the destination, not the runner | [Load](SKILL.md#load-is-slow-destination-io-bound), destination-side capacity |
| Job stopped at a time limit (not `OOMKilled`, and memory **not** at the ceiling) | it wasn't starved of resources | **propose** (Gate 0) `execute={"timeout": "6h"}`, or `execute={"timeout": {"timeout": 7200, "grace_period": 60}}` for a custom grace period (`grace_period` nests **inside** `timeout`) |
| Job **hangs** — no progress lines for minutes, memory pinned at the tier ceiling, no exit code | this **is** RAM exhaustion wearing a timeout's clothes; it would burn the whole timeout without ever being killed | cancel it and tune ([Out of memory](SKILL.md#out-of-memory-ram-or-disk)) — do **not** raise `execute.timeout`, and do not read "it wasn't killed" as "memory was fine" |
| Job **completes** and never comes near the limit (checked against a cgroup peak, not the sampled log line) | memory isn't the constraint | re-diagnose from Step 1 |
| Normalize slow but extract wrote **one** file | the process pool can't split one file across cores | rotate extract output: `[sources.data_writer] file_max_items` |

## Applying it

Step **one** tier at a time, and pair the bump with the lever that consumes it — **size alone changes nothing**, because `[normalize] workers` defaults to 1 and `[load] workers` to 20 regardless of the box. The instance is a *ceiling*, not a lever:

- **RAM-bound** → one tier up; keep the memory levers in place (a bigger box is not a reason to un-tune `buffer_max_items`).
- **CPU-bound** → one tier up **and** raise `[normalize] workers` to the new vCPU count in the same change.

```python
from dlt.hub import run

@run.pipeline(my_pipeline, require={"instance": {"size": "medium"}})
def heavy_sync():
    ...
```

`require` is a **decorator argument only** — there is no `config.toml` or env-var form, and it needs a `__deployment__.py` manifest plus `dlthub deploy` to take effect. **Only with the approval from Gate 0 in hand**, hand over to **dlthub-platform** (`deploy-workspace`) to edit the manifest and deploy; install it if absent: `uv run dlthub --non-interactive ai toolkit install dlthub-platform`. That toolkit's always-loaded **job resources and run-time budget** rule carries the full budget reference and the same permission requirement.

Then **verify the spend is earning its multiplier**: re-read `dlthub job logs <name>` and check peak RSS now fits, or that the stage duration dropped roughly in proportion to the extra vCPU. If it didn't, **propose dropping back to the smaller tier** — you are paying the multiplier for nothing — and return to Step 1. **A bump can fail outright** — an OOM driven by an un-chunkable in-memory step is killed on the bigger tier too, because the amplified requirement outran that tier as well. When that happens the answer is the workload (split it, avoid the copies, chunk the operation), **not** the next tier up — and climbing tiers on a guess needs a fresh Gate 0 approval each step anyway.

Confirm the tier actually changed from the run itself: memory via `cgroup memory.limit_in_bytes` / `/proc/meminfo MemTotal` / `psutil.virtual_memory().total`, and CPU via the cgroup **quota** — `cpu.cfs_quota_us ÷ cpu.cfs_period_us` (v1) or `cpu.max` (v2). Both halves double with each step, so both should show it.

**Never read CPU from `cpu_count()`**: on a sandboxed runner it reports visible logical CPUs, which stay the same across tiers and tell you nothing about your allotment. The quota is authoritative, and a fixed-work process-pool benchmark (same work per process, rising process count — wall time stays flat up to the usable cores, then climbs) agrees with the quota. The enforced quota can also be **lower than the advertised vCPU number**, so size `[normalize] workers` from the quota you read, not from the tier table — on the smallest tier that can already be the default of 1, where raising it buys nothing. Lowering a tier is a resource change like raising one: recommend it, let the user decide (Gate 0).
