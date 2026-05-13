const registerForm = document.getElementById("registerForm");
const apiBaseInput = document.getElementById("apiBase");
const saveApiBaseBtn = document.getElementById("saveApiBaseBtn");
const statusOutput = document.getElementById("statusOutput");

const API_BASE_KEY = "vm_api_base";

function setStatus(message) {
  statusOutput.textContent = message;
}

function getApiBase() {
  return (localStorage.getItem(API_BASE_KEY) || "http://127.0.0.1:8000").replace(/\/+$/, "");
}

function setApiBase(url) {
  localStorage.setItem(API_BASE_KEY, url.replace(/\/+$/, ""));
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

async function registerUser(event) {
  event.preventDefault();
  const email = document.getElementById("registerEmail").value.trim();
  const displayName = document.getElementById("registerDisplayName").value.trim();
  const password = document.getElementById("registerPassword").value;

  try {
    const created = await api("/users", "POST", {
      email,
      display_name: displayName,
      password,
    });
    setStatus(`Konto skapat: ${created.display_name} (${created.email})`);
    registerForm.reset();
  } catch (error) {
    setStatus(`Kunde inte skapa konto: ${error.message}`);
  }
}

function init() {
  apiBaseInput.value = getApiBase();
  saveApiBaseBtn.addEventListener("click", () => {
    setApiBase(apiBaseInput.value.trim());
    setStatus(`API URL sparad: ${getApiBase()}`);
  });
  registerForm.addEventListener("submit", registerUser);
}

init();
