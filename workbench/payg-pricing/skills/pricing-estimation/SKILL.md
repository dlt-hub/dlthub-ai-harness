---
name: pricing-estimation
description: "Estimate what a dltHub workspace will cost per month on pay-as-you-go (PAYG) pricing, from the jobs the customer deployed in their trial workspace: how often each job runs, how long its runs take and which instance size it uses. Use when the user asks what their pipelines or jobs will cost, how much dltHub will cost per month, what their bill or spend will be, how many runtime hours they use, or wants a PAYG estimate, a cost range, ways to lower the cost, or a shareable cost report for their manager or team. Do NOT use to change a job's schedule, instance size or timeout (deploy-workspace), or to make a slow job faster (performance toolkit, optimize-performance)."
---

# Pricing estimation (PAYG)

Turn the customer's trial workspace into a **predictable** monthly bill: a per-job table, an
expected-to-high range, and the cheapest ways to lower it. Output is markdown tables, inline,
plus an optional one-page HTML report to share.

## Price (single source of truth)

- **$10 per runtime hour** on pay-as-you-go. No base fee, no included hours, no volume tiers, no
  bundles, no discounts.
- Charged hours = **wall-clock hours × instance-size multiplier**. Read the multipliers from
  https://dlthub.com/docs/hub/pipeline-operations/job-configuration#instance-size — never quote
  them from memory. A job with no `instance` set runs on the smallest tier.
- Check dlthub.com for current pricing.


**You never do arithmetic.** `payg_estimate.py`, next to this file, computes every number: runs
per month, run-time statistics, hours, costs, the what-if table and every saving. Your job is to
copy facts into a JSON file, choose which changes to propose, and paste the script's output.

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

Write `reports/payg-estimate.json` in the shape documented at the top of `payg_estimate.py`. Per
job, **copy, don't compute**:

| Field | What to copy |
|---|---|
| `schedule` | The trigger as written: `{"every": 15, "unit": "minutes"}` (or `"hours"` / `"days"`), or `{"cron": "0 9 * * 1-5"}`. Don't convert it to runs per day |
| `runs` | Each recent run's duration in minutes and its status (`"ok"` / `"failed"`), as listed — up to the last 20. Don't average them. A job whose runs all failed is fine: it is billed for the failed time |
| `size`, `multiplier` | Size from the manifest (none set = smallest tier); multiplier from the instance-size docs |

- **Interactive / served jobs** (`@run.interactive`, `dlthub serve` — MCP servers, dashboards,
  notebooks, APIs) have no runs. Ask how many hours per day they stay up and use
  `{"always_on_hours_per_day": <answer>}` as the schedule.
- **Event-triggered jobs** (follow-ups, [triggers docs](https://dlthub.com/docs/hub/pipeline-operations/triggers.md)):
  copy the event, never the upstream's schedule. The script counts runs from the upstream's
  runs and failure share, so a job that runs on failure isn't counted once per upstream run.

  | Trigger | `schedule` |
  |---|---|
  | `upstream.success` | `{"on_success_of": "upstream"}` |
  | `upstream.fail` | `{"on_failure_of": "upstream"}` |
  | `upstream.completed` | `{"on_completion_of": "upstream"}` |
  | Selector, e.g. `"job.fail:tag:ingest"` | `{"on_failure_of": [<every job the selector matches>]}` |

  Every upstream must be in `jobs`. If an upstream has no runs yet and the job follows its
  failures, ask the customer how often it fails and pass `"failed_share"` in its `assumed`.
- **Several triggers** (`trigger=[...]`): pass them as a list, e.g.
  `[{"cron": "0 8 * * *"}, {"on_success_of": "backfill"}]`. Each trigger starts its own run.
- **Manual or tag runs** (no trigger; started with `dlthub job trigger`): ask how often they're
  run and use that as the schedule. A `trigger.once` job runs one time; leave it out of the
  monthly estimate and mention it.
- **Freshness checks** (`freshness=[...]`) skip runs while an upstream is loading or failed. The
  script ignores them, so the estimate is an upper bound for those jobs; say so.
- Add the rate from **Price** above as `rate_usd_per_hour`, and today's `date`.

## Step 2: Ask only for the gaps

Ask the customer when a job has **no successful runs**, is **manual-only**, or **nothing is
deployed yet**: how long a run takes (typical and slow) and how often it should run in
production. Pass the answer as `"assumed": {"avg_minutes": ..., "slow_minutes": ...}` instead of
`runs`; the script marks it as the customer's estimate.

**Never guess a duration.** The only exception: the customer explicitly waves it off ("assume
something light") — then pick a value, pass it as `assumed`, and say so in `notes`.

## Step 3: Choose the changes to propose

Add `levers` — the changes, not their savings. The script prices each one:

- run less often: `{"job": "orders_sync", "schedule": {"every": 30, "unit": "minutes"}}`
- smaller instance, only if the job could fit: `{"job": "crm", "size": "small", "multiplier": 1}`
- shorter uptime for an always-on job: `{"job": "dashboard", "always_on_hours_per_day": 4}`
- anything that changes run time, which can't be priced before it's measured — incremental
  loading, merging small jobs: `{"label": "Incremental loading for crm", "unquantified": true}`

Put any other context (where durations came from, caveats specific to this workspace) in
`notes` as plain sentences, without numbers you worked out yourself.

## Step 4: Run the script and present

```sh
uv run python <this skill's folder>/payg_estimate.py summary reports/payg-estimate.json
```

**Paste its output as it is** — assumptions, per-job table, monthly range, what-if table, ways to
cut cost. Don't round, re-add or restate the numbers in your own words. If a number looks wrong,
fix the facts in the JSON and run it again.

Then add, in a sentence or two:

- For making runs faster, hand over to the **performance** toolkit (`optimize-performance`);
  install it if absent: `uv run dlthub --non-interactive ai toolkit install performance`.
- **Only propose.** Never change a schedule, instance size or timeout yourself — those spend
  budget on every run and need the user's explicit yes (see the `job-resources` rule of
  **dlthub-platform**).
- **Caveats**
  - Trial data volumes may differ from production.
  - A first backfill runs longer than steady-state runs; the estimate covers steady state.
  - Scheduled jobs keep running — and billing — until you remove their trigger or undeploy them;
    the trial ending does not stop them.
  - Billed time may include container start-up and any per-run minimum that the run timing
    doesn't show; short, frequent jobs are most affected.

### How the script calculates (for explaining, not for doing)

- A month is 365 / 12 ≈ 30.4 days. Runs per month: from the schedule; cron is counted over a full
  year and divided by 12 (with croniter), so weekday-only, weekly, monthly and yearly crons count
  right.
- Event-triggered jobs: upstream runs × the upstream's success share (`on_success_of`), failure
  share (`on_failure_of`) or 1 (`on_completion_of`), followed back through chains. In the what-if
  table they move with their upstream jobs.
- Average run: mean of successful runs. Slow run: 90th percentile, or the longest run when there
  are fewer than 5. Failed runs are billed once, for the time they ran.
- Hours = runs × run time × instance multiplier; always-on jobs: hours per day × 30.4 × multiplier.
- Cost = hours × the rate. Heavy month = every run as slow as the slow run.

## Step 5: Shareable report (offer, don't push)

After the estimate, ask once: *"Want a one-page report you can share with your team or
manager?"* Only on a yes:

1. Ask, optionally: *"Roughly how many engineer hours a month would running these pipelines
   yourselves take (scheduler, servers, monitoring, reruns), and at what hourly rate?"* Add the
   answer as `engineering`; if they skip it, leave it out — **never invent hours or rates**.
2. Run:
   `uv run python <this skill's folder>/payg_estimate.py report reports/payg-estimate.json --out reports/payg-cost-estimate.html`
3. Tell the user: open the file in a browser, or use Print → Save as PDF to send it on.

The report is one self-contained HTML file (no scripts, nothing downloaded). Its fixed text —
why the bill is predictable, what's included — lives in `report-template.html`; don't edit it
per customer.

## Worked example

Three jobs whose run times the customer gave (no runs yet). Multipliers are illustrative — read
the docs.

```json
{
  "rate_usd_per_hour": 10,
  "date": "2026-11-11",
  "jobs": [
    {"name": "orders_sync", "schedule": {"every": 15, "unit": "minutes"},
     "size": "small", "multiplier": 1, "assumed": {"avg_minutes": 2, "slow_minutes": 3}},
    {"name": "crm_hourly", "schedule": {"every": 1, "unit": "hours"},
     "size": "medium", "multiplier": 2, "assumed": {"avg_minutes": 5, "slow_minutes": 8}},
    {"name": "warehouse_daily", "schedule": {"cron": "0 2 * * *"},
     "size": "small", "multiplier": 1, "assumed": {"avg_minutes": 20, "slow_minutes": 30}}
  ],
  "levers": [
    {"job": "orders_sync", "schedule": {"every": 30, "unit": "minutes"}},
    {"job": "crm_hourly", "schedule": {"every": 2, "unit": "hours"}},
    {"job": "crm_hourly", "size": "small", "multiplier": 1},
    {"label": "Incremental loading for warehouse_daily", "unquantified": true}
  ]
}
```

`payg_estimate.py summary` prints:

**Assumptions**
- $10 per runtime hour; 30.4 days per month (365 / 12).
- Instance multipliers (from the dltHub docs): small 1×, medium 2×.
- orders_sync: run time is the customer's estimate.
- crm_hourly: run time is the customer's estimate.
- warehouse_daily: run time is the customer's estimate.

| Job | Schedule | Runs/month | Average / slow run | Size | Hours/month | $/month |
|---|---|---|---|---|---|---|
| orders_sync | every 15 min | 2,920 | 2 / 3 min | small (1×) | 97.3 | $973.33 |
| crm_hourly | hourly | 730 | 5 / 8 min | medium (2×) | 121.7 | $1,216.67 |
| warehouse_daily | daily | 30.4 | 20 / 30 min | small (1×) | 10.1 | $101.39 |
| **Total** | | 3,680.4 | | | **229.1** | **$2,291.39** |

**Expected about $2,291.39 per month; in a heavy month up to about $3,558.75** (if runs take as long as the slowest 10%).

**What each job would cost at another schedule**

| Job | Now | Every 15 min | Hourly | Every 6 h | Daily |
|---|---|---|---|---|---|
| orders_sync | $973.33 (every 15 min) | $973.33 | $243.33 | $40.56 | $10.14 |
| crm_hourly | $1,216.67 (hourly) | $4,866.67 | $1,216.67 | $202.78 | $50.69 |
| warehouse_daily | $101.39 (daily) | $9,733.33 | $2,433.33 | $405.56 | $101.39 |

**Ways to cut cost**
- orders_sync every 30 min instead of every 15 min: saves $486.67/month.
- crm_hourly every 2 h instead of hourly: saves $608.33/month.
- crm_hourly on small instead of medium (if it fits): saves up to $608.33/month if the run time doesn't change; no saving if it runs 2× slower or more.
- Incremental loading for warehouse_daily: saving depends on the new run time — measure after the change.

## Principles

- **Read before you ask.** The workspace has the real schedules, run times and sizes; ask only
  for what it can't tell you.
- **Never guess a duration.**
- **Never do arithmetic.** Copy facts in, paste the script's output out.
- **Jobs, not pipelines.** Each scheduled job is its own row.
- **Show a range, not a point.** Expected and heavy-month figures make the price predictable;
  neither is a hard bound.
- **Propose, never apply.** Cost levers are the user's decision.
