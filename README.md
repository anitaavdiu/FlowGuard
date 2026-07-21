# FlowGuard

A VS Code extension that watches how you code, scores your cognitive load in real time, and calls an AI to diagnose what's causing a spike and suggest a fix — directly in the editor.

> **Status:** local prototype — backend runs on `localhost:8000`, extension connects to it automatically.

---

## What it does

Every 60 seconds FlowGuard samples three behavioral signals from your editor session:

- **Deletion rate** — high backspace frequency is the strongest predictor of confusion
- **Context switching** — rapid file-hopping suggests you've lost your thread  
- **Workspace errors** — ambient error count as a proxy for broken state

It also runs a lightweight semantic pass: detecting *edit thrash* (the same 5-line region rewritten multiple times inside a 30-second window) and *syntax imbalance* (unmatched braces or parens near the cursor, with string contents skipped to avoid JSX false positives).

All of this feeds a weighted EWMA score (0–100). When you cross **70 — OVERLOADED** — FlowGuard sends your telemetry, the surrounding code snippet, and any semantic signals to Claude, which returns:

- What triggered the overload
- The root cause
- A suggested fix in plain English
- Actual code to insert, surfaced as a **Quick Fix (Ctrl+.)**

The status bar updates every cycle. The rolling score persists in SQLite so a server restart doesn't reset your history.

---

## Architecture

```
VS Code extension (TypeScript)
    │
    │  POST every 60s:
    │    backspace count, file switches, error count
    │    active file + cursor snippet (±15 lines)
    │    semantic trigger (thrash / syntax imbalance)
    ▼
FastAPI backend (Python)
    │
    ├─ scorer.py      weighted instant score → EWMA smoothing
    ├─ db.py          persist every event to flowguard.db (SQLite)
    └─ claude_client  if OVERLOADED: call claude-opus-4-8
                          → structured JSON diagnosis
    │
    ▼  { score, state, diagnosis }
    │
VS Code extension
    ├─ status bar:   $(zap) Flow / $(circle-outline) Normal / $(flame) Overloaded
    ├─ notification: trigger + suggested fix + confidence %
    └─ CodeAction:   Ctrl+. → WorkspaceEdit inserts patch_code at cursor
```

---

## Getting started

### Prerequisites

- Node.js 18+, VS Code 1.85+
- Python 3.9+
- An [Anthropic API key](https://console.anthropic.com/)

### 1. Start the backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # then add your key
uvicorn main:app --reload
```

Create `.env` if you don't have one:

```
ANTHROPIC_API_KEY=sk-ant-...
```

### 2. Run the extension

```bash
npm install
npm run compile
```

Press **F5** in VS Code to open an Extension Development Host. The FlowGuard status bar item appears bottom-right after the first 60-second tick.

---

## How the score works

Each 60-second window is mapped to an instant score, then smoothed into a rolling score with EWMA (α = 0.4) so brief spikes don't immediately trigger a diagnosis.

| Signal | Weight | Spike ceiling (per minute) |
|---|---|---|
| Deletions | 55% | 40 |
| File switches | 30% | 8 |
| Workspace errors | 15% | 5 |

| Score | State | Status bar |
|---|---|---|
| 0 – 29 | FLOW | `$(zap) Flow` |
| 30 – 69 | NORMAL | `$(circle-outline) Normal` |
| 70 – 100 | OVERLOADED | `$(flame) Overloaded` (red) |

The rolling score is written to `backend/flowguard.db` after every request, so the backend can resume from where it left off after a restart.

---

## Running tests

```bash
cd backend
pytest tests/ -v
```

---

## Project structure

```
FlowGuard/
├── src/
│   ├── extension.ts              entry point, event loop
│   ├── analysis/
│   │   └── semanticAnalyzer.ts   thrash detection + syntax imbalance
│   ├── telemetry/
│   │   └── client.ts             payload builder, HTTP client, interfaces
│   └── utils/
│       └── patchProvider.ts      CodeActionProvider, applyPatch command
│
└── backend/
    ├── main.py                   FastAPI app, /telemetry route
    ├── models.py                 shared Pydantic models
    ├── scorer.py                 scoring math (pure functions)
    ├── db.py                     SQLite persistence
    └── claude_client.py          Anthropic API calls
```
