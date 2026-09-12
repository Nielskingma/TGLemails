#!/usr/bin/env python3
"""Google OAuth zonder PKCE — URL kopiëren en code plakken."""
import json, warnings, requests
warnings.filterwarnings("ignore")
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode

CREDENTIALS = Path.home() / ".config" / "gspread" / "credentials.json"
TOKEN_OUT = Path.home() / ".config" / "gspread" / "authorized_user.json"

creds_data = json.loads(CREDENTIALS.read_text())["installed"]
CLIENT_ID = creds_data["client_id"]
CLIENT_SECRET = creds_data["client_secret"]
REDIRECT_URI = "http://localhost"
SCOPES = "https://www.googleapis.com/auth/drive https://spreadsheets.google.com/feeds"

auth_url = (
    "https://accounts.google.com/o/oauth2/auth?"
    + urlencode({
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent",
    })
)

print("=== Stap 1: open deze URL in je browser ===\n")
print(auth_url)
print()
print("=== Stap 2: log in en geef toegang ===")
print("Browser probeert door te sturen naar http://localhost — dat mislukt, dat is OK.")
print()
print("=== Stap 3: kopieer de VOLLEDIGE URL uit de adresbalk ===")
print("(begint met: http://localhost/?code=...)\n")

redirect_url = input("Plak URL hier: ").strip()

parsed = urlparse(redirect_url)
params = parse_qs(parsed.query)
code = params.get("code", [None])[0]
if not code:
    print("Geen code gevonden. Controleer de URL.")
    exit(1)

resp = requests.post("https://oauth2.googleapis.com/token", data={
    "code": code,
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "redirect_uri": REDIRECT_URI,
    "grant_type": "authorization_code",
})
token = resp.json()
if "error" in token:
    print("Fout:", token)
    exit(1)

token_data = {
    "token": token.get("access_token"),
    "refresh_token": token.get("refresh_token"),
    "token_uri": "https://oauth2.googleapis.com/token",
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "scopes": SCOPES.split(),
    "type": "authorized_user",
}
TOKEN_OUT.write_text(json.dumps(token_data, indent=2))
print(f"\nToken opgeslagen. Voer nu uit:\n  python3 nieuw_kwartaal.py \"Q2 2026\"")
