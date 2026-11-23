#!/usr/bin/env python3
"""经获准 Apps GET 接口回读固定样例；不初始化、不清理、不登录，不推断期望实例身份。"""
import argparse
import base64
import importlib.util
import json
import os
import ssl
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener


ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("normalize_readback", ROOT / "normalize_readback.py")
assert spec is not None and spec.loader is not None
normalizer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(normalizer)
require = normalizer.require


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("回读禁止重定向，不能将凭据发送给其它地址")


class AppsReader:
    def __init__(self, origin, token, ca_file=None):
        parts = urlsplit(origin)
        require(parts.scheme == "https" and parts.hostname and not parts.username and not parts.password
                and parts.path in ("", "/") and not parts.query and not parts.fragment, "Apps origin 必须为无路径和凭据的 HTTPS 地址")
        require(isinstance(token, str) and token and token.strip() == token and "\r" not in token and "\n" not in token, "需要独立环境变量中的有效 Bearer token")
        self.origin, self.token = origin.rstrip("/"), token
        self.opener = build_opener(NoRedirect(), HTTPSHandler(context=ssl.create_default_context(cafile=ca_file)))

    def get(self, path, query, binding):
        encoded = base64.urlsafe_b64encode(json.dumps(binding, separators=(",", ":")).encode()).decode().rstrip("=")
        request = Request(self.origin + path + "?" + urlencode(query), headers={
            "Authorization": "Bearer " + self.token, "X-Mp-Namespace": binding["namespace"],
            "X-Magic-Expected-Installation": encoded, "Accept": "application/json"}, method="GET")
        try:
            with self.opener.open(request, timeout=20) as response:
                require(response.status == 200, "Apps 回读 HTTP 状态无效")
                require(response.headers.get_content_type() == "application/json", "Apps 回读不是 JSON")
                payload = response.read((8 << 20) + 1)
        except (HTTPError, URLError, TimeoutError):
            raise ValueError("Apps 回读失败；未重试，也未输出响应或凭据") from None
        require(len(payload) <= 8 << 20, "Apps 回读超过字节预算")
        result = normalizer.strict_json(payload)
        require(isinstance(result, dict) and result.get("error") is None, "Apps owner 返回业务错误")
        return result


def export(reader, target, fixture_bytes):
    fixture = normalizer.strict_json(fixture_bytes)
    require(normalizer.digest(fixture_bytes) == target.get("fixtureDigest"), "固定样例原始摘要不匹配")
    # 先用空记录验证目标合同，不能从远端响应推断或补齐目标。
    snapshot = {"schemaVersion": "magic.device-owner-readback/v1", "binding": target["binding"], "variant": target["variant"],
                "fixtureDigest": target["fixtureDigest"], "dataVersion": fixture["dataVersion"], "definitionVersion": fixture["definitionVersion"],
                "synthetic": fixture["synthetic"], "anchor": fixture["anchor"], "entities": {
                    name: {"pkgKey": "/deviceManagement/" + name, "complete": True, "total": 0, "rows": []} for name in normalizer.ENTITIES}}
    normalizer.normalize(snapshot, target)
    require(fixture.get("schemaVersion") == "magic.device-fixture/v1" and fixture.get("variant") == target["variant"], "固定样例合同或变体不符")
    binding = target["binding"]
    selector = {"deploymentId": binding["deploymentId"]}

    def metadata():
        value = reader.get("/api/v1/apps/application/runtime/query/device-management", selector, binding).get("value")
        require(isinstance(value, dict) and value.get("readIdentity") == binding, "Apps 未确认完整期望安装身份")
        require(isinstance(value.get("application"), dict) and value["application"].get("key") == "device-management", "Apps 返回了其它应用")
        catalog = {}
        for item in value.get("entities", []):
            require(isinstance(item, dict) and isinstance(item.get("entity"), dict), "Apps 实体目录无效")
            entity = item["entity"]
            key = entity.get("pkgPath", "") + "/" + entity.get("name", "")
            require(key not in catalog, "Apps 实体目录重复")
            catalog[key] = item
        require(set(catalog) == {"/deviceManagement/" + name for name in normalizer.ENTITIES}, "Apps 实体目录不等于完整固定候选")
        for item in catalog.values():
            require(item["entity"].get("primaryKey") == "id" and item.get("capabilities", {}).get("query") is True, "实体主键或查询授权不满足回读合同")
        return value

    before = metadata()

    def sweep():
        entities = {}
        for name in normalizer.ENTITIES:
            key = "/deviceManagement/" + name
            query = dict(selector, application="device-management", entity=key, _pageSize="1000", _pageNum="1",
                         _needTotal="true", _sortFilter=json.dumps({"fieldName": "id", "ascFlag": True}, separators=(",", ":")))
            result = reader.get("/api/v1/apps/entity/value/filter/", query, binding)
            page, rows = result.get("pagination"), result.get("values")
            require(isinstance(page, dict) and isinstance(rows, list), "Apps 缺少明确分页或记录集合")
            require(type(page.get("total")) is int and page["total"] == len(rows) and len(rows) <= 1000
                    and page.get("pageNum") == 1 and page.get("pageSize") == 1000
                    and not page.get("hasMore") and not page.get("nextCursor") and not page.get("after")
                    and page.get("mode", "") == "", "Apps 分页不完整或超限；不将当前页当作全量")
            previous = 0
            for row in rows:
                require(isinstance(row, dict), "Apps 记录无效")
                # Python 保留原始整数 token；仍拒绝 SDK 已输出的不安全浮点或指数 ID。
                value = row.get("id")
                require(type(value) in (int, str), "Apps 主键不精确")
                primary = normalizer.identity(str(value))
                require(int(primary) > previous, "Apps 未按唯一主键稳定升序返回")
                previous = int(primary)
                row["id"] = primary
                for field, destination in normalizer.RELATIONS.get(name, {}).items():
                    reference = row.get(field)
                    if reference is not None:
                        require(isinstance(reference, dict) and type(reference.get("id")) in (int, str), "Apps 引用主键不精确")
                        allowed = normalizer.COLUMNS[destination] | {"id", "version", "createTime", "updateTime"}
                        require(reference.keys() <= allowed, "Apps 引用包含未声明字段")
                        projected = {key: reference[key] for key in ("code", "name") if key in reference}
                        projected["id"] = normalizer.identity(str(reference["id"]))
                        row[field] = projected
            entities[name] = {"pkgKey": key, "complete": True, "total": len(rows), "rows": rows}
        return entities

    snapshot["entities"] = sweep()
    require(metadata() == before, "首次回读期间安装或实体目录变化")
    require(sweep() == snapshot["entities"], "两次完整回读内容变化；不输出混合观察")
    require(metadata() == before, "最终回读身份或实体目录变化")
    normalizer.normalize(snapshot, target)
    payload = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
    require(len(payload) <= 8 << 20, "完整 owner 快照超过输出预算")
    return snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--token-env", default="MAGIC_DEVICE_READ_TOKEN")
    parser.add_argument("--ca-file", type=Path)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--fixture", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="必须不存在的新目录")
    args = parser.parse_args()
    require(not args.output.exists(), "拒绝覆盖既有输出目录")
    with args.target.open("rb") as stream:
        target_bytes = stream.read((16 << 10) + 1)
    with args.fixture.open("rb") as stream:
        fixture_bytes = stream.read((8 << 20) + 1)
    require(len(target_bytes) <= 16 << 10 and len(fixture_bytes) <= 8 << 20, "输入超过预算")
    reader = AppsReader(args.origin, os.environ.get(args.token_env), args.ca_file)
    snapshot = export(reader, normalizer.strict_json(target_bytes), fixture_bytes)
    args.output.mkdir(parents=True, exist_ok=False)
    with (args.output / "owner-readback.json").open("x", encoding="utf-8") as stream:
        json.dump(snapshot, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print("已保存两次一致的 owner 回读；这不是原子数据库快照、初始化或清理证明，请另行规范化及独立对账。")


if __name__ == "__main__":
    main()
