# Take over Snowflake tables that another tool wrote

Read this when dlt must load into tables that exist, for example tables from Airbyte
(Destinations V2). These rules come from a migration of about 70 jobs. The aim is that dlt
writes the same column names and types, so downstream models do not change.

## Identifiers

Airbyte's Snowflake destination writes identifiers that Snowflake stores upper-cased. Use
`sql_ci_v1`: it keeps the characters, lower-cases them and declares itself case-insensitive.
dlt then writes unquoted identifiers, and Snowflake upper-cases them. The names match.

Verify, do not assume:

```sql
SELECT table_name, column_name, data_type
FROM <SOURCE_DB>.INFORMATION_SCHEMA.COLUMNS
WHERE table_schema = '<SCHEMA>' AND table_name = '<TABLE>';
```

## Type mapping

| The other tool declares | Its column | dlt default | Pin as |
| --- | --- | --- | --- |
| nullable string | `VARCHAR` | `text`, or `timestamp` if it parses as ISO | `text` + `remove_type_detection("iso_timestamp")` |
| nullable integer | `NUMBER(38,0)` | `bigint` | `bigint` |
| nullable number | `FLOAT` | `bigint` if the first value is whole | `double`, the most common cause of variant columns |
| nullable boolean | `BOOLEAN` | `bool` | `bool` |
| object / array | `VARIANT` | flattened columns / child tables | `json` + `max_table_nesting=0` |

Airbyte types the declaration, not the values. A column declared `number` is `FLOAT` even if
each value so far is whole. Pin `double` before dlt first creates the table. Pin ids that
arrive as `FLOAT` as `double` too, if the column type must match.

## Cutover with a zero-copy clone

A clone copies the history at almost no cost:

```sql
CREATE OR REPLACE TABLE <TARGET_DB>.<SCHEMA>.<TABLE>
CLONE <SOURCE_DB>.<SCHEMA>.<TABLE>
COPY GRANTS;
```

`COPY GRANTS` is necessary. Without it each downstream role loses access on the replace.

## Backfill the dlt columns

dlt adds `_dlt_load_id` and `_dlt_id` as non-nullable columns. Snowflake cannot add a
non-nullable column to a table with rows, and a column default cannot reference other
columns. Do it in three statements before the first dlt load:

```sql
ALTER TABLE <T> ADD COLUMN _dlt_load_id VARCHAR, _dlt_id VARCHAR;
UPDATE <T> SET _dlt_load_id = '<backfill load id>', _dlt_id = UUID_STRING();
ALTER TABLE <T> MODIFY COLUMN _dlt_load_id SET NOT NULL, COLUMN _dlt_id SET NOT NULL;
```

dlt load ids are Unix timestamps stored as strings, and they sort as strings. Choose a
backfill load id with the same format that sorts before each real load id.

## Docs

- dlt naming conventions: https://dlthub.com/docs/general-usage/naming-convention.md
- dlt schema and column hints: https://dlthub.com/docs/general-usage/schema.md
- Snowflake `CREATE ... CLONE`: https://docs.snowflake.com/en/sql-reference/sql/create-clone
