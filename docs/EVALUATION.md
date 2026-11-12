# Nakhla IT Helpdesk Agent v2 — Evaluation Evidence

This report records **observed local runs supplied by the project developer** on 12 November 2026. It does not claim access to the course instructor's hidden tests. All run times are the evaluator's **per-turn** latency statistics, not the mean per test case.

## Latest reported scores

| Suite | Cases | Pass | Mean turn latency | p95 turn latency | Report |
|---|---:|---:|---:|---:|---|
| Original course sample | 10 | **10/10** | **4.28s** | **7.23s** | `evals/scorecard.final-kit.md` |
| Independent challenge suite | 14 | **14/14** | **3.83s** | **6.35s** | `evals/scorecard.final-challenge.md` |
| Own regression suite | 14 | **14/14** | **3.66s** | **7.07s** | `evals/scorecard.phase3c-own.md` |

**Run sequencing note:** The own regression suite was last recorded as 14/14 *before* the subsequent 120-character ticket subject schema fix; the course and challenge suites were rerun successfully *after* that fix. Re-run the own suite on the final commit to establish a single-build 38/38 claim.

## Before / after observations

| Milestone | Kit score | Kit mean | Challenge score | Challenge mean |
|---|---:|---:|---:|---:|
| After policy/RAG improvements, before live LangGraph | 10/10 | 2.79s | 14/14 | 2.21s |
| Phase 3b live routing | 10/10 | 4.03s | 14/14 | 3.49s |
| Phase 3c before schema fix | 10/10 | 4.31s | 13/14 | 3.54s |
| Final schema fix + live routing | **10/10** | **4.28s** | **14/14** | **3.83s** |

**Interpretation:** Functional coverage on the local known cases was preserved and the CH-10 regression fixed. There is an observable latency cost after live model triage: the final kit mean increased about **53%** relative to the earlier 2.79s. Results can vary with OpenRouter network conditions and server load; no controlled statistical performance experiment was performed.

## Selected defect → regression evidence

| Finding from testing | Change | Verification |
|---|---|---|
| Repeated `/api/approve` returned conflict or risked duplicate writes | Server-side cached outcome per action ID + session lock | Phase 1 replay tests, kit approval/rejection flows |
| Code-free KB queries returned generic or unsupported answers | Current-source retrieval and title/phrase evidence | Challenge grounding, KB-003 live Wi-Fi result |
| Contractor/VIP/MFA and user-impact rules incomplete | Preflight policy and source precedence | Policy tests, own & challenge scenarios |
| Ticket-create phrase misread as read history | Separate explicit creation intent guard | Phase 2c and Phase 3c tests |
| LLM may misclassify a sensitive policy query as `knowledge` | Mandatory preflight and safe fallback | Triage benchmark; live graph contract tests |
| `CH-10` failed to create a P1 5-user Wi-Fi ticket | Truncate drafted subject to schema maximum 120 chars | 3/3 schema tests; CH-10 verbose PASS with simulated `IT-2001` |

## Final reproduction commands

From the repo root, use Python 3.12, installed requirements, an authorized OpenRouter key, and the supplied simulated Helpdesk API on `127.0.0.1:8102`. Run the agent on `127.0.0.1:8000` with `V2_LIVE_GRAPH=1`. To evaluate ticket-writing cases, temporarily enable `EVAL_ENABLE_WRITES=1` **only in an isolated loopback-local test environment with Gradio stopped**.

```powershell
python -m unittest discover -s .\tests_v2 -v
python .\evals\run_evals.py --app http://127.0.0.1:8000 --out .\evals\scorecard.final-kit.md
python .\evals\run_evals.py --cases .\nakhla_v2_challenge\cases.v2-challenge.jsonl --app http://127.0.0.1:8000 --out .\evals\scorecard.final-challenge.md
python .\evals\run_evals.py --cases .\evals\cases.v2-own.jsonl --app http://127.0.0.1:8000 --out .\evals\scorecard.final-own.md
```

Do not run evaluation resets while someone is using the local UI. The course evaluator may reset the simulation; the local service is not connected to an enterprise ticket system. Stop and restart the backend with `EVAL_ENABLE_WRITES=0` after the tests.

## What the results do not establish

- The original instructor review gave the earlier submission a **provisional 35/87** and reported weak hidden-test results. Those cases have **not been rerun by the instructor** after these improvements; the current score is unknown.
- Passing all supplied / self-authored cases does **not** prove that the model generalizes to all paraphrases or adversarial instructions.
- The LLM shadow benchmark emitted 14 schema-valid JSON decisions, but those are not 14 correct intent classifications. Some sensitive questions were routed as `knowledge`, which motivated mandatory policy preflight.
- The 120-character ticket-subject fix was verified on the local helpdesk schema; production backend behavior, persistence and authentication remain untested.

## Next evaluation improvements

Add independently authored multi-turn cases with paraphrases, contradictory user instructions, source-precedence conflicts and incident applicability. Measure MCP tool call durations separately from LLM calls; run repeated trials before reporting robust p95. Store prompt/KB versions and a stable scorecard per commit, not only latest local output.
