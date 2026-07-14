"""
Gate 1: Representation Suitability Score (RSS).

Heuristic evaluator for the representation-selection phase. It scores
whether the chosen representation matches the requirement's dominant
concern, abstraction level, complexity, and generation feasibility.

Metrics m1-m10 correspond directly to the ten Suitability Metrics defined
in metrics.md, section "Detailed Suitability Metrics (M1 to M10) Explained":
    m1  Concern Alignment
    m2  Abstraction Level Alignment
    m3  Occam's Razor
    m4  LLM Generation Feasibility
    m5  Oracle Executability Index
    m6  Traceability Density
    m7  Cognitive Auditability
    m8  Change Fragility
    m9  Mutation Support
    m10 Standards & Compliance Fit
"""

import re

from .config import RSS_WEIGHT_PROFILES, RSS_THRESHOLD, get_group, is_sparse_concrete_rep, infer_system_type

_STATE_CUES = re.compile(
    r"\b(start|startup|shutdown|state|transition|ready|fault|mode|lifecycle|activate|deactivate|on|off)\b",
    re.IGNORECASE,
)
_CONCURRENCY_CUES = re.compile(
    r"\b(concurrent|concurrency|parallel|race|deadlock|lock|mutex|semaphore|thread|interleave|timing|ordering)\b",
    re.IGNORECASE,
)
_LOGIC_CUES = re.compile(
    r"\b(if|then|else|unless|rule|constraint|condition|permission|privilege|access|allowed|denied|must)\b",
    re.IGNORECASE,
)
_HIGH_ABS_CUES = re.compile(r"\b(user|stakeholder|goal|story|scenario|business|workflow|outcome)\b", re.IGNORECASE)
_LOW_ABS_CUES = re.compile(
    r"\b(api|endpoint|function|method|class|payload|request|response|database|memory|code|parameter)\b",
    re.IGNORECASE,
)
_SAFETY_CUES = re.compile(
    r"\b(safety|critical|hazard|fault|fail-safe|iso 26262|do-178c|medical|automotive|aerospace)\b",
    re.IGNORECASE,
)

# New cues for the expanded profiles
_DATA_PIPELINE_CUES = re.compile(
    r"\b(data|pipeline|etl|dataset|transform|stream|input vector|distribution|matrix|features|batch)\b",
    re.IGNORECASE,
)
_INTERACTION_CUES = re.compile(
    r"\b(gui|click|press|display|screen|ux|ui|interaction|event graph|button|input|user interface)\b",
    re.IGNORECASE,
)
_PROTOTYPING_CUES = re.compile(
    r"\b(prototype|draft|concept|mvp|mock|rapid|fast-track)\b",
    re.IGNORECASE,
)

_CONCERN_ALIGNMENT = {
    "state":            {1: 0.45, 2: 1.00, 3: 0.80, 4: 0.50, 5: 0.55, 6: 0.60},
    "concurrency":      {1: 0.45, 2: 0.85, 3: 1.00, 4: 0.50, 5: 0.55, 6: 0.75},
    "logic":            {1: 0.70, 2: 0.50, 3: 0.50, 4: 1.00, 5: 0.60, 6: 0.90},
    "high_abstraction": {1: 1.00, 2: 0.50, 3: 0.55, 4: 0.75, 5: 0.45, 6: 0.45},
    "low_abstraction":  {1: 0.45, 2: 0.75, 3: 0.70, 4: 0.60, 5: 1.00, 6: 0.90},
    "formal":           {1: 0.45, 2: 0.80, 3: 0.85, 4: 0.55, 5: 0.65, 6: 1.00},
}

_ABSTRACTION_LEVEL = {1: 1.00, 2: 0.65, 3: 0.55, 4: 0.80, 5: 0.20, 6: 0.30}
_REP_COMPLEXITY = {1: 0.25, 2: 0.60, 3: 0.70, 4: 0.50, 5: 0.80, 6: 0.90}
_LLM_FEASIBILITY = {1: 0.95, 2: 0.75, 3: 0.70, 4: 0.90, 5: 0.85, 6: 0.45}

# ---------------------------------------------------------------------------
# m5-m10: expanded metrics, one named table per metrics.md definition.
# Each table is keyed by representation group (1-6, see config.py) and
# reflects that group's typical characteristics per the doc's own examples
# (e.g. doc says "xUnit = 1.0 Oracle Executability" -> group 5 = 1.00 here).
# ---------------------------------------------------------------------------

# M5 - Oracle Executability Index: can a test runner execute the assertions
# automatically, or does it need adapter code / a human in the loop?
# Doc: xUnit/API contracts = 1.0, Gherkin (needs step defs) = 0.5,
#      purely descriptive text (use cases, goal diagrams) = 0.0.
_ORACLE_EXECUTABILITY = {1: 0.20, 2: 0.45, 3: 0.40, 4: 0.60, 5: 1.00, 6: 0.80}

# M6 - Traceability Density: how directly does each test map back to a
# specific requirement clause?
# Doc: direct 1-to-1 linkage (Test Requirement Matrix) = 1.0,
#      lumped data with no clear linkage (Feature Vectors) = 0.2.
_TRACEABILITY_DENSITY = {1: 0.80, 2: 0.55, 3: 0.50, 4: 1.00, 5: 0.70, 6: 0.85}

# M7 - Cognitive Auditability: can a human reviewer read the test and tell
# if it's correct (i.e. catch an LLM hallucination) at a glance?
# Doc: Gherkin / decision tables = 1.0, symbolic equations / raw matrices = 0.2.
_COGNITIVE_AUDITABILITY = {1: 0.90, 2: 0.80, 3: 0.70, 4: 0.85, 5: 0.65, 6: 0.40}

# M8 - Change Fragility: does a small requirement tweak require a localized
# edit, or does it break the whole model?
# Doc: localized edits (adding a Decision Table row) = 1.0 (robust),
#      minor changes break the entire structure = 0.2 (fragile).
_CHANGE_FRAGILITY = {1: 0.85, 2: 0.65, 3: 0.55, 4: 0.80, 5: 0.60, 6: 0.45}

# M9 - Mutation Support: can the representation undergo automated fault
# injection to prove the test suite actually catches bugs?
# Doc: supports automatic code mutation (xUnit, DSLs) = 1.0,
#      plain text or diagrams with no automated execution = 0.0.
_MUTATION_SUPPORT = {1: 0.30, 2: 0.70, 3: 0.60, 4: 0.40, 5: 0.95, 6: 0.90}

# M10 - Standards & Compliance Fit: is this an officially recognized formal
# model for the target safety-certification level (ISO 26262, DO-178C)?
# Doc: officially recognized formal model = 1.0, vague/unapproved = 0.0.
# This metric is only meaningful when the system is actually safety-critical
# -- see the cap applied in _score_standards_compliance below.
_STANDARDS_COMPLIANCE = {1: 0.50, 2: 0.95, 3: 0.90, 4: 0.70, 5: 0.65, 6: 0.85}

# Cap applied to M10 for non-safety-critical systems: standards compliance
# shouldn't meaningfully reward/penalize a representation choice unless the
# requirement is actually flagged safety-critical.
_M10_NON_SAFETY_CAP = 0.65


def _hit_count(pattern: re.Pattern, text: str) -> int:
    return len(pattern.findall(text or ""))


def _infer_requirement_profile(req_text: str) -> dict:
    text = req_text or ""

    concern_scores = {
        "state": _hit_count(_STATE_CUES, text),
        "concurrency": _hit_count(_CONCURRENCY_CUES, text),
        "logic": _hit_count(_LOGIC_CUES, text),
        "high_abstraction": _hit_count(_HIGH_ABS_CUES, text),
        "low_abstraction": _hit_count(_LOW_ABS_CUES, text),
    }
    dominant_concern = max(concern_scores, key=concern_scores.get)
    if concern_scores[dominant_concern] == 0:
        dominant_concern = "high_abstraction"

    complexity_signals = sum(
        [
            _hit_count(_STATE_CUES, text),
            _hit_count(_CONCURRENCY_CUES, text),
            _hit_count(_LOGIC_CUES, text),
            text.count(" and "),
            text.count(" or "),
            text.count(" unless "),
        ]
    )
    complexity = min(1.0, 0.15 + (complexity_signals * 0.10))

    abstraction_signal = _hit_count(_LOW_ABS_CUES, text) - _hit_count(_HIGH_ABS_CUES, text)
    if abstraction_signal > 1:
        abstraction_target = "low_abstraction"
    elif abstraction_signal < -1:
        abstraction_target = "high_abstraction"
    elif _hit_count(_STATE_CUES, text) or _hit_count(_CONCURRENCY_CUES, text):
        abstraction_target = "formal"
    else:
        abstraction_target = "high_abstraction"

    return {
        "dominant_concern": dominant_concern,
        "abstraction_target": abstraction_target,
        "complexity": complexity,
        "safety_critical": bool(_SAFETY_CUES.search(text)),
        "data_pipeline": bool(_DATA_PIPELINE_CUES.search(text)),
        "distributed_concurrent": bool(_CONCURRENCY_CUES.search(text)),
        "interaction_heavy": bool(_INTERACTION_CUES.search(text)),
        "rapid_prototyping": bool(_PROTOTYPING_CUES.search(text)),
        "concern_scores": concern_scores,
    }


def _score_occam(req_complexity: float, rep_group: int) -> float:
    rep_complexity = _REP_COMPLEXITY.get(rep_group, 0.50)
    return max(0.0, 1.0 - abs(req_complexity - rep_complexity))


def _score_abstraction(rep_group: int, abstraction_target: str) -> float:
    rep_level = _ABSTRACTION_LEVEL.get(rep_group, 0.50)
    target_level = {
        "high_abstraction": 1.00,
        "formal": 0.80,
        "low_abstraction": 0.20,
    }.get(abstraction_target, 0.75)
    return max(0.0, 1.0 - abs(rep_level - target_level))


def _score_oracle_executability(rep_group: int) -> float:
    """M5: how directly the representation's output can be run by a test
    runner without a human writing adapter code first."""
    return _ORACLE_EXECUTABILITY.get(rep_group, 0.50)


def _score_traceability_density(rep_group: int) -> float:
    """M6: how cleanly each generated test maps back to a specific
    requirement clause."""
    return _TRACEABILITY_DENSITY.get(rep_group, 0.50)


def _score_cognitive_auditability(rep_group: int) -> float:
    """M7: how easily a human reviewer can read the test and catch an
    LLM hallucination or mistake."""
    return _COGNITIVE_AUDITABILITY.get(rep_group, 0.60)


def _score_change_fragility(rep_group: int) -> float:
    """M8: how well the representation absorbs small requirement edits
    without needing a full model rewrite."""
    return _CHANGE_FRAGILITY.get(rep_group, 0.55)


def _score_mutation_support(rep_group: int) -> float:
    """M9: whether the representation can undergo automated fault
    injection (mutation testing) to prove the suite's strength."""
    return _MUTATION_SUPPORT.get(rep_group, 0.50)


def _score_standards_compliance(rep_group: int, safety_critical: bool) -> float:
    """M10: alignment with formal safety-certification modeling standards
    (ISO 26262, DO-178C). Only meaningfully rewarded when the requirement
    is actually flagged safety-critical -- otherwise capped, per metrics.md's
    guidance that this metric matters specifically for safety-critical systems."""
    score = _STANDARDS_COMPLIANCE.get(rep_group, 0.55)
    if not safety_critical:
        score = min(score, _M10_NON_SAFETY_CAP)
    return score


def _score_expanded_metrics(rep_group: int, safety_critical: bool) -> dict:
    """Compute m5-m10 as a coherent group, one function per metrics.md
    definition. Returns keys m5..m10 for direct use in metric_values."""
    return {
        "m5": _score_oracle_executability(rep_group),
        "m6": _score_traceability_density(rep_group),
        "m7": _score_cognitive_auditability(rep_group),
        "m8": _score_change_fragility(rep_group),
        "m9": _score_mutation_support(rep_group),
        "m10": _score_standards_compliance(rep_group, safety_critical),
    }


def evaluate_rss(req_text: str, representation: str, weights: dict = None, system_type: str = None) -> dict:
    """Return a heuristic RSS score for a requirement/representation pair.

    metric_values always contains all ten metrics (m1-m10), computed the
    same way regardless of system_type. Which of them actually influence
    rss_score depends entirely on the active weight profile (see
    RSS_WEIGHT_PROFILES in config.py) -- e.g. "standard" zeroes out m5-m10,
    "safety_critical" spreads weight across all ten per metrics.md.
    """
    rep_group = get_group(representation)
    profile = _infer_requirement_profile(req_text)

    # Determine system type dynamically if not provided
    if not system_type:
        system_type = infer_system_type(req_text)

    concern = profile["dominant_concern"]
    alignment = _CONCERN_ALIGNMENT.get(concern, {}).get(rep_group, 0.40)
    abstraction = _score_abstraction(rep_group, profile["abstraction_target"])
    occam = _score_occam(profile["complexity"], rep_group)
    feasibility = _LLM_FEASIBILITY.get(rep_group, 0.50)
    if profile["complexity"] > 0.65:
        feasibility = max(0.0, feasibility - 0.10)
    if is_sparse_concrete_rep(representation):
        feasibility = min(1.0, feasibility + 0.05)

    # All ten metrics computed every time; weight profile decides which count.
    expanded = _score_expanded_metrics(rep_group, profile["safety_critical"])
    metric_values = {
        "m1": alignment,
        "m2": abstraction,
        "m3": occam,
        "m4": feasibility,
        **expanded,
    }

    score_weights = dict(RSS_WEIGHT_PROFILES.get(system_type, RSS_WEIGHT_PROFILES["standard"]))
    if weights:
        score_weights.update(weights)

    rss_score = sum(score_weights[key] * metric_values[key] for key in score_weights)

    return {
        "representation": representation,
        "representation_group": rep_group,
        "requirement_profile": profile,
        "weights_used": score_weights,
        "metrics": metric_values,
        "rss_mode": system_type,
        "system_type": system_type,
        "rss_score": round(rss_score, 4),
        "rss_pass": rss_score >= RSS_THRESHOLD,
        "rss_threshold": RSS_THRESHOLD,
    }