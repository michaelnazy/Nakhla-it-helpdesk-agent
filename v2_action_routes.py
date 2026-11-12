"""Phase 3c: verified read/plan executors for the live LangGraph.

Nothing in this module writes helpdesk tickets. All ticket creation remains
inside agent_backend.approve after a server-side one-time action_id check.
This is local-course-evaluation code, not a production identity service.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from v2_support import impacted_users, priority_for, choose_general_evidence, choose_catalog_evidence, general_answer

log = logging.getLogger(__name__)

_CREATE = re.compile(r"\b(?:open|create|raise|submit|file|log|prepare|make)\b.{0,110}\b(?:new\s+)?(?:support\s+)?(?:ticket|case|incident)\b|\b(?:ticket|case)\b.{0,60}\b(?:opened|created|raised|filed|prepared)\b", re.I)
_NO_CREATE = re.compile(r"\b(?:do\s+not|don.t|without|not\s+to|no\s+need\s+to|never)\b.{0,55}\b(?:open|create|raise|file|prepare|want|need)\b.{0,65}\b(?:ticket|case|incident)\b", re.I)
_INFORMATIONAL = re.compile(r"\b(?:how\s+(?:do|can|should)\s+(?:i|we)|what(?:.s| is)\s+the\s+(?:process|way)|tell\s+me\s+how|explain\s+how)\b.{0,85}\b(?:open|create|file|raise)\b.{0,70}\b(?:ticket|case)\b", re.I)
_WANTS = re.compile(r"\b(?:i|we)\s+(?:really\s+)?(?:need|want|request)\s+(?:a|another|new)\s+(?:support\s+)?(?:ticket|case)\b", re.I)
_READ = re.compile(r"\b(?:show|list|view|read|check|search|find|status\s+of)\b.{0,65}\b(?:my\s+)?(?:open|previous|existing|old|past)?\s*(?:support\s+)?tickets\b", re.I)


def explicit_new_ticket_request(question: str) -> bool:
    """Independent authorization-to-DRAFT guard; LLM alone cannot grant it."""
    q = " ".join(str(question or "").split())
    if not q or _NO_CREATE.search(q) or _INFORMATIONAL.search(q):
        return False
    if _READ.search(q) and not _CREATE.search(q):
        return False
    return bool(_CREATE.search(q) or _WANTS.search(q))


def ticket_category(question: str) -> tuple[str, str]:
    """Categories supported by KB-015 / the simulated helpdesk ticket contract."""
    q = str(question or "").lower()
    if re.search(r"\b(?:security|phishing|phish|compromised|credential|malware|stolen)\b", q):
        return "security", "P2"
    if re.search(r"\b(?:wi[\s-]?fi|wireless|wlan|ethernet|network|internet|vpn|nakhlaconnect|vdi)\b", q):
        return "network_access", ("P2" if re.search(r"\b(?:cannot|can.t|unable|down|outage|blocked|offline|stopped|not working)\b", q) else "P3")
    if re.search(r"\b(?:outlook|mailbox|email|e-mail|calendar|mail)\b", q):
        return "email_collab", "P3"
    if re.search(r"\b(?:nakhlakey|password|nakhlaid|sso|login|sign\s?in|account)\b", q):
        return "identity_access", "P3"
    if re.search(r"\b(?:laptop|dock|monitor|keyboard|hardware|printer)\b", q):
        return "hardware", "P3"
    if re.search(r"\b(?:software|install|application|app|program)\b", q):
        return "software", "P3"
    return "other", "P3"


async def prepare_ticket(question: str, employee: dict | None, session: Any,
                         tools: list[dict], backend: Any) -> dict | None:
    """Return server-generated *pending* ticket draft, or legacy fallback.

    Explicit consent is still required through /api/approve. All VPN / error-code
    / incident-sensitive requests retain the original verified backend route.
    Mandatory policy checks are executed in the graph preflight first.
    """
    if not explicit_new_ticket_request(question):
        return None
    if not isinstance(employee, dict) or not employee.get("email") or not employee.get("department"):
        return backend._reply("I need your verified work email before preparing a support ticket.", tools=tools,
                              workflow="needs_verification")
    if str(employee.get("account_status", "active")).lower() not in {"active", "enabled"}:
        return backend._reply("Your account requires Service Desk verification before a ticket can be proposed.",
                              tools=tools, workflow="needs_verification")
    # Do not change the established verified incident / code / Finance VPN flow.
    # Especially never create a duplicate ticket for an active NX-503 incident.
    if backend.CODE.search(question) or re.search(r"\b(?:vpn|nakhlaconnect|remote access)\b", question, re.I):
        return None
    category, priority = ticket_category(question)
    # A model-proposed ticket route is NOT allowed to bypass high-priority
    # company security rules. The preflight will have handled their drafts.
    affected = impacted_users(question)
    priority = priority_for(priority, employee, category, affected, question)
    refs = [ref for ref in ("KB-015",) if ref in backend.DOCS]
    attempted = (["User reports troubleshooting already attempted: " + question[:350]]
                 if backend._already_tried(question) else
                 ["Reported the problem; troubleshooting steps not confirmed"])
    subject = ("Security" if category == "security" else category.replace("_", " ").title()) + " issue: " + question[:100]
    draft = backend._draft(session, subject, question, category, priority,
                           employee, refs, attempted, tools)
    if isinstance(draft, dict) and draft.get("pending_action") is not None:
        draft["state"] = "langgraph_awaiting_approval"
    return draft


async def verified_incident(question: str, employee: dict | None,
                            tools: list[dict], backend: Any) -> dict | None:
    """Re-use the already-verified active-incident LangGraph, never model claims.

    Strictly follow verified NX-503 behavior; other incidents fall back to the
    legacy status verifier until coverage and gateway rules are migrated.
    """
    code = backend.CODE.search(question)
    if not code or code.group(0).upper() != "NX-503" or not isinstance(employee, dict):
        return None
    try:
        state = await backend.WORKFLOW.ainvoke({"question": question, "employee_email": employee["email"]})
        impact = state.get("incident_applicability") or {}
        sources = state.get("source_validation") or {}
        verified = state.get("verification") or {}
        refs = state.get("source_refs") or []
        answer = state.get("cited_answer")
        if (impact.get("status") == "affected" and sources.get("passed") is True
                and verified.get("passed") is True and "INC-2207" in refs
                and isinstance(answer, str) and answer.strip()):
            tools.append({"tool": "get_service_status", "ok": True})
            return backend._reply(answer, refs, tools=tools,
                                  workflow="langgraph_verified_incident")
    except Exception:
        log.exception("Phase 3c incident verification unavailable; using legacy")
    return None


async def grounded_policy(question: str, tools: list[dict], backend: Any) -> dict | None:
    """Only answer non-mandatory policy questions from approved policy docs.

    Mandatory prohibitions and emergency drafts are applied by the graph
    preflight. Other requests with weak evidence return None to the legacy
    verifier rather than treating LLM opinion as organizational policy.
    """
    if explicit_new_ticket_request(question) or backend.CODE.search(question):
        return None
    try:
        matches = await asyncio.to_thread(backend.vector_search, question, top_k=5)
    except Exception:
        return None
    evidence = choose_general_evidence(question, matches, backend.DOCS)
    if evidence is None:
        evidence = choose_catalog_evidence(question, backend.DOCS)
    if evidence is None:
        return None
    doc_id = evidence["document_id"]
    if not (doc_id.startswith("SP-") or doc_id in {"KB-014", "KB-015", "KB-016"}):
        return None
    text, refs = general_answer(evidence)
    return backend._reply(text, refs, tools=tools, workflow="langgraph_policy_grounded")
