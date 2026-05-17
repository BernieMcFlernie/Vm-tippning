const statusOutput = document.getElementById("statusOutput");
const loginCard = document.getElementById("loginCard");
const adminPanel = document.getElementById("adminPanel");
const playoffPanel = document.getElementById("playoffPanel");
const predictionsPanel = document.getElementById("predictionsPanel");
const adminPassword = document.getElementById("adminPassword");
const loginBtn = document.getElementById("loginBtn");
const logoutBtn = document.getElementById("logoutBtn");
const refreshBtn = document.getElementById("refreshBtn");
const refreshPredictionsBtn = document.getElementById("refreshPredictionsBtn");
const matchesAdminList = document.getElementById("matchesAdminList");
const adminPredictionsList = document.getElementById("adminPredictionsList");
const playoffResultsList = document.getElementById("playoffResultsList");
const savePlayoffBtn = document.getElementById("savePlayoffBtn");

const API_BASE_KEY = "vm_api_base";
const ADMIN_TOKEN_KEY = "vm_admin_token";
const PLAYOFF_ROUNDS = [
  { key: "sextondel", label: "Sextondelsfinal", limit: 32 },
  { key: "attondel", label: "Attondelsfinal", limit: 16 },
  { key: "kvart", label: "Kvartsfinal", limit: 8 },
  { key: "semi", label: "Semifinal", limit: 4 },
  { key: "final", label: "Final", limit: 2 },
  { key: "vinnare", label: "Vinnare", limit: 1 },
];

let allTeams = [];
let playoffResults = createEmptyPlayoffRounds();

function setStatus(message) {
  statusOutput.textContent = message;
}

function getApiBase() {
  return (localStorage.getItem(API_BASE_KEY) || window.location.origin).replace(/\/+$/, "");
}

function getToken() {
  return localStorage.getItem(ADMIN_TOKEN_KEY) || "";
}

function setToken(token) {
  localStorage.setItem(ADMIN_TOKEN_KEY, token);
}

function clearToken() {
  localStorage.removeItem(ADMIN_TOKEN_KEY);
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

function createEmptyPlayoffRounds() {
  return PLAYOFF_ROUNDS.reduce((rounds, round) => {
    rounds[round.key] = [];
    return rounds;
  }, {});
}

function showAdminPanel() {
  loginCard.hidden = true;
  adminPanel.hidden = false;
  playoffPanel.hidden = false;
  predictionsPanel.hidden = false;
  logoutBtn.hidden = false;
}

function showLogin() {
  loginCard.hidden = false;
  adminPanel.hidden = true;
  playoffPanel.hidden = true;
  predictionsPanel.hidden = true;
  logoutBtn.hidden = true;
}

async function login() {
  try {
    const password = adminPassword.value;
    const result = await api("/admin/login", "POST", { password });
    if (!result.token) {
      throw new Error("API:t skickade ingen admin-token");
    }
    setToken(result.token);
    adminPassword.value = "";
    showAdminPanel();
    await loadFacit();
    await loadAllPredictions();
    setStatus("Inloggad.");
  } catch (error) {
    clearToken();
    showLogin();
    setStatus(`Kunde inte logga in: ${error.message}`);
  }
}

function logout() {
  clearToken();
  showLogin();
  setStatus("Utloggad.");
}

function collectTeams(matches) {
  const teams = new Set();
  matches.forEach((match) => {
    const homeTeam = String(match.home_team || "").trim();
    const awayTeam = String(match.away_team || "").trim();
    if (homeTeam) {
      teams.add(homeTeam);
    }
    if (awayTeam) {
      teams.add(awayTeam);
    }
  });
  return Array.from(teams).sort((a, b) => a.localeCompare(b, "sv"));
}

function createNumberInput(value) {
  const input = document.createElement("input");
  input.type = "number";
  input.min = "0";
  input.inputMode = "numeric";
  input.value = value == null ? "" : String(value);
  return input;
}

function createAdvancingSelect(match) {
  const select = document.createElement("select");
  const emptyOption = document.createElement("option");
  emptyOption.value = "";
  emptyOption.textContent = "Inget lag";
  select.appendChild(emptyOption);

  [match.home_team, match.away_team].forEach((team) => {
    const option = document.createElement("option");
    option.value = team;
    option.textContent = team;
    if (match.advancing_team === team) {
      option.selected = true;
    }
    select.appendChild(option);
  });
  return select;
}

function renderMatchAdminRow(match) {
  const item = document.createElement("article");
  item.className = "table-item";

  const title = document.createElement("div");
  title.className = "match-title";
  title.textContent = `#${match.id} ${match.home_team} - ${match.away_team}`;
  item.appendChild(title);

  const row = document.createElement("div");
  row.className = "admin-result-grid";

  const homeGoals = createNumberInput(match.home_goals);
  const awayGoals = createNumberInput(match.away_goals);
  const advancingTeam = createAdvancingSelect(match);
  const saveBtn = document.createElement("button");
  saveBtn.type = "button";
  saveBtn.textContent = "Spara";
  saveBtn.onclick = async () => {
    try {
      const body = {
        home_goals: homeGoals.value === "" ? null : Number(homeGoals.value),
        away_goals: awayGoals.value === "" ? null : Number(awayGoals.value),
        advancing_team: advancingTeam.value || null,
      };
      await api(`/admin/matches/${match.id}/result`, "POST", body);
      setStatus(`Sparade facit for match ${match.id}.`);
    } catch (error) {
      if (error.status === 401 || error.status === 403) {
        logout();
        return;
      }
      setStatus(`Kunde inte spara match ${match.id}: ${error.message}`);
    }
  };

  row.appendChild(homeGoals);
  row.appendChild(awayGoals);
  row.appendChild(advancingTeam);
  row.appendChild(saveBtn);
  item.appendChild(row);
  return item;
}

function getRoundCandidates(roundIndex) {
  if (roundIndex === 0) {
    return allTeams;
  }
  return playoffResults[PLAYOFF_ROUNDS[roundIndex - 1].key] || [];
}

function pruneLaterRounds(startIndex) {
  for (let index = startIndex + 1; index < PLAYOFF_ROUNDS.length; index += 1) {
    const previous = new Set(playoffResults[PLAYOFF_ROUNDS[index - 1].key] || []);
    const round = PLAYOFF_ROUNDS[index];
    playoffResults[round.key] = (playoffResults[round.key] || [])
      .filter((team) => previous.has(team))
      .slice(0, round.limit);
  }
}

function renderPlayoffResults() {
  playoffResultsList.innerHTML = "";

  PLAYOFF_ROUNDS.forEach((round, index) => {
    const candidates = getRoundCandidates(index);
    const selected = new Set(playoffResults[round.key] || []);
    const section = document.createElement("section");
    section.className = "playoff-round";

    const heading = document.createElement("h3");
    heading.textContent = `${round.label} (${selected.size}/${round.limit})`;
    section.appendChild(heading);

    const grid = document.createElement("div");
    grid.className = "team-pick-grid";
    candidates.forEach((team) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "team-pick-btn";
      button.textContent = team;
      if (selected.has(team)) {
        button.classList.add("is-selected");
      }
      button.onclick = () => {
        const currentTeams = playoffResults[round.key] || [];
        if (currentTeams.includes(team)) {
          playoffResults[round.key] = currentTeams.filter((item) => item !== team);
        } else if (currentTeams.length >= round.limit) {
          setStatus(`${round.label} kan ha max ${round.limit} lag.`);
          return;
        } else {
          playoffResults[round.key] = [...currentTeams, team];
        }
        pruneLaterRounds(index);
        renderPlayoffResults();
      };
      grid.appendChild(button);
    });

    if (candidates.length === 0) {
      const empty = document.createElement("p");
      empty.className = "help";
      empty.textContent = "Valj lag i rundan innan forst.";
      section.appendChild(empty);
    } else {
      section.appendChild(grid);
    }
    playoffResultsList.appendChild(section);
  });
}

function renderPlayoffPredictionSummary(rounds) {
  return PLAYOFF_ROUNDS
    .map((round) => {
      const teams = rounds && Array.isArray(rounds[round.key]) ? rounds[round.key] : [];
      return `${round.label}: ${teams.length ? teams.join(", ") : "-"}`;
    })
    .join(" | ");
}

function renderAdminPredictionRow(row) {
  const item = document.createElement("div");
  item.className = "prediction-item";
  item.textContent = `#${row.match_id} ${row.match}: ${row.prediction}`;
  return item;
}

function renderAdminPlayerPredictions(player) {
  const item = document.createElement("article");
  item.className = "table-item";

  const title = document.createElement("div");
  title.className = "match-title";
  title.textContent = `${player.name} | ${player.league_name}`;
  item.appendChild(title);

  const playoff = document.createElement("div");
  playoff.className = "prediction-summary";
  playoff.textContent = `Slutspel: ${renderPlayoffPredictionSummary(player.playoff_predictions)}`;
  item.appendChild(playoff);

  const predictions = Array.isArray(player.predictions) ? player.predictions : [];
  if (predictions.length === 0) {
    const empty = document.createElement("div");
    empty.className = "prediction-item";
    empty.textContent = "Inga matchtippningar.";
    item.appendChild(empty);
    return item;
  }

  predictions.forEach((prediction) => {
    item.appendChild(renderAdminPredictionRow(prediction));
  });
  return item;
}

async function loadAllPredictions() {
  adminPredictionsList.innerHTML = "Laddar tippningar...";
  try {
    const players = await api("/admin/predictions");
    adminPredictionsList.innerHTML = "";
    if (!Array.isArray(players) || players.length === 0) {
      adminPredictionsList.textContent = "Inga spelare hittades.";
      return;
    }
    players.forEach((player) => {
      adminPredictionsList.appendChild(renderAdminPlayerPredictions(player));
    });
  } catch (error) {
    if (error.status === 401 || error.status === 403) {
      logout();
      return;
    }
    adminPredictionsList.textContent = "Kunde inte hamta tippningar.";
    setStatus(`Kunde inte hamta alla tippningar: ${error.message}`);
  }
}

async function savePlayoffResults() {
  try {
    await api("/admin/playoff-results", "POST", { rounds: playoffResults });
    setStatus("Slutspelsfacit sparat.");
  } catch (error) {
    if (error.status === 401 || error.status === 403) {
      logout();
      return;
    }
    setStatus(`Kunde inte spara slutspelsfacit: ${error.message}`);
  }
}

async function loadFacit() {
  try {
    const data = await api("/admin/facit");
    const matches = Array.isArray(data.matches) ? data.matches : [];
    allTeams = collectTeams(matches);
    playoffResults = createEmptyPlayoffRounds();
    PLAYOFF_ROUNDS.forEach((round) => {
      const teams = data.playoff_results && Array.isArray(data.playoff_results[round.key])
        ? data.playoff_results[round.key]
        : [];
      playoffResults[round.key] = teams;
    });

    matchesAdminList.innerHTML = "";
    matches.forEach((match) => {
      matchesAdminList.appendChild(renderMatchAdminRow(match));
    });
    renderPlayoffResults();
  } catch (error) {
    if (error.status === 401 || error.status === 403) {
      clearToken();
      showLogin();
      setStatus("Logga in med adminlosenord.");
      return;
    }
    setStatus(`Kunde inte hamta facit: ${error.message}`);
  }
}

function init() {
  loginBtn.addEventListener("click", login);
  logoutBtn.addEventListener("click", logout);
  refreshBtn.addEventListener("click", loadFacit);
  refreshPredictionsBtn.addEventListener("click", loadAllPredictions);
  savePlayoffBtn.addEventListener("click", savePlayoffResults);
  adminPassword.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      login();
    }
  });

  if (getToken()) {
    showAdminPanel();
    loadFacit();
    loadAllPredictions();
  } else {
    showLogin();
  }
}

init();
