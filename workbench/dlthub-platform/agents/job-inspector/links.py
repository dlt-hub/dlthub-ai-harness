"""Rewrite run ids and job refs in an agent summary as links to their web UI pages."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

__all__ = ["web_ui", "linkify", "run_labels", "labels_from_platform", "link_summary"]


def web_ui() -> Tuple[str, str]:
    """The web UI base and the workspace id, both empty when not available."""
    try:
        from dlt._workspace._workspace_context import active
        from dlt_runtime import urls

        return urls.web_ui_base(), str(active().runtime_config.workspace_id or "")
    except Exception:  # links are optional: no runtime or workspace leaves the text plain
        return "", ""


_MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\([^)]*\)")
"""An existing markdown link, left as is."""

_UNTERMINATED_LINK = re.compile(r"\[[^\]]*\]\([^)]*$|\[[^\]]*$")
"""A link cut by a truncated quote, left as is so links do not nest."""

_CODE_SPAN = re.compile(r"`[^`\n]+`")
"""An inline code span; it becomes link text because a link inside a span does not render."""

_BARE_RUN_ID = re.compile(
    r"\b([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\b"
)
_BARE_JOB_REF = re.compile(r"\b(jobs\.[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+)\b")

_LOG_COMMAND = re.compile(r"\bjob\s+(?:runs\s+)?logs\b")
"""A log command; its link opens the logs tab of the run page."""


def run_labels(entries: Sequence[Dict[str, Any]]) -> Dict[str, str]:
    """`#<number>` per run id, from the `*_run_id` and `*_run_number` fields of the entries."""
    labels: Dict[str, str] = {}
    for entry in entries:
        for prefix in ("inspector", "failed"):
            run_id = str(entry.get(f"{prefix}_run_id") or "").lower()
            number = entry.get(f"{prefix}_run_number")
            if run_id and number not in (None, ""):
                labels.setdefault(run_id, f"#{number}")
    return labels


def labels_from_platform(text: str) -> Dict[str, str]:
    """`#<number>` per run id in `text`, read from the platform; unknown ids get no label."""
    found = {match.group(1).lower() for match in _BARE_RUN_ID.finditer(text or "")}
    if not found:
        return {}
    try:
        import dlthub_sdk
        from dlt._workspace._workspace_context import active

        config = active().runtime_config
        # the token is not renewed: an expired JWT costs only the labels
        token = str(config.api_key or config.auth_token or "")
        if not token or not config.workspace_id:
            return {}
        runtime = dlthub_sdk.connect(
            token=token, base_url=config.api_base_url or "https://api.dlthub.com"
        )
        workspace = runtime.workspaces.get(id=config.workspace_id)
    except Exception:  # labels are best effort, a run id still links without one
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
    """Rewrite run ids and job refs in `text` as links, leaving existing links unchanged.

    `labels` gives the link text for a run id that stands alone.
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


def link_summary(output: Dict[str, Any]) -> Dict[str, Any]:
    """The agent output with run ids and job refs in its summary written as links."""
    summary = output.get("summary", "")
    if not summary or not isinstance(summary, str):
        return output
    return {**output, "summary": linkify(summary, web_ui(), labels_from_platform(summary))}


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
    """A code span holding an id rewritten as the text of a link; other spans unchanged."""
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
    """The query for a run link: `?output=logs` for a citation of a log command, else empty."""
    # dlt_runtime.urls has no parameter for the logs tab
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
