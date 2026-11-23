# 合成数据与录入依赖

按[模拟接入设计](~/dataspace/magicPlatform/apps/models/chess-room-booking/design/simulation-ingestion-and-display.md)生成：43条直接业务输入＋18条派生预期与9条采集来源。员工多引用与动作步骤已纳入当前计划。固定[当前模拟计划](~/codespace/magicTest/applications/chess-room-booking/fixtures/simulation-r5-plan.json)由最新 `simulation-plan` 生成，早期 R3 离线录入计划（executable=false）保留于原资料仓 Git 历史。

[baseline.json](~/codespace/magicTest/applications/chess-room-booking/fixtures/baseline.json)包含 52 条合成记录：2 商户、3 门店、6 房间、4 规则、1 营业例外、2 顾客档案、2 员工范围、9 订单、9 占用、9 订单事件、2 投诉和3 处理条目，已与当前 13 实体正式定义（排除采样来源 `bookingSample`）对齐。模拟主体均使用 fixture 前缀，无真实账号、联系方式或凭据。

时间锚点为 `2026-11-01T00:00:00Z`，固定样例不是当前实时营业数据。自动/人工确认、900 秒预占及样例政策只为分支展示，不是已批准的业务默认值；Q01—Q13 仍待定。含内部投诉备注，后续必须专门验证角色投影，不得把此数据源直接开放给顾客或商户。

记录使用 `key` 与 `$ref` 表达依赖，没有运行主键/安装身份。真实录入时必须由 owner 分配身份并保留别名映射；不能把 fixture subject 当成已认证 CAS 主体，不能把模拟 orderEvent/operationId 当成实际命令回执。

[ingestion-plan.json](~/codespace/magicTest/applications/chess-room-booking/fixtures/ingestion-plan.json)仅列出录入顺序与前置能力，`executable=false`。样例不进入模型包。生成、检查及重新规划命令见[工具说明](~/codespace/magicTest/applications/chess-room-booking/tooling/README.md)。

## 模拟接入计划

[当前模拟计划](~/codespace/magicTest/applications/chess-room-booking/fixtures/simulation-r5-plan.json)由 `simulation_plan` 生成，不含 owner 主键或 version。源与目标分别管理，禁止直接创建目标。[准入规则快照](~/codespace/magicTest/applications/chess-room-booking/fixtures/admission-contract-r4.json)用于离线检测声明漂移，不进入ZIP、不代替Base权威验证。实际执行和未知结果处理见[工具说明](~/codespace/magicTest/applications/chess-room-booking/tooling/README.md)。

[返回棋牌室预订验证套件](~/codespace/magicTest/applications/chess-room-booking/README.md)
