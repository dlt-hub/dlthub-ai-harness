---
name: run-local-jobs
description: Declare, run and debug dlt jobs on this machine. Make a pipeline or a function a job (`@run.pipeline`, `@run.job`, `@run.interactive`), list it in `__deployment__.py`, run it with `dlthub local run` or serve it with `dlthub local serve`, read the result, debug a failed job run, and add triggers. Use before the first deployment and whenever a job fails on this machine. Do NOT use to run or inspect jobs on a deployment platform.
---

# Run and debug jobs on this machine

**Reference**: https://dlthub.com/docs/hub/pipeline-operations/deployments.md |
https://dlthub.com/docs/hub/pipeline-operations/job-configuration.md |
https://dlthub.com/docs/hub/command-line-interface.md

A **job** is a function or a module that `__all__` in `__deployment__.py` lists. A deployment runs it.
`dlthub local run` runs it here the same way: it resolves the job from `__deployment__.py`, applies the settings of
the active profile and runs it. A **job ref** is `jobs.<module>.<name>`. A bare name works when it is unambiguous.

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

## 2. List the job in `__deployment__.py`

Import the job and add its name to `__all__`. The first line of the module docstring describes the deployment.
[deployment-module.md](deployment-module.md) has the import rules, job refs and jobs declared in the module itself.

## 3. Run the job

Run from the project root, with the active profile (`dev` by default). Before you run with a remote profile, ask
the user (see the workspace rule).

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

## 4. Read the result

- The banner shows the job ref, the trigger, the profile and the run id. Check the profile first.
- The exit code comes from the job: `0` when it succeeds, `1` when it raises. `255` means that the job did not
  start: `dlthub` failed to resolve it or to import `__deployment__.py`. The output then lists the jobs it knows.
- Pipeline state is in `.dlt/state/<profile>/`. Data loaded to DuckDB is in `.dlt/data/<profile>/`.

## 5. Debug a failed job run

1. Run again with `--debug` for the full stack trace, or `-v` for the plan of the job run.
2. Inspect the pipeline that the job ran: `dlthub local pipeline trace <pipeline>`, `dlthub local pipeline
   failed-jobs <pipeline>`, `dlthub local pipeline info <pipeline>`.
3. Run `dlthub local info`. The end of its output lists the jobs of `__deployment__.py` and their triggers.
4. Find the cause:

| Symptom | Cause | Fix |
|---|---|---|
| the job is not found (exit code `255`) | `__all__` does not list it, or `__deployment__.py` fails to import | list the job, fix the import, check with `--dry-run` |
| the job runs with the wrong destination or credentials | wrong active profile, or a pipeline created at the module level | check the banner, use `--profile`, create the pipeline inside the job |
| `ConfigFieldMissingException` for a job argument | no value in `[jobs.<module>]` of the active profile | set it in the profile config file, or pass `-c` |
| missing credentials | the secrets file of the active profile has no value | use the `setup-secrets` skill |

5. To start from a clean state, ask the user first. Then run `dlthub local clean`: it removes the state and the
   data of the active profile.

## 6. Add triggers

After the job succeeds here, add its triggers in the decorator: [triggers.md](triggers.md). Follow-up jobs, intervals,
freshness gates and refresh are in [job-patterns.md](job-patterns.md). A platform toolkit deploys the jobs.
