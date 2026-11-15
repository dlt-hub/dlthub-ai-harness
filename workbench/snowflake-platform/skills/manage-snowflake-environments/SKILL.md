---
name: manage-snowflake-environments
description: Deploy the same dlthub workspace to Snowflake more than once, as separate environments such as `ci` or `staging`. Adds the environment, names its remote workspace and workspace schema, gives it its own data connection when it needs other data or another role, deploys and works with it. Use when the user wants a ci, test or staging deployment next to `prod`, or a second schema for the same jobs. Do NOT use for local profiles only (`setup-profiles`).
argument-hint: "[environment]"
---

# Environments on Snowflake

An **environment** is one deployment of the workspace. On Snowflake each environment has its own remote workspace
and its own workspace schema, with its own Snowflake tasks, secrets and job runs. `prod` is the default. The same
local code deploys to as many environments as the roles allow.

**Reference**: `README.md` § Environments and § Add a ci environment · (`setup-profiles`) use case 4 ·
https://dlthub.com/docs/hub/pipeline-operations/profiles.md

## 1. Agree on what the environment is for

Ask what the second deployment does, because that decides the data connection:
- **ci or test**: the same jobs, small data, often the same role. Example: a test schema that CI deploys to on each
  merge.
- **staging**: the same jobs, separate data, often another database or role.

Also ask which jobs deploy there. `__deployment__.py` can deploy fewer jobs to an environment: read
`dlt.current.workspace().environment` there, as (`setup-profiles`) use case 4, step 3 shows.

## 2. Add the environment

```sh
uv run dlthub profile add-environment ci
```

It adds the environment and its default write profile (`ci-write`) to `.dlt/.workspace`. Add a read profile when
the environment deploys jobs that only read: `uv run dlthub profile add ci-read --access read --env ci`.

## 3. Name the remote workspace

By default the remote workspace is `<workspace name>-ci` and its schema is `DLTHUB_<WORKSPACE NAME>_CI`. To name it
differently, set the workspace name of the environment **before the first deploy**. The schema follows the name.
Do not set `workspace_schema` directly:

```toml
# .dlt/config.toml
[workspace.environment.ci]
workspace_name = "github_actions_test"   # schema DLTHUB_GITHUB_ACTIONS_TEST
```

## 4. Give it its data connection

The profiles of the environment hold its data connection. Run (`setup-snowflake-data-connection`) for the profiles
of this environment (`ci-write` instead of `prod`, `ci-read` instead of `access`):
- the same data, the same role: settings files with the same content as `prod`;
- small data: smaller load limits in `.dlt/ci-write.config.toml`, for example under `[jobs.<module>]`;
- other data or another role: its own credentials in `.dlt/ci-write.secrets.toml`.

An environment can also deploy as another Snowflake role: set `deploy_connection_name` under
`[snowflake.deploy]` in the config of its write profile. That role needs the grant of the admin
(`install-snowflake-runner`, step 5).

**STOP**: show the files you will add and what each profile connects to. Get a yes.

## 5. Deploy and work with it

```sh
uv run dlthub snowflake deploy --environment ci --dry-run
uv run dlthub snowflake deploy --environment ci
uv run dlthub snowflake job list --environment ci
```

- `--environment ci` goes anywhere in a command. Without it, the commands work with `prod`.
- The first deploy writes `[workspace.environment.ci] workspace_id` to `.dlt/config.toml`. Commit it, so CI uses the
  same remote workspace.
- The deploy record goes to `.dlthub/snowflake/deploy/ci/`.

## Next

Daily work on the environment is (`maintain-snowflake-jobs`) with `--environment ci`.
