## ALWAYS ACTIVATE those skills
they are essential for ANY work in this project

## Security
CRITICAL: never ask for credentials in chat. Always let the user edit secrets directly and do not attempt to read them.

## toolkits — match intent → install → open the entry skill (no discovery round-trip needed)
Workflow toolkits are installed on demand. This index is authoritative for shipped toolkits: match the user's intent, run the install command, confirm with `dlthub ai status`, then hand over to the entry skill. No discovery call needed for these.
```
intent                                                  → toolkit                | install                                                            | entry skill
ingest from REST / HTTP APIs                            → rest-api-pipeline      | dlthub --non-interactive ai toolkit install rest-api-pipeline      | find-source
ingest from SQL databases (Postgres, MySQL, Snowflake…) → sql-database-pipeline  | dlthub --non-interactive ai toolkit install sql-database-pipeline  | find-source
load files (CSV/Parquet/JSONL) from disk/S3/GCS/Azure/SFTP → filesystem-pipeline | dlthub --non-interactive ai toolkit install filesystem-pipeline    | create-filesystem-pipeline
explore & profile loaded data, build charts & dashboards → data-exploration      | dlthub --non-interactive ai toolkit install data-exploration       | explore-data
transform & model loaded data (dimensional / Kimball)   → transformations        | dlthub --non-interactive ai toolkit install transformations        | annotate-sources
add data quality checks (column expectations, validation rules) → data-quality   | dlthub --non-interactive ai toolkit install data-quality           | setup-data-quality
deploy / schedule pipelines on the dltHub platform      → dlthub-platform        | dlthub --non-interactive ai toolkit install dlthub-platform        | setup-runtime
guided end-to-end demo (ingest → deploy)                → quick-start            | dlthub --non-interactive ai toolkit install quick-start            | quick-start
minimal REST pipeline → local DuckDB → fast deploy      → one-shot-pipeline      | dlthub --non-interactive ai toolkit install one-shot-pipeline      | one-shot-pipeline
```
* Use the `dlthub-router` skill for needs not covered above — it uses live `list_toolkits` to discover newer toolkits.
* DO NOT start data engineering work if no workflow toolkit is installed.
