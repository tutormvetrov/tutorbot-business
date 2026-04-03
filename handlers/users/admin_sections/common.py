from aiogram import html, types

from data import config
from data.config import load_teacher_info
from utils.brand import choose_tone_variant
from utils.speech import choose_form


def is_admin(user_id: int) -> bool:
    return user_id == config.ADMIN_ID


def q(value) -> str:
    return html.quote(str(value)) if value is not None else "—"


def message_to_html(message: types.Message) -> str:
    text = (message.text or "").strip()
    if not text:
        return ""
    if message.entities:
        formatted = (message.html_text or "").strip()
        if formatted:
            return formatted
    return html.quote(text)


def message_or_caption_to_html(message: types.Message) -> str:
    raw = (message.text or message.caption or "").strip()
    if not raw:
        return ""
    if message.entities or getattr(message, "caption_entities", None):
        formatted = (message.html_text or "").strip()
        if formatted:
            return formatted
    return html.quote(raw)


def extract_broadcast_payload(message: types.Message) -> dict | None:
    preview_text = message_or_caption_to_html(message)
    origin_chat_id, origin_message_id = get_message_origin(message, message.from_user.id)

    text = (message.text or "").strip()
    if text:
        return {
            "mode": "text",
            "text": preview_text,
            "preview": preview_text,
        }

    media_labels = [
        ("animation", "🎞 <b>GIF-анимация</b>"),
        ("sticker", "🧩 <b>Стикер</b>"),
        ("photo", "🖼 <b>Фото</b>"),
        ("video", "🎬 <b>Видео</b>"),
        ("document", "📎 <b>Документ</b>"),
        ("voice", "🎤 <b>Голосовое сообщение</b>"),
    ]
    for attr, label in media_labels:
        if getattr(message, attr, None):
            preview = label
            if preview_text:
                preview += f"\n\n{preview_text}"
            return {
                "mode": "copy",
                "preview": preview,
                "source_chat_id": origin_chat_id,
                "source_message_id": origin_message_id,
            }

    return None


def get_level_test_url(info: dict | None = None) -> str:
    info = info or load_teacher_info()
    contacts = info.get("contacts", {})
    return contacts.get("level_test_url", "") or info.get("level_test_url", "")


def build_level_test_broadcast_text(speech_style: str | None = None) -> str:
    url = get_level_test_url()
    intro = choose_tone_variant(
        "Я подготовил короткий тест, который поможет точнее определить",
        "Я подготовил короткий тест, который поможет точнее определить",
        "Я подготовил короткий тест, который поможет точнее определить",
        "Я подготовил небольшой тест, который поможет точнее определить",
    )
    second_line = choose_tone_variant(
        "Так будет проще подобрать подходящую программу занятий и темп.",
        "Так будет проще подобрать подходящую программу занятий и темп.",
        "Так будет проще подобрать подходящую программу занятий и темп.",
        "Так будет легче подобрать подходящий формат занятий и темп.",
    )
    if url:
        safe_url = html.quote(url)
        return (
            "🧪 <b>Тест уровня языка</b>\n\n"
            f"{intro} {choose_form(speech_style, 'ваш', 'твой')} текущий уровень.\n"
            f"{second_line}\n\n"
            f"👉 <a href=\"{safe_url}\">Пройти тест</a>"
        )
    return (
        "🧪 <b>Тест уровня языка</b>\n\n"
        f"Я подготовил короткий тест для определения {choose_form(speech_style, 'вашего', 'твоего')} текущего уровня.\n"
        "Ссылка будет отправлена чуть позже."
    )


class MessageEditor:
    def __init__(self, bot, chat_id: int, message_id: int):
        self.bot = bot
        self.chat_id = chat_id
        self.message_id = message_id

    async def edit_text(self, text: str, reply_markup=None):
        await self.bot.edit_message_text(
            text=text,
            chat_id=self.chat_id,
            message_id=self.message_id,
            reply_markup=reply_markup,
        )


def get_message_origin(message: types.Message, fallback_chat_id: int | None = None) -> tuple[int | None, int | None]:
    chat = getattr(message, "chat", None)
    chat_id = getattr(chat, "id", None) or fallback_chat_id
    message_id = getattr(message, "message_id", None)
    return chat_id, message_id


async def restore_admin_view(bot, db, chat_id: int | None, message_id: int | None, view: str | None):
    if not view or chat_id is None or message_id is None:
        return False

    target = MessageEditor(bot, chat_id, message_id)

    if view in {"admin:home", "back_to_admin"}:
        from handlers.users.admin import render_admin_home

        await render_admin_home(target, db)
        return True

    if view.startswith("admin:cat:"):
        from handlers.users.admin import render_admin_category

        category = view.split(":", 2)[2]
        await render_admin_category(target, category)
        return True

    if view.startswith("admin:student_card:"):
        from handlers.users.admin_sections.students import _render_admin_student_card

        _, _, student_id_str, page_str = view.split(":")
        await _render_admin_student_card(target, db, int(student_id_str), int(page_str))
        return True

    if view.startswith("admin:students:page:"):
        from handlers.users.admin_sections.students import _render_admin_students_page

        page = int(view.split(":")[3])
        await _render_admin_students_page(target, db, page=page)
        return True

    if view.startswith("admin:student_payments:"):
        from handlers.users.admin_sections.payments import _render_admin_payments

        parts = view.split(":")
        student_id = int(parts[2])
        page = int(parts[3]) if len(parts) > 3 else None
        await _render_admin_payments(target, db, student_id, page=page)
        return True

    if view == "admin:all_homework":
        from handlers.users.admin_sections.homework import _render_admin_homework_list

        await _render_admin_homework_list(target, db)
        return True

    if view == "admin:groups":
        from keyboards.inline import make_groups_keyboard
        from utils.product_ui import build_groups_text

        groups = await db.get_groups_overview()
        await target.edit_text(build_groups_text(groups), reply_markup=make_groups_keyboard(groups))
        return True

    if view == "admin:invites":
        from keyboards.inline import make_invites_keyboard
        from utils.product_ui import build_invites_text

        account = await db.get_account()
        invites = await db.get_active_account_invites()
        await target.edit_text(
            build_invites_text(dict(account or {}), [dict(item) for item in invites]),
            reply_markup=make_invites_keyboard(invites),
        )
        return True

    if view == "admin:support":
        from keyboards.inline import support_keyboard
        from utils.product_ui import build_support_text

        support_snapshot = await db.get_support_snapshot()
        product = support_snapshot["billing"]["product"]
        await target.edit_text(
            build_support_text(support_snapshot, product),
            reply_markup=support_keyboard,
        )
        return True

    if view.startswith("admin:group:view:"):
        from keyboards.inline import make_group_detail_keyboard
        from utils.product_ui import build_group_detail_text

        group_id = int(view.split(":")[3])
        group = await db.get_group(group_id)
        if not group:
            return False
        members = await db.get_group_members(group_id)
        await target.edit_text(build_group_detail_text(group, members), reply_markup=make_group_detail_keyboard(group_id))
        return True

    return False
