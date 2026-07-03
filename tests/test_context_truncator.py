import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python-backend"))

from airline.context_truncator import Turn, truncate_turns, validate_rewrite


def test_truncator_keeps_important_turn_and_adds_notice():
    turns = [Turn("user", "a" * 50), Turn("assistant", "commitment", True), Turn("user", "b" * 50)]
    kept = truncate_turns(turns, 10)
    assert kept[0].role == "system"
    assert any(t.content == "commitment" for t in kept)


def test_rewrite_validator_checks_required_terms():
    assert validate_rewrite("hello order", "hello", ["order"]) == ["missing required term: order"]
