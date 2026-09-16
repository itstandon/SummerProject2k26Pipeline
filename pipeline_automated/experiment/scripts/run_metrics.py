import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
EXPERIMENT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
for _p in (SCRIPT_DIR, EXPERIMENT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from call_llm import MODELS
from results.metrics import evaluate_sfv
from generate_testcases import PHASES


def _model_name(model: str) -> str:
    return model.replace(":", "_").replace("/", "_")


def run_evaluate_metrics(req_text, req_filename,
                          test_cases_dir="results/test_cases",
                          output_dir="results/metrics",
                          phases=None):
    """
    Call this right after run_generate_testcases(req_text, req_filename)
    in cli.py.

    Representation selection is gone, and so are Gate 1 (RSS) and Gate 3
    (FSA) -- the only automated check left in this pipeline is Gate 2
    (SFV), rewritten to check the fixed test-case template every phase's
    prompt asks for (Test Case ID / Title / Preconditions / Steps /
    Expected Result -- see gate2_sfv.py), rather than a representation's
    syntax. It's a pure heuristic check, no evaluator LLM call needed.

    The second half of the rubric -- expert ground-truth alignment --
    is handled separately by compare_with_expert.run_compare_with_expert.

    Both phase1_basic and phase2_metrics_aware are scored, for every
    model, so they can be compared head-to-head.
    """
    phases = phases or PHASES
    req_name = os.path.splitext(req_filename)[0]
    os.makedirs(output_dir, exist_ok=True)

    overall_summary = []

    for phase_name in phases:
        for model in MODELS:
            model_name = _model_name(model)
            suite_dir = os.path.join(test_cases_dir, phase_name, f"{model_name}_{req_name}")
            suite_path = os.path.join(suite_dir, f"{req_name}.txt")

            if not os.path.exists(suite_path):
                continue

            with open(suite_path) as f:
                suite_text = f.read()

            model_out_dir = os.path.join(output_dir, phase_name, f"{model_name}_{req_name}")
            os.makedirs(model_out_dir, exist_ok=True)
            metric_json_path = os.path.join(model_out_dir, f"{req_name}_sfv.json")

            print(f"\n  [{phase_name}] Gate 2 (SFV): {model} / {req_name}...")

            sfv_result = evaluate_sfv(test_case_text=suite_text)
            with open(metric_json_path, "w") as out:
                json.dump(sfv_result, out, indent=2)

            status = "PASS" if sfv_result["sfv_pass"] else "FAIL"
            print(f"    SFV = {sfv_result['sfv_score']} ({status}) — "
                  f"{sfv_result['well_formed_count']}/{sfv_result['test_case_count']} test cases well-formed.")
            if sfv_result["issues"]:
                for issue in sfv_result["issues"][:5]:
                    print(f"      - {issue}")

            overall_summary.append({
                "phase": phase_name,
                "model": model,
                "sfv_score": sfv_result.get("sfv_score"),
                "sfv_pass": sfv_result.get("sfv_pass"),
                "test_case_count": sfv_result.get("test_case_count"),
            })

    summary_path = os.path.join(output_dir, f"{req_name}_sfv_summary.json")
    with open(summary_path, "w") as f:
        json.dump(overall_summary, f, indent=2)

    print(f"\n  SFV summary written to {summary_path}")
    return overall_summary


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python run_metrics.py <path_to_requirement_txt>")
        sys.exit(1)

    path = sys.argv[1]
    with open(path) as f:
        text = f.read()
    run_evaluate_metrics(text, os.path.basename(path))