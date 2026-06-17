const sourceFilter = document.getElementById("sourceFilter");
const refreshButton = document.getElementById("refreshButton");
const statusText = document.getElementById("statusText");
const summaryGrid = document.getElementById("summaryGrid");
const leadsBody = document.getElementById("leadsBody");
const leadsCount = document.getElementById("leadsCount");

const leadForm = document.getElementById("leadForm");
const leadSource = document.getElementById("leadSource");

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

    const title = document.createElement("h3");
    title.textContent = row.source_site;
    card.appendChild(title);

    const total = document.createElement("p");
    total.className = "summary-total";
    total.textContent = `${row.total_leads} lead`;
    card.appendChild(total);

    const last = document.createElement("p");
    last.className = "summary-time";
    last.textContent = row.last_submitted_at
      ? `Ultima: ${new Date(row.last_submitted_at).toLocaleString()}`
      : "Nessuna lead ricevuta";
    card.appendChild(last);

    summaryGrid.appendChild(card);
  }
}

function formatAnswersHtml(answers) {
  if (!answers?.length) {
    return "-";
  }
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
    <details class="answers-details" open>
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
    cell.textContent = "Nessuna lead presente.";
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
      <td>${item.submitted_at ? new Date(item.submitted_at).toLocaleString() : "-"}</td>
    `;
    leadsBody.appendChild(row);
  }
}

function formDataToPayload(formElement) {
  const formData = new FormData(formElement);
  const payload = {};

  for (const [key, rawValue] of formData.entries()) {
    const value = String(rawValue ?? "").trim();
    if (!value) {
      continue;
    }

    if (payload[key] === undefined) {
      payload[key] = value;
      continue;
    }

    if (Array.isArray(payload[key])) {
      payload[key].push(value);
      continue;
    }

    payload[key] = [payload[key], value];
  }

  return payload;
}

async function loadSources() {
  const data = await getJson("/api/sources");
  const selectedSource = sourceFilter.value;
  const selectedLeadSource = leadSource.value;

  sourceFilter.innerHTML = '<option value="">Tutte</option>';
  leadSource.innerHTML = "";

  for (const source of data.sources || []) {
    const filterOption = document.createElement("option");
    filterOption.value = source;
    filterOption.textContent = source;
    sourceFilter.appendChild(filterOption);

    const leadOption = document.createElement("option");
    leadOption.value = source;
    leadOption.textContent = source;
    leadSource.appendChild(leadOption);
  }

  sourceFilter.value = selectedSource || "";
  leadSource.value = selectedLeadSource || (data.sources?.[0] ?? "");
}

async function loadSummary() {
  const data = await getJson("/api/lead-summary");
  renderSummary(data.summary || []);
}

async function loadLeads() {
  const params = new URLSearchParams();
  params.set("limit", "1000");
  if (sourceFilter.value) {
    params.set("source_site", sourceFilter.value);
  }

  const data = await getJson(`/api/leads?${params.toString()}`);
  leadsCount.textContent = `${data.count} lead visualizzate`;
  renderLeads(data.items || []);
}

async function submitTestLead(event) {
  event.preventDefault();
  setStatus("Invio lead di test...", "info");

  const selectedSource = leadSource.value;
  const payload = formDataToPayload(leadForm);
  payload.source_site = selectedSource;
  payload.form_name = "manual-test-dashboard";

  try {
    const result = await getJson("/api/leads", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    setStatus(`Lead test salvata (${result.answer_count} risposte).`, "ok");
    leadForm.reset();
    leadSource.value = selectedSource;
    await loadSummary();
    await loadLeads();
  } catch (error) {
    setStatus(`Errore invio lead: ${error.message}`, "error");
  }
}

async function initialize() {
  setStatus("Caricamento...", "info");
  try {
    await loadSources();
    await loadSummary();
    await loadLeads();
    setStatus("Pronto.", "ok");
  } catch (error) {
    setStatus(`Errore inizializzazione: ${error.message}`, "error");
  }
}

sourceFilter.addEventListener("change", () => {
  loadLeads().catch((error) => setStatus(`Errore filtro: ${error.message}`, "error"));
});

refreshButton.addEventListener("click", () => {
  Promise.all([loadSummary(), loadLeads()])
    .then(() => setStatus("Tabella aggiornata.", "ok"))
    .catch((error) => setStatus(`Errore aggiornamento: ${error.message}`, "error"));
});

leadForm.addEventListener("submit", submitTestLead);

initialize().catch((error) => setStatus(`Errore avvio: ${error.message}`, "error"));