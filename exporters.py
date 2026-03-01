"""
Export a list of Contact objects to CSV and/or vCard (.vcf) files.
"""

import csv
from typing import Sequence
from contact_extractor import Contact


def export_csv(contacts: Sequence[Contact], path: str) -> None:
    """Write contacts to a CSV file with columns: name, email."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Name", "Email"])
        for c in contacts:
            writer.writerow([c.name, c.email])
    print(f"  Wrote {len(contacts)} contacts to {path}")


def export_vcf(contacts: Sequence[Contact], path: str) -> None:
    """Write contacts to a vCard 3.0 (.vcf) file."""
    with open(path, "w", encoding="utf-8") as f:
        for c in contacts:
            # Split display name into first/last if there's a space.
            parts = c.name.split(None, 1)
            first = parts[0] if parts else ""
            last = parts[1] if len(parts) > 1 else ""

            f.write("BEGIN:VCARD\r\n")
            f.write("VERSION:3.0\r\n")
            if c.name:
                f.write(f"FN:{c.name}\r\n")
                f.write(f"N:{last};{first};;;\r\n")
            else:
                f.write(f"FN:{c.email}\r\n")
                f.write("N:;;;;\r\n")
            f.write(f"EMAIL;TYPE=INTERNET:{c.email}\r\n")
            f.write("END:VCARD\r\n")
    print(f"  Wrote {len(contacts)} contacts to {path}")
