# CAS E2E 集成用例

## 已落地场景

### IT-001 命名空间治理边界

- panel 默认 namespace 的治理 scope 为 `*`
- 新建 namespace 未显式指定 scope 时，默认回填为 namespace 自身名称
- 被纳入 `Namespace.Scope` 的超级 namespace 可以更新、删除目标 namespace
- scope 外 namespace 不能越权管理其他 namespace

对应测试：
- [namespace_test.py](/home/rangh/codespace/magicTest/cas/namespace/namespace_test.py)

### IT-002 Role 与 Account 绑定

- `Account` 创建必须绑定有效 `Role`
- 绑定禁用 `Role` 的 `Account` 不允许创建
- `Role` 被禁用后，关联 `Account` 登录应失败
- `Account` 更新后应保留既有 `Role` 绑定
- 重复 `Role` 名称在同 namespace 下应被拒绝，不再走隐式 update

对应测试：
- [account_test.py](/home/rangh/codespace/magicTest/cas/account/account_test.py)
- [role_test.py](/home/rangh/codespace/magicTest/cas/role/role_test.py)

### IT-003 Endpoint 显式授权对象

- `Endpoint` 创建时必须显式绑定 `Account`、`Role`、`Scope`
- `Endpoint.Scope` 作为运行态数据访问边界被原样保留
- 禁用 `Role` 不允许作为 `Endpoint` 绑定对象
- 禁用 `Account` 不允许作为 `Endpoint` 绑定对象
- 未显式提供 `Scope` 的 `Endpoint` 创建应失败

对应测试：
- [endpoint_test.py](/home/rangh/codespace/magicTest/cas/endpoint/endpoint_test.py)

### IT-004 AuthSecret 凭证签发与外部授信访问

- `AllocateAuthSecret` 以 `Account` 实体为输入时，可生成新的 endpoint 凭证
- `AllocateAuthSecret` 以 `Account` 实体为输入时，显式 `Role` 覆盖应生效
- `AllocateAuthSecret` 以 `Endpoint` 实体为输入时，会沿用源 endpoint 的账号与 role 绑定，且不允许显式 `Role` 覆盖
- `AllocateAuthSecret` 只允许对当前请求 namespace 下的实体签发，跨 namespace 实体必须拒绝
- 生成的 `AuthSecret` 可被 `MagicSession.bind_auth_secret()` 作为 endpoint 凭证使用
- endpoint 删除、endpoint 失效、绑定 account 失效、绑定 role 失效后，运行态 `AuthSecret` 应被拒绝

对应测试：
- [endpoint_test.py](/home/rangh/codespace/magicTest/cas/endpoint/endpoint_test.py)
- [cas_api_test.py](/home/rangh/codespace/magicTest/cas/cas_api_test.py)

### IT-005 基础链路冒烟

- 默认 `panel` namespace 启动后应具备默认 role / account / endpoint 初始化链
- `namespace -> role -> account -> endpoint` 基础开通链路
- `account login -> refresh -> logout` 会话链路

对应测试：
- [basic_scenario_test.py](/home/rangh/codespace/magicTest/cas/basic_scenario_test.py)

### IT-006 CAS 运行态接口语义

- `verifyAccount` 仅接受正确账号密码
- `updateAccountPassword` 必须校验旧密码，且只能由当前绑定 account 本人 session 修改
- endpoint session 不允许代改绑定 account 密码
- `queryEntity/queryEntityRole` 同时覆盖 `Account` 与 `Endpoint` 实体
- 无 `ReadPermission` / `WritePermission` 的低权限角色不应访问 `filterEntity`、`queryEntity`、`queryEntityRole`、`updateAccountPassword`
- `verifySessionNamespace` 同时覆盖普通 namespace 拒绝越权和 `panel` 全局 scope 放行
- `verifySessionEntity/verifySessionEntityRole` 覆盖 JWT 与 endpoint 两条会话路径
- `verifySessionEntity/verifySessionEntityRole` 对错误 `entityID` 必须拒绝
- `refresh` 必须把 namespace 最新 scope 写入新 JWT，而不是沿用旧 token scope
- 绑定 `Role` 已失效时，已登录 JWT 的 `refresh` 必须拒绝

对应测试：
- [cas_api_test.py](/home/rangh/codespace/magicTest/cas/cas_api_test.py)

## 当前执行约定

- 默认入口：`MAGICTEST_CAS_BASE_URL`，缺省为 `https://panel.local.vpc`
- 默认治理 namespace：`panel`
- 环境不可达时测试直接 `skip`
- 这组用例优先验证设计一致性，不做性能和高并发场景
