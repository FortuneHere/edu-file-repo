# Backend MVP: запуск и smoke-приемка

Этот документ фиксирует повторяемый сценарий приемки backend:

1. Регистрация пользователя
2. Логин и получение JWT
3. Загрузка PDF администратором
4. Просмотр списка файлов
5. Получение presigned-ссылки на скачивание

## 1) Переменные окружения

Создайте `.env` в каталоге `backend`:

```env
DATABASE_URL=sqlite:///./app.db

SECRET_KEY=change-this-secret
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440

YANDEX_ENDPOINT=https://storage.yandexcloud.net
YANDEX_ACCESS_KEY_ID=your-access-key
YANDEX_SECRET_ACCESS_KEY=your-secret-key
YANDEX_BUCKET_NAME=your-bucket
```

Минимально для запуска API нужны `DATABASE_URL` и JWT-переменные.  
Для upload/download-link дополнительно обязательны все `YANDEX_*`.

## 2) Быстрый запуск

Из каталога `backend`:

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

API поднимется на `http://127.0.0.1:8000`, Swagger: `http://127.0.0.1:8000/docs`.

## 3) Smoke-сценарий приемки (manual)

### Шаг A. Регистрация

`POST /register`

```json
{
  "email": "smoke-user@example.com",
  "password": "StrongPass123!"
}
```

Ожидаемо: `201`, `{"message":"Пользователь создан"}`.

### Шаг B. Логин

`POST /token`

```json
{
  "email": "smoke-user@example.com",
  "password": "StrongPass123!"
}
```

Ожидаемо: `200`, поле `access_token`.

### Шаг C. Повышение пользователя до admin

Для приемки upload-части нужен администратор. В Python shell/скрипте:

```python
from database import SessionLocal
from utils import make_admin

db = SessionLocal()
make_admin("smoke-user@example.com", db)
db.close()
```

### Шаг D. Авторизация в Swagger

В Swagger нажать **Authorize** и вставить:

`Bearer <access_token>`

### Шаг E. Загрузка PDF

`POST /upload` с `multipart/form-data`:

- `folder`: `root`
- `file`: любой `.pdf`

Ожидаемо: `200`, ответ содержит `s3_key`, например `root/smoke.pdf`.

### Шаг F. Список файлов

`GET /files?folder=root`

Ожидаемо: `200`, в выдаче есть загруженный файл и его `s3_key`.

### Шаг G. Presigned download link

`GET /files/download-link?s3_key=root/smoke.pdf&expires_in=1200`

Ожидаемо: `200`, ответ содержит:

- `download_url`
- `filename`
- `expires_in`

## 4) Автоматический smoke-тест

Запуск из каталога `backend`:

```bash
pytest -q tests/test_backend_e2e_smoke.py
```

Тест `test_backend_full_smoke_scenario` проверяет весь приемочный поток:

- register -> token
- запрет upload для обычного пользователя (`403`)
- повышение роли до `admin`
- upload PDF
- files list
- download-link через авторизованный запрос
