"""Read the findings the previous run of this job left on the platform.

The job's result is stored with every run, so the newest completed run of the same job
holds the findings to carry forward. A run with no platform behind it, such as a local
run, starts with none and says so in its report.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .tracking import combine

RUNS_LOOKED_AT = 10
# earlier reports read together, so a date one of them found is never lost
REPORTS_COMBINED = 5


def _workspace() -> Any:
    import dlthub_sdk
    from dlt._workspace._workspace_context import active

    config = active().runtime_config
    token = str(config.api_key or config.auth_token or "")
    if not token or not config.workspace_id:
        raise LookupError("no platform credential or workspace id in this run")
    runtime = dlthub_sdk.connect(token=token, base_url=config.api_base_url or "https://api.dlthub.com")
    return runtime.workspaces.get(id=config.workspace_id)


def previous_findings(run_id: str) -> Tuple[Optional[List[Dict[str, Any]]], str]:
    """The findings of the latest earlier runs, combined, and a note on how it went."""
    if not run_id or run_id == "local":
        return None, "a local run has no earlier report to compare with"
    try:
        workspace = _workspace()
        current = workspace.job_runs.get(id=run_id)
        job = workspace.jobs.get_by_ref(current.job_ref)
        reports: List[List[Dict[str, Any]]] = []
        numbers: List[int] = []
        for run in workspace.job_runs.list(job_id=job.id, limit=RUNS_LOOKED_AT):
            if run.id == run_id or str(run.status).split(".")[-1].lower() != "completed":
                continue
            try:
                result = workspace.job_runs.result(id=run.id).result
            except Exception:  # a run that stored no result is skipped, not fatal
                continue
            if isinstance(result, dict) and isinstance(result.get("tracked"), list):
                reports.append(result["tracked"])
                numbers.append(run.number)
            if len(reports) == REPORTS_COMBINED:
                break
        if not reports:
            return [], "first report of this job: no earlier result to compare with"
        return combine(reports), f"compared with run #{numbers[0]}"
    except Exception as ex:  # without history every finding is shown as new, never lost
        return None, f"earlier report not read ({type(ex).__name__}: {ex})"[:200]
