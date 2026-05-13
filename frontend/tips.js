const statusOutput = document.getElementById("statusOutput");
const matchesList = document.getElementById("matchesList");
const playoffTeamsList = document.getElementById("playoffTeamsList");
const logoutBtn = document.getElementById("logoutBtn");
const refreshMatchesBtn = document.getElementById("refreshMatchesBtn");
const savePlayoffTeamsBtn = document.getElementById("savePlayoffTeamsBtn");

const API_BASE_KEY = "vm_api_base";
const TOKEN_KEY = "vm_token";
const MAX_PLAYOFF_TEAM_BUTTONS = 48;
const MAX_SELECTED_PLAYOFF_TEAMS = 4;

let selectedPlayoffTeams = new Set();

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

function isSelectedGroup(prediction, outcome) {
  return prediction && prediction.type === "gruppspel" && prediction.predicted_outcome === outcome;
}

function isSelectedHome(prediction, homeTeam) {
  return (
    isSelectedGroup(prediction, "vinst") ||
    (prediction && prediction.type === "slutspel" && prediction.predicted_team === homeTeam)
  );
}

function isSelectedAway(prediction, awayTeam) {
  return (
    isSelectedGroup(prediction, "forlust") ||
    (prediction && prediction.type === "slutspel" && prediction.predicted_team === awayTeam)
  );
}

async function saveGroupPrediction(matchId, outcome) {
  await api("/predictions/gruppspel", "POST", {
    match_id: matchId,
    predicted_outcome: outcome,
  });
  setStatus(`Tippning sparad for match ${matchId}: ${outcome}`);
}

function getUniqueTeams(matches) {
  const teams = new Set();
  matches.forEach((match) => {
    teams.add(String(match.home_team || "").trim());
    teams.add(String(match.away_team || "").trim());
  });
  return Array.from(teams).filter((team) => team).sort((a, b) => a.localeCompare(b, "sv"));
}

function renderPlayoffTeamPicker(matches) {
  playoffTeamsList.innerHTML = "";
  const teams = getUniqueTeams(matches).slice(0, MAX_PLAYOFF_TEAM_BUTTONS);
  if (teams.length === 0) {
    playoffTeamsList.textContent = "Inga lag hittades.";
    return;
  }

  selectedPlayoffTeams = new Set(
    Array.from(selectedPlayoffTeams)
      .filter((team) => teams.includes(team))
      .slice(0, MAX_SELECTED_PLAYOFF_TEAMS)
  );

  teams.forEach((team) => {
    const teamBtn = document.createElement("button");
    teamBtn.type = "button";
    teamBtn.className = "team-pick-btn";
    if (selectedPlayoffTeams.has(team)) {
      teamBtn.classList.add("is-selected");
    }
    teamBtn.textContent = team;
    teamBtn.onclick = () => {
      const currentlySelected = selectedPlayoffTeams.has(team);
      if (currentlySelected) {
        selectedPlayoffTeams.delete(team);
        teamBtn.classList.remove("is-selected");
        return;
      }
      if (selectedPlayoffTeams.size >= MAX_SELECTED_PLAYOFF_TEAMS) {
        setStatus("Du kan valja max 4 lag till slutspel.");
        return;
      }
      selectedPlayoffTeams.add(team);
      teamBtn.classList.add("is-selected");
    };
    playoffTeamsList.appendChild(teamBtn);
  });
}

async function savePlayoffTeams() {
  try {
    const teams = Array.from(selectedPlayoffTeams);
    if (teams.length !== MAX_SELECTED_PLAYOFF_TEAMS) {
      setStatus("Valj exakt 4 lag innan du sparar.");
      return;
    }
    await api("/playoff-teams/me", "POST", { teams });
    setStatus(`Slutspelsval sparat (${teams.length} lag).`);
  } catch (error) {
    if (error.status === 401) {
      clearToken();
      window.location.href = "./login.html";
      return;
    }
    if (String(error.message || "").includes("Failed to fetch")) {
      setStatus("Kunde inte spara slutspelsval: ingen kontakt med API. Starta om backend och testa igen.");
      return;
    }
    setStatus(`Kunde inte spara slutspelsval: ${error.message}`);
  }
}

function renderMatch(match, prediction) {
  const item = document.createElement("article");
  item.className = "match-item";

  const title = document.createElement("div");
  title.className = "match-title";
  title.textContent = `#${match.id} ${match.home_team} - ${match.away_team}`;
  item.appendChild(title);

  const actions = document.createElement("div");
  actions.className = "actions";

  const groupRow = document.createElement("div");
  groupRow.className = "row";

  const homeBtn = document.createElement("button");
  homeBtn.type = "button";
  homeBtn.textContent = match.home_team;
  if (isSelectedHome(prediction, match.home_team)) {
    homeBtn.classList.add("is-selected");
  }
  homeBtn.onclick = async () => {
    try {
      await saveGroupPrediction(match.id, "vinst");
      await loadMatches();
    } catch (error) {
      setStatus(`Kunde inte spara gruppspelstippning: ${error.message}`);
    }
  };

  const drawBtn = document.createElement("button");
  drawBtn.type = "button";
  drawBtn.textContent = "Kryss";
  if (isSelectedGroup(prediction, "kryss")) {
    drawBtn.classList.add("is-selected");
  }
  drawBtn.onclick = async () => {
    try {
      await saveGroupPrediction(match.id, "kryss");
      await loadMatches();
    } catch (error) {
      setStatus(`Kunde inte spara gruppspelstippning: ${error.message}`);
    }
  };

  const awayBtn = document.createElement("button");
  awayBtn.type = "button";
  awayBtn.textContent = match.away_team;
  if (isSelectedAway(prediction, match.away_team)) {
    awayBtn.classList.add("is-selected");
  }
  awayBtn.onclick = async () => {
    try {
      await saveGroupPrediction(match.id, "forlust");
      await loadMatches();
    } catch (error) {
      setStatus(`Kunde inte spara gruppspelstippning: ${error.message}`);
    }
  };

  groupRow.appendChild(homeBtn);
  groupRow.appendChild(drawBtn);
  groupRow.appendChild(awayBtn);

  actions.appendChild(groupRow);
  item.appendChild(actions);
  return item;
}

function renderGroupSection(title, matches, predictionsByMatchId) {
  const section = document.createElement("section");
  section.className = "stack";

  const heading = document.createElement("h3");
  heading.textContent = title;
  section.appendChild(heading);

  matches.forEach((match) => {
    const prediction = predictionsByMatchId.get(Number(match.id));
    section.appendChild(renderMatch(match, prediction));
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
    const [matches, predictions] = await Promise.all([
      api("/matches"),
      api("/predictions/me"),
    ]);

    let playoffData = { teams: [] };
    try {
      playoffData = await api("/playoff-teams/me");
    } catch (error) {
      if (error.status === 401 || String(error.message || "").includes("401")) {
        clearToken();
        window.location.href = "./login.html";
        return;
      }
      setStatus(`Kunde inte hamta sparade slutspelsval: ${error.message}`);
    }
    selectedPlayoffTeams = new Set(Array.isArray(playoffData.teams) ? playoffData.teams : []);

    const predictionsByMatchId = new Map();
    predictions.forEach((prediction) => {
      predictionsByMatchId.set(Number(prediction.match_id), prediction);
    });

    if (!Array.isArray(matches) || matches.length === 0) {
      matchesList.textContent = "Inga matcher hittades.";
      renderPlayoffTeamPicker([]);
      return;
    }

    groupMatches(matches).forEach((group) => {
      matchesList.appendChild(renderGroupSection(group.title, group.matches, predictionsByMatchId));
    });

    renderPlayoffTeamPicker(matches);
  } catch (error) {
    if (error.status === 401 || String(error.message || "").includes("401")) {
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
  savePlayoffTeamsBtn.addEventListener("click", savePlayoffTeams);
  loadMatches();
}

init();
