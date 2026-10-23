/* ============================================================================
   ACTIVITY INDICATOR
   ----------------------------------------------------------------------------
   The analyst must always know whether the program is working or stuck:
   - every request to the server is counted; after 0.4 s a pill in the top bar names
     what is being waited for and for how long, and says when the database is busy;
   - a failed connection shows "server not responding";
   - a background task (re-score, import, download, officers, backup) is shown with
     the time elapsed and an estimate of the time left, from its progress or from how
     long the same task took last time (kept in this browser).
   ============================================================================ */

const ACTIVITY_SHOW_AFTER_MS = 400;
const ACTIVITY_SLOW_AFTER_MS = 8000;
const ACTIVITY_JOB_POLL_MS = 15000;
const ACTIVITY_JOB_TITLES = {
  score: "FT3 re-score",
  import: "Import",
  download: "Download",
  officers: "Officers from Companies House",
  daily: "Daily update",
  backup: "Backup",
};

const activityState = {
  inflight: new Map(), // id -> { label, started }
  nextId: 1,
  serverDownUntil: 0,
  job: null,
  jobSeenAt: 0,
};

function activityLabel(url) {
  const u = String(url || "");
  if (u.includes("/api/companies?")) return "search";
  if (u.includes("/api/index/search") || u.includes("/api/persons/search")) return "search";
  if (u.includes("/graph")) return "network graph";
  if (u.includes("/api/companies/") && u.includes("/refresh")) return "Companies House";
  if (u.includes("/filings") || u.includes("/documents")) return "filing history";
  if (u.includes("/api/companies/")) return "dossier";
  if (u.includes("/api/stats")) return "counters";
  if (u.includes("/api/geo/")) return "map";
  if (u.includes("/api/ch/")) return "Companies House";
  if (u.includes("/api/data/")) return "data status";
  if (u.includes("/api/score")) return "re-score";
  if (u.includes("/api/export") || u.includes("/api/report")) return "export";
  return "server";
}

(function wrapFetch() {
  const original = window.fetch.bind(window);
  window.fetch = async (input, init) => {
    const url = typeof input === "string" ? input : input?.url || "";
    const id = activityState.nextId++;
    const isApi = url.startsWith("/api/") || url.includes("/api/");
    if (isApi) activityState.inflight.set(id, { label: activityLabel(url), started: Date.now() });
    try {
      return await original(input, init);
    } catch (err) {
      // a network failure means the server is gone or frozen, not a slow query
      if (isApi && !(err && err.name === "AbortError")) activityState.serverDownUntil = Date.now() + 6000;
      throw err;
    } finally {
      activityState.inflight.delete(id);
    }
  };
})();

function formatDuration(ms) {
  const s = Math.max(0, Math.round(ms / 1000));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min`;
  return `${Math.floor(m / 60)} h ${m % 60} min`;
}

function jobDurationKey(kind) {
  return `aethelburg.jobdur.${kind}`;
}

function rememberJobDuration(job) {
  if (!job || job.status !== "completed" || !job.started_at || !job.finished_at) return;
  const ms = Date.parse(job.finished_at) - Date.parse(job.started_at);
  if (ms > 0) {
    try {
      localStorage.setItem(jobDurationKey(job.kind), String(ms));
    } catch (err) {
      /* browser storage unavailable: no estimate next time */
    }
  }
}

function lastJobDuration(kind) {
  try {
    const v = Number(localStorage.getItem(jobDurationKey(kind)));
    return v > 0 ? v : null;
  } catch (err) {
    return null;
  }
}

/** Text for a running background task: elapsed time and what is known about the time left. */
function describeJob(job) {
  const title = ACTIVITY_JOB_TITLES[job.kind] || job.kind;
  const elapsed = Date.now() - Date.parse(job.started_at);
  let left = "";
  if (job.total && job.progress) {
    const rate = job.progress / Math.max(elapsed, 1);
    left = `about ${formatDuration((job.total - job.progress) / rate)} left`;
  } else {
    const last = lastJobDuration(job.kind);
    if (last) left = elapsed < last ? `about ${formatDuration(last - elapsed)} left (last run took ${formatDuration(last)})` : `longer than last time (${formatDuration(last)})`;
    else left = "first run: no estimate yet";
  }
  const stage = job.stage ? ` · ${job.stage}` : "";
  return `${title} running${stage} · ${formatDuration(elapsed)} elapsed · ${left}`;
}

async function pollBackgroundJob() {
  try {
    const res = await fetch("/api/data/status?check_remote=false");
    if (!res.ok) return;
    const st = await res.json();
    activityState.job = st.job && st.job.status === "running" ? st.job : null;
    activityState.jobSeenAt = Date.now();
    (st.job_history || []).forEach(rememberJobDuration);
    if (st.job && st.job.status === "completed") rememberJobDuration(st.job);
  } catch (err) {
    /* the fetch wrapper already marks the server as unreachable */
  }
}

function renderActivityPill() {
  const pill = document.getElementById("activity-pill");
  if (!pill) return;
  const now = Date.now();
  let text = "";
  let cls = "activity-pill";

  if (activityState.serverDownUntil > now) {
    text = "Server not responding — is it still running? Check the terminal window";
    cls += " activity-down";
  } else {
    let oldest = null;
    activityState.inflight.forEach((r) => {
      if (!oldest || r.started < oldest.started) oldest = r;
    });
    if (oldest && now - oldest.started >= ACTIVITY_SHOW_AFTER_MS) {
      const waited = now - oldest.started;
      const others = activityState.inflight.size - 1;
      text = `Working: ${oldest.label} · ${formatDuration(waited)}${others > 0 ? ` (+${others} more)` : ""}`;
      if (waited >= ACTIVITY_SLOW_AFTER_MS) {
        text += activityState.job ? ` — the database is busy with the ${ACTIVITY_JOB_TITLES[activityState.job.kind] || activityState.job.kind}` : " — the database is busy, still waiting";
        cls += " activity-slow";
      } else {
        cls += " activity-busy";
      }
    } else if (activityState.job) {
      text = describeJob(activityState.job);
      cls += " activity-job";
    }
  }

  if (!text) {
    pill.hidden = true;
    return;
  }
  pill.hidden = false;
  pill.className = cls;
  pill.textContent = text;
  pill.title = activityState.job ? "Click to open Data & Updates, where the task is listed" : "What the program is waiting for";
}

document.addEventListener("DOMContentLoaded", () => {
  const pill = document.getElementById("activity-pill");
  if (pill) {
    pill.addEventListener("click", () => {
      if (activityState.job && typeof switchTab === "function") switchTab("data");
    });
  }
  setInterval(renderActivityPill, 500);
  pollBackgroundJob();
  setInterval(pollBackgroundJob, ACTIVITY_JOB_POLL_MS);
});
