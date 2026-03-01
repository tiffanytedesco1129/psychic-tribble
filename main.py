"""
Outlook Contact List Exporter
=============================
Reads all messages from your Outlook/Microsoft 365 mailbox via the
Microsoft Graph API, extracts unique contacts from every sender and
recipient field, and exports them as:

  contacts.csv  — importable into Excel, Google Contacts, etc.
  contacts.vcf  — importable into phone contacts, Apple Contacts, etc.

Usage
-----
1. Copy .env.example to .env and fill in AZURE_CLIENT_ID / AZURE_TENANT_ID.
2. Install dependencies:
       pip install -r requirements.txt
3. Run:
       python main.py

   On the first run you will be asked to open a URL and enter a short code
   to authenticate. After that, your token is cached in .token_cache.bin so
   subsequent runs skip the login step.

Optional flags
--------------
  --csv PATH    Custom output path for the CSV file  (default: contacts.csv)
  --vcf PATH    Custom output path for the vCard file (default: contacts.vcf)
"""

import argparse
import sys

from auth import get_access_token
from email_fetcher import fetch_all_messages
from contact_extractor import extract_contacts
from exporters import export_csv, export_vcf


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export all contacts from your Outlook emails."
    )
    parser.add_argument(
        "--csv",
        default="contacts.csv",
        metavar="PATH",
        help="Output path for the CSV file (default: contacts.csv)",
    )
    parser.add_argument(
        "--vcf",
        default="contacts.vcf",
        metavar="PATH",
        help="Output path for the vCard file (default: contacts.vcf)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print("Step 1/4  Authenticating with Microsoft...")
    token = get_access_token()
    print("          Authenticated.\n")

    print("Step 2/4  Fetching emails from your mailbox...")
    messages = fetch_all_messages(token)

    print("\nStep 3/4  Extracting and deduplicating contacts...")
    contacts = extract_contacts(messages)
    print(f"          Found {len(contacts)} unique contact(s).\n")

    if not contacts:
        print("No contacts found. Nothing to export.")
        sys.exit(0)

    print("Step 4/4  Exporting contacts...")
    export_csv(contacts, args.csv)
    export_vcf(contacts, args.vcf)

    print(
        f"\nDone! {len(contacts)} contacts exported.\n"
        f"  CSV   -> {args.csv}\n"
        f"  vCard -> {args.vcf}"
    )


if __name__ == "__main__":
    main()
