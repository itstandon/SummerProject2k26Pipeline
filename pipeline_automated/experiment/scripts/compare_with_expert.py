import pandas as pd
import json
import re
import os
import glob


def run_compare_with_expert():
    rep_dir = "results/representation_selection"
    expert_path = os.path.join(rep_dir, "expert_ground_truth.csv")

    if not os.path.exists(expert_path):
        print(f"\nError: {expert_path} not found.")
        return

    # Find all LLM output files matching {model_name}_{req_no}.json
    candidates = sorted(glob.glob(os.path.join(rep_dir, "*.json")))
    if not candidates:
        print(f"\nError: no LLM output JSON files found in {rep_dir}")
        return

    print("\nAvailable LLM output files:")
    for i, f in enumerate(candidates):
        print(f"{i + 1} -> {os.path.basename(f)}")

    while True:
        try:
            choice = int(input("\nSelect a file by number: "))
            if 1 <= choice <= len(candidates):
                llm_path = candidates[choice - 1]
                break
            print(f"Please enter a number between 1 and {len(candidates)}.")
        except ValueError:
            print("Please enter a valid integer.")

    expert = set(pd.read_csv(expert_path)["representation"])

    with open(llm_path) as f:
        text = f.read()

    match = re.search(r'\{[\s\S]*\}', text)
    if not match:
        print(f"\nError: No JSON found in {llm_path}")
        return

    data = json.loads(match.group(0))

    # Extract just the "representation" field from each dict entry
    llm = set(item["representation"] for item in data["selected_representations"])

    intersection = expert & llm
    union = expert | llm
    precision = len(intersection) / len(llm) if llm else 0
    recall = len(intersection) / len(expert) if expert else 0
    jaccard = len(intersection) / len(union) if union else 0

    print(f"\nComparing: {os.path.basename(llm_path)}")
    print("\nExpert:")
    print(expert)
    print("\nLLM:")
    print(llm)
    print("\nOverlap:")
    print(intersection)
    print("\nPrecision:", round(precision, 3))
    print("Recall:", round(recall, 3))
    print("Jaccard:", round(jaccard, 3))