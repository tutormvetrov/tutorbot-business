from __future__ import annotations

from datetime import datetime

from aiogram import html

from utils.account_ui import UI_MENU_SECTION_LABELS, UI_PREVIEW_ROLES, get_menu_entries, resolve_ui_payload
from utils.capabilities import CAPABILITY_ORDER, TRIAL_STATUS_LABELS, capability_label, limit_label
from utils.workspace import build_invite_start_link, workspace_role_label


def _format_datetime(value: datetime | None) -> str:
    return value.strftime("%d.%m.%Y %H:%M") if value else "—"


def _plan_name(product: dict, plan_code: str) -> str:
    return product.get("plans", {}).get(plan_code, {}).get("display_name", plan_code.title())


def _locked_features_lines(snapshot: dict) -> list[str]:
    resolved = snapshot["resolved"]
    if not resolved.locked_capabilities:
        return ["Все основные функции уже доступны."]
    return [f"• {html.quote(capability_label(item))}" for item in resolved.locked_capabilities]


def build_workspace_menu_text(account: dict | None, account_user: dict | None, base_text: str) -> str:
    account_name = (account or {}).get("name")
    role_label = workspace_role_label((account_user or {}).get("role"))
    lines = []
    if account_name:
        lines.extend([
            f"🏢 <b>{html.quote(account_name)}</b>",
            f"Роль в аккаунте: <b>{html.quote(role_label)}</b>",
            "",
        ])
    lines.append(base_text)
    return "\n".join(lines)


def build_workspace_selector_text(
    memberships: list[dict],
    current_account_id: int | None = None,
    identity: dict | None = None,
) -> str:
    lines = [
        "🏢 <b>Аккаунты</b>",
        "",
    ]
    if identity:
        display_name = identity.get("full_name") or ("@" + identity["username"] if identity.get("username") else None)
        if display_name:
            lines.append(f"Профиль: <b>{html.quote(display_name)}</b>")
        if identity.get("last_active_account_id"):
            lines.append(f"Последний открытый аккаунт: <b>{html.quote(str(identity['last_active_account_id']))}</b>")
        lines.append("")

    if not memberships:
        lines.append("У вас пока нет доступных аккаунтов.")
        return "\n".join(lines)

    lines.append(f"Доступно аккаунтов: <b>{len(memberships)}</b>")
    for membership in memberships:
        marker = "✅" if membership.get("account_id") == current_account_id else "•"
        lines.append(
            f"{marker} <b>{html.quote(membership.get('account_name', 'Аккаунт'))}</b> "
            f"· {html.quote(workspace_role_label(membership.get('role')))}"
        )
    lines.extend([
        "",
        "Выберите аккаунт ниже. Он станет основным для следующих экранов и команд.",
    ])
    return "\n".join(lines)


def build_product_hub_text(snapshot: dict | None, product: dict) -> str:
    lines = [
        f"💼 <b>{html.quote(product.get('product_name', 'TutorScalebot'))}</b>",
        "",
        html.quote(product.get("tagline", "Telegram-бот для репетиторов и мини-школ")),
    ]
    why_paid = product.get("why_paid") or []
    if why_paid:
        lines.extend(["", "<b>Что бот берёт на себя:</b>"])
        lines.extend([f"• {html.quote(item)}" for item in why_paid])
    if snapshot:
        resolved = snapshot["resolved"]
        lines.extend([
            "",
            "<b>Состояние аккаунта сейчас:</b>",
            f"• Выбранный тариф: <b>{html.quote(_plan_name(product, resolved.plan_code))}</b>",
            f"• Доступ сейчас: <b>{html.quote(_plan_name(product, resolved.effective_plan_code))}</b>",
            f"• Статус: <b>{html.quote(TRIAL_STATUS_LABELS.get(resolved.effective_status, resolved.effective_status))}</b>",
            f"• Активных возможностей уже открыто: <b>{sum(1 for enabled in resolved.capabilities.values() if enabled)}</b>",
            "",
            "Если аккаунт только запускается, начните с быстрой настройки: оформление, контакты, реквизиты, первый ученик и первое занятие.",
        ])
    return "\n".join(lines)


def build_plans_text(snapshot: dict, product: dict) -> str:
    resolved = snapshot["resolved"]
    lines = [
        "💳 <b>Тарифы</b>",
        "",
        f"Сейчас у аккаунта активен доступ уровня <b>{html.quote(_plan_name(product, resolved.effective_plan_code))}</b>.",
        "Ниже можно быстро понять, какой режим подойдёт под текущую нагрузку и формат работы.",
    ]
    for code in ["start", "practice", "studio"]:
        plan = product.get("plans", {}).get(code, {})
        lines.extend([
            "",
            f"<b>{html.quote(plan.get('display_name', code.title()))}</b>",
            html.quote(plan.get("summary", "")),
            f"Подходит для: <b>{html.quote(plan.get('best_for', '—'))}</b>",
            f"Формат подключения: <b>{html.quote(plan.get('price_text', '—'))}</b>",
        ])
        for item in plan.get("included", []):
            lines.append(f"• {html.quote(item)}")
        if code == resolved.effective_plan_code:
            lines.append("• <b>Этот уровень доступа активен у вас сейчас</b>")
    return "\n".join(lines)


def build_included_text(snapshot: dict, product: dict) -> str:
    resolved = snapshot["resolved"]
    lines = [
        "🧩 <b>Что входит</b>",
        "",
        f"Ниже показано, что доступно на тарифе <b>{html.quote(_plan_name(product, resolved.effective_plan_code))}</b>.",
    ]
    for capability in CAPABILITY_ORDER:
        state = "✅" if resolved.capabilities.get(capability, False) else "🔒"
        lines.append(f"{state} {html.quote(capability_label(capability))}")
    lines.extend([
        "",
        f"Лимит активных учеников: <b>{html.quote(limit_label(resolved.limits.get('active_students')))}</b>",
        f"Лимит групп: <b>{html.quote(limit_label(resolved.limits.get('groups')))}</b>",
        f"Командные слоты: <b>{html.quote(limit_label(resolved.limits.get('team_members')))}</b>",
    ])
    return "\n".join(lines)


def build_subscription_text(snapshot: dict, product: dict) -> str:
    resolved = snapshot["resolved"]
    lines = [
        "🪪 <b>Подписка</b>",
        "",
        f"Аккаунт: <b>{html.quote(snapshot['account'].get('name', product.get('product_name', 'Аккаунт')))}</b>",
        f"Выбранный тариф: <b>{html.quote(_plan_name(product, resolved.plan_code))}</b>",
        f"Доступ сейчас: <b>{html.quote(_plan_name(product, resolved.effective_plan_code))}</b>",
        f"Статус: <b>{html.quote(TRIAL_STATUS_LABELS.get(resolved.effective_status, resolved.effective_status))}</b>",
        f"Пробный период до: <b>{html.quote(_format_datetime(resolved.trial_ends_at))}</b>",
        f"Оплачено до: <b>{html.quote(_format_datetime(resolved.paid_until))}</b>",
        "",
        "<b>Сейчас недоступно:</b>",
        *_locked_features_lines(snapshot),
    ]
    if snapshot.get("overrides"):
        lines.extend([
            "",
            "<b>Дополнительно включено:</b>",
            *[f"• {html.quote(capability_label(name))}" for name in sorted(snapshot["overrides"])],
        ])
    if resolved.effective_status == "trial":
        lines.extend([
            "",
            "Пока у аккаунта открыт пробный доступ. Если уже начинаете работать с клиентами, заранее подготовьте продление.",
        ])
    return "\n".join(lines)


def build_try_or_extend_text(snapshot: dict, product: dict) -> str:
    lines = [
        "🚀 <b>Оплата и продление</b>",
        "",
        html.quote(product.get("billing_policy", "")),
        "",
        "<b>Как подключить или продлить тариф:</b>",
    ]
    lines.extend([f"• {html.quote(item)}" for item in product.get("activation_steps", [])])
    lines.extend([
        "",
        f"Поддержка: <b>{html.quote(product.get('support_contact', '—'))}</b>",
        f"Ссылка: <b>{html.quote(product.get('public_website', '—'))}</b>",
        "После оплаты достаточно написать в поддержку название нужного тарифа и имя аккаунта. Автосписания нет: всё включается вручную и прозрачно.",
    ])
    resolved = snapshot["resolved"]
    lines.extend([
        "",
        f"Текущий статус: <b>{html.quote(TRIAL_STATUS_LABELS.get(resolved.effective_status, resolved.effective_status))}</b>",
        f"Пробный период до: <b>{html.quote(_format_datetime(resolved.trial_ends_at))}</b>",
        f"Оплачено до: <b>{html.quote(_format_datetime(resolved.paid_until))}</b>",
    ])
    return "\n".join(lines)


def build_paywall_text(feature_name: str, snapshot: dict, product: dict) -> str:
    resolved = snapshot["resolved"]
    return "\n".join([
        f"🔒 <b>{html.quote(feature_name)} недоступно на текущем плане</b>",
        "",
        f"Сейчас у аккаунта доступ уровня <b>{html.quote(_plan_name(product, resolved.effective_plan_code))}</b>.",
        "Это нормальное ограничение по тарифу, а не ошибка бота.",
        "Откройте тарифы и подписку, чтобы сравнить планы и включить апгрейд вручную без автосписания.",
    ])


def build_billing_admin_text(snapshot: dict, product: dict) -> str:
    resolved = snapshot["resolved"]
    lines = [
        "🧾 <b>Управление тарифом</b>",
        "",
        "Здесь можно вручную продлить доступ и включить отдельные функции.",
        f"Выбранный тариф: <b>{html.quote(_plan_name(product, resolved.plan_code))}</b>",
        f"Доступ сейчас: <b>{html.quote(_plan_name(product, resolved.effective_plan_code))}</b>",
        f"Статус: <b>{html.quote(TRIAL_STATUS_LABELS.get(resolved.effective_status, resolved.effective_status))}</b>",
        f"Пробный период до: <b>{html.quote(_format_datetime(resolved.trial_ends_at))}</b>",
        f"Оплачено до: <b>{html.quote(_format_datetime(resolved.paid_until))}</b>",
        "",
        "<b>Что можно сделать:</b>",
        "• смена плана и продление на фиксированный срок",
        "• продление пробного периода",
        "• отключение пробного периода",
        "• точечное включение отдельных функций",
    ]
    return "\n".join(lines)


def build_owner_onboarding_text(snapshot: dict, product: dict) -> str:
    resolved = snapshot["resolved"]
    return "\n".join([
        f"✅ Вы вошли в <b>{html.quote(product.get('product_name', 'TutorScalebot'))}</b> как <b>владелец</b>.",
        "",
        f"Сейчас для аккаунта активен <b>{html.quote(TRIAL_STATUS_LABELS.get(resolved.effective_status, resolved.effective_status))}</b>.",
        f"Доступ: <b>{html.quote(_plan_name(product, resolved.effective_plan_code))}</b> до <b>{html.quote(_format_datetime(resolved.trial_ends_at if resolved.is_trial_active else resolved.paid_until))}</b>.",
        "",
        "<b>Что сделать сейчас:</b>",
        "1. Откройте быстрый запуск и заполните оформление, контакты и реквизиты.",
        "2. Добавьте первого ученика и первое занятие.",
        "3. Проверьте тариф, пробный период и доступные функции.",
        "4. Calendar можно подключить сразу или позже, когда будет удобно.",
    ])


def build_owner_setup_status(ui_snapshot: dict, analytics: dict, *, calendar_connected: bool) -> dict[str, bool]:
    resolved_ui = resolve_ui_payload(ui_snapshot)
    branding = resolved_ui.get("branding") or {}
    contacts = resolved_ui.get("contacts") or {}
    requisites = resolved_ui.get("requisites") or {}

    has_branding = bool((branding.get("display_name") or "").strip())
    has_contacts = any((contacts.get(key) or "").strip() for key in ["phone", "telegram", "booking_url", "vk_call", "google_meet"])
    has_rates = bool(requisites.get("rates"))
    has_payment_method = any((requisites.get(key) or "").strip() for key in ["card", "sbp", "usdt_trc20"])
    has_students = int(analytics.get("active_students", 0)) > 0
    has_lessons = int(analytics.get("lessons_next_7_days", 0)) > 0
    return {
        "branding": has_branding,
        "contacts": has_contacts,
        "requisites": has_rates and has_payment_method,
        "students": has_students,
        "lessons": has_lessons,
        "calendar": calendar_connected,
    }


def owner_setup_missing_labels(status: dict[str, bool]) -> list[str]:
    labels = {
        "branding": "оформление",
        "contacts": "контакты",
        "requisites": "реквизиты",
        "students": "первого ученика",
        "lessons": "первое занятие",
    }
    return [label for key, label in labels.items() if not status.get(key)]


def owner_setup_needs_attention(status: dict[str, bool]) -> bool:
    return any(not status.get(key) for key in ["branding", "contacts", "requisites", "students", "lessons"])


def build_owner_setup_text(ui_snapshot: dict, analytics: dict, billing_snapshot: dict, *, calendar_connected: bool) -> str:
    billing = billing_snapshot["resolved"]
    status = build_owner_setup_status(ui_snapshot, analytics, calendar_connected=calendar_connected)

    def marker(value: bool, pending: str = "Нужно заполнить", ready: str = "Готово") -> str:
        return f"{'✅' if value else '◻️'} {ready if value else pending}"

    lines = [
        "🚀 <b>Быстрый запуск аккаунта</b>",
        "",
        "Пройдите этот короткий список, чтобы аккаунт уже можно было использовать в работе и показывать клиентам.",
        "",
        f"1. Оформление: {marker(status['branding'], 'Добавить название и тональность')}",
        f"2. Контакты: {marker(status['contacts'], 'Указать хотя бы один способ связи и ссылку')}",
        f"3. Реквизиты: {marker(status['requisites'], 'Добавить ставки и способ оплаты')}",
        f"4. Первый ученик: {marker(status['students'], 'Добавить первого ученика')}",
        f"5. Первое занятие: {marker(status['lessons'], 'Поставить первое занятие')}",
        f"6. Google Calendar: {'✅ Подключён или готов к работе' if status['calendar'] else '◻️ Можно подключить позже'}",
        "",
        f"Пробный период: <b>{html.quote(TRIAL_STATUS_LABELS.get(billing.effective_status, billing.effective_status))}</b>",
        f"Текущий доступ: <b>{html.quote(_plan_name(billing_snapshot['product'], billing.effective_plan_code))}</b>",
        "",
        "Как только пункты 1-5 закрыты, бот уже можно полноценно использовать в ежедневной работе.",
    ]
    return "\n".join(lines)


def build_analytics_text(snapshot: dict, analytics: dict, product: dict) -> str:
    resolved = snapshot["resolved"]
    lines = [
        "📈 <b>Аналитика</b>",
        "",
        f"План доступа: <b>{html.quote(_plan_name(product, resolved.effective_plan_code))}</b>",
        f"Активных учеников: <b>{analytics.get('active_students', 0)}</b>",
        f"Активных родителей: <b>{analytics.get('active_parents', 0)}</b>",
        f"Групп: <b>{analytics.get('active_groups', 0)}</b>",
        f"Уроков на 7 дней: <b>{analytics.get('lessons_next_7_days', 0)}</b>",
        f"Без ближайших уроков: <b>{analytics.get('students_without_upcoming_lessons', 0)}</b>",
    ]
    if resolved.capabilities.get("analytics_plus"):
        lines.extend([
            "",
            "<b>Расширенная аналитика:</b>",
            f"Оплат за 30 дней: <b>{analytics.get('payments_last_30_days', 0)}</b>",
            f"Выручка за 30 дней: <b>{analytics.get('revenue_last_30_days', 0)}</b>",
            f"Очных учеников: <b>{analytics.get('offline_students', 0)}</b>",
            f"Правил Calendar alias: <b>{analytics.get('calendar_alias_rules', 0)}</b>",
        ])
    else:
        lines.extend([
            "",
            "Расширенные показатели по выручке и деталям работы доступны на плане Studio.",
        ])
    return "\n".join(lines)


def build_groups_text(groups: list[dict]) -> str:
    if not groups:
        return (
            "👥 <b>Группы</b>\n\n"
            "Список групп пока пуст.\n"
            "Создайте первую группу, когда понадобится вести несколько учеников вместе."
        )

    lines = [
        "👥 <b>Группы</b>",
        "",
        f"Активных групп: <b>{len(groups)}</b>",
    ]
    for group in groups:
        lines.extend([
            "",
            f"• <b>{html.quote(group['name'])}</b>",
            f"  Участников: <b>{group.get('student_count', 0)}</b>",
        ])
        if group.get("description"):
            lines.append(f"  {html.quote(group['description'])}")
    return "\n".join(lines)


def build_group_detail_text(group: dict, members: list[dict]) -> str:
    lines = [
        f"👥 <b>{html.quote(group['name'])}</b>",
        "",
        html.quote(group.get("description") or "Без описания."),
        "",
        f"Участников: <b>{len(members)}</b>",
    ]
    if members:
        lines.append("")
        for member in members:
            lines.append(f"• {html.quote(member['full_name'])}")
    else:
        lines.extend(["", "Пока никто не добавлен."])
    return "\n".join(lines)


def build_invites_text(account: dict, invites: list[dict], bot_username: str | None = None) -> str:
    lines = [
        "🔗 <b>Приглашения</b>",
        "",
        f"Аккаунт: <b>{html.quote(account.get('name', '—'))}</b>",
        "Здесь можно создавать временные ссылки для команды.",
    ]
    if not invites:
        lines.extend([
            "",
            "Активных приглашений пока нет.",
            "Ниже можно сразу создать ссылку для менеджера или ассистента.",
        ])
        return "\n".join(lines)

    for invite in invites:
        role_label = workspace_role_label(invite.get("role"))
        link = build_invite_start_link(bot_username, invite["token"])
        lines.extend([
            "",
            f"<b>{html.quote(role_label)}</b> · ссылка #{invite['id']}",
            f"Истекает: <b>{html.quote(_format_datetime(invite.get('expires_at')))}</b>",
            f"Статус: <b>{html.quote(invite.get('status', 'active'))}</b>",
        ])
        if invite.get("label"):
            lines.append(f"Метка: <b>{html.quote(invite['label'])}</b>")
        lines.append(f"Ссылка входа: <code>{html.quote(link)}</code>")
    return "\n".join(lines)


def build_team_text(account: dict, members: list[dict], current_role: str | None = None) -> str:
    lines = [
        "👥 <b>Команда</b>",
        "",
        f"Аккаунт: <b>{html.quote(account.get('name', '—'))}</b>",
    ]
    if current_role:
        lines.append(f"Ваш доступ: <b>{html.quote(workspace_role_label(current_role))}</b>")
    if not members:
        lines.extend([
            "",
            "Пока в команде только вы. Пригласите менеджера или ассистента.",
        ])
        return "\n".join(lines)

    lines.extend([
        "",
        f"Участников: <b>{len(members)}</b>",
    ])
    for member in members:
        display_name = member.get("display_name") or member.get("username") or str(member.get("telegram_id") or "—")
        username = member.get("username")
        suffix = f" · @{html.quote(username)}" if username else ""
        lines.append(
            f"• <b>{html.quote(display_name)}</b> — {html.quote(workspace_role_label(member.get('role')))}{suffix}"
        )
    lines.extend([
        "",
        "Владелец управляет тарифом и составом команды. Менеджер помогает с операционной работой. Ассистент подключается по приглашению.",
    ])
    return "\n".join(lines)


def build_partition_text(partition: dict) -> str:
    lines = [
        "🧱 <b>Проверка данных</b>",
        "",
        "✅ Основные таблицы привязаны к аккаунтам." if partition.get("healthy") else "⚠️ Есть строки без привязки к аккаунту.",
        f"Строк без `account_id`: <b>{int(partition.get('null_account_rows', 0))}</b>",
    ]
    for table_name, stats in partition.get("tables", {}).items():
        lines.append(
            "• "
            f"{html.quote(table_name)}: "
            f"account={int(stats.get('account_rows', 0))}, "
            f"other={int(stats.get('other_account_rows', 0))}, "
            f"null={int(stats.get('null_account_rows', 0))}"
        )
    return "\n".join(lines)


def build_identity_split_text(snapshot: dict) -> str:
    return "\n".join([
        "🪪 <b>Связи пользователей</b>",
        "",
        "✅ Основные связи по пользователям в порядке." if snapshot.get("ready") else "⚠️ Есть записи без привязки пользователя.",
        f"Профилей Telegram: <b>{int(snapshot.get('total_global_identities', 0))}</b>",
        f"Пользователей с привязкой: <b>{int(snapshot.get('linked_users', 0))}</b>",
        f"Участников в аккаунтах: <b>{int(snapshot.get('total_memberships', 0))}</b>",
        f"Пользователей без привязки: <b>{int(snapshot.get('users_missing_identity', 0))}</b>",
        f"Участников без привязки: <b>{int(snapshot.get('account_users_missing_identity', 0))}</b>",
    ])


def build_domain_user_refs_text(snapshot: dict) -> str:
    lines = [
        "🔗 <b>Внутренние ссылки</b>",
        "",
        "✅ Основные таблицы уже заполнены новыми связями." if snapshot.get("ready") else "⚠️ Есть записи, где новые связи ещё не заполнены.",
        f"Незаполненных ссылок: <b>{int(snapshot.get('total_missing', 0))}</b>",
    ]
    for key, count in snapshot.get("missing", {}).items():
        lines.append(f"• {html.quote(key)}: <b>{int(count)}</b>")
    return "\n".join(lines)


def build_support_text(snapshot: dict, product: dict) -> str:
    account = snapshot.get("account") or {}
    billing = snapshot.get("billing") or {}
    resolved = billing.get("resolved")
    owner_user = snapshot.get("owner_user") or {}
    analytics = snapshot.get("analytics") or {}
    partition = snapshot.get("partition") or {}
    identity_split = snapshot.get("identity_split") or {}
    domain_user_refs = snapshot.get("domain_user_refs") or {}
    identity_workspace = snapshot.get("identity_workspace") or {}
    identity = identity_workspace.get("identity") or {}
    memberships = identity_workspace.get("memberships") or []

    lines = [
        "🆘 <b>Служебная сводка</b>",
        "",
        f"Аккаунт: <b>{html.quote(account.get('name', product.get('product_name', '—')))}</b>",
        f"ID аккаунта: <b>{html.quote(str(account.get('id', '—')))}</b>",
        f"Адрес: <b>{html.quote(account.get('slug', '—'))}</b>",
        f"Статус: <b>{html.quote(account.get('status', '—'))}</b>",
        f"Владелец: <b>{html.quote(owner_user.get('full_name', '—'))}</b>",
        f"Участников: <b>{int(snapshot.get('active_members', 0))}</b>",
        f"Активных приглашений: <b>{int(snapshot.get('active_invites_count', 0))}</b>",
        f"Контакт поддержки: <b>{html.quote(product.get('support_contact', '—'))}</b>",
    ]
    if resolved:
        lines.extend([
            "",
            "<b>Доступ и срок</b>",
            f"Выбранный тариф: <b>{html.quote(_plan_name(product, resolved.plan_code))}</b>",
            f"Доступ сейчас: <b>{html.quote(_plan_name(product, resolved.effective_plan_code))}</b>",
            f"Статус: <b>{html.quote(TRIAL_STATUS_LABELS.get(resolved.effective_status, resolved.effective_status))}</b>",
            f"Пробный период до: <b>{html.quote(_format_datetime(resolved.trial_ends_at))}</b>",
            f"Оплачено до: <b>{html.quote(_format_datetime(resolved.paid_until))}</b>",
        ])
    if identity:
        identity_name = identity.get("full_name") or ("@" + identity["username"] if identity.get("username") else "—")
        lines.extend([
            "",
            "<b>Профиль оператора</b>",
            f"Профиль: <b>{html.quote(identity_name)}</b>",
            f"Telegram ID: <b>{html.quote(str(identity.get('telegram_id', '—')))}</b>",
            f"Последний активный аккаунт: <b>{html.quote(str(identity.get('last_active_account_id', '—')))}</b>",
            f"Доступно аккаунтов: <b>{len(memberships)}</b>",
        ])
        for membership in memberships:
            current_suffix = " · текущий" if membership.get("account_id") == account.get("id") else ""
            lines.append(
                f"• {html.quote(membership.get('account_name', 'Аккаунт'))} — "
                f"{html.quote(workspace_role_label(membership.get('role')))}{current_suffix}"
            )
    lines.extend([
        "",
        "<b>Операционная сводка</b>",
        f"Активных учеников: <b>{int(analytics.get('active_students', 0))}</b>",
        f"Активных родителей: <b>{int(analytics.get('active_parents', 0))}</b>",
        f"Групп: <b>{int(analytics.get('active_groups', 0))}</b>",
        f"Уроков на 7 дней: <b>{int(analytics.get('lessons_next_7_days', 0))}</b>",
        "",
        build_identity_split_text(identity_split),
        "",
        build_domain_user_refs_text(domain_user_refs),
        "",
        build_partition_text(partition),
    ])
    return "\n".join(lines)


def _value_or_dash(value) -> str:
    text = str(value or "").strip()
    return html.quote(text) if text else "—"


def build_ui_hub_text(snapshot: dict) -> str:
    resolved = resolve_ui_payload(snapshot)
    account = (snapshot.get("account") or {}) if isinstance(snapshot, dict) else {}
    draft_version = snapshot.get("draft_version", 1) if isinstance(snapshot, dict) else 1
    published_version = snapshot.get("published_version", 1) if isinstance(snapshot, dict) else 1
    contacts = resolved.get("contacts") or {}
    requisites = resolved.get("requisites") or {}
    menu = resolved.get("menu") or {}
    has_branding = bool((resolved.get("branding") or {}).get("display_name"))
    has_contacts = any((contacts.get(key) or "").strip() for key in ["phone", "telegram", "booking_url", "vk_call", "google_meet"])
    has_requisites = bool(requisites.get("rates")) and any((requisites.get(key) or "").strip() for key in ["card", "sbp", "usdt_trc20"])
    menu_items = sum(len(items or []) for items in menu.values())
    return "\n".join([
        "🎛 <b>Оформление и экраны</b>",
        "",
        f"Аккаунт: <b>{html.quote(account.get('name', resolved.get('branding', {}).get('display_name', 'Аккаунт')))}</b>",
        f"Черновик: <b>v{draft_version}</b>",
        f"Опубликовано: <b>v{published_version}</b>",
        "",
        f"• Оформление: <b>{'готово' if has_branding else 'нужно проверить'}</b>",
        f"• Контакты: <b>{'заполнены' if has_contacts else 'неполные'}</b>",
        f"• Реквизиты: <b>{'заполнены' if has_requisites else 'неполные'}</b>",
        f"• Пунктов меню в черновике: <b>{menu_items}</b>",
        "",
        "Изменения сначала попадают в черновик. После проверки их можно опубликовать без перезапуска бота.",
    ])


def build_ui_branding_text(snapshot: dict) -> str:
    resolved = resolve_ui_payload(snapshot)
    branding = resolved.get("branding") or {}
    return "\n".join([
        "🎨 <b>Оформление</b>",
        "",
        f"Название аккаунта: <b>{_value_or_dash(branding.get('display_name'))}</b>",
        f"Тональность: <b>{_value_or_dash(branding.get('tone'))}</b>",
        "",
        "Название используется в приветствии и справке. Тональность влияет на автоматические формулировки и клиентские экраны.",
    ])


def build_ui_copy_text(snapshot: dict) -> str:
    resolved = resolve_ui_payload(snapshot)
    copy = resolved.get("copy") or {}
    return "\n".join([
        "🧾 <b>Клиентские тексты</b>",
        "",
        f"Старт: <b>{_value_or_dash(copy.get('start_intro'))}</b>",
        f"Справка: <b>{_value_or_dash(copy.get('help_intro'))}</b>",
        f"Контакты: <b>{_value_or_dash(copy.get('contacts_intro'))}</b>",
        f"Реквизиты: <b>{_value_or_dash(copy.get('requisites_footer'))}</b>",
        f"После регистрации: <b>{_value_or_dash(copy.get('post_registration_intro'))}</b>",
        "",
        "Это короткие вводные блоки для клиентских экранов. Тарифные и биллинговые тексты здесь не редактируются.",
    ])


def build_ui_contacts_text(snapshot: dict) -> str:
    resolved = resolve_ui_payload(snapshot)
    contacts = resolved.get("contacts") or {}
    return "\n".join([
        "📞 <b>Контакты</b>",
        "",
        f"Телефон: <b>{_value_or_dash(contacts.get('phone'))}</b>",
        f"Telegram: <b>{_value_or_dash(contacts.get('telegram'))}</b>",
        f"Discord: <b>{_value_or_dash(contacts.get('discord'))}</b>",
        f"Адрес: <b>{_value_or_dash(contacts.get('address'))}</b>",
        "",
        f"Запись: <b>{_value_or_dash(contacts.get('booking_url'))}</b>",
        f"Расписание: <b>{_value_or_dash(contacts.get('calendar_url'))}</b>",
        f"Сайт: <b>{_value_or_dash(contacts.get('project_site_url'))}</b>",
        f"Тест уровня: <b>{_value_or_dash(contacts.get('level_test_url'))}</b>",
        f"Отзывы: <b>{_value_or_dash(contacts.get('review_url'))}</b>",
        f"VK Звонок: <b>{_value_or_dash(contacts.get('vk_call'))}</b>",
        f"Google Meet: <b>{_value_or_dash(contacts.get('google_meet'))}</b>",
    ])


def build_ui_requisites_text(snapshot: dict) -> str:
    resolved = resolve_ui_payload(snapshot)
    requisites = resolved.get("requisites") or {}
    rates = requisites.get("rates") or []
    rate_lines = [f"• {html.quote(str(item))}" for item in rates] or ["—"]
    return "\n".join([
        "💳 <b>Реквизиты и ставки</b>",
        "",
        "Ставки:",
        *rate_lines,
        "",
        f"Карта: <b>{_value_or_dash(requisites.get('card'))}</b>",
        f"СБП: <b>{_value_or_dash(requisites.get('sbp'))}</b>",
        f"Банки СБП: <b>{_value_or_dash(requisites.get('sbp_banks'))}</b>",
        f"USDT TRC-20: <b>{_value_or_dash(requisites.get('usdt_trc20'))}</b>",
    ])


def build_ui_menu_sections_text(snapshot: dict) -> str:
    resolved = resolve_ui_payload(snapshot)
    lines = [
        "📚 <b>Главное меню</b>",
        "",
        "Здесь можно скрывать кнопки, менять порядок, переименовывать их и добавлять свои ссылки.",
    ]
    menu = resolved.get("menu") or {}
    for section, label in UI_MENU_SECTION_LABELS.items():
        enabled_count = len([item for item in menu.get(section, []) if item.get("enabled", True)])
        total_count = len(menu.get(section, []))
        lines.append(f"• {html.quote(label)}: <b>{enabled_count}</b> из <b>{total_count}</b>")
    return "\n".join(lines)


def build_ui_menu_section_text(snapshot: dict, section: str) -> str:
    resolved = resolve_ui_payload(snapshot)
    lines = [
        f"📚 <b>{html.quote(UI_MENU_SECTION_LABELS.get(section, section))}</b>",
        "",
        "Кнопки идут сверху вниз в том порядке, в котором их видит пользователь.",
    ]
    for item in get_menu_entries(resolved, section):
        state = "вкл" if item.get("enabled", True) else "выкл"
        lines.append(
            f"• <b>{html.quote(item.get('label', item.get('id', 'кнопка')))}</b> "
            f"· {html.quote(item.get('kind', 'callback'))} · {state}"
        )
    return "\n".join(lines)


def build_ui_preview_text(snapshot: dict, role: str) -> str:
    resolved = resolve_ui_payload(snapshot)
    copy = resolved.get("copy") or {}
    label = UI_PREVIEW_ROLES.get(role, role)
    intro = copy.get("start_intro") or "Добро пожаловать!"
    return "\n".join([
        f"👁 <b>Предпросмотр: {html.quote(label)}</b>",
        "",
        html.quote(intro),
        "",
        "Ниже показано черновое главное меню для выбранной роли. После публикации именно его увидит клиент.",
    ])


def build_ui_history_text(snapshot: dict, versions: list[dict]) -> str:
    account = (snapshot.get("account") or {}) if isinstance(snapshot, dict) else {}
    lines = [
        "🕘 <b>История публикаций</b>",
        "",
        f"Аккаунт: <b>{html.quote(account.get('name', 'Аккаунт'))}</b>",
    ]
    if not versions:
        lines.extend([
            "",
            "Публикаций пока нет. После первой публикации здесь появятся версии для отката.",
        ])
        return "\n".join(lines)
    lines.append("")
    for version in versions[:8]:
        published_at = version.get("published_at")
        stamp = published_at.strftime("%d.%m.%Y %H:%M") if published_at else "без даты"
        lines.append(f"• Версия <b>{version['version']}</b> · {html.quote(stamp)}")
    lines.extend([
        "",
        "Нажмите на нужную версию ниже, чтобы быстро откатить опубликованный интерфейс к этому состоянию.",
    ])
    return "\n".join(lines)
