# dlt Glossary

A distilled plain-English reference for the key constructs in `dlt` (data load tool), their canonical names, and how they relate to one another. Use this to ensure consistent wording across documentation.

---

## dlt (data load tool)

The open-source Python library for loading data. Users `import dlt` and use it to define data sources, configure destinations, and run pipelines. The top-level module exposes all primary abstractions described below.

---

## Pipeline

The central orchestration object. A pipeline connects a data **source** to a **destination** and coordinates the three steps of data movement: **extract**, **normalize**, and **load**. It also holds **state** and manages **schemas**.

- Created with `dlt.pipeline()`, which returns a `Pipeline` instance.
- The shortcut `dlt.run(data, ...)` creates a transient pipeline and runs it immediately.
- A pipeline is identified by a `pipeline_name`, which also determines where local state and schemas are persisted (the pipelines directory).
- The `dataset_name` parameter controls the logical group of tables written to the destination (equivalent to a schema in SQL databases, or a folder for file-based destinations).

**Key methods on `Pipeline`:**

| Method | What it does |
|--------|-------------|
| `run(data, ...)` | Full cycle: extract → normalize → load |
| `extract(data, ...)` | Extract data and stage it locally; no destination required |
| `normalize(...)` | Infer/update schema and produce load packages from extracted data |
| `load(...)` | Upload load packages to the destination |
| `dataset(schema=...)` | Return a `Dataset` object for querying loaded data |
| `state` | Return the pipeline's persisted state dictionary |
| `schemas` | Access all schemas associated with this pipeline |

---

## Source

A logical grouping of **resources** that are often extracted and loaded together. A source is associated with a single **schema**.

- Declared with the `@dlt.source` decorator on a function that returns one or more resources.
- The decorated function becomes a `DltSource` (via a `DltSourceFactoryWrapper`) when called.
- The source name (defaults to the function name) becomes the schema name.
- Sources can receive **configuration** and **secrets** via automatically resolved function arguments.
- The `section` parameter determines where dlt looks for configuration values: `sources.<section>.<source_name>.<key>`.

---

## Resource

A single stream of data within a **source**. A resource maps to one (or more, via nesting) tables in the destination.

- Declared with the `@dlt.resource` decorator on a generator function, or by calling `dlt.resource(data)` directly.
- The resource `name` defaults to the function name and becomes the table name.
- A resource carries its **hints** (table schema, write disposition, primary key, etc.) alongside its data.
- Resources are `Iterable` and can be iterated, combined into a source, or passed directly to `pipeline.run`.
- Resources can receive **configuration** and **secrets** the same way sources do.

---

## Transformer

A special form of **resource** that receives data from another resource, enriches or transforms it, and yields new data.

- Declared with `@dlt.transformer` (or `@dlt.resource(data_from=...)`) on a function whose first argument receives items from the upstream resource.
- Bound at creation time (`data_from=upstream`) or dynamically using the pipe operator: `upstream | transformer`.
- Useful for API lookups, enrichment chains, and multi-step extraction patterns.

---

## Schema

A versioned description of the tables and columns produced by a **source**. dlt infers schemas automatically from the data but allows explicit declaration.

- Each source has exactly one schema, named after the source.
- A schema contains **table schemas** (column names, data types, hints).
- Schemas are updated incrementally as new data arrives and new columns or tables are discovered.
- Schema changes are tracked via a version hash; the `is_modified` flag indicates uncommitted changes.
- Schemas can be serialized to YAML and committed to version control as part of the project.
- The **naming convention** of a schema determines how identifiers (table and column names) are normalized (e.g., snake_case, camelCase).

---

## Normalization

The process of transforming extracted data (typically nested JSON) into a relational form — flat tables with typed columns. Normalization also infers and updates the **schema**.

- Runs as the second pipeline step (between extract and load).
- Nested objects become child tables linked to the parent by a generated foreign key (`_dlt_parent_id`).
- `max_table_nesting` limits nesting depth; beyond the limit, nested objects are stored as JSON/struct columns.
- The normalizer produces **load packages** — sets of files (JSONL or Parquet) ready for loading.
- A `_dlt_id` column (unique row identifier) and `_dlt_load_id` column (load package identifier) are added to every table by default.

---

## Hints

Metadata attached to a resource (or applied at run-time) that controls how data is written and structured.

Key hints:

| Hint | Purpose |
|------|---------|
| `write_disposition` | How to write data to the table: `append`, `replace`, `merge`, or `skip` |
| `primary_key` | Column(s) used to identify unique records (required for `merge`) |
| `merge_key` | Column(s) used to define overlap ranges in merge (e.g. a date range key) |
| `columns` | Explicit column schema (types, nullable, etc.) |
| `table_name` | Override the default table name |
| `table_format` | Storage format: `delta` or `iceberg` (destination-dependent) |
| `schema_contract` | Policy for handling new tables or columns |
| `references` | Foreign-key-style relationships to other tables |

Hints can be static (declared at decoration time) or **dynamic** (a callable that returns a hint value per row, enabling fan-out to multiple tables from a single resource).

---

## Write Disposition

Controls how incoming data interacts with existing data in the destination table.

| Disposition | Behaviour |
|-------------|-----------|
| `append` | New rows are added to the end of the table (default) |
| `replace` | Existing table data is replaced with new data each run |
| `merge` | Records are deduplicated and upserted based on `primary_key`; `merge_key` can further define overlap ranges |
| `skip` | Data is extracted but not loaded |

The `merge` disposition supports strategies: the default strategy is a primary-key upsert; `scd2` enables Slowly Changing Dimension Type 2 (history-preserving) behaviour.

---

## Destination

Where data is loaded. dlt ships with built-in destinations for major data warehouses and file systems.

- Destinations are referenced by name (`"duckdb"`, `"bigquery"`) or by importing a module from `dlt.destinations`.
- A destination is configured through **credentials** and a **destination configuration** spec — both resolved via the standard config system.
- Built-in destinations include: BigQuery, Snowflake, Redshift, Postgres, DuckDB, ClickHouse, Databricks, Athena, filesystem (S3, GCS, Azure), and others.
- Each destination exposes **capabilities** (supported file formats, identifier casing rules, max query parameters, etc.) that influence normalization and loading behaviour.

---

## Staging

An optional intermediate destination used before the final load. Data is first written to the staging destination (typically a blob storage), then loaded from there into the final destination using the destination's native bulk-load mechanism.

- Configured with the `staging` parameter in `pipeline.run(staging=...)`.
- Useful for destinations like BigQuery or Snowflake that perform better with file-based loads from object storage.

---

## Dataset

A logical group of tables within a destination — equivalent to a SQL schema or a directory of files. The `dataset_name` parameter on a pipeline or `run()` call controls which dataset tables are written into.

- Access loaded data programmatically with `pipeline.dataset()`, which returns a `Dataset` object.
- `Dataset` provides access to individual tables as dataframes, Arrow tables, or via a SQL/dbapi cursor.
- The `Relation` class represents a single table or query result within a dataset.

---

## Load Package

The unit of work that moves through the pipeline. A load package groups all files produced during a single `normalize` step for one schema and destination. It is identified by a `load_id`.

- Packages pass through three states: **extracted** (raw data files), **normalized** (load-ready files), and **completed** (successfully loaded).
- Failed and pending packages can be inspected and retried.
- Each loaded row carries the `_dlt_load_id` of its package, enabling lineage tracking.

---

## Incremental Loading

A pattern for loading only new or updated records by tracking a cursor value (e.g. a timestamp or integer ID) across pipeline runs.

- Configured with `dlt.sources.incremental` — either passed directly to `@dlt.resource(incremental=...)` or used as a function argument typed `Incremental[T]`.
- dlt persists the last seen cursor value in **pipeline state** and passes it back on the next run, allowing the resource to filter to only new data.
- Supports `initial_value` (starting cursor for the first run), `end_value` (upper bound for backfill), and `lag` (lookback buffer for late-arriving data).

---

## Pipeline State

A persistent dictionary associated with a pipeline, stored both locally and synced to the destination. State survives between runs and is the foundation for **incremental loading** and resource-level bookkeeping.

- Accessed via `pipeline.state`.
- Per-source and per-resource state is namespaced automatically.
- State is extracted alongside data and loaded to a special `_dlt_pipeline_state` table in the destination, allowing state to be restored after the local working directory is deleted.

---

## Schema Contract

A policy that controls how dlt responds to unexpected schema changes — new tables, new columns, or data type mismatches — during extraction or normalization.

- Configured at the source, resource, or pipeline level via `schema_contract`.
- Settings per entity type (`tables`, `columns`, `data_type`): `evolve` (allow and update schema), `discard_row` (drop the offending row), `discard_value` (drop the offending column), or `freeze` (raise an exception).

---

## Configuration and Secrets

The system dlt uses to inject settings and credentials into sources, resources, and destinations without hardcoding values in code.

- **Configuration** (`dlt.config`) holds non-sensitive values (URLs, timeouts, flags).
- **Secrets** (`dlt.secrets`) hold sensitive values (API keys, passwords, tokens).
- Values are resolved from a layered set of **providers** in priority order: explicit arguments → environment variables → `secrets.toml` / `config.toml` → cloud vaults (Google Secret Manager, etc.).
- Config keys follow a hierarchical layout: `sources.<section>.<source_name>.<key>` for sources, `destination.<destination_name>.<key>` for destinations.
- **Specs** (`@dlt.common.configuration.configspec`) are typed dataclass-like classes that declare what configuration a component needs; dlt auto-resolves their fields from providers.
- **Credentials** (`CredentialsConfiguration`) are specs whose values may only come from secret-capable providers. Built-in credentials exist for AWS, GCP, Azure, OAuth2, connection strings, and more.
- Type annotations `TSecretValue` and `TCredentials` signal to dlt that a function argument should be sourced from secrets.

---

## Relationships Between Constructs

```
dlt.pipeline()
  └── Pipeline
        ├── extract(source/resource)
        │     └── DltSource
        │           └── DltResource(s) / Transformers
        │                 └── yields data items → load packages (raw)
        ├── normalize()
        │     └── applies Schema + naming convention
        │           → flattens nested data
        │           → updates Schema (respecting schema_contract)
        │           → produces load packages (files)
        ├── load()
        │     └── sends load packages → Destination (optionally via Staging)
        ├── dataset() → Dataset / Relation  (query loaded data)
        └── state    (persisted across runs, powers incremental loading)
```

---

## Canonical Term Usage

| Preferred term | Avoid / Notes |
|---------------|---------------|
| **pipeline** | "workflow", "job" |
| **source** | "connector", "integration" (these refer to the ecosystem concept; `source` is the Python construct) |
| **resource** | "table source", "data stream" |
| **transformer** | "enricher", "derived resource" |
| **destination** | "sink", "target" |
| **dataset** | "schema" (in destination context); `dataset_name` ≠ `Schema` object |
| **schema** | "table definitions", "data model" — use `Schema` (capital S) for the Python object, `schema` for the concept |
| **hints** | "metadata", "table settings" |
| **write disposition** | "load mode", "insert mode" |
| **incremental loading** | "delta loading", "CDC" (CDC is a different mechanism) |
| **normalization** | "transformation", "flattening" — normalization in dlt is specifically the structural reshape step, not business-logic transformation |
| **load package** | "batch", "file set" |
| **staging** | "intermediate storage", "pre-load area" |
| **state** | "cursor", "checkpoint" — state is the broader store; cursor is the incremental tracking value within state |
| **configuration** | "settings", "config" (lowercase `config` acceptable in code context) |
| **secrets** | "credentials" (credentials are a sub-type of secrets specific to authentication) |
| **spec** | "configuration class", "config schema" |
