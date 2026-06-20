"""
Entity Extraction Pipeline — AtomCollide-智械工坊

Structured entity extraction for airline customer service conversations.
Bridges the gap between EasyRhythm's keyword matching and Rasa's NLU entity extractors.

Features:
- Regex-based fast extraction for structured patterns (flight #, confirmation, seats, dates, airports)
- LLM fallback for ambiguous/complex entity extraction
- Automatic context hydration from extracted entities
- Entity confidence tracking and deduplication
- Entity types: flight_number, confirmation_number, seat_number, airport_code,
  date, passenger_name, compensation_reason, baggage_tag
"""
from __future__ import annotations as _annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Entity type constants
# ---------------------------------------------------------------------------

ENTITY_FLIGHT_NUMBER = "flight_number"
ENTITY_CONFIRMATION_NUMBER = "confirmation_number"
ENTITY_SEAT_NUMBER = "seat_number"
ENTITY_AIRPORT_CODE = "airport_code"
ENTITY_AIRPORT_NAME = "airport_name"
ENTITY_DATE = "date"
ENTITY_PASSENGER_NAME = "passenger_name"
ENTITY_COMPENSATION_REASON = "compensation_reason"
ENTITY_BAGGAGE_TAG = "baggage_tag"
ENTITY_INTENT_MODIFIER = "intent_modifier"  # e.g., "urgent", "front row", "window"


class ExtractedEntity(BaseModel):
    """A single extracted entity with metadata."""
    entity_type: str
    value: str
    raw_text: str  # Original text span
    confidence: float
    source: str  # "regex" or "llm"
    start: int = -1
    end: int = -1
    timestamp: float = 0.0


class EntityExtractionResult(BaseModel):
    """Result of entity extraction from a user message."""
    entities: List[ExtractedEntity] = []
    message: str = ""
    timestamp: float = 0.0


# ---------------------------------------------------------------------------
# Airport code / name mappings
# ---------------------------------------------------------------------------

AIRPORT_CODES: Dict[str, str] = {
    "cdg": "Paris (CDG)",
    "paris": "Paris (CDG)",
    "charles de gaulle": "Paris (CDG)",
    "jfk": "New York (JFK)",
    "new york": "New York (JFK)",
    "laguardia": "New York (LGA)",
    "lga": "New York (LGA)",
    "ewr": "New York (EWR)",
    "aus": "Austin (AUS)",
    "austin": "Austin (AUS)",
    "sfo": "San Francisco (SFO)",
    "san francisco": "San Francisco (SFO)",
    "lax": "Los Angeles (LAX)",
    "los angeles": "Los Angeles (LAX)",
    "ord": "Chicago (ORD)",
    "chicago": "Chicago (ORD)",
    "mia": "Miami (MIA)",
    "miami": "Miami (MIA)",
    "sea": "Seattle (SEA)",
    "seattle": "Seattle (SEA)",
    "bos": "Boston (BOS)",
    "boston": "Boston (BOS)",
    "den": "Denver (DEN)",
    "denver": "Denver (DEN)",
    "atl": "Atlanta (ATL)",
    "atlanta": "Atlanta (ATL)",
    "dfw": "Dallas (DFW)",
    "dallas": "Dallas (DFW)",
    "lhr": "London (LHR)",
    "london": "London (LHR)",
    "heathrow": "London (LHR)",
    "nrt": "Tokyo (NRT)",
    "tokyo": "Tokyo (NRT)",
    "hnd": "Tokyo (HND)",
    "haneda": "Tokyo (HND)",
}

# 3-letter airport code pattern (uppercase)
_AIRPORT_CODE_RE = re.compile(r"\b([A-Z]{3})\b")


# ---------------------------------------------------------------------------
# Regex patterns for structured entity extraction
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EntityPattern:
    """A compiled regex pattern for entity extraction."""
    entity_type: str
    pattern: re.Pattern
    group: int = 1  # Which capture group contains the value
    confidence: float = 0.90
    normalizer: Any = None  # Optional callable to normalize the value


def _normalize_seat(value: str) -> str:
    """Normalize seat number: '14c' → '14C'."""
    return value.upper().replace(" ", "")


def _normalize_confirmation(value: str) -> str:
    """Normalize confirmation: strip spaces, uppercase."""
    return re.sub(r"\s+", "", value).upper()


def _normalize_flight_number(value: str) -> str:
    """Normalize flight number: 'pa 441' → 'PA441', 'flt-123' → 'FLT-123'."""
    cleaned = re.sub(r"[\s\-]+", "", value).upper()
    return cleaned


def _normalize_airport_code(value: str) -> str:
    """Look up airport code and return canonical name."""
    lower = value.lower().strip()
    return AIRPORT_CODES.get(lower, value.upper())


def _normalize_date(value: str) -> str:
    """Basic date normalization."""
    return value.strip()


_ENTITY_PATTERNS: List[EntityPattern] = [
    # Flight numbers: PA441, NY802, FLT-123, AA 1234, UA-456
    EntityPattern(
        entity_type=ENTITY_FLIGHT_NUMBER,
        pattern=re.compile(r"\b([A-Z]{2,3}[\s\-]?\d{2,4})\b", re.I),
        group=1,
        confidence=0.92,
        normalizer=_normalize_flight_number,
    ),
    # Explicit "flight" prefix: "flight PA441", "flight number FLT-123"
    EntityPattern(
        entity_type=ENTITY_FLIGHT_NUMBER,
        pattern=re.compile(r"\b(?:flight(?:\s*(?:number|#|no\.?))?)\s*[:\-]?\s*([A-Z]{2,3}[\s\-]?\d{2,4})\b", re.I),
        group=1,
        confidence=0.96,
        normalizer=_normalize_flight_number,
    ),
    # Confirmation numbers: IR-D204, LL0EZ6, ABC123, 6-char alphanumeric
    EntityPattern(
        entity_type=ENTITY_CONFIRMATION_NUMBER,
        pattern=re.compile(r"\b(?:confirmation|conf(?:irmation)?(?:\s*(?:number|#|no\.?))?)\s*[:\-]?\s*([A-Z0-9]{4,8})\b", re.I),
        group=1,
        confidence=0.95,
        normalizer=_normalize_confirmation,
    ),
    # Standalone confirmation-like codes (6 uppercase alphanumeric, common pattern)
    # Exclude common English words
    EntityPattern(
        entity_type=ENTITY_CONFIRMATION_NUMBER,
        pattern=re.compile(r"\b(?!NUMBER\b|FLIGHT\b|STATUS\b|SEATMAP\b)([A-Z]{2}[\-]?[A-Z0-9]{4})\b"),
        group=1,
        confidence=0.70,
        normalizer=_normalize_confirmation,
    ),
    # Seat numbers: 14C, 23A, 1A, 2A, seat 14C
    EntityPattern(
        entity_type=ENTITY_SEAT_NUMBER,
        pattern=re.compile(r"\b(?:seat\s*(?:number|#|no\.?)?\s*[:\-]?\s*)?(\d{1,3}[A-Fa-f])\b", re.I),
        group=1,
        confidence=0.90,
        normalizer=_normalize_seat,
    ),
    # Baggage tags: BG20488, BG-55678
    EntityPattern(
        entity_type=ENTITY_BAGGAGE_TAG,
        pattern=re.compile(r"\b(BG[\-]?\d{4,6})\b", re.I),
        group=1,
        confidence=0.93,
    ),
    # Dates: 2024-12-09, 12/09/2024, Dec 9, December 9th
    EntityPattern(
        entity_type=ENTITY_DATE,
        pattern=re.compile(
            r"\b(\d{4}[\-/]\d{1,2}[\-/]\d{1,2})\b"
            r"|\b(\d{1,2}[\-/]\d{1,2}[\-/]\d{4})\b"
            r"|\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s*\d{4})?)\b",
            re.I,
        ),
        group=0,  # Full match across alternations
        confidence=0.88,
        normalizer=_normalize_date,
    ),
    # Intent modifiers — seat preferences
    EntityPattern(
        entity_type=ENTITY_INTENT_MODIFIER,
        pattern=re.compile(r"\b(window|aisle|middle|front\s+row|exit\s+row|extra\s+legroom)\b", re.I),
        group=1,
        confidence=0.90,
        normalizer=lambda v: v.lower().strip(),
    ),
    # Intent modifiers — urgency
    EntityPattern(
        entity_type=ENTITY_INTENT_MODIFIER,
        pattern=re.compile(r"\b(urgent|asap|emergency|immediately|right\s+away|as\s+soon\s+as\s+possible)\b", re.I),
        group=1,
        confidence=0.88,
        normalizer=lambda v: "urgent",
    ),
    # Compensation reasons
    EntityPattern(
        entity_type=ENTITY_COMPENSATION_REASON,
        pattern=re.compile(
            r"\b(delayed?\s+\d+\s+hours?|missed\s+connection|cancelled?\s+flight|"
            r"lost\s+baggage|damaged\s+baggage|overbooked|denied\s+boarding)\b",
            re.I,
        ),
        group=1,
        confidence=0.88,
    ),
]


# ---------------------------------------------------------------------------
# LLM-based fallback extractor
# ---------------------------------------------------------------------------

_LLM_EXTRACTION_PROMPT = """Extract structured entities from this airline customer service message.

Return a JSON array of entities. Each entity has:
- "type": one of "flight_number", "confirmation_number", "seat_number", "airport_code", "airport_name", "date", "passenger_name", "compensation_reason", "baggage_tag", "intent_modifier"
- "value": the extracted value (normalized)
- "confidence": 0.0-1.0

Known airports: CDG=Paris, JFK=New York, AUS=Austin, SFO=San Francisco, LAX=Los Angeles, ORD=Chicago, LHR=London, NRT=Tokyo

If no entities found, return: []

User message: {message}

Respond with ONLY the JSON array."""


async def extract_entities_llm(message: str) -> List[ExtractedEntity]:
    """LLM-based entity extraction for complex messages."""
    import json as _json

    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI()
        response = await client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {"role": "system", "content": "You are a precise entity extractor. Respond with valid JSON only."},
                {"role": "user", "content": _LLM_EXTRACTION_PROMPT.format(message=message)},
            ],
            temperature=0.0,
            max_tokens=300,
        )
        raw = (response.choices[0].message.content or "[]").strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        items = _json.loads(raw)
        if not isinstance(items, list):
            return []

        valid_types = {
            ENTITY_FLIGHT_NUMBER, ENTITY_CONFIRMATION_NUMBER, ENTITY_SEAT_NUMBER,
            ENTITY_AIRPORT_CODE, ENTITY_AIRPORT_NAME, ENTITY_DATE,
            ENTITY_PASSENGER_NAME, ENTITY_COMPENSATION_REASON, ENTITY_BAGGAGE_TAG,
            ENTITY_INTENT_MODIFIER,
        }
        entities = []
        for item in items:
            etype = item.get("type", "")
            if etype not in valid_types:
                continue
            entities.append(ExtractedEntity(
                entity_type=etype,
                value=str(item.get("value", "")),
                raw_text=str(item.get("value", "")),
                confidence=float(item.get("confidence", 0.7)),
                source="llm",
                timestamp=time.time(),
            ))
        return entities
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Core extraction pipeline
# ---------------------------------------------------------------------------

def extract_entities_regex(message: str) -> List[ExtractedEntity]:
    """Fast-path: extract entities using compiled regex patterns."""
    entities: List[ExtractedEntity] = []
    seen: Set[Tuple[str, str]] = set()  # (type, value) dedup

    for ep in _ENTITY_PATTERNS:
        for match in ep.pattern.finditer(message):
            # Get the value from the appropriate capture group
            if ep.group == 0:
                raw_value = match.group(0)
            else:
                raw_value = match.group(ep.group)

            if not raw_value:
                continue

            # Normalize
            value = ep.normalizer(raw_value) if ep.normalizer else raw_value.strip()

            # Deduplicate
            dedup_key = (ep.entity_type, value.upper())
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            # For airport codes, check against known codes
            if ep.entity_type == ENTITY_FLIGHT_NUMBER:
                # Skip if it looks like a pure airport code
                if value.upper() in AIRPORT_CODES:
                    continue

            entities.append(ExtractedEntity(
                entity_type=ep.entity_type,
                value=value,
                raw_text=raw_value,
                confidence=ep.confidence,
                source="regex",
                start=match.start(),
                end=match.end(),
                timestamp=time.time(),
            ))

    # Additional pass: extract airport names/codes from text
    for match in _AIRPORT_CODE_RE.finditer(message):
        code = match.group(1)
        if code.upper() in {v.split("(")[1].rstrip(")") for v in AIRPORT_CODES.values() if "(" in v}:
            dedup_key = (ENTITY_AIRPORT_CODE, code.upper())
            if dedup_key not in seen:
                seen.add(dedup_key)
                canonical = AIRPORT_CODES.get(code.lower(), code.upper())
                entities.append(ExtractedEntity(
                    entity_type=ENTITY_AIRPORT_CODE,
                    value=canonical,
                    raw_text=code,
                    confidence=0.85,
                    source="regex",
                    start=match.start(),
                    end=match.end(),
                    timestamp=time.time(),
                ))

    # Extract airport names from text (case-insensitive)
    message_lower = message.lower()
    for name_key, canonical in AIRPORT_CODES.items():
        if len(name_key) >= 4 and name_key in message_lower:  # Skip 3-letter codes (handled above)
            dedup_key = (ENTITY_AIRPORT_NAME, canonical)
            if dedup_key not in seen:
                seen.add(dedup_key)
                idx = message_lower.index(name_key)
                entities.append(ExtractedEntity(
                    entity_type=ENTITY_AIRPORT_NAME,
                    value=canonical,
                    raw_text=message[idx:idx + len(name_key)],
                    confidence=0.87,
                    source="regex",
                    start=idx,
                    end=idx + len(name_key),
                    timestamp=time.time(),
                ))

    return entities


async def extract_entities(message: str, use_llm_fallback: bool = True) -> EntityExtractionResult:
    """
    Full entity extraction pipeline.

    1. Run regex-based extraction (fast, high-precision)
    2. If few entities found and message is substantive, run LLM extraction
    3. Merge and deduplicate results
    """
    regex_entities = extract_entities_regex(message)

    # If regex found entities with high confidence, return them
    high_conf = [e for e in regex_entities if e.confidence >= 0.85]
    if high_conf and len(message.split()) < 20:
        return EntityExtractionResult(
            entities=regex_entities,
            message=message,
            timestamp=time.time(),
        )

    # For longer messages or when regex found little, try LLM fallback
    if use_llm_fallback and len(message.split()) >= 5:
        llm_entities = await extract_entities_llm(message)
        # Merge: regex results take priority for same (type, value)
        existing_keys: Set[Tuple[str, str]] = {
            (e.entity_type, e.value.upper()) for e in regex_entities
        }
        for entity in llm_entities:
            key = (entity.entity_type, entity.value.upper())
            if key not in existing_keys:
                regex_entities.append(entity)
                existing_keys.add(key)

    return EntityExtractionResult(
        entities=regex_entities,
        message=message,
        timestamp=time.time(),
    )


# ---------------------------------------------------------------------------
# Context hydration from extracted entities
# ---------------------------------------------------------------------------

async def hydrate_context_from_entities(
    entities: List[ExtractedEntity],
    context_state: Any,
) -> Dict[str, Any]:
    """
    Apply extracted entities to the conversation context.
    Returns a dict of fields that were updated.
    """
    changes: Dict[str, Any] = {}

    for entity in entities:
        if entity.confidence < 0.70:
            continue  # Skip low-confidence entities

        if entity.entity_type == ENTITY_FLIGHT_NUMBER:
            if not context_state.flight_number or entity.confidence >= 0.90:
                old = context_state.flight_number
                context_state.flight_number = entity.value
                if old != entity.value:
                    changes["flight_number"] = entity.value

        elif entity.entity_type == ENTITY_CONFIRMATION_NUMBER:
            if not context_state.confirmation_number or entity.confidence >= 0.90:
                old = context_state.confirmation_number
                context_state.confirmation_number = entity.value
                if old != entity.value:
                    changes["confirmation_number"] = entity.value

        elif entity.entity_type == ENTITY_SEAT_NUMBER:
            if not context_state.seat_number or entity.confidence >= 0.85:
                old = context_state.seat_number
                context_state.seat_number = entity.value
                if old != entity.value:
                    changes["seat_number"] = entity.value

        elif entity.entity_type == ENTITY_AIRPORT_NAME:
            # Use airport info to set origin/destination
            if not context_state.origin:
                context_state.origin = entity.value
                changes["origin"] = entity.value
            elif not context_state.destination and entity.value != context_state.origin:
                context_state.destination = entity.value
                changes["destination"] = entity.value

        elif entity.entity_type == ENTITY_AIRPORT_CODE:
            # Same as airport name but with code
            canonical = AIRPORT_CODES.get(entity.value.lower(), entity.value)
            if not context_state.origin:
                context_state.origin = canonical
                changes["origin"] = canonical
            elif not context_state.destination and canonical != context_state.origin:
                context_state.destination = canonical
                changes["destination"] = canonical

        elif entity.entity_type == ENTITY_BAGGAGE_TAG:
            if not context_state.baggage_claim_id:
                context_state.baggage_claim_id = entity.value
                changes["baggage_claim_id"] = entity.value

        elif entity.entity_type == ENTITY_PASSENGER_NAME:
            if not context_state.passenger_name:
                context_state.passenger_name = entity.value
                changes["passenger_name"] = entity.value

    return changes
