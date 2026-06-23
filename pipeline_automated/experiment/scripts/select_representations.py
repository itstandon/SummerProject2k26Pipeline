import requests
import json

def run_select_representations(req_text, prompt_path="prompts/select_representations.txt", output_path="results/representation_selection/llm_output.json"):
    with open(prompt_path) as f:
        prompt = f.read()

    prompt = prompt.replace("{REQ}", req_text)

    response = requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model":"qwen2.5:3b",
            "prompt":prompt,
            "stream":False
        },
        timeout=1800
    )

    result = response.json()["response"]

    try:
        parsed = json.loads(result)
        result = json.dumps(parsed, indent=2)
    except json.JSONDecodeError:
        pass  # save raw if model didn't return clean JSON

    with open(output_path, "w") as f:
        f.write(result)

    print(f"Representation selection complete. Output saved to {output_path}")

if __name__ == "__main__":
    with open("requirements/telescope_2_10.txt") as f:
        req = f.read()
    run_select_representations(req)