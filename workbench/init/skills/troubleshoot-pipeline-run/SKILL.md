---
name: troubleshoot-pipeline-run
description: General pipeline troubleshooting, when no troubleshooting guide specific to the source or runtime context is present.
argument-hint: "[pipeline-name] [issue]"
---

# Troubleshoot a pipeline run

**Essential Reading**
- Failed loads, pending and partially loaded packages: https://dlthub.com/docs/running-in-production/running.md
- Config and secret resolution: https://dlthub.com/docs/general-usage/credentials/setup.md
- Profiles (which config, secrets and state a run uses): https://dlthub.com/docs/hub/pipeline-operations/profiles.md

Troubleshooting that holds for any pipeline in a dltHub workspace, whatever the source. A guide made for the source or the runtime goes deeper, so use it when one is installed:

- A verified source → its maintenance notes in `<source>/README.md` (section 6)
- REST API source → `debug-pipeline` (**rest-api-pipeline**)
- SQL database source → `debug-sql-database-pipeline` (**sql-database-pipeline**)
- Transformations → `debug-transformation` (**transformations**)
- Slow, or out of memory → `optimize-performance` (**performance**)

Parse `$ARGUMENTS`:
- `pipeline-name` (optional): the dlt pipeline name. If omitted, infer it from the session or from `dlt.pipeline(pipeline_name=...)` in the script. If ambiguous, ask the user and stop.
- `issue` (optional, after `--`): what went wrong

## 1. Before you change anything

- **The project must be a dltHub workspace**: `.dlt/.workspace` exists in the project root. If it does not, stop: this skill does not troubleshoot plain dlt (OSS) projects. Tell the user and offer the in-place workspace setup (`uvx dlthub-init@latest`).
- **Run from the project root.** dlt looks for `.dlt/.workspace` in the current working directory only, not in parent folders: `uv run python pipelines/my_pipeline.py`, not `cd pipelines && python my_pipeline.py`. Run from another folder, the workspace is not found: `dlt.pipeline()` runs without the profile, config, secrets and state of the workspace, and the `dlthub` CLI fails with `invalid choice: 'local'`.
- **Check the workspace**: `uv run dlthub ai status`. If the `dlt-workspace-mcp` tools fail, this tells you why.
- **Check the profile**: `uv run dlthub profile info`. The profile decides which config, secrets and state the run uses (see **Wrong destination, credentials or state** in section 7).
- **Is the source a verified source?** It has its own folder created by `dlthub pipeline init` and an entry in `.dlt/.sources`. Read its maintenance notes first (section 6).
- **Note the current values** in `.dlt/config.toml` and the pipeline script. You change the user's files while debugging, and at the end you restore only what YOU changed.
- **No destructive operations without user consent, no destructive operations on remote (non local) profiles** - Always confirm with the user or ask user to do for example: pipeline refresh or database table/column drop/alter.

## 2. Increase verbosity

1. Log level in `.dlt/config.toml` (the default is `WARNING`):
   ```toml
   [runtime]
   log_level="INFO"
   ```
2. Progress logging on the `dlt.pipeline()` call. `pipeline.run()` has no `progress` argument. With `psutil` installed it also logs CPU and memory:
   ```python
   pipeline = dlt.pipeline(..., progress="log")
   ```
3. For a source that makes HTTP requests through dlt's `requests` helper or `RESTClient`, show the error response body (hidden by default):
   ```toml
   [runtime]
   http_show_error_body = true
   ```

## 3. Read the exception: which step failed?

A run goes through three steps, and the failing step tells you where to look:

| Step | What it does | Where the error usually comes from |
|---|---|---|
| extract | runs the source and resource code, writes items to files | **your code** or the source system: connection, auth, a bug in a resource or transform function |
| normalize | infers the schema, unnests nested data into child tables, writes load files | data that does not fit the schema, or a schema contract |
| load | creates tables and loads the files into the destination | destination credentials, permissions, type conversion on the destination, bad data in a load file |

Extract and normalize do not change the destination. A failure there is fixed in code or config, and the next run starts clean. A load failure may leave a partially loaded package (section 5).

**Terminal or transient?** A terminal error does not go away on retry: missing config, most HTTP `4xx`, a missing table, bad data in a job file. A transient one may: a timeout or a dropped connection. Fix the cause of a terminal error before you retry.

Common exceptions:

| Exception | Meaning | Fix |
|---|---|---|
| `ConfigFieldMissingException` | a config value or secret was not found. The message lists every key that was looked up | see **Config or secret not found** in section 7 |
| `PipelineStepFailed` | a step failed. `.step` names it, and the cause is the inner exception at the bottom of the traceback | fix the cause. For a load failure, go to section 5 |
| `LoadClientJobTerminalRetry` | a load job failed with a terminal error. The job is queued for retry and its package stays pending | read the job error (section 4), fix the cause, then recover (section 5) |
| `LoadClientJobRetry` | a job failed transiently more than `[load] raise_on_max_retries` times (default `5`). The package stays pending | check that the destination is reachable, then run again: the next run resumes the package |
| a destination error when dlt adds a column: NOT NULL, NULL values, `Adding columns with constraints not yet supported` (DuckDB) | dlt adds a NOT NULL column to a table that already has data | see **A load fails adding a NOT NULL column** in section 7 |
| `DataValidationError` | a schema contract rejected data. Its attributes name the table, the column and the contract mode | fix the data, or change the contract: https://dlthub.com/docs/general-usage/schema-contracts.md |
| `ModuleNotFoundError` / `MissingDependencyException` | a source, destination or reader needs an extra. Destination packages are imported when `run()` connects to the destination, before extract | install what the message names, e.g. `uv add "dlt[hub,<extra>]"` or the driver package |
| import error that reports a wrong `dlthub` plugin version | `dlthub` was installed on its own and does not match the dlt version | reinstall the extra pinned to your dlt version: `uv add "dlt[hub]==<dlt version>"` |
| `CannotRestorePipelineException` from `dlt.attach` | the active profile has no state for this pipeline: another profile is active, the script ran from another folder, or the pipeline never ran | check the profile (**Wrong destination, credentials or state** in section 7) and run from the project root |
| `DestinationTerminalException` containing `database is locked` (DuckDB) | another process holds the DuckDB file: the dashboard, another run, a notebook | close the other process, then run again |

## 4. Inspect the last run

Use the `dlt-workspace-mcp` tools first when they are available. These are the CLI equivalents. `-v` / `-vv` belong to `dlthub` itself, so put them right after it:

```
uv run dlthub local pipeline list                                         # pipelines of the active profile
uv run dlthub -vv local pipeline trace <pipeline_name>                    # config/secret resolution, step timing and counts, the failure
uv run dlthub local pipeline trace <pipeline_name> metrics                # files, rows and sizes per step (--steps extract normalize load)
uv run dlthub -v local pipeline info <pipeline_name>                      # dataset, destination, schemas, resources, pending packages and their load ids, state
uv run dlthub -v local pipeline load-package <pipeline_name> <load_id>    # jobs by state, including jobs pending a retry; tables created
uv run dlthub local pipeline load-package <pipeline_name> <load_id> job <pattern>   # full error history of matching jobs, across retries
uv run dlthub local pipeline load-package <pipeline_name> <load_id> row-counts      # rows written per table for this load id
uv run dlthub local pipeline failed-jobs <pipeline_name>                  # failed jobs of completed packages only
```

Without `<load_id>`, `load-package` shows the most recent package.

**A failed load job stays pending.** Since dlt 1.30, a job that fails on load is queued for retry and its package stays pending, so `failed-jobs` does not list it. Read it with `load-package <pipeline_name> <load_id>` and its `job` action. The most likely cause of a failed job is the data in its file.

The trace shows which config keys were looked up and where each value came from. Read it when a value resolves to the wrong thing, not only when it is missing. The dashboard (`uv run dlthub local pipeline show <pipeline_name>`) shows the same under **Resolved Config Values**.

### Raw load files

A pipeline's working directory is `.dlt/state/<profile>/pipelines/<pipeline_name>/`. Completed packages are under `load/loaded/<load_id>/`, with job files in `completed_jobs/` and `failed_jobs/` (`[load] delete_completed_jobs=true` removes them). Each retry writes its error to the package's `.exceptions` folder, and the first line says `retry: terminal` or `retry: transient`. Gzipped files read with `zcat <file>.gz`. Use them to check what dlt actually sent to the destination.

## 5. Recover a failed load

Escalate in this order and do not skip a step:

1. **Read the failures** (section 4) and fix the cause in code, config or credentials.
2. **Run again.** `run()` first normalizes and loads the pending packages, and then exits without extracting new data. Jobs that completed are never run again, so a retry is safe even for a partially loaded package. Run once more to extract new data. To load the pending packages without running the script: `dlt.attach("<pipeline_name>").load()`.
3. **Fail the jobs that can never load**, for example a file with bad data, then run again:
   ```
   uv run dlthub local pipeline load-package <pipeline_name> <load_id> fail-job <job_id>
   ```
   A job that a crash interrupted cannot be failed this way: run again, or abort.
4. **Abort the pending packages:**
   ```
   uv run dlthub local pipeline abort-packages <pipeline_name>
   ```
   It marks the oldest pending package as aborted and moves its unfinished jobs to `failed_jobs`. It deletes the other pending packages, extracted ones included. Local state and schemas go back to where they were before the package, so incremental cursors rewind. Data the aborted package already loaded stays in the destination (see **Partially loaded package** below). `drop-pending-packages` is a deprecated alias of this command.
5. **Sync with the destination** when local state no longer matches it, for example after the pipeline ran on another machine or the working directory was lost:
   ```
   uv run dlthub local pipeline sync <pipeline_name>
   ```
   `sync` deletes the local working directory (pending packages, unsynced state, schemas) and restores it from the destination. The destination is left as it is. Do not use it to clear pending packages: abort does that.
6. **Drop resources (last resort)**, only when wrong tables or schema were already loaded:
   ```
   uv run dlthub --non-interactive -y local pipeline drop <pipeline_name> <resource>
   ```
   - `drop` deletes the destination tables and resets their state, which forces a full reload of those resources. `--state-only` resets the state and keeps the tables.
   - Resources are exact names, or a regex with the `re:` prefix. Prefer named resources. Use `--drop-all` only after the user confirms it explicitly.
   - `drop` asks `[y/N]`, and `-y` answers yes for you. Before you pass it, confirm the pipeline name, destination, dataset and the resources to drop with the user.

### Partially loaded package

`PipelineStepFailed` warns when a package was partially loaded. To check, run `load-package <pipeline_name> <load_id> row-counts`. If the destination has rows for the `load_id` but the package is not in `_dlt_loads`, the load did not finish.
- **Run again** (step 2): this is always the safest fix.
- **`merge` and `replace` tables**: do not delete rows by hand. Abort and run again.
- **`append` tables**: the rows of the failed load can be deleted by `_dlt_load_id`, nested tables first. The procedure is in running.md. Ask the user before you delete anything from the destination.

## 6. Verified sources

A verified source lives in its own `<source>/` folder, which `dlthub pipeline init` created. `<source>/version.py` holds the installed version.

**Before you change the pipeline, read the source's docs page and follow it like a skill**: setup, credentials, resources and arguments. `<source>/README.md` links it in its first lines; add `.md` to the URL for the markdown version. Without the link, see [verified-sources.md](verified-sources.md).

Then read `<source>/README.md` before the code. It answers two questions:
- **What do I do when something goes wrong?** → **Maintenance & Troubleshooting** (**Operations** in older copies): limits, quirks, failures and their workarounds. Search it for the exception, the error message, the resource, the argument and the backend (`python` / `pyarrow`).
- **Can I upgrade safely from my version?** → **Changelog**: compare it with the latest notes, `https://raw.githubusercontent.com/dlt-hub/verified-sources/master/sources/<source>/README.md`. Entries above the installed version are fixes the copy does not have. If one matches, propose an update instead of patching the code.
- **Backend changed** on a pipeline that already loaded data → **Switching between Python objects and Arrow** in section 7.

**Update** only with the user's OK:
1. Do what the **Upgrade** lines between the two versions require.
2. Run `uv run dlthub --non-interactive pipeline init <source> <destination>`.
3. If the user changed the source files, `--non-interactive` skips the update. Ask the user to run the command in their own terminal instead.

More detail (what init copies, copies without `version.py`, the dlt version check, the update choices): [verified-sources.md](verified-sources.md).

## 7. Common symptoms

### Config or secret not found, or the wrong value is used
- **Read the exception message.** It lists the keys in the order they were looked up, most specific first (with the pipeline name prefix), and for each key it checks environment variables first, then `secrets.toml`. Put the value at one of the listed keys → `setup-secrets`. Never read `secrets.toml`.
- **Secrets are not read from `config.toml`.** A secret stored there is not found.
- **Environment variables override the TOML files.** A stale `SOURCES__...` or `DESTINATION__...` variable wins over a value you edit. Check variable names only, never print their values.
- **Source sections follow the Python module** where the source is defined: `sources.<module>.<function>.<key>`, then `sources.<module>.<key>`, then `sources.<key>`. Renaming or moving the module changes the section.
- **The profile** can override the value: see **Wrong destination, credentials or state** below.
- **To see which value was used and where it came from**, read the trace (section 4).

### The run succeeds but new data is missing, or a table has 0 rows
- **Pending packages ran first.** `run()` loaded packages left by an earlier run and exited without extracting, and the log warns about it. Run again.
- **The resource yielded nothing.** Read the extract counts in the trace (section 4), or call the resource on its own and print what it yields.
- **A limit cut the data.** `.add_limit(N)` counts yields, which for most sources are pages, not rows. Use `.add_limit(N, count_rows=True)` to count rows.
- **An incremental cursor or a filter excluded everything.** See **Incremental loading** below.
- **A schema contract with `discard_row` or `discard_value`** drops data without an error.
- **You are looking at another dataset.**
  - With `dev_mode=True`, every run writes to a new dataset with a datetime suffix.
  - `dataset_name` defaults to `<pipeline_name>_dataset`, and `pipeline_name` defaults to the script's file name. Renaming the script starts a new pipeline, with new state and a new dataset.
- **Data fetched in the body of a `@dlt.source` function** runs when the source is created, outside error handling and metrics. Fetch data in resources.

### A column is missing, or a type or hint change does not apply
- **All-NULL columns.** dlt does not create a column whose values are all NULL, because it cannot infer a type. The column appears once a non-NULL value arrives, or right away with a type hint:
  ```python
  @dlt.resource(columns={"amount": {"data_type": "decimal", "nullable": True}})
  ```
- **Existing columns never change.** A type or hint you add after the first load does not apply to a table that already exists. While developing, reload the data:
  - `dev_mode=True`
  - `refresh="drop_resources"` on `dlt.pipeline()` or `run()`
  - drop the resource (section 5)
- **Removed or renamed fields.** A field removed from the source keeps its column, which stops getting data. A renamed field creates a new column.
- **Money.** Never use `float` for money or other precision-sensitive values: use `decimal`.

### A load fails adding a NOT NULL column
Most destinations cannot add a NOT NULL column to a table that already has rows, because the existing rows have no value for it. DuckDB fails with `Adding columns with constraints not yet supported`. dlt adds such columns in these cases:

| Column | Added when |
|---|---|
| `_dlt_load_id`, `_dlt_id` | a resource that loaded Arrow tables or DataFrames now yields Python objects (see the next section), or dlt loads into a table it did not create |
| `_dlt_parent_id` | dlt loads into a nested table it did not create |
| `_dlt_root_id` | a resource with nested tables switches to `merge`, or gets `root_key=True`, after its nested tables were created |
| your column with `nullable: False` | the column is new in a table that already has rows |

Fix it in one of these ways, and confirm with the user before you change destination tables:
1. **Reload the affected resources:** drop them (section 5) or run once with `refresh="drop_resources"`. This deletes their data and resets their schema, so dlt creates the columns on empty tables.
2. **Keep the data: add the columns yourself.**
   - Add each column to the existing tables as a nullable column. dlt's columns are text.
   - Fill the existing rows.
   - For a `merge` resource, also drop its tables in the staging dataset (`<dataset>_staging`), because they keep the rows of the last load.
   - Then run again. dlt finds the columns in the destination and does not add them. If a load already failed, the next run loads the pending package.
3. **`_dlt_root_id` only:** if the nested tables are at most one level deep, disable root key propagation with `root_key=False` on the source.

Refs:
- Loading into tables dlt did not create: https://dlthub.com/docs/general-usage/destination-tables.md (section "Loading data into existing tables not created by dlt")
- Switching to merge, and the SQL to add `_dlt_root_id`: https://dlthub.com/docs/general-usage/merge-loading.md (section "Add the root key to existing tables")

### Switching between Python objects and Arrow
This covers changing a live resource from yielding Python objects (dicts) to Arrow tables or DataFrames, or back. Changing a source's `backend` argument does the same, e.g. `python` ↔ `pyarrow` in verified sources, or `sqlalchemy` ↔ `pyarrow` / `pandas` / `connectorx` in `sql_database`. The two formats create different tables:

| | Python objects | Arrow tables, DataFrames |
|---|---|---|
| dlt columns | `_dlt_load_id` and `_dlt_id`, both NOT NULL | none by default |
| nested data | lists become child tables, dicts become flattened columns | per the Arrow types (in verified sources, see Maintenance & Troubleshooting) |
| column types | inferred from the values | taken from the Arrow schema |

Because dlt never alters existing columns, a switch on a pipeline that already loaded data leaves tables made for the other format:
- **Arrow → Python**: dlt adds `_dlt_load_id` and `_dlt_id` as NOT NULL columns to tables that have rows, and the load fails (see the previous section). Nested data that went into columns now goes to child tables, so the old columns stop getting data.
- **Python → Arrow**: the existing `_dlt_load_id` and `_dlt_id` columns are NOT NULL, but Arrow rows bring no values for them. Enable both before you switch:
  ```toml
  [normalize.parquet_normalizer]
  add_dlt_load_id = true
  add_dlt_id = true
  ```
  `add_dlt_load_id` costs little. `add_dlt_id` rewrites every file in the normalize step. Without `_dlt_load_id`, rows cannot be traced to a load: neither `row-counts` nor the partial-load cleanup in section 5 can find them.
- **Types can differ between the formats**, for example timestamp time zones and precision, or decimals. That creates variant columns or fails the load.

The cleanest switch reloads the resource (`refresh="drop_resources"` or drop it, section 5). Confirm with the user first, because it reloads all the data. To keep the data, add the dlt columns yourself (previous section) and compare the new columns with the old ones before you run the full load.
Ref: https://dlthub.com/docs/dlt-ecosystem/verified-sources/arrow-pandas.md (section "Add `_dlt_load_id` and `_dlt_id` to your tables")

### Variant columns, unexpected tables or column names
- **Variant columns `<column>__v_<type>`**, e.g. `id__v_text`: a value could not be coerced to the column's type, so dlt stored it in a variant column. Fix the type in the resource or with a column hint. To reject such data instead, use the contract `{"data_type": "freeze"}`.
- **Child tables `<table>__<field>`**: dlt unnests nested lists into child tables and flattens nested dicts into `<field>__<subfield>` columns. To change this:
  - set `max_table_nesting` on the resource (`0` keeps all nested data as JSON). A value set on the source is ignored when the resource is accessed as `source.resources[...]`, so set it on the resource;
  - or hint a single column as `{"data_type": "json"}`.
- **Renamed columns**: the default naming convention turns identifiers into `snake_case`.
  - `primary_key`, incremental cursors, `add_map` and `add_filter` use the **source** names.
  - The schema holds the normalized names.
  - Keys that collide after normalization are merged without a warning.
  - Ref: https://dlthub.com/docs/general-usage/naming-convention.md

### Duplicates, or rows missing after a merge
- **`merge` without `primary_key` or `merge_key`** falls back to `append`.
- **Incremental loading does not deduplicate.** Use `merge` with a `primary_key`.
- **`upsert` expects a unique `primary_key`**: with duplicate keys the result is not deterministic. `delete-insert` deduplicates by primary key but picks an arbitrary row, unless you set the `dedup_sort` column hint.
- **Switching an existing `append` table that has child tables to `merge` fails**: dlt adds a NOT NULL `_dlt_root_id` column. See **A load fails adding a NOT NULL column** above.
- **Do not run two instances of the same pipeline at the same time** on one machine. They share the working directory and the state.
- Ref: https://dlthub.com/docs/general-usage/merge-loading.md

### Incremental loading stops picking up new data
Check the stored cursor with `uv run dlthub -v local pipeline info <pipeline_name>`. Look for `last_value` in the resource state and verify it moves between runs. Also look in the logs for `Bind incremental on <resource_name>`, which confirms the incremental was bound. Then check:
- **Same pipeline between runs.** `pipeline_name`, `destination` and `dataset_name` match the earlier runs, and the profile is the same.
- **No reset settings.** `dev_mode` is off and no `refresh` is set.
- **`write_disposition="replace"` resets the resource state on every run.** The cursor then restarts from `initial_value`.
- **An `end_value` makes the run a backfill** that does not update the stored cursor.
- **The cursor does not advance until the package is fully loaded.** This is intended: a failed load does not skip data.
- Ref: https://dlthub.com/docs/general-usage/incremental/troubleshooting.md

### Wrong destination, credentials or state
The workspace reads config and state per **profile**:
- `config.toml` and `secrets.toml` apply to every profile. `.dlt/<profile>.config.toml` and `.dlt/<profile>.secrets.toml` override them for one profile.
- Each profile has its own working directory, `.dlt/state/<profile>/`, and its own local data, `.dlt/data/<profile>/`. A pipeline that ran under `dev` is not listed under `prod`.
- Local runs use `dev` unless a profile is pinned. A pin (`.dlt/profile-name`) also applies to plain `python` runs.
- Built-in profiles are `dev`, `tests`, `prod` and `access`. Pinning a misspelled name does not fail: the run just finds no config for it.

To check:
```
uv run dlthub profile info                 # active profile and whether it is pinned
uv run dlthub -v local info                # every file location the active profile reads settings from
uv run dlthub local profile use <profile>  # pin another profile
```

### Slow, looks stuck, or runs out of memory
- **A long run may just be a large dataset.** Watch the progress log: new items keep arriving on a big run, while a stuck one repeats the same work or goes quiet.
- **Cap the work while you develop**: add `.add_limit(N)` to the resource.
- **To find which resource is slow** in a multi-resource pipeline, extract one at a time:
  ```toml
  [extract]
  next_item_mode = "fifo"
  ```
- **Silence may be HTTP retries.** Sources that use dlt's `requests` helper or `RESTClient` retry `429`, `5xx` and timeouts with exponential backoff, by default 5 attempts with waits of up to 300 s, and they honor `Retry-After`.
- **Normalize hangs with `[normalize] workers` above 1** on Linux: set `[normalize] start_method="spawn"`.
- **After Ctrl-C** the load step waits for the running jobs to finish. A second Ctrl-C stops it.
- **For tuning**, or a run that is killed or fills the disk, hand off to **performance** → `optimize-performance`.

## 8. Clean up

Revert the debugging settings YOU introduced, and keep anything the user had before:
- [ ] `.dlt/config.toml`: restore `log_level`. Remove `http_show_error_body` and `[extract] next_item_mode` if you added them.
- [ ] Pipeline script: remove `progress="log"`, `.add_limit(N)` and `refresh=` if you added them.
- [ ] `dev_mode=True`: remove it before the pipeline loads real data. It writes every run to a new dataset.

## Next steps

- **Load works** → validate the data with the toolkit that built the pipeline, or hand off to **data-exploration**.
- **Credentials or config missing** → `setup-secrets`.
- **The failure is specific to the source or destination** → that toolkit's debug skill (list at the top). If it is not installed, use `dlthub-router` to install it.
