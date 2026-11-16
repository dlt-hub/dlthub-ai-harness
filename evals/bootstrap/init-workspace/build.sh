#!/usr/bin/env bash
# Build the eval workspaces by hand, since create_eval_workspace.py always runs dlthub ai init.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../../.." && pwd)"
skill="$root/workbench/bootstrap/skills/init-workspace"
out="$root/evals/.evals"
rm -rf "$out/bootstrap--init-workspace--bare" "$out/bootstrap--init-workspace--data-project"
mkdir -p "$out/bootstrap--init-workspace--bare/.claude/skills"
cp -R "$skill" "$out/bootstrap--init-workspace--bare/.claude/skills/"
cp -R "$here/fixtures/data-project" "$out/bootstrap--init-workspace--data-project"
cp -R "$skill" "$out/bootstrap--init-workspace--data-project/.claude/skills/"
echo "built bare and data-project in $out"

# Workspaces where dltHub is already set up, plus the bootstrap skill from the marketplace.
for spec in "with-init:" "with-rest-api:rest-api-pipeline"; do
  ws="$out/bootstrap--init-workspace--${spec%%:*}"
  (cd "$root" && uv run python -c "
import sys; sys.path.insert(0, 'tools')
from pathlib import Path
from create_eval_workspace import create_single_workspace, get_dlt_version
tk = [t for t in sys.argv[2].split(',') if t]
create_single_workspace(Path(sys.argv[1]), f'dlt[hub]=={get_dlt_version()}', tk)
" "$ws" "${spec#*:}") > /dev/null
  cp -R "$skill" "$ws/.claude/skills/"
  echo "built ${spec%%:*}: $(ls "$ws/.claude/skills" | tr '\n' ' ')"
done
