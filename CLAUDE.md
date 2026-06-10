# CLAUDE.md — WAT Framework Configuration

This file is the master configuration that Claude Code reads at the start of every session. It defines how work is organized in this project using the **WAT framework**.

---

## The WAT Framework

WAT stands for **Workflows · Agent · Tools** — a simple model for separating the three layers that make agentic work reliable and repeatable.

### W — Workflows
**Step-by-step procedures that orchestrate the work.**

Workflows live in [`/workflows/`](./workflows/) as plain Markdown files. Each workflow describes a repeatable procedure: the goal, the inputs, the ordered steps, and the expected output. Workflows are *what* gets done and *in what order* — they are the playbooks the agent follows.

A good workflow file:
- States its purpose in one sentence at the top.
- Lists prerequisites (inputs, env vars, tools required).
- Numbers the steps so the agent can track progress.
- Names the tools it expects to call (from `/tools/`).
- Specifies where the output goes (usually `/temp/outputs/`).

### A — Agent
**Claude Code — the AI agent that reads, plans, and executes.**

The agent is the runtime. It reads `CLAUDE.md` at session start, picks the relevant workflow for the user's request, plans the steps, and calls the tools needed to complete each step. The agent owns judgment and adaptation: workflows describe the happy path; the agent handles the messy reality.

Responsibilities of the agent in this project:
- Load and follow the appropriate workflow from `/workflows/`.
- Invoke scripts and integrations from `/tools/`.
- Stage intermediate work in `/temp/` and never commit it.
- Read secrets from `.env` — never print them, never commit them.
- Ask the user before taking irreversible or high-blast-radius actions.

### T — Tools
**Scripts and integrations that the agent uses to get things done.**

Tools live in [`/tools/`](./tools/) — these are the executable units the agent calls from inside a workflow. A tool can be a shell script, a Python script, a Node CLI, or a thin wrapper around an external API. Tools should be small, single-purpose, and composable.

A good tool:
- Does one thing and exits with a clear status code.
- Reads configuration from env vars or arguments, never hardcoded secrets.
- Writes its output to stdout or to a path passed in as an argument.
- Has a one-line usage comment at the top of the file.

---

## Folder Structure

```
.
├── CLAUDE.md           # This file — the master configuration
├── workflows/          # Step-by-step procedures (one .md file per workflow)
├── tools/              # Scripts and integrations the agent calls
├── temp/               # Temporary working files (gitignored)
│   ├── outputs/        # Generated artifacts from workflow runs
│   └── resources/      # Downloaded or staged inputs the agent needs
└── .env                # API keys and secrets — NEVER commit this file
```

### `/workflows/`
One Markdown file per workflow. File name should be a kebab-case verb phrase (e.g. `summarize-pdf.md`, `ingest-csv.md`, `publish-report.md`).

### `/tools/`
Executable scripts and integration modules. Group by capability if the count grows (e.g. `tools/pdf/`, `tools/http/`). Each tool should be invocable from the command line.

### `/temp/`
Scratch space for the current run. Two subfolders:
- **`/temp/outputs/`** — anything the workflow produces. Final deliverables can be moved out; intermediates stay here.
- **`/temp/resources/`** — anything pulled in to support the run: downloaded files, cached API responses, staged inputs.

`/temp/` is treated as ephemeral. The agent may clear it between sessions.

### `.env`
Holds API keys, tokens, and other secrets. Format is standard `KEY=value` per line. **This file must never be committed.** A `.gitignore` should always include `.env`.

---

## Operating Principles

1. **Workflows are the source of truth for *how* work happens.** When a new repeatable task emerges, write a workflow file before doing the work ad hoc a second time.
2. **Tools are reusable across workflows.** If two workflows need the same capability, extract it into a single tool.
3. **Keep `/temp/` clean.** Treat it as a working desk, not a filing cabinet. Move durable outputs elsewhere; let the rest be discarded.
4. **Secrets stay in `.env`.** Never inline a key in a workflow, a tool, or a committed file.
5. **The agent asks before doing anything irreversible** — destructive file ops, external sends, force-pushes, etc.

---

## Quick Start for the Agent

At session start:
1. Read this file.
2. Read any relevant workflow in `/workflows/` matching the user's request.
3. Confirm the plan with the user if it touches tools that hit external systems or modify shared state.
4. Execute step-by-step, writing intermediates to `/temp/` and final outputs to the location the workflow specifies.
