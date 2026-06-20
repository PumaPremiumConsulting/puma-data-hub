const sourceFilter = document.getElementById("sourceFilter");
const searchInput = document.getElementById("searchInput");
const fromInput = document.getElementById("fromInput");
const toInput = document.getElementById("toInput");
const limitSelect = document.getElementById("limitSelect");
const refreshButton = document.getElementById("refreshButton");
const clearFiltersButton = document.getElementById("clearFiltersButton");
const exportCsvButton = document.getElementById("exportCsvButton");
const statusText = document.getElementById("statusText");
const summaryGrid = document.getElementById("summaryGrid");
const leadsBody = document.getElementById("leadsBody");
const leadsCount = document.getElementById("leadsCount");
const kpiTotal = document.getElementById("kpiTotal");
const kpiLast24h = document.getElementById("kpiLast24h");
const kpiLastSubmitted = document.getElementById("kpiLastSubmitted");
const topFormsList = document.getElementById("topFormsList");

let cachedLeads = [];
let searchDebounceTimer = null;

function setStatus(message, type = "info") {
  statusText.textContent = message;
  statusText.className = `status ${type}`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function formatLocalDate(value) {
  if (!value) return "-";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString();
}

function toApiIsoDateTime(value) {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "";
  return parsed.toISOString();
}

function getFilters(includePagination = true) {
  const params = new URLSearchParams();
  if (sourceFilter.value) params.set("source_site", sourceFilter.value);
  const searchTerm = searchInput.value.trim();
  if (searchTerm) params.set("search", searchTerm);
  const fromIso = toApiIsoDateTime(fromInput.value);
  if (fromIso) params.set("submitted_from", fromIso);
  const toIso = toApiIsoDateTime(toInput.value);
  if (toIso) params.set("submitted_to", toIso);
  if (includePagination) {
    params.set("limit", limitSelect.value || "300");
    params.set("offset", "0");
  }
  return params;
}

async function getJson(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload?.detail || payload?.message || "Errore API";
    throw new Error(typeof detail === "string" ? detail : "Errore API");
  }
  return payload;
}

function renderSummary(summary) {
  summaryGrid.innerHTML = "";
  for (const row of summary) {
    const card = document.createElement("article");
    card.className = "summary-card";
    card.innerHTML = `
      <h3>${escapeHtml(row.source_site)}</h3>
      <p class="summary-total">${row.total_leads || 0} lead</p>
      <p class="summary-time">${row.last_submitted_at ? `Ultima: ${formatLocalDate(row.last_submitted_at)}` : "Nessuna lead ricevuta"}</p>
    `;
    summaryGrid.appendChild(card);
  }
}

function renderKpis(stats) {
  kpiTotal.textContent = String(stats.total_leads ?? 0);
  kpiLast24h.textContent = String(stats.leads_last_24h ?? 0);
  kpiLastSubmitted.textContent = stats.last_submitted_at ? formatLocalDate(stats.last_submitted_at) : "-";
  topFormsList.innerHTML = "";
  const topForms = stats.top_forms || [];
  if (!topForms.length) {
    const emptyItem = document.createElement("li");
    emptyItem.textContent = "Nessun dato disponibile";
    topFormsList.appendChild(emptyItem);
    return;
  }
  for (const row of topForms) {
    const item = document.createElement("li");
    item.innerHTML = `<strong>${escapeHtml(row.form_name || "unspecified")}</strong><span>${Number(row.total_leads || 0)} lead</span>`;
    topFormsList.appendChild(item);
  }
}

function formatAnswersHtml(answers) {
  if (!answers?.length) return "-";
  const normalizeQuestionKey = (rawKey) =>
    String(rawKey ?? "")
      .replace(/^answers\./, "")
      .replace(/\./g, " › ")
      .replace(/\[(\d+)\]/g, " #$1")
      .replace(/_/g, " ");
  const listItems = answers
    .map(
      (answer) =>
        `<li><code>${escapeHtml(normalizeQuestionKey(answer.question_key))}</code>: ${escapeHtml(answer.answer_value)}</li>`
    )
    .join("");
  return `
    <details class="answers-details">
      <summary>${answers.length} risposte</summary>
      <ul class="answers-list">${listItems}</ul>
    </details>
  `;
}

function renderLeads(items) {
  leadsBody.innerHTML = "";
  if (!items.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 8;
    cell.textContent = "Nessuna lead presente con i filtri correnti.";
    row.appendChild(cell);
    leadsBody.appendChild(row);
    return;
  }
  for (const item of items) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${escapeHtml(item.source_site || "-")}</td>
      <td>${escapeHtml(item.full_name || "-")}</td>
      <td>${escapeHtml(item.email || "-")}</td>
      <td>${escapeHtml(item.phone || "-")}</td>
      <td>${escapeHtml(item.company || "-")}</td>
      <td>${escapeHtml(item.message || "-")}</td>
      <td>${formatAnswersHtml(item.answers || [])}</td>
      <td>${item.submitted_at ? formatLocalDate(item.submitted_at) : "-"}</td>
    `;
    leadsBody.appendChild(row);
  }
}


async function loadSources() {
  const data = await getJson("/api/sources");
  const selectedSource = sourceFilter.value;
  sourceFilter.innerHTML = '<option value="">Tutte</option>';
  for (const source of data.sources || []) {
    const filterOption = document.createElement("option");
    filterOption.value = source;
    filterOption.textContent = source;
    sourceFilter.appendChild(filterOption);
  }
  sourceFilter.value = selectedSource || "";
}

async function loadDashboardStats() {
  const params = getFilters(false);
  const data = await getJson(`/api/dashboard-stats?${params.toString()}`);
  const stats = data.stats || {};
  renderKpis(stats);
  renderSummary(stats.summary || []);
}

async function loadLeads() {
  const params = getFilters(true);
  const data = await getJson(`/api/leads?${params.toString()}`);
  cachedLeads = data.items || [];
  const totalCount = Number(data.total_count ?? data.count ?? cachedLeads.length);
  leadsCount.textContent = `${cachedLeads.length} lead visualizzate su ${totalCount} totali`;
  renderLeads(cachedLeads);
}

async function refreshDashboard(successMessage = "Dashboard aggiornata.") {
  await Promise.all([loadDashboardStats(), loadLeads()]);
  setStatus(successMessage, "ok");
}

function answersToText(answers) {
  return (answers || [])
    .map((entry) => `${entry.question_key}: ${entry.answer_value}`)
    .join(" | ");
}

function csvEscape(value) {
  const text = String(value ?? "");
  if (/["\n,]/.test(text)) {
    return `"${text.replace(/"/g, "\"\"")}"`;
  }
  return text;
}

function exportCurrentLeadsToCsv() {
  if (!cachedLeads.length) {
    setStatus("Nessuna lead da esportare con i filtri correnti.", "warn");
    return;
  }
  const headers = [
    "id",
    "source_site",
    "form_name",
    "full_name",
    "email",
    "phone",
    "company",
    "message",
    "answer_count",
    "answers",
    "submitted_at",
  ];
  const lines = [headers.map(csvEscape).join(",")];
  for (const item of cachedLeads) {
    const row = [
      item.id,
      item.source_site,
      item.form_name,
      item.full_name,
      item.email,
      item.phone,
      item.company,
      item.message,
      item.answer_count,
      answersToText(item.answers),
      item.submitted_at,
    ];
    lines.push(row.map(csvEscape).join(","));
  }
  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `puma-leads-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.csv`;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
  setStatus("CSV esportato con successo.", "ok");
}

async function clearFiltersAndReload() {
  sourceFilter.value = "";
  searchInput.value = "";
  fromInput.value = "";
  toInput.value = "";
  limitSelect.value = "300";
  await refreshDashboard("Filtri resettati.");
}


async function initialize() {
  setStatus("Caricamento dashboard...", "info");
  try {
    await loadSources();
    await refreshDashboard("Pronto.");
  } catch (error) {
    setStatus(`Errore inizializzazione: ${error.message}`, "error");
  }
}

sourceFilter.addEventListener("change", () => {
  refreshDashboard().catch((error) => setStatus(`Errore filtro sorgente: ${error.message}`, "error"));
});

fromInput.addEventListener("change", () => {
  refreshDashboard().catch((error) => setStatus(`Errore filtro data: ${error.message}`, "error"));
});

toInput.addEventListener("change", () => {
  refreshDashboard().catch((error) => setStatus(`Errore filtro data: ${error.message}`, "error"));
});

limitSelect.addEventListener("change", () => {
  loadLeads()
    .then(() => setStatus("Limite aggiornato.", "ok"))
    .catch((error) => setStatus(`Errore aggiornamento limite: ${error.message}`, "error"));
});

searchInput.addEventListener("input", () => {
  if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
  searchDebounceTimer = window.setTimeout(() => {
    refreshDashboard().catch((error) => setStatus(`Errore filtro ricerca: ${error.message}`, "error"));
  }, 350);
});

refreshButton.addEventListener("click", () => {
  refreshDashboard().catch((error) => setStatus(`Errore aggiornamento: ${error.message}`, "error"));
});

clearFiltersButton.addEventListener("click", () => {
  clearFiltersAndReload().catch((error) => setStatus(`Errore reset filtri: ${error.message}`, "error"));
});

exportCsvButton.addEventListener("click", exportCurrentLeadsToCsv);

initialize().catch((error) => setStatus(`Errore avvio: ${error.message}`, "error"));
