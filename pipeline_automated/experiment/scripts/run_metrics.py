import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
EXPERIMENT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
for _p in (SCRIPT_DIR, EXPERIMENT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from call_llm import call_llm, MODELS
from token_tracker import log_usage
from results.metrics import evaluate_sfv, evaluate_fsa
from results.metrics import evaluate_sfv, evaluate_fsa


def _model_name(model: str) -> str:
    return model.replace(":", "_").replace("/", "_")


def _representation_name_from_filename(filename: str) -> str:
    # generate_testcases.py wrote files as rep_name.replace(" ", "_") + ".txt"
    return os.path.splitext(filename)[0].replace("_", " ")


def run_evaluate_metrics(req_text, req_filename,
                          test_cases_dir="results/test_cases",
                          output_dir="results/metrics",
                          eval_model=None):
    """
    Call this right after run_generate_testcases(req_text, req_filename)
    in cli.py — it walks the same directory structure
    generate_testcases.py just wrote, scores every generated
    representation file against Gate 2 (SFV), Gate 3 (FSA + Groundedness),
    then Gate 4 (SDI) on the same file split into individual test cases.

    Only representations whose FSA passes get an SDI score, matching
    the "Gate 4 runs after FSA passes" flow in metrics.md.
    """
    req_name = os.path.splitext(req_filename)[0]
    os.makedirs(output_dir, exist_ok=True)

    eval_model = eval_model or MODELS[0]
    overall_summary = []

    for model in MODELS:
        model_name = _model_name(model)
        suite_dir = os.path.join(test_cases_dir, f"{model_name}_{req_name}")

        if not os.path.isdir(suite_dir):
            continue

        model_out_dir = os.path.join(output_dir, f"{model_name}_{req_name}")
        os.makedirs(model_out_dir, exist_ok=True)

        print(f"\n  Evaluating metrics for {model}...")

        for filename in sorted(os.listdir(suite_dir)):
            if not filename.endswith(".txt"):
                continue

            representation = _representation_name_from_filename(filename)
            file_path = os.path.join(suite_dir, filename)
            with open(file_path) as f:
                suite_text = f.read()

            metric_json_path = os.path.join(model_out_dir, os.path.splitext(filename)[0] + ".json")
            
            # Check if metrics were already computed during the closed-loop generation phase
            if os.path.exists(metric_json_path):
                print(f"    [Pre-computed] Loading metrics and history for {representation}...")
                with open(metric_json_path) as mj:
                    record = json.load(mj)
                
                # Extract results from the final attempt in history
                if record.get("attempts"):
                    final_attempt = record["attempts"][-1]
                    sfv_result = final_attempt.get("sfv_result") or {}
                    fsa_result = final_attempt.get("fsa_result") or {}
                else:
                    sfv_result = record.get("sfv", {})
                    fsa_result = record.get("fsa", {})
                
                # Print status summary
                if sfv_result.get("sfv_pass"):
                    print(f"      SFV = {sfv_result.get('sfv_score')} (PASS)")
                    if fsa_result.get("fsa_pass"):
                        print(f"      FSA = {fsa_result.get('fsa_score')} (PASS)")
                    else:
                        print(f"      FSA = {fsa_result.get('fsa_score', 0.0)} (FAIL) — send back to Gate 2 generation (to add missing scenarios).")
                else:
                    print(f"      SFV = {sfv_result.get('sfv_score', 0.0)} (FAIL) — send back to Gate 2 generation (to fix syntax errors).")
            else:
                # Fallback: compute metrics freshly if no JSON output exists
                print(f"    Gate 2 (SFV): {representation}...")
                sfv_result = evaluate_sfv(test_case_text=suite_text, representation=representation)
            metric_json_path = os.path.join(model_out_dir, os.path.splitext(filename)[0] + ".json")
            
            # Check if metrics were already computed during the closed-loop generation phase
            if os.path.exists(metric_json_path):
                print(f"    [Pre-computed] Loading metrics and history for {representation}...")
                with open(metric_json_path) as mj:
                    record = json.load(mj)
                
                # Extract results from the final attempt in history
                if record.get("attempts"):
                    final_attempt = record["attempts"][-1]
                    sfv_result = final_attempt.get("sfv_result") or {}
                    fsa_result = final_attempt.get("fsa_result") or {}
                else:
                    sfv_result = record.get("sfv", {})
                    fsa_result = record.get("fsa", {})
                
                # Print status summary
                if sfv_result.get("sfv_pass"):
                    print(f"      SFV = {sfv_result.get('sfv_score')} (PASS)")
                    if fsa_result.get("fsa_pass"):
                        print(f"      FSA = {fsa_result.get('fsa_score')} (PASS)")
                    else:
                        print(f"      FSA = {fsa_result.get('fsa_score', 0.0)} (FAIL) — send back to Gate 2 generation (to add missing scenarios).")
                else:
                    print(f"      SFV = {sfv_result.get('sfv_score', 0.0)} (FAIL) — send back to Gate 2 generation (to fix syntax errors).")
            else:
                # Fallback: compute metrics freshly if no JSON output exists
                print(f"    Gate 2 (SFV): {representation}...")
                sfv_result = evaluate_sfv(test_case_text=suite_text, representation=representation)

                record = {"representation": representation, "sfv": sfv_result}
                fsa_result = {}
                record = {"representation": representation, "sfv": sfv_result}
                fsa_result = {}

                if sfv_result["sfv_pass"]:
                    print(f"      SFV = {sfv_result['sfv_score']} (PASS) — running Gate 3 (FSA + Mg)...")
                    fsa_result = evaluate_fsa(
                        req_text=req_text,
                        representation=representation,
                        test_case_text=suite_text,
                        call_llm_fn=call_llm,
                        model=eval_model,
                        log_usage_fn=log_usage,
                        extra_log={"req_file": req_filename, "representation": representation, "gate": "3"},
                    )
                if sfv_result["sfv_pass"]:
                    print(f"      SFV = {sfv_result['sfv_score']} (PASS) — running Gate 3 (FSA + Mg)...")
                    fsa_result = evaluate_fsa(
                        req_text=req_text,
                        representation=representation,
                        test_case_text=suite_text,
                        call_llm_fn=call_llm,
                        model=eval_model,
                        log_usage_fn=log_usage,
                        extra_log={"req_file": req_filename, "representation": representation, "gate": "3"},
                    )

                    record["fsa"] = fsa_result
                    record["fsa"] = fsa_result

                    if fsa_result.get("error"):
                        print(f"      Gate 3 evaluation failed: {fsa_result['error']}")
                    elif fsa_result["fsa_pass"]:
                        print(f"      FSA = {fsa_result['fsa_score']} (PASS)")
                    else:
                        print(f"      FSA = {fsa_result['fsa_score']} (FAIL) — send back to Gate 2 generation (to add missing scenarios).")
                    if fsa_result.get("error"):
                        print(f"      Gate 3 evaluation failed: {fsa_result['error']}")
                    elif fsa_result["fsa_pass"]:
                        print(f"      FSA = {fsa_result['fsa_score']} (PASS)")
                    else:
                        print(f"      FSA = {fsa_result['fsa_score']} (FAIL) — send back to Gate 2 generation (to add missing scenarios).")
                else:
                    print(f"      SFV = {sfv_result['sfv_score']} (FAIL) — send back to Gate 2 generation (to fix syntax errors).")
                    print(f"      SFV = {sfv_result['sfv_score']} (FAIL) — send back to Gate 2 generation (to fix syntax errors).")

                # Save the fallback computation JSON
                out_name = os.path.splitext(filename)[0] + ".json"
                with open(os.path.join(model_out_dir, out_name), "w") as out:
                    json.dump(record, out, indent=2)
                # Save the fallback computation JSON
                out_name = os.path.splitext(filename)[0] + ".json"
                with open(os.path.join(model_out_dir, out_name), "w") as out:
                    json.dump(record, out, indent=2)

            overall_summary.append({
                "model": model,
                "representation": representation,
                "sfv_score": sfv_result.get("sfv_score"),
                "sfv_pass": sfv_result.get("sfv_pass"),
                "fsa_score": fsa_result.get("fsa_score"),
                "fsa_pass": fsa_result.get("fsa_pass"),
            })

    summary_path = os.path.join(output_dir, f"{req_name}_summary.json")
    with open(summary_path, "w") as f:
        json.dump(overall_summary, f, indent=2)

    print(f"\n  Metrics summary written to {summary_path}")
    return overall_summary


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python run_metrics.py <path_to_requirement_txt>")
        sys.exit(1)

    path = sys.argv[1]
    with open(path) as f:
        text = f.read()
    run_evaluate_metrics(text, os.path.basename(path))