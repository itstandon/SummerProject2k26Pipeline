import json
import os
import re
from datetime import datetime as _dt, timezone as _tz
from .call_llm import call_llm, MODELS
from .mongo_utils import store_to_mongodb

def run_find_dependencies(req_text, req_filename,
                          prompt_path="prompts/find_dependencies.txt",
                          output_dir="results/dependencies"):

    with open(prompt_path) as f:
        prompt = f.read()
    prompt = prompt.replace("{REQ}", req_text)

    os.makedirs(output_dir, exist_ok=True)
    req_name = os.path.splitext(req_filename)[0]

    for model in MODELS:
        model_name = model.replace(":", "_").replace("/", "_")
        print(f"  Finding dependencies with {model}...")
        result = call_llm(prompt, model)

        # Clean and extract JSON from markdown code block if present
        json_str = result.strip()
        match = re.search(r'```(?:json)?\s*(.*?)\s*```', json_str, re.DOTALL)
        if match:
            json_str = match.group(1).strip()

        try:
            parsed = json.loads(json_str)
            result = json.dumps(parsed, indent=2)
        except json.JSONDecodeError:
            raw = re.sub(r',\s*([}\]])', r'\1', json_str)
            try:
                result = json.dumps(json.loads(raw), indent=2)
            except:
                pass

        out_path = os.path.join(output_dir, f"{model_name}_{req_name}.json")
        with open(out_path, "w") as f:
            f.write(result)
        print(f"  Saved to {out_path}")

        # --- Mongo storage (same output, same connection back_forth.py uses) ---
        try:
            content_for_mongo = json.loads(result)
        except Exception:
            content_for_mongo = result

        mongo_doc = {
            "timestamp": _dt.now(_tz.utc).isoformat(),
            "requirement_file": req_filename,
            "model": model,
            "content": content_for_mongo,
        }
        store_to_mongodb(mongo_doc, "dependencies")