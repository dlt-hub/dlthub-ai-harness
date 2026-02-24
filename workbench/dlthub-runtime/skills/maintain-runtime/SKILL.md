---
name: maintain-runtime
description: Inspect dltHub Runtime jobs, check run status, view logs, and open the web dashboard. Use when the user asks to check job status, view runtime logs, debug a failed run, or open the runtime UI.
---

# Maintain dltHub Runtime jobs

**Reference**: https://dlthub.com/docs/hub/runtime/overview.md

## Check job status

```bash
dlt runtime job list                              # all jobs
dlt runtime job info <script_or_name>             # details for one job
dlt runtime job-run list <script_or_name>         # list all runs
dlt runtime job-run info <script_or_name> [run#]  # specific run details
```

## View logs

```bash
dlt runtime logs <script_or_name>                 # latest run
dlt runtime logs <script_or_name> <run#>          # specific run
dlt runtime logs <script_or_name> -f              # follow in real-time
```

## Cancel a running job

```bash
dlt runtime cancel <script_or_name> [run#]
```

## Open the web dashboard

```bash
dlt runtime dashboard
```

Opens the dltHub Runtime UI at dlthub.app — shows jobs, runs, logs, schedules, and deployment history.

## Quick diagnosis

If a job failed:
1. `dlt runtime job-run info <script> <run#>` — check exit status and timing
2. `dlt runtime logs <script> <run#>` — read the error output
3. Common causes: missing dependencies in `pyproject.toml`, secrets not configured for `prod` profile, script missing `if __name__ == "__main__":`
