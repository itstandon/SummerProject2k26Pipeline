import pandas as pd

CSV_FILE = "results/coverage/coverage_mapping.csv"

# Load coverage matrix
df = pd.read_csv(CSV_FILE)

req_cols = [c for c in df.columns if c.startswith("R")]

print("=" * 60)
print("COVERAGE ANALYSIS")
print("=" * 60)

# --------------------------------------------------
# 1. Coverage per Representation
# --------------------------------------------------

print("\nCoverage Per Representation")
print("-" * 60)

representation_results = []

for rep in df["representation"].unique():

    subset = df[df["representation"] == rep]

    covered = (subset[req_cols].sum(axis=0) > 0).sum()

    total = len(req_cols)

    coverage = round((covered / total) * 100, 2)

    representation_results.append(
        (rep, covered, total, coverage)
    )

representation_results.sort(
    key=lambda x: x[3],
    reverse=True
)

for rep, covered, total, coverage in representation_results:

    print(
        f"{rep:20s} "
        f"{covered}/{total} "
        f"({coverage:.2f}%)"
    )

# --------------------------------------------------
# 2. Requirement Coverage
# --------------------------------------------------

print("\nRequirement Coverage")
print("-" * 60)

for req in req_cols:

    count = df[req].sum()

    print(
        f"{req}: covered by {count} test cases"
    )

# --------------------------------------------------
# 3. Missing Requirements per Representation
# --------------------------------------------------

print("\nMissing Requirements")
print("-" * 60)

for rep in df["representation"].unique():

    subset = df[df["representation"] == rep]

    missing = []

    for req in req_cols:

        if subset[req].sum() == 0:
            missing.append(req)

    print(
        f"\n{rep}:"
    )

    if missing:
        print(
            "Missing ->",
            ", ".join(missing)
        )
    else:
        print(
            "All requirements covered"
        )

# --------------------------------------------------
# 4. Overall Coverage
# --------------------------------------------------

overall_covered = (
    df[req_cols].sum(axis=0) > 0
).sum()

overall_total = len(req_cols)

overall_percent = round(
    (overall_covered / overall_total) * 100,
    2
)

print("\nOverall Coverage")
print("-" * 60)

print(
    f"{overall_covered}/{overall_total} "
    f"({overall_percent:.2f}%)"
)

# --------------------------------------------------
# 5. Best Representation
# --------------------------------------------------

best = representation_results[0]

print("\nBest Representation")
print("-" * 60)

print(
    f"{best[0]} "
    f"with {best[3]:.2f}% coverage"
)

print("\nDone.")