# A data connection with another role or user

Read this at step 4 or step 5 of `setup-snowflake-data-connection`. It is not in the docs yet.

## What works on Snowflake

- **No credentials**: dlt uses the default Snowflake connection. In a job service that is the connection that
  Snowflake mounts into the container: the role that owns the Snowflake task. On this machine it is your default
  connection in `connections.toml`.
- **`database`, `warehouse` or `role` alone**: they override the default connection. `database` is the tested case
  (`README.md` § Loading into Snowflake). A `role` override in a job service is not verified: the token of a job
  service belongs to the role that owns it. Prefer a separate user for another role.
- **`connection_name`**: never in `prod` or `access`. The container has no `connections.toml` of yours, only the
  mounted connection.
- **Explicit credentials** (a separate user): the job connects to the account like any client. This is the way to
  load as another role.

## Explicit credentials with a key pair

Key-pair auth works in a container: there is no browser and no MFA prompt. The private key goes into the secrets,
not into a file path, because the container has no key files:

```toml
# .dlt/prod.secrets.toml (or .dlt/access.secrets.toml): placeholders, the user fills in the values
[destination.warehouse.credentials]
host = "MYORG-MYACCOUNT"          # the account identifier
username = "DLT_LOADER"
role = "LOADER"
warehouse = "LOADER_WH"           # a warehouse that the role can use; it runs the load queries
database = "RAW"
private_key = "<the PEM text of the private key, or its base64>"
private_key_passphrase = "<only when the key is encrypted>"
```

Write them with (`setup-secrets`): it writes placeholders, the user pastes the values into the file in their editor.
Never ask for the key in the chat, and never read the file.

## Grants the role needs

The user or an admin runs these for the new role. Show them, do not run them without a yes:

```sql
-- write (prod)
GRANT USAGE ON DATABASE RAW TO ROLE LOADER;
GRANT CREATE SCHEMA ON DATABASE RAW TO ROLE LOADER;
GRANT USAGE ON WAREHOUSE LOADER_WH TO ROLE LOADER;
-- read only (access)
GRANT USAGE ON DATABASE RAW TO ROLE REPORT_READER;
GRANT USAGE ON ALL SCHEMAS IN DATABASE RAW TO ROLE REPORT_READER;
GRANT SELECT ON FUTURE TABLES IN DATABASE RAW TO ROLE REPORT_READER;
GRANT USAGE ON WAREHOUSE REPORT_WH TO ROLE REPORT_READER;
```

The role that loads owns the dataset schemas that dlt creates. A read-only role needs `SELECT` on the tables of
those schemas: grant it on future tables in each schema once the schemas exist.

## How the credentials reach the job

1. `deploy` reads the secrets of each profile of the environment and pushes them as Snowflake secrets into the
   workspace schema. The secrets provider of the job reads them back and merges them in memory.
2. `uv run dlthub snowflake secrets list` shows the secrets files and the Snowflake secrets that deploy pushed, by
   name.
3. The job service reaches the account through the external access integration. The default integration allows every
   host. A workspace integration with `egress_hosts` must list the account host.

## Check it

- Before deploy, on this machine: (`setup-profiles`) use case 1, step 6, checks the `prod` credentials.
- After deploy: the first job run on Snowflake (`run <job> -f`). A failure at connect shows the Snowflake error in
  the log: a wrong key, a missing grant, or a network rule.
