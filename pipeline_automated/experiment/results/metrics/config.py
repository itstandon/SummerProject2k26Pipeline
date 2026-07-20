"""
Central configuration for the Gate 3 (FSA + Groundedness) and Gate 4 (SDI)
metrics, derived from metrics.md.

Everything that varies "per representation" lives here so the scoring code
in fsa.py / diversity.py stays generic.
"""

# ---------------------------------------------------------------------------
# The 30 representations, grouped exactly as in metrics.md's SDI similarity
# table and RSS matrix. Names are matched case-insensitively and via
# substring, so "FSM" or "Finite State Machines (FSM)" both resolve.
# ---------------------------------------------------------------------------

REPRESENTATION_GROUPS = {
    # Group 1: Scenario / Behavioral
    "gherkin": 1,
    "use cases": 1,
    "user stories": 1,
    "kaos": 1,
    "goal-oriented": 1,
    "category partition": 1,

    # Group 2: Stateful / Transitions
    "transition systems": 2,
    "finite state machine": 2,
    "fsm": 2,
    "protocol state machine": 2,
    "fsm path": 2,
    "w method": 2,
    "petri net": 2,

    # Group 3: Concurrency / Interaction
    "sequence diagram": 3,
    "interface automata": 3,
    "gui event graph": 3,
    "temporal logic": 3,
    "ltl": 3,
    "ctl": 3,

    # Group 4: Logical / Rules
    "decision table": 4,
    "cause-effect": 4,
    "cause effect": 4,
    "classification tree": 4,
    "ctm": 4,
    "rule-based": 4,
    "rule based": 4,
    "fault tree": 4,

    # Group 5: Programmatic / Code
    "xunit": 5,
    "structured dsl": 5,
    "structural dsl": 5,
    "domain-specific dsl": 5,
    "object construction graph": 5,
    "ocg": 5,
    "five-structure": 5,

    # Group 6: Math / Symbolic / Contracts
    "concolic": 6,
    "canonical vector space": 6,
    "symbolic path condition": 6,
    "feature vector": 6,
    "test requirement matrix": 6,
    "consumer-driven contract": 6,
    "cdc": 6,
}

# Representations where concrete literal values are sparse by nature -> Mg's
# weight collapses toward 0 and is redistributed to Clause Coverage (wc),
# per metrics.md's note on KAOS / User Stories.
SPARSE_CONCRETE_VALUE_REPS = {"kaos", "goal-oriented", "user stories", "use cases"}


def normalize_rep_name(name: str) -> str:
    return (name or "").strip().lower()


def get_group(representation: str) -> int:
    key = normalize_rep_name(representation)
    for pattern, group in REPRESENTATION_GROUPS.items():
        if pattern in key:
            return group
    return 1  # default: treat unknown reps as text-like scenario descriptions


def is_sparse_concrete_rep(representation: str) -> bool:
    key = normalize_rep_name(representation)
    return any(p in key for p in SPARSE_CONCRETE_VALUE_REPS)


# ---------------------------------------------------------------------------
# Gate 1: RSS weights and threshold
# ---------------------------------------------------------------------------
DEFAULT_RSS_WEIGHTS = {
    "m1": 0.40,  # Concern Alignment
    "m2": 0.30,  # Abstraction Level Alignment
    "m3": 0.15,  # Occam's Razor
    "m4": 0.15,  # LLM Generation Feasibility
}

RSS_THRESHOLD = 0.60

# New system-type profiles for Gate 1 (RSS) suitability checking
RSS_WEIGHT_PROFILES = {
    "standard": {
        "m1": 0.40, "m2": 0.30, "m3": 0.15, "m4": 0.15,
        "m5": 0.00, "m6": 0.00, "m7": 0.00, "m8": 0.00, "m9": 0.00, "m10": 0.00
    },
    "safety_critical": {
        "m1": 0.25, "m2": 0.15, "m3": 0.10, "m4": 0.10,
        "m5": 0.10, "m6": 0.10, "m7": 0.05, "m8": 0.05, "m9": 0.05, "m10": 0.05
    },
    "rapid_prototyping": {
        "m1": 0.15, "m2": 0.10, "m3": 0.10, "m4": 0.25,
        "m5": 0.05, "m6": 0.10, "m7": 0.20, "m8": 0.05, "m9": 0.00, "m10": 0.00
    },
    "data_pipeline": {
        "m1": 0.30, "m2": 0.15, "m3": 0.10, "m4": 0.10,
        "m5": 0.10, "m6": 0.10, "m7": 0.05, "m8": 0.05, "m9": 0.05, "m10": 0.00
    },
    "distributed_concurrent": {
        "m1": 0.35, "m2": 0.15, "m3": 0.05, "m4": 0.10,
        "m5": 0.10, "m6": 0.10, "m7": 0.05, "m8": 0.05, "m9": 0.05, "m10": 0.00
    },
    "interaction_heavy": {
        "m1": 0.20, "m2": 0.15, "m3": 0.10, "m4": 0.10,
        "m5": 0.05, "m6": 0.15, "m7": 0.20, "m8": 0.05, "m9": 0.00, "m10": 0.00
    }
}

# ---------------------------------------------------------------------------
# Gate 2: Syntactic Form Validity
# ---------------------------------------------------------------------------
SFV_THRESHOLD = 0.60

# ---------------------------------------------------------------------------
# Gate 3: FSA weight profiles (sums to 1.0) and system type mapping
# ---------------------------------------------------------------------------
# Justifications for each weight profile:
# - safety_critical: Higher negative (0.25), boundary (0.20), and oracle (0.20) because
#   failures in safety paths or fuzzy assertions cause catastrophic issues.
# - rapid_prototyping: Heavy clause coverage (0.50) since verifying core features is the primary
#   objective, minimizing exception/boundary testing overhead (0.10 each).
# - data_pipeline: Prioritizes boundary (0.25) and negative (0.20) checks to handle bulk data ranges
#   and malformed schema exceptions.
# - distributed_concurrent: Focuses on negative path (0.25) and boundary/timing (0.20) to capture
#   timeouts, disconnections, and concurrency race conditions.
# - interaction_heavy: High clause coverage (0.40) to test complete user journeys and event flows.
# - standard: Balanced baseline across all metrics (wc=0.30, wn=0.20, wo=0.15, wb=0.20, wg=0.15).
FSA_WEIGHT_PROFILES = {
    "standard": {
        "wc": 0.30, "wn": 0.20, "wo": 0.15, "wb": 0.20, "wg": 0.15
    },
    "safety_critical": {
        "wc": 0.25, "wn": 0.25, "wo": 0.20, "wb": 0.20, "wg": 0.10
    },
    "rapid_prototyping": {
        "wc": 0.50, "wn": 0.10, "wo": 0.10, "wb": 0.10, "wg": 0.20
    },
    "data_pipeline": {
        "wc": 0.30, "wn": 0.20, "wo": 0.15, "wb": 0.25, "wg": 0.10
    },
    "distributed_concurrent": {
        "wc": 0.25, "wn": 0.25, "wo": 0.20, "wb": 0.20, "wg": 0.10
    },
    "interaction_heavy": {
        "wc": 0.40, "wn": 0.15, "wo": 0.15, "wb": 0.15, "wg": 0.15
    }
}

import re
_SAFETY_CUES = re.compile(r"\b(safety|critical|hazard|fault|fail-safe|iso 26262|do-178c|medical|automotive|aerospace)\b", re.IGNORECASE)
_CONCURRENCY_CUES = re.compile(r"\b(concurrent|concurrency|parallel|race|deadlock|lock|mutex|semaphore|thread|interleave|timing|ordering)\b", re.IGNORECASE)
_DATA_PIPELINE_CUES = re.compile(r"\b(data|pipeline|etl|dataset|transform|stream|input vector|distribution|matrix|features|batch)\b", re.IGNORECASE)
_INTERACTION_CUES = re.compile(r"\b(gui|click|press|display|screen|ux|ui|interaction|event graph|button|input|user interface)\b", re.IGNORECASE)
_PROTOTYPING_CUES = re.compile(r"\b(prototype|draft|concept|mvp|mock|rapid|fast-track)\b", re.IGNORECASE)

def infer_system_type(req_text: str) -> str:
    text = req_text or ""
    if _SAFETY_CUES.search(text):
        return "safety_critical"
    if _CONCURRENCY_CUES.search(text):
        return "distributed_concurrent"
    if _DATA_PIPELINE_CUES.search(text):
        return "data_pipeline"
    if _INTERACTION_CUES.search(text):
        return "interaction_heavy"
    if _PROTOTYPING_CUES.search(text):
        return "rapid_prototyping"
    return "standard"


def get_fsa_weights(representation: str, system_type: str = "standard") -> dict:
    """Returns system-profile-specific FSA weights, redistributing wg -> wc
    for representations with sparse concrete values (like KAOS, goal-oriented,
    user stories, use cases) to keep the evaluation fair."""
    weights = dict(FSA_WEIGHT_PROFILES.get(system_type, FSA_WEIGHT_PROFILES["standard"]))
    if is_sparse_concrete_rep(representation):
        weights["wc"] += weights["wg"]
        weights["wg"] = 0.0
    return weights


FSA_THRESHOLD = 0.75



REPRESENTATION_SUFFICIENCY_CHECKLISTS = {
    "gherkin": "Every requirements clause maps to a unique scenario. The test set must contain a Scenario Outline with Examples tables containing normal, edge, and invalid values. Then clauses must assert specific system states or variables rather than general descriptions.",
    "use cases": "Must contain a primary success flow, at least one alternative flow, and one exception flow. Actor roles must map exactly to user privileges defined in security requirements.",
    "user stories": "Must contain a primary success flow, at least one alternative flow, and one exception flow. Actor roles must map exactly to user privileges defined in security requirements.",
    "kaos": "All leaf operations must be assigned to specific components/agents. The test set must contain 'obstacle scenarios' checking system behavior when goals fail (e.g., network timeout).",
    "goal-oriented": "All leaf operations must be assigned to specific components/agents. The test set must contain 'obstacle scenarios' checking system behavior when goals fail (e.g., network timeout).",
    "category partition": "Every input parameter partition must be exercised at least once. Extreme bounds and invalid partition inputs must be included.",
    "transition systems": "100% transition coverage (every transition arrow is fired). Safety invariants must hold true in all reachable states.",
    "finite state machine": "100% state coverage and 100% transition coverage. Transition guard conditions must be tested under both True and False values.",
    "fsm": "100% state coverage and 100% transition coverage. Transition guard conditions must be tested under both True and False values.",
    "protocol state machine": "Must verify correct command order. Must send out-of-order commands to check if they are safely rejected with error codes.",
    "fsm path": "Prime path coverage must be achieved. Loop behaviors must be executed 0 times, 1 time, and multiple times to verify memory stability.",
    "w method": "W-set sequences must be fully executed to verify state equivalence.",
    "petri net": "Must check token conservation (no lost tokens), deadlock-freedom, and reachability of target marking states. Firing transitions must check concurrent pathways.",
    "sequence diagram": "All messages, sync calls, async calls, and returns must be executed. Alt (alternative), opt (optional), and loop frames must be tested. Network latency bounds must be asserted.",
    "interface automata": "Verifies that Component A's output actions never trigger Component B to enter an 'illegal' or deadlocked state.",
    "gui event graph": "Event sequence length must cover paths of length L >= 2. Modal boxes must block background interactions.",
    "temporal logic": "Safety properties ('bad things never happen') and liveness properties ('good things eventually happen') must be formally verified for all reachable states.",
    "ltl": "Safety properties ('bad things never happen') and liveness properties ('good things eventually happen') must be formally verified for all reachable states.",
    "ctl": "Safety properties ('bad things never happen') and liveness properties ('good things eventually happen') must be formally verified for all reachable states.",
    "decision table": "100% rule coverage. No two columns must specify conflicting actions for the same inputs. Don't-care values (-) must be checked to confirm they have no impact.",
    "cause-effect": "Logical constraints (Exclusive, Inclusive, Requires) must be validated. Every effect node must be toggled between active (1) and inactive (0).",
    "classification tree": "Pairwise (2-way) or N-way combinations of input classes must be executed. Edge bounds must be tested.",
    "ctm": "Pairwise (2-way) or N-way combinations of input classes must be executed. Edge bounds must be tested.",
    "rule-based": "Rules must fire under positive conditions and remain inactive under negative conditions. Overlapping rule conflicts must resolve correctly.",
    "fault tree": "All cut sets (fault combinations that trigger the main failure) must be simulated and verified to trigger target safety modes.",
    "xunit": "High assertion-to-action ratio. Mock libraries must provide deterministic responses. Exceptions must be explicitly verified (e.g., using pytest.raises).",
    "structured dsl": "DSL syntax must compile without errors. Pre/post conditions must map to system state variables.",
    "domain-specific dsl": "Every command must be tested with physical unit bounds.",
    "object construction graph": "Objects must be created in correct topological order. Teardown sequences must clean up memory and verify no resource leaks.",
    "ocg": "Objects must be created in correct topological order. Teardown sequences must clean up memory and verify no resource leaks.",
    "five-structure": "Verification block must follow each interaction block to verify intermediate states.",
    "concolic": "Concrete values must trigger target symbolic branches.",
    "canonical vector space": "Tests must evaluate overlapping read/write coordinates to check for race conditions.",
    "symbolic path condition": "Solvability check using SMT solvers. Unreachable code paths must be proven to be dead code.",
    "feature vector": "Vectors must cover the entire input space. Distance checks must verify input diversity.",
    "test requirement matrix": "Bi-directional traceability (every test maps to a requirement, and every requirement maps to a test).",
    "consumer-driven contract": "Schema validation. Field types and mandatory flags are asserted. Backward-compatibility checks.",
    "cdc": "Schema validation. Field types and mandatory flags are asserted. Backward-compatibility checks."
}

def get_sufficiency_checklist(representation: str) -> str:
    key = representation.strip().lower()
    for pattern, checklist in REPRESENTATION_SUFFICIENCY_CHECKLISTS.items():
        if pattern in key:
            return checklist
    return "Ensure complete clause coverage, negative flows, boundary checks, and robust verification assertions."


