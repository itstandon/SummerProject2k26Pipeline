import requests
import json

with open("requirements/telescope_2_10.txt") as f:
    req = f.read()

with open("prompts/select_representations.txt") as f:
    prompt = f.read()

prompt = prompt.replace("{REQ}", req)

response = requests.post(
    "http://localhost:11434/api/generate",
    json={
        "model":"llama3.1",
        "prompt":prompt,
        "stream":False
    },
    timeout=1800
)

result = response.json()["response"]

with open(
    "results/representation_selection/llm_output.json",
    "w"
) as f:
    f.write(result)

print("Representation selection complete.")