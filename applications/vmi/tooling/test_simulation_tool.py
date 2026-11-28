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
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
import simulation_tool


MOCK_GATEWAY_IDENTITY = {
    "namespace": "panel",
    "deploymentId": "00c3bc804c879d1bc74601703f001cd2",
    "installationId": 1042779181799680,
    "runtimeApplicationUuid": "ebd1c00f04e76565e68815d35cd78e2a",
    "generation": 1,
    "executionEpoch": 1,
    "artifactDigest": "sha256:" + "a" * 64,
}
MOCK_ACTION_IDENTITY = {
    **MOCK_GATEWAY_IDENTITY,
    "installationId": "1042779181799680",
}


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
        # /api/v1/gateway/services/<svc_key>/<entity>_query
        if len(parts) == 6 and parts[:4] == ["api", "v1", "gateway", "services"] and parts[5].endswith("_query"):
            svc_key, entity = parts[4], parts[5][: -len("_query")]
            state = self.__class__.state
            if self.headers.get("Authorization") != f"ApiKey {state['keys'].get(svc_key)}":
                self._send_json(401, {"error": {"message": "API key is inactive or invalid"}})
                return
            state["calls"].append(("GET", svc_key, entity))
            allowed = state["allowed_entities"].get(svc_key, set())
            if entity not in allowed:
                self._send_json(400, {"error": {"code": 4, "message": "request method or path is not declared in published service contract"}})
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

        # /api/v1/gateway/services/<svc_key>/<entity>_create
        if len(parts) == 6 and parts[:4] == ["api", "v1", "gateway", "services"] and parts[5].endswith("_create"):
            svc_key, entity = parts[4], parts[5][: -len("_create")]
            if self.headers.get("Authorization") != f"ApiKey {state['keys'].get(svc_key)}":
                self._send_json(401, {"error": {"message": "API key is inactive or invalid"}})
                return
            if entity not in state["allowed_entities"].get(svc_key, set()):
                self._send_json(404, {"error": {"message": f"entity {entity} not bound to {svc_key}"}})
                return
            for audit_field in ("createdAt", "updatedAt", "updatedBy"):
                assert body.get(audit_field), f"{entity}_create missing required audit field {audit_field}"
            for fname, fval in body.items():
                if fname.endswith("Id"):
                    assert isinstance(fval, dict) and isinstance(fval.get("id"), int), f"{fname} must be {{id: int}}: {fval}"
                elif fname.endswith("Ids"):
                    assert isinstance(fval, list) and all(isinstance(x, dict) and isinstance(x.get("id"), int) for x in fval)
            if entity == "creditReward":
                ord_id = body["orderId"]["id"]
                ord_row = next((r for r in state["records"].get("order", []) if r["id"] == ord_id), None)
                if not ord_row or ord_row.get("status") not in ("paid", "fulfilling", "completed"):
                    self._send_json(409, {"error": {"message": "creditReward orderId must be paid/fulfilling/completed"}})
                    return

            state["calls"].append(("POST", svc_key, entity))
            new_id = state["next_id"]
            state["next_id"] += 1
            record = {"id": new_id, "version": 1, **body}
            if entity in ("stockin", "stockout"):
                record["status"] = "draft"
            elif entity == "order":
                record["status"] = "pending_payment"
            state["records"].setdefault(entity, []).append(record)
            if entity == "goodsInfo" and float(body.get("quantity") or 0) >= 100:
                state["records"].setdefault("inventoryAlert", []).append({"id": 900 + new_id, "version": 1, "source": "goodsInfo"})
            if entity == "goodsItem" and float(body.get("subtotal") or 0) >= 1000:
                state["records"].setdefault("inventoryAlert", []).append({"id": 900 + new_id, "version": 1, "source": "goodsItem"})
            self._send_json(
                200,
                {
                    "value": record,
                    "receipt": {
                        "apiVersion": "magic.entity-value-write/v1",
                        "identity": MOCK_GATEWAY_IDENTITY,
                        "id": new_id,
                        "version": 1,
                    },
                },
            )
            return

        if parsed.path == "/api/v1/apps/entity/action/execute/":
            if self.headers.get("Authorization") != f"Bearer {state['action_token']}":
                self._send_json(401, {"error": {"message": "invalid bearer token"}})
                return
            qs = parse_qs(parsed.query)
            if qs.get("application") != ["vmi"] or qs.get("deploymentId") != [MOCK_ACTION_IDENTITY["deploymentId"]]:
                self._send_json(400, {"error": {"message": f"missing/invalid scope query: {qs}"}})
                return
            if body.get("identity") != MOCK_ACTION_IDENTITY:
                self._send_json(200, {"error": {"code": 4, "message": "业务动作请求或精确身份无效"}})
                return
            if state.get("force_action_error"):
                self._send_json(200, {"error": {"code": 4, "message": "simulated HTTP 200 action failure"}})
                return
            ent_name = str(body.get("entity") or "").rsplit("/", 1)[-1]
            act_name = body.get("action")
            rec_id = int(body.get("id") or 0)
            new_status = ""
            for rec in state["records"].get(ent_name, []):
                if rec["id"] == rec_id:
                    rec["version"] += 1
                    if ent_name == "stockin":
                        new_status = "submitted" if act_name == "submit" else "completed"
                    elif ent_name == "order":
                        new_status = {"pay": "paid", "start-fulfill": "fulfilling", "complete": "completed"}[act_name]
                    rec["status"] = new_status
            state["action_calls"].append((body.get("entity"), act_name, body.get("id")))
            expected = int(body.get("expectedVersion") or 1)
            self._send_json(
                200,
                {
                    "value": {
                        "apiVersion": "magic.entity-action/v1",
                        "operationId": body.get("operationId"),
                        "identity": MOCK_ACTION_IDENTITY,
                        "entity": body.get("entity"),
                        "action": act_name,
                        "id": str(body.get("id")),
                        "version": str(expected + 1),
                        "state": new_status,
                    }
                },
            )
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
        for step in (*first["creates"], *first["postActionCreates"]):
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
                self.assertEqual(len(post_calls), 27)
                self.assertEqual({c[1] for c in post_calls}, {s["key"] for s in simulation_tool.VMI_DOMAIN_SERVICES})
                self.assertEqual(len(state["action_calls"]), 6)

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

    def test_action_http_200_error_envelope_fails_without_recording_journal(self):
        state = {
            "keys": {svc["key"]: f"secret-{svc['domain']}" for svc in simulation_tool.VMI_DOMAIN_SERVICES},
            "allowed_entities": {svc["key"]: set(svc["entities"]) for svc in simulation_tool.VMI_DOMAIN_SERVICES},
            "action_token": "tok-vmi-operator",
            "force_action_error": True,
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
            with tempfile.TemporaryDirectory(prefix="vmi-sim-err-") as tmp:
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

                simulation_tool.main(["--anchor-utc", "2026-11-01T00:00:00Z", "--run-id", "ERR200", "--output", str(plan_path), "plan"])
                with self.assertRaisesRegex(simulation_tool.Failure, "API error POST .*simulated HTTP 200 action failure"):
                    simulation_tool.main([
                        "--plan", str(plan_path),
                        "--service-map", str(smap_path),
                        "--action-url", f"{base}/api/v1/apps/entity/action/execute/",
                        "--action-token-file", str(tok_path),
                        "--state-dir", str(state_dir),
                        "run",
                    ])
                journal = json.loads((state_dir / "journal.json").read_text(encoding="utf-8"))
                self.assertEqual(journal["actions"], [])
                self.assertEqual(journal["versions"]["stockin:si1"], 1)
                self.assertEqual(journal["versions"]["order:o1"], 1)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
