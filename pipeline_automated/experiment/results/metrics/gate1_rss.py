"""
Gate 1: Representation Suitability Score (RSS).

Heuristic evaluator for the representation-selection phase. It scores
whether the chosen representation matches the requirement's dominant
concern, abstraction level, complexity, and generation feasibility.
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


def _score_expanded_metrics(rep_group: int, safety_critical: bool) -> dict:
    scores = {
        "m5": {1: 0.20, 2: 0.45, 3: 0.40, 4: 0.60, 5: 1.00, 6: 0.80}.get(rep_group, 0.50),
        "m6": {1: 0.80, 2: 0.55, 3: 0.50, 4: 1.00, 5: 0.70, 6: 0.85}.get(rep_group, 0.50),
        "m7": {1: 0.90, 2: 0.80, 3: 0.70, 4: 0.85, 5: 0.65, 6: 0.40}.get(rep_group, 0.60),
        "m8": {1: 0.85, 2: 0.65, 3: 0.55, 4: 0.80, 5: 0.60, 6: 0.45}.get(rep_group, 0.55),
        "m9": {1: 0.30, 2: 0.70, 3: 0.60, 4: 0.40, 5: 0.95, 6: 0.90}.get(rep_group, 0.50),
        "m10": {1: 0.50, 2: 0.95, 3: 0.90, 4: 0.70, 5: 0.65, 6: 0.85}.get(rep_group, 0.50),
    }
    if not safety_critical:
        scores["m10"] = min(scores["m10"], 0.65)
    return scores


def evaluate_rss(req_text: str, representation: str, weights: dict = None, system_type: str = None) -> dict:
    """Return a heuristic RSS score for a requirement/representation pair."""
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

    # All profiles map m1-m10. We get the scores and filter by system profile weights.
    extra = _score_expanded_metrics(rep_group, profile["safety_critical"])
    metric_values = {
        "m1": alignment,
        "m2": abstraction,
        "m3": occam,
        "m4": feasibility,
        **extra,
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
        "rss_score": round(rss_score, 4),
        "rss_pass": rss_score >= RSS_THRESHOLD,
        "rss_threshold": RSS_THRESHOLD,
    }
