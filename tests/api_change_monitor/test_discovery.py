"""Tests for how api-change-monitor finds the APIs production code calls."""

from pathlib import Path

import pytest

from importlib import import_module

from dlt._workspace.deployment.agent.manifest import load_agent_module

from tests.utils import REPO_ROOT

agent = load_agent_module(
    str(REPO_ROOT / "workbench/dlthub-platform/dlthub/agents/api-change-monitor")
)
discovery = agent.discovery
registry = import_module(f"{agent.__package__}.registry")


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    files = {
        "__deployment__.py": (
            "from pipelines.billing import load\nfrom pipelines import code\n"
            '__all__ = ["load", "code"]\n'
        ),
        "pipelines/__init__.py": "",
        "pipelines/billing.py": (
            "from .common import ACME_URL\n"
            'client = {"base_url": "https://api.stripe.com/v1/"}\n'
            '"""See https://docs.stripe.com/api for the url of each endpoint."""\n'
        ),
        "pipelines/common.py": 'ACME_URL = "https://api.acme-billing.io/v2/"\n',
        "pipelines/code.py": 'client = {"base_url": "https://api.github.com/"}\n',
        # not deployed: its API is not watched
        "scratch/shop.py": 'base_url = "https://x.myshopify.com/admin/api/2024-01/"\n',
        ".dlt/secrets.toml": 'hubspot_url = "https://api.hubapi.com"\n',
        ".venv/lib/stripe.py": 'base_url = "https://api.stripe.com"\n',
        "models/customers.sql": "select `id`, email from stripe.customers\n",
    }
    for name, text in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text)
    return tmp_path


def test_production_code_is_what_the_deployment_reaches(workspace: Path) -> None:
    files = {p.relative_to(workspace).as_posix() for p in discovery.production_files(workspace)}

    assert files == {
        "__deployment__.py",
        "pipelines/__init__.py",
        "pipelines/billing.py",
        "pipelines/common.py",
        "pipelines/code.py",
    }


def test_apis_are_found_by_host_and_matched_to_the_registry(workspace: Path) -> None:
    apis = {api.name: api for api in discovery.discover(workspace)}

    assert set(apis) == {"api.acme-billing.io", "github", "stripe"}
    assert apis["stripe"].known is registry.KNOWN_APIS["stripe"]
    assert apis["api.acme-billing.io"].known is None
    assert apis["stripe"].evidence == ["pipelines/billing.py line 2"]


def test_without_a_deployment_the_whole_workspace_is_scanned(workspace: Path) -> None:
    (workspace / "__deployment__.py").unlink()

    names = {api.name for api in discovery.discover(workspace)}

    assert "shopify" in names and "hubspot" not in names


def test_configured_apis_replace_discovery_and_keep_its_evidence(workspace: Path) -> None:
    found = discovery.discover(workspace)

    apis = discovery.configure("Stripe, acme=https://acme.dev/feed.xml, netsuite", found)

    assert [(a.name, a.origin, a.url) for a in apis] == [
        ("stripe", "configured", ""),
        ("acme", "configured", "https://acme.dev/feed.xml"),
        ("netsuite", "configured", ""),
    ]
    assert apis[0].evidence and apis[2].known is registry.KNOWN_APIS["netsuite"]
    assert agent.sources_of(apis[1]) == ["https://acme.dev/feed.xml"]


def test_usage_map_skips_secrets_and_environments(workspace: Path) -> None:
    apis = discovery.discover(workspace)

    text = discovery.render_usage(workspace, apis)

    assert "pipelines/billing.py:2:" in text
    assert "models/customers.sql:1: select 'id', email from stripe.customers" in text
    assert "hubapi" not in text and ".venv" not in text
    assert "- `models/customers.sql`" in text.split("### Downstream model files")[1]


def test_resource_paths_and_pinned_versions(workspace: Path) -> None:
    (workspace / "pipelines" / "code.py").write_text(
        'VERSION = "2022-11-28"\n'
        'client = {"base_url": "https://api.github.com/", "headers": {"X-GitHub-Api-Version": VERSION}}\n'
        'resources = [{"endpoint": {"path": "rate_limit"}}, {"endpoint": {"path": "repos/a/b"}}]\n'
        'from pipelines.common import ACME_URL\n'
    )
    (workspace / "pipelines" / "billing.py").write_text(
        'client = {"base_url": "https://api.stripe.com/v1/", "headers": {"Stripe-Version": "2026-09-30.endive"}}\n'
    )
    github = next(a for a in discovery.discover(workspace) if a.name == "github")

    paths = [p for p, where in discovery.resource_paths(workspace) if "code.py" in where]
    pins = discovery.pinned_versions(workspace, github)

    assert "rate_limit" in paths and "repos/a/b" in paths
    assert not any(p.endswith(".py") for p in paths)
    assert pins == ['`VERSION = "2022-11-28"` (pipelines/code.py line 1)']
    stripe = next(a for a in discovery.discover(workspace) if a.name == "stripe")
    assert len(discovery.pinned_versions(workspace, stripe)) == 1


def test_every_way_of_calling_an_api_in_code_is_found(tmp_path: Path) -> None:
    files = {
        "__deployment__.py": "from pipelines.calls import a, b, c\n__all__ = ['a', 'b', 'c']\n",
        "pipelines/__init__.py": "",
        "pipelines/calls.py": (
            '"""Calls https://docs.notcalled.com, a link in a docstring."""\n'
            "import requests\n"
            "from dlt.sources.helpers.rest_client import RESTClient\n"
            "# https://comment.example.org is a comment\n"
            "def a(sub):\n"
            '    return RESTClient(base_url=f"https://{sub}.acme-desk.com/api/v2")\n'
            "def b():\n"
            '    return requests.get("https://api.acme.io/v1/items")\n'
            "def c():\n"
            '    return requests.Session().post("https://rest.example-erp.com/v2/orders")\n'
        ),
    }
    for name, text in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text)

    apis = {api.name: api for api in discovery.discover(tmp_path)}

    # templated host, a bare request and a session call; docstring and comment links stay out
    assert set(apis) == {"acme-desk.com", "api.acme.io", "rest.example-erp.com"}
    assert apis["acme-desk.com"].hosts == {"*.acme-desk.com"}
    assert apis["api.acme.io"].evidence == ["pipelines/calls.py line 8"]


def test_downstream_models_are_found_by_the_dataset_a_pipeline_loads(tmp_path: Path) -> None:
    files = {
        "__deployment__.py": "from pipelines import pay, gh\n__all__ = ['pay', 'gh']\n",
        "pipelines/__init__.py": "",
        "pipelines/pay.py": (
            'client = {"base_url": "https://api.stripe.com/v1/"}\n'
            'pipeline = dlt.pipeline(pipeline_name="pay", dataset_name="stripe_data")\n'
        ),
        "pipelines/gh.py": (
            'client = {"base_url": "https://api.github.com/"}\n'
            'pipeline = dlt.pipeline(pipeline_name="gh", dataset_name="github_data")\n'
        ),
        "transformations/repos.sql": "select id from github_data.repo\n",
    }
    for name, text in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text)
    apis = {api.name: api for api in discovery.discover(tmp_path)}
    models = discovery.model_lines(tmp_path)

    assert discovery.datasets(tmp_path, apis["stripe"]) == ["stripe_data"]
    assert discovery.downstream(tmp_path, apis["github"], models) == ["transformations/repos.sql"]
    # stripe's tables are read by models somewhere else
    assert discovery.downstream(tmp_path, apis["stripe"], models) == []
    assert agent._downstream_line(tmp_path, apis["stripe"]) == (
        "downstream models: none in this workspace;"
        " possible downstream models of dataset `stripe_data` are not visible here"
    )
