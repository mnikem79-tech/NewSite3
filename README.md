# NewSite3

Интернет-магазин на Django с административной панелью, упакованный
в дистрибутив с автоустановщиком для развёртывания на чистом VPS.

## Стек

| Слой | Технология |
|---|---|
| Backend | Django 5.2 LTS + Django REST Framework |
| БД | PostgreSQL 14+ (`pg_trgm`, `unaccent`, `citext`) |
| Админка | Django Admin |
| Прод | gunicorn + systemd + nginx + certbot |
| Python | 3.10 – 3.13 |

## Структура

```
config/          настройки проекта (base / dev / prod) и корневые маршруты
apps/core/       абстрактные модели: TimeStampedModel, ActivatableModel
apps/accounts/   пользователь с логином по e-mail
requirements/    base.txt — прод, dev.txt — разработка
scripts/         backup_db.sh, restore_db.sh
deploy/          автоустановщик (следующий этап)
docs/            документация и журнал решений
tests/           тесты
```

## Разработка

```bash
cd /opt/newsite3
source .venv/bin/activate

python manage.py runserver 0.0.0.0:8000     # по умолчанию config.settings.dev
python manage.py makemigrations
python manage.py migrate
python manage.py createsuperuser
pytest
ruff check . && black --check .
```

Админка: `http://nail-srv:8000/admin/`
Healthcheck: `http://nail-srv:8000/healthz/`

## Конфигурация

Все параметры среды — в `/opt/newsite3/.env` (права `600`, в git не попадает).
Шаблон с перечнем переменных — `.env.example`.

| Переменная | Назначение |
|---|---|
| `DJANGO_SECRET_KEY` | ключ подписи, генерируется установщиком |
| `DJANGO_DEBUG` | `True` только на деве |
| `DJANGO_ALLOWED_HOSTS` | список доменов через запятую |
| `DATABASE_URL` | строка подключения к PostgreSQL |
| `EMAIL_BACKEND` | на деве — консольный |
| `DEFAULT_CURRENCY` | валюта магазина, по умолчанию RUB |

## Договорённости

- Деньги — только `Decimal(12,2)`, никаких `float`.
- Время в БД и приложении — UTC, локальное только при выводе.
- Миграции коммитятся в репозиторий: установщик их применяет, а не генерирует.
- Секреты и пароли — алфавитно-цифровые, ради переносимости между
  bash, systemd, cron и psql.
- `ATOMIC_REQUESTS = True`: каждый запрос в транзакции, заказ не сохранится
  наполовину.

Полный журнал решений — `docs/DECISIONS.md`.

## Лицензия

Не определена.
