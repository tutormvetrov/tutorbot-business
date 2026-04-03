# Identity Split Migration Draft

## Goal

Подготовить `TutorScalebot` к режиму общего SaaS-бота, где один Telegram-пользователь может состоять в нескольких workspace, не ломая текущие account-aware потоки.

## Current Transitional State

Уже внедрено:

- таблица `global_identities` как глобальный слой идентичности;
- `users.identity_id` как link между account-scoped user projection и глобальной identity;
- `account_users.identity_id` как link между membership и глобальной identity;
- backfill и support snapshot, показывающие readiness к следующему migration step.

После текущего раунда уже сняты ключевые legacy-ограничения:

- `users.telegram_id` больше не держится как глобальный `UNIQUE`;
- `users` upsertится по `(account_id, telegram_id)`;
- last-active workspace хранится в `global_identities.last_active_account_id`;
- базовый multi-workspace UX уже есть: selector, invite switch flow, support snapshot across accounts.

Оставшийся transition-risk теперь смещён не в identity split, а в дальнейшее развитие team permissions и control-plane для общего SaaS.

## Target State

Нужно прийти к модели:

- `global_identities`
  - один Telegram identity на весь SaaS
- `account_users`
  - membership внутри конкретного account
  - ключ: `id`
  - связь: `identity_id -> global_identities.id`
- `users`
  - account-scoped operational projection
  - больше не является глобальным identity-хранилищем
- доменные таблицы
  - ссылаются либо на `account_users.id`, либо на account-scoped `users.id`
  - не полагаются на глобальную уникальность `telegram_id`

## Recommended Migration Order

### Step 1. Finish Identity Coverage

- довести `identity_id` до 100% покрытие в `users`;
- довести `identity_id` до 100% покрытие в `account_users`;
- включить health gate: новые записи без identity не допускаются.

### Step 2. Introduce Stable Membership Keys In Domain Data

- добавить новые FK-колонки:
  - `lessons.student_user_id`
  - `homework.student_user_id`
  - `payments.student_user_id`
  - `payments.payer_user_id`
  - `calendar_student_links.student_user_id`
  - `student_parent.student_user_id`
  - `student_parent.parent_user_id`
- backfill через `(account_id, telegram_id) -> users.id`;
- перевести read-path на новые surrogate keys, сохраняя legacy поля временно.

### Step 3. Make `users` Account-Scoped For Real

- создать `UNIQUE (account_id, telegram_id)` для `users`;
- перевести все ссылки с `users(telegram_id)` на:
  - `users.id`, либо
  - `(account_id, telegram_id)` composite reference, где это действительно оправдано;
- убрать зависимость FK от глобальной уникальности `telegram_id`.

### Step 4. Remove Legacy Single-Workspace Assumption

- убрать `UNIQUE` с `users.telegram_id`;
- обновить `ON CONFLICT (telegram_id)` на account-scoped upserts;
- разрешить одному `global_identity` иметь несколько `users` rows по разным account.

Статус: выполнено.

### Step 5. Multi-Workspace UX

- account selector при нескольких membership;
- last-active workspace memory;
- invite accept flow с выбором “переключиться / остаться / открыть новый workspace”;
- support tools для просмотра membership одного identity across accounts.

Статус: базовый слой выполнен.

## Risk Notes

- Самый рискованный шаг не создание `global_identities`, а отказ от `users.telegram_id UNIQUE`.
- До полного перевода FK нельзя безопасно разрешать multi-workspace projection rows.
- Поэтому текущая стадия сознательно подготовительная: она снижает риск и даёт observability, но не включает финальный switch prematurely.

## Done Criteria For The Next Implementation Round

Следующий раунд теперь логично считать завершённым, когда:

1. owner/manager/assistant матрица будет разведена по чувствительным действиям глубже, чем общий admin gate;
2. invite/team flows получат полноценный account selector после accept и staff onboarding copy;
3. появится control-plane слой для support/tooling над несколькими account;
4. smoke-flow одного identity в двух account будет прогнан уже на живой staging-схеме `tutorscalebot`.
