import json
import os
from call_llm import call_llm, MODELS

def run_select_representations(req_text, req_filename,
                                prompt_path="prompts/select_representations.txt",
                                output_dir="results/representation_selection"):
    with open(prompt_path) as f:
        prompt = f.read()
    prompt = prompt.replace("{REQ}", req_text)

    os.makedirs(output_dir, exist_ok=True)

    for model in MODELS:
        print(f"  Selecting representations with {model}...")
        result = call_llm(prompt, model)

        try:
            parsed = json.loads(result)
            result = json.dumps(parsed, indent=2)
        except json.JSONDecodeError:
            pass

        model_name = model.replace(":", "_").replace("/", "_")
        req_name = os.path.splitext(req_filename)[0]
        out_path = os.path.join(output_dir, f"{model_name}_{req_name}.json")
        with open(out_path, "w") as f:
            f.write(result)
        print(f"  Saved to {out_path}")