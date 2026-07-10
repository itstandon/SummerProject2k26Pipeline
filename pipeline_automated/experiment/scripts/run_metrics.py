import json
import os
import sys

from call_llm import call_llm, MODELS
from token_tracker import log_usage

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
EXPERIMENT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if EXPERIMENT_DIR not in sys.path:
    sys.path.insert(0, EXPERIMENT_DIR)

from results.metrics import evaluate_sfv, evaluate_fsa, compute_sdi, split_test_suite


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

            print(f"    Gate 2 (SFV): {representation}...")
            sfv_result = evaluate_sfv(test_case_text=suite_text, representation=representation)

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

                record["fsa"] = fsa_result

                if fsa_result.get("error"):
                    print(f"      Gate 3 evaluation failed: {fsa_result['error']}")
                elif fsa_result["fsa_pass"]:
                    print(f"      FSA = {fsa_result['fsa_score']} (PASS) — running Gate 4 (SDI)...")
                    test_cases = split_test_suite(suite_text, representation)
                    sdi_result = compute_sdi(test_cases, representation)
                    record["sdi"] = sdi_result
                    print(f"      SDI = {sdi_result['sdi_score']} "
                          f"({'PASS' if sdi_result['sdi_pass'] else 'FLAGGED for near-duplicate regen'})")
                else:
                    print(f"      FSA = {fsa_result['fsa_score']} (FAIL) — send back to Gate 3 regeneration.")
            else:
                print(f"      SFV = {sfv_result['sfv_score']} (FAIL) — send back to Gate 2 regeneration.")

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
                "sdi_score": record.get("sdi", {}).get("sdi_score"),
                "sdi_pass": record.get("sdi", {}).get("sdi_pass"),
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