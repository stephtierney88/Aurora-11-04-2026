"""Aurora-owned Sign in with ChatGPT credentials. Never reads another app's tokens.

Windows DPAPI protects the atomic local store; a process/file lock serializes
rotating refresh tokens. Importing this module performs no IO or sign-in.
"""
from __future__ import annotations
import base64
from contextlib import contextmanager
import ctypes
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import tempfile
import threading
import time
from urllib.parse import parse_qs, urlencode, urlsplit
import uuid
import webbrowser

import requests

ISSUER = "https://auth.openai.com"
AUTHORIZE = ISSUER + "/api/accounts/authorize"
TOKEN = ISSUER + "/api/accounts/oauth/token"
RESOURCE = "https://api.openai.com/v1"
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
_LOCK = threading.RLock()


class ChatGPTAuthError(RuntimeError):
    """Sanitized error safe for UI/logs (never a provider response body)."""


def safe_code(value):
    text = str(value or "unknown_error")
    return text if re.fullmatch(r"[a-zA-Z0-9_.:-]{1,100}", text) else "provider_error"


def provider_error(response):
    try:
        error = response.json().get("error", {})
        code = error.get("code", error.get("type")) if isinstance(error, dict) else error
    except (ValueError, AttributeError):
        code = "http_error"
    return ChatGPTAuthError(f"ChatGPT HTTP {response.status_code}: {safe_code(code)}")


def protected_bytes(data, decrypt=False):
    if os.name != "nt":
        return data  # Store is owner-only on POSIX; Windows uses user-bound DPAPI.
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]
    buffer = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source, target = Blob(len(data), buffer), Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if decrypt:
        fn = crypt.CryptUnprotectData
        fn.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        ok = fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target))
    else:
        fn = crypt.CryptProtectData
        fn.argtypes = [ctypes.POINTER(Blob), wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        ok = fn(ctypes.byref(source), "Aurora ChatGPT", None, None, None, 1, ctypes.byref(target))
    if not ok:
        raise ChatGPTAuthError("Windows credential protection failed; no plaintext fallback.")
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(target.data)


def default_store_path():
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / ".config"))
    return base / "Aurora" / "auth" / "chatgpt.bin"


class CredentialStore:
    def __init__(self, path=None):
        self.path = Path(path) if path else default_store_path()

    @contextmanager
    def locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with _LOCK, open(self.path.with_suffix(".lock"), "a+b") as handle:
            handle.seek(0, 2)
            if handle.tell() == 0:
                handle.write(b"0"); handle.flush()
            deadline = time.monotonic() + 40
            while True:
                try:
                    handle.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise ChatGPTAuthError("Credential store busy; retry after the other operation finishes.") from None
                    time.sleep(.05)
            try:
                yield
            finally:
                handle.seek(0)
                if os.name == "nt":
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle, fcntl.LOCK_UN)

    def read(self):
        if not self.path.exists():
            return {"version": 1, "host_id": "urn:uuid:" + str(uuid.uuid4()), "active": "", "accounts": {}}
        try:
            return json.loads(protected_bytes(self.path.read_bytes(), decrypt=True))
        except (ValueError, OSError) as error:
            raise ChatGPTAuthError("Cannot read the Aurora credential store; existing credentials were preserved.") from error

    def write(self, data):
        blob = protected_bytes(json.dumps(data).encode())
        fd, name = tempfile.mkstemp(prefix=".chatgpt-", dir=self.path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                os.chmod(name, 0o600)
                handle.write(blob); handle.flush(); os.fsync(handle.fileno())
            os.replace(name, self.path)
        finally:
            Path(name).unlink(missing_ok=True)


def validate_callback(url, redirect, state, client_id):
    parsed, expected = urlsplit(url), urlsplit(redirect)
    if (parsed.scheme, parsed.netloc, parsed.path) != (expected.scheme, expected.netloc, expected.path) or parsed.fragment:
        raise ChatGPTAuthError("Callback origin/path mismatch.")
    query = parse_qs(parsed.query, keep_blank_values=True)
    if any(len(values) != 1 for values in query.values()):
        raise ChatGPTAuthError("Ambiguous callback parameters.")
    if not secrets.compare_digest(query.get("state", [""])[0], state):
        raise ChatGPTAuthError("Callback state mismatch.")
    if query.get("error"):
        raise ChatGPTAuthError("Authorization declined: " + safe_code(query["error"][0]))
    issued = query.get("client_id", [client_id])[0]
    if not issued or issued == "dynamic_agent_client" or not query.get("code", [""])[0]:
        raise ChatGPTAuthError("Registration incomplete: missing code or issued client ID.")
    if client_id != "dynamic_agent_client" and issued != client_id:
        raise ChatGPTAuthError("Callback client ID does not match the selected account.")
    return query["code"][0], issued


def trusted_auth_url(url):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.netloc != "auth.openai.com" or parsed.fragment:
        raise ChatGPTAuthError("Unexpected identity endpoint.")
    return url


def identity_metadata():
    response = requests.get(ISSUER + "/.well-known/openid-configuration", timeout=15)
    if response.status_code != 200:
        raise provider_error(response)
    result = response.json()
    if result.get("issuer") != ISSUER:
        raise ChatGPTAuthError("Unexpected identity issuer.")
    return result


def verify_identity(token, client_id, nonce=None, subject=None):
    try:
        import jwt
        metadata = identity_metadata()
        client = jwt.PyJWKClient(trusted_auth_url(metadata["jwks_uri"]), timeout=15)
        key = client.get_signing_key_from_jwt(token)
        claims = jwt.decode(token, key.key, algorithms=["RS256"], audience=client_id, issuer=ISSUER,
                            options={"require": ["exp", "iss", "aud", "sub"]})
        if nonce is not None and claims.get("nonce") != nonce:
            raise ChatGPTAuthError("ID token nonce mismatch.")
        if not claims.get("sub") or (subject is not None and claims["sub"] != subject):
            raise ChatGPTAuthError("Account identity mismatch.")
        return claims
    except ChatGPTAuthError:
        raise
    except Exception:
        raise ChatGPTAuthError("ID token validation failed; credentials were not saved.") from None


def merge_tokens(previous, tokens):
    try:
        expiry = float(tokens["expires_in"])
        if not 0 < expiry < 366 * 86400 or str(tokens.get("token_type", "")).lower() != "bearer" or not tokens.get("access_token"):
            raise ValueError
        scopes = str(tokens["scope"]).split() if "scope" in tokens else previous.get("scopes", [])
        if not scopes:
            raise ValueError
        return {**previous, **{k: tokens[k] for k in ("access_token", "refresh_token", "id_token") if tokens.get(k)},
                "scopes": scopes, "expires_at": time.time() + expiry, "saved_at": time.time(), "token_type": "Bearer"}
    except (KeyError, TypeError, ValueError, OverflowError):
        raise ChatGPTAuthError("Incomplete token response; previous credentials preserved.") from None


class ChatGPTAuth:
    def __init__(self, store=None):
        self.store = store or CredentialStore()

    def status(self):
        with self.store.locked():
            data = self.store.read()
        return {"active": data["active"], "storage": str(self.store.path), "accounts": [
            {"id": key, "email": row.get("email", ""), "connected": bool(row.get("access_token")),
             "plan_enabled": "chatgpt.tokens.use.direct" in row.get("scopes", []),
             "expires_at": row.get("expires_at", 0)} for key, row in data["accounts"].items()]}

    def select(self, account_id):
        with self.store.locked():
            data = self.store.read()
            if account_id not in data["accounts"]:
                raise ChatGPTAuthError("Unknown ChatGPT registration.")
            data["active"] = account_id
            self.store.write(data)

    def login(self, account_id=None, *, cancel=None, timeout=240, notify=lambda message: None, open_browser=webbrowser.open):
        cancel = cancel or threading.Event()
        with self.store.locked():
            data = self.store.read()
            if account_id and account_id not in data["accounts"]:
                raise ChatGPTAuthError("Unknown ChatGPT registration.")
            previous = dict(data["accounts"].get(account_id, {}))
            self.store.write(data)  # Stable host ID survives canceled/new attempts.
        state, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(3))
        client_id = previous.get("client_id", "dynamic_agent_client")
        result = {}
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass
            def do_GET(self):
                try:
                    code, issued = validate_callback(redirect + self.path[len("/auth/callback"):] if self.path.startswith("/auth/callback?") else "http://127.0.0.1:" + str(server.server_port) + self.path, redirect, state, client_id)
                    result.update(code=code, client_id=issued)
                    status, message = 200, b"Aurora sign-in received. You may close this tab and return to Aurora."
                except ChatGPTAuthError as error:
                    if str(error).startswith("Authorization declined"):
                        result["error"] = error
                    status, message = 400, b"Aurora could not accept this callback. Return to Aurora."
                self.send_response(status)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                try:
                    self.wfile.write(message)
                except OSError:
                    pass
        class BoundedServer(HTTPServer):
            def get_request(self):
                connection, address = super().get_request()
                connection.settimeout(2)
                return connection, address
        server = BoundedServer(("127.0.0.1", 0), Handler)
        server.timeout = .25
        redirect = f"http://127.0.0.1:{server.server_port}/auth/callback"
        params = {"client_id": client_id, "ext_agent_host_id": data["host_id"], "response_type": "code",
                  "redirect_uri": redirect, "scope": SCOPES, "resource": RESOURCE, "state": state, "nonce": nonce,
                  "code_challenge_method": "S256", "code_challenge": base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")}
        if client_id == "dynamic_agent_client":
            params["agent_name_hint"] = "Aurora"
        elif previous.get("id_token"):
            params["id_token_hint"] = previous["id_token"]
        try:
            if cancel.is_set():
                raise ChatGPTAuthError("Sign-in canceled.")
            open_browser(AUTHORIZE + "?" + urlencode(params))
            notify("Complete sign-in in your browser. Waiting up to four minutes; Cancel closes Aurora's listener.")
            deadline = time.monotonic() + timeout
            while not result and not cancel.is_set() and time.monotonic() < deadline:
                server.handle_request()
            if cancel.is_set() or not result:
                raise ChatGPTAuthError("Sign-in canceled or timed out; previous account unchanged.")
            if result.get("error"):
                raise result["error"]
            response = requests.post(TOKEN, data={"grant_type": "authorization_code", "client_id": result["client_id"],
                "code": result["code"], "code_verifier": verifier, "redirect_uri": redirect, "resource": RESOURCE}, timeout=20)
            if response.status_code != 200:
                raise provider_error(response)
            tokens = response.json()
            claims = verify_identity(tokens.get("id_token", ""), result["client_id"], nonce, previous.get("subject"))
            account = merge_tokens({**previous, "client_id": result["client_id"], "subject": claims["sub"],
                "email": claims.get("email", ""), "issuer": ISSUER}, tokens)
            key = hashlib.sha256((claims["sub"] + "\0" + result["client_id"]).encode()).hexdigest()[:24]
            if cancel.is_set():
                raise ChatGPTAuthError("Sign-in canceled; credentials were not activated.")
            with self.store.locked():
                latest = self.store.read()
                latest["accounts"][key] = account
                latest["active"] = key
                self.store.write(latest)
            return key
        except requests.RequestException:
            raise ChatGPTAuthError("ChatGPT sign-in network failure; retry explicitly.") from None
        finally:
            server.server_close()

    def access(self):
        with self.store.locked():
            data = self.store.read()
            account = data["accounts"].get(data["active"], {})
            if not account.get("access_token"):
                raise ChatGPTAuthError("Continue with ChatGPT before choosing subscription inference.")
            if "chatgpt.tokens.use.direct" not in account.get("scopes", []):
                raise ChatGPTAuthError("ChatGPT plan usage was not granted. Reauthorize in Connection settings.")
            if account.get("expires_at", 0) <= time.time() + 60:
                if not account.get("refresh_token"):
                    raise ChatGPTAuthError("ChatGPT session expired; sign in again.")
                try:
                    response = requests.post(TOKEN, data={"grant_type": "refresh_token", "client_id": account["client_id"],
                        "refresh_token": account["refresh_token"], "resource": RESOURCE}, timeout=20)
                except requests.RequestException:
                    raise ChatGPTAuthError("ChatGPT refresh network failure; credentials preserved.") from None
                if response.status_code != 200:
                    error = provider_error(response)
                    if any(code in str(error) for code in ("invalid_grant", "refresh_token_reused", "refresh_token_invalidated", "refresh_token_expired")):
                        for key in ("access_token", "refresh_token", "id_token"):
                            account.pop(key, None)
                        self.store.write(data)
                    raise error
                tokens = response.json()
                if tokens.get("id_token"):
                    verify_identity(tokens["id_token"], account["client_id"], subject=account["subject"])
                account = merge_tokens(account, tokens)
                data["accounts"][data["active"]] = account
                self.store.write(data)
                if "chatgpt.tokens.use.direct" not in account["scopes"]:
                    raise ChatGPTAuthError("ChatGPT plan permission no longer granted.")
            return account["access_token"], data["active"]

    def logout(self, account_id):
        confirmed = False
        with self.store.locked():
            data = self.store.read()
            account = data["accounts"].get(account_id)
            if account is None:
                raise ChatGPTAuthError("Unknown ChatGPT registration.")
            try:
                if account.get("refresh_token"):
                    endpoint = trusted_auth_url(identity_metadata()["revocation_endpoint"])
                    response = requests.post(endpoint, data={"token": account["refresh_token"], "token_type_hint": "refresh_token", "client_id": account["client_id"]}, timeout=15)
                    confirmed = response.status_code == 200
            except (requests.RequestException, ChatGPTAuthError, KeyError, ValueError):
                pass
            for key in ("access_token", "refresh_token", "id_token"):
                account.pop(key, None)
            self.store.write(data)
        return "Signed out; renewable session revoked." if confirmed else "Signed out locally; remote revocation unconfirmed. Disconnect Aurora in ChatGPT Settings if needed."
