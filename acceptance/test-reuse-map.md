# 回归脚本复用要求

用例定义、必要性、操作与预期唯一维护在[用例目录](~/codespace/magicTest/acceptance/platform-catalog.json)，可读表、[异常测试清单](~/codespace/magicTest/acceptance/platform-abnormal-cases.md)和[条件专项清单](~/codespace/magicTest/acceptance/platform-special-cases.md)均由[生成工具](~/codespace/magicTest/tools/platform_acceptance.py)生成，execution分组只维护在同一目录中。当前为71类功能、245条必需用例；两个模拟应用单列。

具体候选文件、统一入口target及限制维护在[资产清单](~/codespace/magicTest/regression/inventory.json)，用[只读导航工具](~/codespace/magicTest/regression_inventory.py)查看。候选文件存在不表示本用例已有完整脚本；源码回归、隔离集成、浏览器及部署业务证据分别表达。

| 用例范围 | 复用责任项目 | 脚本必须证明的独立边界 |
| --- | --- | --- |
| F001—F010、F056—F058 | CAS；Runner Web／Panel；Portal | 当前身份、回调／轮换／重放、完整成员、Endpoint角色、自然期限与持久审计 |
| F011—F020 | Runner Panel；Base；ORM；Portal | 定义、完整类型及关系、原子保存、能力开放、正式包和授权冻结 |
| F021—F026 | Runner Panel；Platform；Portal | 多组件实际运行、OCI建议、依赖注入、内置提供方及不可变交付 |
| F027—F035 | Runner Panel；Base；CAS；Gateway | 真审批／任务、当前权限、原请求恢复、同Schema升级、前任／后继及清理 |
| F036、F047—F048 | Runner Apps／Panel；Base；ORM | 精确实例CRUD、字段／游标、Schema和存储保留 |
| F037—F046 | Runner Panel／Gateway；CAS；Portal | 冻结服务、订阅续期、Key原命令、实时权限、日界／重启配额与管理调试 |
| F049—F054 | File；Runner；Base | 文件最后引用、图标、分类、待办／通知及工单附件反向清理 |
| F055、F064—F066 | Runner；Portal | Host品牌、法律文件、当前个人／管理统计及会话切换迟到响应 |
| F059—F063 | Platform；运行服务owner | 隔离部署、owner就绪、初始化／组件刷新职责、停启排空、快照与TLS |
| F067—F068 | Runner Panel；File；Portal | 页面作者、独立资源保存、引用保护、外观预算及精确安装图片 |
| F069—F070 | Runner Apps；Base；ORM；CAS；Portal | 冻结页面源、筛选／聚合、独立动作、可靠写入及原回执 |
| F071 | Runner Panel；Base；CAS | 原子来源接纳、冻结程序、当前原主体、目标事务、恢复和生命周期 |

通用夹具、登录、授权矩阵和页面控件可复用；每个用例与具名参数组合仍需独立断言及结果。默认常规正向（`standard`）184个分项自动执行，破坏性异常（`abnormal`）28个分项与条件专项（`special`）75个分项各自独立显式触发，合计245条用例／287个执行分项；混合用例按caseId与suite分别映射脚本和结果。不得为规避脚本缺口改分组。OAuth开关与Key开关、品牌布局与表单操作、审批动作与任务动作、普通CRUD与可靠写入不能互相替代。

未配套声明应按当前预检明确拒绝；真正运行的正例仍需正式保存／发布／安装后由真实生产者触发，并通过公开owner回读。缺脚本、配置、明确预算、自然期限或故障装置记受阻，不以mock、退出码0、健康200或新建成功样本填补。

复用脚本前核对当前API／SDK、原主体、精确安装与数据归属、预算、断言和清理。历史业务脚本未经核对不能复用；平台常规使用[magicTest统一入口](~/codespace/magicTest/run_tests.py)的`platform-standard`，破坏性异常测试使用`platform-abnormal`独立入口，均由[编排工具](~/codespace/magicTest/regression/run_standard.py)自动采集基线、执行、清理和报告，配置见[工具说明](~/codespace/magicTest/README.md)。缺脚本／夹具／正式角色的常规项保留受阻，不转入专项；当前运行的缺口和证据归其登记目录，本表不累计现场通过数。

身份／模板分项复用[当前身份执行器](~/codespace/magicTest/regression/identity_cases.cjs)：正式首次改密和错误密码页面、同租户CAS会话目录、BFF原凭据精确退出、模板实际授权／上限／撤回。CAS OAuth会话查询须使用同租户审计主体，不能以平台跨租户治理身份替代；模板撤回须证明来源并集保留和独有权限消失。此映射不表示其他身份分项已完成。

注册使用[匿名租户执行器](~/codespace/magicTest/regression/registration_cases.cjs)，会话策略使用[策略与BFF期限执行器](~/codespace/magicTest/regression/session_cases.cjs)，作者样例使用[脚本执行器](~/codespace/magicTest/regression/script_cases.cjs)，通知使用[owner与门户执行器](~/codespace/magicTest/regression/notification_cases.cjs)。同环境整组执行由编排工具本机排他锁串行协调；聚合退役回执可用于已审查的子资源清理核销，但必须关联原身份、保留原失败并独立确认目录不存在，不能将子查询403当作清理成功。
