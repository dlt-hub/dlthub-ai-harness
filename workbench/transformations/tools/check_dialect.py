# tools/check_dialect.py
# Static SQL dialect compatibility checker for @dlt.hub.transformation functions.
# Usage: uv run python ${CLAUDE_PLUGIN_ROOT}/tools/check_dialect.py <transform_file.py> --read <dev_dialect> --write <prod_dialect>
import argparse
import ast
import re
import sys
from pathlib import Path

import sqlglot
from sqlglot import expressions as exp


DLT_TO_SQLGLOT = {
    "motherduck": "duckdb",  # MotherDuck uses DuckDB SQL; no separate SQLGlot dialect
}


def to_sqlglot_dialect(dlt_dest: str) -> str | None:
    mapped = DLT_TO_SQLGLOT.get(dlt_dest, dlt_dest)
    try:
        sqlglot.Dialect.get_or_raise(mapped)
    except Exception:
        return None
    return mapped


def _is_transformation_decorator(node: ast.expr) -> bool:
    if isinstance(node, ast.Call):
        node = node.func
    return isinstance(node, ast.Attribute) and node.attr == "transformation"


def extract_queries(transform_file: Path) -> dict[str, str]:
    """Extract SQL from @dlt.hub.transformation functions via AST.

    Handles both inline literals (dataset("SELECT ...")) and local variable
    assignments (sql = "SELECT ..."; dataset(sql)). Skips f-strings and
    dynamically constructed SQL — those are printed as warnings.
    """
    tree = ast.parse(transform_file.read_text())
    queries = {}
    skipped = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not any(_is_transformation_decorator(d) for d in node.decorator_list):
            continue

        local_strings = {
            n.targets[0].id: n.value.value
            for n in ast.walk(node)
            if isinstance(n, ast.Assign)
            and len(n.targets) == 1
            and isinstance(n.targets[0], ast.Name)
            and isinstance(n.value, ast.Constant)
            and isinstance(n.value.value, str)
        }

        found = False
        for child in ast.walk(node):
            if (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id == "dataset"
                and child.args
            ):
                arg = child.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    queries[node.name] = arg.value
                    found = True
                    break
                if isinstance(arg, ast.Name) and arg.id in local_strings:
                    queries[node.name] = local_strings[arg.id]
                    found = True
                    break
        if not found:
            skipped.append(node.name)
    if skipped:
        print(f"WARNING: skipped {skipped} — SQL is not a static string in dataset(); inspect manually")
    return queries


parser = argparse.ArgumentParser(description="Check SQL dialect compatibility for dlt transformations")
parser.add_argument("transform_file", type=Path, help="Path to the transformation Python file")
parser.add_argument("--read", required=True, metavar="DIALECT", help="Dev/source destination type (e.g. duckdb, motherduck)")
parser.add_argument("--write", required=True, metavar="DIALECT", help="Prod/target destination type (e.g. bigquery, snowflake, postgres)")
args = parser.parse_args()

if not args.transform_file.exists():
    print(f"ERROR: {args.transform_file} not found")
    sys.exit(1)

READ_DIALECT = to_sqlglot_dialect(args.read)
WRITE_DIALECT = to_sqlglot_dialect(args.write)

for label, raw, resolved in [
    ("--read", args.read, READ_DIALECT),
    ("--write", args.write, WRITE_DIALECT),
]:
    if resolved is None:
        available = sorted(d.value for d in sqlglot.dialects.Dialects)
        print(f"ERROR: no SQLGlot dialect for '{raw}' ({label})")
        print(f"Available SQLGlot dialects: {', '.join(available)}")
        sys.exit(1)

QUERIES = extract_queries(args.transform_file)
if not QUERIES:
    print(f"No @dlt.hub.transformation functions with extractable SQL found in {args.transform_file}")
    sys.exit(0)

print(f"Dialects: {READ_DIALECT} -> {WRITE_DIALECT}")
print(f"Checking {len(QUERIES)} transformation(s) from {args.transform_file}\n")

warnings = 0
errors = 0

for name, sql in QUERIES.items():
    query_warnings = []
    query_errors = []

    try:
        parsed = sqlglot.parse_one(sql, read=READ_DIALECT)
        if not isinstance(parsed, exp.Select):
            query_warnings.append(
                f"top-level is {type(parsed).__name__}, not Select; dlt SqlModel may reject it"
            )
    except Exception as e:
        query_errors.append(f"parse failed for {READ_DIALECT}: {e}")

    for identifier in sorted(set(re.findall(r'"([^"\n]+)"', sql))):
        query_warnings.append(
            f'double-quoted identifier "{identifier}"; verify destination quoting in {WRITE_DIALECT}'
        )

    try:
        sqlglot.transpile(
            sql,
            read=READ_DIALECT,
            write=WRITE_DIALECT,
            error_level=sqlglot.ErrorLevel.WARN,
        )
    except Exception as e:
        query_errors.append(f"transpile {READ_DIALECT}->{WRITE_DIALECT} failed: {e}")

    if not query_warnings and not query_errors:
        print(f"[{name}] OK")
        continue

    print(f"[{name}]")
    for warning in query_warnings:
        print(f"  WARN: {warning}")
    for error in query_errors:
        print(f"  ERROR: {error}")
    warnings += len(query_warnings)
    errors += len(query_errors)

print("\nSUMMARY")
print(f"  warnings: {warnings}")
print(f"  errors: {errors}")
sys.exit(1 if warnings or errors else 0)