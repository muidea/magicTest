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
            qs = parse_qs(parsed.query)
            tx = qs.get("transaction", ["tx-1"])[0]
            if tx == "tx-pw":
                payload = {
                    "interaction": "password_change",
                    "transaction": tx,
                    "namespace": "panel",
                    "csrfToken": "csrf-pw-1",
                }
            else:
                payload = {
                    "interaction": "login",
                    "transaction": tx,
                    "namespace": "panel",
                    "csrfToken": "csrf-123",
                }
            self.send_response(401)
            self.send_header("Content-Type", "application/json")
            self.send_header("Set-Cookie", "cas_csrf=csrf-123; Path=/; HttpOnly")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode("utf-8"))
            return
        if parsed.path == "/oauth/consent":
            tx = parse_qs(parsed.query).get("transaction", ["tx-consent"])[0]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "interaction": "consent",
                "transaction": tx,
                "namespace": "panel",
                "csrfToken": "csrf-consent-1",
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
        if parsed.path == "/api/v1/web/proxy/panel/application/installations/storage-options/":
            state["storage_options_qs"] = parse_qs(parsed.query)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"value": {"allocation": {"available": True}}}).encode("utf-8"))
            return
        if parsed.path == "/api/v1/web/proxy/panel/operations/namespaces/panel/application-deployment-requests/77/runtime-options":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"values": [{"kind": "base", "id": "b1"}, {"kind": "gateway", "id": "g1"}]}).encode("utf-8"))
            return
        if parsed.path == "/api/v1/web/proxy/panel/operations/namespaces/panel/application-deployment-operations/op-1":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"value": {"status": "succeeded"}}).encode("utf-8"))
            return
        if parsed.path == "/api/v1/cas/oauth/authorize":
            qs = parse_qs(parsed.query)
            state["authorize_qs"] = qs
            tx = "tx-pkce-pw" if state.get("pkce_force_pw_change") else "tx-pkce"
            self.send_response(302)
            self.send_header("Location", f"/oauth/login?transaction={tx}")
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
            state["login_origin"] = self.headers.get("Origin")
            tx = form.get("transaction", [""])[0]
            if tx == "tx-pkce-pw":
                loc = "/login/cas?namespace=panel&transaction=tx-pw"
            elif tx == "tx-pkce":
                st = state["authorize_qs"]["state"][0]
                loc = f"{state['authorize_qs']['redirect_uri'][0]}?code=code-1&state={st}"
            else:
                loc = "/api/v1/web/auth/callback?code=web-1"
            self.send_response(302)
            self.send_header("Set-Cookie", "cas_sso=sso-cookie-1; Path=/; HttpOnly")
            self.send_header("Location", loc)
            self.end_headers()
            return

        if parsed.path == "/oauth/password/change":
            state["pw_change_origin"] = self.headers.get("Origin")
            state["pw_change_form"] = parse_qs(body.decode("utf-8"))
            self.send_response(302)
            self.send_header("Location", "/oauth/consent?transaction=tx-consent&namespace=panel")
            self.end_headers()
            return

        if parsed.path == "/oauth/consent":
            state["consent_origin"] = self.headers.get("Origin")
            st = state["authorize_qs"]["state"][0]
            loc = f"{state['authorize_qs']['redirect_uri'][0]}?code=code-1&state={st}"
            self.send_response(302)
            self.send_header("Location", loc)
            self.end_headers()
            return

        if parsed.path == "/api/v1/web/proxy/files/self/files/upload-references/":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"value": {"uploadRef": "ref-1"}}).encode("utf-8"))
            return

        if parsed.path == "/api/v1/web/proxy/panel/application/model-packages/imports/":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "value": {
                    "id": 55,
                    "applicationUuid": bsa.APP_SPECS["device-management"]["uuid"],
                    "artifactDigest": "sha256:abc123",
                }
            }).encode("utf-8"))
            return

        if parsed.path == "/api/v1/web/proxy/panel/application/deployment-requests/":
            state["deployment_req_body"] = json.loads(body.decode("utf-8"))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"value": {"id": 77, "version": 1, "namespace": "panel"}}).encode("utf-8"))
            return

        if parsed.path == "/api/v1/web/proxy/panel/operations/namespaces/panel/application-deployment-requests/77/approve":
            state["installations"].append({
                "id": 12,
                "deploymentId": "d1",
                "applicationUuid": bsa.APP_SPECS["device-management"]["uuid"],
                "status": "ready",
                "receipt": {"runtimeApplicationUuid": "rt-dm-1"},
            })
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"value": {"operationId": "op-1"}}).encode("utf-8"))
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

        # Also cover SPA redirect to /login/cas?transaction=... before GET /oauth/login.
        prompt, eff_ns = bsa._resolve_cas_login_prompt(
            sess,
            f"{self.http_url}/login/cas?namespace=panel&transaction=tx-spa",
            200,
            b"<html>SPA</html>",
            namespace="panel",
        )
        self.assertEqual(prompt["transaction"], "tx-spa")
        self.assertEqual(prompt["csrfToken"], "csrf-123")
        self.assertEqual(eff_ns, "panel")

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

    def test_target_address_dry_run_and_custom_https_handler(self):
        import io
        from contextlib import redirect_stdout

        ctx = ssl.create_default_context()
        default_handler = bsa._make_https_handler(ctx, None)
        self.assertIs(type(default_handler), bsa.HTTPSHandler)
        custom_handler = bsa._make_https_handler(ctx, "192.168.13.47")
        self.assertIsNot(type(custom_handler), bsa.HTTPSHandler)

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = bsa.main([
                "all",
                "--base-url", "https://panel.local.vpc",
                "--target-address", "192.168.13.47",
                "--dry-run",
            ])
        self.assertEqual(rc, 0)
        plan = json.loads(buf.getvalue())
        self.assertEqual(plan["targetAddress"], "192.168.13.47")

    def test_ensure_installations_uses_artifact_digest_and_captures_runtime_uuid(self):
        self.state["installations"] = []
        sess = _PlainHttpSession(self.http_url)
        installed = bsa.ensure_installations(
            sess,
            bsa.resolve_platform_root(),
            namespace="panel",
            apps=["device-management"],
            reuse_existing=False,
        )
        self.assertEqual(self.state["storage_options_qs"]["sourceDigest"], ["sha256:abc123"])
        self.assertEqual(self.state["deployment_req_body"]["expectedDigest"], "sha256:abc123")
        self.assertEqual(installed["device-management"]["runtimeApplicationUuid"], "rt-dm-1")

    def test_pkce_handles_password_change_consent_origin_and_action_scope(self):
        orig_cls = bsa.HttpSession
        http_url = self.http_url
        self.state["pkce_force_pw_change"] = True
        rotated: list[str] = []

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
                password="initial-pw",
                client_id="cid-1",
                redirect_uri="https://panel.example.com/oauth/callback",
                on_password_changed=rotated.append,
            )
            self.assertEqual(tok, self.state["issued_token"])
            self.assertEqual(len(rotated), 1)
            self.assertEqual(self.state["pw_change_form"]["password"], [rotated[0]])
            self.assertEqual(self.state["login_origin"], http_url)
            self.assertEqual(self.state["pw_change_origin"], http_url)
            self.assertEqual(self.state["consent_origin"], http_url)
            self.assertIn("magicrunner.usage.apps.data.execute", self.state["authorize_qs"]["scope"][0])
            self.assertIsNone(self.state["token_cookie_header"])
        finally:
            bsa.HttpSession = orig_cls  # type: ignore[assignment]

    def test_run_seed_and_verify_does_not_precreate_dm_run_dir_before_init(self):
        with tempfile.TemporaryDirectory(prefix="bsa-runs-") as tmp:
            state_dir = bsa.ensure_private_dir(Path(tmp) / "state")
            secrets_dir = bsa.ensure_private_dir(state_dir / "secrets")
            orig_run = bsa._run_subprocess
            seen_cmds: list[list[str]] = []
            dm_existed_at_init: list[bool] = []

            def fake_run(cmd, env):
                seen_cmds.append(cmd)
                if len(cmd) > 3 and cmd[3] == "init":
                    dm_dir = state_dir / "runs/device-management"
                    dm_existed_at_init.append(dm_dir.exists())
                    dm_dir.mkdir(parents=True, exist_ok=True)
                    (dm_dir / "config.json").write_text("{}", encoding="utf-8")
                return "{}"

            bsa._run_subprocess = fake_run  # type: ignore[assignment]
            try:
                res = bsa.run_seed_and_verify(
                    action="all",
                    base_url="https://panel.example.com",
                    state_dir=state_dir,
                    secrets_dir=secrets_dir,
                    platform_root=bsa.resolve_platform_root(),
                    services_info={},
                    apps=["device-management"],
                    ca_file=None,
                    trust_leaf=False,
                    cycles=1,
                    anchor_utc=None,
                )
            finally:
                bsa._run_subprocess = orig_run  # type: ignore[assignment]

            self.assertEqual(dm_existed_at_init, [False])
            self.assertEqual([c[3] for c in seen_cmds], ["init", "seed", "backfill", "live-stream", "verify"])
            self.assertIn("device-management", res)


if __name__ == "__main__":
    unittest.main()
