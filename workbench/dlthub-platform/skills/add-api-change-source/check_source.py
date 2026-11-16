"""Prove a release note source with the api-change-monitor agent's own reader.

Run from the workspace root, where the dlthub-platform toolkit is installed:
  uv run python <skill dir>/check_source.py apis
  uv run python <skill dir>/check_source.py check <name> <url> [--topics A,B] [--version RE]
  uv run python <skill dir>/check_source.py window <name> [--since YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any, List

AGENT_DIRS = [
    f".{host}/dlthub/agents/dlthub-platform/api-change-monitor"
    for host in ("claude", "cursor", "agents")
]


def load_agent() -> Any:
    """The installed agent's `agent.py`, imported the way a run imports it."""
    from dlt._workspace.deployment.agent.manifest import load_agent_module

    for folder in AGENT_DIRS:
        if (Path.cwd() / folder / "AGENT.md").is_file():
            return load_agent_module(folder)
    sys.exit(
        "api-change-monitor is not installed here. Run from the workspace root after"
        " `dlthub ai toolkit install dlthub-platform`."
    )


def module(agent: Any, name: str) -> Any:
    from importlib import import_module

    return import_module(f"{agent.__package__}.{name}")


def show_apis(agent: Any) -> None:
    """Every API the agent finds in deployed code, and where its release notes come from."""
    apis = agent.discovery.discover(Path.cwd())
    if not apis:
        print("No API found in the code __deployment__.py deploys.")
    for api in apis:
        sources = agent.sources_of(api)
        origin = agent._origin(api) if sources else "none: guessed or searched at run time"
        print(f"- {api.name}: hosts {', '.join(sorted(api.hosts)) or '-'}")
        print(f"    found in: {', '.join(api.evidence) or '-'}")
        print(f"    release notes: {', '.join(sources) or '-'} ({origin})")


def check(agent: Any, name: str, url: str, topics: List[str], version: str) -> int:
    """Fetch and parse one candidate source; exit code 1 when the agent cannot date it."""
    notes_module = module(agent, "release_notes")
    try:
        body = notes_module.fetch_text(url)
    except Exception as ex:
        print(f"Could not fetch {url}: {type(ex).__name__}: {ex}")
        return 1
    pattern = re.compile(version) if version else None
    notes = notes_module.parse(name, url, body, date.min, date.today(), topics, pattern)
    head = body.lstrip()[:600].lower()
    kind = "feed" if "<rss" in head or "<feed" in head else "html" if "<html" in head else "text"
    dated = sorted((n for n in notes if n.published), key=lambda n: n.published, reverse=True)
    print(f"{url}\n  format: {kind}, {len(body):,} characters")
    if kind == "feed":
        every = notes_module.parse(name, url, body, date.min, date.today())
        labels = Counter(label for n in every for label in n.labels)
        print(f"  feed categories: {', '.join(f'{k} ({v})' for k, v in labels.most_common(20)) or 'none'}")
    print(f"  notes: {len(notes)}, dated: {len(dated)}")
    for note in dated[:8]:
        print(f"    {note.published}  {note.title[:90]}")
    undated = [n for n in notes if not n.published]
    for note in undated[:3]:
        print(f"    (undated) {note.title[:80]}  labels: {', '.join(note.labels)}")
    if dated:
        print(f"  newest entry: {dated[0].published}")
        # a big page cut into few notes keeps most of its entries out of reach
        if len(body) > 100_000 and len(dated) < 5:
            print(
                f"  warning: {len(body):,} characters gave only {len(dated)} dated notes;"
                " the page may date its entries in a way the reader misses. Look for a feed"
                " or a .md variant before using it."
            )
        return 0
    if pattern and undated and any(label.startswith("version ") for label in undated[0].labels):
        print("  no dates, but the version pattern labels the page: usable for a per-release page")
        return 0
    print("  The agent cannot date this page: try a feed, a .md variant or another page.")
    return 1


def window(agent: Any, name: str, since: date) -> None:
    """The release notes, ruled-out titles and usage the model would get for one API."""
    inputs = {"apis": name, "since": since.isoformat(), "run_context": {}}
    prep = agent.prepare(inputs, Path.cwd(), date.today(), first_run=False)
    rendered = agent.model_inputs(prep, inputs, prep.apis)
    for key in ("apis_found", "release_notes", "ruled_out"):
        print(f"===== {key}\n{rendered[key]}\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("apis", help="list the APIs the agent finds and their sources")
    one = commands.add_parser("check", help="parse a candidate release note url")
    one.add_argument("name")
    one.add_argument("url")
    one.add_argument("--topics", default="", help="comma-separated feed categories to keep")
    one.add_argument("--version", default="", help="regex with one group, for undated pages")
    view = commands.add_parser("window", help="show what the model reads for one API")
    view.add_argument("name")
    view.add_argument("--since", default=(date.today() - timedelta(days=30)).isoformat())
    args = parser.parse_args()

    agent = load_agent()
    if args.command == "apis":
        show_apis(agent)
        return 0
    if args.command == "check":
        topics = [t.strip() for t in args.topics.split(",") if t.strip()]
        return check(agent, args.name.lower(), args.url, topics, args.version)
    window(agent, args.name.lower(), date.fromisoformat(args.since))
    return 0


if __name__ == "__main__":
    sys.exit(main())
