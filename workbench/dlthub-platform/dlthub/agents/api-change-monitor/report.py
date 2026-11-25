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
from .tracking import DATE_FIELDS, key, locations

# the order rows take in the table, most urgent first
IMPACT_ORDER = ["action_required", "unknown", "on_upgrade", "schema_change", "table_only", "opportunity"]
TABLE_ROWS = 25
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
    # model files in this workspace reading the API's datasets; None when none was found
    downstream: Optional[List[str]] = None


# what each impact asks of the reader, and the group it is counted in
_LABELS = {
    "action_required": ("act", "act now"),
    "unknown": ("check", "act now"),
    "on_upgrade": ("upgrade", "plan ahead"),
    "schema_change": ("table change", "plan ahead"),
    "table_only": ("table change", "plan ahead"),
    "opportunity": ("adopt", "to adopt"),
}
GROUPS = ["act now", "plan ahead", "to adopt"]
ACTION_CHARS = 160
CHANGE_CHARS = 80
OPEN_SHOWN = 3


def _rows(changes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Changes worth a row: act now first, then plan ahead, then to adopt, each by date."""
    listed = [c for c in changes if c.get("impact") in _LABELS]
    return sorted(
        listed,
        key=lambda c: (
            GROUPS.index(_LABELS[c["impact"]][1]),
            c.get("effective_date") or "9999",
            IMPACT_ORDER.index(c["impact"]),
        ),
    )


def _when(change: Dict[str, Any], today: str = "") -> str:
    """When a change lands, in the fewest words: a date, `passed`, an upgrade or `now`."""
    day = change.get("effective_date") or ""
    if change.get("impact") == "on_upgrade":
        return f"on upgrade, by {day}" if day else "on upgrade"
    if not day:
        # a schema change waits on a release or an upgrade, so no date is no "now"
        return "not dated" if change.get("impact") == "schema_change" else "now"
    return f"{day} passed" if today and day < today else day


def _short_location(change: Dict[str, Any]) -> str:
    """The first file and line the fix names, as `file.py:12`."""
    found = locations(str(change.get("recommendation", "")))
    found = found or locations(", ".join(change.get("affected") or []))
    if not found:
        return ""
    path, line = found[0]
    return f"`{path.rsplit('/', 1)[-1]}:{line}`"


# the place a recommendation opens with, as `In `a.py` line 8 and line 14, `
_LEADING_PLACE = re.compile(
    r"^(?:in|at)\s+`?[\w./-]+\.\w+`?"
    r"(?:[,\s]*(?:and\s+|&\s*)?(?:lines?\s+)?\d+(?:\s*[-\u2013]\s*\d+)?)*,?\s*",
    re.I,
)


# a file and line named inside a sentence, as ` (`a.py` line 16)` or ` in a.py line 18`
_INLINE_PLACE = re.compile(
    r"\s*(?:\(|\bin\s+)?`?[\w./-]+\.(?:py|sql|toml|ya?ml|json)`?"
    r"(?:[,\s]*(?:and\s+|&\s*)?(?:lines?\s+)?\d+(?:\s*[-\u2013]\s*\d+)?)*\)?",
    re.I,
)


def _edit(change: Dict[str, Any]) -> str:
    """The edit to show: the `action`, else the start of the recommendation, else the title."""
    text = str(change.get("action") or "").strip()
    if not text:
        text = re.split(r"(?<=[.;])\s", str(change.get("recommendation", "")).strip())[0]
        # the report adds the place once, so the sentence drops its own references
        text = _INLINE_PLACE.sub("", _LEADING_PLACE.sub("", text))
    text = text.rstrip(" .;")
    return text[:1].upper() + text[1:] if text else str(change.get("title", ""))


def _action(change: Dict[str, Any]) -> str:
    """The exact edit, with the place it lands."""
    text = _short(_edit(change), ACTION_CHARS)
    where = _short_location(change)
    return f"{text} ({where})" if where and where.strip("`").split(":")[0] not in text else text


def _short(text: str, limit: int = OPEN_CHARS) -> str:
    """One line of at most `limit` characters, cut at a word."""
    flat = " ".join(str(text).replace("|", "/").split())
    return flat if len(flat) <= limit else flat[: flat.rfind(" ", 0, limit - 1)] + "…"


def _headline(rows: List[Dict[str, Any]], resolved: List[Dict[str, Any]]) -> str:
    """One bold line: how many findings are open, by group, and how many were resolved."""
    done = f" {len(resolved)} resolved." if resolved else ""
    if not rows:
        return f"**No open findings.**{done}"
    counts = {group: sum(_LABELS[c["impact"]][1] == group for c in rows) for group in GROUPS}
    parts = [f"{n} {group}" for group, n in counts.items() if n]
    new = sum(not c.get("first_reported") for c in rows)
    plural = "" if len(rows) == 1 else "s"
    return f"**{len(rows)} open finding{plural}: {', '.join(parts)}, {new} new.{done}**"


_MODEL_FILE = re.compile(r"`?([\w./-]+\.sql|[\w./-]*(?:models|transformations|transforms|marts|staging)/[\w./-]+\.py)`?")


def _transformations(change: Dict[str, Any], downstream: Optional[List[str]]) -> str:
    """The models a change breaks, or why none is named."""
    found = [m for where in change.get("affected") or [] for m in _MODEL_FILE.findall(str(where))]
    names = list(dict.fromkeys(f"`{path.rsplit('/', 1)[-1]}`" for path in found))
    if names:
        return ", ".join(names)
    if not downstream:
        return "no transformations in the workspace"
    return "none affected"


def _table(
    rows: List[Dict[str, Any]], today: str, downstream: Optional[Dict[str, Optional[List[str]]]] = None
) -> List[str]:
    lines = [
        "| when | api | api change | impact | transformations | action |",
        "|---|---|---|---|---|---|",
    ]
    for c in rows[:TABLE_ROWS]:
        change = _short(str(c.get("title", "")).rstrip(" ."), CHANGE_CHARS)
        models = _transformations(c, (downstream or {}).get(c["api"]))
        cells = [_when(c, today), c["api"], change, _LABELS[c["impact"]][0], models, _action(c)]
        lines.append(f"| {' | '.join(cells)} |")
    if len(rows) > TABLE_ROWS:
        lines.append(f"\n{len(rows) - TABLE_ROWS} more findings are in the `changes` field.")
    return lines


def _open_line(points: List[Tuple[str, str]]) -> str:
    unique = list(dict.fromkeys(f"{api}: {_short(str(text).rstrip(' .;'), 120)}" for api, text in points))
    if not unique:
        return ""
    more = f" (+{len(unique) - OPEN_SHOWN} more)" if len(unique) > OPEN_SHOWN else ""
    return f"**Open:** {'; '.join(unique[:OPEN_SHOWN])}{more}"


def _resolved_line(resolved: List[Dict[str, Any]]) -> str:
    if not resolved:
        return ""
    items = []
    for item in resolved:
        lines = [line["location"] for line in item.get("lines") or []]
        place = lines[0].replace(" line ", ":").rsplit("/", 1)[-1] if lines else ""
        items.append(f"{item.get('api')}: {_short(item.get('title', ''), 60)}" + (f" (`{place}` changed)" if place else ""))
    return f"**Resolved:** {'; '.join(items)}"


def _coverage_line(
    results: List[ApiResult], sources: List[Dict[str, Any]], since: str, note: str
) -> str:
    """What the report covered and what it could not, in one line."""
    notes = sum(r.kept + r.ruled_out for r in results)
    searched = {s["api"] for s in sources if s.get("origin") == "searched"}
    gaps = [f"{r.api} undated" for r in results if r.latest == "undated"]
    gaps += [f"{r.api} silent {m.group(1)}d" for r in results if (m := re.search(r"\((\d+) days ago\)", r.latest))]
    gaps += [f"{r.api} found by search" for r in results if r.api in searched]
    gaps += [f"{r.api} unreadable" for r in results if r.unread and r.api not in searched]
    gaps += [f"{r.api} not checked ({r.reason})" for r in results if r.status == "not_run"]
    if "not read" in note or "local run" in note:
        gaps.append("no earlier report, all findings shown as new")
    ran = sum(1 for r in results if r.turns)
    tokens = sum(r.tokens for r in results)
    apis = f"{len(results)} API{'' if len(results) == 1 else 's'}"
    text = f"**Coverage:** {apis}, {notes} notes since {since}"
    text += f"; gaps: {', '.join(gaps)}" if gaps else ""
    if not ran:
        return text + ". No model run needed."
    return text + f". {ran} model run{'' if ran == 1 else 's'}, {round(tokens / 1000)}k tokens."


def summary(
    results: List[ApiResult],
    changes: List[Dict[str, Any]],
    sources: List[Dict[str, Any]],
    points: List[Tuple[str, str]],
    since: str,
    until: str = "",
    resolved: Optional[List[Dict[str, Any]]] = None,
    history_note: str = "",
) -> str:
    """The report's markdown: a status line, one table, then open, resolved and coverage."""
    rows = _rows(changes)
    parts = [_headline(rows, resolved or [])]
    if rows:
        downstream = {r.api: r.downstream for r in results}
        parts.append("\n".join(_table(rows, until, downstream)))
    tail = [_open_line(points), _resolved_line(resolved or []), _coverage_line(results, sources, since, history_note)]
    parts.extend(line for line in tail if line)
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
    return {
        "status": "failed" if failed else "succeeded",
        "summary": summary(results, rows, sources, points, since, until, resolved, history_note),
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
