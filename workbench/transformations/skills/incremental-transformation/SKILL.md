---
name: incremental-transformation
description: Switch a dlt transformation from full-replace to incremental loading. Use when the user wants to process only new or changed rows, reduce transformation run time, or schedule frequent transformation runs without reprocessing all data.
argument-hint: "[pipeline-name]"
---

# Incremental transformation

Switch an existing `@dlt.hub.transformation` from `write_disposition="replace"` to stateful incremental loading, so only new or changed rows are processed on each run.

**Requires:** an existing transformation script from `create-transformation`. If you don't have one, run that skill first.

Reference: https://dlthub.com/docs/devel/hub/features/transformations#incremental-transformations

## Steps

### 1. Choose a pattern

| Situation | Pattern |
|-----------|---------|
| Output table has a date/timestamp/ID column you control (e.g. daily aggregates) | **Direct column** — cursor on the output table's own column |
| Process only rows from new source ingestion loads; no meaningful output cursor | **Load-based** — cursor on `_dlt_loads.inserted_at`; dlt auto-joins the loads table |
| An external orchestrator (Airflow, CI) controls the time window | **External scheduler** — `allow_external_schedulers=True`; reads `DLT_INTERVAL_START` / `DLT_INTERVAL_END` env vars |

Ask the user which situation applies if it is not obvious from the transformation.

### 2. Identify cursor column and Python type

| Pattern | Cursor column | Typical type |
|---------|--------------|-------------|
| Direct | A column on the output table (e.g. `"date"`, `"created_at"`) | `pendulum.DateTime` or `int` |
| Load-based | `"_dlt_loads.inserted_at"` (fixed — no user choice) | `pendulum.DateTime` |
| External scheduler | A source column the orchestrator will filter on | `pendulum.DateTime` |

The type annotation on the parameter (`dlt.sources.incremental[T]`) must match the column type in the destination.

### 3. Set write disposition and primary key

| Pattern | `write_disposition` | `primary_key` |
|---------|--------------------|-----------------------|
| Direct column | `"merge"` | Required — the grain of the output row (e.g. `"date"`) |
| Load-based | `"append"` (default) or `"merge"` if dedup is needed | Only if `"merge"` |
| External scheduler | `"append"` or `"merge"` | Only if `"merge"` |

### 4. Add incremental parameter and apply to the query

**Pattern 1 — Direct column**

Use when aggregations or lookups produce a row per date/ID that should be upserted on each run.

```python
import pendulum
import dlt

@dlt.hub.transformation(write_disposition="merge", primary_key="date")
def crawl_counts_by_date(
    dataset: dlt.Dataset,
    crawled_at: dlt.sources.incremental[pendulum.DateTime] = dlt.sources.incremental(
        "date",
        initial_value=pendulum.datetime(2020, 1, 1, tz="UTC"),
        range_start="open",
    ),
):
    yield dataset("SELECT date, COUNT(*) FROM connectors GROUP BY date").incremental(crawled_at)
```

**Pattern 2 — Load-based (`_dlt_loads.inserted_at`)**

Use when you want exactly the rows that arrived in new ingestion loads. dlt joins `_dlt_loads` automatically — no manual JOIN needed in SQL or relation chains.

```python
from typing import Any
import pendulum
import dlt

@dlt.hub.transformation(write_disposition="append")
def connectors_from_new_loads(
    dataset: dlt.Dataset,
    loaded_at: dlt.sources.incremental[pendulum.DateTime] = dlt.sources.incremental(
        "_dlt_loads.inserted_at",
        range_start="open",
    ),
) -> Any:
    yield (
        dataset.table("connectors")
        .incremental(loaded_at)
        .select("id", "name", "slug", "type", "_dlt_load_id")
    )
```

**Pattern 3 — External scheduler**

Use when an orchestrator sets the window via env vars. `initial_value` sets the fallback start for the first run before the scheduler takes over.

```python
from typing import Any
import pendulum
import dlt

@dlt.hub.transformation(write_disposition="replace")
def orders_window(
    dataset: dlt.Dataset,
    window: dlt.sources.incremental[pendulum.DateTime] = dlt.sources.incremental(
        "created_at",
        initial_value=pendulum.datetime(2000, 1, 1, tz="UTC"),
        allow_external_schedulers=True,
        range_start="closed",
        range_end="open",
    ),
) -> Any:
    yield dataset.table("orders").incremental(window)
```

The orchestrator sets:
```
DLT_INTERVAL_START=2024-01-01T00:00:00Z
DLT_INTERVAL_END=2024-01-02T00:00:00Z
```

### 5. Rules and gotchas

- **`range_start="open"` (default)**: excludes the last-seen cursor value on the next run, preventing double-processing the boundary row. Switch to `"closed"` only if the source may update the record exactly at the cursor boundary.
- **`merge` requires `primary_key`**: without it, rows are not deduped — merge silently behaves like append.
- **Load-based auto-join**: the dotted path `_dlt_loads.inserted_at` triggers an automatic join to the `_dlt_loads` table. Do not write the JOIN yourself.
- **`columns=` hints still apply**: any column that may be NULL on the first incremental run needs an explicit `columns=` hint, same as in `create-transformation`.
- **Same vs. different destination**: when source and target use the same physical destination (same DB file or host), dlt pushes SQL directly without materializing data. Across different destinations, dlt streams Arrow chunks automatically.

### 6. Test incrementally

```bash
# First run — loads all data from initial_value
python transformations/<dataset_name>_to_cdm.py

# Inspect stored cursor state
dlt pipeline <pipeline_name> info

# Second run — should process 0 new rows if no new data arrived
python transformations/<dataset_name>_to_cdm.py
```

Verify row counts with `dlt pipeline <pipeline_name> show` or the `preview_table` MCP tool. If the second run still reprocesses everything, check that `primary_key` is set and that the cursor column name matches exactly (case-sensitive).