"""
Check Report Email Sender
=========================
Sends the formatted donation report HTML email via the Microsoft Graph API
using the same MSAL authentication already set up in auth.py.

The email is sent FROM the authenticated user's mailbox TO the list of
recipients defined in the .env file (CHECK_REPORT_RECIPIENTS).

.env keys used
--------------
  CHECK_REPORT_RECIPIENTS
      Comma-separated list of email addresses who should receive the report.
      Example: tiffany@midnightmission.com,val@midnightmission.com

  CHECK_REPORT_CC  (optional)
      Comma-separated CC addresses.
"""

import os
import sys
import json

import requests
from dotenv import load_dotenv

load_dotenv()

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# Scopes required — must match what was consented to on the Azure app
SEND_SCOPES = ["Mail.Send", "User.Read"]


def _get_send_token() -> str:
    """
    Return an access token that includes Mail.Send.

    We re-use the same MSAL PublicClientApplication as auth.py but request
    the extended scopes needed for sending mail.  The user may be prompted
    once via device-code flow if the new scope has not been consented yet.
    """
    import msal

    client_id = os.getenv("AZURE_CLIENT_ID")
    tenant_id = os.getenv("AZURE_TENANT_ID")

    if not client_id or not tenant_id:
        sys.exit(
            "Error: AZURE_CLIENT_ID and AZURE_TENANT_ID must be set in .env\n"
            "Copy .env.example to .env and fill in your Azure app credentials."
        )

    cache_file = ".token_cache.bin"
    cache = msal.SerializableTokenCache()
    if os.path.exists(cache_file):
        with open(cache_file, "r") as f:
            cache.deserialize(f.read())

    authority = f"https://login.microsoftonline.com/{tenant_id}"
    app = msal.PublicClientApplication(client_id, authority=authority, token_cache=cache)

    accounts = app.get_accounts()
    result = None
    if accounts:
        result = app.acquire_token_silent(SEND_SCOPES, account=accounts[0])

    if not result:
        flow = app.initiate_device_flow(scopes=SEND_SCOPES)
        if "user_code" not in flow:
            sys.exit(f"Failed to create device flow: {flow.get('error_description')}")
        print("\n" + "=" * 60)
        print("ACTION REQUIRED: Re-authenticate to grant Mail.Send permission")
        print("=" * 60)
        print(flow["message"])
        print("=" * 60 + "\n")
        result = app.acquire_token_by_device_flow(flow)

    if cache.has_state_changed:
        with open(cache_file, "w") as f:
            f.write(cache.serialize())

    if "access_token" not in result:
        sys.exit(
            f"Authentication failed: {result.get('error_description', result.get('error'))}"
        )
    return result["access_token"]


def _parse_addresses(raw: str) -> list[dict]:
    """Turn 'a@b.com, c@d.com' into Graph API recipient objects."""
    result = []
    for addr in raw.split(","):
        addr = addr.strip()
        if addr:
            result.append({"emailAddress": {"address": addr}})
    return result


def send_report(subject: str, html_body: str, plain_body: str) -> None:
    """
    Send the donation report email.

    Parameters
    ----------
    subject:
        Email subject line.
    html_body:
        HTML version of the report.
    plain_body:
        Plain-text fallback (used for logging; Graph sends the HTML version).
    """
    recipients_raw = os.getenv("CHECK_REPORT_RECIPIENTS", "")
    cc_raw = os.getenv("CHECK_REPORT_CC", "")

    if not recipients_raw:
        sys.exit(
            "Error: CHECK_REPORT_RECIPIENTS is not set in .env\n"
            "Example:  CHECK_REPORT_RECIPIENTS=tiffany@midnightmission.com,val@midnightmission.com"
        )

    to_recipients = _parse_addresses(recipients_raw)
    cc_recipients = _parse_addresses(cc_raw) if cc_raw else []

    token = _get_send_token()

    message: dict = {
        "subject": subject,
        "body": {
            "contentType": "HTML",
            "content": html_body,
        },
        "toRecipients": to_recipients,
    }
    if cc_recipients:
        message["ccRecipients"] = cc_recipients

    payload = {"message": message, "saveToSentItems": True}

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    response = requests.post(
        f"{GRAPH_BASE}/me/sendMail",
        headers=headers,
        data=json.dumps(payload),
        timeout=30,
    )

    if response.status_code == 202:
        to_list = ", ".join(r["emailAddress"]["address"] for r in to_recipients)
        print(f"  Email sent successfully to: {to_list}")
    else:
        sys.exit(
            f"Failed to send email. Status: {response.status_code}\n"
            f"Response: {response.text}"
        )
