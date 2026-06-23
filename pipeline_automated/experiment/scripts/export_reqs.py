import os
import shutil
from collections import defaultdict

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
DB_NAME = os.getenv("DB_NAME")
COLLECTION_NAME = os.getenv("COLLECTION_NAME")

OUTPUT_DIR = "../generated_requirements"


############################################################

def section_key(number):
    return [int(x) for x in number.split(".")]


############################################################

def get_group(number, level):
    """
    level = 0 -> X

    level = 1 -> X.X

    level = 2 -> X.X.X

    level = 3 -> X.X.X.X
    """

    parts = number.split(".")

    keep = level + 1

    if len(parts) <= keep:
        return number

    return ".".join(parts[:keep])


############################################################

def export_reqs(level):

    client = MongoClient(
        MONGO_URI,
        serverSelectionTimeoutMS=10000,  # wait up to 10s
        connectTimeoutMS=10000,
    )

    db = client[DB_NAME]

    collection = db[COLLECTION_NAME]

    requirements = list(
        collection.find({}, {"_id": 0})
    )

    requirements.sort(
        key=lambda r: section_key(r["number"])
    )

    grouped = defaultdict(list)

    for req in requirements:

        group = get_group(req["number"], level)

        grouped[group].append(req)

    ########################################################

    if os.path.exists(OUTPUT_DIR):
        shutil.rmtree(OUTPUT_DIR)

    os.makedirs(OUTPUT_DIR)

    ########################################################

    for group, reqs in grouped.items():

        filename = os.path.join(
            OUTPUT_DIR,
            f"{group}.txt"
        )

        with open(
            filename,
            "w",
            encoding="utf-8"
        ) as f:

            f.write(f"SECTION {group}\n")
            f.write("=" * 80)
            f.write("\n\n")

            for req in reqs:

                f.write(f"REQ_ID : {req['req_id']}\n")
                f.write(f"Section: {req['number']}\n")
                f.write(f"Title  : {req['title']}\n")

                if req["content"]:
                    f.write("\n")
                    f.write(req["content"])
                    f.write("\n")

                f.write("\n")
                f.write("-" * 80)
                f.write("\n\n")

    print()
    print(f"Generated {len(grouped)} files.")
    print(f"Saved to {OUTPUT_DIR}")