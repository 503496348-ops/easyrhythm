"""
Intent Classification Engine — AtomCollide-智械工坊

Structured intent classification with confidence scoring and fallback handling.
Bridges the gap between opaque LLM routing and Rasa-style NLU pipelines.

Features:
- Pattern-based fast-path classification (zero-latency for common intents)
- LLM fallback for ambiguous messages (uses gpt-4.1-mini)
- Confidence scoring (0.0–1.0) with configurable fallback threshold
- Intent history tracking per conversation
- Low-confidence fallback: asks for clarification instead of routing blindly
"""
from __future__ import annotations as _annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Intent definitions
# ---------------------------------------------------------------------------

INTENT_FLIGHT_STATUS = "flight_status"
INTENT_BOOKING_CHANGE = "booking_change"
INTENT_CANCELLATION = "cancellation"
INTENT_SEAT_CHANGE = "seat_change"
INTENT_REFUND_REQUEST = "refund_request"
INTENT_BAGGAGE_INQUIRY = "baggage_inquiry"
INTENT_FAQ = "faq"
INTENT_GREETING = "greeting"
INTENT_COMPLAINT = "complaint"
INTENT_GENERAL = "general_inquiry"

# Confidence thresholds
HIGH_CONFIDENCE = 0.85
MEDIUM_CONFIDENCE = 0.60
LOW_CONFIDENCE_THRESHOLD = 0.45  # Below this → trigger fallback clarification

# Agent name mapping per intent
INTENT_TO_AGENT: Dict[str, str] = {
    INTENT_FLIGHT_STATUS: "Flight Information Agent",
    INTENT_BOOKING_CHANGE: "Booking and Cancellation Agent",
    INTENT_CANCELLATION: "Booking and Cancellation Agent",
    INTENT_SEAT_CHANGE: "Seat and Special Services Agent",
    INTENT_REFUND_REQUEST: "Refunds and Compensation Agent",
    INTENT_BAGGAGE_INQUIRY: "FAQ Agent",
    INTENT_FAQ: "FAQ Agent",
    INTENT_GREETING: "Triage Agent",
    INTENT_COMPLAINT: "Refunds and Compensation Agent",
    INTENT_GENERAL: "Triage Agent",
}


# ---------------------------------------------------------------------------
# Pattern definitions — fast regex-based classification
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IntentPattern:
    """A compiled pattern for fast intent matching."""
    intent: str
    patterns: Tuple[re.Pattern, ...]
    base_confidence: float  # Confidence when pattern matches


_PATTERNS: List[IntentPattern] = [
    # Flight status
    IntentPattern(
        intent=INTENT_FLIGHT_STATUS,
        patterns=(
            re.compile(r"\b(flight\s*(status|info|update|delay|delayed|cancelled|canceled))\b", re.I),
            re.compile(r"\b(when\s+(is|does|will)\s+(my|the)\s+flight)\b", re.I),
            re.compile(r"\b(is\s+my\s+flight\s+(on\s+time|delayed|cancelled))\b", re.I),
            re.compile(r"\b(departure|arrival|gate)\s+(time|info|number)\b", re.I),
            re.compile(r"\bwhere\s+is\s+my\s+flight\b", re.I),
            re.compile(r"\bflight\s+[A-Z]{2}\d{2,4}\b"),
        ),
        base_confidence=0.92,
    ),
    # Booking change / rebooking
    IntentPattern(
        intent=INTENT_BOOKING_CHANGE,
        patterns=(
            re.compile(r"\b(rebook|re-book|change\s+(my\s+)?(flight|booking|reservation))\b", re.I),
            re.compile(r"\b(new\s+flight|alternate\s+flight|alternative\s+flight)\b", re.I),
            re.compile(r"\b(reschedule|move\s+(my\s+)?flight)\b", re.I),
            re.compile(r"\b(book\s+(a\s+)?(new|different|another)\s+flight)\b", re.I),
        ),
        base_confidence=0.90,
    ),
    # Cancellation
    IntentPattern(
        intent=INTENT_CANCELLATION,
        patterns=(
            re.compile(r"\b(cancel(lation)?|cancel\s+(my\s+)?(flight|booking|reservation|trip))\b", re.I),
            re.compile(r"\b(don'?t\s+want\s+to\s+(fly|travel|go))\b", re.I),
            re.compile(r"\b(refund\s+for\s+(cancel|cancelation))\b", re.I),
        ),
        base_confidence=0.90,
    ),
    # Seat change
    IntentPattern(
        intent=INTENT_SEAT_CHANGE,
        patterns=(
            re.compile(r"\b(change|switch|move|update)\s+(my\s+)?seat\b", re.I),
            re.compile(r"\b(window|aisle|middle|front\s+row|exit\s+row)\s+seat\b", re.I),
            re.compile(r"\b(sit|sitting|seat)\s+(at|in|near)\b", re.I),
            re.compile(r"\bseat\s+(map|selection|assignment|number)\b", re.I),
            re.compile(r"\b(extra\s+legroom|economy\s+plus|business\s+class)\b", re.I),
            re.compile(r"\b(medical|special\s+service|wheelchair)\b", re.I),
        ),
        base_confidence=0.88,
    ),
    # Refund / compensation
    IntentPattern(
        intent=INTENT_REFUND_REQUEST,
        patterns=(
            re.compile(r"\b(refund|compensation|reimburse|voucher|credit)\b", re.I),
            re.compile(r"\b(hotel|meal|ground\s+transport)\s+(voucher|credit|cover)\b", re.I),
            re.compile(r"\b(missed\s+connection|lost\s+(luggage|baggage))\b", re.I),
            re.compile(r"\b(duty\s+of\s+care|disruption\s+support)\b", re.I),
        ),
        base_confidence=0.88,
    ),
    # Baggage
    IntentPattern(
        intent=INTENT_BAGGAGE_INQUIRY,
        patterns=(
            re.compile(r"\b(bag|bags|baggage|luggage|suitcase|carry[\s-]*on|checked\s+bag)\b", re.I),
            re.compile(r"\b(overweight|over\s*size|weight\s+limit|size\s+limit)\b", re.I),
            re.compile(r"\b(lost\s+bag|missing\s+bag|delayed\s+bag|baggage\s+claim)\b", re.I),
        ),
        base_confidence=0.85,
    ),
    # FAQ (policy, wifi, general info)
    IntentPattern(
        intent=INTENT_FAQ,
        patterns=(
            re.compile(r"\b(wifi|wi-fi|internet|password)\b", re.I),
            re.compile(r"\b(policy|policies|rules|allowance|allow)\b", re.I),
            re.compile(r"\b(how\s+many\s+seats|seat\s+configuration|plane\s+layout)\b", re.I),
            re.compile(r"\b(check[\s-]*in|boarding\s+pass|boarding\s+time)\b", re.I),
        ),
        base_confidence=0.80,
    ),
    # Greeting
    IntentPattern(
        intent=INTENT_GREETING,
        patterns=(
            re.compile(r"^(hi|hello|hey|good\s+(morning|afternoon|evening)|howdy|greetings)\s*[!?.]*$", re.I),
            re.compile(r"^(what'?s\s+up|sup|yo)\s*[!?.]*$", re.I),
        ),
        base_confidence=0.95,
    ),
    # Complaint
    IntentPattern(
        intent=INTENT_COMPLAINT,
        patterns=(
            re.compile(r"\b(terrible|awful|worst|unacceptable|horrible|frustrated|angry|furious)\b", re.I),
            re.compile(r"\b(complain|complaint|speak\s+to\s+(a\s+)?(manager|supervisor))\b", re.I),
            re.compile(r"\b(never\s+(fly|again)|bad\s+service|poor\s+service)\b", re.I),
        ),
        base_confidence=0.85,
    ),
]


# ---------------------------------------------------------------------------
# LLM-based fallback classifier
# ---------------------------------------------------------------------------

_LLM_CLASSIFICATION_PROMPT = """You are an intent classifier for an airline customer service system.
Classify the user message into EXACTLY ONE of these intents:
- flight_status (asking about flight times, delays, gates, status)
- booking_change (wanting to rebook, change, or reschedule a flight)
- cancellation (wanting to cancel a flight or booking)
- seat_change (wanting to change seats, request special seating)
- refund_request (asking for refunds, compensation, vouchers)
- baggage_inquiry (questions about bags, luggage, lost items)
- faq (general policy questions, wifi, check-in info)
- greeting (saying hello, casual opening)
- complaint (expressing dissatisfaction, requesting escalation)
- general_inquiry (anything else airline-related)

Respond with ONLY a JSON object:
{{"intent": "<intent_name>", "confidence": <0.0-1.0>, "reasoning": "<brief reason>"}}

User message: {message}"""


class IntentResult(BaseModel):
    """Result of intent classification."""
    intent: str
    confidence: float
    source: str  # "pattern" or "llm"
    reasoning: str = ""
    agent_target: str = ""
    timestamp: float = 0.0


class IntentClassificationError(Exception):
    """Raised when intent classification fails completely."""
    pass


async def classify_intent_pattern(message: str) -> Optional[IntentResult]:
    """Fast-path: classify using regex patterns. Returns None if no confident match."""
    best: Optional[IntentResult] = None
    best_score = 0.0

    for ip in _PATTERNS:
        for pattern in ip.patterns:
            if pattern.search(message):
                # Boost confidence if multiple patterns match the same intent
                match_count = sum(1 for p in ip.patterns if p.search(message))
                boosted = min(ip.base_confidence + 0.03 * (match_count - 1), 0.99)
                if boosted > best_score:
                    best_score = boosted
                    best = IntentResult(
                        intent=ip.intent,
                        confidence=round(boosted, 3),
                        source="pattern",
                        reasoning=f"Matched {match_count} pattern(s) for {ip.intent}",
                        agent_target=INTENT_TO_AGENT.get(ip.intent, "Triage Agent"),
                        timestamp=time.time(),
                    )
    return best


async def classify_intent_llm(message: str) -> IntentResult:
    """LLM fallback: classify using a lightweight model call."""
    import json as _json

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI()
        response = await client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "You are a precise intent classifier. Respond with valid JSON only."},
                {"role": "user", "content": _LLM_CLASSIFICATION_PROMPT.format(message=message)},
            ],
            temperature=0.0,
            max_tokens=150,
        )
        raw = (response.choices[0].message.content or "").strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        data = _json.loads(raw)
        intent = data.get("intent", INTENT_GENERAL)
        confidence = float(data.get("confidence", 0.5))
        reasoning = data.get("reasoning", "LLM classification")
        return IntentResult(
            intent=intent if intent in INTENT_TO_AGENT else INTENT_GENERAL,
            confidence=round(min(max(confidence, 0.0), 1.0), 3),
            source="llm",
            reasoning=reasoning,
            agent_target=INTENT_TO_AGENT.get(intent, "Triage Agent"),
            timestamp=time.time(),
        )
    except Exception as exc:
        return IntentResult(
            intent=INTENT_GENERAL,
            confidence=0.30,
            source="fallback",
            reasoning=f"LLM classification failed: {exc}",
            agent_target="Triage Agent",
            timestamp=time.time(),
        )


async def classify_intent(message: str) -> IntentResult:
    """
    Classify user intent using pattern matching first, LLM fallback if uncertain.

    Returns an IntentResult with intent, confidence, and recommended agent target.
    """
    # Step 1: Try fast pattern matching
    pattern_result = await classify_intent_pattern(message)

    if pattern_result and pattern_result.confidence >= HIGH_CONFIDENCE:
        return pattern_result

    # Step 2: If pattern match is medium-confidence, still use it but allow LLM override
    llm_result = await classify_intent_llm(message)

    # If LLM is significantly more confident, use LLM result
    if pattern_result and llm_result:
        if llm_result.confidence > pattern_result.confidence + 0.10:
            return llm_result
        return pattern_result

    if llm_result:
        return llm_result

    # Absolute fallback
    return IntentResult(
        intent=INTENT_GENERAL,
        confidence=0.20,
        source="default",
        reasoning="No pattern or LLM match",
        agent_target="Triage Agent",
        timestamp=time.time(),
    )


def should_fallback(intent_result: IntentResult) -> bool:
    """
    Determine if confidence is too low and we should ask for clarification
    instead of routing to an agent.
    """
    return intent_result.confidence < LOW_CONFIDENCE_THRESHOLD


def get_fallback_message(intent_result: IntentResult) -> str:
    """Generate a clarification message for low-confidence intents."""
    return (
        f"I want to make sure I help you with the right thing. "
        f"Could you tell me a bit more about what you need? "
        f"For example, I can help with:\n"
        f"• Flight status and delays\n"
        f"• Booking changes and cancellations\n"
        f"• Seat selection and special services\n"
        f"• Refunds and compensation\n"
        f"• Baggage questions\n"
        f"• General policies"
    )
