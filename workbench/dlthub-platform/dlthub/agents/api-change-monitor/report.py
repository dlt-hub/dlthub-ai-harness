"""Merge the per-API results of one api-change-monitor job into one report.

Each API that needed the model returns an agent output; an API whose notes the hook
ruled out entirely returns none. The report, its summary and its table are written
here in Python, so the shape holds on every run whatever the model wrote.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .redact import redact
from .tracking import DATE_FIELDS, key

# the order rows take in the table, most urgent first
IMPACT_ORDER = ["action_required", "unknown", "on_upgrade", "table_only", "opportunity"]
TABLE_ROWS = 25
CELL_CHARS = 300
OPEN_CHARS = 220


@dataclass
class ApiResult:
    api: str
    # `succeeded`, `failed` or `aborted` from the model, `skipped` when no run was needed,
    # `not_run` when the run failed or the job's budget was spent
    status: str
    output: Optional[Dict[str, Any]] = None
    turns: int = 0
    tokens: int = 0
    ruled_out: int = 0
    kept: int = 0
    sources: List[str] = field(default_factory=list)
    origin: str = "registry"
    reason: str = ""
    # the newest release note seen, with its age when old, or `undated`
    latest: str = ""
    # every source of the API failed to load in the job
    unread: bool = False


def _cell(text: str) -> str:
    flat = " ".join(str(text).replace("|", "/").split())
    return flat if len(flat) <= CELL_CHARS else flat[: CELL_CHARS - 1] + "…"


def _rows(changes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Changes worth a row, most urgent first, then by the date they land."""
    listed = [c for c in changes if c.get("impact") in IMPACT_ORDER]
    return sorted(
        listed,
        key=lambda c: (IMPACT_ORDER.index(c["impact"]), c.get("effective_date") or "9999"),
    )


def _where(location: str) -> str:
    """A location as `path` line N, whatever quoting the model gave it."""
    path, _, rest = location.strip().partition(" ")
    return f"`{path.strip('`')}` {rest}".strip()


def _lands(change: Dict[str, Any]) -> str:
    day = change.get("effective_date") or ""
    removed = change.get("removal_date") or ""
    if change.get("impact") == "on_upgrade":
        text = f"on upgrade, pinned version ends {day}" if day else "on upgrade"
    else:
        text = day or "now"
    return f"{text}, removed {removed}" if removed and removed != day else text


def _models(change: Dict[str, Any]) -> List[str]:
    """The affected locations that are downstream models rather than pipeline code."""
    found = []
    for where in change.get("affected") or []:
        path = where.split(" ")[0].strip("`")
        if path.endswith(".sql") or "/models/" in f"/{path}" or "transformations/" in path:
            found.append(f"`{path}`")
    return list(dict.fromkeys(found))


def _per_api(rows: List[Dict[str, Any]], impact: str, today: str = "") -> List[str]:
    """One bullet per API with changes of one impact: how many, how soon, which models."""
    bullets = []
    for api in dict.fromkeys(c["api"] for c in rows if c["impact"] == impact):
        own = [c for c in rows if c["api"] == api and c["impact"] == impact]
        days = sorted(c["effective_date"] for c in own if c.get("effective_date"))
        models = list(dict.fromkeys(m for c in own for m in _models(c)))
        text = f"- `{api}`: {len(own)} change{'s' if len(own) > 1 else ''}"
        if impact == "on_upgrade":
            text += f", pinned version ends {days[0]}" if days else ", no end date given"
        elif days:
            text += f", earliest {days[0]}" + (" (passed)" if today and days[0] < today else "")
        if models:
            verb = "affects" if impact == "opportunity" else "breaks"
            text += f", {verb} {', '.join(models)}"
        bullets.append(text)
    return bullets


def _short(text: str, limit: int = OPEN_CHARS) -> str:
    """One line of at most `limit` characters, cut at a word."""
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[: flat.rfind(" ", 0, limit - 1)] + "…"


def _open_questions(points: List[Tuple[str, str]]) -> List[str]:
    """One bullet per open point, under the API it came from, without repeats."""
    seen: Dict[str, None] = {}
    for api, text in points:
        seen.setdefault(f"- `{api}`: {_short(text)}", None)
    return list(seen)


def _history(carried: int, resolved: List[Dict[str, Any]], note: str) -> List[str]:
    """What became of the findings earlier reports listed."""
    if "not read" in note or "local run" in note:
        return [f"- Earlier findings: {note}; every finding counts as new."]
    if "first report" in note:
        return [f"- Earlier findings: none, this is the {note.split(':')[0]}."]
    lines = [f"- Earlier findings: {carried} still open, {len(resolved)} resolved ({note})."]
    for item in resolved:
        changed = ", ".join(f"`{line['location']}`" for line in item.get("lines") or [])
        lines.append(f"- Resolved: `{item.get('api')}` {_short(item.get('title', ''), 120)} ({changed} changed).")
    return lines


def _scope(
    results: List[ApiResult], rows: List[Dict[str, Any]], sources: List[Dict[str, Any]], since: str, until: str
) -> List[str]:
    """What the report covered, for a reader deciding how far to trust it."""
    notes = sum(r.kept + r.ruled_out for r in results)
    window = f"{since} to {until}" if until else f"from {since}"
    lines = [
        f"- {window}: {len(results)} APIs, {notes} release notes read,"
        f" {len(rows)} change{'' if len(rows) == 1 else 's'} affect this workspace."
    ]
    searched = {s["api"] for s in sources if s.get("origin") == "searched"}
    counts = [
        f"`{r.api}` {'found by web search' if r.api in searched else r.kept + r.ruled_out}"
        for r in results
        if r.status != "not_run"
    ]
    if counts:
        lines.append(f"- Release notes per API: {', '.join(counts)}.")
    with_rows = {c["api"] for c in rows}
    quiet = [f"`{r.api}`" for r in results if r.api not in with_rows and r.status != "not_run"]
    if quiet:
        lines.append(f"- No change for this workspace: {', '.join(quiet)}.")
    newest = [f"`{r.api}` {r.latest}" for r in results if r.latest and r.latest != "undated"]
    if newest:
        lines.append(f"- Newest release note seen: {', '.join(newest)}.")
    gaps = [f"`{r.api}` publishes no dates" for r in results if r.latest == "undated"]
    for r in results:
        if old := re.search(r"\((\d+) days ago\)", r.latest):
            gaps.append(f"`{r.api}` newest entry is {old.group(1)} days old")
    gaps += [f"`{r.api}` release notes could not be read" for r in results if r.unread and r.api not in searched]
    if gaps:
        lines.append(f"- Coverage gaps: {'; '.join(gaps)}. Finding nothing there is no proof nothing changed.")
    for r in results:
        if r.status == "not_run":
            lines.append(f"- Not checked: `{r.api}`, {r.reason}.")
    ran = [r for r in results if r.turns]
    skipped = [f"`{r.api}`" for r in results if r.status == "skipped"]
    cost = f"- Cost: {len(ran)} model run{'' if len(ran) == 1 else 's'}, {sum(r.tokens for r in results):,} tokens"
    lines.append(cost + (f"; no run needed for {', '.join(skipped)}." if skipped else "."))
    return lines


def summary(
    results: List[ApiResult],
    changes: List[Dict[str, Any]],
    sources: List[Dict[str, Any]],
    points: List[Tuple[str, str]],
    since: str,
    until: str = "",
    history: Optional[List[str]] = None,
) -> str:
    """The report's markdown: five bullet sections, then the table of changes."""
    rows = _rows(changes)
    sections = [
        ("Action required", _per_api(rows, "action_required", until) + _per_api(rows, "unknown", until),
         "No change lands now on a resource or model of this workspace."),
        ("On upgrade", _per_api(rows, "on_upgrade"), "No change waits on a version upgrade."),
        ("Opportunities", _per_api(rows, "opportunity"), "No enhancement or new endpoint applies."),
        ("Open questions", _open_questions(points), "Nothing was left open."),
    ]
    parts = []
    for heading, bullets, empty in sections:
        parts.append(f"## {heading}\n" + "\n".join(bullets or [f"- {empty}"]))
    scope = _scope(results, rows, sources, since, until) + (history or [])
    parts.append("## Scope\n" + "\n".join(scope))
    if rows:
        table = [
            "| api | lands | impact | change | where | change to make | reported |",
            "|---|---|---|---|---|---|---|",
        ]
        for c in rows[:TABLE_ROWS]:
            where = ", ".join(_where(w) for w in c.get("affected") or [])
            # a finding an earlier report listed shows the date it was first listed
            reported = c.get("first_reported") or "new"
            table.append(
                f"| `{c['api']}` | {_cell(_lands(c))} | {c['impact']} | {_cell(c.get('title', ''))}"
                f" | {_cell(where)} | {_cell(c.get('recommendation', ''))} | {reported} |"
            )
        if len(rows) > TABLE_ROWS:
            table.append(f"\n{len(rows) - TABLE_ROWS} more changes are in the `changes` field.")
        parts.append("## Changes\n" + "\n".join(table))
    else:
        parts.append("## Changes\n- No change touches this workspace.")
    return "\n\n".join(parts)


def _redacted(change: Dict[str, Any]) -> Dict[str, Any]:
    """A change with credential literals masked in every text the model wrote."""
    text = {k: redact(v) for k, v in change.items() if isinstance(v, str)}
    affected = [redact(str(where)) for where in change.get("affected") or []]
    return {**change, **text, "affected": affected}


def _really_failed(result: ApiResult) -> bool:
    """True when a run that says it failed could not read its API's release notes."""
    # an open question the note itself leaves is the job done, not a failed run
    sources = (result.output or {}).get("sources") or []
    read = any(s.get("origin") != "not_found" and s.get("url") for s in sources)
    return result.unread and not read or any(s.get("origin") == "not_found" for s in sources)


def _with_earlier(change: Dict[str, Any], item: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """A row reported again, with its first date and the dates only the earlier one gave."""
    if item is None:
        return change
    dates = {f: item[f] for f in DATE_FIELDS if item.get(f) and not change.get(f)}
    return {**change, **dates, "first_reported": item["first_reported"]}


def merge(
    results: List[ApiResult],
    since: str,
    until: str = "",
    tracked: Optional[List[Dict[str, Any]]] = None,
    carried: Optional[List[Dict[str, Any]]] = None,
    resolved: Optional[List[Dict[str, Any]]] = None,
    history_note: str = "",
) -> Dict[str, Any]:
    """One agent output for the job from the per-API results and the earlier findings."""
    changes: List[Dict[str, Any]] = []
    sources: List[Dict[str, Any]] = []
    points: List[Tuple[str, str]] = []
    for r in results:
        output = r.output or {}
        # each run was asked about one API, so its rows belong to that API
        changes.extend(_redacted({**c, "api": r.api}) for c in output.get("changes") or [])
        given = [s for s in output.get("sources") or [] if s.get("api") == r.api]
        sources.extend(given or [{"api": r.api, "url": url, "origin": r.origin} for url in r.sources])
        # a run knows only its own API, so the job names the API each point came from
        points.extend((r.api, redact(str(point))) for point in output.get("open_points") or [])
        if r.status == "aborted":
            points.append((r.api, f"The run aborted: {output.get('summary', '')}"))
    for r in results:
        if r.status == "failed" and not _really_failed(r):
            r.status = "succeeded"
    failed = any(r.status in ("failed", "aborted", "not_run") for r in results)
    # this run's rows carry the date each finding was first reported
    earlier = {item["key"]: item for item in tracked or [] if not item.get("new", True)}
    rows = [_with_earlier(c, earlier.get(key(c))) for c in changes]
    rows += [{**item, "carried": True} for item in carried or []]
    # every earlier finding still open counts, whether the model listed it again or not
    still_open = sum(not item.get("new", True) for item in tracked or [])
    history = _history(still_open, resolved or [], history_note) if history_note else []
    return {
        "status": "failed" if failed else "succeeded",
        "summary": summary(results, rows, sources, points, since, until, history),
        "since": since,
        "sources": sources,
        "changes": changes,
        "open_points": [f"`{api}`: {text}" for api, text in points]
        + [f"`{r.api}` was not checked: {r.reason}." for r in results if r.status == "not_run"],
        "requires_human": any(c.get("impact") == "action_required" for c in rows),
        "tracked": tracked or [],
        "runs": [
            {"api": r.api, "status": r.status, "turns": r.turns, "tokens": r.tokens} for r in results
        ],
    }
