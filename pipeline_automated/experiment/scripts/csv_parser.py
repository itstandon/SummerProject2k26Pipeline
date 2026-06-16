import pandas as pd
import re
from pymongo import MongoClient

import os
from dotenv import load_dotenv

import pandas as pd
import re
from pymongo import MongoClient

load_dotenv()

########################################
# CONFIG
########################################

EXCEL_FILE = "GeminiReqs.xlsx"

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME")
COLLECTION_NAME = os.getenv("COLLECTION_NAME")

########################################
# HELPERS
########################################

def get_parent(req_num):
    parts = req_num.split(".")

    if len(parts) <= 1:
        return None

    return ".".join(parts[:-1])


def get_ancestors(req_num):
    parts = req_num.split(".")
    ancestors = []

    for i in range(1, len(parts)):
        ancestors.append(".".join(parts[:i]))

    return ancestors


########################################
# LOAD EXCEL
########################################

print(f"Loading {EXCEL_FILE}...")

df = pd.read_excel(EXCEL_FILE, header=None)

########################################
# REGEX
########################################

req_id_pattern = re.compile(r"REQ_\d+")

section_pattern = re.compile(
    r"^(\d+(?:\.\d+)*)\s+(.*)$"
)

########################################
# PARSE REQUIREMENTS
########################################

requirements = {}

current_req = None

for _, row in df.iterrows():

    values = [
        str(v).strip()
        for v in row
        if pd.notna(v) and str(v).strip()
    ]

    if not values:
        continue

    req_id = None
    text_values = []

    for value in values:

        if req_id_pattern.fullmatch(value):
            req_id = value
        else:
            text_values.append(value)

    if not text_values:
        continue

    ####################################################
    # Find heading in any cell
    ####################################################

    heading_found = False

    for text in text_values:

        match = section_pattern.match(text)

        if match:

            req_num = match.group(1)
            title = match.group(2)

            requirements[req_num] = {
                "_id": req_id if req_id else req_num,
                "req_id": req_id,
                "number": req_num,
                "title": title,
                "content": "",
                "parent": None,
                "ancestors": [],
                "children": []
            }

            current_req = req_num
            heading_found = True
            break

    ####################################################
    # Content row
    ####################################################

    if not heading_found and current_req:

        content = " ".join(text_values)

        if requirements[current_req]["content"]:
            requirements[current_req]["content"] += "\n"

        requirements[current_req]["content"] += content

########################################
# LOOKUP TABLE
########################################

number_to_reqid = {
    req["number"]: req["req_id"]
    for req in requirements.values()
}

########################################
# BUILD HIERARCHY
########################################

for req_num, req in requirements.items():

    parent_num = get_parent(req_num)

    if parent_num and parent_num in requirements:

        req["parent"] = {
            "number": parent_num,
            "req_id": number_to_reqid[parent_num]
        }

    else:

        req["parent"] = None

    req["ancestors"] = []

    for ancestor_num in get_ancestors(req_num):

        if ancestor_num in requirements:

            req["ancestors"].append({
                "number": ancestor_num,
                "req_id": number_to_reqid[ancestor_num]
            })

########################################
# BUILD CHILDREN
########################################

for req_num, req in requirements.items():

    if req["parent"] is None:
        continue

    parent_num = req["parent"]["number"]

    requirements[parent_num]["children"].append({
        "number": req_num,
        "req_id": req["req_id"]
    })

########################################
# DEBUG PARSER
########################################

print(f"\nRequirements found: {len(requirements)}")

for k in list(requirements.keys())[:10]:
    print(
        k,
        "->",
        requirements[k]["title"]
    )

########################################
# CONNECT TO MONGODB
########################################

print("Connecting to MongoDB Atlas...")

client = MongoClient(MONGO_URI)

try:
    client.admin.command("ping")
    print("Connected successfully.")
except Exception as e:
    print("MongoDB connection failed:")
    print(e)
    raise

########################################
# DATABASE + COLLECTION
########################################

db = client[DB_NAME]

collection = db[COLLECTION_NAME]

########################################
# INDEXES
########################################

collection.create_index("number", unique=True)
collection.create_index("req_id")
collection.create_index("parent.number")
collection.create_index("parent.req_id")

collection.create_index("ancestors.number")
collection.create_index("ancestors.req_id")

collection.create_index("children.number")
collection.create_index("children.req_id")

########################################
# REPLACE EXISTING DATA
########################################

print("Clearing collection...")

collection.delete_many({})

########################################
# INSERT DATA
########################################

if requirements:

    result = collection.insert_many(
        list(requirements.values())
    )

    print(
        f"Inserted {len(result.inserted_ids)} requirements."
    )

else:

    print("No requirements found.")

########################################
# VERIFY
########################################

count = collection.count_documents({})

print(f"MongoDB document count: {count}")

if requirements:

    sample = next(iter(requirements.values()))

    print("\nExample document:\n")
    print(sample)

print("\nDone.")