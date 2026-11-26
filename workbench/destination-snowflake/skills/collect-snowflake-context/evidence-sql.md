# Evidence SQL

Read this at steps 4 and 5 of `collect-snowflake-context`. It is not in the docs yet. The queries come from the
pre-load check and the build-time context of the Pipeline Guardian app, where they ran as hooks on every load.

All of them read `SNOWFLAKE.ACCOUNT_USAGE`. The role needs `IMPORTED PRIVILEGES` on the `SNOWFLAKE` database, or the
database roles `SNOWFLAKE.GOVERNANCE_VIEWER` (`ACCESS_HISTORY`, `QUERY_HISTORY`) and `SNOWFLAKE.OBJECT_VIEWER`
(`TABLES`, `COLUMNS`, `OBJECT_DEPENDENCIES`). `ACCESS_HISTORY` needs Enterprise edition or higher.

Replace the example names. Run each query on its own and read the result before the next one.

## Existing copies (step 4)

The tables with the planned names, or with a term in their name or comment, in every database the role can see.
Leave out the target schema, staging schemas, dlt system tables and nested tables:

```sql
SELECT table_catalog || '.' || table_schema || '.' || table_name AS fqn, row_count, comment, last_altered
FROM SNOWFLAKE.ACCOUNT_USAGE.TABLES
WHERE deleted IS NULL
  AND table_type = 'BASE TABLE'
  AND (table_name IN ('WORKFLOW_RUNS', 'JOBS')
       OR CONTAINS(LOWER(table_name), 'workflow')
       OR CONTAINS(LOWER(COALESCE(comment, '')), 'workflow'))
  AND NOT (table_catalog = 'ANALYTICS' AND table_schema = 'GITHUB_ACTIONS')   -- the target of the new pipeline
  AND table_schema NOT ILIKE '%\\_STAGING'
  AND table_name NOT ILIKE '\\_DLT%'
  AND NOT CONTAINS(table_name, '__');
```

The reads of the matches in the last 30 days, `SELECT` queries only:

```sql
SELECT o.value:objectName::STRING AS fqn,
       COUNT(DISTINCT ah.query_id) AS reads,
       COUNT(DISTINCT ah.user_name) AS users
FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY ah
JOIN SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY q
  ON q.query_id = ah.query_id AND q.query_type = 'SELECT',
LATERAL FLATTEN(ah.base_objects_accessed) o
WHERE ah.query_start_time >= DATEADD(day, -30, CURRENT_TIMESTAMP())
  AND o.value:objectName::STRING IN ('ANALYTICS.CI.WORKFLOW_RUNS', 'RAW.GITHUB.JOBS')
GROUP BY 1;
```

The verdict per planned table: no copy outside the target → **CLEAR**; copies outside the target, each read 50
times or fewer → **WARN**; a copy outside the target read more than 50 times → **CONFLICT**. A copy only in the
target schema is CLEAR: it is the table that the pipeline loads again.

## Usage evidence (step 5)

For one seed table, for example `ANALYTICS.CI.WORKFLOW_RUNS`, over the last 60 days.

The columns:

```sql
SELECT column_name, data_type, comment
FROM SNOWFLAKE.ACCOUNT_USAGE.COLUMNS
WHERE table_catalog = 'ANALYTICS' AND table_schema = 'CI' AND table_name = 'WORKFLOW_RUNS' AND deleted IS NULL
ORDER BY ordinal_position;
```

The queries that read the table, and from them the reads, the column reads and the tables queried with it:

```sql
WITH a AS (
  SELECT ah.query_id, ah.user_name, ah.query_start_time, ah.base_objects_accessed
  FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY ah, LATERAL FLATTEN(ah.base_objects_accessed) o
  WHERE ah.query_start_time > DATEADD(day, -60, CURRENT_TIMESTAMP())
    AND o.value:objectName::STRING = 'ANALYTICS.CI.WORKFLOW_RUNS'
    AND ah.user_name <> CURRENT_USER()
)
-- (a) reads
SELECT COUNT(DISTINCT query_id) AS reads, COUNT(DISTINCT user_name) AS users, MAX(query_start_time) AS last_read FROM a;
-- (b) column reads: run with the same CTE
-- SELECT c.value:columnName::STRING AS column_name, COUNT(DISTINCT a.query_id) AS reads
-- FROM a, LATERAL FLATTEN(a.base_objects_accessed) o, LATERAL FLATTEN(o.value:columns) c
-- WHERE o.value:objectName::STRING = 'ANALYTICS.CI.WORKFLOW_RUNS' GROUP BY 1 ORDER BY 2 DESC;
-- (c) tables queried together: the join candidates
-- SELECT o2.value:objectName::STRING AS other, COUNT(DISTINCT a.query_id) AS queries
-- FROM a, LATERAL FLATTEN(a.base_objects_accessed) o2
-- WHERE o2.value:objectName::STRING <> 'ANALYTICS.CI.WORKFLOW_RUNS'
--   AND o2.value:objectDomain::STRING IN ('Table', 'View')
-- GROUP BY 1 ORDER BY 2 DESC LIMIT 10;
```

The most frequent query shapes, with one example text each. They become the QBE of the document:

```sql
WITH a AS (... the same CTE ...)
SELECT q.query_parameterized_hash, COUNT(*) AS runs, COUNT(DISTINCT q.user_name) AS users,
       ANY_VALUE(q.query_text) AS example, MAX(q.start_time) AS last_run
FROM a JOIN SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY q ON q.query_id = a.query_id
WHERE q.query_type = 'SELECT' AND q.execution_status = 'SUCCESS'
  AND q.query_text NOT ILIKE '%ACCOUNT_USAGE%' AND q.query_text NOT ILIKE '%INFORMATION_SCHEMA%'
GROUP BY 1 ORDER BY 2 DESC, 3 DESC LIMIT 12;
```

The views and other objects built on the table:

```sql
SELECT referencing_database || '.' || referencing_schema || '.' || referencing_object_name AS fqn,
       referencing_object_domain
FROM SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES
WHERE referenced_database = 'ANALYTICS' AND referenced_schema = 'CI' AND referenced_object_name = 'WORKFLOW_RUNS';
```

## How to read the evidence

- **Unused columns** are the data columns missing from the column reads. Report them only when the table has reads
  at all.
- **Required filters**: a predicate in most of the query shapes, by several users.
- **Joins**: a table in "queried together" plus the `ON` clause in the example texts. Check the key names: a key
  joined to a differently named column is a trap to report.
- **Metrics**: the aggregates in the example texts (`SUM(cost) / NULLIF(COUNT(*), 0)`), with the filters they use.
- Clean the example texts: drop comments and literal ids, keep the logic and the table names.
- Cut long results: the 12 top query shapes and the 10 top co-accessed tables are enough.

## When a source is out

- **`ACCESS_HISTORY` is empty** (it needs Enterprise edition; some roles see no rows) while `QUERY_HISTORY` has
  rows: find the queries by their text instead. It is less exact: a name can match a comment or another table.

  ```sql
  SELECT query_parameterized_hash, COUNT(*) AS runs, COUNT(DISTINCT user_name) AS users,
         ANY_VALUE(query_text) AS example, MAX(start_time) AS last_run
  FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
  WHERE start_time > DATEADD(day, -60, CURRENT_TIMESTAMP())
    AND query_type = 'SELECT' AND execution_status = 'SUCCESS'
    AND query_text ILIKE '%WORKFLOW_RUNS%'
    AND query_text NOT ILIKE '%ACCOUNT_USAGE%' AND query_text NOT ILIKE '%INFORMATION_SCHEMA%'
    AND user_name <> CURRENT_USER()
  GROUP BY 1 ORDER BY 2 DESC, 3 DESC LIMIT 12;
  ```

  The reads per copy in step 4 come from the same filter, one copy at a time (match `SCHEMA.TABLE`). There are no
  column reads: say so in the document.
- **No ACCOUNT_USAGE access**: use `<database>.INFORMATION_SCHEMA.TABLES` and `COLUMNS` for the databases the role
  can see, for existing copies only. There is no usage evidence: say so in the document.
- **No usage yet** (new tables, or within the lag): the table context has only its columns and comments.
- **Org rules**: the Guardian app kept team rules in its own `CONTEXT_RULES` table. On an account with Cortex
  Sense, the `corrections` of step 3 take their place. Ask the user for rules that are in neither.
