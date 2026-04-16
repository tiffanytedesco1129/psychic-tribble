"""
Read all mail items from a local Outlook .pst file using Windows COM automation.
Requires Outlook to be installed. No network access or credentials needed.
"""

import win32com.client
from typing import Generator

_MAIL_CLASS = 43  # olMail


def iter_messages(pst_path: str) -> Generator[dict, None, None]:
    outlook = win32com.client.Dispatch("Outlook.Application")
    ns = outlook.GetNamespace("MAPI")
    ns.AddStore(pst_path)
    root = ns.Folders.Item(ns.Folders.Count)
    try:
        yield from _walk_folder(root)
    finally:
        ns.RemoveStore(root)


def _walk_folder(folder) -> Generator[dict, None, None]:
    for item in folder.Items:
        try:
            if item.Class == _MAIL_CLASS:
                yield _normalize(item)
        except Exception:
            pass
    for subfolder in folder.Folders:
        yield from _walk_folder(subfolder)


def _normalize(item) -> dict:
    msg = {"from": None, "toRecipients": [], "ccRecipients": [], "bccRecipients": []}
    type_map = {1: "toRecipients", 2: "ccRecipients", 3: "bccRecipients"}

    addr = item.SenderEmailAddress or ""
    if "@" in addr:
        msg["from"] = {"emailAddress": {"address": addr, "name": item.SenderName or ""}}

    for i in range(1, item.Recipients.Count + 1):
        try:
            r = item.Recipients.Item(i)
            r_addr = r.Address or ""
            if "@" in r_addr:
                field = type_map.get(r.Type, "toRecipients")
                msg[field].append({"emailAddress": {"address": r_addr, "name": r.Name or ""}})
        except Exception:
            pass

    return msg
