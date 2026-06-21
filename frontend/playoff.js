const statusOutput = document.getElementById("statusOutput");
const playerTitle = document.getElementById("playerTitle");
const playoffTree = document.getElementById("playoffTree");
const logoutBtn = document.getElementById("logoutBtn");

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

function formatPoints(value) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "-";
  }
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
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

function getPlayerId() {
  const params = new URLSearchParams(window.location.search);
  return params.get("player_id");
}

function renderTree(data) {
  playoffTree.innerHTML = "";
  const rounds = Array.isArray(data.rounds) ? data.rounds : [];
  if (rounds.length === 0) {
    playoffTree.textContent = "Inget slutspelstrad hittades.";
    return;
  }

  rounds.forEach((round) => {
    const column = document.createElement("section");
    column.className = "playoff-tree-round";

    const heading = document.createElement("h3");
    heading.textContent = round.label || round.key;
    column.appendChild(heading);

    const teams = Array.isArray(round.teams) ? round.teams : [];
    if (teams.length === 0) {
      const empty = document.createElement("p");
      empty.className = "help";
      empty.textContent = "Inga lag valda.";
      column.appendChild(empty);
    }

    teams.forEach((team) => {
      const item = document.createElement("div");
      item.className = "playoff-team-card";
      if (team.is_correct) {
        item.classList.add("is-correct");
      }

      const name = document.createElement("strong");
      name.textContent = team.team;
      const picked = document.createElement("span");
      picked.textContent = `${team.picked_count} tippade laget`;
      const points = document.createElement("span");
      points.textContent = `${formatPoints(team.points_if_correct)} poang om ratt`;
      item.appendChild(name);
      item.appendChild(picked);
      item.appendChild(points);

      column.appendChild(item);
    });

    playoffTree.appendChild(column);
  });
}

async function loadPlayoffTree() {
  const playerId = getPlayerId();
  if (!playerId) {
    setStatus("Saknar player_id i URL:en.");
    playoffTree.textContent = "Ingen spelare vald.";
    return;
  }

  try {
    const data = await api(`/playoff-tree/player/${encodeURIComponent(playerId)}`);
    playerTitle.textContent = `${data.player_name} - poangen visas per lag om tipset slar in.`;
    renderTree(data);
  } catch (error) {
    if (error.status === 401) {
      clearToken();
      window.location.href = "./login.html";
      return;
    }
    if (error.status === 403) {
      playoffTree.textContent = "Admin har stangt av visning av andras tippningar.";
      return;
    }
    setStatus(`Kunde inte hamta slutspelstrad: ${error.message}`);
  }
}

function init() {
  requireLogin();
  logoutBtn.addEventListener("click", logout);
  loadPlayoffTree();
}

init();
