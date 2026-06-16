#!/usr/bin/env python3
"""Run trigger evaluation for a skill across eval workspaces.

Tests whether a skill triggers correctly for a set of queries, and detects
when a competing skill triggers instead (clash). Runs `claude -p` from eval
workspaces where real skills are installed.

Runs against all workspaces defined in config.json.

Output format is compatible with skill-creator's run_eval.py (extended with
`triggered_skill` and `clashes` fields).

Usage:
    python tools/run_trigger_eval.py evals/init/dlthub-router
    python tools/run_trigger_eval.py evals/init/dlthub-router --workspace init-only
    python tools/run_trigger_eval.py evals/init/dlthub-router --runs-per-query 3
"""

import argparse
import json
import os
import re
import select
import subprocess
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVALS_DIR = ROOT / "evals" / ".evals"


def load_config(eval_dir: Path) -> dict[str, dict]:
    """Load workspace configs from config.json."""
    config_path = eval_dir / "config.json"
    if not config_path.exists():
        print(f"ERROR: {config_path} not found", file=sys.stderr)
        sys.exit(1)
    config = json.loads(config_path.read_text())
    workspaces = config.get(".eval-workspaces")
    if workspaces is None:
        ws_config = config.get(".eval-workspace", {})
        workspaces = {"default": ws_config}
    return workspaces


def find_workspace(eval_dir: Path, ws_id: str, agent: str = "claude") -> Path:
    """Find workspace path for a given workspace ID and agent.

    Mirrors create_eval_workspace.ws_name_for: claude paths are unsuffixed;
    cursor/codex get a `--<agent>` suffix so all three coexist.
    """
    rel = eval_dir.relative_to(ROOT / "evals")
    name = str(rel).replace("/", "--").replace("\\", "--") + "--" + ws_id
    if agent != "claude":
        name += "--" + agent
    ws = EVALS_DIR / name
    if not ws.is_dir():
        print(f"ERROR: Workspace not found: {ws}", file=sys.stderr)
        print(
            f"Run: uv run python tools/create_eval_workspace.py "
            f"{eval_dir.relative_to(ROOT)} --agent {agent}",
            file=sys.stderr,
        )
        sys.exit(1)
    return ws


def run_single_query(
    query: str,
    workspace: str,
    timeout: int,
    agent: str = "claude",
    model: str | None = None,
) -> str | None:
    """Run one query and return the skill name that triggered, or None.

    Dispatches to a per-agent runner. Each agent signals a skill trigger
    differently (see the per-agent functions), but they share the return
    contract: the name of the skill that triggered for this query, or None.
    """
    if agent == "claude":
        return _run_claude(query, workspace, timeout, model)
    if agent == "codex":
        return _run_codex(query, workspace, timeout, model)
    if agent == "cursor":
        return _run_cursor(query, workspace, timeout, model)
    raise ValueError(f"Unknown agent: {agent}")


def _run_claude(
    query: str,
    workspace: str,
    timeout: int,
    model: str | None = None,
) -> str | None:
    """Run a query via claude -p. Return the skill name that triggered, or None.

    Claude exposes skills as a native `Skill` tool, so a trigger is the first
    tool_use in the stream being `Skill` (its `input.skill` is the name).
    """
    cmd = [
        "claude",
        "-p",
        query,
        "--output-format",
        "stream-json",
        "--verbose",
        "--include-partial-messages",
        "--no-session-persistence",
    ]
    if model:
        cmd.extend(["--model", model])

    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        cwd=workspace,
        env=env,
    )

    start_time = time.time()
    buffer = ""
    pending_skill = False
    accumulated_json = ""

    try:
        while time.time() - start_time < timeout:
            if process.poll() is not None:
                remaining = process.stdout.read()
                if remaining:
                    buffer += remaining.decode("utf-8", errors="replace")
                break

            ready, _, _ = select.select([process.stdout], [], [], 1.0)
            if not ready:
                continue

            chunk = os.read(process.stdout.fileno(), 8192)
            if not chunk:
                break
            buffer += chunk.decode("utf-8", errors="replace")

            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                line = line.strip()
                if not line:
                    continue

                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Early detection via stream events
                if event.get("type") == "stream_event":
                    se = event.get("event", {})
                    se_type = se.get("type", "")

                    if se_type == "content_block_start":
                        cb = se.get("content_block", {})
                        if cb.get("type") == "tool_use":
                            tool_name = cb.get("name", "")
                            if tool_name == "Skill":
                                pending_skill = True
                                accumulated_json = ""
                            else:
                                # First tool is not Skill → no skill triggered
                                return None

                    elif se_type == "content_block_delta" and pending_skill:
                        delta = se.get("delta", {})
                        if delta.get("type") == "input_json_delta":
                            accumulated_json += delta.get("partial_json", "")

                    elif se_type in ("content_block_stop", "message_stop"):
                        if pending_skill:
                            return _extract_skill_name(accumulated_json)
                        if se_type == "message_stop":
                            return None

                # Fallback: full assistant message
                elif event.get("type") == "assistant":
                    message = event.get("message", {})
                    for content_item in message.get("content", []):
                        if content_item.get("type") != "tool_use":
                            continue
                        if content_item.get("name") == "Skill":
                            return content_item.get("input", {}).get("skill")
                        return None  # first tool call is not Skill

                elif event.get("type") == "result":
                    return None
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()

    return None


def _extract_skill_name(json_fragment: str) -> str | None:
    """Extract skill name from accumulated JSON fragment."""
    try:
        data = json.loads(json_fragment)
        return data.get("skill")
    except json.JSONDecodeError:
        # Partial JSON — look for "skill":"<name>" pattern
        m = re.search(r'"skill"\s*:\s*"([^"]+)"', json_fragment)
        return m.group(1) if m else None


_SKILL_READ_RE = re.compile(r"\.agents/skills/([a-z0-9][a-z0-9-]*)/SKILL\.md")


def _codex_baseline_skills(workspace: str) -> set[str]:
    """Always-on skills registered in the workspace AGENTS.md.

    On Codex these are read on every turn regardless of the query (the
    "ALWAYS ACTIVATE" bullets, written as `- ``<name>```), so they must be
    excluded when detecting which skill a query actually triggered.
    """
    agents_md = Path(workspace) / "AGENTS.md"
    if not agents_md.is_file():
        return set()
    names = set()
    for line in agents_md.read_text().splitlines():
        m = re.match(r"\s*-\s*`([a-z0-9][a-z0-9-]*)`", line)
        if m:
            names.add(m.group(1))
    return names


def _codex_line_skill(line: str, baseline: set[str]) -> str | None:
    """If a JSONL line is a command reading a non-baseline SKILL.md, return that skill."""
    line = line.strip()
    if not line:
        return None
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return None
    if event.get("type") not in ("item.started", "item.completed"):
        return None
    item = event.get("item", {})
    if item.get("type") != "command_execution":
        return None
    for name in _SKILL_READ_RE.findall(item.get("command", "")):
        if name not in baseline:
            return name
    return None


def _stream_scan_for_skill(cmd, workspace, timeout, line_skill):
    """Run cmd in the workspace, stream stdout JSONL, and return the first
    non-None result of line_skill(line) — i.e. the first detected skill.

    Shared by the codex and cursor runners (both have no native Skill tool and
    signal a trigger by reading a SKILL.md). stdin is closed (codex blocks
    otherwise); stderr is discarded.
    """
    process = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        cwd=workspace,
    )

    start_time = time.time()
    buffer = ""
    try:
        while time.time() - start_time < timeout:
            if process.poll() is not None:
                remaining = process.stdout.read()
                if remaining:
                    buffer += remaining.decode("utf-8", errors="replace")
                break
            ready, _, _ = select.select([process.stdout], [], [], 1.0)
            if not ready:
                continue
            chunk = os.read(process.stdout.fileno(), 8192)
            if not chunk:
                break
            buffer += chunk.decode("utf-8", errors="replace")
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                skill = line_skill(line)
                if skill:
                    return skill
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()

    # Drain any remaining buffered lines after process exit.
    for line in buffer.split("\n"):
        skill = line_skill(line)
        if skill:
            return skill
    return None


def _run_codex(
    query: str,
    workspace: str,
    timeout: int,
    model: str | None = None,
) -> str | None:
    """Run a query via `codex exec --json`. Return the skill that triggered, or None.

    Codex has no native Skill tool: it "activates" a skill by running a shell
    command that reads `.agents/skills/<name>/SKILL.md`. Always-on skills (the
    AGENTS.md "ALWAYS ACTIVATE" bullets) are read every turn, so we exclude them
    and return the first *opt-in* skill whose SKILL.md the query caused to be
    read. Runs read-only so the probe cannot mutate the workspace.
    """
    baseline = _codex_baseline_skills(workspace)
    cmd = ["codex", "exec", query, "--json", "-s", "read-only"]
    if model:
        cmd.extend(["-m", model])
    return _stream_scan_for_skill(
        cmd, workspace, timeout, lambda line: _codex_line_skill(line, baseline)
    )


_CURSOR_SKILL_READ_RE = re.compile(r"\.cursor/skills/([a-z0-9][a-z0-9-]*)/SKILL\.md")


def _cursor_line_skill(line: str) -> str | None:
    """If a JSONL line is a readToolCall on an in-workspace SKILL.md, return that skill."""
    line = line.strip()
    if not line:
        return None
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return None
    if event.get("type") != "tool_call":
        return None
    read_call = event.get("tool_call", {}).get("readToolCall")
    if not read_call:
        return None
    path = read_call.get("args", {}).get("path", "")
    m = _CURSOR_SKILL_READ_RE.search(path)
    return m.group(1) if m else None


def _run_cursor(
    query: str,
    workspace: str,
    timeout: int,
    model: str | None = None,
) -> str | None:
    """Run a query via `cursor-agent -p --output-format stream-json`. Return the
    skill that triggered, or None.

    Cursor has no native Skill tool: it activates a skill by reading the file via
    a `readToolCall` on `.cursor/skills/<name>/SKILL.md`. Return the first such
    in-workspace read. No baseline exclusion: cursor keeps always-on content as
    auto-applied `.mdc` rules, not skill reads; the `.cursor/skills/` path
    requirement excludes stray SKILL.md reads elsewhere in the repo. `--trust`
    runs headlessly (auth via `cursor-agent login` or CURSOR_API_KEY) and lets
    file reads through while rejecting shell/web — enough to detect the trigger.
    """
    cmd = ["cursor-agent", "-p", query, "--output-format", "stream-json", "--trust"]
    if model:
        cmd.extend(["--model", model])
    return _stream_scan_for_skill(cmd, workspace, timeout, _cursor_line_skill)


def run_eval_on_workspace(
    eval_set: list[dict],
    skill_name: str,
    workspace: Path,
    ws_id: str,
    num_workers: int,
    timeout: int,
    runs_per_query: int,
    trigger_threshold: float,
    agent: str,
    model: str | None,
    verbose: bool,
) -> dict:
    """Run eval set against one workspace. Returns results dict."""

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        future_to_info = {}
        for item in eval_set:
            for run_idx in range(runs_per_query):
                future = executor.submit(
                    run_single_query,
                    item["query"],
                    str(workspace),
                    timeout,
                    agent,
                    model,
                )
                future_to_info[future] = (item, run_idx)

        query_results: dict[str, list[str | None]] = {}
        query_items: dict[str, dict] = {}
        for future in as_completed(future_to_info):
            item, _ = future_to_info[future]
            query = item["query"]
            query_items[query] = item
            if query not in query_results:
                query_results[query] = []
            try:
                query_results[query].append(future.result())
            except Exception as e:
                print(f"Warning: query failed: {e}", file=sys.stderr)
                query_results[query].append(None)

    results = []
    total_clashes = 0
    for query, triggered_skills in query_results.items():
        item = query_items[query]
        # Per-workspace expectation override: a query's expected behavior depends on
        # which toolkits are installed. Once the matching workflow toolkit is present,
        # the router should DEFER to that toolkit's entry skill instead of triggering
        # itself — so the same query can be should_trigger=true (cold start) yet
        # should_trigger=false with `expect: <entry-skill>` once installed.
        ws_override = item.get("by_workspace", {}).get(ws_id, {})
        should_trigger = ws_override.get("should_trigger", item["should_trigger"])
        expect_skill = ws_override.get("expect")

        # Count triggers for our skill
        our_triggers = sum(1 for s in triggered_skills if s == skill_name)

        trigger_rate = our_triggers / len(triggered_skills)
        if should_trigger:
            did_pass = trigger_rate >= trigger_threshold
        else:
            did_pass = trigger_rate < trigger_threshold

        entry = {
            "query": query,
            "should_trigger": should_trigger,
            "trigger_rate": trigger_rate,
            "triggers": our_triggers,
            "runs": len(triggered_skills),
            "pass": did_pass,
        }

        # Track clashes only on should-trigger queries (wrong skill stole the trigger)
        if should_trigger:
            other_skills = [s for s in triggered_skills if s is not None and s != skill_name]
            if other_skills:
                clash_skills = sorted(set(other_skills))
                entry["clashes"] = clash_skills
                entry["clash_count"] = len(other_skills)
                total_clashes += len(other_skills)

        # When the router is expected to defer, record whether the intended handoff
        # target (e.g. find-source) actually picked up the query.
        if not should_trigger and expect_skill:
            expect_hits = sum(1 for s in triggered_skills if s == expect_skill)
            entry["expect_skill"] = expect_skill
            entry["expect_rate"] = round(expect_hits / len(triggered_skills), 3)

        results.append(entry)

    passed = sum(1 for r in results if r["pass"])
    total = len(results)

    # Compute metrics
    tp = sum(1 for r in results if r["should_trigger"] and r["trigger_rate"] >= trigger_threshold)
    fn = sum(1 for r in results if r["should_trigger"] and r["trigger_rate"] < trigger_threshold)
    fp = sum(
        1 for r in results if not r["should_trigger"] and r["trigger_rate"] >= trigger_threshold
    )

    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0

    return {
        "workspace": ws_id,
        "workspace_path": str(workspace),
        "agent": agent,
        "skill_name": skill_name,
        "results": results,
        "summary": {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "clashes": total_clashes,
        },
    }


VALID_AGENTS = ["claude", "cursor", "codex"]


def parse_agents(spec: str) -> list[str]:
    """Parse a --agent spec ('all', 'codex', or 'codex,cursor') into a list.

    Raises ValueError on an unknown agent name.
    """
    agents = VALID_AGENTS[:] if spec == "all" else [a.strip() for a in spec.split(",") if a.strip()]
    bad = [a for a in agents if a not in VALID_AGENTS]
    if bad:
        raise ValueError(
            f"unknown agent(s): {', '.join(bad)} (valid: {', '.join(VALID_AGENTS)} or 'all')"
        )
    return agents


def per_agent_rollup(all_results: list[dict]) -> list[dict]:
    """Aggregate a flat list of per-(agent,workspace) results into per-agent totals."""
    rollup: dict[str, dict] = {}
    for r in all_results:
        a = r["agent"]
        agg = rollup.setdefault(a, {"agent": a, "total": 0, "passed": 0, "clashes": 0})
        agg["total"] += r["summary"]["total"]
        agg["passed"] += r["summary"]["passed"]
        agg["clashes"] += r["summary"]["clashes"]
    return list(rollup.values())


def main():
    parser = argparse.ArgumentParser(description="Run trigger evaluation for a skill")
    parser.add_argument("eval_dir", help="Path to eval directory (e.g. evals/init/dlthub-router)")
    parser.add_argument("--workspace", default=None, help="Run only this workspace (default: all)")
    parser.add_argument(
        "--num-workers", type=int, default=10, help="Parallel workers (default: 10)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Timeout per query in seconds (default: 60)",
    )
    parser.add_argument(
        "--runs-per-query",
        type=int,
        default=1,
        help="Runs per query (default: 1)",
    )
    parser.add_argument(
        "--trigger-threshold",
        type=float,
        default=0.5,
        help="Trigger rate threshold (default: 0.5)",
    )
    parser.add_argument("--model", default=None, help="Model override")
    parser.add_argument(
        "--agent",
        default="claude",
        help=(
            "Agent(s) to drive headlessly: claude|cursor|codex, 'all', or a "
            "comma-separated list (e.g. codex,cursor). One run reports per-agent "
            "results. Default: claude."
        ),
    )
    parser.add_argument("--verbose", action="store_true", help="Print progress to stderr")
    args = parser.parse_args()

    eval_dir = Path(args.eval_dir)
    if not eval_dir.is_absolute():
        eval_dir = ROOT / eval_dir

    skill_name = eval_dir.name
    ws_configs = load_config(eval_dir)

    # Filter to requested workspace
    if args.workspace:
        if args.workspace not in ws_configs:
            print(f"ERROR: Workspace '{args.workspace}' not in config.json", file=sys.stderr)
            print(f"Available: {', '.join(ws_configs.keys())}", file=sys.stderr)
            sys.exit(1)
        ws_configs = {args.workspace: ws_configs[args.workspace]}

    # Load eval set
    eval_path = eval_dir / "trigger-eval.json"
    if not eval_path.exists():
        print(f"ERROR: {eval_path} not found", file=sys.stderr)
        sys.exit(1)
    eval_set_raw = json.loads(eval_path.read_text())
    disabled = [e for e in eval_set_raw if e.get("disabled")]
    eval_set = [e for e in eval_set_raw if not e.get("disabled")]

    if args.verbose and disabled:
        print(f"Skipping {len(disabled)} disabled queries:", file=sys.stderr)
        for e in disabled:
            reason = e.get("reason", "no reason")
            print(f"  - {e['query'][:60]}... ({reason})", file=sys.stderr)

    try:
        agents = parse_agents(args.agent)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    roots = {"claude": ".claude", "cursor": ".cursor", "codex": ".agents"}

    all_results = []
    for agent in agents:
        skills_root = roots[agent]
        for ws_id in ws_configs:
            workspace = find_workspace(eval_dir, ws_id, agent)

            # Verify skill exists in the agent's install layout
            skill_dir = workspace / skills_root / "skills" / skill_name
            if not skill_dir.is_dir():
                print(
                    f"ERROR: Skill '{skill_name}' not in workspace '{ws_id}' "
                    f"(agent={agent}, looked in {skills_root}/skills)",
                    file=sys.stderr,
                )
                sys.exit(1)

            if args.verbose:
                print(
                    f"\n=== Workspace: {ws_id} ({workspace}) [agent={agent}] ===",
                    file=sys.stderr,
                )
                print(f"Skill: {skill_name}", file=sys.stderr)
                print(
                    f"Queries: {len(eval_set)} ({args.runs_per_query} runs each)",
                    file=sys.stderr,
                )

            output = run_eval_on_workspace(
                eval_set=eval_set,
                skill_name=skill_name,
                workspace=workspace,
                ws_id=ws_id,
                num_workers=args.num_workers,
                timeout=args.timeout,
                runs_per_query=args.runs_per_query,
                trigger_threshold=args.trigger_threshold,
                agent=agent,
                model=args.model,
                verbose=args.verbose,
            )

            if args.verbose:
                s = output["summary"]
                print(
                    f"Results: {s['passed']}/{s['total']} passed  "
                    f"precision={s['precision']}  recall={s['recall']}  "
                    f"clashes={s['clashes']}",
                    file=sys.stderr,
                )
                for r in output["results"]:
                    status = "PASS" if r["pass"] else "FAIL"
                    rate_str = f"{r['triggers']}/{r['runs']}"
                    clash_str = f" CLASH→{r['clashes']}" if r.get("clashes") else ""
                    print(
                        f"  [{status}] rate={rate_str} expected={r['should_trigger']}{clash_str}: "
                        f"{r['query'][:80]}",
                        file=sys.stderr,
                    )

            all_results.append(output)

    # Per-agent rollup when more than one agent ran in this invocation.
    if args.verbose and len(agents) > 1:
        print("\n=== Per-agent summary ===", file=sys.stderr)
        for agg in per_agent_rollup(all_results):
            print(
                f"  {agg['agent']:7} {agg['passed']}/{agg['total']} passed  "
                f"clashes={agg['clashes']}",
                file=sys.stderr,
            )

    print(json.dumps(all_results if len(all_results) > 1 else all_results[0], indent=2))


if __name__ == "__main__":
    main()
