import json
import os
import re
from datetime import datetime as _dt, timezone as _tz
from .call_llm import call_llm, MODELS
from .mongo_utils import store_to_mongodb

from results.metrics import evaluate_rss, evaluate_sfv, evaluate_fsa

MAX_ATTEMPTS = 3
EVAL_MODEL = os.getenv("LLM2_MODEL", "gpt-4o")

# How many Gate-1-passing representations we want locked in before we ever
# start generating test cases. A representation that fails RSS does NOT
# consume one of these slots -- it's discarded and replaced with a freshly
# LLM-selected candidate (#7, #8, #9, ...) until we either fill all
# TARGET_REP_COUNT slots or run out of resolution attempts.
TARGET_REP_COUNT = 6

# Safety cap on how many total candidates we'll evaluate against Gate 1
# while trying to fill TARGET_REP_COUNT slots, so a pathological requirement
# (or a flaky reselection prompt) can't loop forever.
MAX_RESOLUTION_ATTEMPTS = 20


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


def _resolve_representation_context(rep, req_text):
    """Turn a raw candidate (dict or plain string) into (rep_name, rep_context)."""
    if isinstance(rep, dict):
        rep_name = rep["representation"]
        excerpt = rep.get("requirement_excerpt", req_text)
        reason = rep.get("reason", "")
        rep_context = f"{rep_name}\nRelevant requirement: {excerpt}\nReason: {reason}"
    else:
        rep_name = rep
        rep_context = rep
    return rep_name, rep_context


def _resolve_representations(req_text, initial_representations, model,
                              target_count=TARGET_REP_COUNT,
                              max_total_candidates=MAX_RESOLUTION_ATTEMPTS):
    """
    GATE 1 resolution phase.

    Pulls candidates from `initial_representations` (the LLM's original
    picks) and evaluates each against Gate 1 (RSS) until `target_count` of
    them pass, or we exhaust `max_total_candidates` attempts.

    A candidate that fails RSS is discarded -- it never gets generated --
    and is replaced with a freshly LLM-selected alternative appended to the
    back of the queue. Since the queue is only ever popped from the front,
    replacement candidates naturally become #7, #8, #9, ... beyond however
    many the LLM originally proposed, and they get the exact same Gate 1
    treatment as the originals: pass -> fills a slot, fail -> discarded and
    replaced again.

    No test case generation happens here. This function's only job is to
    return a clean list of representations that are known-good per Gate 1,
    plus a full audit trail of every candidate that was tried (pass or fail)
    so the caller can persist a record of what happened during resolution.

    Returns:
        (validated, audit_trail)
        validated: list of dicts {"rep_name": str, "rep_context": str, "rss_result": dict}
        audit_trail: list of dicts {"candidate_number": int, "rep_name": str,
                                     "rss_score": float, "rss_pass": bool}
                     in the order they were tried, including duplicates skipped
                     and every replacement candidate beyond the original picks.
    """
    queued = list(initial_representations)
    seen_representations = set()
    validated = []
    audit_trail = []
    candidates_tried = 0
    candidate_number = 0  # for logging only: 1..N are the original picks, beyond that are replacements

    while queued and len(validated) < target_count and candidates_tried < max_total_candidates:
        rep = queued.pop(0)
        candidate_number += 1
        candidates_tried += 1

        rep_name, rep_context = _resolve_representation_context(rep, req_text)

        if rep_name in seen_representations:
            print(f"    Candidate #{candidate_number} ('{rep_name}') already tried — skipping duplicate.")
            audit_trail.append({
                "candidate_number": candidate_number,
                "rep_name": rep_name,
                "rss_score": None,
                "rss_pass": None,
                "note": "duplicate, skipped",
            })
            continue
        seen_representations.add(rep_name)

        rss_result = evaluate_rss(req_text=req_text, representation=rep_name)
        print(f"    Gate 1 (RSS): candidate #{candidate_number} '{rep_name}' -> {rss_result['rss_score']} "
              f"({'PASS' if rss_result['rss_pass'] else 'FAIL'}) "
              f"[{len(validated)}/{target_count} slots filled]")

        audit_trail.append({
            "candidate_number": candidate_number,
            "rep_name": rep_name,
            "rss_score": rss_result["rss_score"],
            "rss_pass": rss_result["rss_pass"],
        })

        if rss_result["rss_pass"]:
            validated.append({
                "rep_name": rep_name,
                "rep_context": rep_context,
                "rss_result": rss_result,
            })
            continue

        print(f"    '{rep_name}' failed Gate 1 — requesting a replacement representation...")
        replacements = _reselect_representations(req_text, rep_name, model)
        if replacements:
            for replacement in replacements:
                replacement_name = replacement["representation"] if isinstance(replacement, dict) else replacement
                if replacement_name not in seen_representations:
                    queued.append(replacement)
        else:
            print(f"    No replacement suggested for '{rep_name}'; moving on without it.")

    if len(validated) < target_count:
        print(f"    Warning: only found {len(validated)}/{target_count} representations that pass "
              f"Gate 1 after {candidates_tried} candidate(s) evaluated. Proceeding with what passed.")

    return validated, audit_trail


def run_generate_testcases(req_text, req_filename,
                            rep_output_dir="results/representation_selection",
                            prompt_path="prompts/generate_testcases.txt",
                            output_dir="results/test_cases",
                            metrics_output_dir="results/metrics",
                            target_rep_count=TARGET_REP_COUNT):
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

        # ----------------------------------------------------
        # PHASE A -- GATE 1: resolve target_rep_count representations
        # that pass RSS before generating anything. Failures are
        # discarded and replaced with new candidates (#7, #8, #9, ...)
        # until we fill all slots or run out of attempts.
        # ----------------------------------------------------
        print(f"\n  Resolving {target_rep_count} Gate-1-passing representations for {model}...")
        resolved_reps, resolution_audit = _resolve_representations(
            req_text, representations, model, target_count=target_rep_count,
        )

        # Persist the resolution outcome as a SIBLING file next to the
        # original selection JSON. The original file
        # (results/representation_selection/{model}_{req_name}.json) is
        # never touched or overwritten -- it stays a record of the LLM's
        # first guesses. This new "_resolved.json" file is the record of
        # what actually cleared Gate 1 (including any #7, #8, #9...
        # replacements) and therefore went on to generation.
        resolution_record = {
            "requirement_file": req_filename,
            "model": model,
            "target_rep_count": target_rep_count,
            "resolved_count": len(resolved_reps),
            "resolved": [
                {"rep_name": r["rep_name"], "rss_score": r["rss_result"]["rss_score"]}
                for r in resolved_reps
            ],
            "candidates_tried": resolution_audit,
        }
        resolution_path = os.path.join(rep_output_dir, f"{model_name}_{req_name}_resolved.json")
        with open(resolution_path, "w") as f:
            json.dump(resolution_record, f, indent=2)
        print(f"  Gate 1 resolution record saved to {resolution_path}")

        if not resolved_reps:
            print(f"  No representation passed Gate 1 for {model}; skipping test case generation.")
            continue

        print(f"  Gate 1 resolved {len(resolved_reps)}/{target_rep_count} representation(s) for {model}.")

        # ----------------------------------------------------
        # PHASE B -- generate test cases (with the existing closed-loop
        # Gate 2/Gate 3 regeneration) only for representations that
        # already passed Gate 1.
        # ----------------------------------------------------
        print(f"\n  Generating test cases with {model}...")

        for resolved in resolved_reps:
            rep_name = resolved["rep_name"]
            rep_context = resolved["rep_context"]
            rss_result = resolved["rss_result"]

            dep_path = os.path.join("results/dependencies", f"{model_name}_{req_name}.json")
            dep_context = ""
            if os.path.exists(dep_path):
                with open(dep_path) as f:
                    dep_context = f.read()

            initial_prompt = template.replace("{REQ}", req_text).replace("{REP}", rep_context).replace("{DEPS}", dep_context)

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
                        passed_all_gates = True
                        final_content = response_content
                        final_sfv_result = sfv_res
                        final_fsa_result = fsa_res
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
                "final_content": final_content,
                "attempts_history": attempts_history
            }
            store_to_mongodb(mongo_doc, "test_cases")