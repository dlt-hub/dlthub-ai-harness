"""Compute a PAYG cost estimate from workspace facts, and print it or render it as HTML.

Every number in the estimate comes from this script. The agent only copies facts into a JSON
file (schedules, raw run times, instance sizes, the customer's own estimates) and chooses which
changes to propose; it never does arithmetic.

    uv run python <this folder>/payg_estimate.py summary reports/payg-estimate.json
    uv run python <this folder>/payg_estimate.py report reports/payg-estimate.json \\
        --out reports/payg-cost-estimate.html

Input (JSON):

    {
      "rate_usd_per_hour": 10,                     # from the Price section of SKILL.md
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
         "size": "medium", "multiplier": 2}
      ],
      "levers": [                                  # changes to price; the script computes savings
        {"job": "orders_sync", "schedule": {"every": 30, "unit": "minutes"}},
        {"job": "orders_sync", "size": "small", "multiplier": 1},
        {"job": "dashboard", "always_on_hours_per_day": 4},
        {"label": "Incremental loading for orders_sync", "unquantified": true}
      ],
      "engineering": {"hours_per_month": 40, "hourly_rate_usd": 100},   # optional
      "notes": ["Durations from the last 20 runs per job."]             # optional, no numbers
    }

Standard library only.
"""

import argparse
import html
import json
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path
from string import Template

TEMPLATE = Path(__file__).with_name("report-template.html")
DAYS_PER_MONTH = 30
MINUTES_PER_MONTH = DAYS_PER_MONTH * 24 * 60
# a fixed 30-day window starting on a Monday, so calendar crons count the same every time
CRON_WINDOW_START = datetime(2026, 1, 5)
UNIT_MINUTES = {"minutes": 1, "hours": 60, "days": 1440}
LADDER = [
    ("Every 15 min", {"every": 15, "unit": "minutes"}),
    ("Hourly", {"every": 1, "unit": "hours"}),
    ("Every 6 h", {"every": 6, "unit": "hours"}),
    ("Daily", {"every": 1, "unit": "days"}),
]
FEW_RUNS = 5


# --- schedules -------------------------------------------------------------------------------


def _cron_field(field: str, low: int, high: int) -> set[int]:
    values: set[int] = set()
    for part in field.split(","):
        step = 1
        if "/" in part:
            part, step_s = part.split("/")
            step = int(step_s)
        if part == "*":
            start, end = low, high
        elif "-" in part:
            start, end = (int(x) for x in part.split("-"))
        else:
            start = end = int(part)
        values.update(range(start, end + 1, step))
    return values


def _cron_days(expr: str) -> list[int]:
    """Runs on each of the 30 days in the window."""
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError(f"schedule cron {expr!r} must have 5 fields")
    minute, hour, dom, month, dow = fields
    minutes, hours = _cron_field(minute, 0, 59), _cron_field(hour, 0, 23)
    doms, months = _cron_field(dom, 1, 31), _cron_field(month, 1, 12)
    dows = {d % 7 for d in _cron_field(dow, 0, 7)}  # 0 and 7 are both Sunday
    dom_any, dow_any = dom == "*", dow == "*"
    per_day = []
    for day in range(DAYS_PER_MONTH):
        date = CRON_WINDOW_START + timedelta(days=day)
        cron_dow = (date.weekday() + 1) % 7  # cron: Sunday = 0
        dom_ok, dow_ok = date.day in doms, cron_dow in dows
        # standard cron: when both day fields are restricted, either one matching is enough
        day_ok = (dom_ok or dow_ok) if not (dom_any or dow_any) else (dom_ok and dow_ok)
        per_day.append(len(minutes) * len(hours) if date.month in months and day_ok else 0)
    return per_day


def _cron_label(expr: str) -> str:
    per_day = _cron_days(expr)
    days = set(per_day)
    if len(days) == 1:  # the same number of runs every day
        k = per_day[0]
        return "daily" if k == 1 else "hourly" if k == 24 else f"{k}× a day"
    return f"{sum(per_day)}× a month"


def runs_per_month(schedule: dict) -> int:
    """Runs in 30 days for a schedule; always-on jobs have none."""
    if "always_on_hours_per_day" in schedule:
        return 0
    if "cron" in schedule:
        return sum(_cron_days(schedule["cron"]))
    unit = schedule.get("unit")
    if "every" not in schedule or unit not in UNIT_MINUTES:
        raise ValueError(f"schedule {schedule!r} needs 'every' and a unit in {list(UNIT_MINUTES)}")
    return math.ceil(MINUTES_PER_MONTH / (float(schedule["every"]) * UNIT_MINUTES[unit]))


def schedule_label(schedule: dict) -> str:
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
        return {
            "avg_min": avg,
            "slow_min": slow,
            "failed_share": 0.0,
            "failed_min": 0.0,
            "sample": 0,
            "few_runs": False,
            "assumed": True,
        }
    runs = job.get("runs") or []
    ok = sorted(float(r["minutes"]) for r in runs if r.get("status", "ok") == "ok")
    failed = [float(r["minutes"]) for r in runs if r.get("status", "ok") != "ok"]
    if not ok:
        raise ValueError(
            f"job {job.get('name', '?')!r} has no successful runs; ask the customer for run time"
            " and pass it as 'assumed'"
        )
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
    }


# --- the estimate ----------------------------------------------------------------------------


def _hours(schedule: dict, stats: dict | None, multiplier: float) -> tuple[float, float]:
    """Charged hours per month, expected and heavy month."""
    if "always_on_hours_per_day" in schedule:
        h = float(schedule["always_on_hours_per_day"]) * DAYS_PER_MONTH * multiplier
        return h, h
    assert stats is not None
    runs = runs_per_month(schedule)
    failed_h = runs * stats["failed_share"] * stats["failed_min"] / 60
    ok_runs = runs * (1 - stats["failed_share"])  # failed runs are counted once, above
    expected = (ok_runs * stats["avg_min"] / 60 + failed_h) * multiplier
    high = (ok_runs * stats["slow_min"] / 60 + failed_h) * multiplier
    return expected, high


def _need(obj: dict, key: str, what: str) -> float:
    if obj.get(key) is None:
        raise ValueError(f"{what} is missing {key!r}")
    return float(obj[key])


def _lever(lever: dict, jobs: dict[str, dict], rate: float) -> dict:
    if lever.get("unquantified"):
        return {"label": lever["label"], "usd_per_month": None}
    name = lever.get("job")
    if name not in jobs:
        raise ValueError(f"lever names job {name!r}, which is not in jobs")
    job = jobs[name]
    schedule, mult = job["schedule"], job["multiplier"]
    if "schedule" in lever:
        schedule = lever["schedule"]
        label = f"{name} {schedule_label(schedule)} instead of {schedule_label(job['schedule'])}"
    elif "multiplier" in lever:
        mult = _need(lever, "multiplier", f"lever for {name!r}")
        label = f"{name} on {lever.get('size', '?')} instead of {job.get('size', '?')} (if it fits)"
    elif "always_on_hours_per_day" in lever:
        schedule = {"always_on_hours_per_day": lever["always_on_hours_per_day"]}
        label = (
            f"{name} up {_num(lever['always_on_hours_per_day'])} h/day instead of "
            f"{_num(job['schedule']['always_on_hours_per_day'])} h/day"
        )
    else:
        raise ValueError(f"lever for {name!r} changes nothing the script can price")
    new_expected, _ = _hours(schedule, job["stats"], mult)
    return {
        "label": lever.get("label", label),
        "usd_per_month": round((job["hours_expected"] - new_expected) * rate, 2),
    }


def estimate(data: dict) -> dict:
    """All figures for the chat summary and the report."""
    rate = float(data["rate_usd_per_hour"])
    jobs = []
    for raw in data["jobs"]:
        what = f"job {raw.get('name', '?')!r}"
        schedule = raw.get("schedule") or {}
        mult = _need(raw, "multiplier", what)
        stats = None if "always_on_hours_per_day" in schedule else run_stats(raw)
        expected, high = _hours(schedule, stats, mult)
        jobs.append({
            **raw,
            "schedule": schedule,
            "multiplier": mult,
            "stats": stats,
            "runs_month": runs_per_month(schedule),
            "label": schedule_label(schedule),
            "hours_expected": expected,
            "hours_high": high,
            "usd_expected": expected * rate,
            "usd_high": high * rate,
        })

    hours_expected = sum(j["hours_expected"] for j in jobs)
    hours_high = sum(j["hours_high"] for j in jobs)
    runs_total = sum(j["runs_month"] for j in jobs)
    usd_expected = hours_expected * rate
    # always-on jobs have no runs, so their cost would inflate the cost per run
    usd_scheduled = sum(j["usd_expected"] for j in jobs if j["runs_month"])

    by_name = {j["name"]: j for j in jobs}
    ladder = [
        {
            "job": j["name"],
            "usd": [_hours(s, j["stats"], j["multiplier"])[0] * rate for _, s in LADDER],
            "current": [runs_per_month(s) == j["runs_month"] for _, s in LADDER],
        }
        for j in jobs
        if j["stats"] is not None
    ]
    eng = data.get("engineering")
    engineering = None
    if eng:
        diy = float(eng["hours_per_month"]) * float(eng["hourly_rate_usd"])
        engineering = {**eng, "usd_per_month": diy, "difference_usd": diy - usd_expected}

    return {
        "rate": rate,
        "date": data.get("date", ""),
        "title": data.get("title", ""),
        "jobs": jobs,
        "hours_expected": hours_expected,
        "hours_high": hours_high,
        "usd_expected": usd_expected,
        "usd_high": hours_high * rate,
        "runs_per_month": runs_total,
        "usd_per_job": usd_expected / len(jobs) if jobs else 0.0,
        "usd_per_run": usd_scheduled / runs_total if runs_total else None,
        "usd_per_day": usd_expected / DAYS_PER_MONTH,
        "ladder": ladder,
        "savings": [_lever(lv, by_name, rate) for lv in data.get("levers") or []],
        "engineering": engineering,
        "assumptions": _assumptions(jobs, rate, data.get("notes") or []),
    }


def _assumptions(jobs: list[dict], rate: float, notes: list[str]) -> list[str]:
    sizes = {}
    for j in jobs:
        sizes.setdefault(j.get("size", "?"), j["multiplier"])
    lines = [
        f"{_usd(rate)} per runtime hour; {DAYS_PER_MONTH} days per month.",
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
        elif st["assumed"]:
            lines.append(f"{j['name']}: run time is the customer's estimate.")
        else:
            line = f"{j['name']}: {st['sample']} recent runs"
            if st["few_runs"]:
                line += " (fewer than 5, so the slow run is the longest one)"
            if st["failed_share"]:
                line += f"; {st['failed_share']:.0%} failed, billed for the time they ran"
            lines.append(line + ".")
    return lines + list(notes)


# --- formatting ------------------------------------------------------------------------------


def _usd(value: float, cents: bool = False) -> str:
    return f"${value:,.2f}" if cents else f"${value:,.0f}"


def _num(value: float) -> str:
    value = float(value)
    return f"{value:,.0f}" if value == int(value) else f"{value:,.1f}"


def _e(value: object) -> str:
    return html.escape(str(value))


def _run_time(j: dict) -> str:
    if j["stats"] is None:
        return f"{_num(j['schedule']['always_on_hours_per_day'])} h/day"
    return f"{_num(j['stats']['avg_min'])} / {_num(j['stats']['slow_min'])} min"


def summary(est: dict) -> str:
    """Markdown for the chat answer. The agent pastes it as is."""
    out = ["**Assumptions**", *[f"- {a}" for a in est["assumptions"]], ""]
    out += [
        "| Job | Schedule | Runs/month | Average / slow run | Size | Hours/month | $/month |",
        "|---|---|---|---|---|---|---|",
    ]
    for j in est["jobs"]:
        runs = "—" if j["stats"] is None else f"{j['runs_month']:,}"
        out.append(
            f"| {j['name']} | {j['label']} | {runs} | {_run_time(j)} | "
            f"{j.get('size', '?')} ({_num(j['multiplier'])}×) | "
            f"{j['hours_expected']:,.1f} | {_usd(j['usd_expected'], True)} |"
        )
    out.append(
        f"| **Total** | | {est['runs_per_month']:,} | | | "
        f"**{est['hours_expected']:,.1f}** | **{_usd(est['usd_expected'], True)}** |"
    )
    out += [
        "",
        f"**Expected about {_usd(est['usd_expected'], True)} per month; in a heavy month "
        f"up to about {_usd(est['usd_high'], True)}** (if runs take as long as the "
        "slowest 10%).",
    ]
    if est["ladder"]:
        out += [
            "",
            "| Job | " + " | ".join(n for n, _ in LADDER) + " |",
            "|---" * (len(LADDER) + 1) + "|",
        ]
        for row in est["ladder"]:
            cells = [
                f"**{_usd(u, True)}**" if cur else _usd(u, True)
                for u, cur in zip(row["usd"], row["current"])
            ]
            out.append(f"| {row['job']} | " + " | ".join(cells) + " |")
        out.append("\nCurrent schedule in bold.")
    if est["savings"]:
        out += ["", "**Ways to cut cost**"]
        for s in est["savings"]:
            if s["usd_per_month"] is None:
                out.append(
                    f"- {s['label']}: saving depends on the new run time — measure after"
                    " the change."
                )
            else:
                out.append(f"- {s['label']}: saves {_usd(s['usd_per_month'], True)}/month.")
    eng = est["engineering"]
    if eng:
        out += [
            "",
            f"**Engineering time:** doing it yourself "
            f"{_num(eng['hours_per_month'])} h × {_usd(float(eng['hourly_rate_usd']))} = "
            f"{_usd(eng['usd_per_month'], True)}/month, compared with "
            f"{_usd(est['usd_expected'], True)} on dltHub (servers not included).",
        ]
    return "\n".join(out) + "\n"


def _bar(label: str, value: str, pct: float, css: str = "") -> str:
    pct = max(0.0, min(100.0, pct))
    return (
        f'<div class="bar"><div class="label"><span>{label}</span><b>{value}</b></div>'
        f'<div class="track"><div class="fill {css}" style="width:{pct:.1f}%"></div></div></div>'
    )


def report(est: dict) -> str:
    """The one-page HTML report. Every customer-supplied string is escaped."""
    total = est["usd_expected"] or 1.0
    per_run = _usd(est["usd_per_run"], True) if est["usd_per_run"] is not None else "n/a"
    chips = [
        (_usd(est["usd_per_job"]), "per job / month"),
        (per_run, "per scheduled run"),
        (_usd(est["usd_per_day"]), "per day of fresh data"),
        (_num(round(est["hours_expected"], 1)), "runtime hours / month"),
    ]
    rows = []
    for j in est["jobs"]:
        avg = _run_time(j).split(" / ")[0] + ("" if j["stats"] is None else " min")
        share = 100 * j["usd_expected"] / total
        rows.append(
            f"<tr><td>{_e(j['name'])}</td><td>{_e(j['label'])}</td>"
            f'<td class="num">{"—" if j["stats"] is None else _num(j["runs_month"])}</td>'
            f'<td class="num">{_e(avg)}</td>'
            f'<td>{_e(j.get("size", ""))} <span class="tag">{_num(j["multiplier"])}×</span></td>'
            f'<td class="num">{_num(round(j["hours_expected"], 1))}</td>'
            f'<td class="num"><span class="share" style="width:{share * 0.6:.0f}px"></span>'
            f"{_usd(j['usd_expected'])}</td></tr>"
        )

    savings = ""
    if est["savings"]:
        bars = []
        for s in est["savings"]:
            usd = s["usd_per_month"]
            if usd is None:
                bars.append(_bar(_e(s["label"]), "measure after the change", 0))
            else:
                bars.append(_bar(_e(s["label"]), f"−{_usd(usd)} / month", 100 * usd / total))
        savings = (
            '<section><h2>Ways to lower it</h2><div class="bars">'
            + "".join(bars)
            + '</div><p class="note">Each option is a choice you make; nothing changes'
            " until you decide.</p></section>"
        )

    engineering = ""
    eng = est["engineering"]
    if eng:
        diy = eng["usd_per_month"]
        top = max(diy, est["usd_expected"]) or 1.0
        verdict = (
            f"dltHub costs {_usd(eng['difference_usd'])} less per month than doing it yourself."
            if eng["difference_usd"] > 0
            else "In this scenario, running it yourself is estimated to cost less in"
            " engineering time alone."
        )
        engineering = (
            '<section><h2>Engineering time</h2><div class="bars">'
            + _bar(
                "dltHub",
                f"{_usd(est['usd_expected'])} / month",
                100 * est["usd_expected"] / top,
                "dlt",
            )
            + _bar(
                f"Doing it yourself: {_num(eng['hours_per_month'])} h × "
                f"{_usd(float(eng['hourly_rate_usd']))}",
                f"{_usd(diy)} / month",
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
        "usd_expected": _usd(est["usd_expected"]),
        "usd_high": _usd(est["usd_high"]),
        "chips": "".join(f'<div class="chip"><b>{v}</b><span>{k}</span></div>' for v, k in chips),
        "rate_line": f"You pay {_usd(est['rate'])} per runtime hour, times the instance size"
        " multiplier.",
        "rate_short": _usd(est["rate"]),
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
    if args.command == "summary":
        sys.stdout.write(summary(est))
        return
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report(est), encoding="utf-8")
    sys.stdout.write(
        f"Wrote {out}: about {_usd(est['usd_expected'], True)}/month, up to "
        f"{_usd(est['usd_high'], True)} in a heavy month\n"
    )


if __name__ == "__main__":
    main()
