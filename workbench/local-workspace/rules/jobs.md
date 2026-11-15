# Jobs and local job runs
* a **job** is a function declared with `@run.pipeline`, `@run.job`, `@run.interactive` or `run.agent` (`from dlt.hub import run`), or a module, that `__all__` in `__deployment__.py` lists. A deployment runs jobs. Each start of a job is a **job run**. A **job ref** is `jobs.<module>.<name>`.
* run a job on this machine with `dlthub local run <job>`. It resolves the job as a deployment does, with the active profile. A pipeline script that is not a job can still run with `uv run python <file>.py`.
* create a pipeline inside the job that runs it, not at the module level. A pipeline takes the profile that is active when it is created.
* settings of a job are in `[jobs.<module>]` of the config files of the profile. Give a value for one job run with `-c key=value`.
* tests run on the `tests` profile, never on a remote profile.
* **read** about jobs, triggers and local job runs: https://dlthub.com/docs/hub/pipeline-operations/deployments.md and https://dlthub.com/docs/hub/pipeline-operations/triggers.md
