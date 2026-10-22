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

/* ---------- Companies House officer search (whole register, via the REST API) ---------- */

async function searchChOfficers(q) {
  const box = document.getElementById("ch-officer-results");
  if (!box) return;
  box.innerHTML = `<div style="padding:8px 10px; font-size:11.5px;">Searching Companies House for “${escapeHtml(q)}”…</div>`;
  let items = [];
  try {
    items = (await apiJson(`/api/ch/officers/search?q=${encodeURIComponent(q)}`)).items || [];
  } catch (err) {
    box.innerHTML = `<div style="padding:8px 10px; color:var(--risk-critical); font-size:11.5px;">${escapeHtml(err.message)}</div>`;
    return;
  }
  const dob = (d) => (d && d.year ? ` • born ${d.month ? String(d.month).padStart(2, "0") + "/" : ""}${d.year}` : "");
  box.innerHTML = items.length
    ? items
        .map(
          (o) => `<div class="entity-item" style="cursor:default;">
            <div class="entity-item-top"><div class="entity-name">${escapeHtml(o.name)}</div>
              <button class="btn btn-sm" onclick="showOfficerAppointments('${escapeHtml(o.officer_id)}', this)">${o.appointment_count || "?"} appointments</button></div>
            <div class="entity-meta"><span>${escapeHtml((o.address || "").slice(0, 70))}${escapeHtml(dob(o.date_of_birth))}</span></div>
            <div class="officer-appointments"></div>
          </div>`
        )
        .join("")
    : `<div style="padding:8px 10px; font-size:11.5px;">No officer on the UK register has every word of “${escapeHtml(q)}” in the name.</div>`;
}

async function showOfficerAppointments(officerId, btn) {
  const target = btn.closest(".entity-item").querySelector(".officer-appointments");
  target.innerHTML = `<div style="font-size:11px;">Loading…</div>`;
  try {
    const res = await apiJson(`/api/ch/officers/${encodeURIComponent(officerId)}/appointments`);
    target.innerHTML = res.appointments
      .map(
        (a) => `<div style="font-size:11px; padding:3px 0; border-top:1px dashed var(--border-subtle);">
          <strong>${escapeHtml(a.company_name || "")}</strong> <code>${escapeHtml(a.company_number || "")}</code> — ${escapeHtml(a.role || "")}
          ${escapeHtml(a.appointed_on || "?")} → ${escapeHtml(a.resigned_on || "today")} • ${escapeHtml(a.company_status || "")}
          ${a.nationality ? " • " + escapeHtml(a.nationality) : ""}
          <button class="btn btn-sm" onclick="fetchFromCompaniesHouse('${escapeHtml(a.company_number)}')">Fetch</button>
        </div>`
      )
      .join("");
  } catch (err) {
    target.innerHTML = `<div style="color:var(--risk-critical); font-size:11px;">${escapeHtml(err.message)}</div>`;
  }
}

/* ---------- Search: people (PSC controllers and officers) ---------- */

async function appendPersonMatches(q) {
  const container = document.getElementById("entity-list");
  if (!container || !q || q.trim().length < 3) return;
  let people = [];
  try {
    people = (await apiJson(`/api/persons/search?q=${encodeURIComponent(q)}&limit=10`)).items || [];
  } catch (err) {
    return;
  }
  container.insertAdjacentHTML(
    "afterbegin",
    `<div style="padding:6px 10px; border-bottom:1px solid var(--border-subtle);">
       <button class="btn btn-sm" onclick="searchChOfficers(${JSON.stringify(q).replace(/"/g, "&quot;")})"
               title="Search every officer on the UK register (Companies House API, REST key needed)">Search officers on Companies House</button>
       <div id="ch-officer-results"></div>
     </div>`
  );
  if (!people.length) return;
  if (container.textContent.includes("No matching companies found")) container.innerHTML = "";
  const dob = (p) => (p.dob_year ? ` • born ${p.dob_month ? String(p.dob_month).padStart(2, "0") + "/" : ""}${p.dob_year}` : "");
  container.insertAdjacentHTML(
    "afterbegin",
    `<div style="padding:8px 10px; font-size:11px; color:var(--text-secondary); border-bottom:1px solid var(--border-subtle);">
       People matching “${escapeHtml(q)}” — PSC controllers and officers, with their companies
     </div>` +
      people
        .map(
          (p) => `
        <div class="entity-item" style="cursor:default;">
          <div class="entity-item-top"><div class="entity-name">${escapeHtml(p.name)}</div></div>
          <div class="entity-meta"><span>${escapeHtml(p.nationality || "nationality n/a")}${escapeHtml(dob(p))}${p.country_of_residence ? " • lives in " + escapeHtml(p.country_of_residence) : ""}</span></div>
          <div style="margin-top:5px; display:flex; gap:4px; flex-wrap:wrap;">
            ${(p.companies || [])
              .map(
                (c) => `<span class="tech-tag" style="cursor:pointer;" title="${escapeHtml(c.role)} • ${escapeHtml(c.company_status || "")}"
                   onclick="selectCompany('${escapeHtml(c.company_number)}')">${escapeHtml(c.company_name)}</span>`
              )
              .join("") || "<em>no imported company</em>"}
          </div>
        </div>`
        )
        .join("")
  );
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

let releasesCheckedThisSession = false;

async function loadDataPanel(checkRemote = false) {
  const container = document.getElementById("data-container");
  if (!container) return;
  // first visit of the tab: ask publishers for their latest release (cached 10 min on the server)
  if (!releasesCheckedThisSession) {
    checkRemote = true;
    releasesCheckedThisSession = true;
  }
  let st;
  try {
    st = await apiJson(`/api/data/status?check_remote=${checkRemote}`);
  } catch (err) {
    container.innerHTML = `<div class="note"><strong>Error:</strong> ${escapeHtml(err.message)}</div>`;
    return;
  }
  container.innerHTML = renderDataPanel(st, checkRemote);
  loadChanges();

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

  const jobRunning = !!(job && job.status === "running");
  const sourcesRows = (st.sources || [])
    .map((s) => {
      const latest = s.latest_version || (s.latest_error ? "could not check" : "not checked");
      const upToDate = s.latest_version && s.local_version === s.latest_version;
      const outdated = s.latest_version && s.local_version !== s.latest_version;
      let button;
      if (jobRunning) button = `<button class="btn btn-sm" disabled title="Wait for the running task">Busy</button>`;
      else if (upToDate) button = `<button class="btn btn-sm" disabled title="The latest release is already on disk">Up to date</button>`;
      else if (outdated) button = `<button class="btn btn-sm btn-primary" onclick="startDownload(['${s.key}'])">Download ${escapeHtml(s.latest_version)}</button>`;
      else button = `<button class="btn btn-sm" onclick="startDownload(['${s.key}'])">Download latest</button>`;
      return `<tr>
        <td><strong>${escapeHtml(s.title)}</strong><div style="font-size:10.5px; color:var(--text-secondary);">${escapeHtml(s.licence)} • ${escapeHtml(s.frequency)}</div></td>
        <td>${escapeHtml(s.local_version || "not downloaded")}</td>
        <td style="${outdated ? "color:var(--risk-critical); font-weight:700;" : ""}" title="${escapeHtml(s.latest_error || (s.checked_at ? "checked " + s.checked_at.slice(0, 16) + " UTC" : ""))}">${escapeHtml(latest)}${upToDate ? " ✓" : ""}</td>
        <td>${button}</td>
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

  const jobHtml = job ? renderJob(job) : "";

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
          <button class="btn btn-sm" id="check-releases-btn" onclick="checkReleases(this)" ${jobRunning ? "disabled" : ""}>Check for new releases</button>
          <button class="btn btn-sm btn-primary" onclick="startDownload(null)" ${jobRunning ? "disabled" : ""}>Download all new</button>
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
      <h3><span>Daily update &amp; officers</span></h3>
      <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap; font-size:12px;">
        <label><input type="checkbox" id="daily-enabled" ${st.daily && st.daily.enabled ? "checked" : ""}> run every day at</label>
        <input type="text" id="daily-time" class="input-field" style="width:70px;" value="${escapeHtml((st.daily && st.daily.time) || "06:00")}">
        <button class="btn btn-sm" onclick="saveDaily()">Save</button>
        <button class="btn btn-sm btn-primary" onclick="runDailyNow()" ${jobRunning ? "disabled" : ""}>Run now</button>
        <span style="color:var(--text-secondary);">last run: ${escapeHtml((st.daily && st.daily.last_run) || "never")}</span>
      </div>
      <div style="font-size:11px; color:var(--text-secondary); margin:4px 0 10px 0;">Downloads new releases (the PSC snapshot is daily), imports only if something changed (with a backup first), then fetches officers of up to 500 flagged companies. Works while Aethelburg is open; see the guide for Windows Task Scheduler.</div>
      <div style="display:flex; gap:8px; align-items:center; font-size:12px;">
        Officers (API, ~7,000 companies/hour):
        <select id="officers-scope" class="input-field" style="width:auto;">
          <option value="flagged">flagged companies</option><option value="case">companies in the active case</option><option value="subset">whole subset</option>
        </select>
        <button class="btn btn-sm" onclick="fetchOfficers()" ${jobRunning ? "disabled" : ""}>Fetch officers</button>
        <span id="officers-result"></span>
      </div>
    </div>

    <div class="dossier-card" style="margin-top:14px;">
      <h3><span>Backups</span><button class="btn btn-sm btn-primary" onclick="backupNow()" ${jobRunning ? "disabled" : ""}>Back up now</button></h3>
      <div style="font-size:11.5px; color:var(--text-secondary); margin-bottom:6px;">A backup is made automatically before every import; the newest 7 are kept in the <code>backups</code> sub-folder of the data folder.</div>
      <table class="matrix-table" style="width:100%;">
        <thead><tr><th>Backup</th><th>Size</th><th>Created</th><th></th></tr></thead>
        <tbody>${(st.backups || []).map((b) => `<tr><td><code>${escapeHtml(b.name)}</code></td><td>${b.gb} GB</td><td>${escapeHtml(b.created.replace("T", " "))}</td>
          <td><button class="btn btn-sm" onclick="restoreBackup('${escapeHtml(b.name)}')">Restore</button></td></tr>`).join("") || `<tr><td colspan="4"><em>No backups yet</em></td></tr>`}</tbody>
      </table>
      <div id="backup-result" style="font-size:11.5px; margin-top:6px;"></div>
    </div>

    <div class="dossier-card" style="margin-top:14px;">
      <h3><span>Recent changes</span>
        <span style="display:flex; gap:6px; align-items:center;">
          <select id="changes-type" class="input-field" style="width:auto;" onchange="loadChanges()"><option value="">all types</option></select>
          <label style="font-size:11.5px;"><input type="checkbox" id="changes-subset" onchange="loadChanges()"> subset only</label>
          <a class="btn btn-sm" id="changes-csv" href="/api/data/changes?format=csv">CSV</a>
        </span></h3>
      <div style="font-size:11.5px; color:var(--text-secondary); margin-bottom:6px;">What an update changed in companies already in the database (address, status, name, SIC, filings, charges, officers, PSC). The first load of a company is not a change.</div>
      <div id="changes-list"><em>Loading…</em></div>
    </div>

    <div class="dossier-card" style="margin-top:14px;">
      <h3><span>Recent import runs</span></h3>
      <table class="matrix-table" style="width:100%;">
        <thead><tr><th>Task</th><th>Release</th><th>Status</th><th>Rows</th><th>Started (UTC)</th></tr></thead>
        <tbody>${runsRows || `<tr><td colspan="5"><em>None yet</em></td></tr>`}</tbody>
      </table>
    </div>`;
}

function formatBytes(n) {
  if (n == null) return "";
  if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toFixed(2)} GB`;
  return `${Math.round(n / 1024 ** 2).toLocaleString()} MB`;
}

const JOB_TITLES = { download: "Download", import: "Import", officers: "Officers", daily: "Daily update", backup: "Backup" };

function renderJob(job) {
  const title = JOB_TITLES[job.kind] || job.kind;
  let body = "";
  if (job.status === "running") {
    if (job.kind === "download" && job.stage) {
      const pct = job.total ? ` (${Math.floor((job.progress * 100) / job.total)}%)` : "";
      body = `downloading <strong>${escapeHtml(job.stage)}</strong>: ${formatBytes(job.progress)}${job.total ? " of " + formatBytes(job.total) : ""}${pct}`;
    } else if (job.stage) {
      body = `${escapeHtml(job.stage)}: ${Number(job.progress || 0).toLocaleString()}`;
    } else {
      body = "starting…";
    }
  } else if (job.status === "failed") {
    body = `<span style="color:var(--risk-critical);">failed — ${escapeHtml(job.error || "unknown error")}</span>`;
  } else if (job.kind === "download" && Array.isArray(job.result)) {
    body = job.result
      .map((r) =>
        r.status === "already-downloaded"
          ? `${escapeHtml(r.title)}: already up to date (release ${escapeHtml(r.version)}), nothing to download`
          : `${escapeHtml(r.title)}: downloaded release ${escapeHtml(r.version)} (${formatBytes(r.bytes)})`
      )
      .join("<br>");
  } else {
    body = "completed";
  }
  const when = (job.finished_at || job.started_at || "").slice(11, 19);
  return `<div class="note" style="margin:0 0 12px 0;"><strong>${escapeHtml(title)}</strong> ${when ? `<span style="color:var(--text-secondary);">(${when} UTC)</span>` : ""}<div>${body}</div></div>`;
}

async function checkReleases(btn) {
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Checking publishers…";
  }
  await loadDataPanel(true);
}

async function saveDaily() {
  await postJson("/api/data/daily", {
    enabled: document.getElementById("daily-enabled")?.checked || false,
    time: document.getElementById("daily-time")?.value || "06:00",
  }).catch((err) => alertInPanel(err.message));
  loadDataPanel();
}

async function runDailyNow() {
  await postJson("/api/data/daily/run").catch((err) => alertInPanel(err.message));
  loadDataPanel();
}

async function fetchOfficers() {
  const scope = document.getElementById("officers-scope")?.value || "flagged";
  try {
    const res = await postJson("/api/data/officers", { scope });
    const out = document.getElementById("officers-result");
    if (out) out.textContent = `${res.companies.toLocaleString()} companies, about ${res.hours} h`;
  } catch (err) {
    alertInPanel(err.message);
  }
  loadDataPanel();
}

async function backupNow() {
  try {
    await postJson("/api/data/backups");
  } catch (err) {
    alertInPanel(err.message);
  }
  loadDataPanel();
}

async function restoreBackup(name) {
  const out = document.getElementById("backup-result");
  // destructive: the current database is replaced (a safety backup is made first)
  if (!window.confirm(`Replace the current database with ${name}?\nA backup of the current database is made first.`)) return;
  try {
    const res = await postJson(`/api/data/backups/${encodeURIComponent(name)}/restore`);
    if (out) out.innerHTML = `Restored <code>${escapeHtml(res.restored)}</code>. Previous database saved as <code>${escapeHtml(res.safety_backup)}</code>. <strong>Restart Aethelburg.</strong>`;
  } catch (err) {
    if (out) out.innerHTML = `<span style="color:var(--risk-critical);">${escapeHtml(err.message)}</span>`;
  }
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

let changesFilter = { type: "", subset: false };

async function loadChanges() {
  const list = document.getElementById("changes-list");
  if (!list) return;
  const typeSel = document.getElementById("changes-type");
  const subsetBox = document.getElementById("changes-subset");
  // the panel is redrawn every few seconds while a job runs: keep the chosen filter across redraws
  if (typeSel && typeSel.options.length > 1) changesFilter = { type: typeSel.value, subset: subsetBox.checked };
  const params = new URLSearchParams({ limit: "50", subset_only: String(changesFilter.subset) });
  if (changesFilter.type) params.set("change_type", changesFilter.type);
  let res;
  try {
    res = await apiJson(`/api/data/changes?${params}`);
  } catch (err) {
    list.innerHTML = `<div class="note"><strong>Error:</strong> ${escapeHtml(err.message)}</div>`;
    return;
  }
  if (typeSel) {
    typeSel.innerHTML = `<option value="">all types</option>` + res.types
      .map((t) => `<option value="${t}" ${t === changesFilter.type ? "selected" : ""}>${t} (${(res.counts[t] || 0).toLocaleString()})</option>`)
      .join("");
    subsetBox.checked = changesFilter.subset;
  }
  const csv = document.getElementById("changes-csv");
  if (csv) {
    params.delete("limit");
    params.set("format", "csv");
    csv.href = `/api/data/changes?${params}`;
  }
  list.innerHTML = res.items.length
    ? `<table class="matrix-table" style="width:100%;">
        <thead><tr><th>Observed</th><th>Company</th><th>Change</th><th>Old</th><th>New</th><th>Source</th></tr></thead>
        <tbody>${res.items.map((c) => `<tr>
          <td><code>${escapeHtml(c.observed_at.slice(0, 16).replace("T", " "))}</code></td>
          <td><a href="#" onclick="selectCompany('${escapeHtml(c.company_number)}'); return false;">${escapeHtml(c.company_number)}</a> ${escapeHtml(c.company_name || "")}</td>
          <td><span class="tech-tag">${escapeHtml(c.change_type)}</span>${c.effective_date ? `<br><small>${escapeHtml(c.effective_date)}</small>` : ""}</td>
          <td>${escapeHtml(c.old_value || "")}</td><td>${escapeHtml(c.new_value || "")}</td>
          <td style="font-size:11px;">${escapeHtml(c.source || "")}</td></tr>`).join("")}</tbody>
      </table>`
    : `<em>No changes recorded yet: they appear after the next import, streaming event or "Update from CH" of a company already loaded.</em>`;
}

function alertInPanel(message) {
  const container = document.getElementById("data-container");
  if (container) container.insertAdjacentHTML("afterbegin", `<div class="note"><strong>Error:</strong> ${escapeHtml(message)}</div>`);
}
