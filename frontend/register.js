const registerForm = document.getElementById("registerForm");
const apiBaseInput = document.getElementById("apiBase");
const saveApiBaseBtn = document.getElementById("saveApiBaseBtn");
const statusOutput = document.getElementById("statusOutput");
const leagueSelect = document.getElementById("registerLeague");
const leagueCodeInput = document.getElementById("registerLeagueCode");

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

function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token);
}

function updateLeagueCodeRequirement() {
  const leagueNames = {
    slakten: "Slakt och familjevanner",
    lidingo: "Lidingo",
    korpen: "Korpen",
  };
  leagueCodeInput.required = true;
  leagueCodeInput.placeholder = `Kod for ${leagueNames[leagueSelect.value] || "ligan"}`;
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
  const passwordConfirm = document.getElementById("registerPasswordConfirm").value;
  const league = document.getElementById("registerLeague").value;
  const leagueCode = document.getElementById("registerLeagueCode").value.trim();
  let accountCreated = false;

  if (password !== passwordConfirm) {
    setStatus("Losenorden matchar inte.");
    return;
  }

  try {
    const created = await api("/users", "POST", {
      email,
      display_name: displayName,
      password,
      league,
      league_code: leagueCode,
    });
    accountCreated = true;
    const loginResult = await api("/login", "POST", { email, password });
    if (!loginResult.token) {
      throw new Error("Ingen token kom tillbaka vid inloggning");
    }
    setToken(loginResult.token);
    setStatus(`Konto skapat: ${created.display_name} (${created.email})`);
    window.location.href = "./index.html";
  } catch (error) {
    const prefix = accountCreated
      ? "Konto skapat, men automatisk inloggning misslyckades"
      : "Kunde inte skapa konto";
    setStatus(`${prefix}: ${error.message}`);
  }
}

function init() {
  apiBaseInput.value = getApiBase();
  updateLeagueCodeRequirement();
  leagueSelect.addEventListener("change", updateLeagueCodeRequirement);
  saveApiBaseBtn.addEventListener("click", () => {
    setApiBase(apiBaseInput.value.trim());
    setStatus(`API URL sparad: ${getApiBase()}`);
  });
  registerForm.addEventListener("submit", registerUser);
}

init();
