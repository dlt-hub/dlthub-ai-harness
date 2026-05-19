---
name: run-data-quality
argument-hint: "[pipeline-name]"
description: Use when the user asks to "run data quality checks", "execute checks", "run my data quality checks", "check the data now", "run validations", or wants to execute already-defined checks against a loaded pipeline. Do NOT use to define new checks (use define-data-quality-checks) or to review existing results (use review-data-quality).
---
# Run data quality checks

Execute checks against the already-loaded destination data using `dq.run_checks()`. No source re-extraction happens — this reads only from the destination.

Reference: [dlt data quality docs](https://dlthub.com/docs/hub/features/quality/data-quality)

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
| **B — postmortem analyst** | No decorator changes; user wants to check existing destination data without re-running the pipeline | Write and run `tools/dq_run.py` using `dlt.attach` + `dq.run_checks` |

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
   Where should I write the data quality run script? (default: tools/dq_run.py)
   ```

   Use the user's answer as `<script_path>` for all subsequent steps. If they say "default" or give no answer, use `tools/dq_run.py`.

2. **Write `<script_path>`.** Use `dlt.attach` (connects to the existing pipeline, no extraction) and `dq.run_checks` (reads only from the destination).

   ```python
   import dlt
   from dlt.hub import data_quality as dq  # https://dlthub.com/docs/hub/features/quality/data-quality

   pipeline = dlt.attach(pipeline_name="<pipeline-name>")
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

   **Never glob for pipeline files or run the user's original pipeline script.** That re-extracts from the source. `run_checks` is self-contained against the destination.

   **Workspace context gap:** `dlt.attach` looks for pipeline state in `.dlt/.var/dev/pipelines` (the workspace-scoped location) but if the pipeline was run before a `.workspace` file was added to the project, the state is at `~/.dlt/pipelines` instead. If `dlt.attach` raises `CannotRestorePipelineException`, tell the user:

   ```
   The pipeline state isn't in the workspace-scoped location yet. This happens when
   the pipeline was first run before the .workspace file was added.

   Fix: re-run your pipeline once from this directory — that seeds the state in
   .dlt/.var/dev/pipelines so dlt.attach can find it. After that, the data quality
   script will work without modification.
   ```

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
   | `DestinationTerminalException` containing "database is locked" (DuckDB) | Another process holds the DuckDB file — dlt dashboard open, a pipeline EL/T run in progress, or a second terminal session | Close the dashboard and any other pipeline processes, then re-run |
   | `DestinationTerminalException` (other) | Destination config / credential issue | Ask user to check secrets and destination setup |
   | `LineageFailedException` | SQL generation bug in a check (e.g. `is_primary_key`) | Remove the failing check, use `is_unique` instead, rewrite `<script_path>` |
   | `DltLicenseScopeInvalidException` | Missing `dlthub.data_quality` license scope | Run `dlt license issue dlthub.data_quality` |
   | Any other exception | Infrastructure or code error | Surface the full traceback and stop |

   Do not proceed to step 2 (Surface check failures) if the script failed.

---

### 2. Surface check failures

Read check results using the library:

```python
import dlt
from dlt.hub import data_quality as dq  # https://dlthub.com/docs/hub/features/quality/data-quality

pipeline = dlt.attach(pipeline_name="<pipeline-name>")
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

  [1] Deploy it — run these checks on a schedule on the dltHub platform
  [2] Keep it local — re-run manually whenever needed (python <script_path>)
  [3] Discard it — the results are in the destination, the script is no longer needed

```

If the user chooses [1], hand over to **dlthub-platform** (start at `setup-runtime`), passing:
- The script path (`<script_path>`) as the deployment target
- The confirmed pipeline name and destination
