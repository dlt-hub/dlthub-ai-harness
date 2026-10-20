"""Tests for carrying findings across runs until the code they name changes."""

from datetime import date
from pathlib import Path

import pytest

from dlt._workspace.deployment.agent.manifest import load_agent_module

from tests.utils import REPO_ROOT

agent = load_agent_module(
    str(REPO_ROOT / "workbench/dlthub-platform/dlthub/agents/api-change-monitor")
)
tracking, report = agent.tracking, agent.report

TODAY = date(2026, 10, 27)


def pipedrive_finding() -> dict:
    return {
        "api": "pipedrive", "kind": "deprecation", "impact": "action_required",
        "title": "Reminder: Deprecated API v1 endpoints are now out of support",
        "effective_date": "2026-08-01", "source_url": "u",
        "affected": ["pipelines/pipedrive.py line 2", "transformations/deals.sql line 1"],
        "recommendation": "Update base_url in `pipelines/pipedrive.py` line 2 to `/api/v2/`.",
    }


def workspace(tmp_path: Path, base_url: str = "https://api.pipedrive.com/v1/") -> Path:
    (tmp_path / "pipelines").mkdir(exist_ok=True)
    (tmp_path / "pipelines" / "pipedrive.py").write_text(f'"""Deals."""\nBASE = "{base_url}"\n')
    return tmp_path


def test_a_finding_is_fingerprinted_by_the_line_its_fix_changes(tmp_path: Path) -> None:
    root = workspace(tmp_path)

    lines = tracking.fingerprint(pipedrive_finding(), root)

    assert lines == [
        {"location": "pipelines/pipedrive.py line 2", "text": 'BASE = "https://api.pipedrive.com/v1/"'}
    ]


def test_an_earlier_finding_stays_open_until_its_line_changes(tmp_path: Path) -> None:
    root = workspace(tmp_path)
    first, _, _ = tracking.track([pipedrive_finding()], [], root, date(2026, 10, 20), [])
    assert first[0]["first_reported"] == "2026-10-20"

    # a week later the note is out of the window and the model reports nothing
    tracked, carried, resolved = tracking.track([], first, root, TODAY, [])
    assert [c["key"] for c in carried] == [first[0]["key"]] and resolved == []
    assert tracked == carried

    # the line moves a few rows down: still the same code, still open
    (root / "pipelines" / "pipedrive.py").write_text(
        '"""Deals."""\n\n\nBASE = "https://api.pipedrive.com/v1/"\n'
    )
    _, carried, resolved = tracking.track([], first, root, TODAY, [])
    assert len(carried) == 1 and resolved == []

    workspace(root, "https://api.pipedrive.com/api/v2/")
    tracked, carried, resolved = tracking.track([], first, root, TODAY, [])
    assert carried == [] and tracked == [] and len(resolved) == 1


def test_a_finding_reported_again_keeps_its_first_date(tmp_path: Path) -> None:
    root = workspace(tmp_path)
    first, _, _ = tracking.track([pipedrive_finding()], [], root, date(2026, 10, 20), [])
    reworded = {**pipedrive_finding(), "title": "Pipedrive v1 endpoints out of support"}

    tracked, carried, _ = tracking.track([reworded], first, root, TODAY, [])

    # the title changed but the line is the same, so it is the same finding
    assert carried == [] and len(tracked) == 1
    assert tracked[0]["first_reported"] == "2026-10-20"


def test_a_failed_run_keeps_its_findings_and_a_deleted_pipeline_resolves_them(
    tmp_path: Path,
) -> None:
    root = workspace(tmp_path)
    first, _, _ = tracking.track([pipedrive_finding()], [], root, date(2026, 10, 20), [])
    (root / "pipelines" / "pipedrive.py").unlink()

    _, carried, resolved = tracking.track([], first, root, TODAY, ["pipedrive"])
    assert len(carried) == 1 and resolved == []

    _, carried, resolved = tracking.track([], first, root, TODAY, [])
    assert carried == [] and len(resolved) == 1


def test_the_report_lists_carried_and_resolved_findings(tmp_path: Path) -> None:
    root = workspace(tmp_path)
    first, _, _ = tracking.track([pipedrive_finding()], [], root, date(2026, 10, 20), [])
    quiet = report.ApiResult("pipedrive", "skipped", ruled_out=3)

    tracked, carried, resolved = tracking.track([], first, root, TODAY, [])
    merged = report.merge([quiet], "2026-10-20", "2026-10-27", tracked, carried, resolved, "compared with run #4")

    summary = merged["summary"]
    # carried from the earlier report, so it is open but not new
    assert summary.startswith("**1 open finding: 1 act now, 0 new.**")
    assert (
        "| 2026-08-01 passed | pipedrive | Reminder: Deprecated API v1 endpoints are now out of support | act |"
    ) in summary
    assert merged["tracked"] == tracked and merged["requires_human"] is True

    workspace(root, "https://api.pipedrive.com/api/v2/")
    tracked, carried, resolved = tracking.track([], first, root, TODAY, [])
    merged = report.merge([quiet], "2026-10-20", "2026-10-27", tracked, carried, resolved, "compared with run #5")
    assert merged["summary"].startswith("**No open findings.** 1 resolved.")
    assert "**Resolved:** pipedrive: Reminder: Deprecated API v1" in merged["summary"]
    assert "(`pipedrive.py:2` changed)" in merged["summary"]
    assert merged["tracked"] == [] and merged["requires_human"] is False


def test_an_old_note_naming_a_deadline_ahead_comes_back(tmp_path: Path) -> None:
    Note = agent.release_notes.Note
    old = Note("hubspot", "Pipelines API V1 Sunset: December 4, 2026", "u", date(2026, 8, 14), [], "")

    assert agent.release_notes.upcoming(old, TODAY, agent.DEADLINE_AHEAD) == date(2026, 12, 4)
    assert agent.release_notes.upcoming(old, date(2026, 9, 1), agent.DEADLINE_AHEAD) is None


def test_read_notes_keeps_old_notes_only_when_they_name_a_deadline_ahead() -> None:
    feed = """<rss version="2.0"><channel>
<item><title>Pipelines API V1 Sunset: December 4, 2026</title><link>https://h/sunset</link>
<pubDate>Fri, 14 Aug 2026 14:37:13 GMT</pubDate><description>V1 stops.</description></item>
<item><title>Old rollup</title><link>https://h/rollup</link>
<pubDate>Fri, 14 Aug 2026 14:37:13 GMT</pubDate><description>Shipped in May 2026.</description></item>
</channel></rss>"""
    api = agent.discovery.FoundApi("hubspot", None, origin="configured", url="https://h/rss")

    notes, problems = agent.read_notes([api], date(2026, 10, 20), TODAY, {}, lambda url: feed)

    assert problems == {} and [n.title for n in notes] == ["Pipelines API V1 Sunset: December 4, 2026"]
    assert notes[0].labels == ["deadline 2026-12-04"]


def test_a_reworded_finding_on_another_line_of_the_same_file_is_the_same(tmp_path: Path) -> None:
    root = workspace(tmp_path)
    (root / "pipelines" / "pipedrive.py").write_text('"""Deals."""\nBASE = "v1"\nAUTH = "token"\n')
    tokens = {
        **pipedrive_finding(), "title": "Phased end-of-life for API token authentication",
        "effective_date": "2026-10-27", "recommendation": "Change `pipelines/pipedrive.py` line 2.",
    }
    first, _, _ = tracking.track([tokens], [], root, date(2026, 10, 20), [])
    reworded = {**tokens, "title": "API tokens deprecation", "recommendation": "Change `pipelines/pipedrive.py` line 3."}
    other = {**reworded, "title": "Field type change", "effective_date": "2026-08-06"}

    tracked, carried, _ = tracking.track([reworded, other], first, root, TODAY, [])

    assert carried == []
    assert [(t["title"], t["new"], t["first_reported"]) for t in tracked] == [
        ("API tokens deprecation", False, "2026-10-20"),
        ("Field type change", True, "2026-10-27"),
    ]


def test_a_finding_reported_again_without_a_date_keeps_the_earlier_one(tmp_path: Path) -> None:
    """Google Ads: run 1 read the v24 sunset in its lookback, run 2 saw no date."""
    root = workspace(tmp_path)
    dated = {**pipedrive_finding(), "impact": "on_upgrade", "effective_date": "2027-05-01",
             "removal_date": "", "announced_date": "2026-10-14"}
    first, _, _ = tracking.track([dated], [], root, date(2026, 10, 20), [])
    undated = {**dated, "effective_date": "", "removal_date": "2027-06-01", "announced_date": ""}

    tracked, _, _ = tracking.track([undated], first, root, TODAY, [])
    merged = report.merge(
        [report.ApiResult("pipedrive", "succeeded", output={"changes": [undated]})],
        "2026-10-20", "2026-10-27", tracked, [], [], "compared with run #1",
    )

    # a date the new run gives wins, an empty one keeps what the earlier run found
    assert {f: tracked[0][f] for f in tracking.DATE_FIELDS} == {
        "announced_date": "2026-10-14", "effective_date": "2027-05-01", "removal_date": "2027-06-01"
    }
    assert "| on upgrade, by 2027-05-01 | pipedrive |" in merged["summary"]
    assert "| upgrade |" in merged["summary"]


def test_older_reports_fill_dates_the_newest_report_lost(tmp_path: Path) -> None:
    """Google Ads: run 1 had the end date, run 2 dropped it, run 3 is compared with both."""
    root = workspace(tmp_path)
    dated = {**pipedrive_finding(), "impact": "on_upgrade", "effective_date": "2027-05-01",
             "removal_date": "", "announced_date": "",
             "title": "Removal of Customer.conversion_tracking_setting.enhanced_conversions_for_leads_enabled"}
    run1, _, _ = tracking.track([dated], [], root, date(2026, 10, 13), [])
    # run 2 rewords the finding and has no date: the line and the title's words tie them
    reworded = {**dated, "effective_date": "",
                "title": "Removal of enhanced_conversions_for_leads_enabled in ConversionTrackingSetting"}
    run2 = [{**run1[0], "key": tracking.key(reworded), "title": reworded["title"],
             "effective_date": "", "first_reported": "2026-10-20"}]

    combined = tracking.combine([run2, run1])

    assert combined[0]["effective_date"] == "2027-05-01"
    assert combined[0]["first_reported"] == "2026-10-13"
    assert combined[0]["title"] == reworded["title"]
    # a finding only an older report had is not brought back
    assert len(tracking.combine([[], run1])) == 0


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Replace auth in `pipelines/z.py` line 8 and line 14.", [("pipelines/z.py", 8), ("pipelines/z.py", 14)]),
        ("In pipelines/z.py lines 8 and 14, migrate.", [("pipelines/z.py", 8), ("pipelines/z.py", 14)]),
        ("verify `models/d.sql` lines 3-4", [("models/d.sql", 3), ("models/d.sql", 4)]),
        ("`models/x.sql` line 2, 5 and 7", [("models/x.sql", 2), ("models/x.sql", 5), ("models/x.sql", 7)]),
        # a number after the line list belongs to the sentence, not to the file
        ("In `pipelines/gh.py` line 7 from `2022` to 26 versions", [("pipelines/gh.py", 7)]),
        ("change `a.py` line 3 and `b.sql` line 9", [("a.py", 3), ("b.sql", 9)]),
        ("see `a.py`, then line 4", []),
        ("`a.py` lines 10-900", [("a.py", 10)]),
    ],
)
def test_every_line_a_recommendation_names_is_read(text: str, expected: list) -> None:
    assert tracking.locations(text) == expected


def test_findings_naming_one_shared_line_among_several_are_the_same(tmp_path: Path) -> None:
    """Zendesk: run 4 targeted lines 8 and 14, run 5 only line 14 under another title."""
    root = workspace(tmp_path)
    (root / "pipelines" / "pipedrive.py").write_text('"""Deals."""\nEMAIL = "x"\nAUTH = "token"\n')
    earlier = {**pipedrive_finding(), "title": "API token deprecation", "effective_date": "2026-10-27",
               "recommendation": "Replace auth in `pipelines/pipedrive.py` line 2 and line 3."}
    first, _, _ = tracking.track([earlier], [], root, date(2026, 10, 20), [])
    again = {**earlier, "title": "Phased end-of-life for API tokens", "effective_date": "2026-07-28",
             "recommendation": "Replace auth in `pipelines/pipedrive.py` line 3."}

    tracked, carried, _ = tracking.track([again], first, root, TODAY, [])

    assert carried == [] and len(tracked) == 1 and tracked[0]["new"] is False


def test_a_finding_an_older_report_held_twice_is_carried_once(tmp_path: Path) -> None:
    root = workspace(tmp_path)
    (root / "pipelines" / "pipedrive.py").write_text('"""Deals."""\nEMAIL = "x"\nAUTH = "token"\n')
    one = {**pipedrive_finding(), "title": "API token deprecation", "effective_date": "2026-10-27",
           "recommendation": "Replace auth in `pipelines/pipedrive.py` line 2 and line 3."}
    two = {**one, "title": "Phased end-of-life for API tokens",
           "recommendation": "Replace auth in `pipelines/pipedrive.py` line 3."}
    # an older report saved both copies under different keys
    previous = [
        {**one, "key": tracking.key(one), "first_reported": "2026-10-20",
         "lines": tracking.fingerprint(one, root)},
        {**two, "key": tracking.key(two), "first_reported": "2026-10-20",
         "lines": tracking.fingerprint(two, root)},
    ]

    tracked, carried, resolved = tracking.track([one], previous, root, TODAY, [])

    assert len(tracked) == 1 and carried == [] and resolved == []


def test_two_changes_on_one_line_stay_two_findings(tmp_path: Path) -> None:
    """HubSpot: the v1 sunset and the v1-v3 end of support both fix the same endpoint line."""
    root = workspace(tmp_path)
    sunset = {**pipedrive_finding(), "title": "Pipelines API V1 Sunset: December 4, 2026",
              "effective_date": "2026-12-04"}
    legacy = {**pipedrive_finding(), "title": "Legacy APIs and Apps: What's Going Unsupported and When",
              "effective_date": "2027-09-01"}
    first, _, _ = tracking.track([sunset, legacy], [], root, date(2026, 10, 20), [])

    tracked, carried, _ = tracking.track([sunset], first, root, TODAY, [])

    assert len(tracked) == 2 and [c["title"] for c in carried] == [legacy["title"]]
