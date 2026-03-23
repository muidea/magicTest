# CAS Python 客户端

当前客户端实现位于 [cas.py](cas.py)。

## 当前定位

这不是通用 SDK 文档，而是 `magicTest/cas` e2e 用例使用的轻量客户端说明。当前语义以 [cas.md](../cas.md) 和 [integration_test_cases.md](../integration_test_cases.md) 为准。

## 已支持能力

- JWT 会话：
  - `login(account, password)`
  - `logout(session_token)`
  - `refresh(session_token)`
- 会话 claims 读取：
  - `get_session_token()`
  - `get_current_entity()`
  - `get_session_id()`
  - `get_session_claims()`
  - `get_session_scope()`
- 权限清单：
  - `get_system_all_privileges()`
- 实体与运行态校验：
  - `filter_entity(param=None)`
  - `query_entity(entity_id)`
  - `query_entity_role(entity_id)`
  - `verify_session_namespace()`
  - `verify_session_entity(param)`
  - `verify_session_entity_role(param)`
- 账号接口：
  - `verify_account(account, password)`
  - `update_account_password(param)`
- endpoint 凭证签发：
  - `allocate_auth_secret(param)`

## 当前固定语义

- `login()` 返回的是账号 JWT，会把当前 `Account` 实体写入 `current_entity`。
- `refresh()` 会基于当前运行态重新签发 token，新的 JWT scope 应跟随最新 namespace scope，而不是沿用旧 token 快照。
- `allocate_auth_secret()` 是 endpoint 凭证签发入口：
  - 输入 `Account` 实体时，可以显式覆盖 role。
  - 输入 `Endpoint` 实体时，会沿用源 endpoint 的 account 和 role 绑定。
- `verify_session_entity()` 与 `verify_session_entity_role()` 是运行态回源校验，不是单纯读取 token 快照。

## 常用返回约定

- `login()` / `logout()` / `verify_session_namespace()` 返回 `bool`
- `refresh()` 返回新 token 或 `None`
- 查询类接口成功返回 `dict` / `list`，失败返回 `None`
- 失败明细可通过 `get_last_error()` 获取

## 示例

```python
from session import MagicSession
from cas import Cas

session = MagicSession("https://panel.local.vpc", "demo")
cas = Cas(session)

if cas.login("demo-user", "Test@123"):
    token = cas.get_session_token()
    scope = cas.get_session_scope()
    entity = cas.get_current_entity()

    new_token = cas.refresh(token)
    cas.logout(new_token or token)
```

## 说明

- 当前 e2e 环境不可达时，用例会按 `SkipTest` 处理，不把网络问题误判为业务失败。
- 文档若与代码不一致，以 [cas.py](cas.py) 为准。
