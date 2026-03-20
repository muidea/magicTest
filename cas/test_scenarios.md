# CAS 测试索引

## 说明

这份索引只保留当前有效入口，不再维护历史统计数字。详细场景以各模块 `*_test.py` 和 [integration_test_cases.md](/home/rangh/codespace/magicTest/cas/integration_test_cases.md) 为准。

## 当前测试文件

- [namespace_test.py](/home/rangh/codespace/magicTest/cas/namespace/namespace_test.py)
  覆盖 `Namespace.Scope` 的默认回填、治理边界、超级 namespace 管理、越权拒绝
- [role_test.py](/home/rangh/codespace/magicTest/cas/role/role_test.py)
  覆盖 role 状态、privilege 保留、更新语义、重复创建拒绝
- [account_test.py](/home/rangh/codespace/magicTest/cas/account/account_test.py)
  覆盖 account 绑定有效 role、更新保留绑定、禁用 role 后登录失败、namespace 隔离
- [endpoint_test.py](/home/rangh/codespace/magicTest/cas/endpoint/endpoint_test.py)
  覆盖 endpoint 显式绑定、`Scope` 必填、`AllocateAuthSecret`、role override
- [basic_scenario_test.py](/home/rangh/codespace/magicTest/cas/basic_scenario_test.py)
  覆盖默认 `panel` 启动链，以及 `namespace -> role -> account -> endpoint` 基础链路
- [cas_api_test.py](/home/rangh/codespace/magicTest/cas/cas_api_test.py)
  覆盖 `verifyAccount`、`updateAccountPassword`、`queryEntity`、`verifySession*`、`refresh`、endpoint token 失效路径

## 当前重点

- `Namespace.Scope` 和 `Endpoint.Scope` 已按两层语义拆开
- `Endpoint` 是显式授权对象
- `AuthSecret` 是 endpoint 凭证表现形式
- 运行态授权必须回源校验当前实体、role、scope

## 环境约定

- 默认入口：`MAGICTEST_CAS_BASE_URL`
- 默认治理 namespace：`MAGICTEST_CAS_PANEL_NAMESPACE`
- 环境不可达时，e2e 直接 `skip`
