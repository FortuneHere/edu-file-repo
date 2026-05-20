const loginForm = document.getElementById("loginForm");
const uploadForm = document.getElementById("uploadForm");
const createFolderForm = document.getElementById("createFolderForm");
const emailInput = document.getElementById("email");
const passwordInput = document.getElementById("password");
const newFolderPathInput = document.getElementById("newFolderPath");
const folderSelect = document.getElementById("folderSelect");
const pdfFileInput = document.getElementById("pdfFile");
const refreshFoldersBtn = document.getElementById("refreshFoldersBtn");
const refreshFilesBtn = document.getElementById("refreshFilesBtn");
const createFolderBtn = document.getElementById("createFolderBtn");
const deleteFolderBtn = document.getElementById("deleteFolderBtn");
const currentFolderLabel = document.getElementById("currentFolderLabel");
const filesList = document.getElementById("filesList");
const folderTree = document.getElementById("folderTree");
const refreshTicketsBtn = document.getElementById("refreshTicketsBtn");
const ticketsList = document.getElementById("ticketsList");
const refreshAnalyticsBtn = document.getElementById("refreshAnalyticsBtn");
const analyticsPeriodSelect = document.getElementById("analyticsPeriod");
const analyticsBox = document.getElementById("analyticsBox");
const loginBtn = document.getElementById("loginBtn");
const exitAppBtn = document.getElementById("exitAppBtn");
const uploadBtn = document.getElementById("uploadBtn");
const authState = document.getElementById("authState");
const logBox = document.getElementById("logBox");

let token = "";
let selectedFolder = "root";
let folderPaths = ["root"];
const API_BASE_URL = "http://127.0.0.1:8000";

folderSelect.disabled = true;
analyticsPeriodSelect.disabled = true;
renderFolderOptions();

function now() {
  return new Date().toLocaleTimeString();
}

function writeLog(message, type = "info") {
  const prefix = type === "error" ? "[ERROR]" : "[INFO]";
  logBox.textContent += `${now()} ${prefix} ${message}\n`;
  logBox.scrollTop = logBox.scrollHeight;
}

function normalizeBaseUrl() {
  return API_BASE_URL;
}

function updateFolderLabel() {
  currentFolderLabel.textContent = selectedFolder;
  deleteFolderBtn.disabled = !token || selectedFolder === "root";
}

function setAuthenticatedUI(isAuthenticated) {
  loginForm.classList.toggle("hidden", isAuthenticated);
  exitAppBtn.classList.toggle("hidden", !isAuthenticated);
}

function flattenTree(node, accumulator = []) {
  if (!node) {
    return accumulator;
  }
  accumulator.push(node.path);
  (node.children || []).forEach((child) => flattenTree(child, accumulator));
  return accumulator;
}

function stringifyTree(node, depth = 0, lines = []) {
  if (!node) {
    return lines;
  }
  lines.push(`${"  ".repeat(depth)}- ${node.name}`);
  (node.children || []).forEach((child) => stringifyTree(child, depth + 1, lines));
  return lines;
}

function renderFolderOptions() {
  folderSelect.innerHTML = "";
  folderPaths.forEach((path) => {
    const option = document.createElement("option");
    option.value = path;
    option.textContent = path;
    if (path === selectedFolder) {
      option.selected = true;
    }
    folderSelect.appendChild(option);
  });
  updateFolderLabel();
}

async function apiFetch(path, { method = "GET", body, auth = true } = {}) {
  const headers = {};
  if (auth && token) {
    headers.Authorization = `Bearer ${token}`;
  }
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }
  const response = await fetch(`${normalizeBaseUrl()}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined
  });
  if (!response.ok) {
    const detail = await readErrorMessage(response);
    throw new Error(`${method} ${path} failed (${response.status}): ${detail}`);
  }
  const contentType = response.headers.get("content-type") || "";
  return contentType.includes("application/json") ? response.json() : {};
}

function renderFiles(files) {
  filesList.innerHTML = "";
  if (!files.length) {
    const item = document.createElement("li");
    item.className = "list-item muted";
    item.textContent = "В выбранной папке нет файлов.";
    filesList.appendChild(item);
    return;
  }

  files.forEach((file) => {
    const item = document.createElement("li");
    item.className = "list-item";

    const topRow = document.createElement("div");
    topRow.className = "list-row";
    topRow.innerHTML = `<strong>${file.filename}</strong><span>${file.hidden ? "Скрыт" : "Виден"}</span>`;

    const summaryText = document.createElement("p");
    summaryText.className = "meta";
    summaryText.textContent = file.summary
      ? `Кратко: ${file.summary}`
      : "Краткое описание пока не сгенерировано.";

    const renameInput = document.createElement("input");
    renameInput.type = "text";
    renameInput.value = file.filename;

    const actions = document.createElement("div");
    actions.className = "actions";

    const renameBtn = document.createElement("button");
    renameBtn.type = "button";
    renameBtn.textContent = "Переименовать";
    renameBtn.addEventListener("click", async () => {
      const nextName = renameInput.value.trim();
      if (!nextName) {
        writeLog("Имя файла не может быть пустым", "error");
        return;
      }
      try {
        await apiFetch(`/files/${file.id}`, {
          method: "PATCH",
          body: { filename: nextName }
        });
        writeLog(`Файл ${file.filename} переименован в ${nextName}`);
        await refreshFiles();
      } catch (error) {
        writeLog(error.message, "error");
      }
    });

    const hiddenBtn = document.createElement("button");
    hiddenBtn.type = "button";
    hiddenBtn.textContent = file.hidden ? "Показать" : "Скрыть";
    hiddenBtn.addEventListener("click", async () => {
      try {
        await apiFetch(`/files/${file.id}`, {
          method: "PATCH",
          body: { hidden: !file.hidden }
        });
        writeLog(`Файл ${file.filename}: ${file.hidden ? "показан" : "скрыт"}`);
        await refreshFiles();
      } catch (error) {
        writeLog(error.message, "error");
      }
    });

    const downloadBtn = document.createElement("button");
    downloadBtn.type = "button";
    downloadBtn.textContent = "Скачать";
    downloadBtn.addEventListener("click", async () => {
      try {
        const data = await apiFetch(
          `/files/download-link?s3_key=${encodeURIComponent(file.s3_key)}`
        );
        window.open(data.download_url, "_blank", "noopener,noreferrer");
        writeLog(`Открыта ссылка для скачивания файла ${file.filename}`);
      } catch (error) {
        writeLog(error.message, "error");
      }
    });

    const deleteBtn = document.createElement("button");
    deleteBtn.type = "button";
    deleteBtn.textContent = "Удалить файл";
    deleteBtn.addEventListener("click", async () => {
      const shouldDelete = window.confirm(`Удалить файл ${file.filename}?`);
      if (!shouldDelete) {
        return;
      }
      try {
        await apiFetch(`/files/${file.id}`, { method: "DELETE" });
        writeLog(`Файл ${file.filename} удален`);
        await refreshFiles();
      } catch (error) {
        writeLog(error.message, "error");
      }
    });

    actions.appendChild(renameBtn);
    actions.appendChild(hiddenBtn);
    actions.appendChild(downloadBtn);
    actions.appendChild(deleteBtn);
    item.appendChild(topRow);
    item.appendChild(summaryText);
    item.appendChild(renameInput);
    item.appendChild(actions);
    filesList.appendChild(item);
  });
}

function renderTickets(tickets) {
  ticketsList.innerHTML = "";
  if (!tickets.length) {
    const item = document.createElement("li");
    item.className = "list-item muted";
    item.textContent = "Тикетов пока нет.";
    ticketsList.appendChild(item);
    return;
  }

  tickets.forEach((ticket) => {
    const item = document.createElement("li");
    item.className = "list-item";

    const topRow = document.createElement("div");
    topRow.className = "list-row";
    topRow.innerHTML = `<strong>${ticket.title}</strong><span>${ticket.status}</span>`;

    const description = document.createElement("p");
    description.className = "meta";
    description.textContent = ticket.description || "Без описания";

    const meta = document.createElement("p");
    meta.className = "meta";
    meta.textContent = `ID: ${ticket.id}, пользователь: ${ticket.user_email || "unknown"}, вложений: ${(ticket.attachments || []).length}`;

    const attachmentsHeader = document.createElement("p");
    attachmentsHeader.className = "meta";
    attachmentsHeader.textContent = "Вложения:";

    const attachmentsList = document.createElement("ul");
    attachmentsList.className = "attachments-list";
    if (!ticket.attachments || ticket.attachments.length === 0) {
      const noAttachment = document.createElement("li");
      noAttachment.className = "meta";
      noAttachment.textContent = "Нет вложений";
      attachmentsList.appendChild(noAttachment);
    } else {
      ticket.attachments.forEach((attachment) => {
        const attachmentItem = document.createElement("li");
        attachmentItem.className = "list-row";
        const name = document.createElement("span");
        name.textContent = attachment.filename;
        const downloadBtn = document.createElement("button");
        downloadBtn.type = "button";
        downloadBtn.textContent = "Скачать";
        downloadBtn.addEventListener("click", async () => {
          try {
            const link = await apiFetch(
              `/admin/tickets/${ticket.id}/attachments/${attachment.id}/download-link`
            );
            window.open(link.download_url, "_blank", "noopener,noreferrer");
            writeLog(`Открыта ссылка на скачивание вложения ${attachment.filename}`);
          } catch (error) {
            writeLog(error.message, "error");
          }
        });
        attachmentItem.appendChild(name);
        attachmentItem.appendChild(downloadBtn);
        attachmentsList.appendChild(attachmentItem);
      });
    }

    const actions = document.createElement("div");
    actions.className = "actions";
    const deleteBtn = document.createElement("button");
    deleteBtn.type = "button";
    deleteBtn.textContent = "Удалить тикет";
    deleteBtn.addEventListener("click", async () => {
      const shouldDelete = window.confirm(`Удалить тикет #${ticket.id}?`);
      if (!shouldDelete) {
        return;
      }
      try {
        await apiFetch(`/admin/tickets/${ticket.id}`, { method: "DELETE" });
        writeLog(`Тикет #${ticket.id} удален`);
        await refreshTickets();
      } catch (error) {
        writeLog(error.message, "error");
      }
    });
    actions.appendChild(deleteBtn);

    item.appendChild(topRow);
    item.appendChild(description);
    item.appendChild(meta);
    item.appendChild(attachmentsHeader);
    item.appendChild(attachmentsList);
    item.appendChild(actions);
    ticketsList.appendChild(item);
  });
}

async function refreshFolders() {
  try {
    const tree = await apiFetch("/folders/tree");
    folderPaths = flattenTree(tree, []);
    if (!folderPaths.includes(selectedFolder)) {
      selectedFolder = "root";
    }
    folderTree.textContent = stringifyTree(tree, 0, []).join("\n");
    folderTree.classList.remove("muted");
    renderFolderOptions();
  } catch (error) {
    writeLog(error.message, "error");
  }
}

async function refreshFiles() {
  try {
    const files = await apiFetch(
      `/files?folder=${encodeURIComponent(selectedFolder)}&include_hidden=true`
    );
    renderFiles(Array.isArray(files) ? files : []);
  } catch (error) {
    writeLog(error.message, "error");
  }
}

async function refreshTickets() {
  try {
    const tickets = await apiFetch("/admin/tickets");
    renderTickets(Array.isArray(tickets) ? tickets : []);
  } catch (error) {
    writeLog(error.message, "error");
  }
}

async function refreshAnalytics() {
  try {
    const period = analyticsPeriodSelect.value || "week";
    const analytics = await apiFetch(
      `/stats/materials-growth?period=${encodeURIComponent(period)}`
    );
    const growthText =
      analytics.growth_percent === null ? "Н/Д (нет базы сравнения)" : `${analytics.growth_percent}%`;
    analyticsBox.textContent = [
      `Период: ${analytics.period}`,
      `Формула: ${analytics.formula}`,
      `Текущий период (N_current): ${analytics.current_count}`,
      `Предыдущий период (N_previous): ${analytics.previous_count}`,
      `Темп роста: ${growthText}`,
      `Тренд: ${analytics.trend}`,
      `Комментарий: ${analytics.comment}`
    ].join("\n");
    analyticsBox.classList.remove("muted");
  } catch (error) {
    writeLog(error.message, "error");
  }
}

async function readErrorMessage(response) {
  try {
    const body = await response.json();
    if (body && typeof body.detail === "string") {
      return body.detail;
    }
    return JSON.stringify(body);
  } catch {
    return response.statusText || "Unknown error";
  }
}

loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  loginBtn.disabled = true;

  const email = emailInput.value.trim();
  const password = passwordInput.value;

  try {
    writeLog(`Авторизация на ${API_BASE_URL}/token ...`);
    const response = await fetch(`${API_BASE_URL}/token`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        email,
        password
      })
    });

    if (!response.ok) {
      const detail = await readErrorMessage(response);
      throw new Error(`Login failed (${response.status}): ${detail}`);
    }

    const data = await response.json();
    token = data.access_token || "";
    if (!token) {
      throw new Error("Token is missing in response");
    }

    authState.textContent = `Токен получен для ${email}`;
    authState.classList.remove("muted");
    setAuthenticatedUI(true);
    uploadBtn.disabled = false;
    createFolderBtn.disabled = false;
    refreshFoldersBtn.disabled = false;
    refreshFilesBtn.disabled = false;
    refreshTicketsBtn.disabled = false;
    refreshAnalyticsBtn.disabled = false;
    analyticsPeriodSelect.disabled = false;
    folderSelect.disabled = false;
    deleteFolderBtn.disabled = selectedFolder === "root";
    writeLog("Авторизация успешна, можно загружать PDF.");
    await refreshFolders();
    await refreshFiles();
    await refreshTickets();
    await refreshAnalytics();
  } catch (error) {
    token = "";
    setAuthenticatedUI(false);
    uploadBtn.disabled = true;
    createFolderBtn.disabled = true;
    refreshFoldersBtn.disabled = true;
    refreshFilesBtn.disabled = true;
    refreshTicketsBtn.disabled = true;
    refreshAnalyticsBtn.disabled = true;
    analyticsPeriodSelect.disabled = true;
    folderSelect.disabled = true;
    deleteFolderBtn.disabled = true;
    authState.textContent = "Токен не получен";
    authState.classList.add("muted");
    writeLog(error.message, "error");
  } finally {
    loginBtn.disabled = false;
  }
});

uploadForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  uploadBtn.disabled = true;

  const selectedFile = pdfFileInput.files[0];
  const folder = selectedFolder;

  try {
    if (!token) {
      throw new Error("Сначала выполните авторизацию");
    }
    if (!selectedFile) {
      throw new Error("Выберите PDF файл");
    }
    if (!selectedFile.name.toLowerCase().endsWith(".pdf")) {
      throw new Error("Разрешены только PDF файлы");
    }

    const formData = new FormData();
    formData.append("folder", folder);
    formData.append("file", selectedFile);

    writeLog(`Загрузка файла ${selectedFile.name} в папку ${folder} ...`);
    const response = await fetch(`${API_BASE_URL}/upload`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`
      },
      body: formData
    });

    if (!response.ok) {
      const detail = await readErrorMessage(response);
      throw new Error(`Upload failed (${response.status}): ${detail}`);
    }

    const data = await response.json();
    writeLog(
      `Файл загружен. s3_key=${data.s3_key || "unknown"}, message="${data.message || "ok"}"`
    );
    pdfFileInput.value = "";
  } catch (error) {
    writeLog(error.message, "error");
  } finally {
    uploadBtn.disabled = false;
  }
});

createFolderForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const path = newFolderPathInput.value.trim();
  if (!path) {
    writeLog("Введите путь папки", "error");
    return;
  }
  try {
    await apiFetch("/folders", { method: "POST", body: { path } });
    writeLog(`Папка создана: ${path}`);
    newFolderPathInput.value = "";
    await refreshFolders();
  } catch (error) {
    writeLog(error.message, "error");
  }
});

refreshFoldersBtn.addEventListener("click", async () => {
  await refreshFolders();
});

refreshFilesBtn.addEventListener("click", async () => {
  await refreshFiles();
});

refreshTicketsBtn.addEventListener("click", async () => {
  await refreshTickets();
});

refreshAnalyticsBtn.addEventListener("click", async () => {
  await refreshAnalytics();
});

analyticsPeriodSelect.addEventListener("change", async () => {
  if (!token) {
    return;
  }
  await refreshAnalytics();
});

folderSelect.addEventListener("change", async () => {
  selectedFolder = folderSelect.value || "root";
  updateFolderLabel();
  await refreshFiles();
});

deleteFolderBtn.addEventListener("click", async () => {
  if (selectedFolder === "root") {
    writeLog("Нельзя удалить корневую папку root", "error");
    return;
  }
  const shouldDelete = window.confirm(`Удалить папку ${selectedFolder}?`);
  if (!shouldDelete) {
    return;
  }
  try {
    await apiFetch(`/folders?path=${encodeURIComponent(selectedFolder)}`, {
      method: "DELETE"
    });
    writeLog(`Папка ${selectedFolder} удалена`);
    selectedFolder = "root";
    await refreshFolders();
    await refreshFiles();
  } catch (error) {
    writeLog(error.message, "error");
  }
});

exitAppBtn.addEventListener("click", async () => {
  try {
    if (window.appControl?.closeApp) {
      await window.appControl.closeApp();
      return;
    }
    window.close();
  } catch (error) {
    writeLog(`Не удалось закрыть приложение: ${error.message}`, "error");
  }
});

setAuthenticatedUI(false);
