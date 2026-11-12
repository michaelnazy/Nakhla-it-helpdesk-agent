*Simulated systems for the IT Helpdesk Agent brief of the Agentic AI Bootcamp, organized by Jerusalem High-Tech Foundry (JHF) · in partnership with COMCEC.*

# IT Helpdesk kit

Everything your agent needs around it, so your week goes into the agent:

- the **dataset** of Nakhla Systems, a fictional software company: 20 knowledge-base documents
  (2 of them PDF-only), 40 historical tickets, 25 employees, a status page;
- the company's **helpdesk API** (simulated system of record, FastAPI, port **8102**);
- an **MCP server** in front of it (stdio, 6 tools);
- a **UI starter**, the **eval runner** and 10 **sample cases**.

You build the agent: retrieval over the knowledge base, the conversation, the approval gate,
your API contract on port 8000. Do not change the simulated systems: the hidden tests run
against the original.

## Quickstart (Windows PowerShell)

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env                                  # then fill in OPENROUTER_API_KEY

uvicorn services.helpdesk_api:app --port 8102           # terminal 1: the helpdesk API
python check_kit.py                                     # terminal 2: must end with "Kit ready."
python dataset/validate_dataset.py                      # optional: dataset consistency
```

macOS/Linux: `python3.12 -m venv .venv`, `source .venv/bin/activate`, `cp .env.example .env`.
Docker instead of uvicorn: `docker compose up --build` (simulated API on 8102 and agent on 8000).

One venv is enough for the kit **and** your agent: `requirements.txt` also pins the course's agent
framework (`langgraph==1.2.10`, `openai==2.52.0`) and `mcp==1.28.1`, the MCP version CrewAI 1.15 needs.
Already have the course's Module 2 venv? `pip install -r requirements.txt` into it works too.

## Layout

| Path | What |
|---|---|
| `dataset/` | knowledge base, tickets, schemas, manifest, precedence rules: start with `dataset/README.md` |
| `services/helpdesk_api.py` | the simulated helpdesk API (system of record) |
| `services/helpdesk_mcp.py` | the MCP server your agent uses (`python -m services.helpdesk_mcp`) |
| `services/data/` | seed data: `employees.json` (directory), `status.json` (status page) |
| `services/Dockerfile`, `docker-compose.yml` | container for the API; add your app to the compose file |
| `ui/app_ui.py` | Gradio starter: chat, sources panel, ticket-draft card with Approve / Reject. Talks only to your API. |
| `evals/` | `cases.sample.jsonl` (10 cases) and `run_evals.py` (the shared runner) |
| `check_kit.py` | smoke test: API health, a keyed REST call, MCP `list_tools` + one read call |

## The helpdesk API (port 8102)

Business endpoints need the header `X-API-Key` (value of `HELPDESK_API_KEY`). Errors are JSON:
`{"error": {"code": "...", "message": "...", "fields": [...]}}` with real HTTP codes.
Interactive docs: http://localhost:8102/docs

| Method | Path | What it does | Errors |
|---|---|---|---|
| GET | `/health` | `{"status": "ok", "service": "helpdesk"}` (no key) | |
| GET | `/api/directory/{email}` | employee: department, office, VIP, contractor, MFA, VPN client and gateway, account status | 401, 404 `employee_not_found` |
| GET | `/api/status` | status page: services and incidents (`active_incidents` lists the ids) | 401 |
| GET | `/api/tickets?requester_email=&q=&status=&limit=` | search the archive and new tickets; `q` = keywords in subject and description; `status` = open, resolved, closed; `limit` 1-50 (default 10) | 401, 422 |
| GET | `/api/tickets/{ticket_id}` | one ticket with notes | 401, 404 `ticket_not_found` |
| POST | `/api/tickets` | create a ticket; body = `dataset/schemas/ticket.schema.json`; header `Idempotency-Key`; returns 201 and the ticket with `ticket_id` IT-2001, IT-2002, ... | 401, 400, 409 `idempotency_conflict`, 422 `validation_error` with `fields` |
| POST | `/api/tickets/{ticket_id}/notes` | add a note `{"note": "..."}`; header `Idempotency-Key` | 401, 404, 409, 422 |

Ticket body rules: `category` from the 8 categories, `priority` P1-P4, `requester_email` must be in
the directory, `department` must match the directory, `attempted_steps` needs at least one step,
every `kb_refs` id must exist (`[]` is allowed when the KB has no answer), optional `affected_users`.
The API sets `assigned_team` from the category and adds `warnings` if you cite a deprecated or draft document.
Same `Idempotency-Key` + same body = the same ticket, never a duplicate.

### Test-only admin endpoints (no key)

They exist for the eval runner and the hidden tests. **Your app must not call them.**

| Method | Path | What it does |
|---|---|---|
| POST | `/admin/reset` | restore the seed data, clear faults, logs and created tickets |
| POST | `/admin/faults` | `{"target": "create_ticket", "mode": "error_503", "count": 1}`: the next `count` calls of that operation fail |
| GET / DELETE | `/admin/faults` | show / clear armed faults |
| GET | `/admin/log` | recent requests: method, path, status, ms, operation |
| GET | `/admin/tickets` | tickets created since the last reset (`?all=1`: archive too) |
| GET | `/admin/notes` | notes added since the last reset |

Fault targets: `create_ticket`, `directory`, `status`, `search_tickets`, `get_ticket`, `add_note`.
Modes: `error_500`, `error_503`, `timeout` (waits 15 s, then 504), `slow` (waits 3 s, then succeeds).

```powershell
curl.exe -X POST http://localhost:8102/admin/faults -H "Content-Type: application/json" `
  -d '{\"target\": \"create_ticket\", \"mode\": \"error_503\", \"count\": 1}'
curl.exe -X POST http://localhost:8102/admin/reset
```

## The MCP server (stdio)

Your app starts it as a subprocess and talks MCP over stdin/stdout. It calls the REST API, so
its state is the state the tests see. Tool errors come back as `{"ok": false, "error": {...}}`.

| Tool | Use it to |
|---|---|
| `lookup_employee(email)` | get department, VIP, contractor, MFA, VPN client version and gateway **before** applying department rules or choosing a priority |
| `get_service_status()` | check for an active incident **before** troubleshooting or drafting a ticket |
| `search_tickets(query=None, requester_email=None, status=None, limit=5)` | the requester's ticket history (your long-term memory) and similar past cases |
| `create_ticket(subject, description, category, priority, requester_email, department, attempted_steps, kb_refs, idempotency_key, affected_users=1)` | **write**: only from your approval step, after the employee approved this exact draft |
| `get_ticket(ticket_id)` | one ticket with its notes |
| `add_ticket_note(ticket_id, note)` | **write**: add information to the employee's own ticket |

```python
import os, sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

params = StdioServerParameters(command=sys.executable, args=["-m", "services.helpdesk_mcp"],
                               env=dict(os.environ))   # pass env on, or the server will not see your .env values
async with stdio_client(params) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()
        result = await session.call_tool("lookup_employee", {"email": "tariq.hamdan@nakhla.example"})
```

The knowledge base is **not** an MCP tool: ingestion, chunking, embeddings and retrieval over
`dataset/knowledge_base/` (Markdown and PDF) are yours to build, for example OpenRouter
`openai/text-embedding-3-small` with a numpy cosine store, or Chroma.

## The approval gate

Keep `create_ticket` (and `add_ticket_note`) **out of the model's tool list**. The model drafts a
ticket; your API returns it as `pending_action` (`type: "create_ticket"`); only `POST /api/approve`
calls `create_ticket` over MCP with exactly that payload and `idempotency_key = action_id`.
Show only the `ticket_id` the API returned. A rejected draft writes nothing.

## Environment variables

| Variable | Default | Used by |
|---|---|---|
| `HELPDESK_API_KEY` | `dev-key-change-me` | API, MCP server, check_kit (must be the same everywhere) |
| `HELPDESK_API_URL` | `http://localhost:8102` | MCP server, check_kit, your app |
| `HELPDESK_TODAY` | real today | API: date of new tickets and of the status page (`YYYY-MM-DD`) |
| `HELPDESK_TIMEOUT_S` | `20` | MCP server: seconds before a call to the API gives up |
| `HELPDESK_MCP_LOG_LEVEL` | `WARNING` | MCP server log level on stderr |
| `HELPDESK_DATA_DIR`, `HELPDESK_DATASET_DIR` | `services/data`, `dataset` | API seed files |
| `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL`, `MODEL`, `EMBEDDING_MODEL` | see `.env.example` | your agent |
| `APP_URL` | `http://localhost:8000` | UI starter, eval runner |

The API and the MCP server also read the kit's `.env` (without overriding variables you already set).

## UI starter and evals

```powershell
python ui/app_ui.py                          # http://localhost:7860, talks to APP_URL
python evals/run_evals.py                    # the 10 sample cases against your app on :8000
python evals/run_evals.py --only S2-05 -v    # one case, every turn
```

The case format and the API contract are described in the mini-project's `common/CONTRACT.md`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `check_kit.py`: API not answering | start `uvicorn services.helpdesk_api:app --port 8102` from this folder |
| 401 `unauthorized` | the same `HELPDESK_API_KEY` for the API, the MCP server and your app |
| MCP tool returns `unreachable` | the API is not running, or `HELPDESK_API_URL` is wrong (in Docker use the service name) |
| Everything fails with 503 | a fault is still armed: `curl.exe -X DELETE http://localhost:8102/admin/faults` |
| Ticket ids keep growing | `POST /admin/reset` restores the seed state (tests do this before every case) |


## Running the Nakhla IT Helpdesk Agent

### Requirements
- Python 3.12
- Install dependencies with `pip install -r requirements.txt`
- Configure `.env` using `.env.example`

### Start the simulated Helpdesk API

```powershell
python -m uvicorn services.helpdesk_api:app --host 127.0.0.1 --port 8102
```

### Start the agent

Open a second PowerShell terminal:

```powershell
$env:EVAL_ENABLE_WRITES = "1"
python -m uvicorn agent_backend:app --host 127.0.0.1 --port 8000
```

The write flag is for isolated local course evaluation only. The approval endpoint requires a matching pending ticket draft before calling MCP create_ticket. This application is not production-authenticated and must not be publicly exposed.

### Start the Gradio UI

```powershell
python ui/app_ui.py
```

### Run the sample evaluations

```powershell
python evals/run_evals.py --app http://127.0.0.1:8000
```

### Sample evaluation result

The current local evidence is recorded in [evals/scorecard.final-kit.md](evals/scorecard.final-kit.md),
[evals/scorecard.final-challenge.md](evals/scorecard.final-challenge.md), and
[evals/scorecard.phase3c-own.md](evals/scorecard.phase3c-own.md):
10/10 kit cases, 14/14 challenge cases, and 14/14 independently authored cases.

The simulated helpdesk files under `services/` remain unchanged.

<!-- NAKHLA_V2_AGENT_README_START -->

---

# Nakhla IT Helpdesk Agent — v2 implementation

> **Project implementation (separate from the supplied JHF course kit above).**
> The project is a **local-only educational agent**, not a production helpdesk or an authenticated enterprise service.
> `v1` remains the original submitted baseline; the improvements are on `v2-improvements`.

The agent uses **FastAPI + LangGraph + OpenRouter + RAG + MCP** to answer IT questions from approved Nakhla knowledge-base documents, read verified ticket history, enforce company-specific rules, and prepare ticket drafts. **Creating a ticket requires a separate human approval request**; an LLM cannot directly call a write tool.

## What this implementation does

- Routes eligible messages through a **validated LLM triage** and **conditional LangGraph nodes** when `V2_LIVE_GRAPH=1`.
- Retrieves answer evidence from the approved KB; supports exact errors, free-text semantic search, source-validated fallback, and safe abstention when evidence is insufficient.
- Enforces high-priority policies **before model-selected execution** (e.g. contractor VPN restrictions, restricted MFA methods, VIP and multiple-user priorities, security escalations).
- Uses MCP read tools for employee directory, current incidents, and user-owned tickets; leaves verified VPN/error-code paths on a tested legacy fallback when required.
- Returns `pending_action` for a requested ticket; `POST /api/approve` is the only route that can call MCP `create_ticket`, using the draft's `action_id` as idempotency key. Repeated approval of the same action returns its cached result without a second write.

**Limitations:** Some incident and policy decisions still use deterministic Python rules and legacy routing; this is an incremental graph migration, not fully model-driven orchestration. Session state and approval replay are in memory. The local evaluator trusts a caller-supplied employee email after directory lookup; that is **not authentication**. Do not expose port 8000 or Gradio publicly.

## Local quickstart — Windows PowerShell

Requires Python 3.12, the provided `dataset/` and `services/` folders, plus access to OpenRouter. Run each server in a separate terminal **from the repository root**.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env  # only on first setup; then set your local OPENROUTER_API_KEY
```

Keep `.env` private and out of Git. The `HELPDESK_API_KEY` and `HELPDESK_API_URL` must match between the simulated API and MCP. The submitted `rag_store/chunks.json` is source metadata; **if `rag_store/vectors.npz` is missing**, regenerate embeddings with:

```powershell
python build_vector_store.py
```

This may contact the configured embedding provider and use paid tokens. Start services:

**Terminal 1 — simulated helpdesk:**

```powershell
.\.venv\Scripts\Activate.ps1
python -m uvicorn services.helpdesk_api:app --host 127.0.0.1 --port 8102
```

**Terminal 2 — agent API (safe default, no ticket writes):**

```powershell
.\.venv\Scripts\Activate.ps1
$env:V2_LIVE_GRAPH = "1"
$env:EVAL_ENABLE_WRITES = "0"
python -m uvicorn agent_backend:app --host 127.0.0.1 --port 8000
```

**Terminal 3 — smoke check / optional UI:**

```powershell
.\.venv\Scripts\Activate.ps1
python check_kit.py
# or run UI separately: python ui/app_ui.py
```

Test the local `/api/chat` endpoint:

```powershell
$body = @{
  session_id = "demo-wifi-01"
  message = "How do I set up office Wi-Fi?"
  user = @{ email = "tariq.hamdan@nakhla.example" }
} | ConvertTo-Json -Depth 5
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/chat" -Method Post -ContentType "application/json" -Body $body
```

Expected on the tested v2 build: citation `KB-003` and `state = langgraph_rag_answer`. The exact answer wording can vary; never treat an answer lacking grounded citations as verified.

### Run the evaluations (isolated local fixture only)

The evaluator **resets simulated ticket state** and tests approval flows that must write test tickets. Stop the UI and restart **only the loopback backend** with:

```powershell
$env:V2_LIVE_GRAPH = "1"
$env:EVAL_ENABLE_WRITES = "1"  # TEST ONLY — NEVER WITH A PUBLIC SERVER
python -m uvicorn agent_backend:app --host 127.0.0.1 --port 8000
```

Then run in another terminal:

```powershell
python -m unittest discover -s .\tests_v2 -v
python .\evals\run_evals.py --app http://127.0.0.1:8000 --out .\evals\scorecard.final-kit.md
python .\evals\run_evals.py --cases .\nakhla_v2_challenge\cases.v2-challenge.jsonl --app http://127.0.0.1:8000 --out .\evals\scorecard.final-challenge.md
python .\evals\run_evals.py --cases .\evals\cases.v2-own.jsonl --app http://127.0.0.1:8000 --out .\evals\scorecard.final-own.md
```

After tests, stop the backend (`Ctrl+C`); **restart with `EVAL_ENABLE_WRITES=0`** for normal local use. Running a second server without restarting does not change an already-loaded write flag.

## Implementation files

| Path | Responsibility |
|---|---|
| `agent_backend.py` | `/api/chat`, `/api/approve`, session state, mandatory safety flow, MCP bridge and legacy fallback |
| `v2_triage_graph.py` | JSON/Pydantic-validated LLM triage and isolated conditional route selection |
| `v2_live_flow.py` | LangGraph mandatory preflight, conditional routing, safe handler dispatch and fallback |
| `v2_backend_bridge.py` | Graph handler integration for KB, policy, incidents, profile and user-owned ticket reads |
| `v2_action_routes.py` | Explicit ticket intent check, policy/incident evidence and ticket **draft** preparation |
| `v2_support.py` | Grounded KB selection, policy precedence, impact count, priority and topic-shift helpers |
| `ticket_memory_router.py` | Ownership-verified ticket history/read requests |
| `agent_graph.py`, `retrieval.py`, `ingestion.py` | Existing verified incident pipeline and semantic retrieval machinery |
| `tests_v2/` | Consolidated versioned unit/contract tests; no live backend required |
| `evals/cases.v2-own.jsonl`, `nakhla_v2_challenge/cases.v2-challenge.jsonl` | 14 original regression + 14 independent challenge API scenarios |
| `DESIGN.md` and `docs/EVALUATION.md` | Architecture, safety decisions, measured results and known limitations |

**Do not modify** the course-owned `services/`, `dataset/`, `evals/run_evals.py`, or `evals/cases.sample.jsonl` to improve a score.

## Observed results and honest scope

See [docs/EVALUATION.md](docs/EVALUATION.md) for per-run, per-suite evidence. The last reported local runs after the ticket-schema fix were **10/10 kit** and **14/14 challenge**, each with its own scorecard. The 14/14 own-case run was recorded slightly before that small schema fix. These results do **not** establish any instructor hidden-test score. The earlier instructor feedback of 35/87 applied to the prior submission and has **not** been officially regraded.

The measured final kit mean turn latency was **4.28 s**, p95 **7.23 s** (slower than the earlier pre-LangGraph 2.79 s mean). The extra model call and per-call MCP subprocess startup are performance risks for future work.

For design rationale, threat model, and the explicit fallback behavior, see [DESIGN.md](DESIGN.md).

<!-- NAKHLA_V2_AGENT_README_END -->
