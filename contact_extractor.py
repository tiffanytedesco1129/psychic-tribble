from dataclasses import dataclass
from typing import Iterable


@dataclass
class Contact:
    email: str
    name: str = ""


def _extract_address(email_address_obj: dict) -> tuple[str, str]:
    address = (email_address_obj.get("address") or "").strip().lower()
    name = (email_address_obj.get("name") or "").strip()
    return address, name


def extract_contacts(messages: Iterable[dict]) -> list[Contact]:
    seen: dict[str, Contact] = {}

    def _add(email_address_obj: dict) -> None:
        address, name = _extract_address(email_address_obj)
        if not address or "@" not in address:
            return
        if address not in seen:
            seen[address] = Contact(email=address, name=name)
        elif not seen[address].name and name:
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
