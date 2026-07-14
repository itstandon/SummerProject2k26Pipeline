"""
Gate 3: Functional Semantic Adequacy (FSA), extended with the
Requirement Groundedness sub-metric (Mg).

    FSA = wc*CC + wn*NC + wo*OA + wb*BC + wg*Mg

This module drives a single LLM2 ("SOTA evaluator") call per test
case/suite that returns Clause Coverage, Negative Coverage, Oracle
Assertiveness, Boundary Coverage, the raw concrete-element list (for
Mg), and an equivalence-class tag (reused later by Gate 4's Coverage
Entropy). One call instead of five keeps this affordable per your
existing token_tracker usage pattern.
"""

import json
import os
import re

from .config import get_fsa_weights, FSA_THRESHOLD, infer_system_type, get_sufficiency_checklist
from .groundedness import compute_mg

PROMPT_PATH_DEFAULT = "prompts/fsa_evaluate.txt"


def _load_prompt(prompt_path: str) -> str:
    # Look in the correct location relative to config path / pipeline automated experiment
    # Check if absolute, if not make it relative to parent of results/metrics package root
    if not os.path.isabs(prompt_path):
        metrics_root = os.path.dirname(os.path.abspath(__file__))
        exp_root = os.path.dirname(os.path.dirname(metrics_root))
        candidate = os.path.join(exp_root, prompt_path)
        if os.path.exists(candidate):
            prompt_path = candidate
    with open(prompt_path) as f:
        return f.read()


def _parse_json_loose(raw: str) -> dict:
    """Same tolerant-parsing approach used elsewhere in this pipeline
    (generate_testcases.py): find the JSON object, strip trailing
    commas, and fall back gracefully rather than crashing the run."""
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        raise ValueError("No JSON object found in evaluator output.")
    candidate = match.group(0)
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
        return json.loads(candidate)


def evaluate_fsa(req_text: str, representation: str, test_case_text: str,
                  call_llm_fn, model: str, log_usage_fn=None,
                  prompt_path: str = PROMPT_PATH_DEFAULT,
                  weights: dict = None, extra_log: dict = None,
                  system_type: str = None) -> dict:
    """
    Runs the LLM2 evaluation for one generated test case / suite and
    returns a full scoring breakdown.

    call_llm_fn: pass your existing call_llm(prompt, model) -> (result, usage)
    log_usage_fn: pass your existing log_usage(stage, usage, extra) or None to skip.
    """
    checklist = get_sufficiency_checklist(representation)
    template = _load_prompt(prompt_path)
    prompt = (template
              .replace("{REP}", representation)
              .replace("{REQ}", req_text)
              .replace("{TESTCASE}", test_case_text)
              .replace("{SUFFICIENCY_CRITERIA}", checklist))

    result = call_llm_fn(prompt, model)

    if log_usage_fn:
        log_usage_fn("fsa_groundedness_eval", {}, extra=extra_log or {})

    try:
        parsed = _parse_json_loose(result)
    except (ValueError, json.JSONDecodeError) as e:
        return {
            "error": f"Could not parse evaluator output: {e}",
            "raw_output": result,
        }

    cc = float(parsed.get("clause_coverage", 0.0))
    nc = float(parsed.get("negative_coverage", 0.0))
    oa = float(parsed.get("oracle_assertiveness", 0.0))
    bc = float(parsed.get("boundary_coverage", 0.0))
    concrete_elements = parsed.get("concrete_elements", []) or []
    equivalence_class = parsed.get("equivalence_class", "other")

    mg = compute_mg(concrete_elements)

    resolved_system_type = system_type or infer_system_type(req_text)
    w = weights or get_fsa_weights(representation, resolved_system_type)
    fsa_score = (w["wc"] * cc) + (w["wn"] * nc) + (w["wo"] * oa) + (w["wb"] * bc) + (w["wg"] * mg)

    return {
        "representation": representation,
        "system_type": resolved_system_type,
        "weights_used": w,
        "clause_coverage": cc,
        "negative_coverage": nc,
        "oracle_assertiveness": oa,
        "boundary_coverage": bc,
        "groundedness_mg": mg,
        "concrete_elements": concrete_elements,
        "hallucinated_count": sum(1 for e in concrete_elements if e.get("grounded") is False),
        "total_concrete_elements": len(concrete_elements),
        "equivalence_class": equivalence_class,
        "fsa_score": round(fsa_score, 4),
        "fsa_pass": fsa_score >= FSA_THRESHOLD,
        "fsa_threshold": FSA_THRESHOLD,
    }
