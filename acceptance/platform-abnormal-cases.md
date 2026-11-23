# 平台破坏性与异常故障验证清单

由[唯一用例目录](~/codespace/magicTest/acceptance/platform-catalog.json)生成；完整步骤和预期见[用例表](~/codespace/magicTest/acceptance/platform-case-ledger.md)。不手工维护第二套用例正文。

共28条破坏性及故障异常测试分项（权限故障类1、破坏/超限类12、并发/中断恢复类15），其中20条同时包含条件专项分项。不产生破坏性的正向功能、只读权限隔离、正常输入拒绝与无副作用取消保留在默认常规正向验证（`standard`）；本表所列用例统一单列并通过 `platform-abnormal` 独立执行。

## 分类与执行原则

- 归入原则：仅包含故障注入、请求/清理中断、损坏制品/快照、进程重启、响应丢失模拟、并发写竞争、来源限流/锁定及全局边界冲突等产生破坏性或干扰性的测试。
- 不产生破坏性的权限矩阵、跨租户隔离、分页聚合及合法输入/引用保护拒绝均保留在正向回归（`standard`）。
- 通过正向常规回归不代表破坏性异常测试或完整目录通过；混合专项分项按各自条件单独预检与验收。

| 用例 | 类型 | 事实owner | 异常验证范围 | 并存专项范围 | 夹具 / 方法 |
| --- | --- | --- | --- | --- | --- |
| F001-005 刷新轮换、重放及失效分类 | recovery（并发冲突与故障恢复） | magicCas、magicRunner/web、magicWebPortal | 刷新轮换、消费凭证重放、客户端撤销、invalid_grant/invalid_request分类及并发刷新。 | 刷新凭证真实到期；CAS真实短暂5xx及恢复后的会话/审计。 | isolated-ops / live |
| F002-003 重复申请与审核 | recovery（并发冲突与故障恢复） | magicCas、magicRunner/panel、magicWebPortal | 全部步骤及预期；使用可重复创建、正式回收的受控夹具。 | 无 | business / live |
| F010-003 权限修订失效与登录来源限流 | recovery（并发冲突与故障恢复） | magicCas、magicRunner/web、magicRunner/gateway | 回收当前角色后在线校验旧JWT失效、刷新后新权限版本生效与普通401/错误区分，以及独立受控账号密码连续错误锁定（不影响其他账号）。 | 隔离CAS按启动配置触发租户/来源登录限流、关闭来源限流后验证密码锁定保持，并等待真实阻断期限自然恢复。 | isolated-ops / live |
| F010-004 权限变化后的有界重试 | recovery（并发冲突与故障恢复） | magicCas、magicRunner/web、magicRunner/gateway | 权限修订变化后的GET/HEAD有界刷新，写入/带正文请求和普通401不自动重发。 | 提交后丢失响应，核对原业务执行次数及原请求回执。 | isolated-ops / live |
| F010-005 授权规模、令牌及会话字节边界 | boundary（破坏/超限/受损校验） | magicCas、magicRunner/web、magicRunner/gateway | CAS/应用授权初始合同声明计数边界（dataAccess/entityActions/permissions/roles/templates及超限拒绝与收缩）、全量平台档案+已装实例范围下的真实JWT与加密会话Cookie字节实测、合法边界登录/刷新/业务调用及安全撤权清理。 | 隔离环境极大规模实例/动作扩展与HTTP/代理/存储累计字节上限压测及超限保护。 | capacity / live |
| F017-002 脚本非法与超时 | boundary（破坏/超限/受损校验） | magicRunner/panel、magicBase、magicWebPortal | 语法/入口/类型/必需输入/输出诊断（0/false不误判缺失），1..3000ms超时预算与超界拒绝，长循环超时日志有界且其他请求继续，客户端取消与禁止goroutine/init/全局变量。 | 隔离Panel进程侧关联原调试取消请求，独立核验服务端解释器在客户端断开后即时停止且无泄漏。 | business / live |
| F018-002 版本冲突及丢失响应 | recovery（并发冲突与故障恢复） | magicRunner/panel、magicBase | 同版本并发保存、原子性及冲突输入保持。 | 正式保存提交后丢失响应，按原身份确认且不重复创建。 | isolated-ops / live |
| F020-002 损坏制品 | boundary（破坏/超限/受损校验） | magicRunner/panel、magicFile | 全部步骤及预期；使用可重复创建、正式回收的受控夹具。 | 无 | business / live |
| F022-003 镜像解析失败 | recovery（并发冲突与故障恢复） | magicRunner/panel、magicPlatform | 本地缺失镜像/受控仓库拒绝、切换重试和浏览器控制旧建议迟到。 | 实际外部仓库不可访问时的解析拒绝及恢复。 | isolated-ops / live |
| F027-003 重复提交与撤回 | recovery（并发冲突与故障恢复） | magicRunner/panel、magicBase、magicCas | 全部步骤及预期；使用可重复创建、正式回收的受控夹具。 | 无 | isolated-ops / live |
| F028-002 并发审批与版本冲突 | recovery（并发冲突与故障恢复） | magicRunner/panel、magicCas | 全部步骤及预期；使用可重复创建、正式回收的受控夹具。 | 无 | isolated-ops / live |
| F031-003 预览后新增引用 | recovery（并发冲突与故障恢复） | magicRunner/panel、magicBase、magicCas、magicFile | 全部步骤及预期；使用可重复创建、正式回收的受控夹具。 | 无 | isolated-ops / live |
| F034-002 身份不一致的恢复 | boundary（破坏/超限/受损校验） | magicRunner/panel、magicBase、magicCas、magicFile | 公开请求错误安装身份、旧版本及错误恢复引用的拒绝和原资源保持。 | 需要真实异常回执状态的恢复拒绝，须由owner隔离测试装置构造。 | business / live |
| F035-006 完整分派快照与路由确认 | boundary（破坏/超限/受损校验） | magicRunner/panel、magicBase、magicRunner/gateway | 多assignment完整Gateway快照（与Panel活跃模型安装集合逐一核对）、选择器参数拒绝、变更后单调版本推进、注册表路由观察状态与正式字节边界检查。 | 万级assignment与字节上限边界、Base快照及Gateway响应过期/回退/截断/错摘要、确认响应丢失与重启后高水位保持。 | capacity / live |
| F048-003 卸载保留与重新安装 | recovery（并发冲突与故障恢复） | magicRunner/panel、magicBase、magicOrm | retain卸载后独立读取保留存储、恢复资格与跨租户隔离，错版本/重复认领拒绝，独立新分配不串旧存储，合法原绑定恢复、代际围栏、撤权不复活及destroy清理确认。 | retain/restore提交后响应丢失恢复与在途重放防重验证。 | isolated-ops / live |
| F049-003 空文件、大文件和中断 | boundary（破坏/超限/受损校验） | magicFile | 空文件及有效字节上限前/上限/超限上传、属性及错误回读。 | 上传接纳前后中断、原上传身份完整性确认及清理。 | business / live |
| F054-004 工单删除、附件清理及迟到上传 | recovery（并发冲突与故障恢复） | magicRunner、magicFile | 授权工单删除、正常附件释放（含服务专用File路由人工直调403边界）、删除后上传拒绝、另一工单及同内容独立引用保持。 | File清理中断、删除后上传迟到及原工单/引用恢复。 | isolated-ops / live |
| F056-002 无效策略与版本冲突 | boundary（破坏/超限/受损校验） | magicCas、magicRunner/web、magicRunner/panel | 全部步骤及预期；使用可重复创建、正式回收的受控夹具。 | 无 | business / live |
| F057-004 可信来源与安全事件归因 | authorization（故障/伪造边界） | magicCas、magicRunner、magicBase | 同入口伪造转发/身份头抗篡改，CAS登录/BFF操作/Gateway服务凭据事件主体归因与租户审计读取隔离（无秘密原文）。 | 直连/正式受信代理/无效转发多网络链路真实对端来源分离，及可信主机DNS解析暂时失败时不扩大信任与重启恢复。 | isolated-ops / live |
| F058-002 无效配置与冲突 | boundary（破坏/超限/受损校验） | magicCas、magicBase、magicRunner/panel | 各类超界拒绝、0天永久保留及清理周期/批量/批次上下边界保存、并发expectedResourceVersion冲突、界面读取失败不虚填默认值及缩短期限删除提示取消。 | 独立隔离日志owner上验证正数保留天数边界（1..36500天）保存与回读，避免共享环境触发历史失败日志删除。 | business / live |
| F060-003 非法快照及在线恢复 | boundary（破坏/超限/受损校验） | magicPlatform、magicRunner/installer | 全部步骤及预期；使用可重复创建、正式回收的受控夹具。 | 无 | isolated-ops / live |
| F062-002 未知Host和错误证书 | boundary（破坏/超限/受损校验） | magicPlatform、magicRunner/installer | 全部步骤及预期；使用可重复创建、正式回收的受控夹具。 | 无 | isolated-ops / live |
| F064-002 文档缺失与不可用 | boundary（破坏/超限/受损校验） | magicRunner、magicWebPortal | 缺失法律文件的明确提示及不误读其他内容。 | 真实File服务不可用时的页面反馈及恢复。 | business / live |
| F067-002 页面取消、冲突与未知保存 | recovery（并发冲突与故障恢复） | magicRunner/panel、magicWebPortal | 离页取消、两作者同版本冲突及原输入保持。 | 正式页面保存提交后丢失响应，按原保存独立确认。 | business / browser |
| F070-003 可靠创建修改删除及未知响应 | recovery（并发冲突与故障恢复） | magicCas、magicRunner/apps、magicBase、magicOrm、magicWebPortal | 正式可靠创建/修改/删除，同请求重复、不同载荷冲突、并发版本及取消语义。 | 接纳前/提交后响应丢失，按原稳定请求及持久回执确认。 | isolated-ops / live |
| F071-002 可靠来源接纳与载荷冲突 | boundary（破坏/超限/受损校验） | magicRunner/panel、magicBase、magicCas | 正式生产者可靠来源接纳、同身份同载荷防重、冲突载荷与跨实例/绑定拒绝。 | 来源接纳提交后响应丢失时确认原请求、意图及任务关联。 | business / live |
| F071-004 派生目标事务与提交确认 | recovery（并发冲突与故障恢复） | magicRunner/panel、magicBase、magicCas | 真实来源到整批目标的主键/关系/唯一约束及可由合法输入稳定触发的整批失败。 | 目标事务提交后响应丢失、原回执确认及重复恢复防重。 | isolated-ops / live |
| F071-005 领取重启、迟到执行与生命周期 | recovery（并发冲突与故障恢复） | magicRunner/panel、magicBase、magicCas | 实例停用/升级/retain/destroy时来源关闭、在途处理、保留/清理及其他实例保持。 | 领取者中断/重启、旧租约迟到、重复领取/恢复和累计预算保持。 | isolated-ops / live |
