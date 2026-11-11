# Pricing estimation skill — design

Date: 2026-11-11
Branch: `feat/cost-estimation`
Status: approved design, pending spec review

## Goal

For the PAYG (pay-as-you-go) launch the key message is **predictable pricing**. "$10 per runtime
hour" is hard for a customer to translate into a monthly bill. The skill turns the customer's
**trial workspace** — the jobs they deployed, how often they run, how long runs take — into a
monthly cost estimate with a range and concrete ways to lower it.

Based on a colleague's `pricing-estimation` skill (subscription + tiered credits + bundles +
launch discounts). That pricing model does not apply to PAYG and is dropped; the input discipline
(never guess duration, jobs are the scheduled unit, frequency ladder) is kept. Slides are out of
scope for this iteration.

## Audience and placement

- **Runs in the customer's coding agent, inside their trial workspace.**
- Lives at `workbench/init/skills/pricing-estimation/SKILL.md`. An install copies only the toolkit
  directory, so a skill at the repo root never reaches a workspace; `init` is installed into every
  workspace, so any toolkit can name the skill like a local one (same reason
  `create-background-agent` lives there).

## Pricing model (PAYG)

- **$10 per runtime hour.** No base fee, no included hours, no volume tiers, no bundles, no
  discounts. (The $1,190/month subscription is a different plan and is out of scope.)
- Charged hours = **wall-clock hours × instance-size multiplier**, the same rule the platform uses
  for the run-time budget (`dlthub-platform/rules/job-resources.md`). Multipliers are read from the
  instance-size docs, never quoted from memory:
  https://dlthub.com/docs/hub/pipeline-operations/job-configuration#instance-size
- The rate and the link to the pricing page appear **once**, at the top of the SKILL.md, so a price
  change is a one-line edit.

## Inputs — read the workspace first, ask only for gaps

Per **job** (the scheduled unit — a pipeline split into several jobs contributes several rows):

| Input | Source |
|---|---|
| Jobs and their triggers | `uv run dlthub --non-interactive job list` |
| Run durations | `dlthub job runs list <job>` / `dlthub job runs info` — recent successful runs |
| Instance size | `dlthub deploy --show-manifest` (`require.instance.size`; omitted = smallest tier) |
| Runs per month | from the trigger: cron or interval → runs/day × 30 |

Gaps and how they are handled:

- **Job with no completed runs**, **manual-only job**, or **nothing deployed yet** → ask the
  customer for duration and intended cadence; mark the row as *customer assumption*.
- **Never guess a duration.** Only exception: the customer explicitly waves it off ("assume
  something light") — then pick a value, state it loudly, flag it as an assumption to verify.
- **Event-triggered jobs** (e.g. after another job) inherit the upstream job's cadence.
- **Failed runs** are excluded from duration stats; note how many were dropped.

## Calculation

Per job:

1. `runs_month = runs_per_day × 30`
2. `typical_h = median(duration) / 60` and `slow_h = p90(duration) / 60` (minutes → hours). With
   fewer than 5 runs, use min/max instead and say so.
3. `cost_expected = runs_month × typical_h × multiplier × $10`
4. `cost_high = runs_month × slow_h × multiplier × $10`

Total = sum over jobs, for both expected and high. Round hours to 1 decimal, dollars to 2. Python
in a scratch block is fine for the arithmetic; don't show code unless asked.

## Output (inline markdown, minimal prose)

1. **Assumptions** — jobs found, the source of every number (workspace vs customer), the rate,
   the multipliers used.
2. **Per-job table** — job, cadence, runs/month, typical / slow duration, size, hours/month,
   $/month (expected).
3. **Monthly range** — expected to high, presented as "your bill should land between $X and $Y".
   This is the predictability message: a ceiling, not a single guess.
4. **What-if cadence ladder** — the same workload at every 15 min / hourly / every 6 h / daily
   (skip rows that don't make sense).
5. **Ways to cut cost**, each with its dollar saving:
   - run less often
   - smaller runner (only when the job fits; read multipliers from docs)
   - incremental loading, so runs get shorter
   - merge small jobs to save per-run startup time
   For making runs faster, hand over to the **performance** toolkit (`optimize-performance`).
   Following `job-resources.md`, the skill only **proposes** — it never edits schedules, sizes or
   timeouts.
6. **Caveats**
   - Trial data volumes may differ from production.
   - A first backfill runs longer than steady-state runs; estimate covers steady state.
   - Jobs don't pause automatically.

## Wiring

- One line in `workbench/init/rules/dlthub-workspace.md` (always loaded) pointing to
  `pricing-estimation` for "what will this cost" questions.
- Outgoing handover in `workbench/dlthub-platform/rules/workflow.md`: after `deploy-workspace`,
  when the user asks what the deployment will cost → `pricing-estimation` (in `init`, so it is a
  local skill reference, not a toolkit handover — check what the validator expects).
- Skill description triggers on: cost, price, bill, spend, "how much will this cost", runtime
  hours, PAYG estimate. Excludes: changing instance size or cadence (that is `deploy-workspace` /
  `optimize-performance`).

## Testing

- `make validate-toolkits` passes.
- Worked example in the SKILL.md (e.g. 3 jobs: every 15 min / hourly / daily, mixed sizes) with
  hand-checked numbers.
- Optional: trigger eval with `create-eval`.

## Open questions

1. **Do instance multipliers apply to PAYG billing?** The design assumes yes (same as the run-time
   budget). If PAYG bills every hour at a flat $10, drop step "× multiplier" and the smaller-runner
   lever.
2. **Public pricing page URL** for the skill to cite. If not public yet, ship the rate with a
   TODO-free note "check dlthub.com for current pricing" and add the link later.

## Out of scope (later)

- Slides / deck output.
- Comparison with the $1,190/month subscription plan.
- Reading billing data directly from the platform, if such an API appears.
