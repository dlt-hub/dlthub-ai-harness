"""The dialect checker that ships in the `debug-transformation` skill folder."""

import importlib.util
from pathlib import Path

from tests.utils import REPO_ROOT

_PATH = (
    REPO_ROOT
    / "workbench"
    / "transformations"
    / "skills"
    / "debug-transformation"
    / "check_dialect.py"
)
_spec = importlib.util.spec_from_file_location("check_dialect", _PATH)
check_dialect = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_dialect)

TRANSFORMATIONS = '''
import dlt

SUFFIX = "x"


@dlt.hub.transformation
def dim_person(dataset):
    yield dataset("SELECT email, first_name FROM contacts")


@dlt.hub.transformation(write_disposition="replace")
def monthly(dataset):
    sql = "SELECT STRFTIME(created_at, '%Y-%m') AS month FROM events"
    yield dataset(sql, query_dialect="duckdb")
    yield dataset("SELECT id FROM events")


@dlt.hub.transformation
def dynamic(dataset):
    yield dataset("SELECT * FROM " + SUFFIX)


@dlt.hub.transformation
def with_ibis(dataset):
    yield dataset.table("events").to_ibis().limit(10)


def not_a_transformation(dataset):
    yield dataset("SELECT 1")
'''


def _write(tmp_path: Path) -> Path:
    path = tmp_path / "t.py"
    path.write_text(TRANSFORMATIONS, encoding="utf-8")
    return path


def test_extracts_every_static_query_with_its_dialect(tmp_path: Path) -> None:
    queries, skipped = check_dialect.extract_queries(_write(tmp_path))

    assert [(q.function, q.dialect) for q in queries] == [
        ("dim_person", None),
        ("monthly", "duckdb"),
        ("monthly#2", None),
    ]
    assert sorted(skipped) == ["dynamic", "with_ibis"]


def test_maps_dlt_destinations_to_sqlglot_dialects() -> None:
    assert check_dialect.to_sqlglot_dialect("mssql") == "tsql"
    assert check_dialect.to_sqlglot_dialect("synapse") == "tsql"
    assert check_dialect.to_sqlglot_dialect("motherduck") == "duckdb"
    assert check_dialect.to_sqlglot_dialect("snowflake") == "snowflake"
    assert check_dialect.to_sqlglot_dialect("not_a_dialect") is None


def test_query_dialect_wins_over_read(tmp_path: Path) -> None:
    queries, _ = check_dialect.extract_queries(_write(tmp_path))
    monthly = next(q for q in queries if q.function == "monthly")

    # `--read postgres` would not parse DuckDB's STRFTIME the same way; the declared dialect is used
    warnings, errors = check_dialect.check_query(monthly, "postgres", "snowflake")

    assert errors == []


def test_reports_parse_errors() -> None:
    query = check_dialect.Query("broken", "SELECT FROM WHERE", None)

    _, errors = check_dialect.check_query(query, "duckdb", "snowflake")

    assert errors and "failed" in errors[0]
