# 设备管理模拟器操作指南

## 最新 V3 闭环模式（2026-11-22 收口）

入口为 [simulator.py](~/codespace/magicTest/applications/device-management/tooling/simulator.py)，严格通过 Gateway 开放能力与独立订阅 ApiKey 运行，**不直接创建 `alarm`（`alarm_create` 保持关闭），不经普通 `device_update` 改写 `lifecycleStatus`**，通过 `device_update` 上送 `connectionStatus` 与 `lastSeenAt` 设备心跳：

- **`live-stream-v1`（默认实时工况流）**：使用 `seed` 初始化 7 区域、3 分类、12 台初始 `standby` 设备（含 8 在线 / 2 离线 / 2 未知心跳）与 4 条初始维护记录；使用 `backfill` / `live-stream --cycles N` 生成近 24 小时 192 条基线监测及后续 4 场景轮替实时脉冲（平稳运行、`78.5°C / 94% / 5.1 mm/s` 渐变越界触发后端派生告警、`DEV-005` 失联断线制造 `connectNulls: false` 断点、重连恢复在线）。
- **`replay-v3`（固定基线回归模式）**：使用 `--scenario replay-v3` 与 `replay` 子命令在固定 UTC 窗口 `[2026-10-24T00:00:00Z, 2026-10-24T04:00:00Z)` 执行 10 条门槛样本，自动核对幂等重报不重复入库、同键改值拒绝（`HTTP 409` / 冲突码）以及后端派生 9 条告警（`major 3 / critical 2 / minor 4`）。
- **`current-window-v1` / `fixed-history-v1`（扩展 24 设备对比场景）**：保留 24 设备 / 492 条测量的扩展规模基线，同步移除已废弃的直接写 `alarm` 与改写 `lifecycleStatus` 请求，改为通过合法心跳 `device_update` 保持 18/24 在线基准。

```bash
# 1. 固定基线回归（replay-v3）
python3 -I ~/codespace/magicTest/applications/device-management/tooling/simulator.py init \
  --scenario replay-v3 --api-key-file <key> --run-dir <replay-dir>
python3 -I ~/codespace/magicTest/applications/device-management/tooling/simulator.py replay \
  --config <replay-dir>/config.json

# 2. 实时工况接入（live-stream-v1）
python3 -I ~/codespace/magicTest/applications/device-management/tooling/simulator.py init \
  --scenario live-stream-v1 --api-key-file <key> --run-dir <live-dir>
python3 -I ~/codespace/magicTest/applications/device-management/tooling/simulator.py seed \
  --config <live-dir>/config.json
python3 -I ~/codespace/magicTest/applications/device-management/tooling/simulator.py live-stream \
  --config <live-dir>/config.json --cycles 4
```

## 历史运行参考（2026-10-24 V2）

原清空重部署后的运行配置与凭据说明保留于本机运行状态。入口为 [simulator.py](~/codespace/magicTest/applications/device-management/tooling/simulator.py)，使用Python 3标准库及支持partial-chain验证的本机OpenSSL。认证仅需订阅ApiKey，无需管理员账号、Cookie、安装ID或管理合同快照。默认服务为 `https://panel.local.vpc/api/v1/gateway/services/device_management_service`。

## 1. 继续现有运行

当前工作机已完成初始化，直接使用原配置继续采集，无需重新init或重新录入档案：

```bash
python3 -I ~/codespace/magicTest/applications/device-management/tooling/simulator.py collect \
  --config ~/dataspace/device-management-simulator/runs/2026-10-24-reconfigured/config.json \
  --cycles 3

python3 -I ~/codespace/magicTest/applications/device-management/tooling/simulator.py verify \
  --config ~/dataspace/device-management-simulator/runs/2026-10-24-reconfigured/config.json
```

collect会写入业务数据，`--cycles 3` 表示本次新增3轮，每轮18条监测；轮间默认等待60秒，命令有限运行后退出。verify只读取业务数据并更新本机核对产物，应在采集停止后执行。两条命令顺序运行，同一运行目录不支持并发进程。

当前运行标识为 `20261024AC01`。2026-10-24验收时已完成1轮，记录为区域7、分类3、设备24、监测510（492历史＋18实时）、告警12、维护8。后续采集会增加数量，最新结果以本机summary及verify为准。查看[当前实例页面](https://panel.local.vpc/workbench/apps/device-management?source=portal&deploymentId=5d64c2f6fd236dba8b2a93338073f8cf)。

## 2. 新建独立运行

只有需要另一组独立业务数据时才新建运行。每个新run都会创建独立编码的24台设备等记录；页面可能汇总多个run，不能继续套用单run数量作为全应用总数。

准备有效订阅ApiKey：保存到本人拥有的普通文件，设置0600权限，不使用软链接，文件只包含密钥。当前工作机文件为 `~/dataspace/device-management-simulator/secrets/device-management-reconfigured-20261024.key`。不要将密钥直接写入命令行、配置内容、模型包或仓库。

```bash
python3 -I ~/codespace/magicTest/applications/device-management/tooling/simulator.py init \
  --api-key-file ~/dataspace/device-management-simulator/secrets/device-management-reconfigured-20261024.key \
  --run-dir ~/dataspace/device-management-simulator/runs/demo-01

python3 -I ~/codespace/magicTest/applications/device-management/tooling/simulator.py plan \
  --config ~/dataspace/device-management-simulator/runs/demo-01/config.json

python3 -I ~/codespace/magicTest/applications/device-management/tooling/simulator.py probe \
  --config ~/dataspace/device-management/runs/demo-01/config.json

python3 -I ~/codespace/magicTest/applications/device-management/tooling/simulator.py run \
  --config ~/dataspace/device-management-simulator/runs/demo-01/config.json \
  --cycles 1
```

init不联网、不读取密钥内容，生成0700新目录及0600配置和冻结计划，拒绝覆盖已有目录。plan只展示离线计划。probe通过ApiKey查询六实体，核实基本可达性与查询授权，不执行业务写入，也不证明所有写能力均已授权。run依次录入档案、填充历史、执行指定轮数采集并完整回读。

默认信任证书为 `~/dataspace/magicPlatform/services/secret/tls/tls.crt`，作为明确的叶证书信任锚，仍校验证书和主机名。其他机器需在init时指定自己的 `--ca-file`；使用根CA时同时加 `--ca-is-root`。没有关闭证书校验的选项，也不跟随HTTP重定向。可用 `--service-url` 指定另一个符合Gateway路径合同的HTTPS服务。

## 3. 命令与数据范围

全部命令可通过 `--help` 查看参数。除init外均需要 `--config` 指向同一运行的配置。

| 命令 | 行为 | 业务写入 |
| --- | --- | --- |
| init | 生成配置和冻结计划，不读取密钥、不联网 | 无 |
| plan | 检查配置和计划一致性，输出计划 | 无 |
| probe | 查询六实体，建立/使用本机日志 | 无 |
| bootstrap | 7区域、3分类、24设备，另执行19次合法状态条件更新 | 有 |
| backfill | bootstrap完成后，填充492监测、12个open告警、8条维护事实 | 有 |
| collect | bootstrap完成后，按当前UTC时间采集；每轮18监测，每10轮新增1告警 | 有 |
| update | 条件更新本run区域、分类、设备的允许字段 | 有 |
| verify | 双轮完整查询，对比本run记录、引用、版本和重复/额外记录 | 无 |
| run | bootstrap → backfill → collect → verify | 有 |

需要分阶段执行时，依次使用bootstrap、backfill、collect、verify即可。程序没有delete、清表、部署或无限后台运行命令，生成数据保留用于页面查看。

bootstrap/backfill重复执行会跳过日志中已确认的操作；collect/run每次调用默认新增1轮，不是只回放原结果。已中断轮次会从原冻结意图继续。默认整个run最多60轮，轮数不足时命令失败，不会自动新建运行。

普通档案基准为running16、standby5、maintenance3；连接状态全部unknown，lastSeenAt为null，在线率0/24。告警初始均为open。在线/离线通信事实、退役以及告警确认/解决须由对应业务合同或授权页面动作产生，不能通过普通update伪造。固定样例A的18/23在线率、6/3/3告警状态不是当前模拟器的预期。

## 4. 档案条件更新与恢复

更新示例单独放在 `~/codespace/magicTest/applications/device-management/tooling/examples/`，先复制到自己的运行目录，再按需编辑。以下命令沿用当前运行：

```bash
cp ~/codespace/magicTest/applications/device-management/tooling/examples/category-rename.json \
  ~/dataspace/device-management-simulator/runs/2026-10-24-reconfigured/category-rename.json
cp ~/codespace/magicTest/applications/device-management/tooling/examples/category-restore.json \
  ~/dataspace/device-management-simulator/runs/2026-10-24-reconfigured/category-restore.json

python3 -I ~/codespace/magicTest/applications/device-management/tooling/simulator.py update \
  --config ~/dataspace/device-management-simulator/runs/2026-10-24-reconfigured/config.json \
  --entity category --logical-code CAT-PUMP \
  --changes ~/dataspace/device-management-simulator/runs/2026-10-24-reconfigured/category-rename.json

python3 -I ~/codespace/magicTest/applications/device-management/tooling/simulator.py update \
  --config ~/dataspace/device-management-simulator/runs/2026-10-24-reconfigured/config.json \
  --entity category --logical-code CAT-PUMP \
  --changes ~/dataspace/device-management-simulator/runs/2026-10-24-reconfigured/category-restore.json
```

JSON必须含 `fields` 和 `expectedFields`，两者字段名完全一致，分别表示新值和修改前置值。程序先get比对前置值，再携带当前版本发起条件更新。重置前run执行过这对意图；当前新run尚未执行。首次运行上例会真实改名及恢复，重复相同意图会跳过；新演示须使用尚未执行过的新名称及匹配前置值。意图按实体、逻辑编号、新值、前置值共同去重，改文件名不会创建新意图；恢复后也不会重新执行同一历史意图。

| 实体 | 允许字段 |
| --- | --- |
| location | name、description、sortOrder、parent |
| category | name、description、sortOrder |
| device | name、description、category、location、manufacturer、model、serialNumber、commissionedOn、lifecycleStatus |

lifecycleStatus仅允许standby/running/maintenance。关系值使用本run已确认的逻辑引用，例如 `{"$ref":"location:LINE-B1"}`，不接受任意外部ID；可空关系可按模型合同传null。拒绝code改写、通信事实改写、历史修改、普通retired写入和告警update。

## 5. 配置、时间与输出

init生成的config与plan必须成对保留。需要定制时，优先用init参数；如需编辑下表预算，应在首次probe或任何联网命令创建日志之前完成。已创建日志的配置摘要与计划绑定，不能通过改配置绕过预算或改变目标。

| 配置项/参数 | 默认与含义 |
| --- | --- |
| serviceUrl / --service-url | 上述device_management_service；Gateway裁决订阅和实际路由 |
| credentialFile / --api-key-file | 本机0600密钥文件的路径，配置不含密钥内容 |
| tls.caFile、tls.trustLeaf | 明确信任证书路径；默认true，根CA模式为false |
| run.runId / --run-id | 自动生成12位大写十六进制标识；业务code前缀为DM-{runId}- |
| run.scenario / --scenario | current-window-v1；可选fixed-history-v1 |
| run.anchor / --anchor | 当前UTC整点；current-window历史窗为此前24小时，左闭右开 |
| run.randomSeed | 20261023，确定性计划输入 |
| run.intervalSeconds、run.maxCycles | 默认60秒、总计60轮；可配置范围分别为1～3600、1～1440 |
| run.maxRequests、run.maxReadRows | 默认全run累计10000请求、每次扫描每实体最多20000行；可配置上限均为100000 |
| run.qps | 默认串行2QPS，最大10QPS |
| run.journalDirectory | 本run本机运行目录，不能与另一个run混用 |

固定传输限制为单请求30秒、响应最大4MiB。完整字段约束见[配置实现](~/codespace/magicTest/applications/device-management/tooling/simulator/config.py)。不要把其他run的配置、plan或journal拼接使用。

当前验收run历史T0为 `2026-10-24T11:00:00.000Z`，W0为 `[2026-10-23T11:00:00.000Z, 2026-10-24T11:00:00.000Z)`，上海时间对应前一日19:00至当日19:00。该窗随计划冻结，不随再次启动平移。页面“最近24小时”随查看时间移动，因此不能永远期待其显示492条历史记录；需要核对固定基准时，按W0筛选。后续collect使用实际UTC时间。fixed-history-v1固定T0为 `2026-10-14T12:00:00Z`，仅适合固定历史对照，不适合当前时间大屏。

标准实体datetime回读采用ORM明确约定的UTC文本 `YYYY-MM-DD HH:mm:ss.SSS`；模拟器只对六个已知时间字段转为RFC3339 UTC。配置/生成输入仍须显式时区，不根据本机时区猜测，依据见[UTC序列化](~/codespace/magicOrm/internal/utils/datetime.go)。

| 运行目录文件 | 作用 |
| --- | --- |
| config.json、plan.json | 配置与冻结操作计划，不含密钥内容 |
| journal.sqlite3、run.lock | 私有执行日志、已完成轮次、请求预算及单进程锁；恢复依据 |
| id-mapping.json | 本run逻辑编号到真实ID的映射 |
| summary.json | 操作状态和请求预算摘要 |
| readback.json、verification.json | verify成功时输出完整回读及核对结果 |

主键/版本以十进制字符串无损记录。verify双轮完整有界扫描六实体，检查本run记录、字段、引用、版本、同前缀额外记录及监测重复；两轮不一致或存在未决写入时失败。其他run数据不会删除。查看结果时先确认本次命令退出码为0；失败目录中的旧verification文件不能当成本次成功证明。

## 6. 中断和故障处理

中断后保留原目录，使用相同config重新执行原阶段，无需额外恢复开关。已确认意图不重发，未确认结果先回查；satisfied表示后置条件已满足，不证明原请求恰好执行一次。

| 情况 | 处理 |
| --- | --- |
| HTTPS/主机名失败 | 核对服务域名、受信证书和根CA/叶证书模式；不关闭TLS校验 |
| 认证/授权失败 | 核对本机ApiKey、订阅启用和服务授权；不改用管理员会话运行模拟器 |
| run directory already exists | 使用该目录原config继续；仅在确需独立数据集时选新目录 |
| another simulator process owns this run | 先停止/等待占锁进程；不并行写入或删除日志绕过 |
| offline plan differs / binding mismatch | 恢复原配置和原plan，核对是否误改预算、目标或路径 |
| 前置值、版本或回读差异 | 停止其他写入者，核对真实记录和原意图；不强制覆盖 |
| two complete readbacks differ | 停止采集及其他修改后重试verify |
| 轮数或请求预算耗尽 | 停止本run，保留产物；不要改旧日志预算。新独立运行会额外产生业务数据 |
| prepared/unknown写入 | 重跑原阶段协调原意图；若仍不能证明结果则停写并保留日志调查 |

监测create丢失响应且没有返回ID时，当前安装缺少已验收的组合唯一/原操作查询合同，程序会保留unknown并停止。不要删除journal或改runId来绕过：这会失去原请求的恢复依据，无法排除重复记录。已返回ID时先持久保存，再通过get恢复核对。

部署升级或修改服务绑定前先停止模拟器。Gateway负责执行目标与授权；ApiKey客户端不提供跨安装切换的原子围栏。没有确认兼容性及原记录归属前，不沿用旧journal向新环境补写。

## 7. 验证范围与材料

当前重配的录入、1轮采集、双轮完整Gateway回读和独立公式核对见本轮证据（历史临时归档已清理）。以下更新/恢复及测试描述属于重置前证据：模拟器验收（历史临时归档已清理）。27项本机工具回归覆盖恢复、互斥、未知结果停写、大整数及HTTPS边界，测试入口见[工具目录](~/codespace/magicTest/applications/device-management/tooling/README.md)。

后续带数据十页核对（历史临时归档已清理）与旧页面状态快照均保留于原资料仓 Git 历史。当前仍按最新实例与全功能回归口径验收。Gateway回读、独立Apps核对和浏览器验收分别记录，Apps/Bearer工具不属于模拟器认证前提。运行数据、密钥、日志、验收证据均不进入模型ZIP。

[返回工具入口](~/codespace/magicTest/applications/device-management/tooling/README.md) · [返回设备管理](~/codespace/magicTest/applications/device-management/README.md)
