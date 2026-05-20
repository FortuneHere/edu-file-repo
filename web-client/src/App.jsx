import { useEffect, useMemo, useState } from "react";
import "./App.css";
import {
  createTicket,
  deleteMyAccount,
  getFolderTree,
  getDownloadLink,
  getFiles,
  getTickets,
  loginUser,
  registerUser,
  uploadTicketAttachments,
} from "./api";

const TOKEN_KEY = "edu_repo_token";
const MAX_TICKETS_PER_USER = 5;
const MAX_ATTACHMENTS_PER_TICKET = 10;

function FolderTree({ node, selectedPath, onSelect }) {
  if (!node) {
    return null;
  }

  return (
    <ul className="tree-list">
      <li>
        <button
          type="button"
          className={selectedPath === node.path ? "tree-node active" : "tree-node"}
          onClick={() => onSelect(node.path)}
        >
          {node.name}
        </button>
        {Array.isArray(node.children) && node.children.length > 0 ? (
          <div className="tree-children">
            {node.children.map((child) => (
              <FolderTree
                key={child.path}
                node={child}
                selectedPath={selectedPath}
                onSelect={onSelect}
              />
            ))}
          </div>
        ) : null}
      </li>
    </ul>
  );
}

function App() {
  const [mode, setMode] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY) || "");
  const [statusMessage, setStatusMessage] = useState("");
  const [errorMessage, setErrorMessage] = useState("");

  const [folderTree, setFolderTree] = useState(null);
  const [selectedFolder, setSelectedFolder] = useState("root");
  const [files, setFiles] = useState([]);
  const [filesLoading, setFilesLoading] = useState(false);

  const [tickets, setTickets] = useState([]);
  const [ticketTitle, setTicketTitle] = useState("");
  const [ticketDescription, setTicketDescription] = useState("");
  const [ticketFiles, setTicketFiles] = useState([]);
  const [ticketsLoading, setTicketsLoading] = useState(false);

  const isAuthenticated = Boolean(token);
  const canCreateTicket = tickets.length < MAX_TICKETS_PER_USER;
  const ticketFilesLabel = useMemo(
    () => `${ticketFiles.length}/${MAX_ATTACHMENTS_PER_TICKET} файлов выбрано`,
    [ticketFiles.length],
  );

  async function refreshFolderTree() {
    try {
      const tree = await getFolderTree();
      setFolderTree(tree);
      setSelectedFolder((previousFolder) => {
        if (!tree) {
          return "root";
        }
        if (
          previousFolder === "root" &&
          tree.path === "root" &&
          Array.isArray(tree.children) &&
          tree.children.length > 0
        ) {
          return tree.children[0].path;
        }
        return previousFolder;
      });
    } catch (error) {
      setErrorMessage(error.message || "Не удалось загрузить дерево папок");
    }
  }

  async function refreshFiles(currentFolder, authToken = token) {
    if (!authToken) {
      setFiles([]);
      return;
    }
    setFilesLoading(true);
    setErrorMessage("");

    try {
      const data = await getFiles(currentFolder, authToken);
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
      await refreshFolderTree();
      await refreshFiles(selectedFolder, data.access_token);
      await refreshTickets(data.access_token);
    } catch (error) {
      setErrorMessage(error.message || "Ошибка аутентификации");
    }
  }

  function handleLogout() {
    localStorage.removeItem(TOKEN_KEY);
    setToken("");
    setTickets([]);
    setFiles([]);
    setTicketFiles([]);
    setStatusMessage("Вы вышли из аккаунта.");
    setErrorMessage("");
  }

  async function handleDeleteAccount() {
    if (!token) {
      return;
    }
    const shouldDelete = window.confirm("Удалить ваш аккаунт? Это действие необратимо.");
    if (!shouldDelete) {
      return;
    }
    setErrorMessage("");
    setStatusMessage("");
    try {
      await deleteMyAccount(token);
      localStorage.removeItem(TOKEN_KEY);
      setToken("");
      setTickets([]);
      setFiles([]);
      setTicketFiles([]);
      setStatusMessage("Аккаунт удален.");
    } catch (error) {
      setErrorMessage(error.message || "Не удалось удалить аккаунт");
    }
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

    if (!canCreateTicket) {
      setErrorMessage(`Достигнут лимит: максимум ${MAX_TICKETS_PER_USER} тикетов.`);
      return;
    }

    if (ticketFiles.length > MAX_ATTACHMENTS_PER_TICKET) {
      setErrorMessage(`Можно прикрепить не более ${MAX_ATTACHMENTS_PER_TICKET} файлов.`);
      return;
    }

    try {
      const createdTicket = await createTicket(
        {
          title: ticketTitle,
          description: ticketDescription || null,
        },
        token,
      );
      if (ticketFiles.length > 0) {
        await uploadTicketAttachments(createdTicket.id, ticketFiles, token);
      }
      setStatusMessage("Тикет создан.");
      setTicketTitle("");
      setTicketDescription("");
      setTicketFiles([]);
      await refreshTickets();
    } catch (error) {
      setErrorMessage(error.message || "Не удалось создать тикет");
    }
  }

  useEffect(() => {
    void refreshFolderTree();
  }, []);

  useEffect(() => {
    if (!token) {
      return;
    }
    void refreshFiles(selectedFolder);
  }, [selectedFolder, token]);

  useEffect(() => {
    if (!token) {
      setTickets([]);
      return;
    }
    void refreshTickets(token);
  }, [token]);

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
            <div className="row">
              <button type="button" onClick={handleLogout}>
                Выйти
              </button>
              <button type="button" onClick={handleDeleteAccount}>
                Удалить аккаунт
              </button>
            </div>
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
          <button type="button" onClick={() => void refreshFolderTree()}>
            Обновить дерево
          </button>
        </div>
        <div className="row files-layout">
          <div className="folder-panel">
            <p className="muted">Выберите папку</p>
            {folderTree?.path === "root" ? (
              folderTree.children?.length ? (
                folderTree.children.map((child) => (
                  <FolderTree
                    key={child.path}
                    node={child}
                    selectedPath={selectedFolder}
                    onSelect={setSelectedFolder}
                  />
                ))
              ) : (
                <p className="muted">Нет доступных папок.</p>
              )
            ) : (
              <FolderTree node={folderTree} selectedPath={selectedFolder} onSelect={setSelectedFolder} />
            )}
          </div>
          <div className="file-panel">
            <div className="row">
              <p className="muted">Текущая папка: {selectedFolder}</p>
              <button type="button" onClick={() => void refreshFiles(selectedFolder)}>
                Обновить файлы
              </button>
            </div>

            {filesLoading ? <p className="muted">Загрузка файлов...</p> : null}

            {!filesLoading && files.length === 0 ? (
              <p className="muted">В выбранной папке нет файлов.</p>
            ) : null}

            <ul className="list">
              {files.map((file) => (
                <li key={file.id} className="list-item">
                  <div>
                    <strong>{file.filename}</strong>
                    {file.summary ? <p className="muted">{file.summary}</p> : null}
                  </div>
                  <button type="button" onClick={() => handleDownload(file)}>
                    Скачать
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <section className="card">
        <h2>Тикеты</h2>
        <p className="muted">
          Лимит: до {MAX_TICKETS_PER_USER} тикетов на пользователя и до {MAX_ATTACHMENTS_PER_TICKET} файлов
          на тикет.
        </p>

        <form className="form" onSubmit={handleTicketSubmit}>
          <label>
            Тема
            <input
              value={ticketTitle}
              onChange={(event) => setTicketTitle(event.target.value)}
              placeholder="Например: Нужна новая методичка"
              required
              disabled={!isAuthenticated || !canCreateTicket}
            />
          </label>

          <label>
            Описание
            <textarea
              value={ticketDescription}
              onChange={(event) => setTicketDescription(event.target.value)}
              rows={4}
              placeholder="Опишите запрос"
              disabled={!isAuthenticated || !canCreateTicket}
            />
          </label>

          <label>
            Вложения к тикету
            <input
              type="file"
              multiple
              onChange={(event) => setTicketFiles(Array.from(event.target.files || []))}
              disabled={!isAuthenticated || !canCreateTicket}
            />
            <span className="muted">{ticketFilesLabel}</span>
          </label>

          <button type="submit" disabled={!isAuthenticated || !canCreateTicket}>
            Создать тикет
          </button>
        </form>

        {!canCreateTicket && isAuthenticated ? (
          <p className="error">Достигнут лимит: максимум {MAX_TICKETS_PER_USER} тикетов.</p>
        ) : null}

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
                <p className="muted">Вложений: {ticket.attachments?.length || 0}</p>
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
