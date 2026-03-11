# dlt Relation API reference

Reference: https://dlthub.com/docs/api_reference/dlt/dataset/relation#relation-objects
Dataset docs: https://dlthub.com/docs/general-usage/dataset-access/dataset.md

## Query priority for charts

For chart queries, prefer SQL — it's concise and readable for aggregations. Use ibis for complex joins or computed columns. Use the Relation API for simple discovery (row counts, column inspection, quick filters).

## Getting a dataset and table relations

```python
import dlt

pipeline = dlt.attach("<pipeline_name>")
dataset = pipeline.dataset()

# Get a Relation for a table
table = dataset["my_table"]
```

## Connecting to a standalone DuckDB file

If data exists in a `.duckdb` file but no attached pipeline is available, connect with an explicit destination:

```python
import dlt

pipeline = dlt.pipeline(
    pipeline_name="local_duckdb_analysis",
    destination=dlt.destinations.duckdb("/absolute/path/to/data.duckdb"),
    dataset_name="github_data",  # optional if known
)
dataset = pipeline.dataset()
dataset.row_counts().df()
```

## SQL queries (preferred for charts)

```python
dataset("SELECT * FROM orders WHERE amount > 100").df()

## ibis expressions (complex queries)

Use `table.to_ibis()` when you need joins, group-by, computed columns, or complex boolean filters:

```python
t = dataset["orders"].to_ibis()
expr = (
    t.filter(t.amount > 100)
    .group_by("category")
    .aggregate(total=t.amount.sum(), count=t.id.count())
    .order_by(ibis.desc("total"))
)
dataset(expr).df()  # execute ibis expression back through the dataset
```

Key ibis operations: `group_by/aggregate`, `filter`, `join`, `order_by(ibis.desc(...))`, `mutate`.

Ibis docs: https://ibis-project.org/reference/expression-collections

## Chainable query methods

All methods return a new `Relation` (immutable chaining):

```python
# Select columns
table.select("id", "name", "amount")

# Filter rows (column, operator, value)
table.where("status", "eq", "active")
table.where("amount", "gt", 100)
table.where("id", "in", [1, 2, 3])
# Operators: eq, ne, gt, lt, gte, lte, in, not_in

# Limit and ordering
table.limit(100)
table.head()                             # limit(5) by default
table.order_by("created_at")            # ascending by default
table.order_by("amount", "desc")

# Chain them together
table.select("id", "amount").where("amount", "gt", 100).order_by("amount", "desc").limit(10)
```

## Materializing results

Relations are lazy — they execute only when you materialize:

```python
table.df()                     # -> pandas DataFrame (or None if empty)
table.arrow()                  # -> PyArrow Table (or None if empty)
table.fetchall()               # -> list[tuple[...]]
table.fetchone()               # -> tuple[...] | None (first row)
```

## Row counts and schema inspection

```python
dataset.row_counts().df()          # DataFrame with row counts for all tables
table.columns                      # list of column names
table.columns_schema               # dlt column schema dict
```

## Relation limitations

No `join()`, `count()`, or `group_by()` — use `to_ibis()` or raw SQL for these.

## Joining parent/child tables (dlt nested data)

dlt creates child tables for nested data (e.g., `orders__items`). Join on `_dlt_id` / `_dlt_parent_id`:
```python
parent = dataset["orders"].to_ibis()
child = dataset["orders__items"].to_ibis()
joined = parent.join(child, parent._dlt_id == child._dlt_parent_id)
```
