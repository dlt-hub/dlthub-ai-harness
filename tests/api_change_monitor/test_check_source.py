"""Tests for the add-api-change-source skill's helper, run against the agent's reader."""

import importlib.util
import shutil
from pathlib import Path

import pytest

from tests.utils import REPO_ROOT

AGENT = REPO_ROOT / "workbench/dlthub-platform/dlthub/agents/api-change-monitor"
HELPER = REPO_ROOT / "workbench/dlthub-platform/skills/add-api-change-source/check_source.py"

FEED = """<rss version="2.0"><channel>
<item><title>Removed `legacy_id`</title><link>https://a/1</link>
<pubDate>Fri, 02 Oct 2026 14:00:00 +0000</pubDate><category>REST API</category>
<description>x</description></item>
<item><title>New theme editor</title><link>https://a/2</link>
<pubDate>Fri, 02 Oct 2026 14:00:00 +0000</pubDate><category>Themes</category>
<description>x</description></item>
</channel></rss>"""


@pytest.fixture
def helper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The helper, run from a workspace with the agent installed where a toolkit puts it."""
    shutil.copytree(AGENT, tmp_path / ".claude/dlthub/agents/dlthub-platform/api-change-monitor")
    monkeypatch.chdir(tmp_path)
    spec = importlib.util.spec_from_file_location("check_source", HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fetch_returning(helper, monkeypatch, body: str):
    agent = helper.load_agent()
    monkeypatch.setattr(helper.module(agent, "release_notes"), "fetch_text", lambda url: body)
    return agent


def test_a_feed_shows_its_categories_and_dated_notes(helper, monkeypatch, capsys) -> None:
    agent = fetch_returning(helper, monkeypatch, FEED)

    code = helper.check(agent, "acme", "https://a/feed", ["REST API"], "")

    out = capsys.readouterr().out
    assert code == 0
    assert "feed categories: REST API (1), Themes (1)" in out
    assert "notes: 1, dated: 1" in out and "Removed `legacy_id`" in out


def test_a_page_the_agent_cannot_date_fails(helper, monkeypatch, capsys) -> None:
    agent = fetch_returning(helper, monkeypatch, "<html><body>Pricing and plans</body></html>")

    assert helper.check(agent, "acme", "https://a/pricing", [], "") == 1
    assert "cannot date this page" in capsys.readouterr().out


def test_an_undated_release_page_passes_with_a_version_pattern(helper, monkeypatch) -> None:
    page = "<html><body><h1>Acme 2026.2 Release</h1><p>Removed the v1 search.</p></body></html>"
    agent = fetch_returning(helper, monkeypatch, page)

    assert helper.check(agent, "acme", "https://a/release", [], "") == 1
    assert helper.check(agent, "acme", "https://a/release", [], r"Acme (\d{4}\.\d) Release") == 0


def test_without_the_agent_installed_it_says_so(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    spec = importlib.util.spec_from_file_location("check_source", HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    with pytest.raises(SystemExit, match="not installed here"):
        module.load_agent()
