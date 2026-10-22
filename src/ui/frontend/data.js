/* ============================================================================
   COMPANIES HOUSE REFRESH, REGISTER INDEX SEARCH, TAB 6 "DATA & UPDATES"
   ============================================================================ */

let dataPanelTimer = null;

// Version shown in the top bar and footer comes from the server settings (single source)
fetch("/api/health")
  .then((r) => r.json())
  .then((h) => {
    const badge = document.getElementById("app-version-badge");
    const footer = document.getElementById("app-version-footer");
    if (badge && h.version) badge.textContent = `v${h.version}`;
    if (footer && h.version) footer.textContent = h.version;
  })
  .catch(() => {});

async function apiJson(url, options = {}) {
  const res = await fetch(url, options);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `HTTP ${res.status}`);
  return body;
}

function postJson(url, payload) {
  return apiJson(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload || {}),
  });
}

/* ---------- Companies House refresh from the dossier ---------- */

async function refreshCurrentCompany() {
  if (!currentCompanyNumber) return;
  await fetchFromCompaniesHouse(currentCompanyNumber);
}

async function fetchFromCompaniesHouse(companyNumber) {
  const btn = document.getElementById("ch-refresh-btn");
  const status = document.getElementById("center-status");
  if (btn) btn.disabled = true;
  if (status) status.textContent = `Downloading ${companyNumber} from Companies House…`;
  try {
    const res = await postJson(`/api/companies/${encodeURIComponent(companyNumber)}/refresh`);
    if (status) {
      status.textContent = `Companies House: ${res.officers} appointments (${res.active_officers} active), ${res.psc_statements} PSC statements — ${res.company_status || ""}`;
    }
    await loadCompanies();
    await selectCompany(res.company_number);
  } catch (err) {
    if (status) status.textContent = `Companies House: ${err.message}`;
  } finally {
    if (btn) btn.disabled = false;
  }
}

/* ---------- Search: companies only in the register index ---------- */

async function appendIndexMatches(q) {
  const container = document.getElementById("entity-list");
  if (!container || !q || q.trim().length < 2) return;
  let items = [];
  try {
    items = (await apiJson(`/api/index/search?q=${encodeURIComponent(q)}&limit=15`)).items || [];
  } catch (err) {
    return;
  }
  if (!items.length) return;
  if (container.textContent.includes("No matching companies found")) container.innerHTML = "";
  container.insertAdjacentHTML(
    "beforeend",
    `<div style="padding:8px 10px; font-size:11px; color:var(--text-secondary); border-top:1px solid var(--border-subtle);">
       In the UK register index, not imported yet — <strong>Fetch</strong> downloads it from Companies House
     </div>` +
      items
        .map(
          (c) => `
        <div class="entity-item">
          <div class="entity-item-top">
            <div class="entity-name">${escapeHtml(c.company_name)}</div>
            <button class="btn btn-sm" onclick="event.stopPropagation(); fetchFromCompaniesHouse('${escapeHtml(c.company_number)}')">Fetch</button>
          </div>
          <div class="entity-meta">
            <code>${escapeHtml(c.company_number)}</code><span>•</span>
            <span>${escapeHtml(c.company_status || "")}</span><span>•</span>
            <span>${escapeHtml(c.postcode || "N/A")}</span>
          </div>
        </div>`
        )
        .join("")
  );
}

/* ---------- Tab 6: Data & Updates ---------- */

async function loadDataPanel(checkRemote = false) {
  const container = document.getElementById("data-container");
  if (!container) return;
  let st;
  try {
    st = await apiJson(`/api/data/status?check_remote=${checkRemote}`);
  } catch (err) {
    container.innerHTML = `<div class="note"><strong>Error:</strong> ${escapeHtml(err.message)}</div>`;
    return;
  }
  container.innerHTML = renderDataPanel(st, checkRemote);

  clearTimeout(dataPanelTimer);
  const busy = (st.job && st.job.status === "running") || (st.stream && st.stream.running);
  if (busy && document.getElementById("view-data")?.classList.contains("active")) {
    dataPanelTimer = setTimeout(() => loadDataPanel(false), 4000);
  }
}

function renderDataPanel(st, checkedRemote) {
  const loc = st.location || {};
  const cfg = st.subset.config || {};
  const job = st.job;
  const stream = st.stream || {};

  const sourcesRows = (st.sources || [])
    .map((s) => {
      const latest = s.latest_version || (s.latest_error ? "error" : checkedRemote ? "—" : "not checked");
      const outdated = s.latest_version && s.local_version !== s.latest_version;
      return `<tr>
        <td><strong>${escapeHtml(s.title)}</strong><div style="font-size:10.5px; color:var(--text-secondary);">${escapeHtml(s.licence)} • ${escapeHtml(s.frequency)}</div></td>
        <td>${escapeHtml(s.local_version || "not downloaded")}</td>
        <td style="${outdated ? "color:var(--risk-critical); font-weight:700;" : ""}">${escapeHtml(latest)}</td>
        <td><button class="btn btn-sm" onclick="startDownload(['${s.key}'])">Download</button></td>
      </tr>`;
    })
    .join("");

  const reasons = Object.entries(st.subset.by_reason || {})
    .sort((a, b) => b[1] - a[1])
    .map(([k, v]) => `<span class="tech-tag">${escapeHtml(k)}: ${v.toLocaleString()}</span>`)
    .join(" ");

  const runsRows = (st.runs || [])
    .slice(0, 8)
    .map(
      (r) => `<tr><td>${escapeHtml(r.task)}</td><td>${escapeHtml(r.source_version || "")}</td>
        <td>${escapeHtml(r.status)}</td><td style="text-align:right;">${Number(r.rows_written).toLocaleString()}</td>
        <td>${escapeHtml((r.started_at || "").slice(0, 16))}</td></tr>`
    )
    .join("");

  const jobHtml = job
    ? `<div class="note" style="margin:0 0 12px 0;"><strong>${escapeHtml(job.kind)}:</strong> ${escapeHtml(job.status)}
        ${job.stage ? ` — ${escapeHtml(job.stage)} ${Number(job.progress || 0).toLocaleString()}` : ""}
        ${job.error ? `<div style="color:var(--risk-critical);">${escapeHtml(job.error)}</div>` : ""}</div>`
    : "";

  const streamRows = Object.entries(stream.streams || {})
    .map(
      ([k, v]) => `<tr><td>${escapeHtml(k)}</td><td>${v.connected ? "connected" : "idle"}</td>
        <td style="text-align:right;">${Number(v.events).toLocaleString()}</td><td style="text-align:right;">${Number(v.applied).toLocaleString()}</td>
        <td>${escapeHtml(String(v.timepoint ?? "—"))}</td><td>${escapeHtml((v.last_event_at || "").slice(0, 19))}</td>
        <td style="color:var(--risk-critical);">${escapeHtml(v.error || "")}</td></tr>`
    )
    .join("");

  const check = (key, label) =>
    `<label style="display:flex; gap:6px; align-items:center;"><input type="checkbox" id="subset-${key}" ${cfg[key] ? "checked" : ""}> ${label}</label>`;

  return `
    ${jobHtml}
    <div style="display:grid; grid-template-columns: 1fr 1fr; gap:14px;">
      <div class="dossier-card">
        <h3><span>Data folder</span><button class="btn btn-sm" onclick="openHelp('data-and-updates')">?</button></h3>
        <div class="kv-grid">
          <div class="kv-key">Folder</div><div class="kv-val"><code>${escapeHtml(loc.path || "")}</code></div>
          <div class="kv-key">Set by</div><div class="kv-val">${escapeHtml(loc.origin || "")}</div>
          <div class="kv-key">Database</div><div class="kv-val">${escapeHtml(String(loc.database_gb ?? 0))} GB</div>
          <div class="kv-key">Free space</div><div class="kv-val">${escapeHtml(String(loc.free_gb ?? "?"))} GB</div>
        </div>
        <div style="display:flex; gap:6px; margin-top:10px;">
          <input type="text" id="data-location-input" class="input-field" placeholder="New folder, e.g. D:\\AethelburgData" style="flex:1;">
          <label style="display:flex; gap:4px; align-items:center; font-size:11.5px;"><input type="checkbox" id="data-location-move" checked> copy data</label>
          <button class="btn btn-sm" onclick="changeDataLocation()">Change</button>
        </div>
        <div id="data-location-result" style="font-size:11.5px; margin-top:6px;"></div>
      </div>

      <div class="dossier-card">
        <h3><span>Subset imported in full</span><span class="badge-pill">${Number(st.subset.members).toLocaleString()} companies</span></h3>
        <div style="font-size:11.5px; color:var(--text-secondary); margin-bottom:6px;">
          Register index: <strong>${Number(st.index_rows).toLocaleString()}</strong> companies searchable; the subset below also gets PSC and FT3 scoring.
        </div>
        <div style="display:flex; flex-wrap:wrap; gap:4px; margin-bottom:8px;">${reasons || "<em>No import yet</em>"}</div>
        <div style="display:grid; grid-template-columns:1fr 1fr; gap:4px 12px; font-size:12px;">
          ${check("risk_links", "Risk links (sanctions, ICIJ, foreign/offshore PSC)")}
          ${check("risk_links_one_hop", "+ one hop via shared controllers")}
          ${check("mass_address", "Mass registration addresses")}
          <label>min companies <input type="number" id="subset-mass_address_min_companies" class="input-field" style="width:70px;" value="${cfg.mass_address_min_companies}"></label>
          ${check("recent", "Recent incorporations")}
          <label>last <input type="number" id="subset-recent_years" class="input-field" style="width:55px;" value="${cfg.recent_years}"> years</label>
          <label>combine the two:
            <select id="subset-broad_criteria_mode" class="input-field" style="width:auto;">
              <option value="and" ${cfg.broad_criteria_mode === "and" ? "selected" : ""}>both (recent AND mass address)</option>
              <option value="or" ${cfg.broad_criteria_mode === "or" ? "selected" : ""}>either (OR)</option>
            </select></label>
          ${check("broad_criteria_active_only", "Broad criteria: live companies only")}
          <label style="grid-column:1 / span 2;">PSC nationalities
            <input type="text" id="subset-psc_nationalities" class="input-field" style="width:60%;"
                   value="${escapeHtml((cfg.psc_nationalities || []).join(", "))}" placeholder="e.g. Italian, Maltese (empty = off)"></label>
        </div>
        <div style="display:flex; gap:6px; margin-top:10px;">
          <button class="btn btn-sm" onclick="saveSubsetConfig()">Save filters</button>
          <button class="btn btn-sm btn-primary" onclick="startImport()">Run import</button>
        </div>
      </div>
    </div>

    <div class="dossier-card" style="margin-top:14px;">
      <h3><span>Bulk sources</span>
        <span style="display:flex; gap:6px;">
          <button class="btn btn-sm" onclick="loadDataPanel(true)">Check for new releases</button>
          <button class="btn btn-sm btn-primary" onclick="startDownload(null)">Download all</button>
        </span></h3>
      <table class="matrix-table" style="width:100%;">
        <thead><tr><th>Source</th><th>On disk</th><th>Latest available</th><th></th></tr></thead>
        <tbody>${sourcesRows}</tbody>
      </table>
    </div>

    <div class="dossier-card" style="margin-top:14px;">
      <h3><span>Live updates (Companies House Streaming API)</span>
        <span style="display:flex; gap:6px;">
          <button class="btn btn-sm btn-primary" onclick="streamAction('start')" ${stream.running ? "disabled" : ""}>Start</button>
          <button class="btn btn-sm" onclick="streamAction('stop')" ${stream.running ? "" : "disabled"}>Stop</button>
        </span></h3>
      ${stream.configured ? "" : `<div class="note" style="margin:0 0 8px 0;"><strong>No streaming key.</strong> Create a <em>Streaming</em> key on developer.company-information.service.gov.uk and store it with <code>python -m keyring set aethelburg ch_streaming_key</code>.</div>`}
      <div id="stream-result" style="font-size:11.5px; color:var(--risk-critical);"></div>
      <table class="matrix-table" style="width:100%;">
        <thead><tr><th>Stream</th><th>State</th><th>Events</th><th>Applied</th><th>Timepoint</th><th>Last event</th><th>Error</th></tr></thead>
        <tbody>${streamRows}</tbody>
      </table>
    </div>

    <div class="dossier-card" style="margin-top:14px;">
      <h3><span>Recent import runs</span></h3>
      <table class="matrix-table" style="width:100%;">
        <thead><tr><th>Task</th><th>Release</th><th>Status</th><th>Rows</th><th>Started (UTC)</th></tr></thead>
        <tbody>${runsRows || `<tr><td colspan="5"><em>None yet</em></td></tr>`}</tbody>
      </table>
    </div>`;
}

async function startDownload(sources) {
  try {
    await postJson("/api/data/download", { sources });
  } catch (err) {
    alertInPanel(err.message);
  }
  loadDataPanel();
}

async function startImport() {
  try {
    await postJson("/api/data/import");
  } catch (err) {
    alertInPanel(err.message);
  }
  loadDataPanel();
}

async function saveSubsetConfig() {
  const payload = {};
  ["risk_links", "risk_links_one_hop", "mass_address", "recent", "broad_criteria_active_only"].forEach((k) => {
    payload[k] = document.getElementById(`subset-${k}`)?.checked || false;
  });
  payload.mass_address_min_companies = Number(document.getElementById("subset-mass_address_min_companies")?.value || 50);
  payload.recent_years = Number(document.getElementById("subset-recent_years")?.value || 3);
  payload.broad_criteria_mode = document.getElementById("subset-broad_criteria_mode")?.value || "and";
  payload.psc_nationalities = (document.getElementById("subset-psc_nationalities")?.value || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  await postJson("/api/data/subset", payload);
  loadDataPanel();
}

async function changeDataLocation() {
  const path = document.getElementById("data-location-input")?.value?.trim();
  const move = document.getElementById("data-location-move")?.checked || false;
  const out = document.getElementById("data-location-result");
  if (!path) return;
  try {
    const res = await postJson("/api/data/location", { path, move });
    if (out) out.innerHTML = `Saved. <strong>Restart Aethelburg</strong> to use <code>${escapeHtml(res.target)}</code>${move ? " (data copied; the old folder was kept)" : ""}.`;
  } catch (err) {
    if (out) out.innerHTML = `<span style="color:var(--risk-critical);">${escapeHtml(err.message)}</span>`;
  }
}

async function streamAction(action) {
  try {
    await postJson(`/api/data/stream/${action}`);
  } catch (err) {
    const out = document.getElementById("stream-result");
    if (out) out.textContent = err.message;
    return;
  }
  loadDataPanel();
}

function alertInPanel(message) {
  const container = document.getElementById("data-container");
  if (container) container.insertAdjacentHTML("afterbegin", `<div class="note"><strong>Error:</strong> ${escapeHtml(message)}</div>`);
}
