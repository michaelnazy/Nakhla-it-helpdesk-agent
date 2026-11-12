"""Live Nakhla graph bridge: safe MCP/KB handlers, no write tools.

This calls existing, already-tested functions; the graph cannot make arbitrary
MCP calls and cannot call create_ticket or add_ticket_note.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from v2_live_flow import run_live_graph
from v2_action_routes import (explicit_new_ticket_request, prepare_ticket, verified_incident, grounded_policy)

log = logging.getLogger(__name__)

async def maybe_route(message, email, employee, session, tools, backend):
    """Return a normal FastAPI response or None to retain the old agent path."""
    from ticket_memory_router import handle_ticket_query
    from v2_support import policy_first, choose_general_evidence, choose_catalog_evidence, general_answer, choose_reported_error_evidence

    async def preflight(question):
        # Ownership-verified historical ticket reads take precedence over
        # keyword-sensitive policy checks, matching v1 behavior.
        ticket = await handle_ticket_query(question, email, employee, session,
                                           tools, backend.mcp_call, backend._reply)
        if ticket is not None:
            return ticket
        override = policy_first(question, employee)
        if override is None:
            return None
        session.last_error = ''
        session.last_category = ''
        session.turns.clear()
        refs = [r for r in override['refs'] if r in backend.DOCS]
        if override['kind'] == 'draft':
            return backend._draft(session, override['subject'], override['description'],
                                  override['category'], override['priority'], employee,
                                  refs, override['attempted'], tools)
        return backend._reply(override['text'], refs, tools=tools,
                              workflow='langgraph_policy_enforced')

    async def knowledge(question):
        # NAKHLA_V2_PHASE3C: never let a mistaken knowledge classification
        # swallow an explicit ticket-creation request. Use legacy fallback.
        if explicit_new_ticket_request(question):
            return None
        # Exact error-code KB selection and active incidents remain in the
        # existing, source-checked course workflow until migrated safely.
        if backend.CODE.search(question) or session.last_error:
            # Follow-up context and error-specific procedures stay in the
            # established verifier until migrated with multi-turn evidence.
            return None
        reported = choose_reported_error_evidence(question, backend.DOCS)
        if reported is not None:
            answer, refs = general_answer(reported)
            return backend._reply(answer, refs, tools=tools, workflow='langgraph_rag_answer')
        try:
            results = await asyncio.to_thread(backend.vector_search, question, top_k=5)
        except Exception:
            log.warning('LangGraph knowledge route unavailable, using legacy retrieval')
            return None
        evidence = choose_general_evidence(question, results, backend.DOCS)
        if evidence is None:
            # NAKHLA_V2_PHASE3B_RAGFIX: recover an exact current KB title match
            # if vector search misses the relevant chunk (or scores too low).
            evidence = choose_catalog_evidence(question, backend.DOCS)
        answer, refs = general_answer(evidence)
        return backend._reply(answer, refs, tools=tools,
                              workflow='langgraph_rag_answer' if refs else 'langgraph_unknown')

    async def ticket_read(question):
        # Never infer ticket ownership from the LLM. The existing router
        # performs get_ticket owner verification on every displayed record.
        return await handle_ticket_query(question, email, employee, session,
                                         tools, backend.mcp_call, backend._reply)

    async def profile(question):
        if not isinstance(employee, dict) or not email:
            return backend._reply('I could not verify your employee record.', tools=tools)
        department = employee.get('department') or 'Not available'
        vpn_data = employee.get('vpn') if isinstance(employee.get('vpn'), dict) else {}
        gateway = employee.get('vpn_gateway') or employee.get('gateway') or vpn_data.get('gateway') or 'Not available'
        session.turns.clear()
        session.last_error = ''
        session.last_category = ''
        return backend._reply(f'Department: {department}\nAssigned VPN gateway: {gateway}',
                              tools=tools, workflow='langgraph_employee_lookup')

    # A model suggestion to create a ticket is NOT itself a permission to
    # create or draft one. The existing mandatory approval path handles this.
    # NAKHLA_V2_PHASE3C: source-validated read/plan execution nodes.
    # The LLM selects routes, but only server-side policy and ticket guards
    # can decide whether a draft is permitted. No graph tool can write.
    async def ticket_create(question):
        return await prepare_ticket(question, employee, session, tools, backend)

    async def incident(question):
        return await verified_incident(question, employee, tools, backend)

    async def policy(question):
        return await grounded_policy(question, tools, backend)

    handlers = {
        'knowledge': knowledge,
        'policy': policy,
        'incident': incident,
        'ticket_create': ticket_create,
        'ticket_read': ticket_read,
        'employee_profile': profile,
    }
    return await run_live_graph(message, preflight, handlers)
