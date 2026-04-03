from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(os.getenv("TUTORBOT_ROOT", Path(__file__).resolve().parents[1])).resolve()
SERVICE_NAME = os.getenv("TUTORBOT_SERVICE_NAME", "tutorscalebot")
WATCH_TARGETS = [
    ROOT / "app.py",
    ROOT / "loader.py",
    ROOT / ".env",
    ROOT / "data" / "config.py",
    ROOT / "handlers",
    ROOT / "keyboards",
    ROOT / "states",
    ROOT / "utils",
]
IGNORED_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}
ALLOWED_SUFFIXES = {".py", ".env", ".toml", ".ini", ".yaml", ".yml", ".json"}
EXACT_FILENAMES = {".env"}
POLL_INTERVAL_SECONDS = 1.0
SETTLE_SECONDS = 0.75
RESTART_COMMAND = ["systemctl", "--user", "restart", SERVICE_NAME]


def _should_watch(path: Path) -> bool:
    try:
        relative = path.relative_to(ROOT)
    except ValueError:
        return False

    if any(part in IGNORED_DIRS for part in relative.parts):
        return False

    return path.name in EXACT_FILENAMES or path.suffix in ALLOWED_SUFFIXES


def _iter_watched_files(target: Path):
    if not target.exists():
        return

    if target.is_file():
        if _should_watch(target):
            yield target
        return

    for dirpath, dirnames, filenames in os.walk(target):
        dirnames[:] = [name for name in dirnames if name not in IGNORED_DIRS]
        for filename in filenames:
            candidate = Path(dirpath) / filename
            if _should_watch(candidate):
                yield candidate


def _build_snapshot() -> dict[str, tuple[int, int]]:
    snapshot: dict[str, tuple[int, int]] = {}
    for target in WATCH_TARGETS:
        for path in _iter_watched_files(target):
            try:
                stat = path.stat()
            except FileNotFoundError:
                continue
            snapshot[str(path)] = (stat.st_mtime_ns, stat.st_size)
    return snapshot


def _summarize_changes(previous: dict[str, tuple[int, int]], current: dict[str, tuple[int, int]]) -> str:
    added = sorted(set(current) - set(previous))
    removed = sorted(set(previous) - set(current))
    changed = sorted(
        path
        for path in set(previous) & set(current)
        if previous[path] != current[path]
    )
    interesting = added + removed + changed
    if not interesting:
        return "changes detected"
    labels = [str(Path(path).relative_to(ROOT)) for path in interesting[:5]]
    suffix = "..." if len(interesting) > 5 else ""
    return ", ".join(labels) + suffix


def _restart_bot() -> bool:
    result = subprocess.run(RESTART_COMMAND, check=False)
    return result.returncode == 0

def main() -> int:
    previous = _build_snapshot()
    print(f"tutorscalebot-watch: monitoring project files for changes in {ROOT}", flush=True)

    while True:
        time.sleep(POLL_INTERVAL_SECONDS)
        current = _build_snapshot()
        if current == previous:
            continue

        time.sleep(SETTLE_SECONDS)
        settled = _build_snapshot()
        change_summary = _summarize_changes(previous, settled)
        print(f"tutorscalebot-watch: restarting service after changes in {change_summary}", flush=True)

        if _restart_bot():
            previous = settled
            print(f"tutorscalebot-watch: {SERVICE_NAME} restarted successfully", flush=True)
            continue

        print(f"tutorscalebot-watch: failed to restart {SERVICE_NAME}", file=sys.stderr, flush=True)
        previous = settled


if __name__ == "__main__":
    raise SystemExit(main())
