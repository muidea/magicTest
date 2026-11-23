# 平台条件专项用例

由[唯一用例目录](~/codespace/magicTest/acceptance/platform-catalog.json)生成；完整步骤和预期见[用例表](~/codespace/magicTest/acceptance/platform-case-ledger.md)。不手工维护第二套用例正文。

共75条涉及专项，其中42条同时包含自动回归分项。专项缺条件不阻断常规正向或异常回归；混合用例必须全部分组都通过才算整条通过。

## 条件、准备与退出要求

### external-idp：真实外部身份提供方

准备：准备隔离测试IdP、真实issuer/受众/回调、账号映射及有效和无效身份；记录配置摘要，秘密走私密配置。

退出：真实联邦链路及本地角色独立回读；协议替身结果不得冒充真实集成。

### public-pki：公网DNS与证书签发方

准备：准备受控测试域名、DNS提供方最小权限凭据及声明支持的CA；确认签发/续期窗口与速率预算。

退出：核对真实DNS挑战、证书链/SAN、序列号及重载后入口，不用本地CA结果替代。

### external-registry：实际外部镜像仓库

准备：准备隔离仓库地址、测试镜像/摘要和最小权限主体；使用受控拒绝或不可达条件，不等待生产仓库偶发故障。

退出：真实解析/拉取结果与原操作回执一致；恢复后重试原合法路径，不把旧镜像记为新更新成功。

### optional-apm：声明启用的外部观测集成

准备：准备真实采集端、访问配置及可关联测试请求，记录启用范围。

退出：同一请求在平台和采集端归属/时间/次数一致；未配置记条件不足，不影响常规观测回归。

### natural-time：服务端真实自然期限

准备：通过正式接口设置合法期限，记录原资源、服务端截止点、最早观察时刻和调度预算；不改时钟/私有时间字段。

退出：到期前后沿同一资源独立回读并验证真实门禁/清理；未到期限保留待验，不以参数保存替代。

### controlled-fault：隔离故障与精确执行窗口

准备：准备独立部署及owner公开测试装置/受控代理，声明目标阶段、暂停/中断点和恢复命令；先证明命中窗口，缺装置记工具缺口。

退出：沿原请求/任务/资源核对提交和未知结果，正式恢复或有证明终结；回读残留和另一实例，保留失败历史。

### isolated-daemon：独立嵌套容器与宿主机部署环境

准备：准备独立嵌套 Docker 守护进程及可销毁部署根目录，准备锁定镜像、本地证书／目录隔离装置与原运行清单；不得在共享正常业务验收环境执行。

退出：所有容器停启、目录归属、证书轮换、更新／reset 与持久故障注入全部完成独立回读及还原清理证明，原宿主环境不受任何影响。

## 执行与证据

按功能owners通过正式公开接口独立读取；对照逐条expected，记录精确主体、租户、实例、安装、请求及资源身份。负例须到达目标校验，不能用认证提前失败代替。

记录本次精确资源及保留意图，通过owner正式删除、退役或恢复，独立确认所属残留及其他实例保持；未知结果先核对原身份，保留失败历史。

执行证据写入当前登记运行目录，含候选身份、日志、浏览器截图、独立回读与清理结果；不修改既往报告、不承接旧通过结论。

专项按各自条件预检和调度。缺脚本、owner测试装置、有效预算或支持合同分别登记缺口，不统一归为第三方不可用。不得在业务环境临时停服务制造样本。

| 用例 | 事实owner | 保留在自动回归的范围 | 单列专项范围 | 前置条件 |
| --- | --- | --- | --- | --- |
| F001-005 刷新轮换、重放及失效分类 | magicCas、magicRunner/web、magicWebPortal | abnormal：刷新轮换、消费凭证重放、客户端撤销、invalid_grant/invalid_request分类及并发刷新。 | 刷新凭证真实到期；CAS真实短暂5xx及恢复后的会话/审计。 | natural-time；natural-time、controlled-fault |
| F003-001 空间新增、修改、状态与期限 | magicCas、magicRunner/panel | standard：新增/编辑空间、合法期限保存回读、范围和禁用门禁；其他租户原会话保持、目标旧会话失效及重新认证恢复。 | 原测试空间自然到期后的目录与受保护入口。 | natural-time；natural-time |
| F003-003 空间访问发布失败 | magicCas、magicRunner/panel | 无；本用例全部单列专项 | 授权发布故障窗口内保存空间及恢复后状态一致性。 | isolated-ops；controlled-fault |
| F003-004 空间删除与在用引用 | magicCas、magicRunner/panel | standard：在用租户拒绝删除及全保持、清理阻塞项后空租户删除、目标404、CAS不存在、退役回执与无关会话保持。 | 中断原始退役后的故障注入恢复与原身份重整。 | isolated-ops；controlled-fault |
| F009-001 外部身份登录 | magicCas | 无；本用例全部单列专项 | 全部步骤及预期：真实IdP登录/回调、身份映射及无效身份拒绝。 | external-idp；external-idp |
| F009-002 外部身份校验 | magicCas | 无；本用例全部单列专项 | 全部步骤及预期：真实IdP登录/回调、身份映射及无效身份拒绝。 | external-idp；external-idp |
| F009-003 身份提供方不可用 | magicCas | 无；本用例全部单列专项 | 真实IdP不可用及恢复后的登录，禁止降级绕过身份校验。 | external-idp；external-idp、controlled-fault |
| F010-003 权限修订失效与登录来源限流 | magicCas、magicRunner/web、magicRunner/gateway | abnormal：回收当前角色后在线校验旧JWT失效、刷新后新权限版本生效与普通401/错误区分，以及独立受控账号密码连续错误锁定（不影响其他账号）。 | 隔离CAS按启动配置触发租户/来源登录限流、关闭来源限流后验证密码锁定保持，并等待真实阻断期限自然恢复。 | natural-time；isolated-daemon、natural-time |
| F010-004 权限变化后的有界重试 | magicCas、magicRunner/web、magicRunner/gateway | abnormal：权限修订变化后的GET/HEAD有界刷新，写入/带正文请求和普通401不自动重发。 | 提交后丢失响应，核对原业务执行次数及原请求回执。 | isolated-ops；controlled-fault |
| F010-005 授权规模、令牌及会话字节边界 | magicCas、magicRunner/web、magicRunner/gateway | abnormal：CAS/应用授权初始合同声明计数边界（dataAccess/entityActions/permissions/roles/templates及超限拒绝与收缩）、全量平台档案+已装实例范围下的真实JWT与加密会话Cookie字节实测、合法边界登录/刷新/业务调用及安全撤权清理。 | 隔离环境极大规模实例/动作扩展与HTTP/代理/存储累计字节上限压测及超限保护。 | capacity；isolated-daemon |
| F015-003 后置功能失败 | magicBase、magicRunner/panel | 无；本用例全部单列专项 | 业务写已提交后功能块真实失败及准确反馈。 | isolated-ops；controlled-fault |
| F017-002 脚本非法与超时 | magicRunner/panel、magicBase、magicWebPortal | abnormal：语法/入口/类型/必需输入/输出诊断（0/false不误判缺失），1..3000ms超时预算与超界拒绝，长循环超时日志有界且其他请求继续，客户端取消与禁止goroutine/init/全局变量。 | 隔离Panel进程侧关联原调试取消请求，独立核验服务端解释器在客户端断开后即时停止且无泄漏。 | isolated-ops；isolated-daemon |
| F018-002 版本冲突及丢失响应 | magicRunner/panel、magicBase | abnormal：同版本并发保存、原子性及冲突输入保持。 | 正式保存提交后丢失响应，按原身份确认且不重复创建。 | isolated-ops；controlled-fault |
| F022-003 镜像解析失败 | magicRunner/panel、magicPlatform | abnormal：本地缺失镜像/受控仓库拒绝、切换重试和浏览器控制旧建议迟到。 | 实际外部仓库不可访问时的解析拒绝及恢复。 | isolated-ops；external-registry |
| F024-001 依赖声明和安装注入 | magicRunner/panel、magicPlatform | standard：就绪组件依赖、端点消费及必需/可选/默认覆盖/未声明参数注入与两容器退役。 | 依赖宿主 runtimeSecuritySecret 目录的数据库/服务/密钥依赖校验。 | isolated-ops；isolated-daemon |
| F024-003 注入失败与补偿 | magicRunner/panel、magicPlatform | 无；本用例全部单列专项 | 私密交付提交前后中断、原冻结任务恢复/取消及副本反向清理。 | isolated-ops；controlled-fault |
| F028-004 批准后权限或资源失效 | magicRunner/panel、magicCas | 无；本用例全部单列专项 | 批准冻结后、分派前撤权/停用资源，原任务执行/恢复门禁。 | isolated-ops；controlled-fault |
| F029-002 执行器恢复与重复领取 | magicRunner/panel、magicBase、magicCas | 无；本用例全部单列专项 | 执行器停止/恢复、重复领取及实际部署防重。 | isolated-ops；controlled-fault |
| F029-003 任务按状态操作 | magicRunner/panel、magicBase、magicCas | standard：成功模型任务、native exit23失败、UI重试经运行窗至成功、正式终止及三宽度诊断/版本冲突。 | 额度耗尽/paused/授权与Schema诊断动作及慢响应切换任务选中的故障窗口。 | isolated-ops；controlled-fault |
| F029-004 未知提交、冻结意图与累计预算 | magicRunner/panel、magicBase、magicCas | 无；本用例全部单列专项 | 副作用前和提交后窗口中断、预算耗尽、重复恢复及迟到执行者。 | isolated-ops；controlled-fault |
| F030-002 进行中和未确认记录 | magicRunner/panel、magicBase、magicCas、magicFile | standard：提交中请求及成功交付任务的清理拒绝保护（运行资源和成功交付依据不被删除）；允许在正常审批交付窗口探测未终态清理拒绝，不依赖人为降速。 | 受控延迟或中断使交付任务稳定停留于进行中（running）及资源清理未确认态时，前后双侧确认清理被拒绝且运行/回收依据不丢失。 | isolated-ops；controlled-fault |
| F030-003 清理响应丢失 | magicRunner/panel、magicBase、magicCas、magicFile | 无；本用例全部单列专项 | 取消/删除确认丢失后按原请求回查、恢复及范围保护。 | isolated-ops；controlled-fault |
| F033-001 模型生命周期与卸载 | magicRunner/panel、magicBase、magicCas、magicRunner/gateway、magicFile | standard：双模型安装、停用/激活、停用来源拒绝、retain/restore及destroy正式清理（首期不提供历史代际任务查询接口）。 | 在途任务中断/恢复、claimant重启、late-lease围栏与完整CAS/Gateway/File残留细读。 | isolated-ops；controlled-fault |
| F033-002 原生卸载审批 | magicRunner/panel、magicBase、magicCas、magicRunner/gateway、magicFile | standard：含入口与双native消费者、packaged destroy明确拒绝、retain卸载、路由及容器撤除与保留卷回执。 | 共享授权owner退役与CAS/注入副本残留内部细读。 | isolated-ops；controlled-fault |
| F033-003 卸载部分失败 | magicRunner/panel、magicBase、magicCas、magicRunner/gateway、magicFile | 无；本用例全部单列专项 | 卸载阶段中断、原请求恢复及部分清理证明。 | isolated-ops；controlled-fault |
| F034-001 安装摘要与诊断 | magicRunner/panel、magicBase、magicCas、magicFile | standard：双成功模型摘要、实时健康区分、三宽度界面及原生失败诊断清理。 | 部署中途故障注入生成失败安装记录及其摘要与服务端nextAction。 | isolated-ops；controlled-fault |
| F034-002 身份不一致的恢复 | magicRunner/panel、magicBase、magicCas、magicFile | abnormal：公开请求错误安装身份、旧版本及错误恢复引用的拒绝和原资源保持。 | 需要真实异常回执状态的恢复拒绝，须由owner隔离测试装置构造。 | isolated-ops；controlled-fault |
| F034-003 受控修复确认 | magicRunner/panel、magicBase、magicCas、magicFile | 无；本用例全部单列专项 | 当次受控失败任务的正式诊断、恢复/终结、迟到执行者及残留。 | isolated-ops；controlled-fault |
| F034-004 升级失败的原身份恢复 | magicRunner/panel、magicBase、magicCas、magicFile | 无；本用例全部单列专项 | 升级各交接窗口失败、撤权后恢复、前任/后继及原身份终结。 | isolated-ops；controlled-fault |
| F035-002 租约过期与承载重启 | magicRunner/panel、magicBase、magicRunner/gateway | 无；本用例全部单列专项 | 原租约真实失效/承载停止、恢复新代际及迟到原执行者。 | isolated-ops；controlled-fault |
| F035-004 运行放置策略与承载交接 | magicRunner/panel、magicBase、magicRunner/gateway | standard：默认运行放置策略条件修订、旧版本/错kind拒绝，及省略placement新审批按平台默认策略解析冻结与runtime执行。 | 双 Base / 双 Gateway 跨实例移交（handoff）、排空、吊销与接管恢复（平台支持能力）。 | isolated-ops；isolated-daemon、controlled-fault |
| F035-005 失败交接关联处置与范围保护 | magicRunner/panel、magicBase、magicRunner/gateway | 无；本用例全部单列专项 | 失败交接原身份continue/return/stop关联处置及治理范围保护。 | isolated-ops；controlled-fault |
| F035-006 完整分派快照与路由确认 | magicRunner/panel、magicBase、magicRunner/gateway | abnormal：多assignment完整Gateway快照（与Panel活跃模型安装集合逐一核对）、选择器参数拒绝、变更后单调版本推进、注册表路由观察状态与正式字节边界检查。 | 万级assignment与字节上限边界、Base快照及Gateway响应过期/回退/截断/错摘要、确认响应丢失与重启后高水位保持。 | isolated-ops；controlled-fault、isolated-daemon |
| F036-002 分页与字段校验 | magicRunner/apps、magicBase、magicOrm、magicCas | standard：复合主键游标、同值排序、bool/decimal/UTC/int64分页投影、切换筛选及非法/错安装/变条件/变页长游标拒绝与字段约束原行保持。 | 自然墙钟游标过期及专用关系集合分页投影边界。 | natural-time；natural-time |
| F041-002 订阅期限和重复申请 | magicRunner/panel、magicRunner/gateway、magicCas | standard：同一有效服务重复申请及有效订阅唯一性。 | 原订阅自然到期后的失效调用拒绝。 | natural-time；natural-time |
| F042-004 Key签发与删除的未知结果恢复 | magicRunner/panel、magicRunner/gateway、magicCas | 无；本用例全部单列专项 | CAS签发/删除提交前后回包中断及原命令确认/续办。 | isolated-ops；controlled-fault |
| F045-001 配额与限流 | magicRunner/panel、magicRunner/gateway、magicCas | standard：单Gateway下QPS/日额的有限边界、同Key并发和租户/订阅隔离（单应用只由单个Gateway服务；首期不包含最大并发与独立公开计数器直读）。 | 跨正式自然日界观察原计数重置，不修改系统时间。 | natural-time；natural-time |
| F045-002 重启保额与授权故障 | magicRunner/panel、magicRunner/gateway、magicCas | 无；本用例全部单列专项 | Gateway重启保额、CAS真实不可用时拒绝及恢复。 | isolated-ops；controlled-fault |
| F045-003 服务及租户凭证隔离 | magicRunner/panel、magicRunner/gateway、magicCas | standard：服务AKey调用B及伪造租户Header拒绝；上游已验证租户与无泄漏。 | 原Key自然到期后的实际调用拒绝。 | natural-time；natural-time |
| F048-003 卸载保留与重新安装 | magicRunner/panel、magicBase、magicOrm | abnormal：retain卸载后独立读取保留存储、恢复资格与跨租户隔离，错版本/重复认领拒绝，独立新分配不串旧存储，合法原绑定恢复、代际围栏、撤权不复活及destroy清理确认。 | retain/restore提交后响应丢失恢复与在途重放防重验证。 | isolated-ops；controlled-fault |
| F049-003 空文件、大文件和中断 | magicFile | abnormal：空文件及有效字节上限前/上限/超限上传、属性及错误回读。 | 上传接纳前后中断、原上传身份完整性确认及清理。 | isolated-ops；controlled-fault |
| F052-003 重复同步 | magicRunner、magicBase | standard：Insert-pending、Update/Delete、同源去重、内容跟随、终态退出/重开及双实例peer保持（首期不提供Base全量历史待办终态读取接口）。 | 精确事件重投与并发写竞争故障窗口。 | isolated-ops；controlled-fault |
| F054-003 重复发送与失败 | magicRunner、magicFile | 无；本用例全部单列专项 | 消息发送响应丢失后确认原操作及重复提交防重。 | isolated-ops；controlled-fault |
| F054-004 工单删除、附件清理及迟到上传 | magicRunner、magicFile | abnormal：授权工单删除、正常附件释放（含服务专用File路由人工直调403边界）、删除后上传拒绝、另一工单及同内容独立引用保持。 | File清理中断、删除后上传迟到及原工单/引用恢复。 | isolated-ops；controlled-fault |
| F056-001 会话期限保存生效 | magicCas、magicRunner/web、magicRunner/panel | standard：平台/租户会话策略继承、覆盖、重置；新旧会话实际到期字段回读。 | 原新旧会话自然到期及绝对会话上限不被刷新延长。 | natural-time；natural-time |
| F057-003 审计补写与实际结果 | magicCas、magicRunner、magicBase | 无；本用例全部单列专项 | CAS/Panel审计提交前后持久投递中断、重启及同事件接纳。 | isolated-ops；controlled-fault |
| F057-004 可信来源与安全事件归因 | magicCas、magicRunner、magicBase | abnormal：同入口伪造转发/身份头抗篡改，CAS登录/BFF操作/Gateway服务凭据事件主体归因与租户审计读取隔离（无秘密原文）。 | 直连/正式受信代理/无效转发多网络链路真实对端来源分离，及可信主机DNS解析暂时失败时不扩大信任与重启恢复。 | isolated-ops；controlled-fault、isolated-daemon |
| F057-005 持久补写容量及提交结果真实性 | magicCas、magicRunner、magicBase | 无；本用例全部单列专项 | 在独立嵌套容器环境核对正式持久队列数量/单项字节预算边界、并发预留隔离、目录不可写及业务提交前/后持久补写故障、重启恢复和原回执。 | isolated-ops；controlled-fault、isolated-daemon |
| F058-001 日志留存实际清理 | magicCas、magicBase、magicRunner/panel | 无；本用例全部单列专项 | 两类日志真实到期清理及永久保留对照；缺失/损坏共享策略停止清理。 | natural-time；natural-time、controlled-fault |
| F058-002 无效配置与冲突 | magicCas、magicBase、magicRunner/panel | abnormal：各类超界拒绝、0天永久保留及清理周期/批量/批次上下边界保存、并发expectedResourceVersion冲突、界面读取失败不虚填默认值及缩短期限删除提示取消。 | 独立隔离日志owner上验证正数保留天数边界（1..36500天）保存与回读，避免共享环境触发历史失败日志删除。 | isolated-ops；isolated-daemon |
| F059-002 监控和成本观测 | magicPlatform、magicRunner/installer | 无；本用例全部单列专项 | 在独立嵌套容器环境核对平台HTTP/RPC/SQL/路由/pprof空闲/真实请求观测、开关、敏感信息门禁及声明启用的真实外部APM关联观测。 | isolated-ops；isolated-daemon、optional-apm |
| F059-003 健康与业务可用区别 | magicPlatform、magicRunner/installer | 无；本用例全部单列专项 | 真实依赖不可用时live/ready/实际业务的区别与恢复。 | isolated-ops；controlled-fault |
| F060-001 全新和离线交付 | magicPlatform、magicRunner/installer | 无；本用例全部单列专项 | 全部步骤及预期；在独立嵌套容器与可销毁宿主机根目录使用正式受控夹具验证，记作待办项，不纳入正常业务验收。 | isolated-ops；isolated-daemon |
| F060-002 停机备份恢复演练 | magicPlatform、magicRunner/installer | 无；本用例全部单列专项 | 全部步骤及预期；在独立嵌套容器与可销毁宿主机根目录使用正式受控夹具验证，记作待办项，不纳入正常业务验收。 | isolated-ops；isolated-daemon |
| F061-001 目录与实例归属 | magicPlatform、magicRunner/installer | 无；本用例全部单列专项 | 全部步骤及预期；在独立嵌套容器与可销毁宿主机根目录使用正式受控夹具验证，记作待办项，不纳入正常业务验收。 | isolated-ops；isolated-daemon |
| F061-002 越界清理与路径 | magicPlatform、magicRunner/installer | 无；本用例全部单列专项 | 全部步骤及预期；在独立嵌套容器与可销毁宿主机根目录使用正式受控夹具验证，记作待办项，不纳入正常业务验收。 | isolated-ops；isolated-daemon |
| F061-003 start和stop覆盖实例 | magicPlatform、magicRunner/installer | 无；本用例全部单列专项 | 全部步骤及预期；在独立嵌套容器与可销毁宿主机根目录使用正式受控夹具验证，记作待办项，不纳入正常业务验收。 | isolated-ops；isolated-daemon |
| F062-001 域名证书访问 | magicPlatform、magicRunner/installer | 无；本用例全部单列专项 | 在独立嵌套容器环境核对本地CA/显式证书信任链、SAN、Host与双租户路由及未知Host门禁，以及声明支持的真实公网DNS挑战与CA签发路径。 | isolated-ops；isolated-daemon、public-pki |
| F062-003 证书更新与重载 | magicPlatform、magicRunner/installer | 无；本用例全部单列专项 | 在独立嵌套容器环境核对受控本地/显式证书更新、重载、租户路由及正常恢复，以及真实外部DNS/CA续期、签发及入口重载。 | isolated-ops；isolated-daemon、public-pki |
| F063-001 开发更新所有组件 | magicPlatform、magicRunner/installer | 无；本用例全部单列专项 | 全部步骤及预期；在独立嵌套容器与可销毁宿主机根目录使用正式受控夹具验证，记作待办项，不纳入正常业务验收。 | isolated-ops；isolated-daemon |
| F063-002 reset本地镜像与严格锁定 | magicPlatform、magicRunner/installer | 无；本用例全部单列专项 | 全部步骤及预期；在独立嵌套容器与可销毁宿主机根目录使用正式受控夹具验证，记作待办项，不纳入正常业务验收。 | isolated-ops；isolated-daemon |
| F063-003 更新失败与版本记录 | magicPlatform、magicRunner/installer | 无；本用例全部单列专项 | 受控拉取失败和组件ready失败、实际版本及原更新回执。 | isolated-ops；controlled-fault |
| F064-002 文档缺失与不可用 | magicRunner、magicWebPortal | abnormal：缺失法律文件的明确提示及不误读其他内容。 | 真实File服务不可用时的页面反馈及恢复。 | isolated-ops；controlled-fault |
| F067-002 页面取消、冲突与未知保存 | magicRunner/panel、magicWebPortal | abnormal：离页取消、两作者同版本冲突及原输入保持。 | 正式页面保存提交后丢失响应，按原保存独立确认。 | isolated-ops；controlled-fault |
| F069-002 共享筛选、选择器和游标 | magicRunner/apps、magicBase、magicOrm、magicWebPortal | standard：冻结主键分页、多列复合排序、eq筛选与未声明拒绝、options选择器游标、主体/安装隔离及真实页面首屏读。 | 自然墙钟游标过期窗口。 | natural-time；natural-time |
| F069-003 聚合、时间窗口及显示精度 | magicRunner/apps、magicBase、magicOrm、magicWebPortal | standard：计数/分组/无分组均值、UTC小时桶、Asia/Shanghai时区、桶/点/分组限流与取消，及预检拒绝sum/min/max与过滤均值。 | 构造大于1000行专用数据集验证SQL分组饱和上限。 | business；isolated-daemon |
| F069-004 运行页面授权和读取恢复 | magicRunner/apps、magicBase、magicOrm、magicWebPortal | standard：显式实体视图双安装下普通账号list/aggregate/options访问控制、撤权与安装/digest/代际围栏（首期Endpoint不开放页面数据源）。 | 引用关系标签投影与撤权前返回/迟到响应并发故障窗口。 | isolated-ops；controlled-fault |
| F069-005 运行刷新、导航及迟到响应 | magicRunner/apps、magicBase、magicOrm、magicWebPortal | standard：三宽度5秒自动读取、10秒失败退避恢复、重叠保护、离页清理、持久草稿、时间窗与切账号。 | 有头交互式OS窗口切换下document.hidden真后台暂停与切回恢复。 | business；isolated-daemon |
| F070-001 独立业务动作与状态约束 | magicCas、magicRunner/apps、magicBase、magicOrm、magicWebPortal | standard：冻结动作API、跨动作与跨租户隔离、禁用恢复、权限分离、三宽度单次提交及回执/重放/版本/状态门禁（serviceExpose仅支持CRUD）。 | 自然墙钟令牌过期及全量并发故障矩阵。 | natural-time；natural-time、controlled-fault |
| F070-002 数据权、动作权和主体隔离 | magicCas、magicRunner/apps、magicBase、magicOrm、magicWebPortal | standard：冻结动作API、跨动作与跨租户隔离、禁用恢复、权限分离、三宽度单次提交及回执/重放/版本/状态门禁（serviceExpose仅支持CRUD）。 | 自然墙钟令牌过期及全量并发故障矩阵。 | natural-time；natural-time、controlled-fault |
| F070-003 可靠创建修改删除及未知响应 | magicCas、magicRunner/apps、magicBase、magicOrm、magicWebPortal | abnormal：正式可靠创建/修改/删除，同请求重复、不同载荷冲突、并发版本及取消语义。 | 接纳前/提交后响应丢失，按原稳定请求及持久回执确认。 | isolated-ops；controlled-fault |
| F071-002 可靠来源接纳与载荷冲突 | magicRunner/panel、magicBase、magicCas | abnormal：正式生产者可靠来源接纳、同身份同载荷防重、冲突载荷与跨实例/绑定拒绝。 | 来源接纳提交后响应丢失时确认原请求、意图及任务关联。 | isolated-ops；controlled-fault |
| F071-003 冻结程序与原主体当前授权 | magicRunner/panel、magicBase、magicCas | standard：安装后作者修改程序/目标草稿下，原普通来源仍按冻结程序派生、未授权拒绝及可靠回执（首期casaccess不开放Endpoint来源提交）。 | 接纳前编辑竞态、领取前撤权及租约/代际故障注入。 | isolated-ops；controlled-fault |
| F071-004 派生目标事务与提交确认 | magicRunner/panel、magicBase、magicCas | abnormal：真实来源到整批目标的主键/关系/唯一约束及可由合法输入稳定触发的整批失败。 | 目标事务提交后响应丢失、原回执确认及重复恢复防重。 | isolated-ops；controlled-fault |
| F071-005 领取重启、迟到执行与生命周期 | magicRunner/panel、magicBase、magicCas | abnormal：实例停用/升级/retain/destroy时来源关闭、在途处理、保留/清理及其他实例保持。 | 领取者中断/重启、旧租约迟到、重复领取/恢复和累计预算保持。 | isolated-ops；controlled-fault |
