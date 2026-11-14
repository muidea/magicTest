# magicTest 测试导航

Node.js浏览器工具统一使用用户级Playwright `1.65.0`（入口为`~/.local/bin/playwright`，Node API位于`~/.local/share/playwright`），仓库不再携带第二份Playwright依赖。首次准备执行`~/.local/bin/playwright install chromium`；所有Node执行器通过`regression/playwright.cjs`加载同一份API和用户缓存浏览器。该Node.js依赖不替代Python浏览器套件所需的Python包。

平台基本功能以交付可重复执行的完整场景、逐条用例及配套脚本为目标，统一要求见[平台全量功能回归说明](~/dataspace/magicPlatform/docs/technical/platform-functional-regression.md)，两个模拟应用单列。正式回归材料只描述当前功能、环境准备、操作断言、清理和执行方式，不包含过去的临时阶段记录。

[资产清单](~/codespace/magicTest/regression/inventory.json)是开发整理资料，保留有效用例编号，按14个主场景查找71类功能、245条必需用例的候选脚本和缺口；清单存在不代表完整脚本套件已经交付。默认常规全量目标为223个分项自动执行，48个条件专项单独预检与验证；26条混合用例分别记账，完整目录仍为245条。异常类型不直接决定是否专项，可稳定构造的权限／输入／并发／浏览器反例保留在常规。

```sh
cd ~/codespace/magicTest
python3 regression_inventory.py --check
python3 regression_inventory.py --case F033-001
python3 regression_inventory.py --scenario R10
python3 regression_inventory.py --suite standard --json
python3 regression_inventory.py --suite special --json
python3 regression_inventory.py --json
```

[盘点工具](~/codespace/magicTest/regression_inventory.py)只读原用例目录并复用目录owner的分组校验，不运行测试；默认展示整个目录，`--suite`只筛选导航，不执行所选组。分组详情和条件见[专项清单](~/codespace/docs/acceptance/platform-special-cases.md)。缺协作仓库或引用失效会明确失败；可用`--workspace`与`--platform-root`指定checkout。执行仍使用下文统一入口；现有部分套件可能跳过，退出码为0不等于对应功能用例已通过。

### 平台常规统一执行

业务动作 F070-001/002 使用[动作执行器](~/codespace/magicTest/regression/business_action_cases.cjs)：正式冻结模型、页面动作绑定和精确实例动作角色，配对查看／编辑／管理数据与独立动作权限、仅动作账号、原会话撤权、双实例拒绝、安装身份失配、状态／旧版本、原回执及已确认重放／输入冲突。真实动作表单包含390／1366／1920三宽度、单次点击、原请求与回执、独立完整业务行回读及终态禁用断言，源码尚待实际浏览器验证。动作与数据写入均先记原意图；响应丢失只查询原回执，主体漂移或结果未知保留原业务行、账号、模板和安装，不自动重发。Endpoint、真实另一租户、真实过期安装与完整生命周期仍缺，不计整例完成。当前按用户约定先补执行器及工具检查，平台Live后续单独执行。

正式入口为`platform-standard`，由[编排工具](~/codespace/magicTest/regression/run_standard.py)自动采集部署与健康基线、调用逐例执行器、正式清理夹具、再次核对候选并生成报告。使用仓库外的私密配置文件；配置仅引用凭据文件，不把密码写在命令行。示例配置：

初次浏览器启动有120秒预算；启动完成后不再用该预算中断业务命令。启动超时会保留原私密状态并继续采集健康／失败报告，不重试写入、不推定已清理，也不保证内核不可中断线程已经退出。原身份恢复入口可继续使用原私密目录。

正式同步租户创建 `POST /panel/namespace-onboardings/` 的 owner 传输等待预算为120秒，覆盖CAS策略准备；其他 owner 请求保持30秒。此预算只用于接收单次原请求结果，不重试或放宽性能断言。超时后仍须用原创建ID及正式回执恢复，不能据此重发创建或认定资源不存在。

```json
{
  "credentials": "~/.local/state/magicTest/regression-credentials.json",
  "output": "~/codespace/docs/acceptance/runs/<current-run>/standard"
}
```

```sh
cd ~/codespace/magicTest
python3 -B run_tests.py --target platform-standard --dry-run
MAGICTEST_REGRESSION_CONFIG=~/.local/state/magicTest/regression-config.json python3 -B run_tests.py --target platform-standard
```

配置可选`catalog`（唯一用例目录）、`cases`（常规用例ID数组，省略即全量）、`chrome`（已安装浏览器）和`fileUploadMaxBytes`（实际部署的文件上传上限字节，F049-003必填）。直接执行`python3 -B regression/run_standard.py --config <private-config> --dry-run`可只读核对实际选择，不访问部署。当前入口仍有尚未实现的常规分项，运行入口存在不代表完整套件交付。

每次在已登记运行目录下生成唯一子目录，保留`inputs.json`、`health-before`、`browser`、`health-after`、`results.json`和`report.json`。报告校验逐例证据摘要；只有常规分项全部通过、部署身份不变、前后健康、本次资源已独立确认清理且执行器成功，才返回成功。定向执行也报告完整常规目录覆盖率，其余项显示未执行；非零退出需根据逐例状态区分受阻、工具错误和产品失败。私密恢复状态自动留在仓库外，位置打印到终端，不归档其内容。当前浏览器夹具清理不代表历史基础设施登记器已全局核销。

同一HTTPS origin的常规执行串行进行。编排工具从预检到清理／报告持有本机排他锁，重复启动在业务操作前明确拒绝；不同用例的独立租户仍可能共享平台OAuth客户端，不能据此并发启动整组夹具。直接调用子执行器须由调用方保障同环境互斥；锁不协调其他机器或平台管理操作。

[注册执行器](~/codespace/magicTest/regression/registration_cases.cjs)通过真实匿名租户Host调用公开申请入口，管理策略路径为`policies`；管理代理不能替代匿名正例。[会话策略执行器](~/codespace/magicTest/regression/session_cases.cjs)保存平台及租户策略，独立读取BFF新旧会话身份和实际到期时间，并条件恢复平台原策略；自然到期仍按专项处理。[脚本执行器](~/codespace/magicTest/regression/script_cases.cjs)核对格式化、样例输出／日志、诊断及正式库保存回读；F017-002 另核对作者调试1—3000ms（0默认3000）的边界、超时和传输取消，运行绑定1—30000ms独立验证。浏览器取消不直接证明服务端已停止。[通知执行器](~/codespace/magicTest/regression/notification_cases.cjs)核对真实门户详情、受众与租户范围、下线／删除及读取失败后的旧缓存保护。各模块登记不表示用例已经通过。

注册账号的 `templateRefs` 只表示人工模板来源，不能用它断言注册来源的初始授权。执行器另通过公开 `subject-role-bindings` 集合读取原账号的绑定，核对注册来源、来源键、有效状态及精确角色集合，并保留实际登录和管理权限拒绝验证。目录仅在 `values:null` 且明确 `total:0` 时按空集读取；缺失或不完整结果保持受阻。

[公开文档与管理概览执行器](~/codespace/magicTest/regression/public_ui_cases.cjs)覆盖 F064-001/002/003 与 F066-003。法律文档使用当前部署的真实文本，独立匿名读取并核对摘要；保留临时说明时同时验证其标识可见，不推导正式法律内容已确认。缺失文件和概览读取失败仅在当前浏览器注入，移除后验证真实读取恢复；真实 File 服务中断仍属专项。管理概览使用独立租户的真实空目录、CAS 注册待办长内容及正式驳回后的独立回读，覆盖 390、1366、1920 三宽度和实际处理入口；不写入伪造待办或修改法律原文。

[待办执行器](~/codespace/magicTest/regression/todo_cases.cjs)覆盖 F052-001、F052-002 和 F066-001：由 CAS 真实注册申请产生持久待办，独立回读原请求、账号及来源投影，从待办目录实际跳转处理入口，分别批准和驳回后核对原来源终态及 pending 列表移除。双租户正例、普通成员拒绝及猜测来源身份核对访问范围；管理概览计数与当前租户账号目录对照，经快捷入口实际处理原事项。Panel 公开接口固定仅返回待处理事项，不将 pending 缺失宣称为直接读取了 Base 终态历史。原租户通过正式退役回收；不直接注入内部事件、修改待办存储或将重复查询当成重复事件交付验证。

[门户概览执行器](~/codespace/magicTest/regression/portal_overview_cases.cjs)覆盖 F065-001：普通账号的完整应用、服务、通知及反馈投影与三宽度页面计数对照，以真实非空订阅、通知、私有工单和双模型安装核对详情与跳转身份。服务首页先保留未筛选概览证据，再通过实际搜索定位原服务，适用于超过4条预览的完整回归。定义 UUID、运行 UUID、部署 ID 和订阅摘要分别按正式合同核验；不以管理员或空列表替代普通账号正例。原订阅和工单沿正式入口清理，保留外部安装夹具；此入口不替代 F065-002 的会话切换及迟到响应验证。

[审批状态执行器](~/codespace/magicTest/regression/approval_state_cases.cjs)覆盖 F028-003：创建原模型申请，核对待审批、驳回、撤回和批准完成后的实际操作；三宽度下编辑长审批原因并取消，独立确认无写入。终态批准／驳回必须命中准确状态门禁并保持完整申请、任务和安装事实，不以认证拒绝或过期版本代替。已批准申请等待真实执行完成，不伪造瞬态；当次安装与申请按原身份正式回收，未知命令保留待确认。

[字段约束执行器](~/codespace/magicTest/regression/field_constraint_cases.cjs)覆盖 F013-002：使用普通成员和冻结模型，实际提交省略自动主键、owner版本及默认字段的可靠创建，独立回读 null、空串、合法文本及零值；必填、长度、类型和owner只读字段的负例须命中准确字段拒绝，核对原完成回执缺失和完整原记录不变。未知命令阻断清理，确认后沿原主体可靠删除并独立证明原记录不存在。工具测试和Live结果分别留证。

[存储分配门禁执行器](~/codespace/magicTest/regression/storage_admission_cases.cjs)覆盖 F048-002：新建隔离禁用端点目录，通过真实审批核对不可用资源及范围外专属资源的准确拒绝、完整安装/操作/存储目录保持及原申请正式取消清理。未知审批保留所选端点和相关租户；清理不重发原审批，不修改既有共享端点。

[TLS交付执行器](~/codespace/magicTest/regression/tls_delivery_cases.cjs)覆盖 F062-001：在隔离环境对当前有效本地CA材料执行正式复用及显式files交付，严格验证实际HTTPS叶证书、信任链、SAN、双租户Host及未知租户404。证书名称错误须在HTTP之前拒绝；两个准备路径的实际证书字节一致，原运行材料保持。私钥副本仅留在仓外临时目录并同步删除；F062-001 不安装系统信任、不轮换证书或重载入口。

F062-003 在同一隔离环境通过正式 `files` 交付与 `reload-traefik-tls.sh` 更新证书，严格核对新CA、实际叶证书、三租户Host和未知租户404，再正式恢复并核对原材料、原叶证书和会话。私密备份仅在恢复确认后删除；未确认命令不重发，外来材料或运行身份改变时保留原记录。Docker容器与挂载按完整属性集合比较，返回顺序不属于所有权。外部DNS／CA续期与签发属于条件专项。

[实体能力声明执行器](~/codespace/magicTest/regression/entity_capability_cases.cjs)使用四个独立原模型身份逐一核对未知键、重复键、空项及空键的正式预检／保存及完整回读；已确认的意外接受如实记录为失败，未知结果阻断后续写入；[模型交付夹具](~/codespace/magicTest/regression/model_delivery.cjs)以条件发布、正式构包和不可变回读保留新夹具。发布／构包结果未知时不重发，不删除已发布事实；安装后能力目录与实际服务消费仍属未完成覆盖，F019-003 不计整例通过。

[生成服务汇聚执行器](~/codespace/magicTest/regression/generated_service_cases.cjs)覆盖 F038-001：以超过显式分页预算的真实安装能力核对完整目录、同来源重复汇聚及已发布接口冻结，分别验证能力占用在发布前后及停用后仍受保护，再通过正式解绑、编辑和重新发布转移能力。所有变更先记录原意图；未知结果不重发，清理由公开服务级联退役和完整服务／绑定／发布目录独立确认，并核对源能力及原安装保持。

[接口文档执行器](~/codespace/magicTest/regression/service_contract_cases.cjs)覆盖 F039-001：下载内部已安装实体 GET 与外部 GET／POST 的真实 OpenAPI 和公开合同，对照冻结 owner 的方法、路径、参数及请求／响应 Schema，再解析浏览器复制的示例并通过原 ApiKey 实际调用。样例只按限定语法解析，不交给 Shell。内部调用以普通成员可靠写入的原记录为基准，先核对 Endpoint 未授权拒绝，再经 CAS 正式模板赋予精确实例读取角色并核对成功，撤权后原 Key 必须失效。未知模板变更保留原命令、模板、凭据及父订阅／服务；工具检查和 Live 结果分别记录。

[服务范围与生命周期执行器](~/codespace/magicTest/regression/service_scope_cases.cjs)在 F041-001 中验证现有的待审批拒绝、正式批准、免审批开通及真实 ApiKey 调用，再由原普通订阅者退订。Portal DELETE 的身份是服务 ID，由 owner 解析原主体的订阅；凭据与 Endpoint 的退役须结合原响应、Panel 精确及完整目录、CAS Client／Endpoint／Credential 独立事实确认。未知退订禁止重发及父资源清理。驳回、续期及关联 Key 期限传播按已保留的能力缺口明确记部分验证，不生成替代合同或整例通过。

[服务配额执行器](~/codespace/magicTest/regression/service_scope_cases.cjs)在 F045-001 中以原 ApiKey 发送有限并发请求，分别核对单 Gateway 的 QPS 和日额边界、无效凭据不消耗日额，以及不同订阅和租户的独立预算。每个请求使用独立 marker，精确区分配额 429 与前置鉴权拒绝，并回读真实受控上游的实际执行次数。QPS 跨真实秒界的样本保持受阻，不重置计数或重跑替代；下一自然秒恢复单独验证。最大并发、跨 Gateway 计数和独立公开计数回读仍明确保留缺口，不能据此宣称整例通过。

F046-001另以原管理账号验证未订阅时可使用显式管理路径，再验证同账号订阅Key耗尽日额后管理路径仍可调用，且不恢复Key额度。路由和聚合指标不能替代独立持久管理调试来源记录，该证据未齐时整例保持部分验证。


[授权快照比较](~/codespace/magicTest/regression/authority_snapshot.cjs)仅忽略 CAS 顶层授权集合及完整账号目录的排列顺序，保留重复元素、全部资源字段、权限和修订差异。其他数组保留顺序，不以 JSON 原始排列断言授权集合变化。[品牌清理](~/codespace/magicTest/regression/branding_cleanup.cjs)保存原账号、租户和每次请求结果；仅对已确认发生在命令准入前的精确繁忙拒绝进行有界重试，响应丢失或其他结果未知保持开放。`--resume-cleanup` 仅从原始清理证据恢复已拒绝的品牌清理及其所属租户，不创建替代夹具。

[完整目录读取器](~/codespace/magicTest/regression/directory.cjs)固定原主体、origin、查询条件及页预算，检查分页总数、重复身份和短页；没有 owner 快照修订时不承诺并发原子快照。分类只读角色和租户管理员夹具使用完整分页，不凭第一页认定角色或账号不存在。F051-003 缺 reader 时报告正式候选／Installer／CAS 配套条件，不使用临时 Role 或初始化重放补权。

[资源台账](~/codespace/magicTest/regression/resource_lifecycle.cjs)覆盖公共 `create/createAs/remove` 夹具入口。发送前原子持久化私密意图，创建响应后保存精确身份并独立读取；首次回读失败但已保存匹配的成功响应与精确 ID 时，清理可在原主体／origin 下重读原 ID，确认原提交身份后再删除，台账重载后同样适用；若原 ID 已独立确认不存在则只记录处置证明。删除前记意图，响应后独立确认原身份不存在。未知创建不重放、不猜 ID 删除；未知删除仍存在且无 owner 终态证明时保持开放。原主体／origin 变化阻断清理，未解决子项不能靠删除父租户掩盖。手写订阅等业务命令仍须各自提供原请求恢复与回收证明，公共 helper 不代替这些合同。

[服务标识执行器](~/codespace/magicTest/regression/service_cases.cjs)覆盖 F037-001/003 与 F038-002。展示编辑按内外部来源回读；来源冲突使用已发布双实例的真实能力，对现有外部服务的同一 key 发起正式汇聚，要求目标阶段明确拒绝及服务、能力、绑定、发布完整目录不变。标识拒绝创建同租户两个独立服务，验证重复 key 和不可编辑身份的精确拒绝阶段，并完整查询相关目录、回读两条原资源证明未覆盖。地址仅作合法外部服务元数据，不调用上游。失败／未知写入先登记，再保留原资源及清理开放状态。工具输入指纹自动包含全部运行 `.cjs` 模块，包含目录、公开探针及写入台账。

[服务夹具](~/codespace/magicTest/regression/service_graph.cjs)、[服务治理执行器](~/codespace/magicTest/regression/service_governance_cases.cjs)和[服务范围执行器](~/codespace/magicTest/regression/service_scope_cases.cjs)使用正式发布、原requestId订阅回执、一次性Key和本机受控HTTP上游的随机marker。普通OAuth Endpoint没有被登记到订阅时不能作为Gateway成功凭据；secret退休与access token撤销分别验证。外部上游剥离内部身份Header，不能据此证明内部能力上游的租户传播。服务草稿、发布门禁、实际下载OpenAPI和原订阅Key的新冻结路由配对验证，未确认的服务命令阻断原服务及父租户清理。
[服务调试执行器](~/codespace/magicTest/regression/service_debug_cases.cjs)通过真实Monaco剪贴板粘贴JSON，独立核对上游请求字节；先证明原慢请求到达上游，再以页面切换触发取消并验证迟到响应不会污染当前执行记录。指南验证在两个真实租户域名实际复制URL及调用示例，只按受限语法解析文本而不执行shell，使用各自原订阅Key无Cookie调用。订阅、凭据、轮换和清理均绑定原owner；当前账号不匹配时拒绝写入与清理。未声明响应格式通过实际OpenAPI和合同下载核对，不伪造schema。


[owner传输](~/codespace/magicTest/regression/owner_transport.cjs)在发出请求前固定选择独立单次HTTP，复用原浏览器精确Cookie、Host和Origin，并明确本机租户Host连接映射；不跟跳转、不重试，不在未知浏览器写入后切换通道重放。UI操作、故障注入和无Cookie协议调用仍使用浏览器。资源公共创建／删除也使用此预选通道；原UI写入观察器显式保留唯一原路由转发，不因继承ownerApi替换原生产者。

[CAS表单传输](~/codespace/magicTest/regression/cas_form_transport.cjs)在真实登录操作前选定，只转发浏览器原始同源登录／首次改密表单，保留原字节、Cookie、Origin、Host和真实跳转及Cookie响应。原身份与私密发送意图先持久化，每条表单命令只发送一次；网络失败、重复或变更主体时拒绝，不合成登录或错误后重发。Live显式选择已安装的完整Chrome；浏览器域名映射与APIRequest连接映射分别配置。

[工单执行器](~/codespace/magicTest/regression/feedback_cases.cjs)覆盖F054-001/002及F050-003：真实附件二进制、原requestId消息回执、双方状态和页面顺序，以及同租户普通成员／外租户主体对非空私有工单的隔离。外租户有权限查询自身空列表属于范围隔离；精确附件拒绝可以是owner定义的HTTP404纯文本。正式聚合删除后独立回读原工单和消息，不据此宣称独立File物理字节已验证删除。

[普通文件执行器](~/codespace/magicTest/regression/file_cases.cjs)覆盖F049-001/002：原上传回包、token视图和精确ID相互核对，管理GET／DELETE保留原fileSource，下载比对原始二进制。共享入口在写入前以随机不存在路径检查HTTP404，SPA兜底或上游错误立即失败，避免反复遗留文件。原上传已确认时才允许正式精确删除，再分别核对ID、token和字节路由；HTTP500不能算删除后访问通过。未知上传／删除不重放，未解决文件或工单阻断其原创建账号及租户清理。

[公开证据派生工具](~/codespace/magicTest/regression/evidence_derivative.py)仅按仓外私密清单中的原File token替换错误文本中的回显，生成独立目录；先校验原证据摘要，再按依赖顺序重算公开引用，保留原用例判定、数值错误码及处置事实。原始字节须保留在仓外私密目录，公开目录以`redaction-provenance.json`列出原文件与派生文件摘要；不得把派生报告当作未经转换的原输出，不改写或丢弃原失败历史。它不是通用秘密检测器。

[文件边界执行器](~/codespace/magicTest/regression/file_boundary_cases.cjs)覆盖F049-003常规分项。私密编排配置须显式提供实际部署上限`fileUploadMaxBytes`（字节），不能把工具预算当作产品合同；执行0、L−1、L、L+1实际上传，以原token、精确ID和完整流式摘要回读，并逐个正式清理原文件。[流式传输](~/codespace/magicTest/regression/file_stream_transport.cjs)复用原Cookie/Origin，明确multipart实际长度，不重试未知上传，不因文件大而截取验证。上传接纳中断另属专项。

[数据库资源执行器](~/codespace/magicTest/regression/database_cases.cjs)覆盖F047-001/002：通过[独立PostgreSQL夹具](~/codespace/magicTest/regression/postgres_fixture.cjs)验证实际连接、资源编辑、规划容量、状态、精确租户独占、正式存储选项与控制台；异常分支验证规范化重复及真实错误连接。夹具仅使用本机既有镜像ID、确认的Panel网络和无持久卷新容器；不使用生产数据库或直接SQL。原平台记录及placement正式删除后才移除精确容器；原命令结果未知时保留，不盲目重试。placement只有正式目录读取，不能假设存在单项GET。规格字段不代表实际硬限额。

[页面拒绝执行器](~/codespace/magicTest/regression/page_validation_cases.cjs)补齐F067-003/F068-002的草稿子分项：正式check/save配对验证结构、属性和引用拒绝，合法边框0/12、真实图片类型及8MiB公开JSON请求边界。PNG字节、base64与完整UTF-8请求分别计量；大图片证据保留两种表示的摘要，原命令字节留仓外私密台账。仅明确拒绝且原模型/页面/图片/版本完整保持时确认意图；未知结果不重放。正式发布、导入、安装和运行尚未覆盖，整例保持部分验证。

[概览权限执行器](~/codespace/magicTest/regression/profile_cases.cjs)核对F066-002的目录/指标四组合、原账号会话撤权、独立owner计数和正式租户切换中实际旧GET响应迟到。缺内置角色保持受阻；无Panel入口的组合验证明确拒绝页面，不假定概览读取角色同时授予管理入口。

[交付夹具工具](~/codespace/magicTest/regression/delivery_fixture.cjs)仅在已核对完整容器ID、数据根与daemon ID的独立嵌套Docker中，经正式作者发布、构包、申请/批准安装及CAS成员授权准备双实例；凭据和原意图仅存仓外私密目录。已发布定义与安装事实按owner合同保留，本次业务行和可变编辑单独正式清理/恢复，不以删除隔离环境代替原请求终结。[冻结交付](~/codespace/magicTest/regression/delivery_cases.cjs)、[实例名称](~/codespace/magicTest/regression/instance_cases.cjs)和[普通业务写入](~/codespace/magicTest/regression/business_cases.cjs)分别核对ZIP与草稿隔离、条件改名与双实例保持、原普通主体的可靠CRUD/取消/载荷冲突和独立owner回读。回执摘要使用冻结制品摘要，不能混用定义摘要或ZIP传输摘要。

夹具 `resume-bootstrap` 只恢复原隔离身份的 `bootstrap-in-progress` 阶段，且要求原CAS表单、命令、资源台账均为空，也没有任何改密意图。它用于浏览器在首个登录表单发出前受阻的情况；一旦已有登录表单或改密意图，该入口必须拒绝，保留原请求并核对owner结果，不能重放。原错误和夹具身份继续保留。

F031-003使用同一隔离夹具验证包清理预览后新增申请：实际删除必须重新拒绝，原包字节、双实例和成功交付权威保持；新增未批准申请由原请求者按条件版本正式取消及清理。结果未知时保留原意图，不重发命令。F011-002以完整目录前后比对和原模型回读证明非法创建无副作用，避免其他用例合法模型影响断言。上述执行器登记不代表已取得Live通过。

数据库夹具默认施加256MiB/0.5CPU限制。嵌套Docker的cgroup不允许这类控制时，可在私密配置中显式选择`databaseFixtureMode: "isolated-tmpfs-only"`并指定`deliveryFixtureConfig`；工具逐项核对原daemon、数据根和容器身份后，仅使用128MiB tmpfs，不自动降级或重发失败启动。规划容量验证回读原容器实际限制和SQL服务器身份，不将该模式记作宿主资源限制验收。普通文件边界通过`fileUploadMaxBytes`输入已核对的部署内容限额，仍须实际执行L−1/L/L+1并清理原文件。

[成员实例范围](~/codespace/magicTest/regression/application_authority_cases.cjs)使用现有普通功能角色与已登记实例角色，同一组的两名成员分别选择editor/viewer范围；对照CAS原绑定、账号功能角色投影和真实实例读写。范围替换意图先持久化，未知结果不重发；F006-003用独立Panel直接授权和CAS组授权验证并集及分别移除，原直接授权通过原assignment正式退役并核对CAS绑定消失。F006-002另以同一普通账号核对双实例manager/viewer，再替换为精确实例独立read/write/delete角色并真实调用，保留原写回执和完整owner回读；第三实例与真实业务动作证据未齐仍记partial。退役reason必须为空；已证字段拒绝仅在原submission不存在且assignment/epoch不变后另建合法意图，保留原拒绝。未解决直接授权、调试写入或业务行阻断原账号删除。[快照执行器](~/codespace/magicTest/regression/deployment_cases.cjs)调用正式快照入口，验证实际恢复字节、损坏校验、错误根与活跃挂载拒绝，按精确容器身份回收本次夹具。上述注册及源码检查均不能代替本轮Live报告。

[模型基本信息](~/codespace/magicTest/regression/definition_metadata_cases.cjs)用显式元数据DTO及当前定义版本保存名称、标识、图标、前缀和存储声明，区分包的初始协议格式、应用版本文本与发布修订；对原已发布定义另做可变元数据编辑，独立核对双实例/冻结材料不变并条件恢复。[浏览器会话释放](~/codespace/magicTest/regression/session_lifecycle.cjs)在每例结束后将已完成应用页面切至同源只读会话页，停止后台轮询而保留原Cookie和身份，后续owner读写仍使用原会话。恢复入口`--reconcile-proxy-session-refusals true`只核销精确原BFF刷新中拒绝及完整owner目录无残留，不能把一般503、超时或目录暂时为空当作未知写未提交。

离线[模型夹具生成工具](~/codespace/magicTest/regression/model_fixture.py)接收当前`ApplicationModelArtifact`非秘密JSON，经仓外Go overlay调用Runner当前正式`Build`/`Parse`，默认vendor、关闭自动网络下载，核对确定性、回读摘要与可移植身份；输出目录必须新建且位于源码仓外。它不创建发布历史、上传引用或安装，源码成功不能替代部署验收。使用：

```bash
python3 -B ~/codespace/magicTest/regression/model_fixture.py \
  --runner ~/codespace/magicRunner \
  --artifact /tmp/current-nonsecret-artifact.json \
  --output /tmp/new-portable-fixture
```

[第一方回调执行器](~/codespace/magicTest/regression/callback_cases.cjs)在真实BFF首跳Location保留原授权、state和S256材料，每个探针仅改变nonce、state或S256一项进行对照，观察后续浏览器真实授权及回调，正常会话和探针退出均独立回读；已确认失败在原探针正式处置后继续核对其他独立分支，最后汇总断言；未完成分支仍报告partial。原code、state和nonce仅留在仓外私密journal。

[OAuth应用接入执行器](~/codespace/magicTest/regression/oauth_access_cases.cjs)分别执行机密授权码和Endpoint客户端凭据流程，用租户实际discovery/JWKS验证RS256签名、issuer、完整受众、原主体、客户端、空间、授权修订和到期；无Cookie introspection及UserInfo独立回读。身份scope不生成业务授权，机器主体保留原Endpoint及所属账号；未声明流程拒绝与两类原凭据正式撤销配对检查。

[刷新族执行器](~/codespace/magicTest/regression/oauth_refresh_cases.cjs)以普通账号真实授权码及S256、独立机密客户端取得刷新凭据，核对轮换、已消费凭据重放、当前族失效、参数错误不消费、双请求并发和客户端正式撤销。每个原命令在发送前记入仓外私密台账，结果未知不重放；独立无Cookie introspection与CAS审计核对实际主体、租户、客户端及原族。真实到期和CAS真实5xx仍属条件专项。授权码等字符串被证据脱敏器移除，数值业务错误码保留用于诊断。

[审计事件执行器](~/codespace/magicTest/regression/audit_cases.cjs)从真实错误密码、成功登录和退出产生CAS事件，保留原同账号会话；账号角色条件变更和服务正式修改独立回读。平台操作日志入口按其platform/home声明验证平台内服务变更，不通过切换active namespace绕过范围；租户操作日志读取和正式授权变更审计仍有未验证合同，完整用例保持partial。原操作日志按精确服务/动作/原主体/目标空间公开条件查询，限制读取预算；读取原日志，不直接写日志或用令牌撤销事件替代授权变更。

[品牌继承执行器](~/codespace/magicTest/regression/branding_cases.cjs)覆盖F055-001的平台品牌设置、双租户继承、单租户名称/主题/PNG图标覆盖和正式重置；核对独立owner、匿名Host投影及真实登录页。平台原标量使用原资源身份/最新版本条件恢复，保留原素材；未知命令和并发修改阻止覆盖。租户原图片重置后独立读取404。文件、工单和CAS身份清理按原主体会话读取，仅401/code11时重新认证一次，不重放未知业务操作。

[日志留存边界执行器](~/codespace/magicTest/regression/retention_cases.cjs)通过正式双策略合同验证16项越界、清理参数上下界、条件并发、读取失败及缩短取消。共享环境所有测试成功写入均设永久保留0，最后按精确最新版本恢复原策略；未知写不重放，不覆盖其他维护者修改。正数最大天数及实际清理必须使用独立日志owner。

[租户启停台账](~/codespace/magicTest/regression/namespace_availability.cjs)在每次状态写入前持久化精确版本和输入，要求CAS完成回执及独立回读。未知结果阻止重复状态写；已确认CAS事实与入口投影分别核销，显式原运行清理可调用既有入口恢复命令。原资源恢复不执行新用例，也不改变原失败报告。

实体作者的独立回读与API准备、API专用模型断言也在执行前选用owner传输。F018-002仍使用真实浏览器注入原响应丢失。原字段冲突已获明确VersionConflict、但回读被网络变化打断时，可用`--reconcile-authoring-conflicts true --authoring-conflict-evidence <原逐例证据>`配合原私密状态单独核销；[核销工具](~/codespace/magicTest/regression/authoring_conflict_recovery.cjs)要求不可变证据中的原拒绝、原较新保存快照，以及当前精确owner完整回读一致。仅确认原意图并正式清理原对象，不执行用例或重发PUT。

[原清理恢复](~/codespace/magicTest/regression/cleanup_recovery.cjs)以`--resume-tracked-cleanup <原cleanup.json>`恢复原私密台账中的精确资源，须使用原凭据、`--private-state`、同候选`--baseline-health`和新的`--output`；不执行新用例。可选`--namespace-creation-proofs`提供原CAS日志与公开回执，缺原条件版本或终态证明仍开放。`--dns-failure-proofs`仅接受原attempt内逐例文件、SHA256和journal映射，匹配原Host、POST路径及字节长度的ENOTFOUND，再完整读取原模板key不存在；超时和其他网络错误不适用。`--reconcile-retired-credentials true`仅接受原正式父订阅DELETE回包中已有的精确凭据身份，独立确认Panel/CAS终态。所有追加处置保留原unknown和原失败报告，不伪造丢失的成功响应；直接子执行器恢复须由调用方持有同环境互斥锁。

业务记录和成员授权退役记录可能没有通用 `id`；恢复时按完整原记录匹配原清理证据，包括原主体、安装身份、命令及阶段，只移除清理结果外层的 `confirmed`／`error`。必须唯一匹配，重复证据或任意原记录变化都阻止恢复；不为消除歧义生成资源 ID 或排除其他未完成记录。

[模型作者执行器](~/codespace/magicTest/regression/authoring_cases.cjs)覆盖 F015-002、F018-001/002/003 和 F067-004。使用独立应用定义，配对预检只读、实体及脚本绑定原子保存、自增业务主键与定义身份、同版本冲突、功能块阶段拒绝和页面读／预检／写权限。丢失响应由真实浏览器在唯一原保存已返回后中断，再按原定义ID、实体ID、版本及目标摘要独立回读；不重发未知保存。私密台账保留原保存意图，未确认时保留对应定义，不能靠清理父资源掩盖。页面只读成员复用正式发布负责人角色，并与同租户普通成员及跨租户管理员配对；预检校验原实体／字段引用及过期版本，独立回读原模型保持不变。预检结果不证明运行数据权。

[原生编排执行器](~/codespace/magicTest/regression/native_cases.cjs)覆盖 F021-001/002/003、F022-001/002/003：真实向导首组件自动打开、多组件前后切换及草稿保存，空组件门禁与取消无创建，未确认输入跨页签及手动刷新保持、显式保存后步骤往返、跨组件迟到响应和三宽度表格，本地无标签／平台标签镜像读取，缺失镜像重试和旧建议迟到保护。UI 原 POST 通过共享资源台账先记录意图，再精确转发一次，独立 owner 回读后才可清理；回读失败保留原身份。镜像场景需要本地已有 `postgres:17.7-alpine3.22` 、`muidea/magicbase:master` 及 `muidea/magicfile:master`，执行器核对实际镜像身份及标签，缺条件明确受阻，不拉取或构建镜像。元数据与草稿成功不代表实际部署、挂载、入口或运行能力通过。

F026-002配合[原生构建准入台账](~/codespace/magicTest/regression/native_admission.cjs)，先用真实本地镜像完成合法预检，再验证缺组件依赖、缺本地镜像在预检与正式构建中的精确组件拒绝；缺镜像草稿还执行正式修订预检和发布拒绝。完整包目录、原草稿和完整修订目录均独立核对。发布请求中的正例构建digest仅用于非空信封对照，只有先命中组件错误才通过，不将其声称为无效修订的匹配发布digest。实际命令写前记台账；未知、非目标拒绝或意外成功保留原身份，阻断原父定义删除，不重放或猜ID清理；不代替成功发布、安装和恢复验证。

品牌布局执行器通过本轮临时租户的公开品牌owner设置长名称，独立核对Host解析后的品牌与实际解码的图标／登录素材，覆盖三宽度登录控件遮挡、Panel与Portal口径。写入前登记原意图；仅沿正式重置及独立回读结束，不修改平台全局品牌或上传替代素材。执行器存在不等于Live已通过。

[页面作者执行器](~/codespace/magicTest/regression/page_author_cases.cjs)覆盖 F067-002、F068-003：真实未保存离页确认、原输入保持、同版本双作者冲突，以及一条原页面保存提交后丢失响应、独立完整回读和界面只读恢复。图片通过真实上传控件独立保存；取消页面保留图片，已引用图片的界面与owner删除均拒绝，删除确认前新增引用会再次阻断；清除全部引用并保存后通过正式成员命令释放精确原字节。所有原写命令先记台账，未确认时阻断父定义清理；不重发未知保存，不代替发布/安装/运行场景。

原意图核销还支持互斥的 `--reconcile-rejected-definitions true` 和 `--reconcile-authoring-writes true`，沿用原 `--private-state`、凭据与基线，并使用新的输出目录。前者仅接受创建前模型包前缀校验的精确拒绝回包、原主体／UUID及完整目录不存在证明，不处理未知创建；后者仅接受原页面／成员 PUT 成功回包、原定义身份、确切新版本与完整内容的独立回读，不处理无回包或内容已改变的写入。两者均不执行新用例、不创建替代夹具、不重放业务命令；原报告保留，核销及后续正式清理另存新 attempt。所有恢复模式须显式选择且互斥，错误参数在浏览器启动前拒绝。

[分类名称执行器](~/codespace/magicTest/regression/catalog_cases.cjs)覆盖 F051-001/002，核对分类创建与改名、实际应用/服务分类展示、独立File标签保存/回读/详情展示，以及父子目录、同名不同身份、租户隔离，以及改名／删除目录后应用与服务原名称字符串保持。分类目录不是跨资源稳定ID关系，不推导在用删除保护。File标签不创建分类目录；原文件和分类正式清理后才汇总展示断言，失败仍保留原证据。

[实体作者浏览器执行器](~/codespace/magicTest/regression/definition_browser_cases.cjs)覆盖 F012-001/002/003、F013-003 和 F016-002：实际目录及字段分页、父节点明细、迟到响应、空态与原实体删除后的失效选择，390／1366／1920 三宽度长内容及操作，字段弹窗取消／确认／冲突，脚本引用保护及草稿取消。字段确认后仍需保存原实体才会落库；模型草稿保存只更新显式提交的实体，省略实体不代表删除。UI 的原 PUT／DELETE 在转发前记录台账，独立 owner 回读确认后才能清理定义，错误回包或回读失败均保留原现场。

已成功返回的原实体 DELETE 若因后续回读中断而未核销，可将 `standard.cjs` 的 `--private-state` 指向原状态、`--output` 指向新的证据目录，提供常规必需的凭据及健康基线参数，并显式传入 `--reconcile-authoring-deletions true`。该模式核对原主体、原定义及原删除回包，只读确认同一实体缺失，再通过原资源台账正式清理原定义；不执行用例或创建替代夹具。未知 DELETE、缺原回包或身份不符仍保持开放。该处置不改写原失败报告，也不处理租户未知删除。

租户正式删除后，BFF可能拒绝再查询该租户子资源，403不能作为不存在的证明。执行器保留子身份，结合原租户DELETE回执、公开持久退役记录和独立目录不存在证明，核对已审查的聚合清理合同；不声称逐个删除后仍可读取子资源。只读`--reconcile-cleanup`模式向唯一新attempt追加原失败资源的处置证明，不重放DELETE、不修改旧记录，也不会回落为常规执行。

注册夹具在新租户创建后等待已发布入口生效：每次读取精确原租户身份、版本、启用及有效期，再匿名GET会话入口；仅404允许最多5次一秒等待，必须得到未认证响应才进入用例。其他响应或持续404直接失败，不重发写命令，不改变禁用／过期租户统一404断言。

[公开首跳探针](~/codespace/magicTest/regression/public_probe.cjs)在原浏览器页面使用原会话 Cookie，只读同源 GET；禁止自动跳转，记录 Chromium 原始首跳状态及 Location。301／302／307／308 后最终404不能满足统一404断言。普通登录流程仍按正式跳转执行。

[负例写入台账](~/codespace/magicTest/regression/negative_mutations.cjs)在 F051 创建分类及 F055 伪造目标提示／跨 Host 写平台品牌前持久化精确意图；意外成功也先登记返回身份，再抛出用例失败。分类按原返回 ID、完整目录和 owner 回读确认后清理；平台品牌只对本次已确认的精确资源ID与版本执行条件 PUT，原无覆盖时发送空标量并保留素材。响应丢失、版本冲突、分页不完整及缺少同一命令终态证明保持 cleanup 开放，不盲目重放，不以删除测试租户代替全局品牌恢复。状态目录须保留，禁止直接更改其 phase 制造 allCleaned。

工具自身回归（隔离 HTTP／真实 Chromium 与 handler 夹具，不计产品 Live 通过）：

```sh
node --test regression/*.test.cjs
python3 -B -m unittest regression.test_run_standard
```

### 常规分项浏览器执行器

[执行器](~/codespace/magicTest/regression/standard.cjs)读取权威目录，为所选常规分项逐项输出结果；[具体断言](~/codespace/magicTest/regression/standard_cases.cjs)只登记已有实现，未覆盖全部步骤、缺少夹具或没有执行器的分项明确受阻。它仍不是已交付的完整常规套件，不能以已注册handler数推断完整覆盖。

[身份与模板断言](~/codespace/magicTest/regression/identity_cases.cjs)使用正式登录／首次改密表单、错误密码提示、CAS会话与授权目录及BFF精确退出。CAS OAuth管理接口由同租户真实审计账号回读；平台治理账号不能代替租户本地OAuth身份。退出保留原BFF凭据副本验证服务端失效，并核对另一独立会话保持；该结果只证明当前会话退出。模板验证包含真实授权操作、委派上限、来源权限并集、撤回和在用删除门禁。

登录布局及共享拒绝登录分支统一使用[登录就绪工具](~/codespace/magicTest/regression/login_readiness.cjs)，有界等待真实 CAS 表单与明确凭据错误反馈；`networkidle` 不代表初始化或交互就绪。失败时在关闭上下文前采集路径、状态、耗时、可见性和截图，不记录查询参数、请求体、凭据或浏览器错误正文；取证失败保留原异常，不重发认证命令。错误密码、注册审核、密码重置与账号禁用共用该门禁，隔离延迟DOM测试和真实认证回归分别记账。

```sh
node ~/codespace/magicTest/regression/standard.cjs --dry-run true
node ~/codespace/magicTest/regression/standard.cjs --dry-run true --cases F001-004,F065-003
```

实际执行必须传入`--credentials`、`--private-state`、`--output`、`--baseline-health`；可用`--case`或`--cases`筛选分项。凭据为仓库外权限受限的JSON文件，字段为明确HTTPS的`origin`、原账号所在`namespace`、`account`及`password`；秘密和浏览器状态不得提交。`--baseline-health`使用报告工具采集的当前部署结果。`--output`指向应用资料仓库当前登记运行下的新执行目录，不能覆盖既有结果；已完成清理的私密fixture状态不再复用，新执行另用私密状态目录。正常退出仍需核对逐例结果及cleanup证据，退出码2表示未全部通过或清理未完成。

长时间 Live 执行的私密恢复状态须保存在仓外持久目录，避免 WSL／宿主重启清空 `/tmp` 后丢失原请求日志。统一入口使用 Python 的临时目录机制，可在启动进程前将 `TMPDIR` 指向新建且权限为0700的持久目录，例如 `~/.local/state/magicTest/t`；该路径应足够短，避免 Chromium 的 Unix socket 超过系统路径长度限制。隔离环境的数据库、配置、夹具与恢复状态均需使用持久宿主 bind source；容器内的 `/tmp/platform-executor-*` 只是隔离工具要求的挂载目标路径。重启后缺失的原状态不能靠新样本或重建空目录代替，也不能据此声称已正式清理。

默认复用`~/.local/bin/playwright`对应的Chromium；首次准备执行`~/.local/bin/playwright install chromium`。可用`--chrome`显式指定其他已安装浏览器。当前本地环境使用`*.local.vpc`映射到本机，其他部署须先适配浏览器解析配置，不能直接套用本机网络假设。专项不由此入口触发。

F003-001 先证明目标受保护入口可访问；租户不可用时，访问该租户的请求统一返回HTTP 404，不能以403或HTTP200中的JSON NotFound代替。执行器对页面、BFF、CAS公开注册、发现文档、通知和未知路径追加代表性GET矩阵；该矩阵不代替自然到期／删除后或其他HTTP方法的独立验证。404只证明入口关闭。重新启用后仍须验证普通用户及管理员原会话被认证拒绝，再通过新登录证明访问恢复，同时核对panel两个独立原会话与另一租户原会话持续有效。重新发布入口时，登录页可能短暂返回404；执行器仅对同一个`/login/cas`页面最多重读五次，不重放OAuth或业务命令。登录表单缺失时保存脱敏页面状态及截图，不把等待超时直接判作认证缺陷。

账号范围用例使用专用目标账号，配对验证范围内修改与范围外拒绝，不修改后续用例的原主体。脚本库只读夹具复用已有应用发布负责人角色；分类只读夹具必须来自owner正式声明的可分配角色，不能用普通无权限成员、管理员或临时伪造Role代替。服务权限夹具经正式登记、发布、普通成员订阅和owner回读后再验证编辑／删除拒绝；该用例不调用上游，不能推导服务调用链通过。品牌用例先证明租户合法修改成功，再核对伪造空间提示仍局限本租户、原会话访问实际全局Host被拒绝及全局独立回读不变；不把合法的租户内保存判作越权。

## 项目定位与开发边界

本仓 `AGENTS.md` 直接列出项目定位、公开能力、职责边界及开发验证要求，单独检出即可执行；跨项目配合使用项目名和 Git 地址识别。先修改事实 owner，再同步消费者和交付材料。平台架构长文作为补充设计依据，不是读取本仓规则的前置依赖。下文日期化记录保留各批范围，不代表当前部署全部验收通过。

`magicTest` 当前已经包含多套不同目标的测试代码，但入口分散在 `cas / file / panel / platform / vmi` 各自目录中。  
本说明的目的不是重写现有测试，而是按“测试目标”重新整理现有资产，方便后续按需求快速选择测试入口。

---

## 1. 测试目标分层

当前测试代码按目标可分为 8 类：

| 测试目标 | 说明 | 主要目录 |
| --- | --- | --- |
| `foundation` | 会话、请求封装和测试基础设施自身验证 | `~/codespace/magicTest/session` |
| `auth` | CAS 认证、账号、角色、命名空间、注册审核 | `~/codespace/magicTest/cas` |
| `ui` | 真实浏览器层面的注册、登录与页面入口验收 | `~/codespace/magicTest/ui` |
| `file` | 文件服务基础能力验证 | `~/codespace/magicTest/file` |
| `platform-core` | `magicBase` 平台核心接口回归 | `~/codespace/magicTest/platform` |
| `panel-api` | `magicPanel` / `portal` 控制面与消费面接口回归 | `~/codespace/magicTest/panel` |
| `business-scenario` | 业务应用级场景与模块回归 | `~/codespace/magicTest/vmi` |
| `load` | 并发、热点、老化等压测入口 | `~/codespace/magicTest/vmi` |

这次整理后的原则是：

- 不打散现有稳定目录和 runner
- 在根目录提供统一导航和聚合入口
- 按“测试目标”而不是“历史目录名”来找测试

---

## 2. 当前统一入口

新增根层入口：

- [run_tests.py](~/codespace/magicTest/run_tests.py)
- [test_catalog.py](~/codespace/magicTest/test_catalog.py)

推荐先用它做导航和执行。`cas/platform/panel/vmi` 各子目录里的 `run_tests.py` 保留给高级调试，不再作为日常主入口。

### 2.1 查看测试目标

```bash
cd ~/codespace/magicTest
source ~/codespace/venv/bin/activate
python3 run_tests.py --list-goals
```

### 2.2 查看全部套件

```bash
python3 run_tests.py --list
```

### 2.3 查看环境配置

```bash
python3 run_tests.py --list-envs
```

当前内置了两类常用环境：

- `panel-local`：`panel/cas` 默认指向 `panel.local.vpc`
- `autotest-local`：`platform/file/vmi` 默认指向 `autotest.local.vpc`

### 2.4 查看常用执行预设

```bash
python3 run_tests.py --list-presets
```

### 2.5 查看某个目标下有哪些套件

```bash
python3 run_tests.py --list --goal panel-api
python3 run_tests.py --list --goal load
```

### 2.6 按预设执行

```bash
python3 run_tests.py --preset auth-smoke
python3 run_tests.py --preset auth-ui
python3 run_tests.py --preset panel-smoke
python3 run_tests.py --preset platform-smoke
python3 run_tests.py --preset business-smoke
python3 run_tests.py --preset load-hotspot
python3 run_tests.py --preset business-prepare-users
```

如果要显式切换环境配置：

```bash
python3 run_tests.py --preset panel-full --env-profile panel-local
python3 run_tests.py --preset business-full --env-profile autotest-local
```

### 2.7 按目标执行

```bash
python3 run_tests.py --goal auth
python3 run_tests.py --goal ui
python3 run_tests.py --goal panel-api
python3 run_tests.py --goal load
```

多数情况下不需要再单独设置 `MAGICTEST_*_BASE_URL`。根入口会按套件自动应用默认环境：

- `cas/panel` 默认用 `panel-local`
- `platform/file/vmi` 默认用 `autotest-local`

如果当前 shell 已经显式导出了环境变量，则默认不会覆盖；只有传入 `--env-profile` 时才会强制改用指定环境。

### 2.8 执行单个套件

```bash
python3 run_tests.py --target cas-registration
python3 run_tests.py --target portal-registration-ui
python3 run_tests.py --target panel-service-api
python3 run_tests.py --target vmi-hotspot
```

### 2.9 只看命令，不执行

```bash
python3 run_tests.py --goal panel-api --dry-run
python3 run_tests.py --target vmi-aging --dry-run
python3 run_tests.py --preset panel-smoke --dry-run
```

---

## 3. 按需求选测试

### 3.1 我要验证认证、登录、注册、审核

选：

- `cas-api`
- `cas-registration`

命令：

```bash
python3 run_tests.py --preset auth-smoke
```

如果要补充真实浏览器层面验收，使用：

```bash
python3 run_tests.py --preset auth-ui
```

`auth-ui` 依赖 Playwright。未安装 Playwright 时测试会明确跳过，不影响 API 回归。

### 3.2 我要验证平台核心接口是否稳定

选：

- `platform-core-api`

命令：

```bash
python3 run_tests.py --preset platform-smoke
```

### 3.3 我要验证 panel / portal 接口主链

选：

- `panel-runtime-api`
- `panel-governance-api`
- `panel-page-api`
- `panel-service-api`

命令：

```bash
python3 run_tests.py --preset panel-smoke
```

### 3.4 我要验证业务应用功能

选：

- `vmi-tenant-user-prepare`
- `vmi-quick`
- `vmi-module`
- `vmi-scenario`

命令：

```bash
python3 run_tests.py --preset business-smoke
python3 run_tests.py --preset business-full
python3 run_tests.py --preset business-prepare-users
```

如果要在指定租户列表内自动创建多用户测试账号：

```bash
python3 run_tests.py --target vmi-tenant-user-prepare --env-profile autotest-local
python3 run_tests.py --preset business-prepare-users --env MAGICTEST_TENANT_TARGETS=t001,t002 --env MAGICTEST_TENANT_USER_POOL_ENABLED=true --env MAGICTEST_USERS_PER_TENANT=3
```

### 3.5 我要做并发 / 热点 / 老化压测

选：

- `vmi-concurrent`
- `vmi-hotspot`
- `vmi-aging`

命令：

```bash
python3 run_tests.py --preset load-hotspot
python3 run_tests.py --target vmi-concurrent
python3 run_tests.py --preset load-aging
```

---

## 4. 现有目录的职责

### `~/codespace/magicTest/session`

只放测试基础设施和 `MagicSession` 相关验证，不承载业务接口回归。

### `~/codespace/magicTest/cas`

只放认证与注册治理相关测试：

- 登录
- refresh
- 账号 / 角色 / 端点 / 命名空间
- 注册模板 / 注册策略 / 注册审核

### `~/codespace/magicTest/ui`

只放真实浏览器层面的页面链路验收：

- 注册页加载
- 注册申请提交
- 审核后登录
- 登录后进入 portal 首页

当前 `ui` 测试是可选增强套件，依赖 Playwright；日常接口回归仍以 `~/codespace/magicTest/cas` 和 `~/codespace/magicTest/panel` 为主。

### `~/codespace/magicTest/file`

只放 `magicFile` 相关基础回归。

### `~/codespace/magicTest/platform`

只放 `magicBase` 平台核心接口：

- application
- block
- entity
- value
- operation_log
- totalizator

### `~/codespace/magicTest/panel`

只放 `magicplatform` 当前控制面 / 消费面接口回归：

- apps runtime
- 生命周期
- 定义与订阅
- profile / system context
- 服务访问主链

### `~/codespace/magicTest/vmi`

只放具体业务应用级验证与压测：

- 模块测试
- 场景测试
- 多租户
- 并发
- 热点
- 老化

---

## 5. 现阶段建议

当前这次整理后，后续新增测试代码建议遵守这条规则：

1. 先确定测试目标
2. 再决定放到哪个目录
3. 同步在 `test_catalog.py` 注册
4. 如果是新大类，再补到本 README

不要再新增“只能靠人记得住”的零散入口脚本。

如果某类测试已经形成稳定使用路径，优先补：

1. `test_catalog.py` 里的 `TestTarget`
2. 根入口的 `preset`
3. 本 README 的使用示例

不要优先新增新的子目录 `run_tests.py`。

---

## 6. 相关文档

- [panel/README.md](~/codespace/magicTest/panel/README.md)
- [platform/README.md](~/codespace/magicTest/platform/README.md)
- [vmi/README.md](~/codespace/magicTest/vmi/README.md)
- [session/USAGE.md](~/codespace/magicTest/session/USAGE.md)

正式服务回归由[服务图执行器](~/codespace/magicTest/regression/service_graph.cjs)维护原订阅requestId和owner回执，经正式发布、订阅、凭据及Gateway调用本机受控HTTP上游。真实上游收到的随机请求标识作为独立转发证据，拒绝分支同时验证未到达上游；测试上游在本轮资源清理后关闭。未知申请／撤销不重发，未确认子记录阻断父服务及租户清理，凭据不归档。

未知Host和证书边界由[入口隔离执行器](~/codespace/magicTest/regression/ingress_cases.cjs)只读验证：完整CAS目录确认随机名称不存在，公共浏览器入口不得回落默认租户；使用实际入口证书链，在严格证书名校验下核对不匹配Host于HTTP前失败，不修改证书或部署。

实例只读调试 F017-003 使用普通作者已有功能角色和仅实例A查看范围，先真实查询，再验证吞掉更新/删除错误仍被沙箱拒绝，以及实例B的精确数据读取门禁；独立回读两实例原记录并可靠删除。本入口位于[脚本执行器](~/codespace/magicTest/regression/script_cases.cjs)，未知调试写入保留原记录和原主体。

模型包完整性 F020-002 由[制品执行器](~/codespace/magicTest/regression/artifact_integrity_cases.cjs)验证：下载原冻结包，重新打包CRC有效但内容或校验摘要损坏的ZIP，经真实私有上传引用导入，要求命中精确checksum拒绝；错误安装摘要必须在原包绑定处拒绝，完整包／申请／任务／安装目录及原ZIP保持。原上传和命令预写台账，未知不重放，未确认补偿保持开放。File补偿以Panel正式拒绝回执证明，不宣称独立物理字节回读。

包清理 F031-002/003 接受正式HTTP409/code21未完成申请拒绝。若旧工具留下原申请，只能通过 `--resume-tracked-cleanup` 配合 `--package-refusal-proofs`，核对原cleanup／case的SHA、原journal、账号、拒绝及历史／当前ZIP和原申请，再正式取消与cleanup；不重发原包DELETE，保留原失败。

安装申请及审批由[交付决策执行器](~/codespace/magicTest/regression/deployment_review_cases.cjs)验证同意图重复确认、独立实例申请、原请求撤回、两名不同审批人的同版本并发，以及真实running期间的撤回／清理拒绝。只有实际观察到目标执行窗口才算通过；独立读取申请与任务跨过完成时刻时先确认终态。新模型实例通过正式destroy卸载并读取Schema回收；成功交付和卸载回执按owner合同保留。原失败可沿 `--resume-tracked-cleanup` 核对原命令及原资源后处置，不重放审批或卸载。

内置包权限与申请准入由[原生提供方执行器](~/codespace/magicTest/regression/native_provider_access_cases.cjs)核对默认空间和运维权限的双门禁、普通作者原生预检正控、Base/Gateway真实包的读取／申请／删除拒绝、非法目标空间和模型包摘要。HTTP401只有同时命中精确code5权限文案并通过独立会话确认时才属于目标拒绝；一般认证失败不能充当通过。缺少已有内置镜像或配置配套时保持部分验证，不构建产品镜像补造前提。

原生包重复交付由 `~/codespace/magicTest/regression/native_package_cases.cjs` 覆盖 F026-003：确认原构建后主动重复同输入，逐字段核对原包、完整目录及 ZIP；修改组件 Env 和应用发布版本后生成独立摘要，分别清理新包并证明旧包保持。未知构建不作为重复场景重发，恢复绑定原命令和回执。初始运行格式仍为 v1，应用发布版本变化不递增格式标识。

F026-001 使用同一原生包执行器完成多组件预检、构建、下载、ZIP 内置图标／应用发布版本／组件依赖回读，再由 File `application-deployment-package` 上传引用进入正式导入。相同摘要的导入必须返回原包；上传或导入结果未知时保留原 File 意图及包，禁止重发。文件型图标与安装运行分别由对应专项场景覆盖。

F038-003 由 `~/codespace/magicTest/regression/service_cases.cjs` 使用两个真实已安装实例的能力，分别让其他租户服务管理员执行正式汇聚。先证明请求者自己的服务写权限，再核对精确 scoped NotFound、原主体会话和源／请求者／另一租户完整治理目录保持；认证、权限和依赖错误不能替代能力归属拒绝。未知汇聚保留原命令。

F027-001 由 `~/codespace/magicTest/regression/installation_request_cases.cjs` 使用仅发布／申请权限的普通账号提交模型及真实原生包申请，省略实例标识、名称和承载选择；核对自动生成身份、原申请者及审批前无执行事实，再按原账号、原请求条件版本撤回清理。原申请者秘密只保留仓外私密状态；未知命令保留账号和原意图，不改由管理员续办。

[原生配置边界执行器](~/codespace/magicTest/regression/native_validation_cases.cjs)覆盖 F023-002 的13种端口、挂载及敏感字面量输入，逐项走草稿校验、预检和真实构包拒绝入口，独立确认原包目录保持。敏感探针在证据脱敏前核对原始响应，返回错误同时回显明文仍判失败，不能以报告脱敏代替产品响应安全。

[原生实例运行执行器](~/codespace/magicTest/regression/native_runtime_cases.cjs)覆盖 F023-001/003、F030-001、F031-001、F061-001：正式构包、申请/批准安装，按owner回执容器ID只读核对真实参数、挂载文件和HTTPS入口；同包双实例核对名称、网络别名与持久路径隔离，逐个卸载核对另一实例保持。F031-001在实例仍运行时按正式预览删除来源包，核对原实例、持久数据、HTTPS服务和任务身份保持。F030-001新建启动退出码23的实例，必须实际命中该失败诊断，随后沿原任务正式终止，独立确认容器不存在，再经允许的包清理终结原任务与申请；原失败历史保留。F061-001核对实际双实例的功能分类目录、生成配置与挂载，以及核心services目录投影保持；不读取凭据内容，不把未使用目录的按需创建当缺陷。原生卸载经平台审批，容器独立确认消失，卷与执行回执按正式合同保留。

[安装身份及版本执行器](~/codespace/magicTest/regression/lifecycle_admission_cases.cjs)覆盖 F034-002：对原双模型实例的错误摘要、旧安装版本及原部署任务的旧版本分别调用正式命令，只接受精确阶段错误；独立核对两实例、请求、任务、分配回执和尝试次数保持。每次负例先持久化原意图，未知响应只回读，不能重发或猜测清理。该执行器不伪造损坏回执或代替受控故障专项。

[脚本库复用执行器](~/codespace/magicTest/regression/script_library_cases.cjs)覆盖 F016-001：完整文件库新建、编辑与复制，已有库和直接定义绑定、必填0/false及输出映射保存重进，真实调试和新修订发布，修改作者源码后核对冻结程序与副本保持。新发布定义和修订仅在专属隔离部署建立并作为正式夹具保留；不删除已发布事实，也不声称运行落库。

[部署任务进度执行器](~/codespace/magicTest/regression/deployment_progress_cases.cjs)覆盖 F029-001：分别运行真实模型与原生部署，独立读取原任务阶段、尝试、版本与最终安装回执；缺少真实中间阶段采样时记受阻。模型正式销毁，原生经平台审批卸载并保留卷与持久回执。

[多页成员目录执行器](~/codespace/magicTest/regression/member_directory_cases.cjs)覆盖 F005-004：独立租户六个普通成员、模板与绑定跨页回读；已知绑定变化后丢弃在途聚合并从头读取。浏览器第二页受控取消/失败不能返回完整目录，之后独立确认owner不变；不宣称事务快照或服务端依赖故障注入。

[冻结页面分页执行器](~/codespace/magicTest/regression/page_runtime_cases.cjs)补充 F069-002 已安装列表：12条原可靠写入形成多页，正式源结果逐主键对照独立业务读取；游标跨主体／安装、格式／字节／页预算拒绝后完整数据保持，并核对真实安装渲染。冻结夹具仅含主键排序，筛选交集、选择器、复合排序及自然到期仍待独立验证，整例保持部分验证。

该执行器同时补充 F069-004 当前账号读取权限：通过正式作者、发布与安装建立独立显式视图双实例，逐键对照独立业务读取，验证未授权、viewer范围、撤权及错误安装摘要／代际。账号授权经 CAS 模板，安装管理授权经 Panel 原请求，业务行通过可靠命令清理，再正式撤回授权并销毁本次安装。缺少 Endpoint、聚合／选项／标签及迟到响应证据时保持部分验证。新显式视图夹具不覆盖原空视图页面已接受但运行读取失败的记录。

[冻结聚合执行器](~/codespace/magicTest/regression/page_aggregate_cases.cjs)补充 F069-003 的计数、分组、无分组数值均值及有效样本数。使用正式发布和安装的独立显式视图，以可靠写入的0—3值及逐主键业务 owner 回读对照聚合，核对空态、聚合分页参数拒绝和正式删除后的结果。整数及小数以字符串和精确分数比较，不经浮点转换。sum/min/max和带条件均值按当前能力报告只验证只读预检拒绝，不尝试绕过发布；UTC桶、窗口边缘、显示精度／时区、组数／点数预算及取消仍开放，整例保持部分验证。

显式视图夹具先执行正式页面只读预检并确认原草稿不变，再保存和发布；主键只读约束来自本次作者模型，冻结页面对照完整作者内容及正式应用身份。安装清理逐项保持资源事实、摘要和当前条件时间戳，只允许读取投影中的部署版本单调推进。未知保存及响应丢失保留原身份，通过正式回读对账，不重放写入。

独立数据写权限的原请求遭页面runtime读取门禁拒绝时，可用 `--reconcile-matrix-write-refusals true` 对账原私密状态。只接受精确原拒绝、原实际调用者完成回执不存在、原创建回执和完整原行无变化的组合证明；不重发原更新，不额外发权，不修改原失败报告。缺任一证明则保留原账号与资源。

[安装摘要执行器](~/codespace/magicTest/regression/installation_summary_cases.cjs)补充 F034-001：公开安装回执与实际运行身份、独立存储目录核对后，在三种宽度读取双模型实例的摘要，验证保存回执不代表实时健康；受控原生启动失败按原申请、任务、Docker组件身份核对诊断并正式处置。启动失败未生成安装记录时，失败安装摘要与服务端下一步建议仍未验证，不能用任务诊断代替整例通过。

[工单反向生命周期执行器](~/codespace/magicTest/regression/feedback_cases.cjs)补充 F054-004：正式删除带消息及私有附件的原工单，确认原工单/消息不存在、原附件在提交者和管理方入口不可读；向原已删除工单发起的新上传须被 owner 拒绝。相同字节、不同消费者绑定的另一工单与附件保持完整。上传响应未知时重新保持原资源开放，不重复原 DELETE 或上传。聚合删除确认不代表独立 File 物理字节回收证明，单引用共享、清理中断和此前已派发上传的迟到窗口仍需分别验证。

[正常分派执行器](~/codespace/magicTest/regression/runtime_placement_cases.cjs)补充 F035-001：新模型申请显式选择公开选项中的 Base/Gateway，对照审批冻结的解析身份与注册版本、原任务和安装回执；通过普通账号的当前安装围栏执行可靠读写、独立业务回读及删除，再正式撤权并销毁本次安装。控制观察游标允许按合同前进，注册配置和原双实例保持；承载交接、快照异常和重启故障注入归各自用例。

[冻结页面数据源执行器](~/codespace/magicTest/regression/page_source_cases.cjs)补充 F069-001：独立发布并安装显式视图，以普通账号读取 list/detail/options 并逐键对照业务 owner；在三种宽度验证实际列表和详情入口，再验证未发布作者修改、源包正式清理均不改变安装内冻结页面与数据源。源包删除先记录精确原意图，再核对允许清理的预检和公开目录缺失，未知结果不重发；已发布定义和修订显式保留。独立实体 fallback 和 UI 选项选择仍缺覆盖时，整例保持部分验证。

[失败模型原身份处置工具](~/codespace/magicTest/regression/model_failure_cleanup.cjs)仅在原审批、请求、任务、来源包及唯一失败安装完整配对后执行正式销毁；传输包摘要与安装制品摘要分别核验。独立确认原 Schema 回收，再按原任务版本终止，核对原请求/任务配对终态、尝试预算及其他安装保持。未知响应不重发，失败历史和持久回执保留；工具测试与实际处置分别记账。

[实体能力开关执行器](~/codespace/magicTest/regression/capability_switch_cases.cjs)覆盖 F019-001 的七实体总开关及五种逐操作开关矩阵：正式发布/安装后，对照冻结实体键、安装回执和完整能力目录，核对所有启用组合、所有关闭组合及未发布修改隔离；正式销毁原安装后确认能力退役和其他来源目录保持。发布实体数据库 ID 按正式合同归零，以冻结实体键和运行回执配对，不借用作者可变 ID。真实生成服务调用及重新发布关闭仍未覆盖时，整例保持部分验证。

[页面作者主流程执行器](~/codespace/magicTest/regression/page_author_cases.cjs)补充 F067-001：通过真实设计控件验证标题／路由、撤销／重做、文本和组件排序，发送一次原条件保存并核对完整owner内容，再关闭、重新打开。正式只读预检、发布和双实例安装后，以普通成员核对冻结页面及安装身份，作者未发布修改不得改变原安装。UI初始页面创建、导航／动作绑定和正式ZIP导入消费者未覆盖时仍记部分验证。

能力目录按原主体所在租户和安装的公开runtimeApplication投影配对，不要求公开能力DTO没有提供的namespace字段；详情源不发送分页字段。原已接受页面保存如仅将详情源pagination:null省略，恢复须保留原载荷和回执，精确匹配当前合同表示及完整独立owner内容／版本，不能推广为任意字段归一化或重放未知保存。

已正式清理源包的成功安装申请，读取时会转为packageRemoved历史投影，仅保留冻结来源摘要；它与源包存在时的展示对象不同。执行器须同时证明原源包删除已确认、完整原请求除该正式展示投影外保持、原任务不变、原修订不变、精确安装及Schema正式退役，才能完成清理核验。不得忽略整个modelPackage对象、重放卸载或把历史展示当可安装制品。

页面作者组件选择采用真实键盘激活并核对aria-pressed，同时记录原组件中心点的只读命中几何。鼠标被操作浮层遮挡的原观察保持开放；键盘完成作者主链不能计为鼠标交互修复，不使用force click或修改页面状态绕过。

[完整业务集合执行器](~/codespace/magicTest/regression/business_collection_cases.cjs)补充 F036-001/002：可靠标量写入后，普通主体的完整列表和逐键详情逐字段对照，分别遍历 offset、主键游标及冻结复合排序／筛选；同名记录和排序同值跨页不得遗漏或重复。游标拒绝必须命中正式阶段并保持完整原数据。关系、非保护普通写、完整类型及自然到期缺少证据时保持部分验证，不降级可靠写入。

[安装图标执行器](~/codespace/magicTest/regression/installed_icon_cases.cjs)补充 F050-001/002：真实文件输入及条件保存、正式模型 ZIP 上传导入、manifest／checksum／原图片字节、双实例普通成员 Portal／Apps 和真实图片解码分别核验。未发布图片修改及正式源包移除不得改变原安装；清包前在授权完成后独立读取完整安装快照，清包后全字段比较。原 UI 接受保存的确认与图片成功分开，空值保存不能算上传成功；未知命令仅按原身份回读，不重放。原定义、修订和 File 物理清除的证明范围分别记录。门户完整应用目录超过预览上限时，通过实际“查看全部”按钮及独立目录总数进入完整列表，等待原应用卡片可见后检查唯一图片消费者；不将预览未展示目标视为图片失效。

[依赖准入执行器](~/codespace/magicTest/regression/dependency_cases.cjs)补充 F024-002：先以真实本地镜像建立合法预检，再核对缺失组件依赖在草稿、预览和实际构包的精确拒绝；复用正式存储审批执行器核对停用及范围外专属存储，保留原请求、完整目录和正式清理证据。登录错误、摘要错误及无关状态冲突不能替代目标依赖拒绝。

仅依赖已发布隔离夹具的执行器须明确声明 requiresOnlyDeliveryFixture，且全体所选项均符合、无通用主体要求、当前资源／夹具为空时，才跳过通用租户准备；仍先独立核对隔离 daemon 和正式修订／包。混合选择或已有原资源继续使用原准备／恢复门禁。减少无关夹具创建不关闭任何历史失败租户。

[页面外观执行器](~/codespace/magicTest/regression/page_appearance_cases.cjs)补充 F068-001：条件保存标量外观、清除并恢复覆盖，核对透明／六位／八位颜色和0／12px边框；真实作者三种预览、正式ZIP导入、双实例普通成员三宽度渲染及未发布隔离分别留证。实际背景控件已配对清空、条件保存和恢复；图片背景及失败回退、大屏未覆盖时保持部分验证，不以共享渲染器源码测试代替真实DOM。

成功部署任务的 executionResumeMode 是随当前时间计算的只读诊断；清理核对仅允许该字段在正式枚举内变化，其余完整任务事实、版本、尝试数及回执保持精确比较。撤权执行明确返回原事务未应用时，只能按原持久意图、原key／epoch及当前原版本调用正式 resumeOriginal；恢复响应未知不再次发送。被未完成授权操作明确拒绝的卸载须先证明完整原安装和请求保持，再完成原撤权，后续清理使用当前owner条件。未产生安装回执的失败模型，只有原owner正式终止、独立成对任务／请求回读和完整安装目录核对齐备才能结束；目录缺失本身不算清理，不宣称Schema回收，已有安装仍必须取得正式卸载证明。

升级或存储恢复移交后，Panel 的历史安装读取不含 `deploymentVersion`，该字段只投影到当前安装。历史前驱必须与原完整历史快照精确一致且均不含该字段；当前继任仍核对正式部署版本，恢复后的版本必须大于原保留点版本。安装关联、存储绑定、CAS 撤销／恢复意图、原业务行处置和 Schema 回收证明继续完整比较，不能将历史读取当作当前条件写的版本来源。执行器断言修正不终结原失败资源，原身份仍须独立回读和正式处置。

[安装页面图片执行器](~/codespace/magicTest/regression/page_image_cases.cjs)补充 F068-004：真实PNG/JPEG包成员、ZIP索引与独立checksum、正式导入和双实例普通主体精确字节读取；错误安装身份/资源键/额外选择器、未发布资源替换、正式源包移除和原实例撤权分别核验。公开读取使用注册后规范化的 `/apps/application/assets/{key}`，真实页面保持原消费者请求以暴露合同偏差，不在测试中改写路由制造渲染成功。DOM真实Blob解码、三宽度普通页/大屏及原资源正式清理分别留证；跨租户、切会话和迟到响应未覆盖时不计整例通过。

[页面刷新执行器](~/codespace/magicTest/regression/page_refresh_cases.cjs)补充 F069-005：冻结5秒不重叠读取配置，普通成员三宽度真实自动读取；仅延迟精确原应用/安装/源的只读POST响应，跨刷新间隔检查不重叠，再通过真实导航离页、释放原响应并返回。单次真实只读失败后核对可见错误、声明退避和真实owner恢复；真实后台页检查仅在浏览器实际报告hidden后才计证据。原业务行由独立owner核对，可靠删除后再正式卸载；隐藏转换不可用、时间窗口、切账号或持久写面板未覆盖时仍按部分验证记录。


剩余45项的源码补充以[执行器清单](~/codespace/magicTest/regression/inventory.json)和[当前补充范围](~/codespace/docs/acceptance/runs/2026-11-05-platform-standard-regression/executor-completion-20261108T114109Z/implementation-scope.json)为准：原45项均已补实质验证子集，均保持partial；统一入口222项，另有独立健康检查1项，常规分项均有执行入口。注册入口不代表整例覆盖或Live通过；本阶段按用户要求只补源码，平台实际验证留后。

[模型输入执行器](~/codespace/magicTest/regression/model_input_cases.cjs)补充类型、关系、引用删除与表单协议子集；[交付补充](~/codespace/magicTest/regression/delivery_completion_cases.cjs)补充完整ZIP/checksum/程序文件、冻结授权和同版本升级拒绝。[提供方补充](~/codespace/magicTest/regression/provider_completion_cases.cjs)与[依赖运行](~/codespace/magicTest/regression/dependency_runtime_cases.cjs)分别覆盖真实包中的启动身份、范围申请，以及组件实际消费依赖就绪与参数。租户删除、权限修订、服务停发/重发和同浏览器账号切换另由各自执行器覆盖；尚缺的完整矩阵逐例记录，不用空handler填充。

[派生执行器](~/codespace/magicTest/regression/source_effect_cases.cjs)通过正式来源execute/receipt、Panel安装effects/search和普通主体业务读取核对原来源、任务及目标；确认原回执后才重放已确认输入。作者草稿修改不替换安装冻结程序，目标主键、来源摘要、任务尝试和双实例分别核对。[安装控制](~/codespace/magicTest/regression/installation_control_cases.cjs)补充条件停用/激活及数据保持；原生F033-002复用双实例正式retain审批卸载。模型retain恢复现由下述原绑定执行器补充；原生恢复、在途领取、迟到执行者和完整退役矩阵仍开放。

[应用观察执行器](~/codespace/magicTest/regression/application_observation_cases.cjs)核对独立日志/累加器只读声明、安装CAS角色、真实账号授权和撤权；空结果只证明读取授权，不证明块生产了数据。[内置执行器](~/codespace/magicTest/regression/builtin_execution_cases.cjs)核对已安装解释器insert输出真实落库，[运行身份执行器](~/codespace/magicTest/regression/runtime_identity_cases.cjs)核对活跃人类无法冒充机器快照读取。未知写入或角色替换会保留原定义、主体、授权与安装，不重放或猜测拆除。

授权补充入口：[Endpoint当前角色及账号上限](~/codespace/magicTest/regression/endpoint_authority_cases.cjs)覆盖独立同账号双Endpoint真实读取、单独撤权、账号收缩的CAS禁用/原Key失效及恢复账号不复活Key；[授权声明数量边界](~/codespace/magicTest/regression/authorization_capacity_cases.cjs)覆盖三类扩展63/64及逐维65拒绝和原定义条件收缩。两项仍为partial：机器写删/账号禁用、安装规模及JWT/加密会话完整字节预算等分支未完成。

[保留存储恢复执行器](~/codespace/magicTest/regression/storage_recovery_cases.cjs)补充 F048-003：原业务完整行与peer、正式撤权及retain、恢复点/Schema独立回读、第三allocate独立分配，再按原instanceKey与资源版本恢复。核对前驱claimed至精确继任、CAS恢复意图、原撤权不复活；显式新grant后证明同原行、旧安装fence拒绝及新实例隔离。继任可靠删除单独保存新身份回执，不覆盖原create身份；正式destroy和Schema回收后，前驱以原点已消费且精确继任已销毁关联处置，不二次卸载前驱。未确认的原写保留所有关联资源；主动成员保持、过期选择/并发竞争、响应丢失恢复、跨租户与在途矩阵未覆盖，整例partial。此阶段仅补源码和browser-free工具检查，平台实际执行留后。

[部署任务状态执行器](~/codespace/magicTest/regression/deployment_task_state_cases.cjs)补充 F029-003：真实成功模型、预期原生exit23失败、同原任务正式终止后cancelled三态，核对原任务动作、尝试与错误、三宽度表单输入保持及真实owner手动刷新。负例使用原条件版本，精确区分目标状态/版本拒绝与鉴权、传输或无关冲突；完整请求/任务/安装目录及原主体保持后才确认无写。意外UI命令在转发前持久记录，未知结果保留原任务与关联源包，即使运行资源已终止也不猜测删除历史。普通任务不要求运行交接合同的allowedActions字段；等待/执行窗口、实际允许重试、额度耗尽/授权/Schema诊断及迟到响应切任务仍缺，整例partial，Live留后。

[待办来源同步执行器](~/codespace/magicTest/regression/todo_sync_cases.cjs)补充F052-003：正式内置todo绑定、发布和双安装，普通主体可靠业务更新真实触发同源重复同步、同Todo身份和内容跟随、终态pending退出/重开及DELETE退出，配对peer保持与原业务独立回读。pending残留或读取未知保留源安装/授权；Panel pending不代表Base完整终态历史，精确事件重投/并发和Insert-pending仍缺。

[模型维护窗口升级执行器](~/codespace/magicTest/regression/model_upgrade_cases.cjs)补充F033-004：[交付夹具](~/codespace/magicTest/regression/model_delivery.cjs)保留首版和全部较新修订独立回执，通过正式upgrade-preview、既有部署申请/审批完成同deployment/Schema升级，验证新runtime身份与新冻结页面、原成员assignment及原业务继续读写。原创建身份不覆盖，使用继任可靠写/删和正式destroy后独立Schema回收证明关联终结前驱，不再次卸载历史前驱；未知结果保护全部谱系。非空参考数据、兼容服务/发布/订阅/Key及完整撤旧排空证明仍缺，两例均partial；本阶段只补源码与离线工具，Live留后。


[成本观测执行器](~/codespace/magicTest/regression/cost_observation_cases.cjs)补充 F059-002：在既有独立交付夹具中，以原普通成员可靠创建的完整记录为基准，分别采集空闲窗口和一次真实 QueryEntityValue 读取窗口。候选内正式 `collect-qps-analysis.py`／`summarize-qps-analysis.py` 负责日志解析和统计；[有界采集工具](~/codespace/magicTest/regression/cost_observation.py)先记录实际容器、镜像、启动时间与允许导出的观测开关，完成初始数据库统计快照后才通知就绪。读取延后至前沿不完整窗口结束，并校验整个真实请求处于采集区间；窗口重复／截断、统计重置、缺少或重复请求根、容器／源码漂移均不能作为完整观测。SQL指纹的int64身份以文本保真，未启用扩展时明确记录不可用。原业务与版本保持，原行经可靠删除和独立absence清理；失败的采集结果仅保留在仓外私密状态，未通过敏感信息检查的记录不进入公开证据。

使用已有 `deliveryFixtureConfig` 的独立部署声明，在该私密JSON中增加以下字段（并按实际需要列出额外模型执行Base容器）；统一回归配置仍只传既有 `deliveryFixtureConfig` 路径。工具不自动启用开关或重启服务。

```json
{
  "costObservation": {
    "containers": ["magicPanel", "magicbase", "magiccas", "postgres"],
    "seconds": 12
  }
}
```

每个声明的Go容器须实际设置 `MAGIC_PROFILE_WINDOW` 为 `1s`—`10s`，Panel须实际设置 `MAGIC_PROFILE_SAMPLE_EVERY=1`；每阶段 `seconds` 为8—40且至少为最大窗口秒数的三倍加2。例如所有窗口1s可用12秒，窗口10s至少32秒。这里只核对已声明容器的聚合类别与Panel请求根；完整目标执行Base覆盖仍须配套实际拓扑证明。进程统计包含后台任务和采集查询，嵌套阶段与RPC耗时重叠，不相加当作端到端成本，不把窗口SQL差分当作逐请求SQL追踪。开关关闭与恢复、HTTP路由／pprof访问控制和可选APM仍未覆盖，整例partial；源码工具通过不等于Live通过。

[原生生命周期执行器](~/codespace/magicTest/regression/native_lifecycle_cases.cjs)补充 F061-002／F061-003 子集：只在既有 `deliveryFixtureConfig` 声明并实际确认的独立 nested daemon 中，经正式构包、申请和批准建立双实例。网络中的完整 native 目标集必须恰为这两个原实例，隔离根中的正式 stop/start 脚本须与当前候选源码摘要相同；不修改平台原 `.env`。五种负例分别使用无挂载且从不启动的真实探针，字面传递越界根、`../`、project UUID、working_dir 和 deployment 身份，调用正式 remove helper 并独立证明双原容器、数据、owner 和无关核心／模型 peer 保持。正常路径调用正式 native stop/start helpers，以完整原 ID／镜像／Compose journal 恢复原容器；应用自身只在首次启动创建的持久标记用于证明数据保持。

派发前持久记录原意图。创建确认丢失、停止结果未知、恢复失败或 journal／容器身份漂移均禁止重放及依赖卸载／清包；已确认探针只按完整原 ID／label／image／network／无挂载身份清理，删除响应丢失只做原 ID 不存在回读。恢复原运行后，仍使用正式平台审批 retain 卸载，保留卷不称为物理字节删除。两个入口均为 partial：完整顶层平台 stop/start、在途排空及原未知请求、重启后业务写、Panel/reset 全部清理路径仍缺；本阶段不执行实际 Docker、平台或浏览器。

[部署材料执行器](~/codespace/magicTest/regression/deployment_material_cases.cjs)补充 F060-001／F060-002／F063-001／F063-002 子集，沿用既有 `deliveryFixtureConfig` 严格核对独立 nested daemon。正式脚本逐字节复制到新建仓外私有根；实际本地 installer 镜像的正确发行锁先通过，再用合法但错误的摘要验证完整 initialize／reset 在目标阶段拒绝，缺 OEM 拒绝另验。development reset 只验证正式本地镜像策略 helper，不运行完整破坏性 reset，也不从 tag 推断镜像身份。命令派发前记录，原输出私密保存、公开仅摘要；未知结果不重发，原 daemon 容器／启动与有限夹具的字节、mode、数字 UID／GID 保持后才确认处置。

冷快照子集使用正式 backup／verify／restore 与私有有限文件，包含 services 和两个应用目录。核对完整原清单／摘要、归档权限、现存目标拒绝、同根恢复的全部原内容／数字 owner，以及被替换状态保留。夹具字节不冒充真实数据库、秘密身份或持久 owner 回执。镜像发现子集使用正式双原生安装，完整原样 helper 与独立 Compose／native manifest 集合、实际本地 image ID 配对，确认原 owner／卷／无关核心保持后正式 retain 卸载。四例均 partial：完整初始化／业务与待投递恢复、真实全组件 update 与回执、完整 development reset 尚缺，源码检查不代表 Live。

[权限重试执行器](~/codespace/magicTest/regression/authority_retry_cases.cjs)补充 F010-004 的真实管理链路反例：正式发布双租户受控外部服务，原会话通过 BFF／Gateway 发送 GET／POST，核对普通401、业务409和伪造内部证明头均仅执行原上游一次，响应与请求的内部头应被剥离；前后成功请求证明会话仍可用，服务及发布由owner独立回读。写前持久化原actor／origin／服务／marker／正文，未知不重发并保护服务、发布和父租户。真实权限修订、CAS刷新次数与至多一次重试正例、HEAD／带正文GET／网络错误及并发恢复仍缺，整例保持partial；工具替身和本地HTTP不能替代Live。

[来源审计执行器](~/codespace/magicTest/regression/audit_source_cases.cjs)补充 F057-004 的单入口防伪造子集：原平台home会话交替发送三次正常请求与两次伪造转发／租户／actor头的条件服务更新，逐次核对原owner内容和旁路服务保持，再关联唯一的新审计event、原主体、目标租户及来源地址。正常请求的实测地址只用于比较不变量，不作为独立socket或完整可信代理链的正确性证明；控制来源发生变化时保持受阻，不把漂移归因为伪造。写前保存原版本／正文／headers，响应或审计未知不重发，原服务和父租户保持。真实双来源、直连／trusted／invalid链、CAS登录及Gateway安全事件和并发恢复仍缺；整例partial，离线工具检查不替代Live。审计服务夹具使用独立的 audit_source 标识，不与来源治理用例共用资源身份；原同名创建受保护时，不重复 POST 或复用其他场景资源。

[运行控制执行器](~/codespace/magicTest/regression/runtime_control_cases.cjs)补充 F035-004／F035-006，均为部分覆盖。前者仅在独立交付部署更新现存默认策略的原目标，以原版本条件更新，核对旧版本／错误kind拒绝；全部策略、registry配置和原安装冻结事实独立保持。合法新修订保留，不倒退回填，不创建无公开删除的策略；未知命令保留原台账，绝不重发或猜测回滚。实际默认解析及双Base／Gateway交接、排空／撤权／恢复仍需补充。

F035-006使用[机器只读传输](~/codespace/magicTest/regression/runtime_machine_transport.cjs)，常规私有配置可增加 `runtimeSnapshotConfig` 文件路径；该文件只允许 `origin`、`instanceId`、`incarnation`、`endpointId`、`clientId`、`tokenFile` 六字段。origin为运维明确配置的原Panel机器HTTP／HTTPS入口，不假定公共Traefik暴露机器接口；Gateway与CAS凭据身份必须由独立registry读取确认。配置与token文件必须在仓外、当前UID拥有、无group／other权限的普通文件，禁止符号链接。token使用原部署流程签发的短期Bearer，工具不生成、刷新或撤销机器身份；过期或缺入口按真实条件失败／受阻。令牌不归档，输入只记录配置摘要。HTTPS保持证书校验；HTTP仅用于运维配置的隔离转发入口。

机器只执行 `/api/v1/panel/runtime-execution/snapshot/` GET及三种有限query拒绝探针，无Cookie、无跳转、无重试，15秒整个请求预算。完整JSON响应信封body按16MiB流式限额计数；8192字节配置和65536字节token文件上限是工具输入预算，不是产品合同。快照核对原机器／有效租约、完整标记、独立双安装已知行及真实普通主体业务集合读取，运行双方时钟应同步。已知行与完整标记不能证明所有assignment；实际Gateway Apply／持久history／route-receipt及完整容量、字节与重启边界仍开放。测试本机socket通过仅证明工具门禁，不代表平台通过。


[文件受管引用执行器](~/codespace/magicTest/regression/bound_reference_cases.cjs)补充 F049-004 的现有单消费者合同：人类会话经 `/files/self/files/upload-references/` 完成私有上传，核对直调 Service-only `/files/upload-references/:uploadRef/consume` 与 `/files/bound-files/` 路由返回 403 边界隔离；由认证后的 Panel 所有者接口（功能块源码绑定与模型包导入）执行实际服务端消费、原摘要/purpose 校验、单一合法 consumer 绑定、外 consumer/错摘要/错 purpose 拒绝、不可变包字节读取与独立 peer 保持。先持久记录原命令，未知不重发；当前不存在多合法引用增减公开合同，共享最后引用与并发释放仍开放，整例保持partial。

[审计接纳执行器](~/codespace/magicTest/regression/audit_admission_cases.cjs)补充 F057-005 的锁冲突子集，仅在已确认的独立交付部署中运行。绑定原daemon、Panel容器／image／startedAt／restartCount及原持久bind mount和数字UID，[只读锁工具](~/codespace/magicTest/regression/audit_admission_lock.py)仅用只读fd占用已经存在的.operation-audit/admission.lock，不创建、改写、删除或更换队列文件。ready后、派发前再核对持有状态与部署身份；原条件更新须命中接纳锁拒绝，并独立保持完整服务和精确审计基线。原inode释放且原部署保持后，发送不同正文的新命令，以完整业务owner和唯一新持久审计event证明真实提交。任何命令未知不重发，holder退出只释放自身锁。此子集不构造真实满队列，不验证10000条／16KiB信封或CAS pending+reserved边界；容量、故障、提交后恢复及留存仍需另验，整例保持partial。

非浏览器部署材料和原生生命周期夹具使用 `realpath(os.tmpdir())` 创建私有目录，以支持 Chromium 的短路径 TMPDIR 别名；原目录、文件与恢复路径仍须通过真实路径、前缀及原身份检查，不接受链接或越界。

关系输入负例区分 Apps 请求合同拒绝与 Base 业务拒绝。重复引用和禁止的集合更新须在 execute／receipt 同时命中精确请求合同错误，并保持原 owner 行；这不宣称存在或不存在持久回执。有效请求的业务拒绝仍须查询原操作的精确未完成结果。安装生命周期预检复用严格安装比较：部署聚合版本可正向前进，安装全部正式字段、原主体、状态、摘要和更新时间仍用于正式条件命令，聚合版本倒退或安装字段变化时不得派发。

来源生命周期的各验证变体使用独立定义名称，避免同轮已发布定义的唯一约束互相阻挡。禁用安装后的来源请求须命中精确运行实例查找拒绝；正式恢复原安装后独立比较完整来源与目标，并核对任务查询的代际范围。当前代际不返回旧任务且原代际查询精确返回409／code19“历史实例暂不可查询”时，历史任务可查性单列为能力缺口，不能据此判定任务已删除或历史保持已通过。原拒绝可在来源／目标保持后核销，原安装仍须由正式destroy及独立存储／授权回执证明退役；整例保持partial。租户不可用的入口404另按租户合同验证。没有通用ID的来源任务恢复，以完整原始快照唯一匹配，不补造ID或仅按资源类型关联。

来源生命周期恢复模式 `--reconcile-source-lifecycles true` 必须配对 `--source-lifecycle-evidence`，后者绑定原cleanup摘要及原用例文件／摘要和精确安装ID；恢复外层须持有统一origin锁并核对原候选。只处理已记录启用回执、明确禁用来源拒绝和原来源／目标证据；未知写不重发。原私密journal与脱敏原响应及原成功断言配对核验，不恢复被脱敏的查询过滤条件，不把已观察任务当作历史全集。正式撤销原grant／destroy原安装后保留原失败报告、任务证据及历史查询缺口；缺证据、状态漂移或owner拒绝时保持开放。

任务状态定位限定原任务行中的状态标签；重试按钮仅允许两汉字间的排版空白差异，保留真实指针点击及完整owner门禁。浏览器环境须具备中文字体，并抽查实际截图；DOM文本存在不能证明中文字形已呈现。缺字体的运行保留原结果和环境限制，补齐后使用新运行复验，不能覆盖旧截图或据其宣称中文视觉验收通过。

部署材料的容器摘要先按目标路径排序完整挂载对象，并稳定化对象键顺序；配置、网络、挂载值及启动身份仍须完全保持。摘要编码变化不能回填旧基线。TLS私有目录也在真实TMPDIR下创建，原路径、私钥权限和素材摘要门禁保持。租户创建POST及精确租户资源条件PUT分别采用120秒单次观察预算；其他请求保持原预算，所有未知结果仍禁止重发，等待完成不代表证明服务延迟的根因。
