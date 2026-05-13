const statusOutput = document.getElementById("statusOutput");
const matchesList = document.getElementById("matchesList");
const logoutBtn = document.getElementById("logoutBtn");
const refreshMatchesBtn = document.getElementById("refreshMatchesBtn");

const API_BASE_KEY = "vm_api_base";
const TOKEN_KEY = "vm_token";

function setStatus(message) {
  statusOutput.textContent = message;
}

function getApiBase() {
  return (localStorage.getItem(API_BASE_KEY) || window.location.origin).replace(/\/+$/, "");
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
    const error = new Error(data.detail || `HTTP ${response.status}`);
    error.status = response.status;
    throw error;
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

function formatResult(match) {
  if (match.home_goals == null || match.away_goals == null) {
    return "Ej inlagt";
  }
  return `${match.home_goals}-${match.away_goals}`;
}

function renderPredictionRow(row) {
  const item = document.createElement("div");
  item.className = "prediction-item";
  const pointsIfCorrect =
    typeof row.points_if_correct === "number" ? row.points_if_correct.toFixed(2) : "-";
  const pointsAwarded =
    typeof row.points_awarded === "number" ? row.points_awarded.toFixed(2) : "0.00";
  const pointsText = row.is_played
    ? `Poang fick: ${pointsAwarded} | Poang om ratt: ${pointsIfCorrect}`
    : `Poang om ratt: ${pointsIfCorrect}`;
  item.textContent = `${row.player_name}: ${row.prediction} | ${pointsText}`;
  return item;
}

async function loadPredictionsForMatch(matchId, panel) {
  panel.innerHTML = "Laddar tippningar...";
  try {
    const rows = await api(`/predictions/match/${matchId}`);
    panel.innerHTML = "";
    if (!Array.isArray(rows) || rows.length === 0) {
      panel.textContent = "Inga tippningar pa den har matchen.";
      return;
    }
    rows.forEach((row) => {
      panel.appendChild(renderPredictionRow(row));
    });
    return true;
  } catch (error) {
    if (error.status === 401) {
      clearToken();
      window.location.href = "./login.html";
      return;
    }
    panel.textContent = "Kunde inte hamta tippningar.";
    setStatus(`Kunde inte hamta tippningar for match ${matchId}: ${error.message}`);
    return false;
  }
}

function renderMatch(match) {
  const item = document.createElement("article");
  item.className = "table-item";

  const toggleBtn = document.createElement("button");
  toggleBtn.type = "button";
  toggleBtn.className = "match-toggle";
  toggleBtn.textContent = `#${match.id} ${match.home_team} - ${match.away_team} | Resultat: ${formatResult(match)}`;

  const panel = document.createElement("div");
  panel.className = "match-dropdown";
  panel.hidden = true;
  panel.dataset.loaded = "false";

  toggleBtn.onclick = async () => {
    const shouldOpen = panel.hidden;
    panel.hidden = !shouldOpen;
    if (!shouldOpen) {
      return;
    }
    if (panel.dataset.loaded === "true") {
      return;
    }
    const loaded = await loadPredictionsForMatch(match.id, panel);
    panel.dataset.loaded = loaded ? "true" : "false";
  };

  item.appendChild(toggleBtn);
  item.appendChild(panel);
  return item;
}

function renderGroupSection(title, matches) {
  const section = document.createElement("section");
  section.className = "stack";

  const heading = document.createElement("h3");
  heading.textContent = title;
  section.appendChild(heading);

  matches.forEach((match) => {
    section.appendChild(renderMatch(match));
  });

  return section;
}

function groupMatches(matches) {
  const groupNames = "ABCDEFGHIJKL".split("");
  const groups = [];
  for (let index = 0; index < matches.length; index += 6) {
    const groupIndex = Math.floor(index / 6);
    groups.push({
      title: `Grupp ${groupNames[groupIndex] || groupIndex + 1}`,
      matches: matches.slice(index, index + 6),
    });
  }
  return groups;
}

async function loadMatches() {
  matchesList.innerHTML = "";
  try {
    const matches = await api("/matches");
    if (!Array.isArray(matches) || matches.length === 0) {
      matchesList.textContent = "Inga matcher hittades.";
      return;
    }
    groupMatches(matches).forEach((group) => {
      matchesList.appendChild(renderGroupSection(group.title, group.matches));
    });
  } catch (error) {
    if (error.status === 401) {
      clearToken();
      window.location.href = "./login.html";
      return;
    }
    setStatus(`Kunde inte hamta matcher: ${error.message}`);
  }
}

function init() {
  requireLogin();
  logoutBtn.addEventListener("click", logout);
  refreshMatchesBtn.addEventListener("click", loadMatches);
  loadMatches();
}

init();
