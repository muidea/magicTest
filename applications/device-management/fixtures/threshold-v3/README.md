# 阈值自动告警验证样例

目标：业务版本 `0.2.0-dev.1`，V3 作者草稿已同步现场；本组测量与自动派生告警尚未在新实例灌入。该样例独立于 fixed-v1 和 current-window-v1，不能混用它们的记录数、状态或时间窗口。

[bootstrap.json](~/codespace/magicTest/applications/device-management/fixtures/threshold-v3/bootstrap.json)提供园区→车间→产线 3 个区域、1 个分类、1 台 standby 设备；关系按业务码解析为新实例的真实主键，文件不是可直接发送的 API 请求体。不固定 id／version，不写 connectionStatus／lastSeenAt／审计字段，不预置告警或维护。

[cases.json](~/codespace/magicTest/applications/device-management/fixtures/threshold-v3/cases.json)含冻结规则、10 条新测量和 10 个脚本边界／错误样例。Live 只能发送 liveSequence；scriptOnlyCases 包含非法输入，除相应负例外不得灌入业务表。采集请求只发送设备引用、sampledAt、三个指标，不传 rules、expected、deviceCode 或目标告警。

纯计算调试可直接使用当前脚本声明的example：在应用定义的“自定义脚本”打开“测量上下限告警判断”，展开“脚本调试”，点击“生成输入样例”后“运行验证”。默认输入取multi-high和完整三规则，期望major／critical／minor各一条候选；无需手动补rules。该路径不写业务记录，不能替代下述十条测量落库验收。现场验证及用户确认（历史临时归档已清理）已通过。

| 序号 | 场景 | 期望告警 |
| --- | --- | --- |
| 1～3 | 正常、上下限等值 | 0 |
| 4～5 | 温度低于／高于边界 | major 各 1 |
| 6 | 振动高于上限 | critical 1 |
| 7～8 | 负载低于／高于边界 | minor 各 1 |
| 9 | 三指标同时越界 | major／critical／minor 各 1 |
| 10 | 温度 null，振动 0，负载 0 | minor 1；null 跳过、零值参与 |

验收窗口固定为 `[2026-10-24T00:00:00.000Z, 2026-10-24T00:10:00.000Z)`。固定时间是样例事实，不修改系统时间或运行包默认窗口。十条样本可乱序提交，发生时间仍按各自 sampledAt，不按到达顺序。新的持续采集模式若平移到当前时间，必须在发出前冻结新的 T0、整个输入和对应 oracle，不能覆盖本样例或原运行日志。

完成后预期：location 3、category 1、device 1、telemetry 10、alarm 9、maintenance 0；告警 major 3／critical 2／minor 4，状态 open 9；设备在线率 0/1=0%，维护设备 0。最近告警仅显示 5 条不能当成告警总数。全部重放增量应为 0／0；同设备同时间改变指标必须冲突。acknowledge／resolve 后重试不得重置告警状态。所有期望仅在合法授权且可靠 effect 完成后核对。

当前仅可运行[离线验证器](~/codespace/magicTest/applications/device-management/tooling/validate_threshold_candidate.py)。旧模拟器仍会创建告警，禁止将旧 backfill／collect 用于本场景；新的 telemetry-only 模式及可靠 effect 消费者仍待实现。分组检查与恢复、授权、隔离条件见[自动告警设计](~/dataspace/magicPlatform/apps/models/device-management/design/threshold-alarms.md)。

[返回固定样例说明](~/codespace/magicTest/applications/device-management/fixtures/README.md)
