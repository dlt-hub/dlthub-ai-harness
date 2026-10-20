"""Tests for the first-run lookback, coverage gaps, separate dates and credential masking."""

from datetime import date
from importlib import import_module
from pathlib import Path

import pytest

from dlt._workspace.deployment.agent.manifest import load_agent_module

from tests.utils import REPO_ROOT

agent = load_agent_module(
    str(REPO_ROOT / "workbench/dlthub-platform/dlthub/agents/api-change-monitor")
)
report = agent.report
redact = import_module(f"{agent.__package__}.redact").redact

TODAY = date(2026, 10, 27)
# fake keys built at run time, so no secret scanner sees a key in the source
FAKE_STRIPE = "sk_" + "live_" + "51HxYzAbCdEfGh"
FAKE_GITHUB = "gh" + "p_" + "0123456789abcdefghijABCDEFGHIJ"
SINCE = date(2026, 9, 27)

FEED = """<rss version="2.0"><channel>
<item><title>Reminder: Deprecated API v1 endpoints are now out of support</title>
<link>https://p/v1</link><pubDate>Wed, 29 Jul 2026 10:00:00 GMT</pubDate><description>x</description></item>
<item><title>Introducing Projects API v2 next to v1</title>
<link>https://p/projects</link><pubDate>Thu, 21 May 2026 10:00:00 GMT</pubDate><description>x</description></item>
<item><title>API v1 deprecated</title>
<link>https://p/old</link><pubDate>Mon, 01 Sep 2025 10:00:00 GMT</pubDate><description>x</description></item>
</channel></rss>"""


def pipedrive() -> object:
    return agent.discovery.FoundApi("pipedrive", None, origin="configured", url="https://p/rss")


def test_a_first_run_looks_back_for_endings_of_the_pinned_version() -> None:
    notes, _ = agent.read_notes([pipedrive()], SINCE, TODAY, {}, lambda url: FEED, {"pipedrive": ["v1"]})

    # an addition naming v1 stays out, and so does an ending older than the lookback
    assert [n.title for n in notes] == ["Reminder: Deprecated API v1 endpoints are now out of support"]
    assert notes[0].labels == ["earlier note on pinned v1"]


def test_a_later_run_leaves_old_notes_to_the_earlier_report() -> None:
    notes, _ = agent.read_notes([pipedrive()], SINCE, TODAY, {}, lambda url: FEED)

    assert notes == []


def test_coverage_records_the_newest_entry_and_undated_sources() -> None:
    coverage = agent.Coverage({}, [])
    page = agent.discovery.FoundApi("policy", None, origin="configured", url="https://s/eol")
    fetch = {"https://p/rss": FEED, "https://s/eol": "# Policy\nVersions 31 to 40 retire."}.get

    agent.read_notes([pipedrive(), page], SINCE, TODAY, {}, fetch, coverage=coverage)

    assert coverage.latest == {"pipedrive": date(2026, 7, 29)}
    assert coverage.undated == ["policy"]


def test_the_scope_names_coverage_gaps() -> None:
    results = [
        report.ApiResult("jira", "succeeded", kept=2, latest="2026-10-16"),
        report.ApiResult("github", "skipped", ruled_out=3, latest="2026-03-10 (231 days ago)"),
        report.ApiResult("salesforce", "skipped", latest="undated"),
        report.ApiResult("acme", "skipped", unread=True),
    ]

    summary = report.merge(results, "2026-09-27", "2026-10-27")["summary"]

    assert "- Newest release note seen: `jira` 2026-10-16, `github` 2026-03-10 (231 days ago)." in summary
    assert (
        "- Coverage gaps: `salesforce` publishes no dates; `github` newest entry is 231 days old;"
        " `acme` release notes could not be read. Finding nothing there is no proof nothing changed."
    ) in summary


@pytest.mark.parametrize(
    "change, lands",
    [
        ({"impact": "action_required", "effective_date": "2027-06-01", "removal_date": "2028-06-01"},
         "2027-06-01, removed 2028-06-01"),
        ({"impact": "action_required", "effective_date": "2026-12-04", "removal_date": "2026-12-04"},
         "2026-12-04"),
        ({"impact": "on_upgrade", "effective_date": "", "removal_date": ""}, "on upgrade"),
        ({"impact": "action_required", "effective_date": "", "removal_date": ""}, "now"),
    ],
)
def test_the_table_keeps_the_dates_apart(change: dict, lands: str) -> None:
    assert report._lands(change) == lands


@pytest.mark.parametrize(
    "line, masked",
    [
        (f'api_key = "{FAKE_STRIPE}"', 'api_key = "***"'),
        ('"auth": {"type": "bearer", "token": "abcdef123456"}', '"auth": {"type": "bearer", "token": "***"}'),
        ('headers={"Authorization": "Bearer abcdefghijklmnop"}', 'headers={"Authorization": "Bearer ***"}'),
        ('KEY = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8"', 'KEY = "***"'),
        (f'client = "{FAKE_GITHUB}"', 'client = "***"'),
    ],
)
def test_credential_literals_are_masked(line: str, masked: str) -> None:
    assert redact(line) == masked


@pytest.mark.parametrize(
    "line",
    [
        "token: str = dlt.secrets.value",
        '"password": api_token',
        'GITHUB_API_VERSION = "2022-11-28"',
        "select customer__conversion_tracking_setting__enhanced_conversions_for_leads_enabled",
        "analytics_salesAndTraffic_2023_11_15",
        '"path": "crm-pipelines/v1/pipelines/deals"',
        "Migrate from API token basic authentication to OAuth2 access tokens.",
        "Send a Bearer authorization header.",
    ],
)
def test_code_that_holds_no_credential_is_left_alone(line: str) -> None:
    assert redact(line) == line


def test_a_hard_coded_key_never_reaches_the_prompt_or_the_report(tmp_path: Path) -> None:
    (tmp_path / "pipelines").mkdir()
    (tmp_path / "pipelines" / "pay.py").write_text(
        f'client = {{"base_url": "https://api.stripe.com/v1/", "api_key": "{FAKE_STRIPE}"}}\n'
    )
    apis = agent.discovery.discover(tmp_path)

    usage = agent.discovery.render_usage(tmp_path, apis)
    finding = {
        "api": "stripe", "kind": "breaking", "impact": "action_required", "title": "t",
        "effective_date": "", "announced_date": "", "removal_date": "", "source_url": "u",
        "affected": ["pipelines/pay.py line 1"],
        "recommendation": f'In `pipelines/pay.py` line 1, keep api_key = "{FAKE_STRIPE}".',
    }
    merged = report.merge([report.ApiResult("stripe", "succeeded", output={"changes": [finding]})], "2026-10-01")
    tracked, _, _ = agent.tracking.track(merged["changes"], [], tmp_path, TODAY, [])

    assert all(FAKE_STRIPE not in str(text) for text in (usage, merged, tracked))
    assert tracked[0]["lines"][0]["text"].endswith('"api_key": "***"}')
    assert agent.tracking.still_open(tracked[0], tmp_path)
