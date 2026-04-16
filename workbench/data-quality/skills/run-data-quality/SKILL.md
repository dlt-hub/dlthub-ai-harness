---
name: run-data-quality
argument-hint: "[pipeline-name]"
description: Use after define-data-quality-checks to run the pipeline with DQ enabled and surface immediate check failures.
---
# Run data quality checks

Execute the pipeline so dlt computes checks and metrics post-load, then surface any failures immediately.

Reference: [dlt data quality docs](https://dlthub.com/docs/hub/features/quality/data-quality)

## Session context — carry-over from define-data-quality-checks

Expected from prior steps:
- Confirmed pipeline name
- Pipeline script path (the file where checks and metrics were applied)
- Resource type (decorator vs. dynamic) — used when interpreting failures

If the pipeline script path is unknown, glob for `*_pipeline.py` or `*pipeline*.py` in the project root.

## Steps

### 1. Verify the DQ flag is set

Before running, use the `get_local_pipeline_state` MCP tool to confirm `dq.enable_data_quality()` was called on this pipeline.

If the DQ flag is absent in pipeline state:

```
DQ flag not found in pipeline state for "<pipeline-name>".
This means metrics and checks will not be computed on this run.
```

Stop and ask the user to go back to `setup-data-quality` to enable it, unless they explicitly want to run without DQ (e.g., a dry run to test the pipeline itself). Do not silently continue.

### 2. Locate the pipeline run entrypoint

Check session context for the pipeline script path. If not available:

1. Glob the project root for `*pipeline*.py` files
2. If multiple candidates, read the top few lines of each and pick the one that matches the confirmed pipeline name (look for `pipeline_name="<name>"`)
3. Confirm the path with the user before running if ambiguous

### 3. Run the pipeline

Run the pipeline script:

```
uv run python <pipeline_file>.py
```

Capture both stdout and stderr. Do not suppress output — the raw dlt trace is important for diagnosing failures.

If the pipeline script is not self-contained (i.e., it does not call `pipeline.run(...)` at module level), generate a minimal run snippet instead:

```python
import dlt
from <pipeline_module> import <source_function>

pipeline = dlt.attach(pipeline_name="<pipeline-name>")
load_info = pipeline.run(<source_function>())
print(load_info)
load_info.raise_on_failed_jobs()
```

Write it to `tools/dq_run.py` in the project root and run with `uv run python tools/dq_run.py`. Never write to a random temp location.

### 4. Handle pipeline run failure

If `pipeline.run()` raises an exception or `raise_on_failed_jobs()` fails:

**Diagnose the error type:**

| Error pattern | Likely cause | Action |
|---|---|---|
| `PipelineStepFailed` / schema mismatch | Source data changed shape | Hand over to `debug-pipeline` in **rest-api-pipeline** toolkit |
| `DestinationTerminalException` | Destination config / credential issue | Ask user to check secrets and destination setup |
| `DQCheckFailure` / check-related exception | Pre-load check blocked the load (future API) | Go to step 5 |
| Any other exception | Infrastructure or code error | Surface the full traceback and stop |

For non-DQ exceptions, present the error clearly and stop:

```
Pipeline run failed — this is not a DQ issue.

Error: <exception type>
<first 5–10 lines of traceback>

This looks like a [schema / destination / code] problem.
Suggestion: <action from table above>
```

Do not proceed to check result reading if the pipeline itself failed to load data.

### 5. Surface immediate check failures

If the pipeline run succeeded (data loaded), do a quick pass to detect any check failures before handing off to `review-data-quality`.

**Prefer MCP:** use `list_tables` to check whether the destination already has a DQ results table (typically named `_dlt_dq_*` or similar). If found, query it directly with `execute_sql_query`:

```sql
SELECT table_name, check_name, outcome, COUNT(*) as n
FROM <dq_results_table>
GROUP BY table_name, check_name, outcome
ORDER BY outcome DESC
```

**Fallback — Python API:** if the DQ results table name is not discoverable, write and run `tools/dq_quick_check.py`:

```python
import dlt
from dlt.hub import data_quality as dq  # https://dlthub.com/docs/hub/features/quality/data-quality

pipeline = dlt.attach(pipeline_name="<pipeline-name>")
dataset = pipeline.dataset()

results = dq.read_check(dataset).df()
failures = results[results["outcome"] == "fail"] if "outcome" in results.columns else results
print(failures.to_string())
```

**If no failures:**

```
Run complete. All checks passed.
  Tables loaded: <n>
  Rows loaded:   <n>
  Checks run:    <n> — all passed

Moving to review-data-quality for a full metrics review →
```

Proceed immediately to `review-data-quality`.

**If failures are found**, present them in a structured way before proceeding:

```
Run complete — <n> check failure(s) detected:

  Table: orders
    ✗ is_not_null("customer_id")   — 42 rows failed
    ✗ case("amount >= 0")          — 3 rows failed

  Table: customers
    ✓ is_primary_key("id")         — passed
    ✗ is_unique("email")           — 7 duplicate emails found
```

Then ask the user how to proceed with two clear options:

```
How would you like to handle this?

  [1] Adjust the check definition — e.g., the check is too strict for this data
  [2] Investigate the source data — the data has a real quality problem

Or say "continue" to proceed to the full review regardless.
```

**If the user chooses option 1:** hand back to `define-data-quality-checks` with the specific failing checks pre-loaded as the edit target. Do not re-run the full define flow — go straight to the check that needs changing.

**If the user chooses option 2 or "continue":** proceed to `review-data-quality` with the failure context already in session so the review step can prioritise those tables.

## Output and handover

Pass to `review-data-quality`:
- Confirmed pipeline name
- Run outcome (success / failures detected)
- Failing checks and tables (if any) — so review can prioritise them
- Row counts from `load_info` (total rows loaded per table)