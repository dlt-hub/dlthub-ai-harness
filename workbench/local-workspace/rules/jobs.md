# Jobs and local job runs
* a **job** is a function declared with `@run.pipeline`, `@run.job`, `@run.interactive` or `run.agent` (`from dlt.hub import run`), or a module, that `__all__` in `__deployment__.py` lists. A deployment runs jobs. Each start of a job is a **job run**. A **job ref** is `jobs.<module>.<name>`.
* run a job on this machine with `dlthub local run <job>`. It resolves the job as a deployment does. A pipeline script that is not a job can still run with `uv run python <file>.py`.
* a job run activates its profile before it imports the job module, so a pipeline created at the module level runs with the profile of the job run. Create the pipeline at the module level when other jobs, notebooks or checks read its dataset: they import it.
* settings of a job are in `[jobs.<module>]` of the config files of the profile. Give a value for one job run with `-c key=value`.
* tests run on the `tests` profile, never on a remote profile.
* a deployment gives each job a profile of its environment by the data access the job declares: pipelines get the default write profile (`prod` in `prod`), notebooks `access`. **NEVER** give an agent job (`run.agent`) `prod` or any write data access: work that needs production write credentials is a pipeline or a plain job. The `setup-profiles` skill has the rules, use case "limit the data access of jobs".
* **read** about jobs, triggers and local job runs: https://dlthub.com/docs/hub/pipeline-operations/deployments.md and https://dlthub.com/docs/hub/pipeline-operations/triggers.md
