# Deploying an evaluator

This file owns the prepare, judge and finalize shape, the two deployments an evaluator takes, and
the rules of a scheduled window. Everything it leaves out is in `deployment.md` beside
(`create-background-agent`): `run.agent`, what a decorated function overrides, the signature
rules, why an abort raises instead of returning, the profile pin, the trigger strings, `section=`
and the `AGENT__` variables. Read that file first. The checks themselves are in
[check-registry.md](check-registry.md).

## Prepare, judge, finalize

Deterministic checks have to run before the loop and again after it, so an evaluator takes the
decorated form. `prepare` resolves the graded run, fetches every artifact the checks read, runs
the deterministic checks and builds the evidence windows. The loop judges. `finalize` writes the
computed results over the judge's output and assembles the summary.

## Per run

```python
import sys
from typing import Annotated

from dlt.hub import run

sys.path.insert(0, ".claude/dlthub/agents/job-inspector-eval")
from checks import DEFAULT_MAX_RUNS_READ, judge_runs, prepare

# `section` is explicit because this module uses the inspector's own triggers; see
# `deployment.md`
inspector = run.agent(
    "dlthub-platform:job-inspector",
    section="__deployment__",
    trigger="job.fail:tag:ingest",
    require={"profile": "access"},
)


@run.agent(
    agent="dlthub-platform:job-inspector-eval",
    trigger=[inspector.success, inspector.fail],
    require={"profile": "access"},
)
async def job_inspector_eval(
    run_context: run.TJobRunContext = None,
    inspector_run_id: Annotated[
        str,
        run.Entity("job-run"),
        run.Doc("run id of the job-inspector run to evaluate; empty on a trigger"),
    ] = "",
    inspector_job_ref: Annotated[
        str,
        run.Entity("job"),
        run.Doc("job ref of the inspector job; its latest run is evaluated without a run id"),
    ] = "",
    max_runs_read: Annotated[
        int,
        run.Doc("distinct runs the inspector may read before `single_run_scope` fails"),
    ] = DEFAULT_MAX_RUNS_READ,
) -> dict:
    prep = prepare(
        run_context,
        inspector_run_id=inspector_run_id,
        inspector_job_ref=inspector_job_ref,
        max_runs_read=max_runs_read,
    )
    if prep.aborted:
        raise run.JobAbortedException(prep.abort_reason, prep.aborted_output)
    evaluations, degraded = await judge_runs(
        run_context["ai_loop"], [prep], tolerate_failures=True
    )
    if not evaluations:
        # the judge ran out of turns or tokens after Python decided its checks; `judge_runs`
        # kept those rather than lose the run's whole result
        raise run.JobAbortedException(degraded[0]["summary"], degraded[0])
    return evaluations[0]
```

## On a schedule

The declaration above evaluates one run per trigger. A workspace that would rather read one report
covering the runs of the current definition deploys the same agent on a schedule and lets the
preparation step resolve the window:

```python
@run.agent(
    agent="dlthub-platform:job-inspector-eval",
    trigger="schedule:0 7 * * 1",
    require={"profile": "access"},
)
async def job_inspector_eval_batch(
    run_context: run.TJobRunContext = None,
    inspector_job_ref: Annotated[
        str, run.Entity("job"), run.Doc("job ref whose window is evaluated")
    ] = "jobs.__deployment__.job_inspector",
    window_days: Annotated[int, run.Doc("fallback window with no deployment history")] = 7,
    max_runs: Annotated[int, run.Doc("runs one scheduled job evaluates")] = 25,
) -> dict:
    batch = prepare_batch(run_context, inspector_job_ref=inspector_job_ref,
                          window_days=window_days, max_runs=max_runs)
    if batch.aborted:
        raise run.JobAbortedException(batch.abort_reason, batch.aborted_output)
    # one run out of budget or out of shape must not cost the rest of the window
    evaluations, degraded = await judge_runs(
        run_context["ai_loop"], batch.preps, tolerate_failures=True
    )
    if not evaluations:
        # not one loop run completed, so `loop.trace` does not exist and a returned dict
        # fails the job on it; the degraded runs carry their deterministic checks into the
        # aborted output
        report = finalize_batch([], batch, degraded)
        if batch.found:
            raise run.JobAbortedException(report["summary"], {**report, "status": "aborted"})
        print(report["summary"])
        return {}
    recommendation = await judge_window_recommendation(
        run_context["ai_loop"], evaluations + degraded, batch
    )
    return finalize_batch(evaluations, batch, degraded, recommendation)
```

**Deploy one or the other.** An agent watched by both is graded twice.

## What the scheduled path settles

- **The window starts at the last definition change.** The runs before it were graded against
  different instructions. The walk runs down the workspace's deployments from the newest and takes
  the oldest one still carrying the current hash of the graded agent's `AGENT.md`. Pass `since` to
  override it; with no deployment history the window falls back to `window_days`.
- **A run is graded again on the next schedule** until the definition changes, because the window
  is the definition's lifetime. `max_runs` bounds what that costs.
- **The window is walked.** Run listing yields runs newest first, pages lazily and takes no `since`
  or `until`, so the walk runs from the newest run down to the first one outside the window and a
  window holding more runs than a page still comes back whole.
- **Every run found is accounted for.** A run still going, one that declared no result and one
  whose artifacts could not be read are listed under `skipped_runs` with the reason, and
  `runs_found` equals `runs_evaluated + runs_skipped`.
- **A judge out of budget costs one run its judge checks, not its results.** The deterministic
  checks Python decided before the loop started are reported, the judge checks read `N/A`, the run
  counts as evaluated and never passes, and the window names the reason in a scope bullet. The
  recommendation pass is guarded the same way: a failure there is reported in place of the
  recommendation and the graded window still reports.
- **A graded run is `completed` or `failed`.** A run record speaks the platform's vocabulary
  (`pending`, `starting`, `running`, `cancelling`, `completed`, `failed`, `cancelled`, `skipped`)
  and an agent result speaks its own (`succeeded`, `failed`, `aborted`), so a run that finished
  well reads `completed` on the record and `succeeded` in the result.
- **One judge run per graded run.** `limits.max_tokens` counts from zero on each, so the limit in
  `defaults` means one evaluation and the cost of the job is the sum.
- **The job result carries the last loop's trace.** dlt stores one trace per job run, so a batch
  output counts turns and tokens over its evaluations instead.
- **An empty window reports to the log.** Right after a definition change the graded agent has not
  run yet. A job whose loop never started has no trace, and the finish path reads one on any
  returned dict carrying `status`, so an empty window prints its report and returns `{}`. A window
  that found runs and graded none raises.
- **The recommendation is written over a window only.** A change to the instructions the agent
  followed rests on a pattern across runs. The scheduled job makes one more judge call after the
  window is graded, given the broken checks with how many runs broke each and a few of the
  reasonings, and writes one to three bullets naming the file and the section to change.
- **A recommendation never weakens a guardrail.** The graded agent's constraints, its `access` and
  `tools` blocks and the bans its definition states stand whatever the window shows, so a broken
  check that turns on one of them is answered by sharpening that instruction.

## Inputs and where a default lives

Every input is a parameter of the deployment function. A workspace changes a default by editing
that parameter; a single run overrides one with `-c <name>=...`, and a job section in
`config.toml` overrides it for every run of that job.

| input | per-run deployment | scheduled deployment | default |
|---|---|---|---|
| `inspector_run_id` | the run graded; empty on a trigger, then `prev_run_id` | unused | `""` |
| `inspector_job_ref` | the job whose latest run is graded when no run id is given | the job whose window is graded | `""`, and the inspector's job ref on the scheduled one |
| `max_runs_read` | bounds `single_run_scope` | the same, on every run in the window | `DEFAULT_MAX_RUNS_READ` in `checks.py`, 5 |
| `window_days` | unused | how far back the window reaches with no deployment history | `DEFAULT_WINDOW_DAYS` in `checks.py`, 7 |
| `max_runs` | unused | inspector runs one scheduled job grades | `DEFAULT_BATCH_RUNS` in `checks.py`, 25 |

`prepare_batch` also takes `since` to pin the window start. It is an argument of the function, not
a declared input, so a deployment that exposes it as a parameter gets a manifest warning that the
system prompt never mentions it.
