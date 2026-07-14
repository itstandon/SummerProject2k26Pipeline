"""
Gate 4: Suite Diversity Index (SDI).

    SDI = wd * (1 - RR) + we * CE_norm

Runs AFTER a suite has passed Gate 3 (FSA). Evaluates the suite as a
whole: are the individual test cases meaningfully different from each
other, and do they spread across the equivalence classes the
representation actually defines (not just pass each clause once each
via near-duplicate scenarios)?
"""

import math
from collections import Counter
from itertools import combinations

from .config import get_similarity_method, DEFAULT_SDI_WEIGHTS, SIMILARITY_TAU, SDI_THRESHOLD
from .similarity import similarity

_CLASS_KEYWORDS = {
    "exception": ["invalid", "error", "exception", "fail", "reject", "unauthorized", "denied"],
    "boundary": ["boundary", "edge", "max", "min", "limit", "overflow", "underflow", "threshold"],
    "alternative": ["alt", "alternative", "fallback", "retry"],
}


def heuristic_classify(test_case_text: str) -> str:
    """Cheap, LLM-free equivalence-class tagger used when no LLM2
    equivalence_class labels were already produced during FSA scoring.
    Prefer passing labels from fsa.py's evaluate_fsa() output when
    available – this is a fallback, not the primary classifier."""
    text_lower = (test_case_text or "").lower()
    for label, keywords in _CLASS_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return label
    return "happy"


def redundancy_rate(test_cases: list, representation: str, tau: float = SIMILARITY_TAU) -> dict:
    n = len(test_cases)
    if n < 2:
        return {"redundancy_rate": 0.0, "redundant_pairs": 0, "total_pairs": 0, "pairs_detail": []}

    method = get_similarity_method(representation)
    redundant_pairs = 0
    total_pairs = 0
    detail = []

    for i, j in combinations(range(n), 2):
        sim = similarity(test_cases[i], test_cases[j], method)
        total_pairs += 1
        is_redundant = sim > tau
        if is_redundant:
            redundant_pairs += 1
        detail.append({"i": i, "j": j, "similarity": round(sim, 4), "redundant": is_redundant})

    rr = redundant_pairs / total_pairs if total_pairs else 0.0
    return {
        "redundancy_rate": rr,
        "redundant_pairs": redundant_pairs,
        "total_pairs": total_pairs,
        "similarity_method": method,
        "tau": tau,
        "pairs_detail": detail,
    }


def coverage_entropy(classes: list, num_defined_classes: int = None) -> dict:
    """
    classes: equivalence-class label per test case (from LLM2's
    equivalence_class field, or heuristic_classify as fallback).
    num_defined_classes (k): total classes the representation defines
    for this requirement (e.g. number of decision-table rows, number
    of FSM transitions). Defaults to the number of DISTINCT classes
    observed if not supplied – note this under-counts if the suite
    never touched some classes at all; pass k explicitly when you know
    it (e.g. from your representation-selection output) for an
    accurate score.
    """
    n = len(classes)
    if n == 0:
        return {"coverage_entropy": 0.0, "class_counts": {}, "k": 0}

    counts = Counter(classes)
    k = num_defined_classes or len(counts)
    if k <= 1:
        return {"coverage_entropy": 1.0, "class_counts": dict(counts), "k": k}

    probs = [c / n for c in counts.values()]
    raw_entropy = -sum(p * math.log2(p) for p in probs if p > 0)
    ce_norm = raw_entropy / math.log2(k)
    ce_norm = min(1.0, ce_norm)  # guard float overshoot when k < distinct classes observed

    return {"coverage_entropy": ce_norm, "class_counts": dict(counts), "k": k}


def compute_sdi(test_cases: list, representation: str,
                 equivalence_classes: list = None,
                 num_defined_classes: int = None,
                 weights: dict = None, tau: float = SIMILARITY_TAU) -> dict:
    """
    test_cases: list of individual test-case strings (use
        metrics.splitter.split_test_suite() to produce these from a
        raw generated file).
    equivalence_classes: optional pre-computed labels (e.g. reused
        from fsa.py's LLM2 call, one per test case, same order as
        test_cases). If omitted, falls back to heuristic_classify.
    """
    w = weights or DEFAULT_SDI_WEIGHTS

    rr_result = redundancy_rate(test_cases, representation, tau=tau)

    classes = equivalence_classes or [heuristic_classify(t) for t in test_cases]
    ce_result = coverage_entropy(classes, num_defined_classes)

    sdi_score = (w["wd"] * (1 - rr_result["redundancy_rate"])) + (w["we"] * ce_result["coverage_entropy"])

    return {
        "representation": representation,
        "num_test_cases": len(test_cases),
        "redundancy": rr_result,
        "coverage_entropy": ce_result,
        "weights_used": w,
        "sdi_score": round(sdi_score, 4),
        "sdi_pass": sdi_score >= SDI_THRESHOLD,
        "sdi_threshold": SDI_THRESHOLD,
    }
