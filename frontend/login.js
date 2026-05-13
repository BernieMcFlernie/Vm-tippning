const loginForm = document.getElementById("loginForm");
const apiBaseInput = document.getElementById("apiBase");
const saveApiBaseBtn = document.getElementById("saveApiBaseBtn");
const statusOutput = document.getElementById("statusOutput");

const API_BASE_KEY = "vm_api_base";
const TOKEN_KEY = "vm_token";

function setStatus(message) {
  statusOutput.textContent = message;
}

function getApiBase() {
  return (localStorage.getItem(API_BASE_KEY) || window.location.origin).replace(/\/+$/, "");
}

function setApiBase(url) {
  localStorage.setItem(API_BASE_KEY, url.replace(/\/+$/, ""));
}

function getToken() {
  return localStorage.getItem(TOKEN_KEY) || "";
}

function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}

async function api(path, method = "GET", body = undefined) {
  const response = await fetch(`${getApiBase()}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || `HTTP ${response.status}`);
  }
  return data;
}

async function login(event) {
  event.preventDefault();
  const email = document.getElementById("loginEmail").value.trim();
  const password = document.getElementById("loginPassword").value;

  try {
    const result = await api("/login", "POST", { email, password });
    if (!result.token) {
      throw new Error("Ingen token i svar");
    }
    setToken(result.token);
    window.location.href = "./index.html";
  } catch (error) {
    setStatus(`Inloggning misslyckades: ${error.message}`);
  }
}

function init() {
  if (getToken()) {
    window.location.href = "./index.html";
    return;
  }
  apiBaseInput.value = getApiBase();
  saveApiBaseBtn.addEventListener("click", () => {
    setApiBase(apiBaseInput.value.trim());
    setStatus(`API URL sparad: ${getApiBase()}`);
  });
  loginForm.addEventListener("submit", login);
}

init();
