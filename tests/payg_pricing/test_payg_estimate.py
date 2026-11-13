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
    with pytest.raises(ValueError, match="no runs"):
        pe.run_stats({"name": "j", "runs": []})


def test_job_that_never_succeeded_is_billed_for_its_failed_runs() -> None:
    stats = pe.run_stats({"name": "j", "runs": [{"minutes": 0.2, "status": "failed"}] * 4})

    assert stats["never_succeeded"] is True
    assert stats["failed_share"] == 1
    assert stats["failed_min"] == pytest.approx(0.2)


# --- event triggers --------------------------------------------------------------------------

DAILY_RUNS = 365 / 12


def job(name: str, schedule: dict | list, runs: list[dict] | None = None) -> dict:
    return {
        "name": name,
        "schedule": schedule,
        "size": "small",
        "multiplier": 1,
        "runs": runs or [{"minutes": 1, "status": "ok"}],
    }


def runs_with(failed: int, ok: int, failed_min: float = 0.5, ok_min: float = 1) -> list[dict]:
    return [{"minutes": failed_min, "status": "failed"}] * failed + [
        {"minutes": ok_min, "status": "ok"}
    ] * ok


def sap_example() -> dict:
    """The PR example: an inspector agent that runs each time either of two loads fails."""
    return {
        "rate_usd_per_hour": 10,
        "jobs": [
            job("business_partner", every(1, "days"), runs_with(failed=3, ok=7)),
            job("bp_address", every(1, "days"), runs_with(failed=4, ok=0, failed_min=0.2)),
            job(
                "job_inspector",
                {"on_failure_of": ["business_partner", "bp_address"]},
                [{"minutes": 0.7, "status": "ok"}],
            ),
        ],
    }


def runs_of(est: dict) -> dict[str, float]:
    return {j["name"]: j["runs_month"] for j in est["jobs"]}


def test_on_failure_of_runs_once_per_upstream_failure() -> None:
    runs = runs_of(pe.estimate(sap_example()))

    # 30% of business_partner's runs fail and all of bp_address's: not 2 x the daily runs
    assert runs["job_inspector"] == pytest.approx(DAILY_RUNS * (0.3 + 1.0))


@pytest.mark.parametrize(
    "event, share",
    [("on_success_of", 0.7), ("on_failure_of", 0.3), ("on_completion_of", 1.0)],
)
def test_each_event_trigger_follows_its_share(event: str, share: float) -> None:
    data = {
        "rate_usd_per_hour": 10,
        "jobs": [
            job("load", every(1, "hours"), runs_with(failed=3, ok=7)),
            job("after", {event: "load"}),
        ],
    }

    assert runs_of(pe.estimate(data))["after"] == pytest.approx(730 * share)


def test_event_triggers_chain() -> None:
    data = {
        "rate_usd_per_hour": 10,
        "jobs": [
            job("ingest", every(1, "days"), runs_with(failed=1, ok=9)),
            job("transform", {"on_success_of": "ingest"}, runs_with(failed=1, ok=1)),
            job("report", {"on_completion_of": "transform"}),
        ],
    }
    runs = runs_of(pe.estimate(data))

    assert runs["transform"] == pytest.approx(DAILY_RUNS * 0.9)
    assert runs["report"] == pytest.approx(DAILY_RUNS * 0.9)


def test_a_list_of_triggers_adds_up() -> None:
    data = {
        "rate_usd_per_hour": 10,
        "jobs": [
            job("backfill", every(1, "days")),
            job("daily_load", [{"cron": "0 8 * * *"}, {"on_success_of": "backfill"}]),
        ],
    }
    est = pe.estimate(data)

    assert runs_of(est)["daily_load"] == pytest.approx(2 * DAILY_RUNS)
    assert est["jobs"][1]["label"] == "daily + when backfill succeeds"


def test_event_labels() -> None:
    assert pe.schedule_label({"on_failure_of": ["a", "b"]}) == "when a or b fails"
    assert pe.schedule_label({"on_success_of": "a"}) == "when a succeeds"
    assert pe.schedule_label({"on_completion_of": "a"}) == "when a finishes"


def test_assumed_upstream_can_give_a_failure_share() -> None:
    data = {
        "rate_usd_per_hour": 10,
        "jobs": [
            {
                "name": "load",
                "schedule": every(1, "days"),
                "size": "small",
                "multiplier": 1,
                "assumed": {"avg_minutes": 5, "failed_share": 0.1},
            },
            job("inspector", {"on_failure_of": "load"}),
        ],
    }
    est = pe.estimate(data)

    assert runs_of(est)["inspector"] == pytest.approx(DAILY_RUNS * 0.1)
    assert "and so is its 10% failure share" in " ".join(est["assumptions"])


@pytest.mark.parametrize(
    "jobs, error",
    [
        ([job("a", {"on_failure_of": "nope"})], "not in jobs"),
        ([job("a", {"on_success_of": "b"}), job("b", {"on_success_of": "a"})], "loop"),
        ([job("a", {"on_failure_of": "a"})], "loop"),
        (
            [
                {**job("dash", {"always_on_hours_per_day": 8}), "runs": None},
                job("a", {"on_failure_of": "dash"}),
            ],
            "always-on",
        ),
        ([job("a", {"on_failure_of": []})], "no upstream"),
        ([job("a", every(1, "days")), job("a", every(1, "days"))], "unique"),
    ],
)
def test_bad_event_triggers_fail_loudly(jobs: list[dict], error: str) -> None:
    with pytest.raises(ValueError, match=error):
        pe.estimate({"rate_usd_per_hour": 10, "jobs": jobs})


def test_runs_per_month_refuses_event_triggers() -> None:
    with pytest.raises(ValueError, match="other jobs"):
        pe.runs_per_month({"on_failure_of": "a"})


def test_job_that_never_succeeded_in_the_estimate() -> None:
    est = pe.estimate(sap_example())
    bp = {j["name"]: j for j in est["jobs"]}["bp_address"]

    assert bp["hours_expected"] == pytest.approx(DAILY_RUNS * 0.2 / 60)
    md = pe.summary(est)
    assert "never succeeded (0.2 min per failed run)" in md
    assert "bp_address: all 4 recent runs failed" in md
    assert "its cost once it works is unknown" in md
    assert (
        "job_inspector: runs each time business_partner or bp_address fails; failure share"
        " from their recent runs (business_partner 30%, bp_address 100%)." in md
    )


def test_report_shows_never_succeeded_and_event_label() -> None:
    page = pe.report(pe.estimate(sap_example()))

    assert "never succeeded (0.2 min per failed run)</td>" in page
    assert "min per failed run) min" not in page
    assert "when business_partner or bp_address fails" in page
    assert '<td class="num">1 min</td>' in page


def test_what_if_table_moves_event_jobs_with_their_upstream() -> None:
    est = pe.estimate(sap_example())
    ladder = {row["job"]: row["usd"] for row in est["ladder"]}
    hourly = [label for label, _ in pe.LADDER].index("Hourly")

    # both loads hourly: the inspector runs 730 x (30% + 100%) times, 0.7 min each, $10/h
    assert ladder["job_inspector"][hourly] == pytest.approx(730 * 1.3 * 0.7 / 60 * 10)


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


def test_cadence_lever_on_an_upstream_saves_on_its_event_jobs_too() -> None:
    # a daily load that fails 40% of the time, an inspector on failure, a dq check on success
    def pipeline(load_schedule: dict) -> dict:
        return {
            "rate_usd_per_hour": 10,
            "jobs": [
                job("load", load_schedule, runs_with(failed=4, ok=6, failed_min=5, ok_min=10)),
                job("inspector", {"on_failure_of": ["load"]}, [{"minutes": 3, "status": "ok"}]),
                job("dq", {"on_success_of": ["load"]}, [{"minutes": 4, "status": "ok"}]),
            ],
            "levers": [{"job": "load", "schedule": every(2, "days")}],
        }

    est = pe.estimate(pipeline(every(1, "days")))
    after = pe.estimate(pipeline(every(2, "days")))["usd_expected"]

    # the saving is what the whole estimate drops by, not only the load's own share
    assert est["savings"][0]["usd_per_month"] == round(est["usd_expected"] - after, 2)


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
