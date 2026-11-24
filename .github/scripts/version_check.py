"""Fail if a toolkit changed vs BASE without a version bump in plugin.json and marketplace.json.

Usage: version_check.py BASE_REF   (compares BASE_REF...HEAD, i.e. against the merge base)
"""
import json, re, subprocess, sys

def git(*a):
    return subprocess.run(["git", *a], check=True, capture_output=True, text=True).stdout

def show(ref, path):
    r = subprocess.run(["git", "show", f"{ref}:{path}"], capture_output=True, text=True)
    return json.loads(r.stdout) if r.returncode == 0 else None

def semver(v):
    # shortcut: ignores pre-release tags (1.0.0-rc1 compares as 1.0.0), fine until we ship pre-releases
    m = re.match(r"(\d+)\.(\d+)\.(\d+)", v or "")
    return tuple(map(int, m.groups())) if m else None

def mkt_version(mkt, toolkit):
    """Return the version of the marketplace entry whose name is the toolkit."""
    return next((p.get("version") for p in (mkt or {}).get("plugins", []) if p.get("name") == toolkit), None)

def main(base):
    changed = git("diff", "--name-only", f"{base}...HEAD").splitlines()
    toolkits = sorted({p.split("/")[1] for p in changed if p.startswith("workbench/") and p.count("/") >= 2})
    base_mkt, head_mkt = show(base, ".claude-plugin/marketplace.json"), show("HEAD", ".claude-plugin/marketplace.json")
    errors = []
    for t in toolkits:
        pj = f"workbench/{t}/.claude-plugin/plugin.json"
        old_p, new_p = show(base, pj), show("HEAD", pj)
        head_mkt_version = mkt_version(head_mkt, t)
        if new_p is not None and new_p.get("version") != head_mkt_version:
            errors.append(f"Toolkit '{t}': version in {pj} is {new_p.get('version')} but marketplace.json "
                          f"has {head_mkt_version}. Make them equal.")
        if old_p is None or new_p is None:
            continue  # toolkit added or removed in this PR: nothing to compare
        for label, old, new in [
            (pj, old_p.get("version"), new_p.get("version")),
            (f".claude-plugin/marketplace.json (entry '{t}')", mkt_version(base_mkt, t), head_mkt_version),
        ]:
            if old is None:
                continue  # entry did not exist on base
            if semver(old) is None:
                errors.append(f"Toolkit '{t}': base version in {label} is '{old}', not X.Y.Z. Fix it on base.")
            elif semver(new) is None or semver(new) <= semver(old):
                errors.append(f"Toolkit '{t}' changed but version in {label} is {new} (base: {old}). Bump it, "
                              "otherwise Claude Code will not update users.")
    for e in errors:
        print(f"::error::{e}")
    print(f"checked toolkits: {toolkits or 'none'}")
    return 1 if errors else 0

if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
