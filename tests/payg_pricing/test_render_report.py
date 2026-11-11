"""Tests for `render_report.py`, which renders a PAYG estimate as a one-page HTML report."""

import importlib.util
import json
from pathlib import Path

import pytest

from tests.utils import REPO_ROOT

SKILL_DIR = REPO_ROOT / "workbench/payg-pricing/skills/pricing-estimation"
_spec = importlib.util.spec_from_file_location("render_report", SKILL_DIR / "render_report.py")
assert _spec and _spec.loader
rr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rr)


def worked_example() -> dict:
    """The worked example from SKILL.md: 3 jobs, no failed runs."""
    return {
        "rate_usd_per_hour": 10,
        "date": "2026-11-11",
        "jobs": [
            {
                "name": "orders_sync",
                "cadence": "every 15 min",
                "runs_per_month": 2880,
                "avg_min": 2,
                "slow_min": 3,
                "size": "small",
                "multiplier": 1,
            },
            {
                "name": "crm_hourly",
                "cadence": "hourly",
                "runs_per_month": 720,
                "avg_min": 5,
                "slow_min": 8,
                "size": "medium",
                "multiplier": 2,
            },
            {
                "name": "warehouse_daily",
                "cadence": "daily",
                "runs_per_month": 30,
                "avg_min": 20,
                "slow_min": 30,
                "size": "small",
                "multiplier": 1,
            },
        ],
        "savings": [
            {"label": "orders_sync every 30 min instead of 15", "usd_per_month": 480},
            {"label": "Incremental loading for crm_hourly", "usd_per_month": None},
        ],
        "assumptions": ["Durations from the last 20 successful runs."],
    }


def test_worked_example_totals_match_the_skill() -> None:
    est = rr.compute(worked_example())

    assert [round(j["hours_expected"], 1) for j in est["jobs"]] == [96.0, 120.0, 10.0]
    assert round(est["hours_expected"], 1) == 226.0
    assert round(est["usd_expected"], 2) == 2260.00
    assert round(est["hours_high"], 1) == 351.0
    assert round(est["usd_high"], 2) == 3510.00


def test_per_unit_figures() -> None:
    est = rr.compute(worked_example())

    assert est["runs_per_month"] == 3630
    assert round(est["usd_per_job"], 2) == round(2260 / 3, 2)
    assert round(est["usd_per_run"], 4) == round(2260 / 3630, 4)
    assert round(est["usd_per_day"], 2) == round(2260 / 30, 2)


def test_failed_runs_are_billed_once_not_twice() -> None:
    data = worked_example()
    data["jobs"] = [
        {
            "name": "flaky",
            "cadence": "hourly",
            "runs_per_month": 100,
            "avg_min": 6,
            "slow_min": 6,
            "size": "small",
            "multiplier": 1,
            "failed_share": 0.1,
            "failed_min": 3,
        },
    ]
    est = rr.compute(data)

    # 90 successful runs x 6 min + 10 failed runs x 3 min = 570 min = 9.5 h
    assert round(est["hours_expected"], 2) == 9.5
    assert round(est["usd_expected"], 2) == 95.0


def test_always_on_job_bills_uptime() -> None:
    data = worked_example()
    data["jobs"] = [
        {
            "name": "dashboard",
            "cadence": "always on",
            "uptime_hours_per_day": 8,
            "size": "medium",
            "multiplier": 2,
        },
    ]
    est = rr.compute(data)

    # 8 h/day x 30 days x 2 = 480 h, the same in a heavy month
    assert est["hours_expected"] == est["hours_high"] == 480
    assert est["runs_per_month"] == 0
    assert est["usd_per_run"] is None


def test_cost_per_run_leaves_always_on_jobs_out() -> None:
    data = worked_example()
    data["jobs"].append({
        "name": "dashboard",
        "cadence": "always on",
        "uptime_hours_per_day": 10,
        "size": "small",
        "multiplier": 1,
    })
    est = rr.compute(data)

    # the dashboard adds $3,000 to the total but no runs; per run stays $2,260 / 3,630
    assert round(est["usd_expected"], 2) == 5260.00
    assert round(est["usd_per_run"], 4) == round(2260 / 3630, 4)


def test_engineering_time_comparison() -> None:
    data = worked_example()
    data["engineering"] = {"hours_per_month": 40, "hourly_rate_usd": 100}
    est = rr.compute(data)

    assert est["engineering"]["usd_per_month"] == 4000
    assert round(est["engineering"]["difference_usd"], 2) == 4000 - 2260


def test_missing_engineering_answer_leaves_the_section_out() -> None:
    page = rr.render(rr.compute(worked_example()))

    assert "Engineering time" not in page


def test_report_is_self_contained() -> None:
    data = worked_example()
    data["engineering"] = {"hours_per_month": 40, "hourly_rate_usd": 100}
    page = rr.render(rr.compute(data))

    assert "<script" not in page.lower()
    assert "http://" not in page and "https://" not in page
    assert "$2,260" in page and "$3,510" in page
    assert "orders_sync" in page and "Engineering time" in page
    assert "{{" not in page and "}}" not in page


def test_customer_text_is_escaped() -> None:
    data = worked_example()
    data["jobs"][0]["name"] = "<b>orders</b>"
    page = rr.render(rr.compute(data))

    assert "<b>orders</b>" not in page
    assert "&lt;b&gt;orders&lt;/b&gt;" in page


def test_unquantified_saving_says_so() -> None:
    page = rr.render(rr.compute(worked_example()))

    assert "measure after the change" in page


@pytest.mark.parametrize(
    "job, message",
    [
        (
            {
                "name": "x",
                "cadence": "hourly",
                "runs_per_month": 720,
                "slow_min": 3,
                "size": "small",
                "multiplier": 1,
            },
            "avg_min",
        ),
        (
            {
                "name": "x",
                "cadence": "hourly",
                "runs_per_month": 720,
                "avg_min": 2,
                "slow_min": 3,
                "size": "small",
            },
            "multiplier",
        ),
    ],
)
def test_missing_inputs_fail_loudly(job: dict, message: str) -> None:
    data = worked_example()
    data["jobs"] = [job]

    with pytest.raises(ValueError, match=message):
        rr.compute(data)


def test_cli_writes_the_report(tmp_path: Path) -> None:
    src = tmp_path / "estimate.json"
    out = tmp_path / "report.html"
    src.write_text(json.dumps(worked_example()), encoding="utf-8")

    rr.main([str(src), "--out", str(out)])

    assert out.read_text(encoding="utf-8").startswith("<!doctype html>")
