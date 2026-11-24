---
name: optimize-sql-performance
description: Speed up a dlt SQL database pipeline. Use when extraction from a relational database (postgres, mysql, mssql, oracle, snowflake, etc.) is slow or memory-heavy and the user wants to optimize it — pick a faster backend, tune chunk size, parallelize tables, or reduce reflection overhead. For first-time incremental/merge setup or removing .add_limit() use adjust-table instead.
argument-hint: "[pipeline-name] [symptom]"
---

# Optimize SQL database extraction

Source-specific tuning for `sql_database` / `sql_table` pipelines. Work the loop — **diagnose → pick the fix → apply → measure → repeat**, one change at a time. Combine these with the source-agnostic stage levers in the **performance** toolkit's `optimize-performance` skill.

**Essential reading:** https://dlthub.com/docs/dlt-ecosystem/verified-sources/sql_database/advanced

Parse `$ARGUMENTS`:
- `pipeline-name` (optional): the dlt pipeline. If omitted, infer from session context; if ambiguous, ask and stop.
- `symptom` (optional): e.g. "extract is slow", "OOM on a wide table", "one table dominates".

## 1. Diagnose

- **Measure first.** Read per-table extract time from `pipeline.last_trace` (or `progress="log"`); confirm extract is the slow stage (if normalize/load dominates, that's the **performance** toolkit).
- **Gate — load less data first.** The biggest SQL speedup is not transferring rows you don't need. If incremental loading isn't set up yet, do that before tuning knobs — see `adjust-table` (it owns cursor/merge/`primary_key` setup).
- **Name the bottleneck:** slow row transfer itself? high memory on a wide table? one big table, or many tables extracted one-by-one? slow startup before any rows load? pulling columns/rows you don't need? a huge first backfill that won't finish?

## 2. Pick the fix

Match the symptom to a lever. They **compose** — apply every one that fits; just don't tune what isn't the bottleneck.

| Symptom | Fix (see Apply) |
|---|---|
| Row transfer itself is slow (default `sqlalchemy`) | Faster backend |
| Memory grows with table size; OOM, killed or hung on a small runner | Bounded reads: `chunk_size`, ConnectorX memory, fewer columns/rows, split backfill |
| Too many round-trips | Tune `chunk_size` |
| Extract is fast but **load** is slow | `optimize-performance` → "Load is slow" (ADBC + parquet, loader formats) |
| One big table, or many tables extracted sequentially | `.parallelize()` tables |
| Parallelized, but threads stall or the DB refuses connections | Size the connection pool |
| Slow startup before any rows load (many/huge tables) | Reduce `reflection_level` |
| Pulling tables / columns / rows you don't need | Push filters/projection to SQL |
| Huge first backfill won't finish or OOMs | Partition / split-load the backfill |

## 3. Apply

**Faster backend** — the single biggest lever for row-transfer speed:

**Size the table first.** Get row count and average row width (`SELECT count(*)`, a sampled `avg(length(...))` or table stats). Compare it with the RAM of the runner. The dltHub platform default instance has a few GiB and no spill to disk. Out of RAM, a job is killed (exit 137), stalls (exit 247) or hangs until `execute.timeout`.

| backend | use when | trade-offs |
|---|---|---|
| `sqlalchemy` (default) | small tables, or nested data to unnest into child tables | max type fidelity; only backend that runs normalize; slowest |
| `pyarrow` | medium/large flat tables; `chunk_size` 5,000–50,000 | needs `numpy`; keeps decimal/date types; reads in `chunk_size` batches, so memory stays bounded |
| `connectorx` | fastest reads, table fits easily in RAM | own connection string; holds the **whole result in memory** and ignores `chunk_size`; dlt may copy it again for type fixes (see ConnectorX memory) |
| `pandas` | DataFrame workflow only | loses precision on decimal and date columns |

Arrow backends (`pyarrow`, `connectorx`) skip normalize and keep nested values as JSON/struct columns. They also let dlt load a bulk format (parquet, or csv on Postgres), so most of their gain is outside extract. Local benchmark (dlt 1.32.0, Postgres → DuckDB, 200k flat rows): `pyarrow` ~15x and `connectorx` ~20x faster end to end than `sqlalchemy`, but only ~2.5x and ~4.5x on extract alone. Ratios change with data shape, network and destination: measure each stage.

```python
from dlt.sources.sql_database import sql_database, sql_table

table = sql_table(table="<table>", backend="pyarrow", chunk_size=50000)
source = sql_database(backend="pyarrow", chunk_size=50000)  # all tables
# connectorx: backend_kwargs={"conn": "<conn-str>"}
```
Install `dlt[sql_database]` (SQLAlchemy is not in the base workspace), plus `numpy` for `pyarrow` or `connectorx` for `connectorx`. With `connectorx`, a **sqlite source needs an absolute path** (`sqlite:////abs/path.db`), else "unable to open database file".

**ConnectorX memory** — peak memory grows with the table. On a small runner this ends in an OOM kill or a hang. Try in this order:
1. Switch to `pyarrow` when memory matters more than read speed.
2. Read less: `included_columns`, a filtering `query_adapter_callback`, incremental loading, or date/id-range slices.
3. Stream: `backend_kwargs={"return_type": "arrow_stream"}` (`batch_size` defaults to `chunk_size`). **Not proven to bound memory** — local test (dlt 1.32.0, 313 MB Postgres table, extract only): peak RSS `pyarrow` 337 MiB, `connectorx` 492 MiB, `arrow_stream` 455 MiB. Measure peak RSS (`resource.getrusage(...).ru_maxrss`, fresh process) on a table larger than the limit first.

**Tune `chunk_size`** — rows per round-trip; larger = fewer round-trips, more memory. Start at `50000`; lower on memory pressure, raise for narrow tables over high-latency links. `connectorx` uses it only in streaming mode.

**Slow load into MSSQL / MySQL / Postgres** — not a source problem. Use "Faster loader format (ADBC + parquet)" in `optimize-performance` (**performance** toolkit). It also lists loader formats to test for other destinations.

**`.parallelize()` tables** — each table extracts in its own thread (no multiprocessing); best when queries are slow or latency is high. Size `[extract] workers` in `optimize-performance`.
```python
source = sql_database().parallelize()             # all tables
table = sql_table(table="<table>").parallelize()  # or per resource
```

**Size the connection pool** — `.parallelize()` runs N threads, each needing its own DB connection; the default SQLAlchemy pool (5) makes extra threads queue, and some DBs reject too many connections. Give the pool room for the parallel threads:
```python
sql_database(engine_kwargs={"pool_size": 8, "max_overflow": 4})
```

**Reduce `reflection_level`** — schema reflection runs before extraction; on many/huge tables it adds startup cost.
```python
sql_database(reflection_level="minimal")   # names + nullability only ("full" is default)
```
For **orchestrated / decomposed** parallel runs (e.g. Airflow `parallel-isolated`), `defer_table_reflect=True` reflects each table at execution time (in its own task/thread) instead of all up front. Requires `table_names`; and since schema is decided at execution, it can override `query_adapter_callback`/`apply_hints` — don't enable it for plain local `.parallelize()`.

**Push work to the database** — less data crosses the wire:
- **Fewer columns** — `included_columns` pulls only the columns you need (simpler than a `table_adapter_callback`):
  ```python
  table = sql_table(table="orders", included_columns=["id", "amount", "updated_at"])
  ```
- **Fewer rows** — `query_adapter_callback` adds `WHERE`/`LIMIT` so the DB filters server-side; `table_adapter_callback` handles more complex table changes. See `create-sql-database-pipeline` — "Add transformation callbacks".
- **Fewer tables** — pass `table_names` so dlt reflects **only** those tables instead of the whole database (`.with_resources(...)` still reflects everything first, then filters — so it doesn't save the reflection cost):
  ```python
  source = sql_database(table_names=["orders", "customers"])
  ```

**Partition / split-load a large initial load** — for an **already-incremental** table (set up in `adjust-table`) whose first backfill is too big for one pass. Two ways:
- **Bounded date-range slices** — load parallel/sequential windows, then let incremental take over: `incremental("updated_at", initial_value=start, end_value=end, range_start="open", range_end="closed")`.
- **`add_limit()` loop (caps memory per run)** — pull a few chunks per run and repeat until empty:
  ```python
  t = sql_table(table="events", chunk_size=1000,
                incremental=dlt.sources.incremental("id", row_order="asc", range_start="open"))
  while not pipeline.run(t.add_limit(5)).is_empty:   # 5 chunks per run
      pass
  ```
`range_start="open"` (`>=` → `>`) skips re-fetching boundary rows; `row_order="asc"` keeps the split gap-free.

## 4. Measure, then repeat

- Re-run and compare per-table time in `pipeline.last_trace` against step 1.
- **Errors under bigger chunks / higher concurrency** → use `debug-sql-database-pipeline`.
- **Memory-bound on the dltHub platform?** Use every pipeline-side fix first: backend, `chunk_size`, fewer columns/rows, sliced backfill, buffers and rotation (`optimize-performance`). A bigger instance is the last resort and needs the user's explicit approval (`optimize-performance`, Step 4). It costs more on every run, and a job that holds the whole table in memory fails on the next tier too.
- **Stop or repeat — check in, don't loop autonomously.** Report the before/after to the user, then:
  - **Stop** when it meets the user's goal (fast enough / fits memory), the last lever gave **no meaningful improvement** (diminishing returns), or you've hit an external ceiling (source DB throughput, network bandwidth) that tuning can't move.
  - **Repeat** with the next matching lever, one at a time. "Fast enough" is the user's call — a minor improvement may already be enough, so confirm before another round rather than chasing micro-gains.

## Next steps

- **Stage-level tuning (workers, buffers, normalize/load parallelism, memory)** → hand over to the **performance** toolkit → `optimize-performance` (install if not present: `uv run dlthub --non-interactive ai toolkit install performance`).
- **Tuned and stable** → hand over to **dlthub-platform** to deploy (install if not present: `uv run dlthub --non-interactive ai toolkit install dlthub-platform`).
