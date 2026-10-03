"""Code dlt runs around the job-inspector-eval loop for a single-run evaluation.

`validate_input` resolves the inspector run, runs the deterministic checks and hands the judge
its evidence; `validate_output` writes the computed results over the judge's answer. The
preparation is kept in `_PREP` between the two: dlt imports this module afresh for every run.
"""

from typing import Any, Dict, Optional

from dlt.hub.run import JobAbortedException

from .checks import DEFAULT_MAX_RUNS_READ, EvalPrep, fetcher_for, finalize, prepare

_PREP: Optional[EvalPrep] = None


def validate_input(inputs: Dict[str, Any]) -> Dict[str, Any]:
    global _PREP
    run_context = inputs["run_context"]
    _PREP = prepare(
        run_context,
        fetcher=fetcher_for(run_context),
        inspector_run_id=inputs.get("inspector_run_id") or "",
        inspector_job_ref=inputs.get("inspector_job_ref") or "",
        max_runs_read=inputs.get("max_runs_read") or DEFAULT_MAX_RUNS_READ,
    )
    if _PREP.aborted:
        # nothing to evaluate: the run ends without calling the model
        raise JobAbortedException(_PREP.abort_reason, _PREP.aborted_output)
    return {**inputs, **_PREP.judge_inputs}


def validate_output(output: Dict[str, Any]) -> Dict[str, Any]:
    return finalize(output, _PREP)
