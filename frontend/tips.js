const statusOutput = document.getElementById("statusOutput");
const matchesList = document.getElementById("matchesList");
const playoffTeamsList = document.getElementById("playoffTeamsList");
const logoutBtn = document.getElementById("logoutBtn");
const refreshMatchesBtn = document.getElementById("refreshMatchesBtn");
const savePlayoffTeamsBtn = document.getElementById("savePlayoffTeamsBtn");

const API_BASE_KEY = "vm_api_base";
const TOKEN_KEY = "vm_token";
const PLAYOFF_ROUNDS = [
  { key: "sextondel", label: "Sextondelsfinal", limit: 32 },
  { key: "attondel", label: "Attondelsfinal", limit: 16 },
  { key: "kvart", label: "Kvartsfinal", limit: 8 },
  { key: "semi", label: "Semifinal", limit: 4 },
  { key: "final", label: "Final", limit: 2 },
  { key: "vinnare", label: "Vinnare", limit: 1 },
];

let selectedPlayoffRounds = createEmptyPlayoffRounds();
let predictionStatus = {
  deadline: "2026-06-11T00:00:00",
  locked: false,
  can_edit: true,
  can_view_others: false,
};

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

function formatDeadline(deadline) {
  const date = new Date(deadline);
  if (Number.isNaN(date.getTime())) {
    return "2026-06-11 00:00";
  }
  return date.toLocaleString("sv-SE", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
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
  if (predictionStatus.locked) {
    setStatus("Tippningen ar last och kan inte andras.");
    return;
  }
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

function createEmptyPlayoffRounds() {
  return PLAYOFF_ROUNDS.reduce((rounds, round) => {
    rounds[round.key] = [];
    return rounds;
  }, {});
}

function getRoundCandidates(roundIndex, matches) {
  if (roundIndex === 0) {
    return getUniqueTeams(matches);
  }
  return selectedPlayoffRounds[PLAYOFF_ROUNDS[roundIndex - 1].key] || [];
}

function pruneLaterPlayoffRounds(startIndex) {
  for (let index = startIndex + 1; index < PLAYOFF_ROUNDS.length; index += 1) {
    const previous = new Set(selectedPlayoffRounds[PLAYOFF_ROUNDS[index - 1].key] || []);
    const round = PLAYOFF_ROUNDS[index];
    selectedPlayoffRounds[round.key] = (selectedPlayoffRounds[round.key] || [])
      .filter((team) => previous.has(team))
      .slice(0, round.limit);
  }
}

function renderPlayoffTeamPicker(matches) {
  playoffTeamsList.innerHTML = "";
  const locked = Boolean(predictionStatus.locked);
  if (!Array.isArray(matches) || matches.length === 0) {
    playoffTeamsList.textContent = "Inga lag hittades.";
    return;
  }

  PLAYOFF_ROUNDS.forEach((round, index) => {
    const candidates = getRoundCandidates(index, matches);
    const selected = new Set(selectedPlayoffRounds[round.key] || []);

    const section = document.createElement("section");
    section.className = "playoff-round";

    const heading = document.createElement("h3");
    heading.textContent = `${round.label} (${selected.size}/${round.limit})`;
    section.appendChild(heading);

    const grid = document.createElement("div");
    grid.className = "team-pick-grid";

    if (candidates.length === 0) {
      const empty = document.createElement("p");
      empty.className = "help";
      empty.textContent = index === 0 ? "Inga lag hittades." : "Valj lag i rundan innan forst.";
      section.appendChild(empty);
    } else {
      candidates.forEach((team) => {
        const teamBtn = document.createElement("button");
        teamBtn.type = "button";
        teamBtn.className = "team-pick-btn";
        if (selected.has(team)) {
          teamBtn.classList.add("is-selected");
        }
        teamBtn.disabled = locked;
        if (locked) {
          teamBtn.title = "Tippningen ar last.";
        }
        teamBtn.textContent = team;
        teamBtn.onclick = () => {
          if (locked) {
            setStatus("Tippningen ar last och kan inte andras.");
            return;
          }
          const currentTeams = selectedPlayoffRounds[round.key] || [];
          const isSelected = currentTeams.includes(team);
          if (isSelected) {
            selectedPlayoffRounds[round.key] = currentTeams.filter((item) => item !== team);
          } else if (currentTeams.length >= round.limit) {
            setStatus(`${round.label} kan ha max ${round.limit} lag.`);
            return;
          } else {
            selectedPlayoffRounds[round.key] = [...currentTeams, team];
          }
          pruneLaterPlayoffRounds(index);
          renderPlayoffTeamPicker(matches);
        };
        grid.appendChild(teamBtn);
      });
      section.appendChild(grid);
    }

    playoffTeamsList.appendChild(section);
  });
}

async function savePlayoffTeams() {
  if (predictionStatus.locked) {
    setStatus("Tippningen ar last och kan inte andras.");
    return;
  }
  try {
    await api("/playoff-predictions/me", "POST", { rounds: selectedPlayoffRounds });
    setStatus("Slutspelstippning sparad.");
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
    setStatus(`Kunde inte spara slutspelstippning: ${error.message}`);
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
  homeBtn.disabled = Boolean(predictionStatus.locked);
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
  drawBtn.disabled = Boolean(predictionStatus.locked);
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
  awayBtn.disabled = Boolean(predictionStatus.locked);
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
    const [matches, predictions, status] = await Promise.all([
      api("/matches"),
      api("/predictions/me"),
      api("/predictions/status"),
    ]);
    predictionStatus = status;
    savePlayoffTeamsBtn.disabled = Boolean(predictionStatus.locked);
    setStatus(
      predictionStatus.locked
        ? `Tippningen ar last sedan ${formatDeadline(predictionStatus.deadline)}.`
        : `Tippningen laser ${formatDeadline(predictionStatus.deadline)}.`
    );

    let playoffData = { rounds: createEmptyPlayoffRounds() };
    try {
      playoffData = await api("/playoff-predictions/me");
    } catch (error) {
      if (error.status === 401 || String(error.message || "").includes("401")) {
        clearToken();
        window.location.href = "./login.html";
        return;
      }
      setStatus(`Kunde inte hamta sparade slutspelsval: ${error.message}`);
    }
    selectedPlayoffRounds = createEmptyPlayoffRounds();
    PLAYOFF_ROUNDS.forEach((round) => {
      const teams = playoffData.rounds && Array.isArray(playoffData.rounds[round.key])
        ? playoffData.rounds[round.key]
        : [];
      selectedPlayoffRounds[round.key] = teams;
    });

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
