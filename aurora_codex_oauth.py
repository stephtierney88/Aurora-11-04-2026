import argparse
import base64
import hashlib
import json
import os
import secrets
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import requests


DEFAULT_ISSUER = "https://auth.openai.com"
DEFAULT_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
DEFAULT_SCOPE = "openid profile email offline_access api.connectors.read api.connectors.invoke"
DEFAULT_CALLBACK_HOST = "127.0.0.1"
DEFAULT_CALLBACK_PORT = 1455
DEFAULT_CALLBACK_PATH = "/auth/callback"


class CodexOAuthError(RuntimeError):
    pass


def _now_epoch():
    return int(time.time())


def _utc_timestamp():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _workspace_dir():
    return Path(__file__).resolve().parent


def default_cache_path():
    return _workspace_dir() / "aurora_codex_oauth.json"


def default_codex_auth_path():
    return Path.home() / ".codex" / "auth.json"


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def decode_jwt_claims(raw_token: str):
    if not raw_token or "." not in raw_token:
        return {}
    try:
        payload = raw_token.split(".")[1]
        payload += "=" * ((4 - len(payload) % 4) % 4)
        return json.loads(base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8"))
    except Exception:
        return {}


def token_expired(raw_token: str, leeway_seconds: int = 300) -> bool:
    claims = decode_jwt_claims(raw_token)
    exp = claims.get("exp")
    if not isinstance(exp, int):
        return True
    return exp <= (_now_epoch() + leeway_seconds)


def extract_chatgpt_account_id(token_claims: dict):
    if not isinstance(token_claims, dict):
        return ""
    auth_claims = token_claims.get("https://api.openai.com/auth", {})
    if isinstance(auth_claims, dict):
        return (
            auth_claims.get("chatgpt_account_id")
            or auth_claims.get("chatgpt_account_user_id")
            or auth_claims.get("chatgpt_user_id")
            or auth_claims.get("user_id")
            or ""
        )
    return ""


def generate_pkce_pair():
    verifier = _b64url_encode(os.urandom(32))
    challenge = _b64url_encode(hashlib.sha256(verifier.encode("ascii")).digest())
    return {"code_verifier": verifier, "code_challenge": challenge}


def build_authorize_url(
    issuer: str,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    state: str,
):
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": DEFAULT_SCOPE,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    return f"{issuer}/oauth/authorize?{urllib.parse.urlencode(params)}"


def extract_code_from_manual_input(raw_value: str, expected_state: str = ""):
    raw_value = (raw_value or "").strip()
    if not raw_value:
        raise CodexOAuthError("No callback URL or authorization code was provided.")

    if raw_value.startswith("http://") or raw_value.startswith("https://"):
        parsed = urllib.parse.urlparse(raw_value)
        query = urllib.parse.parse_qs(parsed.query)
        state = (query.get("state") or [""])[0]
        code = (query.get("code") or [""])[0]
        error = (query.get("error") or [""])[0]
        if error:
            raise CodexOAuthError(f"OAuth callback failed: {error}")
        if expected_state and state and state != expected_state:
            raise CodexOAuthError("OAuth callback failed: oauth_state_mismatch")
        if not code:
            raise CodexOAuthError("Callback URL did not contain an authorization code.")
        return code

    return raw_value


def prompt_for_manual_callback(auth_url: str, expected_state: str = ""):
    print()
    print("Aurora OAuth manual fallback")
    print("1. Open this URL in a browser and finish ChatGPT sign-in:")
    print(auth_url)
    print("2. If the browser lands on a localhost callback page or errors after redirect,")
    print("   copy the full redirected URL from the address bar and paste it below.")
    print("3. You can also paste only the authorization code if needed.")
    print()
    manual_value = input("Paste redirected URL or auth code: ").strip()
    return extract_code_from_manual_input(manual_value, expected_state=expected_state)


def exchange_code_for_tokens(
    code: str,
    redirect_uri: str,
    code_verifier: str,
    issuer: str = DEFAULT_ISSUER,
    client_id: str = DEFAULT_CLIENT_ID,
):
    body = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": code_verifier,
    }
    response = requests.post(
        f"{issuer}/oauth/token",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    if not response.ok:
        raise CodexOAuthError(
            f"OAuth token exchange failed: {response.status_code} {response.text[:400]}"
        )
    data = response.json()
    return {
        "id_token": data.get("id_token", ""),
        "access_token": data.get("access_token", ""),
        "refresh_token": data.get("refresh_token", ""),
    }


def refresh_chatgpt_tokens(
    refresh_token: str,
    issuer: str = DEFAULT_ISSUER,
    client_id: str = DEFAULT_CLIENT_ID,
):
    response = requests.post(
        f"{issuer}/oauth/token",
        json={
            "client_id": client_id,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=30,
    )
    if not response.ok:
        raise CodexOAuthError(
            f"ChatGPT token refresh failed: {response.status_code} {response.text[:400]}"
        )
    data = response.json()
    return {
        "id_token": data.get("id_token", ""),
        "access_token": data.get("access_token", ""),
        "refresh_token": data.get("refresh_token", refresh_token),
    }


def exchange_id_token_for_api_access_token(
    id_token: str,
    issuer: str = DEFAULT_ISSUER,
    client_id: str = DEFAULT_CLIENT_ID,
):
    body = {
        "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
        "client_id": client_id,
        "requested_token": "openai-api-key",
        "subject_token": id_token,
        "subject_token_type": "urn:ietf:params:oauth:token-type:id_token",
    }
    response = requests.post(
        f"{issuer}/oauth/token",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    if not response.ok:
        raise CodexOAuthError(
            f"API token exchange failed: {response.status_code} {response.text[:400]}"
        )
    data = response.json()
    api_access_token = data.get("access_token", "")
    return {
        "api_access_token": api_access_token,
        "api_access_token_claims": decode_jwt_claims(api_access_token),
        "api_access_token_exchanged_at": _utc_timestamp(),
    }


def load_auth_bundle(path: Path):
    if not path.exists():
        raise CodexOAuthError(f"Auth file not found: {path}")
    data = _read_json(path)
    if not isinstance(data, dict):
        raise CodexOAuthError(f"Auth file has invalid structure: {path}")
    return data


def normalize_auth_bundle(data: dict, source_path: Path):
    tokens = dict(data.get("tokens") or {})
    normalized = {
        "source_path": str(source_path),
        "issuer": data.get("issuer") or DEFAULT_ISSUER,
        "client_id": data.get("client_id") or DEFAULT_CLIENT_ID,
        "auth_mode": data.get("auth_mode") or "chatgpt",
        "tokens": {
            "id_token": tokens.get("id_token", ""),
            "access_token": tokens.get("access_token", ""),
            "refresh_token": tokens.get("refresh_token", ""),
            "account_id": tokens.get("account_id") or data.get("account_id", ""),
        },
        "last_refresh": data.get("last_refresh", ""),
        "api_access_token": data.get("api_access_token", ""),
        "api_access_token_claims": data.get("api_access_token_claims", {}),
        "api_access_token_exchanged_at": data.get("api_access_token_exchanged_at", ""),
    }
    id_claims = decode_jwt_claims(normalized["tokens"]["id_token"])
    if not normalized["tokens"]["account_id"]:
        normalized["tokens"]["account_id"] = extract_chatgpt_account_id(id_claims)
    return normalized


def save_auth_bundle(path: Path, bundle: dict):
    _write_json(path, bundle)


class _OAuthCallbackState:
    def __init__(self, expected_state: str):
        self.expected_state = expected_state
        self.code = None
        self.error = None
        self.received_state = None
        self.event = threading.Event()


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    shared_state = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != DEFAULT_CALLBACK_PATH:
            self.send_response(404)
            self.end_headers()
            return

        query = urllib.parse.parse_qs(parsed.query)
        state = (query.get("state") or [""])[0]
        code = (query.get("code") or [""])[0]
        error = (query.get("error") or [""])[0]

        self.shared_state.received_state = state
        if error:
            self.shared_state.error = error
        elif state != self.shared_state.expected_state:
            self.shared_state.error = "oauth_state_mismatch"
        elif code:
            self.shared_state.code = code
        else:
            self.shared_state.error = "missing_code"

        self.shared_state.event.set()

        message = "Aurora OAuth complete. You can close this tab." if self.shared_state.code else (
            f"Aurora OAuth failed: {self.shared_state.error}. You can close this tab."
        )
        body = (
            "<html><body><h2>Aurora OAuth</h2>"
            f"<p>{message}</p>"
            "</body></html>"
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


def run_browser_login(
    output_path: Path,
    issuer: str = DEFAULT_ISSUER,
    client_id: str = DEFAULT_CLIENT_ID,
    host: str = DEFAULT_CALLBACK_HOST,
    port: int = DEFAULT_CALLBACK_PORT,
    open_browser: bool = True,
    timeout_seconds: int = 300,
    show_url: bool = False,
    allow_manual_fallback: bool = True,
):
    pkce = generate_pkce_pair()
    state = secrets.token_urlsafe(24)
    callback_state = _OAuthCallbackState(state)
    _OAuthCallbackHandler.shared_state = callback_state

    redirect_uri = f"http://{host}:{port}{DEFAULT_CALLBACK_PATH}"
    auth_url = build_authorize_url(issuer, client_id, redirect_uri, pkce["code_challenge"], state)
    if show_url or not open_browser:
        print(auth_url)

    server = None
    callback_ready = False
    try:
        server = ThreadingHTTPServer((host, port), _OAuthCallbackHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        callback_ready = True
    except OSError:
        callback_ready = False

    if open_browser:
        webbrowser.open(auth_url)

    authorization_code = ""
    if callback_ready:
        if not callback_state.event.wait(timeout_seconds):
            if allow_manual_fallback:
                authorization_code = prompt_for_manual_callback(auth_url, expected_state=state)
            else:
                server.shutdown()
                server.server_close()
                raise CodexOAuthError(
                    "OAuth callback timed out. Re-run the login helper and finish browser sign-in."
                )
        else:
            if callback_state.error:
                if allow_manual_fallback:
                    authorization_code = prompt_for_manual_callback(auth_url, expected_state=state)
                else:
                    server.shutdown()
                    server.server_close()
                    raise CodexOAuthError(f"OAuth callback failed: {callback_state.error}")
            elif callback_state.code:
                authorization_code = callback_state.code
            else:
                if allow_manual_fallback:
                    authorization_code = prompt_for_manual_callback(auth_url, expected_state=state)
                else:
                    server.shutdown()
                    server.server_close()
                    raise CodexOAuthError("OAuth callback completed without a code.")
    elif allow_manual_fallback:
        authorization_code = prompt_for_manual_callback(auth_url, expected_state=state)
    else:
        raise CodexOAuthError(
            f"OAuth callback server could not bind to {redirect_uri}. Re-run with manual fallback enabled."
        )

    if server is not None:
        server.shutdown()
        server.server_close()

    token_bundle = exchange_code_for_tokens(
        authorization_code,
        redirect_uri,
        pkce["code_verifier"],
        issuer=issuer,
        client_id=client_id,
    )
    api_bundle = exchange_id_token_for_api_access_token(
        token_bundle["id_token"],
        issuer=issuer,
        client_id=client_id,
    )

    bundle = {
        "issuer": issuer,
        "client_id": client_id,
        "auth_mode": "chatgpt",
        "tokens": token_bundle,
        "last_refresh": _utc_timestamp(),
        **api_bundle,
    }
    bundle["tokens"]["account_id"] = extract_chatgpt_account_id(decode_jwt_claims(bundle["tokens"]["id_token"]))
    save_auth_bundle(output_path, bundle)
    return {
        "output_path": str(output_path),
        "account_id": bundle["tokens"]["account_id"],
        "issuer": issuer,
        "client_id": client_id,
        "has_api_access_token": bool(bundle.get("api_access_token")),
    }


class CodexOAuthManager:
    def __init__(
        self,
        cache_path: Path | None = None,
        codex_auth_path: Path | None = None,
        issuer: str = DEFAULT_ISSUER,
        client_id: str = DEFAULT_CLIENT_ID,
    ):
        self.cache_path = Path(cache_path) if cache_path else default_cache_path()
        self.codex_auth_path = Path(codex_auth_path) if codex_auth_path else default_codex_auth_path()
        self.issuer = issuer
        self.client_id = client_id

    def _candidate_paths(self):
        paths = []
        if self.cache_path:
            paths.append(self.cache_path)
        if self.codex_auth_path and self.codex_auth_path != self.cache_path:
            paths.append(self.codex_auth_path)
        return paths

    def _load_best_bundle(self):
        for path in self._candidate_paths():
            if path.exists():
                return normalize_auth_bundle(load_auth_bundle(path), path)
        raise CodexOAuthError(
            "No Codex OAuth auth file found. Sign in with ChatGPT in Codex or run aurora_codex_oauth.py."
        )

    def _save_cache_bundle(self, bundle: dict):
        save_auth_bundle(self.cache_path, bundle)

    def _ensure_fresh_chatgpt_tokens(self, bundle: dict, force_refresh: bool = False):
        id_token = bundle["tokens"].get("id_token", "")
        if not force_refresh and id_token and not token_expired(id_token):
            return bundle

        refresh_token = bundle["tokens"].get("refresh_token", "")
        if not refresh_token:
            raise CodexOAuthError(
                "Codex OAuth id_token is expired and no refresh_token is available. Sign in again."
            )

        refreshed = refresh_chatgpt_tokens(
            refresh_token,
            issuer=self.issuer,
            client_id=self.client_id,
        )
        bundle["tokens"].update(refreshed)
        bundle["tokens"]["account_id"] = extract_chatgpt_account_id(decode_jwt_claims(bundle["tokens"]["id_token"]))
        bundle["last_refresh"] = _utc_timestamp()
        self._save_cache_bundle(bundle)
        return bundle

    def get_api_access_token(self, force_refresh: bool = False):
        bundle = self._load_best_bundle()

        api_access_token = bundle.get("api_access_token", "")
        if not force_refresh and api_access_token and not token_expired(api_access_token):
            return api_access_token

        bundle = self._ensure_fresh_chatgpt_tokens(bundle, force_refresh=force_refresh)
        api_bundle = exchange_id_token_for_api_access_token(
            bundle["tokens"]["id_token"],
            issuer=self.issuer,
            client_id=self.client_id,
        )
        bundle.update(api_bundle)
        self._save_cache_bundle(bundle)
        return bundle["api_access_token"]

    def get_status(self):
        bundle = self._load_best_bundle()
        id_claims = decode_jwt_claims(bundle["tokens"].get("id_token", ""))
        api_claims = decode_jwt_claims(bundle.get("api_access_token", ""))
        return {
            "cache_path": str(self.cache_path),
            "source_path": bundle.get("source_path", ""),
            "account_id": bundle["tokens"].get("account_id", ""),
            "id_token_exp": id_claims.get("exp"),
            "api_access_token_exp": api_claims.get("exp"),
            "has_refresh_token": bool(bundle["tokens"].get("refresh_token")),
            "has_api_access_token": bool(bundle.get("api_access_token")),
        }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Sign in with ChatGPT/Codex OAuth and store Aurora-compatible tokens, including "
            "the API-key-style access token exchange used by open-source Codex."
        )
    )
    parser.add_argument("--output", default=str(default_cache_path()))
    parser.add_argument("--issuer", default=DEFAULT_ISSUER)
    parser.add_argument("--client-id", default=DEFAULT_CLIENT_ID)
    parser.add_argument("--host", default=DEFAULT_CALLBACK_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_CALLBACK_PORT)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--show-url", action="store_true")
    parser.add_argument("--no-manual-fallback", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    manager = CodexOAuthManager(cache_path=Path(args.output), issuer=args.issuer, client_id=args.client_id)

    if args.status:
        print(json.dumps(manager.get_status(), indent=2))
        return

    result = run_browser_login(
        output_path=Path(args.output),
        issuer=args.issuer,
        client_id=args.client_id,
        host=args.host,
        port=args.port,
        open_browser=not args.no_browser,
        show_url=args.show_url,
        allow_manual_fallback=not args.no_manual_fallback,
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
