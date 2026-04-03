import logging

from aiogram import Router, html, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from keyboards.inline import (
    back_to_admin_keyboard,
    make_calendar_alias_editor_keyboard,
    make_calendar_alias_student_keyboard,
    make_paywall_keyboard,
)
from states.registration import AdminCalendarAliases
from utils.capabilities import capability_label
from utils.db_api.postgresql import Database
from utils.google_calendar import format_sync_report_html, load_last_sync_report, sync_calendar_to_db
from utils.product_ui import build_paywall_text
from utils.workspace import has_workspace_admin_access

logger = logging.getLogger(__name__)
router = Router()


def _is_admin(user_id: int) -> bool:
    return has_workspace_admin_access(user_id)


def _q(value) -> str:
    return html.quote(str(value)) if value is not None else "—"


def _parse_calendar_alias_input(text: str) -> list[dict]:
    items = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.lower().startswith("re:"):
            pattern = line[3:].strip()
            if pattern:
                items.append({"calendar_alias": None, "calendar_event_pattern": pattern})
        else:
            items.append({"calendar_alias": line, "calendar_event_pattern": None})
    return items


def _merge_calendar_alias_items(existing_links: list, new_items: list[dict], replace: bool = False) -> list[dict]:
    merged = [] if replace else [
        {
            "calendar_alias": (link.get("calendar_alias") or "").strip() or None,
            "calendar_event_pattern": (link.get("calendar_event_pattern") or "").strip() or None,
        }
        for link in existing_links
    ]
    seen = {
        (
            (item.get("calendar_alias") or "").strip().lower(),
            (item.get("calendar_event_pattern") or "").strip().lower(),
        )
        for item in merged
    }
    for item in new_items:
        key = (
            (item.get("calendar_alias") or "").strip().lower(),
            (item.get("calendar_event_pattern") or "").strip().lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(
            {
                "calendar_alias": (item.get("calendar_alias") or "").strip() or None,
                "calendar_event_pattern": (item.get("calendar_event_pattern") or "").strip() or None,
            }
        )
    return merged


def _render_calendar_alias_lines(links: list) -> list[str]:
    if not links:
        return ["Пока пусто."]

    lines = []
    for link in links:
        alias = (link.get("calendar_alias") or "").strip()
        pattern = (link.get("calendar_event_pattern") or "").strip()
        if alias:
            lines.append(f"• alias: <code>{_q(alias)}</code>")
        if pattern:
            lines.append(f"• regex: <code>{_q(pattern)}</code>")
    return lines


def _build_calendar_sync_snapshot_lines() -> list[str]:
    report = load_last_sync_report()
    if not report:
        return []

    lines = [
        "",
        "Последний sync:",
        (
            f"• {report.get('events_fetched', 0)} событий  |  "
            f"+{report.get('imported', 0)} / ♻️{report.get('updated', 0)} / "
            f"⏭ {report.get('skipped', 0)} / 🗑 {report.get('deleted', 0)}"
        ),
    ]
    unresolved = [
        item for item in (report.get("skipped_items") or [])
        if item.get("reason") in {"no_alias_match", "ambiguous_alias_match", "student_id_not_found"}
    ]
    if unresolved:
        lines.append("Примеры непривязанных событий:")
        for item in unresolved[:3]:
            lines.append(
                f"• {html.quote(item.get('summary', 'Без названия'))}"
            )
    return lines


@router.callback_query(lambda c: c.data == 'admin:calendar_aliases')
async def admin_calendar_aliases(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    if not await db.has_capability("calendar_sync"):
        snapshot = await db.get_account_billing_snapshot()
        await callback_query.message.edit_text(
            build_paywall_text(capability_label("calendar_sync"), snapshot, snapshot["product"]),
            reply_markup=make_paywall_keyboard(back_callback="admin:cat:service", show_billing=True),
        )
        await callback_query.answer()
        return

    students = await db.get_students_with_calendar_alias_counts()
    if not students:
        await callback_query.message.edit_text(
            "🧭 <b>Алиасы Calendar</b>\n\nНет активных учеников.",
            reply_markup=back_to_admin_keyboard,
        )
        await callback_query.answer()
        return

    await state.set_state(AdminCalendarAliases.waiting_for_student)
    await callback_query.message.edit_text(
        "🧭 <b>Алиасы Calendar</b>\n\n"
        "Выберите ученика. Число в скобках — сколько у него активных алиасов.",
        reply_markup=make_calendar_alias_student_keyboard(students),
    )
    await callback_query.answer()


@router.callback_query(
    lambda c: c.data.startswith('calendar_alias_student:'),
    StateFilter(AdminCalendarAliases.waiting_for_student),
)
async def admin_calendar_alias_student_selected(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    student_id = int(callback_query.data.split(':')[1])
    student = await db.get_user(student_id)
    links = await db.get_calendar_student_links_for_student(student_id)
    await state.set_state(AdminCalendarAliases.waiting_for_aliases)
    await state.update_data(student_id=student_id)

    name = _q(student['full_name']) if student else str(student_id)
    lines = [
        f"🧭 <b>Алиасы Calendar для {name}</b>",
        "",
        "Текущие правила:",
        *_render_calendar_alias_lines(links),
        "",
        "Отправьте новые правила сообщением.",
        "По умолчанию новые строки <b>добавляются</b> к уже существующим.",
        "Если нужно полностью заменить список, начните сообщение со строки <code>!replace</code>.",
        "Каждая следующая строка — отдельный alias.",
        "Если нужен regex, начните строку с <code>re:</code>",
        "",
        "Пример:",
        "<code>Анной Смирновой</code>",
        "<code>Анна Смирнова</code>",
        "<code>re:Урок с Анной Смирновой</code>",
    ]
    lines.extend(_build_calendar_sync_snapshot_lines())
    await callback_query.message.edit_text(
        "\n".join(lines),
        reply_markup=make_calendar_alias_editor_keyboard(student_id),
    )
    await callback_query.answer()


@router.message(StateFilter(AdminCalendarAliases.waiting_for_aliases))
async def admin_calendar_aliases_text(message: types.Message, state: FSMContext, db: Database):
    data = await state.get_data()
    student_id = data.get("student_id")
    if not student_id:
        await state.clear()
        await message.answer("⚠️ Ученик не выбран.", reply_markup=back_to_admin_keyboard)
        return

    raw_text = (message.text or "").strip()
    replace_mode = False
    if raw_text.lower().startswith("!replace"):
        replace_mode = True
        raw_text = raw_text[len("!replace"):].strip()

    items = _parse_calendar_alias_input(raw_text)
    if not items:
        await message.answer(
            "⚠️ Не удалось распознать ни одного alias.\n"
            "Отправьте по одному alias на строку или regex в формате <code>re:...</code>.\n"
            "Для полной замены списка начните сообщение со строки <code>!replace</code>.",
            reply_markup=make_calendar_alias_editor_keyboard(student_id),
        )
        return

    existing_links = await db.get_calendar_student_links_for_student(student_id)
    merged_items = _merge_calendar_alias_items(existing_links, items, replace=replace_mode)
    await db.replace_calendar_student_links(student_id, merged_items)
    student = await db.get_user(student_id)
    name = _q(student['full_name']) if student else str(student_id)
    await message.answer("🔄 Алиасы сохранены. Пересинхронизирую Google Calendar...")
    await state.clear()
    await message.answer(
        f"✅ <b>Алиасы сохранены</b> для {name}.\n\n"
        f"Режим: <b>{'полная замена' if replace_mode else 'добавление'}</b>\n"
        f"Всего активных правил: <b>{len(merged_items)}</b>",
        reply_markup=back_to_admin_keyboard,
    )
    try:
        report = await sync_calendar_to_db(db)
    except Exception as exc:
        logger.error("Ошибка автосинхронизации Calendar после сохранения алиасов: %s", exc)
        await message.answer(
            f"⚠️ Автосинхронизация не удалась:\n<code>{_q(exc)}</code>",
            reply_markup=back_to_admin_keyboard,
        )
        return

    await message.answer(
        format_sync_report_html(report),
        reply_markup=back_to_admin_keyboard,
    )


@router.callback_query(lambda c: c.data.startswith('calendar_aliases:clear:'))
async def admin_calendar_aliases_clear(callback_query: types.CallbackQuery, state: FSMContext, db: Database):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return

    student_id = int(callback_query.data.split(':')[2])
    await db.clear_calendar_student_links(student_id)
    student = await db.get_user(student_id)
    name = _q(student['full_name']) if student else str(student_id)
    await state.clear()
    await callback_query.message.edit_text(
        f"🗑 <b>Алиасы очищены</b> для {name}.",
        reply_markup=back_to_admin_keyboard,
    )
    await callback_query.answer()
