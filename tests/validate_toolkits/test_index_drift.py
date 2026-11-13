"""The always-loaded intent index lists every listed workflow toolkit, and no unlisted one.

An unlisted toolkit (`"listed": false`) is installed by name only, for example by customers on a
specific plan, so the index that every workspace loads must not advertise it.
"""

from pathlib import Path

from tests.validate_toolkits.utils import write

from tools import validate_toolkits as V


def index_root(tmp_path: Path, indexed: list[str]) -> Path:
    rows = "\n".join(
        f"x → {name} | dlthub --non-interactive ai toolkit install {name} | entry"
        for name in indexed
    )
    for rel in V._INDEX_FILES:
        write(tmp_path / rel, f"```\n{rows}\n```\n")
    return tmp_path


def listed_toolkit(root: Path, name: str, listed: bool) -> None:
    flag = "true" if listed else "false"
    write(
        root / V.AI_DIR / name / ".claude-plugin" / "toolkit.json",
        f'{{"dependencies": ["init"], "listed": {flag}}}',
    )


def drift_errors(root: Path, marketplace_names: set[str]) -> list[str]:
    errors: list[str] = []
    V.validate_index_drift(root, marketplace_names, errors)
    return errors


def test_unlisted_toolkit_needs_no_index_row(tmp_path: Path) -> None:
    root = index_root(tmp_path, ["rest-api-pipeline"])
    listed_toolkit(root, "rest-api-pipeline", listed=True)
    listed_toolkit(root, "payg-pricing", listed=False)

    assert drift_errors(root, {"init", "rest-api-pipeline", "payg-pricing"}) == []


def test_unlisted_toolkit_in_the_index_is_an_error(tmp_path: Path) -> None:
    root = index_root(tmp_path, ["payg-pricing"])
    listed_toolkit(root, "payg-pricing", listed=False)

    errors = drift_errors(root, {"init", "payg-pricing"})

    assert len(errors) == len(V._INDEX_FILES)
    assert all("payg-pricing" in e for e in errors)


def test_listed_toolkit_missing_from_the_index_is_an_error(tmp_path: Path) -> None:
    root = index_root(tmp_path, [])
    listed_toolkit(root, "rest-api-pipeline", listed=True)

    errors = drift_errors(root, {"init", "rest-api-pipeline"})

    assert len(errors) == len(V._INDEX_FILES)
    assert all("missing workflow toolkit 'rest-api-pipeline'" in e for e in errors)
