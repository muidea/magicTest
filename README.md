# magicTest 测试导航

Node.js浏览器工具的Playwright固定为`1.56.1`，依赖及锁文件维护在本仓根目录。首次检出或依赖目录缺失时在`~/codespace/magicTest`执行`npm ci`；常规验证直接复用本仓`node_modules`，不向临时目录重复安装。浏览器可使用本机Google Chrome；使用Playwright自带Chromium时首次执行`npx playwright install chromium`，其缓存由用户目录复用。该Node.js依赖不替代Python浏览器套件所需的Python包。

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

正式入口为`platform-standard`，由[编排工具](~/codespace/magicTest/regression/run_standard.py)自动采集部署与健康基线、调用逐例执行器、正式清理夹具、再次核对候选并生成报告。使用仓库外的私密配置文件；配置仅引用凭据文件，不把密码写在命令行。示例配置：

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

[授权快照比较](~/codespace/magicTest/regression/authority_snapshot.cjs)仅忽略 CAS 顶层授权集合及完整账号目录的排列顺序，保留重复元素、全部资源字段、权限和修订差异。其他数组保留顺序，不以 JSON 原始排列断言授权集合变化。[品牌清理](~/codespace/magicTest/regression/branding_cleanup.cjs)保存原账号、租户和每次请求结果；仅对已确认发生在命令准入前的精确繁忙拒绝进行有界重试，响应丢失或其他结果未知保持开放。`--resume-cleanup` 仅从原始清理证据恢复已拒绝的品牌清理及其所属租户，不创建替代夹具。

[完整目录读取器](~/codespace/magicTest/regression/directory.cjs)固定原主体、origin、查询条件及页预算，检查分页总数、重复身份和短页；没有 owner 快照修订时不承诺并发原子快照。分类只读角色和租户管理员夹具使用完整分页，不凭第一页认定角色或账号不存在。F051-003 缺 reader 时报告正式候选／Installer／CAS 配套条件，不使用临时 Role 或初始化重放补权。

[资源台账](~/codespace/magicTest/regression/resource_lifecycle.cjs)覆盖公共 `create/createAs/remove` 夹具入口。发送前原子持久化私密意图，创建响应后保存精确身份并独立读取；首次回读失败但已保存匹配的成功响应与精确 ID 时，清理可在原主体／origin 下重读原 ID，确认原提交身份后再删除，台账重载后同样适用；若原 ID 已独立确认不存在则只记录处置证明。删除前记意图，响应后独立确认原身份不存在。未知创建不重放、不猜 ID 删除；未知删除仍存在且无 owner 终态证明时保持开放。原主体／origin 变化阻断清理，未解决子项不能靠删除父租户掩盖。手写订阅等业务命令仍须各自提供原请求恢复与回收证明，公共 helper 不代替这些合同。

[服务标识执行器](~/codespace/magicTest/regression/service_cases.cjs)覆盖 F037-003，创建同租户两个独立服务，验证重复 key 和不可编辑身份的精确拒绝阶段，并完整查询相关目录、回读两条原资源证明未覆盖。地址仅作合法外部服务元数据，不调用上游。失败／未知写入先登记，再保留原资源及清理开放状态。工具输入指纹自动包含全部运行 `.cjs` 模块，包含目录、公开探针及写入台账。

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

默认复用已安装Playwright配套Chromium；首次准备执行`~/codespace/magicTest/node_modules/.bin/playwright install chromium`。可用`--chrome`指定其他已安装浏览器。当前本地环境使用`*.local.vpc`映射到本机，其他部署须先适配浏览器解析配置，不能直接套用本机网络假设。专项不由此入口触发。

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
