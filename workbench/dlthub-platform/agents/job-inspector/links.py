"""Run ids and job refs in an agent summary, written as links to their web UI pages.

An agent names a run by its uuid, because that is what a person pastes into
`dlthub job runs logs`. A uuid in prose is unreadable, so the summary goes through
`linkify` after the loop: the uuid stays in the link target, which is the run's page in the
platform web UI, and the text becomes what the reader needs, a run number where the caller
knows one.

The inspector and the evaluator both use this module, so a run reads the same way in both
summaries. It ships in the inspector's folder and the evaluator loads it from there; the
two install side by side as one toolkit.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import quote

__all__ = ["web_ui", "linkify", "run_labels", "labels_from_platform", "agent_run_links"]


def web_ui() -> Tuple[str, str]:
    """The web UI base and the workspace id, both empty when they cannot be resolved.

    `dlt_runtime.urls` turns the API base url into the UI one, the mapping the CLI prints a
    run link with. A local replay has neither, and the summary then names runs by id.
    """
    try:
        from dlt._workspace._workspace_context import active
        from dlt_runtime import urls

        return urls.web_ui_base(), str(active().runtime_config.workspace_id or "")
    except Exception:
        return "", ""


_MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\([^)]*\)")
"""A link already written. Nothing inside one is linked again, and neither is its target."""

_UNTERMINATED_LINK = re.compile(r"\[[^\]]*\]\([^)]*$|\[[^\]]*$")
"""A link a quote cut in half. A check truncates the line it quotes, so a link the agent
already wrote can lose its closing paren; linking inside what is left nests one link in
another. Everything from the opening bracket on is left alone."""

_CODE_SPAN = re.compile(r"`[^`\n]+`")
"""An inline code span. A link inside one is broken markdown, so the span becomes the text of
the link instead: the inspector cites a run as `dlthub job runs logs <id>`, and that whole
command is what a reader clicks."""

_BARE_RUN_ID = re.compile(
    r"\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b"
)
_BARE_JOB_REF = re.compile(r"\b(jobs\.[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+)\b")

_LOG_COMMAND = re.compile(r"\bjob\s+(?:runs\s+)?logs\b")
"""A citation that opens a log rather than a run record. The run page defaults to its
overview, so a log citation carries `?output=logs` and lands the reader on the lines it
quotes."""



def agent_run_links(
    text: str, links: Tuple[str, str] = ("", ""), job_refs: Optional[Mapping[str, str]] = None
) -> str:
    """Moves the run links of agent jobs onto the route the web app serves them from.

    A run of an agent job has its page at `/agents/<job ref>/runs/<id>`; `/runs/<id>` is the
    route of a plain job run, and it is what `dlt_runtime.urls` builds for every run alike. A
    run id says nothing about the job behind it, so the caller passes the job ref of each run
    it knows to be an agent's. The rewrite keeps whatever query the link carries.
    """
    base, workspace = links
    if not base or not workspace or not text:
        return text
    for run_id, job_ref in (job_refs or {}).items():
        if not run_id or not job_ref:
            continue
        text = text.replace(
            f"{base}/w/{workspace}/runs/{run_id}",
            f"{base}/w/{workspace}/agents/{quote(str(job_ref), safe='')}/runs/{run_id}",
        )
    return text


def run_labels(entries: Sequence[Dict[str, Any]]) -> Dict[str, str]:
    """Link text per run id: the run number, which the bullet writes the job ref beside.

    A uuid tells a reader nothing, so it goes in the link target and `#27` goes in the text,
    the way the inspector's "Cite the artifact in the bullet" names an artifact rather than
    pointing at one. A run whose number the caller does not hold keeps its uuid.
    """
    labels: Dict[str, str] = {}
    for entry in entries:
        for prefix in ("inspector", "failed"):
            run_id = str(entry.get(f"{prefix}_run_id") or "").lower()
            number = entry.get(f"{prefix}_run_number")
            if run_id and number not in (None, ""):
                labels.setdefault(run_id, f"#{number}")
    return labels


def labels_from_platform(text: str) -> Dict[str, str]:
    """`#<number>` per run id the text names, read from the platform.

    The evaluator builds its labels from the runs it already holds. An agent summary names
    runs the caller never fetched, the producer's among them, so they are looked up here, one
    call per distinct id. A lookup that fails leaves that id as its uuid, which is what the
    citation carries anyway: the label is a readability gain, not evidence.

    The token is read once rather than renewed. A runner holds a service `api_key` that does
    not expire; a developer machine holds a JWT that does, and an expired one costs the
    labels and nothing else.
    """
    found = {match.group(1).lower() for match in _BARE_RUN_ID.finditer(text or "")}
    if not found:
        return {}
    try:
        import dlthub_sdk
        from dlt._workspace._workspace_context import active

        config = active().runtime_config
        token = str(config.api_key or config.auth_token or "")
        if not token or not config.workspace_id:
            return {}
        runtime = dlthub_sdk.connect(
            token=token, base_url=config.api_base_url or "https://api.dlthub.com"
        )
        workspace = runtime.workspaces.get(id=config.workspace_id)
    except Exception:
        return {}
    labels: Dict[str, str] = {}
    for run_id in found:
        try:
            number = workspace.job_runs.get(id=run_id).number
        except Exception:
            continue
        if number not in (None, ""):
            labels[run_id] = f"#{number}"
    return labels


def linkify(
    text: str,
    links: Tuple[str, str] = ("", ""),
    labels: Optional[Mapping[str, str]] = None,
) -> str:
    """Every run id and job ref in a line, written as a link to its page.

    A run id is a link wherever it falls: a summary bullet, a reasoning a check wrote, a
    table cell. `labels` gives the link its text where the id stands alone, so a reader sees
    the run number and the uuid stays in the target. Text already inside a link is left
    alone, and so is the target of one.
    """
    base, workspace = links
    if not base or not workspace or not text:
        return text
    written: List[str] = []
    last = 0
    for match in _MARKDOWN_LINK.finditer(text):
        written.append(_outside_links(text[last:match.start()], base, workspace, labels or {}))
        written.append(match.group(0))
        last = match.end()
    written.append(_outside_links(text[last:], base, workspace, labels or {}))
    return "".join(written)


def _outside_links(text: str, base: str, workspace: str, labels: Mapping[str, str]) -> str:
    """Link the ids in text that sits outside an existing link, spans included."""
    if cut := _UNTERMINATED_LINK.search(text):
        return _outside_links(text[:cut.start()], base, workspace, labels) + text[cut.start():]
    written: List[str] = []
    last = 0
    for match in _CODE_SPAN.finditer(text):
        written.append(_bare(text[last:match.start()], base, workspace, labels))
        written.append(_span(match.group(0), base, workspace, labels))
        last = match.end()
    written.append(_bare(text[last:], base, workspace, labels))
    return "".join(written)


def _span(span: str, base: str, workspace: str, labels: Mapping[str, str]) -> str:
    """A code span holding an id, written as the text of a link to that id's page.

    The span is the text and never the target of the link: a link wrapped around a code span
    renders, a link written inside one prints its markup. A span carrying no id is left as it
    stands.
    """
    inner = span[1:-1]
    if run_match := _BARE_RUN_ID.search(inner):
        run_id = run_match.group(1)
        label = labels.get(run_id.lower(), "")
        # a span that is only the id gives way to the label; a command keeps the text a
        # reader pastes and takes the number beside it
        if inner == run_id:
            shown = label or span
        else:
            shown = f"{span} {label}" if label else span
        return f"[{shown}]({base}/w/{workspace}/runs/{run_id}{_run_query(inner)})"
    if job_match := _BARE_JOB_REF.search(inner):
        return f"[{span}]({base}/w/{workspace}/jobs/{job_match.group(1)})"
    return span


def _run_query(inner: str) -> str:
    """What a run link carries beyond its id: the logs tab, and the line cited there.

    `output=logs` is the tab the platform prints in its own run links. The line the citation
    names is printed beside the link, since the web app reads no parameter for it that this
    repository can see: `dlt_runtime.urls` builds workspace, pipeline, job and run URLs and
    stops there.
    """
    if not _LOG_COMMAND.search(inner):
        return ""
    return "?output=logs"


def _bare(text: str, base: str, workspace: str, labels: Mapping[str, str]) -> str:
    """Ids written as plain prose, with no span around them."""
    def run(match: "re.Match[str]") -> str:
        run_id = match.group(1)
        shown = labels.get(run_id.lower()) or f"`{run_id}`"
        return f"[{shown}]({base}/w/{workspace}/runs/{run_id})"

    def job(match: "re.Match[str]") -> str:
        return f"[`{match.group(1)}`]({base}/w/{workspace}/jobs/{match.group(1)})"

    return _BARE_JOB_REF.sub(job, _BARE_RUN_ID.sub(run, text))
