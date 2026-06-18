import pandas as pd
import json
import re

# -----------------------
# Expert representations
# -----------------------

expert = set(
    pd.read_csv(
        "results/representation_selection/expert_ground_truth.csv"
    )["representation"]
)

# -----------------------
# LLM representations
# -----------------------

with open(
    "results/representation_selection/llm_output.json"
) as f:
    text = f.read()

match = re.search(
    r'\{[\s\S]*\}',
    text
)

if not match:
    raise Exception("No JSON found in llm_output.json")

data = json.loads(
    match.group(0)
)

llm = set(
    data["selected_representations"]
)

# -----------------------
# Metrics
# -----------------------

intersection = expert & llm
union = expert | llm

precision = len(intersection) / len(llm)
recall = len(intersection) / len(expert)
jaccard = len(intersection) / len(union)

print("\nExpert:")
print(expert)

print("\nLLM:")
print(llm)

print("\nOverlap:")
print(intersection)

print("\nPrecision:", round(precision, 3))
print("Recall:", round(recall, 3))
print("Jaccard:", round(jaccard, 3))