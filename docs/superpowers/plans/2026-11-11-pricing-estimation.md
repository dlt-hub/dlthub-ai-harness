# Pricing Estimation Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a `pricing-estimation` skill in the `init` toolkit that turns a customer's trial workspace (deployed jobs, cadence, run durations, instance size) into a predictable PAYG monthly cost range at $10 per runtime hour.

**Architecture:** One `SKILL.md` under `workbench/init/skills/pricing-estimation/`. The agent reads the workspace with the `dlthub job` CLI, computes per-job charged hours (runs × duration × instance multiplier), and outputs markdown tables. Discoverability: one line in the always-loaded `init` rule and its Codex twin `AGENTS.md`, plus a plain-text pointer in `dlthub-platform/rules/workflow.md`.

**Tech Stack:** Markdown skills (Claude Code plugin format), `dlthub` CLI, `tools/validate_toolkits.py` (`make validate-toolkits`), pytest (`make test`).

**Spec:** `docs/superpowers/specs/2026-11-11-pricing-estimation-design.md`

## Global Constraints

- PAYG rate: **$10 per runtime hour**. No base fee, no included hours, no tiers, no bundles, no discounts.
- Charged hours = **wall-clock hours × instance-size multiplier**; multipliers are read from https://dlthub.com/docs/hub/pipeline-operations/job-configuration#instance-size, never quoted from memory.
- The rate appears **once** in the skill (top section).
- Jobs are the scheduled unit, not pipelines. Runs/month = runs/day × 30.
- Never guess a run duration; ask, unless the customer explicitly waves it off (then state it loudly as an assumption).
- The skill only **proposes** cost-cutting; it never edits schedules, instance sizes or timeouts (`workbench/dlthub-platform/rules/job-resources.md`).
- Skill frontmatter `name` must equal the directory name; `description` ≤ 1024 chars.
- No toolkit file may name a repo-root `.md` (other than README.md/CLAUDE.md) outside a URL.
- In a toolkit `workflow.md`, `` (`name`) `` must resolve to a skill **in that toolkit** — references to `init` skills use plain backticks without parens.
- Run all `dlthub` commands as `uv run dlthub --non-interactive ...` from the project root.
- Open question carried from the spec: whether multipliers apply to PAYG. Implement with multipliers; keep the multiplier in one formula line so it can be dropped.

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `workbench/init/skills/pricing-estimation/SKILL.md` | Create | The skill: rate, inputs, calculation, output format, worked example, principles |
| `workbench/init/rules/dlthub-workspace.md` | Modify (`# how we work` section, after line 21) | Always-loaded pointer for Claude/Cursor |
| `workbench/init/AGENTS.md` | Modify (after `## Security`, line 5) | Same pointer for Codex |
| `workbench/dlthub-platform/rules/workflow.md` | Modify (`## Extend and harden`, after item 4) | Point deployers at the cost estimate |

---

### Task 1: Write the `pricing-estimation` skill

**Files:**
- Create: `workbench/init/skills/pricing-estimation/SKILL.md`
- Test: `make validate-toolkits` (skill frontmatter, name/dir match, description length, root-doc refs); scratch arithmetic check (not committed)

**Interfaces:**
- Consumes: nothing.
- Produces: skill name `pricing-estimation` (directory and frontmatter), referenced by Tasks 2 and 3.

- [ ] **Step 1: Confirm the validator currently passes (baseline)**

Run: `make validate-toolkits`
Expected: exits 0. If it already fails, note the pre-existing errors so they are not attributed to this change.

- [ ] **Step 2: Check the CLI against the docs**

Open https://dlthub.com/docs/hub/command-line-interface.md and confirm these commands and what they print: `dlthub job list` (job names + triggers/schedules), `dlthub job runs list [name_or_selector]` (runs with status and timing), `dlthub job runs info <name> [run#]` (exit status and timing), `dlthub deploy --show-manifest` (per-job `require.instance.size`). If a command name or flag differs, use the documented one in Step 4's content. Also open https://dlthub.com/docs/hub/pipeline-operations/job-configuration#instance-size and confirm the size names (`small`, `medium`, `large`, `xlarge`) and that `small` is the default at 1×.

- [ ] **Step 3: Verify the worked-example arithmetic (scratch, not committed)**

Run:
```bash
python3 -c "
jobs=[('orders_sync',2880,2,3,1),('crm_hourly',720,5,8,2),('warehouse_daily',30,20,30,1)]
te=th=0
for n,r,t,s,m in jobs:
  a=r*t/60*m; b=r*s/60*m; te+=a; th+=b; print(n,a,a*10,b,b*10)
print('total',te,te*10,th,th*10)
for n,_,t,_,m in jobs:
  print(n,[(r*t/60*m, r*t/60*m*10) for r in (2880,720,120,30)])
"
```
Expected:
```
orders_sync 96.0 960.0 144.0 1440.0
crm_hourly 120.0 1200.0 192.0 1920.0
warehouse_daily 10.0 100.0 15.0 150.0
total 226.0 2260.0 351.0 3510.0
orders_sync [(96.0, 960.0), (24.0, 240.0), (4.0, 40.0), (1.0, 10.0)]
crm_hourly [(480.0, 4800.0), (120.0, 1200.0), (20.0, 200.0), (5.0, 50.0)]
warehouse_daily [(960.0, 9600.0), (240.0, 2400.0), (40.0, 400.0), (10.0, 100.0)]
```

- [ ] **Step 4: Create the skill file**

Create `workbench/init/skills/pricing-estimation/SKILL.md` with exactly this content (adjust CLI names only if Step 2 found differences):

````markdown
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
````

- [ ] **Step 5: Check the description length**

Run: `python3 -c "import re,sys;t=open('workbench/init/skills/pricing-estimation/SKILL.md').read();d=re.search(r'^description: \"(.*)\"$',t,re.M).group(1);print(len(d))"`
Expected: a number ≤ 1024.

- [ ] **Step 6: Run the validator**

Run: `make validate-toolkits`
Expected: exits 0, no new `[init]` errors or warnings mentioning `pricing-estimation`.

- [ ] **Step 7: Commit**

```bash
git add workbench/init/skills/pricing-estimation/SKILL.md
git commit -m "init: add pricing-estimation skill for PAYG cost estimates"
```

---

### Task 2: Make the skill discoverable

**Files:**
- Modify: `workbench/init/rules/dlthub-workspace.md` (`# how we work` section; insert after the `**use web search**` bullet, currently line 21)
- Modify: `workbench/init/AGENTS.md` (insert a new section after `## Security`, currently lines 4–5)
- Modify: `workbench/dlthub-platform/rules/workflow.md` (`## Extend and harden`, after item 4 `Inspect failures unattended`)
- Test: `make validate-toolkits`, `make test`

**Interfaces:**
- Consumes: skill name `pricing-estimation` from Task 1.
- Produces: nothing later tasks depend on.

- [ ] **Step 1: Add the pointer to the always-loaded rule**

In `workbench/init/rules/dlthub-workspace.md`, after the line starting `* **use web search**:`, add:

```markdown
* **cost questions**: when the user asks what their jobs or workspace will cost, their monthly bill, or runtime hours on pay-as-you-go, use the `pricing-estimation` skill — it reads the deployed jobs and their runs and gives a monthly range.
```

- [ ] **Step 2: Add the same pointer for Codex**

In `workbench/init/AGENTS.md`, after the `## Security` paragraph (the line starting `CRITICAL: never ask for credentials`), add a blank line and:

```markdown
## Cost questions
When the user asks what their jobs or workspace will cost, their monthly bill, or runtime hours on pay-as-you-go, use the `pricing-estimation` skill — it reads the deployed jobs and their runs and gives a monthly range.
```

- [ ] **Step 3: Point deployers at it from `dlthub-platform`**

In `workbench/dlthub-platform/rules/workflow.md`, after the `## Extend and harden` item that starts `4. **Inspect failures unattended**`, add:

```markdown
5. **Estimate the monthly bill** — `pricing-estimation` skill (in `init`, always installed) — once jobs are deployed and have run, or when the user asks what the deployment will cost; it reads cadence, run durations and instance size and gives a PAYG range
```

Use plain backticks, **not** `` (`pricing-estimation`) `` — the validator resolves parenthesised refs only against `dlthub-platform`'s own skills and would fail.

- [ ] **Step 4: Run the validator and the test suite**

Run: `make validate-toolkits`
Expected: exits 0.

Run: `make test`
Expected: all tests pass (same count as before plus none failing).

- [ ] **Step 5: Commit**

```bash
git add workbench/init/rules/dlthub-workspace.md workbench/init/AGENTS.md workbench/dlthub-platform/rules/workflow.md
git commit -m "init, dlthub-platform: point cost questions at pricing-estimation"
```

---

### Task 3: Trigger eval (optional, needs user go-ahead)

**Files:**
- Created by the `create-eval` skill (see `EVALS.md`)

**Interfaces:**
- Consumes: skill `init:pricing-estimation` from Task 1.
- Produces: eval workspace and queries.

- [ ] **Step 1: Ask the user whether to run a trigger eval now**

If yes, invoke the `create-eval` skill for `init:pricing-estimation`, then `run-eval`. Target queries to include: "what will these pipelines cost per month?", "how much will dltHub charge me for this?", "estimate my PAYG bill"; near-misses that must NOT trigger: "make this job run on a medium instance", "why is my job slow?", "schedule this job hourly".

- [ ] **Step 2: If precision/recall is poor, adjust only the `description` and re-run**

Commit any description change:
```bash
git add workbench/init/skills/pricing-estimation/SKILL.md
git commit -m "init: tune pricing-estimation trigger description"
```

---

## Out of scope

- Slides / deck output.
- Comparison with the $1,190/month subscription plan.
- Reading billing data from a platform API.
