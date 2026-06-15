import requests

response = requests.post(
    "http://localhost:11434/api/generate",
    json={
        "model": "llama3.1",
        "prompt": "What is 2+2?",
        "stream": False
    },
    timeout=120
)

print(response.json()["response"])