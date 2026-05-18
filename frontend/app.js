const statusOutput = document.getElementById("statusOutput");
const meOutput = document.getElementById("meOutput");
const tableList = document.getElementById("tableList");
const logoutBtn = document.getElementById("logoutBtn");
const refreshTableBtn = document.getElementById("refreshTableBtn");

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

function formatPredictionLabel(row) {
  const prediction = String(row.prediction || "").trim();
  if (!prediction) {
    return "Ingen tippning";
  }
  return prediction;
}

function formatPoints(value) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "-";
  }
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}

function createPredictionCell(text, isSelected = false, extraClass = "") {
  const cell = document.createElement("div");
  cell.className = `prediction-cell${extraClass ? ` ${extraClass}` : ""}`;
  cell.textContent = text;
  if (isSelected) {
    cell.classList.add("is-selected");
  }
  return cell;
}

function renderPredictionHeader() {
  const header = document.createElement("div");
  header.className = "prediction-header prediction-grid";

  const columns = [
    { className: "prediction-match-id", text: "#" },
    { className: "prediction-cell", text: "Hemma" },
    { className: "prediction-cell prediction-draw", text: "Kryss" },
    { className: "prediction-cell", text: "Borta" },
    { className: "prediction-result", text: "Resultat" },
    { className: "prediction-points", text: "Poang" },
    { className: "prediction-choice", text: "Gissning" },
  ];

  columns.forEach((column) => {
    const cell = document.createElement("div");
    cell.className = column.className;
    cell.textContent = column.text;
    header.appendChild(cell);
  });

  return header;
}

function renderPredictionRow(row) {
  const item = document.createElement("div");
  item.className = "prediction-item prediction-grid";

  const matchId = document.createElement("div");
  matchId.className = "prediction-match-id";
  matchId.textContent = `#${row.match_id}`;
  item.appendChild(matchId);

  const selectedPrediction = formatPredictionLabel(row);
  const homeTeam = String(row.home_team || "").trim();
  const awayTeam = String(row.away_team || "").trim();
  const isGroupStage = row.prediction_type === "gruppspel";

  item.appendChild(createPredictionCell(homeTeam || "-", selectedPrediction === homeTeam));
  item.appendChild(createPredictionCell("Kryss", selectedPrediction === "Kryss", "prediction-draw"));
  item.appendChild(createPredictionCell(awayTeam || "-", selectedPrediction === awayTeam));

  const result = document.createElement("div");
  result.className = "prediction-result";
  result.textContent = row.result ? `Res: ${row.result}` : "Res: -";
  item.appendChild(result);

  const points = document.createElement("div");
  points.className = "prediction-points";
  if (row.result) {
    points.textContent = `Poang: ${formatPoints(row.points_awarded)}`;
  } else if (typeof row.points_if_correct === "number") {
    points.textContent = `Poang vid ratt: ${formatPoints(row.points_if_correct)}`;
  } else {
    points.textContent = "Poang: -";
  }
  item.appendChild(points);

  const choice = document.createElement("div");
  choice.className = "prediction-choice";
  choice.textContent = isGroupStage
    ? `Gissning: ${selectedPrediction}`
    : `Slutspel: ${selectedPrediction}`;
  if (selectedPrediction !== "Ingen tippning") {
    choice.classList.add("is-selected");
  }
  item.appendChild(choice);

  return item;
}

function renderPlayerPredictions(container, data) {
  container.innerHTML = "";

  const playoffPredictions = data.playoff_predictions || {};
  const playoffSummary = [
    ["sextondel", "Sextondel"],
    ["attondel", "Attondel"],
    ["kvart", "Kvart"],
    ["semi", "Semi"],
    ["final", "Final"],
    ["vinnare", "Vinnare"],
  ]
    .map(([key, label]) => {
      const teams = Array.isArray(playoffPredictions[key]) ? playoffPredictions[key] : [];
      return `${label}: ${teams.length ? teams.join(", ") : "-"}`;
    })
    .join(" | ");
  const playoffBox = document.createElement("div");
  playoffBox.className = "prediction-summary";
  playoffBox.textContent = `Slutspel: ${playoffSummary}`;
  container.appendChild(playoffBox);

  const list = document.createElement("div");
  list.className = "match-dropdown";
  list.appendChild(renderPredictionHeader());

  const predictions = Array.isArray(data.predictions) ? data.predictions : [];
  predictions.forEach((row) => {
    list.appendChild(renderPredictionRow(row));
  });

  if (predictions.length === 0) {
    const empty = document.createElement("div");
    empty.className = "prediction-item";
    empty.textContent = "Inga tippningar hittades.";
    list.appendChild(empty);
  }

  container.appendChild(list);
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

async function loadMe() {
  try {
    const me = await api("/me");
    const displayName = String(me.display_name || "").trim();
    const league = String(me.league || "").trim();
    const leagueLabel = league === "lidingo" ? "Lidingö" : "Släkt och familjevänner";
    meOutput.textContent = displayName ? `Hej ${displayName} | Liga: ${leagueLabel}` : `Hej | Liga: ${leagueLabel}`;
  } catch (error) {
    if (error.message.includes("401")) {
      clearToken();
      window.location.href = "./login.html";
      return;
    }
    setStatus(`Kunde inte hamta profil: ${error.message}`);
  }
}

async function loadTable() {
  tableList.innerHTML = "";
  try {
    const rows = await api("/table");
    rows.forEach((row) => {
      const el = document.createElement("article");
      el.className = "table-item";

      const header = document.createElement("div");
      header.className = "table-row";

      const text = document.createElement("div");
      text.className = "table-row-text";
      text.textContent = `${row.position}. ${row.name} - ${formatPoints(row.points)} poang`;

      const button = document.createElement("button");
      button.type = "button";
      button.className = "table-row-btn";
      button.textContent = "Visa tippning";

      const details = document.createElement("div");
      details.className = "table-details";
      details.hidden = true;

      let isLoaded = false;
      button.addEventListener("click", async () => {
        if (!details.hidden) {
          details.hidden = true;
          button.textContent = "Visa tippning";
          return;
        }

        details.hidden = false;
        button.textContent = "Dolj tippning";

        if (isLoaded) {
          return;
        }

        details.textContent = "Laddar tippningar...";
        try {
          const playerData = await api(`/predictions/player/${row.player_id}`);
          renderPlayerPredictions(details, playerData);
          isLoaded = true;
        } catch (error) {
          if (error.status === 403 || String(error.message || "").includes("Andras tippningar")) {
            details.textContent = "Admin har stangt av visning av andras tippningar.";
            return;
          }
          details.textContent = `Kunde inte hamta tippningar: ${error.message}`;
          button.textContent = "Visa tippning";
          details.hidden = true;
        }
      });

      header.appendChild(text);
      header.appendChild(button);
      el.appendChild(header);
      el.appendChild(details);
      tableList.appendChild(el);
    });
  } catch (error) {
    setStatus(`Kunde inte hamta tabell: ${error.message}`);
  }
}

function init() {
  requireLogin();
  logoutBtn.addEventListener("click", logout);
  refreshTableBtn.addEventListener("click", loadTable);

  loadMe();
  loadTable();
}

init();
