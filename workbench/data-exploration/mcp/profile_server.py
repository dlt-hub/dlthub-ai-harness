"""MCP server with a single bulk `profile_tables` tool.

Profiles many tables in one MCP call (schema + row counts + per-column stats
+ sample rows) instead of the dozens of small calls the generic
`dlt-workspace-mcp` tools require. Run from the workspace root so dlt can
resolve the run context:

    uv run python <path>/profile_server.py
"""

import json
from typing import Any, Dict, List, Optional

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

import dlt
from dlt.common.schema.schema import Schema

# dlt data types that support meaningful MIN/MAX aggregation
_ORDERED_TYPES = {"bigint", "double", "decimal", "wei", "timestamp", "date", "time"}
# dlt data types where COUNT(DISTINCT) is meaningful and safe across engines
_DISTINCT_TYPES = _ORDERED_TYPES | {"bool", "text"}

SAMPLE_ROWS = 5


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


def _stats_query(dataset: dlt.Dataset, table: Dict[str, Any]) -> str:
    """One SELECT computing row count + null/distinct/min/max for every column."""
    schema = dataset.schema
    escape = dataset.sql_client.escape_column_name
    selects = ["COUNT(*) AS row_count"]
    for col in table["columns"].values():
        if col["name"].startswith("_dlt_"):
            continue
        ident = escape(schema.naming.normalize_tables_path(col["name"]))
        data_type = col.get("data_type")
        selects.append(f"COUNT(*) - COUNT({ident}) AS {escape(col['name'] + '__nulls')}")
        if data_type in _DISTINCT_TYPES:
            selects.append(f"COUNT(DISTINCT {ident}) AS {escape(col['name'] + '__distinct')}")
        if data_type in _ORDERED_TYPES:
            selects.append(f"MIN({ident}) AS {escape(col['name'] + '__min')}")
            selects.append(f"MAX({ident}) AS {escape(col['name'] + '__max')}")
    table_ident = escape(schema.naming.normalize_tables_path(table["name"]))
    return f"SELECT {', '.join(selects)} FROM {table_ident}"


def _profile_one(dataset: dlt.Dataset, table: Dict[str, Any]) -> Dict[str, Any]:
    relation = dataset(_stats_query(dataset, table))
    stats_row = dict(zip(relation.columns, relation.fetchall()[0]))
    row_count = stats_row.pop("row_count")

    columns: Dict[str, Any] = {}
    for col in table["columns"].values():
        name = col["name"]
        if name.startswith("_dlt_"):
            continue
        col_profile: Dict[str, Any] = {
            "data_type": col.get("data_type"),
            "nullable": col.get("nullable", True),
        }
        for stat in ("nulls", "distinct", "min", "max"):
            key = f"{name}__{stat}"
            if key in stats_row:
                col_profile[stat] = stats_row[key]
        columns[name] = col_profile

    sample_rel = dataset[table["name"]].limit(SAMPLE_ROWS)
    sample = [dict(zip(sample_rel.columns, row)) for row in sample_rel.fetchall()]

    return {"row_count": row_count, "columns": columns, "sample_rows": sample}


def profile_tables(
    pipeline_name: str,
    table_names: Optional[List[str]] = None,
) -> str:
    """Profile tables of a dlt pipeline in ONE call: per-table schema, row count,
    per-column stats (null count, distinct count, min/max) and sample rows.
    Omit `table_names` to profile all data tables. Use this instead of separate
    list_tables/get_table_schema/get_row_counts/execute_sql_query/preview_table calls."""
    try:
        dataset = _get_dataset(pipeline_name)
    except Exception as e:
        raise ToolError(
            f"Could not attach to pipeline '{pipeline_name}'. Verify the name with"
            " `list_pipelines` from dlt-workspace-mcp."
        ) from e

    data_tables = {t["name"]: t for t in dataset.schema.data_tables()}
    if table_names is None:
        table_names = list(data_tables)

    profiles: Dict[str, Any] = {}
    errors: Dict[str, str] = {}
    for name in table_names:
        if name not in data_tables:
            errors[name] = "table not found in schema"
            continue
        try:
            profiles[name] = _profile_one(dataset, data_tables[name])
        except Exception as e:
            errors[name] = str(e)

    result: Dict[str, Any] = {"pipeline": pipeline_name, "tables": profiles}
    if errors:
        result["errors"] = errors
    return json.dumps(result, default=str)


mcp = FastMCP(name="dlt-profiling-mcp")
mcp.tool(profile_tables)

if __name__ == "__main__":
    mcp.run()
