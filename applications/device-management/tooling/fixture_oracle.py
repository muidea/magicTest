#!/usr/bin/env python3
"""独立核对逻辑样例或经 owner 回读并规范化的记录；不导入生成器或聚合实现。"""
import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path


T = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)
START = T - timedelta(hours=24)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def utc(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(parsed.tzinfo is not None and parsed.utcoffset() == timedelta(0), "时间必须显式为 UTC")
    return parsed


def indexed(rows, name):
    result = {row["code"]: row for row in rows}
    require(len(result) == len(rows), name + " 业务编号重复")
    require(all("id" not in row for row in rows), "逻辑数据不能携带环境主键")
    return result


def verify(document):
    require(document["schemaVersion"] == "magic.device-fixture/v1" and document["synthetic"] is True, "样例合同或虚构标记错误")
    require(document["dataVersion"] == "device-management/v0.1" and document["definitionVersion"] == "device-management/v0.2", "数据/定义版本不符")
    require(utc(document["anchor"]) == T, "统计锚点改变")
    variant = document["variant"]
    require(variant in ("A", "B", "C"), "未知隔离变体")
    entities = document["entities"]
    expected_counts = dict(zip(("location", "category", "device", "telemetry", "alarm", "maintenance"),
                               (7, 3, 24, 492, 12, 8) if variant == "A" else (7, 3, 3 if variant == "B" else 1, 0, 0, 0)))
    require(set(entities) == set(expected_counts), "实体集合不完整")
    require({key: len(rows) for key, rows in entities.items()} == expected_counts, "实体记录数不符")
    locations, categories, devices, alarms, maintenance = (indexed(entities[key], key) for key in ("location", "category", "device", "alarm", "maintenance"))
    expected_parents = {"SITE-01": None, "WS-A": "SITE-01", "WS-B": "SITE-01", "LINE-A1": "WS-A", "LINE-A2": "WS-A", "LINE-B1": "WS-B", "LINE-B2": "WS-B"}
    require({key: row["parent"] for key, row in locations.items()} == expected_parents, "区域树不符")
    require(set(categories) == {"CAT-PUMP", "CAT-MOTOR", "CAT-FAN"}, "分类集合不符")
    require(set(devices) == {f"DEV-{n:03}" for n in range(1, expected_counts["device"] + 1)}, "设备集合不符")
    for code, row in devices.items():
        number = int(code[4:])
        require(row["location"] == ("LINE-A1", "LINE-A2", "LINE-B1", "LINE-B2")[(number - 1) // 6], "设备区域不符")
        require(row["category"] == {1: "CAT-PUMP", 2: "CAT-MOTOR", 0: "CAT-FAN"}[number % 3], "设备分类不符")
        expected_state = "retired" if number == 24 else "maintenance" if number >= 21 else "standby" if number >= 17 else "running"
        connection = "unknown" if number == 24 else "offline" if number >= 19 else "online"
        require(row["lifecycleStatus"] == expected_state and row["connectionStatus"] == connection, "设备状态不符")
        if connection == "unknown":
            require(row["lastSeenAt"] is None, "未知设备时间应为空")
        else:
            require(utc(row["lastSeenAt"]) == T - (timedelta(hours=13) if connection == "offline" else timedelta(minutes=1)), "通信时间不符")
        if variant != "A":
            require(("B实例" if variant == "B" else "C租户") in row["name"], "隔离变体展示名缺失")
    require(devices["DEV-001"]["serialNumber"] is None, "serialNumber null 丢失")
    if "DEV-002" in devices:
        require(devices["DEV-002"]["description"] == "", "空字符串丢失")
    if variant != "A":
        return {"variant": variant, "counts": expected_counts, "onlineRate": "100.00", "unresolvedAlarms": 0}
    require(devices["DEV-004"]["name"] == "风机 <b>仅显示文本</b> & 测试", "字面 HTML 样例改变")
    require(len(devices["DEV-003"]["name"]) > 30, "长名称样例缺失")
    seen, per_device, buckets = set(), Counter(), {}
    for row in entities["telemetry"]:
        require(row["device"] in devices and row["device"] != "DEV-024", "监测设备引用错误")
        number = int(row["device"][4:])
        sampled = utc(row["sampledAt"])
        require(START <= sampled < T and (sampled - START).total_seconds() % 3600 == 0, "监测时间越界或不在桶起点")
        hour = int((sampled - START).total_seconds() / 3600)
        identity = (row["device"], sampled)
        require(identity not in seen, "监测自然键重复")
        seen.add(identity)
        require(number <= 18 or hour < 12, "离线缺口被填充")
        expected_temperature = None if number == 5 and hour == 7 else Decimal(20) + number + Decimal(hour) / 10
        actual = row["temperature"]
        require((actual is None and expected_temperature is None) or (actual is not None and expected_temperature is not None and Decimal(str(actual)) == expected_temperature), "温度公式或 null 错误")
        require(Decimal(str(row["vibration"])) == Decimal(1) + Decimal(number % 5) / 10 + Decimal(hour % 3) / 100, "振动公式错误")
        require(row["loadPercent"] == (0 if number == 2 and hour == 0 else (number * 3 + hour * 2) % 101), "负载公式或有效零值错误")
        per_device[row["device"]] += 1
        buckets.setdefault(hour, []).append(row)
    require(all(per_device[f"DEV-{n:03}"] == (24 if n <= 18 else 12) for n in range(1, 24)), "单设备监测数量错误")
    require([len(buckets[h]) for h in range(24)] == [23] * 12 + [18] * 12, "时间桶数量错误")
    def mean(rows):
        values = [Decimal(str(row["temperature"])) for row in rows if row["temperature"] is not None]
        return sum(values, Decimal(0)) / len(values), len(values)
    require(mean(buckets[0])[0] == Decimal("32") and mean(buckets[23])[0] == Decimal("31.8"), "全局桶温度均值错误")
    device_one = [row for row in entities["telemetry"] if row["device"] == "DEV-001"]
    average, _ = mean(device_one)
    require(average == Decimal("22.15") and average.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP) == Decimal("22.2"), "单设备平均值或舍入错误")
    require(mean([row for row in entities["telemetry"] if row["device"] == "DEV-005"])[1] == 23, "有效样本数量错误")
    expected_alarm_devices = (1, 2, 2, 3, 7, 8, 12, 16, 19, 21, 22, 23)
    expected_alarm_states = ("open", "acknowledged", "open", "open", "acknowledged", "resolved", "open", "open", "open", "acknowledged", "resolved", "resolved")
    require(set(alarms) == {f"ALM-{n:03}" for n in range(1, 13)}, "告警编号不符")
    for number, (device, status) in enumerate(zip(expected_alarm_devices, expected_alarm_states), 1):
        row = alarms[f"ALM-{number:03}"]
        occurred = START + timedelta(hours=number)
        require(row["device"] == f"DEV-{device:03}" and row["status"] == status, "告警引用或状态错误")
        require(row["severity"] == ("critical" if number <= 2 else "major" if number <= 6 else "minor"), "告警等级错误")
        require(utc(row["occurredAt"]) == occurred, "告警时间错误")
        require((row["acknowledgedAt"] is None if status == "open" else utc(row["acknowledgedAt"]) == occurred + timedelta(minutes=5)), "确认时间错误")
        require((row["resolvedAt"] is None and row["resolution"] is None) if status != "resolved" else utc(row["resolvedAt"]) == occurred + timedelta(minutes=10) and bool(row["resolution"].strip()), "解决字段错误")
    require(Counter(row["status"] for row in alarms.values()) == {"open": 6, "acknowledged": 3, "resolved": 3}, "告警统计错误")
    require(set(maintenance) == {f"MNT-{n:03}" for n in range(1, 9)}, "维护编号不符")
    for number, (device, kind) in enumerate(zip((1, 1, 2, 3, 7, 7, 21, 23), ("inspection", "service", "inspection", "repair", "service", "inspection", "repair", "service")), 1):
        row = maintenance[f"MNT-{number:03}"]
        require(row["device"] == f"DEV-{device:03}" and row["kind"] == kind and row["technician"] == "模拟维护员", "维护事实错误")
        require(utc(row["performedAt"]) == T - timedelta(days=9 - number), "维护时间错误")
        require(row["cost"] == (0 if number == 1 else None if number == 2 else 100 * number), "维护费用 null/0 错误")
    require(len({row["device"] for row in maintenance.values()}) == 6, "维护涉及设备数错误")
    require(Counter(row["lifecycleStatus"] for row in devices.values()) == {"running": 16, "standby": 4, "maintenance": 3, "retired": 1}, "设备状态统计错误")
    eligible = [row for row in devices.values() if row["lifecycleStatus"] != "retired"]
    online = sum(row["connectionStatus"] == "online" for row in eligible)
    rate = (Decimal(online) * 100 / len(eligible)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    require(rate == Decimal("78.26"), "在线率分母错误")
    unresolved = sum(row["status"] != "resolved" for row in alarms.values())
    require(unresolved == 9, "未解决告警数量错误")
    def descendants(code):
        result = {code}
        while True:
            expanded = result | {key for key, row in locations.items() if row["parent"] in result}
            if expanded == result:
                return result
            result = expanded
    region_counts = {key: sum(row["location"] in descendants(key) for row in devices.values()) for key in ("SITE-01", "WS-A", "LINE-B2")}
    require(region_counts == {"SITE-01": 24, "WS-A": 12, "LINE-B2": 6}, "区域后代查询错误")
    pump_a = sorted(code for code, row in devices.items() if row["location"] in descendants("WS-A") and row["category"] == "CAT-PUMP")
    require(pump_a == ["DEV-001", "DEV-004", "DEV-007", "DEV-010"], "区域分类组合错误")
    detail_counts = {key: [sum(row["device"] == key for row in entities[name]) for name in ("telemetry", "alarm", "maintenance")] for key in ("DEV-002", "DEV-024")}
    require(detail_counts == {"DEV-002": [24, 2, 1], "DEV-024": [0, 0, 0]}, "设备详情数量或空态错误")
    recent = [row["code"] for row in sorted(alarms.values(), key=lambda row: (utc(row["occurredAt"]), row["code"]), reverse=True)[:5]]
    require(recent == ["ALM-012", "ALM-011", "ALM-010", "ALM-009", "ALM-008"], "最近告警排序错误")
    return {"variant": variant, "counts": expected_counts, "onlineRate": str(rate), "unresolvedAlarms": unresolved,
            "temperatureMeanDEV001": str(average), "maintenanceDevices": 6,
            "regionDescendantCounts": region_counts, "workshopAPumps": pump_a,
            "detailCounts": detail_counts, "recentAlarms": recent,
            "hourlySamples": [len(buckets[h]) for h in range(24)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--bundle", type=Path)
    inputs.add_argument("--document", type=Path, help="核对规范化的单实例回读，不读取或猜测目标实例")
    args = parser.parse_args()
    if args.document is not None:
        result = verify(json.loads(args.document.read_bytes(), parse_float=Decimal))
        print(json.dumps(result, ensure_ascii=False))
        return
    manifest = json.loads((args.bundle / "manifest.json").read_text(encoding="utf-8"))
    require(manifest["schemaVersion"] == "magic.device-fixture-manifest/v1" and manifest["synthetic"] is True, "清单版本错误")
    require(set(manifest["files"]) == {"A.json", "B.json", "C.json"}, "清单成员错误")
    for name in ("A.json", "B.json", "C.json"):
        payload = (args.bundle / name).read_bytes()
        expected = manifest["files"][name]
        require(len(payload) == expected["size"] and "sha256:" + hashlib.sha256(payload).hexdigest() == expected["digest"], "成员完整性错误")
        result = verify(json.loads(payload, parse_float=Decimal))
        require(result["variant"] == name[0], "成员变体不符")
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
