---
name: setup-snowflake-workspace
description: Set up a dlthub workspace to deploy and run its jobs on Snowflake with the SPCS Context Runner. Checks the tools, the Snowflake connection and role that deploy uses, names the workspace, and verifies the setup with `dlthub snowflake info` and the MCP server. Use when the user wants to deploy, run or schedule pipelines on Snowflake for the first time, or when a `dlthub snowflake` command fails on setup. Do NOT use to install the runner in an account (that is the admin skill `install-snowflake-runner`) or to choose where jobs load data (`setup-snowflake-data-connection`).
argument-hint: "[connection-name]"
---

# Set up the workspace for Snowflake

Get one local workspace ready to deploy to Snowflake. At the end, `uv run dlthub snowflake info` shows the
connection, the role and the workspace schema without errors.

**Reference**: `README.md` § Getting started, step 3 · `uv run dlthub snowflake info --help`

The runner must be installed in the account, and the user's role must be granted (`README.md` § Getting started,
steps 1–2). Both are admin work: when a step below fails because of them, go to step 6.

## 1. Check the tools

Deploy builds a docker image on this machine and pushes it to Snowflake, so three tools must work:

```sh
uv run dlthub --version
snow --version
docker info --format '{{.ServerVersion}}'
```

- `uv` or `dlthub` missing: follow the workspace setup in the `init-dlthub-workspace` rule.
- `snow` missing: the user installs the Snowflake CLI (https://docs.snowflake.com/en/developer-guide/snowflake-cli/installation/installation).
- `docker info` fails: the user starts docker. Deploy cannot build images without it.

## 2. Pick the Snowflake connection

Deploy uses one connection from `~/.snowflake/connections.toml`. Its role is the role that the admin granted: deploy
creates the Snowflake tasks as this role, and the jobs run as it.

**Never read `~/.snowflake/connections.toml` or a key file.** Ask the user for the connection name (`$ARGUMENTS`
when given). If they have none, show them the block to add, from `README.md` § Getting started, step 3:

```toml
[dlthub]
account = "MYORG-MYACCOUNT"
user = "JANE"
authenticator = "SNOWFLAKE_JWT"
private_key_file = "~/.snowflake/keys/jane_rsa_key.p8"
role = "DATA_ENGINEER"     # the role that the admin granted
warehouse = "COMPUTE_WH"   # runs the queries of the commands, not the jobs
database = "ANALYTICS"     # the database of the install
```

Then test it. The output shows the account, user, role and database, not the key:

```sh
snow connection test -c dlthub
```

If the role or database is not what the admin granted, the user fixes the connection. Wait until the test passes.

## 3. Name the workspace and the connection

Two settings in `.dlt/config.toml`. The workspace name becomes the name of the remote workspace and of the
workspace schema (`DLTHUB_<NAME>`):

```toml
[workspace.settings]
name = "github_actions"

[snowflake.deploy]
deploy_connection_name = "dlthub"   # else the default Snowflake connection
```

- Pick a short name for what the workspace does. Changing it later creates a new workspace schema.
- If the admin installed the runner with other names than the defaults (pool, warehouse, app, integration), add
  them under `[snowflake.deploy]` as `README.md` § Getting started, step 2 lists.

**STOP**: show the two settings and get a yes before you write them.

## 4. Check the setup

```sh
uv run dlthub snowflake info
```

Read both sections:
- **dltHub**: the environment (`prod`, the default), the profiles with their data access, the remote workspace and
  the organization. Before the first deploy, the remote workspace has no id yet: that is fine.
- **Snowflake**: the connection, `Role`, `Database`, `Workspace schema`, `Compute pool`, `Jobs warehouse` and the
  external access integration.

When there is an `Error` line, it says what happened, why and what to run. Do what it says, or go to step 6 when it
names an admin.

## 5. Give Cortex Code the Snowflake tools

The dlt workspace MCP server serves read-only Snowflake tools (`snowflake_info`, `snowflake_list_jobs`,
`snowflake_list_job_runs`, `snowflake_get_run_logs`, `snowflake_list_secrets`) when it runs with the `snowflake`
feature. Check:

```sh
uv run dlthub ai status
```

It checks the MCP config that this Cortex Code surface reads. When the server is missing or serves no Snowflake
tools, it prints the fix and how to reload, and you do what it says. In the CLI, for example:

```sh
cortex mcp remove dlt-workspace-mcp   # only when it is registered without the snowflake feature
cortex mcp add dlt-workspace-mcp uv run dlthub ai mcp --stdio --features +snowflake
```

In Desktop, the fix is the entry it prints, put into `mcpServers` of `.cortex/mcp.json`. Keep the other servers
there, and commit the file.

## 6. When the fix needs an admin

Errors that name an admin mean the runner is not installed, or the role has no grant. Do not try to work around
them. Write the user a short message for their admin with:
- the account and the role from step 2;
- the command from the error, or `make grant-role CONNECTION=<admin connection> DATABASE=<database> ROLE=<role>`;
- a pointer to `admin/README.md`.

The admin can run (`install-snowflake-runner`) in their own session.

## Next

The workspace is set up. Continue with the workflow: declare the jobs (`prepare-deployment`, step 3 only), then
(`setup-snowflake-data-connection`).
