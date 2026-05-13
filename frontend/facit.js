const statusOutput = document.getElementById("statusOutput");
const facitList = document.getElementById("facitList");
const logoutBtn = document.getElementById("logoutBtn");

const API_BASE_KEY = "vm_api_base";
const TOKEN_KEY = "vm_token";

function setStatus(message) {
  statusOutput.textContent = message;
}

function getApiBase() {
  return (localStorage.getItem(API_BASE_KEY) || "http://127.0.0.1:8000").replace(/\/+$/, "");
}

function getToken() {
  return localStorage.getItem(TOKEN_KEY) || "";
}

function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

async function api(path, method = "GET", body = undefined) {
  const token = getToken();
  const response = await fetch(`${getApiBase()}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || `HTTP ${response.status}`);
  }
  return data;
}

function requireLogin() {
  if (!getToken()) {
    window.location.href = "./login.html";
  }
}

async function logout() {
  try {
    await api("/logout", "POST");
  } catch (error) {
    setStatus(`Logout-varning: ${error.message}`);
  } finally {
    clearToken();
    window.location.href = "./login.html";
  }
}

function renderFacitRow(row) {
  const item = document.createElement("article");
  item.className = "table-item";
  const predictionText = row.your_prediction || "Ingen tippning";
  const resultText = row.result || "-";
  const correctText = row.is_correct ? "Ratt" : "Fel";
  const pointsIfCorrectText = row.points_if_correct == null ? "-" : row.points_if_correct;
  item.textContent = `#${row.match_id} ${row.home_team} - ${row.away_team} | Resultat: ${resultText} | Facit: ${row.facit} | Din tippning: ${predictionText} | ${correctText} | Poang: ${row.points} | Poang om ratt svar: ${pointsIfCorrectText}`;
  return item;
}

async function loadFacit() {
  facitList.innerHTML = "";
  try {
    const rows = await api("/facit/me");
    if (!Array.isArray(rows) || rows.length === 0) {
      facitList.textContent = "Inget facit att visa.";
      return;
    }
    rows.forEach((row) => {
      facitList.appendChild(renderFacitRow(row));
    });
  } catch (error) {
    if (error.message.includes("401")) {
      clearToken();
      window.location.href = "./login.html";
      return;
    }
    setStatus(`Kunde inte hamta facit: ${error.message}`);
  }
}

function init() {
  requireLogin();
  logoutBtn.addEventListener("click", logout);
  loadFacit();
}

init();
