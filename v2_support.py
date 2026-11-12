"""Nakhla v2: policy-first safeguards and source-grounded general RAG fallback.

These helpers are deliberately independent of the simulated course services and
use no model-generated instructions for security or ticket write decisions.
Phase 2 does not yet replace regex triage with model-driven LangGraph routing.
"""
from __future__ import annotations

import re
from typing import Any

V2_TAG = 'NAKHLA_V2_PHASE2'

_NUM_WORDS = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
              'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10}


def impacted_users(text: str) -> int:
    """Only count explicitly stated affected people; fail to one otherwise."""
    q = ' '.join(str(text or '').lower().split())
    patterns = (
        r'\b(\d{1,3}|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:affected\s+)?(?:users|people|employees|colleagues|staff|teammates|coworkers)\b',
        r'\b(\d{1,3}|one|two|three|four|five|six|seven|eight|nine|ten)\s+of\s+us\b',
        r'\b(?:affects?|impacts?|blocking)\s+(\d{1,3}|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:users|people|employees|colleagues|staff|teammates|coworkers)\b',
    )
    for pattern in patterns:
        match = re.search(pattern, q)
        if match:
            token = match.group(1)
            number = int(token) if token.isdigit() else _NUM_WORDS[token]
            return max(1, min(number, 999))
    return 1


def executive(employee: dict[str, Any] | None) -> bool:
    employee = employee or {}
    dept = str(employee.get('department') or '').strip().lower()
    return dept in {'executive office', 'executive-office'} or employee.get('is_vip') is True or employee.get('vip') is True


def contractor(employee: dict[str, Any] | None) -> bool:
    employee = employee or {}
    dept = str(employee.get('department') or '').strip().lower()
    return dept in {'contractors', 'contractor'} or employee.get('is_contractor') is True or employee.get('contractor') is True


def priority_for(base: str, employee: dict[str, Any] | None,
                 category: str, affected: int, description: str = '') -> str:
    """P1 is mandatory for Executive Office, >3 users, or security incidents."""
    q = description.lower()
    if executive(employee) or affected > 3:
        return 'P1'
    if category == 'security' and re.search(r'\b(?:stolen|lost|phishing|compromised)\b', q):
        return 'P1'
    if category == 'security' and str((employee or {}).get('department') or '').lower() == 'finance' and (re.search(r'\b(?:vpn|remote access|nx-\d+)\b', q)):
        return 'P2'
    return base if base in {'P1', 'P2', 'P3', 'P4'} else 'P3'


def policy_first(message: str, employee: dict[str, Any] | None) -> dict[str, Any] | None:
    """Mandatory policy exemptions, *before* generic KB or ticket logic.

    Returns either {kind: 'answer', text, refs} or {kind: 'draft', ...};
    the existing server-side _draft()/approval gate remains the only writer.
    """
    q = ' '.join((message or '').lower().split())
    vpn = bool(re.search(r'\b(?:vpn|nakhlaconnect|remote access|nx-\d+)\b', q))
    if contractor(employee) and vpn:
        return {'kind': 'answer', 'refs': ['SP-002', 'KB-016'],
                'text': ('Contractors are not permitted to use the NakhlaConnect VPN. '
                         'Use the Nakhla Workspace VDI portal https://vdi.nakhla.example instead. '
                         'A VPN access ticket must not be created for contractors.')}
    personal = bool(re.search(r'\b(?:personal|own|home)\s+(?:laptop|computer|pc)\b', q))
    corp = bool(re.search(r'\b(?:vpn|nakhlaconnect|nakhla-corp|corporate wi-?fi|nx-\d+)\b', q))
    if personal and corp:
        return {'kind': 'answer', 'refs': ['SP-002'],
                'text': ('Personal laptops cannot connect directly to Nakhla-Corp or NakhlaConnect VPN. '
                         'Use the approved VDI portal with manager approval; do not bypass device compliance checks.')}
    # NAKHLA_V2_PHASE2B: explicit phone/chat/email password-reset prohibition.
    # SP-001 is authoritative; KB-004 supplies the self-service steps.
    password_reset = bool(re.search(r'\b(?:reset|recover|change|resetting)\b', q)
                          and re.search(r'\b(?:password|nakhlaid)\b', q))
    assisted_channel = bool(re.search(
        r'\b(?:over|by|via|on)\s+(?:the\s+)?(?:phone|telephone|chat|email|e-mail|call)\b', q))
    desk_request = bool(re.search(r'\b(?:service desk|help\s*desk|it staff|it support|can it)\b', q))
    if password_reset and assisted_channel and (desk_request or 'over the phone' in q):
        return {'kind': 'answer', 'refs': ['SP-001', 'KB-004'],
                'text': ('The Service Desk cannot reset or read out NakhlaID passwords over '
                         'the phone, chat or email. Phone-based password reset is not allowed '
                         'under current security policy SP-001. Use self-service at '
                         'https://id.nakhla.example/reset (KB-004). If self-service is '
                         'impossible, an assisted reset requires an identity_access ticket, '
                         'manager approval and in-person or video identity verification.')}
    mfa = bool(re.search(r'\b(?:mfa|2fa|nakhlakey|authenticator|sign[- ]?in|log[- ]?in|login|one.time|verification)\b', q))
    sms = bool(re.search(r'\b(?:sms|text message|voice[- ]?call|voice code|phone call)\b', q))
    if sms and (mfa or re.search(r'\b(?:code|codes|otp|one[- ]?time password)\b', q)):
        # Do not provide a policy-prohibited SMS/voice MFA fallback even when
        # the user phrases it only as an SMS verification code request.
        return {'kind': 'answer', 'refs': ['SP-002', 'KB-007'],
                'text': ('SMS and voice-call MFA codes are not allowed (prohibited) under current security policy SP-002. '
                         'Use NakhlaKey, an approved FIDO2 key, or a one-time backup code. '
                         'Never use an old FAQ that suggests SMS codes.')}
    phone_at_home = bool(re.search(r'\b(?:left|forgot)\b.{0,35}\bphone\b.{0,18}\bhome\b|\bphone\b.{0,12}\bat home\b', q))
    if phone_at_home:
        return {'kind': 'answer', 'refs': ['SP-002', 'KB-007'],
                'text': ('A phone left at home is not a security incident. '
                         'Use one of your one-time backup codes to sign in; SMS codes are not supported.')}
    # NAKHLA_V2_PHASE2C_SECURITY_ROUTING: mandatory current-doc policies.
    # KB-014: automatic external mail forwarding is blocked. Regular outgoing
    # messages to external recipients are NOT prohibited by this rule.
    mail = bool(re.search(r'\b(?:mail|email|outlook|mailbox|nakhla mail)\b', q))
    forwarding = bool(re.search(r'\b(?:forward|forwarding|redirect|redirecting)\b', q))
    automatic = bool(re.search(
        r'\b(?:automatic|automatically|auto[- ]?forward|rule|always|every message|all messages|set up|setup)\b', q))
    external = bool(re.search(
        r'\b(?:personal|private|external|outside|non[- ]?company|gmail|yahoo|hotmail|outlook\.com)\b', q))
    if mail and forwarding and automatic and external:
        return {'kind': 'answer', 'refs': ['KB-014'],
                'text': ('Automatic forwarding of Nakhla Mail to external or personal accounts '
                         '(including Gmail) is blocked and not allowed by Security Operations '
                         '(KB-014). Rules forwarding outside nakhla.example silently fail. '
                         'Use approved company mail instead; do not provide bypass steps.')}

    # SP-001 §4: actual disclosure of a password/credential to a suspicious
    # site, or unexpected NakhlaKey prompts, is a P1 security incident.
    credentials = bool(re.search(r'\b(?:password|passwords|credentials?|passphrase)\b', q))
    submitted = bool(re.search(r'\b(?:typed|entered|submitted|pasted|gave|shared|supplied|put)\b', q))
    suspicious_page = bool(re.search(
        r'\b(?:fake|phishing|phish|fraudulent|suspicious|bogus|spoofed|malicious|lookalike|look-alike)\b', q))
    unexpected_mfa = bool(re.search(r'\bnakhlakey\b', q)
                          and re.search(r'\bprompts?\b', q)
                          and re.search(r"\b(?:did not|didn.t|never|not me|unexpected|unsolicited|unrecognized)\b", q))
    negated_submission = bool(re.search(
        r"\b(?:never|didn.t|did not|have not|haven.t)\s+(?:actually\s+)?"
        r"(?:type|typed|enter|entered|submit|submitted|paste|pasted|give|gave|share|shared)\b", q))
    exposed = (credentials and submitted and suspicious_page and not negated_submission) or unexpected_mfa
    if exposed:
        action = bool(re.search(r'\b(?:open|create|raise|file|submit|log)\b.{0,70}\b(?:ticket|case|incident)\b', q))
        if action:
            return {'kind': 'draft', 'refs': ['SP-001', 'KB-014', 'KB-015'],
                    'category': 'security', 'priority': 'P1',
                    'subject': 'Suspected credential compromise / phishing security incident',
                    'description': message + '\nPotential credential compromise; Security Operations P1 escalation per SP-001.',
                    'attempted': ['Reported suspected credential compromise; password reset not confirmed']}
        return {'kind': 'answer', 'refs': ['SP-001', 'KB-004', 'KB-014'],
                'text': ('This is a potential security compromise (SP-001). Reset your '
                         'NakhlaID password immediately at https://id.nakhla.example/reset, '
                         'deny NakhlaKey prompts you did not start, and report the incident '
                         'to Security Operations as security P1. Use Report Phish in Outlook '
                         'for a suspicious email (KB-014).')}

    # SP-001 §3: three or more unexplained lockouts in one day indicate a
    # possible password-guessing attack. Ordinary lockouts use KB-006.
    locked = bool(re.search(r'\b(?:lock(?:ed|outs?|ing)?|locked\s+out)\b', q))
    three_or_more = bool(re.search(
        r'\b(?:three|3|third|four|4|fourth|five|5|fifth|six|6|sixth|seven|7|eight|8)\b'
        r'.{0,55}\b(?:times?|lockouts?|occasions?|today)\b', q))
    same_day = bool(re.search(r'\b(?:today|one day|same day|past 24 hours|last 24 hours)\b', q))
    unexplained = bool(re.search(
        r"\b(?:don.t|do not|can.t|cannot)\s+(?:know|explain|understand|figure)\b|"
        r"\b(?:no idea|no clue|no reason|unknown cause|unexplained|not sure why|without a known cause)\b", q))
    if locked and three_or_more and same_day and unexplained:
        wants_ticket = bool(re.search(
            r'\b(?:open|create|raise|file|submit|log)\b.{0,70}\b(?:ticket|case|incident)\b', q))
        if wants_ticket:
            return {'kind': 'draft', 'refs': ['SP-001', 'KB-006', 'KB-015'],
                    'category': 'security', 'priority': 'P2',
                    'subject': 'Repeated unexplained NakhlaID account lockouts',
                    'description': message + '\nPossible password-guessing attack; Security Operations P2 per SP-001.',
                    'attempted': ['Reported repeated unexplained lockouts; source not identified']}
        return {'kind': 'answer', 'refs': ['SP-001', 'KB-006'],
                'text': ('Three or more unexplained account lockouts in one day may be '
                         'a password-guessing attack. Report this to Security Operations '
                         'as category security, priority P2 under SP-001. '
                         'You may use https://id.nakhla.example/unlock (KB-006), '
                         'but repeated unexplained lockouts require security review.')}

    lost = bool(re.search(r'\b(?:lost|stolen|stole|missing)\b', q))
    phone = bool(re.search(r'\b(?:phone|mobile)\b', q))
    laptop = bool(re.search(r'\b(?:company|work|corporate)\s+(?:laptop|computer)\b', q))
    has_mfa_app = bool(re.search(r'\b(?:nakhlakey|authenticator|mfa)\b', q))
    if lost and (laptop or (phone and has_mfa_app)):
        return {'kind': 'draft', 'refs': ['SP-002', 'KB-015'], 'category': 'security', 'priority': 'P1',
                'subject': 'Lost or stolen company device / NakhlaKey security incident',
                'description': (message + '\nReport within 1 hour; Security Operations must handle device lock/wipe.'),
                'attempted': ['Reported lost or stolen device; no security action confirmed yet']}
    if lost and phone and not has_mfa_app:
        return {'kind': 'answer', 'refs': ['SP-002'],
                'text': 'Was NakhlaKey installed on the lost or stolen phone? This determines whether a P1 security incident must be reported within one hour.'}
    return None


_STOP = frozenset('the a an i my we our is are was were to of in on at with can could how do does why what where when me you your help about for and or that this from please need issue problem not work working it use using have has had want get getting'.split())


def _terms(text: str) -> set[str]:
    # NAKHLA_V2_PHASE3B_RAGFIX: normalize hyphenated Wi-Fi before tokenization.
    # Without this, the regex discards "Wi" and "Fi" as two short tokens.
    normalized = re.sub(r'\bwi[\s-]?fi\b', 'wifi', str(text or '').lower())
    terms: set[str] = set()
    for token in re.findall(r'[a-z][a-z0-9]{2,}', normalized):
        if token in _STOP:
            continue
        if token in {'wireless', 'wi-fi', 'wifi'}:
            token = 'wifi'
        if token in {'authenticate', 'authentication', 'login', 'logon', 'signin'}:
            token = 'signin'
        terms.add(token)
    return terms


def choose_general_evidence(question: str, retrieved: list[dict], docs: dict[str, dict],
                            min_similarity: float = 0.38) -> dict[str, Any] | None:
    """Choose a verified current KB chunk; no fabricated steps or citations.

    Guard against irrelevant embeddings by requiring meaningfully overlapping
    query terms in the retrieved chunk *and* source title/tags. Scores are tuned
    conservatively and should be recalibrated with a local labeled test set.
    """
    terms = _terms(question)
    if not terms:
        return None
    for match in retrieved[:6]:
        if not isinstance(match, dict):
            continue
        doc_id = match.get('document_id')
        doc = docs.get(doc_id)
        if not doc:
            continue
        meta = doc.get('meta') or {}
        if str(meta.get('status', 'current')).lower() != 'current' or meta.get('authoritative') is False:
            continue
        try:
            similarity = float(match.get('score', 0))
        except (ValueError, TypeError):
            continue
        if similarity < min_similarity or similarity > 1.35:
            continue
        section = str(match.get('text') or '').strip()
        if not section or section.lower().startswith('## change log'):
            continue
        overlap = terms.intersection(_terms(section + ' ' + str(meta.get('title') or '') + ' ' + ' '.join(meta.get('tags') or [])))
        minimum = min(2, len(terms))
        if len(overlap) < minimum:
            continue
        return {'document_id': doc_id, 'text': section[:1650], 'score': similarity,
                'overlap': sorted(overlap)}
    return None


def general_answer(evidence: dict[str, Any] | None) -> tuple[str, list[str]]:
    if not evidence:
        return ('I could not find a sufficiently relevant answer in the current approved knowledge base. '
                'I will not invent troubleshooting steps. Please provide more details, or ask me to prepare a support ticket for approval.', [])
    ref = evidence['document_id']
    return (f'According to current knowledge-base article {ref}:\n\n'
            f'{evidence["text"]}\n\nSource: {ref}\n\n'
            'If this does not address your issue, tell me what you tried and I can prepare a ticket for your approval.', [ref])


def topic_shift(question: str, previous_code: str) -> bool:
    """Prevent a previous error-code topic from swallowing an unrelated question.

    Follow-up phrases without a new topic still inherit the prior code.
    """
    q = ' '.join((question or '').lower().split())
    if not previous_code or re.search(r'\b(?:already tried|still|doesn.t work|didn.t work|same issue|same error|those steps|that fix|after that)\b', q):
        return False
    topic = None
    if re.search(r'\b(?:wi-?fi|wireless|printer|printing|paper|guest network)\b', q):
        topic = 'network_other'
    elif re.search(r'\b(?:software|licen[cs]e|software center|installing)\b', q):
        topic = 'software'
    elif re.search(r'\b(?:password|mfa|nakhlakey|authenticator|account lock|sso|signin|login)\b', q):
        topic = 'identity'
    elif re.search(r'\b(?:email|outlook|mailbox|calendar)\b', q):
        topic = 'email'
    elif re.search(r'\b(?:laptop|hardware|dock|monitor|phone)\b', q):
        topic = 'hardware'
    elif re.search(r'\b(?:vpn|nakhlaconnect|remote access)\b', q):
        topic = 'vpn'
    if not topic:
        return False
    previous = 'vpn' if previous_code.startswith('NX-') else 'identity' if previous_code.startswith(('NID-', 'MFA-', 'CRM-')) else 'software' if previous_code.startswith('SWC-') else 'hardware' if previous_code.startswith('HW-') else ''
    return topic != previous


# NAKHLA_V2_PHASE2B: exact reported error-message retrieval from CURRENT source text.
def choose_reported_error_evidence(question: str, docs: dict[str, dict]) -> dict[str, Any] | None:
    """Anchor a code-free error quote to the exact documented phrase.

    Example: an app that says 'This app is not assigned to me' matches
    the documented NID-512 row without the user having to know NID-512.
    This is a verified lexical retrieval path, not an LLM guess; it checks
    only current authoritative docs, with the matching source line returned.
    No result means the normal embedding search should run.
    """
    q = str(question or '')
    match = re.search(r'\b(?:says?|shows?|displays?|reads?|reports?)\s*:?\s*(.+)', q, re.I)
    if not match:
        return None
    reported = re.split(r'[.!?](?:\s|$)', match.group(1), maxsplit=1)[0]

    def tokens(value: str) -> list[str]:
        return re.findall(r'[a-z0-9]+', value.casefold())

    words = tokens(reported)
    # Avoid speculative matching on short/common phrases such as 'error' or
    # 'access denied' alone. Require a documented five-word sequence.
    if len(words) < 5:
        return None
    qgrams = {tuple(words[i:i + 5]) for i in range(len(words) - 4)}
    winner = None
    for doc_id, doc in docs.items():
        meta = (doc or {}).get('meta') or {}
        if str(meta.get('status', 'current')).lower() != 'current' or meta.get('authoritative') is False:
            continue
        for line in str(doc.get('text') or '').splitlines():
            source_words = tokens(line)
            if len(source_words) < 5:
                continue
            source_grams = {tuple(source_words[i:i + 5]) for i in range(len(source_words) - 4)}
            common = len(qgrams.intersection(source_grams))
            if common and (winner is None or common > winner[0]):
                winner = (common, doc_id, line.strip())
    if winner is None:
        return None
    _, doc_id, line = winner
    return {
        'document_id': doc_id,
        'text': 'Documented error message and its instructions:\n' + line[:1650],
        'score': 1.0,
        'overlap': [],
        'evidence_kind': 'reported_error_phrase',
    }


def choose_catalog_evidence(question: str, docs: dict[str, dict]) -> dict[str, Any] | None:
    """Only recover a direct title match from *current, authoritative* KB docs.

    This is a conservative lexical fallback if vector top_k misses a document.
    Require >=2 distinctive query/title tokens, >=55% query-term coverage,
    and an unambiguous best document. Never generate an ungrounded fix.
    """
    terms = _terms(question)
    if len(terms) < 2:
        return None
    candidates: list[tuple[float, int, str, dict]] = []
    for doc_id, doc in docs.items():
        if not isinstance(doc, dict):
            continue
        meta = doc.get('meta') or {}
        if str(meta.get('status', 'current')).lower() != 'current' or meta.get('authoritative') is False:
            continue
        title = str(meta.get('title') or '')
        title_terms = _terms(title)
        common = terms & title_terms
        if len(common) < 2 or len(common) / len(terms) < 0.55:
            continue
        source_text = str(doc.get('text') or '').strip()
        if not source_text:
            continue
        # Favor explicit title matches, not loosely related body/FAQ mentions.
        score = len(common) / len(terms)
        candidates.append((score, len(common), str(doc_id), doc))
    if not candidates:
        return None
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    if len(candidates) > 1 and candidates[0][:2] == candidates[1][:2]:
        return None  # ambiguous: don't choose an arbitrary source
    _, _, doc_id, doc = candidates[0]
    content = str(doc['text']).split('## Change log', 1)[0].strip()
    if not content:
        return None
    return {'document_id': doc_id, 'text': content[:1650],
            'score': 1.0, 'overlap': sorted(terms & _terms(doc['meta']['title']))}
