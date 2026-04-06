# CAS 核对清单

## 当前口径

历史版本里混入过旧语义，这里只保留当前仍有效的核对点。业务与测试基线以 [cas.md](cas.md) 和 [integration_test_cases.md](integration_test_cases.md) 为准。

## 已确认

- `Account -> Role -> Endpoint` 是当前固定绑定链。
- `Namespace.Scope` 是治理范围，不是 endpoint 数据范围。
- `Endpoint.Scope` 是运行态数据访问范围，不是 namespace 管理范围。
- `AuthSecret` 是 `Endpoint` 的凭证表现形式，不是独立授权主体。
- `AllocateAuthSecret`：
  - 以 `Account` 实体为输入时可显式覆盖 role。
  - 以 `Endpoint` 实体为输入时沿用 endpoint 现有 account / role 绑定。
- `refresh()` 必须基于当前 CAS 运行态快照重签 JWT，不能沿用旧 token scope。
- namespace.scope 对 CAS 的生效允许延迟，不要求在 namespace 管理返回后立刻反映到新 JWT。
- 运行态鉴权必须回源校验当前 `Endpoint` / `Account` / `Role` 是否仍然有效。

## 当前 e2e 已覆盖

- namespace 默认 scope、自管理、超级 namespace 管理边界、越权拒绝
- role 显式状态、权限保留、重复创建拒绝
- account 绑定有效 role、更新保留绑定、禁用 role 后登录失败
- endpoint 显式绑定 account / role / scope、重复名拒绝、无 scope 拒绝、禁用 account/role 拒绝
- `AllocateAuthSecret` 的 account 输入、endpoint 输入、role override
- `AllocateAuthSecret` 跨 namespace 实体拒绝
- endpoint token 在 endpoint 删除、endpoint 禁用、绑定 account 禁用、绑定 role 禁用后的失效
- `verifyAccount`、`updateAccountPassword`、`queryEntity`、`queryEntityRole`
- endpoint session 不允许代改绑定 account 密码
- `verifySessionEntity` / `verifySessionEntityRole` 的 JWT 与 endpoint 路径
- `refresh()` 基于当前 CAS 运行态快照重签
- `panel` 默认 `superRole` / `administrator` / `defaultEndpoint` 初始化链

## 当前未做的事

- 不在这里继续维护历史“分析过程”。
- 若需补新场景，直接更新 [integration_test_cases.md](integration_test_cases.md) 和对应测试文件。
