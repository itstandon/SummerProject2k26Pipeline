"""
Your generate_testcases.py currently writes ONE file per representation
per requirement (one LLM call's output), which typically contains a
whole suite (multiple Scenarios / test functions / table rows) rather
than a single test case. Gate 4 (SDI) needs to compare test CASES
against each other within that suite, so this module splits a raw
generated file back into individual units, using representation-aware
heuristics with a generic fallback.
"""

import re

from .config import get_group

_SPLIT_PATTERNS = {
    1: re.compile(r"(?=^\s*Scenario(?: Outline)?\s*:)", re.MULTILINE),   # Gherkin
    5: re.compile(r"(?=^\s*def test_\w+)", re.MULTILINE),                 # xUnit
}

_HEADER_SPLIT = re.compile(r"(?=^\s*#{1,4}\s|^\s*\d+[\.\)]\s)", re.MULTILINE)
_BLANK_LINE_SPLIT = re.compile(r"\n\s*\n+")


def split_test_suite(text: str, representation: str) -> list:
    """Returns a list of non-empty test-case strings."""
    if not text or not text.strip():
        return []

    group = get_group(representation)
    pattern = _SPLIT_PATTERNS.get(group)

    chunks = []
    if pattern:
        chunks = [c.strip() for c in pattern.split(text) if c.strip()]
        # re.split's lookahead puts any preamble before the first match
        # (e.g. a Gherkin "Feature:" header) into its own leading chunk.
        # That's not a test case, so drop it when there's more than one chunk.
        if len(chunks) > 1 and not pattern.match(chunks[0]):
            chunks = chunks[1:]

    if len(chunks) <= 1:
        chunks = [c.strip() for c in _HEADER_SPLIT.split(text) if c.strip()]

    if len(chunks) <= 1:
        chunks = [c.strip() for c in _BLANK_LINE_SPLIT.split(text) if c.strip()]

    if len(chunks) <= 1:
        # Nothing splittable – treat the whole file as a single case.
        chunks = [text.strip()]

    return chunks
