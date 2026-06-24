import requests

MODELS = [
    "qwen2.5:3b",
    "llama3.2:3b",
    #add models
]

def call_llm(prompt, model, timeout=1800):
    response = requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_ctx": 2048,
                "num_predict": 1024,
            }
        },
        timeout=timeout
    )
    return response.json()["response"]