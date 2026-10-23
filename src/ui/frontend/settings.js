/* ============================================================================
   TAB 7 "SETTINGS": COMPANIES HOUSE KEYS (SAVED IN THE DATABASE), DAILY UPDATE, BACKUPS
   ============================================================================ */

const KEY_FIELDS = {
  api_key: { title: "REST API key", type: "REST", use: "company profiles, officers, PSC, filing history, documents" },
  streaming_key: { title: "Streaming key", type: "Streaming", use: "live updates in Data & Updates" },
};
const KEY_SOURCES = {
  database: "saved here (database)",
  keyring: "system keyring",
  environment: "environment variable (wins over this page)",
};

async function loadSettingsPanel() {
  const container = document.getElementById("settings-container");
  if (!container) return;
  try {
    container.innerHTML = renderSettingsPanel(await apiJson("/api/settings"));
  } catch (err) {
    container.innerHTML = `<div class="note"><strong>Error:</strong> ${escapeHtml(err.message)}</div>`;
  }
}

function renderSettingsPanel(st) {
  const keys = st.ch_keys || {};
  const keyRows = Object.entries(KEY_FIELDS)
    .map(([field, info]) => {
      const k = keys[field] || {};
      const state = k.configured
        ? `<span style="color:var(--risk-low, green); font-weight:700;">set</span> <code>${escapeHtml(k.hint || "")}</code> <span style="color:var(--text-secondary);">— ${escapeHtml(KEY_SOURCES[k.source] || k.source || "")}</span>`
        : `<span style="color:var(--risk-critical); font-weight:700;">not set</span>`;
      return `<div class="kv-key">${escapeHtml(info.title)}<div style="font-size:10.5px; color:var(--text-secondary);">${escapeHtml(info.use)}</div></div>
        <div class="kv-val">
          <div style="margin-bottom:4px;">${state} <span id="key-test-${field}" style="margin-left:6px;"></span></div>
          <div style="display:flex; gap:6px;">
            <input type="password" id="key-input-${field}" class="input-field" style="flex:1;" autocomplete="off" spellcheck="false"
                   placeholder="Paste a ${escapeHtml(info.type)} key to ${k.configured ? "replace the saved one" : "save it"}">
            ${k.source === "database" ? `<button class="btn btn-sm" onclick="removeChKey('${field}')">Remove</button>` : ""}
          </div>
        </div>`;
    })
    .join("");
  const daily = st.daily || {};
  const loc = st.location || {};
  return `
    <div class="dossier-card">
      <h3><span>Companies House keys</span><button class="btn btn-sm" onclick="openHelp('companies-house-api')">?</button></h3>
      <div style="font-size:11.5px; color:var(--text-secondary); margin-bottom:8px;">
        Create the keys on <a href="https://developer.company-information.service.gov.uk/manage-applications" target="_blank" rel="noopener">developer.company-information.service.gov.uk</a>:
        one application, one key of type <em>REST</em> and one of type <em>Streaming</em>. Use the <em>Copy</em> link next to each key and paste it once.
        Keys are saved in the database on this computer and take effect at once; the page never shows them again, only their last four characters.
      </div>
      <div class="kv-grid">${keyRows}</div>
      <div style="display:flex; gap:6px; margin-top:10px;">
        <button class="btn btn-sm btn-primary" onclick="saveChKeys()">Save keys</button>
        <button class="btn btn-sm" onclick="testChKeys(this)">Test with Companies House</button>
      </div>
      <div id="keys-result" style="font-size:11.5px; margin-top:6px;"></div>
    </div>

    <div class="dossier-card" style="margin-top:14px;">
      <h3><span>Daily update</span></h3>
      <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap; font-size:12px;">
        <label><input type="checkbox" id="settings-daily-enabled" ${daily.enabled ? "checked" : ""}> run every day at</label>
        <input type="text" id="settings-daily-time" class="input-field" style="width:70px;" value="${escapeHtml(daily.time || "06:00")}">
        <label title="Latest accounts and confirmation statement PDFs of the 50 highest-risk flagged companies"><input type="checkbox" id="settings-daily-documents" ${daily.documents ? "checked" : ""}> also download latest documents</label>
        <button class="btn btn-sm" onclick="saveSettingsDaily()">Save</button>
      </div>
      <div style="font-size:11px; color:var(--text-secondary); margin-top:4px;">Downloads new releases, imports only if something changed (with a backup first), then fetches officers of up to 500 flagged companies. Runs while Aethelburg is open; <em>Run now</em> is in Data &amp; Updates.</div>
      <div id="daily-result" style="font-size:11.5px; margin-top:6px;"></div>
    </div>

    <div class="dossier-card" style="margin-top:14px;">
      <h3><span>Backups</span></h3>
      <div style="display:flex; gap:8px; align-items:center; font-size:12px;">
        Keep the newest <input type="number" id="settings-backup-keep" class="input-field" style="width:60px;" min="1" max="50" value="${Number(st.backup_keep || 7)}"> backups
        <button class="btn btn-sm" onclick="saveSettingsGeneral()">Save</button>
        <span id="general-result"></span>
      </div>
      <div style="font-size:11px; color:var(--text-secondary); margin-top:4px;">Each backup is a full copy of the database, saved keys included: keep the data folder private.</div>
    </div>

    <div class="dossier-card" style="margin-top:14px;">
      <h3><span>Risk scoring</span></h3>
      <div style="display:flex; gap:8px; align-items:center; font-size:12px; flex-wrap:wrap;">
        Co-registration hub (FT3-SC-001) from <input type="number" id="settings-mass-address" class="input-field" style="width:80px;" min="5" max="100000" value="${Number(st.mass_address_threshold || 20)}"> companies at one address
        <button class="btn btn-sm" onclick="saveSettingsGeneral()">Save</button>
      </div>
      <div style="font-size:11px; color:var(--text-secondary); margin-top:4px;">A shared address is context, not evidence: it adds 10 points (6 for agents with thousands of companies) and never flags a company on its own. Applied at the next scoring run (Data &amp; Updates → Re-score).</div>
    </div>

    <div class="dossier-card" style="margin-top:14px;">
      <h3><span>Where things are</span></h3>
      <div class="kv-grid">
        <div class="kv-key">Data folder</div><div class="kv-val"><code>${escapeHtml(loc.path || "")}</code> <span style="color:var(--text-secondary);">(change it in Data &amp; Updates)</span></div>
        <div class="kv-key">Database</div><div class="kv-val"><code>${escapeHtml(st.database || "")}</code></div>
        <div class="kv-key">User settings file</div><div class="kv-val"><code>${escapeHtml(st.config_file || "")}</code></div>
        <div class="kv-key">Version</div><div class="kv-val">${escapeHtml(st.version || "")}</div>
      </div>
    </div>`;
}

function showSettingsResult(id, html, isError = false) {
  const el = document.getElementById(id);
  if (el) el.innerHTML = `<span style="color:${isError ? "var(--risk-critical)" : "var(--text-primary)"};">${html}</span>`;
}

async function saveChKeys() {
  const payload = {};
  for (const field of Object.keys(KEY_FIELDS)) {
    const value = document.getElementById(`key-input-${field}`)?.value.trim();
    if (value) payload[field] = value;
  }
  if (!Object.keys(payload).length) {
    showSettingsResult("keys-result", "Paste a key first.", true);
    return;
  }
  await submitChKeys(payload, "Saved.");
}

async function removeChKey(field) {
  await submitChKeys({ [field]: "" }, `${KEY_FIELDS[field].title} removed.`);
}

async function submitChKeys(payload, okText) {
  try {
    const res = await postJson("/api/settings/ch-keys", payload);
    await loadSettingsPanel();
    const overridden = (res.overridden_by_environment || []).map((f) => KEY_FIELDS[f].title);
    showSettingsResult(
      "keys-result",
      escapeHtml(okText) + (overridden.length ? ` Note: ${escapeHtml(overridden.join(", "))} is set by an environment variable, which is used instead.` : " Use Test to check them with Companies House.")
    );
  } catch (err) {
    showSettingsResult("keys-result", escapeHtml(err.message), true);
  }
}

async function testChKeys(btn) {
  if (btn) btn.disabled = true;
  showSettingsResult("keys-result", "Asking Companies House…");
  try {
    const res = await postJson("/api/settings/ch-keys/test");
    for (const [field, r] of Object.entries(res)) {
      const el = document.getElementById(`key-test-${field}`);
      if (el) el.innerHTML = `<span style="color:${r.ok ? "var(--risk-low, green)" : "var(--risk-critical)"};">${r.ok ? "✓" : "✗"} ${escapeHtml(r.message)}</span>`;
    }
    showSettingsResult("keys-result", "");
  } catch (err) {
    showSettingsResult("keys-result", escapeHtml(err.message), true);
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function saveSettingsDaily() {
  try {
    const res = await postJson("/api/data/daily", {
      enabled: document.getElementById("settings-daily-enabled")?.checked || false,
      time: document.getElementById("settings-daily-time")?.value || "06:00",
      documents: document.getElementById("settings-daily-documents")?.checked || false,
    });
    showSettingsResult("daily-result", res.enabled ? `Saved: every day at ${escapeHtml(res.time)}.` : "Saved: daily update off.");
  } catch (err) {
    showSettingsResult("daily-result", escapeHtml(err.message), true);
  }
}

async function saveSettingsGeneral() {
  const keep = Number(document.getElementById("settings-backup-keep")?.value || 7);
  const hub = Number(document.getElementById("settings-mass-address")?.value || 20);
  try {
    await postJson("/api/settings/general", { backup_keep: keep, mass_address_threshold: hub });
    showSettingsResult("general-result", "Saved.");
  } catch (err) {
    showSettingsResult("general-result", escapeHtml(err.message), true);
  }
}
