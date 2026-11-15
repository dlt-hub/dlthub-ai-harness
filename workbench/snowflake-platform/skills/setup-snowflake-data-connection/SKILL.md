---
name: setup-snowflake-data-connection
description: Decide and configure where the jobs of a workspace load and read data on Snowflake, step by step. Sets up the `prod` profile with a Snowflake destination, by default with the connection that Snowflake gives each job (the deploying role, the database of the workspace schema), or with another database, role or user, and the `access` profile for jobs that only read. Use before the first deploy to Snowflake, when the user wants the jobs to load into another database or as another role, or when a job fails on Snowflake credentials. Replaces steps 1–2 of `prepare-deployment` on Snowflake. Do NOT use for the deploy connection (`setup-snowflake-workspace`) or for local-only destinations.
argument-hint: "[destination-name] [database]"
---

# Set up the data connection

The **data connection** is where and as whom the jobs load and read data. It is not the deploy connection of
`setup-snowflake-workspace`, though by default the two use the same role. Each profile holds one data connection:
`prod` for the jobs that write, `access` for the jobs that only read, `dev` for this machine.

**Reference**: `README.md` § Loading into Snowflake and § Environments · (`setup-profiles`) use cases 1 and 3 ·
(`setup-secrets`) · https://dlthub.com/docs/dlt-ecosystem/destinations/snowflake

Ask one question per step. Write nothing until step 7.

## 1. Read the jobs

Read `__deployment__.py` and the job modules it imports. For each job, note:
- its pipeline, the destination it names and the dataset;
- its declared data access: write (the default for a batch job) or read (`@run.job(access={"data": ["read"]})`).

The pipelines must use a **named destination**, for example `destination="warehouse"`, so each profile can say what
`warehouse` means. When a pipeline names a destination type (`destination="duckdb"`), propose the change first, as
(`setup-profiles`) use case 1 says.

## 2. Show the default data connection

On Snowflake, a destination without credentials uses the connection that Snowflake gives the job:

| | In a job on Snowflake | In a local run with `prod` |
|---|---|---|
| role | the role that deployed (it owns the Snowflake task) | the role of your default Snowflake connection |
| database | the database of the workspace schema | the database of that connection |
| warehouse | the jobs warehouse | the warehouse of that connection |

Run `uv run dlthub snowflake info` and fill in the real values: `Role`, `Database`, `Workspace schema`,
`Jobs warehouse`. Then ask: **"The jobs will load into `ANALYTICS` as `DATA_ENGINEER`. Is that where the data should
go?"**

- **Yes**: the `prod` profile needs only the destination type. Write `.dlt/prod.config.toml`:

  ```toml
  [destination.warehouse]
  destination_type = "snowflake"
  ```

  The secrets hold no Snowflake password. Go to step 5.
- **Another database**: step 3. **Another role or user**: step 4.

## 3. Another database

Set only `database` under the credentials of the destination, in the secrets of `prod`. The role and the warehouse
stay the default:

```toml
# .dlt/prod.secrets.toml
[destination.warehouse.credentials]
database = "RAW"
```

- Write it with (`setup-secrets`). Never read a secrets file.
- The deploying role needs `CREATE SCHEMA` on that database (dlt creates the dataset schemas). Check:
  `SHOW GRANTS ON DATABASE RAW;`. When it is missing, the user asks an admin for
  `GRANT USAGE, CREATE SCHEMA ON DATABASE RAW TO ROLE DATA_ENGINEER;`.

## 4. Another role or user

The jobs then connect as a separate Snowflake user, with its own role and access. Read
[another-role.md](another-role.md) now: it has the credentials, the grants and the checks.

- The user creates the Snowflake user, its key pair and its role, or asks an admin for them.
- The credentials go to `.dlt/prod.secrets.toml` with (`setup-secrets`), as placeholders that the user fills in.
- Deploy pushes the secrets of each profile to Snowflake secrets. The jobs read them there.

## 5. Jobs that only read

Notebooks, agent jobs and batch jobs that declare read access get the `access` profile, not `prod`. Ask: **"Some
jobs only read. Should they use a role that can only read?"**

- **Yes**: put a read-only data connection in `.dlt/access.secrets.toml`, as step 4 does for `prod`. The role needs
  `USAGE` on the database and schemas and `SELECT` on the tables.
- **No**: until `access` has settings files, those jobs use `prod`. `deploy` warns about each of them.

(`setup-profiles`) use case 3 explains data access in full.

## 6. Keep local development local

`dev` stays what it is: DuckDB, or the user's own Snowflake connection.
- When `dev` is DuckDB and the workspace has transformations, run (`debug-transformation`, transformations toolkit)
  for the SQL dialect check before the first deploy.
- A local run with `prod` (`WORKSPACE__PROFILE=prod`) writes into the production data with your local connection.
  Do it only after the user agrees.

## 7. Show the plan and write

**STOP**: show the user every file you will change, and the role and database each job will use. Example:

```txt
load_github_actions (write)  -> prod   -> ANALYTICS as DATA_ENGINEER (the default connection)
github_report        (read)  -> access -> ANALYTICS as REPORT_READER (key pair, .dlt/access.secrets.toml)
files: .dlt/prod.config.toml (new), .dlt/access.config.toml (new), .dlt/access.secrets.toml (placeholders)
```

After a yes, write the files. Make sure no placeholder is left in the secrets of `prod` or `access` before deploy:
`uv run dlthub ai secrets list` shows the files and their keys, not the values.

## Next

Test the jobs locally (`run-local-jobs`, `test-local-jobs`), then deploy (`deploy-snowflake-workspace`). The data
connection of a job is checked for real at its first job run on Snowflake.
