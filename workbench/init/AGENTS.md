## ALWAYS ACTIVATE those skills
they are essential for ANY work in this project

## Security
CRITICAL: never ask for credentials in chat. Always let the user edit secrets directly and do not attempt to read them.

## toolkits — match intent → install → open the entry skill (no discovery round-trip needed)
Workflow toolkits are installed on demand. This index is authoritative for shipped toolkits: match the user's intent, run the install command (with `--non-interactive`), confirm with `dlthub ai status`, then hand over to the entry skill. No discovery call needed for these.
```
intent                                              → toolkit                | install                                           | entry skill
REST / HTTP APIs                                    → rest-api-pipeline      | dlthub ai toolkit install rest-api-pipeline       | find-source
SQL databases (SQLAlchemy)                          → sql-database-pipeline  | dlthub ai toolkit install sql-database-pipeline   | find-source
files CSV/Parquet/JSONL (disk/S3/GCS/Azure/SFTP)    → filesystem-pipeline    | dlthub ai toolkit install filesystem-pipeline     | create-filesystem-pipeline
profile data, charts, marimo dashboards             → data-exploration       | dlthub ai toolkit install data-exploration        | explore-data
model raw data into a CDM (Kimball)                 → transformations        | dlthub ai toolkit install transformations         | annotate-sources
column checks + load metrics                        → data-quality           | dlthub ai toolkit install data-quality            | setup-data-quality
deploy / schedule on the dltHub platform            → dlthub-platform        | dlthub ai toolkit install dlthub-platform         | setup-runtime
guided end-to-end demo (ingest→deploy)              → quick-start            | dlthub ai toolkit install quick-start             | quick-start
minimal REST pipeline → local DuckDB → deploy       → one-shot-pipeline      | dlthub ai toolkit install one-shot-pipeline       | one-shot-pipeline
```
* Use the `dlthub-router` skill for needs not covered above — it uses live `list_toolkits` to discover newer toolkits.
* DO NOT start data engineering work if no workflow toolkit is installed.
