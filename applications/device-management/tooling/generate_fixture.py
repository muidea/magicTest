#!/usr/bin/env python3
"""生成固定的虚构设备样例；只写新目录，不连接实例或生成数据库主键。"""
import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


ANCHOR = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)


def instant(value):
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def generate(variant):
    locations = [
        {"code": "SITE-01", "name": "园区", "parent": None, "kind": "site", "sortOrder": 0},
        {"code": "WS-A", "name": "A车间", "parent": "SITE-01", "kind": "workshop", "sortOrder": 0},
        {"code": "WS-B", "name": "B车间", "parent": "SITE-01", "kind": "workshop", "sortOrder": 1},
    ]
    for index, code in enumerate(("LINE-A1", "LINE-A2", "LINE-B1", "LINE-B2")):
        locations.append({"code": code, "name": code, "parent": "WS-" + code[5], "kind": "line", "sortOrder": index % 2})
    categories = [{"code": code, "name": name, "sortOrder": index} for index, (code, name) in enumerate((("CAT-PUMP", "水泵"), ("CAT-MOTOR", "电机"), ("CAT-FAN", "风机")))]
    devices, telemetry, alarms, maintenance = [], [], [], []
    limit = {"A": 24, "B": 3, "C": 1}[variant]
    for number in range(1, limit + 1):
        category = categories[(number - 1) % 3]
        name = category["name"] + f" {number:03}"
        if number == 3:
            name = "二号车间循环冷却系统备用变频驱动电机（长名称展示与省略提示验证设备）"
        if number == 4:
            name = "风机 <b>仅显示文本</b> & 测试"
        if variant != "A":
            name += "（" + {"B": "B实例", "C": "C租户"}[variant] + "）"
        state = "running" if number <= 16 else "standby" if number <= 20 else "maintenance" if number <= 23 else "retired"
        connection = "online" if number <= 18 else "offline" if number <= 23 else "unknown"
        devices.append({"code": f"DEV-{number:03}", "name": name, "category": category["code"],
                        "location": ("LINE-A1", "LINE-A2", "LINE-B1", "LINE-B2")[(number - 1) // 6],
                        "lifecycleStatus": state, "connectionStatus": connection,
                        "lastSeenAt": instant(ANCHOR - (timedelta(minutes=1) if connection == "online" else timedelta(hours=13))) if connection != "unknown" else None,
                        "manufacturer": "虚构样例制造商", "model": "DEMO-" + category["code"],
                        "serialNumber": None if number == 1 else f"DEMO-SN-{number:03}",
                        "commissionedOn": "2024-02-29", "description": "" if number == 2 else "虚构验收样例，不代表真实设备"})
    if variant == "A":
        start = ANCHOR - timedelta(days=1)
        for number in range(1, 24):
            for hour in range(24 if number <= 18 else 12):
                telemetry.append({"device": f"DEV-{number:03}", "sampledAt": instant(start + timedelta(hours=hour)),
                                  "temperature": None if (number, hour) == (5, 7) else (200 + 10 * number + hour) / 10,
                                  "vibration": (100 + 10 * (number % 5) + hour % 3) / 100,
                                  "loadPercent": 0 if (number, hour) == (2, 0) else (3 * number + 2 * hour) % 101})
        alarm_devices = (1, 2, 2, 3, 7, 8, 12, 16, 19, 21, 22, 23)
        statuses = ("open", "acknowledged", "open", "open", "acknowledged", "resolved", "open", "open", "open", "acknowledged", "resolved", "resolved")
        for number, (device, status) in enumerate(zip(alarm_devices, statuses), 1):
            occurred = start + timedelta(hours=number)
            category = categories[(device - 1) % 3]
            alarms.append({"code": f"ALM-{number:03}", "device": f"DEV-{device:03}",
                           "title": f"{category['name']} DEV-{device:03} ALM-{number:03}",
                           "severity": "critical" if number <= 2 else "major" if number <= 6 else "minor", "status": status,
                           "occurredAt": instant(occurred), "acknowledgedAt": instant(occurred + timedelta(minutes=5)) if status != "open" else None,
                           "resolvedAt": instant(occurred + timedelta(minutes=10)) if status == "resolved" else None,
                           "resolution": "虚构处理说明：已完成样例故障复核" if status == "resolved" else None,
                           "description": "虚构告警；主体由获准初始化 owner 注入，不伪造真实人员"})
        for number, (device, kind) in enumerate(zip((1, 1, 2, 3, 7, 7, 21, 23), ("inspection", "service", "inspection", "repair", "service", "inspection", "repair", "service")), 1):
            maintenance.append({"code": f"MNT-{number:03}", "device": f"DEV-{device:03}", "kind": kind,
                                "performedAt": instant(ANCHOR - timedelta(days=9 - number)), "technician": "模拟维护员",
                                "summary": f"虚构维护记录 {number:03}", "cost": 0 if number == 1 else None if number == 2 else number * 100,
                                "notes": "仅用于独立私有实例验收"})
    return {"location": locations, "category": categories, "device": devices,
            "telemetry": telemetry, "alarm": alarms, "maintenance": maintenance}


def write_bundle(output):
    # mkdir(exist_ok=False) 防止覆盖历史证据、旧映射或未知文件。
    output.mkdir(parents=True, exist_ok=False)
    files = {}
    for variant in ("A", "B", "C"):
        payload = (json.dumps({"schemaVersion": "magic.device-fixture/v1", "dataVersion": "device-management/v0.1",
                               "definitionVersion": "device-management/v0.2", "variant": variant,
                               "synthetic": True, "anchor": instant(ANCHOR), "entities": generate(variant)},
                              ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
        name = f"{variant}.json"
        (output / name).write_bytes(payload)
        files[name] = {"size": len(payload), "digest": "sha256:" + hashlib.sha256(payload).hexdigest()}
    manifest = {"schemaVersion": "magic.device-fixture-manifest/v1", "synthetic": True, "files": files,
                "initialization": "not-run", "live": "not-run"}
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="必须不存在的新输出目录")
    args = parser.parse_args()
    manifest = write_bundle(args.output)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
