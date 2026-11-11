"""Render a PAYG cost estimate as a self-contained, one-page HTML report.

Usage: uv run python <this folder>/render_report.py estimate.json --out reports/payg-report.html

The input is the estimate the skill already worked out, as JSON:

    {
      "rate_usd_per_hour": 10,
      "date": "2026-11-11",
      "jobs": [
        {"name": "orders_sync", "cadence": "every 15 min", "runs_per_month": 2880,
         "avg_min": 2, "slow_min": 3, "size": "small", "multiplier": 1,
         "failed_share": 0.0, "failed_min": 0},
        {"name": "dashboard", "cadence": "always on", "uptime_hours_per_day": 8,
         "size": "medium", "multiplier": 2}
      ],
      "savings": [{"label": "orders_sync every 30 min", "usd_per_month": 480},
                  {"label": "Incremental loading", "usd_per_month": null}],
      "engineering": {"hours_per_month": 40, "hourly_rate_usd": 100},
      "assumptions": ["Durations from the last 20 successful runs."]
    }

`engineering`, `savings`, `assumptions`, `failed_share` and `failed_min` are optional. The script
does all the arithmetic, so the report always agrees with the formulas in SKILL.md. Standard
library only.
"""

import argparse
import html
import json
import sys
from pathlib import Path
from string import Template

TEMPLATE = Path(__file__).with_name("report-template.html")
DAYS_PER_MONTH = 30


def _need(job: dict, key: str) -> float:
    if job.get(key) is None:
        raise ValueError(f"job {job.get('name', '?')!r} is missing {key!r}")
    return float(job[key])


def compute(data: dict) -> dict:
    """Charged hours and cost per job and in total, plus per-unit figures."""
    rate = float(data["rate_usd_per_hour"])
    jobs = []
    for job in data["jobs"]:
        multiplier = _need(job, "multiplier")
        if "uptime_hours_per_day" in job:
            runs = 0.0
            expected = high = _need(job, "uptime_hours_per_day") * DAYS_PER_MONTH * multiplier
        else:
            runs = _need(job, "runs_per_month")
            avg, slow = _need(job, "avg_min"), _need(job, "slow_min")
            failed_share = float(job.get("failed_share") or 0)
            failed_min = float(job.get("failed_min") or 0)
            # failed runs are billed for the time they ran, and counted only once
            failed_h = runs * failed_share * failed_min / 60
            ok_runs = runs * (1 - failed_share)
            expected = (ok_runs * avg / 60 + failed_h) * multiplier
            high = (ok_runs * slow / 60 + failed_h) * multiplier
        jobs.append({
            **job,
            "runs": runs,
            "hours_expected": expected,
            "hours_high": high,
            "usd_expected": expected * rate,
            "usd_high": high * rate,
        })

    hours_expected = sum(j["hours_expected"] for j in jobs)
    hours_high = sum(j["hours_high"] for j in jobs)
    runs_total = sum(j["runs"] for j in jobs)
    usd_expected = hours_expected * rate
    # always-on jobs have no runs, so their cost would inflate the cost per run
    usd_scheduled = sum(j["usd_expected"] for j in jobs if j["runs"])
    est = {
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
        "savings": data.get("savings") or [],
        "assumptions": data.get("assumptions") or [],
        "engineering": None,
    }
    eng = data.get("engineering")
    if eng:
        diy = float(eng["hours_per_month"]) * float(eng["hourly_rate_usd"])
        est["engineering"] = {**eng, "usd_per_month": diy, "difference_usd": diy - usd_expected}
    return est


def _usd(value: float, cents: bool = False) -> str:
    return f"${value:,.2f}" if cents else f"${value:,.0f}"


def _num(value: float) -> str:
    return f"{value:,.0f}" if value == int(value) else f"{value:,.1f}"


def _e(value: object) -> str:
    return html.escape(str(value))


def _bar(label: str, value: str, pct: float, css: str = "") -> str:
    pct = max(0.0, min(100.0, pct))
    return (
        f'<div class="bar"><div class="label"><span>{label}</span><b>{value}</b></div>'
        f'<div class="track"><div class="fill {css}" style="width:{pct:.1f}%"></div></div></div>'
    )


def render(est: dict) -> str:
    """Fill the HTML template. Every customer-supplied string is escaped."""
    total = est["usd_expected"] or 1.0
    chips = [
        (_usd(est["usd_per_job"]), "per job / month"),
        (
            _usd(est["usd_per_run"], cents=True) if est["usd_per_run"] is not None else "n/a",
            "per scheduled run",
        ),
        (_usd(est["usd_per_day"]), "per day of fresh data"),
        (_num(round(est["hours_expected"], 1)), "runtime hours / month"),
    ]
    rows = []
    for j in est["jobs"]:
        always_on = "uptime_hours_per_day" in j
        avg = (
            f"{_num(j['uptime_hours_per_day'])} h/day" if always_on else f"{_num(j['avg_min'])} min"
        )
        share = 100 * j["usd_expected"] / total
        rows.append(
            f"<tr><td>{_e(j['name'])}</td><td>{_e(j.get('cadence', ''))}</td>"
            f'<td class="num">{"—" if always_on else _num(j["runs"])}</td>'
            f'<td class="num">{avg}</td>'
            f'<td>{_e(j.get("size", ""))} <span class="tag">{_num(j["multiplier"])}×</span></td>'
            f'<td class="num">{_num(round(j["hours_expected"], 1))}</td>'
            f'<td class="num"><span class="share" style="width:{share * 0.6:.0f}px"></span>'
            f"{_usd(j['usd_expected'])}</td></tr>"
        )

    savings = ""
    if est["savings"]:
        bars = []
        for s in est["savings"]:
            usd = s.get("usd_per_month")
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
                f"Doing it yourself: {_num(float(eng['hours_per_month']))} h × "
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
        "rate_line": f"{_usd(est['rate'])} per runtime hour, times the instance size multiplier.",
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
    parser.add_argument("estimate", help="estimate JSON file")
    parser.add_argument(
        "--out", default="reports/payg-cost-estimate.html", help="HTML file to write"
    )
    args = parser.parse_args(argv)

    data = json.loads(Path(args.estimate).read_text(encoding="utf-8"))
    est = compute(data)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(est), encoding="utf-8")
    sys.stdout.write(
        f"Wrote {out}: about {_usd(est['usd_expected'], cents=True)}/month, up to "
        f"{_usd(est['usd_high'], cents=True)} in a heavy month\n"
    )


if __name__ == "__main__":
    main()
