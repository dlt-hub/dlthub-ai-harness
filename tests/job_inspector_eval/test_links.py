"""`links.py`, the one helper both agents write their summary links with.

A link inside an inline code span is broken markdown, and the inspector cites a run as
`dlthub job runs logs <id>`. So a span holding an id becomes the text of the link.
"""

import importlib.util
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parents[2] / "workbench/dlthub-platform/dlthub/agents"
_spec = importlib.util.spec_from_file_location(
    "links", AGENT_DIR / "job-inspector" / "links.py"
)
assert _spec and _spec.loader
links = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(links)

WEB = ("https://app.example", "ws-1")
RUN = "3cecd342-6d50-4332-89f1-005276e75d84"
RUN_URL = f"https://app.example/w/ws-1/runs/{RUN}"
JOB = "jobs.__deployment__.jaffle_shop"
JOB_URL = f"https://app.example/w/ws-1/jobs/{JOB}"


def test_a_citation_span_becomes_the_link_text():
    """The inspector's own citation form: the command a reader would paste."""
    out = links.linkify(f"(`dlthub job runs logs {RUN}` line 42)", WEB)
    assert out == f"([`dlthub job runs logs {RUN}`]({RUN_URL}?output=logs) line 42)"


def test_a_log_citation_opens_the_logs_tab():
    out = links.linkify(f"(`dlthub job runs logs {RUN}` line 20)", WEB)
    assert out == f"([`dlthub job runs logs {RUN}`]({RUN_URL}?output=logs) line 20)"


def test_a_record_citation_opens_the_run_page():
    """`info` names the record, so the link lands on the overview rather than the logs."""
    out = links.linkify(f"(`dlthub job runs info {RUN}`, field `trigger`)", WEB)
    assert out == f"([`dlthub job runs info {RUN}`]({RUN_URL}), field `trigger`)"


def test_a_command_span_takes_the_run_number_beside_it():
    """The command stays pasteable and the reader still sees which run it opens."""
    out = links.linkify(f"(`dlthub job runs logs {RUN}` line 42)", WEB, {RUN: "#19"})
    assert out == f"([`dlthub job runs logs {RUN}` #19]({RUN_URL}?output=logs) line 42)"


def test_a_span_holding_only_an_id_gives_way_to_its_label():
    out = links.linkify(f"run `{RUN}`", WEB, {RUN: "#27"})
    assert out == f"run [#27]({RUN_URL})"


def test_a_span_holding_only_an_id_keeps_the_id_without_a_label():
    out = links.linkify(f"run `{RUN}`", WEB)
    assert out == f"run [`{RUN}`]({RUN_URL})"


def test_a_job_ref_inside_a_longer_span_keeps_the_span():
    out = links.linkify(f"let its `job.success:{JOB}` trigger fire", WEB)
    assert out == f"let its [`job.success:{JOB}`]({JOB_URL}) trigger fire"


def test_a_span_with_no_id_is_left_alone():
    assert links.linkify('set `cursor_path="ordered_at"`', WEB) == 'set `cursor_path="ordered_at"`'


def test_an_id_in_plain_prose_is_linked():
    assert links.linkify(f"plain {RUN} here", WEB) == f"plain [`{RUN}`]({RUN_URL}) here"


def test_a_link_a_quote_cut_in_half_is_left_alone():
    """A check truncates the line it quotes, so a link can lose its closing paren. Linking
    inside what is left nests one link in another."""
    cut = f"closes early: '- [`{JOB}`](https://dlthub.example/w/ws-1/jobs/{JOB[:12]}"
    assert links.linkify(cut, WEB) == cut


def test_a_link_already_written_is_left_alone():
    already = f"see [`{RUN}`](https://elsewhere/x)"
    assert links.linkify(already, WEB) == already


def test_nothing_is_linked_without_a_workspace():
    assert links.linkify(f"run `{RUN}`", ("", "")) == f"run `{RUN}`"


def test_run_labels_take_the_run_number_and_skip_a_run_without_one():
    labels = links.run_labels([
        {"inspector_run_id": RUN, "inspector_run_number": 114,
         "failed_run_id": "f" * 8 + "-1111-4111-8111-111111111111", "failed_run_number": None},
    ])
    assert labels == {RUN: "#114"}


def test_a_platform_lookup_that_cannot_connect_yields_no_labels():
    """Outside a connected workspace there is nothing to read, and the ids keep their uuids."""
    assert links.labels_from_platform(f"run `{RUN}`") == {}


def test_a_text_naming_no_run_asks_the_platform_nothing():
    assert links.labels_from_platform("no ids here") == {}


def test_link_summary_links_the_summary_and_keeps_the_rest(monkeypatch):
    """The `outputs_validator` of the reference form: the launcher stores what it returns."""
    monkeypatch.setattr(links, "web_ui", lambda: WEB)
    monkeypatch.setattr(links, "labels_from_platform", lambda text: {RUN: "#45"})
    output = {
        "status": "succeeded",
        "summary": f"(`dlthub job runs logs {RUN}` line 36)",
        "classification": "config",
    }

    out = links.link_summary(output)

    assert out["summary"] == f"([`dlthub job runs logs {RUN}` #45]({RUN_URL}?output=logs) line 36)"
    assert out["status"] == "succeeded" and out["classification"] == "config"
    assert output["summary"] == f"(`dlthub job runs logs {RUN}` line 36)"


def test_link_summary_returns_an_output_without_a_summary_as_it_came():
    output = {"status": "aborted", "summary": ""}
    assert links.link_summary(output) is output


def test_link_summary_outside_a_workspace_keeps_the_text():
    """`web_ui` resolves nothing on a local replay, so the ids stay as the model wrote them."""
    assert links.link_summary({"summary": f"run `{RUN}`"})["summary"] == f"run `{RUN}`"
