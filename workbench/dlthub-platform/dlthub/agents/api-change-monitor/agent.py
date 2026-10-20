"""Hooks and the per-API job of the api-change-monitor agent.

`prepare` finds the APIs production code calls, reads their release notes and rules
out the notes that touch nothing here. `validate_input` hands all APIs to one model run;
`run_per_api` gives each API with notes left its own run and merges them in `report`.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dataclasses import dataclass

from . import discovery, guess, history, release_notes, report, tracking
from .discovery import FoundApi

DEFAULT_WINDOW = timedelta(days=7)
# an older note naming a date this close comes back into the window
DEADLINE_AHEAD = timedelta(days=60)
# how far a first run looks back for notes about the version the workspace pins
LOOKBACK = timedelta(days=365)
# a newest entry this old is reported, since the source may have stopped updating
STALE = timedelta(days=180)
# wording of a note that announces something stops working
_ENDING = re.compile(
    r"(?i)deprecat|sunset|retire|remov|end[- ]of[- ]life|unsupported|out of support|"
    r"no longer (?:supported|available)|breaking|discontinu|shut ?down"
)
RULED_OUT_LINES = 30
# names a note must name, with none matching, before a note with no endpoint is ruled out
MIN_FIELDS = 3
# tokens the per-API runs of one job may spend together; each run has its own limits too
MAX_JOB_TOKENS = 3_000_000


def resolve_since(inputs: Dict[str, Any], today: date) -> date:
    """The first day of the window: `since`, else the schedule's interval, else a week."""
    given = str(inputs.get("since") or "").strip()
    if given:
        return date.fromisoformat(given[:10])
    run_context = inputs.get("run_context") or {}
    start, end = run_context.get("interval_start"), run_context.get("interval_end")
    # a point-in-time trigger carries start == end, which is no window
    if start and end and str(start) != str(end):
        return datetime.fromisoformat(str(start)).date()
    return today - DEFAULT_WINDOW


def reviewed_versions(given: str) -> Dict[str, str]:
    """`acme=2026.2, other=1.4` as a mapping of API name to the version reviewed."""
    pairs = (item.partition("=") for item in given.split(","))
    return {name.strip().lower(): version.strip() for name, _, version in pairs if version}


def sources_of(api: FoundApi) -> List[str]:
    if api.url:
        return [api.url]
    return list(api.known.sources) if api.known else []


@dataclass
class Coverage:
    # the newest dated entry seen per API, across all its sources
    latest: Dict[str, date]
    # APIs with a source that carries no date at all
    undated: List[str]


def names_pin(note: release_notes.Note, tokens: List[str]) -> List[str]:
    """The pinned versions a note names outside an endpoint path, such as `v1`."""
    text = f"{note.title}\n{note.text}"
    # a version inside an endpoint path such as `/v1/deals` is no mention of it
    return [t for t in tokens if re.search(rf"(?<![\w./]){re.escape(t)}(?![\w/])", text)]


def read_notes(
    apis: List[FoundApi],
    since: date,
    today: date,
    reviewed: Dict[str, str],
    fetch: release_notes.Fetch = release_notes.fetch_text,
    lookback_pins: Optional[Dict[str, List[str]]] = None,
    coverage: Optional[Coverage] = None,
) -> Tuple[List[release_notes.Note], Dict[str, List[str]]]:
    """The notes of every API with a source, and what could not be read, per API."""
    notes: List[release_notes.Note] = []
    problems: Dict[str, List[str]] = {}
    coverage = coverage if coverage is not None else Coverage({}, [])
    for api in apis:
        topics = api.known.topics if api.known and not api.url else []
        version = api.known.version if api.known and not api.url else None
        for url in sources_of(api):
            try:
                # parse the whole history: an old note can name a deadline still ahead
                found = release_notes.parse(
                    api.name, url, fetch(url), date.min, today, topics, version
                )
            except Exception as ex:  # one source down must not cost the others
                problems.setdefault(api.name, []).append(f"{url}: {type(ex).__name__}: {ex}"[:300])
                continue
            dated = [n.published for n in found if n.published]
            if dated:
                newest = max(dated)
                coverage.latest[api.name] = max(newest, coverage.latest.get(api.name, newest))
            elif found and api.name not in coverage.undated:
                coverage.undated.append(api.name)
            seen = reviewed.get(api.name)
            pins = (lookback_pins or {}).get(api.name, [])
            for note in found:
                if seen and f"version {seen}" in note.labels:
                    continue
                if note.published is None or note.published >= since:
                    notes.append(note)
                elif deadline := release_notes.upcoming(note, today, DEADLINE_AHEAD):
                    note.labels.append(f"deadline {deadline.isoformat()}")
                    notes.append(note)
                elif (
                    # a first run has no earlier report, so it looks back for what still applies
                    pins
                    and note.published >= today - LOOKBACK
                    and names_pin(note, pins)
                    and _ENDING.search(f"{note.title}\n{note.text}")
                ):
                    note.labels.append(f"earlier note on pinned {', '.join(names_pin(note, pins))}")
                    notes.append(note)
    return notes, problems


def link_models(
    notes: List[release_notes.Note], lines: List[Tuple[str, str]], into: str = "models"
) -> None:
    """Record on each note the lines naming a field it names, models or pipeline code."""
    for note in notes:
        found_in: List[str] = getattr(note, into)
        names = release_notes.fields(f"{note.title}\n{note.text}")
        if not names:
            continue
        # a name matches whole, or as one segment of a dlt column path like `a__name__b`
        alternatives = "|".join(map(re.escape, names))
        pattern = re.compile(
            rf"(?<![A-Za-z0-9])(?:[A-Za-z0-9_]*__)?({alternatives})(?:__[A-Za-z0-9_]*)?(?![A-Za-z0-9_])"
        )
        for where, line in lines:
            if (found := pattern.search(line)) and len(found_in) < 8:
                found_in.append(f"`{found.group(1)}` in {where}")


def link_calls(notes: List[release_notes.Note], paths: List[Tuple[str, str]]) -> None:
    """Record on each note the workspace calls of the endpoints it names."""
    for note in notes:
        for template in release_notes.endpoints(f"{note.title}\n{note.text}"):
            for path, where in paths:
                call = f"`{template}` as `{path}` ({where})"
                if release_notes.path_matches(template, path) and call not in note.calls:
                    note.calls.append(call)


def triage(
    notes: List[release_notes.Note], pins: Dict[str, List[str]]
) -> Tuple[List[release_notes.Note], List[release_notes.Note]]:
    """Notes the model reads, and notes the hook rules out as touching nothing here."""
    kept, ruled_out = [], []
    for note in notes:
        text = f"{note.title}\n{note.text}"
        # a missed endpoint is strong evidence, a few missed names are not: one stray
        # identifier such as an exception class must not hide a note
        named = release_notes.endpoints(text) or len(release_notes.fields(text)) >= MIN_FIELDS
        note.pinned = names_pin(note, pins.get(note.api, []))
        pinned = bool(note.pinned)
        flagged = {"imminent", "not parsed"} & set(note.labels)
        # only a note whose names were all checked and none matched is ruled out
        if named and not (note.calls or note.models or note.code or pinned or flagged):
            ruled_out.append(note)
        else:
            kept.append(note)
    return kept, ruled_out


def render_ruled_out(ruled_out: List[release_notes.Note], apis: List[str]) -> str:
    """One line per ruled-out note, per API, so the model can overrule the hook."""
    lines = []
    for api in apis:
        own = [n for n in ruled_out if n.api == api]
        if own:
            lines.append(f"- `{api}`: {len(own)} notes")
            lines.extend(f"  - {n.title[:120]}" for n in own[:RULED_OUT_LINES])
            if len(own) > RULED_OUT_LINES:
                lines.append(f"  - and {len(own) - RULED_OUT_LINES} more")
    return "\n".join(lines) or "None."


def render_apis(apis: List[FoundApi], problems: Dict[str, List[str]]) -> str:
    """One bullet per API: how it was found and where its release notes come from."""
    lines = []
    for api in apis:
        how = (
            "named in the `apis` input"
            if api.origin == "configured"
            else "found in production code"
        )
        where = ", ".join(api.evidence) or "no workspace file"
        sources = sources_of(api)
        if not sources:
            state = "release notes unknown: find them"
        elif len(problems.get(api.name, [])) == len(sources):
            state = "release notes not read: find them"
        else:
            state = "release notes read from " + ", ".join(sources)
            if api.guessed:
                state += " (found at a common changelog location: check it is the official one)"
            elif api.known and api.known.workspace and not api.url:
                state += " (the workspace's own source)"
        lines.append(f"- `{api.name}`: {how} ({where}); {state}")
        pins = discovery.pinned_versions(Path.cwd(), api)
        lines.append(f"  - pinned version: {'; '.join(pins)}" if pins else "  - pinned version: none found")
    return "\n".join(lines)


@dataclass
class Prep:
    root: Path
    since: date
    apis: List[FoundApi]
    kept: List[release_notes.Note]
    ruled_out: List[release_notes.Note]
    problems: Dict[str, List[str]]
    coverage: Coverage


def prepare(inputs: Dict[str, Any], root: Path, today: date, first_run: bool = True) -> Prep:
    """Everything the script decides before any model runs, for every API."""
    from dlt.hub import run

    try:
        since = resolve_since(inputs, today)
    except ValueError:
        raise run.JobAbortedException(
            f"`since` is {inputs.get('since')!r}; give a date as YYYY-MM-DD.", {}
        )
    discovered = discovery.discover(root)
    given = str(inputs.get("apis") or "")
    apis = discovery.configure(given, discovered, root) if given.strip() else discovered
    if not apis:
        raise run.JobAbortedException(
            "Production code calls no API this agent recognises. Name them in the `apis`"
            " input, as `name=<release notes url>`.",
            {},
        )
    for api in apis:
        # an API nobody knows a source for is tried at the common changelog places
        if not sources_of(api) and api.hosts:
            found = guess.find_source(api.name, sorted(api.hosts), today)
            if found:
                api.url, api.guessed = found, True
    reviewed = reviewed_versions(str(inputs.get("reviewed_versions") or ""))
    pins = {api.name: discovery.pinned_tokens(discovery.pinned_versions(root, api)) for api in apis}
    coverage = Coverage({}, [])
    notes, problems = read_notes(
        apis, since, today, reviewed, lookback_pins=pins if first_run else None, coverage=coverage
    )
    models = discovery.model_lines(root)
    for api in apis:
        # an API's notes are matched against the code that calls that API only
        own = [n for n in notes if n.api == api.name]
        files = discovery.api_files(root, api)
        link_calls(own, discovery.resource_paths(root, files))
        link_models(own, models)
        link_models(own, discovery.code_lines(root, files), into="code")
    kept, ruled_out = triage(notes, pins)
    return Prep(root, since, apis, kept, ruled_out, problems, coverage)


def model_inputs(prep: Prep, inputs: Dict[str, Any], apis: List[FoundApi]) -> Dict[str, Any]:
    """The rendered inputs of one model run over the given APIs."""
    names = [api.name for api in apis]
    kept = [n for n in prep.kept if n.api in names]
    ruled_out = [n for n in prep.ruled_out if n.api in names]
    problems = {name: prep.problems[name] for name in names if name in prep.problems}
    return {
        **inputs,
        "apis": ", ".join(names),
        "since": prep.since.isoformat(),
        "apis_found": render_apis(apis, problems),
        "release_notes": release_notes.render(kept, problems, names, prep.since),
        "ruled_out": render_ruled_out(ruled_out, names),
        "workspace_usage": discovery.render_usage(prep.root, apis),
    }


def needs_model(prep: Prep, api: FoundApi) -> bool:
    """True when an API has notes left, or release notes only a search can find."""
    sources = sources_of(api)
    unread = len(prep.problems.get(api.name, [])) >= len(sources)
    return unread or any(n.api == api.name for n in prep.kept)


def _coverage_note(prep: Prep, api: str, today: date) -> str:
    """The newest entry seen for an API, with a warning when it may be a coverage gap."""
    if api in prep.coverage.undated and api not in prep.coverage.latest:
        return "undated"
    newest = prep.coverage.latest.get(api)
    if newest is None:
        return ""
    age = (today - newest).days
    return f"{newest.isoformat()} ({age} days ago)" if today - newest > STALE else newest.isoformat()


def _origin(api: FoundApi) -> str:
    """Where an API's release notes came from, as the output's `sources` names it."""
    if api.guessed:
        return "guessed"
    if api.url or (api.known and api.known.workspace):
        return "configured"
    return "registry"


def validate_input(inputs: Dict[str, Any]) -> Dict[str, Any]:
    prep = prepare(inputs, Path.cwd(), date.today())
    return model_inputs(prep, inputs, prep.apis)


def load_previous(run_id: str) -> Tuple[Optional[List[Dict[str, Any]]], str]:
    """The earlier run's findings; a test replaces this to skip the platform."""
    return history.previous_findings(run_id)


async def run_per_api(
    run_context: Dict[str, Any],
    apis: str = "",
    since: str = "",
    reviewed_versions: str = "",
    max_job_tokens: int = MAX_JOB_TOKENS,
) -> Dict[str, Any]:
    """The job's report: one model run per API with notes left, merged in Python."""
    from dlt._workspace.deployment.agent.exceptions import AgentRunFailed

    inputs = {"apis": apis, "since": since, "reviewed_versions": reviewed_versions}
    inputs["run_context"] = run_context
    # the earlier report decides whether this run has to look back past its window
    previous, note = load_previous(str(run_context.get("run_id") or ""))
    prep = prepare(inputs, Path.cwd(), date.today(), first_run=not previous)
    loop = run_context["ai_loop"]
    results: List[report.ApiResult] = []
    spent = 0
    for api in prep.apis:
        result = report.ApiResult(
            api=api.name,
            status="skipped",
            kept=sum(n.api == api.name for n in prep.kept),
            ruled_out=sum(n.api == api.name for n in prep.ruled_out),
            sources=sources_of(api),
            origin=_origin(api),
            latest=_coverage_note(prep, api.name, date.today()),
            unread=bool(sources_of(api)) and len(prep.problems.get(api.name, [])) >= len(sources_of(api)),
        )
        results.append(result)
        if not needs_model(prep, api):
            continue
        if spent >= max_job_tokens:
            result.status, result.reason = "not_run", f"the job spent its {max_job_tokens:,} tokens"
            continue
        try:
            output = await loop.run(inputs=model_inputs(prep, inputs, [api]))
        except AgentRunFailed as ex:
            # one API's run hitting a limit must not cost the report on the others
            result.status, result.reason = "not_run", f"its run failed: {ex}"[:300]
            spent += loop.tokens_used
            continue
        trace = loop.trace
        spent += trace["total_tokens"]
        result.output, result.status = output, output.get("status", "failed")
        result.turns, result.tokens = trace["turn_count"], trace["total_tokens"]
    today = date.today()
    changes = [{**c, "api": r.api} for r in results for c in (r.output or {}).get("changes") or []]
    unchecked = [r.api for r in results if r.status == "not_run"]
    tracked, carried, resolved = tracking.track(changes, previous or [], prep.root, today, unchecked)
    return report.merge(
        results, prep.since.isoformat(), today.isoformat(), tracked, carried, resolved, note
    )
