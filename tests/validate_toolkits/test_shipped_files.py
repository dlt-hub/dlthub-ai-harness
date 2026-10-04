"""An install copies an agent folder verbatim, so everything in it reaches a workspace."""

from pathlib import Path

from tests.utils import REPO_ROOT
from tests.validate_toolkits.utils import write

from tools import validate_toolkits as V


def shipped_errors(agent_dir: Path) -> list[str]:
    errors: list[str] = []
    V._validate_shipped_files("tk", agent_dir, errors)
    return errors


def test_a_definition_with_its_modules_passes(tmp_path: Path) -> None:
    write(tmp_path / V._AGENT_FILE, "# an agent\n")
    write(tmp_path / "agent.py", "x = 1\n")
    write(tmp_path / "links.py", "y = 2\n")

    assert shipped_errors(tmp_path) == []


def test_bytecode_beside_a_module_fails(tmp_path: Path) -> None:
    write(tmp_path / V._AGENT_FILE, "# an agent\n")
    write(tmp_path / "links.py", "x = 1\n")
    write(tmp_path / "__pycache__" / "links.cpython-313.pyc", "")

    errors = shipped_errors(tmp_path)

    assert len(errors) == 1
    assert "__pycache__" in errors[0]


def test_every_stray_file_is_listed(tmp_path: Path) -> None:
    write(tmp_path / V._AGENT_FILE, "# an agent\n")
    write(tmp_path / "README.md", "notes\n")
    write(tmp_path / "data.json", "{}\n")

    errors = shipped_errors(tmp_path)

    assert len(errors) == 1
    assert "README.md" in errors[0] and "data.json" in errors[0]


def test_the_shipped_agent_folders_hold_nothing_else() -> None:
    agents = REPO_ROOT / V.AI_DIR / "dlthub-platform" / "agents"
    errors: list[str] = []
    for agent_dir in sorted(p for p in agents.iterdir() if p.is_dir()):
        V._validate_shipped_files("dlthub-platform", agent_dir, errors)

    assert errors == []
