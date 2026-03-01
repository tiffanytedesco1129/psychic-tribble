"""
Fetch all messages from the authenticated user's Outlook mailbox via
Microsoft Graph API, handling pagination transparently.
"""

from typing import Generator
import requests

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# Only request the fields we actually need to reduce response size.
_SELECT = "from,toRecipients,ccRecipients,bccRecipients"
# Maximum allowed by Graph API per page.
_PAGE_SIZE = 999


def fetch_all_messages(token: str) -> Generator[dict, None, None]:
    """
    Yield every message object from all mail folders for the signed-in user.

    Each yielded dict has the shape returned by Graph API:
        {
            "from": {"emailAddress": {"name": ..., "address": ...}},
            "toRecipients": [{"emailAddress": {"name": ..., "address": ...}}, ...],
            "ccRecipients": [...],
            "bccRecipients": [...]
        }
    """
    headers = {"Authorization": f"Bearer {token}"}
    url = (
        f"{GRAPH_BASE}/me/messages"
        f"?$select={_SELECT}&$top={_PAGE_SIZE}"
    )

    page_num = 0
    total = 0
    while url:
        page_num += 1
        response = requests.get(url, headers=headers, timeout=30)

        if response.status_code == 401:
            raise RuntimeError(
                "Access token expired or invalid. Delete .token_cache.bin and re-run."
            )
        if not response.ok:
            raise RuntimeError(
                f"Graph API error {response.status_code}: {response.text}"
            )

        data = response.json()
        messages = data.get("value", [])
        total += len(messages)
        print(f"  Fetched page {page_num}: {len(messages)} messages (total so far: {total})")

        for msg in messages:
            yield msg

        # Follow the next page link if present.
        url = data.get("@odata.nextLink")

    print(f"  Done. Fetched {total} messages across {page_num} page(s).")
