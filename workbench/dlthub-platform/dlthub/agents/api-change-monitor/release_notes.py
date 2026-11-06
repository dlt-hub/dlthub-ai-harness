"""Read any API's release notes since a date: RSS or Atom, markdown or HTML pages.

A page is cut into notes by its dated headings, else by the dated rows of its tables,
else by passages around its dated lines. A page with no date at all is one undated
note, flagged `not parsed` when too long to show. `render` bounds the window.
"""

from __future__ import annotations

import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, timedelta
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence, Tuple

# a removal this close to today is listed on every run, announced in the window or not
IMMINENT = timedelta(days=30)

NOTE_CHARS = 1_800
"""Characters of one note's text kept in the window when the window is full."""

MAX_NOTE_CHARS = 6_000
"""Characters of one note's text kept when the window has room to spare."""

WINDOW_CHARS = 60_000
"""Characters of the whole window; the system prompt is resent on every turn."""

_CONTENT = "{http://purl.org/rss/1.0/modules/content/}encoded"
_ATOM = "{http://www.w3.org/2005/Atom}"
_ISO_DATE = re.compile(r"(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)")
# `September 30, 2026`, `Sep 30 2026`, `Aug 1st, 2026`
_MONTH_FIRST = re.compile(r"\b([A-Z][a-z]{2,8})\.? (\d{1,2})(?:st|nd|rd|th)?,? (\d{4})\b")
# `30 September 2026`, `1st Aug 2026`
_DAY_FIRST = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)? ([A-Z][a-z]{2,8})\.?,? (\d{4})\b")
_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1
)}
_HEADING = re.compile(r"(?m)^(#{1,6}) +(.+)$")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")


@dataclass
class Note:
    api: str
    title: str
    url: str
    published: Optional[date]
    labels: List[str] = field(default_factory=list)
    text: str = ""
    # endpoints the note names that a workspace resource calls, with where it calls them
    calls: List[str] = field(default_factory=list)
    # model lines reading a field the note names
    models: List[str] = field(default_factory=list)
    # pipeline code lines naming a field the note names, as a query selecting it
    code: List[str] = field(default_factory=list)
    # versions the workspace pins that the note names
    pinned: List[str] = field(default_factory=list)


Fetch = Callable[[str], str]


def fetch_text(url: str) -> str:
    """The body of `url` as text, in English, raising on an HTTP error."""
    from dlt.sources.helpers import requests

    response = requests.get(url, timeout=30, headers={"Accept-Language": "en-US,en"})
    response.raise_for_status()
    # a page that names no charset is decoded as latin-1, which garbles utf-8 text
    if "charset" not in response.headers.get("content-type", "").lower():
        response.encoding = "utf-8"
    return str(response.text)


def dates_in(text: str) -> List[Tuple[int, date]]:
    """Every date in text with its position, ISO or with the month in words."""
    found = []
    for match in _ISO_DATE.finditer(text):
        try:
            found.append((match.start(), date.fromisoformat(match.group(1))))
        except ValueError:
            continue
    for pattern, order in ((_MONTH_FIRST, (2, 1, 3)), (_DAY_FIRST, (1, 2, 3))):
        for match in pattern.finditer(text):
            day, month, year = (match.group(i) for i in order)
            number = _MONTHS.get(month[:3].lower())
            if number is None:
                continue
            try:
                found.append((match.start(), date(int(year), number, int(day))))
            except ValueError:
                continue
    return sorted(found)


def find_date(text: str) -> Optional[date]:
    """The first date in text, ISO or with the month written out or abbreviated."""
    found = dates_in(text)
    return found[0][1] if found else None


def upcoming(note: "Note", today: date, ahead: timedelta) -> Optional[date]:
    """The earliest date a note names between today and `ahead` from now, or None."""
    days = [d for _, d in dates_in(f"{note.title}\n{note.text}") if today <= d <= today + ahead]
    return min(days) if days else None


def strip_html(markup: str) -> str:
    """Markdown-ish text of an HTML page: headings as `#`, list items as bullets."""
    text = re.sub(r"(?is)<(script|style|nav|header|footer|head)\b.*?</\1>", "", markup)
    text = re.sub(
        r"(?is)<h([1-6])[^>]*>(.*?)</h\1>",
        lambda m: f"\n{'#' * int(m.group(1))} {re.sub(r'<[^>]+>', '', m.group(2))}\n",
        text,
    )
    text = re.sub(r"(?is)<code[^>]*>(.*?)</code>", lambda m: f"`{m.group(1)}`", text)
    text = re.sub(r"(?is)<tr\b[^>]*>(.*?)</tr>", _table_row, text)
    text = re.sub(r"(?i)<li[^>]*>", "\n- ", text)
    text = re.sub(r"(?i)</?(p|div|br|ul|ol|tr|pre|section|article)\b[^>]*>", "\n", text)
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    lines = (re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines())
    # a page rendered by script says so in a line that carries no content
    lines = (line for line in lines if "JavaScript must be enabled" not in line)
    # a list item wrapping a paragraph leaves its bullet on a line of its own
    return re.sub(r"(?m)^-\n", "- ", "\n".join(line for line in lines if line))


def _table_row(match: "re.Match[str]") -> str:
    """An HTML table row as one markdown row, so dated rows are read like markdown."""
    cells = re.findall(r"(?is)<t[dh]\b[^>]*>(.*?)</t[dh]>", match.group(1))
    flat = [
        re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", c))).replace("|", "/").strip()
        for c in cells
    ]
    return f"\n| {' | '.join(flat)} |\n" if flat else "\n"


def parse(
    api: str,
    url: str,
    body: str,
    since: date,
    today: date,
    topics: Sequence[str] = (),
    version: Optional["re.Pattern[str]"] = None,
) -> List[Note]:
    """The notes of one fetched release note source, whatever its format."""
    head = body.lstrip()[:600].lower()
    if "<rss" in head or "<feed" in head:
        return parse_feed(api, body, since, topics)
    label = ""
    if version is not None and (found := version.search(body)):
        label = found.group(1)
    title = ""
    if "<html" in head or "<!doctype html" in head or "<body" in head:
        if found := re.search(r"(?is)<title[^>]*>(.*?)</title>", body):
            title = html.unescape(found.group(1)).strip()
        body = strip_html(body)
    return parse_page(api, url, body, since, today, label, title)


def parse_feed(api: str, feed: str, since: date, topics: Sequence[str] = ()) -> List[Note]:
    """RSS items or Atom entries published on or after `since`, in the given topics."""
    root = ET.fromstring(feed.lstrip())
    notes = []
    for item in root.findall("./channel/item") + root.findall(f"{_ATOM}entry"):
        labels = [c.text or "" for c in item.findall("category")]
        labels += [c.get("term") or "" for c in item.findall(f"{_ATOM}category")]
        if topics and not set(topics) & set(labels):
            continue
        published = _item_date(item)
        if published is None or published < since:
            continue
        bodies = ("description", _CONTENT, f"{_ATOM}content", f"{_ATOM}summary")
        text = max((item.findtext(tag) or "" for tag in bodies), key=len)
        link = item.findtext("link") or ""
        atom_link = item.find(f"{_ATOM}link")
        if not link.strip() and atom_link is not None:
            link = atom_link.get("href") or ""
        title = item.findtext("title") or item.findtext(f"{_ATOM}title") or ""
        notes.append(
            Note(
                api=api,
                title=title.strip(),
                url=link.strip(),
                published=published,
                labels=[label for label in labels if label],
                text=strip_html(text),
            )
        )
    return notes


def _item_date(item: ET.Element) -> Optional[date]:
    raw = item.findtext("pubDate")
    if raw:
        try:
            return parsedate_to_datetime(raw).date()
        except (TypeError, ValueError):
            return None
    raw = item.findtext(f"{_ATOM}updated") or item.findtext(f"{_ATOM}published")
    return find_date(raw) if raw else None


def parse_page(
    api: str, url: str, text: str, since: date, today: date, version: str = "", title: str = ""
) -> List[Note]:
    """Notes of a page: its dated sections, else its dated table rows, else the whole."""
    text = re.sub(r"\A---\n.*?\n---\n", "", text.lstrip(), flags=re.S)
    headings = [(m, find_date(m.group(2))) for m in _HEADING.finditer(text)]
    if any(day for _, day in headings):
        return _dated_sections(api, url, text, headings, since)
    if any(find_date(" ".join(cells)) for _, cells in _table_rows(text)):
        return _dated_rows(api, url, text, since, today)
    lines = text.splitlines()
    if any(find_date(line) for line in lines):
        return _dated_passages(api, url, lines, since, today)
    title = title or (headings[0][0].group(2).strip() if headings else url)
    labels = [f"version {version}"] if version else ["not dated"]
    # a long page with no date to cut it by is one the agent reads itself
    if len(text) > MAX_NOTE_CHARS:
        labels.append("not parsed")
    return [
        Note(
            api=api,
            title=f"{title} ({version})" if version else title,
            url=url,
            published=None,
            labels=labels,
            text=text,
        )
    ]


PASSAGE_BEFORE, PASSAGE_AFTER = 3, 8
"""Lines kept before and after a dated line of a page with no other structure."""


def _dated_passages(
    api: str, url: str, lines: List[str], since: date, today: date
) -> List[Note]:
    """A passage around each dated line in the window, for a page with no other structure."""
    notes = []
    covered = -1
    for index, line in enumerate(lines):
        day = find_date(line)
        imminent = day is not None and today <= day <= today + IMMINENT
        if index <= covered or day is None or (day < since and not imminent):
            continue
        start = max(index - PASSAGE_BEFORE, covered + 1)
        covered = min(index + PASSAGE_AFTER, len(lines) - 1)
        passage = lines[start : covered + 1]
        # the title is the longest line, which is the subject rather than a label or a date
        title = max(passage, key=lambda text: len(text) if not find_date(text) else 0)
        notes.append(
            Note(
                api=api,
                title=title[:150],
                url=url,
                # the line that opened the passage dates it, not a neighbour's older date
                published=day,
                labels=["passage"] + (["imminent"] if imminent else []),
                text="\n".join(passage),
            )
        )
    return notes


def _dated_sections(
    api: str, url: str, text: str, headings: List[Tuple[Any, Optional[date]]], since: date
) -> List[Note]:
    """One note per subsection of each dated section published on or after `since`."""
    notes = []
    covered = 0
    for index, (match, day) in enumerate(headings):
        # a dated heading inside a section already taken is part of that section
        if day is None or day < since or match.start() < covered:
            continue
        level = len(match.group(1))
        end = len(text)
        # the section runs to the next heading of the same level or higher
        for later, _ in headings[index + 1 :]:
            if len(later.group(1)) <= level:
                end = later.start()
                break
        covered = end
        section = text[match.end() : end]
        heading = _LINK.sub(r"\1", match.group(2)).strip()
        anchor = re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")
        page = url[:-3] if url.endswith(".md") else url
        source = url if "#" in url or "?" in url else f"{page}#{anchor}"
        parts = re.split(r"(?m)^#{1,6} +(.+)$", section)
        pieces = [(heading, parts[0])] + list(zip(parts[1::2], parts[2::2]))
        pieces = [split for title, body in pieces for split in _split_long(title, body)]
        for title, body in pieces:
            if not body.strip():
                continue
            notes.append(
                Note(
                    api=api,
                    title=_LINK.sub(r"\1", title).strip(),
                    url=source,
                    published=day,
                    labels=[heading] if title != heading else [],
                    text=body.strip(),
                )
            )
    return notes


_TOP_BULLET = re.compile(r"(?m)^[*-] +")
_INLINE_TAGS = re.compile(r"</?(details|summary|strong|em|b|i|br)\s*/?>", re.I)


def _split_long(title: str, body: str) -> List[Tuple[str, str]]:
    """A section past `NOTE_CHARS` as one piece per top-level bullet, titled by it."""
    body = _INLINE_TAGS.sub("", body)
    starts = [m.start() for m in _TOP_BULLET.finditer(body)]
    if len(body) <= NOTE_CHARS or len(starts) < 2:
        return [(title, body)]
    pieces = []
    for start, end in zip(starts, starts[1:] + [len(body)]):
        item = body[start:end].strip()
        first = _TOP_BULLET.sub("", item.splitlines()[0]).replace("**", "").strip()
        pieces.append((first[:150] or title, item))
    # a preface before the first bullet keeps the section's own title
    if body[: starts[0]].strip():
        pieces.insert(0, (title, body[: starts[0]]))
    return pieces


def _table_rows(text: str) -> Iterator[Tuple[str, List[str]]]:
    """`(section heading, cells)` of every markdown table row that is not a separator."""
    section = ""
    for line in text.splitlines():
        if heading := _HEADING.match(line):
            section = heading.group(2).strip()
        elif line.lstrip().startswith("|") and not re.fullmatch(r"[\s|:-]+", line):
            yield section, [c.strip() for c in line.strip().strip("|").split("|")]


def _dated_rows(api: str, url: str, text: str, since: date, today: date) -> List[Note]:
    """Rows first dated since `since`, or naming a date within `IMMINENT` of today."""
    notes = []
    for section, cells in _table_rows(text):
        days = [day for day in map(find_date, cells) if day]
        if not days:
            continue
        imminent = any(today <= day <= today + IMMINENT for day in days)
        if min(days) < since and not imminent:
            continue
        row = re.sub(r"\s*<br\s*/?>\s*", ", ", _LINK.sub(r"\1", " | ".join(cells)))
        notes.append(
            Note(
                api=api,
                title=f"{section}: {row[:120]}" if section else row[:120],
                url=url,
                published=min(days),
                labels=[section] + (["imminent"] if imminent else []),
                text=row,
            )
        )
    return notes


def render(notes: List[Note], problems: Dict[str, List[str]], apis: List[str], since: date) -> str:
    """The notes as markdown under a heading per API, within `WINDOW_CHARS`."""
    # a quiet window lets every note keep more of its text
    cap = max(NOTE_CHARS, min(MAX_NOTE_CHARS, WINDOW_CHARS // max(len(notes), 1)))
    blocks = {a: [_block(n, cap) for n in notes if n.api == a] for a in apis}
    shares = _shares({a: sum(len(b) for b in own) for a, own in blocks.items()})
    parts: List[str] = []
    cut = 0
    for api in apis:
        own = [n for n in notes if n.api == api]
        parts.append(f"### {api} ({len(own)} notes since {since.isoformat()})\n")
        parts.extend(f"Not read: {problem}\n" for problem in problems.get(api, []))
        if not own and not problems.get(api):
            parts.append("No release note in the window.\n")
        used = 0
        for note, block in zip(own, blocks[api]):
            if used + len(block) > shares[api]:
                block, cut = _head(note), cut + 1
            parts.append(block)
            used += len(block)
    if cut:
        parts.append(f"\n{cut} notes past the window size are listed by title and url only.\n")
    return "\n".join(parts)


def _shares(sizes: Dict[str, int]) -> Dict[str, int]:
    """Characters per API: what a quiet API leaves goes to the busy ones."""
    shares: Dict[str, int] = {}
    left = WINDOW_CHARS
    for count, api in enumerate(sorted(sizes, key=sizes.__getitem__)):
        shares[api] = min(sizes[api], left // (len(sizes) - count))
        left -= shares[api]
    return shares


def _head(note: Note) -> str:
    published = note.published.isoformat() if note.published else "not dated"
    labels = ", ".join(label for label in note.labels if label)
    head = f"#### {note.title}\n- url: {note.url}\n- published: {published}\n- labels: {labels}\n"
    if version := note_version(note):
        head += f"- api version: `{version}`\n"
    if note.pinned:
        head += f"- names the pinned version: {', '.join(f'`{v}`' for v in note.pinned)}\n"
    calls = "".join(f"  - {call}\n" for call in note.calls)
    models = "".join(f"  - {line}\n" for line in note.models)
    head += f"- called by this workspace:\n{calls}" if calls else ""
    code = "".join(f"  - {line}\n" for line in note.code)
    head += f"- named in pipeline code:\n{code}" if code else ""
    return head + (f"- read by downstream models:\n{models}" if models else "")


def _block(note: Note, cap: int = NOTE_CHARS) -> str:
    """The head and the text of a note, the text cut at `cap` characters."""
    # headings inside a note would break the window's own headings
    text = re.sub(r"(?m)^#{1,6} +", "", note.text).strip()
    if len(text) > cap:
        text = text[:cap] + "\n[cut short]"
    return f"{_head(note)}\n{text}\n"


_METHOD_PATH = re.compile(r"\b(?:GET|POST|PUT|PATCH|DELETE)\s+`?(/[^\s`'\"<>)]*)")
_CODE_PATH = re.compile(r"`(/[A-Za-z0-9_{}:.\-]+(?:/[A-Za-z0-9_{}:.\-]*)*)`")


def endpoints(text: str) -> List[str]:
    """Endpoint paths a note names, as `GET /a/{b}` or a backticked `/a/b`."""
    found = _METHOD_PATH.findall(text) + _CODE_PATH.findall(text)
    return list(dict.fromkeys(path.split("?")[0].rstrip("/.,") for path in found if len(path) > 1))


def _is_param(segment: str) -> bool:
    return segment.startswith(("{", ":", "<")) or segment == "*"


def path_matches(template: str, path: str) -> bool:
    """True when a workspace path is a call of an endpoint template."""
    wanted = [s for s in template.strip("/").split("/") if s]
    called = [s for s in path.split("?")[0].strip("/").split("/") if s]
    # a base url can hold a prefix the template spells out, such as `v1` or `rest/api/3`
    for skip in range(0, 5):
        rest = wanted[skip:]
        if any(_is_param(s) for s in wanted[:skip]) or not any(not _is_param(s) for s in rest):
            break
        # trailing parameters are optional: a list call omits the id
        while len(rest) > len(called) and _is_param(rest[-1]):
            rest = rest[:-1]
        # a placeholder in the workspace path stands only for a parameter of the template
        if len(rest) == len(called) and all(
            _is_param(w) if _is_param(c) else _is_param(w) or w.lower() == c.lower()
            for w, c in zip(rest, called)
        ):
            return True
    return False


_VERSION_WORD = re.compile(r"(?i)\b(?:api\s+)?version\s+`?(v?\d[\w.-]*)")
_VERSION_LABEL = re.compile(r"^(v\d+(?:\.\d+)*|\d{4}-\d{2}(?:-\d{2})?(?:\.\w+)?)$")


def note_version(note: Note) -> str:
    """The API version a note's change ships in, or empty for a change on a date."""
    for text in [note.title, *note.labels]:
        if found := _VERSION_WORD.search(text):
            return found.group(1).rstrip(".,")
    return next((label for label in note.labels if _VERSION_LABEL.match(label.strip())), "")


_IDENTIFIER = re.compile(r"`([A-Za-z_][A-Za-z0-9_.]{2,})`|\"([A-Za-z_][A-Za-z0-9_]{2,})\"")
_SHAPED = re.compile(r"[_.0-9]|[a-z][A-Z]")
_NOT_FIELDS = {"GET", "POST", "PUT", "PATCH", "DELETE", "true", "false", "null", "type"}


def fields(text: str) -> List[str]:
    """Field names a note names, each with its dlt column name beside it."""
    names = [a or b for a, b in _IDENTIFIER.findall(text)]
    found: List[str] = []
    for name in names:
        # a plain lowercase word such as `customer` or `url` matches everywhere
        if name in _NOT_FIELDS or not _SHAPED.search(name):
            continue
        # dlt snake-cases names and joins nested ones with a double underscore
        column = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name).lower().replace(".", "__")
        found.extend([name, column] if column != name else [name])
    return list(dict.fromkeys(found))
