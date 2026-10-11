#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

for tool in bandit pip-audit npm detect-secrets python; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    printf 'Required audit tool not found: %s\n' "$tool" >&2
    exit 2
  fi
done

printf '\n== Bandit: Python AST security analysis ==\n'
bandit -r agentdrift app -ll -ii

printf '\n== pip-audit: Python dependency vulnerabilities ==\n'
pip-audit -r requirements.txt

printf '\n== npm audit: frontend dependency vulnerabilities ==\n'
npm audit --prefix web --audit-level=high

printf '\n== detect-secrets: repository secret scan ==\n'
scan_output="$(mktemp)"
trap 'rm -f "$scan_output"' EXIT
# Include tracked and untracked repository files, while excluding local runtime
# credentials and generated dependency/virtual-environment trees.
detect-secrets scan --all-files \
  --exclude-files '(^|/)(\.env$|\.git/|\.venv/|node_modules/|\.pytest_cache/|\.ruff_cache/)' \
  > "$scan_output"
python - "$scan_output" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as scan_file:
    report = json.load(scan_file)

results = report.get("results", {})
findings = [
    (path, item)
    for path, items in results.items()
    for item in items
]
if findings:
    print(f"detect-secrets found {len(findings)} potential secret(s):", file=sys.stderr)
    for path, item in findings:
        print(f"  {path}:{item.get('line_number', '?')} ({item.get('type', 'unknown')})", file=sys.stderr)
    print("Review each finding and remove credentials; do not commit a baseline that hides real secrets.", file=sys.stderr)
    raise SystemExit(1)

print("No potential secrets found.")
PY

printf '\nSecurity audit passed.\n'
