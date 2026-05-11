const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

async function apiRequest(path, { method = "GET", token, body } = {}) {
  const headers = {};

  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  const contentType = response.headers.get("content-type") || "";
  const isJson = contentType.includes("application/json");
  const data = isJson ? await response.json() : null;

  if (!response.ok) {
    const detail = data?.detail || "Request failed";
    throw new Error(detail);
  }

  return data;
}

export function registerUser(payload) {
  return apiRequest("/register", { method: "POST", body: payload });
}

export function loginUser(payload) {
  return apiRequest("/token", { method: "POST", body: payload });
}

export function getFiles(folder) {
  const query = encodeURIComponent(folder || "root");
  return apiRequest(`/files?folder=${query}`);
}

export function getDownloadLink(s3Key, token) {
  const query = encodeURIComponent(s3Key);
  return apiRequest(`/files/download-link?s3_key=${query}`, { token });
}

export function getTickets(token) {
  return apiRequest("/tickets", { token });
}

export function createTicket(payload, token) {
  return apiRequest("/tickets", { method: "POST", token, body: payload });
}
