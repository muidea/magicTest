#!/usr/bin/env python3
"""Deterministic VMI 18-entity 6-domain Gateway + Bearer Apps-Action simulator: inspect/plan/run/verify."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import secrets
import ssl
import stat
import sys
import tempfile
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from platform_paths import resolve_app_model_root

ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = resolve_app_model_root("vmi")
PKG_PREFIX = "vmi"
SERVICE_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{2,63}$")

VMI_DOMAIN_SERVICES: tuple[dict[str, Any], ...] = (
    {
        "key": "vmi_partner_service",
        "domain": "partner",
        "showName": "VMI 合作方与会员服务",
        "entities": ("partner", "member"),
    },
    {
        "key": "vmi_catalog_service",
        "domain": "catalog",
        "showName": "VMI 商品目录与规格服务",
        "entities": ("product", "productInfo"),
    },
    {
        "key": "vmi_warehouse_service",
        "domain": "warehouse",
        "showName": "VMI 仓储与货架库位服务",
        "entities": ("warehouse", "shelf"),
    },
    {
        "key": "vmi_inventory_service",
        "domain": "inventory",
        "showName": "VMI 门店商品与出入库告警服务",
        "entities": ("store", "goods", "stockin", "stockout", "goodsInfo", "inventoryAlert"),
    },
    {
        "key": "vmi_order_service",
        "domain": "order",
        "showName": "VMI 销售订单与履约服务",
        "entities": ("order", "goodsItem"),
    },
    {
        "key": "vmi_loyalty_service",
        "domain": "loyalty",
        "showName": "VMI 激励策略与积分报表服务",
        "entities": ("rewardPolicy", "credit", "creditReward", "creditReport"),
    },
)

VMI_SERVICE_BY_KEY: dict[str, dict[str, Any]] = {svc["key"]: svc for svc in VMI_DOMAIN_SERVICES}
VMI_SERVICE_KEY_BY_DOMAIN: dict[str, str] = {svc["domain"]: svc["key"] for svc in VMI_DOMAIN_SERVICES}
VMI_ENTITY_TO_SERVICE_KEY: dict[str, str] = {
    entity: svc["key"]
    for svc in VMI_DOMAIN_SERVICES
    for entity in svc["entities"]
}


class Failure(ValueError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise Failure(message)


def service_key_for_entity(entity_name: str) -> str:
    svc_key = VMI_ENTITY_TO_SERVICE_KEY.get(entity_name)
    require(svc_key is not None, f"unknown VMI entity for domain routing: {entity_name!r}")
    return str(svc_key)


def resolve_domain_filter(raw: str | None) -> tuple[str, ...]:
    if raw is None or not raw.strip():
        return tuple(svc["key"] for svc in VMI_DOMAIN_SERVICES)
    tokens = [tok.strip() for tok in raw.split(",") if tok.strip()]
    require(bool(tokens), "empty --domains filter")
    selected_set: set[str] = set()
    for tok in tokens:
        if tok in VMI_SERVICE_BY_KEY:
            selected_set.add(tok)
        elif tok in VMI_SERVICE_KEY_BY_DOMAIN:
            selected_set.add(VMI_SERVICE_KEY_BY_DOMAIN[tok])
        else:
            raise Failure(f"unknown VMI domain or service key: {tok!r}")
    return tuple(svc["key"] for svc in VMI_DOMAIN_SERVICES if svc["key"] in selected_set)


def validate_domain_services(model_root: Path = MODEL_ROOT) -> None:
    entities_dir = model_root / "definition/application/entities"
    model_entities = {p.stem for p in entities_dir.glob("*.json")}
    require(bool(model_entities), f"no entity definitions found under {entities_dir}")

    seen: dict[str, str] = {}
    for svc in VMI_DOMAIN_SERVICES:
        svc_key = str(svc["key"])
        require(bool(SERVICE_KEY_RE.fullmatch(svc_key)), f"invalid service key format: {svc_key!r}")
        for ent in svc["entities"]:
            require(ent not in seen, f"entity {ent!r} duplicated across {seen.get(ent)!r} and {svc_key!r}")
            seen[ent] = svc_key
    missing = sorted(model_entities - set(seen))
    extra = sorted(set(seen) - model_entities)
    require(not missing and not extra, f"domain service entity mismatch: missing={missing}, extra={extra}")


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def strict_json(raw: bytes | str) -> Any:
    def unique(items):
        result = {}
        for k, v in items:
            require(k not in result, f"duplicate JSON key: {k}")
            result[k] = v
        return result

    try:
        return json.loads(
            raw,
            object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(Failure("nonfinite JSON")),
        )
    except (UnicodeError, json.JSONDecodeError):
        raise Failure("invalid JSON") from None


def parse_utc(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(timezone.utc).replace(microsecond=0)
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    require(parsed.tzinfo is not None, "explicit timezone required")
    return parsed.astimezone(timezone.utc).replace(microsecond=0)


def iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def simulation_plan(anchor_utc: str | None = None, run_id: str | None = None, mode: str = "seed") -> dict[str, Any]:
    require(mode in ("seed", "replay"), f"unsupported mode: {mode}")
    anchor = parse_utc(anchor_utc)
    rid = (run_id or hashlib.sha256(f"{mode}:{iso_utc(anchor)}".encode()).hexdigest()[:12]).upper()
    t0 = iso_utc(anchor)
    t1 = iso_utc(anchor + timedelta(minutes=15))

    creates = [
        {"key": "partner:root", "entity": "partner", "values": {"partnerCode": f"VMI-P-{rid}-ROOT", "name": f"中心分销商-{rid}", "contact": "010-80001001"}},
        {"key": "partner:sub", "entity": "partner", "values": {"partnerCode": f"VMI-P-{rid}-SUB", "name": f"华东加盟商-{rid}", "refererId": {"$ref": "partner:root"}, "contact": "021-60002002"}},
        {"key": "warehouse:main", "entity": "warehouse", "values": {"code": f"VMI-WH-{rid}", "name": f"华东中心仓-{rid}", "region": "华东", "address": "上海市浦东新区临港园区1号"}},
        {"key": "shelf:a1", "entity": "shelf", "values": {"code": f"VMI-SH-{rid}-A1", "name": "冷链主货架A1", "warehouseId": {"$ref": "warehouse:main"}, "capacity": 500, "usedCapacity": 320}},
        {"key": "shelf:a2", "entity": "shelf", "values": {"code": f"VMI-SH-{rid}-A2", "name": "常温主货架A2", "warehouseId": {"$ref": "warehouse:main"}, "capacity": 300, "usedCapacity": 120}},
        {"key": "product:drink", "entity": "product", "values": {"code": f"VMI-PR-{rid}-01", "name": "精品乌龙茶", "category": "饮品", "expireHours": 4320}},
        {"key": "productInfo:sku1", "entity": "productInfo", "values": {"sku": f"VMI-SKU-{rid}-500ML", "productId": {"$ref": "product:drink"}, "specName": "500ml*15整箱", "unitPrice": 68.5}},
        {"key": "store:s1", "entity": "store", "values": {"code": f"VMI-ST-{rid}-01", "name": f"陆家嘴旗舰店-{rid}", "warehouseId": {"$ref": "warehouse:main"}, "shelfIds": [{"$ref": "shelf:a1"}, {"$ref": "shelf:a2"}]}},
        {"key": "member:m1", "entity": "member", "values": {"memberCode": f"VMI-MB-{rid}-01", "name": "张明", "partnerId": {"$ref": "partner:sub"}, "phone": "13800001001"}},
        {"key": "goods:g1", "entity": "goods", "values": {"goodsCode": f"VMI-GD-{rid}-01", "name": "旗舰店精品乌龙茶箱装", "storeId": {"$ref": "store:s1"}, "productInfoId": {"$ref": "productInfo:sku1"}, "shelfIds": [{"$ref": "shelf:a1"}], "price": 79.0, "stockCount": 8, "safetyStock": 15}},
        {"key": "stockin:si1", "entity": "stockin", "values": {"billNo": f"VMI-SI-{rid}-01", "storeId": {"$ref": "store:s1"}, "warehouseId": {"$ref": "warehouse:main"}, "totalQuantity": 150}},
        {"key": "stockout:so1", "entity": "stockout", "values": {"billNo": f"VMI-SO-{rid}-01", "storeId": {"$ref": "store:s1"}, "warehouseId": {"$ref": "warehouse:main"}, "totalQuantity": 20}},
        {"key": "order:o1", "entity": "order", "values": {"orderNo": f"VMI-OD-{rid}-01", "storeId": {"$ref": "store:s1"}, "customerId": {"$ref": "member:m1"}, "totalCost": 1580.0, "totalItems": 20}},
        {"key": "rewardPolicy:rp1", "entity": "rewardPolicy", "values": {"policyCode": f"VMI-RP-{rid}-01", "name": "满千返1%积分", "rate": 1.0, "minOrderAmount": 1000.0}},
        {"key": "credit:cr1", "entity": "credit", "values": {"entryNo": f"VMI-CR-{rid}-01", "ownerId": {"$ref": "member:m1"}, "orderId": {"$ref": "order:o1"}, "deltaAmount": 15.8, "balanceAfter": 15.8, "reason": "订单消费返利入账", "occurredAt": t1}},
        {"key": "creditReport:rep1", "entity": "creditReport", "values": {"reportCode": f"VMI-REP-{rid}-01", "ownerId": {"$ref": "member:m1"}, "periodKey": anchor.strftime("%Y-%m"), "totalEarned": 20.8, "totalSpent": 5.0, "currentBalance": 15.8}},
        # Below-threshold goodsInfo -> 0 alerts; high-quantity goodsInfo -> 1 warning alert
        {"key": "goodsInfo:low", "entity": "goodsInfo", "values": {"lineNo": f"VMI-MV-{rid}-01", "direction": "out", "stockoutId": {"$ref": "stockout:so1"}, "storeId": {"$ref": "store:s1"}, "goodsId": {"$ref": "goods:g1"}, "productInfoId": {"$ref": "productInfo:sku1"}, "quantity": 20, "unitPrice": 68.5, "occurredAt": t0}},
        {"key": "goodsInfo:high", "entity": "goodsInfo", "values": {"lineNo": f"VMI-MV-{rid}-02", "direction": "in", "stockinId": {"$ref": "stockin:si1"}, "storeId": {"$ref": "store:s1"}, "goodsId": {"$ref": "goods:g1"}, "productInfoId": {"$ref": "productInfo:sku1"}, "quantity": 150, "unitPrice": 68.5, "occurredAt": t1}},
        # High-value goodsItem -> 1 warning alert (while order:o1 is pending_payment)
        {"key": "goodsItem:high", "entity": "goodsItem", "values": {"itemCode": f"VMI-GI-{rid}-01", "orderId": {"$ref": "order:o1"}, "storeId": {"$ref": "store:s1"}, "goodsId": {"$ref": "goods:g1"}, "quantity": 20, "unitPrice": 79.0, "subtotal": 1580.0, "occurredAt": t1}},
    ]
    post_action_creates = [
        # creditReward references order.status in [paid, fulfilling, completed]
        {"key": "creditReward:rw1", "entity": "creditReward", "values": {"rewardNo": f"VMI-RW-{rid}-01", "policyId": {"$ref": "rewardPolicy:rp1"}, "ownerId": {"$ref": "member:m1"}, "orderId": {"$ref": "order:o1"}, "rewardAmount": 15.8, "status": "issued", "occurredAt": t1}},
    ]
    for step in (*creates, *post_action_creates):
        step["serviceKey"] = service_key_for_entity(step["entity"])
        vals = step["values"]
        stamp = vals.get("occurredAt") or t0
        vals.setdefault("createdAt", stamp)
        vals.setdefault("updatedAt", stamp)
        vals.setdefault("updatedBy", "vmi:simulator")

    actions = [
        {"targetKey": "stockin:si1", "entity": "stockin", "action": "submit", "payload": {}},
        {"targetKey": "stockin:si1", "entity": "stockin", "action": "complete", "payload": {}},
        {"targetKey": "order:o1", "entity": "order", "action": "pay", "payload": {}},
        {"targetKey": "order:o1", "entity": "order", "action": "start-fulfill", "payload": {}},
        {"targetKey": "order:o1", "entity": "order", "action": "complete", "payload": {}},
    ]

    return {
        "schemaVersion": "vmi.simulation-plan/v1",
        "mode": mode,
        "runId": rid,
        "anchorUtc": iso_utc(anchor),
        "domainServices": [
            {
                "key": svc["key"],
                "domain": svc["domain"],
                "showName": svc["showName"],
                "entities": list(svc["entities"]),
            }
            for svc in VMI_DOMAIN_SERVICES
        ],
        "creates": creates,
        "actions": actions,
        "postActionCreates": post_action_creates,
        "expectedAlertCount": 2,
    }


def _read_secret(path: str | None, env_name: str, label: str) -> str:
    if path:
        fd = os.open(Path(path).expanduser(), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            require(
                stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o600,
                f"{label} file requires owned regular mode 0600",
            )
            raw = os.read(fd, 16385)
            require(len(raw) <= 16384, f"{label} file too large")
            value = raw.decode().strip()
        finally:
            os.close(fd)
    else:
        value = os.environ.get(env_name, "").strip()
    require(bool(value) and len(value) <= 16384, f"missing {label}")
    return value


def _tls_context(ca_file: str | None = None, trust_leaf: bool = False) -> ssl.SSLContext:
    context = ssl.create_default_context(cafile=str(Path(ca_file).expanduser()) if ca_file else None)
    if trust_leaf:
        require(bool(ca_file) and hasattr(ssl, "VERIFY_X509_PARTIAL_CHAIN"), "explicit leaf trust unsupported")
        context.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
    return context


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _http_json(
    opener,
    method: str,
    url: str,
    headers: dict[str, str],
    body: Any = None,
    timeout: float = 30.0,
) -> tuple[int, Any]:
    raw_body = dumps(body).encode("utf-8") if body is not None else None
    req = Request(url, data=raw_body, method=method, headers=headers)
    try:
        with opener.open(req, timeout=timeout) as resp:
            payload = resp.read((8 << 20) + 1)
            require(len(payload) <= (8 << 20), "response exceeded 8MiB")
            parsed = strict_json(payload)
            if isinstance(parsed, dict) and parsed.get("error") is not None:
                raise Failure(f"API error {method} {url}: {parsed['error']}")
            return resp.status, parsed
    except HTTPError as exc:
        err_raw = exc.read(1 << 20)
        raise Failure(f"HTTP {exc.code} {url}: {err_raw.decode('utf-8', 'replace')}") from exc
    except URLError as exc:
        raise Failure(f"request error {url}: {exc.reason}") from exc


def _http_status(
    opener,
    method: str,
    url: str,
    headers: dict[str, str],
    timeout: float = 30.0,
) -> int:
    req = Request(url, method=method, headers=headers)
    try:
        with opener.open(req, timeout=timeout) as resp:
            resp.read(64 << 10)
            return int(resp.status)
    except HTTPError as exc:
        try:
            exc.read(64 << 10)
            return int(exc.code)
        finally:
            exc.close()
    except URLError as exc:
        raise Failure(f"request error {url}: {exc.reason}") from exc


def _build_opener(ca_file: str | None, trust_leaf: bool):
    ctx = _tls_context(ca_file, trust_leaf)
    target = (os.environ.get("MAGICTEST_TARGET_ADDRESS") or "").strip()
    if not target:
        return build_opener(_NoRedirect(), HTTPSHandler(context=ctx))

    class _TargetHTTPSHandler(HTTPSHandler):
        def https_open(self, req):
            class _SniConn(http.client.HTTPSConnection):
                def __init__(self, host, port=None, **kwargs):
                    parsed = urlsplit(f"https://{host}")
                    self._sni_host = parsed.hostname or host
                    super().__init__(target, port=parsed.port or port or 443, **kwargs)

                def connect(self):
                    sock = self._create_connection((self.host, self.port), self.timeout, self.source_address)
                    self.sock = self._context.wrap_socket(sock, server_hostname=self._sni_host)

            return self.do_open(_SniConn, req, context=ctx)

    return build_opener(_NoRedirect(), _TargetHTTPSHandler())


def load_service_routes(args: argparse.Namespace) -> dict[str, dict[str, str]]:
    if args.service_map:
        raw_doc = strict_json(Path(args.service_map).expanduser().read_text(encoding="utf-8"))
        require(isinstance(raw_doc, dict) and isinstance(raw_doc.get("services"), dict), "service-map requires object field 'services'")
        routes: dict[str, dict[str, str]] = {}
        for svc_key, cfg in raw_doc["services"].items():
            require(svc_key in VMI_SERVICE_BY_KEY, f"unknown serviceKey in service-map: {svc_key!r}")
            require(isinstance(cfg, dict), f"service-map entry {svc_key!r} must be an object")
            svc_url = str(cfg.get("serviceUrl") or "").strip().rstrip("/")
            require(bool(svc_url), f"service-map entry {svc_key!r} missing serviceUrl")
            key_file = cfg.get("apiKeyFile")
            require(bool(key_file), f"service-map entry {svc_key!r} missing apiKeyFile")
            api_key = _read_secret(str(key_file), f"VMI_SIM_API_KEY_{svc_key.upper()}", f"ApiKey ({svc_key})")
            routes[svc_key] = {"serviceUrl": svc_url, "apiKey": api_key}
        require(bool(routes), "service-map services object is empty")
        return routes

    base_svc_url = str(args.service_url or "").strip().rstrip("/")
    require(bool(base_svc_url), "missing --service-url or --service-map")
    api_key = _read_secret(args.api_key_file, "VMI_SIM_API_KEY", "ApiKey")
    return {
        svc["key"]: {"serviceUrl": base_svc_url, "apiKey": api_key}
        for svc in VMI_DOMAIN_SERVICES
    }


def _resolve_value(val: Any, id_map: dict[str, int | str]) -> Any:
    if isinstance(val, dict) and set(val) == {"$ref"}:
        ref = val["$ref"]
        require(ref in id_map, f"unresolved reference {ref}")
        return {"id": int(id_map[ref])}
    if isinstance(val, list):
        return [_resolve_value(item, id_map) for item in val]
    return val


def _gateway_headers(api_key: str, *, with_body: bool = False) -> dict[str, str]:
    headers = {"Authorization": f"ApiKey {api_key}", "Accept": "application/json"}
    if with_body:
        headers["Content-Type"] = "application/json"
    return headers


def _save_journal(
    journal_path: Path,
    run_id: str,
    identity: dict[str, Any] | None,
    id_map: dict[str, Any],
    version_map: dict[str, int],
    completed_actions: list[str],
) -> None:
    journal_path.write_text(
        dumps({
            "planRunId": run_id,
            "identity": identity,
            "ids": id_map,
            "versions": version_map,
            "actions": completed_actions,
        }) + "\n",
        encoding="utf-8",
    )


def inspect_remote(
    routes: dict[str, dict[str, str]],
    opener,
    selected_services: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    selected = selected_services or tuple(
        svc["key"] for svc in VMI_DOMAIN_SERVICES if svc["key"] in routes
    )
    require(bool(selected), "no services selected for inspection")
    counts: dict[str, int] = {}
    service_counts: dict[str, int] = {}
    query_qs = urlencode({"_pageNum": 1, "_pageSize": 100, "_needTotal": "true", "_viewType": "detail"})
    for svc_key in selected:
        require(svc_key in routes, f"missing service route for {svc_key!r}")
        route = routes[svc_key]
        headers = _gateway_headers(route["apiKey"])
        svc_total = 0
        for name in VMI_SERVICE_BY_KEY[svc_key]["entities"]:
            _, doc = _http_json(opener, "GET", f"{route['serviceUrl']}/{name}_query?{query_qs}", headers)
            pagination = doc.get("pagination") or {}
            cnt = int(pagination.get("total") if pagination.get("total") is not None else len(doc.get("values") or []))
            counts[name] = cnt
            svc_total += cnt
        service_counts[svc_key] = svc_total
    total = sum(counts.values())
    return {
        "empty": total == 0,
        "totalRecords": total,
        "selectedServices": list(selected),
        "counts": counts,
        "serviceCounts": service_counts,
    }


def _normalize_action_identity(scope: dict[str, Any]) -> dict[str, Any]:
    return {
        "namespace": str(scope["namespace"]),
        "deploymentId": str(scope["deploymentId"]),
        "installationId": str(int(scope["installationId"])),
        "runtimeApplicationUuid": str(scope["runtimeApplicationUuid"]),
        "generation": int(scope["generation"]),
        "executionEpoch": int(scope["executionEpoch"]),
        "artifactDigest": str(scope["artifactDigest"]),
    }


def _execute_create_batch(
    steps: list[dict[str, Any]],
    routes: dict[str, dict[str, str]],
    opener,
    plan_run_id: str,
    id_map: dict[str, Any],
    version_map: dict[str, int],
    completed_actions: list[str],
    identity_holder: dict[str, Any],
    journal_path: Path,
    used_services: set[str],
) -> None:
    for step in steps:
        k = step["key"]
        svc_key = step.get("serviceKey") or service_key_for_entity(step["entity"])
        used_services.add(svc_key)
        if k in id_map:
            continue
        route = routes[svc_key]
        gw_headers = _gateway_headers(route["apiKey"], with_body=True)
        payload = {fname: _resolve_value(fval, id_map) for fname, fval in step["values"].items()}
        _, resp = _http_json(opener, "POST", f"{route['serviceUrl']}/{step['entity']}_create", gw_headers, payload)
        val = resp.get("value") or {}
        require("id" in val, f"create {k} missing id: {resp}")
        receipt = resp.get("receipt") or {}
        scope = receipt.get("identity") if isinstance(receipt, dict) else None
        if isinstance(scope, dict) and scope.get("deploymentId"):
            norm_scope = _normalize_action_identity(scope)
            if identity_holder["identity"] is None:
                identity_holder["identity"] = norm_scope
            else:
                require(identity_holder["identity"] == norm_scope, f"execution identity changed on {k}")
        id_map[k] = val["id"]
        version_map[k] = int(val.get("version") or (receipt.get("version") if isinstance(receipt, dict) else None) or 1)
        _save_journal(journal_path, plan_run_id, identity_holder["identity"], id_map, version_map, completed_actions)


def run_plan(args: argparse.Namespace) -> dict[str, Any]:
    require(args.plan is not None, "--plan is required for run")
    require(bool(str(args.action_url or "").strip()), "--action-url is required for run")
    plan = strict_json(Path(args.plan).read_text(encoding="utf-8"))
    routes = load_service_routes(args)
    pre_creates = list(plan.get("creates") or [])
    post_creates = list(plan.get("postActionCreates") or [])
    for step in (*pre_creates, *post_creates):
        svc_key = step.get("serviceKey") or service_key_for_entity(step["entity"])
        require(svc_key in routes, f"missing service route for {svc_key!r}")

    action_token = _read_secret(args.action_token_file, "VMI_SIM_ACTION_TOKEN", "ActionToken")
    state_dir = Path(args.state_dir).expanduser().resolve()
    state_dir.mkdir(parents=True, exist_ok=True)
    journal_path = state_dir / "journal.json"
    opener = _build_opener(args.ca_file, args.trust_leaf)

    id_map: dict[str, Any] = {}
    version_map: dict[str, int] = {}
    completed_actions: list[str] = []
    identity_holder: dict[str, Any] = {"identity": None}
    if journal_path.is_file():
        journal = strict_json(journal_path.read_text(encoding="utf-8"))
        id_map = dict(journal.get("ids") or {})
        version_map = dict(journal.get("versions") or {})
        completed_actions = list(journal.get("actions") or [])
        raw_identity = journal.get("identity")
        if isinstance(raw_identity, dict) and raw_identity.get("deploymentId"):
            identity_holder["identity"] = _normalize_action_identity(raw_identity)
        else:
            identity_holder["identity"] = raw_identity

    used_services: set[str] = set()
    _execute_create_batch(
        pre_creates, routes, opener, plan["runId"], id_map, version_map, completed_actions, identity_holder, journal_path, used_services
    )

    act_headers = {"Authorization": f"Bearer {action_token}", "Content-Type": "application/json", "Accept": "application/json"}
    actions = list(plan.get("actions") or [])
    if actions:
        scope = identity_holder["identity"]
        require(isinstance(scope, dict) and bool(scope.get("deploymentId")), "missing execution identity from Gateway create receipt")
        norm_scope = _normalize_action_identity(scope)
        sep = "&" if "?" in args.action_url else "?"
        action_url = f"{args.action_url}{sep}{urlencode({'application': 'vmi', 'deploymentId': norm_scope['deploymentId']})}"
        for idx, act in enumerate(actions):
            sig = f"{idx}:{act['targetKey']}:{act['action']}"
            if sig in completed_actions:
                continue
            target_id = id_map[act["targetKey"]]
            expected_version = version_map[act["targetKey"]]
            op_id = secrets.token_hex(16)
            body = {
                "apiVersion": "magic.entity-action/v1",
                "operationId": op_id,
                "identity": norm_scope,
                "entity": f"/{PKG_PREFIX}/{act['entity']}",
                "action": act["action"],
                "id": str(target_id),
                "expectedVersion": str(expected_version),
                "fields": [{"name": k, "value": v} for k, v in sorted((act.get("payload") or {}).items())],
            }
            _, resp = _http_json(opener, "POST", action_url, act_headers, body)
            receipt = resp.get("value") if isinstance(resp, dict) else None
            require(
                isinstance(receipt, dict)
                and receipt.get("apiVersion") == "magic.entity-action/v1"
                and receipt.get("operationId") == op_id
                and receipt.get("action") == act["action"]
                and str(receipt.get("id") or "") == str(target_id),
                f"invalid action receipt on {sig}: {resp}",
            )
            next_ver = int(receipt["version"])
            require(next_ver == expected_version + 1, f"unexpected version on {sig}: {receipt}")
            version_map[act["targetKey"]] = next_ver
            completed_actions.append(sig)
            _save_journal(journal_path, plan["runId"], norm_scope, id_map, version_map, completed_actions)

    _execute_create_batch(
        post_creates, routes, opener, plan["runId"], id_map, version_map, completed_actions, identity_holder, journal_path, used_services
    )
    return {
        "created": len(id_map),
        "actions": len(completed_actions),
        "runId": plan["runId"],
        "servicesUsed": sorted(used_services),
    }


def _check_domain_isolation(routes: dict[str, dict[str, str]], opener) -> dict[str, Any]:
    if "vmi_warehouse_service" in routes and "vmi_order_service" in routes:
        probe_svc, foreign_svc = "vmi_warehouse_service", "vmi_order_service"
    else:
        ordered = [svc["key"] for svc in VMI_DOMAIN_SERVICES if svc["key"] in routes]
        probe_svc, foreign_svc = ordered[0], ordered[1]
    foreign_entity = VMI_SERVICE_BY_KEY[foreign_svc]["entities"][0]
    probe_route = routes[probe_svc]
    probe_url = f"{probe_route['serviceUrl']}/{foreign_entity}_query?_pageNum=1&_pageSize=1"
    status_code = _http_status(
        opener,
        "GET",
        probe_url,
        _gateway_headers(probe_route["apiKey"]),
    )
    require(
        status_code in (400, 403, 404),
        f"domain isolation failed: service {probe_svc!r} returned HTTP {status_code} for foreign entity {foreign_entity!r}",
    )
    return {
        "probedService": probe_svc,
        "foreignEntity": foreign_entity,
        "status": status_code,
        "blocked": True,
    }


def verify_plan(args: argparse.Namespace) -> dict[str, Any]:
    routes = load_service_routes(args)
    selected = resolve_domain_filter(args.domains)
    for svc_key in selected:
        require(svc_key in routes, f"missing service route for selected domain service {svc_key!r}")

    opener = _build_opener(args.ca_file, args.trust_leaf)
    check_alerts = "vmi_inventory_service" in selected
    expected_alerts = 0
    if args.plan is not None:
        plan = strict_json(Path(args.plan).read_text(encoding="utf-8"))
        expected_alerts = int(plan["expectedAlertCount"])
    elif check_alerts:
        raise Failure("--plan is required when verifying vmi_inventory_service")

    deadline = time.monotonic() + max(1, int(args.wait_seconds))
    while True:
        inspected = inspect_remote(routes, opener, selected_services=selected)
        if not check_alerts:
            break
        alerts = inspected["counts"].get("inventoryAlert", 0)
        if alerts >= expected_alerts or time.monotonic() >= deadline:
            require(
                alerts >= expected_alerts,
                f"expected at least {expected_alerts} derived inventoryAlert records, got {inspected}",
            )
            break
        time.sleep(2)

    if args.service_map and not args.skip_isolation_check and len(routes) >= 2:
        inspected["isolationCheck"] = _check_domain_isolation(routes, opener)
    return inspected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", default="seed", choices=["seed", "replay"])
    parser.add_argument("--anchor-utc", default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--plan", type=Path, default=None)
    parser.add_argument("--service-url", default="")
    parser.add_argument("--service-map", type=Path, default=None, help="JSON mapping domain service keys to serviceUrl and apiKeyFile")
    parser.add_argument("--domains", default=None, help="Optional comma-separated domain names or service keys for on-demand inspect/verify")
    parser.add_argument("--skip-isolation-check", action="store_true", help="Skip cross-domain Gateway isolation negative check during verify")
    parser.add_argument("--action-url", default="")
    parser.add_argument("--state-dir", type=Path, default=Path("."))
    parser.add_argument("--api-key-file", default=None)
    parser.add_argument("--action-token-file", default=None)
    parser.add_argument("--ca-file", default=None)
    parser.add_argument("--trust-leaf", action="store_true")
    parser.add_argument("--wait-seconds", type=int, default=60)
    parser.add_argument("command", choices=["plan", "inspect", "run", "verify"])
    args = parser.parse_args(argv)

    if args.command == "plan":
        doc = simulation_plan(args.anchor_utc, args.run_id, mode=args.mode)
        out = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(out, encoding="utf-8")
        print(out)
        return 0
    if args.command == "inspect":
        routes = load_service_routes(args)
        selected = resolve_domain_filter(args.domains)
        doc = inspect_remote(routes, _build_opener(args.ca_file, args.trust_leaf), selected_services=selected)
        print(json.dumps(doc, ensure_ascii=False, indent=2))
        return 0
    if args.command == "run":
        doc = run_plan(args)
        print(json.dumps(doc, ensure_ascii=False, indent=2))
        return 0
    doc = verify_plan(args)
    print(json.dumps(doc, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
