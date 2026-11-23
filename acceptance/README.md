# 平台回归材料

当前权威范围为 71 类功能、245 条必需用例、14 个主场景；两个模拟应用单列。默认常规回归只执行正向功能与非破坏性验证（`standard`，184 个分项、覆盖 66 类功能；包含正向流程、页面交互以及不产生破坏性的权限隔离、分页聚合、输入/引用保护拒绝），破坏性与故障异常测试（`abnormal`，28 个分项、覆盖 24 类功能；包含故障注入、中断、损坏制品、并发冲突、重启/恢复与全局策略冲突）与条件专项（`special`，75 个分项、覆盖 36 类功能）分别单列验证与统计。全量共 162 条仅 `standard`、8 条仅 `abnormal`、33 条仅 `special`、22 条 `standard+special` 混合、20 条 `abnormal+special` 混合，合计 245 条用例 / 287 个执行分项；混合分项不新增用例 ID。需独立嵌套 Docker 守护进程的 11 项非正常业务/部署运维与故障注入用例（`F057-005`、`F059-002`、`F060-001/002`、`F061-001/002/003`、`F062-001/003`、`F063-001/002`）已归入 `special` 待办项（前置条件 `isolated-daemon`），后续使用单独环境验证，不作为正常功能验收执行。

- [全量功能回归说明](~/dataspace/magicPlatform/docs/technical/platform-functional-regression.md)：目录用途、分组边界、脚本交付、统一执行及结果要求。
- [唯一用例目录](~/codespace/magicTest/acceptance/platform-catalog.json)：用例目的、owner、完整步骤/预期、`execution` 分组及具名前置条件的权威数据。
- [可读用例表](~/codespace/magicTest/acceptance/platform-case-ledger.md)：由目录自动生成，不手工修改。
- [异常测试清单](~/codespace/magicTest/acceptance/platform-abnormal-cases.md)：由同一目录生成，集中列出权限拒绝、边界约束和冲突恢复等异常验证范围，可通过 `platform-abnormal` 独立执行，默认不混入正向常规回归。
- [条件专项清单](~/codespace/magicTest/acceptance/platform-special-cases.md)：由同一目录生成，列出外部集成、真实期限和故障窗口，以及混合用例保留的自动回归范围、准备/退出及恢复要求。
- [卸载中断恢复 Runbook](~/codespace/magicTest/acceptance/uninstall-interruption-runbook.md)：`F033-003` 独立卸载中断恢复夹具与检核边界。
- [脚本复用要求](~/codespace/magicTest/acceptance/test-reuse-map.md)、[资产清单](~/codespace/magicTest/regression/inventory.json)和[只读导航](~/codespace/magicTest/regression_inventory.py)：定位候选入口、已复核范围与缺口，不代表脚本已就绪或业务已通过。
- [报告与生成工具](~/codespace/magicTest/tools/platform_acceptance.py)：默认按 `standard` 判定，`abnormal` 与 `special` 各自单列，`catalogCoverage` 始终保留完整目录覆盖情况；通过正向常规不能冒充异常或整体通过。
- [设备管理应用验证套件](~/codespace/magicTest/applications/device-management/README.md)与[棋牌室预订应用验证套件](~/codespace/magicTest/applications/chess-room-booking/README.md)：各自维护应用夹具、模拟器与 Live E2E 脚本，权威定义位于[模型应用资产目录](~/dataspace/magicPlatform/apps/models/README.md)。

全部步骤、预期及必要性只维护在目录中，表格和专项清单不得复制成另一套手工正文。外部条件不足不阻断常规完成；常规脚本、夹具或正式合同缺失仍须受阻，不得通过移组或静默跳过取得通过。

执行证据默认按本地运行目录保存在 `~/codespace/magicTest/reports/`（受 `.gitignore` 忽略、统一不提交 Git），原报告对应原目录摘要及候选，不继承为当前范围通过数。每次执行全量回归（未指定 `--cases` 子集且非 `--dry-run`）前，`~/codespace/magicTest/regression/run_standard.py` 会自动清理 `reports/`（或显式指定的本地 `runs/`）下之前的历史数据（同轮全量 `abnormal` 保留同轮 `standard/`）；如需手动切换/初始化空轮次目录，使用 `python3 -B ~/codespace/magicTest/tools/start_acceptance_round.py YYYY-MM-DD-name`。文件归档清理只操作本地文件，不操作服务数据、凭据或 owner 回执。
