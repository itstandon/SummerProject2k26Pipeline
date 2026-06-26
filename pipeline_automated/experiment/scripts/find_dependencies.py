import json
import os
import re
from call_llm import call_llm, MODELS

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

        try:
            parsed = json.loads(result)
            result = json.dumps(parsed, indent=2)
        except json.JSONDecodeError:
            raw = re.sub(r',\s*([}\]])', r'\1', result)
            try:
                result = json.dumps(json.loads(raw), indent=2)
            except:
                pass

        out_path = os.path.join(output_dir, f"{model_name}_{req_name}.json")
        with open(out_path, "w") as f:
            f.write(result)
        print(f"  Saved to {out_path}")
