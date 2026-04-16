import csv
from typing import Sequence
from contact_extractor import Contact


def export_csv(contacts: Sequence[Contact], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Name", "Email"])
        for c in contacts:
            writer.writerow([c.name, c.email])
    print(f"  Wrote {len(contacts)} contacts to {path}")


def export_vcf(contacts: Sequence[Contact], path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for c in contacts:
            parts = c.name.split(None, 1)
            first = parts[0] if parts else ""
            last = parts[1] if len(parts) > 1 else ""
            fn = c.name or c.email
            n = f"{last};{first};;;" if c.name else ";;;;"
            f.write(
                f"BEGIN:VCARD\r\n"
                f"VERSION:3.0\r\n"
                f"FN:{fn}\r\n"
                f"N:{n}\r\n"
                f"EMAIL;TYPE=INTERNET:{c.email}\r\n"
                f"END:VCARD\r\n"
            )
    print(f"  Wrote {len(contacts)} contacts to {path}")
