# 固定样例与独立对账

## 分版本使用

新增 [threshold-v3](~/codespace/magicTest/applications/device-management/fixtures/threshold-v3/README.md)：3 区域、1 分类、1 设备、10 条测量，预期自动生成 9 条告警；零预置告警。用于新版上下限脚本和可靠效果验证，当前仅离线计算通过。

后文 fixed-v1／A/B/C 数据及 oracle 保留原定义；current-window-v1 属于现场 V2 模拟器。三种数据场景的时间窗口、记录数及告警来源不得混用；新版阈值样例不覆盖原全功能验收。

状态：模型正式包已归档至[模型应用资产](~/dataspace/magicPlatform/apps/models/device-management/README.md)；下列A/B/C固定样例保留原字节供离线回归。离线逻辑数据、正式GET导出适配器及回读规范化/ID映射工具已有源码和离线回归；受控样例初始化、实际全量owner导出、未知恢复、精确清理和带数据Live仍待验证。所有记录为虚构验收样例，不是实际设备或人员历史。见[当前就绪清单](~/dataspace/magicPlatform/apps/models/device-management/design/package-readiness.md)。

## 产物

- [固定数据清单](~/codespace/magicTest/applications/device-management/fixtures/fixed-v1/manifest.json)：绑定 A/B/C 原始 JSON 大小和 SHA-256；不含凭据、环境身份或数据库主键。
- [A 完整样例](~/codespace/magicTest/applications/device-management/fixtures/fixed-v1/A.json)：7 区域、3 分类、24 设备、492 监测、12 告警、8 维护，维护涉及 6 台设备。
- [B 同租户变体](~/codespace/magicTest/applications/device-management/fixtures/fixed-v1/B.json)：相同区域和分类，DEV-001～003；无监测、告警和维护。
- [C 跨租户变体](~/codespace/magicTest/applications/device-management/fixtures/fixed-v1/C.json)：相同区域和分类，仅 DEV-001；无监测、告警和维护。
- [生成器](~/codespace/magicTest/applications/device-management/tooling/generate_fixture.py)、[独立 oracle](~/codespace/magicTest/applications/device-management/tooling/fixture_oracle.py)、[离线回归](~/codespace/magicTest/applications/device-management/tooling/test_fixture_tools.py)。oracle 不导入生成器或生产聚合实现。

运行数据始终在模型 ZIP 外。引用是逻辑业务编号，必须由受控初始化 owner 按精确租户/实例解析为正式 ID；不能直接把本文 JSON 当作 Base 写入 DTO。alarm 的历史主体字段有意省略，由获准初始化 owner 注入真实核验身份，不伪造人员审计。通信事实、历史状态和 append-only 记录需要独立初始化能力，普通 CRUD 不能因此获得越权写入能力。

## 离线使用

```bash
python3 -I ~/codespace/magicTest/applications/device-management/tooling/test_fixture_tools.py
python3 -I ~/codespace/magicTest/applications/device-management/tooling/fixture_oracle.py \
  --bundle ~/codespace/magicTest/applications/device-management/fixtures/fixed-v1

# 仅生成到不存在的新目录；拒绝覆盖已存在目录。
python3 -I ~/codespace/magicTest/applications/device-management/tooling/generate_fixture.py \
  --output /tmp/device-fixture-new-run
```

固定锚点为 `2026-10-14T12:00:00Z`，窗口左闭右开。oracle 校验记录数、自然键、树和引用、精确数值公式、null/0、有效样本数、告警/维护时间、区域后代组合、详情空态、排序与在线率。基准在线率为 18/23=78.26%，未解决告警 9；DEV-001 温度均值为 22.15，按一位小数 half-up 显示 22.2。结果与源码验证不表示真实数据库已写入或服务端聚合已通过。

生成器只写新目录，不连接网络、不初始化实例、不修改系统时钟、不生成发布版本或重签旧 ZIP。完整受控导入、实际 owner 回读证据与精确清理工具仍待实现，MP08 保持阻塞；禁止用这个离线工具替代正常 owner 接口或绕过只读/动作规则。
## 正式 GET 导出适配器

[导出器](~/codespace/magicTest/applications/device-management/tooling/export_readback.py) 接入正式 Apps 元数据/实体 filter GET；[离线回归](~/codespace/magicTest/applications/device-management/tooling/test_export_readback.py) 只使用传输替身，不访问实际服务。应用 key 是 `device-management`，实体前缀是 `deviceManagement`，二者不可混用。

需先取得独立核验的 target，并部署配套 Apps 精确安装读取围栏和 Base 结果保精度/null 修复。target 不从远端快照自动生成。token 仅经指定环境变量读取，不作为命令参数/URL 或输出记录；HTTPS 校验证书，可显式给私有 CA，禁止跳过证书校验和重定向。每次 GET 带完整七字段期望身份，读取前后由 Apps 核对正式绑定及当前请求授权，不因此增加数据权限。原先 vendor 重建拒绝属于历史批次：用户已刷新依赖，Base 结果精度/null 公共文件与 Runner vendor 已核对一致，Runner 全仓 test/vet/build 通过；这不等于实际 Apps 导出已执行。

```bash
python3 -I ~/codespace/magicTest/applications/device-management/tooling/test_export_readback.py
# 以下是获准环境中的只读执行方式，本批未执行；凭据须由操作者安全设置环境变量。
python3 -I ~/codespace/magicTest/applications/device-management/tooling/export_readback.py \
  --origin https://authorized.example \
  --token-env MAGIC_DEVICE_READ_TOKEN \
  --target /tmp/device-expected-target.json \
  --fixture ~/codespace/magicTest/applications/device-management/fixtures/fixed-v1/A.json \
  --output /tmp/device-owner-new-run
```

六实体分别要求单页最多 1000、total 等于记录数、无剩余页/游标，按唯一主键稳定升序；超限拒绝，不把当前页当全量。连续读取两套完整数据，前/中/后元数据与期望身份均不变才输出 owner-readback.json；失败不重试、不输出部分目录。随后用上一节规范化器和独立 oracle 对账。该双读是静止样例观察协议，不是原子数据库快照，不排除 ABA；现场需明确获准静止窗口。当前未实际调用 Apps，不能据离线替身宣布 ID 映射、初始化、清理或 Live 已通过。


## A/B/C 离线执行预检

[预检器](~/codespace/magicTest/applications/device-management/tooling/preflight_validation.py) 组合固定清单原始大小/摘要、独立 oracle、目标身份合同和可选三实例回读；[离线测试](~/codespace/magicTest/applications/device-management/tooling/test_preflight_validation.py) 使用明确构造的回读，不访问服务。无网络能力、不加载 token、不写输出文件、不初始化或清理实例；报告写标准输出且不打印目标身份或业务行。

目标集合为 `magic.device-validation-targets/v1`，顶层只允许 `schemaVersion` 和 `targets`；`targets` 必须恰含 A/B/C，每项使用下节 `magic.device-readback-target/v1` 合同，由操作者独立核验。预检要求 A/B 同租户、C 异租户，三者 deployment/runtime 身份均不同且固定候选 artifactDigest 相同，fixtureDigest 分别匹配固定清单。它只验证目标合同，不从快照生成身份，也不能证明真实服务端隔离。

```bash
python3 -I ~/codespace/magicTest/applications/device-management/tooling/test_preflight_validation.py
# 仅离线预检已准备的目标，默认不读取任何服务。
python3 -I ~/codespace/magicTest/applications/device-management/tooling/preflight_validation.py \
  --bundle ~/codespace/magicTest/applications/device-management/fixtures/fixed-v1 \
  --targets /tmp/device-independent-targets.json
# 可选：同时提供 --snapshot-a /tmp/A-owner.json \
#   --snapshot-b /tmp/B-owner.json --snapshot-c /tmp/C-owner.json
```

提供快照时必须三个一起提供；逐项核对独立目标、规范化和精确 ID/引用，再运行独立 oracle 并比较全部逻辑字段及 JSON 值类型（不把布尔值当成 0/1），不以统计相等掩盖描述或名称变化。通过只标为 `offline-observation-verified`；不能证明快照来源、写入授权或原子数据库快照。输出始终 `liveReady:false`，初始化、清理和 Live 始终为 `not-run`，并列出尚需证据。只检查目标时也不把构造的空记录当作空库证明。没有改固定数据、候选 ZIP 或历史摘要。

## 实例回读规范化与映射合同

[规范化器](~/codespace/magicTest/applications/device-management/tooling/normalize_readback.py) 只处理已经由正式 owner 导出的完整 JSON 快照，不自行登录或连接服务。[回归](~/codespace/magicTest/applications/device-management/tooling/test_readback_tools.py) 构造离线输入覆盖 A/B/C、超安全整数主键、引用、完整性和跨实例拒绝；这些输入不是实际导出证据。

输入分别为独立核验的期望目标与 owner 回读。目标 `magic.device-readback-target/v1` 包含 `variant`、固定样例 `fixtureDigest` 和完整 `binding`：namespace、32 位规范 deploymentId、十进制字符串 installationId、runtimeApplicationUuid、generation、executionEpoch、artifactDigest。回读 `magic.device-owner-readback/v1` 必须逐项匹配该目标；同时包含 dataVersion、definitionVersion、synthetic、anchor 及六类 entities。每个实体封装 pkgKey、complete、total、rows，拒绝未完成分页或数量不符。目标不能从待核对快照自身自动推断，否则失去串实例检测意义。

记录主键及引用主键保留十进制字符串，大整数 JSON number、bool、重复 ID/业务编号/自然键、外来引用、缺失 null 和未声明字段均拒绝。时间只接收有时区 RFC3339 并归一到 UTC，不猜测毫秒/秒；高于微秒精度明确拒绝而非截断。告警主体和资源版本等观察元数据保留于映射，不投影成逻辑样例字段，也不制造主体。

```bash
python3 -I ~/codespace/magicTest/applications/device-management/tooling/test_readback_tools.py
python3 -I ~/codespace/magicTest/applications/device-management/tooling/normalize_readback.py \
  --snapshot /tmp/device-owner-export.json \
  --target /tmp/device-expected-target.json \
  --output /tmp/device-normalized-new-run
python3 -I ~/codespace/magicTest/applications/device-management/tooling/fixture_oracle.py \
  --document /tmp/device-normalized-new-run/logical.json
```

输出新目录中的 logical.json 与 id-mapping.json；拒绝覆盖既有目录。映射绑定快照/目标原始摘要、实例身份、自然键及观察 ID，但明确标记为只读观察，不是初始化账本、删除权限或清理证明。原始文件及目标含环境信息，交付时由操作者按隐私范围保管；不得放入模型 ZIP。`complete:true` 和摘要只能证明文件合同，不能自行证明导出来源可信或真实服务已返回全部记录。正式导出适配器源码见下一节；实际 owner 导出证据、受控初始化操作与精确清理仍缺，不将工具通过记成 Live 通过。

[返回设备管理验证套件](~/codespace/magicTest/applications/device-management/README.md)
