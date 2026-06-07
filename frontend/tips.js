const statusOutput = document.getElementById("statusOutput");
const matchesList = document.getElementById("matchesList");
const playoffTeamsList = document.getElementById("playoffTeamsList");
const logoutBtn = document.getElementById("logoutBtn");
const refreshMatchesBtn = document.getElementById("refreshMatchesBtn");
const savePlayoffTeamsBtn = document.getElementById("savePlayoffTeamsBtn");

const API_BASE_KEY = "vm_api_base";
const TOKEN_KEY = "vm_token";
const PLAYOFF_ROUNDS = [
  {
    key: "sextondel",
    label: "Tippa sextondelsfinal",
    limit: 32,
    explanation: "Här ser du alla lag i gruppspelet. Markera de lag du tror går vidare till sextondelsfinal.",
  },
  {
    key: "attondel",
    label: "Tippa åttondelsfinal",
    limit: 16,
    explanation: "Här ser du lagen du tippat till sextondelsfinal. Markera de lag du tror går vidare till åttondelsfinal.",
  },
  {
    key: "kvart",
    label: "Tippa kvartsfinal",
    limit: 8,
    explanation: "Här ser du lagen du tippat till åttondelsfinal. Markera de lag du tror går vidare till kvartsfinal.",
  },
  {
    key: "semi",
    label: "Tippa semifinal",
    limit: 4,
    explanation: "Här ser du lagen du tippat till kvartsfinal. Markera de lag du tror går vidare till semifinal.",
  },
  {
    key: "final",
    label: "Tippa final",
    limit: 2,
    explanation: "Här ser du lagen du tippat till semifinal. Markera de lag du tror går vidare till final.",
  },
  {
    key: "vinnare",
    label: "Tippa vinnare",
    limit: 1,
    explanation: "Här ser du lagen du tippat till final. Markera laget du tror vinner VM.",
  },
];
const GROUP_LIMITED_ROUNDS = new Set(["sextondel", "attondel"]);
const MAX_PLAYOFF_TEAMS_PER_GROUP = 3;

let selectedPlayoffRounds = createEmptyPlayoffRounds();
let predictionStatus = {
  locked: false,
  can_edit: true,
  can_view_others: false,
};
let playoffSaveRequestId = 0;
let playoffSaveChain = Promise.resolve();

function setStatus(message) {
  statusOutput.textContent = message;
}

function renderWithoutScrollJump(renderFn) {
  const scrollX = window.scrollX;
  const scrollY = window.scrollY;
  renderFn();
  requestAnimationFrame(() => {
    window.scrollTo(scrollX, scrollY);
  });
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

function getTeamGroups(matches) {
  const teamGroups = new Map();
  groupMatches(matches).forEach((group) => {
    group.matches.forEach((match) => {
      [match.home_team, match.away_team].forEach((team) => {
        const normalizedTeam = String(team || "").trim();
        if (normalizedTeam && !teamGroups.has(normalizedTeam)) {
          teamGroups.set(normalizedTeam, group.title);
        }
      });
    });
  });
  return teamGroups;
}

function countSelectedFromGroup(teams, teamGroups, groupTitle) {
  return teams.filter((team) => teamGroups.get(team) === groupTitle).length;
}

function createEmptyPlayoffRounds() {
  return PLAYOFF_ROUNDS.reduce((rounds, round) => {
    rounds[round.key] = [];
    return rounds;
  }, {});
}

function clonePlayoffRounds(rounds) {
  return PLAYOFF_ROUNDS.reduce((copy, round) => {
    copy[round.key] = Array.isArray(rounds[round.key]) ? [...rounds[round.key]] : [];
    return copy;
  }, {});
}

function getRoundCandidates(roundIndex, matches) {
  if (roundIndex === 0) {
    const teams = [];
    const seen = new Set();
    groupMatches(matches).forEach((group) => {
      group.matches.forEach((match) => {
        [match.home_team, match.away_team].forEach((team) => {
          const normalizedTeam = String(team || "").trim();
          if (normalizedTeam && !seen.has(normalizedTeam)) {
            seen.add(normalizedTeam);
            teams.push(normalizedTeam);
          }
        });
      });
    });
    return teams;
  }
  return selectedPlayoffRounds[PLAYOFF_ROUNDS[roundIndex - 1].key] || [];
}

function groupCandidatesByMatchGroup(candidates, matches, teamGroups) {
  const candidateSet = new Set(candidates);
  const usedTeams = new Set();
  const groups = [];

  groupMatches(matches).forEach((matchGroup) => {
    const teams = [];
    matchGroup.matches.forEach((match) => {
      [match.home_team, match.away_team].forEach((team) => {
        const normalizedTeam = String(team || "").trim();
        if (!normalizedTeam || !candidateSet.has(normalizedTeam) || usedTeams.has(normalizedTeam)) {
          return;
        }
        usedTeams.add(normalizedTeam);
        teams.push(normalizedTeam);
      });
    });
    if (teams.length > 0) {
      groups.push({ title: matchGroup.title, teams });
    }
  });

  const ungroupedTeams = candidates.filter((team) => !usedTeams.has(team));
  if (ungroupedTeams.length > 0) {
    groups.push({ title: "Ogrupperade lag", teams: ungroupedTeams });
  }

  return groups;
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

  const teamGroups = getTeamGroups(matches);

  PLAYOFF_ROUNDS.forEach((round, index) => {
    const candidates = getRoundCandidates(index, matches);
    const selected = new Set(selectedPlayoffRounds[round.key] || []);

    const section = document.createElement("section");
    section.className = "playoff-round";

    const heading = document.createElement("h3");
    heading.textContent = `${round.label} (${selected.size}/${round.limit})`;
    section.appendChild(heading);

    const explanation = document.createElement("p");
    explanation.className = "playoff-round-explanation";
    explanation.textContent = round.explanation;
    section.appendChild(explanation);

    if (candidates.length === 0) {
      const empty = document.createElement("p");
      empty.className = "help";
      empty.textContent = index === 0 ? "Inga lag hittades." : "Valj lag i rundan innan forst.";
      section.appendChild(empty);
    } else {
      groupCandidatesByMatchGroup(candidates, matches, teamGroups).forEach((candidateGroup) => {
        const teams = candidateGroup.teams;
        const groupTitle = candidateGroup.title;
        const groupSection = document.createElement("section");
        groupSection.className = "team-group-section";

        const groupHeading = document.createElement("h4");
        const selectedInGroup = countSelectedFromGroup(
          selectedPlayoffRounds[round.key] || [],
          teamGroups,
          groupTitle,
        );
        groupHeading.textContent = GROUP_LIMITED_ROUNDS.has(round.key)
          ? `${groupTitle} (${selectedInGroup}/${MAX_PLAYOFF_TEAMS_PER_GROUP})`
          : groupTitle;
        groupSection.appendChild(groupHeading);

        const grid = document.createElement("div");
        grid.className = "team-pick-grid";

        teams.forEach((team) => {
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
          teamBtn.onclick = async () => {
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
            } else if (
              GROUP_LIMITED_ROUNDS.has(round.key) &&
              countSelectedFromGroup(currentTeams, teamGroups, teamGroups.get(team)) >= MAX_PLAYOFF_TEAMS_PER_GROUP
            ) {
              setStatus(`Du kan valja max ${MAX_PLAYOFF_TEAMS_PER_GROUP} lag fran samma grupp.`);
              return;
            } else {
              selectedPlayoffRounds[round.key] = [...currentTeams, team];
            }
            pruneLaterPlayoffRounds(index);
            renderWithoutScrollJump(() => renderPlayoffTeamPicker(matches));
            await savePlayoffTeams("Slutspelstippning sparad automatiskt.");
          };
          grid.appendChild(teamBtn);
        });
        groupSection.appendChild(grid);
        section.appendChild(groupSection);
      });
    }

    playoffTeamsList.appendChild(section);
  });
}

async function persistPlayoffTeams(roundsSnapshot, successMessage, requestId) {
  try {
    await api("/playoff-predictions/me", "POST", { rounds: roundsSnapshot });
    if (requestId === playoffSaveRequestId) {
      setStatus(successMessage);
    }
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

function savePlayoffTeams(successMessage = "Slutspelstippning sparad.") {
  if (predictionStatus.locked) {
    setStatus("Tippningen ar last och kan inte andras.");
    return Promise.resolve();
  }
  const requestId = playoffSaveRequestId + 1;
  playoffSaveRequestId = requestId;
  const roundsSnapshot = clonePlayoffRounds(selectedPlayoffRounds);
  playoffSaveChain = playoffSaveChain
    .catch(() => undefined)
    .then(() => persistPlayoffTeams(roundsSnapshot, successMessage, requestId));
  return playoffSaveChain;
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
      homeBtn.classList.add("is-selected");
      drawBtn.classList.remove("is-selected");
      awayBtn.classList.remove("is-selected");
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
      homeBtn.classList.remove("is-selected");
      drawBtn.classList.add("is-selected");
      awayBtn.classList.remove("is-selected");
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
      homeBtn.classList.remove("is-selected");
      drawBtn.classList.remove("is-selected");
      awayBtn.classList.add("is-selected");
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
    if (savePlayoffTeamsBtn) {
      savePlayoffTeamsBtn.disabled = Boolean(predictionStatus.locked);
    }
    setStatus(
      predictionStatus.locked
        ? "Tippningen ar last och kan inte andras."
        : "Tippningen ar oppen for andringar."
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
  if (savePlayoffTeamsBtn) {
    savePlayoffTeamsBtn.addEventListener("click", () => savePlayoffTeams());
  }
  loadMatches();
}

init();
