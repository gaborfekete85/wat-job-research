// Single-file React dashboard. Uses htm tagged templates so we don't need JSX.
import React, { useEffect, useState, useCallback, useRef } from "react";
import { createRoot } from "react-dom/client";
import htm from "htm";

const html = htm.bind(React.createElement);

// ─── API ───────────────────────────────────────────────────────────────────

const api = {
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
  const pdfReady = job.tailored_pdf_path && job.status === "staged";
  const generating = pdfState === "running";
  const errorState = (pdfState || "").startsWith("error:");
  const errorMsg = errorState ? pdfState.slice(6) : null;

  return html`
    <div className="card border-2 border-slate-200 rounded-lg p-3 bg-white shadow-sm">
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

function Column({ title, accent, jobs, expandedJobId, jobDetails, pdfStates, onView, onDismiss, onGenerate, onToggleExpand, emptyMessage }) {
  return html`
    <div className="flex-1 min-w-0 flex flex-col gap-2">
      <div className=${`flex items-center justify-between border-l-4 ${accent} pl-2 mb-2`}>
        <h2 className="font-semibold text-lg">${title}</h2>
        <span className="text-xs text-slate-500">${jobs.length}</span>
      </div>
      ${jobs.length === 0 ? html`
        <div className="text-sm text-slate-400 italic p-4 border border-dashed border-slate-300 rounded text-center">
          ${emptyMessage}
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

  useEffect(() => { refresh(); }, [refresh]);

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

  const total = jobs.new.length + jobs.viewed.length + jobs.staged.length;

  return html`
    <div className="max-w-screen-2xl mx-auto p-4 md:p-6">
      <header className="flex items-baseline justify-between mb-6 pb-3 border-b border-slate-200">
        <div>
          <h1 className="text-2xl font-bold">WAT Job Search</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            ${total} jobs · ${jobs.new.length} NEW · ${jobs.viewed.length} VIEWED · ${jobs.staged.length} STAGED${jobs.submitted.length ? ` · ${jobs.submitted.length} SUBMITTED` : ""}
          </p>
        </div>
        <div className="text-xs text-slate-400">
          Refreshed ${new Date(lastRefresh).toLocaleTimeString()}
          <button onClick=${refresh} className="ml-2 underline hover:text-slate-600">refresh</button>
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <${Column}
          title="NEW" accent="border-blue-500"
          jobs=${jobs.new}
          expandedJobId=${expandedJobId}
          jobDetails=${jobDetails}
          pdfStates=${pdfStates}
          onView=${handleView}
          onDismiss=${handleDismiss}
          onGenerate=${handleGenerate}
          onToggleExpand=${handleToggleExpand}
          emptyMessage="No new jobs. Run a search from Claude Desktop."
        />
        <${Column}
          title="VIEWED" accent="border-slate-400"
          jobs=${jobs.viewed}
          expandedJobId=${expandedJobId}
          jobDetails=${jobDetails}
          pdfStates=${pdfStates}
          onView=${handleView}
          onDismiss=${handleDismiss}
          onGenerate=${handleGenerate}
          onToggleExpand=${handleToggleExpand}
          emptyMessage="No viewed jobs yet."
        />
        <${Column}
          title="STAGED" accent="border-emerald-500"
          jobs=${jobs.staged}
          expandedJobId=${expandedJobId}
          jobDetails=${jobDetails}
          pdfStates=${pdfStates}
          onView=${handleView}
          onDismiss=${handleDismiss}
          onGenerate=${handleGenerate}
          onToggleExpand=${handleToggleExpand}
          emptyMessage="No applications staged yet. Click Generate PDF on a job with an LLM score."
        />
      </div>

      <${Toast} message=${toast.msg} type=${toast.type} />
    </div>`;
}

createRoot(document.getElementById("app")).render(html`<${App} />`);
