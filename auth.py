"""
Microsoft Graph API authentication using MSAL device code flow.

The device code flow lets the user authenticate in their browser without
requiring a redirect URI, making it ideal for CLI tools.
"""

import os
import sys
import msal
from dotenv import load_dotenv

load_dotenv()

SCOPES = ["Mail.Read", "User.Read"]
GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# MSAL caches tokens to disk so the user only needs to authenticate once.
_TOKEN_CACHE_FILE = ".token_cache.bin"


def _load_cache() -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    if os.path.exists(_TOKEN_CACHE_FILE):
        with open(_TOKEN_CACHE_FILE, "r") as f:
            cache.deserialize(f.read())
    return cache


def _save_cache(cache: msal.SerializableTokenCache) -> None:
    if cache.has_state_changed:
        with open(_TOKEN_CACHE_FILE, "w") as f:
            f.write(cache.serialize())


def _build_app(cache: msal.SerializableTokenCache) -> msal.PublicClientApplication:
    client_id = os.getenv("AZURE_CLIENT_ID")
    tenant_id = os.getenv("AZURE_TENANT_ID")

    if not client_id or not tenant_id:
        sys.exit(
            "Error: AZURE_CLIENT_ID and AZURE_TENANT_ID must be set.\n"
            "Copy .env.example to .env and fill in your Azure app credentials."
        )

    authority = f"https://login.microsoftonline.com/{tenant_id}"
    return msal.PublicClientApplication(
        client_id, authority=authority, token_cache=cache
    )


def get_access_token() -> str:
    """
    Return a valid access token, prompting the user to authenticate if needed.
    Tokens are cached to disk and reused across runs.
    """
    cache = _load_cache()
    app = _build_app(cache)

    # Try to get a token silently from cache first.
    accounts = app.get_accounts()
    result = None
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])

    # Fall back to interactive device code flow.
    if not result:
        flow = app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            sys.exit(f"Failed to create device flow: {flow.get('error_description')}")

        print("\n" + "=" * 60)
        print("ACTION REQUIRED: Authenticate with Microsoft")
        print("=" * 60)
        print(flow["message"])
        print("=" * 60 + "\n")

        result = app.acquire_token_by_device_flow(flow)

    _save_cache(cache)

    if "access_token" not in result:
        sys.exit(
            f"Authentication failed: {result.get('error_description', result.get('error'))}"
        )

    return result["access_token"]
