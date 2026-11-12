# Nakhla v2 — independent challenge suite (14 cases)

Purpose: expose gaps in generalization beyond the 10 supplied kit samples and the first 14 custom cases. These are **new tests, not known passing cases**. Failure is useful evidence and should not be concealed. Not an estimate of the instructor's hidden score.

All expectations are sourced from the CURRENT KB in the user-supplied v1 kit (KB-003, KB-009, KB-010, KB-014, KB-015, SP-001) and are intended as a diagnostic rubric. They may reveal a test-design weakness: investigate the actual response and authoritative source before deciding to change the agent.

## Before running
- Make sure Terminal 1 (simulated Helpdesk API :8102) and Terminal 2 (AI backend :8000) are running on 127.0.0.1.
- For approval tests, backend must have EVAL_ENABLE_WRITES=1. This is for **isolated local evaluation only**; never share the UI or expose the backend in this mode.
- Stop the Gradio UI. The evaluation runner may reset simulated ticket data.
- Do not alter any kit-owned files or tests.

## Command (Terminal 3)

```powershell
python .\evals\run_evals.py --cases .\nakhla_v2_challenge\cases.v2-challenge.jsonl --app http://127.0.0.1:8000 --out .\evals\scorecard.v2-challenge.md
```

Afterward, preserve independent reports so they do not overwrite each other:

```powershell
python .\evals\run_evals.py --cases .\nakhla_v2_phase1\evals\cases.v2-own.jsonl --app http://127.0.0.1:8000 --out .\evals\scorecard.v2-own.md
python .\evals\run_evals.py --app http://127.0.0.1:8000 --out .\evals\scorecard.kit-v2.md
```

Record failing cases, call traces, cited documents, and suspected root causes for Phase 3. **Do not modify an agent just to satisfy wording of a test if its substantive answer and evidence are correct**; a classifier/retriever architecture should generalize across paraphrases.

Important: the code base is local-demo only with unverified email identity. Keep it off public links. Stop the write-enabled backend when finished, and restart with EVAL_ENABLE_WRITES=0 for local UI use.
