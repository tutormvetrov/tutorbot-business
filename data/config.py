import json
import os
from pathlib import Path
from dotenv import load_dotenv

from utils.brand import DEFAULT_BRAND_TONE, load_brand_settings

load_dotenv()

INTERNAL_TEST_ACCOUNT_RULES = [
    {
        "telegram_ids": {389264815},
        "usernames": {"eliza_znkv"},
        "surname": "занкевич",
        "names": {"лиза", "елизавета", "eliza"},
    },
]

BOT_TOKEN = str(os.getenv("BOT_TOKEN"))
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))

PGUSER = str(os.getenv("PGUSER"))
PGPASSWORD = str(os.getenv("PGPASSWORD"))
DATABASE = str(os.getenv("DATABASE"))
PGHOST = str(os.getenv("PGHOST"))
PGPORT = str(os.getenv("PGPORT"))
PGSCHEMA = (os.getenv("PGSCHEMA", "tutorscalebot") or "tutorscalebot").strip() or "tutorscalebot"

POSTGRES_URI = f"postgresql://{PGUSER}:{PGPASSWORD}@{PGHOST}:{PGPORT}/{DATABASE}"

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.getenv("TUTORBOT_DATA_DIR", PROJECT_ROOT / "data"))
FSM_STORAGE_FILE = Path(os.getenv("FSM_STORAGE_FILE", DATA_DIR / "fsm_storage.json"))
SERVICE_NAME = os.getenv("TUTORBOT_SERVICE_NAME", "tutorscalebot")

GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "")
GOOGLE_CREDENTIALS_FILE = os.getenv(
    "GOOGLE_CREDENTIALS_FILE",
    "/home/deploy/.secrets/tutorscalebot/credentials.json",
)

_CONFIG_DIR = Path(__file__).resolve().parent
_TEACHER_INFO_PATH = _CONFIG_DIR / "teacher_info.json"
_PRODUCT_CONFIG_PATH = _CONFIG_DIR / "product_config.json"


def load_teacher_info() -> dict:
    """Load teacher contacts and requisites from data/teacher_info.json.
    Read on every call so edits take effect without restarting the bot.
    """
    try:
        with _TEACHER_INFO_PATH.open(encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}


def load_product_config() -> dict:
    """Load product-facing branding, trial policy and plan copy."""
    try:
        with _PRODUCT_CONFIG_PATH.open(encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError:
        return {}


def get_product_name() -> str:
    return load_product_config().get("product_name", "TutorScalebot")


def _menu_item(item_id: str, label: str, value: str, order: int, *, kind: str = "callback", enabled: bool = True) -> dict:
    return {
        "id": item_id,
        "label": label,
        "value": value,
        "kind": kind,
        "enabled": enabled,
        "order": order,
    }


def load_ui_seed_defaults() -> dict:
    teacher_info = load_teacher_info()
    product = load_product_config()
    brand = load_brand_settings()
    contacts = dict(teacher_info.get("contacts") or {})
    requisites = dict(teacher_info.get("requisites") or {})
    rates = list(requisites.get("rates") or [])
    if not rates and requisites.get("rate"):
        rates = [requisites["rate"]]

    product_name = product.get("product_name", "TutorScalebot")
    tone = brand.get("tone") or DEFAULT_BRAND_TONE

    return {
        "branding": {
            "display_name": product_name,
            "tone": tone,
        },
        "contacts": {
            "phone": contacts.get("phone", ""),
            "telegram": contacts.get("telegram", ""),
            "discord": contacts.get("discord", ""),
            "address": contacts.get("address", ""),
            "booking_url": contacts.get("booking_url", ""),
            "calendar_url": contacts.get("calendar_url", ""),
            "project_site_url": contacts.get("project_site_url", ""),
            "level_test_url": contacts.get("level_test_url", ""),
            "review_url": contacts.get("review_url", ""),
            "vk_call": contacts.get("vk_call", ""),
            "google_meet": contacts.get("google_meet", ""),
        },
        "requisites": {
            "rates": rates,
            "card": requisites.get("card", ""),
            "sbp": requisites.get("sbp", ""),
            "sbp_banks": requisites.get("sbp_banks", ""),
            "usdt_trc20": requisites.get("usdt_trc20", ""),
        },
        "reschedule": dict(teacher_info.get("reschedule") or {}),
        "copy": {
            "start_intro": f"👋 Добро пожаловать в {product_name}!",
            "help_intro": f"Короткая справка по {product_name}.",
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


def normalize_person_name(value: str) -> str:
    return " ".join((value or "").lower().replace("ё", "е").split())


def is_internal_test_account(
    full_name: str = "",
    username: str = "",
    telegram_id: int | None = None,
) -> bool:
    normalized_username = normalize_person_name(username).lstrip("@")
    normalized = normalize_person_name(full_name)
    tokens = set(normalized.split())
    for rule in INTERNAL_TEST_ACCOUNT_RULES:
        if telegram_id is not None and telegram_id in rule.get("telegram_ids", set()):
            return True
        if normalized_username and normalized_username in rule.get("usernames", set()):
            return True
        if rule["surname"] in tokens and tokens.intersection(rule["names"]):
            return True
        if tokens and tokens.issubset(rule["names"]):
            return True
    return False


def is_internal_test_account_name(full_name: str) -> bool:
    return is_internal_test_account(full_name=full_name)
