import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from utils import observability


class _FakeRuntimeStore:
    def __init__(self):
        self.documents = {}
        self.events = []

    async def merge_document(self, key, payload):
        current = dict(self.documents.get(key) or {})
        current.update(dict(payload or {}))
        self.documents[key] = current

    async def write_document(self, key, payload):
        self.documents[key] = dict(payload or {})

    async def load_document(self, key):
        return dict(self.documents.get(key) or {})

    async def load_documents(self, prefix):
        return {
            key: dict(value)
            for key, value in self.documents.items()
            if key.startswith(prefix)
        }

    async def append_event(self, event_type, status, payload=None):
        self.events.append(
            {
                "event_type": event_type,
                "status": status,
                **dict(payload or {}),
            }
        )

    async def load_recent_events(self, limit=20):
        return list(self.events[-limit:])


class ObservabilityTest(unittest.IsolatedAsyncioTestCase):
    async def test_update_job_status_preserves_existing_ops_fields(self):
        fake_store = _FakeRuntimeStore()
        original_store = observability.runtime_store._store
        observability.runtime_store._store = fake_store
        try:
            await observability.update_ops_status(status="running", scheduler="running")
            await observability.update_job_status("lesson_reminder", "ok", sent=2, checked=3)

            payload = await observability.load_ops_status()
            self.assertEqual(payload["status"], "running")
            self.assertEqual(payload["scheduler"], "running")
            self.assertEqual(payload["jobs"]["lesson_reminder"]["status"], "ok")
            self.assertEqual(payload["jobs"]["lesson_reminder"]["sent"], 2)
            self.assertEqual(payload["jobs"]["lesson_reminder"]["checked"], 3)
        finally:
            observability.runtime_store._store = original_store


if __name__ == "__main__":
    unittest.main()
