"""Compute a PAYG cost estimate from workspace facts, and print it or render it as HTML.

Every number in the estimate comes from this script. The agent only copies facts into a JSON
file (schedules, raw run times, instance sizes, the customer's own estimates) and chooses which
changes to propose; it never does arithmetic.

    uv run python <this folder>/payg_estimate.py summary reports/payg-estimate.json
    uv run python <this folder>/payg_estimate.py report reports/payg-estimate.json \\
        --out reports/payg-cost-estimate.html

Input (JSON):

    {
      "currency": "EUR",                           # "USD" (US) or "EUR" (EU): ask the user
      "rate_per_hour": 10,                         # from the Price section of SKILL.md
      "date": "2026-11-11",
      "title": "Acme analytics",                   # optional, shown in the report header
      "jobs": [
        {"name": "orders_sync",
         "schedule": {"every": 15, "unit": "minutes"},       # or "hours" / "days"
         "size": "small", "multiplier": 1,                   # multiplier from the docs
         "runs": [{"minutes": 2.1, "status": "ok"},          # recent runs, copied as listed
                  {"minutes": 0.4, "status": "failed"}]},
        {"name": "weekday_report", "schedule": {"cron": "0 9 * * 1-5"},
         "size": "small", "multiplier": 1,
         "assumed": {"avg_minutes": 10, "slow_minutes": 15}}, # customer's estimate, no runs yet
        {"name": "dashboard", "schedule": {"always_on_hours_per_day": 8},
         "size": "medium", "multiplier": 2},
        {"name": "job_inspector",                           # event trigger: job.fail
         "schedule": {"on_failure_of": ["orders_sync", "weekday_report"]},
         "size": "small", "multiplier": 1,                   # also on_success_of,
         "runs": [{"minutes": 0.7, "status": "ok"}]}         # on_completion_of
      ],                                                    # "schedule" may be a list: any
                                                            # trigger fires its own run
      "levers": [                                  # changes to price; the script computes savings
        {"job": "orders_sync", "schedule": {"every": 30, "unit": "minutes"}},
        {"job": "orders_sync", "size": "small", "multiplier": 1},
        {"job": "dashboard", "always_on_hours_per_day": 4},
        {"label": "Incremental loading for orders_sync", "unquantified": true}
      ],
      "engineering": {"hours_per_month": 40, "hourly_rate": 100},   # optional
      "notes": ["Durations from the last 20 runs per job."]             # optional, no numbers
    }

Standard library plus croniter, which ships with dlt, so every dlt workspace has it.
"""

import argparse
import html
import json
import math
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from string import Template

from croniter import croniter

TEMPLATE = Path(__file__).with_name("report-template.html")
DAYS_PER_MONTH = 365 / 12  # the average month, so monthly and yearly crons count right
MINUTES_PER_MONTH = DAYS_PER_MONTH * 24 * 60
CRON_YEAR = 2026  # any non-leap year: every date and month once
UNIT_MINUTES = {"minutes": 1, "hours": 60, "days": 1440}
LADDER = [
    ("Every 15 min", {"every": 15, "unit": "minutes"}),
    ("Hourly", {"every": 1, "unit": "hours"}),
    ("Every 6 h", {"every": 6, "unit": "hours"}),
    ("Daily", {"every": 1, "unit": "days"}),
]
FEW_RUNS = 5
CURRENCIES = {"USD": "$", "EUR": "€"}  # the workspace's region decides: US dollars, EU euros


# --- schedules -------------------------------------------------------------------------------


def _cron_days(expr: str) -> list[int]:
    """Runs on each day of a full year, so every month and every day of the month counts."""
    if len(expr.split()) != 5 or not croniter.is_valid(expr):
        raise ValueError(f"schedule cron {expr!r} is not a valid 5-field cron")
    minute, hour = croniter.expand(expr)[0][:2]
    per_day_max = (60 if minute == ["*"] else len(minute)) * (24 if hour == ["*"] else len(hour))
    first = datetime(
        CRON_YEAR, 1, 1, 0 if hour == ["*"] else hour[0], 0 if minute == ["*"] else minute[0]
    )
    days = (date(CRON_YEAR + 1, 1, 1) - date(CRON_YEAR, 1, 1)).days
    # whether the job runs on a day only depends on the day fields, so check its first time
    return [
        per_day_max if croniter.match(expr, first + timedelta(days=d)) else 0 for d in range(days)
    ]


def _cron_label(expr: str) -> str:
    per_day = _cron_days(expr)
    days = set(per_day)
    if len(days) == 1:  # the same number of runs every day
        k = per_day[0]
        return "daily" if k == 1 else "hourly" if k == 24 else f"{k}× a day"
    per_year = sum(per_day)
    if per_year < 12:
        return f"{per_year}× a year"
    return f"{_num(per_year / 12)}× a month"


# event triggers, as the platform names them: job.success, job.fail, job.completed
EVENTS = {"on_success_of": "succeeds", "on_failure_of": "fails", "on_completion_of": "finishes"}


def _triggers(schedule: dict | list) -> list[dict]:
    """A job's triggers; a list means any of them starts its own run."""
    triggers = schedule if isinstance(schedule, list) else [schedule]
    if not triggers or any(not isinstance(t, dict) for t in triggers):
        raise ValueError(f"schedule {schedule!r} needs one trigger or a list of triggers")
    return triggers


def _event(trigger: dict) -> tuple[str, list[str]] | None:
    """The event and the upstream job names of an event trigger, or None for a time trigger."""
    for key in EVENTS:
        if key in trigger:
            names = trigger[key]
            names = [names] if isinstance(names, str) else list(names)
            if not names:
                raise ValueError(f"trigger {trigger!r} names no upstream job")
            return key, names
    return None


def _is_always_on(schedule: dict | list) -> bool:
    return isinstance(schedule, dict) and "always_on_hours_per_day" in schedule


def runs_per_month(schedule: dict) -> float:
    """Runs in an average month for a time trigger; always-on jobs have none."""
    if _event(schedule):
        raise ValueError("event triggers depend on other jobs; their runs come from estimate()")
    if "always_on_hours_per_day" in schedule:
        return 0
    if "cron" in schedule:
        return sum(_cron_days(schedule["cron"])) / 12
    unit = schedule.get("unit")
    if "every" not in schedule or unit not in UNIT_MINUTES:
        raise ValueError(f"schedule {schedule!r} needs 'every' and a unit in {list(UNIT_MINUTES)}")
    return MINUTES_PER_MONTH / (float(schedule["every"]) * UNIT_MINUTES[unit])


def schedule_label(schedule: dict | list) -> str:
    if isinstance(schedule, list):
        return " + ".join(schedule_label(t) for t in _triggers(schedule))
    event = _event(schedule)
    if event:
        return f"when {' or '.join(event[1])} {EVENTS[event[0]]}"
    if "always_on_hours_per_day" in schedule:
        return "always on"
    if "cron" in schedule:
        return _cron_label(schedule["cron"])
    n, unit = schedule["every"], schedule["unit"]
    if unit == "minutes":
        return f"every {_num(n)} min"
    if unit == "hours":
        return "hourly" if n == 1 else f"every {_num(n)} h"
    return "daily" if n == 1 else f"every {_num(n)} days"


# --- run statistics --------------------------------------------------------------------------


def run_stats(job: dict) -> dict:
    """Average and slow run time, failure share and failed-run time from raw runs."""
    if "assumed" in job:
        a = job["assumed"]
        avg = float(a["avg_minutes"])
        slow = float(a.get("slow_minutes", avg))
        share = float(a.get("failed_share", 0))
        return {
            "avg_min": avg,
            "slow_min": slow,
            "failed_share": share,
            # a failed run is billed for the time it ran; without data, assume a full run
            "failed_min": float(a.get("failed_minutes", avg)) if share else 0.0,
            "sample": 0,
            "few_runs": False,
            "assumed": True,
            "never_succeeded": False,
        }
    runs = job.get("runs") or []
    ok = sorted(float(r["minutes"]) for r in runs if r.get("status", "ok") == "ok")
    failed = [float(r["minutes"]) for r in runs if r.get("status", "ok") != "ok"]
    if not runs:
        raise ValueError(
            f"job {job.get('name', '?')!r} has no runs; ask the customer for run time"
            " and pass it as 'assumed'"
        )
    if not ok:
        # every run failed: it is billed for the failed time; its cost once it works is unknown
        return {
            "avg_min": 0.0,
            "slow_min": 0.0,
            "failed_share": 1.0,
            "failed_min": sum(failed) / len(failed),
            "sample": len(runs),
            "few_runs": False,
            "assumed": False,
            "never_succeeded": True,
        }
    few = len(ok) < FEW_RUNS
    slow = ok[-1] if few else ok[math.ceil(0.9 * len(ok)) - 1]  # 90th percentile, nearest rank
    return {
        "avg_min": sum(ok) / len(ok),
        "slow_min": slow,
        "failed_share": len(failed) / len(runs),
        "failed_min": sum(failed) / len(failed) if failed else 0.0,
        "sample": len(runs),
        "few_runs": few,
        "assumed": False,
        "never_succeeded": False,
    }


# --- the estimate ----------------------------------------------------------------------------


def _hours(
    runs: float, schedule: dict | list, stats: dict | None, multiplier: float
) -> tuple[float, float]:
    """Charged hours per month, expected and heavy month."""
    if _is_always_on(schedule):
        h = float(schedule["always_on_hours_per_day"]) * DAYS_PER_MONTH * multiplier
        return h, h
    assert stats is not None
    failed_h = runs * stats["failed_share"] * stats["failed_min"] / 60
    ok_runs = runs * (1 - stats["failed_share"])  # failed runs are counted once, above
    expected = (ok_runs * stats["avg_min"] / 60 + failed_h) * multiplier
    high = (ok_runs * stats["slow_min"] / 60 + failed_h) * multiplier
    return expected, high


class _Runs:
    """Runs per month for every job, following event triggers back to the scheduled jobs."""

    def __init__(self, schedules: dict[str, dict | list], stats: dict[str, dict | None]):
        self.schedules, self.stats = schedules, stats

    def of(self, name: str, cadence: dict | None = None, path: tuple[str, ...] = ()) -> float:
        """Runs of a job; with a cadence, every time trigger upstream runs at that cadence."""
        if name in path:
            raise ValueError(f"event triggers loop: {' -> '.join((*path, name))}")
        schedule = self.schedules[name]
        if _is_always_on(schedule):
            return 0.0
        total, timed = 0.0, []
        for trigger in _triggers(schedule):
            event = _event(trigger)
            if event is None:
                timed.append(trigger)
                continue
            key, upstream = event
            for up in upstream:
                if up not in self.schedules:
                    raise ValueError(f"job {name!r} follows {up!r}, which is not in jobs")
                up_stats = self.stats[up]
                if up_stats is None:
                    raise ValueError(
                        f"job {name!r} follows always-on job {up!r}, which has no runs"
                    )
                share = up_stats["failed_share"]
                factor = {"on_success_of": 1 - share, "on_failure_of": share}.get(key, 1.0)
                total += self.of(up, cadence, (*path, name)) * factor
        if timed:
            total += runs_per_month(cadence) if cadence else sum(runs_per_month(t) for t in timed)
        return total


def _need(obj: dict, key: str, what: str) -> float:
    if obj.get(key) is None:
        raise ValueError(f"{what} is missing {key!r}")
    return float(obj[key])


def _lever(lever: dict, jobs: dict[str, dict], counter: _Runs, rate: float) -> dict:
    if lever.get("unquantified"):
        return {"label": lever["label"], "cost_per_month": None, "break_even_slowdown": None}
    name = lever.get("job")
    if name not in jobs:
        raise ValueError(f"lever names job {name!r}, which is not in jobs")
    job = jobs[name]
    schedule, mult = job["schedule"], job["multiplier"]
    # a smaller instance may run slower; the saving assumes the same run time, so it is an
    # upper bound, and it is gone once the run is old/new multiplier times slower
    break_even = None
    if "schedule" in lever:
        schedule = lever["schedule"]
        label = f"{name} {schedule_label(schedule)} instead of {schedule_label(job['schedule'])}"
    elif "multiplier" in lever:
        mult = _need(lever, "multiplier", f"lever for {name!r}")
        label = f"{name} on {lever.get('size', '?')} instead of {job.get('size', '?')} (if it fits)"
        if 0 < mult < job["multiplier"]:
            break_even = job["multiplier"] / mult
    elif "always_on_hours_per_day" in lever:
        schedule = {"always_on_hours_per_day": lever["always_on_hours_per_day"]}
        label = (
            f"{name} up {_num(lever['always_on_hours_per_day'])} h/day instead of "
            f"{_num(job['schedule']['always_on_hours_per_day'])} h/day"
        )
    else:
        raise ValueError(f"lever for {name!r} changes nothing the script can price")
    # re-price every job: event-triggered jobs downstream follow a new cadence
    schedules = {**counter.schedules, name: schedule}
    changed = _Runs(schedules, counter.stats)
    old_total = sum(j["hours_expected"] for j in jobs.values())
    new_total = sum(
        _hours(changed.of(n), schedules[n], j["stats"], mult if n == name else j["multiplier"])[0]
        for n, j in jobs.items()
    )
    return {
        "label": lever.get("label", label),
        "cost_per_month": round((old_total - new_total) * rate, 2),
        "break_even_slowdown": break_even,
    }


def estimate(data: dict) -> dict:
    """All figures for the chat summary and the report."""
    currency = data.get("currency")
    if currency not in CURRENCIES:
        raise ValueError(
            f"currency {currency!r} must be one of {list(CURRENCIES)}; ask whether the workspace"
            " runs in the US (USD) or the EU (EUR)"
        )
    rate = _need(data, "rate_per_hour", "the estimate")
    names = [raw.get("name") for raw in data["jobs"]]
    if len(set(names)) != len(names):
        raise ValueError("job names must be unique")
    schedules = {raw["name"]: raw.get("schedule") or {} for raw in data["jobs"]}
    stats_by_name = {
        raw["name"]: None if _is_always_on(schedules[raw["name"]]) else run_stats(raw)
        for raw in data["jobs"]
    }
    counter = _Runs(schedules, stats_by_name)
    jobs = []
    for raw in data["jobs"]:
        what = f"job {raw.get('name', '?')!r}"
        schedule = schedules[raw["name"]]
        mult = _need(raw, "multiplier", what)
        stats = stats_by_name[raw["name"]]
        runs = counter.of(raw["name"])
        expected, high = _hours(runs, schedule, stats, mult)
        jobs.append({
            **raw,
            "schedule": schedule,
            "multiplier": mult,
            "stats": stats,
            "runs_month": runs,
            "label": schedule_label(schedule),
            "hours_expected": expected,
            "hours_high": high,
            "cost_expected": expected * rate,
            "cost_high": high * rate,
        })

    hours_expected = sum(j["hours_expected"] for j in jobs)
    hours_high = sum(j["hours_high"] for j in jobs)
    runs_total = sum(j["runs_month"] for j in jobs)
    cost_expected = hours_expected * rate
    # always-on jobs have no runs, so their cost would inflate the cost per run
    cost_scheduled = sum(j["cost_expected"] for j in jobs if j["runs_month"])

    by_name = {j["name"]: j for j in jobs}
    ladder = [
        {
            "job": j["name"],
            # an event-triggered job follows its upstream jobs to the new cadence
            "cost": [
                _hours(counter.of(j["name"], s), j["schedule"], j["stats"], j["multiplier"])[0]
                * rate
                for _, s in LADDER
            ],
        }
        for j in jobs
        if j["stats"] is not None
    ]
    eng = data.get("engineering")
    engineering = None
    if eng:
        diy = float(eng["hours_per_month"]) * float(eng["hourly_rate"])
        engineering = {**eng, "cost_per_month": diy, "difference": diy - cost_expected}

    return {
        "currency": currency,
        "rate": rate,
        "date": data.get("date", ""),
        "title": data.get("title", ""),
        "jobs": jobs,
        "hours_expected": hours_expected,
        "hours_high": hours_high,
        "cost_expected": cost_expected,
        "cost_high": hours_high * rate,
        "runs_per_month": runs_total,
        "cost_per_job": cost_expected / len(jobs) if jobs else 0.0,
        "cost_per_run": cost_scheduled / runs_total if runs_total else None,
        "cost_per_day": cost_expected / DAYS_PER_MONTH,
        "ladder": ladder,
        "savings": [_lever(lv, by_name, counter, rate) for lv in data.get("levers") or []],
        "engineering": engineering,
        "assumptions": _assumptions(jobs, currency, rate, data.get("notes") or []),
    }


def _assumptions(jobs: list[dict], currency: str, rate: float, notes: list[str]) -> list[str]:
    money = _money(currency)
    sizes = {}
    for j in jobs:
        sizes.setdefault(j.get("size", "?"), j["multiplier"])
    lines = [
        f"{money(rate)} per runtime hour; {_num(DAYS_PER_MONTH)} days per month (365 / 12).",
        "Instance multipliers (from the dltHub docs): "
        + ", ".join(f"{s} {_num(m)}×" for s, m in sizes.items())
        + ".",
    ]
    for j in jobs:
        st = j["stats"]
        if st is None:
            lines.append(
                f"{j['name']}: uptime ({_num(j['schedule']['always_on_hours_per_day'])}"
                " h/day) is the customer's estimate."
            )
        elif st["never_succeeded"]:
            lines.append(
                f"{j['name']}: all {st['sample']} recent runs failed, billed for the time they ran;"
                " its cost once it works is unknown."
            )
        elif st["assumed"]:
            line = f"{j['name']}: run time is the customer's estimate"
            if st["failed_share"]:
                line += f", and so is its {st['failed_share']:.0%} failure share"
            lines.append(line + ".")
        else:
            line = f"{j['name']}: {st['sample']} recent runs"
            if st["few_runs"]:
                line += " (fewer than 5, so the slow run is the longest one)"
            if st["failed_share"]:
                line += f"; {st['failed_share']:.0%} failed, billed for the time they ran"
            lines.append(line + ".")
    by_name = {j["name"]: j for j in jobs}
    for j in jobs:
        for trigger in [] if _is_always_on(j["schedule"]) else _triggers(j["schedule"]):
            event = _event(trigger)
            if event is None or event[0] == "on_completion_of":
                continue
            shares = ", ".join(
                f"{up} {by_name[up]['stats']['failed_share']:.0%}" for up in event[1]
            )
            kind = "fails" if event[0] == "on_failure_of" else "succeeds"
            lines.append(
                f"{j['name']}: runs each time {' or '.join(event[1])} {kind}; failure share"
                f" from their recent runs ({shares})."
            )
    return lines + list(notes)


# --- formatting ------------------------------------------------------------------------------


def _money(currency: str):
    """A formatter for amounts in the estimate's currency: $1,234 or €1,234."""
    symbol = CURRENCIES[currency]

    def money(value: float, cents: bool = False) -> str:
        return f"{symbol}{value:,.2f}" if cents else f"{symbol}{value:,.0f}"

    return money


def _num(value: float) -> str:
    value = float(value)
    return f"{value:,.0f}" if value == int(value) else f"{value:,.1f}"


def _e(value: object) -> str:
    return html.escape(str(value))


def _run_time(j: dict) -> str:
    if j["stats"] is None:
        return f"{_num(j['schedule']['always_on_hours_per_day'])} h/day"
    if j["stats"]["never_succeeded"]:
        return f"never succeeded ({_num(j['stats']['failed_min'])} min per failed run)"
    return f"{_num(j['stats']['avg_min'])} / {_num(j['stats']['slow_min'])} min"


def summary(est: dict) -> str:
    """Markdown for the chat answer. The agent pastes it as is."""
    money = _money(est["currency"])
    out = ["**Assumptions**", *[f"- {a}" for a in est["assumptions"]], ""]
    out += [
        "| Job | Schedule | Runs/month | Average / slow run | Size | Hours/month | "
        f"{CURRENCIES[est['currency']]}/month |",
        "|---|---|---|---|---|---|---|",
    ]
    for j in est["jobs"]:
        runs = "—" if j["stats"] is None else _num(j["runs_month"])
        out.append(
            f"| {j['name']} | {j['label']} | {runs} | {_run_time(j)} | "
            f"{j.get('size', '?')} ({_num(j['multiplier'])}×) | "
            f"{j['hours_expected']:,.1f} | {money(j['cost_expected'], True)} |"
        )
    out.append(
        f"| **Total** | | {_num(est['runs_per_month'])} | | | "
        f"**{est['hours_expected']:,.1f}** | **{money(est['cost_expected'], True)}** |"
    )
    out += [
        "",
        f"**Expected about {money(est['cost_expected'], True)} per month; in a heavy month "
        f"up to about {money(est['cost_high'], True)}** (if runs take as long as the "
        "slowest 10%).",
    ]
    if est["ladder"]:
        out += [
            "",
            "**What each job would cost at another schedule**",
            "",
            "| Job | Now | " + " | ".join(n for n, _ in LADDER) + " |",
            "|---" * (len(LADDER) + 2) + "|",
        ]
        by_name = {j["name"]: j for j in est["jobs"]}
        for row in est["ladder"]:
            job = by_name[row["job"]]
            now = f"{money(job['cost_expected'], True)} ({job['label']})"
            cells = [money(u, True) for u in row["cost"]]
            out.append(f"| {row['job']} | {now} | " + " | ".join(cells) + " |")
    if est["savings"]:
        out += ["", "**Ways to cut cost**"]
        for s in est["savings"]:
            if s["cost_per_month"] is None:
                out.append(
                    f"- {s['label']}: saving depends on the new run time — measure after"
                    " the change."
                )
            elif s["break_even_slowdown"]:
                out.append(
                    f"- {s['label']}: saves up to {money(s['cost_per_month'], True)}/month"
                    f" {_upper_bound_note(s['break_even_slowdown'])}."
                )
            else:
                out.append(f"- {s['label']}: saves {money(s['cost_per_month'], True)}/month.")
    eng = est["engineering"]
    if eng:
        out += [
            "",
            f"**Engineering time:** doing it yourself "
            f"{_num(eng['hours_per_month'])} h × {money(float(eng['hourly_rate']))} = "
            f"{money(eng['cost_per_month'], True)}/month, compared with "
            f"{money(est['cost_expected'], True)} on dltHub (servers not included).",
        ]
    return "\n".join(out) + "\n"


def _upper_bound_note(slowdown: float) -> str:
    return f"if the run time doesn't change; no saving if it runs {_num(slowdown)}× slower or more"


def _bar(label: str, value: str, pct: float, css: str = "") -> str:
    pct = max(0.0, min(100.0, pct))
    return (
        f'<div class="bar"><div class="label"><span>{label}</span><b>{value}</b></div>'
        f'<div class="track"><div class="fill {css}" style="width:{pct:.1f}%"></div></div></div>'
    )


def report(est: dict) -> str:
    """The one-page HTML report. Every customer-supplied string is escaped."""
    money = _money(est["currency"])
    total = est["cost_expected"] or 1.0
    per_run = money(est["cost_per_run"], True) if est["cost_per_run"] is not None else "n/a"
    chips = [
        (money(est["cost_per_job"]), "per job / month"),
        (per_run, "per scheduled run"),
        (money(est["cost_per_day"]), "per day of fresh data"),
        (_num(round(est["hours_expected"], 1)), "runtime hours / month"),
    ]
    rows = []
    for j in est["jobs"]:
        if j["stats"] is None or j["stats"]["never_succeeded"]:
            avg = _run_time(j)
        else:
            avg = f"{_num(j['stats']['avg_min'])} min"
        share = 100 * j["cost_expected"] / total
        rows.append(
            f"<tr><td>{_e(j['name'])}</td><td>{_e(j['label'])}</td>"
            f'<td class="num">{"—" if j["stats"] is None else _num(j["runs_month"])}</td>'
            f'<td class="num">{_e(avg)}</td>'
            f'<td>{_e(j.get("size", ""))} <span class="tag">{_num(j["multiplier"])}×</span></td>'
            f'<td class="num">{_num(round(j["hours_expected"], 1))}</td>'
            f'<td class="num"><span class="share" style="width:{share * 0.6:.0f}px"></span>'
            f"{money(j['cost_expected'])}</td></tr>"
        )

    savings = ""
    if est["savings"]:
        bars = []
        for s in est["savings"]:
            saving = s["cost_per_month"]
            if saving is None:
                bars.append(_bar(_e(s["label"]), "measure after the change", 0))
            elif s["break_even_slowdown"]:
                label = (
                    f'{_e(s["label"])}<br><span class="tag">'
                    f"{_e(_upper_bound_note(s['break_even_slowdown']))}</span>"
                )
                bars.append(_bar(label, f"up to −{money(saving)} / month", 100 * saving / total))
            else:
                bars.append(_bar(_e(s["label"]), f"−{money(saving)} / month", 100 * saving / total))
        savings = (
            '<section><h2>Ways to lower it</h2><div class="bars">'
            + "".join(bars)
            + '</div><p class="note">Each option is a choice you make; nothing changes'
            " until you decide.</p></section>"
        )

    engineering = ""
    eng = est["engineering"]
    if eng:
        diy = eng["cost_per_month"]
        top = max(diy, est["cost_expected"]) or 1.0
        verdict = (
            f"dltHub costs {money(eng['difference'])} less per month than doing it yourself."
            if eng["difference"] > 0
            else "In this scenario, running it yourself is estimated to cost less in"
            " engineering time alone."
        )
        engineering = (
            '<section><h2>Engineering time</h2><div class="bars">'
            + _bar(
                "dltHub",
                f"{money(est['cost_expected'])} / month",
                100 * est["cost_expected"] / top,
                "dlt",
            )
            + _bar(
                f"Doing it yourself: {_num(eng['hours_per_month'])} h × "
                f"{money(float(eng['hourly_rate']))}",
                f"{money(diy)} / month",
                100 * diy / top,
                "diy",
            )
            + f'</div><div class="callout">{verdict}</div>'
            '<p class="note">Engineering hours and rate are your own estimate. Doing it yourself'
            " also needs servers to run on; their cost is not included here.</p></section>"
        )

    title = f" · {_e(est['title'])}" if est["title"] else ""
    values = {
        "title_line": f"Prepared {_e(est['date'])}{title}",
        "cost_expected": money(est["cost_expected"]),
        "cost_high": money(est["cost_high"]),
        "chips": "".join(f'<div class="chip"><b>{v}</b><span>{k}</span></div>' for v, k in chips),
        "rate_line": f"You pay {money(est['rate'])} per runtime hour, times the instance size"
        " multiplier.",
        "rate_short": money(est["rate"]),
        "job_rows": "".join(rows),
        "runs_total": _num(est["runs_per_month"]),
        "hours_expected": _num(round(est["hours_expected"], 1)),
        "savings_section": savings,
        "engineering_section": engineering,
        "assumption_items": "".join(f"<li>{_e(a)}</li>" for a in est["assumptions"]),
        "date": _e(est["date"]),
    }
    return Template(TEMPLATE.read_text(encoding="utf-8")).substitute(values)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("summary", help="print the estimate as markdown for the chat answer")
    s.add_argument("estimate", help="estimate JSON file")
    r = sub.add_parser("report", help="write the one-page HTML report")
    r.add_argument("estimate", help="estimate JSON file")
    r.add_argument("--out", default="reports/payg-cost-estimate.html", help="HTML file to write")
    args = parser.parse_args(argv)

    est = estimate(json.loads(Path(args.estimate).read_text(encoding="utf-8")))
    money = _money(est["currency"])
    if args.command == "summary":
        sys.stdout.write(summary(est))
        return
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report(est), encoding="utf-8")
    sys.stdout.write(
        f"Wrote {out}: about {money(est['cost_expected'], True)}/month, up to "
        f"{money(est['cost_high'], True)} in a heavy month\n"
    )


if __name__ == "__main__":
    main()
