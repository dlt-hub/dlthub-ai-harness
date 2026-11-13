"""Tests for `payg_estimate.py`: every number in the PAYG estimate comes from code, not the LLM."""

import importlib.util
import json
from pathlib import Path

import pytest

from tests.utils import REPO_ROOT

SKILL_DIR = REPO_ROOT / "workbench/payg-pricing/skills/pricing-estimation"
_spec = importlib.util.spec_from_file_location("payg_estimate", SKILL_DIR / "payg_estimate.py")
assert _spec and _spec.loader
pe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pe)


def every(n: int, unit: str = "minutes") -> dict:
    return {"every": n, "unit": unit}


def assumed(avg: float, slow: float) -> dict:
    return {"avg_minutes": avg, "slow_minutes": slow}


def worked_example() -> dict:
    """The worked example from SKILL.md: 3 jobs, durations given as customer assumptions."""
    return {
        "rate_usd_per_hour": 10,
        "date": "2026-11-11",
        "jobs": [
            {
                "name": "orders_sync",
                "schedule": every(15),
                "size": "small",
                "multiplier": 1,
                "assumed": assumed(2, 3),
            },
            {
                "name": "crm_hourly",
                "schedule": every(1, "hours"),
                "size": "medium",
                "multiplier": 2,
                "assumed": assumed(5, 8),
            },
            {
                "name": "warehouse_daily",
                "schedule": every(1, "days"),
                "size": "small",
                "multiplier": 1,
                "assumed": assumed(20, 30),
            },
        ],
        "levers": [
            {"job": "orders_sync", "schedule": every(30)},
            {"job": "crm_hourly", "schedule": every(2, "hours")},
            {"job": "crm_hourly", "size": "small", "multiplier": 1},
            {"label": "Incremental loading for warehouse_daily", "unquantified": True},
        ],
    }


# --- schedules -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "schedule, runs",
    [
        # an average month is 365 / 12 days
        (every(5), 8760),
        (every(15), 2920),
        (every(30), 1460),
        (every(1, "hours"), 730),
        (every(6, "hours"), 365 / 3),
        (every(1, "days"), 365 / 12),
        ({"cron": "*/15 * * * *"}, 2920),
        ({"cron": "0 * * * *"}, 730),
        ({"cron": "0 2 * * *"}, 365 / 12),  # same as every 1 day
        ({"cron": "0 9 * * 1-5"}, 261 / 12),  # weekdays only: not 30
        ({"cron": "0 9 * * MON-FRI"}, 261 / 12),  # names work too
        ({"cron": "0 9 * * 1"}, 52 / 12),  # weekly on Mondays
        ({"cron": "30 8,17 * * *"}, 2 * 365 / 12),
        ({"cron": "0 2 4 * *"}, 1),  # monthly on the 4th
        ({"cron": "0 0 1 7 *"}, 1 / 12),  # yearly, in July
        ({"cron": "0 2 L * *"}, 1),  # last day of the month
    ],
)
def test_runs_per_month(schedule: dict, runs: float) -> None:
    assert pe.runs_per_month(schedule) == pytest.approx(runs)


@pytest.mark.parametrize(
    "cron, label",
    [
        ("0 */6 * * *", "4× a day"),
        ("0 2 * * *", "daily"),
        ("0 * * * *", "hourly"),
        ("0 9 * * 1-5", "21.8× a month"),
        ("0 9 * * 1", "4.3× a month"),
        ("0 2 4 * *", "1× a month"),
        ("0 0 1 7 *", "1× a year"),
    ],
)
def test_cron_labels_are_readable(cron: str, label: str) -> None:
    assert pe.schedule_label({"cron": cron}) == label


def test_bad_schedule_fails_loudly() -> None:
    with pytest.raises(ValueError, match="schedule"):
        pe.runs_per_month({"every": 15, "unit": "fortnights"})


# --- run statistics --------------------------------------------------------------------------


def test_run_stats_from_raw_runs() -> None:
    runs = [{"minutes": m, "status": "ok"} for m in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)]
    runs += [{"minutes": 0.5, "status": "failed"}, {"minutes": 1.5, "status": "failed"}]
    stats = pe.run_stats({"name": "j", "runs": runs})

    assert stats["avg_min"] == 5.5
    assert stats["slow_min"] == 9  # 90th percentile, nearest rank
    assert stats["failed_share"] == 2 / 12
    assert stats["failed_min"] == 1.0
    assert stats["sample"] == 12


def test_few_runs_use_the_longest_as_slow() -> None:
    runs = [{"minutes": m, "status": "ok"} for m in (2, 3, 7)]
    stats = pe.run_stats({"name": "j", "runs": runs})

    assert stats["slow_min"] == 7
    assert stats["few_runs"] is True


def test_job_without_runs_or_assumption_fails() -> None:
    with pytest.raises(ValueError, match="no successful runs"):
        pe.run_stats({"name": "j", "runs": [{"minutes": 1, "status": "failed"}]})


# --- the estimate ----------------------------------------------------------------------------


def test_worked_example_totals() -> None:
    est = pe.estimate(worked_example())

    assert [round(j["hours_expected"], 1) for j in est["jobs"]] == [97.3, 121.7, 10.1]
    assert round(est["usd_expected"], 2) == 2291.39
    assert round(est["usd_high"], 2) == 3558.75
    assert est["runs_per_month"] == pytest.approx(2920 + 730 + 365 / 12)


def test_failed_runs_are_billed_once() -> None:
    runs = [{"minutes": 6, "status": "ok"}] * 9 + [{"minutes": 3, "status": "failed"}]
    data = {
        "rate_usd_per_hour": 10,
        "jobs": [
            {
                "name": "flaky",
                "schedule": every(1, "days"),
                "size": "small",
                "multiplier": 1,
                "runs": runs,
            }
        ],
    }
    est = pe.estimate(data)

    # 365 / 12 runs, 10% failed: 0.9 x 6 min + 0.1 x 3 min = 5.7 min per run
    assert est["hours_expected"] == pytest.approx(365 / 12 * 5.7 / 60)


def test_always_on_job() -> None:
    data = {
        "rate_usd_per_hour": 10,
        "jobs": [
            {
                "name": "dash",
                "schedule": {"always_on_hours_per_day": 8},
                "size": "medium",
                "multiplier": 2,
            }
        ],
    }
    est = pe.estimate(data)

    assert est["hours_expected"] == est["hours_high"] == pytest.approx(8 * 2 * 365 / 12)
    assert est["usd_per_run"] is None


def test_cost_per_run_leaves_always_on_jobs_out() -> None:
    data = worked_example()
    data["jobs"].append({
        "name": "dash",
        "schedule": {"always_on_hours_per_day": 10},
        "size": "small",
        "multiplier": 1,
    })
    est = pe.estimate(data)

    assert round(est["usd_expected"], 2) == 5333.06
    assert est["usd_per_run"] == pytest.approx(2291.39 / 3680.42, abs=1e-4)


def test_ladder() -> None:
    est = pe.estimate(worked_example())
    ladder = {row["job"]: row["usd"] for row in est["ladder"]}

    assert [round(v, 2) for v in ladder["orders_sync"]] == [973.33, 243.33, 40.56, 10.14]
    assert [round(v, 2) for v in ladder["crm_hourly"]] == [4866.67, 1216.67, 202.78, 50.69]
    assert [round(v, 2) for v in ladder["warehouse_daily"]] == [9733.33, 2433.33, 405.56, 101.39]


def test_levers_are_priced_by_the_script() -> None:
    est = pe.estimate(worked_example())
    savings = [(s["label"], s["usd_per_month"]) for s in est["savings"]]

    assert savings[0] == ("orders_sync every 30 min instead of every 15 min", 486.67)
    assert savings[1] == ("crm_hourly every 2 h instead of hourly", 608.33)
    assert savings[2] == ("crm_hourly on small instead of medium (if it fits)", 608.33)
    assert savings[3] == ("Incremental loading for warehouse_daily", None)


def test_size_lever_is_an_upper_bound_with_break_even() -> None:
    est = pe.estimate(worked_example())
    slowdown = [s["break_even_slowdown"] for s in est["savings"]]

    # a smaller instance may run slower; medium 2x -> small 1x saves nothing at 2x slower
    assert slowdown == [None, None, 2, None]


def test_size_lever_to_a_bigger_instance_has_no_break_even() -> None:
    data = worked_example()
    data["levers"] = [{"job": "orders_sync", "size": "medium", "multiplier": 2}]
    est = pe.estimate(data)

    assert est["savings"][0]["break_even_slowdown"] is None


def test_lever_for_unknown_job_fails() -> None:
    data = worked_example()
    data["levers"] = [{"job": "nope", "schedule": every(30)}]

    with pytest.raises(ValueError, match="nope"):
        pe.estimate(data)


def test_engineering_comparison() -> None:
    data = worked_example()
    data["engineering"] = {"hours_per_month": 40, "hourly_rate_usd": 100}
    est = pe.estimate(data)

    assert est["engineering"]["usd_per_month"] == 4000
    assert round(est["engineering"]["difference_usd"], 2) == 1708.61


def test_assumptions_are_generated() -> None:
    runs = [{"minutes": 2, "status": "ok"}] * 3
    data = worked_example()
    data["jobs"][0] = {
        "name": "orders_sync",
        "schedule": every(15),
        "size": "small",
        "multiplier": 1,
        "runs": runs,
    }
    est = pe.estimate(data)
    text = " ".join(est["assumptions"])

    assert "30.4 days per month (365 / 12)" in text
    assert "orders_sync: 3 recent runs" in text and "fewer than 5" in text
    assert "crm_hourly: run time is the customer's estimate" in text
    assert "small 1×" in text and "medium 2×" in text


# --- outputs ---------------------------------------------------------------------------------


def test_summary_markdown() -> None:
    md = pe.summary(pe.estimate(worked_example()))

    assert "| orders_sync | every 15 min | 2,920 |" in md
    assert "Expected about $2,291.39 per month" in md
    assert "up to about $3,558.75" in md
    # the what-if table names today's cost in its own column instead of bold formatting
    assert "| Job | Now | Every 15 min | Hourly | Every 6 h | Daily |" in md
    assert "| orders_sync | $973.33 (every 15 min) | $973.33 | $243.33 |" in md
    assert "| warehouse_daily | $101.39 (daily) |" in md
    assert "in bold" not in md and "**$973.33**" not in md
    assert "saves $486.67/month" in md
    assert (
        "crm_hourly on small instead of medium (if it fits): saves up to $608.33/month if the"
        " run time doesn't change; no saving if it runs 2× slower or more." in md
    )
    assert "measure after the change" in md


def test_report_is_self_contained_and_escaped() -> None:
    data = worked_example()
    data["jobs"][0]["name"] = "<b>orders</b>"
    data["levers"][0]["job"] = "<b>orders</b>"
    data["engineering"] = {"hours_per_month": 40, "hourly_rate_usd": 100}
    page = pe.report(pe.estimate(data))

    assert page.startswith("<!doctype html>")
    assert "<script" not in page.lower()
    assert "http://" not in page and "https://" not in page
    assert "<b>orders</b>" not in page and "&lt;b&gt;orders&lt;/b&gt;" in page
    assert "$2,291" in page and "Engineering time" in page
    assert "$usd" not in page and "$job_rows" not in page


def test_report_without_engineering_leaves_the_section_out() -> None:
    page = pe.report(pe.estimate(worked_example()))

    assert "Engineering time" not in page


def test_report_marks_size_saving_as_upper_bound() -> None:
    page = pe.report(pe.estimate(worked_example()))

    assert "up to −$608 / month" in page
    assert "if the run time doesn&#x27;t change; no saving if it runs 2× slower or more" in page


def test_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    src = tmp_path / "estimate.json"
    out = tmp_path / "report.html"
    src.write_text(json.dumps(worked_example()), encoding="utf-8")

    pe.main(["summary", str(src)])
    assert "Expected about $2,291.39" in capsys.readouterr().out

    pe.main(["report", str(src), "--out", str(out)])
    assert out.read_text(encoding="utf-8").startswith("<!doctype html>")
