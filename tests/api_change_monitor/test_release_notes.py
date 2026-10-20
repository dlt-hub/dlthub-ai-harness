"""Tests for the api-change-monitor release note parsing and windowing."""

from datetime import date
from typing import List

import pytest

from importlib import import_module

from dlt._workspace.deployment.agent.manifest import load_agent_module

from tests.utils import REPO_ROOT

AGENT_DIR = REPO_ROOT / "workbench/dlthub-platform/dlthub/agents/api-change-monitor"
agent = load_agent_module(str(AGENT_DIR))
release_notes = agent.release_notes
registry = import_module(f"{agent.__package__}.registry").KNOWN_APIS

SINCE = date(2026, 10, 1)
TODAY = date(2026, 10, 19)

RSS = """<?xml version="1.0"?><rss version="2.0"><channel>
<item><title>`automaticDiscounts` query is removed in API version 2027-01</title>
<link>https://shopify.dev/changelog/automatic-discounts-removed</link>
<pubDate>Fri, 02 Oct 2026 14:00:00 +0000</pubDate>
<category>Breaking API Change</category><category>Admin GraphQL API</category>
<description><![CDATA[<p>Use <code>discountNodes</code> instead.</p><ul><li><p>one</p></li></ul>]]></description>
</item>
<item><title>Hydrogen release</title><link>https://shopify.dev/changelog/hydrogen</link>
<pubDate>Fri, 02 Oct 2026 14:00:00 +0000</pubDate>
<category>API</category><category>Hydrogen</category><description>x</description></item>
<item><title>Old admin change</title><link>https://shopify.dev/changelog/old</link>
<pubDate>Mon, 01 Sep 2026 14:00:00 +0000</pubDate>
<category>Admin REST API</category><description>x</description></item>
</channel></rss>"""

ATOM = """<feed xmlns="http://www.w3.org/2005/Atom"><title>Acme</title>
<entry><title>Orders endpoint gains updated_since</title>
<link href="https://acme.dev/changelog/orders"/><updated>2026-10-05T10:00:00Z</updated>
<content type="html">&lt;p&gt;Filter with &lt;code&gt;updated_since&lt;/code&gt;.&lt;/p&gt;</content></entry>
<entry><title>Old</title><link href="https://acme.dev/old"/><updated>2026-08-05T10:00:00Z</updated>
<content>x</content></entry></feed>"""

DATED_SECTIONS = """---
updatedAt: 2026-10-01
---
# SP-API Release Notes

## October 14, 2026

#### API changes

##### [Orders API v2026-01-01](https://developer-docs.amazon/sp-api/reference/orders)

* Added the `lastUpdatedAfter` filter to `searchOrders`.

##### [Reports API v2021-06-30](https://developer-docs.amazon/sp-api/reference/reports)

* Added a report type.

## September 30, 2026

##### Feeds API

* Too old for the window.
"""

STRIPE = """# Changelog

# Endive
## 2026-10-07.endive

| Title | Breaking change? |
| --- | --- |
| [Removes `legacy_field`](https://docs.stripe.com/x.md) | Breaking |

## 2026-08-26.dahlia

| Old | Non-breaking |
"""

DEPRECATIONS = """# SP-API Deprecation Schedule

## Catalog Items API

| Data product | Removed items | Deprecation date | Removal date |
| :--- | :--- | :--- | :--- |
| [Catalog Items API v0](https://x) | `listCatalogItems`<br/> `getCatalogItem` | October 5, 2026 | April 24, 2027 |
| Catalog Items API v0 | `listCatalogCategories` | May 21, 2025 | October 30, 2026 |
| Catalog Items API v0 | `old` | May 21, 2024 | March 1, 2025 |
"""

NETSUITE = """<html><head><title>NetSuite - SuiteTalk Web Services Integration</title></head>
<body><nav>menu</nav><p>JavaScript must be enabled to correctly display this content</p>
<div>NetSuite 2026.2 Release Notes</div>
<h2>Support for Bound Parameters</h2>
<p>Use <code>params</code> with SuiteQL.</p></body></html>"""


def titles(notes: List) -> List[str]:
    return [n.title for n in notes]


def test_rss_keeps_the_topics_inside_the_window() -> None:
    shopify = registry["shopify"]
    notes = release_notes.parse("shopify", "u", RSS, SINCE, TODAY, shopify.topics)

    assert titles(notes) == ["`automaticDiscounts` query is removed in API version 2027-01"]
    assert notes[0].published == date(2026, 10, 2)
    assert "`discountNodes`" in notes[0].text and "- one" in notes[0].text


def test_rss_without_topics_reads_every_item() -> None:
    notes = release_notes.parse("x", "u", RSS, SINCE, TODAY)

    assert len(notes) == 2


def test_atom_entries_are_read() -> None:
    notes = release_notes.parse("acme", "u", ATOM, SINCE, TODAY)

    assert titles(notes) == ["Orders endpoint gains updated_since"]
    assert notes[0].url == "https://acme.dev/changelog/orders"
    assert "`updated_since`" in notes[0].text


def test_dated_sections_split_into_their_subsections() -> None:
    url = "https://d.com/release-notes.md"
    notes = release_notes.parse("amazon-sp-api", url, DATED_SECTIONS, SINCE, TODAY)

    assert titles(notes) == ["Orders API v2026-01-01", "Reports API v2021-06-30"]
    assert notes[0].url == "https://d.com/release-notes#october-14-2026"
    assert notes[0].labels == ["October 14, 2026"]
    assert "`lastUpdatedAfter`" in notes[0].text


def test_iso_dated_sections_keep_their_table() -> None:
    notes = release_notes.parse("stripe", "https://s/changelog.md", STRIPE, SINCE, TODAY)

    assert titles(notes) == ["2026-10-07.endive"]
    assert "`legacy_field`" in notes[0].text and "Old" not in notes[0].text


def test_a_page_without_dated_headings_reads_its_dated_rows() -> None:
    notes = release_notes.parse("amazon-sp-api", "u", DEPRECATIONS, SINCE, TODAY)

    assert len(notes) == 2
    announced, imminent = notes
    assert "`listCatalogItems`, `getCatalogItem`" in announced.text
    assert "imminent" not in announced.labels
    assert imminent.labels == ["Catalog Items API", "imminent"]


def test_an_undated_page_is_one_note_with_its_version() -> None:
    netsuite = registry["netsuite"]
    notes = release_notes.parse("netsuite", "u", NETSUITE, SINCE, TODAY, (), netsuite.version)

    assert titles(notes) == ["NetSuite - SuiteTalk Web Services Integration (2026.2)"]
    assert notes[0].labels == ["version 2026.2"]
    assert "## Support for Bound Parameters" in notes[0].text
    assert "menu" not in notes[0].text and "JavaScript" not in notes[0].text


def test_a_reviewed_version_is_skipped_and_a_down_source_reported() -> None:
    found = agent.discovery.FoundApi("netsuite", registry["netsuite"])
    acme = agent.discovery.FoundApi("acme", None, origin="configured", url="https://acme.dev/x")

    def fetch(url: str) -> str:
        if "acme" in url:
            raise ConnectionError("down")
        return NETSUITE

    notes, problems = agent.read_notes([found, acme], SINCE, TODAY, {"netsuite": "2026.2"}, fetch)
    assert notes == [] and list(problems) == ["acme"] and "down" in problems["acme"][0]

    notes, _ = agent.read_notes([found], SINCE, TODAY, {"netsuite": "2026.1"}, fetch)
    assert len(notes) == 2


def test_render_lists_past_the_window_by_title(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(release_notes, "WINDOW_CHARS", 1_000)
    Note = release_notes.Note
    notes = [Note("busy", f"note {i}", f"https://b/{i}", SINCE, [], "x" * 400) for i in range(5)]
    notes.append(Note("quiet", "only one", "https://q", SINCE, [], "## Head\nbody"))

    text = release_notes.render(notes, {"down": ["u: offline"]}, ["busy", "quiet", "down"], SINCE)

    assert "notes past the window size" in text and "#### note 4" in text
    # the quiet API keeps its text, with the heading inside it flattened
    assert "Head\nbody" in text and "## Head" not in text
    assert "Not read: u: offline" in text


def test_since_falls_back_from_input_to_interval_to_a_week() -> None:
    interval = {
        "interval_start": "2026-10-12T07:00:00+00:00",
        "interval_end": "2026-10-19T07:00:00+00:00",
    }
    point = {"interval_start": "2026-10-19T07:00:00", "interval_end": "2026-10-19T07:00:00"}

    assert agent.resolve_since({"since": "2026-10-03"}, TODAY) == date(2026, 10, 3)
    assert agent.resolve_since({"run_context": interval}, TODAY) == date(2026, 10, 12)
    assert agent.resolve_since({"run_context": point}, TODAY) == date(2026, 10, 12)
    assert agent.reviewed_versions("NetSuite=2026.2, bad") == {"netsuite": "2026.2"}


def test_a_long_section_of_bullets_splits_into_one_note_per_bullet() -> None:
    item = "* **Remove deprecated `{0}` property**\n  <details><summary>Affected</summary>\n{1}\n"
    body = "".join(item.format(f"field_{i}", "  * `GET /x`\n" * 60) for i in range(3))
    page = f"# Breaking changes\n\n## Version 2026-10-10\n\n{body}"

    notes = release_notes.parse("github", "https://d?p=x", page, SINCE, TODAY)

    assert titles(notes) == [f"Remove deprecated `field_{i}` property" for i in range(3)]
    assert notes[0].labels == ["Version 2026-10-10"] and notes[0].url == "https://d?p=x"
    assert "<details>" not in notes[0].text and "field_1" not in notes[0].text


@pytest.mark.parametrize(
    "template, path, matches",
    [
        ("/repos/{owner}/{repo}/contents/{path}", "repos/dlt-hub/dlt/contents/", True),
        ("/repos/{owner}/{repo}", "repos/dlt-hub/dlt", True),
        ("/repos/{owner}/{repo}", "repos/dlt-hub/dlt/issues", False),
        ("/rate_limit", "rate_limit", True),
        ("/v1/customers/{id}", "customers", True),
        ("/v1/customers", "/v1/customers/{resources.x.id}", False),
        ("/repos/{owner}/{repo}", "rate_limit", False),
        ("/orgs/{org}/teams", "repos/a/b", False),
        # a placeholder in workspace code stands for a parameter, never a literal segment
        ("/user/migrations/{migration_id}", "{email}/token", False),
        (
            "/orgs/{org}/attestations/{subject_digest}",
            "customers/{CUSTOMER_ID}/googleAds:searchStream",
            False,
        ),
        ("/repos/{owner}/{repo}/issues/{issue_number}", "repos/a/b/issues/{resources.x.id}", True),
        ("/rest/api/3/search/jql", "search/jql", True),
    ],
)
def test_endpoint_templates_match_the_paths_a_resource_calls(
    template: str, path: str, matches: bool
) -> None:
    assert release_notes.path_matches(template, path) is matches


def test_endpoints_fields_and_version_come_out_of_a_note() -> None:
    Note = release_notes.Note
    text = 'Use `resources.core`.\n  * `GET /rate_limit`\n  * `POST /orgs/{org}/teams`\nThe "assignee" field.'
    note = Note("github", "Remove `rate` from rate limit", "u", SINCE, ["Version 2026-03-10"], text)

    assert release_notes.endpoints(text) == ["/rate_limit", "/orgs/{org}/teams"]
    # plain words like `rate` and "assignee" match everywhere, so only shaped names count
    assert release_notes.fields(f"{note.title}\n{text}") == ["resources.core", "resources__core"]
    assert release_notes.note_version(note) == "2026-03-10"
    assert release_notes.note_version(Note("s", "x", "u", SINCE, ["API", "2026-10"])) == "2026-10"
    assert release_notes.note_version(Note("h", "Field removed", "u", SINCE, [])) == ""
    assert release_notes.fields("`customerEmail`") == ["customerEmail", "customer_email"]


def test_notes_are_linked_to_resource_calls_and_model_lines() -> None:
    Note = release_notes.Note
    note = Note("github", "Remove `use_squash_pr_title_as_default`", "u", SINCE, [],
                "* `GET /repos/{owner}/{repo}`")
    paths = [("repos/dlt-hub/dlt", "p.py line 21"), ("rate_limit", "p.py line 35")]
    lines = [("m.sql line 2", "select use_squash_pr_title_as_default from repo")]

    agent.link_calls([note], paths)
    agent.link_models([note], lines)

    assert note.calls == ["`/repos/{owner}/{repo}` as `repos/dlt-hub/dlt` (p.py line 21)"]
    assert note.models == ["`use_squash_pr_title_as_default` in m.sql line 2"]
    head = release_notes._head(note)
    assert "- called by this workspace:\n  - `/repos" in head
    assert "- read by downstream models:\n  - `use_squash" in head


@pytest.mark.parametrize(
    "text, day",
    [
        ("## 16 October 2026", date(2026, 10, 16)),
        ("Sep 14, 2026 | Deprecated", date(2026, 9, 14)),
        ("Effective from: Aug 1st, 2026", date(2026, 8, 1)),
        ("Sept. 3 2026", date(2026, 9, 3)),
        ("released 2026-10-05T10:00Z", date(2026, 10, 5)),
        ("On upgrade to v24 in June", None),
    ],
)
def test_dates_in_the_formats_changelogs_use(text: str, day: object) -> None:
    assert release_notes.find_date(text) == day


def test_an_html_table_reads_as_dated_rows() -> None:
    page = (
        "<html><title>Changelog</title><body><table><tr><th>Date</th><th>Subject</th></tr>"
        "<tr><td>Oct 14, 2026</td><td><p>Deprecated</p><p>Templating | API</p></td></tr>"
        "<tr><td>Jan 2, 2025</td><td>Old</td></tr></table></body></html>"
    )

    notes = release_notes.parse("zendesk", "u", page, SINCE, TODAY)

    assert [n.published for n in notes] == [date(2026, 10, 14)]
    assert "Deprecated Templating / API" in notes[0].text


def test_a_page_without_structure_is_cut_into_dated_passages() -> None:
    lines = ["Changelog", "DEPRECATED", "Effective from:", "Aug 1st, 2026",
             "Reminder: Deprecated API v1 endpoints are now out of support",
             "Announced: July 29, 2026"] + [f"filler {i}" for i in range(20)] + [
             "ADDED", "Announced: October 9, 2026", "Introducing Projects API v2 filter"]

    notes = release_notes.parse_page("pipedrive", "u", "\n".join(lines), SINCE, TODAY)

    assert [n.title for n in notes] == ["Introducing Projects API v2 filter"]
    notes = release_notes.parse_page("pipedrive", "u", "\n".join(lines), date(2026, 7, 1), TODAY)
    assert notes[0].title == "Reminder: Deprecated API v1 endpoints are now out of support"
    assert notes[0].published == date(2026, 8, 1) and len(notes) == 2
    # read from the beginning of time, a passage still keeps the date of its own entry
    every = release_notes.parse_page("pipedrive", "u", "\n".join(lines), date.min, TODAY)
    assert [n.published for n in every] == [date(2026, 8, 1), date(2026, 10, 9)]


def test_a_long_page_with_no_date_is_flagged_not_parsed() -> None:
    notes = release_notes.parse_page("x", "u", "# Policy\n" + "word " * 3000, SINCE, TODAY)

    assert notes[0].labels == ["not dated", "not parsed"]


def test_triage_rules_out_only_notes_whose_names_all_missed() -> None:
    Note = release_notes.Note
    called = Note("a", "Remove `x`", "u", SINCE, [], "", calls=["`/x` as `x` (p line 1)"])
    missed = Note("a", "Remove `unused_field`", "u", SINCE, [], "* `GET /other`")
    pinned = Note("a", "API v1 endpoints are out of support", "u", SINCE, [], "`GET /deals`")
    unnamed = Note("a", "API tokens end of life", "u", SINCE, [], "Tokens stop working.")
    stray = Note("a", "Creator searches rejected", "u", SINCE, [], "Raises `UnsupportedOperation`.")
    fields_missed = Note("a", "Fields", "u", SINCE, [], "`a_b`, `c_d` and `e_f` are removed.")
    imminent = Note("a", "Remove `y`", "u", SINCE, ["imminent"], "")

    notes = [called, missed, pinned, unnamed, imminent, stray, fields_missed]
    kept, ruled_out = agent.triage(notes, {"a": ["v1"]})

    assert ruled_out == [missed, fields_missed]
    assert pinned.pinned == ["v1"] and "- names the pinned version: `v1`" in release_notes._head(pinned)
    assert kept == [called, pinned, unnamed, imminent, stray]
    assert "Remove `unused_field`" in agent.render_ruled_out(ruled_out, ["a"])
