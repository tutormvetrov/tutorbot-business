from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(os.getenv("TUTORBOT_ROOT", Path(__file__).resolve().parents[1])).resolve()
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


def _service_name() -> str:
    return os.getenv("TUTORBOT_SERVICE_NAME", "tutorscalebot").strip() or "tutorscalebot"


def _systemd_scope() -> str:
    return os.getenv("TUTORBOT_SYSTEMD_SCOPE", "system").strip().lower() or "system"


def _restart_mode() -> str:
    configured = os.getenv("TUTORBOT_RESTART_MODE", "").strip().lower()
    if configured:
        return configured
    return "trigger-file" if _systemd_scope() == "system" else "systemctl"


def _restart_command() -> list[str]:
    service_name = _service_name()
    if _systemd_scope() == "user":
        return ["systemctl", "--user", "restart", service_name]
    return ["systemctl", "restart", service_name]


def _reload_trigger_path() -> Path:
    raw = os.getenv("TUTORBOT_RELOAD_TRIGGER", "").strip()
    return Path(raw).expanduser().resolve() if raw else (ROOT / ".restart-trigger")


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


def _restart_bot() -> tuple[bool, str]:
    if _restart_mode() == "trigger-file":
        trigger_path = _reload_trigger_path()
        trigger_path.parent.mkdir(parents=True, exist_ok=True)
        trigger_path.write_text(str(time.time_ns()), encoding="utf-8")
        return True, f"restart requested via {trigger_path}"

    result = subprocess.run(_restart_command(), check=False)
    if result.returncode == 0:
        return True, f"{_service_name()} restarted successfully"
    return False, f"failed to restart {_service_name()}"

def main() -> int:
    previous = _build_snapshot()
    print(
        f"tutorscalebot-watch: monitoring project files for changes in {ROOT} "
        f"(restart mode: {_restart_mode()})",
        flush=True,
    )

    while True:
        time.sleep(POLL_INTERVAL_SECONDS)
        current = _build_snapshot()
        if current == previous:
            continue

        time.sleep(SETTLE_SECONDS)
        settled = _build_snapshot()
        change_summary = _summarize_changes(previous, settled)
        print(f"tutorscalebot-watch: restarting service after changes in {change_summary}", flush=True)

        restarted, detail = _restart_bot()
        if restarted:
            previous = settled
            print(f"tutorscalebot-watch: {detail}", flush=True)
            continue

        print(f"tutorscalebot-watch: {detail}", file=sys.stderr, flush=True)
        previous = settled


if __name__ == "__main__":
    raise SystemExit(main())
