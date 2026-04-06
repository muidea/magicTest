# magicTest CAS E2E 基线

这组 e2e 测试以 [design-cas-auth.md](../../docs/design-cas-auth.md) 和 [design-modules.md](../../magicCas/docs/design-modules.md) 为准，当前固定采用以下业务口径：

## 核心语义

- `Account`
  归属主体，用于识别凭证归属与审计归责。
- `Role`
  功能与操作权限集合。
- `Namespace`
  治理边界与隔离边界。
- `Namespace.Scope`
  namespace 的治理范围定义，用于表达“这个 namespace 可以管理哪些 namespace”。
- `Endpoint`
  显式访问授权对象，必须绑定有效 `Account`、有效 `Role`、显式 `Scope`。
- `Endpoint.Scope`
  运行态数据访问范围定义，不等同于 `Namespace.Scope`。
- `AuthSecret`
  `Endpoint` 的凭证表现形式，不单独承载业务语义。

## 当前 E2E 覆盖重点

- 默认新建 namespace 在未显式传入 `scope` 时，应回填为 namespace 自身名称。
- `panel` 是默认治理 namespace，其 `Scope` 为全局 `*`。
- 超级 namespace 只有在自己的 `Namespace.Scope` 纳入目标 namespace 时，才允许管理目标 namespace。
- `Account` 必须绑定有效 `Role`。
- `Endpoint` 必须绑定有效 `Account`、有效 `Role`、显式 `Scope`。
- `AllocateAuthSecret` 是 `Endpoint` 凭证签发入口：
  - 以 `Account` 实体为输入时，可显式指定 role 覆盖。
  - 以 `Endpoint` 实体为输入时，应沿用 endpoint 绑定的账号和 role，不能再显式覆盖 role。
  - 只允许对当前请求 namespace 下的实体签发 endpoint 凭证。
- `queryEntity` / `queryEntityRole` 只能读取当前请求 namespace 下的实体，不能跨 namespace 读取其他租户实体信息。
- `updateAccountPassword` 只能由当前绑定 account 本人 session 修改自己的密码，不能由其他 account session 或 endpoint session 代改。
- 低权限 role 不能越权访问需要 `ReadPermission` / `WritePermission` 的 CAS 运行态接口。
- 运行态 `role/scope` 校验必须按当前服务端状态回源确认，不能只信任 JWT 或 endpoint token 中缓存的旧 role/scope。
- 外部访问通过 `AuthSecret` 绑定到 `Endpoint` 进行平台授信访问。
- 默认 `panel` namespace 启动后，应自动具备 `superRole`、`administrator`、`defaultEndpoint` 这条基线初始化链。
- 运行态鉴权必须回源校验当前 `Endpoint` / `Account` / `Role` 的有效性，不能只信任旧 token 快照。
- `JWT refresh` 必须按当前 CAS 运行态快照重新签发新 token。
- namespace 管理变更通过事件传播到 CAS，scope 生效允许延迟，不要求在 namespace 更新返回后立即反映到 refresh 结果。

## 运行方式

- 默认访问地址使用环境变量 `MAGICTEST_CAS_BASE_URL`，缺省值为 `https://panel.local.vpc`。
- 测试默认通过 `X-Mp-Namespace` 在同一入口下切换 namespace。
- 当 e2e 环境不可达时，测试会显式 `skip`，避免把 DNS / 网络问题误判为业务回归。
