const loginForm = document.getElementById("loginForm");
const uploadForm = document.getElementById("uploadForm");
const backendUrlInput = document.getElementById("backendUrl");
const emailInput = document.getElementById("email");
const passwordInput = document.getElementById("password");
const folderInput = document.getElementById("folder");
const pdfFileInput = document.getElementById("pdfFile");
const loginBtn = document.getElementById("loginBtn");
const uploadBtn = document.getElementById("uploadBtn");
const authState = document.getElementById("authState");
const logBox = document.getElementById("logBox");

let token = "";

function now() {
  return new Date().toLocaleTimeString();
}

function writeLog(message, type = "info") {
  const prefix = type === "error" ? "[ERROR]" : "[INFO]";
  logBox.textContent += `${now()} ${prefix} ${message}\n`;
  logBox.scrollTop = logBox.scrollHeight;
}

function normalizeBaseUrl() {
  return backendUrlInput.value.trim().replace(/\/$/, "");
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

  const baseUrl = normalizeBaseUrl();
  const email = emailInput.value.trim();
  const password = passwordInput.value;

  try {
    writeLog(`Авторизация на ${baseUrl}/token ...`);
    const response = await fetch(`${baseUrl}/token`, {
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
    uploadBtn.disabled = false;
    writeLog("Авторизация успешна, можно загружать PDF.");
  } catch (error) {
    token = "";
    uploadBtn.disabled = true;
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
  const folder = folderInput.value.trim() || "root";
  const baseUrl = normalizeBaseUrl();

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
    const response = await fetch(`${baseUrl}/upload`, {
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
