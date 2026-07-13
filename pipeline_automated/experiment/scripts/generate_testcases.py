import json
import os
import re
from datetime import datetime as _dt, timezone as _tz
from .call_llm import call_llm, MODELS
from .mongo_utils import store_to_mongodb

from results.metrics import evaluate_rss


def _call_llm_text(prompt, model):
    result = call_llm(prompt, model)
    if isinstance(result, tuple):
        return result[0]
    return result


def _parse_selected_representations(raw_text):
    match = re.search(r'\{[\s\S]*\}', raw_text)
    if not match:
        return None

    raw = match.group(0)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raw = re.sub(r',\s*([}\]])', r'\1', raw)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            rep_names = re.findall(r'"representation"\s*:\s*"([^"]+)"', raw)
            if not rep_names:
                return None
            data = {"selected_representations": [{"representation": name} for name in rep_names]}

    return data.get("selected_representations", [])


def _reselect_representations(req_text, failed_rep_name, model,
                              prompt_path="prompts/select_representations.txt"):
    with open(prompt_path) as f:
        prompt = f.read()

    prompt = prompt.replace("{REQ}", req_text)
    prompt += (
        f"\n\nThe representation \"{failed_rep_name}\" failed the RSS gate. "
        "Do not select it again. Replace it with a better alternative from the available list and return JSON only."
    )

    result = _call_llm_text(prompt, model)
    return _parse_selected_representations(result)

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

        representations = _parse_selected_representations(text)
        if not representations:
            print(f"  Skipping {model} — no valid JSON in output.")
            continue

        model_out_dir = os.path.join(output_dir, f"{model_name}_{req_name}")
        os.makedirs(model_out_dir, exist_ok=True)

        print(f"\n  Generating test cases with {model}...")
        queued_representations = list(representations)
        seen_representations = set()

        while queued_representations:
            rep = queued_representations.pop(0)
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
                seen_representations.add(rep_name)

                replacement_reps = _reselect_representations(req_text, rep_name, model)
                if replacement_reps:
                    for replacement in replacement_reps:
                        replacement_name = replacement["representation"] if isinstance(replacement, dict) else replacement
                        if replacement_name not in seen_representations:
                            queued_representations.append(replacement)
                            print(f"    Re-selected candidate: {replacement_name}")
                            break
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
            result = _call_llm_text(prompt, model)

            filename = re.sub(r'[^A-Za-z0-9_\-\.]', '_', rep_name.replace(" ", "_"))
            try:
                with open(os.path.join(model_out_dir, f"{filename}.txt"), "w") as out:
                    out.write(result)
                print(f"    {rep_name} done.")
            except OSError as e:
                print(f"    Failed to save {rep_name}: {e}")
                continue
            print(f"    {rep_name} done.")
            seen_representations.add(rep_name)

            # --- Mongo storage (same output, same connection back_forth.py uses) ---
            mongo_doc = {
                "timestamp": _dt.now(_tz.utc).isoformat(),
                "requirement_file": req_filename,
                "model": model,
                "representation": rep_name,
                "rss_score": rss_result["rss_score"],
                "content": result,
            }
            store_to_mongodb(mongo_doc, "test_cases")