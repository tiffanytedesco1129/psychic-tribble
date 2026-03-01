"""
Extract and deduplicate contacts from Graph API message objects.

A contact is keyed by lowercase email address. When the same address
appears with different display names, the first non-empty name wins.
"""

from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class Contact:
    email: str
    name: str = ""


def _extract_address(email_address_obj: dict) -> tuple[str, str]:
    """Return (address, name) from a Graph API emailAddress object."""
    address = (email_address_obj.get("address") or "").strip().lower()
    name = (email_address_obj.get("name") or "").strip()
    return address, name


def extract_contacts(messages: Iterable[dict]) -> list[Contact]:
    """
    Walk every message and collect unique contacts from all recipient fields.
    Returns a list of Contact objects sorted by email address.
    """
    # Map: lowercase email -> Contact
    seen: dict[str, Contact] = {}

    def _add(email_address_obj: dict) -> None:
        address, name = _extract_address(email_address_obj)
        if not address or "@" not in address:
            return
        if address not in seen:
            seen[address] = Contact(email=address, name=name)
        elif not seen[address].name and name:
            # Fill in a name we didn't have before.
            seen[address].name = name

    for msg in messages:
        sender = msg.get("from", {}).get("emailAddress")
        if sender:
            _add(sender)

        for field_name in ("toRecipients", "ccRecipients", "bccRecipients"):
            for recipient in msg.get(field_name) or []:
                addr_obj = recipient.get("emailAddress")
                if addr_obj:
                    _add(addr_obj)

    return sorted(seen.values(), key=lambda c: c.email)
