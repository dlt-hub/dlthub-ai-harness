---
name: pricing-estimation
description: "Estimate what a dltHub workspace will cost per month on pay-as-you-go (PAYG) pricing, from the jobs the customer deployed in their trial workspace: how often each job runs, how long its runs take and which instance size it uses. Use when the user asks what their pipelines or jobs will cost, how much dltHub will cost per month, what their bill or spend will be, how many runtime hours they use, or wants a PAYG estimate, a cost range, or ways to lower the cost. Do NOT use to change a job's schedule, instance size or timeout (deploy-workspace), or to make a slow job faster (performance toolkit, optimize-performance)."
---

# Pricing estimation (PAYG)

Turn the customer's trial workspace into a **predictable** monthly bill: a per-job table, an
expected-to-high range, and the cheapest ways to lower it. Output is markdown tables, inline.

## Price (single source of truth)

- **$10 per runtime hour** on pay-as-you-go. No base fee, no included hours, no volume tiers, no
  bundles, no discounts.
- Charged hours = **wall-clock hours × instance-size multiplier**. Read the multipliers from
  https://dlthub.com/docs/hub/pipeline-operations/job-configuration#instance-size — never quote
  them from memory. A job with no `instance` set runs on the smallest tier.
- Current pricing: https://dlthub.com/pricing

## Step 1: Read the workspace

Run from the project root. **Jobs are the scheduled unit, not pipelines** — a pipeline split into
several jobs gives several rows.

```sh
uv run dlthub --non-interactive job list                 # jobs and their triggers
uv run dlthub --non-interactive job runs list <job>      # recent runs, status and timing
uv run dlthub --non-interactive job runs info <job> <n>  # one run's timing, if the list lacks it
uv run dlthub --non-interactive deploy --show-manifest   # require.instance.size per job
```

CLI reference: https://dlthub.com/docs/hub/command-line-interface.md

Per job, collect:

| Field | How |
|---|---|
| Runs per day | From the trigger: every 5 min → 288, every 15 min → 96, hourly → 24, every 2 h → 12, every 6 h → 4, every 12 h → 2, daily → 1; for cron, count fires per day |
| Typical run | Median duration of recent **successful** runs, in minutes |
| Slow run | 90th-percentile duration of the same runs; with fewer than 5 runs use the shortest and longest run and say so |
| Instance size | From the manifest; none set = smallest tier |

- **Failed runs** are left out of the durations. Say how many were dropped.
- **Job triggered by another job** runs at the upstream job's cadence.

## Step 2: Ask only for the gaps

Ask the customer when a job has **no successful runs**, is **manual-only**, or **nothing is
deployed yet**: how long a run takes and how often it should run in production. Mark those rows
*customer assumption*.

**Never guess a duration.** Every number depends on it. The only exception: the customer
explicitly waves it off ("assume something light") — then pick a value, state it in the
assumptions, and flag it to verify.

## Step 3: Compute

Per job:

1. `runs_month = runs_per_day × 30`
2. `hours_expected = runs_month × typical_min / 60 × multiplier`
3. `hours_high = runs_month × slow_min / 60 × multiplier`
4. `cost = hours × $10`

Total = sum over jobs, for expected and high. Round hours to 1 decimal, dollars to 2. Do the
arithmetic in a scratch Python block; don't show the code unless asked.

## Step 4: Present

Keep prose minimal. In this order:

1. **Assumptions** — jobs found, where each number came from (workspace or customer), the rate,
   the multipliers used.
2. **Per-job table** — job, cadence, runs/month, typical / slow run, size, hours/month,
   $/month (expected).
3. **Monthly range** — "Your bill should land between $<expected> and $<high> per month." This
   is the predictability message: a ceiling, not a single guess.
4. **What-if cadence ladder** — each job's monthly cost at every 15 min / hourly / every 6 h /
   daily. Skip cadences that make no sense for the job.
5. **Ways to cut cost** — each with its dollar saving per month:
   - run less often (from the ladder)
   - smaller instance, only if the job fits in it — runs may get longer, so say so
   - incremental loading, so each run moves less data and finishes sooner
   - merge small jobs that run at the same cadence, to save per-run startup time

   For making runs faster, hand over to the **performance** toolkit (`optimize-performance`);
   install it if absent: `uv run dlthub --non-interactive ai toolkit install performance`.
   **Only propose.** Never change a schedule, instance size or timeout yourself — those spend
   budget on every run and need the user's explicit yes (see the `job-resources` rule of
   **dlthub-platform**).
6. **Caveats**
   - Trial data volumes may differ from production.
   - A first backfill runs longer than steady-state runs; the estimate covers steady state.
   - Jobs don't pause automatically.

## Worked example

Workspace with 3 jobs. Multipliers assumed from the docs: small 1×, medium 2×.

**Assumptions:** 3 jobs read from the workspace; durations from the last 20 successful runs;
$10/runtime hour; small 1×, medium 2×.

| Job | Cadence | Runs/month | Typical / slow run | Size | Hours/month | $/month |
|---|---|---|---|---|---|---|
| orders_sync | every 15 min | 2,880 | 2 / 3 min | small (1×) | 96.0 | $960.00 |
| crm_hourly | hourly | 720 | 5 / 8 min | medium (2×) | 120.0 | $1,200.00 |
| warehouse_daily | daily | 30 | 20 / 30 min | small (1×) | 10.0 | $100.00 |
| **Total** | | | | | **226.0** | **$2,260.00** |

**Your bill should land between $2,260.00 and $3,510.00 per month** (high = slow runs:
144.0 + 192.0 + 15.0 = 351.0 hours).

| Job | Every 15 min | Hourly | Every 6 h | Daily |
|---|---|---|---|---|
| orders_sync | **$960.00** | $240.00 | $40.00 | $10.00 |
| crm_hourly | $4,800.00 | **$1,200.00** | $200.00 | $50.00 |
| warehouse_daily | $9,600.00 | $2,400.00 | $400.00 | **$100.00** |

Current cadence in bold.

**Ways to cut cost**
- orders_sync every 30 min instead of 15: saves $480.00/month.
- crm_hourly every 2 h: saves $600.00/month.
- crm_hourly on small instead of medium, if it fits in memory: up to $600.00/month, less if runs
  get longer.

## Principles

- **Read before you ask.** The workspace has the real cadence, durations and sizes; ask only for
  what it can't tell you.
- **Never guess a duration.**
- **Jobs, not pipelines.** Each scheduled job is its own row.
- **Show a range, not a point.** Expected and high are what make the price predictable.
- **Show your sources.** Every number says whether it came from the workspace or the customer.
- **Propose, never apply.** Cost levers are the user's decision.
