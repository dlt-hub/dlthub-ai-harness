---
name: define-and-debug-jobs
description: "Use when the user wants to make a pipeline, a transformation or a notebook a job, give a job triggers (a cron string, an interval, a follow-up after another job) or auto-refresh, declare the jobs of a deployment in __deployment__.py, or debug a job with dlthub local run, including a job run that failed on this machine. Defines jobs and the deployment module, and debugs the jobs locally. Not for deploying, scheduling or running jobs in production (prepare-deployment starts that)."
---

# Define jobs and debug them on this machine

**Reference**: https://dlthub.com/docs/hub/pipeline-operations/deployments.md |
https://dlthub.com/docs/hub/pipeline-operations/job-configuration.md |
https://dlthub.com/docs/hub/pipeline-operations/triggers.md |
https://dlthub.com/docs/hub/command-line-interface.md

A **job** is a function or a module that `__all__` in `__deployment__.py` lists. A deployment runs it, and its
triggers decide when. Here you define the jobs, their triggers and the deployment module, then debug each job with
`dlthub local run`. A local run starts the job at once with the active profile: it does not deploy the job and does
not fire its triggers. A **job ref** is `jobs.<module>.<name>`. A bare name works when it is unambiguous.

**Handed over from another toolkit?** The pipeline scripts and their destination are in the session already: start
step 1 with them.

## 1. Make the code a job

1. Decorate the function that runs the pipeline: `@run.pipeline("<pipeline name>")` (`from dlt.hub import run`).
   Use `@run.job` for other batch work and `@run.interactive` for notebooks, dashboards and MCP servers.
2. When other jobs, notebooks or checks read the dataset of the pipeline, create the pipeline at the module level, so
   they import it and call `pipeline.dataset()`. A job run activates its profile before it imports the module, so the
   pipeline still runs with the profile of the job run. Otherwise create it inside the job.
3. If a value changes per profile or per job run, make it a job argument with `dlt.config.value` (for example
   `limit: int = dlt.config.value`). Set it in `[jobs.<module>]` of the profile config files.
4. If the user runs the file with `uv run python`, keep the `if __name__ == "__main__":` block. The job does not
   need it.

## 2. Give the job its triggers

Triggers tell a deployment when to run the job: a cron schedule, an interval, or a follow-up after another job.
Declare them in the decorator, for example `@run.pipeline("my_pipeline", trigger="0 0 * * *")`. A job without a
trigger runs only when someone starts it. [triggers.md](triggers.md) has the trigger types and follow-up chains,
[job-patterns.md](job-patterns.md) intervals and freshness.

## 3. Turn on auto-refresh

Add `auto_refresh_pipeline_mode="drop_sources"` to the decorator (or `drop_resources`, `drop_data`), so that a refresh
run reloads every pipeline in the job. Without it, a refresh run does not reload the pipeline. The modes and the
refresh cascade to follow-up jobs are in "Refresh runs and the refresh cascade" of [job-patterns.md](job-patterns.md).

## 4. Define the deployment (`__deployment__.py`)

Import the jobs and list them in `__all__`. The first line of the module docstring describes the deployment.
[deployment-module.md](deployment-module.md) has the import rules, job refs and jobs declared in the module itself.
Check it with `dlthub local info`, which lists the jobs and their triggers, and with `dlthub local run <job>
--dry-run`. Repeat this step when more pipelines or notebooks join the workspace.

## 5. Debug the jobs with local runs

Run each job once from the project root, with the active profile (`dev` by default). Before you run with a remote
profile, ask the user (see the workspace rule).

```sh
dlthub local run <job>                        # job ref, bare name or selector
dlthub local run <job> -c limit=10            # a setting for this job run only (repeat -c)
dlthub local run <job> --start <ISO 8601> --end <ISO 8601>   # the interval of an interval job
dlthub local run <job> --refresh              # send the refresh signal
dlthub local run <job> --dry-run              # resolve the job, do not run it
dlthub local run <file>.py                    # a file that __deployment__.py does not list
dlthub local serve <job>                      # an interactive job
```

With `--non-interactive`, a selector that matches more than one job fails with exit code `255`. Name the job ref,
or add `--job-ref <job ref>`.

**Read the result**:
- The banner shows the job ref, the trigger, the profile and the run id. Check the profile first.
- The exit code comes from the job: `0` when it succeeds, `1` when it raises. `255` means that the job did not
  start: `dlthub` failed to resolve it or to import `__deployment__.py`. The output then lists the jobs it knows.
- Pipeline state is in `.dlt/state/<profile>/`. Data loaded to DuckDB is in `.dlt/data/<profile>/`.

**Debug a failed job run**:
1. Run again with `--debug` for the full stack trace, or `-v` for the plan of the job run.
2. Inspect the pipeline that the job ran: `dlthub local pipeline trace <pipeline>`, `dlthub local pipeline
   failed-jobs <pipeline>`, `dlthub local pipeline info <pipeline>`.
3. Run `dlthub local info`. The end of its output lists the jobs of `__deployment__.py` and their triggers.
4. Find the cause:

| Symptom | Cause | Fix |
|---|---|---|
| the job is not found (exit code `255`) | `__all__` does not list it, or `__deployment__.py` fails to import | list the job, fix the import, check with `--dry-run` |
| the job runs with the wrong destination or credentials | wrong active profile | check the banner, use `--profile` |
| `ConfigFieldMissingException` for a job argument | no value in `[jobs.<module>]` of the active profile | set it in the profile config file, or pass `-c` |
| missing credentials | the secrets file of the active profile has no value | use the `setup-secrets` skill |

5. To start from a clean state, ask the user first. Then run `dlthub local clean`: it removes the state and the
   data of the active profile.

## Next

Tests for the jobs are in (`test-local-jobs`). A deployment starts with (`prepare-deployment`): it checks that the
workspace is ready, sets up the production settings, and hands over to the platform toolkit.
