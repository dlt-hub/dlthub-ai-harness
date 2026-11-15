---
name: setup-profiles
description: "Use when the user wants different credentials or settings for dev, tests and production: DuckDB locally and a warehouse in production, tests isolated on the tests profile, read-only or no data access for jobs, a staging environment, or running and inspecting with another profile. Declares and switches dlt profiles and environments. Not for picking the first destination of a new pipeline."
---

# Profiles and environments

**Reference**: https://dlthub.com/docs/hub/pipeline-operations/profiles.md

## What they are

- A **profile** holds the credentials a pipeline or job runs with and declares their **data access**: `write`,
  `read` or `none` (write includes read). dlt never checks what a credential can do: the user sets up its rights at
  the destination (a profile with read data access gets a read-only role or key).
- A profile also holds **settings files**: `.dlt/<profile>.config.toml` and `.dlt/<profile>.secrets.toml` add to the
  shared `config.toml` and `secrets.toml` and win over them. Each profile has its own state and data folders
  (`.dlt/state/<profile>/`, `.dlt/data/<profile>/`): two profiles never share pipeline state or a local DuckDB file.
- **Local** profiles (`dev`, the default, and `tests`) never leave this machine. Their settings files never deploy.
  **Remote** profiles belong to an environment and deploy with it.
- An **environment** is what a deployment is made to. Each environment has a remote workspace of its own. `prod`, the
  default, is for production. `staging`, for example, is for a review of changes on small data. An environment
  declares:
  - its **profiles**, deployed together (`prod` ships `prod` and `access`).
  - one **default profile** for each data access that its profiles have. The default profile with write data access
    is the **default write profile**: a deployment is made with it. In `prod`, `prod` is the default write profile
    and `access` the default profile with read data access. The first profile of a data access that you add becomes
    its default.
  - whether it is **strict about access** (`strict_access`). `prod` is not strict. Every environment that
    `dlthub profile add-environment` declares is strict.
- **How a job gets its profile** in a deployment. Each job declares the data access that it needs: with
  `access={"data": [...]}` on the job, or by its kind:

  | Job                                                  | Data access it declares                             |
  | ---------------------------------------------------- | --------------------------------------------------- |
  | batch and stream jobs (`@run.pipeline`, `@run.job`)  | write                                               |
  | interactive jobs (notebooks, dashboards)             | read                                                |
  | agent jobs, and any job with `access`                | what `access.data` declares, `none` without `data`  |

  - A job without a declared profile gets the default profile of its data access. That profile must have settings
    files, unless it has no data access.
  - A job that declares `require={"profile": ...}` keeps that profile. The profile must belong to the environment.
  - In an environment that is not strict, a job whose default profile is missing or has no settings files gets the
    closest default profile with more data access, and `deploy` warns. In the end that is the default write profile.
  - A strict environment gives exactly the declared data access. Otherwise `deploy` fails and names the fix.
- **Which profile a local command runs with**, the first that applies:
  1. `--profile <name>`, before or after the command.
  2. `WORKSPACE__PROFILE`.
  3. The active profile that `dlthub local profile use <name>` recorded in `.dlt/profile-name`.
  4. The default profile, `dev`.

  An environment name is not a profile name.
- **Which environment** a command that deploys or works with a deployment uses (deploy, jobs, runs, logs):
  `--environment <name>`, else the environment of the active profile when it is remote, else the default environment.
- In code, `dlt.current.workspace().profile` is the active profile, and `.environment` is its environment (`None` for
  a local profile).

## Before you change anything

1. See what is declared: `dlthub profile list` (profiles per environment, with the remote workspace of each) and
   `dlthub profile info` (the active profile, its settings files and folders). The `list_profiles` and
   `get_workspace_info` MCP tools return the same.
2. `dlthub profile add` and `dlthub profile add-environment` show what they declare and which files they create, then
   ask. With `--non-interactive`, they do not ask. Before you run them, **STOP** and show your plan to the user.
3. Write credentials to the secrets file of the profile with the `setup-secrets` skill. Pass that file as `path`.
4. Write `destination_type` in the config file of the profile, never with `secrets_update_fragment`. It is a setting,
   not a secret.
5. The profiles and environments live in `.dlt/.workspace`, a yaml file that dlt writes. Change it with
   `dlthub profile add` and `dlthub profile add-environment`. For other changes, edit the file directly.
   [workspace-file.md](workspace-file.md) says how to change the default profile of a data access, rename a profile,
   make an environment strict or not strict, change the default environment, remove a profile or an environment, and
   start over. Keep the default environment `prod` and its
   profiles `prod` and `access` as they are.

## Run on another profile

1. Before you read or write data with a remote profile, **ALWAYS** ask the user. Remote profiles hold production or
   staging credentials.
2. For one command, override the active profile with `--profile <name>`, before or after the command, or with
   `WORKSPACE__PROFILE=<name>`.
3. For a command that deploys or works with a deployment, name `--environment <env>`. These commands take no
   `--profile`.
4. For the session and the MCP tools, make it the active profile: `dlthub local profile use <name>`. When you are
   done, make `dev` the active profile again.
5. The MCP tools read the active profile on every call, so they need no restart. `list_profiles` and
   `get_workspace_info` also take `profile`, which overrides the active profile for one call.

## Use case 1: DuckDB locally, a warehouse in production

The pipeline names its destination. Each profile says what the name means. The code never changes.

1. In the pipeline, use a named destination: `destination="warehouse"`.
2. In `.dlt/dev.config.toml`, set `destination_type = "duckdb"` under `[destination.warehouse]`.
3. In `.dlt/prod.config.toml`, set the production `destination_type` under `[destination.warehouse]`. Put its
   `credentials` under the same section in `.dlt/prod.secrets.toml`.
4. Put settings that differ per profile in the config file of each profile. For example, set the load limit of a job
   under `[jobs.<module>]` in `dev.config.toml` and `prod.config.toml`.
5. Run on this machine: `dlthub local run <pipeline script>`. The data goes to `.dlt/data/dev/` and the state to
   `.dlt/state/dev/`.
6. Before the first deployment, check the production credentials. From the project root, run
   `uv run python <skill folder>/check_destination.py prod warehouse [dataset_name]`
   ([check_destination.py](check_destination.py)). Or make `prod` the active profile and restore the pipeline state
   from the destination:
   `dlthub --debug local pipeline sync <pipeline> --destination warehouse --dataset-name <dataset>`.
   Run `sync` only on a fresh `prod` state. It drops the local working directory. Before the first load,
   "Pipeline ... was not found in dataset ..." is expected.
7. Deploy with `deploy`. It deploys to the default environment `prod`, with `prod`, its default write profile.
8. To reach the production data from this machine, make `prod` the active profile as
   [Run on another profile](#run-on-another-profile) says.

## Use case 2: run tests on the `tests` profile

`tests` has its own state and data, so tests never touch the pipelines on `dev`, and both can run at the same time.

1. In `.dlt/tests.config.toml`, define `warehouse` as for `dev` (`destination_type = "duckdb"`).
2. Make `tests` the active profile for every test in `conftest.py`:

   ```py
   import pytest
   import dlt

   @pytest.fixture(autouse=True, scope="session")
   def tests_profile() -> None:
       dlt.current.workspace().switch_profile("tests")
   ```

   Or override the profile for one `pytest` run: `WORKSPACE__PROFILE=tests uv run pytest`.
3. If a test fails, inspect its pipeline with `--profile tests`:
   `dlthub --profile tests local pipeline trace <pipeline>`, `... failed-jobs <pipeline>`, `dlthub --profile tests local show`.
4. `dlthub --profile tests local clean` removes the test data and state.

## Use case 3: limit the data access of jobs

1. In `prod`, jobs that declare read data access get `access`, its default profile with read data access. Put
   read-only credentials in `.dlt/access.secrets.toml`. The user creates the read-only role or token at the
   destination. Until `access` has settings files, these jobs get `prod`, and `deploy` warns about each of them.
2. If a batch job only reads, declare it on the job: `@run.job(access={"data": ["read"]})`. Then it gets `access`, not
   `prod`.
3. If an agent job needs no credentials of its own, declare no profile on it. Keep `write` out of `access.data` in
   its agent definition. Without `data` in `access`, the agent job declares no data access.
4. Add a profile without data access to every environment that the agent job deploys to:
   `dlthub profile add <env>-none --access none --env <env>`. It needs no settings files and reads only the shared
   `config.toml` and `secrets.toml`. Keep destination credentials out of these shared files.
   - In `prod` without such a profile, the agent job gets `access`, or `prod` while `access` has no settings files.
     `deploy` warns.
   - In a strict environment without one, `deploy` fails.
5. If a job must not share `access`, give it a profile of its own. An agent job that reads personal data is an
   example:
   - Declare the profile: `dlthub profile add sensitive-access --access read`. It is not the default, because
     `access` is.
   - Put its read-only credentials in `.dlt/sensitive-access.secrets.toml`.
   - Declare it on the job: `require={"profile": "sensitive-access"}`. The agent definition declares `data: read`.

   A declared profile must belong to the environment. For each other environment, declare a profile there and pick
   it in `__deployment__.py`, as use case 4, step 3 shows. To make another profile the default of its data access,
   see [workspace-file.md](workspace-file.md).

## Use case 4: a staging environment with its own remote workspace

A staging environment deploys the same workspace to a second remote workspace, with its own credentials and settings.
Changes run there on small data before they reach `prod`.

1. Declare the environment and the profile that interactive jobs need:

   ```sh
   dlthub profile add-environment staging          # strict, default write profile staging-write
   dlthub profile add staging-read --access read --env staging
   ```

   `staging` is strict. `staging-read` is its first profile with read data access, so it is the default that
   interactive jobs get. Without it, a deployment with a notebook fails. If the jobs need more profiles, add them, for
   example `dlthub profile add staging-sensitive-access --access read --env staging`. It is not a default: only a job
   that declares it gets it. For agent jobs, add `staging-none` as use case 3 says.
2. Put the staging credentials in `.dlt/staging-write.secrets.toml` and the other `staging-*` secrets files. Put the
   staging settings, for example a smaller load limit, in `.dlt/staging-write.config.toml`. In a strict environment,
   a profile without settings files does not count: every profile with data access needs its files.
3. Vary the deployment by environment in `__deployment__.py`: read `dlt.current.workspace().environment` to decide
   which jobs deploy and which profile a job declares. Credentials and limits stay in the settings files.
4. Deploy with `deploy --environment staging`. The deployment module runs with `staging-write`, the default write
   profile, so the environment there is `staging`. The first deployment connects the local workspace to the remote workspace `<workspace>-staging`
   and writes `[workspace.environment.staging]` (`workspace_id`, `workspace_name`) into `config.toml`. `deploy`
   without `--environment` still goes to `prod`.
5. To work with the staging deployment, name `--environment staging` on each command, for example
   `job list --environment staging`. Or make `staging-read` the active profile: `dlthub local profile use staging-read`.
   Then a plain `deploy` also goes to `staging`, and local commands run with `staging-read`. When you are done, make
   `dev` the active profile again.
