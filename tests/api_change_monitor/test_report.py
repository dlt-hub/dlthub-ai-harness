"""Tests for how one job merges its per-API runs into one short report."""

from dlt._workspace.deployment.agent.manifest import load_agent_module

from tests.utils import REPO_ROOT

agent = load_agent_module(
    str(REPO_ROOT / "workbench/dlthub-platform/dlthub/agents/api-change-monitor")
)
report = agent.report


def change(impact: str, day: str = "", affected: tuple = (), title: str = "x", action: str = "") -> dict:
    return {
        "api": "wrong", "kind": "breaking", "title": title, "effective_date": day,
        "announced_date": "", "removal_date": "",
        "source_url": "u", "impact": impact, "affected": list(affected), "loaded_tables": [],
        "action": action, "recommendation": "Change | this\nnow.",
    }


def test_runs_merge_into_one_short_report_with_a_table() -> None:
    github = report.ApiResult(
        "github", "succeeded", turns=4, tokens=1000, kept=3, ruled_out=17,
        output={
            "changes": [
                change("on_upgrade", "", ["`pipelines/gh.py` line 7"], action="Read `resources.core`"),
                change("not_used"),
            ],
            "sources": [{"api": "github", "url": "g", "origin": "registry"}],
            "open_points": ["check x"],
        },
    )
    zendesk = report.ApiResult(
        "zendesk", "succeeded", turns=3, tokens=500, kept=2,
        output={"changes": [change(
            "action_required", "2026-08-06",
            ["pipelines/z.py line 23", "transformations/asset_costs.sql line 2"],
            action="Sum `purchase_cost__amount` | not the object",
        )]},
    )
    stripe = report.ApiResult("stripe", "skipped", ruled_out=4, sources=["s"])

    merged = report.merge([github, zendesk, stripe], "2026-01-01", "2026-10-20")

    assert merged["status"] == "succeeded" and merged["requires_human"] is True
    # each run was about one API, so its rows take that API whatever the model wrote
    assert {c["api"] for c in merged["changes"]} == {"github", "zendesk"}
    assert merged["sources"][-1] == {"api": "stripe", "url": "s", "origin": "registry"}
    assert merged["runs"][2] == {"api": "stripe", "status": "skipped", "turns": 0, "tokens": 0}
    # the job names the API of every open point, which a run cannot do itself
    assert merged["open_points"] == ["`github`: check x"]
    assert merged["summary"].splitlines() == [
        "**2 open findings: 1 act now, 1 plan ahead, 2 new.**",
        "",
        "| when | api | api change | impact | transformations | action |",
        "|---|---|---|---|---|---|",
        # act now first, a date already gone marked, the cell keeps no pipe
        "| 2026-08-06 passed | zendesk | x | act | `asset_costs.sql` | Sum `purchase_cost__amount` / not the object (`z.py:23`) |",
        "| on upgrade | github | x | upgrade | no transformations in the workspace | Read `resources.core` (`gh.py:7`) |",
        "",
        "**Open:** github: check x",
        "",
        "**Coverage:** 3 APIs, 26 notes since 2026-01-01. 2 model runs, 2k tokens.",
    ]


def test_a_run_that_did_not_finish_fails_the_job_and_says_why() -> None:
    down = report.ApiResult("jira", "not_run", reason="the job spent its 3,000,000 tokens")

    merged = report.merge([down], "2026-01-01")

    assert merged["status"] == "failed"
    assert merged["open_points"] == ["`jira` was not checked: the job spent its 3,000,000 tokens."]
    assert merged["summary"].splitlines() == [
        "**No open findings.**",
        "",
        "**Coverage:** 1 API, 0 notes since 2026-01-01; gaps: jira not checked (the job spent"
        " its 3,000,000 tokens). No model run needed.",
    ]


def test_open_points_are_cut_short_and_listed_three_at_most() -> None:
    points = ["word " * 80, "word " * 80, "second", "third", "fourth"]
    result = report.ApiResult("hubspot", "succeeded", output={"open_points": points})

    line = next(l for l in report.merge([result], "2026-01-01")["summary"].splitlines() if l.startswith("**Open:**"))

    # repeats collapse, each point is cut at a word, the rest is counted
    assert line.count("hubspot:") == 3 and "word…;" in line and line.endswith("(+1 more)")


def test_an_open_question_the_note_leaves_is_no_failed_run() -> None:
    """Pipedrive's note named no endpoints: an `unknown` finding is the job done."""
    unknown = {**change("unknown", "2026-08-01"), "recommendation": "Check the v1 endpoints."}
    pipedrive = report.ApiResult(
        "pipedrive", "failed", turns=3,
        output={
            "changes": [unknown],
            "sources": [{"api": "pipedrive", "url": "https://p/changelog", "origin": "registry"}],
            "open_points": ["The note does not list which v1 endpoints are out of support."],
        },
    )
    unread = report.ApiResult(
        "acme", "failed", unread=True,
        output={"sources": [{"api": "acme", "url": "", "origin": "not_found"}]},
    )

    merged = report.merge([pipedrive], "2026-09-20")
    assert merged["status"] == "succeeded" and merged["runs"][0]["status"] == "succeeded"
    assert "**Open:** pipedrive: The note does not list" in merged["summary"]
    assert "| 2026-08-01 | pipedrive | x | check |" in merged["summary"]

    # release notes nobody could read or find are a failure on the job's side
    assert report.merge([pipedrive, unread], "2026-09-20")["status"] == "failed"


def test_a_schema_change_for_possible_downstream_models_is_a_row() -> None:
    schema = {
        **change("schema_change", "", action="Expect `billing_cycle_anchor` as an object"),
        "loaded_tables": ["stripe_data.subscriptions.billing_cycle_anchor"],
        "recommendation": "In `pipelines/stripe.py` line 7, expect an object.",
    }
    stripe = report.ApiResult("stripe", "succeeded", output={"changes": [schema]})

    summary = report.merge([stripe], "2026-09-20", "2026-10-20")["summary"]

    assert summary.startswith("**1 open finding: 1 plan ahead, 1 new.**")
    assert "| not dated | stripe | x | table change | no transformations in the workspace | Expect `billing_cycle_anchor` as an object (`stripe.py:7`) |" in summary


def test_a_row_without_an_action_shows_the_start_of_its_recommendation() -> None:
    """Findings saved before `action` existed still say what to change, not their title."""
    carried = {
        **change("unknown", "2026-08-01", title="Reminder: v1 endpoints are out of support"),
        "recommendation": "In `pipelines/pipedrive.py` line 16 and line 17, check whether `deals`"
                          " and `persons` call retired v1 endpoints. Read the migration guide.",
    }
    assert report._edit(carried) == "Check whether `deals` and `persons` call retired v1 endpoints"
    assert report._action(carried).endswith("(`pipedrive.py:16`)")
    # an action, when there is one, is shown as written
    assert report._edit({**carried, "action": "Change `v1` to `v2`"}) == "Change `v1` to `v2`"
    assert report._edit({**carried, "recommendation": ""}) == carried["title"]


def test_the_fallback_drops_places_the_report_adds_itself() -> None:
    """Run 8: carried rows named their files inside the sentence, twice per row."""
    pipedrive = {**change("unknown"), "recommendation": (
        "Check whether the `deals` resource (`pipelines/pipedrive_pipeline.py` line 16) and"
        " `persons` resource (`pipelines/pipedrive_pipeline.py` line 17) use API v1 endpoints."
    )}
    hubspot = {**change("action_required"), "recommendation": (
        "Change endpoint path in pipelines/hubspot_pipeline.py line 18 from"
        " 'crm-pipelines/v1/pipelines/deals' to 'crm/v3/pipelines/deals'."
    )}

    assert report._edit(pipedrive) == (
        "Check whether the `deals` resource and `persons` resource use API v1 endpoints"
    )
    assert report._edit(hubspot) == (
        "Change endpoint path from 'crm-pipelines/v1/pipelines/deals' to 'crm/v3/pipelines/deals'"
    )
    assert report._action(pipedrive).endswith("(`pipedrive_pipeline.py:16`)")
    # a full stop the model put after an action is dropped too
    assert report._edit({**change("act"), "action": "Change `v1` to `v2`."}) == "Change `v1` to `v2`"


def test_the_transformations_column_names_the_models_or_says_why_none() -> None:
    breaks = change("action_required", affected=["pipelines/z.py line 2", "transformations/costs.sql line 3"])
    misses = change("table_only", affected=["pipelines/z.py line 2"])

    assert report._transformations(breaks, ["transformations/costs.sql"]) == "`costs.sql`"
    # the API has models here, the change reaches none of them
    assert report._transformations(misses, ["transformations/costs.sql"]) == "none affected"
    # no model in the workspace reads the API's tables at all
    assert report._transformations(misses, None) == "no transformations in the workspace"


def test_open_points_lose_their_full_stop_before_the_separator() -> None:
    result = report.ApiResult("jira", "succeeded", output={"open_points": ["One.", "Two."]})

    line = next(l for l in report.merge([result], "2026-01-01")["summary"].splitlines() if l.startswith("**Open:**"))

    assert line == "**Open:** jira: One; jira: Two"
