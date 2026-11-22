---
name: setup-snowflake-destination
description: "Use when a dlt pipeline should load into Snowflake, moves from DuckDB to Snowflake, or fails there: a Snowflake connection in connections.toml (connection_name), the default connection, key-pair or PAT credentials, 'Account must be specified', quoted or lower-case column names, a __V_DOUBLE variant column, a leftover _staging dataset, lost grants after a replace, 'Non-nullable column _DLT_LOAD_ID cannot be added', tables another tool wrote. Configures and fixes Snowflake as a destination. Not for comments or semantic views (annotate-with-cortex)."
---

# Set up Snowflake as a dlt destination

The goal is a pipeline that loads into Snowflake with the same schema in each profile, and a
user who knows which Snowflake role, warehouse and database the load uses. Most Snowflake
problems with dlt come from three places: the credentials block, identifier case, and types
that dlt infers from the first rows. Check them in this order.

## 1. Find out what exists

Read the pipeline code and the `.dlt/` config names before you change anything:

- Pipeline name, dataset name, and the destination: `snowflake`, or a named destination such as
  `[destination.warehouse]` with `destination_type = "snowflake"`.
- Which profiles exist (`dev`, `prod`, `access`) and which destination each one uses. A common
  setup is duckdb in `dev` and Snowflake in `prod`.
- If the target tables already exist in Snowflake and who wrote them. If another tool wrote
  them, read `references/existing-tables.md` before the first load.

Never read or print the secrets file. Use the `setup-secrets` skill to see the shape of the
secrets and to set values.

## 2. Connection

Choose one of three ways. The credentials go under the destination's name: `[destination.snowflake.credentials]`, or
`[destination.warehouse.credentials]` for a named destination. Each profile can connect its own way (`setup-profiles`),
for example a personal connection in `dev` and a service user in `prod`.

**A Snowflake connection**, the usual choice on a developer machine. It is a named connection in the user's
`~/.snowflake/connections.toml`, the same one the Snowflake CLI and Cortex Code use. **Never read that file or a key
file.** Ask the user for the connection name, and let them test it with `snow connection test -c <name>`.

```toml
[destination.snowflake.credentials]
connection_name = "<name>"
database = "<DB>"                  # optional: overrides the database of the connection
```

The connection gives the account, the user and the authentication. Only `database`, `warehouse`, `role` and `query`
can override it: any other credential next to `connection_name` fails.

**No credentials**, only in a Snowpark Container Services job: dlt uses the connection that Snowflake mounts into
the container. Set `database`, `warehouse` or `role` only where they differ. On a developer machine, dlt never picks
the default connection by itself: name a connection. A profile that runs both locally and in a job keeps its
connection and falls back to the mounted one in the container:

```toml
[destination.snowflake.credentials]
connection_name = "<name>"
allow_default_connection_fallback = true   # use the default connection when <name> is not defined
```

**Explicit credentials**, for a service user without a connection. Prefer a key pair: it does not expire and does not
need a network policy. A programmatic access token (PAT) also works, but it expires and Snowflake usually requires a
network policy for the user. Write them with the `setup-secrets` skill:

```toml
[destination.snowflake.credentials]
host = "<account identifier>"      # for example myorg-myaccount, NOT the full URL
username = "<user>"
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----"
# private_key_passphrase = "..."
database = "<DB>"
warehouse = "<WH>"
role = "<ROLE>"
```

- `host` is the bare account identifier. A full `*.snowflakecomputing.com` URL or a
  region-qualified name the connector does not accept gives `Account must be specified`.
- For a PAT, set `authenticator = "PROGRAMMATIC_ACCESS_TOKEN"` and `token` in place of the
  private key.
- A native connection string also works: `snowflake://user:pass@account/db?warehouse=...`.
- A user behind a network policy connects only from the allowed addresses: a job that runs
  somewhere else needs a fixed egress address from the platform that runs it. PAT users always
  sit behind a policy.

In every case, name the role. Without it Snowflake uses the user's default role, and that role can be different
between a laptop and a job.

Then prove the connection with a query, before a full load (`<destination>` is `snowflake` or the destination's name):

```bash
uv run python -c "import dlt; p = dlt.pipeline('<pipeline>', destination='<destination>', dataset_name='<dataset>'); print(p.sql_client().__enter__().execute_sql('SELECT CURRENT_ROLE(), CURRENT_WAREHOUSE(), CURRENT_DATABASE()'))"
```

Tell the user the role, warehouse and database that come back.

## 3. Identifiers: choose the naming convention once

Snowflake stores unquoted identifiers in upper case. dlt's default `snake_case` convention
writes unquoted lower-case names, and Snowflake upper-cases them. That is correct for a new
dataset, so keep the default there.

Change the convention only when the names must match something that exists, and set it the
same in every profile. A case-sensitive convention (`duck_case`, `sql_cs_v1`) makes dlt write
quoted `"CompanyName"`, and for Snowflake that is a different column from `COMPANYNAME`. A
convention that differs between `dev` and `prod` gives two different schemas for one pipeline.

```toml
[sources.<name>]
schema.naming = "sql_ci_v1"   # keeps the characters, case-insensitive, unquoted
```

A convention does not rename tables that exist. Set it before the first load, or rebuild the
tables.

## 4. Types: pin what the first rows cannot tell

dlt infers a column type from the first values it sees. Three cases cause trouble on Snowflake:

- A number column whose first values are whole. dlt infers `bigint`. The first `12.5` then goes
  to a variant column `AMOUNT__V_DOUBLE`. Pin `double` (or `decimal`) with a column hint.
- A text column whose values look like ISO timestamps. dlt infers `timestamp`. Pin `text`, or
  remove the `iso_timestamp` detection for the source.
- Nested objects and arrays. dlt makes child tables by default. Pin `json` and set
  `max_table_nesting=0` if the column must stay one `VARIANT` column.

A pin has no effect on a column that exists. Pin before the first load. If the table exists,
rebuild it with `pipeline.run(..., refresh="drop_resources")`, and tell the user that this
drops and reloads the table.

## 5. Staging and replace behaviour

- `merge` and `replace` loads create a `<dataset>_staging` dataset. Clean it after each load:

  ```toml
  [load]
  truncate_staging_dataset = true    # set false only while you debug a merge
  ```

- All replace strategies work. `truncate-and-insert` is the default. Use `insert-from-staging`
  if downstream readers must never see an empty table during a load.
- All three `refresh` modes work on Snowflake.
- The role needs `USAGE` on the warehouse and the database, and `CREATE SCHEMA` on the
  database, because dlt creates the dataset and the staging dataset.

## 6. Verify

Run the pipeline once and check the result in Snowflake, not only in the dlt trace:

```sql
SELECT table_name, column_name, data_type
FROM <DB>.INFORMATION_SCHEMA.COLUMNS
WHERE table_schema = '<DATASET>'
ORDER BY table_name, ordinal_position;
```

Look for quoted or mixed-case names, `__V_` variant columns, and child tables that you did not
expect. Each one points back to step 3 or step 4.

## Known failures

| Error | Cause | Fix |
| --- | --- | --- |
| `Account must be specified` | full URL in `host` | bare account identifier |
| `<COL>__V_DOUBLE` appears | number inferred as `bigint` | pin `double`, rebuild with `refresh="drop_resources"` |
| values silently rounded | type pinned after the table existed | rebuild; a pin never alters a column that exists |
| `Non-nullable column '_DLT_LOAD_ID' cannot be added to non-empty table` | load into a table that dlt did not create | backfill `_dlt_*` first, see `references/existing-tables.md` |
| downstream roles lose access after a table swap | `CLONE` or `CREATE OR REPLACE` without `COPY GRANTS` | add `COPY GRANTS` |
| two columns that differ only in case | case-sensitive naming convention | `sql_ci_v1` or the default, the same in each profile |

## Next

When the load works, go back to the skill that sent you here. On a model of the loaded data,
offer dynamic tables (`create-snowflake-dynamic-tables`) and a semantic view
(`create-snowflake-semantic-view`); for comments grounded in the rows, `annotate-with-cortex`.

## Reference docs

- dlt Snowflake destination: https://dlthub.com/docs/dlt-ecosystem/destinations/snowflake.md
- dlt naming conventions: https://dlthub.com/docs/general-usage/naming-convention.md
- dlt schema and column hints: https://dlthub.com/docs/general-usage/schema.md
- dlt replace strategies: https://dlthub.com/docs/general-usage/full-loading.md
- dlt credentials setup: https://dlthub.com/docs/general-usage/credentials/setup.md
- Snowflake key-pair authentication: https://docs.snowflake.com/en/user-guide/key-pair-auth
