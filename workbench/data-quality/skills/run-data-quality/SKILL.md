---
name: run-data-quality
argument-hint: "[pipeline-name]"
description: "Use when the user wants to run data quality checks that are already defined on a loaded pipeline: 'run my checks', 'check the data now'. Runs them against the destination without loading the source again. Not for defining checks (define-data-quality-checks) or reading results (review-data-quality)."
---
# Run data quality checks

Execute checks against the already-loaded destination data using `dq.run_checks()`. No source re-extraction happens — this reads only from the destination.

Reference: [dlthub data quality docs](https://dlthub.com/docs/hub/data-quality.md)

## Session context — carry-over from define-data-quality-checks

Expected from prior steps:
- Confirmed pipeline name
- The full checks dict (table → list of checks) confirmed by the user

## Steps

### 1. Detect profile

Before writing any script, determine which execution profile applies:

| Profile | Signal | Action |
|---|---|---|
| **A — pipeline author** | Checks were applied via `@dq.with_checks` / `dq.with_checks(resource, ...)` decorators in the pipeline file | Run the existing pipeline script — checks fire automatically during load |
| **B — postmortem analyst** | No decorator changes; user wants to check existing destination data without re-running the pipeline | Write and run a data quality script (`<script_path>`, for example `dq_run.py`) that takes the pipeline and calls `dq.run_checks` |

If the profile is ambiguous, ask: "Were the checks added to the pipeline code (decorators), or do you want to run them against data already in the destination without re-extracting?"

---

**Profile A — run the pipeline**

1. `@dq.with_checks` and `@dq.with_metrics` only store hints in the schema metadata — they do not execute on their own. Results are written to `_dlt_checks` by `dq.data_quality_checks(pipeline.dataset())`, which `define-data-quality-checks` already added to the pipeline file. Instruct the user to run their pipeline script. Show the exact command (infer from session context or ask):

   ```
   uv run python <pipeline_script>.py
   ```

   This runs the data load AND the `dq.data_quality_checks(...)` call in sequence. Both must complete for results to appear.

2. Wait for the user to confirm the run completed before proceeding to step 2.

---

**Profile B — write and run the data quality script**

1. **Confirm the script path.** Before writing anything, ask:

   ```
   Where should I write the data quality run script? (for example dq_run.py, next to your pipeline)
   ```

   Use the user's answer as `<script_path>` for all subsequent steps. If the workspace already keeps scripts in a folder, propose that folder. Do not pick a path without the user's answer.

2. **Write `<script_path>`.** Take the pipeline without running it, and call `dq.run_checks` (reads only from the destination). Import the pipeline when a module creates it at the module level. Otherwise create the same pipeline: the same name, destination and dataset name (`uv run dlthub local pipeline info <pipeline-name>` shows them). Either way the script also runs as a job on a deployment, where the pipeline state comes from the destination.

   ```python
   import dlt
   from dlt.hub import data_quality as dq  # https://dlthub.com/docs/hub/data-quality.md

   # or: from <module> import pipeline
   pipeline = dlt.pipeline("<pipeline-name>", destination="<destination>", dataset_name="<dataset_name>")
   load_info = dq.run_checks(pipeline, checks={
       "<table>": [
           dq.checks.is_unique("<col>"),
           dq.checks.is_not_null("<col>"),
           # ... all confirmed checks
       ],
   })
   print(load_info)
   load_info.raise_on_failed_jobs()
   ```

   **Never glob for pipeline files or run the user's original pipeline script.** That re-extracts from the source. `run_checks` is self-contained against the destination. Importing a module that only creates the pipeline runs nothing.

   **Tables not found:** the name, destination or dataset name differs from the pipeline that loaded the data, or the pipeline never loaded with the active profile. Compare with `uv run dlthub local pipeline info <pipeline-name>` and `uv run dlthub profile info`, and tell the user which one differs.

   **Note on `case()` and NULLs:** `dq.checks.case("col >= 0")` treats NULL as a failing row. If the column is nullable and NULLs are expected, either exclude them in the expression (`case("col IS NULL OR col >= 0")`) or use `is_not_null` as a separate check.

   Show the written file to the user and ask for explicit confirmation before running:

   ```
   I've written <script_path> with your checks. Ready to run it?
   ```

   Do not proceed until the user confirms.

3. **Run the script.** Once the user confirms, ask how they run Python scripts if it is not already clear from session context:

   ```
   python <script_path>
   # or, if using uv:
   uv run python <script_path>
   ```

   Capture stdout and stderr in full.

4. **Handle script failure.** If `run_checks` raises an exception or `raise_on_failed_jobs()` fails:

   | Error pattern | Likely cause | Action |
   |---|---|---|
   | `DestinationTerminalException` containing "database is locked" (DuckDB) | Another process holds the DuckDB file — dlthub dashboard open, a pipeline EL/T run in progress, or a second terminal session | Close the dashboard and any other pipeline processes, then re-run |
   | `DestinationTerminalException` (other) | Destination config / credential issue | Ask user to check secrets and destination setup; a destination with a destination toolkit → the known failures of its connection skill |
   | `LineageFailedException` | SQL generation bug in a check (e.g. `is_primary_key`) | Remove the failing check, use `is_unique` instead, rewrite `<script_path>` |
   | Any other exception | Infrastructure or code error | Surface the full traceback and stop |

   Do not proceed to step 2 (Surface check failures) if the script failed.

---

### 2. Surface check failures

Read check results using the library:

```python
import dlt
from dlt.hub import data_quality as dq  # https://dlthub.com/docs/hub/data-quality.md

pipeline = dlt.pipeline("<pipeline-name>", destination="<destination>", dataset_name="<dataset_name>")
results = dq.read_check(pipeline.dataset())
rows = results.fetchall()
cols = results.columns
```

Consume results with `.fetchall()` and `.columns` — do not iterate the `Relation` directly. Fields: `table_name`, `check_qualified_name`, `row_count`, `success_count`, `success_rate` (0.0–1.0; 1.0 = all rows passed). A check passes if `success_count = row_count`.

**If no failures:**

```
All checks passed.
  Checks run: <n> — all passed

Moving to review-data-quality for a full metrics review →
```

**If failures are found**, present them before proceeding:

```
<n> check failure(s) detected:

  Table: orders
    ✗ customer_id__is_not_null   — 42/500 rows failed  (success_rate: 0.92)
    ✗ amount__case__GT           — 3/500 rows failed   (success_rate: 0.99)

  Table: customers
    ✓ id__is_unique              — passed
    ✗ email__is_unique           — 7 duplicates found  (success_rate: 0.99)
```

Then ask:

```
How would you like to handle this?

  [1] Adjust the check — e.g., the check is too strict for this data
  [2] Investigate the source data — the data has a real quality problem

Or say "continue" to proceed to the full review regardless.
```

**If option 1:** hand back to `define-data-quality-checks` with the specific failing checks pre-targeted. Do not re-run the full define flow.

**If option 2 or "continue":** proceed to `review-data-quality` with the failure context already in session.

## Output and handover

Pass to `review-data-quality`:
- Confirmed pipeline name
- Run outcome (success / failures detected)
- Failing checks and tables (if any)
- Profile (A or B) — so `review-data-quality` can tailor its deployment recommendation

**Profile B only — after review is complete**, surface the deployment question:

```
<script_path> ran your checks once against the current data. What would you like to do with it?

  [1] Deploy it — run these checks on a schedule
  [2] Keep it local — re-run manually whenever needed (python <script_path>)
  [3] Discard it — the results are in the destination, the script is no longer needed

```

If the user chooses [1], follow the workflow entry of the installed platform toolkit (when none is installed, `dlthub-router` installs one), passing:
- The script path (`<script_path>`) as the deployment target
- The confirmed pipeline name and destination
