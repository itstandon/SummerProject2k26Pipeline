import json
import os
import re
from datetime import datetime as _dt, timezone as _tz
from .call_llm import call_llm, MODELS
from .mongo_utils import store_to_mongodb

from results.metrics import evaluate_rss, evaluate_sfv, evaluate_fsa, compute_sdi, split_test_suite

MAX_ATTEMPTS = 3
EVAL_MODEL = os.getenv("LLM2_MODEL", "gpt-4o")


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
                            output_dir="results/test_cases",
                            metrics_output_dir="results/metrics"):
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
        model_metrics_dir = os.path.join(metrics_output_dir, f"{model_name}_{req_name}")
        os.makedirs(model_out_dir, exist_ok=True)
        os.makedirs(model_metrics_dir, exist_ok=True)

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

            # ----------------------------------------------------
            # GATE 1: Representational Suitability Score (RSS)
            # ----------------------------------------------------
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

            initial_prompt = template.replace("{REQ}", req_text).replace("{REP}", rep_context).replace("{DEPS}", dep_context)
            initial_prompt = initial_prompt.replace("{REQ}", req_text)
            initial_prompt = initial_prompt.replace("{REP}", rep_context)
            initial_prompt = initial_prompt.replace("{DEPS}", dep_context)

            print(f"    {rep_name}...")
            
            # ----------------------------------------------------
            # Closed-Loop Regeneration attempts for Gates 2 & 3
            # ----------------------------------------------------
            attempts_history = []
            current_prompt = initial_prompt
            final_content = ""
            passed_all_gates = False
            final_sfv_result = None
            final_fsa_result = None
            final_sdi_result = None

            for attempt_idx in range(MAX_ATTEMPTS):
                print(f"      [Attempt {attempt_idx + 1}/{MAX_ATTEMPTS}] Generating test suite...")
                response_content = _call_llm_text(current_prompt, model)
                
                # Check Gate 2: Syntactic Form Validity
                sfv_res = evaluate_sfv(test_case_text=response_content, representation=rep_name)
                
                attempt_record = {
                    "attempt_index": attempt_idx + 1,
                    "prompt_sent": current_prompt,
                    "response_received": response_content,
                    "sfv_result": sfv_res,
                    "fsa_result": None,
                    "sdi_result": None
                }

                if sfv_res["sfv_pass"]:
                    print(f"        SFV = {sfv_res['sfv_score']} (PASS) — running Gate 3 (FSA + Mg)...")
                    # Check Gate 3: Functional Semantic Adequacy
                    fsa_res = evaluate_fsa(
                        req_text=req_text,
                        representation=rep_name,
                        test_case_text=response_content,
                        call_llm_fn=call_llm,
                        model=EVAL_MODEL,
                        system_type=rss_result["system_type"]
                    )
                    attempt_record["fsa_result"] = fsa_res

                    if not fsa_res.get("error") and fsa_res.get("fsa_pass"):
                        print(f"        FSA = {fsa_res['fsa_score']} (PASS) — running Gate 4 (SDI)...")
                        test_cases = split_test_suite(response_content, rep_name)
                        sdi_res = compute_sdi(test_cases, rep_name)
                        attempt_record["sdi_result"] = sdi_res
                        
                        passed_all_gates = True
                        final_content = response_content
                        final_sfv_result = sfv_res
                        final_fsa_result = fsa_res
                        final_sdi_result = sdi_res
                        attempts_history.append(attempt_record)
                        print(f"        All gates PASSED on attempt {attempt_idx + 1}!")
                        break
                    else:
                        attempts_history.append(attempt_record)
                        err_msg = fsa_res.get("error") or f"Functional semantic adequacy score ({fsa_res.get('fsa_score', 0.0)}) failed to meet the threshold."
                        print(f"        FSA = {fsa_res.get('fsa_score', 0.0)} (FAIL) — send back to Gate 2 (re-generation to add missing scenarios).")
                        
                        # Build semantic feedback prompt
                        semantic_feedback = (
                            f"\n\n[REGENERATION FEEDBACK - Attempt {attempt_idx + 1} failed Gate 3 (FSA)]\n"
                            "Your generated test cases failed the Functional Semantic Adequacy (FSA) evaluation.\n"
                            f"Feedback / Issues identified: {err_msg}\n"
                            "Please rewrite and expand the test suite to ensure:\n"
                            "- 100% clause coverage of the requirement.\n"
                            "- Coverage of negative paths, error handling, and exception flows.\n"
                            "- Boundary condition/equivalence partition validation.\n"
                            "- Precise and deterministic test assertions (oracle assertiveness).\n"
                            "Do not leave placeholders. Output the complete corrected test suite."
                        )
                        current_prompt = initial_prompt + semantic_feedback
                else:
                    attempts_history.append(attempt_record)
                    print(f"        SFV = {sfv_res['sfv_score']} (FAIL) — send back to Gate 2 (re-generation to fix syntax errors).")
                    
                    # Build syntactic feedback prompt
                    syntax_feedback = (
                        f"\n\n[REGENERATION FEEDBACK - Attempt {attempt_idx + 1} failed Gate 2 (SFV)]\n"
                        "Your generated test cases failed the Syntactic Form Validity check for the representation.\n"
                        f"Syntax issues identified: {sfv_res.get('issues', [])}\n"
                        f"Please rewrite the test suite and fix the syntax errors to comply strictly with the {rep_name} standards."
                    )
                    current_prompt = initial_prompt + syntax_feedback

            # If it failed all attempts, use the last attempt's content
            if not passed_all_gates and attempts_history:
                final_content = attempts_history[-1]["response_received"]
                final_sfv_result = attempts_history[-1]["sfv_result"]
                final_fsa_result = attempts_history[-1].get("fsa_result")
                final_sdi_result = attempts_history[-1].get("sdi_result")

            # Save the final text output
            filename = re.sub(r'[^A-Za-z0-9_\-\.]', '_', rep_name.replace(" ", "_"))
            try:
                with open(os.path.join(model_out_dir, f"{filename}.txt"), "w") as out:
                    out.write(final_content)
                print(f"    {rep_name} final output saved.")
            except OSError as e:
                print(f"    Failed to save final {rep_name}: {e}")
                continue

            # Save complete metrics evaluation history locally
            metric_record = {
                "requirement_file": req_filename,
                "model": model,
                "representation": rep_name,
                "rss_score": rss_result["rss_score"],
                "passed_all_gates": passed_all_gates,
                "final_attempt_index": len(attempts_history),
                "attempts": attempts_history
            }
            with open(os.path.join(model_metrics_dir, f"{filename}.json"), "w") as out:
                json.dump(metric_record, out, indent=2)

            seen_representations.add(rep_name)

            # --- MongoDB Storage of final results and full regeneration history ---
            mongo_doc = {
                "timestamp": _dt.now(_tz.utc).isoformat(),
                "requirement_file": req_filename,
                "model": model,
                "representation": rep_name,
                "rss_score": rss_result["rss_score"],
                "passed_all_gates": passed_all_gates,
                "final_attempt_index": len(attempts_history),
                "final_sfv_result": final_sfv_result,
                "final_fsa_result": final_fsa_result,
                "final_sdi_result": final_sdi_result,
                "final_content": final_content,
                "attempts_history": attempts_history
            }
            store_to_mongodb(mongo_doc, "test_cases")