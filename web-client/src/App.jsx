import { useState } from "react";
import "./App.css";
import {
  createTicket,
  getDownloadLink,
  getFiles,
  getTickets,
  loginUser,
  registerUser,
} from "./api";

const TOKEN_KEY = "edu_repo_token";

function App() {
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY) || "");
  const [statusMessage, setStatusMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  const [folder, setFolder] = useState("root");
  const [files, setFiles] = useState([]);
  const [filesLoading, setFilesLoading] = useState(false);

  const [tickets, setTickets] = useState([]);
  const [ticketTitle, setTicketTitle] = useState("");
  const [ticketDescription, setTicketDescription] = useState("");
  const [ticketsLoading, setTicketsLoading] = useState(false);

  const isAuthenticated = Boolean(token);

  async function refreshFiles(currentFolder) {
    setFilesLoading(true);
    setErrorMessage("");

    try {
      const data = await getFiles(currentFolder);
      setFiles(Array.isArray(data) ? data : []);
    } catch (error) {
      setErrorMessage(error.message || "Не удалось загрузить список файлов");
    } finally {
      setFilesLoading(false);
    }
  }

  async function refreshTickets(authToken = token) {
    if (!authToken) {
      return;
    }

    setTicketsLoading(true);
    setErrorMessage("");

    try {
      const data = await getTickets(authToken);
      setTickets(Array.isArray(data) ? data : []);
    } catch (error) {
      setErrorMessage(error.message || "Не удалось загрузить тикеты");
    } finally {
      setTicketsLoading(false);
    }
  }

  async function handleAuthSubmit(event) {
    event.preventDefault();
    setErrorMessage("");
    setStatusMessage("");

    try {
      if (mode === "register") {
        await registerUser({ email, password });
        setStatusMessage("Регистрация успешна. Теперь выполните вход.");
        setMode("login");
        setPassword("");
        return;
      }

      const data = await loginUser({ email, password });
      localStorage.setItem(TOKEN_KEY, data.access_token);
      setToken(data.access_token);
      setStatusMessage("Вход выполнен.");
      setPassword("");
      await refreshFiles(folder);
      await refreshTickets(data.access_token);
    } catch (error) {
      setErrorMessage(error.message || "Ошибка аутентификации");
    }
  }

  function handleLogout() {
    localStorage.removeItem(TOKEN_KEY);
    setToken("");
    setTickets([]);
    setStatusMessage("Вы вышли из аккаунта.");
    setErrorMessage("");
  }

  async function handleDownload(file) {
    if (!token) {
      setErrorMessage("Для скачивания файла нужен вход в аккаунт.");
      return;
    }

    setErrorMessage("");
    setStatusMessage("");

    try {
      const data = await getDownloadLink(file.s3_key, token);
      window.open(data.download_url, "_blank", "noopener,noreferrer");
      setStatusMessage(`Ссылка для ${file.filename} создана (вкладка открыта).`);
    } catch (error) {
      setErrorMessage(error.message || "Не удалось получить ссылку для скачивания");
    }
  }

  async function handleTicketSubmit(event) {
    event.preventDefault();
    if (!token) {
      setErrorMessage("Сначала выполните вход.");
      return;
    }

    setErrorMessage("");
    setStatusMessage("");

    try {
      await createTicket(
        {
          title: ticketTitle,
          description: ticketDescription || null,
        },
        token,
      );
      setStatusMessage("Тикет создан.");
      setTicketTitle("");
      setTicketDescription("");
      await refreshTickets();
    } catch (error) {
      setErrorMessage(error.message || "Не удалось создать тикет");
    }
  }

  return (
    <main className="app">
      <header className="card">
        <h1>Edu File Repository</h1>
        <p className="muted">MVP веб-клиент: auth, файлы, скачивание и тикеты.</p>
      </header>

      <section className="card">
        <div className="row">
          <h2>Аутентификация</h2>
          {isAuthenticated ? (
            <button type="button" onClick={handleLogout}>
              Выйти
            </button>
          ) : null}
        </div>

        {!isAuthenticated ? (
          <form className="form" onSubmit={handleAuthSubmit}>
            <div className="tabs">
              <button
                type="button"
                className={mode === "login" ? "active" : ""}
                onClick={() => setMode("login")}
              >
                Вход
              </button>
              <button
                type="button"
                className={mode === "register" ? "active" : ""}
                onClick={() => setMode("register")}
              >
                Регистрация
              </button>
            </div>

            <label>
              Email
              <input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
              />
            </label>

            <label>
              Пароль
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </label>

            <button type="submit">
              {mode === "register" ? "Создать аккаунт" : "Войти"}
            </button>
          </form>
        ) : (
          <p className="muted">Вы авторизованы. Теперь доступно создание тикетов и скачивание.</p>
        )}
      </section>

      <section className="card">
        <div className="row">
          <h2>Файлы</h2>
          <form
            className="inline-form"
            onSubmit={(event) => {
              event.preventDefault();
              void refreshFiles(folder);
            }}
          >
            <input
              value={folder}
              onChange={(event) => setFolder(event.target.value)}
              placeholder="root"
            />
            <button type="submit">Обновить</button>
          </form>
        </div>

        {filesLoading ? <p className="muted">Загрузка файлов...</p> : null}

        {!filesLoading && files.length === 0 ? (
          <p className="muted">В папке нет файлов.</p>
        ) : null}

        <ul className="list">
          {files.map((file) => (
            <li key={file.id} className="list-item">
              <div>
                <strong>{file.filename}</strong>
                <p className="muted">Папка: {file.folder_path}</p>
              </div>
              <button type="button" onClick={() => handleDownload(file)}>
                Скачать
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section className="card">
        <h2>Тикеты</h2>

        <form className="form" onSubmit={handleTicketSubmit}>
          <label>
            Тема
            <input
              value={ticketTitle}
              onChange={(event) => setTicketTitle(event.target.value)}
              placeholder="Например: Нужна новая методичка"
              required
              disabled={!isAuthenticated}
            />
          </label>

          <label>
            Описание
            <textarea
              value={ticketDescription}
              onChange={(event) => setTicketDescription(event.target.value)}
              rows={4}
              placeholder="Опишите запрос"
              disabled={!isAuthenticated}
            />
          </label>

          <button type="submit" disabled={!isAuthenticated}>
            Создать тикет
          </button>
        </form>

        {ticketsLoading ? <p className="muted">Загрузка тикетов...</p> : null}

        {!ticketsLoading && isAuthenticated && tickets.length === 0 ? (
          <p className="muted">У вас пока нет тикетов.</p>
        ) : null}

        <ul className="list">
          {tickets.map((ticket) => (
            <li key={ticket.id} className="ticket-item">
              <div>
                <strong>{ticket.title}</strong>
                <p className="muted">{ticket.description || "Без описания"}</p>
              </div>
              <span className="badge">{ticket.status}</span>
            </li>
          ))}
        </ul>
      </section>

      {statusMessage ? <p className="status">{statusMessage}</p> : null}
      {errorMessage ? <p className="error">{errorMessage}</p> : null}
    </main>
  );
}

export default App;
