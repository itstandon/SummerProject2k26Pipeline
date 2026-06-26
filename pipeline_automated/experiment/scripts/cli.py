import os
from export_reqs import export_reqs
from select_representations import run_select_representations
from find_dependencies import run_find_dependencies
from generate_testcases import run_generate_testcases
from compare_with_expert import run_compare_with_expert
from coverage_analysis import run_coverage_analysis



def post_generation_menu():
    while True:
        print("\n" + "=" * 50)
        print("What would you like to do next?")
        print("=" * 50)
        print("1 -> Back and forth")
        print("2 -> Compare representations with expert")
        print("3 -> Coverage analysis")
        print("q -> Quit menu")

        choice = input("\nChoice: ").strip().lower()

        if choice == "1":
            print("\n(Not implemented yet.)")
        elif choice == "2":
            run_compare_with_expert()
        elif choice == "3":
            run_coverage_analysis()
        elif choice == "q":
            break
        else:
            print("Please enter 1, 2, 3, or q.")


def main():

    print("=" * 50)
    print("Requirement Export & Select Utility")
    print("=" * 50)


    while True:
        print("\nChoose grouping level:\n")

        print("0 -> X")
        print("1 -> X.X")
        print("2 -> X.X.X")
        print("3 -> X.X.X.X")

        while True:
            try:
                inp = input("\nGrouping level: ").strip()
                if inp.lower() == "q":
                    print("Exiting.")
                    return
                level = int(inp)
                if level < 0:
                    raise ValueError
                break
            except ValueError:
                print("Please enter a non-negative integer or 'q' to quit.")

        export_reqs(level)
        
        # List generated requirements
        req_dir = "../generated_requirements"
        if not os.path.exists(req_dir):
            print(f"Error: Directory {req_dir} not found.")
            continue

        files = sorted([f for f in os.listdir(req_dir) if os.path.isfile(os.path.join(req_dir, f))])
        
        if not files:
            print(f"No files found in {req_dir}.")
            continue

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
        run_select_representations(req_text, selected_file)
        print("Representation selection complete.")

        print("\nFinding dependencies between requirements...")
        run_find_dependencies(req_text, selected_file)
        print("Dependency analysis complete.")

        # Step 2: generate test cases using the mappings
        print("\nGenerating test cases for selected representations...")
        run_generate_testcases(req_text, selected_file)
        print("\nAll test cases generated in results/test_cases/")
        post_generation_menu()


if __name__ == "__main__":
    main()