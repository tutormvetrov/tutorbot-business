import logging
from aiogram import Router, F, html
from aiogram.filters import CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from data import config
from data.config import get_product_name, load_product_config, is_internal_test_account
from keyboards.inline import (
    get_main_menu_keyboard, role_keyboard, level_keyboard,
    cancel_fsm_keyboard, make_invite_join_keyboard, make_post_registration_keyboard,
    owner_onboarding_keyboard, owner_setup_keyboard,
)
from states.registration import Registration
from utils.account_ui import (
    build_teacher_info_from_ui,
    resolve_ui_payload,
    ui_copy_text,
    ui_display_name,
    ui_tone,
)
from utils.db_api.postgresql import Database
from utils.domain_errors import BusinessRuleError
from utils.product_ui import (
    build_owner_onboarding_text,
    build_owner_setup_status,
    build_workspace_menu_text,
    owner_setup_missing_labels,
    owner_setup_needs_attention,
)
from utils.text_utils import normalize_language, parse_age
from utils.ui_text import MAIN_MENU_TEXT, build_contacts_text
from utils.workspace import extract_invite_token, extract_start_payload, workspace_role_label

router = Router()
logger = logging.getLogger(__name__)


def _progress(step: int, total: int) -> str:
    filled = "▓" * step
    empty = "░" * (total - step)
    return f"\n\n<i>Шаг {step} из {total}: {filled}{empty}</i>"


def _menu_keyboard_for_role(role: str | None, user_id: int, ui_config: dict | None = None) -> object:
    return get_main_menu_keyboard(role, is_platform_admin=user_id == config.ADMIN_ID, ui_config=ui_config)


async def _identity_id_for(db: Database, telegram_id: int, full_name: str = "", username: str | None = None) -> int | None:
    if not hasattr(db, "ensure_global_identity"):
        return None
    identity = await db.ensure_global_identity(
        telegram_id=telegram_id,
        full_name=full_name,
        username=username,
    )
    return identity["id"] if identity else None


async def _operator_recipient_ids(db: Database) -> list[int]:
    if hasattr(db, "get_account_operator_chat_ids"):
        return await db.get_account_operator_chat_ids()
    return [config.ADMIN_ID] if config.ADMIN_ID else []


async def _notify_account_operators(bot, db: Database, text: str, reply_markup=None):
    recipients = await _operator_recipient_ids(db)
    for chat_id in recipients:
        try:
            await bot.send_message(chat_id, text, reply_markup=reply_markup)
        except Exception as exc:
            logger.warning("Не удалось отправить account-scoped уведомление в %s: %s", chat_id, exc)


async def _complete_workspace_invite(message: Message, db: Database, invite_token: str) -> bool:
    previous_context = await db.resolve_account_context(message.from_user.id)
    try:
        invite_result = await db.redeem_account_invite(
            invite_token,
            message.from_user.id,
            full_name=message.from_user.full_name,
            username=message.from_user.username,
        ) if hasattr(db, "redeem_account_invite") else None
    except BusinessRuleError as exc:
        await message.answer(f"⚠️ {html.quote(str(exc))}")
        return True
    if not invite_result:
        return False

    account = invite_result.get("account") or {}
    role = (invite_result.get("account_user") or {}).get("role") or (invite_result.get("invite") or {}).get("role")
    role_label = workspace_role_label(role)
    previous_account = previous_context.get("account") or {}
    previous_account_user = previous_context.get("account_user") or {}
    previous_account_id = previous_account.get("id")
    previous_account_name = previous_account.get("name")
    if not previous_account_user:
        previous_account_id = None
        previous_account_name = None
    if previous_account_id == account.get("id"):
        previous_account_id = None
        previous_account_name = None

    await message.answer(
        "✅ <b>Аккаунт подключён</b>\n\n"
        f"Аккаунт: <b>{html.quote(account.get('name', get_product_name()))}</b>\n"
        f"Роль: <b>{html.quote(role_label)}</b>\n\n"
        "Приглашение принято. Этот аккаунт уже выбран основным. Можно сразу открыть его, "
        "вернуться в прошлый аккаунт или переключиться через список аккаунтов.",
        reply_markup=make_invite_join_keyboard(
            previous_account_id=previous_account_id,
            previous_account_name=previous_account_name,
            role=role,
        ),
    )
    return True


async def _register_admin(message: Message, db: Database):
    account_id = db.require_account_id() if hasattr(db, "require_account_id") else 1
    identity_id = await _identity_id_for(
        db,
        telegram_id=message.from_user.id,
        full_name=message.from_user.full_name,
        username=message.from_user.username,
    )
    async with db.pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users (account_id, identity_id, telegram_id, full_name, username, role)
            VALUES ($1, $2, $3, $4, $5, 'owner')
            ON CONFLICT (account_id, telegram_id) DO UPDATE
            SET identity_id = EXCLUDED.identity_id,
                full_name = EXCLUDED.full_name,
                username = EXCLUDED.username,
                role = 'owner',
                is_active = true
            """,
            account_id,
            identity_id,
            message.from_user.id,
            message.from_user.full_name,
            message.from_user.username,
        )
    if hasattr(db, "ensure_account_user"):
        await db.ensure_account_user(message.from_user.id, "owner")
    if hasattr(db, "ensure_default_subscription"):
        await db.ensure_default_subscription()
    product = load_product_config()
    ui_snapshot = await db.get_resolved_ui_config(account_id) if hasattr(db, "get_resolved_ui_config") else {}
    snapshot = await db.get_account_billing_snapshot() if hasattr(db, "get_account_billing_snapshot") else {
        "resolved": type("Snapshot", (), {"effective_status": "trial", "effective_plan_code": "practice", "trial_ends_at": None, "paid_until": None, "is_trial_active": True})(),
    }
    await message.answer(
        f"{build_owner_onboarding_text(snapshot, product)}\n\n"
        "Откройте быстрый запуск ниже: он проведёт по обязательным первым шагам без лишней ручной настройки.",
        reply_markup=owner_onboarding_keyboard,
    )


@router.message(CommandStart())
async def command_start(message: Message, state: FSMContext, db: Database):
    await state.clear()
    logger.info(f"Команда /start от {message.from_user.id}")
    user_id = message.from_user.id
    ui_snapshot = await db.get_resolved_ui_config(db.require_account_id()) if hasattr(db, "get_resolved_ui_config") else {}
    ui_payload = resolve_ui_payload(ui_snapshot)
    product_name = ui_display_name(ui_payload, fallback=get_product_name())
    payload = extract_start_payload(message.text)
    invite_token = extract_invite_token(payload)

    if user_id == config.ADMIN_ID:
        await _register_admin(message, db)
        return

    if invite_token:
        invite_redeemed = await _complete_workspace_invite(message, db, invite_token)
        if invite_redeemed:
            return
        await message.answer(
            "⚠️ Эта ссылка уже недействительна: она могла истечь, быть отозвана или уже использована.\n\n"
            "Если доступ ещё нужен, попросите владельца аккаунта создать новую ссылку.",
        )

    user = await db.get_user(user_id)

    if not user:
        start_intro = ui_copy_text(ui_payload, "start_intro", fallback=f"👋 Добро пожаловать в {product_name}!")
        await message.answer(
            f"{start_intro}\n\n"
            "Выберите вашу роль:",
            reply_markup=role_keyboard,
        )
    else:
        full_name = html.quote(user["full_name"])
        account = await db.get_account()
        account_user = await db.get_account_user(user_id, account["id"]) if account else None
        ui_snapshot = await db.get_resolved_ui_config(db.require_account_id()) if hasattr(db, "get_resolved_ui_config") else {}
        ui_payload = resolve_ui_payload(ui_snapshot)
        await message.answer(
            f"👋 С возвращением, <b>{full_name}</b>!\n\n"
            f"{build_workspace_menu_text(dict(account or {}), dict(account_user or {}), MAIN_MENU_TEXT)}",
            reply_markup=_menu_keyboard_for_role(user.get("role"), user_id, ui_payload),
        )
        if user.get("role") == "owner":
            analytics = await db.get_account_analytics_snapshot() if hasattr(db, "get_account_analytics_snapshot") else {}
            status = build_owner_setup_status(
                ui_snapshot,
                dict(analytics or {}),
                calendar_connected=bool((config.GOOGLE_CALENDAR_ID or "").strip()),
            )
            if owner_setup_needs_attention(status):
                pending = owner_setup_missing_labels(status)
                await message.answer(
                    "🚦 Быстрый запуск ещё не завершён.\n\n"
                    f"Осталось закрыть: <b>{html.quote(', '.join(pending))}</b>.\n"
                    "Там собраны оформление, контакты, реквизиты и первые рабочие шаги.",
                    reply_markup=owner_setup_keyboard,
                )


# ─── Role selected ────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("role:"))
async def process_role_choice(callback_query: CallbackQuery, state: FSMContext):
    role = callback_query.data.split(":")[1]
    total = 5 if role == "student" else 4
    await state.update_data(role=role, reg_total=total)
    await state.set_state(Registration.waiting_for_full_name)
    await callback_query.message.edit_text(
        "📝 Введите ваше <b>имя и фамилию</b>:\n\n"
        f"Например: <code>Иван Петров</code>{_progress(1, total)}",
        reply_markup=cancel_fsm_keyboard,
    )
    await callback_query.answer()


# ─── Name entered ─────────────────────────────────────────────────────────────

@router.message(StateFilter(Registration.waiting_for_full_name))
async def process_full_name(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer(
            "⚠️ Введите имя и фамилию (минимум 2 символа).",
            reply_markup=cancel_fsm_keyboard,
        )
        return

    data = await state.get_data()
    total = data.get("reg_total", 5)
    await state.update_data(full_name=name)
    await state.set_state(Registration.waiting_for_age)
    safe_name = html.quote(name)
    await message.answer(
        f"✅ Имя сохранено: <b>{safe_name}</b>\n\n"
        f"Сколько вам лет?\n\n"
        f"Например: <code>16</code> или <code>шестнадцать</code>{_progress(2, total)}",
        reply_markup=cancel_fsm_keyboard,
    )


# ─── Age entered ──────────────────────────────────────────────────────────────

@router.message(StateFilter(Registration.waiting_for_age))
async def process_age(message: Message, state: FSMContext):
    age = parse_age((message.text or "").strip())
    if age is None:
        await message.answer(
            "⚠️ Не удалось распознать возраст. Введите число или словами:\n"
            "<code>16</code> или <code>шестнадцать</code>",
            reply_markup=cancel_fsm_keyboard,
        )
        return

    data = await state.get_data()
    role = data.get("role")
    total = data.get("reg_total", 5)
    await state.update_data(age=age)

    if role == "parent":
        await state.set_state(Registration.waiting_for_student_info)
        await message.answer(
            f"✅ Возраст: <b>{age} лет</b>\n\n"
            "Введите информацию о вашем ребёнке:\n"
            "<b>Имя Фамилия, возраст</b>\n\n"
            f"Например: <i>Анна Петрова, 14</i>{_progress(3, total)}",
            reply_markup=cancel_fsm_keyboard,
        )
    else:
        await state.set_state(Registration.waiting_for_language)
        await message.answer(
            f"✅ Возраст: <b>{age} лет</b>\n\n"
            "Какой язык вы хотите изучать?\n\n"
            f"Например: <code>английский</code>, <code>French</code>{_progress(3, total)}",
            reply_markup=cancel_fsm_keyboard,
        )


# ─── Language entered ─────────────────────────────────────────────────────────

@router.message(StateFilter(Registration.waiting_for_language))
async def process_language(message: Message, state: FSMContext):
    raw = (message.text or "").strip()
    if not raw:
        await message.answer(
            "⚠️ Введите название языка.",
            reply_markup=cancel_fsm_keyboard,
        )
        return

    language, is_known = normalize_language(raw)
    data = await state.get_data()
    total = data.get("reg_total", 5)
    await state.update_data(language=language)
    await state.set_state(Registration.waiting_for_level)

    if is_known:
        lang_line = f"✅ Язык: <b>{language}</b>"
    else:
        lang_line = (
            f"⚠️ Язык сохранён как «<b>{language}</b>».\n"
            "Если это опечатка — введите язык снова.\n"
            "Иначе выберите уровень ниже:"
        )
    await message.answer(
        f"{lang_line}{_progress(4, total)}\n\n"
        "Выберите ваш текущий уровень:",
        reply_markup=level_keyboard,
    )


# ─── Level selected ───────────────────────────────────────────────────────────

LEVEL_LABELS = {
    "A1": "A1 — Начинающий",
    "A2": "A2 — Элементарный",
    "B1": "B1 — Средний",
    "B2": "B2 — Выше среднего",
    "C1": "C1 — Продвинутый",
    "C2": "C2 — Мастерство",
    "unknown": "Не знаю",
}


@router.callback_query(F.data.startswith("level:"), StateFilter(Registration.waiting_for_level))
async def process_level(callback_query: CallbackQuery, state: FSMContext, db: Database):
    level = callback_query.data.split(":", 1)[1]
    data = await state.get_data()
    full_name = data["full_name"]
    language = data["language"]
    user_id = callback_query.from_user.id
    account_id = db.require_account_id() if hasattr(db, "require_account_id") else 1
    identity_id = await _identity_id_for(
        db,
        telegram_id=user_id,
        full_name=full_name,
        username=callback_query.from_user.username,
    )
    is_internal_account = is_internal_test_account(
        full_name=full_name,
        username=callback_query.from_user.username or "",
        telegram_id=user_id,
    )
    if hasattr(db, "ensure_student_capacity"):
        try:
            await db.ensure_student_capacity(
                user_id,
                is_internal=is_internal_account,
                account_id=account_id,
            )
        except BusinessRuleError as exc:
            await state.clear()
            await callback_query.message.edit_text(
                f"⚠️ {html.quote(str(exc))}\n\n"
                "Если нужно, можно выбрать другой тариф или попросить преподавателя освободить слот.",
                reply_markup=cancel_fsm_keyboard,
            )
            await callback_query.answer()
            return

    async with db.pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users (account_id, identity_id, telegram_id, full_name, username, role, age, language, level, is_internal_account)
            VALUES ($1, $2, $3, $4, $5, 'student', $6, $7, $8, $9)
            ON CONFLICT (account_id, telegram_id) DO UPDATE
            SET identity_id = EXCLUDED.identity_id,
                full_name = EXCLUDED.full_name,
                username = EXCLUDED.username,
                role = EXCLUDED.role,
                age = EXCLUDED.age,
                language = EXCLUDED.language,
                level = EXCLUDED.level,
                is_internal_account = EXCLUDED.is_internal_account,
                is_active = true
            """,
            account_id,
            identity_id,
            user_id,
            full_name,
            callback_query.from_user.username,
            data.get("age"),
            language,
            level,
            is_internal_account,
        )
    if hasattr(db, "ensure_account_user"):
        await db.ensure_account_user(user_id, "student")
    sync_parent_links = getattr(db, "sync_parent_links_for_student", None)
    if callable(sync_parent_links):
        await sync_parent_links(user_id, full_name)

    await state.clear()
    level_label = LEVEL_LABELS.get(level, level)
    safe_full_name = html.quote(full_name)
    safe_language = html.quote(language)
    safe_level_label = html.quote(level_label)

    await _notify_account_operators(
        callback_query.bot,
        db,
        f"🎉 <b>Новый ученик!</b>\n\n"
        f"👤 {safe_full_name}\n"
        f"🎂 Возраст: {data.get('age')} лет\n"
        f"📚 Язык: {safe_language}  •  📊 Уровень: {safe_level_label}",
    )

    ui_snapshot = await db.get_resolved_ui_config(account_id) if hasattr(db, "get_resolved_ui_config") else {}
    ui_payload = resolve_ui_payload(ui_snapshot)
    info = build_teacher_info_from_ui(ui_payload)
    contacts_text = build_contacts_text(
        info,
        show_address=True,
        tone=ui_tone(ui_payload),
        intro_text=ui_copy_text(ui_payload, "post_registration_intro"),
    )
    booking_url = info.get("contacts", {}).get("booking_url", "")
    website_url = info.get("contacts", {}).get("project_site_url", "")

    await callback_query.message.edit_text(
        f"✅ <b>Регистрация завершена!</b>\n\n"
        f"👤 {safe_full_name}  •  🎂 {data.get('age')} лет\n"
        f"📚 {safe_language}  •  📊 {safe_level_label}\n\n"
        f"{contacts_text}\n\n"
        "Тест уровня и уведомления доступны в профиле.",
        reply_markup=make_post_registration_keyboard(booking_url, website_url),
    )
    await callback_query.answer()


# ─── Parent: child info ────────────────────────────────────────────────────────

@router.message(StateFilter(Registration.waiting_for_student_info))
async def process_student_info(message: Message, state: FSMContext, db: Database):
    parts = (message.text or "").split(",", 1)
    if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
        await message.answer(
            "⚠️ Не удалось распознать формат. Введите данные так:\n"
            "<b>Анна Петрова, 14</b>",
            reply_markup=cancel_fsm_keyboard,
        )
        return

    student_name = parts[0].strip()
    student_age = parts[1].strip()
    data = await state.get_data()
    full_name = data["full_name"]
    account_id = db.require_account_id() if hasattr(db, "require_account_id") else 1
    identity_id = await _identity_id_for(
        db,
        telegram_id=message.from_user.id,
        full_name=full_name,
        username=message.from_user.username,
    )
    is_internal_account = is_internal_test_account(
        full_name=full_name,
        username=message.from_user.username or "",
        telegram_id=message.from_user.id,
    )

    async with db.pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users (account_id, identity_id, telegram_id, full_name, username, role, is_internal_account)
            VALUES ($1, $2, $3, $4, $5, 'parent', $6)
            ON CONFLICT (account_id, telegram_id) DO UPDATE
            SET identity_id = EXCLUDED.identity_id,
                full_name = EXCLUDED.full_name,
                username = EXCLUDED.username,
                role = EXCLUDED.role,
                is_internal_account = EXCLUDED.is_internal_account,
                is_active = true
            """,
            account_id,
            identity_id,
            message.from_user.id,
            full_name,
            message.from_user.username,
            is_internal_account,
        )
    if hasattr(db, "ensure_account_user"):
        await db.ensure_account_user(message.from_user.id, "parent")

    find_active_student = getattr(db, "find_active_student_by_name", None)
    upsert_parent_link = getattr(db, "upsert_parent_student_link", None)
    if callable(upsert_parent_link):
        linked_student = await find_active_student(student_name) if callable(find_active_student) else None
        await upsert_parent_link(
            parent_id=message.from_user.id,
            student_info=f"{student_name} ({student_age})",
            student_id=linked_student["telegram_id"] if linked_student else None,
        )

    await state.clear()
    safe_full_name = html.quote(full_name)
    safe_student_name = html.quote(student_name)
    safe_student_age = html.quote(student_age)
    ui_snapshot = await db.get_resolved_ui_config(account_id) if hasattr(db, "get_resolved_ui_config") else {}
    await message.answer(
        f"✅ <b>Регистрация завершена!</b>\n\n"
        f"👤 Вы: {safe_full_name}\n"
        f"👧 Ребёнок: {safe_student_name}, {safe_student_age} лет.\n\n"
        "Главные действия для родителя собраны в меню ниже.",
        reply_markup=_menu_keyboard_for_role("parent", message.from_user.id, resolve_ui_payload(ui_snapshot)),
    )
