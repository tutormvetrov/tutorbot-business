#!/usr/bin/env bash
set -euo pipefail

ROOT="${TUTORBOT_ROOT:-/srv/tutorscalebot}"
SERVICE_NAME="${TUTORBOT_SERVICE_NAME:-tutorscalebot}"
SYSTEMD_SCOPE="${TUTORBOT_SYSTEMD_SCOPE:-system}"
BOT_CMD="$ROOT/.venv/bin/python $ROOT/app.py"

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

PYTHON_BIN="${TUTORBOT_PYTHON_BIN:-$ROOT/.venv/bin/python}"

PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" <<'PY'
import asyncio
from datetime import datetime, timedelta, timezone

from utils.observability import load_ops_status

async def main():
    data = await load_ops_status()
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

asyncio.run(main())
PY

echo "ok"
