"""
Requirement Groundedness (Mg) – metrics.md's new Gate 3 sub-metric.

Mg = 1 - H / A
  A = total concrete elements asserted in the test case
  H = number of those elements that are hallucinated (unsupported or
      contradicted by the SRS text)

The heavy lifting (NLI-style entailment check of each concrete element
against the SRS) is delegated to the evaluator LLM (LLM2) inside
fsa.py's single evaluation call, since that call already has the SRS
and the test case in context. This module holds:

  1. The pure scoring formula (compute_mg), so it can be unit-tested /
     reused independently of any LLM call.
  2. A regex-based fallback extractor (extract_concrete_elements_regex)
     for representations/pipelines that want a cheap, LLM-free first
     pass, or want to sanity-check what LLM2 found.
"""

import re

NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?%?")
ENUM_STATE_RE = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")            # e.g. READY, FAULT, HTTP_OK
STATUS_CODE_RE = re.compile(r"\b[1-5]\d{2}\b")                    # e.g. 200, 404
FIELD_VALUE_RE = re.compile(r'"[^"]{1,40}"|\'[^\']{1,40}\'')       # quoted literals


def compute_mg(concrete_elements: list) -> float:
    """
    concrete_elements: list of dicts like
        {"value": "READY", "context": "...", "grounded": True/False}
    Elements with grounded == "uncertain" are treated as NOT counted
    against the score (benefit of the doubt goes to neither side is
    wrong; we simply exclude them from A and H so an evaluator's
    uncertainty doesn't tank or inflate the score).

    Returns Mg in [0, 1]. If there are no concrete elements at all
    (A == 0), the test case makes no falsifiable claims, so Mg = 1.0
    (vacuously grounded).
    """
    if not concrete_elements:
        return 1.0

    counted = [e for e in concrete_elements if e.get("grounded") in (True, False)]
    a_total = len(counted)
    if a_total == 0:
        return 1.0

    h_hallucinated = sum(1 for e in counted if e.get("grounded") is False)
    return max(0.0, 1.0 - (h_hallucinated / a_total))


def extract_concrete_elements_regex(test_text: str) -> list:
    """
    Cheap, LLM-free extraction of candidate concrete elements: numeric
    literals, ALL_CAPS enum/state-like tokens, HTTP-ish status codes,
    and quoted field values. Returns a list of {"value": ..., "context": ...}
    with no "grounded" verdict filled in – pair this with your own
    grounding check, or use it only as a sanity cross-check against
    LLM2's extraction in fsa.py.
    """
    elements = []
    seen = set()

    def add(match_iter, kind):
        for m in match_iter:
            val = m.group(0)
            key = (kind, val)
            if key in seen:
                continue
            seen.add(key)
            start = max(0, m.start() - 30)
            end = min(len(test_text), m.end() + 30)
            elements.append({
                "value": val,
                "kind": kind,
                "context": test_text[start:end].replace("\n", " ").strip(),
            })

    add(STATUS_CODE_RE.finditer(test_text), "status_code")
    add(ENUM_STATE_RE.finditer(test_text), "enum_or_state")
    add(FIELD_VALUE_RE.finditer(test_text), "field_value")
    add(NUMBER_RE.finditer(test_text), "numeric_literal")

    return elements
