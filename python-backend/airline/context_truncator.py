"""Conversation context truncation with boundary-preserving summaries."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class Turn:
    role: str
    content: str
    important: bool = False


def truncate_turns(turns: Iterable[Turn], max_chars: int) -> list[Turn]:
    turns = list(turns)
    kept: list[Turn] = []
    budget = max_chars
    for turn in reversed(turns):
        cost = len(turn.role) + len(turn.content)
        if turn.important or cost <= budget:
            kept.append(turn)
            if not turn.important:
                budget -= cost
    kept.reverse()
    if len(kept) != len(turns):
        omitted = len(turns) - len(kept)
        kept.insert(0, Turn("system", f"{omitted} earlier turns omitted; preserve unresolved user commitments.", True))
    return kept


def validate_rewrite(original: str, rewritten: str, required_terms: Iterable[str]) -> list[str]:
    errors = []
    if not rewritten.strip():
        errors.append("rewritten text is empty")
    for term in required_terms:
        if term and term not in rewritten:
            errors.append(f"missing required term: {term}")
    if len(rewritten) > len(original) * 2 + 200:
        errors.append("rewrite expanded beyond safe bound")
    return errors
