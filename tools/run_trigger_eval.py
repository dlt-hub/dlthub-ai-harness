#!/usr/bin/env python3
"""Run trigger evaluation for a skill across eval workspaces.

Tests whether a skill triggers correctly for a set of queries, and detects
when a competing skill triggers instead (clash). Runs `claude -p` from eval
workspaces where real skills are installed.

Runs against all workspaces defined in config.json.

Output format is compatible with skill-creator's run_eval.py (extended with
`triggered_skill` and `clashes` fields).

Usage:
    python tools/run_trigger_eval.py evals/init/toolkit-dispatch
    python tools/run_trigger_eval.py evals/init/toolkit-dispatch --workspace init-only
    python tools/run_trigger_eval.py evals/init/toolkit-dispatch --runs-per-query 3
"""

import argparse
import json
import os
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


def find_workspace(eval_dir: Path, ws_id: str) -> Path:
    """Find workspace path for a given workspace ID."""
    rel = eval_dir.relative_to(ROOT / "evals")
    name = str(rel).replace("/", "--").replace("\\", "--") + "--" + ws_id
    ws = EVALS_DIR / name
    if not ws.is_dir():
        print(f"ERROR: Workspace not found: {ws}", file=sys.stderr)
        print(
            f"Run: uv run python tools/create_eval_workspace.py {eval_dir.relative_to(ROOT)}",
            file=sys.stderr,
        )
        sys.exit(1)
    return ws


def run_single_query(
    query: str,
    workspace: str,
    timeout: int,
    model: str | None = None,
) -> str | None:
    """Run a query via claude -p. Return the skill name that triggered, or None."""
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
        import re

        m = re.search(r'"skill"\s*:\s*"([^"]+)"', json_fragment)
        return m.group(1) if m else None


def run_eval_on_workspace(
    eval_set: list[dict],
    skill_name: str,
    workspace: Path,
    ws_id: str,
    num_workers: int,
    timeout: int,
    runs_per_query: int,
    trigger_threshold: float,
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
        should_trigger = item["should_trigger"]

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


def main():
    parser = argparse.ArgumentParser(description="Run trigger evaluation for a skill")
    parser.add_argument(
        "eval_dir", help="Path to eval directory (e.g. evals/init/toolkit-dispatch)"
    )
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

    all_results = []
    for ws_id in ws_configs:
        workspace = find_workspace(eval_dir, ws_id)

        # Verify skill exists
        skill_dir = workspace / ".claude" / "skills" / skill_name
        if not skill_dir.is_dir():
            print(f"ERROR: Skill '{skill_name}' not in workspace '{ws_id}'", file=sys.stderr)
            sys.exit(1)

        if args.verbose:
            print(f"\n=== Workspace: {ws_id} ({workspace}) ===", file=sys.stderr)
            print(f"Skill: {skill_name}", file=sys.stderr)
            print(f"Queries: {len(eval_set)} ({args.runs_per_query} runs each)", file=sys.stderr)

        output = run_eval_on_workspace(
            eval_set=eval_set,
            skill_name=skill_name,
            workspace=workspace,
            ws_id=ws_id,
            num_workers=args.num_workers,
            timeout=args.timeout,
            runs_per_query=args.runs_per_query,
            trigger_threshold=args.trigger_threshold,
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

    print(json.dumps(all_results if len(all_results) > 1 else all_results[0], indent=2))


if __name__ == "__main__":
    main()
