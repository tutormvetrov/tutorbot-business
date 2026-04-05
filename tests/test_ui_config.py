import json
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from utils.db_api.business import DatabaseBusinessMixin


def _menu_item(item_id: str, label: str, value: str, order: int, *, kind: str = "callback", enabled: bool = True) -> dict:
    return {
        "id": item_id,
        "label": label,
        "value": value,
        "kind": kind,
        "enabled": enabled,
        "order": order,
    }


def _seed_defaults() -> dict:
    return {
        "branding": {
            "display_name": "TutorScalebot",
            "tone": "warm",
        },
        "contacts": {
            "phone": "+7 900 000-00-00",
            "telegram": "@TutorScalebot",
            "discord": "",
            "address": "ул. Пример, 1",
            "booking_url": "https://example.com/book",
            "calendar_url": "",
            "project_site_url": "https://example.com",
            "level_test_url": "",
            "review_url": "",
            "vk_call": "",
            "google_meet": "",
        },
        "requisites": {
            "rates": ["0 рублей / 60 минут", "0 рублей / 90 минут"],
            "card": "1234 5678 9000 1111",
            "sbp": "+7 900 000-00-00",
            "sbp_banks": "Т-Банк",
            "usdt_trc20": "",
        },
        "copy": {
            "start_intro": "Добро пожаловать в TutorScalebot!",
            "help_intro": "Короткая справка по TutorScalebot.",
            "contacts_intro": "Здесь собраны основные способы связи и подключения к занятию.",
            "requisites_footer": "Если уже отправили оплату, можно сразу нажать кнопку «Сообщить об оплате».",
            "post_registration_intro": "Регистрация завершена. Ниже — полезные ссылки и следующий шаг.",
        },
        "menu": {
            "client_main": [
                _menu_item("schedule", "📅 Расписание", "schedule", 1),
                _menu_item("homework", "📚 Домашние задания", "homework", 2),
                _menu_item("freeze", "❄️ Заморозка", "freeze", 3),
                _menu_item("payment", "💰 Оплата", "payment", 4),
                _menu_item("profile", "👤 Профиль", "profile", 5),
                _menu_item("contacts", "📞 Контакты", "contacts", 6),
                _menu_item("requisites", "💳 Реквизиты", "requisites", 7),
            ],
            "parent_main": [
                _menu_item("children", "👨‍👧 Дети", "parent:children", 1),
                _menu_item("payment", "💰 Оплата", "payment", 2),
                _menu_item("profile", "👤 Профиль", "profile", 3),
                _menu_item("contacts", "📞 Контакты", "contacts", 4),
                _menu_item("requisites", "💳 Реквизиты", "requisites", 5),
            ],
            "owner_main": [
                _menu_item("setup", "🚦 Быстрый запуск", "admin:setup", 1),
                _menu_item("admin", "🛠 Панель", "admin:home", 2),
                _menu_item("workspace", "🏢 Аккаунт", "workspace:selector", 3),
                _menu_item("product", "💼 Продукт", "product:hub", 4),
                _menu_item("team", "👥 Команда", "product:team", 5),
                _menu_item("profile", "👤 Профиль", "profile", 6),
            ],
            "manager_main": [
                _menu_item("admin", "🛠 Панель", "admin:home", 1),
                _menu_item("workspace", "🏢 Аккаунт", "workspace:selector", 2),
                _menu_item("product", "💼 Продукт", "product:hub", 3),
                _menu_item("team", "👥 Команда", "product:team", 4),
                _menu_item("profile", "👤 Профиль", "profile", 5),
            ],
            "assistant_main": [
                _menu_item("workspace", "🏢 Аккаунт", "workspace:selector", 1),
                _menu_item("product", "💼 Продукт", "product:hub", 2),
                _menu_item("team", "👥 Команда", "product:team", 3),
                _menu_item("profile", "👤 Профиль", "profile", 4),
            ],
            "admin_account": [
                _menu_item("analytics", "📈 Аналитика", "admin:analytics", 1),
                _menu_item("billing", "🧾 Тариф", "admin:billing", 2),
                _menu_item("team", "👥 Команда", "admin:team", 3),
                _menu_item("invites", "🔗 Инвайты", "admin:invites", 4),
                _menu_item("support", "🆘 Диагностика", "admin:support", 5),
                _menu_item("workspace", "🏢 Аккаунт", "workspace:selector", 6),
            ],
            "admin_system": [
                _menu_item("setup", "🚦 Быстрый запуск", "admin:setup", 1),
                _menu_item("sync", "🔄 Синхронизация", "admin:sync:system", 2),
                _menu_item("aliases", "🧭 Алиасы Calendar", "admin:calendar_aliases", 3),
                _menu_item("report", "📋 Отчёт синхронизации", "admin:calendar_report", 4),
                _menu_item("health", "🏥 Здоровье бота", "admin:health", 5),
                _menu_item("tone", "🎨 Оформление и экраны", "admin:ui", 6),
                _menu_item("notes", "📝 Заметки", "admin:notes", 7),
            ],
            "admin_service": [
                _menu_item("setup", "🚦 Быстрый запуск", "admin:setup", 1),
                _menu_item("sync", "🔄 Синхронизация Calendar", "admin:sync:service", 2),
                _menu_item("aliases", "🧭 Алиасы Calendar", "admin:calendar_aliases", 3),
                _menu_item("report", "📋 Отчёт синхронизации", "admin:calendar_report", 4),
                _menu_item("plans", "💳 Тарифы", "product:plans", 5),
                _menu_item("subscription", "🪪 Подписка", "product:subscription", 6),
                _menu_item("analytics", "📈 Аналитика", "admin:analytics", 7),
                _menu_item("billing", "🧾 Тариф", "admin:billing", 8),
                _menu_item("team", "👥 Команда", "admin:team", 9),
                _menu_item("invites", "🔗 Инвайты", "admin:invites", 10),
                _menu_item("support", "🆘 Диагностика", "admin:support", 11),
                _menu_item("workspace", "🏢 Аккаунт", "workspace:selector", 12),
                _menu_item("health", "🏥 Здоровье бота", "admin:health", 13),
                _menu_item("tone", "🎨 Оформление и экраны", "admin:ui", 14),
                _menu_item("notes", "📝 Заметки", "admin:notes", 15),
            ],
        },
    }


class _FakeTxn:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeConn:
    def __init__(self, state):
        self.state = state

    def transaction(self):
        return _FakeTxn()

    async def fetchrow(self, query, *args):
        return await self.state.fetchrow(query, *args)

    async def execute(self, query, *args):
        return await self.state.execute(query, *args)


class _FakeAcquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakePool:
    def __init__(self, state):
        self.state = state

    def acquire(self):
        return _FakeAcquire(_FakeConn(self.state))


class _UIConfigFakeDB(DatabaseBusinessMixin):
    def __init__(self, defaults: dict | None = None):
        self.defaults = deepcopy(defaults or _seed_defaults())
        self.pool = _FakePool(self)
        self.account = {"id": 1, "name": "Demo Workspace", "slug": "demo-workspace", "status": "active"}
        self.configs: dict[int, dict] = {}
        self.versions: list[dict] = []
        self._config_id = 0
        self._version_id = 0

    async def execute(self, query, *args, fetch: bool = False, fetchval: bool = False, fetchrow: bool = False, execute: bool = False):
        query = " ".join(str(query).split())
        if "SELECT * FROM account_ui_configs" in query:
            return self.configs.get(args[0])
        if "SELECT * FROM account_ui_versions" in query and "ORDER BY version DESC, id DESC" in query:
            account_id = args[0]
            rows = [deepcopy(row) for row in self.versions if row["account_id"] == account_id]
            return sorted(rows, key=lambda row: (row["version"], row["id"]), reverse=True)
        if "SELECT * FROM account_ui_versions" in query and "AND version = $2" in query:
            account_id, version = args
            for row in self.versions:
                if row["account_id"] == account_id and row["version"] == version:
                    return deepcopy(row)
            return None
        if "INSERT INTO account_ui_configs" in query:
            if len(args) == 2:
                account_id, payload_json = args
                payload = self._loads(payload_json)
                current = self.configs.get(account_id)
                if current is None:
                    self.configs[account_id] = self._make_config_row(account_id, payload, payload, 1, 1, None, None)
                else:
                    if not current.get("draft_payload"):
                        current["draft_payload"] = deepcopy(payload)
                    if not current.get("published_payload"):
                        current["published_payload"] = deepcopy(payload)
                    current.setdefault("draft_version", 1)
                    current.setdefault("published_version", 1)
                    current["updated_at"] = datetime(2026, 4, 3, 12, 0)
                return "OK"
            account_id, draft_json, published_json, draft_version, published_version, updated_by = args
            row = self.configs.get(account_id) or self._make_config_row(account_id, {}, {}, 1, 1, None, None)
            row.update(
                draft_payload=self._loads(draft_json),
                published_payload=self._loads(published_json),
                draft_version=int(draft_version),
                published_version=int(published_version),
                updated_by=updated_by,
                updated_at=datetime(2026, 4, 3, 12, 0),
                published_at=row.get("published_at") or datetime(2026, 4, 3, 12, 0),
            )
            self.configs[account_id] = row
            return "OK"
        if "INSERT INTO account_ui_versions" in query:
            if len(args) == 2:
                account_id, payload_json = args
                self._insert_version(account_id, 1, self._loads(payload_json), None)
            else:
                account_id, version, payload_json, published_by = args
                self._insert_version(account_id, int(version), self._loads(payload_json), published_by)
            return "OK"
        if "UPDATE account_ui_configs" in query:
            account_id, payload_json, version, actor_id = args
            row = self.configs.get(account_id)
            if row is None:
                raise AssertionError("config row missing")
            payload = self._loads(payload_json)
            row.update(
                draft_payload=deepcopy(payload),
                published_payload=deepcopy(payload),
                draft_version=max(int(row.get("draft_version") or 1), int(version)),
                published_version=int(version),
                updated_by=actor_id if actor_id is not None else row.get("updated_by"),
                published_by=actor_id,
                published_at=datetime(2026, 4, 3, 12, 0),
                updated_at=datetime(2026, 4, 3, 12, 0),
            )
            self.configs[account_id] = row
            return "OK"
        return None

    async def fetchrow(self, query, *args):
        return await self.execute(query, *args, fetchrow=True)

    async def get_account_by_id(self, account_id: int):
        return deepcopy(self.account) if account_id == self.account["id"] else None

    def _loads(self, payload):
        if payload is None:
            return {}
        if isinstance(payload, str):
            return json.loads(payload)
        return deepcopy(payload)

    def _make_config_row(self, account_id: int, draft_payload: dict, published_payload: dict, draft_version: int, published_version: int, updated_by, published_by):
        self._config_id += 1
        now = datetime(2026, 4, 3, 12, 0)
        return {
            "id": self._config_id,
            "account_id": account_id,
            "draft_payload": deepcopy(draft_payload),
            "published_payload": deepcopy(published_payload),
            "draft_version": draft_version,
            "published_version": published_version,
            "updated_by": updated_by,
            "published_by": published_by,
            "updated_at": now,
            "published_at": now,
            "created_at": now,
        }

    def _insert_version(self, account_id: int, version: int, payload: dict, published_by):
        if any(row["account_id"] == account_id and row["version"] == version for row in self.versions):
            return
        self._version_id += 1
        now = datetime(2026, 4, 3, 12, 0)
        self.versions.append(
            {
                "id": self._version_id,
                "account_id": account_id,
                "version": version,
                "payload": deepcopy(payload),
                "published_by": published_by,
                "published_at": now,
                "created_at": now,
            }
        )


class UIConfigLifecycleTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.defaults = _seed_defaults()
        patcher = patch("utils.db_api.business.load_ui_seed_defaults", side_effect=lambda: deepcopy(self.defaults))
        self.addCleanup(patcher.stop)
        patcher.start()
        self.db = _UIConfigFakeDB(self.defaults)

    async def test_resolved_defaults_fallback_uses_seed_when_config_missing(self):
        snapshot = await self.db.get_resolved_ui_config(1)

        self.assertEqual(snapshot["source"], "defaults")
        self.assertEqual(snapshot["account"]["name"], "Demo Workspace")
        self.assertEqual(snapshot["resolved"]["branding"]["display_name"], "TutorScalebot")
        self.assertEqual(snapshot["resolved"]["copy"]["start_intro"], "Добро пожаловать в TutorScalebot!")

    async def test_save_publish_and_rollback_lifecycle_with_safe_menu_validation(self):
        draft = await self.db.save_ui_draft(
            1,
            {
                "branding": {
                    "display_name": "TutorScalebot Studio",
                    "tone": "calm",
                },
                "contacts": {
                    "telegram": "@TutorScalebotStudio",
                    "booking_url": "https://example.com/book-now",
                },
                "copy": {
                    "start_intro": "Добро пожаловать в TutorScalebot Studio!",
                },
                "menu": {
                    "client_main": [
                        _menu_item("schedule", "Расписание", "schedule", 1),
                        _menu_item("site", "Сайт", "https://example.com", 2, kind="url"),
                        _menu_item("chat", "Telegram", "https://t.me/TutorScalebot", 3, kind="telegram_url"),
                    ]
                },
            },
            updated_by=9001,
        )

        self.assertEqual(draft["draft_version"], 2)
        self.assertEqual(draft["published_version"], 1)
        self.assertEqual(draft["draft"]["branding"]["display_name"], "TutorScalebot Studio")
        self.assertEqual(draft["draft"]["menu"]["client_main"][1]["kind"], "url")
        self.assertEqual(draft["draft"]["menu"]["client_main"][2]["kind"], "telegram_url")
        self.assertEqual(draft["updated_by"], 9001)

        published = await self.db.publish_ui_draft(1, published_by=9001)
        self.assertEqual(published["published_version"], 2)
        self.assertEqual(published["resolved"]["branding"]["display_name"], "TutorScalebot Studio")
        self.assertEqual(published["resolved"]["copy"]["start_intro"], "Добро пожаловать в TutorScalebot Studio!")

        versions = await self.db.list_ui_versions(1)
        self.assertEqual([row["version"] for row in versions], [2, 1])
        self.assertEqual(versions[0]["payload"]["branding"]["display_name"], "TutorScalebot Studio")

        rolled_back = await self.db.rollback_ui_version(1, 1, actor_id=9001)
        self.assertEqual(rolled_back["published_version"], 3)
        self.assertEqual(rolled_back["resolved"]["branding"]["display_name"], "TutorScalebot")
        self.assertEqual(rolled_back["resolved"]["copy"]["start_intro"], "Добро пожаловать в TutorScalebot!")

        versions = await self.db.list_ui_versions(1)
        self.assertEqual([row["version"] for row in versions], [3, 2, 1])

    async def test_unsafe_callback_menu_payload_is_rejected(self):
        with self.assertRaises(ValueError):
            await self.db.save_ui_draft(
                1,
                {
                    "menu": {
                        "client_main": [
                            _menu_item("danger", "Удалить все", "admin:drop_everything", 1),
                        ]
                    }
                },
                updated_by=1,
            )


if __name__ == "__main__":
    unittest.main()
