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
| Memory grows with table size, or OOM / killed / hung on a small runner | Bounded reads (`chunk_size`, ConnectorX caveat), fewer columns/rows, split backfill. **Instance size is the last resort** |
| Extract is fast but **load** is slow | Destination-side file format / ADBC (see below) |
| High memory, or too many round-trips | Tune `chunk_size` |
| One big table, or many tables extracted sequentially | `.parallelize()` tables |
| Parallelized, but threads stall or the DB refuses connections | Size the connection pool |
| Slow startup before any rows load (many/huge tables) | Reduce `reflection_level` |
| Pulling tables / columns / rows you don't need | Push filters/projection to SQL |
| Huge first backfill won't finish or OOMs | Partition / split-load the backfill |

## 3. Apply

**Faster backend** — the single biggest lever for row-transfer speed:

| backend | typical use (starting points, verify on your data) |
|---|---|
| `sqlalchemy` | default; max type fidelity; the only one where dlt normalizes nested data into child tables; slowest |
| `pyarrow` | good default for large flat tables: Arrow-native, reads in `chunk_size` batches so memory stays bounded |
| `connectorx` | often the fastest reader, **but by default reads the whole result into memory and ignores `chunk_size`**; see the ConnectorX note below |
| `pandas` | only if you specifically need DataFrame coercion |

Local benchmark (200k flat rows, DuckDB sink; your data will differ): pyarrow was ~8-15x and connectorx ~25-30x faster end to end than `sqlalchemy`. Most of that gain was **not** extract: Arrow backends skip normalize and let dlt load parquet instead of `INSERT`s. Nested/wide data, a slower network, or another destination can change the ratios, so re-measure the stages.

```python
from dlt.sources.sql_database import sql_database, sql_table

table = sql_table(table="<table>", backend="pyarrow", chunk_size=50000)
source = sql_database(backend="pyarrow", chunk_size=50000)   # or set for all tables at the source
# backend-specific tuning via backend_kwargs, e.g. connectorx: backend_kwargs={"conn": "<conn-str>"}
```
Prerequisites: `uv add "dlt[sql_database]"` (SQLAlchemy is **not** in the base dlthub workspace), `numpy` for `pyarrow`, `connectorx` for `connectorx`. `connectorx` re-derives its URL from the engine, so **sqlite sources need an absolute path** (`sqlite:////abs/path.db`) — a relative one fails with "unable to open database file".

**ConnectorX memory.** In default mode ConnectorX returns the full query result as one Arrow table, so peak memory scales with the table (and `chunk_size` is ignored). On a memory-limited runner that can end in an OOM kill or a silent hang. Choose one of these, in this order of preference unless you have a measurement saying otherwise:
1. Use `pyarrow` (bounded by `chunk_size`) when memory matters more than the last bit of read speed.
2. Shrink what ConnectorX reads: `included_columns`, a filtering `query_adapter_callback`, incremental loading, or bounded date/id-range slices so each read fits comfortably in RAM.
3. Try ConnectorX streaming: `backend_kwargs={"return_type": "arrow_stream", "batch_size": 50000}` (dlt then yields record batches). **Unverified:** in a small local test (300 MB table, sqlite/Postgres/MySQL) peak extract memory with `arrow_stream` was only ~10% below the default and above pyarrow, so do not assume it bounds memory. Measure peak RSS on your source (a fresh process, `resource.getrusage(...).ru_maxrss`) at a table size larger than the memory limit before relying on it.

**Fast loading with ADBC + parquet (destination side, dlt ≥ 1.19)** — the source backend only speeds up *reading*. When the **destination** is MSSQL, MySQL or Postgres, dlt defaults to `INSERT` statements; installing an [ADBC](https://arrow.apache.org/adbc/) driver makes dlt bulk-load **parquet** instead. Docs report large gains; in our local benchmark (200k rows, loopback Docker) load time dropped ~1.7x for MySQL and ~4.7x for Postgres (total run 1.5x / 3.4x), so expect less than the headline numbers unless the link is slow. Combine with `backend="pyarrow"`/`"connectorx"` so data stays Arrow end-to-end (normalize is skipped). dlt has **no ADBC *source* backend** — ADBC is only for loading.

| destination | how to enable | notes |
|---|---|---|
| `mssql` | install driver → parquet is picked **automatically** | driver is go-mssqldb based; dlt converts the ODBC string (`Encrypt=yes` → `true`, `no` → `disable`). Ingests one row-group at a time to bound memory; no dictionary encoding. |
| `sqlalchemy` + `mysql+pymysql://…` | install driver **and** pass `loader_file_format="parquet"` | go-mysql driver; dlt maps `ssl_ca/ssl_cert/ssl_key/ssl_mode` to `tls-*`. The target MySQL *database* is the dlt `dataset_name`. |
| `postgres` | `loader_file_format="parquet"` opt-in (parquet is not preferred by default); driver is bundled in `adbc-driver-postgresql`, no `dbc` needed | Biggest win measured locally; normalize also disappears once data stays Arrow. |
| `sqlalchemy` + `sqlite` | **nothing to do — ADBC is intentionally disabled** | Python `sqlite3` and `adbc_driver_sqlite` bundle different SQLite builds and corrupt the WAL `-shm` file. Parquet is loaded via batched `INSERT`s. Don't install the sqlite driver for dlt. |

```sh
uv add adbc-driver-manager dbc      # dbc = Columnar's ADBC driver installer
uv run dbc install mssql            # and/or: uv run dbc install mysql
```
`dbc` installs into the active venv (`.venv/etc/adbc/drivers`) — it must run in **every** environment that loads (CI image, deployed runner/container build step), not just your laptop.

```python
source = sql_database(backend="pyarrow", chunk_size=50000)
pipeline = dlt.pipeline("p", destination="mssql", dataset_name="raw")      # parquet auto when driver found
pipeline.run(source)
# MySQL (sqlalchemy destination) must opt in; revert any destination with loader_file_format="insert_values"
pipeline.run(source, loader_file_format="parquet")
```

**The fallback is silent — always verify.** If the driver is missing, dlt drops `parquet` and uses `INSERT` (a warning is logged only if parquet was explicitly requested). Check both:
```python
from dlt.destinations._adbc_jobs import has_adbc_driver
print(has_adbc_driver("mssql"))   # (True, None) = found. For mysql, (True, "…missing required option uri") is also fine: it was found.
jobs = pipeline.last_trace.last_load_info.load_packages[0].jobs["completed_jobs"]
print({j.job_file_info.file_format for j in jobs})   # data tables must show 'parquet' (MySQL/MSSQL ADBC); 'insert_values' = fallback
```
(dlt's own tables like `_dlt_loads` always load as `insert_values`.) Before blaming the driver, rule out `disable_adbc_detection = true` in `config.toml`. Rotate files (`[normalize.data_writer] file_max_items`) so `[load] workers` can ingest several parquet files in parallel — see `optimize-performance`.

**Destination-specific file formats (hypotheses to measure).** The format dlt writes for loading is a per-destination choice, and the best one depends on the destination and your data. dlt's defaults / supported formats (from its destination capabilities in dlt 1.x; re-check against your version with `dlt.destinations.<name>().capabilities()`):

| Destination | Default loader format | Also supported | Notes |
|---|---|---|---|
| BigQuery | jsonl | parquet | Parquet is usually the better fit for Arrow-backed sources. Avro is not a dlt loader format in this version, so do not plan around it. Loads go through GCS staging for bulk. |
| Snowflake | jsonl | parquet, csv | CSV and parquet are both worth comparing; CSV tends to suit flat, row-oriented data, parquet suits Arrow sources and preserves types. Stage via a bucket for large loads. |
| Databricks | parquet | jsonl | Parquet via staging is the natural path. |
| ClickHouse | jsonl | parquet | |
| Redshift | insert_values | (jsonl/parquet via staging) | Large loads need a staging bucket. |
| Postgres | insert_values | csv, parquet | parquet via ADBC (above); csv is another option. |
| MSSQL, MySQL | insert_values | parquet | parquet via ADBC (above). |
| DuckDB | insert_values | parquet, jsonl | Arrow sources load as parquet. |

How to use this: with an Arrow backend, parquet is the default candidate because no conversion is needed. Treat any other format (csv for Snowflake, jsonl for nested data, etc.) as an experiment: set `loader_file_format=` on `pipeline.run`, compare the load stage time and the completed-job file formats from `last_trace`, keep what wins. Format choice can interact with `file_max_items` / `[load] workers`, so re-test when you change those.

**Tune `chunk_size`** — rows fetched per round-trip. Larger = fewer round-trips, more memory. Start at `50000` for `pyarrow` (for `connectorx` it only applies in streaming mode); lower on memory pressure, raise for narrow tables over high-latency links.

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
- **Memory-bound on the dltHub platform?** Exhaust pipeline-side fixes first (backend/`chunk_size`, fewer columns and rows, incremental or sliced backfill, buffers and file rotation via `optimize-performance`). A bigger instance is a last resort: it multiplies cost on every run, disk does not grow with it, and a job that materializes the whole table is OOM-killed on the next tier too. It needs the user's explicit approval (see `optimize-performance`, Step 4).
- **Stop or repeat — check in, don't loop autonomously.** Report the before/after to the user, then:
  - **Stop** when it meets the user's goal (fast enough / fits memory), the last lever gave **no meaningful improvement** (diminishing returns), or you've hit an external ceiling (source DB throughput, network bandwidth) that tuning can't move.
  - **Repeat** with the next matching lever, one at a time. "Fast enough" is the user's call — a minor improvement may already be enough, so confirm before another round rather than chasing micro-gains.

## Next steps

- **Stage-level tuning (workers, buffers, normalize/load parallelism, memory)** → hand over to the **performance** toolkit → `optimize-performance` (install if not present: `uv run dlthub --non-interactive ai toolkit install performance`).
- **Tuned and stable** → hand over to **dlthub-platform** to deploy (install if not present: `uv run dlthub --non-interactive ai toolkit install dlthub-platform`).
