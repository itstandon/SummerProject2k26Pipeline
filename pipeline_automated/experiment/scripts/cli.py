from export_reqs import export_reqs


def main():

    print("=" * 50)
    print("Requirement Export Utility")
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


if __name__ == "__main__":
    main()