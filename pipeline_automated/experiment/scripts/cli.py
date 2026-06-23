import os
from export_reqs import export_reqs
from select_representations import run_select_representations
from generate_testcases import run_generate_testcases


def main():

    print("=" * 50)
    print("Requirement Export & Select Utility")
    print("=" * 50)

    print("\nChoose grouping level:\n")

    print("0 -> X")
    print("1 -> X.X")
    print("2 -> X.X.X")
    print("3 -> X.X.X.X")

    while True:

        try:
            level = int(input("\nGrouping level: "))

            if level < 0:
                raise ValueError

            break

        except ValueError:
            print("Please enter a non-negative integer.")

    export_reqs(level)
    
    # List generated requirements
    req_dir = "../generated_requirements"
    if not os.path.exists(req_dir):
        print(f"Error: Directory {req_dir} not found.")
        return

    files = sorted([f for f in os.listdir(req_dir) if os.path.isfile(os.path.join(req_dir, f))])
    
    if not files:
        print(f"No files found in {req_dir}.")
        return

    print("\nGenerated requirement files:")
    for i, f in enumerate(files):
        print(f"{i + 1} -> {f}")

    while True:
        try:
            choice = int(input("\nSelect a file by number for representation selection: "))
            if 1 <= choice <= len(files):
                selected_file = files[choice - 1]
                break
            else:
                print(f"Please enter a number between 1 and {len(files)}.")
        except ValueError:
            print("Please enter a valid integer.")

    file_path = os.path.join(req_dir, selected_file)
    print(f"\nReading {file_path} for representation selection...")
    
    with open(file_path, "r", encoding="utf-8") as f:
        req_text = f.read()

    # Step 1: select representations
    print("Running representation selection via LLM...")
    run_select_representations(req_text)
    print("Representation selection complete.")

    # Step 2: generate test cases using the mappings
    print("\nGenerating test cases for selected representations...")
    run_generate_testcases(req_text)
    print("\nAll test cases generated in results/test_cases/")


if __name__ == "__main__":
    main()