"""Check the SQL of `@dlt.hub.transformation` functions for dialect compatibility.

Usage, from the project root, with this file from the `debug-transformation` skill folder:
    uv run python <skill folder>/check_dialect.py <transform_file.py> --read <dev_dialect> --write <prod_dialect>
"""

import argparse
import ast
import sys
from pathlib import Path
from typing import NamedTuple, Optional

import sqlglot
from sqlglot import expressions as exp


DLT_TO_SQLGLOT = {
    "motherduck": "duckdb",  # MotherDuck uses DuckDB SQL; no separate SQLGlot dialect
    "mssql": "tsql",
    "synapse": "tsql",
}


class Query(NamedTuple):
    function: str
    sql: str
    dialect: Optional[str]
    """`query_dialect` passed to `dataset()`, else `None`."""


def to_sqlglot_dialect(dlt_dest: str) -> Optional[str]:
    """SQLGlot dialect for a dlt destination type, `None` when SQLGlot has none."""
    mapped = DLT_TO_SQLGLOT.get(dlt_dest, dlt_dest)
    try:
        sqlglot.Dialect.get_or_raise(mapped)
    except Exception:
        return None
    return mapped


def _is_transformation_decorator(node: ast.expr) -> bool:
    # any `<x>.transformation`, bare or called, matches
    if isinstance(node, ast.Call):
        node = node.func
    return isinstance(node, ast.Attribute) and node.attr == "transformation"


def _static_string(node: ast.expr, local_strings: dict[str, str]) -> Optional[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return local_strings.get(node.id)
    return None


def extract_queries(transform_file: Path) -> tuple[list[Query], list[str]]:
    """Every static SQL string passed to `dataset()` in `@dlt.hub.transformation` functions, and the
    functions with SQL that is not a static string."""
    tree = ast.parse(transform_file.read_text())
    queries: list[Query] = []
    skipped: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not any(_is_transformation_decorator(d) for d in node.decorator_list):
            continue

        # resolves `sql = "..."; dataset(sql)` through string constants assigned in the function
        local_strings = {
            n.targets[0].id: n.value.value
            for n in ast.walk(node)
            if isinstance(n, ast.Assign)
            and len(n.targets) == 1
            and isinstance(n.targets[0], ast.Name)
            and isinstance(n.value, ast.Constant)
            and isinstance(n.value.value, str)
        }

        calls = [
            child
            for child in ast.walk(node)
            if isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id == "dataset"
            and child.args
        ]
        found = 0
        for call in calls:
            sql = _static_string(call.args[0], local_strings)
            if sql is None:
                continue
            dialect = next(
                (
                    _static_string(kw.value, local_strings)
                    for kw in call.keywords
                    if kw.arg == "query_dialect"
                ),
                None,
            )
            found += 1
            label = node.name if found == 1 else f"{node.name}#{found}"
            queries.append(Query(label, sql, dialect))
        # dynamic SQL, or table and ibis expressions only
        if found < len(calls) or not calls:
            skipped.append(node.name)
    return queries, skipped


def check_query(query: Query, read: str, write: str) -> tuple[list[str], list[str]]:
    """Warnings and errors for one query, read in its own `query_dialect` or else in `read`."""
    warnings: list[str] = []
    errors: list[str] = []
    source = to_sqlglot_dialect(query.dialect) if query.dialect else read
    if source is None:
        return warnings, [f"no SQLGlot dialect for query_dialect '{query.dialect}'"]

    parsed = None
    try:
        parsed = sqlglot.parse_one(query.sql, read=source)
        if not isinstance(parsed, exp.Select):
            warnings.append(
                f"top-level is {type(parsed).__name__}, not Select; dlthub SqlModel can reject it"
            )
    except Exception as e:
        errors.append(f"parse failed for {source}: {e}")

    if parsed is not None:
        for identifier in sorted(
            {node.name for node in parsed.find_all(exp.Identifier) if node.quoted}
        ):
            warnings.append(
                f'double-quoted identifier "{identifier}"; verify destination quoting in {write}'
            )

    try:
        sqlglot.transpile(query.sql, read=source, write=write, error_level=sqlglot.ErrorLevel.WARN)
    except Exception as e:
        errors.append(f"transpile {source}->{write} failed: {e}")
    return warnings, errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check SQL dialect compatibility for dlthub transformations"
    )
    parser.add_argument("transform_file", type=Path, help="Path to the transformation Python file")
    parser.add_argument(
        "--read",
        required=True,
        metavar="DIALECT",
        help="Dev/source destination type (for example duckdb, motherduck)",
    )
    parser.add_argument(
        "--write",
        required=True,
        metavar="DIALECT",
        help="Prod/target destination type (for example bigquery, snowflake, postgres)",
    )
    parser.add_argument(
        "--strict", action="store_true", help="Treat warnings as errors (exit non-zero on any warning)"
    )
    args = parser.parse_args()

    if not args.transform_file.exists():
        print(f"ERROR: {args.transform_file} not found")
        return 1

    read_dialect = to_sqlglot_dialect(args.read)
    write_dialect = to_sqlglot_dialect(args.write)
    for label, raw, resolved in [
        ("--read", args.read, read_dialect),
        ("--write", args.write, write_dialect),
    ]:
        if resolved is None:
            available = sorted(d.value for d in sqlglot.dialects.Dialects if d.value)
            print(f"ERROR: no SQLGlot dialect for '{raw}' ({label})")
            print(f"Available SQLGlot dialects: {', '.join(available)}")
            return 1

    queries, skipped = extract_queries(args.transform_file)
    if skipped:
        print(
            f"WARNING: skipped {skipped}. The SQL in dataset() is not a static string, or the"
            " function uses table or ibis expressions only. Inspect it manually."
        )
    if not queries:
        print(
            "No @dlt.hub.transformation functions with extractable SQL found in"
            f" {args.transform_file}"
        )
        return 1 if skipped else 0

    print(f"Dialects: {read_dialect} -> {write_dialect}")
    print(f"Checking {len(queries)} queries from {args.transform_file}\n")

    warnings = 0
    errors = 0
    for query in queries:
        query_warnings, query_errors = check_query(query, read_dialect, write_dialect)
        if not query_warnings and not query_errors:
            print(f"[{query.function}] OK")
            continue
        print(f"[{query.function}]")
        for warning in query_warnings:
            print(f"  WARN: {warning}")
        for error in query_errors:
            print(f"  ERROR: {error}")
        warnings += len(query_warnings)
        errors += len(query_errors)

    print("\nSUMMARY")
    print(f"  warnings: {warnings}")
    print(f"  errors: {errors}")
    print(f"  skipped: {len(skipped)}")
    return 1 if errors or skipped or (args.strict and warnings) else 0


if __name__ == "__main__":
    sys.exit(main())
