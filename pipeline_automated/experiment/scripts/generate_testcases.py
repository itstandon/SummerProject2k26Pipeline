import requests
import json
import os
import re

with open(
    "requirements/telescope_2_10.txt"
) as f:
    req = f.read()

with open(
    "results/representation_selection/llm_output.json"
) as f:
    text = f.read()

match = re.search(
    r'\{[\s\S]*\}',
    text
)

if not match:
    raise Exception("No JSON found")

data = json.loads(match.group(0))

representations = data["selected_representations"]

with open(
    "prompts/generate_testcases.txt"
) as f:
    template = f.read()

os.makedirs(
    "results/test_cases",
    exist_ok=True
)

for rep in representations:

    prompt = template

    prompt = prompt.replace(
        "{REQ}",
        req
    )

    prompt = prompt.replace(
        "{REP}",
        rep
    )

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

    filename = rep.replace(" ","_")

    with open(
        f"results/test_cases/{filename}.txt",
        "w"
    ) as out:

        out.write(result)

    print(rep,"done")