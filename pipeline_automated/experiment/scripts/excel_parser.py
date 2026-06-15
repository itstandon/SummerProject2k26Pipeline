import pandas as pd
import re
import json

# Load Excel
df = pd.read_excel("scripts/GeminiReqs.xlsx")

# Dictionary:
# {
#   "2.10": {
#       "title": "...",
#       "content": [...]
#   }
# }
sections = {}

current_section = None

# Match only X.Y headings
section_pattern = re.compile(r'^(\d+\.\d+)\s+(.*)')

for _, row in df.iterrows():

    # Get all non-empty cells in the row
    values = [
        str(v).strip()
        for v in row
        if pd.notna(v) and str(v).strip()
    ]

    for value in values:

        match = section_pattern.match(value)

        if match:
            section_id = match.group(1)
            title = match.group(2)

            current_section = section_id

            sections[current_section] = {
                "title": title,
                "content": []
            }

        elif current_section:
            sections[current_section]["content"].append(value)

# Convert content list into text
for sec in sections:
    sections[sec]["content"] = "\n".join(
        sections[sec]["content"]
    )

# Save JSON
with open(
    "results/json_parsed/requirements_by_section.json",
    "w",
    encoding="utf-8"
) as f:
    json.dump(
        sections,
        f,
        indent=2,
        ensure_ascii=False
    )

print(
    f"Extracted {len(sections)} sections."
)