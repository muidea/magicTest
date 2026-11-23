#!/usr/bin/env python3
"""将已由正式 owner 回读的精确实例快照转换为逻辑样例及 ID 映射；不连接网络或写实例。"""
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


ENTITIES = ("location", "category", "device", "telemetry", "alarm", "maintenance")
RELATIONS = {"location": {"parent": "location"}, "device": {"category": "category", "location": "location"},
             "telemetry": {"device": "device"}, "alarm": {"device": "device"}, "maintenance": {"device": "device"}}
TIMES = {"device": {"lastSeenAt"}, "telemetry": {"sampledAt"},
         "alarm": {"occurredAt", "acknowledgedAt", "resolvedAt"}, "maintenance": {"performedAt"}}
COLUMNS = {
    "location": {"code", "name", "parent", "kind", "sortOrder"},
    "category": {"code", "name", "sortOrder"},
    "device": {"code", "name", "category", "location", "lifecycleStatus", "connectionStatus", "lastSeenAt",
               "manufacturer", "model", "serialNumber", "commissionedOn", "description"},
    "telemetry": {"device", "sampledAt", "temperature", "vibration", "loadPercent"},
    "alarm": {"code", "device", "title", "severity", "status", "occurredAt", "acknowledgedAt", "resolvedAt", "resolution", "description"},
    "maintenance": {"code", "device", "kind", "performedAt", "technician", "summary", "cost", "notes"},
}
BINDING_FIELDS = {"namespace", "deploymentId", "installationId", "runtimeApplicationUuid", "generation", "executionEpoch", "artifactDigest"}
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def strict_json(payload):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "JSON 含重复字段")
            result[key] = value
        return result
    def constant(_):
        raise ValueError("JSON 含非有限数值")
    return json.loads(payload, object_pairs_hook=pairs, parse_constant=constant)


def digest(payload):
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def identity(value):
    # 数字 ID 仅接受 JSON/浏览器安全范围；大 snowflake 必须保留原十进制字符串。
    require(type(value) is str or type(value) is int and 0 < value <= 9007199254740991, "主键必须是精确十进制字符串或安全整数")
    text = str(value)
    require(re.fullmatch(r"[1-9][0-9]{0,18}", text) is not None and int(text) <= 9223372036854775807, "主键无效")
    return text


def instant(value):
    if value is None:
        return None
    require(isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})", value) is not None,
            "回读时间必须是有时区的 RFC3339 瞬间，不能猜测数值时间单位")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    return parsed.isoformat(timespec="microseconds" if parsed.microsecond else "seconds").replace("+00:00", "Z")


def normalize(snapshot, expected):
    require(set(expected) == {"schemaVersion", "binding", "variant", "fixtureDigest"} and expected["schemaVersion"] == "magic.device-readback-target/v1", "期望目标合同无效")
    binding = expected["binding"]
    require(isinstance(binding, dict) and set(binding) == BINDING_FIELDS, "期望实例绑定不完整")
    require(all(isinstance(binding[key], str) and binding[key].strip() == binding[key] and binding[key] for key in ("namespace", "runtimeApplicationUuid")), "空间或运行应用身份无效")
    require(re.fullmatch(r"[0-9a-f]{32}", binding["deploymentId"]) is not None, "deployment ID 必须是完整规范值")
    require(identity(binding["installationId"]) == binding["installationId"], "installation ID 必须为字符串")
    require(all(type(binding[key]) is int and binding[key] > 0 for key in ("generation", "executionEpoch")), "运行代际无效")
    require(isinstance(binding["artifactDigest"], str) and DIGEST.fullmatch(binding["artifactDigest"]), "制品摘要无效")
    require(expected["variant"] in ("A", "B", "C") and isinstance(expected["fixtureDigest"], str) and DIGEST.fullmatch(expected["fixtureDigest"]), "样例变体或摘要无效")
    require(set(snapshot) == {"schemaVersion", "binding", "variant", "fixtureDigest", "dataVersion", "definitionVersion", "synthetic", "anchor", "entities"}, "回读快照字段无效")
    require(snapshot["schemaVersion"] == "magic.device-owner-readback/v1" and snapshot["binding"] == binding, "回读实例、安装或代际与明确期望目标不匹配")
    require(snapshot["variant"] == expected["variant"] and snapshot["fixtureDigest"] == expected["fixtureDigest"], "回读样例身份不匹配")
    require(snapshot["synthetic"] is True and snapshot["dataVersion"] == "device-management/v0.1" and snapshot["definitionVersion"] == "device-management/v0.2", "回读不是指定虚构样例")
    require(instant(snapshot["anchor"]) == "2026-10-14T12:00:00Z", "回读统计锚点不匹配")
    require(isinstance(snapshot["entities"], dict) and set(snapshot["entities"]) == set(ENTITIES), "回读实体集合不完整")
    ids, actual = {}, {}
    for name in ENTITIES:
        entity = snapshot["entities"][name]
        require(set(entity) == {"pkgKey", "complete", "total", "rows"} and entity["pkgKey"] == "/deviceManagement/" + name, "回读实体 key 错误")
        rows = entity["rows"]
        require(entity["complete"] is True and type(entity["total"]) is int and isinstance(rows, list) and entity["total"] == len(rows) and len(rows) <= 1000, "回读分页未完成或超限，不能当作完整数据")
        ids[name], actual[name] = {}, {}
        for row in rows:
            require(isinstance(row, dict), "回读记录必须为对象")
            key = identity(row.get("id"))
            require(key not in actual[name], "同一实体回读主键重复")
            actual[name][key] = row
            if name != "telemetry":
                code = row.get("code")
                require(isinstance(code, str) and code and code not in ids[name].values(), "回读业务编号为空或重复")
                ids[name][key] = code
    logical, mapping = {}, {}
    for name in ENTITIES:
        logical[name], mapping[name] = [], []
        natural = set()
        for key, row in actual[name].items():
            audit = {"id", "version", "createTime", "updateTime"} | ({"acknowledgedBy", "resolvedBy"} if name == "alarm" else set())
            require(COLUMNS[name] <= row.keys() and row.keys() <= COLUMNS[name] | audit, "回读字段缺失或出现未声明字段: " + name)
            value = {field: row[field] for field in COLUMNS[name]}
            for field, target in RELATIONS.get(name, {}).items():
                reference = value[field]
                if reference is None:
                    require(name == "location" and field == "parent", "必需引用为空")
                    continue
                require(isinstance(reference, dict) and "id" in reference and reference.keys() <= {"id", "code", "name"}, "引用必须是 owner 回读的主键对象")
                target_id = identity(reference["id"])
                require(target_id in ids[target], "引用目标不在同一快照中")
                target_code = ids[target][target_id]
                require("code" not in reference or reference["code"] == target_code, "引用主键与业务编号冲突")
                value[field] = target_code
            for field in TIMES.get(name, set()):
                value[field] = instant(value[field])
            natural_key = [value["device"], value["sampledAt"]] if name == "telemetry" else [value["code"]]
            token = json.dumps(natural_key, ensure_ascii=False, separators=(",", ":"))
            require(token not in natural, "回读自然键重复")
            natural.add(token)
            logical[name].append(value)
            observed = {field: row[field] for field in sorted(row.keys() - COLUMNS[name] - {"id"})}
            mapping[name].append({"id": key, "naturalKey": natural_key, "observedMetadata": observed})
        logical[name].sort(key=lambda row: json.dumps([row["device"], row["sampledAt"]] if name == "telemetry" else [row["code"]], ensure_ascii=False))
        mapping[name].sort(key=lambda row: row["naturalKey"])
    document = {"schemaVersion": "magic.device-fixture/v1", "dataVersion": snapshot["dataVersion"], "definitionVersion": snapshot["definitionVersion"],
                "variant": snapshot["variant"], "synthetic": True, "anchor": instant(snapshot["anchor"]), "entities": logical}
    report = {"schemaVersion": "magic.device-id-mapping/v1", "binding": dict(binding), "variant": snapshot["variant"],
              "fixtureDigest": snapshot["fixtureDigest"], "entities": mapping, "authority": "observed-owner-readback-not-cleanup-authorization"}
    return document, report


def write_result(snapshot_path, target_path, output):
    snapshot_bytes, target_bytes = snapshot_path.read_bytes(), target_path.read_bytes()
    require(len(snapshot_bytes) <= 8 << 20 and len(target_bytes) <= 16 << 10, "输入超出预算")
    document, mapping = normalize(strict_json(snapshot_bytes), strict_json(target_bytes))
    mapping["snapshotDigest"], mapping["targetDigest"] = digest(snapshot_bytes), digest(target_bytes)
    output.mkdir(parents=True, exist_ok=False)
    for name, value in (("logical.json", document), ("id-mapping.json", mapping)):
        with (output / name).open("x", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
    return document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="必须不存在的新输出目录")
    args = parser.parse_args()
    write_result(args.snapshot, args.target, args.output)
    print("已输出逻辑回读与 ID 映射；须另行运行独立 oracle，不代表初始化或 Live 成功。")


if __name__ == "__main__":
    main()
