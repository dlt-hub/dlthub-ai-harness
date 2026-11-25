"""The launcher package must pass the Codex (OpenAI) plugin directory rules."""

import json
from pathlib import Path

from tests.utils import REPO_ROOT

from tools import generate_catalogs as G

LAUNCHER = REPO_ROOT / "workbench" / G.LAUNCHER


def launcher_codex() -> dict:
    return json.loads((LAUNCHER / ".codex-plugin" / "plugin.json").read_text())


def valid_folder(tmp_path: Path) -> Path:
    folder = tmp_path / G.LAUNCHER
    (folder / "skills" / "setup").mkdir(parents=True)
    (folder / "skills" / "setup" / "SKILL.md").write_text("---\nname: setup\n---\n")
    (folder / "assets").mkdir()
    (folder / "assets" / "icon.jpeg").write_bytes(b"")
    return folder


def manifest(**interface: str) -> dict:
    return {
        "version": "1.0.0",
        "interface": {
            "displayName": "dltHub Setup",
            "shortDescription": "dltHub toolkit launcher",
            "logo": "./assets/icon.jpeg",
            "composerIcon": "./assets/icon.jpeg",
            **interface,
        },
    }


def test_shipped_launcher_passes() -> None:
    assert G.codex_errors(LAUNCHER, launcher_codex()) == []


def test_valid_package_passes(tmp_path: Path) -> None:
    assert G.codex_errors(valid_folder(tmp_path), manifest()) == []


def test_long_short_description(tmp_path: Path) -> None:
    errors = G.codex_errors(valid_folder(tmp_path), manifest(shortDescription="x" * 31))

    assert errors == [f"{G.LAUNCHER}: interface.shortDescription is longer than 30 characters"]


def test_bad_version(tmp_path: Path) -> None:
    errors = G.codex_errors(valid_folder(tmp_path), {**manifest(), "version": "1.0"})

    assert errors == [f"{G.LAUNCHER}: version '1.0' is not semver"]


def test_missing_icon(tmp_path: Path) -> None:
    errors = G.codex_errors(valid_folder(tmp_path), manifest(logo="./assets/icon.png"))

    assert errors == [f"{G.LAUNCHER}: interface.logo file ./assets/icon.png does not exist"]


def test_no_skills(tmp_path: Path) -> None:
    folder = valid_folder(tmp_path)
    (folder / "skills" / "setup" / "SKILL.md").unlink()

    assert G.codex_errors(folder, manifest()) == [f"{G.LAUNCHER}: skills/ has no <name>/SKILL.md"]


def test_rejected_entries(tmp_path: Path) -> None:
    folder = valid_folder(tmp_path)
    (folder / "hooks").mkdir()
    (folder / ".mcp.json").write_text("{}")

    assert G.codex_errors(folder, manifest()) == [
        f"{G.LAUNCHER}: hooks is not allowed",
        f"{G.LAUNCHER}: .mcp.json is not allowed",
    ]


def test_rejects_unknown_category(tmp_path: Path) -> None:
    errors = G.codex_errors(valid_folder(tmp_path), manifest(category="Data"))
    assert errors == [f"{G.LAUNCHER}: interface.category 'Data' is not a Codex category"]


def test_rejects_too_many_prompts(tmp_path: Path) -> None:
    prompts = ["a", "b", "c", "d"]
    errors = G.codex_errors(
        valid_folder(tmp_path),
        {**manifest(), "interface": {**manifest()["interface"], "defaultPrompt": prompts}},
    )
    assert errors == [f"{G.LAUNCHER}: interface.defaultPrompt has more than 3 prompts"]


def test_rejects_long_prompt(tmp_path: Path) -> None:
    iface = {**manifest()["interface"], "defaultPrompt": ["x" * 129]}
    errors = G.codex_errors(valid_folder(tmp_path), {**manifest(), "interface": iface})
    assert len(errors) == 1 and "too long" in errors[0]
