#!/usr/bin/env python3
"""Bootstrap, provision, seed, and verify simulated apps (device-management & chess-room-booking) against a live magicPlatform."""
from __future__ import annotations

from collections.abc import Callable
import argparse
import base64
import hashlib
import http.client
from http.cookiejar import CookieJar
import json
import os
from pathlib import Path
import secrets
import ssl
import stat
import subprocess
import sys
import tempfile
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit
from urllib.request import (
    HTTPCookieProcessor,
    HTTPRedirectHandler,
    HTTPSHandler,
    Request,
    build_opener,
)
import uuid

LIVE_E2E_DIR = Path(__file__).resolve().parent
APPLICATIONS_ROOT = LIVE_E2E_DIR.parent
MAGICTEST_ROOT = APPLICATIONS_ROOT.parent
if str(APPLICATIONS_ROOT) not in sys.path:
    sys.path.insert(0, str(APPLICATIONS_ROOT))

from platform_paths import resolve_app_model_root, resolve_platform_root

MAX_ACTION_TOKEN_BYTES = 16384
MAX_HTTP_RESPONSE_BYTES = 8 << 20
SYSTEM_CA_CANDIDATES = (
    "/etc/ssl/certs/ca-certificates.crt",
    "/etc/pki/tls/certs/ca-bundle.crt",
    "/etc/ssl/cert.pem",
)

APP_SPECS: dict[str, dict[str, Any]] = {
    "device-management": {
        "uuid": "91bc30d3ee955b09b75fdaffc0231e25",
        "instanceKey": "device-management",
        "instanceName": "设备管理模拟实例",
        "serviceKeys": ("device_management_service",),
        "storageRequired": True,
    },
    "chess-room-booking": {
        "uuid": "8e602de43d0f4a6294b531643b304a89",
        "instanceKey": "chess-room-booking",
        "instanceName": "棋牌室预订模拟实例",
        "serviceKeys": ("chess_room_booking_simulation", "chess_room_booking_service"),
        "storageRequired": True,
    },
}


class BootstrapError(RuntimeError):
    """Base error for bootstrap orchestration."""


class SafetyRefusal(BootstrapError):
    """Raised when a safety guard blocks destructive or ambiguous mutation."""


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def make_ssl_context(ca_file: Path | None = None, trust_leaf: bool = False) -> ssl.SSLContext:
    ctx = ssl.create_default_context(cafile=str(ca_file.expanduser()) if ca_file else None)
    if trust_leaf:
        if not ca_file or not hasattr(ssl, "VERIFY_X509_PARTIAL_CHAIN"):
            raise BootstrapError("--trust-leaf requires --ca-file and OpenSSL VERIFY_X509_PARTIAL_CHAIN support")
        ctx.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
    return ctx


def validate_base_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError(f"base URL must be an HTTPS origin without credentials: {url}")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise ValueError(f"base URL must be an origin without path/query: {url}")
    return f"https://{parsed.netloc}"


def read_secret_file(path: Path | None, env_name: str | None = None, label: str = "secret") -> str:
    if path is not None:
        resolved = path.expanduser()
        fd = os.open(resolved, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or stat.S_IMODE(st.st_mode) != 0o600:
                raise SafetyRefusal(f"{label} file {resolved} must be a regular file owned by current user with mode 0600")
            raw = os.read(fd, 16385)
        finally:
            os.close(fd)
        if len(raw) > 16384:
            raise SafetyRefusal(f"{label} file exceeds 16 KiB safety limit")
        val = raw.decode("utf-8").strip()
    elif env_name:
        val = os.environ.get(env_name, "").strip()
    else:
        val = ""
    if not val:
        raise SafetyRefusal(f"missing required {label}")
    return val


def ensure_private_dir(path: Path) -> Path:
    path = path.expanduser().resolve()
    if path.is_symlink():
        raise SafetyRefusal(f"directory cannot be a symlink: {path}")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    st = path.stat()
    if st.st_uid != os.getuid():
        raise SafetyRefusal(f"directory not owned by current user: {path}")
    if stat.S_IMODE(st.st_mode) != 0o700:
        os.chmod(path, 0o700)
    return path


def write_secret_file(path: Path, secret_value: str) -> Path:
    ensure_private_dir(path.parent)
    if path.is_symlink():
        raise SafetyRefusal(f"secret target cannot be a symlink: {path}")
    fd, tmp_name = tempfile.mkstemp(prefix=".secret-", dir=path.parent)
    try:
        os.chmod(tmp_name, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(secret_value.strip() + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    return path


def resolve_system_ca_file() -> Path | None:
    for candidate in SYSTEM_CA_CANDIDATES:
        p = Path(candidate)
        if p.is_file():
            return p
    return None


def pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
    return verifier, challenge


def _encode_multipart_file(field_name: str, filename: str, payload: bytes, content_type: str = "application/zip") -> tuple[bytes, str]:
    boundary = f"----magicSimBoundary{secrets.token_hex(12)}"
    header = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode("utf-8")
    footer = f"\r\n--{boundary}--\r\n".encode("utf-8")
    return header + payload + footer, f"multipart/form-data; boundary={boundary}"


def _make_https_handler(ssl_context: ssl.SSLContext, target_address: str | None = None) -> HTTPSHandler:
    target = (target_address or os.environ.get("MAGICTEST_TARGET_ADDRESS") or "").strip()
    if not target:
        return HTTPSHandler(context=ssl_context)

    class _TargetHTTPSHandler(HTTPSHandler):
        def https_open(self, req):
            class _SniConn(http.client.HTTPSConnection):
                def __init__(self, host, port=None, **kwargs):
                    parsed = urlsplit(f"https://{host}")
                    self._sni_host = parsed.hostname or host
                    super().__init__(target, port=parsed.port or port or 443, **kwargs)

                def connect(self):
                    sock = self._create_connection((self.host, self.port), self.timeout, self.source_address)
                    if self._tunnel_host:
                        self.sock = sock
                        self._tunnel()
                    self.sock = self._context.wrap_socket(sock, server_hostname=self._sni_host)

            return self.do_open(_SniConn, req, context=self._context)

    return _TargetHTTPSHandler(context=ssl_context)


class HttpSession:
    """HTTP client managing explicit redirect hops, optional CookieJar, and Origin enforcement."""

    def __init__(
        self,
        base_url: str,
        ssl_context: ssl.SSLContext,
        *,
        use_cookies: bool = True,
        timeout: int = 30,
        target_address: str | None = None,
    ):
        self.base_url = validate_base_url(base_url)
        self.timeout = timeout
        self.cookie_jar = CookieJar() if use_cookies else None
        handlers: list[Any] = [_NoRedirectHandler(), _make_https_handler(ssl_context, target_address)]
        if self.cookie_jar is not None:
            handlers.append(HTTPCookieProcessor(self.cookie_jar))
        self.opener = build_opener(*handlers)

    def raw_request(
        self,
        method: str,
        url: str,
        *,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> tuple[int, Any, bytes]:
        target = urljoin(self.base_url + "/", url) if not url.startswith("https://") else url
        req_headers = dict(headers or {})
        if self.cookie_jar is None:
            req_headers.pop("Cookie", None)
        req = Request(target, method=method, data=data, headers=req_headers)
        try:
            with self.opener.open(req, timeout=self.timeout) as resp:
                body = resp.read(MAX_HTTP_RESPONSE_BYTES + 1)
                if len(body) > MAX_HTTP_RESPONSE_BYTES:
                    raise BootstrapError(f"response too large from {target}")
                if self.cookie_jar is not None:
                    self.cookie_jar.extract_cookies(resp, req)
                return resp.status, resp.headers, body
        except HTTPError as exc:
            try:
                body = exc.read(MAX_HTTP_RESPONSE_BYTES + 1)
                if self.cookie_jar is not None:
                    self.cookie_jar.extract_cookies(exc, req)
                return exc.code, exc.headers, body
            finally:
                exc.close()
        except (URLError, TimeoutError, OSError) as exc:
            raise BootstrapError(f"HTTP transport error on {method} {target}: {exc}") from exc

    def follow_redirects(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        max_hops: int = 12,
        stop_prefixes: tuple[str, ...] = (),
    ) -> tuple[str, int, Any, bytes]:
        current = urljoin(self.base_url + "/", url) if not url.startswith("https://") else url
        for _ in range(max_hops):
            if any(urlsplit(current).path.startswith(p) or current.startswith(p) for p in stop_prefixes):
                return current, 0, {}, b""
            status, resp_headers, body = self.raw_request("GET", current, headers=headers)
            if status in (301, 302, 303, 307, 308):
                loc = resp_headers.get("Location")
                if not loc:
                    return current, status, resp_headers, body
                next_url = urljoin(current, loc)
                if any(urlsplit(next_url).path.startswith(p) or next_url.startswith(p) for p in stop_prefixes):
                    return next_url, status, resp_headers, body
                current = next_url
                continue
            return current, status, resp_headers, body
        raise BootstrapError(f"too many redirects starting from {url}")

    def proxy_json(
        self,
        method: str,
        proxy_path: str,
        *,
        payload: dict[str, Any] | list[Any] | None = None,
        ok_codes: tuple[int, ...] = (200,),
    ) -> dict[str, Any]:
        if not proxy_path.startswith("/api/v1/web/proxy/"):
            raise ValueError(f"proxy_json path must start with /api/v1/web/proxy/: {proxy_path}")
        if "/panel/hub/subscriptions" in proxy_path and method.upper() == "POST":
            raise SafetyRefusal("refusing to call /panel/hub/subscriptions/; Portal subscriptions only")
        headers = {
            "Accept": "application/json",
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/panel/",
        }
        raw_body: bytes | None = None
        if payload is not None:
            raw_body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        status, _, body = self.raw_request(method.upper(), proxy_path, data=raw_body, headers=headers)
        if status not in ok_codes:
            raise BootstrapError(f"{method} {proxy_path} failed with HTTP {status}: {body.decode('utf-8', 'replace')[:400]}")
        doc = json.loads(body.decode("utf-8")) if body else {}
        if isinstance(doc, dict) and doc.get("error"):
            raise BootstrapError(f"{method} {proxy_path} returned error: {doc['error']}")
        return doc

    def upload_file(self, proxy_path: str, file_path: Path) -> str:
        raw, content_type = _encode_multipart_file("file", file_path.name, file_path.read_bytes())
        headers = {
            "Accept": "application/json",
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/panel/",
            "Content-Type": content_type,
        }
        status, _, body = self.raw_request("POST", proxy_path, data=raw, headers=headers)
        if status != 200:
            raise BootstrapError(f"upload {proxy_path} failed HTTP {status}: {body.decode('utf-8', 'replace')[:400]}")
        doc = json.loads(body.decode("utf-8"))
        if doc.get("error"):
            raise BootstrapError(f"upload {proxy_path} error: {doc['error']}")
        upload_ref = (doc.get("value") or {}).get("uploadRef")
        if not upload_ref:
            raise BootstrapError(f"upload response missing value.uploadRef: {doc}")
        return str(upload_ref)


def _resolve_cas_login_prompt(
    session: HttpSession,
    current_url: str,
    status: int,
    body: bytes,
    *,
    namespace: str,
) -> tuple[dict[str, Any], str]:
    parsed = urlsplit(current_url)
    if parsed.path.endswith("/login/cas"):
        tx_id = parse_qs(parsed.query).get("transaction", [""])[0]
        if not tx_id:
            raise BootstrapError(f"CAS SPA login redirect missing transaction: {current_url}")
        status, _, body = session.raw_request(
            "GET",
            f"/oauth/login?{urlencode({'transaction': tx_id})}",
            headers={"Accept": "application/json"},
        )
        current_url = urljoin(session.base_url + "/", f"/oauth/login?{urlencode({'transaction': tx_id})}")
        parsed = urlsplit(current_url)
    if status not in (200, 401):
        raise BootstrapError(f"GET {current_url} returned unexpected HTTP {status}")
    try:
        prompt = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise BootstrapError(f"CAS /oauth/login did not return valid JSON prompt (HTTP {status})") from exc
    if prompt.get("interaction") not in ("login", "password_change"):
        raise BootstrapError(f"unsupported CAS login interaction state: {prompt.get('interaction')!r}")
    csrf_token = prompt.get("csrfToken") or ""
    tx_id = prompt.get("transaction") or parse_qs(parsed.query).get("transaction", [""])[0]
    eff_ns = prompt.get("namespace") or namespace
    if not csrf_token or not tx_id:
        raise BootstrapError("CAS login prompt missing csrfToken or transaction")
    return prompt, eff_ns


def _list_all_pages(session: HttpSession, base_path: str, page_size: int = 200) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page_num = 1
    sep = "&" if "?" in base_path else "?"
    while True:
        doc = session.proxy_json(
            "GET",
            f"{base_path}{sep}{urlencode({'_pageNum': page_num, '_pageSize': page_size})}",
        )
        batch = doc.get("values") or []
        rows.extend(batch)
        pagination = doc.get("pagination") or {}
        if not pagination.get("hasMore") or len(batch) < page_size:
            break
        page_num += 1
    return rows


def authenticate_bff_session(
    session: HttpSession,
    *,
    namespace: str,
    account: str,
    password: str,
) -> dict[str, Any]:
    """Authenticate an account into the Web BFF session via CAS /oauth/login (handles HTTP 401 csrfToken)."""
    current_url, status, headers, body = session.follow_redirects(
        "/api/v1/web/auth/login?return_to=%2Fpanel%2F",
        headers={"Accept": "application/json"},
    )
    parsed = urlsplit(current_url)
    if parsed.path.endswith("/oauth/login") or parsed.path.endswith("/login/cas") or "interaction" in body.decode("utf-8", "ignore"):
        prompt, eff_ns = _resolve_cas_login_prompt(session, current_url, status, body, namespace=namespace)
        csrf_token = prompt.get("csrfToken") or ""
        tx_id = prompt.get("transaction") or parse_qs(parsed.query).get("transaction", [""])[0]

        form_bytes = urlencode({
            "transaction": tx_id,
            "namespace": eff_ns,
            "account": account,
            "password": password,
            "csrf_token": csrf_token,
        }).encode("utf-8")
        post_status, post_headers, post_body = session.raw_request(
            "POST",
            "/oauth/login",
            data=form_bytes,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "Origin": session.base_url,
            },
        )
        if post_status not in (301, 302, 303, 307, 308):
            raise BootstrapError(f"POST /oauth/login failed HTTP {post_status}: {post_body.decode('utf-8', 'replace')[:300]}")
        loc = post_headers.get("Location") or ""
        if "/oauth/password/change" in loc:
            raise SafetyRefusal(f"account {account} requires an interactive initial password change first")
        session.follow_redirects(loc, headers={"Accept": "text/html,application/json"})

    return session.proxy_json("GET", "/api/v1/web/proxy/panel/profile")


def acquire_pkce_access_token(
    base_url: str,
    ssl_context: ssl.SSLContext,
    *,
    namespace: str,
    account: str,
    password: str,
    client_id: str,
    redirect_uri: str,
    scope: str = "openid profile magicrunner.usage.apps.data.execute",
    timeout: int = 30,
    on_password_changed: Callable[[str], None] | None = None,
) -> str:
    """Acquire an OAuth2 S256 PKCE + nonce Access Token with cookie-free /oauth/token exchange."""
    browser = HttpSession(base_url, ssl_context, use_cookies=True, timeout=timeout)
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(18)
    nonce = secrets.token_urlsafe(18)

    auth_query = urlencode({
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "namespace": namespace,
        "client_namespace": namespace,
    })
    callback_prefix = redirect_uri.split("?", 1)[0]
    cur_url, status, _, body = browser.follow_redirects(
        f"/api/v1/cas/oauth/authorize?{auth_query}",
        headers={"Accept": "application/json"},
        stop_prefixes=(callback_prefix,),
    )

    def complete_interactive(next_loc: str) -> str:
        loc = next_loc
        for _ in range(6):
            c_url, c_status, _, c_body = browser.follow_redirects(
                loc,
                headers={"Accept": "application/json"},
                stop_prefixes=(callback_prefix,),
            )
            if c_url.startswith(callback_prefix):
                return c_url
            c_parsed = urlsplit(c_url)
            if c_parsed.path.endswith("/oauth/login") or c_parsed.path.endswith("/login/cas"):
                c_prompt, c_ns = _resolve_cas_login_prompt(browser, c_url, c_status, c_body, namespace=namespace)
                if c_prompt.get("interaction") != "password_change":
                    raise BootstrapError("CAS returned login prompt again after credential submission")
                new_pw = "SimOp!" + secrets.token_urlsafe(18)
                p_tx = c_prompt.get("transaction") or parse_qs(c_parsed.query).get("transaction", [""])[0]
                p_csrf = c_prompt.get("csrfToken") or ""
                pw_form = urlencode({
                    "transaction": p_tx,
                    "namespace": c_ns,
                    "password": new_pw,
                    "password_confirm": new_pw,
                    "csrf_token": p_csrf,
                }).encode("utf-8")
                pw_status, pw_hdrs, pw_body = browser.raw_request(
                    "POST",
                    "/oauth/password/change",
                    data=pw_form,
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Accept": "application/json",
                        "Origin": browser.base_url,
                    },
                )
                if pw_status not in (301, 302, 303, 307, 308):
                    raise BootstrapError(
                        f"POST /oauth/password/change failed HTTP {pw_status}: {pw_body.decode('utf-8', 'replace')[:300]}"
                    )
                if on_password_changed is not None:
                    on_password_changed(new_pw)
                loc = pw_hdrs.get("Location") or ""
                continue

            if not c_parsed.path.endswith("/oauth/consent"):
                qs = parse_qs(c_parsed.query)
                tx_q = qs.get("transaction", [""])[0]
                ns_q = qs.get("namespace", [namespace])[0]
                if tx_q and c_status == 200 and not c_body.lstrip().startswith(b"{"):
                    c_status, _, c_body = browser.raw_request(
                        "GET",
                        f"/oauth/consent?{urlencode({'transaction': tx_q, 'namespace': ns_q})}",
                        headers={"Accept": "application/json"},
                    )
                    c_url = urljoin(
                        browser.base_url + "/",
                        f"/oauth/consent?{urlencode({'transaction': tx_q, 'namespace': ns_q})}",
                    )
                    c_parsed = urlsplit(c_url)

            if c_parsed.path.endswith("/oauth/consent") and c_status == 200:
                consent_doc = json.loads(c_body.decode("utf-8"))
                c_csrf = consent_doc.get("csrfToken") or ""
                c_tx = consent_doc.get("transaction") or parse_qs(c_parsed.query).get("transaction", [""])[0]
                c_ns = consent_doc.get("namespace") or parse_qs(c_parsed.query).get("namespace", [namespace])[0]
                consent_form = urlencode({
                    "transaction": c_tx,
                    "namespace": c_ns,
                    "csrf_token": c_csrf,
                    "decision": "approve",
                }).encode("utf-8")
                p_status, p_hdrs, p_body = browser.raw_request(
                    "POST",
                    "/oauth/consent",
                    data=consent_form,
                    headers={
                        "Content-Type": "application/x-www-form-urlencoded",
                        "Accept": "application/json",
                        "Origin": browser.base_url,
                    },
                )
                if p_status not in (301, 302, 303, 307, 308):
                    raise BootstrapError(
                        f"POST /oauth/consent failed HTTP {p_status}: {p_body.decode('utf-8', 'replace')[:300]}"
                    )
                loc = p_hdrs.get("Location") or ""
                continue

            raise BootstrapError(f"unexpected OAuth post-login interaction URL {c_url} (HTTP {c_status})")
        raise BootstrapError("too many interactive OAuth hops without callback")

    if not cur_url.startswith(callback_prefix):
        cur_path = urlsplit(cur_url).path
        if not (cur_path.endswith("/oauth/login") or cur_path.endswith("/login/cas")):
            raise BootstrapError(f"unexpected OAuth authorize stop URL {cur_url} (HTTP {status})")
        prompt, eff_ns = _resolve_cas_login_prompt(browser, cur_url, status, body, namespace=namespace)
        if prompt.get("interaction") != "login":
            raise BootstrapError(f"unexpected initial CAS authorize interaction: {prompt.get('interaction')!r}")
        csrf_token = prompt.get("csrfToken") or ""
        tx_id = prompt.get("transaction") or parse_qs(urlsplit(cur_url).query).get("transaction", [""])[0]
        form_bytes = urlencode({
            "transaction": tx_id,
            "namespace": eff_ns,
            "account": account,
            "password": password,
            "csrf_token": csrf_token,
        }).encode("utf-8")
        p_status, p_hdrs, p_body = browser.raw_request(
            "POST",
            "/oauth/login",
            data=form_bytes,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "Origin": browser.base_url,
            },
        )
        if p_status not in (301, 302, 303, 307, 308):
            raise BootstrapError(f"OAuth PKCE login failed HTTP {p_status}: {p_body.decode('utf-8', 'replace')[:300]}")
        cur_url = complete_interactive(p_hdrs.get("Location") or "")

    cb_qs = parse_qs(urlsplit(cur_url).query)
    if cb_qs.get("error"):
        raise BootstrapError(f"OAuth authorize error: {cb_qs['error'][0]}")
    if cb_qs.get("state", [""])[0] != state or not cb_qs.get("code"):
        raise BootstrapError(f"OAuth callback missing code or state mismatch: {cur_url}")
    auth_code = cb_qs["code"][0]

    # Critical invariant: /oauth/token rejects requests carrying browser cookies.
    cookie_free = HttpSession(base_url, ssl_context, use_cookies=False, timeout=timeout)
    token_form = urlencode({
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": verifier,
        "namespace": namespace,
        "client_namespace": namespace,
    }).encode("utf-8")
    t_status, _, t_body = cookie_free.raw_request(
        "POST",
        "/api/v1/cas/oauth/token",
        data=token_form,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
    )
    if t_status != 200:
        raise BootstrapError(f"POST /api/v1/cas/oauth/token failed HTTP {t_status}: {t_body.decode('utf-8', 'replace')[:300]}")
    token_doc = json.loads(t_body.decode("utf-8"))
    access_token = str(token_doc.get("access_token") or "")
    if not access_token:
        raise BootstrapError("OAuth token response missing access_token")
    token_bytes = len(access_token.encode("utf-8"))
    if token_bytes > MAX_ACTION_TOKEN_BYTES:
        raise SafetyRefusal(
            f"OAuth action token ({token_bytes} bytes) exceeds 16 KiB limit; assign a least-privilege role template"
        )
    return access_token


def preview_endpoint_authority(
    session: HttpSession,
    *,
    namespace: str,
    endpoint_id: int,
    account_id: int,
    role_template_keys: list[str],
    scope: str,
    status: int,
    start_time: int,
    expire_time: int,
) -> dict[str, Any]:
    """Preview endpoint authority while always supplying explicit accountId required by CAS."""
    if account_id <= 0:
        raise ValueError("authority/preview requires a positive accountId")
    return session.proxy_json(
        "POST",
        f"/api/v1/web/proxy/cas/namespaces/{namespace}/endpoints/{endpoint_id}/authority/preview",
        payload={
            "accountId": account_id,
            "roleTemplateKeys": role_template_keys,
            "scope": scope,
            "status": status,
            "startTime": start_time,
            "expireTime": expire_time,
        },
    )


def package_zip_path(platform_root: Path, app_key: str) -> Path:
    return platform_root / "apps/models" / app_key / "package/package.zip"


def package_sha256(zip_path: Path) -> str:
    return "sha256:" + hashlib.sha256(zip_path.read_bytes()).hexdigest()


def ensure_installations(
    session: HttpSession,
    platform_root: Path,
    *,
    namespace: str,
    apps: list[str],
    reuse_existing: bool,
    wait_seconds: int = 180,
) -> dict[str, dict[str, Any]]:
    list_doc = session.proxy_json("GET", "/api/v1/web/proxy/panel/application/installations/?_pageSize=200")
    existing = list_doc.get("values") or []
    result: dict[str, dict[str, Any]] = {}

    for app_key in apps:
        spec = APP_SPECS[app_key]
        matched = next(
            (
                row for row in existing
                if row.get("applicationUuid") == spec["uuid"]
                and row.get("status") not in ("uninstalled",)
            ),
            None,
        )
        if matched is not None:
            status = str(matched.get("status") or "")
            if status == "ready" and not reuse_existing:
                raise SafetyRefusal(
                    f"installation for {app_key} (id={matched.get('id')}, status=ready) already exists; pass --reuse-existing to continue without altering ready instances"
                )
            if status == "ready":
                result[app_key] = {
                    "action": "reused",
                    "installationId": matched.get("id"),
                    "deploymentId": matched.get("deploymentId"),
                    "runtimeApplicationUuid": (matched.get("receipt") or {}).get("runtimeApplicationUuid"),
                    "status": status,
                }
                continue
            raise BootstrapError(
                f"existing installation for {app_key} is in non-ready state '{status}' (id={matched.get('id')}); inspect owner operation instead of re-installing"
            )

        pkg_file = package_zip_path(platform_root, app_key)
        upload_ref = session.upload_file(
            "/api/v1/web/proxy/files/self/files/upload-references/?purpose=application-model-package",
            pkg_file,
        )
        try:
            imp_doc = session.proxy_json(
                "POST",
                "/api/v1/web/proxy/panel/application/model-packages/imports/",
                payload={"uploadRef": upload_ref},
            )
            pkg = imp_doc.get("value") or {}
        except BootstrapError:
            pkgs = session.proxy_json("GET", "/api/v1/web/proxy/panel/application/model-packages/?_pageSize=200").get("values") or []
            pkg = next((p for p in pkgs if p.get("applicationUuid") == spec["uuid"]), {})
            if not pkg.get("id"):
                raise

        package_id = int(pkg["id"])
        source_digest = str(pkg.get("artifactDigest") or pkg.get("digest") or pkg.get("sourceDigest") or "")
        storage_opts = session.proxy_json(
            "GET",
            "/api/v1/web/proxy/panel/application/installations/storage-options/?"
            + urlencode({"applicationUuid": spec["uuid"], "sourceDigest": source_digest}),
        ).get("value") or {}

        req_body: dict[str, Any] = {
            "sourceKind": "model-package",
            "packageId": package_id,
            "instanceKey": spec["instanceKey"],
            "instanceName": spec["instanceName"],
            "expectedDigest": source_digest,
            "reason": f"bootstrap simulated app {app_key}",
        }
        if spec["storageRequired"] and (storage_opts.get("allocation") or {}).get("available", True):
            req_body["storageProvisioning"] = {"mode": "allocate"}

        req_doc = session.proxy_json(
            "POST",
            "/api/v1/web/proxy/panel/application/deployment-requests/",
            payload=req_body,
        )
        req_row = req_doc.get("value") or {}
        req_id = int(req_row["id"])
        req_version = int(req_row.get("version") or 1)
        req_ns = str(req_row.get("namespace") or namespace)

        runtime_opts = session.proxy_json(
            "GET",
            f"/api/v1/web/proxy/panel/operations/namespaces/{req_ns}/application-deployment-requests/{req_id}/runtime-options",
        ).get("values") or []
        placement: dict[str, str] = {}
        for opt in runtime_opts:
            if opt.get("kind") == "base" and "executionInstanceId" not in placement:
                placement["executionInstanceId"] = str(opt["id"])
            elif opt.get("kind") == "gateway" and "gatewayInstanceId" not in placement:
                placement["gatewayInstanceId"] = str(opt["id"])

        approve_payload: dict[str, Any] = {
            "expectedVersion": req_version,
            "reason": f"approve bootstrap install {app_key}",
        }
        if placement:
            approve_payload["runtimePlacement"] = placement
        app_doc = session.proxy_json(
            "POST",
            f"/api/v1/web/proxy/panel/operations/namespaces/{req_ns}/application-deployment-requests/{req_id}/approve",
            payload=approve_payload,
        ).get("value") or {}
        op_id = app_doc.get("operationId") or ""

        deadline = time.monotonic() + wait_seconds
        while time.monotonic() < deadline and op_id:
            op_doc = session.proxy_json(
                "GET",
                f"/api/v1/web/proxy/panel/operations/namespaces/{req_ns}/application-deployment-operations/{op_id}",
            ).get("value") or {}
            op_status = op_doc.get("status")
            if op_status == "succeeded":
                break
            if op_status in ("failed", "cancelled", "rejected"):
                raise BootstrapError(f"deployment operation {op_id} ended with status={op_status}: {op_doc.get('failure')}")
            time.sleep(2)

        refreshed = session.proxy_json("GET", "/api/v1/web/proxy/panel/application/installations/?_pageSize=200").get("values") or []
        final_inst = next(
            (r for r in refreshed if r.get("applicationUuid") == spec["uuid"] and r.get("status") == "ready"),
            None,
        )
        if final_inst is None:
            raise BootstrapError(f"installation for {app_key} did not become ready within {wait_seconds}s")
        result[app_key] = {
            "action": "installed",
            "installationId": final_inst.get("id"),
            "deploymentId": final_inst.get("deploymentId"),
            "runtimeApplicationUuid": (final_inst.get("receipt") or {}).get("runtimeApplicationUuid"),
            "status": "ready",
        }
    return result


def _resolve_ready_installations(
    session: HttpSession,
    apps: list[str],
    installations: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    resolved: dict[str, dict[str, Any]] = {}
    need_fetch = False
    for app_key in apps:
        row = (installations or {}).get(app_key) or {}
        if row.get("deploymentId") and row.get("runtimeApplicationUuid"):
            resolved[app_key] = {
                "deploymentId": str(row["deploymentId"]),
                "runtimeApplicationUuid": str(row["runtimeApplicationUuid"]),
            }
        else:
            need_fetch = True
    if not need_fetch:
        return resolved

    rows = _list_all_pages(session, "/api/v1/web/proxy/panel/application/installations/")
    for app_key in apps:
        if app_key in resolved:
            continue
        spec = APP_SPECS[app_key]
        matched = next(
            (r for r in rows if r.get("applicationUuid") == spec["uuid"] and r.get("status") == "ready"),
            None,
        )
        if matched is None:
            raise BootstrapError(f"ready installation not found for {app_key}")
        dep_id = str(matched.get("deploymentId") or "")
        rt_uuid = str((matched.get("receipt") or {}).get("runtimeApplicationUuid") or "")
        if not dep_id or not rt_uuid:
            raise BootstrapError(f"ready installation for {app_key} missing deploymentId or runtimeApplicationUuid")
        resolved[app_key] = {"deploymentId": dep_id, "runtimeApplicationUuid": rt_uuid}
    return resolved


def _select_preferred_template(
    templates: list[dict[str, Any]],
    *,
    subject_type: str,
    deployment_id: str,
    preferred_keys: tuple[str, ...],
    required_role_keys: tuple[str, ...] = (),
) -> dict[str, Any] | None:
    app_module = f"/applications/{deployment_id}"
    candidates = [
        t for t in templates
        if t.get("subjectType") == subject_type
        and int(t.get("status") or 0) == 2
        and (
            any(r.get("module") == app_module for r in (t.get("roleRefs") or []))
            or deployment_id in str(t.get("key") or "")
        )
        and all(
            any(r.get("module") == app_module and r.get("key") == req for r in (t.get("roleRefs") or []))
            for req in required_role_keys
        )
    ]
    for pref in preferred_keys:
        hit = next((t for t in candidates if pref in str(t.get("key") or "")), None)
        if hit is not None:
            return hit
    return candidates[0] if candidates else None


def _ensure_endpoint_role_binding(
    session: HttpSession,
    *,
    namespace: str,
    deployment_id: str,
    endpoint_id: int,
    templates: list[dict[str, Any]],
) -> str:
    ep_tpl = _select_preferred_template(
        templates,
        subject_type="endpoint",
        deployment_id=deployment_id,
        preferred_keys=("collector", "channel-ingestor"),
    )
    if ep_tpl is None:
        raise BootstrapError(f"no enabled CAS endpoint role template found for deployment {deployment_id}")
    ep_tpl_key = str(ep_tpl["key"])

    ep = session.proxy_json(
        "GET",
        f"/api/v1/web/proxy/cas/namespaces/{namespace}/endpoints/{endpoint_id}",
    ).get("value") or {}
    owner_account_id = int((ep.get("account") or {}).get("id") or 0)
    if owner_account_id <= 0:
        raise BootstrapError(f"CAS endpoint {endpoint_id} missing owning account id")

    acc = session.proxy_json(
        "GET",
        f"/api/v1/web/proxy/cas/namespaces/{namespace}/accounts/{owner_account_id}",
    ).get("value") or {}
    app_module = f"/applications/{deployment_id}"
    effective_roles = {(r.get("module"), r.get("key")) for r in (acc.get("effectiveRoles") or [])}
    needed_roles = {
        (r.get("module"), r.get("key"))
        for r in (ep_tpl.get("roleRefs") or [])
        if r.get("module") == app_module
    }
    if not needed_roles.issubset(effective_roles):
        acc_tpl = _select_preferred_template(
            templates,
            subject_type="account",
            deployment_id=deployment_id,
            preferred_keys=("operator", "master-data", "platform-ops", "store-manager"),
            required_role_keys=("application-data-write",),
        )
        if acc_tpl is None:
            raise BootstrapError(
                f"no enabled CAS account role template covering application-data-write found for deployment {deployment_id}"
            )
        acc_tpl_key = str(acc_tpl["key"])
        existing_keys = [str(ref["key"]) for ref in (acc.get("templateRefs") or []) if ref.get("key")]
        if acc_tpl_key not in existing_keys:
            existing_keys.append(acc_tpl_key)
        tpl_by_key = {str(t.get("key") or ""): t for t in templates}
        bindings = _list_all_pages(
            session,
            f"/api/v1/web/proxy/cas/namespaces/{namespace}/subject-role-bindings/?"
            + urlencode({"subjectId": f"{owner_account_id}|=", "subjectType": "account|="}),
        )
        app_scopes: list[dict[str, Any]] = []
        seen_scope_keys: set[str] = set()
        for b in bindings:
            if b.get("sourceType") == "template" and int(b.get("status") or 0) == 2 and b.get("applicationAccess"):
                skey = str(b.get("sourceKey") or "")
                if skey and skey in existing_keys and skey not in seen_scope_keys:
                    app_scopes.append({"templateKey": skey, "applicationAccess": b["applicationAccess"]})
                    seen_scope_keys.add(skey)
        for key in existing_keys:
            if key in seen_scope_keys:
                continue
            tpl_obj = tpl_by_key.get(key) or {}
            if tpl_obj.get("applicationAccess"):
                app_scopes.append({
                    "templateKey": key,
                    "applicationAccess": [{"applicationUuid": deployment_id, "accessLevel": "manager"}],
                })
                seen_scope_keys.add(key)
        session.proxy_json(
            "PUT",
            f"/api/v1/web/proxy/cas/namespaces/{namespace}/accounts/{owner_account_id}/role-templates",
            payload={"roleTemplateKeys": existing_keys, "applicationScopes": app_scopes},
        )

    session.proxy_json(
        "PUT",
        f"/api/v1/web/proxy/cas/namespaces/{namespace}/endpoints/{endpoint_id}/role-templates",
        payload={"roleTemplateKeys": [ep_tpl_key]},
    )
    return ep_tpl_key


def ensure_portal_subscriptions_and_keys(
    session: HttpSession,
    secrets_dir: Path,
    *,
    namespace: str,
    apps: list[str],
    installations: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    resolved_installations = _resolve_ready_installations(session, apps, installations)
    panel_svcs = _list_all_pages(session, "/api/v1/web/proxy/panel/hub/services/")
    panel_pubs = _list_all_pages(session, "/api/v1/web/proxy/panel/hub/publications/")
    panel_caps: list[dict[str, Any]] | None = None
    role_templates = _list_all_pages(session, f"/api/v1/web/proxy/cas/namespaces/{namespace}/role-templates/")
    out: dict[str, dict[str, Any]] = {}

    for app_key in apps:
        spec = APP_SPECS[app_key]
        inst = resolved_installations[app_key]
        deployment_id = inst["deploymentId"]
        runtime_app_uuid = inst["runtimeApplicationUuid"]

        svc = next((row for row in panel_svcs if row.get("key") in spec["serviceKeys"]), None)
        pub: dict[str, Any] | None = None
        if svc is None:
            if panel_caps is None:
                panel_caps = _list_all_pages(session, "/api/v1/web/proxy/panel/hub/capabilitys/")
            matched_caps = [
                c for c in panel_caps
                if c.get("providerType") == "application"
                and c.get("providerKey") == runtime_app_uuid
                and int(c.get("status") or 0) == 1
            ]
            cap_ids = sorted(int(c["id"]) for c in matched_caps)
            if not cap_ids:
                raise BootstrapError(
                    f"no enabled source capabilities found for {app_key} (runtimeApplicationUuid={runtime_app_uuid})"
                )
            svc_key_desired = spec["serviceKeys"][0]
            converge_doc = session.proxy_json(
                "POST",
                "/api/v1/web/proxy/panel/hub/services/generated/converge/",
                payload={
                    "items": [{
                        "service": {
                            "key": svc_key_desired,
                            "name": svc_key_desired,
                            "showName": spec["instanceName"],
                        },
                        "capabilityIDs": cap_ids,
                        "publication": {
                            "status": 1,
                            "visibleScope": namespace,
                            "allowSubscription": True,
                            "requireApproval": False,
                            "maxSubscriptions": 10,
                            "maxQPS": 50,
                            "dailyQuota": 100000,
                        },
                    }]
                },
            )
            converged_items = converge_doc.get("values") or []
            if not converged_items:
                raise BootstrapError(f"generated service convergence for {app_key} returned no item")
            svc = converged_items[0].get("service") or {}
            pub = converged_items[0].get("publication") or {}
        svc_id = int(svc["id"])
        svc_key = str(svc["key"])

        if pub is None:
            pub = next((p for p in panel_pubs if int((p.get("service") or {}).get("id") or 0) == svc_id), None)
        if pub is None:
            pub = session.proxy_json(
                "POST",
                "/api/v1/web/proxy/panel/hub/publications/",
                payload={
                    "service": {"id": svc_id},
                    "status": 1,
                    "visibleScope": namespace,
                    "allowSubscription": True,
                    "requireApproval": False,
                    "maxSubscriptions": 10,
                    "maxQPS": 50,
                    "dailyQuota": 100000,
                },
            ).get("value") or {}
        pub_id = int(pub["id"])
        if int(pub.get("status") or 0) != 2:
            session.proxy_json(
                "PUT",
                f"/api/v1/web/proxy/panel/hub/publication/publish/{pub_id}",
                payload={},
            )

        portal_svcs = _list_all_pages(session, "/api/v1/web/proxy/portal/services/")
        portal_svc = next((row for row in portal_svcs if int(row.get("id") or 0) == svc_id), None)
        if portal_svc is None:
            raise BootstrapError(f"Portal service id={svc_id} ({svc_key}) not visible after publication")

        sub_action = "existing"
        if int((portal_svc.get("leaseTerm") or {}).get("status") or 0) != 2:
            request_id = uuid.uuid4().hex
            sub_res = session.proxy_json(
                "POST",
                "/api/v1/web/proxy/portal/service/subscriptions/",
                payload={"requestId": request_id, "service": svc_id, "leaseTerm": 1},
            )
            outcome = sub_res.get("value") or {}
            if outcome.get("phase") not in (None, "complete"):
                for _ in range(15):
                    polled = session.proxy_json(
                        "GET",
                        f"/api/v1/web/proxy/portal/service/subscription-requests/{request_id}?service={svc_id}",
                    ).get("value") or {}
                    if polled.get("phase") == "complete":
                        break
                    time.sleep(1)
            sub_action = "subscribed"

        key_path = secrets_dir / f"{app_key}.api-key"
        key_action = "reused_local"
        endpoint_id = 0
        if not key_path.exists():
            cred_doc = session.proxy_json(
                "POST",
                "/api/v1/web/proxy/portal/service/credentials/",
                payload={"service": svc_id, "name": f"bootstrap-{app_key}-{secrets.token_hex(4)}"},
            )
            cred_val = cred_doc.get("value") or {}
            endpoint_id = int(cred_val.get("endpointId") or 0)
            api_key = str(cred_doc.get("apiKey") or cred_val.get("apiKey") or "")
            if not api_key:
                raise BootstrapError(f"credential creation for {svc_key} returned no apiKey")
            write_secret_file(key_path, api_key)
            key_action = "created"

        if endpoint_id <= 0:
            cred_rows = _list_all_pages(
                session,
                f"/api/v1/web/proxy/portal/service/credentials/?service={svc_id}",
            )
            active_cred = next((r for r in cred_rows if int(r.get("endpointId") or 0) > 0), None)
            if active_cred is None:
                raise BootstrapError(f"no Portal credential with endpointId found for service id={svc_id}")
            endpoint_id = int(active_cred["endpointId"])

        ep_tpl_key = _ensure_endpoint_role_binding(
            session,
            namespace=namespace,
            deployment_id=deployment_id,
            endpoint_id=endpoint_id,
            templates=role_templates,
        )

        out[app_key] = {
            "serviceId": svc_id,
            "serviceKey": svc_key,
            "subscription": sub_action,
            "apiKeyStatus": key_action,
            "apiKeyFile": str(key_path),
            "endpointId": endpoint_id,
            "endpointTemplateKey": ep_tpl_key,
        }
    return out


def ensure_crb_operator_token(
    session: HttpSession,
    secrets_dir: Path,
    *,
    namespace: str,
    deployment_id: str,
    operator_account: str,
    operator_password: str,
    ssl_context: ssl.SSLContext,
    on_password_changed: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    crb_uuid = APP_SPECS["chess-room-booking"]["uuid"]
    templates = _list_all_pages(session, f"/api/v1/web/proxy/cas/namespaces/{namespace}/role-templates/")
    chosen_template = _select_preferred_template(
        templates,
        subject_type="account",
        deployment_id=deployment_id,
        preferred_keys=("platform-ops", "store-manager", "frontdesk"),
    )
    if chosen_template is None:
        chosen_template = next(
            (
                t for t in templates
                if t.get("subjectType") == "account"
                and int(t.get("status") or 0) == 2
                and (
                    crb_uuid in str(t.get("key") or "")
                    or any(a.get("applicationUuid") == crb_uuid for a in (t.get("applicationAccess") or []))
                )
            ),
            None,
        )
    if chosen_template is None:
        raise BootstrapError(f"no chess-room-booking account role template found in namespace {namespace}")
    tpl_key = str(chosen_template["key"])

    accounts = _list_all_pages(session, f"/api/v1/web/proxy/cas/namespaces/{namespace}/accounts/")
    acc = next((a for a in accounts if a.get("account") == operator_account), None)
    if acc is None:
        created = session.proxy_json(
            "POST",
            f"/api/v1/web/proxy/cas/namespaces/{namespace}/accounts/",
            payload={
                "account": operator_account,
                "displayName": "CRB Simulation Operator",
                "password": operator_password,
                "email": f"{operator_account}@{namespace}.local",
                "description": "Least-privilege operator for chess-room-booking simulation",
                "status": 2,
                "roleTemplateKeys": [tpl_key],
            },
        )
        acc = created.get("value") or {}
    acc_id = int(acc["id"])

    app_scopes = (
        [{"templateKey": tpl_key, "applicationAccess": [{"applicationUuid": deployment_id, "accessLevel": "manager"}]}]
        if chosen_template.get("applicationAccess")
        else []
    )
    session.proxy_json(
        "PUT",
        f"/api/v1/web/proxy/cas/namespaces/{namespace}/accounts/{acc_id}/role-templates",
        payload={
            "roleTemplateKeys": [tpl_key],
            "applicationScopes": app_scopes,
        },
    )

    desired_scopes = "openid profile magicrunner.usage.apps.data.execute"
    redirect_uri = f"{session.base_url}/oauth/callback"
    clients = _list_all_pages(session, f"/api/v1/web/proxy/cas/namespaces/{namespace}/oauth/clients/")
    client = next(
        (c for c in clients if c.get("name") == "crb-sim-pkce-client" and c.get("clientType") == "public"),
        None,
    )
    if client is None:
        client = session.proxy_json(
            "POST",
            f"/api/v1/web/proxy/cas/namespaces/{namespace}/oauth/clients/",
            payload={
                "name": "crb-sim-pkce-client",
                "developerName": "magicTest",
                "clientType": "public",
                "partyType": "third_party",
                "authenticationNamespaces": [namespace],
                "redirectUris": [redirect_uri],
                "grantTypes": ["authorization_code"],
                "allowedScopes": desired_scopes,
                "scopeDescription": "Least-privilege chess-room-booking simulator token",
                "audience": "api://magicrunner",
                "requirePKCE": True,
                "status": 2,
                "description": "PKCE client for least-privilege CRB simulation actions",
                "endpointId": 0,
            },
        ).get("value") or {}
    else:
        existing_scopes = set(str(client.get("allowedScopes") or "").split())
        if "magicrunner.usage.apps.data.execute" not in existing_scopes or client.get("audience") != "api://magicrunner":
            client = session.proxy_json(
                "PUT",
                f"/api/v1/web/proxy/cas/namespaces/{namespace}/oauth/clients/{client['clientId']}",
                payload={
                    "expectedVersion": int(client.get("version") or 1),
                    "name": client.get("name") or "crb-sim-pkce-client",
                    "developerName": client.get("developerName") or "magicTest",
                    "authenticationNamespaces": client.get("authenticationNamespaces") or [namespace],
                    "redirectUris": client.get("redirectUris") or [redirect_uri],
                    "grantTypes": client.get("grantTypes") or ["authorization_code"],
                    "allowedScopes": desired_scopes,
                    "scopeDescription": client.get("scopeDescription") or "Least-privilege chess-room-booking simulator token",
                    "audience": "api://magicrunner",
                    "requirePKCE": bool(client.get("requirePKCE", True)),
                    "status": int(client.get("status") or 2),
                    "description": client.get("description") or "PKCE client for least-privilege CRB simulation actions",
                    "endpointId": int(client.get("endpointId") or 0),
                },
            ).get("value") or client
    client_id = str(client["clientId"])

    token = acquire_pkce_access_token(
        session.base_url,
        ssl_context,
        namespace=namespace,
        account=operator_account,
        password=operator_password,
        client_id=client_id,
        redirect_uri=redirect_uri,
        scope=desired_scopes,
        timeout=session.timeout,
        on_password_changed=on_password_changed,
    )
    token_path = secrets_dir / "crb-operator.token"
    write_secret_file(token_path, token)
    return {
        "operatorAccount": operator_account,
        "accountId": acc_id,
        "templateKey": tpl_key,
        "clientId": client_id,
        "tokenBytes": len(token.encode("utf-8")),
        "actionTokenFile": str(token_path),
    }


def _sim_tls_args_for_dm(base_url: str, ca_file: Path | None, trust_leaf: bool) -> list[str]:
    if ca_file is not None:
        args = ["--ca-file", str(ca_file)]
        if not trust_leaf:
            args.append("--ca-is-root")
        return args
    if urlsplit(base_url).hostname and not str(urlsplit(base_url).hostname).endswith(".local.vpc"):
        sys_ca = resolve_system_ca_file()
        if sys_ca is not None:
            return ["--ca-file", str(sys_ca), "--ca-is-root"]
    return []


def _sim_tls_args_for_crb(ca_file: Path | None, trust_leaf: bool) -> list[str]:
    if ca_file is None:
        return []
    args = ["--ca-file", str(ca_file)]
    if trust_leaf:
        args.append("--trust-leaf")
    return args


def _run_subprocess(cmd: list[str], env: dict[str, str]) -> str:
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise BootstrapError(f"command failed ({proc.returncode}): {' '.join(cmd)}\nstdout: {proc.stdout}\nstderr: {proc.stderr}")
    return proc.stdout


def run_seed_and_verify(
    *,
    action: str,
    base_url: str,
    state_dir: Path,
    secrets_dir: Path,
    platform_root: Path,
    services_info: dict[str, dict[str, Any]],
    apps: list[str],
    ca_file: Path | None,
    trust_leaf: bool,
    cycles: int,
    anchor_utc: str | None,
    target_address: str | None = None,
) -> dict[str, Any]:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "MAGICPLATFORM_ROOT": str(platform_root)}
    if target_address and target_address.strip():
        env["MAGICTEST_TARGET_ADDRESS"] = target_address.strip()
    results: dict[str, Any] = {}

    if "device-management" in apps:
        dm_tool = APPLICATIONS_ROOT / "device-management/tooling/simulator.py"
        runs_dir = ensure_private_dir(state_dir / "runs")
        dm_run_dir = runs_dir / "device-management"
        dm_cfg = dm_run_dir / "config.json"
        dm_key_file = Path(services_info["device-management"]["apiKeyFile"]) if "device-management" in services_info else (secrets_dir / "device-management.api-key")
        dm_svc_key = services_info.get("device-management", {}).get("serviceKey", "device_management_service")
        dm_svc_url = f"{base_url}/api/v1/gateway/services/{dm_svc_key}"

        if action in ("seed-data", "all"):
            if not dm_cfg.exists():
                init_cmd = [
                    sys.executable, "-B", str(dm_tool), "init",
                    "--scenario", "live-stream-v1",
                    "--api-key-file", str(dm_key_file),
                    "--run-dir", str(dm_run_dir),
                    "--service-url", dm_svc_url,
                    *_sim_tls_args_for_dm(base_url, ca_file, trust_leaf),
                ]
                _run_subprocess(init_cmd, env)
            _run_subprocess([sys.executable, "-B", str(dm_tool), "seed", "--config", str(dm_cfg)], env)
            _run_subprocess([sys.executable, "-B", str(dm_tool), "backfill", "--config", str(dm_cfg)], env)
            _run_subprocess([sys.executable, "-B", str(dm_tool), "live-stream", "--config", str(dm_cfg), "--cycles", str(cycles)], env)

        if action in ("verify", "all"):
            if not dm_cfg.exists():
                raise BootstrapError(f"missing device-management config for verify: {dm_cfg}")
            _run_subprocess([sys.executable, "-B", str(dm_tool), "verify", "--config", str(dm_cfg)], env)
        results["device-management"] = {"runDir": str(dm_run_dir), "serviceUrl": dm_svc_url}

    if "chess-room-booking" in apps:
        crb_tool = APPLICATIONS_ROOT / "chess-room-booking/tooling/simulation_tool.py"
        crb_state_dir = ensure_private_dir(state_dir / "runs/chess-room-booking")
        plan_path = state_dir / "runs/crb-plan.json"
        crb_key_file = Path(services_info["chess-room-booking"]["apiKeyFile"]) if "chess-room-booking" in services_info else (secrets_dir / "chess-room-booking.api-key")
        crb_tok_file = secrets_dir / "crb-operator.token"
        crb_svc_key = services_info.get("chess-room-booking", {}).get("serviceKey", "chess_room_booking_simulation")
        crb_svc_url = f"{base_url}/api/v1/gateway/services/{crb_svc_key}"
        crb_act_url = f"{base_url}/api/v1/apps/entity/action/execute/"
        tls_args = _sim_tls_args_for_crb(ca_file, trust_leaf)

        if action in ("seed-data", "all"):
            if not plan_path.exists():
                plan_cmd = [
                    sys.executable, "-B", str(crb_tool),
                    "--mode", "seed",
                    "--output", str(plan_path),
                    "plan",
                ]
                if anchor_utc:
                    plan_cmd[3:3] = ["--anchor-utc", anchor_utc]
                _run_subprocess(plan_cmd, env)
            _run_subprocess([
                sys.executable, "-B", str(crb_tool),
                "--mode", "seed",
                "--plan", str(plan_path),
                "--service-url", crb_svc_url,
                "--action-url", crb_act_url,
                "--state-dir", str(crb_state_dir),
                "--api-key-file", str(crb_key_file),
                "--action-token-file", str(crb_tok_file),
                *tls_args,
                "run",
            ], env)

        if action in ("verify", "all"):
            if not plan_path.exists():
                raise BootstrapError(f"missing chess-room-booking plan for verify: {plan_path}")
            _run_subprocess([
                sys.executable, "-B", str(crb_tool),
                "--mode", "seed",
                "--plan", str(plan_path),
                "--service-url", crb_svc_url,
                "--state-dir", str(crb_state_dir),
                "--api-key-file", str(crb_key_file),
                "--wait-seconds", "60",
                *tls_args,
                "verify",
            ], env)
        results["chess-room-booking"] = {"stateDir": str(crb_state_dir), "planFile": str(plan_path), "serviceUrl": crb_svc_url}

    return results


def parse_apps(raw: str) -> list[str]:
    selected = [item.strip() for item in raw.split(",") if item.strip()]
    invalid = [item for item in selected if item not in APP_SPECS]
    if not selected or invalid:
        raise ValueError(f"unsupported app selector {raw!r}; expected subset of {sorted(APP_SPECS)}")
    return selected


def build_dry_run_plan(args: argparse.Namespace, platform_root: Path, apps: list[str]) -> dict[str, Any]:
    base_url = validate_base_url(args.base_url)
    app_plans = {}
    for app_key in apps:
        pkg = package_zip_path(platform_root, app_key)
        app_plans[app_key] = {
            "uuid": APP_SPECS[app_key]["uuid"],
            "packageZip": str(pkg),
            "packageExists": pkg.is_file(),
            "packageSha256": package_sha256(pkg) if pkg.is_file() else "",
        }
    return {
        "mode": "dry-run",
        "command": args.command,
        "baseUrl": base_url,
        "targetAddress": (args.target_address or "").strip() or None,
        "namespace": args.namespace,
        "reuseExisting": bool(args.reuse_existing),
        "stateDir": str(args.state_dir.expanduser()),
        "apps": app_plans,
        "safetyGuards": [
            "refuses ready installations without --reuse-existing",
            "creates Portal subscriptions only (never /panel/hub/subscriptions/)",
            "exchanges /oauth/token without cookies",
            "enforces <= 16384 byte action token limit using least-privilege operator account",
        ],
    }


def main(argv: list[str] | None = None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--base-url", required=True, help="Target https://panel.<domain> base URL")
    common.add_argument("--namespace", default="panel", help="Target CAS/Panel namespace (default: panel)")
    common.add_argument("--admin-account", default="platform-admin", help="Admin login account (default: platform-admin)")
    common.add_argument("--admin-password-file", type=Path, default=None, help="0600 file containing admin password")
    common.add_argument("--operator-account", default="crb-sim-operator", help="Least-privilege operator for CRB actions")
    common.add_argument("--operator-password-file", type=Path, default=None, help="0600 file for operator password")
    common.add_argument("--platform-root", type=Path, default=None, help="Path to magicPlatform")
    common.add_argument("--state-dir", type=Path, default=Path("~/.local/state/magicTest/bootstrap"), help="0700 working state dir")
    common.add_argument("--ca-file", type=Path, default=None, help="TLS CA / leaf certificate file")
    common.add_argument("--trust-leaf", action="store_true", help="Trust --ca-file as a self-signed leaf certificate")
    common.add_argument("--target-address", default=os.environ.get("MAGICTEST_TARGET_ADDRESS") or None, help="Optional target IP/host override while preserving Host and TLS SNI")
    common.add_argument("--reuse-existing", action="store_true", help="Explicitly allow reusing already-ready installations")
    common.add_argument("--apps", default="device-management,chess-room-booking", help="Comma-separated simulated app keys")
    common.add_argument("--cycles", type=int, default=2, help="device-management live-stream cycles (default: 2)")
    common.add_argument("--anchor-utc", default=None, help="Optional UTC anchor ISO timestamp for chess-room-booking")
    common.add_argument("--timeout", type=int, default=30, help="Per-HTTP request timeout in seconds")
    common.add_argument("--dry-run", action="store_true", help="Validate local inputs and print planned workflow without network")

    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("all", "import-install", "provision-access", "seed-data", "verify"):
        sub.add_parser(name, parents=[common])

    args = parser.parse_args(argv)
    apps = parse_apps(args.apps)
    platform_root = resolve_platform_root(args.platform_root)
    base_url = validate_base_url(args.base_url)

    if args.dry_run:
        print(json.dumps(build_dry_run_plan(args, platform_root, apps), ensure_ascii=False, indent=2))
        return 0

    target_address = (args.target_address or "").strip() or None
    if target_address:
        os.environ["MAGICTEST_TARGET_ADDRESS"] = target_address
    state_dir = ensure_private_dir(args.state_dir)
    secrets_dir = ensure_private_dir(state_dir / "secrets")
    ssl_ctx = make_ssl_context(args.ca_file, trust_leaf=args.trust_leaf)

    summary: dict[str, Any] = {
        "command": args.command,
        "baseUrl": base_url,
        "targetAddress": target_address,
        "namespace": args.namespace,
        "reuseExisting": bool(args.reuse_existing),
        "apps": apps,
    }

    services_info: dict[str, dict[str, Any]] = {}
    session: HttpSession | None = None

    if args.command in ("all", "import-install", "provision-access"):
        admin_pw = read_secret_file(args.admin_password_file, "MAGIC_ADMIN_PASSWORD", label="admin password")
        session = HttpSession(base_url, ssl_ctx, use_cookies=True, timeout=args.timeout)
        authenticate_bff_session(session, namespace=args.namespace, account=args.admin_account, password=admin_pw)

    if args.command in ("all", "import-install") and session is not None:
        summary["installations"] = ensure_installations(
            session,
            platform_root,
            namespace=args.namespace,
            apps=apps,
            reuse_existing=args.reuse_existing,
        )

    if args.command in ("all", "provision-access") and session is not None:
        installations_info = summary.get("installations")
        services_info = ensure_portal_subscriptions_and_keys(
            session,
            secrets_dir,
            namespace=args.namespace,
            apps=apps,
            installations=installations_info,
        )
        summary["portal"] = services_info
        if "chess-room-booking" in apps:
            crb_inst = _resolve_ready_installations(session, ["chess-room-booking"], installations_info)["chess-room-booking"]
            op_pw_path = secrets_dir / f"{args.operator_account}.password"
            if args.operator_password_file is not None:
                op_pw = read_secret_file(args.operator_password_file, label="operator password")
                write_secret_file(op_pw_path, op_pw)
            elif op_pw_path.exists():
                op_pw = read_secret_file(op_pw_path, label="operator password")
            else:
                op_pw = "SimOp!" + secrets.token_urlsafe(18)
                write_secret_file(op_pw_path, op_pw)
            summary["crbOperator"] = ensure_crb_operator_token(
                session,
                secrets_dir,
                namespace=args.namespace,
                deployment_id=crb_inst["deploymentId"],
                operator_account=args.operator_account,
                operator_password=op_pw,
                ssl_context=ssl_ctx,
                on_password_changed=lambda new_pw, p=op_pw_path: write_secret_file(p, new_pw),
            )

    if args.command in ("all", "seed-data", "verify"):
        summary["simulation"] = run_seed_and_verify(
            action=args.command,
            base_url=base_url,
            state_dir=state_dir,
            secrets_dir=secrets_dir,
            platform_root=platform_root,
            services_info=services_info,
            apps=apps,
            ca_file=args.ca_file,
            trust_leaf=args.trust_leaf,
            cycles=args.cycles,
            anchor_utc=args.anchor_utc,
            target_address=target_address,
        )

    summary_path = state_dir / "bootstrap-summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(summary_path, 0o600)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
