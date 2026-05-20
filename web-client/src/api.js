const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";

async function apiRequest(path, { method = "GET", token, body } = {}) {
  const headers = {};

  const isFormData = typeof FormData !== "undefined" && body instanceof FormData;

  if (body !== undefined && !isFormData) {
    headers["Content-Type"] = "application/json";
  }

  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body:
      body === undefined
        ? undefined
        : isFormData
          ? body
          : JSON.stringify(body),
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

export function getFiles(folder, token, includeHidden = false) {
  const query = encodeURIComponent(folder || "root");
  return apiRequest(`/files?folder=${query}&include_hidden=${includeHidden}`, { token });
}

export function getFolderTree() {
  return apiRequest("/folders/tree");
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

export function uploadTicketAttachments(ticketId, files, token) {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));
  return apiRequest(`/tickets/${ticketId}/attachments`, {
    method: "POST",
    token,
    body: formData,
  });
}

export function deleteMyAccount(token) {
  return apiRequest("/users/me", { method: "DELETE", token });
}
