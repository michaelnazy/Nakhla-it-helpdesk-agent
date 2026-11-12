"""Nakhla v2 phase 3b — safe, conditional LangGraph execution.

All requests pass through the graph when V2_LIVE_GRAPH=1. Mandatory read
ownership and policy checks run BEFORE model routing. Model output is not an
authorization. Agent graph is read-only; ticket drafting still uses the existing
server-side approval mechanism and ALL writes stay in /api/approve.

This is an incremental migration; the legacy backend remains the fallback for
unhandled routes and for any model/graph failure. It is not yet the completed
agent architecture requested by the course feedback.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, NotRequired, TypedDict

from v2_triage_graph import build_triage_graph

log = logging.getLogger(__name__)
MaybeReply = dict[str, Any] | None
Handler = Callable[[str], Awaitable[MaybeReply]]

class LiveState(TypedDict):
    question: str
    status: NotRequired[str]
    route: NotRequired[str]
    triage_status: NotRequired[str]
    model_confidence: NotRequired[float]
    response: NotRequired[dict[str, Any] | None]


def build_live_graph(preflight: Handler,
                     handlers: dict[str, Handler],
                     model_fn=None):
    """Create real graph nodes with isolated, injected executors.

    preflight is allowed to consult verified MCP tickets or enforce company
    policy. It may return a final response. No node may call a write MCP tool.
    """
    from langgraph.graph import START, END, StateGraph
    triage = build_triage_graph(model_fn)
    graph = StateGraph(LiveState)

    async def enforce(state: LiveState) -> dict:
        response = await preflight(state['question'])
        if response is not None:
            return {"status": "policy_or_ticket_preflight", "response": response}
        return {"status": "pending_triage"}

    async def classify(state: LiveState) -> dict:
        decision = await triage.ainvoke({"question": state['question']})
        route = str(decision.get('selected_route') or 'clarify')
        confidence = float(decision.get('confidence') or 0)
        if decision.get('triage_status') != 'model_validated':
            # Fail closed to the existing documented workflow; never use a
            # guessed model route to create a draft.
            return {"route": "legacy", "triage_status": "model_unavailable",
                    "model_confidence": confidence}
        if route in ('ticket_create', 'ticket_read', 'employee_profile') and confidence < 0.8:
            return {"route": "legacy", "triage_status": "low_action_confidence",
                    "model_confidence": confidence}
        if route not in handlers:
            route = 'legacy'
        return {"route": route, "triage_status": "model_validated",
                "model_confidence": confidence}

    def make_dispatch(route: str):
        async def run_route(state: LiveState) -> dict:
            executor = handlers.get(route)
            if executor is None:
                return {"status": "legacy_fallback"}
            try:
                response = await executor(state['question'])
            except Exception:
                # The verified legacy workflow remains the recovery path.
                log.exception("Live graph route failed: %s", route)
                return {"status": "handler_failed_fallback"}
            if response is None:
                return {"status": "legacy_fallback"}
            return {"status": "graph_answered", "response": response}
        return run_route

    graph.add_node('mandatory_preflight', enforce)
    graph.add_node('llm_triage', classify)
    graph.add_edge(START, 'mandatory_preflight')
    graph.add_conditional_edges('mandatory_preflight',
        lambda st: 'stop' if st.get('response') is not None else 'triage',
        {'stop': END, 'triage': 'llm_triage'})
    # Crucially: distinct conditional edges enter real route-specific nodes.
    # Each node invokes only its explicit injected, non-writing executor.
    for name in sorted(handlers):
        graph.add_node(name, make_dispatch(name))
        graph.add_edge(name, END)
    graph.add_conditional_edges('llm_triage',
        lambda st: st.get('route') if st.get('route') in handlers else 'legacy',
        {**{route: route for route in handlers}, 'legacy': END})
    return graph.compile()


async def run_live_graph(question: str, preflight: Handler,
                         handlers: dict[str, Handler], model_fn=None) -> MaybeReply:
    graph = build_live_graph(preflight, handlers, model_fn)
    result = await graph.ainvoke({"question": question})
    return result.get('response')
