---
name: setup-snowflake-destination
description: Configure and verify Snowflake as the destination of a dlt pipeline - key-pair or PAT credentials, the account identifier, the naming convention, type pins, staging and replace behaviour - and fix the load errors that are specific to Snowflake. Use this whenever a dlt pipeline should load into Snowflake, moves from duckdb to Snowflake, or fails there, for example "Account must be specified", quoted or lower-case column names, a `__V_DOUBLE` variant column, a leftover `_staging` dataset, lost grants after a replace, or "Non-nullable column '_DLT_LOAD_ID' cannot be added". Also use it when dlt takes over tables that another tool wrote (Airbyte, Fivetran, hand-made tables) and the columns and types must match. Do NOT use to write comments or a semantic view on loaded data, use annotate-with-cortex for that.
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

## 2. Credentials

Prefer key-pair authentication. It does not expire and does not need a network policy. A
programmatic access token (PAT) also works, but it expires and Snowflake usually requires a
network policy for the user.

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
- Name the role. Without it Snowflake uses the user's default role, and that role can be
  different between a laptop and a job.
- On the dltHub platform, a Snowflake user behind a network policy needs
  `require={"static_egress_ips": True}` on the job. PAT users always sit behind a policy.

Then prove the connection with a query, before a full load:

```bash
uv run python -c "import dlt; p = dlt.pipeline('<pipeline>', destination='snowflake', dataset_name='<dataset>'); print(p.sql_client().__enter__().execute_sql('SELECT CURRENT_ROLE(), CURRENT_WAREHOUSE(), CURRENT_DATABASE()'))"
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

When the load works, continue with `annotate-with-cortex` to let a Cortex agent write comments
and a semantic view on the loaded tables.

## Reference docs

- dlt Snowflake destination: https://dlthub.com/docs/dlt-ecosystem/destinations/snowflake.md
- dlt naming conventions: https://dlthub.com/docs/general-usage/naming-convention.md
- dlt schema and column hints: https://dlthub.com/docs/general-usage/schema.md
- dlt replace strategies: https://dlthub.com/docs/general-usage/full-loading.md
- dlt credentials setup: https://dlthub.com/docs/general-usage/credentials/setup.md
- Snowflake key-pair authentication: https://docs.snowflake.com/en/user-guide/key-pair-auth
