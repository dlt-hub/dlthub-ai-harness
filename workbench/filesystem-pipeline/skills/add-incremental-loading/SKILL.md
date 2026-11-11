---
name: add-incremental-loading
description: Add incremental loading to a dlt filesystem pipeline — filter files by modification date, optionally filter records by a timestamp column, and switch to merge with a primary key to deduplicate updated records, so each run only reads new or modified files. Use after create-filesystem-pipeline produces a working replace-mode pipeline, or when the user wants to set up merge/dedup or move a pipeline from replace to incremental. For speed/memory tuning (faster reader, chunked streaming, parallel reads, glob narrowing) use optimize-filesystem-performance instead.
---

# Add incremental loading to a filesystem pipeline

## Prerequisites
Skip this if you already checked it in this session.
1. Run `uv --version`. If it fails, `uv` is missing.
   - Ask the user to allow the `uv` install. Do not install it without approval.
   - On macOS and Linux, run `curl -LsSf https://astral.sh/uv/install.sh | sh`.
   - On Windows, run `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`.
   - Docs: https://docs.astral.sh/uv/getting-started/installation/
   - If `uv` is still not found, tell the user to open a new shell, because the install changes `PATH`.
2. Run `uv run dlthub ai status`. If it fails, `dlt[hub]` or the dlthub workspace is missing.
3. Check that these skills are available. If a skill is not available, its toolkit is missing.
   - `setup-secrets` from the `init` toolkit
   - Do not check the `dlt-workspace-mcp` tools. They do not start without `dlt[hub]`.
4. Find how this skill was installed. Look at the folder of this skill.
   - The folder is in the project (`.claude/`, `.cursor/` or `.agents/`): the `dlthub` CLI installed it.
   - The folder is not in the project: a plugin marketplace installed it.
5. If anything is missing, tell the user that this skill does not work without it.
   - Ask the user to allow each install.
   - Install from the same channel as this skill. Then each toolkit has only one copy.
6. The `dlthub` CLI installed this skill:
   - If `dlt[hub]` or `init` is missing, run `uvx dlthub-init@latest`. It installs both.
   - For each other missing toolkit, run `uv run dlthub --non-interactive ai toolkit install <toolkit>`.
7. A plugin marketplace installed this skill:
   - If `dlt[hub]` or the workspace is missing, run `uvx --from "dlt[hub]" dlthub init`.
   - Do not run `uvx dlthub-init@latest`. It adds a second copy of `init`.
   - Ask the user to install each missing toolkit from the same marketplace.
   - In Claude Code, the command is `/plugin install <toolkit>@dlthub-ai-harness`.
8. After the install, tell the user to restart the session. Skills, rules and MCP load only at session start.
9. If the user refuses an install, stop. Do not run other steps of this skill.

Extends a working filesystem pipeline to load only new or modified files (and optionally only new records within those files) on each run.

**Reference**: https://dlthub.com/docs/tutorial/filesystem#7-loading-data-incrementally

## Preconditions

Requires a working filesystem pipeline. If the pipeline file is not already known from session context, ask the user which file to modify before proceeding.

## Steps

### 1. Read the current pipeline

Read the pipeline file. Note:
- The current write disposition — it may be `replace`, `append`, or already `merge`
- Whether `dev_mode=True` is set (it must be removed before incremental runs)
- Whether it is single-table or multi-table layout

### 2. Ask about incremental strategy

Ask the user in one round (parallel questions):

- **Record-level filtering** — should individual records also be filtered by a timestamp column (e.g. only rows where `updated_at` is newer than the last run)? If yes, which column?
- **Primary key** — which column(s) uniquely identify a record? Required for `merge` deduplication. If the data has no natural key, `append` write disposition is the fallback (no deduplication).

File-level filtering (by file modification date) is always applied — do not ask about it.

### 3. Apply file-level incremental

Add `incremental=dlt.sources.incremental("modification_date")` to the `filesystem()` call:

```python
# Single-table
reader = (
    filesystem(file_glob="<pattern>", incremental=dlt.sources.incremental("modification_date"))
    | read_csv()
).with_name("<table_name>")
```

For multi-table layout, add the same `incremental=` argument to each `filesystem(...)` call.

### 4. Apply record-level incremental (if chosen in step 2)

Call `apply_hints` on the reader **after** `.with_name(...)`:

```python
reader = (
    filesystem(file_glob="<pattern>", incremental=dlt.sources.incremental("modification_date"))
    | read_csv()
).with_name("<table_name>")

reader.apply_hints(
    primary_key="<pk_column>",
    incremental=dlt.sources.incremental("<timestamp_column>"),
)
```

If no primary key exists, skip `apply_hints` and use `append` write disposition (step 5) — dlt will accumulate rows without deduplication.

### 5. Switch write disposition and remove dev_mode

Change `write_disposition="replace"` → `"merge"` (or `"append"` if no primary key). Remove `dev_mode=True` from `dlt.pipeline(...)` — dev mode generates a fresh dataset name on every run, which breaks state tracking across runs.

```python
pipeline = dlt.pipeline(
    pipeline_name="<pipeline_name>",
    destination="<destination>",
    dataset_name="<dataset>",
    # dev_mode removed
)

load_info = pipeline.run(reader, write_disposition="merge")
```

### 6. Run and verify

Run the pipeline twice to confirm incremental behaviour:

1. **First run** — loads all files matching the glob. Check row count with `get_row_counts` MCP tool or `dlthub local pipeline show <name>`.
2. **Second run (no new files)** — should load 0 rows. Check pipeline state with `get_local_pipeline_state` MCP tool to confirm the `modification_date` cursor advanced.

If the user can add a test file to the bucket, run a third time to confirm only the new file is picked up.
