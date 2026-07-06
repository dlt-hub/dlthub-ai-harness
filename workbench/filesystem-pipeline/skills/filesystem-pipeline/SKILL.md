---
name: filesystem-pipeline
description: Build a dlt pipeline that loads files — CSV, Parquet, or JSONL — from a
  local disk, S3, GCS, Azure, or SFTP. Use when the user wants to ingest files from a
  bucket or folder into a destination. DO NOT USE for REST/HTTP APIs (use
  rest-api-pipeline) or live SQL databases (use sql-database-pipeline).
---

Your identity and guardrails (SOUL) are already loaded via the `init` base toolkit — operate from them, especially on secrets, sampling, and running from the project root.

## Before you start

Requires a dlthub workspace. Verify with `uv run dlthub ai status`. If the
workspace or dlt isn't set up, help the user initialize one before continuing.

For dlt itself: read https://dlthub.com/docs/llms.txt and follow it to the
filesystem source — https://dlthub.com/docs/dlt-ecosystem/verified-sources/filesystem

## Workflow

### Step 1 — Scaffold and configure access
Scaffold the `filesystem` source. Set the bucket URL / path, the file glob, and the reader (CSV, Parquet, JSONL). Configure bucket credentials through the workspace secrets tools.
→ Docs: https://dlthub.com/docs/dlt-ecosystem/verified-sources/filesystem
✓ Done when: a pipeline run can list the target files without an access error.

### Step 2 — Run on a sample
Run under `dev_mode=True` against a small glob or a single file to validate the parsed schema before a full load.
→ Docs: https://dlthub.com/docs/dlt-ecosystem/file-formats/ and https://dlthub.com/docs/general-usage/pipeline#do-experiments-with-dev-mode
✓ Done when: the pipeline completes without errors and at least one table loads with the expected schema.

### Step 3 — Inspect and confirm
Show the user the loaded tables, row counts, and schema through the dlt dataset API. Get confirmation the parse looks right before proceeding.
→ Docs: https://dlthub.com/docs/hub/data-discovery/datasets
✓ Done when: the user confirms the data looks correct.

### Step 4 — Run full load
Widen the glob to the full set, switch off `dev_mode`, and run. Add incremental loading — filter files by modification date and switch to merge write disposition where it fits. If earlier runs left the dev namespace polluted (pending load packages, schema conflicts), run into a fresh dataset instead of migrating broken state.
→ Docs: https://dlthub.com/docs/tutorial/filesystem#7-loading-data-incrementally
✓ Done when: a full run completes and row counts, checked through the dataset API, match expectations.

## What's next

- Data loaded successfully → the pipeline is ready for scheduling or transformation.
- User wants to explore the data → point them to the dlt dataset API (https://dlthub.com/docs/hub/data-discovery/datasets).
- User wants to schedule or deploy → outside this toolkit's scope (requires dltHub Platform).
