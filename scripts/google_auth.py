#!/usr/bin/env python3
"""Generate Google Drive OAuth credentials for the hosted bot.

Run locally after downloading a Desktop OAuth client JSON from Google Cloud.
The script prints base64 environment-variable values. Treat both as secrets.
"""

from __future__ import annotations

import argparse
import base64
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Create Personal Vault Google Drive OAuth tokens")
    parser.add_argument("--credentials", default="credentials.json", help="Downloaded Desktop OAuth client JSON")
    parser.add_argument("--token-output", default="google_token.json", help="Local token JSON output")
    parser.add_argument("--no-browser", action="store_true", help="Print authorization URL instead of opening a browser")
    args = parser.parse_args()

    credentials_path = Path(args.credentials)
    if not credentials_path.is_file():
        raise SystemExit(f"OAuth client file not found: {credentials_path}")

    flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
    credentials = flow.run_local_server(
        host="127.0.0.1",
        port=0,
        open_browser=not args.no_browser,
        access_type="offline",
        prompt="consent",
    )
    token_json = credentials.to_json()
    token_path = Path(args.token_output)
    token_path.write_text(token_json, encoding="utf-8")

    client_b64 = base64.b64encode(credentials_path.read_bytes()).decode("ascii")
    token_b64 = base64.b64encode(token_json.encode("utf-8")).decode("ascii")

    print("\nAdd these two values to your hosting provider's environment variables.")
    print("Do not share them or commit them to GitHub.\n")
    print(f"GOOGLE_OAUTH_CLIENT_B64={client_b64}")
    print(f"GOOGLE_OAUTH_TOKEN_B64={token_b64}")
    print(f"\nLocal token saved at: {token_path.resolve()}")


if __name__ == "__main__":
    main()
