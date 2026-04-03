# TutorScalebot

`TutorScalebot` — отдельный коммерческий Telegram-бот для репетиторов и мини-школ.
Ветка и репозиторий развиваются как самостоятельный продукт: с тарифами, trial, ручной активацией подписки, capability-gating и архитектурой, готовой к дальнейшему переходу от “один инстанс на клиента” к общему SaaS.

Имя systemd unit и логическое имя сервиса теперь `tutorscalebot`.
Рекомендуемый runtime root изолирован от первого бота: `/srv/tutorscalebot`.
Отдельная operational schema по умолчанию: `PGSCHEMA=tutorscalebot`.

## Что уже есть

- product config c branding, trial policy и текстами тарифов
- `accounts`, `account_users`, `subscriptions`, `plans`, feature overrides
- account-aware schema для основных сущностей
- тарифные экраны, экран подписки и экран trial / upgrade
- ручной billing flow из админки
- capability gating для premium-функций
- groundwork под группы и analytics

## Быстрый старт

1. Скопируйте `.env.example` в `.env`.
2. Заполните переменные окружения.
3. Настройте customer-facing файлы:
   `data/product_config.json` — название продукта, support, trial и тарифные тексты.
   `data/teacher_info.json` — контакты, ссылки, реквизиты и ссылки на календарь.
4. Создайте виртуальное окружение и установите зависимости:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

5. Запустите бота:

```bash
.venv/bin/python app.py
```

## Переменные окружения

- `BOT_TOKEN` — токен Telegram-бота.
- `ADMIN_ID` — Telegram ID owner/product-admin в текущем v1-инстансе.
- `PGUSER`, `PGPASSWORD`, `DATABASE`, `PGHOST`, `PGPORT` — PostgreSQL.
- `PGSCHEMA` — отдельная schema внутри PostgreSQL для TutorScalebot.
- `GOOGLE_CALENDAR_ID` — календарь для sync.
- `GOOGLE_CREDENTIALS_FILE` — путь к service account JSON.
- `TUTORBOT_DATA_DIR` — директория для runtime-data, если нужно вынести её из репозитория.
- `FSM_STORAGE_FILE` — путь к JSON storage для FSM.
- `TUTORBOT_SERVICE_NAME` — имя systemd-сервиса для healthcheck/watch-скриптов.
  По умолчанию: `tutorscalebot`.
- `TUTORBOT_SYSTEMD_SCOPE` — `system` или `user` для watch/health tooling.

## Структура проекта

- `app.py` — точка входа, middleware и scheduler.
- `handlers/` — user/admin/product flows.
- `keyboards/` — inline keyboards, включая product/billing UI.
- `utils/db_api/` — schema, query mixins и business-layer для account/subscription logic.
- `utils/capabilities.py` — capability matrix и resolver по тарифам.
- `utils/product_ui.py` — product-facing и billing-facing тексты.
- `data/product_config.json` — branding и тарифные тексты.
- `data/teacher_info.json` — контакты и реквизиты.

## Тесты

Локальный прогон:

```bash
BOT_TOKEN=12345:TESTTOKEN ADMIN_ID=1 .venv/bin/python -m unittest discover -s tests -q
```

## Deploy

В репозитории лежат серверные артефакты:

- `deploy/tutorscalebot.service`
- `deploy/tutorscalebot-watch.service`
- `deploy/logrotate/tutorscalebot`
- `scripts/healthcheck.sh`
- `scripts/tutorbot_watch.py`

Рекомендуемый порядок:

1. Разверните проект в `/srv/tutorscalebot`.
2. Положите `.env` и credentials по нужным путям.
3. Скопируйте `deploy/tutorscalebot.service` в `/etc/systemd/system/tutorscalebot.service`.
4. При необходимости скопируйте `deploy/tutorscalebot-watch.service` в `/etc/systemd/system/tutorscalebot-watch.service`.
5. Скопируйте `deploy/logrotate/tutorscalebot` в `/etc/logrotate.d/tutorscalebot`.
6. Включите сервисы:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now tutorscalebot
sudo systemctl enable --now tutorscalebot-watch
```

Ручная проверка:

```bash
TUTORBOT_ROOT=/srv/tutorscalebot TUTORBOT_SERVICE_NAME=tutorscalebot ./scripts/healthcheck.sh
```

Для полной изоляции от первого бота не переиспользуйте `/srv/tutorbot`, его `.env` или `public` schema.
Поднимайте отдельный checkout, отдельный `.env`, отдельную `PGSCHEMA` и отдельные systemd unit'ы только для TutorScalebot.

## Примечание по v1

Billing в первой версии намеренно ручной: без checkout, без автопродления и без Stars.
Сильное ядро продукта продаётся через тарифы, trial, paywall и ручную активацию плана из админки.
