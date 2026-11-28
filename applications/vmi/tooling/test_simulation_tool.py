"""Offline unit tests for VMI 6-domain simulation plan, routing, isolation & verification."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import threading
import unittest
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import simulation_tool


class _MockDomainGatewayHandler(BaseHTTPRequestHandler):
    state: dict = {}

    def log_message(self, format, *args):  # noqa: A002
        return

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def _send_json(self, code: int, doc: dict) -> None:
        raw = json.dumps(doc, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):  # noqa: N802
        parsed = urlsplit(self.path)
        parts = [p for p in parsed.path.split("/") if p]
        # /api/v1/gateway/services/<svc_key>/vmi/<entity>/
        if len(parts) == 7 and parts[:4] == ["api", "v1", "gateway", "services"] and parts[5] == "vmi":
            svc_key, entity = parts[4], parts[6]
            api_key = self.headers.get("X-API-Key")
            state = self.__class__.state
            if api_key != state["keys"].get(svc_key):
                self._send_json(401, {"error": {"message": "invalid api key"}})
                return
            state["calls"].append(("GET", svc_key, entity))
            allowed = state["allowed_entities"].get(svc_key, set())
            if entity not in allowed:
                self._send_json(404, {"error": {"message": f"entity {entity} not bound to {svc_key}"}})
                return
            rows = state["records"].get(entity, [])
            self._send_json(200, {"values": rows, "pagination": {"total": len(rows)}})
            return
        self._send_json(404, {"error": {"message": "not found"}})

    def do_POST(self):  # noqa: N802
        parsed = urlsplit(self.path)
        parts = [p for p in parsed.path.split("/") if p]
        state = self.__class__.state
        body = self._read_json()

        if len(parts) == 7 and parts[:4] == ["api", "v1", "gateway", "services"] and parts[5] == "vmi":
            svc_key, entity = parts[4], parts[6]
            if self.headers.get("X-API-Key") != state["keys"].get(svc_key):
                self._send_json(401, {"error": {"message": "invalid api key"}})
                return
            if entity not in state["allowed_entities"].get(svc_key, set()):
                self._send_json(404, {"error": {"message": f"entity {entity} not bound to {svc_key}"}})
                return
            state["calls"].append(("POST", svc_key, entity))
            new_id = state["next_id"]
            state["next_id"] += 1
            record = {"id": new_id, "version": 1, **body}
            state["records"].setdefault(entity, []).append(record)
            if entity == "goodsInfo" and float(body.get("quantity") or 0) >= 100:
                state["records"].setdefault("inventoryAlert", []).append({"id": 900 + new_id, "version": 1, "source": "goodsInfo"})
            if entity == "goodsItem" and float(body.get("subtotal") or 0) >= 1000:
                state["records"].setdefault("inventoryAlert", []).append({"id": 900 + new_id, "version": 1, "source": "goodsItem"})
            self._send_json(200, {"value": record})
            return

        if parsed.path == "/api/v1/apps/entity/action/execute/":
            if self.headers.get("Authorization") != f"Bearer {state['action_token']}":
                self._send_json(401, {"error": {"message": "invalid bearer token"}})
                return
            state["action_calls"].append((body.get("entity"), body.get("action"), body.get("id")))
            expected = int(body.get("expectedVersion") or 1)
            self._send_json(200, {"value": {"id": body.get("id"), "version": expected + 1}})
            return

        self._send_json(404, {"error": {"message": "not found"}})


class VmiSimulationToolTests(unittest.TestCase):
    def test_domain_service_partition_matches_model_entities(self):
        simulation_tool.validate_domain_services()
        self.assertEqual(len(simulation_tool.VMI_DOMAIN_SERVICES), 6)
        self.assertEqual(len(simulation_tool.VMI_ENTITY_TO_SERVICE_KEY), 18)

    def test_plan_determinism_and_reference_order(self):
        first = simulation_tool.simulation_plan("2026-11-01T00:00:00Z", "FIXED1")
        second = simulation_tool.simulation_plan("2026-11-01T08:00:00+08:00", "FIXED1")
        self.assertEqual(first, second)
        self.assertEqual(len(first["domainServices"]), 6)

        seen_keys: set[str] = set()
        for step in first["creates"]:
            self.assertEqual(step["serviceKey"], simulation_tool.service_key_for_entity(step["entity"]))

            def check_refs(val):
                if isinstance(val, dict) and "$ref" in val:
                    self.assertIn(val["$ref"], seen_keys, f"reference {val['$ref']} used before creation in {step['key']}")
                elif isinstance(val, list):
                    for item in val:
                        check_refs(item)

            for field_val in step["values"].values():
                check_refs(field_val)
            seen_keys.add(step["key"])

        store_step = next(s for s in first["creates"] if s["key"] == "store:s1")
        self.assertEqual(len(store_step["values"]["shelfIds"]), 2)
        self.assertEqual(first["expectedAlertCount"], 2)

    def test_multi_service_inspect_run_verify_and_isolation_with_mock_gateway(self):
        state = {
            "keys": {svc["key"]: f"secret-{svc['domain']}" for svc in simulation_tool.VMI_DOMAIN_SERVICES},
            "allowed_entities": {svc["key"]: set(svc["entities"]) for svc in simulation_tool.VMI_DOMAIN_SERVICES},
            "action_token": "tok-vmi-operator",
            "records": {},
            "calls": [],
            "action_calls": [],
            "next_id": 100,
        }
        _MockDomainGatewayHandler.state = state
        server = HTTPServer(("127.0.0.1", 0), _MockDomainGatewayHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"

        try:
            with tempfile.TemporaryDirectory(prefix="vmi-sim-test-") as tmp:
                tmp_path = Path(tmp)
                sec_dir = tmp_path / "secrets"
                sec_dir.mkdir(mode=0o700)
                services_cfg = {}
                for svc in simulation_tool.VMI_DOMAIN_SERVICES:
                    svc_key = svc["key"]
                    kpath = sec_dir / f"{svc_key}.key"
                    kpath.write_text(state["keys"][svc_key] + "\n", encoding="utf-8")
                    os.chmod(kpath, 0o600)
                    services_cfg[svc_key] = {
                        "serviceUrl": f"{base}/api/v1/gateway/services/{svc_key}",
                        "apiKeyFile": str(kpath),
                    }

                tok_path = sec_dir / "operator.token"
                tok_path.write_text(state["action_token"] + "\n", encoding="utf-8")
                os.chmod(tok_path, 0o600)

                smap_path = tmp_path / "service-map.json"
                smap_path.write_text(json.dumps({"services": services_cfg}), encoding="utf-8")
                plan_path = tmp_path / "plan.json"
                state_dir = tmp_path / "state"

                self.assertEqual(
                    simulation_tool.main(["--anchor-utc", "2026-11-01T00:00:00Z", "--run-id", "TEST6DOM", "--output", str(plan_path), "plan"]),
                    0,
                )

                # On-demand inspect restricted to warehouse domain only.
                self.assertEqual(
                    simulation_tool.main(["--service-map", str(smap_path), "--domains", "warehouse", "inspect"]),
                    0,
                )
                self.assertEqual(state["calls"], [("GET", "vmi_warehouse_service", "warehouse"), ("GET", "vmi_warehouse_service", "shelf")])

                state["calls"].clear()
                self.assertEqual(
                    simulation_tool.main([
                        "--plan", str(plan_path),
                        "--service-map", str(smap_path),
                        "--action-url", f"{base}/api/v1/apps/entity/action/execute/",
                        "--action-token-file", str(tok_path),
                        "--state-dir", str(state_dir),
                        "run",
                    ]),
                    0,
                )
                post_calls = [c for c in state["calls"] if c[0] == "POST"]
                self.assertEqual(len(post_calls), 20)
                self.assertEqual({c[1] for c in post_calls}, {s["key"] for s in simulation_tool.VMI_DOMAIN_SERVICES})
                self.assertEqual(len(state["action_calls"]), 5)

                # Full verify passes all 6 domain services + isolation negative probe (HTTP 404).
                self.assertEqual(
                    simulation_tool.main([
                        "--plan", str(plan_path),
                        "--service-map", str(smap_path),
                        "--wait-seconds", "5",
                        "verify",
                    ]),
                    0,
                )
                self.assertIn(("GET", "vmi_warehouse_service", "order"), state["calls"])

                # If warehouse accidentally leaks order (returns 200), verify must fail isolation check.
                state["allowed_entities"]["vmi_warehouse_service"].add("order")
                with self.assertRaisesRegex(simulation_tool.Failure, "domain isolation failed"):
                    simulation_tool.main([
                        "--plan", str(plan_path),
                        "--service-map", str(smap_path),
                        "--domains", "warehouse",
                        "verify",
                    ])
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
