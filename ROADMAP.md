# TutorScalebot Roadmap

## Current Baseline

К апрелю 2026 в проект уже заложены:

- коммерческая продуктовая оболочка: тарифы, trial, подписка, paywall, billing v1;
- account-aware schema для ключевых сущностей;
- capability resolver и feature gating по планам;
- группы, analytics-lite, segment broadcasts groundwork;
- invite flows, support tooling, account-aware routing и partition health checks;
- изолированный runtime-контур для `TutorScalebot`: отдельный deploy root, `.env`, service/watch unit и `PGSCHEMA`;
- multi-workspace UX: selector, last-active workspace memory, invite switch flow, support snapshot across accounts;
- mini-school growth layer: manager/assistant memberships, team screen, membership-aware admin gates;
- подготовка к SaaS-переходу без немедленного усложнения billing и RBAC.

## Phase 5. Identity Split And Multi-Workspace Readiness

Цель: уйти от текущего ограничения `users.telegram_id UNIQUE` и подготовить реальный shared SaaS-бот.

- разделить `global_identities` и `account_members`;
- перевести связи с `users(telegram_id)` на account-scoped membership keys;
- подготовить миграцию для multi-workspace membership одного Telegram-пользователя;
- ввести account selector / last-active workspace routing;
- добавить безопасные migration checks и rollback plan.

## Phase 6. Team Roles And Invite Maturity

Цель: превратить groundwork ролей в рабочий mini-school режим.

- owner / manager / assistant permissions matrix;
- экран приглашённых участников и статусы invite lifecycle;
- revoke / resend / expire flows;
- отдельные меню и доступы для team roles;
- staff onboarding внутри workspace.

## Phase 7. SaaS Control Plane

Цель: подготовить единый бот к поддержке многих клиентов.

- support/admin console для поиска account по owner, slug, plan, status;
- account lifecycle actions: suspend, reactivate, rename, transfer owner;
- service-side account routing и diagnostic tools;
- partition audits across all accounts;
- backup/export tooling per workspace.

## Phase 8. Billing v2

Цель: перейти от manual activation к полуавтоматическому, а затем автоматическому биллингу.

- invoice workflow и подтверждение оплаты без ручного SQL/операций;
- subscription history, billing notes, plan change log;
- grace period, dunning, scheduled expirations;
- checkout integration как отдельный слой, не смешанный с capability core;
- entitlement sync tests и finance-safe audit trail.

## Phase 9. Product Growth

Цель: усилить коммерческую ценность для репетиторов и мини-школ.

- полноценные groups journeys: групповые уроки, групповые ДЗ, attendance;
- analytics-plus: retention, revenue trends, load, unpaid risk;
- richer broadcasts: saved segments, campaign history, templates;
- onboarding wizard для новых owners;
- public-facing conversion copy и upgrade nudges внутри продукта.

## Phase 10. Reliability And Operations

Цель: сделать продукт устойчивым для SaaS-эксплуатации.

- structured audit logs по критичным admin actions;
- background jobs isolation per account;
- rate limiting и abuse protection;
- SLO/alerting dashboards;
- smoke tests для deploy и pre-release regression suite.

## Recommended Immediate Next Sprint

Если идти самым сильным порядком после текущего этапа, следующий спринт лучше посвятить:

1. углубить permission matrix для owner / manager / assistant по чувствительным операциям;
2. собрать control-plane support console поверх нескольких account и планов;
3. довести workspace onboarding для staff и mini-school сценария;
4. готовить staging smoke-flow общего SaaS-бота на отдельной operational schema.
