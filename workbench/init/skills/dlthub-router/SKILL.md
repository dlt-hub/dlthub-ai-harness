---
name: dlthub-router
description: "The entry point for building anything with dlthub: route the user to the right workflow toolkit and install it on demand. MUST use when the user asks 'what can you do', 'what can I build', 'what are toolkits', 'how do I build a pipeline', 'I want to pull data from a REST API', 'ingest from a SQL database', 'ingest CSVs from S3 into a warehouse', 'make reports / dashboards', 'transform / model my data', 'add data quality checks', 'how do I deploy / schedule a pipeline', 'where do I start', or seems unsure what to do next after setup. Also use when the user names a data-engineering goal and no matching toolkit is installed yet, when the user wants to deploy and no platform toolkit is installed, or when a handover names a toolkit that is not installed. Do NOT use when the matching toolkit is already installed: go straight to its entry skill. Do NOT use when a specific task is in progress (debugging a pipeline, validating data, adding endpoints) and its toolkit is installed."
---

# dlthub-router

Route the user to the right toolkit, install it when it is missing, and hand over to its entry skill.

> **Router vs handovers.** This skill handles **cold start**: picking a toolkit when none of the installed ones fits, or installing the target of a handover. Inside a workflow, the **handover** sections of the toolkit's `workflow.md` route to the next skill and carry the context forward (pipeline name, dataset, destination). Do **not** use this skill mid-workflow when the relevant toolkit is already installed.

## Toolkits

```
intent                                                                               → toolkit               | entry skill
ingest from REST / HTTP APIs — production-grade pipeline                             → rest-api-pipeline     | find-source
ingest from SQL databases (Postgres, MySQL, Snowflake…)                              → sql-database-pipeline | find-sql-database-source
load files (CSV/Parquet/JSONL) from disk/S3/GCS/Azure/SFTP                           → filesystem-pipeline   | create-filesystem-pipeline
explore & profile loaded data, build charts & dashboards                             → data-exploration      | explore-data
transform & model loaded data (dimensional / Kimball)                                → transformations       | annotate-sources
add data quality checks (column expectations, validation rules)                      → data-quality          | setup-data-quality
optimize / speed up a slow or memory-heavy pipeline — parallelism, workers, batching → performance           | optimize-performance
guided end-to-end tour, ingest to dashboard (uses the real toolkits)                 → quick-start           | quick-start
deploy, schedule or run jobs on a platform; a deployed job failed                    → a platform toolkit    | its workflow entry
```

## Route

1. **Match** the user's intent, or the toolkit a handover names, to a row.
2. **A platform toolkit** deploys and runs the workspace on one platform: deployments, schedules, job runs and their logs. When one is installed, follow its workflow entry. Otherwise run `uv run dlthub --non-interactive ai toolkit list` and pick from the toolkits whose description starts with `Platform toolkit`, by the platform the user names. Ask the user when none is named and more than one fits. A toolkit whose description says `Requires <platform> Platform` works only with that platform, for example a guided first deploy: offer it when the user wants to try that platform.
3. **Install** the toolkit if its entry skill is not available: `uv run dlthub --non-interactive ai toolkit install <toolkit>`.
4. **Hand over** in this session: open the entry skill and follow the toolkit's workflow rule, with the context you already have. Do not ask the user to restart. A skill installed in this session may not be registered until the next one; then read its `SKILL.md` and the workflow rule from the paths in the install output.
5. **Only if the install output shows an error**, run `uv run dlthub ai status` and fix what it reports before handing over.

**"my job failed"**: a local pipeline or transformation run goes to that toolkit's own debug skill (`debug-pipeline`, `debug-sql-database-pipeline` or `debug-transformation`). A dlt **load job** in a failed load package belongs there too, on the user's machine. A deployed job goes to the platform toolkit.

If no row matches, tell the user which toolkits exist and ask what they want; do not start an unrelated workflow.
