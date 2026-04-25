# panel

`magicTest/panel` 用于回归 `magicPanel` 当前公开的运行期对象入口。默认目标环境是 `https://panel.local.vpc/api/v1`，默认 namespace 是 `panel`。

日常执行优先使用根入口 [magicTest/run_tests.py](/home/rangh/codespace/magicTest/run_tests.py)：

```bash
cd /home/rangh/codespace/magicTest
python3 run_tests.py --preset panel-smoke
python3 run_tests.py --preset panel-full
```

本目录下的 `python3 -m unittest ...` 入口保留给单套件调试。

当前第一批已落地的是“应用生命周期组”的最小测试入口：

- [application_lifecycle_test.py](application_lifecycle_test.py)
  - `fetch running application` smoke
  - 在显式提供 `MAGICTEST_PANEL_APP_UUID` 时执行可恢复的 `start/stop` 回归
- [application_install_roundtrip_test.py](application_install_roundtrip_test.py)
  - 自动选择一个已发布且已存在原实例的非 `bootstrap` 应用源
  - 执行“第二实例在线安装 -> 卸载 -> 再次安装”回归
  - 校验同一发布多实例安装、卸载、重复安装下的运行期幂等行为
- [subscription_test.py](subscription_test.py)
  - `filter subscription` smoke
  - 在显式提供 `MAGICTEST_PANEL_SUBSCRIPTION_ID` 时查询订阅详情
  - 在显式提供 `MAGICTEST_PANEL_MUTABLE_SUBSCRIPTION_ID` 时执行 endpoint create/delete roundtrip
  - 在额外允许状态变更时执行可恢复的 `enable/disable` roundtrip
- [definition_test.py](definition_test.py)
  - `filter entity definition` smoke
  - 在显式提供 definition id 时查询 application/entity definition 与 `pkg tree`
  - 在额外允许变更时执行 application/entity definition roundtrip
- [profile_test.py](profile_test.py)
  - `GetSystemNotification` smoke
  - `Profile` smoke
  - 校验 `summary` / `notification` 的返回结构
- [system_context_test.py](system_context_test.py)
  - 校验 `/api/v1/system/context/` 在 `panel / portal / workbench / app / other` 不同 `surface` 下的返回边界
  - 固化 `panel.*` 与 `portal.*` 页面级功能区不会跨 surface 混出
- [service_access_test.py](service_access_test.py)
  - 多能力项服务未带 capability key 时返回 `400`
  - `query` 能力通过 `gateway` 访问
  - 优先从 `query` 结果自动推导实体 ID；当前 `user_service` 已可稳定覆盖 `get`
- [service_roundtrip_test.py](service_roundtrip_test.py)
  - 校验服务定义、已发布状态、portal 服务目录可见性
  - 校验 `panel` 账号态进入服务与调试元数据
  - 校验 `portal` 订阅、审批、默认凭证签发与 `gateway` 访问
  - 优先从 `query` 结果自动推导 `get` 所需实体 ID
  - 若未显式提供 CRUD payload，则优先基于运行期实体元数据自动生成最小写入样本
  - 若服务未开放 `delete`，则使用运行期 `apps` delete API 清理测试创建的数据
  - 若测试中创建了订阅，会在结束时自动清理
- [apps_runtime_test.py](apps_runtime_test.py)
  - 校验运行中应用的 `/api/v1/apps/application/runtimes/:key` 元数据可访问
  - 校验运行期实体自动补齐的 CRUD API 元数据
  - 校验至少一个运行期实体列表接口可直接访问

## 认证方式

优先级如下：

1. `MAGICTEST_PANEL_BEARER_TOKEN`
2. `MAGICTEST_PANEL_AUTH_TOKEN`
3. `MAGICTEST_PANEL_AUTH_ENDPOINT` 仅作为调试/展示辅助，可选
4. `MAGICTEST_PANEL_LOGIN_ACCOUNT` + `MAGICTEST_PANEL_LOGIN_PASSWORD`

如果走账号密码方式，测试会自动调用 CAS 登录并把 session token 绑定到 panel session。

当前服务消费凭证的最终协议是：

- 账号 JWT：`Authorization: Bearer <jwt>`
- endpoint token：`Authorization: Sig <authSecret.token>`

`MAGICTEST_PANEL_AUTH_ENDPOINT` 不再参与签名拼装，只保留为测试上下文中的 endpoint 元信息。

## 推荐命令

```bash
cd /home/rangh/codespace/magicTest
source ~/codespace/venv/bin/activate
python3 run_tests.py --preset panel-smoke
python3 run_tests.py --preset panel-full
```

如果只需要单个套件：

```bash
python3 run_tests.py --target panel-runtime-api
python3 run_tests.py --target panel-page-api
python3 run_tests.py --target panel-service-api
python3 run_tests.py --target panel-governance-api
```

只有在定位单一文件问题时，才建议进入 `panel/` 目录使用 `python3 -m unittest ...`。

如果要执行 `start/stop` 回归，还需要额外提供：

- `MAGICTEST_PANEL_APP_UUID`

如果要执行多实例在线安装 / 卸载幂等回归，可选提供：

- `MAGICTEST_PANEL_INSTALL_RELEASE_ID`
- `MAGICTEST_PANEL_INSTALL_PACKAGE_ID`
- `MAGICTEST_PANEL_INSTALL_SOURCE_UUID`
- `MAGICTEST_PANEL_INSTALL_SOURCE_PKG_PREFIX`
- `MAGICTEST_PANEL_INSTALL_DATABASE_INSTANCE_ID`
- `MAGICTEST_PANEL_INSTALL_TASK_TIMEOUT`

如果要执行 `subscription` 的增强回归，还需要按场景提供：

- `MAGICTEST_PANEL_SUBSCRIPTION_ID`
- `MAGICTEST_PANEL_MUTABLE_SUBSCRIPTION_ID`
- `MAGICTEST_PANEL_ALLOW_STATUS_MUTATION=true`

如果要执行 `definition` 的增强回归，还需要按场景提供：

- `MAGICTEST_PANEL_APPLICATION_DEFINITION_ID`
- `MAGICTEST_PANEL_ENTITY_DEFINITION_ID`
- `MAGICTEST_PANEL_ALLOW_DEFINITION_MUTATION=true`

如果要执行 `service access` 回归，建议按场景提供：

- `MAGICTEST_PANEL_SERVICE_KEY`
- `MAGICTEST_PANEL_QUERY_CAPABILITY_KEY`
- `MAGICTEST_PANEL_GET_CAPABILITY_KEY`
- `MAGICTEST_PANEL_GET_ENTITY_ID`
  - 若未提供，则测试会优先从 `query` 结果自动提取第一个实体 ID

如果要执行 `service roundtrip` 主流程回归，建议按场景提供：

- `MAGICTEST_PANEL_SERVICE_KEY`
- `MAGICTEST_PANEL_QUERY_CAPABILITY_KEY`
- `MAGICTEST_PANEL_GET_CAPABILITY_KEY`
- `MAGICTEST_PANEL_GET_ENTITY_ID`
  - 若未提供，则测试会优先从 `query` 结果自动提取第一个实体 ID
- 如需执行 CRUD roundtrip，再额外提供：
  - `MAGICTEST_PANEL_CREATE_CAPABILITY_KEY`
  - `MAGICTEST_PANEL_UPDATE_CAPABILITY_KEY`
  - `MAGICTEST_PANEL_DELETE_CAPABILITY_KEY`
  - `MAGICTEST_PANEL_CREATE_PAYLOAD_JSON`
  - `MAGICTEST_PANEL_UPDATE_PAYLOAD_JSON`
- 并优先使用账号态认证：
  - `MAGICTEST_PANEL_BEARER_TOKEN`
  - 或 `MAGICTEST_PANEL_LOGIN_ACCOUNT` + `MAGICTEST_PANEL_LOGIN_PASSWORD`

如果要执行 `apps runtime` 回归，建议按场景提供：

- `MAGICTEST_APPS_RUNTIME_KEY`
- 可选 `MAGICTEST_PANEL_APP_UUID`
- 可选 `MAGICTEST_APPS_RUNTIME_ENTITY`

## 当前边界

- 当前只落了生命周期组的安全入口，不默认执行安装/卸载
- `application_install_roundtrip` 会执行真实在线安装与卸载，只会针对自动发现或显式指定的非 `bootstrap` 发布源创建临时实例，并在测试结束时自动清理
- `subscription` 组默认只跑读路径；写路径只在显式提供可变更对象时执行
- `definition` 组默认只跑读路径；写路径只在显式提供允许变更时执行
- `profile` 组当前全部为只读 smoke，不引入额外副作用
- `system_context` 组当前全部为只读 smoke，用于校验 `surface` 过滤和页面级功能区边界
- `service access` 默认先锁定协议与 query 访问；`get` 访问只在显式提供实体 ID 时执行
- 当前 `user_service` 已存在稳定样本，`service_access_test` 会自动覆盖 `query + get`
- `service roundtrip` 优先复用当前用户既有订阅；若无订阅则尝试创建并在测试结束后清理
- `service roundtrip` 优先使用显式提供的 `MAGICTEST_PANEL_CREATE_PAYLOAD_JSON` / `MAGICTEST_PANEL_UPDATE_PAYLOAD_JSON`
- 若未提供且运行期实体元数据足够，则自动生成最小 `create/update` payload
- 若服务未开放 `delete` 能力，则通过运行期实体 delete API 做测试清理，避免脏数据累计
- `apps runtime` 默认优先使用显式指定的 `MAGICTEST_APPS_RUNTIME_KEY`；若未指定，则只从“非 bootstrap 的运行中应用”列表自动发现目标，自动发现失败时会跳过而不是误判为 runtime 同步失败
- 安装/卸载、schema、subscription、definition、feedback、notification 的专项回归分组设计见 `magicRunner/docs/design-panel-regression-plan.md`
