import requests
import json
import os
import re

def run_generate_testcases(req_text, llm_output_path="results/representation_selection/llm_output.json",
                            prompt_path="prompts/generate_testcases.txt",
                            output_dir="results/test_cases"):

    with open(llm_output_path) as f:
        text = f.read()

    match = re.search(r'\{[\s\S]*\}', text)
    if not match:
        raise Exception("No JSON found in llm_output.json")

    data = json.loads(match.group(0))
    representations = data["selected_representations"]

    with open(prompt_path) as f:
        template = f.read()

    os.makedirs(output_dir, exist_ok=True)

    for rep in representations:
        # Handle both old format (string) and new format (object with mapping)
        if isinstance(rep, dict):
            rep_name = rep["representation"]
            excerpt = rep.get("requirement_excerpt", req_text)
            reason = rep.get("reason", "")
            rep_context = f"{rep_name}\nRelevant requirement: {excerpt}\nReason: {reason}"
        else:
            rep_name = rep
            rep_context = rep

        prompt = template
        prompt = prompt.replace("{REQ}", req_text)
        prompt = prompt.replace("{REP}", rep_context)

        print(f"  Generating test cases for: {rep_name}...")
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "qwen2.5:3b",
                "prompt": prompt,
                "stream": False,
                "options": {
                    "num_ctx": 2048,
                    "num_predict": 1024,
                }
            },
            timeout=1800
        )

        result = response.json()["response"]
        filename = rep_name.replace(" ", "_")
        with open(f"{output_dir}/{filename}.txt", "w") as out:
            out.write(result)
        print(f"  {rep_name} done.")