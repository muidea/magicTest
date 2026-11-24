#!/usr/bin/env python3
"""Offline unit tests for bootstrap_simulated_apps.py (local mock HTTPS/HTTP test server + unit checks)."""
from __future__ import annotations

import base64
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import ssl
import stat
import sys
import tempfile
import threading
import unittest
from urllib.parse import parse_qs, urlsplit

LIVE_E2E_DIR = Path(__file__).resolve().parent
APPLICATIONS_ROOT = LIVE_E2E_DIR.parent
for entry in (LIVE_E2E_DIR, APPLICATIONS_ROOT):
    if str(entry) not in sys.path:
        sys.path.insert(0, str(entry))

import bootstrap_simulated_apps as bsa


class _MockHttpHandler(BaseHTTPRequestHandler):
    server_state: dict = {}

    def log_message(self, format, *args):  # noqa: A002
        return

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def do_GET(self):  # noqa: N802
        parsed = urlsplit(self.path)
        state = self.__class__.server_state
        state["requests"].append(("GET", parsed.path, dict(self.headers)))

        if parsed.path == "/api/v1/web/auth/login":
            self.send_response(302)
            self.send_header("Location", "/oauth/login?transaction=tx-1")
            self.end_headers()
            return
        if parsed.path == "/oauth/login":
            tx = parse_qs(parsed.query).get("transaction", ["tx-1"])[0]
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.send_header("Set-Cookie", "cas_csrf=csrf-123; Path=/; HttpOnly")
            self.end_headers()
            self.wfile.write(json.dumps({
                "interaction": "login",
                "transaction": tx,
                "namespace": "panel",
                "csrfToken": "csrf-123",
            }).encode("utf-8"))
            return
        if parsed.path == "/api/v1/web/auth/callback":
            self.send_response(200)
            self.send_header("Set-Cookie", "bff_sid=sess-ok; Path=/; HttpOnly")
            self.end_headers()
            self.wfile.write(b"ok")
            return
        if parsed.path == "/api/v1/web/proxy/panel/profile":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"value": {"account": "platform-admin"}}).encode("utf-8"))
            return
        if parsed.path == "/api/v1/web/proxy/panel/application/installations/":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"values": state["installations"]}).encode("utf-8"))
            return
        if parsed.path == "/api/v1/cas/oauth/authorize":
            qs = parse_qs(parsed.query)
            state["authorize_qs"] = qs
            self.send_response(302)
            self.send_header("Location", f"/oauth/login?transaction=tx-pkce")
            self.end_headers()
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):  # noqa: N802
        parsed = urlsplit(self.path)
        body = self._read_body()
        state = self.__class__.server_state
        state["requests"].append(("POST", parsed.path, dict(self.headers)))
        state["bodies"][parsed.path] = body.decode("utf-8", "replace")

        if parsed.path == "/oauth/login":
            form = parse_qs(body.decode("utf-8"))
            tx = form.get("transaction", [""])[0]
            if tx == "tx-pkce":
                st = state["authorize_qs"]["state"][0]
                loc = f"{state['authorize_qs']['redirect_uri'][0]}?code=code-1&state={st}"
            else:
                loc = "/api/v1/web/auth/callback?code=web-1"
            self.send_response(302)
            self.send_header("Set-Cookie", "cas_sso=sso-cookie-1; Path=/; HttpOnly")
            self.send_header("Location", loc)
            self.end_headers()
            return

        if parsed.path == "/api/v1/cas/oauth/token":
            state["token_cookie_header"] = self.headers.get("Cookie")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"access_token": state["issued_token"]}).encode("utf-8"))
            return

        if parsed.path.endswith("/authority/preview"):
            doc = json.loads(body.decode("utf-8"))
            state["preview_payload"] = doc
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"value": {"effectiveRoles": []}}).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()


class _PlainHttpSession(bsa.HttpSession):
    def __init__(self, base_http_url: str, *, use_cookies: bool = True):
        # Allow local http://127.0.0.1 for unit test mocks without HTTPS sockets.
        self.base_url = base_http_url.rstrip("/")
        self.timeout = 10
        from http.cookiejar import CookieJar
        from urllib.request import HTTPCookieProcessor, HTTPHandler, build_opener

        self.cookie_jar = CookieJar() if use_cookies else None
        handlers = [bsa._NoRedirectHandler(), HTTPHandler()]
        if self.cookie_jar is not None:
            handlers.append(HTTPCookieProcessor(self.cookie_jar))
        self.opener = build_opener(*handlers)


class BootstrapSimulatedAppsTests(unittest.TestCase):
    def setUp(self):
        self.state = {
            "requests": [],
            "bodies": {},
            "installations": [
                {"id": 11, "deploymentId": "d1", "applicationUuid": bsa.APP_SPECS["device-management"]["uuid"], "status": "ready"}
            ],
            "issued_token": "tok." + base64.urlsafe_b64encode(b"payload").decode() + ".sig",
            "token_cookie_header": "UNSET",
        }
        _MockHttpHandler.server_state = self.state
        self.server = HTTPServer(("127.0.0.1", 0), _MockHttpHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.http_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def test_dry_run_validates_packages_without_network(self):
        rc = bsa.main(["all", "--base-url", "https://panel.example.com", "--dry-run"])
        self.assertEqual(rc, 0)

    def test_rejects_panel_hub_subscription_endpoint(self):
        sess = _PlainHttpSession(self.http_url)
        with self.assertRaises(bsa.SafetyRefusal):
            sess.proxy_json("POST", "/api/v1/web/proxy/panel/hub/subscriptions/", payload={"service": 1})

    def test_handles_401_csrf_login_and_refuses_ready_without_reuse_existing(self):
        sess = _PlainHttpSession(self.http_url)
        profile = bsa.authenticate_bff_session(sess, namespace="panel", account="platform-admin", password="pw")
        self.assertEqual(profile["value"]["account"], "platform-admin")

        with self.assertRaises(bsa.SafetyRefusal):
            bsa.ensure_installations(
                sess,
                bsa.resolve_platform_root(),
                namespace="panel",
                apps=["device-management"],
                reuse_existing=False,
            )

        reused = bsa.ensure_installations(
            sess,
            bsa.resolve_platform_root(),
            namespace="panel",
            apps=["device-management"],
            reuse_existing=True,
        )
        self.assertEqual(reused["device-management"]["action"], "reused")

    def test_preview_endpoint_authority_includes_account_id(self):
        sess = _PlainHttpSession(self.http_url)
        bsa.preview_endpoint_authority(
            sess,
            namespace="panel",
            endpoint_id=5,
            account_id=42,
            role_template_keys=["collector"],
            scope="openid",
            status=2,
            start_time=100,
            expire_time=200,
        )
        self.assertEqual(self.state["preview_payload"]["accountId"], 42)
        with self.assertRaises(ValueError):
            bsa.preview_endpoint_authority(
                sess, namespace="panel", endpoint_id=5, account_id=0,
                role_template_keys=[], scope="", status=2, start_time=0, expire_time=0,
            )

    def test_pkce_token_exchange_sends_no_cookies_and_rejects_oversized_jwt(self):
        orig_cls = bsa.HttpSession
        http_url = self.http_url

        class _NoHttpsPatch:
            def __call__(self, base_url, ssl_context, *, use_cookies=True, timeout=30):
                return _PlainHttpSession(http_url, use_cookies=use_cookies)

        bsa.HttpSession = _NoHttpsPatch()  # type: ignore[assignment]
        try:
            tok = bsa.acquire_pkce_access_token(
                "https://panel.example.com",
                ssl.create_default_context(),
                namespace="panel",
                account="crb-sim-operator",
                password="pw",
                client_id="cid-1",
                redirect_uri="http://127.0.0.1/cb",
            )
            self.assertEqual(tok, self.state["issued_token"])
            self.assertIsNone(self.state["token_cookie_header"])

            self.state["issued_token"] = "A" * (bsa.MAX_ACTION_TOKEN_BYTES + 1)
            with self.assertRaises(bsa.SafetyRefusal):
                bsa.acquire_pkce_access_token(
                    "https://panel.example.com",
                    ssl.create_default_context(),
                    namespace="panel",
                    account="crb-sim-operator",
                    password="pw",
                    client_id="cid-1",
                    redirect_uri="http://127.0.0.1/cb",
                )
        finally:
            bsa.HttpSession = orig_cls  # type: ignore[assignment]

    def test_secret_file_permissions_enforced(self):
        with tempfile.TemporaryDirectory(prefix="bsa-secret-") as tmp:
            sec_path = Path(tmp) / "secrets/api.key"
            bsa.write_secret_file(sec_path, "secret-value")
            self.assertEqual(stat.S_IMODE(sec_path.stat().st_mode), 0o600)
            self.assertEqual(bsa.read_secret_file(sec_path), "secret-value")
            os.chmod(sec_path, 0o644)
            with self.assertRaises(bsa.SafetyRefusal):
                bsa.read_secret_file(sec_path)


if __name__ == "__main__":
    unittest.main()
