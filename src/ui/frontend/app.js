/**
 * Aethelburg v0.3.0-beta.1 — Frontend Application Controller
 *
 * Implements:
 *   1. OpenStreetMap Geospatial Intelligence (100% Free, ZERO API Key) +
 *      Acta Diurna (`SOsintOps/acta-diurna`) vendorized regional GeoJSON & Samaritan square markers.
 *   2. Link Analysis Network Graph compliant with:
 *      - UNODC *Criminal Intelligence: Manual for Analysts* (2011, Chapters 4 & 6)
 *      - IBM i2 Analyst's Notebook & Anacapa POLE visual conventions
 *      - Malcolm Sparrow (1991) SNA Centrality & Concentric Rings
 *      - Peter Klerks (2001) Fluid Network vs Hierarchy multi-view switching
 *      - OCCRP FollowTheMoney (`FtM v3.x`) & Quaesitor (`SOsintOps/quaesitor`) 4-corner badges & Untangle
 *   3. Interactive Draggable & Pinnable Nodes across all layouts (Organic, Hierarchical, Concentric, Circular, Matrix).
 */

let currentCompanyNumber = null;
let currentDossier = null;
let ft3MetadataList = [];
let activeInvestigationId = null;
let searchDebounceTimer = null;

// Graph state (Interactive Link Analysis)
let currentGraphPayload = null;
let graphNodes = [];
let graphEdges = [];
let graphNodeMap = new Map();
let currentGraphLayout = "organic"; // 'organic' | 'hierarchical' | 'concentric' | 'circular' | 'matrix'
let showGraphEdgeLabels = true;
let showChartKeyPanel = true;
let graphZoomState = { scale: 1, tx: 0, ty: 0 };
let draggedNode = null;
let dragStartMouse = { x: 0, y: 0 };
let dragMovedPx = 0;

// Map state (Leaflet + OpenStreetMap Free No-Key + Acta Diurna regional GeoJSON)
let ukLeafletMap = null;
let ukTileLayer = null;
let ukMarkersLayer = null;
let ukBoundaryLayer = null;
let ukActiveRegionLayer = null;
let ukRegionsGeoJson = null;
let currentBasemapStyle = "osm-light";
let lastGeoJsonData = null;
let lastFlaggedOnlyMap = true;
let mapZoomState = { scale: 1, tx: 0, ty: 0 };

// Embedded fallback UK coastline GeoJSON (used immediately & in 100% offline mode)
const UK_BOUNDARY_GEOJSON = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      properties: { reg_name: "Great Britain", code: "GBR" },
      geometry: {
        type: "Polygon",
        coordinates: [[
          [-5.00, 58.60], [-4.02, 58.56], [-3.10, 58.64], [-3.09, 58.44], [-3.82, 57.95],
          [-4.01, 57.69], [-3.65, 57.70], [-2.95, 57.69], [-1.99, 57.69], [-1.78, 57.48],
          [-2.07, 57.14], [-2.21, 56.88], [-2.46, 56.71], [-2.69, 56.56], [-2.79, 56.34],
          [-2.60, 56.26], [-3.18, 56.06], [-3.38, 56.01], [-2.82, 56.06], [-2.37, 55.94],
          [-2.02, 55.77], [-1.60, 55.60], [-1.61, 55.00], [-1.37, 54.91], [-1.16, 54.62],
          [-0.40, 54.28], [-0.08, 54.11], [0.15, 53.57], [0.02, 53.48], [0.35, 53.14],
          [0.54, 52.97], [1.30, 52.93], [1.76, 52.48], [1.58, 52.10], [1.28, 51.85],
          [0.95, 51.78], [0.60, 51.52], [0.85, 51.45], [1.44, 51.38], [1.38, 51.13],
          [0.97, 50.91], [0.28, 50.76], [-0.14, 50.82], [-0.79, 50.73], [-1.30, 50.76],
          [-1.95, 50.70], [-2.45, 50.52], [-3.18, 50.68], [-3.53, 50.45], [-3.84, 50.21],
          [-4.19, 50.33], [-4.78, 50.33], [-5.20, 49.96], [-5.71, 50.07], [-5.53, 50.22],
          [-5.05, 50.55], [-4.55, 50.83], [-4.22, 51.12], [-3.48, 51.20], [-2.98, 51.22],
          [-2.66, 51.60], [-3.18, 51.48], [-3.68, 51.44], [-4.22, 51.56], [-4.70, 51.65],
          [-5.15, 51.67], [-5.34, 51.88], [-5.07, 52.02], [-4.60, 52.15], [-4.15, 52.38],
          [-4.06, 52.68], [-4.12, 52.90], [-4.77, 52.79], [-4.45, 53.08], [-4.68, 53.32],
          [-4.30, 53.42], [-3.85, 53.34], [-3.35, 53.35], [-3.05, 53.45], [-3.02, 53.92],
          [-2.88, 54.10], [-3.25, 54.12], [-3.62, 54.52], [-3.35, 54.88], [-3.82, 54.86],
          [-4.38, 54.78], [-4.90, 54.64], [-5.15, 54.99], [-4.86, 55.38], [-4.65, 55.62],
          [-4.90, 55.96], [-5.35, 55.90], [-5.68, 55.31], [-5.58, 55.85], [-5.65, 56.22],
          [-5.48, 56.45], [-5.90, 56.60], [-6.22, 56.73], [-5.88, 57.00], [-5.70, 57.33],
          [-5.85, 57.58], [-5.62, 57.88], [-5.35, 58.05], [-5.42, 58.25], [-5.08, 58.42],
          [-5.00, 58.60]
        ]],
      },
    },
    {
      type: "Feature",
      properties: { reg_name: "Northern Ireland", code: "NIR" },
      geometry: {
        type: "Polygon",
        coordinates: [[
          [-6.56, 55.21], [-6.14, 55.20], [-5.83, 54.92], [-5.69, 54.66], [-5.45, 54.35],
          [-5.85, 54.05], [-6.25, 54.03], [-6.65, 54.08], [-6.95, 54.25], [-7.35, 54.15],
          [-7.88, 54.22], [-8.16, 54.46], [-7.58, 54.68], [-7.42, 54.99], [-7.25, 55.06],
          [-6.93, 55.17], [-6.56, 55.21]
        ]],
      },
    },
  ],
};

document.addEventListener("DOMContentLoaded", async () => {
  initTheme();
  // Load vendorized UK regional boundaries (Acta Diurna pattern: local GeoJSON, zero remote dependency)
  fetch("/static/uk_regions.geojson")
    .then((r) => (r.ok ? r.json() : UK_BOUNDARY_GEOJSON))
    .then((data) => {
      ukRegionsGeoJson = data;
    })
    .catch(() => {
      ukRegionsGeoJson = UK_BOUNDARY_GEOJSON;
    });

  await Promise.all([
    loadDashboardStats(),
    loadFt3Metadata(),
    loadCompanies(),
    loadHotspots(),
    loadInvestigations(),
  ]);
  await loadGeoMap(true);
});

/* ============================================================================
   THEME, EXPLORATORES KONAMI EASTER EGG & NAVIGATION
   ============================================================================ */

const EXPLORATORES_TAB_MOTTOES = {
  graph: "Qui quaerit, invenit",
  map: "Orbis pictus, veritas scripta",
  timeline: "Omnia tempus revelat",
  ftm: "Numero, pondere et mensura",
  casework: "Littera gesta docet",
  data: "Tempora mutantur",
};

function initTheme() {
  const saved = localStorage.getItem("aethelburg-theme") || "light";
  setTheme(saved, false);
  initKonamiEasterEgg();
}

function setTheme(themeName, rerender = true) {
  const valid = ["light", "classical", "dark"].includes(themeName) ? themeName : "light";
  document.documentElement.setAttribute("data-theme", valid);
  document.body.classList.toggle("matrix-mode", valid === "classical");
  localStorage.setItem("aethelburg-theme", valid);

  const themeSel = document.getElementById("theme-select");
  if (themeSel && themeSel.value !== valid) {
    themeSel.value = valid;
  }

  const sel = document.getElementById("basemap-select");
  if (sel && (sel.value === "osm-dark" || sel.value === "osm-light")) {
    sel.value = valid === "dark" ? "osm-dark" : "osm-light";
    currentBasemapStyle = sel.value;
  }

  if (rerender) {
    updateLeafletThemeTiles();
    if (graphNodes.length) renderGraphFromState();
  }
}

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") || "light";
  const next = current === "light" ? "classical" : current === "classical" ? "dark" : "light";
  setTheme(next, true);
}

function initKonamiEasterEgg() {
  const konamiSequence = [
    "ArrowUp", "ArrowUp", "ArrowDown", "ArrowDown",
    "ArrowLeft", "ArrowRight", "ArrowLeft", "ArrowRight",
    "b", "a",
  ];
  let seqPos = 0;
  document.addEventListener("keydown", (e) => {
    const req = konamiSequence[seqPos];
    if (e.key && e.key.toLowerCase() === req.toLowerCase()) {
      seqPos++;
      if (seqPos === konamiSequence.length) {
        setTheme("classical", true);
        const titleEl = document.getElementById("brand-main-title");
        if (titleEl) titleEl.textContent = "AETHELBURG • OMNIA TEMPUS REVELAT";
        seqPos = 0;
      }
    } else {
      seqPos = 0;
    }
  });
}

function switchTab(tabName) {
  document.querySelectorAll(".tab-btn").forEach((b) => {
    b.classList.toggle("active", b.dataset.tab === tabName);
  });
  document.querySelectorAll(".center-view").forEach((v) => {
    v.classList.toggle("active", v.id === `view-${tabName}`);
  });
  const motto = EXPLORATORES_TAB_MOTTOES[tabName] || "Omnia tempus revelat";
  const mottoEl = document.getElementById("brand-motto");
  const footerMottoEl = document.getElementById("footer-motto");
  if (mottoEl) mottoEl.textContent = motto;
  if (footerMottoEl) footerMottoEl.textContent = motto;

  if (tabName === "map") {
    setTimeout(() => {
      initOrRefreshUkMap();
      if (ukLeafletMap) {
        ukLeafletMap.invalidateSize();
      }
      if (lastGeoJsonData) {
        if (ukLeafletMap && currentBasemapStyle !== "offline-vector") {
          renderLeafletMarkers(lastGeoJsonData);
        } else {
          renderUkSvgMap(lastGeoJsonData);
        }
      } else {
        loadGeoMap(lastFlaggedOnlyMap);
      }
    }, 60);
  } else if (tabName === "graph") {
    setTimeout(() => {
      if (graphNodes.length) renderGraphFromState();
    }, 40);
  } else if (tabName === "data" && typeof loadDataPanel === "function") {
    loadDataPanel();
  }
}

/* ============================================================================
   KPI STRIP & METADATA
   ============================================================================ */

async function loadDashboardStats() {
  try {
    const res = await fetch("/api/stats");
    const data = await res.json();
    const c = data.counts || {};
    document.getElementById("kpi-companies").textContent = (c.companies || 0).toLocaleString();
    document.getElementById("kpi-flagged").textContent = (c.flagged_companies || 0).toLocaleString();
    document.getElementById("kpi-sanctions").textContent = (c.sanctions || 0).toLocaleString();
    document.getElementById("kpi-icij").textContent = (c.icij_entities || 0).toLocaleString();
    document.getElementById("kpi-ftm").textContent = (c.ftm_entities || 0).toLocaleString();
  } catch (err) {
    console.error("Failed to load stats:", err);
  }
}

async function loadFt3Metadata() {
  try {
    const res = await fetch("/api/ft3/techniques");
    const data = await res.json();
    ft3MetadataList = data.techniques || [];
    const sel = document.getElementById("ft3-filter");
    if (sel) {
      ft3MetadataList.forEach((t) => {
        const opt = document.createElement("option");
        opt.value = t.code;
        opt.textContent = `${t.code} — ${t.name}`;
        sel.appendChild(opt);
      });
    }
  } catch (err) {
    console.error("Failed to load FT3 techniques:", err);
  }
}

/* ============================================================================
   LEFT PANEL: ENTITY SEARCH & FILTERING
   ============================================================================ */

function debounceSearch() {
  clearTimeout(searchDebounceTimer);
  searchDebounceTimer = setTimeout(() => loadCompanies(), 220);
}

async function loadCompanies() {
  const q = document.getElementById("search-input")?.value || "";
  const ft3 = document.getElementById("ft3-filter")?.value || "";
  const minRisk = document.getElementById("risk-filter")?.value || "0";

  const params = new URLSearchParams({
    q,
    min_risk: minRisk,
    limit: "80",
  });
  if (ft3) params.set("ft3", ft3);

  try {
    const res = await fetch(`/api/companies?${params.toString()}`);
    const data = await res.json();
    const items = data.items || [];
    const totalCount = data.total || items.length;
    const countNumEl = document.getElementById("search-count-num");
    if (countNumEl) {
      countNumEl.textContent = String(totalCount);
    } else {
      const lbl = document.getElementById("search-count-label");
      if (lbl) lbl.innerHTML = `<strong>${totalCount}</strong> entity(s)`;
    }
    renderEntityList(items);
    if (typeof appendIndexMatches === "function") appendIndexMatches(q);

    if (!currentCompanyNumber && items.length > 0) {
      selectCompany(items[0].company_number);
    }
  } catch (err) {
    console.error("Failed to load companies:", err);
  }
}

function riskClass(score) {
  if (score >= 65) return "risk-critical";
  if (score >= 40) return "risk-high";
  if (score >= 20) return "risk-medium";
  return "risk-low";
}

function renderEntityList(items) {
  const container = document.getElementById("entity-list");
  if (!container) return;
  if (!items.length) {
    container.innerHTML = `<div style="padding:20px; text-align:center; color:var(--text-secondary);">No matching companies found.</div>`;
    return;
  }

  container.innerHTML = items
    .map((c) => {
      const score = Number(c.risk_score || 0);
      const rCls = riskClass(score);
      const techs = (c.ft3_techniques || [])
        .slice(0, 3)
        .map((t) => `<span class="tech-tag">${escapeHtml(t)}</span>`)
        .join("");
      const activeCls = c.company_number === currentCompanyNumber ? "active" : "";

      return `
        <div class="entity-item ${activeCls}" data-cnum="${escapeHtml(c.company_number)}" onclick="selectCompany('${escapeHtml(c.company_number)}')">
          <div class="entity-item-top">
            <div class="entity-name">${escapeHtml(c.company_name)}</div>
            <span class="risk-badge ${rCls}">${score.toFixed(0)}</span>
          </div>
          <div class="entity-meta">
            <code>${escapeHtml(c.company_number)}</code>
            <span>•</span>
            <span>${escapeHtml(c.company_status || "Active")}</span>
            <span>•</span>
            <span>${escapeHtml(c.reg_address_postcode || "N/A")}</span>
          </div>
          <div style="margin-top:5px; display:flex; gap:4px; flex-wrap:wrap;">
            ${techs}
          </div>
        </div>
      `;
    })
    .join("");
}

/* ============================================================================
   SELECT COMPANY -> DOSSIER, GRAPH, TIMELINE, FTM INSPECTOR
   ============================================================================ */

async function selectCompany(companyNumber) {
  if (!companyNumber) return;
  currentCompanyNumber = companyNumber;
  document.querySelectorAll(".entity-item").forEach((el) => {
    el.classList.toggle("active", el.dataset.cnum === companyNumber);
  });

  try {
    const [dossierRes, graphRes] = await Promise.all([
      fetch(`/api/companies/${encodeURIComponent(companyNumber)}`),
      fetch(`/api/companies/${encodeURIComponent(companyNumber)}/graph?hops=2`),
    ]);

    if (dossierRes.ok) {
      currentDossier = await dossierRes.json();
      renderDossierPanel(currentDossier);
      renderTimelineAndFt3(currentDossier);
      renderFtmInspector(currentDossier);
      highlightSelectedCompanyOnMap(currentDossier);
    }

    if (graphRes.ok) {
      const graphData = await graphRes.json();
      const mapActive = document.getElementById("view-map")?.classList.contains("active");
      if (!mapActive) {
        document.getElementById("center-status").textContent =
          `Link Chart: ${currentDossier?.company?.company_name || companyNumber} — ${graphData.stats.node_count} nodes, ${graphData.stats.edge_count} links, ${graphData.stats.cycle_count} cycles`;
      }
      initGraphData(graphData);
    }
  } catch (err) {
    console.error("Error selecting company:", err);
  }
}

function renderDossierPanel(d) {
  const panel = document.getElementById("dossier-panel");
  if (!panel || !d || !d.company) return;
  const c = d.company;
  const score = Number(c.risk_score || 0);
  const flags = d.risk_flags || [];
  const pscs = d.pscs || [];
  const coloc = d.colocated_companies || [];
  const sancs = d.sanctions_matches || [];
  const icij = d.icij_matches || [];

  const flagsHtml = flags.length
    ? flags
        .map(
          (f) => `
        <div class="flag-box ${escapeHtml(f.severity)}">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:3px;">
            <strong style="font-size:12px;">${escapeHtml(f.ft3_code)} — ${escapeHtml(f.technique_name)}</strong>
            <span class="tech-tag" title="UNODC 4x4 Evaluation Grade">UNODC: ${escapeHtml(f.unodc_grade)} (${escapeHtml(f.confidence)})</span>
          </div>
          <div style="font-size:11.5px; color:var(--text-primary);">${escapeHtml(f.description)}</div>
          <div class="innocent-details">
            <strong>Mandatory Innocent Explanations (ICD 203):</strong>
            ${(f.innocent_explanations || []).map(escapeHtml).join(" • ")}
          </div>
        </div>
      `
        )
        .join("")
    : `<div style="color:var(--text-secondary); font-size:12px;">No FT3 flags triggered for this entity.</div>`;

  const pscHtml = pscs.length
    ? pscs
        .map((p) => {
          const holder = p.is_super_secure
            ? "🔒 Super-Secure Restricted Person (s.790ZG)"
            : p.person_name || p.legal_entity_name || "Unknown PSC";
          const sub = p.person_nationality
            ? `Nationality: ${p.person_nationality}${p.is_pep ? " • [PEP]" : ""}`
            : p.jurisdiction
            ? `Jurisdiction: ${p.jurisdiction}${p.is_offshore ? " • [OFFSHORE]" : ""}`
            : p.psc_kind;
          return `
          <div style="padding:7px 0; border-bottom:1px solid var(--border-subtle); font-size:12px;">
            <div style="font-weight:700;">${escapeHtml(holder)}</div>
            <div style="color:var(--text-secondary); font-size:11px;">${escapeHtml(sub)}</div>
            <div style="color:var(--accent-blue); font-size:11px; margin-top:2px;">
              Control: ${(p.nature_of_control || []).map(escapeHtml).join(", ")}
            </div>
          </div>
        `;
        })
        .join("")
    : `<div style="color:var(--text-secondary); font-size:12px;">No PSC records filed (Potential FT3-SC-010 opacity gap).</div>`;

  const alertsHtml =
    sancs.length || icij.length
      ? `
      <div class="dossier-card" style="border-color:var(--risk-critical);">
        <h3 style="color:var(--risk-critical);"><span>Cross-Dataset Hits (Sanctions &amp; ICIJ)</span><span>${sancs.length + icij.length}</span></h3>
        ${sancs
          .map(
            (s) => `
          <div style="font-size:12px; margin-bottom:6px; color:var(--risk-critical);">
            <strong>🚨 UK SANCTION:</strong> ${escapeHtml(s.name)} (<code>${escapeHtml(s.opensanctions_id)}</code> — ${escapeHtml(s.list_name)})
          </div>`
          )
          .join("")}
        ${icij
          .map(
            (i) => `
          <div style="font-size:12px; margin-bottom:6px; color:var(--accent-gold);">
            <strong>🌴 ICIJ OFFSHORE LEAK:</strong> ${escapeHtml(i.name)} (${escapeHtml(i.source_id_list)} — ${escapeHtml(i.jurisdiction_description || "Offshore")})
          </div>`
          )
          .join("")}
      </div>
    `
      : "";

  const colocHtml = coloc.length
    ? coloc
        .slice(0, 6)
        .map(
          (co) => `
        <div style="display:flex; justify-content:space-between; padding:4px 0; font-size:11.5px; cursor:pointer;"
             onclick="selectCompany('${escapeHtml(co.company_number)}')">
          <span style="color:var(--accent-blue); text-decoration:underline;">${escapeHtml(co.company_name)} (${escapeHtml(co.company_number)})</span>
          <span class="risk-badge ${riskClass(co.risk_score)}">${Number(co.risk_score || 0).toFixed(0)}</span>
        </div>
      `
        )
        .join("")
    : `<div style="color:var(--text-secondary); font-size:12px;">No other co-located companies at this address.</div>`;

  panel.innerHTML = `
    <div class="dossier-card">
      <h3>
        <span>Subject Profile</span>
        <span class="risk-badge ${riskClass(score)}">Risk: ${score.toFixed(1)} / 100</span>
      </h3>
      <div style="font-size:15px; font-weight:800; margin-bottom:8px;">${escapeHtml(c.company_name)}</div>
      <div class="kv-grid">
        <div class="kv-key">CRN</div><div class="kv-val"><code>${escapeHtml(c.company_number)}</code></div>
        <div class="kv-key">FtM Entity ID</div><div class="kv-val"><code>${escapeHtml(c.ftm_id)}</code></div>
        <div class="kv-key">Status / Type</div><div class="kv-val">${escapeHtml(c.company_status)} • ${escapeHtml(c.company_category || "LTD")}</div>
        <div class="kv-key">Incorporated</div><div class="kv-val">${escapeHtml(c.incorporation_date || "Unknown")}</div>
        <div class="kv-key">Registered Office</div>
        <div class="kv-val">
          ${escapeHtml(c.reg_address_line1 || "")}, ${escapeHtml(c.reg_address_post_town || "")},
          <strong style="color:var(--accent-gold); cursor:pointer;" onclick="switchTab('map'); focusHotspotOnMap('${escapeHtml(c.reg_address_postcode || "")}', ${d.geo?.lat || "null"}, ${d.geo?.lon || "null"})">${escapeHtml(c.reg_address_postcode || "")}</strong>
        </div>
        <div class="kv-key">SIC Codes</div><div class="kv-val">${escapeHtml((c.sic_codes || []).join(", ") || "None")}</div>
      </div>
    </div>

    ${alertsHtml}

    <div class="dossier-card">
      <h3><span>FT3 Risk Flags &amp; UNODC 4x4 Evaluation</span><span>${flags.length}</span></h3>
      ${flagsHtml}
    </div>

    <div class="dossier-card">
      <h3><span>Beneficial Owners (PSC) &amp; Control</span><span>${pscs.length}</span></h3>
      ${pscHtml}
    </div>

    <div class="dossier-card">
      <h3><span>Co-Located Entities at Address</span><span>${d.colocated_total || 1} total</span></h3>
      ${colocHtml}
    </div>
  `;
}

/* ============================================================================
   TAB 1: LINK ANALYSIS NETWORK GRAPH (UNODC / i2 / SPARROW / KLERKS / FTM)
   ============================================================================ */

async function loadCompanyGraph(companyNumber, hops = 2) {
  if (!companyNumber) return;
  try {
    const res = await fetch(`/api/companies/${encodeURIComponent(companyNumber)}/graph?hops=${hops}`);
    const payload = await res.json();
    document.getElementById("center-status").textContent =
      `Link Chart: ${companyNumber} (${hops} hops) — ${payload.stats.node_count} entities, ${payload.stats.edge_count} links, ${payload.stats.cycle_count} cycles`;
    initGraphData(payload);
  } catch (err) {
    console.error("Failed to load company graph:", err);
  }
}

async function loadOverviewGraph() {
  try {
    const res = await fetch("/api/graph/overview?limit=25");
    const payload = await res.json();
    document.getElementById("center-status").textContent =
      `Global High-Risk Ring Overview — ${payload.stats.node_count} entities, ${payload.stats.edge_count} links, ${payload.stats.cycle_count} cycles`;
    initGraphData(payload);
  } catch (err) {
    console.error("Failed to load overview graph:", err);
  }
}

function initGraphData(payload) {
  currentGraphPayload = payload;
  graphNodes = (payload.elements?.nodes || []).map((n, idx) => ({
    ...n.data,
    idx,
    x: 400,
    y: 300,
    pinned: false,
  }));
  graphEdges = (payload.elements?.edges || []).map((e) => ({ ...e.data }));
  graphNodeMap = new Map();
  graphNodes.forEach((n) => graphNodeMap.set(n.id, n));

  graphZoomState = { scale: 1, tx: 0, ty: 0 };
  updateChartKeyCover(payload);
  applyGraphLayout(currentGraphLayout);
  renderGraphFromState();
}

function updateChartKeyCover(payload) {
  const focusEl = document.getElementById("ck-focus");
  const dateEl = document.getElementById("ck-date");
  const statsEl = document.getElementById("ck-stats");
  if (focusEl) {
    focusEl.textContent = payload.root_id
      ? `${currentDossier?.company?.company_name || payload.root_id} (${currentCompanyNumber || ""})`
      : "Global Multi-Cluster Ring";
  }
  if (dateEl) {
    const now = new Date().toISOString().slice(0, 16).replace("T", " ") + " UTC";
    dateEl.textContent = `${now} • Rev #1`;
  }
  if (statsEl && payload.stats) {
    statsEl.textContent = `${payload.stats.node_count} Nodes • ${payload.stats.edge_count} Links • Density ${payload.stats.density}`;
  }
}

function setGraphLayout(layoutName) {
  currentGraphLayout = layoutName;
  document.querySelectorAll(".layout-btn").forEach((b) => {
    b.classList.toggle("active", b.id === `btn-ly-${layoutName}`);
  });

  const matrixOverlay = document.getElementById("graph-matrix-view");
  const svg = document.getElementById("graph-svg");
  if (layoutName === "matrix") {
    if (matrixOverlay) {
      matrixOverlay.style.display = "block";
      renderUnodcAssociationMatrix();
    }
    return;
  } else {
    if (matrixOverlay) matrixOverlay.style.display = "none";
    if (svg) svg.style.display = "block";
  }

  applyGraphLayout(layoutName);
  renderGraphFromState();
}

function applyGraphLayout(layoutName) {
  const svg = document.getElementById("graph-svg");
  const rect = svg ? svg.getBoundingClientRect() : { width: 860, height: 600 };
  const width = Math.max(rect.width || 860, 720);
  const height = Math.max(rect.height || 600, 500);
  const cx = width / 2;
  const cy = height / 2;
  const rootId = currentGraphPayload?.root_id;

  if (!graphNodes.length) return;

  if (layoutName === "hierarchical") {
    // UNODC p. 44 / i2 Analyst's Notebook Tiered Hierarchy (Top-Down Company Tree)
    // Tier 0: Sanctions, UBO Persons, SuperSecurePSC, ICIJ Leaks
    // Tier 1: Parent / Offshore Legal Entities
    // Tier 2: Root / Subject UK Company
    // Tier 3: Subsidiary / Co-located UK Companies
    // Tier 4: Registered Address Hubs
    const tiers = new Map([
      [0, []],
      [1, []],
      [2, []],
      [3, []],
      [4, []],
    ]);

    graphNodes.forEach((n) => {
      let lvl = n.hierarchy_level;
      if (lvl === undefined || lvl === null) {
        if (n.node_type === "Sanction" || n.node_type === "Person" || n.node_type === "SuperSecurePSC") lvl = 0;
        else if (n.node_type === "OffshoreEntity" || n.node_type === "LegalEntity") lvl = 1;
        else if (n.is_root) lvl = 2;
        else if (n.node_type === "Company") lvl = 3;
        else lvl = 4;
      }
      if (!tiers.has(lvl)) tiers.set(lvl, []);
      tiers.get(lvl).push(n);
    });

    const activeLevels = [0, 1, 2, 3, 4].filter((l) => (tiers.get(l) || []).length > 0);
    const topPad = 85;
    const bottomPad = 80;
    const usableH = Math.max(320, height - topPad - bottomPad);
    const rowStep = activeLevels.length > 1 ? usableH / (activeLevels.length - 1) : 0;

    activeLevels.forEach((lvl, rowIdx) => {
      const rowNodes = tiers.get(lvl);
      // Sort nodes within tier by degree descending so central connectors sit near the center
      rowNodes.sort((a, b) => (b.degree || 0) - (a.degree || 0));
      const y = activeLevels.length === 1 ? cy : topPad + rowIdx * rowStep;
      const leftPad = 110;
      const usableW = Math.max(480, width - leftPad * 2);
      rowNodes.forEach((n, i) => {
        if (n.pinned) return;
        const x =
          rowNodes.length === 1
            ? cx
            : leftPad + ((i + 0.5) / rowNodes.length) * usableW;
        n.x = x;
        n.y = y;
      });
    });
  } else if (layoutName === "concentric") {
    // Malcolm Sparrow (1991) Ego-Centric Radial Centrality Layout
    // Ring 0 (Center): Root target or highest-betweenness broker
    // Ring 1 (Inner): Direct 1-hop controllers, PSCs, sanctions, address
    // Ring 2 (Outer): 2-hop / co-located / extended network
    let centerNode = graphNodes.find((n) => n.id === rootId || n.is_root);
    if (!centerNode) {
      centerNode = [...graphNodes].sort(
        (a, b) => (b.betweenness_centrality || b.degree || 0) - (a.betweenness_centrality || a.degree || 0)
      )[0];
    }

    const ring1 = [];
    const ring2 = [];
    const directIds = new Set();
    if (centerNode) {
      graphEdges.forEach((e) => {
        if (e.source === centerNode.id) directIds.add(e.target);
        if (e.target === centerNode.id) directIds.add(e.source);
      });
    }

    graphNodes.forEach((n) => {
      if (centerNode && n.id === centerNode.id) return;
      if (directIds.has(n.id) || n.hop_distance === 1) ring1.push(n);
      else ring2.push(n);
    });

    if (centerNode && !centerNode.pinned) {
      centerNode.x = cx;
      centerNode.y = cy;
    }

    const r1Radius = Math.min(width, height) * 0.24;
    const r2Radius = Math.min(width, height) * 0.41;

    ring1.forEach((n, i) => {
      if (n.pinned) return;
      const angle = (2 * Math.PI * i) / Math.max(ring1.length, 1) - Math.PI / 2;
      n.x = cx + r1Radius * Math.cos(angle);
      n.y = cy + r1Radius * Math.sin(angle);
    });

    ring2.forEach((n, i) => {
      if (n.pinned) return;
      const angle = (2 * Math.PI * i) / Math.max(ring2.length, 1) - Math.PI / 4;
      n.x = cx + r2Radius * Math.cos(angle);
      n.y = cy + r2Radius * Math.sin(angle);
    });
  } else if (layoutName === "circular") {
    // Structural POLE Category Ring (Grouped by Entity Type)
    const order = { Sanction: 1, Person: 2, SuperSecurePSC: 3, OffshoreEntity: 4, LegalEntity: 5, Company: 6, Address: 7 };
    const sorted = [...graphNodes].sort(
      (a, b) => (order[a.node_type] || 9) - (order[b.node_type] || 9) || (b.risk_score || 0) - (a.risk_score || 0)
    );
    const radius = Math.min(width, height) * 0.37;
    sorted.forEach((n, i) => {
      if (n.pinned) return;
      const angle = (2 * Math.PI * i) / Math.max(sorted.length, 1) - Math.PI / 2;
      n.x = cx + radius * Math.cos(angle);
      n.y = cy + radius * Math.sin(angle);
    });
  } else {
    // 'organic' — Force-Directed SNA Layout with collision separation
    runForceSimulation(width, height, 110, false);
  }
}

function runForceSimulation(width, height, iterations = 110, randomize = false) {
  const cx = width / 2;
  const cy = height / 2;
  const rootId = currentGraphPayload?.root_id;

  graphNodes.forEach((n, idx) => {
    if (n.pinned) return;
    if (n.id === rootId && !randomize) {
      n.x = cx;
      n.y = cy;
    } else if (randomize) {
      const angle = (2 * Math.PI * idx) / Math.max(graphNodes.length, 1) + (Math.random() - 0.5) * 0.8;
      const rad = (0.18 + Math.random() * 0.25) * Math.min(width, height);
      n.x = cx + rad * Math.cos(angle);
      n.y = cy + rad * Math.sin(angle);
    } else {
      const ring = n.hop_distance === 1 ? 1 : 2;
      const angle = (2 * Math.PI * idx) / Math.max(graphNodes.length - 1, 1);
      const radius = ring === 1 ? Math.min(width, height) * 0.24 : Math.min(width, height) * 0.38;
      n.x = cx + radius * Math.cos(angle);
      n.y = cy + radius * Math.sin(angle);
    }
  });

  for (let iter = 0; iter < iterations; iter++) {
    // Node-node Coulomb repulsion + minimum box separation
    for (let i = 0; i < graphNodes.length; i++) {
      for (let j = i + 1; j < graphNodes.length; j++) {
        const a = graphNodes[i];
        const b = graphNodes[j];
        let dx = b.x - a.x;
        let dy = b.y - a.y;
        let distSq = dx * dx + dy * dy + 0.1;
        let dist = Math.sqrt(distSq);
        const minSep = 135;
        let repulse = 7500 / distSq;
        if (dist < minSep) {
          repulse += (minSep - dist) * 0.35;
        }
        const fx = (dx / dist) * repulse;
        const fy = (dy / dist) * repulse;
        if (!a.pinned && a.id !== rootId) {
          a.x -= fx;
          a.y -= fy;
        }
        if (!b.pinned && b.id !== rootId) {
          b.x += fx;
          b.y += fy;
        }
      }
    }

    // Hooke spring attraction along links
    graphEdges.forEach((e) => {
      const s = graphNodeMap.get(e.source);
      const t = graphNodeMap.get(e.target);
      if (!s || !t) return;
      const dx = t.x - s.x;
      const dy = t.y - s.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const targetLen = 165;
      const force = (dist - targetLen) * 0.05;
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;
      if (!s.pinned && s.id !== rootId) {
        s.x += fx;
        s.y += fy;
      }
      if (!t.pinned && t.id !== rootId) {
        t.x -= fx;
        t.y -= fy;
      }
    });

    // Gentle centering gravity so components don't drift off-canvas
    graphNodes.forEach((n) => {
      if (n.pinned || n.id === rootId) return;
      n.x += (cx - n.x) * 0.012;
      n.y += (cy - n.y) * 0.012;
      n.x = Math.max(85, Math.min(width - 85, n.x));
      n.y = Math.max(55, Math.min(height - 55, n.y));
    });
  }
}

/* ============================================================================
   UNODC STEP 7: UNTANGLE (MINIMIZE EDGE CROSSINGS, INSPIRED BY QUAESITOR)
   ============================================================================ */

function countEdgeCrossings() {
  const segs = [];
  graphEdges.forEach((e) => {
    const s = graphNodeMap.get(e.source);
    const t = graphNodeMap.get(e.target);
    if (s && t) {
      segs.push({ x1: s.x, y1: s.y, x2: t.x, y2: t.y, s: e.source, t: e.target });
    }
  });
  const sgn = (ax, ay, bx, by, cx, cy) => Math.sign((bx - ax) * (cy - ay) - (by - ay) * (cx - ax));
  let crossings = 0;
  for (let i = 0; i < segs.length; i++) {
    for (let j = i + 1; j < segs.length; j++) {
      const p = segs[i];
      const q = segs[j];
      if (p.s === q.s || p.s === q.t || p.t === q.s || p.t === q.t) continue;
      const d1 = sgn(p.x1, p.y1, p.x2, p.y2, q.x1, q.y1);
      const d2 = sgn(p.x1, p.y1, p.x2, p.y2, q.x2, q.y2);
      const d3 = sgn(q.x1, q.y1, q.x2, q.y2, p.x1, p.y1);
      const d4 = sgn(q.x1, q.y1, q.x2, q.y2, p.x2, p.y2);
      if (d1 !== d2 && d3 !== d4) crossings++;
    }
  }
  return crossings;
}

function untangleGraph() {
  if (graphNodes.length < 3) return;
  const svg = document.getElementById("graph-svg");
  const rect = svg ? svg.getBoundingClientRect() : { width: 860, height: 600 };
  const width = Math.max(rect.width || 860, 720);
  const height = Math.max(rect.height || 600, 500);

  let bestPositions = graphNodes.map((n) => ({ id: n.id, x: n.x, y: n.y }));
  let bestCrossings = countEdgeCrossings();

  for (let attempt = 0; attempt < 12; attempt++) {
    if (bestCrossings === 0) break;
    runForceSimulation(width, height, 95, true);
    const c = countEdgeCrossings();
    if (c < bestCrossings) {
      bestCrossings = c;
      bestPositions = graphNodes.map((n) => ({ id: n.id, x: n.x, y: n.y }));
    }
  }

  bestPositions.forEach((p) => {
    const n = graphNodeMap.get(p.id);
    if (n && !n.pinned) {
      n.x = p.x;
      n.y = p.y;
    }
  });

  currentGraphLayout = "organic";
  document.querySelectorAll(".layout-btn").forEach((b) => {
    b.classList.toggle("active", b.id === "btn-ly-organic");
  });
  renderGraphFromState();
  document.getElementById("center-status").textContent =
    `Untangled Link Chart (UNODC Step 7) — Crossings reduced to ${bestCrossings}`;
}

function unpinAllGraphNodes() {
  graphNodes.forEach((n) => {
    n.pinned = false;
  });
  applyGraphLayout(currentGraphLayout);
  renderGraphFromState();
}

function toggleGraphEdgeLabels() {
  showGraphEdgeLabels = !showGraphEdgeLabels;
  const btn = document.getElementById("btn-toggle-labels");
  if (btn) btn.textContent = `Labels: ${showGraphEdgeLabels ? "ON" : "OFF"}`;
  renderGraphFromState();
}

function toggleChartKey() {
  showChartKeyPanel = !showChartKeyPanel;
  const panel = document.getElementById("graph-chart-key");
  if (panel) panel.style.display = showChartKeyPanel ? "block" : "none";
}

/* ============================================================================
   SVG GRAPH RENDERER (POLE SHAPES, 4-CORNER BADGES, SOLID/DASHED LINKS, DRAG)
   ============================================================================ */

function getGraphThemePalette() {
  const theme = document.documentElement.getAttribute("data-theme") || "light";
  if (theme === "dark") {
    return {
      nodeFill: "#0f172a",
      nodeText: "#f8fafc",
      nodeSub: "#94a3b8",
      badgeBg: "#1e293b",
      badgeBorder: "#475569",
      badgeText: "#e2e8f0",
      pillBg: "#0b1324",
      pillText: "#e2e8f0",
      guideStroke: "#334155",
      guideText: "#64748b",
      primaryBlue: "#38bdf8",
    };
  }
  if (theme === "classical") {
    return {
      nodeFill: "#fffdf5",
      nodeText: "#2c1a00",
      nodeSub: "#5c4014",
      badgeBg: "#f7f0dc",
      badgeBorder: "#C9A84C",
      badgeText: "#2c1a00",
      pillBg: "#fffdf5",
      pillText: "#2c1a00",
      guideStroke: "#C9A84C",
      guideText: "#8B6914",
      primaryBlue: "#8B6914",
    };
  }
  // Exploratores Standard (Light)
  return {
    nodeFill: "#ffffff",
    nodeText: "#333333",
    nodeSub: "#555555",
    badgeBg: "#eaeaea",
    badgeBorder: "#cccccc",
    badgeText: "#333333",
    pillBg: "#ffffff",
    pillText: "#333333",
    guideStroke: "#cccccc",
    guideText: "#666666",
    primaryBlue: "#0066ff",
  };
}

function nodeColor(n) {
  const pal = getGraphThemePalette();
  const t = n.node_type;
  if (t === "Sanction") return "#c0392b";
  if (t === "OffshoreEntity") return "#e67e22";
  if (t === "Person") return n.is_pep ? "#d81b60" : "#8e44ad";
  if (t === "Address") return "#2e7d32";
  if (t === "SuperSecurePSC") return "#c8a000";
  if (t === "Company" || t === "LegalEntity") return n.is_flagged ? "#d9534f" : pal.primaryBlue;
  return "#64748b";
}

function renderBackgroundGuides(width, height) {
  const cx = width / 2;
  const cy = height / 2;
  const pal = getGraphThemePalette();

  if (currentGraphLayout === "hierarchical") {
    const tierNames = [
      "TIER 1: BENEFICIAL OWNERS (PSC / PEP) & SANCTIONS",
      "TIER 2: CORPORATE PARENTS & OFFSHORE ENTITIES",
      "TIER 3: SUBJECT / OPERATING UK COMPANIES",
      "TIER 4: SUBSIDIARIES & CO-LOCATED ENTITIES",
      "TIER 5: REGISTERED OFFICE HUBS (LOCATIONS)",
    ];
    const activeLevels = [];
    const seen = new Set(graphNodes.map((n) => n.hierarchy_level ?? 2));
    [0, 1, 2, 3, 4].forEach((l) => {
      if (seen.has(l)) activeLevels.push(l);
    });
    const topPad = 85;
    const bottomPad = 80;
    const usableH = Math.max(320, height - topPad - bottomPad);
    const rowStep = activeLevels.length > 1 ? usableH / (activeLevels.length - 1) : 0;

    return activeLevels
      .map((lvl, idx) => {
        const y = activeLevels.length === 1 ? cy : topPad + idx * rowStep;
        return `
          <g class="layout-guide">
            <line x1="30" y1="${y.toFixed(1)}" x2="${(width - 30).toFixed(1)}" y2="${y.toFixed(1)}"
                  stroke="${pal.guideStroke}" stroke-width="1" stroke-dasharray="4,6" stroke-opacity="0.7" />
            <text x="36" y="${(y - 28).toFixed(1)}" fill="${pal.guideText}" font-size="9.5" font-weight="700" letter-spacing="0.06em">
              ${tierNames[lvl] || `TIER ${lvl + 1}`}
            </text>
          </g>
        `;
      })
      .join("");
  }

  if (currentGraphLayout === "concentric") {
    const r1 = Math.min(width, height) * 0.24;
    const r2 = Math.min(width, height) * 0.41;
    return `
      <g class="layout-guide">
        <circle cx="${cx}" cy="${cy}" r="${r1.toFixed(1)}" fill="none" stroke="${pal.guideStroke}" stroke-width="1" stroke-dasharray="5,5" stroke-opacity="0.7" />
        <circle cx="${cx}" cy="${cy}" r="${r2.toFixed(1)}" fill="none" stroke="${pal.guideStroke}" stroke-width="1" stroke-dasharray="5,5" stroke-opacity="0.55" />
        <text x="${cx}" y="${(cy - r1 - 6).toFixed(1)}" text-anchor="middle" fill="${pal.guideText}" font-size="9.5" font-weight="700">
          RING 1: DIRECT CONTROLLERS &amp; STATUTORY LINKS (1 HOP)
        </text>
        <text x="${cx}" y="${(cy - r2 - 6).toFixed(1)}" text-anchor="middle" fill="${pal.guideText}" font-size="9.5" font-weight="700">
          RING 2: EXTENDED SHELL RING &amp; OFFSHORE LEAKS (2 HOPS)
        </text>
      </g>
    `;
  }

  return "";
}

function renderNodeShapeAndGlyph(n) {
  const pal = getGraphThemePalette();
  const color = nodeColor(n);
  const isRoot = Boolean(n.is_root);
  const strokeColor = isRoot ? pal.primaryBlue : color;
  const strokeWidth = isRoot ? 3.0 : 2.0;
  const score = Math.round(Number(n.risk_score || 0));
  const grade = n.unodc_grade || "A2";
  const cc = n.country_code || "GB";
  const pinBadge = n.pinned ? "📌 " : "";

  // NW Role badge
  let roleTag = n.ftm_schema || n.node_type;
  if (isRoot) roleTag = "TARGET";
  else if (n.is_pep) roleTag = "PEP";
  else if (n.is_bridge) roleTag = "BRIDGE";
  else if (n.node_type === "OffshoreEntity") roleTag = "OFFSHORE";
  else if (n.node_type === "Address") roleTag = `HUB (${n.colocated_count || 1})`;

  // 1. UNODC Organization / Company -> RECTANGLE (UNODC Manual p. 39 & 44)
  if (n.node_type === "Company" || n.node_type === "LegalEntity" || n.node_type === "OffshoreEntity") {
    const w = 138;
    const h = 46;
    const hw = w / 2;
    const hh = h / 2;
    const subLine = n.company_number
      ? `CRN: ${n.company_number}`
      : n.jurisdiction
      ? n.jurisdiction.slice(0, 18)
      : "Corporate Entity";

    return `
      <!-- Organization Rectangle (UNODC Ch. 6) -->
      <rect x="${-hw}" y="${-hh}" width="${w}" height="${h}" rx="3"
            fill="${pal.nodeFill}" stroke="${strokeColor}" stroke-width="${strokeWidth}" />
      <rect x="${-hw}" y="${-hh}" width="26" height="${h}" rx="3" fill="${color}" fill-opacity="0.18" />
      <!-- Building Glyph -->
      <path d="M${-hw + 8},${-6} h10 v14 h-10 z M${-hw + 10},${-3} h2 v2 h-2 z M${-hw + 14},${-3} h2 v2 h-2 z M${-hw + 10},${2} h2 v2 h-2 z M${-hw + 14},${2} h2 v2 h-2 z"
            fill="${color}" />
      <!-- Legal Name & Registration Number inside box (UNODC p. 44) -->
      <text x="${-hw + 31}" y="-4" text-anchor="start" fill="${pal.nodeText}" font-size="10" font-weight="700">
        ${escapeHtml(pinBadge + (n.short_label || n.label || "").slice(0, 16))}
      </text>
      <text x="${-hw + 31}" y="10" text-anchor="start" fill="${pal.nodeSub}" font-size="8.8" font-family="Consolas, monospace">
        ${escapeHtml(subLine)}
      </text>
      <!-- 4 Corner Badges (NW=Role, NE=UNODC Grade, SW=Country, SE=Risk) -->
      <rect x="${-hw}" y="${-hh - 11}" width="46" height="11" rx="2" fill="${color}" />
      <text x="${-hw + 23}" y="${-hh - 3}" text-anchor="middle" fill="#ffffff" font-size="7.5" font-weight="800">${escapeHtml(roleTag)}</text>

      <rect x="${hw - 22}" y="${-hh - 11}" width="22" height="11" rx="2" fill="${pal.badgeBg}" stroke="${pal.badgeBorder}" stroke-width="0.8" />
      <text x="${hw - 11}" y="${-hh - 3}" text-anchor="middle" fill="${pal.primaryBlue}" font-size="7.5" font-weight="800">${escapeHtml(grade)}</text>

      <rect x="${-hw}" y="${hh + 2}" width="22" height="11" rx="2" fill="${pal.badgeBg}" stroke="${pal.badgeBorder}" stroke-width="0.8" />
      <text x="${-hw + 11}" y="${hh + 10}" text-anchor="middle" fill="${pal.badgeText}" font-size="7.5" font-weight="700">${escapeHtml(cc)}</text>

      <rect x="${hw - 36}" y="${hh + 2}" width="36" height="11" rx="2" fill="${score >= 60 ? "#c0392b" : pal.badgeBg}" stroke="${color}" stroke-width="0.8" />
      <text x="${hw - 18}" y="${hh + 10}" text-anchor="middle" fill="${score >= 60 ? "#ffffff" : pal.badgeText}" font-size="7.5" font-weight="800">R:${score}</text>
    `;
  }

  // 2. UNODC Individual / Person -> CIRCLE (UNODC Manual p. 39)
  if (n.node_type === "Person" || n.node_type === "SuperSecurePSC") {
    const r = 22;
    const isUnknown = n.node_type === "SuperSecurePSC";
    const dashAttr = isUnknown ? `stroke-dasharray="4,3"` : "";
    return `
      <circle r="${r}" fill="${pal.nodeFill}" stroke="${color}" stroke-width="2.5" ${dashAttr} />
      <circle r="${r - 4}" fill="${color}" fill-opacity="0.16" />
      ${
        isUnknown
          ? `<text y="5" text-anchor="middle" fill="${color}" font-size="15" font-weight="800">?</text>`
          : `<circle cx="0" cy="-5" r="5" fill="${color}" />
             <path d="M -9 9 C -9 2, 9 2, 9 9 Z" fill="${color}" />`
      }
      <!-- Corner Badges on Person Circle -->
      <rect x="-26" y="-30" width="26" height="10" rx="2" fill="${color}" />
      <text x="-13" y="-22.5" text-anchor="middle" fill="#ffffff" font-size="7" font-weight="800">${escapeHtml(roleTag)}</text>

      <rect x="6" y="-30" width="20" height="10" rx="2" fill="${pal.badgeBg}" stroke="${pal.badgeBorder}" stroke-width="0.8" />
      <text x="16" y="-22.5" text-anchor="middle" fill="${pal.primaryBlue}" font-size="7" font-weight="800">${escapeHtml(grade)}</text>

      <rect x="-24" y="16" width="18" height="10" rx="2" fill="${pal.badgeBg}" stroke="${pal.badgeBorder}" stroke-width="0.8" />
      <text x="-15" y="23.5" text-anchor="middle" fill="${pal.badgeText}" font-size="7" font-weight="700">${escapeHtml(cc)}</text>

      <text y="${r + 16}" text-anchor="middle" fill="${pal.nodeText}" font-size="10.5" font-weight="700">
        ${escapeHtml(pinBadge + (n.short_label || n.label || n.id))}
      </text>
    `;
  }

  // 3. Location / Registered Office Hub -> DIAMOND (POLE Location)
  if (n.node_type === "Address") {
    const s = 24;
    return `
      <polygon points="0,${-s} ${s},0 0,${s} ${-s},0" fill="${pal.nodeFill}" stroke="${color}" stroke-width="2.4" />
      <circle cx="0" cy="-2" r="4" fill="${color}" />
      <path d="M 0 -8 C -5 -8 -7 -3 0 7 C 7 -3 5 -8 0 -8 Z" fill="${color}" fill-opacity="0.35" />
      <rect x="8" y="-26" width="20" height="10" rx="2" fill="${pal.badgeBg}" stroke="${color}" stroke-width="0.8" />
      <text x="18" y="-18.5" text-anchor="middle" fill="${color}" font-size="7" font-weight="800">${escapeHtml(grade)}</text>
      <text y="${s + 14}" text-anchor="middle" fill="${pal.nodeText}" font-size="10" font-weight="700">
        ${escapeHtml(pinBadge + (n.short_label || n.label))} [${n.colocated_count || 1} cos]
      </text>
    `;
  }

  // 4. Official Sanction -> OCTAGON SHIELD
  const o = 22;
  const d = 9;
  return `
    <polygon points="${-d},${-o} ${d},${-o} ${o},${-d} ${o},${d} ${d},${o} ${-d},${o} ${-o},${d} ${-o},${-d}"
             fill="#fdf2f2" stroke="#c0392b" stroke-width="2.5" />
    <text y="4" text-anchor="middle" fill="#c0392b" font-size="9" font-weight="800">OFSI</text>
    <text y="${o + 14}" text-anchor="middle" fill="#c0392b" font-size="10" font-weight="700">
      ${escapeHtml(pinBadge + (n.short_label || n.label))}
    </text>
  `;
}

function computeEdgeGeometry(s, t) {
  const dx = t.x - s.x;
  const dy = t.y - s.y;
  const dist = Math.sqrt(dx * dx + dy * dy) || 1;
  // Pad start/end so arrowheads land cleanly at the node boundary (rectangle vs circle)
  const padStart = s.node_type === "Company" || s.node_type === "LegalEntity" || s.node_type === "OffshoreEntity" ? 42 : 26;
  const padEnd = t.node_type === "Company" || t.node_type === "LegalEntity" || t.node_type === "OffshoreEntity" ? 48 : 28;
  const x1 = s.x + (dx / dist) * Math.min(padStart, dist * 0.35);
  const y1 = s.y + (dy / dist) * Math.min(padStart, dist * 0.35);
  const x2 = t.x - (dx / dist) * Math.min(padEnd, dist * 0.35);
  const y2 = t.y - (dy / dist) * Math.min(padEnd, dist * 0.35);
  const mx = (x1 + x2) / 2;
  const my = (y1 + y2) / 2;
  return { x1, y1, x2, y2, mx, my };
}

function renderGraphFromState() {
  const svg = document.getElementById("graph-svg");
  if (!svg) return;
  const rect = svg.getBoundingClientRect();
  const width = Math.max(rect.width || 860, 720);
  const height = Math.max(rect.height || 600, 500);

  if (!graphNodes.length) {
    svg.innerHTML = `<text x="${width / 2}" y="${height / 2}" text-anchor="middle" fill="#94a3b8">No graph entities loaded</text>`;
    return;
  }

  const guidesSvg = renderBackgroundGuides(width, height);
  const pal = getGraphThemePalette();

  const edgesSvg = graphEdges
    .map((e, idx) => {
      const s = graphNodeMap.get(e.source);
      const t = graphNodeMap.get(e.target);
      if (!s || !t) return "";
      const { x1, y1, x2, y2, mx, my } = computeEdgeGeometry(s, t);

      // UNODC Link Convention: Confirmed (A1, A2, B1, B2) = Solid, Suspected/Inferred (C3) = Dashed
      const isConfirmed = e.confirmed !== false;
      const dashAttr = isConfirmed ? "" : `stroke-dasharray="7,5"`;
      const stroke =
        e.edge_type === "SANCTIONED_AS"
          ? "#c0392b"
          : e.edge_type === "OFFSHORE_MATCH"
          ? "#e67e22"
          : e.edge_type === "CONTROLS"
          ? pal.primaryBlue
          : "#2e7d32";
      const markerId =
        e.edge_type === "SANCTIONED_AS"
          ? "arrow-red"
          : e.edge_type === "OFFSHORE_MATCH"
          ? "arrow-amber"
          : e.edge_type === "CONTROLS"
          ? "arrow-blue"
          : "arrow-green";
      const strokeW = Number(e.weight || 2.0).toFixed(1);
      const labelText = e.label || "";
      const pillW = Math.max(54, labelText.length * 5.6 + 12);

      return `
        <g class="graph-edge" data-edge-idx="${idx}">
          <line class="edge-line" x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}"
                stroke="${stroke}" stroke-width="${strokeW}" ${dashAttr} stroke-opacity="0.88"
                marker-end="url(#${markerId})" />
          <g class="edge-label-group" transform="translate(${mx.toFixed(1)},${my.toFixed(1)})"
             style="display:${showGraphEdgeLabels && labelText ? "block" : "none"};">
            <rect x="${(-pillW / 2).toFixed(1)}" y="-8" width="${pillW.toFixed(1)}" height="15" rx="3"
                  fill="${pal.pillBg}" fill-opacity="0.95" stroke="${stroke}" stroke-width="0.9" stroke-opacity="0.7" />
            <text y="2.5" text-anchor="middle" fill="${pal.pillText}" font-size="8.8" font-weight="600">
              ${escapeHtml(labelText)}
            </text>
          </g>
        </g>
      `;
    })
    .join("");

  const nodesSvg = graphNodes
    .map((n) => {
      return `
        <g class="graph-node" data-node-id="${escapeHtml(n.id)}"
           transform="translate(${n.x.toFixed(1)},${n.y.toFixed(1)})">
          ${renderNodeShapeAndGlyph(n)}
          <title>${escapeHtml(n.label || n.id)}
FtM Schema: ${escapeHtml(n.ftm_schema || "")} (${escapeHtml(n.ftm_id || "")})
UNODC Grade: ${escapeHtml(n.unodc_grade || "A2")} | Links (Step 5): ${n.degree || 0} | Centrality: ${n.betweenness_centrality || 0}
[Drag to move &amp; pin • Click to inspect • Double-click to pivot]</title>
        </g>
      `;
    })
    .join("");

  svg.innerHTML = `
    <defs>
      <marker id="arrow-blue" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
        <path d="M 0 1 L 10 5 L 0 9 z" fill="${pal.primaryBlue}" />
      </marker>
      <marker id="arrow-red" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
        <path d="M 0 1 L 10 5 L 0 9 z" fill="#c0392b" />
      </marker>
      <marker id="arrow-amber" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
        <path d="M 0 1 L 10 5 L 0 9 z" fill="#e67e22" />
      </marker>
      <marker id="arrow-green" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
        <path d="M 0 1 L 10 5 L 0 9 z" fill="#2e7d32" />
      </marker>
    </defs>
    <g id="graph-viewport" transform="translate(${graphZoomState.tx},${graphZoomState.ty}) scale(${graphZoomState.scale})">
      ${guidesSvg}
      <g id="graph-edges-layer">${edgesSvg}</g>
      <g id="graph-nodes-layer">${nodesSvg}</g>
    </g>
  `;

  bindGraphInteractions(svg);
}

/**
 * Interactive Node Dragging + Canvas Pan/Zoom:
 * - Mousedown on `.graph-node`: starts dragging that specific node (`draggedNode`).
 * - Mousemove while `draggedNode`: updates `(draggedNode.x, draggedNode.y)` in SVG coordinates
 *   and updates connected edge lines & label pills in real time at 60fps!
 * - Mouseup after <5px movement: triggers click (`selectCompany` if it's a company node).
 * - Double-click on a company node: pivots the multi-hop graph onto that company!
 */
function bindGraphInteractions(svgEl) {
  let isCanvasPanning = false;
  let panStartX = 0;
  let panStartY = 0;

  // Attach node mousedown & dblclick listeners
  svgEl.querySelectorAll(".graph-node").forEach((nodeEl) => {
    nodeEl.addEventListener("mousedown", (ev) => {
      if (ev.button !== 0) return;
      ev.stopPropagation(); // Prevent canvas pan when grabbing a node
      const nodeId = nodeEl.getAttribute("data-node-id");
      const nodeObj = graphNodeMap.get(nodeId);
      if (!nodeObj) return;

      draggedNode = nodeObj;
      dragStartMouse = { x: ev.clientX, y: ev.clientY };
      dragMovedPx = 0;
      nodeEl.classList.add("dragging");
    });

    nodeEl.addEventListener("dblclick", (ev) => {
      ev.stopPropagation();
      const nodeId = nodeEl.getAttribute("data-node-id");
      const nodeObj = graphNodeMap.get(nodeId);
      if (nodeObj && nodeObj.company_number) {
        selectCompany(nodeObj.company_number);
      }
    });
  });

  svgEl.onwheel = (ev) => {
    ev.preventDefault();
    const rect = svgEl.getBoundingClientRect();
    const mx = ev.clientX - rect.left;
    const my = ev.clientY - rect.top;
    const oldScale = graphZoomState.scale;
    const factor = ev.deltaY < 0 ? 1.15 : 0.87;
    const newScale = Math.min(5.0, Math.max(0.25, oldScale * factor));
    graphZoomState.tx = mx - ((mx - graphZoomState.tx) * newScale) / oldScale;
    graphZoomState.ty = my - ((my - graphZoomState.ty) * newScale) / oldScale;
    graphZoomState.scale = newScale;
    const vp = document.getElementById("graph-viewport");
    if (vp) {
      vp.setAttribute("transform", `translate(${graphZoomState.tx},${graphZoomState.ty}) scale(${graphZoomState.scale})`);
    }
  };

  svgEl.onmousedown = (ev) => {
    if (ev.button !== 0 || draggedNode) return;
    isCanvasPanning = true;
    panStartX = ev.clientX - graphZoomState.tx;
    panStartY = ev.clientY - graphZoomState.ty;
  };

  svgEl.onmousemove = (ev) => {
    if (draggedNode) {
      const dxScreen = ev.clientX - dragStartMouse.x;
      const dyScreen = ev.clientY - dragStartMouse.y;
      dragMovedPx += Math.abs(dxScreen) + Math.abs(dyScreen);
      dragStartMouse = { x: ev.clientX, y: ev.clientY };

      // Convert screen delta to SVG viewport delta using current zoom scale
      draggedNode.x += dxScreen / graphZoomState.scale;
      draggedNode.y += dyScreen / graphZoomState.scale;
      draggedNode.pinned = true;

      updateDraggedNodeDom(svgEl, draggedNode);
      return;
    }

    if (isCanvasPanning) {
      graphZoomState.tx = ev.clientX - panStartX;
      graphZoomState.ty = ev.clientY - panStartY;
      const vp = document.getElementById("graph-viewport");
      if (vp) {
        vp.setAttribute("transform", `translate(${graphZoomState.tx},${graphZoomState.ty}) scale(${graphZoomState.scale})`);
      }
    }
  };

  const finishInteraction = () => {
    if (draggedNode) {
      const clickedNode = draggedNode;
      const moved = dragMovedPx;
      draggedNode = null;
      svgEl.querySelectorAll(".graph-node.dragging").forEach((el) => el.classList.remove("dragging"));

      if (moved < 6 && clickedNode.company_number) {
        selectCompany(clickedNode.company_number);
      }
    }
    isCanvasPanning = false;
  };

  svgEl.onmouseup = finishInteraction;
  svgEl.onmouseleave = finishInteraction;
}

function updateDraggedNodeDom(svgEl, nodeObj) {
  // Update the dragged node's transform immediately
  const nodeEl = svgEl.querySelector(`.graph-node[data-node-id="${CSS.escape(nodeObj.id)}"]`);
  if (nodeEl) {
    nodeEl.setAttribute("transform", `translate(${nodeObj.x.toFixed(1)},${nodeObj.y.toFixed(1)})`);
  }

  // Update all incident edges in real time
  graphEdges.forEach((e, idx) => {
    if (e.source !== nodeObj.id && e.target !== nodeObj.id) return;
    const s = graphNodeMap.get(e.source);
    const t = graphNodeMap.get(e.target);
    if (!s || !t) return;
    const { x1, y1, x2, y2, mx, my } = computeEdgeGeometry(s, t);
    const edgeGroup = svgEl.querySelector(`.graph-edge[data-edge-idx="${idx}"]`);
    if (!edgeGroup) return;
    const lineEl = edgeGroup.querySelector(".edge-line");
    if (lineEl) {
      lineEl.setAttribute("x1", x1.toFixed(1));
      lineEl.setAttribute("y1", y1.toFixed(1));
      lineEl.setAttribute("x2", x2.toFixed(1));
      lineEl.setAttribute("y2", y2.toFixed(1));
    }
    const lblEl = edgeGroup.querySelector(".edge-label-group");
    if (lblEl) {
      lblEl.setAttribute("transform", `translate(${mx.toFixed(1)},${my.toFixed(1)})`);
    }
  });
}

/* ============================================================================
   UNODC STEP 3-5 ASSOCIATION MATRIX & SPARROW SNA CENTRALITY VIEW
   ============================================================================ */

function renderUnodcAssociationMatrix() {
  const container = document.getElementById("graph-matrix-view");
  if (!container) return;

  // Order entities per UNODC Step 3 (p. 37): Individuals alphabetically, then Organisations, then Addresses
  const orderGroup = (n) =>
    n.pole_category === "Person" ? 1 : n.pole_category === "Organization" ? 2 : 3;
  const ordered = [...graphNodes]
    .sort((a, b) => orderGroup(a) - orderGroup(b) || (a.short_label || "").localeCompare(b.short_label || ""))
    .slice(0, 18); // Keep matrix readable

  const pairCode = new Map();
  graphEdges.forEach((e) => {
    const code = e.matrix_code || (e.confirmed !== false ? "●" : "○");
    pairCode.set(`${e.source}|${e.target}`, code);
    if (!pairCode.has(`${e.target}|${e.source}`)) {
      pairCode.set(`${e.target}|${e.source}`, code === "→" ? "←" : code);
    }
  });

  const headerCols = ordered
    .map((n, idx) => `<th title="${escapeHtml(n.label)}">${idx + 1}</th>`)
    .join("");

  const rowsHtml = ordered
    .map((rowNode, rIdx) => {
      const cells = ordered
        .map((colNode, cIdx) => {
          if (rIdx === cIdx) {
            return `<td class="matrix-cell-diag">${rIdx + 1}</td>`;
          }
          const sym = pairCode.get(`${rowNode.id}|${colNode.id}`) || "";
          const color =
            sym === "→" || sym === "←"
              ? "#38bdf8"
              : sym === "+"
              ? "#a855f7"
              : sym === "●"
              ? "#10b981"
              : sym === "○" || sym === "-"
              ? "#f59e0b"
              : "transparent";
          return `<td style="color:${color}; font-weight:800; font-size:13px;">${sym}</td>`;
        })
        .join("");

      return `
        <tr>
          <td style="text-align:left; font-weight:700; white-space:nowrap;">
            <code>#${rIdx + 1}</code> ${escapeHtml(rowNode.short_label || rowNode.id)}
            <span class="tech-tag">${escapeHtml(rowNode.pole_category || rowNode.node_type)}</span>
          </td>
          ${cells}
          <td><strong>${rowNode.degree || 0}</strong></td>
          <td><code>${Number(rowNode.betweenness_centrality || 0).toFixed(3)}</code></td>
          <td><span class="tech-tag">${escapeHtml(rowNode.unodc_grade || "A2")}</span></td>
        </tr>
      `;
    })
    .join("");

  container.innerHTML = `
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
      <div>
        <h3 style="margin:0; font-size:14px; color:var(--accent-gold);">
          UNODC Step 3–5 Association Matrix &amp; Malcolm Sparrow (1991) SNA Centrality
        </h3>
        <div style="font-size:11.5px; color:var(--text-secondary); margin-top:2px;">
          Codes (UNODC Manual Fig. 6-4, p. 38):
          <strong style="color:#38bdf8;">→</strong> Confirmed Investment/Ownership •
          <strong style="color:#a855f7;">+</strong> Confirmed Officer/PSC •
          <strong style="color:#10b981;">●</strong> Confirmed Link (A1–B2) •
          <strong style="color:#f59e0b;">○ / -</strong> Suspected / Inferred Link (C3)
        </div>
      </div>
      <button class="btn btn-sm btn-primary" onclick="setGraphLayout('organic')">Return to Graph Canvas</button>
    </div>
    <table class="matrix-table">
      <thead>
        <tr>
          <th style="text-align:left;">Entity (Ordered: People → Orgs → Locations)</th>
          ${headerCols}
          <th>Links (Step 5)</th>
          <th>Betweenness</th>
          <th>Grade</th>
        </tr>
      </thead>
      <tbody>
        ${rowsHtml}
      </tbody>
    </table>
  `;
}

function zoomGraphBy(factor) {
  graphZoomState.scale = Math.min(5.0, Math.max(0.25, graphZoomState.scale * factor));
  const vp = document.getElementById("graph-viewport");
  if (vp) {
    vp.setAttribute("transform", `translate(${graphZoomState.tx},${graphZoomState.ty}) scale(${graphZoomState.scale})`);
  }
}

function resetGraphZoom() {
  graphZoomState = { scale: 1, tx: 0, ty: 0 };
  const vp = document.getElementById("graph-viewport");
  if (vp) vp.setAttribute("transform", "translate(0,0) scale(1)");
}

function enableSvgPanZoom(svgEl, viewportId, stateObj) {
  let isPanning = false;
  let startX = 0;
  let startY = 0;

  svgEl.onwheel = (ev) => {
    ev.preventDefault();
    const rect = svgEl.getBoundingClientRect();
    const mx = ev.clientX - rect.left;
    const my = ev.clientY - rect.top;
    const oldScale = stateObj.scale;
    const factor = ev.deltaY < 0 ? 1.15 : 0.87;
    const newScale = Math.min(6.0, Math.max(0.25, oldScale * factor));
    stateObj.tx = mx - ((mx - stateObj.tx) * newScale) / oldScale;
    stateObj.ty = my - ((my - stateObj.ty) * newScale) / oldScale;
    stateObj.scale = newScale;
    const vp = document.getElementById(viewportId);
    if (vp) {
      vp.setAttribute("transform", `translate(${stateObj.tx},${stateObj.ty}) scale(${stateObj.scale})`);
    }
  };

  svgEl.onmousedown = (ev) => {
    if (ev.button !== 0) return;
    isPanning = true;
    startX = ev.clientX - stateObj.tx;
    startY = ev.clientY - stateObj.ty;
  };

  svgEl.onmousemove = (ev) => {
    if (!isPanning) return;
    stateObj.tx = ev.clientX - startX;
    stateObj.ty = ev.clientY - startY;
    const vp = document.getElementById(viewportId);
    if (vp) {
      vp.setAttribute("transform", `translate(${stateObj.tx},${stateObj.ty}) scale(${stateObj.scale})`);
    }
  };

  svgEl.onmouseup = () => {
    isPanning = false;
  };
  svgEl.onmouseleave = () => {
    isPanning = false;
  };
}

/* ============================================================================
   TAB 2: GEOSPATIAL UK MAP (OPENSTREETMAP FREE NO-KEY + ACTA DIURNA PATTERN)
   ============================================================================ */

/**
 * Acta Diurna / Samaritan square threat marker (`samSquare` from `ItalyMap.tsx`):
 * High-threat nodes are rendered as glowing squares rather than generic circles.
 */
function samSquareIcon(size, colorHex, filled) {
  return L.divIcon({
    className: "",
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    html: `<div style="width:${size}px;height:${size}px;border:2px solid ${colorHex};background:${
      filled ? colorHex : "rgba(15,23,42,0.75)"
    };box-shadow:0 0 ${filled ? 14 : 6}px ${colorHex};cursor:pointer;"></div>`,
  });
}

function initOrRefreshUkMap() {
  const mapDiv = document.getElementById("uk-leaflet-map");
  const svgFallback = document.getElementById("map-svg");

  if (typeof window.L !== "undefined" && mapDiv && currentBasemapStyle !== "offline-vector") {
    mapDiv.style.display = "block";
    if (svgFallback) svgFallback.style.display = "none";

    if (!ukLeafletMap) {
      ukLeafletMap = L.map("uk-leaflet-map", {
        center: [54.2, -2.5],
        zoom: 6,
        minZoom: 4,
        maxZoom: 19,
        zoomControl: false,
        scrollWheelZoom: true,
        dragging: true,
      });
      L.control.zoom({ position: "bottomright" }).addTo(ukLeafletMap);

      // Base UK Regions layer from vendorized `/static/uk_regions.geojson` (Acta Diurna pattern)
      ukBoundaryLayer = L.geoJSON(ukRegionsGeoJson || UK_BOUNDARY_GEOJSON, {
        style: () => ({
          color: "#38bdf8",
          weight: 1.3,
          opacity: 0.45,
          fillColor: "#112240",
          fillOpacity: 0.12,
        }),
      }).addTo(ukLeafletMap);

      updateLeafletThemeTiles();
      ukMarkersLayer = L.layerGroup().addTo(ukLeafletMap);
    }

    ukLeafletMap.invalidateSize();
    if (lastGeoJsonData) {
      renderLeafletMarkers(lastGeoJsonData);
    }
  } else {
    // 100% Offline Vector UK Map (Zero Network / Zero Tile Server)
    if (mapDiv) mapDiv.style.display = "none";
    if (svgFallback) {
      svgFallback.style.display = "block";
      if (lastGeoJsonData) renderUkSvgMap(lastGeoJsonData);
    }
  }
}

function changeBasemapStyle(styleName) {
  currentBasemapStyle = styleName;
  initOrRefreshUkMap();
  if (styleName !== "offline-vector") {
    updateLeafletThemeTiles();
  }
}

/**
 * Uses standard free OpenStreetMap tile servers (`tile.openstreetmap.org`)
 * which NEVER require an API key, with `.osm-tiles-dark` CSS filter for Dark Mode.
 */
function updateLeafletThemeTiles() {
  if (!ukLeafletMap || typeof window.L === "undefined") return;
  if (ukTileLayer) {
    ukLeafletMap.removeLayer(ukTileLayer);
    ukTileLayer = null;
  }
  if (currentBasemapStyle === "offline-vector") return;

  let tileUrl = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
  let tileClass = "";
  let attribution =
    '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap</a> contributors (Free / No API Key) • UK Regions GeoJSON';

  if (currentBasemapStyle === "osm-dark") {
    tileUrl = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
    tileClass = "osm-tiles-dark";
  } else if (currentBasemapStyle === "osm-hot") {
    tileUrl = "https://{s}.tile.openstreetmap.fr/hot/{z}/{x}/{y}.png";
    const isDark = (document.documentElement.getAttribute("data-theme") || "dark") === "dark";
    tileClass = isDark ? "osm-tiles-dark" : "";
    attribution =
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, HOT style';
  }

  ukTileLayer = L.tileLayer(tileUrl, {
    maxZoom: 19,
    // OSM tile usage policy rejects requests without a Referer (serves an "Access blocked" tile)
    referrerPolicy: "strict-origin-when-cross-origin",
    className: tileClass,
    attribution,
  }).addTo(ukLeafletMap);
}

/**
 * Acta Diurna `ItalyMap.tsx` Regional Highlighting:
 * When a company is selected, draws a dashed red regional boundary around its UK nation/region.
 */
function highlightSelectedCompanyOnMap(dossier) {
  if (!ukLeafletMap || !dossier || !ukRegionsGeoJson) return;
  if (ukActiveRegionLayer) {
    ukActiveRegionLayer.remove();
    ukActiveRegionLayer = null;
  }

  const pc = (dossier.company?.reg_address_postcode || "").toUpperCase();
  const country = (dossier.company?.country_of_origin || "").toUpperCase();
  let targetRegion = "England";
  if (pc.startsWith("EH") || pc.startsWith("G") || pc.startsWith("AB") || pc.startsWith("DD") || country.includes("SCOT")) {
    targetRegion = "Scotland";
  } else if (pc.startsWith("CF") || pc.startsWith("SA") || pc.startsWith("LL") || country.includes("WAL")) {
    targetRegion = "Wales";
  } else if (pc.startsWith("BT")) {
    targetRegion = "Northern Ireland";
  } else if (/^(EC|WC|E\d|W\d|N\d|NW|SE|SW)/.test(pc)) {
    targetRegion = "Greater London";
  }

  const feats = (ukRegionsGeoJson.features || []).filter(
    (f) => f.properties?.reg_name === targetRegion
  );
  if (feats.length > 0) {
    ukActiveRegionLayer = L.geoJSON(
      { type: "FeatureCollection", features: feats },
      {
        style: {
          color: "rgba(239, 68, 68, 0.85)",
          weight: 2.2,
          opacity: 0.9,
          fill: false,
          dashArray: "5, 5",
        },
      }
    ).addTo(ukLeafletMap);
  }
}

async function loadGeoMap(flaggedOnly = true) {
  lastFlaggedOnlyMap = flaggedOnly;
  try {
    const res = await fetch(`/api/geo/map?flagged_only=${flaggedOnly}&limit=450`);
    const geojson = await res.json();
    lastGeoJsonData = geojson;
    const featCount = (geojson.features || []).length;
    const mapTabActive = document.getElementById("view-map")?.classList.contains("active");
    if (mapTabActive) {
      document.getElementById("center-status").textContent =
        `UK Geospatial Intelligence (OpenStreetMap Free) — ${featCount} spatial features`;
    }

    initOrRefreshUkMap();
    if (ukLeafletMap && currentBasemapStyle !== "offline-vector") {
      renderLeafletMarkers(geojson);
    } else {
      renderUkSvgMap(geojson);
    }
  } catch (err) {
    console.error("Failed to load geo map:", err);
  }
}

function renderLeafletMarkers(geojson) {
  if (!ukLeafletMap || !ukMarkersLayer) return;
  ukMarkersLayer.clearLayers();

  const features = geojson.features || [];
  features.forEach((f) => {
    const g = f.geometry || {};
    const p = f.properties || {};

    if (g.type === "LineString" && g.coordinates?.length >= 2) {
      const [lon1, lat1] = g.coordinates[0];
      const [lon2, lat2] = g.coordinates[1];
      const line = L.polyline(
        [
          [lat1, lon1],
          [lat2, lon2],
        ],
        {
          color: "#a855f7",
          weight: 2.2,
          opacity: 0.82,
          dashArray: "5, 5",
        }
      );
      line.bindPopup(`
        <div style="min-width:210px;">
          <div style="font-weight:700; color:#a855f7; margin-bottom:4px;">Shared PSC / Controller Link</div>
          <div><strong>Controller:</strong> ${escapeHtml(p.controller_name || "Unknown")}</div>
          <div><strong>From:</strong> ${escapeHtml(p.from_name)} (<code>${escapeHtml(p.from_company)}</code>)</div>
          <div><strong>To:</strong> ${escapeHtml(p.to_name)} (<code>${escapeHtml(p.to_company)}</code>)</div>
          <div><strong>Distance:</strong> ${p.distance_km} km</div>
        </div>
      `);
      ukMarkersLayer.addLayer(line);
    } else if (g.type === "Point" && g.coordinates?.length === 2) {
      const [lon, lat] = g.coordinates;
      const score = Number(p.risk_score || 0);
      const fillColor = score >= 60 ? "#ef4444" : score >= 30 ? "#f59e0b" : "#38bdf8";

      const approximate = p.location_precision && p.location_precision !== "postcode";
      const precisionNote = approximate
        ? `<div style="font-size:11px; color:#f59e0b; margin-bottom:6px;">Approximate location: centre of the postcode ${escapeHtml(p.location_precision)}, not the exact address. Import ONSPD for exact positions.</div>`
        : "";

      let marker;
      // Acta Diurna / Samaritan convention: High-risk targets are glowing squares
      if (score >= 30 && !approximate) {
        const sqSize = Math.min(20, 10 + Math.round(Math.log2(Math.max(1, p.colocated_count || 1)) * 2.5));
        marker = L.marker([lat, lon], {
          icon: samSquareIcon(sqSize, fillColor, score >= 60),
        });
      } else {
        // Approximate positions: hollow dashed ring in the risk colour
        marker = L.circleMarker([lat, lon], {
          radius: approximate ? 8 : 6,
          fillColor,
          color: approximate ? fillColor : "#ffffff",
          weight: approximate ? 2 : 1.3,
          opacity: 0.9,
          fillOpacity: approximate ? 0.15 : 0.8,
          dashArray: approximate ? "3, 3" : null,
        });
      }

      marker.bindPopup(`
        <div style="min-width:230px;">
          <div style="font-weight:800; font-size:13px; margin-bottom:3px;">${escapeHtml(p.company_name)}</div>
          <div style="font-size:11.5px; margin-bottom:6px;">
            CRN: <code>${escapeHtml(p.company_number)}</code> • Postcode: <code>${escapeHtml(p.postcode || "")}</code>
          </div>
          <div style="font-size:11.5px; margin-bottom:4px;">
            <strong>Risk Score:</strong> <span style="color:${fillColor}; font-weight:700;">${score} / 100</span>
            • <strong>Co-located:</strong> ${p.colocated_count || 1} cos
          </div>
          <div style="font-size:11px; color:#94a3b8; margin-bottom:8px;">
            ${escapeHtml(p.address || p.district || "")}
          </div>
          ${precisionNote}
          <div style="display:flex; gap:6px;">
            <button class="btn btn-sm btn-primary" onclick="selectCompany('${p.company_number}')">Inspect Dossier</button>
            <button class="btn btn-sm" onclick="selectCompany('${p.company_number}'); switchTab('graph');">Network Graph</button>
          </div>
        </div>
      `);

      marker.on("click", () => {
        selectCompany(p.company_number);
      });

      ukMarkersLayer.addLayer(marker);
    }
  });
}

function zoomUkMap(delta) {
  if (ukLeafletMap && currentBasemapStyle !== "offline-vector") {
    if (delta > 0) ukLeafletMap.zoomIn();
    else ukLeafletMap.zoomOut();
  } else {
    const factor = delta > 0 ? 1.25 : 0.8;
    mapZoomState.scale = Math.min(6.0, Math.max(0.4, mapZoomState.scale * factor));
    const vp = document.getElementById("map-viewport");
    if (vp) {
      vp.setAttribute("transform", `translate(${mapZoomState.tx},${mapZoomState.ty}) scale(${mapZoomState.scale})`);
    }
  }
}

function resetUkMapView() {
  if (ukLeafletMap && currentBasemapStyle !== "offline-vector") {
    ukLeafletMap.flyTo([54.2, -2.5], 6, { duration: 0.6 });
  } else {
    mapZoomState = { scale: 1, tx: 0, ty: 0 };
    const vp = document.getElementById("map-viewport");
    if (vp) vp.setAttribute("transform", "translate(0,0) scale(1)");
  }
}

function focusMapOnLondon() {
  if (ukLeafletMap && currentBasemapStyle !== "offline-vector") {
    ukLeafletMap.flyTo([51.515, -0.105], 12, { duration: 0.7 });
  }
}

function renderUkSvgMap(geojson) {
  const svg = document.getElementById("map-svg");
  if (!svg) return;
  const rect = svg.getBoundingClientRect();
  const width = Math.max(rect.width || 760, 680);
  const height = Math.max(rect.height || 580, 520);

  const minLat = 49.0, maxLat = 59.4;
  const minLon = -8.6, maxLon = 2.4;

  const project = (lon, lat) => {
    const x = ((lon - minLon) / (maxLon - minLon)) * (width - 100) + 50;
    const y = ((maxLat - lat) / (maxLat - minLat)) * (height - 60) + 30;
    return [x, y];
  };

  const sourceRegions = ukRegionsGeoJson || UK_BOUNDARY_GEOJSON;
  const ukPolygonsSvg = (sourceRegions.features || [])
    .map((feat) => {
      const ring = feat.geometry.coordinates[0];
      const pts = ring
        .map(([lon, lat]) => {
          const [x, y] = project(lon, lat);
          return `${x.toFixed(1)},${y.toFixed(1)}`;
        })
        .join(" ");
      return `<polygon points="${pts}" fill="#112240" fill-opacity="0.75" stroke="#38bdf8" stroke-width="1.5" stroke-opacity="0.65" />`;
    })
    .join("");

  const refCities = [
    { name: "London", lat: 51.5074, lon: -0.1278 },
    { name: "Birmingham", lat: 52.4862, lon: -1.8904 },
    { name: "Manchester", lat: 53.4808, lon: -2.2426 },
    { name: "Leeds", lat: 53.8008, lon: -1.5491 },
    { name: "Edinburgh", lat: 55.9533, lon: -3.1883 },
    { name: "Glasgow", lat: 55.8642, lon: -4.2518 },
    { name: "Cardiff", lat: 51.4816, lon: -3.1791 },
    { name: "Belfast", lat: 54.5973, lon: -5.9301 },
  ];

  const citiesSvg = refCities
    .map((c) => {
      const [x, y] = project(c.lon, c.lat);
      return `
        <g transform="translate(${x.toFixed(1)},${y.toFixed(1)})">
          <circle r="2.5" fill="#94a3b8" />
          <text x="6" y="3" fill="#94a3b8" font-size="10" font-weight="600">${c.name}</text>
        </g>
      `;
    })
    .join("");

  const features = geojson.features || [];
  const linesSvg = [];
  const pointsSvg = [];

  features.forEach((f) => {
    const g = f.geometry || {};
    const p = f.properties || {};
    if (g.type === "LineString") {
      const [lon1, lat1] = g.coordinates[0];
      const [lon2, lat2] = g.coordinates[1];
      const [x1, y1] = project(lon1, lat1);
      const [x2, y2] = project(lon2, lat2);
      linesSvg.push(`
        <line x1="${x1.toFixed(1)}" y1="${y1.toFixed(1)}" x2="${x2.toFixed(1)}" y2="${y2.toFixed(1)}"
              stroke="#a855f7" stroke-width="1.6" stroke-dasharray="4,3" stroke-opacity="0.75">
          <title>Shared Controller: ${escapeHtml(p.controller_name || "")} (${p.distance_km} km)</title>
        </line>
      `);
    } else if (g.type === "Point") {
      const [lon, lat] = g.coordinates;
      const [x, y] = project(lon, lat);
      const score = Number(p.risk_score || 0);
      const fill = score >= 60 ? "#ef4444" : score >= 30 ? "#f59e0b" : "#38bdf8";
      const s = Math.min(16, 8 + Math.log2(Math.max(1, p.colocated_count || 1)) * 2.2);
      pointsSvg.push(`
        <rect x="${(x - s / 2).toFixed(1)}" y="${(y - s / 2).toFixed(1)}" width="${s.toFixed(1)}" height="${s.toFixed(1)}"
              fill="${fill}" fill-opacity="0.82" stroke="#ffffff" stroke-width="1.2"
              style="cursor:pointer;" onclick="selectCompany('${p.company_number}')">
          <title>${escapeHtml(p.company_name)} (${p.company_number})\nPostcode: ${p.postcode} | Risk: ${score} | Co-located: ${p.colocated_count}</title>
        </rect>
      `);
    }
  });

  svg.innerHTML = `
    <g id="map-viewport" transform="translate(${mapZoomState.tx},${mapZoomState.ty}) scale(${mapZoomState.scale})">
      ${ukPolygonsSvg}
      ${citiesSvg}
      ${linesSvg.join("")}
      ${pointsSvg.join("")}
    </g>
  `;
  enableSvgPanZoom(svg, "map-viewport", mapZoomState);
}

async function loadHotspots() {
  try {
    const res = await fetch("/api/geo/hotspots?min_companies=2&limit=30");
    const data = await res.json();
    const list = data.hotspots || [];
    const container = document.getElementById("hotspots-list");
    if (!container) return;
    container.innerHTML = list
      .map(
        (h) => `
        <div class="dossier-card" style="margin-bottom:8px; cursor:pointer;"
             onclick="focusHotspotOnMap('${escapeHtml(h.postcode || "")}', ${h.lat || "null"}, ${h.lon || "null"})">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <strong>${escapeHtml(h.postcode || h.address_fingerprint)}</strong>
            <span class="risk-badge ${riskClass(h.max_risk_score)}">${h.company_count} companies</span>
          </div>
          <div style="font-size:11.5px; color:var(--text-secondary); margin-top:4px;">
            ${escapeHtml(h.sample_address || "")}, ${escapeHtml(h.post_town || "")}
          </div>
          <div style="font-size:11px; color:var(--text-muted); margin-top:4px;">
            Flagged: <strong>${h.flagged_count}</strong> • Max Risk: <strong>${h.max_risk_score}</strong>
          </div>
        </div>
      `
      )
      .join("");
  } catch (err) {
    console.error("Failed to load hotspots:", err);
  }
}

function focusHotspotOnMap(postcode, lat, lon) {
  if (ukLeafletMap && currentBasemapStyle !== "offline-vector" && lat !== null && lon !== null) {
    ukLeafletMap.flyTo([lat, lon], 14, { duration: 0.7 });
  }
  filterByPostcode(postcode);
}

function filterByPostcode(postcode) {
  const input = document.getElementById("search-input");
  if (input) {
    input.value = postcode;
    loadCompanies();
  }
}

/* ============================================================================
   TAB 3: TIMELINE & FT3 TAXONOMY MATRIX
   ============================================================================ */

function renderTimelineAndFt3(d) {
  const container = document.getElementById("timeline-and-ft3-container");
  if (!container) return;
  const tl = d.timeline || [];
  const activeSet = new Set(d.company?.ft3_techniques || []);

  const tlHtml = tl.length
    ? tl
        .map(
          (ev) => `
          <div style="display:grid; grid-template-columns:110px 150px 1fr 170px; gap:10px; padding:8px 10px; border-bottom:1px solid var(--border-subtle); align-items:center;">
            <code>${escapeHtml(ev.date)}</code>
            <span class="tech-tag">${escapeHtml(ev.event_type)}</span>
            <strong>${escapeHtml(ev.title)}</strong>
            <span style="font-size:11px; color:var(--text-secondary); text-align:right;">${escapeHtml(ev.source)}</span>
          </div>
        `
        )
        .join("")
    : `<div style="color:var(--text-secondary);">No timeline events available.</div>`;

  const matrixHtml = ft3MetadataList
    .map((t) => {
      const triggered = activeSet.has(t.code);
      return `
        <div class="dossier-card" style="border-color:${triggered ? "var(--risk-critical)" : "var(--border-subtle)"}; opacity:${triggered ? "1" : "0.75"};">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
            <div>
              <span class="risk-badge ${t.priority === "CRITICAL" ? "risk-critical" : t.priority === "HIGH" ? "risk-high" : "risk-medium"}">${t.priority}</span>
              <strong style="margin-left:6px;">${t.code} — ${escapeHtml(t.name)}</strong>
              <span style="color:var(--text-secondary); font-size:11px; margin-left:6px;">(${escapeHtml(t.tactic)})</span>
            </div>
            <div>
              ${triggered ? `<span class="risk-badge risk-critical">TRIGGERED ON SUBJECT</span>` : `<span class="tech-tag">INACTIVE</span>`}
              <span class="tech-tag">Default UNODC: ${t.default_grade}</span>
            </div>
          </div>
          <div style="font-size:12px; margin-top:4px;">${escapeHtml(t.description)}</div>
          <div class="innocent-details">
            <strong>Mandatory ICD 203 Innocent Explanations:</strong> ${(t.innocent_explanations || []).map(escapeHtml).join(" | ")}
          </div>
        </div>
      `;
    })
    .join("");

  container.innerHTML = `
    <div class="dossier-card" style="margin-bottom:16px;">
      <h3><span>Chronological Event Timeline — ${escapeHtml(d.company.company_name)}</span><span>${tl.length} events</span></h3>
      ${tlHtml}
    </div>
    <h3 style="margin:12px 0 8px 0; text-transform:uppercase; font-size:12px; color:var(--text-secondary);">
      Stripe FT3 Shell Company Threat Taxonomy &amp; UNODC 4x4 Evaluation Matrix
    </h3>
    <div style="display:flex; flex-direction:column; gap:10px;">
      ${matrixHtml}
    </div>
  `;
}

/* ============================================================================
   TAB 4: FOLLOW THE MONEY (FtM v3.x) INSPECTOR
   ============================================================================ */

function renderFtmInspector(d) {
  const container = document.getElementById("ftm-inspector-content");
  if (!container || !d.ftm_entity) return;
  const ftm = d.ftm_entity;
  const propsRows = Object.entries(ftm.properties || {})
    .map(
      ([k, vals]) => `
      <tr>
        <td style="padding:6px 10px; border-bottom:1px solid var(--border-subtle); font-weight:600; width:180px;"><code>${escapeHtml(k)}</code></td>
        <td style="padding:6px 10px; border-bottom:1px solid var(--border-subtle);">${(vals || []).map((v) => `<code>${escapeHtml(String(v))}</code>`).join(", ")}</td>
      </tr>
    `
    )
    .join("");

  container.innerHTML = `
    <div style="display:grid; grid-template-columns: 1fr 1fr; gap:14px;">
      <div class="dossier-card">
        <h3><span>FtM Entity Properties</span><span>Schema: ${escapeHtml(ftm.schema)}</span></h3>
        <div style="margin-bottom:10px; font-size:12px;">
          <div><strong>Canonical FtM ID:</strong> <code>${escapeHtml(ftm.id)}</code></div>
          <div><strong>Caption:</strong> ${escapeHtml(ftm.caption)}</div>
          <div><strong>Datasets:</strong> <code>${escapeHtml((ftm.datasets || []).join(", "))}</code></div>
          <div><strong>Cross-Dataset Referents:</strong> <code>${escapeHtml((ftm.referents || []).join(", ") || "None")}</code></div>
        </div>
        <table style="width:100%; border-collapse:collapse; font-size:12px;">
          <tbody>${propsRows}</tbody>
        </table>
      </div>
      <div class="dossier-card">
        <h3><span>Canonical .ftm.json Payload (Aleph / OpenSanctions / Quaesitor)</span><span>JSONL</span></h3>
        <pre class="code-block">${escapeHtml(JSON.stringify(ftm, null, 2))}</pre>
      </div>
    </div>
  `;
}

function exportSelectedCompanyFtm() {
  if (!currentCompanyNumber) return;
  window.location.href = `/api/export/ftm?company_number=${encodeURIComponent(currentCompanyNumber)}`;
}

/* ============================================================================
   TAB 5: CASEWORK & INVESTIGATIONS
   ============================================================================ */

async function loadInvestigations() {
  try {
    const res = await fetch("/api/investigations");
    const data = await res.json();
    const items = data.items || [];
    if (items.length && !activeInvestigationId) {
      activeInvestigationId = items[0].id;
    }
    if (activeInvestigationId) {
      const detailRes = await fetch(`/api/investigations/${activeInvestigationId}`);
      const invDetail = await detailRes.json();
      renderCaseworkTab(items, invDetail);
    }
  } catch (err) {
    console.error("Failed to load investigations:", err);
  }
}

function renderCaseworkTab(allCases, activeCase) {
  const container = document.getElementById("casework-container");
  if (!container) return;

  const entitiesHtml = (activeCase.entities || [])
    .map(
      (e) => `
      <div style="display:flex; justify-content:space-between; align-items:center; padding:8px; border-bottom:1px solid var(--border-subtle); cursor:pointer;"
           onclick="selectCompany('${e.entity_id}')">
        <div>
          <strong>${escapeHtml(e.company_name || e.entity_id)}</strong> (<code>${escapeHtml(e.entity_id)}</code>)
          <div style="font-size:11px; color:var(--text-secondary);">Role: <code>${escapeHtml(e.role_in_case)}</code> • ${escapeHtml(e.notes || "")}</div>
        </div>
        <span class="risk-badge ${riskClass(e.risk_score || 0)}">${Number(e.risk_score || 0).toFixed(1)}</span>
      </div>
    `
    )
    .join("");

  const annotationsHtml = (activeCase.annotations || [])
    .map(
      (a) => `
      <div class="flag-box HIGH" style="margin-bottom:8px;">
        <div style="display:flex; justify-content:space-between; font-size:11px; color:var(--text-secondary); margin-bottom:4px;">
          <span>Entity: <code>${escapeHtml(a.entity_id || "Case-level")}</code> • Type: <strong>${escapeHtml(a.annotation_type)}</strong></span>
          <span>UNODC Grade: <code>${escapeHtml(a.source_grade)}</code> • Confidence: <strong>${escapeHtml(a.confidence)}</strong></span>
        </div>
        <div style="font-size:12.5px;">${escapeHtml(a.annotation_text)}</div>
      </div>
    `
    )
    .join("");

  container.innerHTML = `
    <div style="display:grid; grid-template-columns: 1fr 1fr; gap:14px;">
      <div class="dossier-card">
        <h3><span>Active Investigation Case</span><span class="badge-pill">${escapeHtml(activeCase.classification || "CONFIDENTIAL")}</span></h3>
        <div style="font-size:15px; font-weight:700; margin-bottom:6px;">${escapeHtml(activeCase.title)}</div>
        <p style="font-size:12px; color:var(--text-secondary); margin:0 0 8px 0;">${escapeHtml(activeCase.description || "")}</p>
        <div class="innocent-details" style="margin-bottom:12px;">
          <strong>Working Hypothesis:</strong> ${escapeHtml(activeCase.hypothesis || "N/A")}
        </div>
        <h3><span>Enrolled Target Entities (${(activeCase.entities || []).length})</span></h3>
        ${entitiesHtml || "<div>No entities enrolled yet.</div>"}
      </div>

      <div class="dossier-card">
        <h3><span>Analyst Findings &amp; UNODC 4x4 Annotations</span></h3>
        <div style="margin-bottom:12px; display:flex; flex-direction:column; gap:8px;">
          <textarea id="new-annotation-text" rows="3" placeholder="Write BLUF finding or analytic note (ICD 203)..."></textarea>
          <div style="display:flex; gap:8px;">
            <select id="new-annotation-grade">
              <option value="A1">Grade A1 (Confirmed Statutory)</option>
              <option value="A2">Grade A2 (Official Registry)</option>
              <option value="B2" selected>Grade B2 (PSC / ICIJ Leak)</option>
              <option value="C3">Grade C3 (Fuzzy / Indirect Lead)</option>
            </select>
            <select id="new-annotation-conf">
              <option value="high" selected>High Confidence</option>
              <option value="moderate">Moderate Confidence</option>
              <option value="low">Low Confidence</option>
            </select>
            <button class="btn btn-primary" onclick="submitAnnotation()">Save Finding</button>
          </div>
        </div>
        ${annotationsHtml}
      </div>
    </div>
  `;
}

async function submitAnnotation() {
  const txt = document.getElementById("new-annotation-text")?.value?.trim();
  const grade = document.getElementById("new-annotation-grade")?.value || "B2";
  const conf = document.getElementById("new-annotation-conf")?.value || "high";
  if (!txt || !activeInvestigationId) return;

  await fetch(`/api/investigations/${activeInvestigationId}/annotations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      entity_type: "company",
      entity_id: currentCompanyNumber,
      annotation_text: txt,
      annotation_type: "finding",
      confidence: conf,
      source_grade: grade,
    }),
  });
  await loadInvestigations();
  if (currentCompanyNumber) await selectCompany(currentCompanyNumber);
}

async function enrollCurrentInCase() {
  if (!currentCompanyNumber || !activeInvestigationId) return;
  await fetch(`/api/investigations/${activeInvestigationId}/entities`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      entity_type: "company",
      entity_id: currentCompanyNumber,
      role_in_case: "subject",
      notes: `Added by analyst from Dossier view`,
    }),
  });
  switchTab("casework");
  await loadInvestigations();
}

function openPrintableReport() {
  if (!currentCompanyNumber) return;
  window.open(`/api/reports/company/${encodeURIComponent(currentCompanyNumber)}`, "_blank");
}

function handleQuickExport(selectEl) {
  const fmt = selectEl.value;
  if (!fmt) return;
  selectEl.value = "";
  const cParam = currentCompanyNumber ? `&company_number=${encodeURIComponent(currentCompanyNumber)}` : "";
  window.location.href = `/api/export/${fmt}?flagged_only=true${cParam}`;
}

async function rescoreDatabase() {
  const res = await fetch("/api/score/run", { method: "POST" });
  if (res.ok) {
    await loadDashboardStats();
    await loadCompanies();
    if (currentCompanyNumber) await selectCompany(currentCompanyNumber);
  }
}

function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
