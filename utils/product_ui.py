from __future__ import annotations

from datetime import datetime

from aiogram import html

from utils.capabilities import CAPABILITY_ORDER, TRIAL_STATUS_LABELS, capability_label, limit_label
from utils.workspace import build_invite_start_link, workspace_role_label


def _format_datetime(value: datetime | None) -> str:
    return value.strftime("%d.%m.%Y %H:%M") if value else "—"


def _plan_name(product: dict, plan_code: str) -> str:
    return product.get("plans", {}).get(plan_code, {}).get("display_name", plan_code.title())


def _locked_features_lines(snapshot: dict) -> list[str]:
    resolved = snapshot["resolved"]
    if not resolved.locked_capabilities:
        return ["Все ключевые premium-возможности уже доступны."]
    return [f"• {html.quote(capability_label(item))}" for item in resolved.locked_capabilities]


def build_workspace_menu_text(account: dict | None, account_user: dict | None, base_text: str) -> str:
    account_name = (account or {}).get("name")
    role_label = workspace_role_label((account_user or {}).get("role"))
    lines = []
    if account_name:
        lines.extend([
            f"🏢 <b>{html.quote(account_name)}</b>",
            f"Роль в workspace: <b>{html.quote(role_label)}</b>",
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
        "🧭 <b>Workspace Selector</b>",
        "",
    ]
    if identity:
        display_name = identity.get("full_name") or ("@" + identity["username"] if identity.get("username") else None)
        if display_name:
            lines.append(f"Identity: <b>{html.quote(display_name)}</b>")
        if identity.get("last_active_account_id"):
            lines.append(f"Last active account: <b>{html.quote(str(identity['last_active_account_id']))}</b>")
        lines.append("")

    if not memberships:
        lines.append("У этой identity пока нет активных workspace-membership.")
        return "\n".join(lines)

    lines.append(f"Доступно workspace: <b>{len(memberships)}</b>")
    for membership in memberships:
        marker = "✅" if membership.get("account_id") == current_account_id else "•"
        lines.append(
            f"{marker} <b>{html.quote(membership.get('account_name', 'Workspace'))}</b> "
            f"· {html.quote(workspace_role_label(membership.get('role')))}"
        )
    lines.extend([
        "",
        "Выберите workspace ниже, чтобы закрепить его как активный для следующих экранов и команд.",
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
        lines.extend(["", "<b>Почему продукт платный:</b>"])
        lines.extend([f"• {html.quote(item)}" for item in why_paid])
    if snapshot:
        resolved = snapshot["resolved"]
        lines.extend([
            "",
            "<b>Текущий статус аккаунта:</b>",
            f"• План по настройке: <b>{html.quote(_plan_name(product, resolved.plan_code))}</b>",
            f"• Доступ сейчас: <b>{html.quote(_plan_name(product, resolved.effective_plan_code))}</b>",
            f"• Статус: <b>{html.quote(TRIAL_STATUS_LABELS.get(resolved.effective_status, resolved.effective_status))}</b>",
        ])
    return "\n".join(lines)


def build_plans_text(snapshot: dict, product: dict) -> str:
    resolved = snapshot["resolved"]
    lines = [
        "💳 <b>Тарифы</b>",
        "",
        f"Сейчас у аккаунта активен доступ уровня <b>{html.quote(_plan_name(product, resolved.effective_plan_code))}</b>.",
    ]
    for code in ["start", "practice", "studio"]:
        plan = product.get("plans", {}).get(code, {})
        lines.extend([
            "",
            f"<b>{html.quote(plan.get('display_name', code.title()))}</b>",
            html.quote(plan.get("summary", "")),
            f"Подходит для: <b>{html.quote(plan.get('best_for', '—'))}</b>",
            f"Позиционирование: <b>{html.quote(plan.get('price_text', '—'))}</b>",
        ])
        for item in plan.get("included", []):
            lines.append(f"• {html.quote(item)}")
    return "\n".join(lines)


def build_included_text(snapshot: dict, product: dict) -> str:
    resolved = snapshot["resolved"]
    lines = [
        "🧩 <b>Что входит</b>",
        "",
        f"Ниже — capability-матрица для плана <b>{html.quote(_plan_name(product, resolved.effective_plan_code))}</b>.",
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
        f"План по настройке: <b>{html.quote(_plan_name(product, resolved.plan_code))}</b>",
        f"Фактический доступ: <b>{html.quote(_plan_name(product, resolved.effective_plan_code))}</b>",
        f"Статус: <b>{html.quote(TRIAL_STATUS_LABELS.get(resolved.effective_status, resolved.effective_status))}</b>",
        f"Trial до: <b>{html.quote(_format_datetime(resolved.trial_ends_at))}</b>",
        f"Оплачено до: <b>{html.quote(_format_datetime(resolved.paid_until))}</b>",
        "",
        "<b>Сейчас заблокировано:</b>",
        *_locked_features_lines(snapshot),
    ]
    if snapshot.get("overrides"):
        lines.extend([
            "",
            "<b>Точечные overrides:</b>",
            *[f"• {html.quote(capability_label(name))}" for name in sorted(snapshot["overrides"])],
        ])
    return "\n".join(lines)


def build_try_or_extend_text(snapshot: dict, product: dict) -> str:
    lines = [
        "🚀 <b>Попробовать / Продлить</b>",
        "",
        html.quote(product.get("billing_policy", "")),
        "",
        "<b>Как это работает:</b>",
    ]
    lines.extend([f"• {html.quote(item)}" for item in product.get("activation_steps", [])])
    lines.extend([
        "",
        f"Поддержка: <b>{html.quote(product.get('support_contact', '—'))}</b>",
        f"Сайт: <b>{html.quote(product.get('public_website', '—'))}</b>",
    ])
    resolved = snapshot["resolved"]
    lines.extend([
        "",
        f"Текущий статус: <b>{html.quote(TRIAL_STATUS_LABELS.get(resolved.effective_status, resolved.effective_status))}</b>",
        f"Trial до: <b>{html.quote(_format_datetime(resolved.trial_ends_at))}</b>",
        f"Оплачено до: <b>{html.quote(_format_datetime(resolved.paid_until))}</b>",
    ])
    return "\n".join(lines)


def build_paywall_text(feature_name: str, snapshot: dict, product: dict) -> str:
    resolved = snapshot["resolved"]
    return "\n".join([
        f"🔒 <b>{html.quote(feature_name)} недоступно на текущем плане</b>",
        "",
        f"Сейчас у аккаунта доступ уровня <b>{html.quote(_plan_name(product, resolved.effective_plan_code))}</b>.",
        "Откройте тарифы и подписку, чтобы увидеть, что входит в апгрейд и как активировать его вручную.",
    ])


def build_billing_admin_text(snapshot: dict, product: dict) -> str:
    resolved = snapshot["resolved"]
    lines = [
        "🧾 <b>Billing v1</b>",
        "",
        "Ручное управление подпиской для текущего account.",
        f"План в карточке: <b>{html.quote(_plan_name(product, resolved.plan_code))}</b>",
        f"Фактический доступ: <b>{html.quote(_plan_name(product, resolved.effective_plan_code))}</b>",
        f"Статус: <b>{html.quote(TRIAL_STATUS_LABELS.get(resolved.effective_status, resolved.effective_status))}</b>",
        f"Trial до: <b>{html.quote(_format_datetime(resolved.trial_ends_at))}</b>",
        f"Paid until: <b>{html.quote(_format_datetime(resolved.paid_until))}</b>",
        "",
        "<b>Админ-действия ниже:</b>",
        "• смена плана и продление на фиксированный срок",
        "• продление trial",
        "• отключение trial",
        "• включение точечных feature overrides",
    ]
    return "\n".join(lines)


def build_owner_onboarding_text(snapshot: dict, product: dict) -> str:
    resolved = snapshot["resolved"]
    return "\n".join([
        f"✅ Вы вошли в <b>{html.quote(product.get('product_name', 'TutorScalebot'))}</b> как <b>owner</b>.",
        "",
        f"Сейчас для аккаунта активен <b>{html.quote(TRIAL_STATUS_LABELS.get(resolved.effective_status, resolved.effective_status))}</b>.",
        f"Доступ: <b>{html.quote(_plan_name(product, resolved.effective_plan_code))}</b> до <b>{html.quote(_format_datetime(resolved.trial_ends_at if resolved.is_trial_active else resolved.paid_until))}</b>.",
        "",
        "<b>Быстрый onboarding:</b>",
        "1. Подключите Google Calendar.",
        "2. Добавьте учеников и расписание.",
        "3. Проверьте тариф, trial и заблокированные функции.",
        "4. При необходимости откройте billing-экран и активируйте нужный план.",
    ])


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
            "Расширенные метрики по выручке и операционным деталям доступны на плане Studio.",
        ])
    return "\n".join(lines)


def build_groups_text(groups: list[dict]) -> str:
    if not groups:
        return (
            "👥 <b>Группы</b>\n\n"
            "Пока ни одной группы нет.\n"
            "Создайте первую группу, чтобы собрать мини-школьный контур внутри продукта."
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
        "🔗 <b>Invite Flows</b>",
        "",
        f"Workspace: <b>{html.quote(account.get('name', '—'))}</b>",
        "Создавайте временные инвайты для будущих участников account-aware workspace.",
    ]
    if not invites:
        lines.extend([
            "",
            "Активных инвайтов пока нет.",
            "Ниже можно сразу выпустить invite для менеджера или ассистента.",
        ])
        return "\n".join(lines)

    for invite in invites:
        role_label = workspace_role_label(invite.get("role"))
        link = build_invite_start_link(bot_username, invite["token"])
        lines.extend([
            "",
            f"<b>{html.quote(role_label)}</b> · invite #{invite['id']}",
            f"Истекает: <b>{html.quote(_format_datetime(invite.get('expires_at')))}</b>",
            f"Статус: <b>{html.quote(invite.get('status', 'active'))}</b>",
        ])
        if invite.get("label"):
            lines.append(f"Метка: <b>{html.quote(invite['label'])}</b>")
        lines.append(f"Старт: <code>{html.quote(link)}</code>")
    return "\n".join(lines)


def build_team_text(account: dict, members: list[dict], current_role: str | None = None) -> str:
    lines = [
        "👥 <b>Команда workspace</b>",
        "",
        f"Workspace: <b>{html.quote(account.get('name', '—'))}</b>",
    ]
    if current_role:
        lines.append(f"Ваш текущий доступ: <b>{html.quote(workspace_role_label(current_role))}</b>")
    if not members:
        lines.extend([
            "",
            "В команде пока только базовый owner-контур. Добавьте менеджера или ассистента через инвайты.",
        ])
        return "\n".join(lines)

    lines.extend([
        "",
        f"Активных membership: <b>{len(members)}</b>",
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
        "Контур mini-school уже готов: owner управляет billing и составом команды, manager ведёт операционный слой, assistant подключается через workspace-aware invite flow.",
    ])
    return "\n".join(lines)


def build_partition_text(partition: dict) -> str:
    lines = [
        "🧱 <b>Data Partitioning</b>",
        "",
        "✅ Все partitioned-таблицы account-aware." if partition.get("healthy") else "⚠️ Есть строки без account context.",
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
        "🪪 <b>Identity Split Readiness</b>",
        "",
        "✅ База готова к следующему migration step." if snapshot.get("ready") else "⚠️ Есть записи без identity link.",
        f"Global identities: <b>{int(snapshot.get('total_global_identities', 0))}</b>",
        f"Users c identity link: <b>{int(snapshot.get('linked_users', 0))}</b>",
        f"Memberships в account: <b>{int(snapshot.get('total_memberships', 0))}</b>",
        f"Users без identity: <b>{int(snapshot.get('users_missing_identity', 0))}</b>",
        f"Memberships без identity: <b>{int(snapshot.get('account_users_missing_identity', 0))}</b>",
    ])


def build_domain_user_refs_text(snapshot: dict) -> str:
    lines = [
        "🔗 <b>Surrogate User Refs</b>",
        "",
        "✅ Доменные таблицы заполнены новыми `*_user_id` ссылками." if snapshot.get("ready") else "⚠️ Остались legacy-only строки без `*_user_id`.",
        f"Всего незаполненных ссылок: <b>{int(snapshot.get('total_missing', 0))}</b>",
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
        "🆘 <b>Support Tooling</b>",
        "",
        f"Workspace: <b>{html.quote(account.get('name', product.get('product_name', '—')))}</b>",
        f"Account ID: <b>{html.quote(str(account.get('id', '—')))}</b>",
        f"Slug: <b>{html.quote(account.get('slug', '—'))}</b>",
        f"Статус account: <b>{html.quote(account.get('status', '—'))}</b>",
        f"Owner: <b>{html.quote(owner_user.get('full_name', '—'))}</b>",
        f"Участников workspace: <b>{int(snapshot.get('active_members', 0))}</b>",
        f"Активных invite-ссылок: <b>{int(snapshot.get('active_invites_count', 0))}</b>",
        f"Поддержка продукта: <b>{html.quote(product.get('support_contact', '—'))}</b>",
    ]
    if resolved:
        lines.extend([
            "",
            "<b>Billing snapshot</b>",
            f"План: <b>{html.quote(_plan_name(product, resolved.plan_code))}</b>",
            f"Фактический доступ: <b>{html.quote(_plan_name(product, resolved.effective_plan_code))}</b>",
            f"Статус: <b>{html.quote(TRIAL_STATUS_LABELS.get(resolved.effective_status, resolved.effective_status))}</b>",
            f"Trial до: <b>{html.quote(_format_datetime(resolved.trial_ends_at))}</b>",
            f"Paid until: <b>{html.quote(_format_datetime(resolved.paid_until))}</b>",
        ])
    if identity:
        identity_name = identity.get("full_name") or ("@" + identity["username"] if identity.get("username") else "—")
        lines.extend([
            "",
            "<b>Identity across workspaces</b>",
            f"Identity: <b>{html.quote(identity_name)}</b>",
            f"Telegram ID: <b>{html.quote(str(identity.get('telegram_id', '—')))}</b>",
            f"Last active account: <b>{html.quote(str(identity.get('last_active_account_id', '—')))}</b>",
            f"Workspace memberships: <b>{len(memberships)}</b>",
        ])
        for membership in memberships:
            current_suffix = " · current" if membership.get("account_id") == account.get("id") else ""
            lines.append(
                f"• {html.quote(membership.get('account_name', 'Workspace'))} — "
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
