"""Tests for finding the release notes of an API no source is known for."""

from datetime import date
from importlib import import_module

import pytest

from dlt._workspace.deployment.agent.manifest import load_agent_module

from tests.utils import REPO_ROOT

agent = load_agent_module(
    str(REPO_ROOT / "workbench/dlthub-platform/dlthub/agents/api-change-monitor")
)
guess = import_module(f"{agent.__package__}.guess")

TODAY = date(2026, 10, 27)
CHANGELOG = "# Changelog\n\n## 2026-10-01\n\n* Removed the `legacy_id` field.\n"


@pytest.mark.parametrize(
    "host, domain",
    [
        ("api.acme.io", "acme.io"),
        ("*.acme-desk.com", "acme-desk.com"),
        ("rest.example-erp.com", "example-erp.com"),
        ("apiv2.acme.io", "acme.io"),
        ("acme.io", "acme.io"),
        ("data.acme.co.uk", "data.acme.co.uk"),
    ],
)
def test_the_provider_domain_comes_from_the_api_host(host: str, domain: str) -> None:
    assert guess.provider_domain(host) == domain


def test_the_first_candidate_that_reads_as_release_notes_wins() -> None:
    pages = {
        "https://developers.acme.io/changelog": CHANGELOG,
        "https://docs.acme.io/changelog": CHANGELOG,
        # a page with no date is no changelog, whatever its path
        "https://acme.io/changelog": "<html><body>Pricing</body></html>",
    }

    def fetch(url: str) -> str:
        if url not in pages:
            raise ConnectionError(url)
        return pages[url]

    assert guess.find_source("acme", ["api.acme.io"], TODAY, fetch) == "https://developers.acme.io/changelog"
    assert guess.find_source("acme", ["api.other.io"], TODAY, fetch) is None


def test_a_guessed_source_is_marked_for_the_model_and_the_report() -> None:
    api = agent.discovery.FoundApi("api.acme.io", None, hosts={"api.acme.io"})
    api.url, api.guessed = "https://developers.acme.io/changelog", True

    text = agent.render_apis([api], {})

    assert "(found at a common changelog location: check it is the official one)" in text
