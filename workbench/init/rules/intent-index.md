Read SOUL.md — it defines who you are and how you operate in this workspace.

# toolkits
* toolkits are data engineering workflows automated via skills, commands and rules.
* each toolkit has a parent skill that you must follow. you **must** start with the parent skill if available
* workflows end with handover to other workflows, also the `dlthub-router` skill may be helpful
* **NEVER assume a handover target toolkit is installed** — before following any handover, always run `uv run dlthub --non-interactive ai toolkit install <toolkit-name>` first, then invoke the entry skill. Do NOT run web research, manual code edits but use the entry skill.
* **DO NOT** start data engineering work if no workflow toolkit is installed - see `dlthub ai status` output!

## toolkits — match intent → install → open the entry skill (no discovery round-trip needed)
This index is authoritative for shipped toolkits. Match the user's intent, run the install command, then hand over to the entry skill. No MCP call needed for these.
<!-- This shipped index can drift from the live catalog on a user's machine until runtime refresh lands; tracked in dlt-hub/dlthub-ai-workbench-internal#71. The build-time drift guard (validate_index_drift) only keeps this in sync with marketplace.json. -->

```
intent                                                  → toolkit                | install                                                            | entry skill
ingest from REST / HTTP APIs — production-grade pipeline → rest-api-pipeline     | dlthub --non-interactive ai toolkit install rest-api-pipeline      | rest-api-pipeline
ingest from SQL databases (Postgres, MySQL, Snowflake…) → sql-database-pipeline  | dlthub --non-interactive ai toolkit install sql-database-pipeline  | sql-database-pipeline
load files (CSV/Parquet/JSONL) from disk/S3/GCS/Azure/SFTP → filesystem-pipeline | dlthub --non-interactive ai toolkit install filesystem-pipeline    | filesystem-pipeline
explore & profile loaded data, build charts & dashboards → data-exploration      | dlthub --non-interactive ai toolkit install data-exploration       | data-exploration
transform & model loaded data (dimensional / Kimball)   → transformations        | dlthub --non-interactive ai toolkit install transformations        | transformations
add data quality checks (column expectations, validation rules) → data-quality   | dlthub --non-interactive ai toolkit install data-quality           | data-quality
deploy / schedule pipelines on the dltHub platform      → dlthub-platform        | dlthub --non-interactive ai toolkit install dlthub-platform        | dlthub-platform
guided end-to-end tour, ingest to dashboard (uses the real toolkits) → quick-start | dlthub --non-interactive ai toolkit install quick-start          | quick-start
test/try dlthub end-to-end — minimal pipeline + educational test deploy, NOT production → one-shot       | dlthub --non-interactive ai toolkit install one-shot               | one-shot
```
* `one-shot` vs `rest-api-pipeline`: one-shot is for **testing / trying dlthub / onboarding / a quick demo** — a minimal single-endpoint, row-limited pipeline on local DuckDB plus an educational test deploy. Educational examples only, NOT production-grade. For a **real or production** REST pipeline (auth, incremental, multiple endpoints, production deploy), use `rest-api-pipeline`. `quick-start` is the guided tour that walks the real toolkits end-to-end.
* After installing, run `uv run dlthub ai status` to confirm, then continue **in the same session** — load the new toolkit's parent skill via `toolkit_info` (or read the installed files) and proceed. No restart needed (toolkits reuse the already-running `dlt-workspace-mcp`); don't lose the user's context.
* The `dlthub-router` skill wraps this flow and is the fallback for needs not covered above (it uses live `list_toolkits` to discover newer toolkits).
* DO NOT start data engineering work if no workflow toolkit is installed.
