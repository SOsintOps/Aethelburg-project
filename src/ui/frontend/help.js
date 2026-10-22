/* ============================================================================
   USER GUIDE: in-app help panel over docs/guide/*.md (served by /api/help)
   ============================================================================ */

const TAB_HELP_CHAPTERS = {
  graph: "network-graph",
  map: "geoint-and-hubs",
  timeline: "timeline-and-ft3-matrix",
  ftm: "followthemoney",
  casework: "casework-and-reports",
  data: "data-and-updates",
  settings: "companies-house-api",
};
let helpChapters = [];
const helpCache = {};

function currentHelpChapter() {
  const active = document.querySelector(".tab-btn.active")?.dataset.tab;
  return TAB_HELP_CHAPTERS[active] || "getting-started";
}

async function openHelp(slug) {
  ensureHelpOverlay();
  document.getElementById("help-overlay").style.display = "flex";
  if (!helpChapters.length) {
    try {
      helpChapters = (await (await fetch("/api/help")).json()).chapters || [];
    } catch (err) {
      helpChapters = [];
    }
  }
  renderHelpIndex(slug);
  await showHelpChapter(slug || "getting-started");
}

function closeHelp() {
  const overlay = document.getElementById("help-overlay");
  if (overlay) overlay.style.display = "none";
}

function ensureHelpOverlay() {
  if (document.getElementById("help-overlay")) return;
  document.body.insertAdjacentHTML(
    "beforeend",
    `<div id="help-overlay" style="position:fixed; inset:0; background:rgba(0,0,0,0.45); z-index:5000; display:none; align-items:center; justify-content:center;" onclick="if (event.target === this) closeHelp()">
      <div style="background:var(--bg-panel); color:var(--text-primary); width:min(1100px, 94vw); height:min(820px, 90vh); display:grid; grid-template-columns:260px 1fr; border:1px solid var(--border-subtle); box-shadow:0 10px 40px rgba(0,0,0,0.35);">
        <nav style="border-right:1px solid var(--border-subtle); padding:12px; overflow-y:auto;">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            <strong>Aethelburg guide</strong>
            <button class="btn btn-sm" onclick="closeHelp()" title="Close (Esc)">×</button>
          </div>
          <input type="search" id="help-search" class="input-field" placeholder="Search the guide…" oninput="searchHelp(this.value)" style="width:100%; margin-bottom:8px;">
          <div id="help-index"></div>
        </nav>
        <article id="help-content" class="help-content" style="padding:18px 26px; overflow-y:auto; font-size:13px; line-height:1.55;"></article>
      </div>
    </div>`
  );
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeHelp();
  });
}

function renderHelpIndex(activeSlug, matches) {
  const index = document.getElementById("help-index");
  if (!index) return;
  const list = matches || helpChapters;
  index.innerHTML = list.length
    ? list
        .map(
          (c) => `<div style="padding:5px 6px; cursor:pointer; ${c.slug === activeSlug ? "font-weight:700; color:var(--accent-gold);" : ""}"
                     onclick="showHelpChapter('${c.slug}')">${escapeHtml(c.title)}</div>`
        )
        .join("")
    : `<div style="color:var(--text-secondary); font-size:12px;">No chapter matches.</div>`;
}

async function loadHelpMarkdown(slug) {
  if (!helpCache[slug]) {
    const res = await fetch(`/api/help/${encodeURIComponent(slug)}`);
    if (!res.ok) throw new Error(`Chapter not found: ${slug}`);
    helpCache[slug] = (await res.json()).markdown;
  }
  return helpCache[slug];
}

async function showHelpChapter(slug) {
  const content = document.getElementById("help-content");
  if (!content) return;
  try {
    content.innerHTML = renderMarkdown(await loadHelpMarkdown(slug));
  } catch (err) {
    content.innerHTML = `<p>${escapeHtml(err.message)}</p>`;
  }
  content.scrollTop = 0;
  if (!document.getElementById("help-search")?.value) renderHelpIndex(slug);
}

async function searchHelp(term) {
  const q = term.trim().toLowerCase();
  if (!q) return renderHelpIndex(null);
  await Promise.all(helpChapters.map((c) => loadHelpMarkdown(c.slug).catch(() => "")));
  renderHelpIndex(null, helpChapters.filter((c) => (helpCache[c.slug] || "").toLowerCase().includes(q)));
}

document.addEventListener("keydown", (e) => {
  if (e.key === "F1") {
    e.preventDefault();
    openHelp(currentHelpChapter());
  }
});

/* ---------- Minimal Markdown renderer (headings, lists, tables, code, links) ---------- */

function renderInline(text) {
  return escapeHtml(text)
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (m, label, href) =>
      /^https?:\/\//.test(href)
        ? `<a href="${href}" target="_blank" rel="noopener noreferrer">${label}</a>`
        : /[./]/.test(href) // a file of the repository, not a chapter: show it as text
        ? label
        : `<a href="#" onclick="showHelpChapter('${href.replace(/[^a-z0-9-]/gi, "")}'); return false;">${label}</a>`
    );
}

function renderMarkdown(md) {
  const lines = md.replace(/\r\n/g, "\n").split("\n");
  const out = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.startsWith("```")) {
      const code = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) code.push(lines[i++]);
      i++;
      out.push(`<pre style="background:var(--bg-card); padding:8px 10px; overflow-x:auto;"><code>${escapeHtml(code.join("\n"))}</code></pre>`);
      continue;
    }
    const heading = line.match(/^(#{1,3})\s+(.*)$/);
    if (heading) {
      const level = heading[1].length;
      out.push(`<h${level + 1}>${renderInline(heading[2])}</h${level + 1}>`);
      i++;
      continue;
    }
    if (line.startsWith("|")) {
      const rows = [];
      while (i < lines.length && lines[i].startsWith("|")) rows.push(lines[i++]);
      const cells = (r) => r.replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      const body = rows.filter((r) => !/^\|[\s|:-]+\|$/.test(r));
      out.push(
        `<table class="matrix-table" style="width:100%; margin:8px 0;"><thead><tr>${cells(body[0]).map((c) => `<th>${renderInline(c)}</th>`).join("")}</tr></thead><tbody>` +
          body.slice(1).map((r) => `<tr>${cells(r).map((c) => `<td>${renderInline(c)}</td>`).join("")}</tr>`).join("") +
          "</tbody></table>"
      );
      continue;
    }
    if (/^\s*(-|\d+\.)\s+/.test(line)) {
      const ordered = /^\s*\d+\./.test(line);
      const items = [];
      while (i < lines.length && /^\s*(-|\d+\.)\s+/.test(lines[i])) {
        items.push(lines[i++].replace(/^\s*(-|\d+\.)\s+/, ""));
      }
      const tag = ordered ? "ol" : "ul";
      out.push(`<${tag}>${items.map((t) => `<li>${renderInline(t)}</li>`).join("")}</${tag}>`);
      continue;
    }
    if (!line.trim()) {
      i++;
      continue;
    }
    const para = [];
    while (i < lines.length && lines[i].trim() && !/^(#|\||```|\s*(-|\d+\.)\s)/.test(lines[i])) para.push(lines[i++]);
    out.push(`<p>${renderInline(para.join(" "))}</p>`);
  }
  return out.join("\n");
}
