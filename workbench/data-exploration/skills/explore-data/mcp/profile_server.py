"""MCP server with a single bulk `profile_tables` tool.

Profiles many tables in one MCP call (schema + row counts + per-column stats
+ sample rows) instead of the dozens of small calls the generic
`dlt-workspace-mcp` tools require. Run from the workspace root so dlt can
resolve the run context.

Launched from .mcp.json via `sh -c` with a CLAUDE_PLUGIN_ROOT fallback so the
same entry works in both install channels: Claude Code plugin installs set
CLAUDE_PLUGIN_ROOT; `dlthub ai toolkit install` vendors this file under
`.claude/skills/explore-data/mcp/` in the workspace.
"""

import math
from typing import Any, Dict, List, Optional, Tuple

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

import dlt
from dlt.common.schema.schema import Schema

# dlt data types that support meaningful MIN/MAX aggregation
_ORDERED_TYPES = {"bigint", "double", "decimal", "wei", "timestamp", "date", "time"}
# dlt data types where COUNT(DISTINCT) is meaningful and safe across engines
_DISTINCT_TYPES = _ORDERED_TYPES | {"bool", "text"}

SAMPLE_ROWS = 5
# bound a single call: more tables are reported in `skipped_tables`
MAX_TABLES = 20
# skip COUNT(DISTINCT) full scans above this row count
DISTINCT_ROW_LIMIT = 10_000_000


def _get_unified_schema(pipeline: dlt.Pipeline) -> Schema:
    schema_names = list(pipeline.schemas)
    if len(schema_names) <= 1:
        return pipeline.default_schema
    default = pipeline.default_schema
    others = [pipeline.schemas[n] for n in schema_names if n != default.name]
    return default.unify_schemas(others)


def _get_dataset(pipeline_name: str) -> dlt.Dataset:
    pipeline = dlt.attach(pipeline_name)
    return pipeline.dataset(schema=_get_unified_schema(pipeline))


def _profilable_columns(table: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Columns worth profiling: skip dlt internals and incomplete (hint-only,
    never materialized) columns — referencing those fails the whole query."""
    return [
        col
        for col in table["columns"].values()
        if not col["name"].startswith("_dlt_") and col.get("data_type")
    ]


def _clean(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, (bytes, bytearray)):
        return f"<{len(value)} bytes>"
    return value


def _stats_query(
    dataset: dlt.Dataset, table: Dict[str, Any], with_distinct: bool
) -> Tuple[str, List[str]]:
    """One SELECT computing row count + null/distinct/min/max for every column.

    Returns (sql, keys); results are consumed positionally — aliases must not
    round-trip through the destination's identifier casefolding (e.g. Snowflake
    uppercases them), so they are neutral s<i> names.
    """
    schema = dataset.schema
    escape = dataset.sql_client.escape_column_name
    selects = ["COUNT(*)"]
    keys = ["row_count"]
    for col in _profilable_columns(table):
        ident = escape(schema.naming.normalize_tables_path(col["name"]))
        data_type = col["data_type"]
        selects.append(f"COUNT(*) - COUNT({ident})")
        keys.append(f"{col['name']}__nulls")
        if with_distinct and data_type in _DISTINCT_TYPES:
            selects.append(f"COUNT(DISTINCT {ident})")
            keys.append(f"{col['name']}__distinct")
        if data_type in _ORDERED_TYPES:
            selects.append(f"MIN({ident})")
            keys.append(f"{col['name']}__min")
            selects.append(f"MAX({ident})")
            keys.append(f"{col['name']}__max")
    aliased = [f"{expr} AS s{i}" for i, expr in enumerate(selects)]
    table_ident = escape(schema.naming.normalize_tables_path(table["name"]))
    return f"SELECT {', '.join(aliased)} FROM {table_ident}", keys


def _profile_one(
    dataset: dlt.Dataset, table: Dict[str, Any], with_distinct: bool
) -> Dict[str, Any]:
    sql, keys = _stats_query(dataset, table, with_distinct)
    values = dataset(sql).fetchall()[0]
    stats_row = {key: _clean(value) for key, value in zip(keys, values)}
    row_count = stats_row.pop("row_count")

    profilable = _profilable_columns(table)
    columns: Dict[str, Any] = {}
    for col in profilable:
        name = col["name"]
        col_profile: Dict[str, Any] = {
            "data_type": col["data_type"],
            "nullable": col.get("nullable", True),
        }
        for stat in ("nulls", "distinct", "min", "max"):
            key = f"{name}__{stat}"
            if key in stats_row:
                col_profile[stat] = stats_row[key]
        columns[name] = col_profile

    sample: List[Dict[str, Any]] = []
    if profilable:
        sample_rel = (
            dataset[table["name"]].select(*[c["name"] for c in profilable]).limit(SAMPLE_ROWS)
        )
        sample = [
            {col: _clean(value) for col, value in zip(sample_rel.columns, row)}
            for row in sample_rel.fetchall()
        ]

    return {"row_count": row_count, "columns": columns, "sample_rows": sample}


def profile_tables(
    pipeline_name: str,
    table_names: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Profile tables of a dlt pipeline in ONE call: per-table schema, row count,
    per-column stats (null count, distinct count, min/max) and sample rows.
    Omit `table_names` to profile all data tables (capped at 20 per call —
    remaining tables are listed in `skipped_tables`; call again with those
    names). Use this instead of separate list_tables/get_table_schema/
    get_row_counts/execute_sql_query/preview_table calls."""
    try:
        dataset = _get_dataset(pipeline_name)
    except Exception as e:
        raise ToolError(
            f"Could not attach to pipeline '{pipeline_name}': {e}. Verify the name"
            " with `list_pipelines` from dlt-workspace-mcp."
        ) from e

    data_tables = {t["name"]: t for t in dataset.schema.data_tables(seen_data_only=True)}
    if table_names is None:
        table_names = list(data_tables)
    skipped = table_names[MAX_TABLES:]
    table_names = table_names[:MAX_TABLES]

    # one bulk query for row counts, used to guard COUNT(DISTINCT) full scans
    row_counts: Dict[str, int] = {}
    try:
        row_counts = dict(dataset.row_counts().fetchall())
    except Exception:
        pass  # guard degrades to always computing distinct counts

    profiles: Dict[str, Any] = {}
    errors: Dict[str, str] = {}
    for name in table_names:
        if name not in data_tables:
            errors[name] = "table not found in schema (or has not loaded data yet)"
            continue
        with_distinct = row_counts.get(name, 0) <= DISTINCT_ROW_LIMIT
        try:
            profiles[name] = _profile_one(dataset, data_tables[name], with_distinct)
        except Exception as e:
            errors[name] = str(e)

    result: Dict[str, Any] = {"pipeline": pipeline_name, "tables": profiles}
    if skipped:
        result["skipped_tables"] = skipped
    if errors:
        result["errors"] = errors
    return result


mcp = FastMCP(name="dlt-profiling-mcp")
mcp.tool(profile_tables)

if __name__ == "__main__":
    mcp.run()
