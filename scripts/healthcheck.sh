#!/usr/bin/env bash
set -euo pipefail

ROOT="${TUTORBOT_ROOT:-/srv/tutorscalebot}"
SERVICE_NAME="${TUTORBOT_SERVICE_NAME:-tutorscalebot}"
SYSTEMD_SCOPE="${TUTORBOT_SYSTEMD_SCOPE:-system}"
BOT_CMD="$ROOT/.venv/bin/python $ROOT/app.py"
OPS_STATUS="$ROOT/data/ops_status.json"
RUNTIME_METRICS="$ROOT/data/runtime_metrics.jsonl"

if [ "$SYSTEMD_SCOPE" = "user" ]; then
  SYSTEMCTL=(systemctl --user)
else
  SYSTEMCTL=(systemctl)
fi

if command -v systemctl >/dev/null 2>&1 && "${SYSTEMCTL[@]}" is-active --quiet "$SERVICE_NAME"; then
  :
elif pgrep -af "$BOT_CMD" >/dev/null 2>&1; then
  :
else
  echo "bot process not running"
  exit 1
fi

if [ ! -f "$OPS_STATUS" ]; then
  echo "ops status file missing"
  exit 1
fi

python3 - "$OPS_STATUS" <<'PY'
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ops_path = Path(sys.argv[1])
data = json.loads(ops_path.read_text(encoding="utf-8"))
status = str(data.get("status", "unknown"))
if status not in {"running", "starting"}:
    print(f"ops status is {status}")
    raise SystemExit(1)

updated_at = data.get("updated_at")
if updated_at:
    stamp = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    if datetime.now(timezone.utc) - stamp > timedelta(minutes=20):
        print("ops status is stale")
        raise SystemExit(1)
PY

if [ -f "$RUNTIME_METRICS" ] && [ ! -s "$RUNTIME_METRICS" ]; then
  echo "runtime metrics file is empty"
  exit 1
fi

echo "ok"
