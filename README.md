# TutorBot

Telegram-бот для управления учебным процессом: регистрация учеников и родителей, расписание, домашние задания, оплаты, напоминания и админ-панель.

## Быстрый старт

1. Создайте и заполните `.env`.
2. Укажите сервисный аккаунт Google Calendar через `GOOGLE_CREDENTIALS_FILE`.
3. Заполните `data/teacher_info.json` своими контактами, ссылками и реквизитами.
4. Установите зависимости:

```bash
pip install -r requirements.txt
```

5. Запустите бота:

```bash
python app.py
```

## Переменные окружения

- `BOT_TOKEN` - токен Telegram-бота.
- `ADMIN_ID` - Telegram ID администратора.
- `PGUSER`, `PGPASSWORD`, `DATABASE`, `PGHOST`, `PGPORT` - параметры PostgreSQL.
- `GOOGLE_CALENDAR_ID` - ID календаря для синхронизации.
- `GOOGLE_CREDENTIALS_FILE` - путь к JSON credentials service account.

## Структура проекта

- `app.py` - точка входа и запуск планировщика.
- `handlers/` - обработчики сообщений и callback.
- `keyboards/` - inline-клавиатуры.
- `utils/` - работа с БД, календарём, текстом и scheduler.
- `data/` - конфигурация и вспомогательные JSON-файлы.

## Проверка

Для базовой проверки можно запустить:

```bash
python -m unittest discover -s tests
```

## Deploy

В репозитории лежат готовые артефакты для сервера:

- `deploy/tutorbot.service` - unit для `systemd`
- `deploy/logrotate/tutorbot` - конфиг ротации логов
- `scripts/healthcheck.sh` - проверка живости бота и свежести ops status
- `.env.example` - шаблон переменных окружения

Рекомендуемый порядок:

1. Скопируйте `.env.example` в `.env` и заполните значения.
2. Поместите Google credentials в путь из `GOOGLE_CREDENTIALS_FILE`.
3. Скопируйте `deploy/tutorbot.service` в `/etc/systemd/system/tutorbot.service`.
4. Скопируйте `deploy/logrotate/tutorbot` в `/etc/logrotate.d/tutorbot`.
5. Включите сервис:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now tutorbot
```

Проверку состояния можно запускать вручную:

```bash
TUTORBOT_ROOT=/srv/tutorbot ./scripts/healthcheck.sh
```

Healthcheck проверяет:

- запущен ли процесс бота или сервис `tutorbot`
- свежий ли `data/ops_status.json`
- не истекло ли время последнего обновления ops status
- не пуст ли `data/runtime_metrics.jsonl`, если файл уже создан
