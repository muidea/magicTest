#!/usr/bin/env python3
"""Offline unit tests for load.apm_client and load.run_load using stdlib mock servers."""
from __future__ import annotations

import base64
import http.server
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.parse import parse_qs, urlsplit

from load import apm_client, run_load


class _MockTargetServer:
    def __init__(self):
        self.requests = []
        self.expected_auth = None

        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                outer.requests.append({
                    "method": "GET",
                    "path": self.path,
                    "auth": self.headers.get("Authorization"),
                    "connection": self.headers.get("Connection"),
                })
                if outer.expected_auth and self.headers.get("Authorization") != outer.expected_auth:
                    self.send_response(401)
                    self.end_headers()
                    self.wfile.write(b'{"error":{"code":11,"message":"unauthorized"}}')
                    return
                if "biz_err=1" in self.path:
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(b'{"error":{"code":5,"message":"denied"}}')
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b'{"value":{"ok":true}}')

            def log_message(self, *args):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}/api/v1/probe"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


class _MockPrometheusServer:
    def __init__(self, *, required_basic_auth: str | None = None):
        self.required_basic_auth = required_basic_auth
        self.seen_auth: list[str | None] = []
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                auth = self.headers.get("Authorization")
                outer.seen_auth.append(auth)
                if outer.required_basic_auth and auth != outer.required_basic_auth:
                    self.send_response(401)
                    self.end_headers()
                    return
                parsed = urlsplit(self.path)
                if parsed.path == "/prometheus/-/ready":
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"Prometheus Server is Ready.\n")
                    return
                if parsed.path == "/prometheus/api/v1/targets":
                    payload = {
                        "status": "success",
                        "data": {
                            "activeTargets": [
                                {"labels": {"job": "traefik", "instance": "traefik:8082"}, "health": "up"},
                                {"labels": {"job": "node-exporter", "instance": "node-exporter:9100"}, "health": "up"},
                                {"labels": {"job": "postgres-exporter", "instance": "postgres-exporter:9187"}, "health": "up"},
                                {"labels": {"job": "cadvisor", "instance": "cadvisor:8080"}, "health": "up"},
                                {"labels": {"job": "magicbase", "instance": "magicbase:9090"}, "health": "up"},
                            ]
                        },
                    }
                    self._json(payload)
                    return
                qs = parse_qs(parsed.query)
                promql = qs.get("query", [""])[0]
                if parsed.path == "/prometheus/api/v1/query_range":
                    val = "42.5" if "node_cpu_seconds_total" in promql else "61.0"
                    self._json({
                        "status": "success",
                        "data": {"resultType": "matrix", "result": [{"metric": {}, "values": [[1000, val], [1015, val]]}]},
                    })
                    return
                if parsed.path == "/prometheus/api/v1/query":
                    if "container_cpu_usage_seconds_total" in promql:
                        res = [{"metric": {"name": "magicPanel"}, "value": [1000, "0.25"]}]
                    elif "container_memory_working_set_bytes" in promql:
                        res = [{"metric": {"name": "magicPanel"}, "value": [1000, "128.5"]}]
                    elif "traefik_service_requests_total" in promql:
                        res = [{"metric": {"code": "200"}, "value": [1000, "120"]}]
                    elif "traefik_service_request_duration_seconds_bucket" in promql:
                        res = [{"metric": {}, "value": [1000, "0.012"]}]
                    elif "pg_stat_database_xact_commit" in promql:
                        res = [{"metric": {}, "value": [1000, "80"]}]
                    elif "pg_stat_activity_count" in promql:
                        res = [{"metric": {}, "value": [1000, "3"]}]
                    elif "magicBase_" in promql:
                        res = []  # simulate absent magicbase series -> graceful partial availability
                    else:
                        res = [{"metric": {}, "value": [1000, "1.5"]}]
                    self._json({"status": "success", "data": {"resultType": "vector", "result": res}})
                    return
                self.send_response(404)
                self.end_headers()

            def _json(self, payload):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(payload).encode("utf-8"))

            def log_message(self, *args):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}/prometheus"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


class LoadSuiteTests(unittest.TestCase):
    def test_dry_run_and_secret_file_guards(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            secret = root / "key.txt"
            secret.write_text("SECRET-SHOULD-NOT-APPEAR\n")
            secret.chmod(0o644)
            with self.assertRaisesRegex(ValueError, "0600"):
                run_load.main(["--url", "https://panel.example.com/", "--auth-mode", "apikey", "--secret-file", str(secret), "--output", str(root / "out1")])

            secret.chmod(0o600)
            link = root / "link.txt"
            link.symlink_to(secret)
            with self.assertRaisesRegex(ValueError, "symlink"):
                run_load.main(["--url", "https://panel.example.com/", "--auth-mode", "apikey", "--secret-file", str(link), "--output", str(root / "out2")])

            oversize = root / "big.token"
            oversize.write_text("A" * 17000)
            oversize.chmod(0o600)
            with self.assertRaisesRegex(ValueError, "16384"):
                run_load.main(["--url", "https://panel.example.com/", "--auth-mode", "bearer", "--secret-file", str(oversize), "--output", str(root / "out3")])

            buf = io.StringIO()
            old_out = os.sys.stdout
            os.sys.stdout = buf
            try:
                rc = run_load.main([
                    "--url", "https://panel.example.com/api/v1/web/branding/",
                    "--apm-url", "https://apm.example.com/prometheus/",
                    "--mode", "step", "--concurrency", "2,4", "--dry-run",
                ])
            finally:
                os.sys.stdout = old_out
            self.assertEqual(rc, 0)
            plan = json.loads(buf.getvalue())
            self.assertTrue(plan["dryRun"])
            self.assertEqual(plan["spec"]["concurrency"], [2, 4])

    def test_step_load_with_apm_correlation_and_zero_secret_leak(self):
        target = _MockTargetServer()
        prom = _MockPrometheusServer(required_basic_auth="Basic " + base64.b64encode(b"apm:pass123").decode("ascii"))
        self.addCleanup(target.close)
        self.addCleanup(prom.close)

        secret_value = "sk_test_0123456789abcdef_PRIVATE"
        target.expected_auth = f"ApiKey {secret_value}"

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            secret = root / "api.key"
            secret.write_text(secret_value + "\n")
            secret.chmod(0o600)
            apm_auth = root / "apm.auth"
            apm_auth.write_text("apm:pass123\n")
            apm_auth.chmod(0o600)
            out_dir = root / "report"

            rc = run_load.main([
                "--url", target.url,
                "--auth-mode", "apikey",
                "--secret-file", str(secret),
                "--mode", "step",
                "--concurrency", "1,2",
                "--duration", "0.25",
                "--connection-mode", "keep-alive",
                "--apm-url", prom.url,
                "--apm-auth-file", str(apm_auth),
                "--apm-settle-seconds", "0",
                "--require-apm",
                "--output", str(out_dir),
            ])
            self.assertEqual(rc, 0)
            report_text = (out_dir / "report.json").read_text(encoding="utf-8")
            summary_text = (out_dir / "summary.md").read_text(encoding="utf-8")
            self.assertNotIn(secret_value, report_text)
            self.assertNotIn("pass123", report_text)
            self.assertNotIn(secret_value, summary_text)

            report = json.loads(report_text)
            self.assertEqual(len(report["stages"]), 2)
            self.assertTrue(report["apmReady"]["ready"])
            self.assertEqual(report["apmReady"]["jobs"]["traefik"]["up"], 1)
            for stage in report["stages"]:
                self.assertGreater(stage["successfulRequests"], 0)
                self.assertEqual(stage["failedRequests"], 0)
                self.assertGreater(stage["qps"], 0)
                self.assertIsNotNone(stage["latencyMs"]["p95"])
                self.assertTrue(stage["apm"]["host"]["available"])
                self.assertTrue(stage["apm"]["traefik"]["available"])
                self.assertEqual(stage["apm"]["traefik"]["p95LatencyMs"], 12.0)
                self.assertFalse(stage["apm"]["magicbase"]["available"])

    def test_aging_cold_tls_mode_and_sim_state_resolution(self):
        target = _MockTargetServer()
        self.addCleanup(target.close)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            state_dir = root / "sim-state"
            (state_dir / "secrets").mkdir(parents=True)
            (state_dir / "runs/device-management").mkdir(parents=True)
            key_file = state_dir / "secrets/device-management.api-key"
            key_file.write_text("sk_dm_12345\n")
            key_file.chmod(0o600)
            target.expected_auth = "ApiKey sk_dm_12345"
            (state_dir / "bootstrap-summary.json").write_text(json.dumps({
                "baseUrl": "https://panel.example.com",
                "targetAddress": "192.168.13.47",
                "apps": ["device-management", "chess-room-booking"],
                "installations": {
                    "chess-room-booking": {
                        "installationId": 42,
                        "deploymentId": "dep6b79",
                    }
                },
                "portal": {
                    "device-management": {
                        "serviceKey": "device_management_service",
                        "apiKeyFile": str(key_file),
                    },
                    "chess-room-booking": {
                        "serviceKey": "chess_room_booking_simulation",
                        "apiKeyFile": str(state_dir / "secrets/chess-room-booking.api-key"),
                    },
                },
                "crbOperator": {
                    "actionTokenFile": str(state_dir / "secrets/crb-operator.token"),
                },
                "simulation": {
                    "device-management": {
                        "serviceUrl": target.url,
                    },
                    "chess-room-booking": {
                        "serviceUrl": "https://panel.example.com/api/v1/gateway/services/chess_room_booking_simulation",
                    },
                },
            }))
            (state_dir / "runs/device-management/config.json").write_text(json.dumps({
                "serviceUrl": target.url,
                "apiKeyFile": str(key_file),
            }))

            out_dir = root / "aging-report"
            rc = run_load.main([
                "--from-sim-state", str(state_dir),
                "--sim-app", "device-management",
                "--sim-scenario", "gateway-read",
                "--mode", "aging",
                "--concurrency", "2",
                "--duration", "0.3",
                "--window-seconds", "0.1",
                "--connection-mode", "cold-tls",
                "--output", str(out_dir),
            ])
            self.assertEqual(rc, 0)
            report = json.loads((out_dir / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["stages"][0]["connectionMode"], "cold-tls")
            self.assertGreaterEqual(len(report["stages"][0].get("agingTimeline", [])), 1)
            self.assertTrue(all(r["connection"] == "close" for r in target.requests))

            resolved_dm = run_load._resolve_sim_target(
                str(state_dir), "device-management", "gateway-read",
            )
            self.assertEqual(resolved_dm["targetAddress"], "192.168.13.47")
            self.assertEqual(resolved_dm["secretFile"], str(key_file))
            self.assertEqual(
                run_load._append_gateway_query(
                    "https://panel.example.com/api/v1/gateway/services/device_management_service",
                    "device_query",
                ),
                "https://panel.example.com/api/v1/gateway/services/device_management_service/device_query?_pageNum=1&_pageSize=20",
            )

            resolved_crb_gw = run_load._resolve_sim_target(str(state_dir), "chess-room-booking", "gateway-read")
            self.assertEqual(
                resolved_crb_gw["url"],
                "https://panel.example.com/api/v1/gateway/services/chess_room_booking_simulation/room_query?_pageNum=1&_pageSize=20",
            )
            self.assertEqual(resolved_crb_gw["secretFile"], str(state_dir / "secrets/chess-room-booking.api-key"))
            self.assertEqual(resolved_crb_gw["targetAddress"], "192.168.13.47")

            resolved = run_load._resolve_sim_target(str(state_dir), "chess-room-booking", "apps-read")
            self.assertEqual(
                resolved["url"],
                "https://panel.example.com/api/v1/apps/application/runtimes/chess-room-booking?deploymentId=dep6b79",
            )
            self.assertEqual(resolved["authMode"], "bearer")
            self.assertEqual(resolved["secretFile"], str(state_dir / "secrets/crb-operator.token"))
            self.assertEqual(resolved["targetAddress"], "192.168.13.47")


if __name__ == "__main__":
    unittest.main()
