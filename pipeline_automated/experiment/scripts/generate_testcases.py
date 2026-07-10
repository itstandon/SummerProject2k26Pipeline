import json
import os
import re
import sys
from call_llm import call_llm, MODELS
from token_tracker import log_usage

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
EXPERIMENT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if EXPERIMENT_DIR not in sys.path:
    sys.path.insert(0, EXPERIMENT_DIR)

from results.metrics import evaluate_rss

def run_generate_testcases(req_text, req_filename,
                            rep_output_dir="results/representation_selection",
                            prompt_path="prompts/generate_testcases.txt",
                            output_dir="results/test_cases"):
    with open(prompt_path) as f:
        template = f.read()

    req_name = os.path.splitext(req_filename)[0]

    for model in MODELS:
        model_name = model.replace(":", "_").replace("/", "_")
        llm_output_path = os.path.join(rep_output_dir, f"{model_name}_{req_name}.json")

        if not os.path.exists(llm_output_path):
            print(f"  Skipping {model} — no representation output found.")
            continue

        with open(llm_output_path) as f:
            text = f.read()

        match = re.search(r'\{[\s\S]*\}', text)
        if not match:
            print(f"  Skipping {model} — no valid JSON in output.")
            continue

        # Try to fix common LLM JSON issues before parsing
        raw = match.group(0)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Remove trailing commas before ] or }
            raw = re.sub(r',\s*([}\]])', r'\1', raw)
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                print(f"  JSON malformed for {model}, extracting representation names only...")
                rep_names = re.findall(r'"representation"\s*:\s*"([^"]+)"', raw)
                if not rep_names:
                    print(f"  Skipping {model} — couldn't extract anything.")
                    continue
                data = {"selected_representations": [{"representation": name} for name in rep_names]}
        representations = data["selected_representations"]

        model_out_dir = os.path.join(output_dir, f"{model_name}_{req_name}")
        os.makedirs(model_out_dir, exist_ok=True)

        print(f"\n  Generating test cases with {model}...")
        for rep in representations:
            if isinstance(rep, dict):
                rep_name = rep["representation"]
                excerpt = rep.get("requirement_excerpt", req_text)
                reason = rep.get("reason", "")
                rep_context = f"{rep_name}\nRelevant requirement: {excerpt}\nReason: {reason}"
            else:
                rep_name = rep
                rep_context = rep

            rss_result = evaluate_rss(req_text=req_text, representation=rep_name)
            print(f"    Gate 1 (RSS): {rep_name} -> {rss_result['rss_score']} "
                  f"({'PASS' if rss_result['rss_pass'] else 'FAIL'})")
            if not rss_result["rss_pass"]:
                print(f"    Skipping {rep_name} because it failed Gate 1.")
                continue

            dep_path = os.path.join("results/dependencies", f"{model_name}_{req_name}.json")
            dep_context = ""
            if os.path.exists(dep_path):
                with open(dep_path) as f:
                    dep_context = f.read()

            prompt = template.replace("{REQ}", req_text).replace("{REP}", rep_context).replace("{DEPS}", dep_context)
            prompt = prompt.replace("{REQ}", req_text)
            prompt = prompt.replace("{REP}", rep_context)
            prompt = prompt.replace("{DEPS}", dep_context) 

            print(f"    {rep_name}...")
            result, usage = call_llm(prompt, model)
            log_usage("generate_testcases", usage, extra={
                "req_file": req_filename,
                "representation": rep_name,
            })

            filename = rep_name.replace(" ", "_")
            with open(os.path.join(model_out_dir, f"{filename}.txt"), "w") as out:
                out.write(result)
            print(f"    {rep_name} done.")