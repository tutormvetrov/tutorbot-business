import json
import logging
from datetime import datetime
from pathlib import Path

from aiogram import Router, html, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext

from keyboards.inline import admin_notes_keyboard, cancel_fsm_keyboard, make_back_button_keyboard
from states.registration import AdminNotes
from utils.workspace import has_workspace_admin_access

router = Router()
logger = logging.getLogger(__name__)

NOTES_FILE = Path(__file__).resolve().parents[3] / "data" / "admin_notes.json"
CLAUDE_MEMORY_DIR = Path.home() / ".claude" / "projects" / "-root-bot" / "memory"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
CLAUDE_DOC_FILE = PROJECT_ROOT / "CLAUDE.md"
AGENT_CONTEXT_FILE = PROJECT_ROOT / "AGENT_CONTEXT.md"
DEBUG_CONTEXT_LOG_FILE = PROJECT_ROOT / "data" / "debug_context.jsonl"
DEBUG_MEDIA_DIR = PROJECT_ROOT / "data" / "debug_media"
SERVICE_BACK_KEYBOARD = make_back_button_keyboard("◀️ К сервису", "admin:cat:service")


def _is_admin(user_id: int) -> bool:
    return has_workspace_admin_access(user_id)


def _load_notes() -> list:
    if not NOTES_FILE.exists():
        return []
    try:
        return json.loads(NOTES_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_notes(notes: list):
    NOTES_FILE.write_text(json.dumps(notes, ensure_ascii=False, indent=2), encoding="utf-8")
    _sync_all_note_targets(notes)


def _append_debug_context_event(event_type: str, note: dict | None = None, notes_count: int | None = None):
    payload = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "event": event_type,
        "notes_count": notes_count,
    }
    if note is not None:
        payload["note"] = {
            "timestamp": note.get("timestamp"),
            "content": note.get("content"),
            "kind": note.get("kind", "text"),
            "local_path": note.get("local_path"),
        }
    DEBUG_CONTEXT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with DEBUG_CONTEXT_LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _safe_sync(step_name: str, sync_fn, notes: list):
    try:
        sync_fn(notes)
    except Exception as exc:
        logger.warning("Не удалось обновить %s: %s", step_name, exc)


def _sync_all_note_targets(notes: list):
    _safe_sync("CLAUDE.md", _sync_notes_to_project_doc, notes)
    _safe_sync("Claude memory", _sync_notes_to_claude_memory, notes)
    _safe_sync("AGENT_CONTEXT.md", _sync_notes_to_agent_context, notes)


def _note_kind(note: dict) -> str:
    return note.get("kind") or ("photo" if note.get("local_path") else "text")


def _note_summary(note: dict) -> str:
    content = (note.get("content") or "").strip()
    if _note_kind(note) == "photo":
        return f"🖼 {content}" if content else "🖼 Скриншот без подписи"
    return content


def _note_detail_lines(note: dict) -> list[str]:
    content = (note.get("content") or "").strip()
    if _note_kind(note) == "photo":
        lines = ["🖼 Скриншот"]
        if content:
            lines.append(content)
        if note.get("local_path"):
            lines.append(f"Файл: `{note['local_path']}`")
        return lines
    return [content] if content else ["(пустая заметка)"]


def _sync_notes_to_project_doc(notes: list):
    lines = [
        "# CLAUDE.md",
        "",
        "Этот файл хранит пожелания и рабочий контекст владельца проекта.",
        "Актуальный статус реализации см. в `IMPLEMENTATION_STATUS.md`.",
        "",
        "## Источник",
        "",
        "- `data/admin_notes.json`",
        "- заметки из админ-панели бота",
        "",
        "## Текущие пожелания",
        "",
    ]
    if notes:
        for note in notes:
            lines.append(f"### {note['timestamp']}")
            lines.append("")
            lines.extend(_note_detail_lines(note))
            lines.append("")
    else:
        lines.append("Пока пожеланий нет.")
        lines.append("")
    CLAUDE_DOC_FILE.write_text("\n".join(lines), encoding="utf-8")


def _sync_notes_to_claude_memory(notes: list):
    CLAUDE_MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    notes_file = CLAUDE_MEMORY_DIR / "admin_notes.md"
    lines = [
        "---",
        "name: Admin Debug Notes",
        "description: Заметки администратора — важный контекст для текущей работы с ботом",
        "type: project",
        "---",
        "",
    ]
    if notes:
        for note in notes:
            lines.append(f"## {note['timestamp']}")
            lines.extend(_note_detail_lines(note))
            lines.append("")
    else:
        lines.append("_(Заметок нет)_")
    notes_file.write_text("\n".join(lines), encoding="utf-8")

    memory_index = CLAUDE_MEMORY_DIR / "MEMORY.md"
    pointer = "- [Admin Debug Notes](admin_notes.md) — заметки администратора для контекста"
    if memory_index.exists():
        content = memory_index.read_text(encoding="utf-8")
        if "admin_notes.md" not in content:
            memory_index.write_text(content.rstrip() + "\n" + pointer + "\n", encoding="utf-8")
    else:
        memory_index.write_text(pointer + "\n", encoding="utf-8")


def _sync_notes_to_agent_context(notes: list):
    lines = [
        "# AGENT_CONTEXT.md",
        "",
        "Этот файл обновляется ботом автоматически.",
        "Он нужен как краткий актуальный контекст для следующей рабочей сессии агента.",
        "",
        "## Где смотреть полную историю",
        "",
        "- `data/admin_notes.json` — текущее состояние сообщений для отладки",
        "- `data/debug_context.jsonl` — журнал изменений",
        "- `CLAUDE.md` — рабочая сводка проекта",
        "",
        "## Активные сообщения для отладки",
        "",
    ]
    if notes:
        for index, note in enumerate(reversed(notes), 1):
            lines.append(f"{index}. {note['timestamp']}")
            lines.extend(_note_detail_lines(note))
            lines.append("")
    else:
        lines.append("Сейчас активных сообщений нет.")
        lines.append("")
    AGENT_CONTEXT_FILE.write_text("\n".join(lines), encoding="utf-8")


async def _save_message_image(message: types.Message) -> dict | None:
    file_id = None
    unique_id = None
    fallback_name = ""
    if message.photo:
        item = message.photo[-1]
        file_id = item.file_id
        unique_id = item.file_unique_id
        fallback_name = ".jpg"
    elif message.document and (message.document.mime_type or "").startswith("image/"):
        item = message.document
        file_id = item.file_id
        unique_id = item.file_unique_id
        fallback_name = item.file_name or ".png"
    else:
        return None

    file = await message.bot.get_file(file_id)
    suffix = Path(file.file_path or fallback_name).suffix or Path(fallback_name).suffix or ".jpg"
    filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{unique_id}{suffix}"
    destination = DEBUG_MEDIA_DIR / filename
    DEBUG_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    await message.bot.download_file(file.file_path, destination=destination)
    return {
        "kind": "photo",
        "file_id": file_id,
        "local_path": str(destination),
        "telegram_path": file.file_path,
    }


async def _build_note_from_message(message: types.Message) -> dict | None:
    timestamp = datetime.now().strftime("%d.%m.%Y %H:%M МСК")
    content = (message.text or message.caption or "").strip()
    image_meta = await _save_message_image(message)
    if image_meta is not None:
        return {
            "timestamp": timestamp,
            "content": content,
            **image_meta,
        }
    if content:
        return {
            "timestamp": timestamp,
            "content": content,
            "kind": "text",
        }
    return None


def ensure_debug_context_files():
    notes = _load_notes()
    _sync_all_note_targets(notes)
    if not DEBUG_CONTEXT_LOG_FILE.exists():
        try:
            _append_debug_context_event("bootstrap_sync", notes_count=len(notes))
        except Exception as exc:
            logger.warning("Не удалось инициализировать debug_context.jsonl: %s", exc)


@router.callback_query(lambda c: c.data == 'admin:notes')
async def admin_notes_view(callback_query: types.CallbackQuery, state: FSMContext):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await state.clear()
    notes = _load_notes()
    if notes:
        lines = [f"📝 <b>Сообщения для отладки</b> ({len(notes)} шт.)\n"]
        for i, note in enumerate(notes, 1):
            lines.append(f"<b>{i}. {note['timestamp']}</b>")
            lines.append(html.quote(_note_summary(note)))
            lines.append("")
        text = "\n".join(lines)
    else:
        text = "📝 <b>Сообщения для отладки</b>\n\nСообщений пока нет."
    await callback_query.message.edit_text(text, reply_markup=admin_notes_keyboard)
    await callback_query.answer()


@router.callback_query(lambda c: c.data == 'admin:notes:add')
async def admin_notes_add_start(callback_query: types.CallbackQuery, state: FSMContext):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    await state.set_state(AdminNotes.waiting_for_text)
    await callback_query.message.edit_text(
        "📝 Отправьте текст или фото для рабочей заметки.\n\n"
        "Скриншот можно прислать с подписью или без неё. Заметка сразу попадёт в контекст проекта для следующей сессии.",
        reply_markup=cancel_fsm_keyboard,
    )
    await callback_query.answer()


@router.message(StateFilter(AdminNotes.waiting_for_text))
async def admin_notes_text_entered(message: types.Message, state: FSMContext):
    note = await _build_note_from_message(message)
    if not note:
        await message.answer(
            "⚠️ Пришлите текст или фото со скриншотом.",
            reply_markup=cancel_fsm_keyboard,
        )
        return

    notes = _load_notes()
    notes.append(note)
    _save_notes(notes)
    _append_debug_context_event("note_added", note=note, notes_count=len(notes))

    await state.clear()
    saved_title = "✅ <b>Скриншот сохранён.</b>" if _note_kind(note) == "photo" else "✅ <b>Заметка сохранена.</b>"
    summary = _note_summary(note)
    detail = f"\n\n{html.quote(summary)}" if summary else ""
    await message.answer(
        f"{saved_title}{detail}",
        reply_markup=SERVICE_BACK_KEYBOARD,
    )


@router.callback_query(lambda c: c.data == 'admin:notes:clear')
async def admin_notes_clear(callback_query: types.CallbackQuery):
    if not _is_admin(callback_query.from_user.id):
        await callback_query.answer()
        return
    _save_notes([])
    _append_debug_context_event("notes_cleared", notes_count=0)
    await callback_query.message.edit_text(
        "🗑 <b>Все сообщения очищены.</b>",
        reply_markup=SERVICE_BACK_KEYBOARD,
    )
    await callback_query.answer()


ensure_debug_context_files()
