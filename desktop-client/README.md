# Desktop Admin MVP

Electron-клиент для администратора, который выполняет:

1. Авторизацию через backend `POST /token`
2. Загрузку PDF через защищенный endpoint `POST /upload`

## Требования

- Node.js 18+
- Запущенный backend API (`http://127.0.0.1:8000` по умолчанию)
- Пользователь с ролью `admin`

## Запуск

```bash
cd desktop-client
npm install --save-dev electron
npm start
```

## Smoke-check

1. Введите `Backend URL`, `Email`, `Password`.
2. Нажмите "Войти и получить токен".
3. Выберите `folder` и PDF-файл.
4. Нажмите "Загрузить PDF".
5. Убедитесь, что в логе есть успешный ответ с `s3_key`.
