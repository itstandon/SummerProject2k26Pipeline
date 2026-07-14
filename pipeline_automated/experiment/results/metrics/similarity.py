"""
Representation-dependent similarity functions for Gate 4's Redundancy
Rate (SDI). Deliberately dependency-free (stdlib only) so this drops
into any environment without needing sentence-transformer / sklearn
installs. If you later wire in a real embedding model, swap out
`embedding_similarity` only – everything else calls it through
`similarity(a, b, method)`.
"""

import ast
import difflib
import math
import re
from collections import Counter

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")
_TRANSITION_RE = re.compile(r"([\w.]+)\s*(?:-{1,2}>|=>)\s*([\w.]+)")
_NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")


def _tokenize(text: str) -> list:
    return _TOKEN_RE.findall((text or "").lower())


def embedding_similarity(a: str, b: str) -> float:
    """Bag-of-words TF cosine similarity, used as a stand-in for a real
    sentence-embedding model for Group 1 (Gherkin, Use Cases, KAOS).
    Swap this out for a real embedding call if/when one is available."""
    ta, tb = Counter(_tokenize(a)), Counter(_tokenize(b))
    if not ta or not tb:
        return 0.0
    common = set(ta) & set(tb)
    dot = sum(ta[t] * tb[t] for t in common)
    norm_a = math.sqrt(sum(v * v for v in ta.values()))
    norm_b = math.sqrt(sum(v * v for v in tb.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def graph_similarity(a: str, b: str) -> float:
    """Jaccard similarity over extracted transition/path tokens
    (e.g. 'OFF -> STARTING'), used for Group 2/3 (FSM, Protocol SM,
    Petri Nets, Sequence Diagrams, Interface Automata). Falls back to
    embedding_similarity if no transition-like tokens are found."""
    edges_a = set(_TRANSITION_RE.findall(a or ""))
    edges_b = set(_TRANSITION_RE.findall(b or ""))
    if not edges_a or not edges_b:
        return embedding_similarity(a, b)
    union = edges_a | edges_b
    inter = edges_a & edges_b
    if not union:
        return 0.0
    return len(inter) / len(union)


def hamming_similarity(a: str, b: str) -> float:
    """Normalized Hamming similarity over condition-column-like rows
    (lines containing '|'), used for Group 4 (Decision Tables,
    Cause-Effect Graphs, CTM, Rule-Based Constraints). Falls back to
    embedding_similarity if neither text looks tabular."""
    rows_a = [ln for ln in (a or "").splitlines() if "|" in ln]
    rows_b = [ln for ln in (b or "").splitlines() if "|" in ln]
    if not rows_a or not rows_b:
        return embedding_similarity(a, b)

    cells_a = "".join(rows_a).replace(" ", "")
    cells_b = "".join(rows_b).replace(" ", "")
    length = max(len(cells_a), len(cells_b))
    if length == 0:
        return 1.0
    cells_a = cells_a.ljust(length)
    cells_b = cells_b.ljust(length)
    diffs = sum(1 for x, y in zip(cells_a, cells_b) if x != y)
    return 1.0 - (diffs / length)


def ast_similarity(a: str, b: str) -> float:
    """Normalized AST tree-edit-distance proxy for Group 5 (xUnit,
    Structured/Domain DSLs, Object Construction Graphs). Tries a real
    Python AST diff first (via difflib over ast.dump output); falls
    back to a plain text SequenceMatcher ratio for non-Python DSLs,
    which is still a legitimate normalized structural-similarity proxy."""
    try:
        dump_a = ast.dump(ast.parse(a))
        dump_b = ast.dump(ast.parse(b))
        return difflib.SequenceMatcher(None, dump_a, dump_b).ratio()
    except SyntaxError:
        return difflib.SequenceMatcher(None, a or "", b or "").ratio()


def vector_similarity(a: str, b: str) -> float:
    """Cosine similarity over extracted numeric vectors, for Group 6
    (Canonical Vector Spaces, Symbolic Path Conditions, Feature
    Vectors, CDC) – these representations are already numeric/native."""
    va = [float(x) for x in _NUMBER_RE.findall(a or "")]
    vb = [float(x) for x in _NUMBER_RE.findall(b or "")]
    if not va or not vb:
        return embedding_similarity(a, b)
    length = max(len(va), len(vb))
    va = va + [0.0] * (length - len(va))
    vb = vb + [0.0] * (length - len(vb))
    dot = sum(x * y for x, y in zip(va, vb))
    norm_a = math.sqrt(sum(x * x for x in va))
    norm_b = math.sqrt(sum(y * y for y in vb))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


_METHODS = {
    "embedding": embedding_similarity,
    "graph": graph_similarity,
    "hamming": hamming_similarity,
    "ast": ast_similarity,
    "vector": vector_similarity,
}


def similarity(a: str, b: str, method: str) -> float:
    fn = _METHODS.get(method, embedding_similarity)
    return fn(a, b)
