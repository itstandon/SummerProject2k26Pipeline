"""
Gate 2: Syntactic Form Validity (SFV).

Lightweight, representation-aware syntax checks for generated test
suites. The goal is to catch malformed output early without requiring a
full parser for every representation family.
"""

import ast
import re

from .config import SFV_THRESHOLD, get_group

_BALANCED_PAIRS = (("(", ")"), ("[", "]"), ("{", "}"))


def _balanced(text: str) -> bool:
    for left, right in _BALANCED_PAIRS:
        if text.count(left) != text.count(right):
            return False
    return True


def _gherkin_sfv(text: str) -> dict:
    feature_count = len(re.findall(r"^\s*Feature\s*:", text, re.MULTILINE))
    scenario_count = len(re.findall(r"^\s*Scenario(?: Outline)?\s*:", text, re.MULTILINE))
    step_count = len(re.findall(r"^\s*(Given|When|Then|And|But)\b", text, re.MULTILINE))
    example_count = len(re.findall(r"^\s*Examples\s*:", text, re.MULTILINE))

    signals = 0
    valid = 0

    if feature_count:
        signals += 1
        valid += 1
    if scenario_count:
        signals += 1
        valid += 1
    if step_count:
        signals += 1
        valid += min(1, step_count / max(1, scenario_count * 3))
    if "Scenario Outline" in text:
        signals += 1
        valid += 1 if example_count else 0
    if _balanced(text):
        signals += 1
        valid += 1

    if signals == 0:
        return {"score": 0.0, "signals": 0, "issues": ["No Gherkin structure detected."]}

    return {
        "score": valid / signals,
        "signals": signals,
        "issues": [] if valid == signals else ["Gherkin structure incomplete."],
    }


def _xunit_sfv(text: str) -> dict:
    issues = []
    try:
        ast.parse(text)
        parsed = True
    except SyntaxError as exc:
        parsed = False
        issues.append(f"Python syntax error: {exc.msg}")

    test_defs = len(re.findall(r"^\s*def\s+test_\w+\s*\(", text, re.MULTILINE))
    class_defs = len(re.findall(r"^\s*class\s+Test\w+", text, re.MULTILINE))
    asserts = len(re.findall(r"^\s*assert\b", text, re.MULTILINE))

    if not test_defs and not class_defs:
        issues.append("No xUnit-style test definitions found.")

    signals = 1 + int(bool(test_defs or class_defs)) + int(asserts > 0)
    valid = 0
    valid += 1 if parsed else 0
    valid += 1 if (test_defs or class_defs) else 0
    valid += 1 if asserts else 0

    return {"score": valid / signals if signals else 0.0, "signals": signals, "issues": issues}


def _table_sfv(text: str) -> dict:
    rows = [line.strip() for line in text.splitlines() if "|" in line]
    if len(rows) < 2:
        return {"score": 0.0, "signals": 0, "issues": ["No table structure detected."]}

    col_counts = [len([cell for cell in row.split("|") if cell.strip()]) for row in rows]
    consistent = len(set(col_counts)) == 1
    separators = any(re.match(r"^\s*\|?\s*:?[- ]{3,}", row) for row in rows)
    signals = 3
    valid = int(consistent) + int(separators) + int(_balanced(text))
    issues = [] if valid == signals else ["Table syntax is inconsistent."]
    return {"score": valid / signals, "signals": signals, "issues": issues}


def _sequence_sfv(text: str) -> dict:
    lowered = text.lower()
    sequence_marker = "sequencediagram" in lowered or "sequence diagram" in lowered
    arrow_lines = len(re.findall(r"->>|-->>|->|-->", text))
    participant_count = len(re.findall(r"^\s*participant\b", text, re.MULTILINE))
    frame_markers = sum(lowered.count(token) for token in ("alt ", "opt ", "loop "))
    end_count = len(re.findall(r"^\s*end\s*$", text, re.MULTILINE))

    signals = 0
    valid = 0
    if sequence_marker:
        signals += 1
        valid += 1
    if arrow_lines:
        signals += 1
        valid += 1
    if participant_count or arrow_lines:
        signals += 1
        valid += 1
    if frame_markers:
        signals += 1
        valid += 1 if end_count >= frame_markers else 0
    if _balanced(text):
        signals += 1
        valid += 1

    if signals == 0:
        return {"score": 0.0, "signals": 0, "issues": ["No sequence-diagram structure detected."]}

    return {
        "score": valid / signals,
        "signals": signals,
        "issues": [] if valid == signals else ["Sequence diagram syntax is incomplete."],
    }


def _rule_sfv(text: str) -> dict:
    rule_keywords = len(re.findall(r"\b(rule|if|then|unless|requires|forbids|must)\b", text, re.IGNORECASE))
    boolean_ops = len(re.findall(r"\b(and|or|not|xor)\b|&&|\|\||!", text, re.IGNORECASE))
    signals = 2 + int(_balanced(text))
    valid = min(1, rule_keywords / 2) + min(1, boolean_ops / 2) + int(_balanced(text))
    return {"score": valid / signals if signals else 0.0, "signals": signals, "issues": [] if valid >= signals else ["Rule syntax is incomplete."]}


def _symbolic_sfv(text: str) -> dict:
    eq_like = len(re.findall(r"[=<>]{1,2}|=>|<=", text))
    matrix_like = len([line for line in text.splitlines() if "|" in line or "," in line])
    signals = 2 + int(_balanced(text))
    valid = min(1, eq_like / 3) + min(1, matrix_like / 2) + int(_balanced(text))
    return {"score": valid / signals if signals else 0.0, "signals": signals, "issues": [] if valid >= signals else ["Symbolic syntax is incomplete."]}


def _generic_sfv(text: str) -> dict:
    structure_hits = sum(
        [
            1 if re.search(r"^\s*#", text, re.MULTILINE) else 0,
            1 if re.search(r"^\s*\d+[\.)]", text, re.MULTILINE) else 0,
            1 if "::" in text or "->" in text or "=>" in text else 0,
            1 if _balanced(text) else 0,
        ]
    )
    score = structure_hits / 4
    issues = [] if structure_hits == 4 else ["Could not fully validate syntax with generic checks."]
    return {"score": score, "signals": 4, "issues": issues}


def evaluate_sfv(test_case_text: str, representation: str, threshold: float = None) -> dict:
    """Return a heuristic SFV score for a generated suite."""
    rep_group = get_group(representation)
    text = test_case_text or ""

    lowered = representation.lower()
    if rep_group == 1 or "gherkin" in lowered or "use case" in lowered or "user story" in lowered:
        result = _gherkin_sfv(text)
    elif rep_group == 2 or any(key in lowered for key in ("state machine", "fsm", "transition system", "petri net", "protocol")):
        result = _generic_sfv(text)
    elif rep_group == 3 or any(key in lowered for key in ("sequence diagram", "interface automata", "temporal logic", "gui event")):
        result = _sequence_sfv(text)
    elif rep_group == 4 or any(key in lowered for key in ("decision table", "cause-effect", "classification tree", "rule-based", "fault tree")):
        result = _table_sfv(text)
    elif rep_group == 5 or any(key in lowered for key in ("xunit", "dsl", "object construction", "five-structure")):
        result = _xunit_sfv(text) if ("def " in text or "assert " in text or "import " in text) else _generic_sfv(text)
    elif rep_group == 6 or any(key in lowered for key in ("concolic", "vector", "symbolic", "contract", "matrix")):
        result = _symbolic_sfv(text)
    else:
        result = _generic_sfv(text)

    sfv_score = round(result["score"], 4)
    sfv_threshold = SFV_THRESHOLD if threshold is None else threshold
    return {
        "representation": representation,
        "representation_group": rep_group,
        "sfv_score": sfv_score,
        "sfv_pass": sfv_score >= sfv_threshold,
        "sfv_threshold": sfv_threshold,
        "signals_checked": result.get("signals", 0),
        "issues": result.get("issues", []),
    }
