import importlib.util
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
WATCH_SCRIPT = ROOT / "scripts" / "tutorbot_watch.py"


def _load_watch_module():
    spec = importlib.util.spec_from_file_location("tutorscalebot_watch", WATCH_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("tutorscalebot_watch", module)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


watch = _load_watch_module()


class WatchRestartTest(unittest.TestCase):
    def test_system_scope_uses_trigger_file_restart(self):
        with TemporaryDirectory() as tmpdir:
            trigger_path = Path(tmpdir) / ".restart-trigger"
            with patch.dict(
                "os.environ",
                {
                    "TUTORBOT_SYSTEMD_SCOPE": "system",
                    "TUTORBOT_RESTART_MODE": "trigger-file",
                    "TUTORBOT_RELOAD_TRIGGER": str(trigger_path),
                    "TUTORBOT_SERVICE_NAME": "tutorscalebot",
                },
                clear=False,
            ):
                restarted, detail = watch._restart_bot()
                self.assertTrue(restarted)
                self.assertIn(str(trigger_path), detail)
                self.assertTrue(trigger_path.exists())
                self.assertTrue(trigger_path.read_text(encoding="utf-8").strip())

    def test_user_scope_uses_user_systemctl_restart(self):
        with patch.object(watch.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run_mock:
            with patch.dict(
                "os.environ",
                {
                    "TUTORBOT_SYSTEMD_SCOPE": "user",
                    "TUTORBOT_RESTART_MODE": "systemctl",
                    "TUTORBOT_SERVICE_NAME": "tutorscalebot",
                },
                clear=False,
            ):
                restarted, detail = watch._restart_bot()

        self.assertTrue(restarted)
        self.assertIn("restarted successfully", detail)
        run_mock.assert_called_once_with(
            ["systemctl", "--user", "restart", "tutorscalebot"],
            check=False,
        )
