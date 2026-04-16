import argparse
import sys

from pst_reader import iter_messages
from contact_extractor import extract_contacts
from exporters import export_csv, export_vcf


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract contacts from an Outlook .pst file and export to CSV and vCard."
    )
    parser.add_argument(
        "pst",
        metavar="PST_FILE",
        help="Path to your exported Outlook .pst file",
    )
    parser.add_argument("--csv", default="contacts.csv", metavar="PATH",
                        help="Output CSV path (default: contacts.csv)")
    parser.add_argument("--vcf", default="contacts.vcf", metavar="PATH",
                        help="Output vCard path (default: contacts.vcf)")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print(f"Step 1/3  Opening {args.pst} ...")
    messages = iter_messages(args.pst)

    print("Step 2/3  Extracting and deduplicating contacts...")
    contacts = extract_contacts(messages)
    print(f"          Found {len(contacts)} unique contact(s).\n")

    if not contacts:
        print("No contacts found. Nothing to export.")
        sys.exit(0)

    print("Step 3/3  Exporting contacts...")
    export_csv(contacts, args.csv)
    export_vcf(contacts, args.vcf)

    print(
        f"\nDone! {len(contacts)} contacts exported.\n"
        f"  CSV   -> {args.csv}\n"
        f"  vCard -> {args.vcf}"
    )


if __name__ == "__main__":
    main()
