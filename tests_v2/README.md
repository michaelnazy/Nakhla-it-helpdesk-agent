# Unified v2 unit/contract test suite

These tests consolidate the previously scattered Phase 1–3c tests into one directory. They depend on the actual repo modules, not patch installer directories. They do not call the live Helpdesk API, do not create tickets, and do not need OpenRouter credentials. Some LangGraph tests require that the pinned dependencies are installed; they may be skipped in environments without LangGraph.

```powershell
python -m unittest discover -s .\tests_v2 -v
```

For real API/MCP/approval integration use `evals/run_evals.py` with the simulated API and separate case suites. Results from the original patch directories have not been blindly counted as independent evaluations.
