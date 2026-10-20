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

TRACKED_IMPACTS = ("action_required", "unknown", "on_upgrade", "schema_change")
DATE_FIELDS = ("announced_date", "effective_date", "removal_date")

_FILE = re.compile(r"`?([\w./-]+\.(?:py|sql|toml|ya?ml|json))`?")
# the line list right after a file: `line 8 and line 14`, `lines 8 and 14`, `lines 3-4`
_LINE_LIST = re.compile(
    r"[`\s,]*\blines?\s+(\d+(?:\s*[-\u2013]\s*\d+)?"
    r"(?:\s*(?:,|\band\b|&)\s*(?:lines?\s+)?\d+(?:\s*[-\u2013]\s*\d+)?)*)"
)
_NUMBER = re.compile(r"(\d+)(?:\s*[-\u2013]\s*(\d+))?")
MAX_RANGE = 20


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


def locations(text: str) -> List[Tuple[str, int]]:
    """`(path, line)` for every line a text names after a file, ranges spread out."""
    found: List[Tuple[str, int]] = []
    for match in _FILE.finditer(text):
        listed = _LINE_LIST.match(text, match.end())
        if not listed:
            continue
        for first, last in _NUMBER.findall(listed.group(1)):
            start = int(first)
            end = int(last) if last and 0 <= int(last) - start <= MAX_RANGE else start
            found.extend((match.group(1), number) for number in range(start, end + 1))
    return list(dict.fromkeys(found))


def fingerprint(change: Dict[str, Any], root: Path) -> List[Dict[str, str]]:
    """The lines a finding's fix changes, from its recommendation, else its locations."""
    found = locations(str(change.get("recommendation", "")))
    found = found or locations(", ".join(change.get("affected") or []))
    lines = []
    for path, number in found:
        text = _line(root, path, number)
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
    for found, item in list(earlier.items()):
        # an older report may hold the same finding twice: one copy matched, drop the others
        if any(_same_finding({found: item}, new, new.get("lines") or []) for new in tracked):
            continue
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


_FILLER = {"a", "an", "the", "and", "or", "of", "for", "to", "in", "on", "from", "with", "is", "are", "be", "now", "new"}


def _words(title: str) -> set:
    words = re.findall(r"[a-z0-9]+", str(title).lower())
    # plurals fold into one word, so `tokens` meets `token`
    return {w[:-1] if len(w) > 3 and w.endswith("s") else w for w in words if w not in _FILLER}


def _similar(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """True when two findings share a date, or half the words of the shorter title."""
    if a.get("effective_date") and a.get("effective_date") == b.get("effective_date"):
        return True
    ours, theirs = _words(a.get("title", "")), _words(b.get("title", ""))
    return bool(ours and theirs) and len(ours & theirs) >= max(2, min(len(ours), len(theirs)) / 2)


def _same_finding(
    earlier: Dict[str, Dict[str, Any]], change: Dict[str, Any], lines: List[Dict[str, str]]
) -> Optional[Dict[str, Any]]:
    """Pop the earlier finding a reworded one repeats: a shared line and a similar change."""
    wanted = {(line["location"], line["text"]) for line in lines}
    files = {line["location"].rsplit(" line ", 1)[0] for line in lines}
    targets = set(locations(str(change.get("recommendation", ""))))
    for found, item in list(earlier.items()):
        if item.get("api") != change.get("api"):
            continue
        theirs = item.get("lines") or []
        shared = wanted & {(line["location"], line["text"]) for line in theirs}
        # an older report may hold fewer fingerprints, so its recommendation is read again
        shared = shared or targets & set(locations(str(item.get("recommendation", ""))))
        # one line can carry two changes, so a shared line needs a similar change too
        if shared and _similar(change, item):
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
