// Single-file React dashboard. Uses htm tagged templates so we don't need JSX.
import React, { useEffect, useState, useCallback, useRef } from "react";
import { createRoot } from "react-dom/client";
import htm from "htm";

const html = htm.bind(React.createElement);

// ─── API ───────────────────────────────────────────────────────────────────

const api = {
  async getPreferences() {
    const r = await fetch("/api/preferences");
    if (!r.ok) throw new Error(`prefs: ${r.status}`);
    return r.json();
  },
  async updatePreferences(payload) {
    const r = await fetch("/api/preferences", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!r.ok) {
      const body = await r.json().catch(() => ({}));
      throw new Error(body.detail?.fields ? JSON.stringify(body.detail.fields) : `prefs put: ${r.status}`);
    }
    return r.json();
  },
  async typeaheadLocations(q) {
    const r = await fetch(`/api/locations/typeahead?q=${encodeURIComponent(q)}`);
    if (!r.ok) throw new Error(`typeahead: ${r.status}`);
    return r.json();
  },
  async setStatus(id, status) {
    const r = await fetch(`/api/jobs/${id}/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    if (!r.ok) throw new Error(`status ${id}→${status}: ${r.status}`);
    return r.json();
  },
  async listJobs() {
    const r = await fetch("/api/jobs");
    if (!r.ok) throw new Error(`list: ${r.status}`);
    return r.json();
  },
  async getJob(id) {
    const r = await fetch(`/api/jobs/${id}`);
    if (!r.ok) throw new Error(`get ${id}: ${r.status}`);
    return r.json();
  },
  async markViewed(id) {
    const r = await fetch(`/api/jobs/${id}/view`, { method: "POST" });
    if (!r.ok) throw new Error(`view ${id}: ${r.status}`);
    return r.json();
  },
  async dismiss(id) {
    const r = await fetch(`/api/jobs/${id}/dismiss`, { method: "POST" });
    if (!r.ok) throw new Error(`dismiss ${id}: ${r.status}`);
    return r.json();
  },
  async generatePdf(id) {
    const r = await fetch(`/api/jobs/${id}/generate-pdf`, { method: "POST" });
    if (r.status === 409) {
      const body = await r.json();
      throw new Error(body.detail?.message || "Needs LLM scoring first");
    }
    if (!r.ok) throw new Error(`generate ${id}: ${r.status}`);
    return r.json();
  },
  async pdfStatus(id) {
    const r = await fetch(`/api/jobs/${id}/pdf-status`);
    if (!r.ok) throw new Error(`status ${id}: ${r.status}`);
    return r.json();
  },
};

// ─── Components ────────────────────────────────────────────────────────────

function ScoreBadge({ label, value, accent }) {
  if (value == null) return null;
  const pct = Math.round(value * 100);
  const color = accent === "llm"
    ? (pct >= 70 ? "bg-emerald-100 text-emerald-800"
      : pct >= 50 ? "bg-amber-100 text-amber-800"
                  : "bg-rose-100 text-rose-800")
    : "bg-slate-200 text-slate-700";
  return html`
    <span className=${`text-xs px-2 py-0.5 rounded ${color}`}>
      ${label} ${pct}
    </span>`;
}

function JobCard({ job, onView, onDismiss, onGenerate, pdfState, expanded, onToggleExpand, fullDetail }) {
  const hasMatch = job.has_match_result;
  const pdfReady = (job.status === "staged" || job.status === "submitted") && job.tailored_pdf_path;
  const generating = pdfState === "running";
  const errorState = (pdfState || "").startsWith("error:");
  const errorMsg = errorState ? pdfState.slice(6) : null;

  const handleDragStart = (e) => {
    e.dataTransfer.setData("text/plain", job.id);
    e.dataTransfer.setData("application/x-job-status", job.status);
    e.dataTransfer.effectAllowed = "move";
  };

  return html`
    <div
      draggable=${true}
      onDragStart=${handleDragStart}
      className="card border-2 border-slate-200 rounded-lg p-3 bg-white shadow-sm cursor-grab active:cursor-grabbing">
      <div className="flex justify-between items-start gap-2">
        <div className="flex-1 min-w-0">
          <h3 className="font-bold text-sm leading-tight">${job.title}</h3>
          <p className="text-xs text-slate-600 mt-0.5">
            ${job.company}${job.location ? ` · ${job.location}` : ""}
          </p>
          <div className="flex gap-1 mt-2 flex-wrap">
            <${ScoreBadge} label="KW" value=${job.keyword_score} />
            <${ScoreBadge} label="LLM" value=${job.llm_final_score} accent="llm" />
            ${!hasMatch ? html`<span className="text-xs px-2 py-0.5 rounded bg-slate-100 text-slate-500">needs LLM</span>` : null}
          </div>
        </div>
      </div>

      ${expanded && fullDetail ? html`
        <div className="mt-3 pt-3 border-t border-slate-200">
          <p className="text-xs text-slate-700 whitespace-pre-wrap line-clamp-[12]">${fullDetail.description?.slice(0, 1200) || "(no description)"}${fullDetail.description?.length > 1200 ? "…" : ""}</p>
          ${fullDetail.match_result ? html`
            <div className="mt-2 text-xs text-slate-600 italic">
              ${fullDetail.match_result.reasoning}
            </div>` : null}
        </div>` : null}

      <div className="flex gap-2 mt-3 flex-wrap">
        <button
          onClick=${onToggleExpand}
          className="text-xs px-2 py-1 rounded bg-slate-100 hover:bg-slate-200">
          ${expanded ? "Collapse" : "View JD"}
        </button>
        ${job.link ? html`
          <a href=${job.link} target="_blank" rel="noopener noreferrer"
            className="text-xs px-2 py-1 rounded bg-slate-100 hover:bg-slate-200">
            LinkedIn ↗
          </a>` : null}
        ${pdfReady ? html`
          <a href=${`/pdfs/${job.id}.pdf`} target="_blank" rel="noopener noreferrer"
            className="text-xs px-2 py-1 rounded bg-emerald-600 text-white hover:bg-emerald-700">
            Open PDF ↗
          </a>` : html`
          <button
            onClick=${onGenerate}
            disabled=${!hasMatch || generating}
            title=${!hasMatch ? "LLM scoring required before tailoring" : "Generate tailored CV PDF"}
            className=${`text-xs px-2 py-1 rounded ${hasMatch ? "bg-blue-600 text-white hover:bg-blue-700" : "bg-slate-200 text-slate-400 cursor-not-allowed"} ${generating ? "opacity-60" : ""}`}>
            ${generating ? "Generating…" : "Generate PDF"}
          </button>`}
        ${job.status === "new" ? html`
          <button onClick=${onView}
            className="text-xs px-2 py-1 rounded text-slate-500 hover:text-slate-700">
            ✓ Mark viewed
          </button>` : null}
        <button onClick=${onDismiss}
          className="text-xs px-2 py-1 rounded text-slate-400 hover:text-rose-600 ml-auto">
          Dismiss
        </button>
      </div>

      ${errorMsg ? html`
        <div className="mt-2 text-xs text-rose-600 bg-rose-50 rounded p-2 border border-rose-200">
          ⚠ ${errorMsg}
        </div>` : null}
    </div>`;
}

function Column({ title, accent, status, jobs, expandedJobId, jobDetails, pdfStates, onView, onDismiss, onGenerate, onToggleExpand, onDropJob, emptyMessage }) {
  const [isOver, setIsOver] = useState(false);
  const dragDepth = useRef(0);  // counter for nested dragenter/leave

  const handleDragEnter = (e) => {
    e.preventDefault();
    dragDepth.current += 1;
    setIsOver(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    dragDepth.current -= 1;
    if (dragDepth.current <= 0) {
      dragDepth.current = 0;
      setIsOver(false);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
  };

  const handleDrop = (e) => {
    e.preventDefault();
    dragDepth.current = 0;
    setIsOver(false);
    const jobId = e.dataTransfer.getData("text/plain");
    const fromStatus = e.dataTransfer.getData("application/x-job-status");
    if (jobId && fromStatus !== status) {
      onDropJob(jobId, status);
    }
  };

  return html`
    <div
      onDragEnter=${handleDragEnter}
      onDragLeave=${handleDragLeave}
      onDragOver=${handleDragOver}
      onDrop=${handleDrop}
      className=${`flex-1 min-w-0 flex flex-col gap-2 rounded-lg p-2 transition-colors ${isOver ? "bg-blue-50 ring-2 ring-blue-400" : ""}`}>
      <div className=${`flex items-center justify-between border-l-4 ${accent} pl-2 mb-2`}>
        <h2 className="font-semibold text-lg">${title}</h2>
        <span className="text-xs text-slate-500">${jobs.length}</span>
      </div>
      ${jobs.length === 0 ? html`
        <div className=${`text-sm text-slate-400 italic p-4 border border-dashed rounded text-center ${isOver ? "border-blue-400 text-blue-600" : "border-slate-300"}`}>
          ${isOver ? "Drop here" : emptyMessage}
        </div>` : null}
      ${jobs.map(j => html`
        <${JobCard}
          key=${j.id}
          job=${j}
          expanded=${expandedJobId === j.id}
          fullDetail=${jobDetails[j.id]}
          pdfState=${pdfStates[j.id]}
          onView=${() => onView(j.id)}
          onDismiss=${() => onDismiss(j.id)}
          onGenerate=${() => onGenerate(j.id)}
          onToggleExpand=${() => onToggleExpand(j.id)}
        />`)}
    </div>`;
}

function LocationCombobox({ value, geoId, onChange }) {
  // Controlled component. onChange(displayName, geoId | null) — emits null geoId
  // when the user types freely without picking from the dropdown.
  const [hits, setHits] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const debounceRef = useRef(null);

  const fetchHits = useCallback(async (q) => {
    if (q.trim().length < 2) {
      setHits([]); return;
    }
    setLoading(true);
    try {
      const data = await api.typeaheadLocations(q);
      setHits(data);
    } catch {
      setHits([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const onInput = (e) => {
    const next = e.target.value;
    // User typed → invalidate previous geoId match
    onChange(next, null);
    setOpen(true);
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => fetchHits(next), 300);
  };

  const pickHit = (hit) => {
    onChange(hit.displayName, hit.id);
    setHits([]);
    setOpen(false);
  };

  return html`
    <div className="relative">
      <input
        type="text"
        value=${value}
        onChange=${onInput}
        onFocus=${() => { if (hits.length) setOpen(true); }}
        onBlur=${() => setTimeout(() => setOpen(false), 200)}
        placeholder="Start typing a city, e.g. Zurich"
        className="w-full px-3 py-2 border border-slate-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
      />
      ${geoId ? html`
        <span className="absolute right-2 top-2 text-xs text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded">
          ✓ confirmed (geoId ${geoId})
        </span>` : null}
      ${open && (hits.length > 0 || loading) ? html`
        <div className="absolute z-10 left-0 right-0 mt-1 bg-white border border-slate-200 rounded shadow-lg max-h-64 overflow-y-auto">
          ${loading ? html`<div className="px-3 py-2 text-xs text-slate-400">Loading…</div>` : null}
          ${hits.map(h => html`
            <button
              key=${h.id}
              type="button"
              onMouseDown=${(e) => { e.preventDefault(); pickHit(h); }}
              className="w-full text-left px-3 py-2 text-sm hover:bg-slate-100 border-b border-slate-100 last:border-b-0">
              <span className="font-medium">${h.displayName}</span>
              <span className="text-xs text-slate-400 ml-2">${h.id}</span>
            </button>`)}
        </div>` : null}
    </div>`;
}

function PreferencesPanel({ prefs, onSave }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({ keywords: "", location: "", location_geo_id: null });
  const [saving, setSaving] = useState(false);

  const startEdit = () => {
    setDraft({
      keywords: prefs.keywords || "",
      location: prefs.location || "",
      location_geo_id: prefs.location_geo_id || null,
    });
    setEditing(true);
  };

  const cancel = () => setEditing(false);

  const save = async () => {
    setSaving(true);
    try {
      await onSave({
        keywords: draft.keywords,
        location: draft.location,
        location_geo_id: draft.location_geo_id,  // null clears the row on the server
      });
      setEditing(false);
    } finally {
      setSaving(false);
    }
  };

  if (!prefs) return null;

  if (editing) {
    return html`
      <div className="mb-6 p-4 bg-white rounded-lg border border-slate-200 shadow-sm">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-semibold text-sm text-slate-700">Search preferences</h2>
          <span className="text-xs text-amber-700 bg-amber-50 px-2 py-0.5 rounded">
            Applies to the NEXT search Claude runs
          </span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-xs text-slate-500 font-medium">Keywords</span>
            <input
              type="text"
              value=${draft.keywords}
              onChange=${e => setDraft({ ...draft, keywords: e.target.value })}
              placeholder="e.g. ai OR software developer OR consultant"
              className="px-3 py-2 border border-slate-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <span className="text-xs text-slate-400">LinkedIn supports OR boolean syntax</span>
          </label>
          <div className="flex flex-col gap-1">
            <span className="text-xs text-slate-500 font-medium">Location</span>
            <${LocationCombobox}
              value=${draft.location}
              geoId=${draft.location_geo_id}
              onChange=${(loc, gid) => setDraft({ ...draft, location: loc, location_geo_id: gid })}
            />
            ${draft.location_geo_id
              ? html`<span className="text-xs text-emerald-700">Locked to LinkedIn geoId — the workflow will use this exact location.</span>`
              : html`<span className="text-xs text-amber-700">⚠ No LinkedIn confirmation. The workflow will resolve at run time and may pick the wrong place (e.g. Zurich, Canada).</span>`}
          </div>
        </div>
        <div className="flex gap-2 mt-3">
          <button
            onClick=${save}
            disabled=${saving}
            className="px-3 py-1.5 rounded bg-blue-600 text-white hover:bg-blue-700 text-sm disabled:opacity-60">
            ${saving ? "Saving…" : "Save"}
          </button>
          <button
            onClick=${cancel}
            disabled=${saving}
            className="px-3 py-1.5 rounded bg-slate-100 text-slate-700 hover:bg-slate-200 text-sm">
            Cancel
          </button>
        </div>
      </div>`;
  }

  return html`
    <div className="mb-6 p-3 bg-white rounded-lg border border-slate-200 shadow-sm flex flex-wrap items-center gap-3">
      <div className="flex-1 min-w-0 grid grid-cols-1 md:grid-cols-2 gap-2 md:gap-4">
        <div className="text-sm">
          <span className="text-xs text-slate-500 font-medium uppercase tracking-wide">Keywords</span>
          <div className="font-mono text-slate-800 truncate">${prefs.keywords}</div>
        </div>
        <div className="text-sm">
          <span className="text-xs text-slate-500 font-medium uppercase tracking-wide">Location</span>
          <div className="font-mono text-slate-800 truncate">
            ${prefs.location}
            ${prefs.location_geo_id
              ? html`<span className="ml-2 text-xs text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded">✓ ${prefs.location_geo_id}</span>`
              : html`<span className="ml-2 text-xs text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded">unconfirmed</span>`}
          </div>
        </div>
      </div>
      <button
        onClick=${startEdit}
        className="px-3 py-1.5 rounded bg-slate-100 text-slate-700 hover:bg-slate-200 text-sm shrink-0">
        Edit
      </button>
    </div>`;
}

function Toast({ message, type }) {
  if (!message) return null;
  const cls = type === "error"
    ? "bg-rose-600 text-white"
    : "bg-emerald-600 text-white";
  return html`
    <div className=${`toast ${cls} px-4 py-2 rounded shadow-lg text-sm`}>
      ${message}
    </div>`;
}

// ─── App ───────────────────────────────────────────────────────────────────

function App() {
  const [jobs, setJobs] = useState({ new: [], viewed: [], staged: [], submitted: [] });
  const [prefs, setPrefs] = useState(null);
  const [pdfStates, setPdfStates] = useState({});  // {job_id: 'running' | 'done' | 'error:…'}
  const [expandedJobId, setExpandedJobId] = useState(null);
  const [jobDetails, setJobDetails] = useState({});  // {job_id: full row}
  const [toast, setToast] = useState({ msg: null, type: "info" });
  const [lastRefresh, setLastRefresh] = useState(Date.now());
  const pollingRef = useRef(new Set());  // job_ids currently being polled

  const refresh = useCallback(async () => {
    try {
      const data = await api.listJobs();
      setJobs(data);
      setLastRefresh(Date.now());
    } catch (e) {
      setToast({ msg: `Failed to load jobs: ${e.message}`, type: "error" });
    }
  }, []);

  const loadPrefs = useCallback(async () => {
    try {
      const p = await api.getPreferences();
      setPrefs(p);
    } catch (e) {
      setToast({ msg: `Failed to load preferences: ${e.message}`, type: "error" });
    }
  }, []);

  const handleSavePrefs = useCallback(async (draft) => {
    try {
      const updated = await api.updatePreferences(draft);
      setPrefs(updated);
      setToast({ msg: "Preferences saved — next search will use these.", type: "info" });
    } catch (e) {
      setToast({ msg: `Save failed: ${e.message}`, type: "error" });
      throw e;
    }
  }, []);

  useEffect(() => { refresh(); loadPrefs(); }, [refresh, loadPrefs]);

  // Auto-refresh every 5 s
  useEffect(() => {
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
  }, [refresh]);

  // Auto-dismiss toast
  useEffect(() => {
    if (!toast.msg) return;
    const id = setTimeout(() => setToast({ msg: null, type: "info" }), 4000);
    return () => clearTimeout(id);
  }, [toast.msg]);

  // Poll PDF status for any jobs in 'running' state
  const pollPdfStatus = useCallback((jobId) => {
    if (pollingRef.current.has(jobId)) return;
    pollingRef.current.add(jobId);
    const tick = async () => {
      try {
        const { state } = await api.pdfStatus(jobId);
        setPdfStates(s => ({ ...s, [jobId]: state }));
        if (state === "running") {
          setTimeout(tick, 1000);
        } else {
          pollingRef.current.delete(jobId);
          if (state === "done") {
            setToast({ msg: `PDF ready for job ${jobId}`, type: "info" });
            refresh();
          } else if (state.startsWith("error:")) {
            setToast({ msg: state.slice(6), type: "error" });
          }
        }
      } catch (e) {
        pollingRef.current.delete(jobId);
      }
    };
    tick();
  }, [refresh]);

  const handleView = async (id) => {
    try {
      await api.markViewed(id);
      await refresh();
    } catch (e) {
      setToast({ msg: e.message, type: "error" });
    }
  };

  const handleToggleExpand = async (id) => {
    if (expandedJobId === id) {
      setExpandedJobId(null);
      return;
    }
    setExpandedJobId(id);
    // First time expanding → fire view + fetch full detail
    if (!jobDetails[id]) {
      try {
        const detail = await api.getJob(id);
        setJobDetails(d => ({ ...d, [id]: detail }));
        if (detail.status === "new") {
          await api.markViewed(id);
          await refresh();
        }
      } catch (e) {
        setToast({ msg: e.message, type: "error" });
      }
    } else if (jobs.new.some(j => j.id === id)) {
      // Already cached detail, but card is still 'new' → mark viewed
      await api.markViewed(id);
      await refresh();
    }
  };

  const handleDismiss = async (id) => {
    try {
      await api.dismiss(id);
      await refresh();
    } catch (e) {
      setToast({ msg: e.message, type: "error" });
    }
  };

  const handleGenerate = async (id) => {
    try {
      await api.generatePdf(id);
      setPdfStates(s => ({ ...s, [id]: "running" }));
      pollPdfStatus(id);
    } catch (e) {
      setToast({ msg: e.message, type: "error" });
    }
  };

  const handleDropJob = async (id, targetStatus) => {
    try {
      await api.setStatus(id, targetStatus);
      await refresh();
    } catch (e) {
      setToast({ msg: `Move failed: ${e.message}`, type: "error" });
    }
  };

  const total = jobs.new.length + jobs.viewed.length + jobs.staged.length + jobs.submitted.length;

  return html`
    <div className="max-w-screen-2xl mx-auto p-4 md:p-6">
      <header className="flex items-baseline justify-between mb-4 pb-3 border-b border-slate-200">
        <div>
          <h1 className="text-2xl font-bold">WAT Job Search</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            ${total} jobs · ${jobs.new.length} NEW · ${jobs.viewed.length} VIEWED · ${jobs.staged.length} STAGED · ${jobs.submitted.length} SUBMITTED
          </p>
          <p className="text-xs text-slate-400 mt-1">Tip: drag a card between columns to change its status.</p>
        </div>
        <div className="text-xs text-slate-400">
          Refreshed ${new Date(lastRefresh).toLocaleTimeString()}
          <button onClick=${refresh} className="ml-2 underline hover:text-slate-600">refresh</button>
        </div>
      </header>

      <${PreferencesPanel} prefs=${prefs} onSave=${handleSavePrefs} />

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        <${Column}
          title="NEW" accent="border-blue-500" status="new"
          jobs=${jobs.new}
          expandedJobId=${expandedJobId}
          jobDetails=${jobDetails}
          pdfStates=${pdfStates}
          onView=${handleView}
          onDismiss=${handleDismiss}
          onGenerate=${handleGenerate}
          onToggleExpand=${handleToggleExpand}
          onDropJob=${handleDropJob}
          emptyMessage="No new jobs. Run a search from Claude Desktop."
        />
        <${Column}
          title="VIEWED" accent="border-slate-400" status="viewed"
          jobs=${jobs.viewed}
          expandedJobId=${expandedJobId}
          jobDetails=${jobDetails}
          pdfStates=${pdfStates}
          onView=${handleView}
          onDismiss=${handleDismiss}
          onGenerate=${handleGenerate}
          onToggleExpand=${handleToggleExpand}
          onDropJob=${handleDropJob}
          emptyMessage="No viewed jobs yet."
        />
        <${Column}
          title="STAGED" accent="border-emerald-500" status="staged"
          jobs=${jobs.staged}
          expandedJobId=${expandedJobId}
          jobDetails=${jobDetails}
          pdfStates=${pdfStates}
          onView=${handleView}
          onDismiss=${handleDismiss}
          onGenerate=${handleGenerate}
          onToggleExpand=${handleToggleExpand}
          onDropJob=${handleDropJob}
          emptyMessage="No applications staged yet. Click Generate PDF on a job with an LLM score."
        />
        <${Column}
          title="SUBMITTED" accent="border-violet-500" status="submitted"
          jobs=${jobs.submitted}
          expandedJobId=${expandedJobId}
          jobDetails=${jobDetails}
          pdfStates=${pdfStates}
          onView=${handleView}
          onDismiss=${handleDismiss}
          onGenerate=${handleGenerate}
          onToggleExpand=${handleToggleExpand}
          onDropJob=${handleDropJob}
          emptyMessage="No submitted applications yet. Drag a card from STAGED here once you've actually submitted."
        />
      </div>

      <${Toast} message=${toast.msg} type=${toast.type} />
    </div>`;
}

createRoot(document.getElementById("app")).render(html`<${App} />`);
