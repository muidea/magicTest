#!/usr/bin/env python3
"""Cross-server HTTPS load generator with platform Prometheus APM correlation."""
from __future__ import annotations

import argparse
from collections import Counter
import concurrent.futures
from datetime import datetime, timezone
import http.client
import json
import math
from pathlib import Path
import ssl
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from load.apm_client import PrometheusClient, build_ssl_context, collect_window_metrics, read_private_secret


class _SniHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, connect_host: str, sni_host: str, port: int, *, context: ssl.SSLContext, timeout: float):
        super().__init__(connect_host, port=port, context=context, timeout=timeout)
        self._sni_host = sni_host

    def connect(self) -> None:
        sock = self._create_connection((self.host, self.port), self.timeout, self.source_address)
        if self._tunnel_host:
            self.sock = sock
            self._tunnel()
        self.sock = self._context.wrap_socket(sock, server_hostname=self._sni_host)


def _percentile(sorted_vals: List[float], pct: float) -> Optional[float]:
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return round(sorted_vals[0], 3)
    idx = (len(sorted_vals) - 1) * (pct / 100.0)
    lo = math.floor(idx)
    hi = math.ceil(idx)
    if lo == hi:
        return round(sorted_vals[lo], 3)
    frac = idx - lo
    return round(sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac, 3)


def _latency_summary(latencies_ms: List[float]) -> Dict[str, Optional[float]]:
    if not latencies_ms:
        return {"min": None, "avg": None, "p50": None, "p90": None, "p95": None, "p99": None, "max": None}
    s = sorted(latencies_ms)
    return {
        "min": round(s[0], 3),
        "avg": round(sum(s) / len(s), 3),
        "p50": _percentile(s, 50),
        "p90": _percentile(s, 90),
        "p95": _percentile(s, 95),
        "p99": _percentile(s, 99),
        "max": round(s[-1], 3),
    }


def _append_gateway_query(url: str, op_suffix: str) -> str:
    parsed = urlsplit(url)
    marker = "/api/v1/gateway/services/"
    idx = parsed.path.find(marker)
    if idx < 0:
        return url
    tail = parsed.path[idx + len(marker):].strip("/")
    if not tail or "/" in tail:
        return url
    base = url.rstrip("/")
    return f"{base}/{op_suffix}?_pageNum=1&_pageSize=20"


def _resolve_sim_target(state_dir_raw: str, sim_app: str, sim_scenario: str) -> Dict[str, Any]:
    state_dir = Path(state_dir_raw).expanduser().resolve()
    summary_file = state_dir / "bootstrap-summary.json"
    summary = json.loads(summary_file.read_text(encoding="utf-8")) if summary_file.is_file() else {}
    base_url = str(summary.get("baseUrl") or "").rstrip("/")
    target_address = str(summary.get("targetAddress") or "").strip() or None
    simulation = summary.get("simulation") or {}
    portal = summary.get("portal") or {}
    installations = summary.get("installations") or {}
    crb_op = summary.get("crbOperator") or {}

    secrets_dir = state_dir / "secrets"
    if sim_app == "device-management":
        if sim_scenario != "gateway-read":
            raise ValueError("device-management simulation currently supports sim-scenario=gateway-read")
        cfg_path = state_dir / "runs/device-management/config.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.is_file() else {}
        dm_sim = simulation.get("device-management") or {}
        dm_portal = portal.get("device-management") or {}
        svc_key = str(dm_portal.get("serviceKey") or "device_management_service")
        url = str(dm_sim.get("serviceUrl") or cfg.get("serviceUrl") or "").strip()
        if not url and base_url:
            url = f"{base_url}/api/v1/gateway/services/{svc_key}"
        if not url:
            raise ValueError(f"Unable to determine device-management gateway URL from {state_dir}")
        api_key_file = str(dm_portal.get("apiKeyFile") or cfg.get("apiKeyFile") or (secrets_dir / "device-management.api-key"))
        return {
            "url": _append_gateway_query(url, "device_query"),
            "authMode": "apikey",
            "secretFile": api_key_file,
            "method": "GET",
            "targetAddress": target_address,
        }

    if sim_app == "chess-room-booking":
        crb_sim = simulation.get("chess-room-booking") or {}
        crb_portal = portal.get("chess-room-booking") or {}
        crb_inst = installations.get("chess-room-booking") or {}
        if sim_scenario == "gateway-read":
            svc_key = str(crb_portal.get("serviceKey") or "chess_room_booking_simulation")
            url = str(crb_sim.get("serviceUrl") or "").strip()
            if not url and base_url:
                url = f"{base_url}/api/v1/gateway/services/{svc_key}"
            if not url:
                raise ValueError(f"Unable to determine chess-room-booking gateway URL from {state_dir}")
            api_key_file = str(crb_portal.get("apiKeyFile") or (secrets_dir / "chess-room-booking.api-key"))
            return {
                "url": _append_gateway_query(url, "room_query"),
                "authMode": "apikey",
                "secretFile": api_key_file,
                "method": "GET",
                "targetAddress": target_address,
            }
        if sim_scenario == "apps-read":
            dep_id = crb_inst.get("deploymentId")
            if not base_url or not dep_id:
                raise ValueError(f"Unable to determine chess-room-booking deploymentId/baseUrl from {state_dir}")
            url = f"{base_url}/api/v1/apps/application/runtimes/chess-room-booking?deploymentId={dep_id}"
            token_file = str(crb_op.get("actionTokenFile") or (secrets_dir / "crb-operator.token"))
            return {
                "url": url,
                "authMode": "bearer",
                "secretFile": token_file,
                "method": "GET",
                "targetAddress": target_address,
            }
        raise ValueError(f"Unsupported sim-scenario for chess-room-booking: {sim_scenario}")

    raise ValueError(f"Unsupported sim-app: {sim_app}")


def _build_spec(args: argparse.Namespace) -> Dict[str, Any]:
    cfg = json.loads(Path(args.config).expanduser().read_text(encoding="utf-8")) if args.config else {}
    sim_state = args.from_sim_state or cfg.get("fromSimState")
    sim_resolved: Dict[str, Any] = {}
    if sim_state:
        sim_app = args.sim_app or cfg.get("simApp") or "device-management"
        sim_scenario = args.sim_scenario or cfg.get("simScenario") or "gateway-read"
        sim_resolved = _resolve_sim_target(sim_state, sim_app, sim_scenario)

    url = args.url or cfg.get("url") or sim_resolved.get("url")
    if not url:
        raise ValueError("Target --url (or --from-sim-state / config.url) is required")
    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Target URL must be an explicit http/https URL without userinfo")

    method = (args.method or cfg.get("method") or sim_resolved.get("method") or "GET").upper()
    if method not in ("GET", "POST", "PUT", "DELETE"):
        raise ValueError(f"Unsupported HTTP method: {method}")

    auth_mode = args.auth_mode or cfg.get("authMode") or sim_resolved.get("authMode") or "public"
    if auth_mode not in ("public", "apikey", "bearer"):
        raise ValueError(f"Unsupported authMode: {auth_mode}")

    secret_file = args.secret_file or cfg.get("secretFile") or sim_resolved.get("secretFile")
    if auth_mode != "public" and not secret_file:
        raise ValueError(f"authMode={auth_mode} requires --secret-file")

    mode = args.mode or cfg.get("mode") or "steady"
    if mode not in ("steady", "step", "aging"):
        raise ValueError(f"Unsupported load mode: {mode}")

    conc_raw = args.concurrency or cfg.get("concurrency") or ("2,4" if mode == "step" else "4")
    if isinstance(conc_raw, list):
        concurrency = [int(x) for x in conc_raw]
    else:
        concurrency = [int(x.strip()) for x in str(conc_raw).split(",") if x.strip()]
    if not concurrency or any(c <= 0 or c > 512 for c in concurrency):
        raise ValueError("concurrency values must be integers in 1..512")

    duration = float(args.duration if args.duration is not None else cfg.get("duration", 10.0))
    if duration <= 0:
        raise ValueError("duration must be > 0 seconds")

    window_seconds = float(args.window_seconds if args.window_seconds is not None else cfg.get("windowSeconds", 60.0))
    if window_seconds <= 0:
        raise ValueError("windowSeconds must be > 0")

    connection_mode = args.connection_mode or cfg.get("connectionMode") or "keep-alive"
    if connection_mode not in ("keep-alive", "cold-tls"):
        raise ValueError("connectionMode must be keep-alive or cold-tls")

    timeout = float(args.timeout if args.timeout is not None else cfg.get("timeout", 15.0))
    if timeout <= 0:
        raise ValueError("timeout must be > 0")

    apm_url = (args.apm_url or cfg.get("apmUrl") or "").strip() or None
    apm_auth_file = args.apm_auth_file or cfg.get("apmAuthFile")
    apm_idle_seconds = int(args.apm_idle_seconds if args.apm_idle_seconds is not None else cfg.get("apmIdleSeconds", 0))
    apm_settle_seconds = int(args.apm_settle_seconds if args.apm_settle_seconds is not None else cfg.get("apmSettleSeconds", 15))
    require_apm = bool(args.require_apm or cfg.get("requireApm", False))
    if require_apm and not apm_url:
        raise ValueError("--require-apm requires --apm-url")

    body_text = None
    body_file = args.body_file or cfg.get("bodyFile")
    if body_file:
        body_text = Path(body_file).expanduser().read_text(encoding="utf-8")
    elif cfg.get("bodyJson") is not None:
        body_text = json.dumps(cfg["bodyJson"], ensure_ascii=False)

    return {
        "url": url,
        "method": method,
        "authMode": auth_mode,
        "secretFile": str(Path(secret_file).expanduser()) if secret_file else None,
        "targetAddress": (args.target_address or cfg.get("targetAddress") or sim_resolved.get("targetAddress") or "").strip() or None,
        "caFile": str(Path(args.ca_file or cfg.get("caFile")).expanduser()) if (args.ca_file or cfg.get("caFile")) else None,
        "trustLeaf": bool(args.trust_leaf or cfg.get("trustLeaf", False)),
        "insecure": bool(args.insecure or cfg.get("insecure", False)),
        "mode": mode,
        "concurrency": concurrency,
        "durationSeconds": duration,
        "windowSeconds": window_seconds,
        "connectionMode": connection_mode,
        "timeoutSeconds": timeout,
        "bodyText": body_text,
        "apmUrl": apm_url,
        "apmAuthFile": str(Path(apm_auth_file).expanduser()) if apm_auth_file else None,
        "apmIdleSeconds": apm_idle_seconds,
        "apmSettleSeconds": apm_settle_seconds,
        "requireApm": require_apm,
    }


def _load_auth_header(spec: Dict[str, Any]) -> Optional[str]:
    mode = spec["authMode"]
    if mode == "public":
        return None
    max_bytes = 16384 if mode == "bearer" else 4096
    secret = read_private_secret(spec["secretFile"], max_bytes=max_bytes, label=mode)
    if mode == "apikey":
        return f"ApiKey {secret}"
    return f"Bearer {secret}"


def _open_connection(spec: Dict[str, Any], parsed, ssl_ctx: Optional[ssl.SSLContext]) -> http.client.HTTPConnection:
    connect_host = spec["targetAddress"] or parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if parsed.scheme == "https":
        assert ssl_ctx is not None
        return _SniHTTPSConnection(connect_host, parsed.hostname, port, context=ssl_ctx, timeout=spec["timeoutSeconds"])
    return http.client.HTTPConnection(connect_host, port=port, timeout=spec["timeoutSeconds"])


def _run_stage(
    spec: Dict[str, Any],
    *,
    workers: int,
    duration_seconds: float,
    auth_header: Optional[str],
    ssl_ctx: Optional[ssl.SSLContext],
    track_windows: bool = False,
) -> Dict[str, Any]:
    parsed = urlsplit(spec["url"])
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    headers: Dict[str, str] = {"Host": parsed.netloc, "Accept": "application/json"}
    if auth_header:
        headers["Authorization"] = auth_header
    body_bytes: Optional[bytes] = None
    if spec.get("bodyText") is not None:
        body_bytes = spec["bodyText"].encode("utf-8")
        headers["Content-Type"] = "application/json"
    if spec["connectionMode"] == "cold-tls":
        headers["Connection"] = "close"

    stop_at = time.monotonic() + duration_seconds
    lock = threading.Lock()
    latencies: List[float] = []
    status_counts: Counter[str] = Counter()
    biz_errors: Counter[str] = Counter()
    transport_errors: Counter[str] = Counter()
    slice_samples: List[Tuple[float, float, bool]] = []
    first_start: Optional[float] = None
    last_end: Optional[float] = None
    start_wall = time.time()

    def worker_fn() -> None:
        nonlocal first_start, last_end
        conn: Optional[http.client.HTTPConnection] = None
        local_lat: List[float] = []
        local_statuses: Counter[str] = Counter()
        local_biz: Counter[str] = Counter()
        local_tx: Counter[str] = Counter()
        local_slices: List[Tuple[float, float, bool]] = []
        w_first: Optional[float] = None
        w_last: Optional[float] = None
        try:
            while True:
                now_m = time.monotonic()
                if now_m >= stop_at:
                    break
                if w_first is None:
                    w_first = now_m
                ok = False
                req_start = now_m
                try:
                    if conn is None or spec["connectionMode"] == "cold-tls":
                        if conn is not None:
                            conn.close()
                        conn = _open_connection(spec, parsed, ssl_ctx)
                    conn.request(spec["method"], path, body=body_bytes, headers=headers)
                    resp = conn.getresponse()
                    raw = resp.read(2 * 1024 * 1024)
                    req_end = time.monotonic()
                    w_last = req_end
                    elapsed_ms = (req_end - req_start) * 1000.0
                    local_lat.append(elapsed_ms)
                    local_statuses[str(resp.status)] += 1
                    biz_code = None
                    if resp.status == 200:
                        try:
                            payload = json.loads(raw.decode("utf-8"))
                            if isinstance(payload, dict) and payload.get("error"):
                                err = payload["error"]
                                biz_code = str(err.get("code", "unknown") if isinstance(err, dict) else err)
                                local_biz[biz_code] += 1
                            else:
                                ok = True
                        except Exception:
                            ok = True
                    if spec["connectionMode"] == "cold-tls":
                        conn.close()
                        conn = None
                except Exception as exc:
                    req_end = time.monotonic()
                    w_last = req_end
                    local_tx[type(exc).__name__] += 1
                    if conn is not None:
                        try:
                            conn.close()
                        except Exception:
                            pass
                        conn = None
                if track_windows:
                    local_slices.append((req_start, (req_end - req_start) * 1000.0, ok))
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
        with lock:
            latencies.extend(local_lat)
            status_counts.update(local_statuses)
            biz_errors.update(local_biz)
            transport_errors.update(local_tx)
            if track_windows:
                slice_samples.extend(local_slices)
            if w_first is not None and (first_start is None or w_first < first_start):
                first_start = w_first
            if w_last is not None and (last_end is None or w_last > last_end):
                last_end = w_last

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(worker_fn) for _ in range(workers)]
        for fut in futures:
            fut.result()

    end_wall = time.time()
    biz_window = max(0.001, (last_end - first_start) if (first_start is not None and last_end is not None) else duration_seconds)
    total_ok = sum(int(v) for k, v in status_counts.items() if k == "200") - sum(biz_errors.values())
    total_ok = max(0, total_ok)
    total_requests = sum(status_counts.values()) + sum(transport_errors.values())
    total_failed = total_requests - total_ok

    stage_result: Dict[str, Any] = {
        "concurrency": workers,
        "connectionMode": spec["connectionMode"],
        "startedAt": datetime.fromtimestamp(start_wall, tz=timezone.utc).isoformat(),
        "endedAt": datetime.fromtimestamp(end_wall, tz=timezone.utc).isoformat(),
        "startTimestamp": round(start_wall, 3),
        "endTimestamp": round(end_wall, 3),
        "businessWindowSeconds": round(biz_window, 4),
        "totalRequests": total_requests,
        "successfulRequests": total_ok,
        "failedRequests": total_failed,
        "qps": round(total_ok / biz_window, 3),
        "latencyMs": _latency_summary(latencies),
        "httpStatusCounts": dict(status_counts),
        "businessErrorCodes": dict(biz_errors),
        "transportErrors": dict(transport_errors),
    }

    if track_windows and slice_samples:
        origin_m = min(s[0] for s in slice_samples)
        win_len = spec["windowSeconds"]
        buckets: Dict[int, List[Tuple[float, bool]]] = {}
        for ts_m, lat_ms, ok in slice_samples:
            idx = int((ts_m - origin_m) // win_len)
            buckets.setdefault(idx, []).append((lat_ms, ok))
        timeline = []
        for idx in sorted(buckets):
            rows = buckets[idx]
            ok_rows = sum(1 for _, ok in rows if ok)
            timeline.append({
                "windowIndex": idx,
                "totalRequests": len(rows),
                "successfulRequests": ok_rows,
                "qps": round(ok_rows / win_len, 3),
                "latencyMs": _latency_summary([r[0] for r in rows]),
            })
        stage_result["agingTimeline"] = timeline
        if len(timeline) >= 2 and timeline[0]["latencyMs"]["p95"] and timeline[-1]["latencyMs"]["p95"]:
            base_p95 = timeline[0]["latencyMs"]["p95"]
            end_p95 = timeline[-1]["latencyMs"]["p95"]
            stage_result["p95DegradationPercent"] = round(((end_p95 - base_p95) / base_p95) * 100.0, 2)

    return stage_result


def _render_markdown(report: Dict[str, Any]) -> str:
    lines = [
        "# Cross-Server Load & APM Report",
        "",
        f"- Mode: `{report['spec']['mode']}` (`{report['spec']['connectionMode']}`)",
        f"- Target URL: `{report['spec']['url']}` (`{report['spec']['method']}`)",
        f"- Auth Mode: `{report['spec']['authMode']}`",
        f"- APM URL: `{report['spec'].get('apmUrl') or 'disabled'}`",
        "",
        "## Stages",
        "",
        "| Stage | Concurrency | Total | Success | Failed | QPS | P50 (ms) | P95 (ms) | P99 (ms) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for idx, st in enumerate(report["stages"], start=1):
        lat = st["latencyMs"]
        lines.append(
            f"| {idx} | {st['concurrency']} | {st['totalRequests']} | {st['successfulRequests']} | "
            f"{st['failedRequests']} | {st['qps']} | {lat['p50']} | {lat['p95']} | {lat['p99']} |"
        )
        apm = st.get("apm")
        if isinstance(apm, dict):
            lines.append("")
            lines.append(f"### Stage {idx} APM Summary ({apm.get('windowSeconds')}s)")
            lines.append(f"- Host CPU avg/max: `{apm['host'].get('cpuPercent')}`")
            lines.append(f"- Traefik RPS avg / P95 ms: `{apm['traefik'].get('rpsAvg')}` / `{apm['traefik'].get('p95LatencyMs')}`")
            lines.append(f"- Postgres commits delta / active conn: `{apm['postgres'].get('commitsDelta')}` / `{apm['postgres'].get('activeConnections')}`")
            lines.append(f"- magicBase ORM delta / HTTP delta: `{apm['magicbase'].get('ormOperationsDelta')}` / `{apm['magicbase'].get('httpRequestsDelta')}`")
    return "\n".join(lines).rstrip() + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", help="Optional JSON load specification file")
    parser.add_argument("--url", help="Target HTTPS/HTTP endpoint URL")
    parser.add_argument("--method", choices=["GET", "POST", "PUT", "DELETE"], help="HTTP method (default: GET)")
    parser.add_argument("--body-file", help="Optional JSON request body file")
    parser.add_argument("--from-sim-state", help="Reuse non-secret URLs and 0600 secrets from bootstrap_simulated_apps state-dir")
    parser.add_argument("--sim-app", choices=["device-management", "chess-room-booking"], help="Simulated app key")
    parser.add_argument("--sim-scenario", choices=["gateway-read", "apps-read"], help="Simulated app load scenario")
    parser.add_argument("--auth-mode", choices=["public", "apikey", "bearer"], help="Authentication mode")
    parser.add_argument("--secret-file", help="0600 regular file containing ApiKey or Bearer JWT")
    parser.add_argument("--target-address", help="Optional explicit IP/host override while preserving Host/SNI")
    parser.add_argument("--ca-file", help="Optional TLS CA or leaf certificate file")
    parser.add_argument("--trust-leaf", action="store_true", help="Allow partial chain leaf certificate verification")
    parser.add_argument("--insecure", action="store_true", help="Skip TLS verification (dev-only)")
    parser.add_argument("--mode", choices=["steady", "step", "aging"], help="Load profile mode")
    parser.add_argument("--concurrency", help="Concurrency level(s), e.g. 8 or 2,8,16")
    parser.add_argument("--duration", type=float, help="Duration in seconds (per stage for steady/step; total for aging)")
    parser.add_argument("--window-seconds", type=float, help="Aging time-slice window seconds (default: 60)")
    parser.add_argument("--connection-mode", choices=["keep-alive", "cold-tls"], help="Connection reuse vs cold TLS")
    parser.add_argument("--timeout", type=float, help="Per-request timeout seconds")
    parser.add_argument("--apm-url", help="Platform Prometheus base URL (e.g. https://apm.example.com/prometheus/)")
    parser.add_argument("--apm-auth-file", help="0600 file containing user:password for APM BasicAuth")
    parser.add_argument("--apm-idle-seconds", type=int, help="Pre-load idle APM baseline duration in seconds")
    parser.add_argument("--apm-settle-seconds", type=int, help="Post-stage wait seconds before Prometheus query")
    parser.add_argument("--require-apm", action="store_true", help="Fail fast if Prometheus APM is unreachable")
    parser.add_argument("--output", help="Output directory (must not overwrite existing report.json)")
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs and print plan without sending requests")
    args = parser.parse_args(argv)

    spec = _build_spec(args)
    if args.dry_run:
        safe_spec = {k: v for k, v in spec.items() if k != "bodyText"}
        print(json.dumps({"dryRun": True, "spec": safe_spec}, ensure_ascii=False, indent=2))
        return 0

    auth_header = _load_auth_header(spec)
    parsed = urlsplit(spec["url"])
    ssl_ctx = build_ssl_context(ca_file=spec["caFile"], trust_leaf=spec["trustLeaf"], insecure=spec["insecure"]) if parsed.scheme == "https" else None

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.output or (ROOT / "reports/load" / stamp)).expanduser().resolve()
    report_path = out_dir / "report.json"
    if report_path.exists():
        raise ValueError(f"Output already contains report.json: {report_path}")
    out_dir.mkdir(parents=True, exist_ok=True)

    apm_client: Optional[PrometheusClient] = None
    apm_ready: Optional[Dict[str, Any]] = None
    apm_idle: Optional[Dict[str, Any]] = None
    if spec["apmUrl"]:
        apm_client = PrometheusClient(
            spec["apmUrl"],
            target_address=spec["targetAddress"],
            ca_file=spec["caFile"],
            trust_leaf=spec["trustLeaf"],
            insecure=spec["insecure"],
            basic_auth_file=spec["apmAuthFile"],
            timeout=spec["timeoutSeconds"],
        )
        try:
            apm_ready = apm_client.check_ready()
        except Exception as exc:
            if spec["requireApm"]:
                raise
            apm_ready = {"ready": False, "error": f"{type(exc).__name__}: {exc}"}

        if apm_ready.get("ready") and spec["apmIdleSeconds"] > 0:
            idle_start = time.time()
            time.sleep(spec["apmIdleSeconds"])
            idle_end = time.time()
            apm_idle = collect_window_metrics(apm_client, idle_start, idle_end)

    stages: List[Dict[str, Any]] = []
    concurrency_list = spec["concurrency"] if spec["mode"] == "step" else [spec["concurrency"][0]]
    for workers in concurrency_list:
        stage = _run_stage(
            spec,
            workers=workers,
            duration_seconds=spec["durationSeconds"],
            auth_header=auth_header,
            ssl_ctx=ssl_ctx,
            track_windows=(spec["mode"] == "aging"),
        )
        if apm_client and apm_ready and apm_ready.get("ready"):
            if spec["apmSettleSeconds"] > 0:
                time.sleep(spec["apmSettleSeconds"])
            stage["apm"] = collect_window_metrics(apm_client, stage["startTimestamp"], stage["endTimestamp"])
        stages.append(stage)

    safe_spec = {k: v for k, v in spec.items() if k != "bodyText"}
    report: Dict[str, Any] = {
        "schema": "magic.load.report/v1",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "spec": safe_spec,
        "apmReady": apm_ready,
        "apmIdleBaseline": apm_idle,
        "stages": stages,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "summary.md").write_text(_render_markdown(report), encoding="utf-8")
    print(json.dumps({"outputDir": str(out_dir), "stages": len(stages), "apmReady": bool(apm_ready and apm_ready.get("ready"))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"Load runner failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
