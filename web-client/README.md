# Web Client MVP

React + Vite клиент для базового сценария:

- регистрация и вход (`/register`, `/token`)
- просмотр списка файлов (`/files`)
- скачивание файла через presigned URL (`/files/download-link`)
- создание и просмотр своих тикетов (`/tickets`)

## Запуск

```bash
npm install
npm run dev
```

По умолчанию API ожидается на `http://127.0.0.1:8000`.

Можно переопределить через `.env` в этой папке:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000
```
