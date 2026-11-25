#!/usr/bin/env python3
"""Read-only Prometheus APM client for cross-server performance verification."""
from __future__ import annotations

import base64
import http.client
import json
import os
from pathlib import Path
import ssl
import stat
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode, urlsplit


class _SniHTTPSConnection(http.client.HTTPSConnection):
    """Connect to an explicit target IP/address while preserving TLS SNI."""

    def __init__(self, connect_host: str, sni_host: str, port: int, *, context: ssl.SSLContext, timeout: float):
        super().__init__(connect_host, port=port, context=context, timeout=timeout)
        self._sni_host = sni_host

    def connect(self) -> None:
        sock = self._create_connection((self.host, self.port), self.timeout, self.source_address)
        if self._tunnel_host:
            self.sock = sock
            self._tunnel()
        self.sock = self._context.wrap_socket(sock, server_hostname=self._sni_host)


def read_private_secret(path_value: str | Path, *, max_bytes: int = 16384, label: str = "secret") -> str:
    """Read a regular, owner-only (0600), non-symlink secret file outside repositories."""
    path = Path(path_value).expanduser()
    if path.is_symlink():
        raise ValueError(f"{label} file must not be a symlink: {path}")
    if not path.is_file():
        raise ValueError(f"{label} file does not exist: {path}")
    st = path.stat()
    if hasattr(os, "getuid") and st.st_uid != os.getuid():
        raise ValueError(f"{label} file must be owned by current user: {path}")
    if stat.S_IMODE(st.st_mode) & 0o077:
        raise ValueError(f"{label} file permissions must be 0600 (no group/other access): {path}")
    raw = path.read_bytes()
    if not raw.strip():
        raise ValueError(f"{label} file is empty: {path}")
    if len(raw) > max_bytes:
        raise ValueError(f"{label} file exceeds {max_bytes} byte limit ({len(raw)} bytes): {path}")
    return raw.decode("utf-8").strip()


def build_ssl_context(*, ca_file: Optional[str] = None, trust_leaf: bool = False, insecure: bool = False) -> ssl.SSLContext:
    if insecure:
        return ssl._create_unverified_context()
    if ca_file:
        ctx = ssl.create_default_context(cafile=str(Path(ca_file).expanduser()))
        if trust_leaf and hasattr(ssl, "VERIFY_X509_PARTIAL_CHAIN"):
            ctx.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
        return ctx
    return ssl.create_default_context()


class PrometheusClient:
    """Zero-dependency HTTP/HTTPS Prometheus query client."""

    def __init__(
        self,
        base_url: str,
        *,
        target_address: Optional[str] = None,
        ca_file: Optional[str] = None,
        trust_leaf: bool = False,
        insecure: bool = False,
        basic_auth_file: Optional[str] = None,
        timeout: float = 15.0,
    ) -> None:
        parsed = urlsplit(base_url.strip())
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("apmUrl requires an explicit http/https URL without embedded credentials")
        self.base_url = base_url.strip().rstrip("/")
        self._parsed = parsed
        self._base_path = parsed.path.rstrip("/")
        self._connect_host = target_address.strip() if target_address and target_address.strip() else parsed.hostname
        self._port = parsed.port or (443 if parsed.scheme == "https" else 80)
        self._timeout = timeout
        self._ssl_ctx = build_ssl_context(ca_file=ca_file, trust_leaf=trust_leaf, insecure=insecure) if parsed.scheme == "https" else None
        self._auth_header: Optional[str] = None
        if basic_auth_file:
            creds = read_private_secret(basic_auth_file, max_bytes=4096, label="APM basic auth")
            if ":" not in creds:
                raise ValueError("APM basic auth file must be user:password")
            token = base64.b64encode(creds.encode("utf-8")).decode("ascii")
            self._auth_header = f"Basic {token}"

    def _request(self, suffix: str, params: Optional[Dict[str, Any]] = None) -> tuple[int, bytes]:
        path = f"{self._base_path}{suffix}"
        if params:
            path = f"{path}?{urlencode(params)}"
        headers = {"Host": self._parsed.netloc, "Accept": "application/json"}
        if self._auth_header:
            headers["Authorization"] = self._auth_header
        if self._parsed.scheme == "https":
            conn: http.client.HTTPConnection = _SniHTTPSConnection(
                self._connect_host, self._parsed.hostname, self._port, context=self._ssl_ctx, timeout=self._timeout
            )
        else:
            conn = http.client.HTTPConnection(self._connect_host, port=self._port, timeout=self._timeout)
        try:
            conn.request("GET", path, headers=headers)
            resp = conn.getresponse()
            body = resp.read(8 * 1024 * 1024)
            return resp.status, body
        finally:
            conn.close()

    def _query_json(self, suffix: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        status, body = self._request(suffix, params)
        if status != 200:
            raise RuntimeError(f"Prometheus HTTP {status} on {suffix}")
        payload = json.loads(body.decode("utf-8"))
        if payload.get("status") != "success":
            raise RuntimeError(f"Prometheus API error on {suffix}: {payload.get('error', payload.get('status'))}")
        return payload.get("data", {})

    def check_ready(self) -> Dict[str, Any]:
        status, _ = self._request("/-/ready")
        if status != 200:
            raise RuntimeError(f"Prometheus readiness check returned HTTP {status}")
        targets_data = self._query_json("/api/v1/targets", {"state": "active"})
        active = targets_data.get("activeTargets", [])
        jobs: Dict[str, Dict[str, int]] = {}
        down_targets: List[Dict[str, str]] = []
        for item in active:
            labels = item.get("labels") or {}
            job = str(labels.get("job") or item.get("scrapePool") or "unknown")
            health = str(item.get("health") or "unknown")
            bucket = jobs.setdefault(job, {"up": 0, "down": 0, "unknown": 0})
            if health == "up":
                bucket["up"] += 1
            elif health == "down":
                bucket["down"] += 1
                down_targets.append({
                    "job": job,
                    "instance": str(labels.get("instance") or item.get("scrapeUrl") or ""),
                    "lastError": str(item.get("lastError") or "")[:200],
                })
            else:
                bucket["unknown"] += 1
        return {
            "ready": True,
            "activeTargetCount": len(active),
            "jobs": jobs,
            "downTargets": down_targets,
        }

    def query(self, promql: str, *, at_ts: Optional[float] = None) -> Dict[str, Any]:
        params: Dict[str, Any] = {"query": promql}
        if at_ts is not None:
            params["time"] = f"{at_ts:.3f}"
        return self._query_json("/api/v1/query", params)

    def query_range(self, promql: str, start_ts: float, end_ts: float, step_seconds: int = 15) -> Dict[str, Any]:
        return self._query_json(
            "/api/v1/query_range",
            {
                "query": promql,
                "start": f"{start_ts:.3f}",
                "end": f"{end_ts:.3f}",
                "step": f"{max(1, int(step_seconds))}s",
            },
        )


def _scalar_value(data: Dict[str, Any]) -> Optional[float]:
    results = data.get("result") or []
    if not results:
        return None
    raw = results[0].get("value")
    if not isinstance(raw, list) or len(raw) < 2:
        return None
    try:
        val = float(raw[1])
        return val if val == val else None
    except (TypeError, ValueError):
        return None


def _vector_map(data: Dict[str, Any], label_keys: tuple[str, ...]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for row in data.get("result") or []:
        metric = row.get("metric") or {}
        key = "/".join(str(metric.get(k, "")) for k in label_keys if metric.get(k))
        if not key:
            key = "unknown"
        raw = row.get("value")
        if not isinstance(raw, list) or len(raw) < 2:
            continue
        try:
            val = float(raw[1])
        except (TypeError, ValueError):
            continue
        if val == val:
            out[key] = round(val, 4)
    return out


def _range_stats(data: Dict[str, Any]) -> Optional[Dict[str, float]]:
    series = data.get("result") or []
    if not series:
        return None
    vals: List[float] = []
    for item in series:
        for pair in item.get("values") or []:
            if isinstance(pair, list) and len(pair) >= 2:
                try:
                    v = float(pair[1])
                    if v == v:
                        vals.append(v)
                except (TypeError, ValueError):
                    continue
    if not vals:
        return None
    return {
        "avg": round(sum(vals) / len(vals), 4),
        "max": round(max(vals), 4),
        "samples": len(vals),
    }


def _safe_query(client: PrometheusClient, promql: str, *, at_ts: float, errors: List[Dict[str, str]], label: str) -> Dict[str, Any]:
    try:
        return client.query(promql, at_ts=at_ts)
    except Exception as exc:
        errors.append({"metric": label, "error": f"{type(exc).__name__}: {exc}"})
        return {"result": []}


def _safe_range(
    client: PrometheusClient,
    promql: str,
    *,
    start_ts: float,
    end_ts: float,
    step_seconds: int,
    errors: List[Dict[str, str]],
    label: str,
) -> Dict[str, Any]:
    try:
        return client.query_range(promql, start_ts, end_ts, step_seconds=step_seconds)
    except Exception as exc:
        errors.append({"metric": label, "error": f"{type(exc).__name__}: {exc}"})
        return {"result": []}


def collect_window_metrics(
    client: PrometheusClient,
    start_ts: float,
    end_ts: float,
    *,
    step_seconds: int = 15,
) -> Dict[str, Any]:
    """Collect host, container, Traefik, Postgres, and magicBase metrics for [start_ts, end_ts]."""
    duration_s = max(1, int(round(end_ts - start_ts)))
    window = f"{duration_s}s"
    errors: List[Dict[str, str]] = []

    # 1. Host (node-exporter)
    host_cpu = _range_stats(_safe_range(
        client,
        '100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[1m])))',
        start_ts=start_ts, end_ts=end_ts, step_seconds=step_seconds, errors=errors, label="host.cpuPercent",
    ))
    host_mem = _range_stats(_safe_range(
        client,
        '100 * (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes))',
        start_ts=start_ts, end_ts=end_ts, step_seconds=step_seconds, errors=errors, label="host.memoryUsedPercent",
    ))
    host_load1 = _scalar_value(_safe_query(client, "node_load1", at_ts=end_ts, errors=errors, label="host.load1"))
    host_section: Dict[str, Any] = {
        "available": any(x is not None for x in (host_cpu, host_mem, host_load1)),
        "cpuPercent": host_cpu,
        "memoryUsedPercent": host_mem,
        "load1": round(host_load1, 4) if host_load1 is not None else None,
    }

    # 2. Containers (cadvisor)
    cpu_by_c = _vector_map(
        _safe_query(
            client,
            f'sum by (name) (rate(container_cpu_usage_seconds_total{{name!=""}}[{window}]))',
            at_ts=end_ts, errors=errors, label="containers.cpuCores",
        ),
        ("name",),
    )
    mem_by_c = _vector_map(
        _safe_query(
            client,
            'max by (name) (container_memory_working_set_bytes{name!=""}) / 1048576',
            at_ts=end_ts, errors=errors, label="containers.memoryMiB",
        ),
        ("name",),
    )
    containers: Dict[str, Dict[str, Any]] = {}
    for name in sorted(set(cpu_by_c) | set(mem_by_c)):
        containers[name] = {
            "cpuCoresAvg": cpu_by_c.get(name),
            "memoryWorkingSetMiB": mem_by_c.get(name),
        }
    containers_section = {
        "available": bool(containers),
        "byContainer": containers,
    }

    # 3. Traefik ingress metrics
    traefik_reqs = _vector_map(
        _safe_query(
            client,
            f'sum by (code) (increase(traefik_service_requests_total[{window}]))',
            at_ts=end_ts, errors=errors, label="traefik.requestsByCode",
        ),
        ("code",),
    )
    traefik_p95_s = _scalar_value(_safe_query(
        client,
        f'histogram_quantile(0.95, sum by (le) (rate(traefik_service_request_duration_seconds_bucket[{window}])))',
        at_ts=end_ts, errors=errors, label="traefik.p95DurationSeconds",
    ))
    traefik_p99_s = _scalar_value(_safe_query(
        client,
        f'histogram_quantile(0.99, sum by (le) (rate(traefik_service_request_duration_seconds_bucket[{window}])))',
        at_ts=end_ts, errors=errors, label="traefik.p99DurationSeconds",
    ))
    traefik_total = sum(traefik_reqs.values()) if traefik_reqs else None
    traefik_section = {
        "available": bool(traefik_reqs) or traefik_p95_s is not None,
        "requestsTotalDelta": round(traefik_total, 4) if traefik_total is not None else None,
        "rpsAvg": round(traefik_total / duration_s, 4) if traefik_total is not None else None,
        "requestsByStatusCode": traefik_reqs,
        "p95LatencyMs": round(traefik_p95_s * 1000.0, 3) if traefik_p95_s is not None else None,
        "p99LatencyMs": round(traefik_p99_s * 1000.0, 3) if traefik_p99_s is not None else None,
    }

    # 4. PostgreSQL (postgres-exporter)
    pg_commits = _scalar_value(_safe_query(
        client, f"sum(increase(pg_stat_database_xact_commit[{window}]))", at_ts=end_ts, errors=errors, label="postgres.commitsDelta",
    ))
    pg_rollbacks = _scalar_value(_safe_query(
        client, f"sum(increase(pg_stat_database_xact_rollback[{window}]))", at_ts=end_ts, errors=errors, label="postgres.rollbacksDelta",
    ))
    pg_active = _scalar_value(_safe_query(
        client, 'sum(pg_stat_activity_count{state="active"})', at_ts=end_ts, errors=errors, label="postgres.activeConnections",
    ))
    pg_idle = _scalar_value(_safe_query(
        client, 'sum(pg_stat_activity_count{state="idle"})', at_ts=end_ts, errors=errors, label="postgres.idleConnections",
    ))
    pg_hit_ratio = _scalar_value(_safe_query(
        client,
        f"sum(increase(pg_stat_database_blks_hit[{window}])) / clamp_min(sum(increase(pg_stat_database_blks_hit[{window}])) + sum(increase(pg_stat_database_blks_read[{window}])), 1)",
        at_ts=end_ts, errors=errors, label="postgres.cacheHitRatio",
    ))
    postgres_section = {
        "available": any(x is not None for x in (pg_commits, pg_rollbacks, pg_active, pg_idle, pg_hit_ratio)),
        "commitsDelta": round(pg_commits, 4) if pg_commits is not None else None,
        "rollbacksDelta": round(pg_rollbacks, 4) if pg_rollbacks is not None else None,
        "activeConnections": round(pg_active, 2) if pg_active is not None else None,
        "idleConnections": round(pg_idle, 2) if pg_idle is not None else None,
        "cacheHitRatio": round(pg_hit_ratio, 6) if pg_hit_ratio is not None else None,
    }

    # 5. magicBase (fixed base :9090)
    base_http = _scalar_value(_safe_query(
        client, f"sum(increase(magicBase_magicbase_http_requests_total[{window}]))", at_ts=end_ts, errors=errors, label="magicbase.httpRequestsDelta",
    ))
    base_orm = _scalar_value(_safe_query(
        client, f"sum(increase(magicBase_magicorm_orm_operations_total[{window}]))", at_ts=end_ts, errors=errors, label="magicbase.ormOperationsDelta",
    ))
    base_db_q = _scalar_value(_safe_query(
        client, f"sum(increase(magicBase_magicorm_database_queries_total[{window}]))", at_ts=end_ts, errors=errors, label="magicbase.dbQueriesDelta",
    ))
    base_db_e = _scalar_value(_safe_query(
        client, f"sum(increase(magicBase_magicorm_database_executions_total[{window}]))", at_ts=end_ts, errors=errors, label="magicbase.dbExecutionsDelta",
    ))
    magicbase_section = {
        "available": any(x is not None for x in (base_http, base_orm, base_db_q, base_db_e)),
        "httpRequestsDelta": round(base_http, 4) if base_http is not None else None,
        "ormOperationsDelta": round(base_orm, 4) if base_orm is not None else None,
        "dbQueriesDelta": round(base_db_q, 4) if base_db_q is not None else None,
        "dbExecutionsDelta": round(base_db_e, 4) if base_db_e is not None else None,
        "note": "Reflects scraped fixed magicBase target(s); check monitoring.samplingRate (default 0.5) before comparing raw counts to client requests.",
    }

    return {
        "windowSeconds": duration_s,
        "startTimestamp": round(start_ts, 3),
        "endTimestamp": round(end_ts, 3),
        "host": host_section,
        "containers": containers_section,
        "traefik": traefik_section,
        "postgres": postgres_section,
        "magicbase": magicbase_section,
        "queryErrors": errors,
    }
