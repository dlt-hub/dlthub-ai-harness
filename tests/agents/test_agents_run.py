"""The toolkit's agent runs as a user declares it: `run.agent("<toolkit>:<agent>")`.

Each test checks the returned output and `last_job_result`. The model is `TestModel`.
"""

from pathlib import Path

import pytest

from dlt.hub import run

NULL_LOOP = "null-pydantic-ai"
FAILED_RUN_ID = "3f2b9c1e-8a4d-4e6f-9b2a-1c3d5e7f9a0b"


def inspector_report(summary: str) -> dict:
    return {
        "status": "succeeded",
        "summary": summary,
        "failed_run_id": FAILED_RUN_ID,
        "classification": "config",
        "confidence": "high",
        "evidence": [
            {"source": "run log", "excerpt": "destination type missing", "provenance": "run_log"}
        ],
        "open_points": [],
        "requires_human": False,
    }


@pytest.mark.asyncio
async def test_job_inspector_runs_and_links_its_summary(
    workspace: Path, null_loop: type, monkeypatch: pytest.MonkeyPatch
) -> None:
    # a workspace id is all the summary links need; no token, so nothing is looked up
    monkeypatch.setenv("RUNTIME__WORKSPACE_ID", "ws-test")
    null_loop.output = inspector_report(f"- Run {FAILED_RUN_ID} of `jobs.ingest.load` failed.")
    inspector = run.agent("dlthub-platform:job-inspector")

    report = await inspector(failed_run_id=FAILED_RUN_ID)

    # the output went through `validate_output` in the agent's `agent.py`: ids became links
    assert f"/w/ws-test/runs/{FAILED_RUN_ID})" in report["summary"]
    assert "/w/ws-test/jobs/jobs.ingest.load)" in report["summary"]
    job_result = inspector.last_job_result
    assert job_result["type"] == "job.background_agent.dlthub-platform:job-inspector"
    assert job_result["status"] == "succeeded"
    assert job_result["result"] == report
    assert any(
        {"type": entity_type, "id": f"{entity_type}/{FAILED_RUN_ID}"} in job_result["object"]
        for entity_type in ("job-runs", "job-run")
    )
    trace = job_result["trace"]
    assert trace["loop_type"] == NULL_LOOP
    assert trace["inputs"]["failed_run_id"] == FAILED_RUN_ID
    assert trace["unresolved_placeholders"] == []
    assert trace["inlined_skills"] == ["dlthub-platform:debug-deployment"]


@pytest.mark.asyncio
async def test_job_inspector_output_generated_from_its_schema_validates(workspace: Path) -> None:
    """`TestModel` fills the output from the declared schema; dlt validates it in full."""
    inspector = run.agent("dlthub-platform:job-inspector")

    report = await inspector(failed_run_id=FAILED_RUN_ID)

    for field in ("status", "summary", "classification", "confidence", "evidence"):
        assert field in report
    assert inspector.last_job_result["status"] == report["status"]


SHOPIFY_NOTE = """<rss version="2.0"><channel><item>
<title>The `automaticDiscounts` query is removed in API version 2027-01</title>
<link>https://shopify.dev/changelog/automatic-discounts-removed</link>
<pubDate>{published}</pubDate>
<category>Breaking API Change</category><category>Admin GraphQL API</category>
<description>Use discountNodes instead.</description>
</item></channel></rss>"""


class _Page:
    def __init__(self, text: str) -> None:
        self.text = text
        self.headers = {"content-type": "application/xml; charset=utf-8"}

    def raise_for_status(self) -> None:
        pass


def monitor_report() -> dict:
    return {
        "status": "succeeded",
        "summary": "## Action required\n- shopify\n\n## Opportunities\n- none\n\n## Scope\n- one",
        "since": "2026-10-12",
        "sources": [
            {"api": "shopify", "url": "https://shopify.dev/changelog/feed.xml", "origin": "registry"}
        ],
        "changes": [
            {
                "api": "shopify",
                "kind": "breaking",
                "title": "automaticDiscounts removed in 2027-01",
                "announced_date": "2026-10-01",
                "effective_date": "2027-01-01",
                "removal_date": "",
                "source_url": "https://shopify.dev/changelog/automatic-discounts-removed",
                "impact": "action_required",
                "affected": ["pipelines/shopify_pipeline.py line 4"],
                "loaded_tables": [],
                "action": "Replace the `automaticDiscounts` query with `discountNodes`",
                "recommendation": "Replace the automaticDiscounts query with discountNodes.",
            }
        ],
        "open_points": [],
        "requires_human": True,
    }


@pytest.mark.asyncio
async def test_api_change_monitor_renders_the_notes_and_the_usage_map(
    workspace: Path, null_loop: type, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import date, timedelta
    from email.utils import format_datetime
    from datetime import datetime, timezone

    from dlt.sources.helpers import requests

    published = format_datetime(datetime.now(timezone.utc) - timedelta(days=1))
    fetched: list = []

    def fake_get(url: str, **kwargs: object) -> _Page:
        fetched.append(url)
        if "shopify" in url:
            return _Page(SHOPIFY_NOTE.format(published=published))
        raise ConnectionError("offline")

    monkeypatch.setattr(requests, "get", fake_get)
    (workspace / "pipelines").mkdir()
    (workspace / "pipelines" / "shopify_pipeline.py").write_text(
        'QUERY = "automaticDiscounts"  # shopify admin api 2025-01\n'
    )
    null_loop.output = monitor_report()
    monitor = run.agent("dlthub-platform:api-change-monitor")

    report = await monitor(apis="shopify, amazon-sp-api")

    assert report["changes"][0]["impact"] == "action_required"
    trace = monitor.last_job_result["trace"]
    assert trace["unresolved_placeholders"] == []
    # the web tools are native: a model serving them gets them, the offline one does not
    assert set(trace["local_tools"]) == {"Read", "Glob", "Grep"}
    inputs = trace["inputs"]
    assert inputs["since"] == (date.today() - timedelta(days=7)).isoformat()
    assert "automaticDiscounts` query is removed" in inputs["release_notes"]
    # amazon was down: the run goes on and the window says so
    assert "### amazon-sp-api (0 notes" in inputs["release_notes"]
    assert "ConnectionError: offline" in inputs["release_notes"]
    assert "`amazon-sp-api`: named in the `apis` input" in inputs["apis_found"]
    assert "release notes not read: find them" in inputs["apis_found"]
    assert "pipelines/shopify_pipeline.py:1:" in inputs["workspace_usage"]
    # the query names the removed field, so the hook keeps the note for the model
    assert "- named in pipeline code:" in inputs["release_notes"]
    assert inputs["ruled_out"] == "None."
    assert any("shopify.dev/changelog/feed.xml" in url for url in fetched)


@pytest.mark.asyncio
async def test_api_change_monitor_aborts_when_production_calls_no_api(workspace: Path) -> None:
    monitor = run.agent("dlthub-platform:api-change-monitor")

    with pytest.raises(Exception, match="calls no API this agent recognises"):
        await monitor()


STRIPE_CHANGELOG = """# Changelog

## {day}.endive

* Removes `dispute.evidence_details.has_evidence` from `GET /v1/disputes/{{id}}`.
"""


@pytest.mark.asyncio
async def test_api_change_monitor_job_runs_the_model_once_per_api_with_notes(
    workspace: Path, null_loop: type, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import datetime, timedelta, timezone
    from email.utils import format_datetime

    from dlt._workspace.deployment.agent.manifest import load_agent_module
    from dlt.sources.helpers import requests

    yesterday = datetime.now(timezone.utc) - timedelta(days=1)

    def fake_get(url: str, **kwargs: object) -> _Page:
        if "shopify" in url:
            return _Page(SHOPIFY_NOTE.format(published=format_datetime(yesterday)))
        return _Page(STRIPE_CHANGELOG.format(day=yesterday.date().isoformat()))

    monkeypatch.setattr(requests, "get", fake_get)
    (workspace / "pipelines").mkdir()
    (workspace / "pipelines" / "shop.py").write_text(
        'client = {"base_url": "https://x.myshopify.com/admin/api/2025-01/graphql.json"}\n'
        'QUERY = "automaticDiscounts"\n'
    )
    (workspace / "pipelines" / "pay.py").write_text(
        'client = {"base_url": "https://api.stripe.com/v1/"}\n'
        'resources = [{"endpoint": {"path": "customers"}}]\n'
    )
    runs: list = []
    original_run = null_loop.run

    async def counting_run(self: object, *args: object, **kwargs: object) -> dict:
        runs.append(kwargs["inputs"]["apis"])
        return await original_run(self, *args, **kwargs)

    monkeypatch.setattr(null_loop, "run", counting_run)
    null_loop.output = monitor_report()
    monitor = load_agent_module(
        str(workspace / ".claude/dlthub/agents/dlthub-platform/api-change-monitor")
    )

    @run.agent(agent="dlthub-platform:api-change-monitor")
    async def api_change_monitor(
        run_context: run.TJobRunContext = None,
        apis: str = "",
        since: str = "",
        reviewed_versions: str = "",
    ) -> dict:
        return await monitor.run_per_api(
            run_context, apis=apis, since=since, reviewed_versions=reviewed_versions
        )

    report = await api_change_monitor(apis="shopify, stripe")

    # stripe's only note names an endpoint no resource calls, so it needs no model run
    assert runs == ["shopify"]
    assert [(r["api"], r["status"]) for r in report["runs"]] == [
        ("shopify", "succeeded"), ("stripe", "skipped")
    ]
    assert report["status"] == "succeeded" and report["requires_human"] is True
    assert report["changes"][0]["api"] == "shopify"
    summary = report["summary"]
    assert summary.startswith("**1 open finding: 1 act now, 1 new.**")
    assert "| when | api | impact | action |" in summary
    assert "| shopify | act | Replace the `automaticDiscounts` query with `discountNodes`" in summary
    assert "1 model run," in summary.splitlines()[-1]
    trace = api_change_monitor.last_job_result["trace"]
    assert trace["unresolved_placeholders"] == []
    assert "automaticDiscounts` query is removed" in trace["inputs"]["release_notes"]
    # the workspace holds no transformations: the run still works and says where models are
    assert "downstream models: none in this workspace" in trace["inputs"]["apis_found"]
    assert "### Downstream model files\n\nNone found." in trace["inputs"]["workspace_usage"]
