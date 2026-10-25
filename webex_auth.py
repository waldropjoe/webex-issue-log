import os
import json
import secrets
import requests
import time
from urllib.parse import urlencode
from dotenv import load_dotenv

load_dotenv()

client_id = os.getenv("WEBEX_CLIENT_ID")
client_secret = os.getenv("WEBEX_CLIENT_SECRET")
redirect_uri = os.getenv("WEBEX_REDIRECT_URI")

SCOPES = "spark:messages_read spark:rooms_read spark:people_read"
TOKEN_FILE = "tokens.json"


def build_authorization_url():
    state = secrets.token_urlsafe(16)
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": SCOPES,
        "state": state,
    }
    return "https://webexapis.com/v1/authorize?" + urlencode(params)


def exchange_code_for_tokens(code):
    response = requests.post(
        "https://webexapis.com/v1/access_token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        },
    )
    response.raise_for_status()
    return response.json()


def save_tokens(tokens):
    tokens["access_token_expires_at"] = time.time() + tokens["expires_in"]
    with open(TOKEN_FILE, "w") as f:
        json.dump(tokens, f, indent=2)


def load_tokens():
    with open(TOKEN_FILE) as f:
        return json.load(f)


def refresh_access_token():
    tokens = load_tokens()
    response = requests.post(
        "https://webexapis.com/v1/access_token",
        data={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": tokens["refresh_token"],
        },
    )
    if not response.ok:
        print("Webex returned an error:", response.status_code)
        print(response.text)
    response.raise_for_status()
    new_tokens = response.json()
    save_tokens(new_tokens)
    return new_tokens["access_token"]


def get_valid_access_token():
    tokens = load_tokens()
    buffer_seconds = 300
    if time.time() < tokens.get("access_token_expires_at", 0) - buffer_seconds:
        return tokens["access_token"]
    return refresh_access_token()

def login():
    """
    One-time sign-in: opens Webex in the browser, catches the OAuth
    redirect on WEBEX_REDIRECT_URI (a localhost URL), checks the state
    value, exchanges the code and saves tokens.json.
    """
    import http.server
    import webbrowser
    from urllib.parse import urlparse, parse_qs

    url = build_authorization_url()
    expected_state = parse_qs(urlparse(url).query)["state"][0]
    redirect = urlparse(redirect_uri)
    result = {}

    class Callback(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path != redirect.path:
                self.send_response(404)
                self.end_headers()
                return
            result.update({k: v[0] for k, v in parse_qs(parsed.query).items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("Signed in. You can close this tab.".encode())

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer((redirect.hostname, redirect.port or 80), Callback)
    print("Opening Webex in your browser. If nothing opens, visit:\n" + url)
    webbrowser.open(url)
    while "code" not in result and "error" not in result:
        server.handle_request()
    server.server_close()

    if result.get("state") != expected_state or "code" not in result:
        raise SystemExit(f"Sign-in didn't complete: {result.get('error', 'state mismatch')}")
    save_tokens(exchange_code_for_tokens(result["code"]))
    print(f"Saved {TOKEN_FILE}.")


if __name__ == "__main__":
    import sys

    if sys.argv[1:] == ["login"]:
        login()
    else:
        token = get_valid_access_token()
        print("Got a token:", token is not None)