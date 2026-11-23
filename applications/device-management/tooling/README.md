# 设备管理工具入口

## 本批离线维护与 V3 计划工具

[entity_declaration.py](~/codespace/magicTest/applications/device-management/tooling/entity_declaration.py)从独立读取的最新实体与应用生成完整条件版本修改请求，保留 indexes、uniqueConstraints、字段、绑定、写规则及开放声明；遇到未知视图字段、流程字段 patch 或身份不符即拒绝。prepare 后审查输出，通过正式作者 API 保存，再用同文件 verify 函数全量核对独立回读。工具自身不调用 API，不负责自动重试；原现场索引仍待恢复。

```bash
python3 ~/codespace/magicTest/applications/device-management/tooling/entity_declaration.py \
  --entity /tmp/entity-current.json --application /tmp/application-current.json \
  --patch /tmp/entity-patch.json --output /tmp/entity-save-request-new.json
```

恢复单个历史索引时用 `--restore-index` 替代 `--patch`，输入仅含 name／fields。该模式把索引合并到最新集合，保留新增索引、完整绑定和唯一约束；同名但字段不同则拒绝，不能覆盖他人的后续设计。原采样索引为 `{"name":"ix_dm_telemetry_sampled","fields":["sampledAt"]}`。保存后仍须独立回读并执行全量 verify。

[threshold_plan.py](~/codespace/magicTest/applications/device-management/tooling/threshold_plan.py)仅离线生成新隔离部署的 V3 计划：指定精确 deployment ID、全新12位大写十六进制 run ID 和 UTC anchor，生成5条基础档案和10条监测，预期9条派生告警；不创建 alarm 或 maintenance。输出使用独立 schemaVersion 和未就绪状态，不接受旧模拟器执行，不证明真实自动触发／持久化／恢复；本批没有在线 V3 run。

```bash
python3 ~/codespace/magicTest/applications/device-management/tooling/threshold_plan.py \
  --deployment-id 0123456789abcdef0123456789abcdef \
  --run-id ABCDEF012345 --anchor 2026-10-25T08:00:00Z \
  --output /tmp/threshold-offline-plan-new.json
```

示例部署 ID 仅作离线演示。未来在线执行须先配套正式授权／执行／恢复消费者，再提供有界等待和原意图回查；禁止用旧 backfill／collect 直接灌告警冒充派生。39项 Python 工具回归通过，源码与本地验证见本批证据（历史临时归档已清理）。

## V3 阈值候选离线核对

[validate_threshold_candidate.py](~/codespace/magicTest/applications/device-management/tooling/validate_threshold_candidate.py)执行引用／版本／服务声明检查，通过 Go overlay 加载 [Go 核对程序](~/codespace/magicTest/applications/device-management/tooling/validate_threshold_candidate.go.txt)，使用 Runner 默认 vendor 模式下的正式 Build／Parse、Base 脚本 Validate／Debug 和 ORM PostgreSQL builder。全程不连接服务或数据库，不写模型包，不在共享仓库创建或删除临时测试文件；overlay与临时输入在命令退出后清理。

```bash
python3 -I ~/codespace/magicTest/applications/device-management/tooling/validate_threshold_candidate.py
```

默认打印报告；可用 --report 指向尚不存在的包外文件保存新一轮证据，不覆盖已有报告。修改定义后需重新核对并另存新报告；报告区分纯计算、DDL生成、真实持久化及Live，可靠效果运行时仍为not-implemented。

[新样例](~/codespace/magicTest/applications/device-management/fixtures/threshold-v3/README.md)不是旧模拟器输入。下面的模拟器命令继续属于 **V2**；V3 telemetry-only 在线执行与效果回读仍待实现，禁止直接用于新版服务。

已扩展为同时验证[未激活效果绑定设计](~/dataspace/magicPlatform/apps/models/device-management/definition/threshold-effect.binding.design.json)：真实脚本→通用冻结计划→九个待执行创建候选，检查完整编号、来源追溯、精确大整数引用、重算一致性及发布门禁。新增输出 frozenEffectPlan／mappedCandidateCreates／effectDigests；它们不表示业务持久化、幂等或恢复通过。绑定设计不进入当前正式包，数据库与Live仍为not-run，同时包含 `frozenEffectSnapshot` 严格往返验证。

本目录维护包外模拟器、固定样例工具及配套测试；工具和运行数据不加入应用模型ZIP。

## 日常模拟接入

使用[模拟器操作指南](~/codespace/magicTest/applications/device-management/tooling/simulator-usage.md)。认证只需本机文件中的ApiKey，默认服务为 `https://panel.local.vpc/api/v1/gateway/services/device_management_service`。

| 入口 | 用途 |
| --- | --- |
| [simulator.py](~/codespace/magicTest/applications/device-management/tooling/simulator.py) | 唯一命令入口：计划、探测、档案录入、历史填充、采集、条件更新和回读 |
| [操作指南](~/codespace/magicTest/applications/device-management/tooling/simulator-usage.md) | 继续当前运行、新建运行、参数、产物及故障恢复 |
| [分类改名样例](~/codespace/magicTest/applications/device-management/tooling/examples/category-rename.json) / [名称恢复样例](~/codespace/magicTest/applications/device-management/tooling/examples/category-restore.json) | 复制到自己的运行目录后，用update提交；包含修改前置值 |
| [实现目录](~/codespace/magicTest/applications/device-management/tooling/simulator/) | 配置、HTTP客户端、冻结计划、SQLite日志与执行器 |
| [设计](~/dataspace/magicPlatform/apps/models/device-management/design/simulator-design.md) / [验收要求](~/dataspace/magicPlatform/apps/models/device-management/design/data-integration-acceptance.md) | 行为合同、已知缺口与完整应用验收范围 |

凭据和所有运行产物保存在本机独立状态目录，不要复制进本仓库。

## 固定历史样例与独立核对

以下工具用于[固定A/B/C样例](~/codespace/magicTest/applications/device-management/fixtures/README.md)，其固定时间、连接状态和告警处置预期不能直接套用到当前模拟器生成的数据。

| 工具 | 用途与边界 |
| --- | --- |
| [generate_fixture.py](~/codespace/magicTest/applications/device-management/tooling/generate_fixture.py) | 离线生成固定样例；不写入Live |
| [fixture_oracle.py](~/codespace/magicTest/applications/device-management/tooling/fixture_oracle.py) | 固定样例的独立期望计算 |
| [export_readback.py](~/codespace/magicTest/applications/device-management/tooling/export_readback.py) | 独立Apps只读导出，使用其自身Bearer授权；不是模拟器的启动步骤或认证要求 |
| [normalize_readback.py](~/codespace/magicTest/applications/device-management/tooling/normalize_readback.py) | 固定样例回读归一化 |
| [preflight_validation.py](~/codespace/magicTest/applications/device-management/tooling/preflight_validation.py) | 固定样例离线预检；不证明现场完整就绪 |

## 开发验证与历史工具

仅模拟器测试：

```bash
python3 -I ~/codespace/magicTest/applications/device-management/tooling/test_simulator.py
```

全部工具回归（使用本地临时 HTTPS 证书，不使用生产密钥；实际数量以运行结果为准）：

```bash
python3 -I -m unittest discover \
  -s ~/codespace/magicTest/applications/device-management/tooling -p 'test_*.py'
```

测试文件与工具相邻保留，便于现有导入和独立运行。[export_candidate.py](~/codespace/magicTest/applications/device-management/tooling/export_candidate.py)及[Go模板](~/codespace/magicTest/applications/device-management/tooling/export_candidate_test.go.txt)属于历史阻塞候选研究，仍含旧拒绝断言，不作为当前正式包刷新命令。正式模型包的来源和更新流程见[模型包说明](~/dataspace/magicPlatform/apps/models/device-management/package/README.md)。

[返回设备管理](~/codespace/magicTest/applications/device-management/README.md)
