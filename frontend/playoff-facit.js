const statusOutput = document.getElementById("statusOutput");
const facitTree = document.getElementById("facitTree");
const teamSearch = document.getElementById("teamSearch");
const teamList = document.getElementById("teamList");
const teamDetails = document.getElementById("teamDetails");
const teamDetailTitle = document.getElementById("teamDetailTitle");
const logoutBtn = document.getElementById("logoutBtn");

const API_BASE_KEY = "vm_api_base";
const TOKEN_KEY = "vm_token";

let allTeams = [];
let selectedTeam = "";

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

function renderFacitTree(rounds) {
  facitTree.innerHTML = "";
  if (!Array.isArray(rounds) || rounds.length === 0) {
    facitTree.textContent = "Inget slutspelsfacit finns annu.";
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
      empty.textContent = "Inga lag inlagda.";
      column.appendChild(empty);
    }

    teams.forEach((team) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "playoff-team-card playoff-team-button";

      const name = document.createElement("strong");
      name.textContent = team.team;
      const picked = document.createElement("span");
      picked.textContent = `${team.picked_count} tippade laget`;
      const points = document.createElement("span");
      points.textContent = `${formatPoints(team.points_awarded)} poang`;
      button.appendChild(name);
      button.appendChild(picked);
      button.appendChild(points);

      button.addEventListener("click", () => selectTeam(team.team));
      column.appendChild(button);
    });

    facitTree.appendChild(column);
  });
}

function renderTeamList() {
  const query = teamSearch.value.trim().toLowerCase();
  teamList.innerHTML = "";
  allTeams
    .filter((item) => item.team.toLowerCase().includes(query))
    .forEach((item) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "team-list-button";
      if (item.team === selectedTeam) {
        button.classList.add("is-selected");
      }
      button.textContent = item.team;
      button.addEventListener("click", () => selectTeam(item.team));
      teamList.appendChild(button);
    });
}

function selectTeam(teamName) {
  selectedTeam = teamName;
  renderTeamList();

  const team = allTeams.find((item) => item.team === teamName);
  teamDetailTitle.textContent = teamName;
  teamDetails.innerHTML = "";

  if (!team) {
    teamDetails.textContent = "Laget hittades inte.";
    return;
  }

  team.rounds.forEach((round) => {
    const item = document.createElement("article");
    item.className = "table-item";
    if (round.is_correct) {
      item.classList.add("is-correct");
    }
    const players = Array.isArray(round.players) ? round.players.map((player) => player.name).join(", ") : "";
    item.textContent = `${round.label}: ${round.picked_count} tippade laget${players ? ` - ${players}` : ""} | Poang: ${formatPoints(round.points_awarded)}`;
    teamDetails.appendChild(item);
  });
}

async function loadPlayoffFacit() {
  try {
    const data = await api("/facit/playoff");
    allTeams = Array.isArray(data.teams) ? data.teams : [];
    renderFacitTree(data.rounds);
    renderTeamList();
    if (allTeams.length > 0) {
      selectTeam(allTeams[0].team);
    }
  } catch (error) {
    if (error.status === 401) {
      clearToken();
      window.location.href = "./login.html";
      return;
    }
    if (error.status === 403) {
      facitTree.textContent = "Admin har stangt av visning av andras tippningar.";
      return;
    }
    setStatus(`Kunde inte hamta slutspelsfacit: ${error.message}`);
  }
}

function init() {
  requireLogin();
  logoutBtn.addEventListener("click", logout);
  teamSearch.addEventListener("input", renderTeamList);
  loadPlayoffFacit();
}

init();
