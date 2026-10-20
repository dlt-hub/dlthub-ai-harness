"""Carry findings from one api-change-monitor run to the next until the code changes.

A finding is kept with the text of the lines its recommendation targets. While one of
those lines still reads the same, the finding is open and is reported again; once all
of them changed or went away, it is reported resolved. No model takes part.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .redact import redact

TRACKED_IMPACTS = ("action_required", "unknown", "on_upgrade")
DATE_FIELDS = ("announced_date", "effective_date", "removal_date")

# `pipelines/a.py` line 12, pipelines/a.py line 12, `models/x.sql` lines 3-4
_LOCATION = re.compile(r"`?([\w./-]+\.(?:py|sql|toml|ya?ml|json))`?,? lines? (\d+)")


def key(change: Dict[str, Any]) -> str:
    """What identifies a finding across runs: its API and its title, normalised."""
    title = re.sub(r"[^a-z0-9]+", " ", str(change.get("title", "")).lower()).strip()
    return f"{change.get('api', '')}|{title[:120]}"


def _line(root: Path, path: str, number: int) -> Optional[str]:
    try:
        lines = (root / path).read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    # the fingerprint is stored on the platform, so it never holds a credential
    return redact(lines[number - 1].strip()) if 0 < number <= len(lines) else None


def fingerprint(change: Dict[str, Any], root: Path) -> List[Dict[str, str]]:
    """The lines a finding's fix changes, from its recommendation, else its locations."""
    found = _LOCATION.findall(str(change.get("recommendation", "")))
    found = found or _LOCATION.findall(" ".join(change.get("affected") or []))
    lines = []
    for path, number in dict.fromkeys(found):
        text = _line(root, path, int(number))
        if text:
            lines.append({"location": f"{path} line {number}", "text": text})
    return lines


def still_open(item: Dict[str, Any], root: Path) -> bool:
    """True while one fingerprinted line still reads the same anywhere in its file."""
    lines = item.get("lines") or []
    # a finding with nothing to compare stays open rather than vanish unchecked
    if not lines:
        return True
    for line in lines:
        path = line["location"].rsplit(" line ", 1)[0]
        try:
            text = (root / path).read_text(encoding="utf-8")
            current = {redact(line.strip()) for line in text.splitlines()}
        except (OSError, UnicodeDecodeError):
            continue
        if line["text"] in current:
            return True
    return False


def track(
    changes: List[Dict[str, Any]],
    previous: List[Dict[str, Any]],
    root: Path,
    today: date,
    unchecked_apis: List[str],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """The findings to keep, the earlier ones still open, and the ones resolved."""
    earlier = {item["key"]: item for item in previous if item.get("key")}
    tracked: List[Dict[str, Any]] = []
    for change in changes:
        if change.get("impact") not in TRACKED_IMPACTS:
            continue
        found, lines = key(change), fingerprint(change, root)
        same = earlier.pop(found, None) or _same_finding(earlier, change, lines)
        first = (same or {}).get("first_reported") or today.isoformat()
        item = {**change, "key": found, "first_reported": first, "lines": lines}
        # a note read only once, such as a first run's lookback, keeps the date it gave
        item.update({f: same[f] for f in DATE_FIELDS if same and same.get(f) and not item.get(f)})
        tracked.append({**item, "new": same is None})
    carried, resolved = [], []
    for item in earlier.values():
        # an API whose run failed keeps its findings; a deleted pipeline resolves its own
        if item.get("api") in unchecked_apis or still_open(item, root):
            carried.append({**item, "new": False})
        else:
            resolved.append(item)
    return tracked + carried, carried, resolved


def combine(reports: List[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """The newest report's findings, with dates and first dates only older reports had."""
    if not reports:
        return []
    newest = [dict(item) for item in reports[0]]
    for older in reports[1:]:
        pool = {item["key"]: item for item in older if item.get("key")}
        for item in newest:
            match = pool.pop(item.get("key", ""), None) or _same_finding(pool, item, item.get("lines") or [])
            if not match:
                continue
            item.update({f: match[f] for f in DATE_FIELDS if match.get(f) and not item.get(f)})
            earliest = min(filter(None, [item.get("first_reported"), match.get("first_reported")]))
            item["first_reported"] = earliest
    return newest


def _same_finding(
    earlier: Dict[str, Dict[str, Any]], change: Dict[str, Any], lines: List[Dict[str, str]]
) -> Optional[Dict[str, Any]]:
    """Pop the earlier finding a reworded one repeats: same line, or same change and file."""
    wanted = {(line["location"], line["text"]) for line in lines}
    files = {line["location"].rsplit(" line ", 1)[0] for line in lines}
    for found, item in list(earlier.items()):
        if item.get("api") != change.get("api"):
            continue
        theirs = item.get("lines") or []
        if wanted & {(line["location"], line["text"]) for line in theirs}:
            return earlier.pop(found)
        # the model may target another line of the same file for the same dated change
        same_change = (
            item.get("kind") == change.get("kind")
            and change.get("effective_date")
            and item.get("effective_date") == change.get("effective_date")
        )
        if same_change and files & {line["location"].rsplit(" line ", 1)[0] for line in theirs}:
            return earlier.pop(found)
    return None
