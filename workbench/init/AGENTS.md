## ALWAYS ACTIVATE those skills
they are essential for ANY work in this project

## Security
CRITICAL: never ask for credentials in chat. Always let the user edit secrets directly and do not attempt to read them.

## toolkits — match intent → install → open the entry skill (no discovery round-trip needed)
Workflow toolkits are installed on demand. This index is authoritative for shipped toolkits: match the user's intent, run the install command (with `--non-interactive`), confirm with `dlthub ai status`, then hand over to the entry skill. No discovery call needed for these.
```
intent                                              → toolkit                | install                                           | entry skill
REST / HTTP APIs                                    → rest-api-pipeline      | dlthub ai toolkit rest-api-pipeline install       | find-source
SQL databases (SQLAlchemy)                          → sql-database-pipeline  | dlthub ai toolkit sql-database-pipeline install   | find-source
files CSV/Parquet/JSONL (disk/S3/GCS/Azure/SFTP)    → filesystem-pipeline    | dlthub ai toolkit filesystem-pipeline install     | create-filesystem-pipeline
profile data, charts, marimo dashboards             → data-exploration       | dlthub ai toolkit data-exploration install        | explore-data
model raw data into a CDM (Kimball)                 → transformations        | dlthub ai toolkit transformations install         | annotate-sources
column checks + load metrics                        → data-quality           | dlthub ai toolkit data-quality install            | setup-data-quality
deploy / schedule on the dltHub platform            → dlthub-platform        | dlthub ai toolkit dlthub-platform install         | setup-runtime
guided end-to-end demo (ingest→deploy)              → quick-start            | dlthub ai toolkit quick-start install             | quick-start
minimal REST pipeline → local DuckDB → deploy       → one-shot-pipeline      | dlthub ai toolkit one-shot-pipeline install       | one-shot-pipeline
```
* Use the `dlthub-router` skill for needs not covered above — it uses live `list_toolkits` to discover newer toolkits.
* DO NOT start data engineering work if no workflow toolkit is installed.
