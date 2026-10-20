"""Tests for how one job merges its per-API runs into one report."""

from dlt._workspace.deployment.agent.manifest import load_agent_module

from tests.utils import REPO_ROOT

agent = load_agent_module(
    str(REPO_ROOT / "workbench/dlthub-platform/dlthub/agents/api-change-monitor")
)
report = agent.report


def change(impact: str, day: str = "", affected: tuple = (), title: str = "x") -> dict:
    return {
        "api": "wrong", "kind": "breaking", "title": title, "effective_date": day,
        "announced_date": "", "removal_date": "",
        "source_url": "u", "impact": impact, "affected": list(affected),
        "recommendation": "Change | this\nnow.",
    }


def test_runs_merge_into_one_report_with_a_table() -> None:
    github = report.ApiResult(
        "github", "succeeded", turns=4, tokens=1000, kept=3, ruled_out=17,
        output={
            "changes": [
                change("on_upgrade", "", ["`pipelines/gh.py` line 7"]),
                change("not_used"),
            ],
            "sources": [{"api": "github", "url": "g", "origin": "registry"}],
            "open_points": ["check x"],
        },
    )
    zendesk = report.ApiResult(
        "zendesk", "succeeded", turns=3, tokens=500, kept=2,
        output={"changes": [change("action_required", "2026-08-06",
                                   ["pipelines/z.py line 23", "transformations/asset_costs.sql line 2"])]},
    )
    stripe = report.ApiResult("stripe", "skipped", ruled_out=4, sources=["s"])

    merged = report.merge([github, zendesk, stripe], "2026-01-01", "2026-10-20")

    assert merged["status"] == "succeeded" and merged["requires_human"] is True
    # each run was about one API, so its rows take that API whatever the model wrote
    assert {c["api"] for c in merged["changes"]} == {"github", "zendesk"}
    assert merged["sources"][-1] == {"api": "stripe", "url": "s", "origin": "registry"}
    assert merged["runs"][2] == {"api": "stripe", "status": "skipped", "turns": 0, "tokens": 0}
    summary = merged["summary"]
    # a date before the report's own is marked, since that change already landed
    assert "- `zendesk`: 1 change, earliest 2026-08-06 (passed), breaks `transformations/asset_costs.sql`" in summary
    assert "- `github`: 1 change, no end date given" in summary
    # the job names the API of every open point, which a run cannot do itself
    assert "## Open questions\n- `github`: check x" in summary
    assert merged["open_points"] == ["`github`: check x"]
    scope = summary.split("## Scope\n")[1].split("\n\n")[0].splitlines()
    assert scope == [
        "- 2026-01-01 to 2026-10-20: 3 APIs, 26 release notes read, 2 changes affect this workspace.",
        "- Release notes per API: `github` 20, `zendesk` 2, `stripe` 4.",
        "- No change for this workspace: `stripe`.",
        "- Cost: 2 model runs, 1,500 tokens; no run needed for `stripe`.",
    ]
    rows = summary.split("## Changes\n")[1].splitlines()
    # action required first, the cell keeps no pipe and no line break
    assert rows[2].startswith("| `zendesk` | 2026-08-06 | action_required |")
    assert rows[2].endswith("| Change / this now. | new |")
    assert "| `pipelines/z.py` line 23, `transformations/asset_costs.sql` line 2 |" in rows[2]
    assert rows[3].startswith("| `github` | on upgrade | on_upgrade |")
    assert len(rows) == 4


def test_a_run_that_did_not_finish_fails_the_job_and_says_why() -> None:
    down = report.ApiResult("jira", "not_run", reason="the job spent its 3,000,000 tokens")

    merged = report.merge([down], "2026-01-01")

    assert merged["status"] == "failed"
    assert merged["open_points"] == ["`jira` was not checked: the job spent its 3,000,000 tokens."]
    assert "- Not checked: `jira`, the job spent its 3,000,000 tokens." in merged["summary"]
    assert merged["summary"].endswith("## Changes\n- No change touches this workspace.")


def test_a_long_open_point_is_cut_at_a_word() -> None:
    point = "word " * 80
    result = report.ApiResult("hubspot", "succeeded", output={"open_points": [point, point]})

    bullets = report.merge([result], "2026-01-01")["summary"].split("## Open questions\n")[1]
    first = bullets.split("\n\n")[0].splitlines()

    # repeats collapse into one bullet
    assert len(first) == 1 and first[0].endswith("word…") and len(first[0]) < 240


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
    assert "## Open questions\n- `pipedrive`: The note does not list" in merged["summary"]

    # release notes nobody could read or find are a failure on the job's side
    assert report.merge([pipedrive, unread], "2026-09-20")["status"] == "failed"
