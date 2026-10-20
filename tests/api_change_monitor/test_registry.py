"""Tests for the workspace's own release note sources laid over the built-in ones."""

from importlib import import_module
from pathlib import Path

from dlt._workspace.deployment.agent.manifest import load_agent_module

from tests.utils import REPO_ROOT

agent = load_agent_module(
    str(REPO_ROOT / "workbench/dlthub-platform/dlthub/agents/api-change-monitor")
)
registry = import_module(f"{agent.__package__}.registry")

CONFIG = """
[runtime]
log_level = "WARNING"

[api_change_monitor.sources.acme]
hosts = ["api.acme.io", "*.acme-desk.com"]
urls = ["https://developers.acme.io/page/changelog"]
topics = ["REST API"]
modules = ["acme_sdk"]

[api_change_monitor.sources.github]
hosts = ["api.github.com"]
urls = ["https://github.example/our-mirror/changelog.md"]

[api_change_monitor.sources.broken]
hosts = ["api.broken.io"]
urls = []
version = "(unclosed"
"""


def workspace(tmp_path: Path, config: str = CONFIG) -> Path:
    (tmp_path / ".dlt").mkdir()
    (tmp_path / ".dlt" / "config.toml").write_text(config)
    return tmp_path


def test_workspace_entries_add_to_and_replace_the_built_in_ones(tmp_path: Path) -> None:
    apis = registry.load(workspace(tmp_path))

    acme = apis["acme"]
    assert acme.workspace and acme.sources == ["https://developers.acme.io/page/changelog"]
    assert acme.topics == ["REST API"] and acme.version is None
    assert apis["github"].sources == ["https://github.example/our-mirror/changelog.md"]
    # an entry with no url cannot be read, so it is left out rather than break the run
    assert "broken" not in apis
    assert apis["stripe"] is registry.KNOWN_APIS["stripe"]


def test_hosts_and_modules_match_a_workspace_entry(tmp_path: Path) -> None:
    apis = registry.load(workspace(tmp_path))

    assert registry.match_host("api.acme.io", apis).name == "acme"
    assert registry.match_host("eu.acme-desk.com", apis).name == "acme"
    assert registry.match_host("notacme.io", apis) is None
    assert registry.match_module("acme_sdk.client", apis).name == "acme"


def test_no_config_or_a_broken_one_leaves_the_built_ins(tmp_path: Path) -> None:
    assert registry.load(tmp_path) == registry.KNOWN_APIS
    assert registry.load(workspace(tmp_path, "not = [toml")) == registry.KNOWN_APIS


def test_discovery_names_an_api_by_its_workspace_entry(tmp_path: Path) -> None:
    root = workspace(tmp_path)
    (root / "pipelines").mkdir()
    (root / "pipelines" / "acme.py").write_text('client = {"base_url": "https://api.acme.io/v1/"}\n')

    apis = agent.discovery.discover(root)

    assert [api.name for api in apis] == ["acme"]
    assert agent.sources_of(apis[0]) == ["https://developers.acme.io/page/changelog"]
    assert agent._origin(apis[0]) == "configured"
    assert "(the workspace's own source)" in agent.render_apis(apis, {})
