# panel

`magicTest/panel` 用于回归 `magicPanel` 当前公开的运行期对象入口。默认目标环境是 `https://autotest.local.vpc/api/v1`，默认 namespace 是 `panel`。

当前第一批已落地的是“应用生命周期组”的最小测试入口：

- [application_lifecycle_test.py](application_lifecycle_test.py)
  - `fetch running application` smoke
  - 在显式提供 `MAGICTEST_PANEL_APP_UUID` 时执行可恢复的 `start/stop` 回归
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

## 认证方式

优先级如下：

1. `MAGICTEST_PANEL_BEARER_TOKEN`
2. `MAGICTEST_PANEL_AUTH_ENDPOINT` + `MAGICTEST_PANEL_AUTH_TOKEN`
3. `MAGICTEST_PANEL_LOGIN_ACCOUNT` + `MAGICTEST_PANEL_LOGIN_PASSWORD`

如果走账号密码方式，测试会自动调用 CAS 登录并把 session token 绑定到 panel session。

## 推荐命令

```bash
cd ../magicTest/panel
source ../venv/bin/activate
HTTPS_PROXY= HTTP_PROXY= https_proxy= http_proxy= \
NO_PROXY=autotest.local.vpc no_proxy=autotest.local.vpc \
PYTHONPATH=..:.:$PYTHONPATH \
python3 -m unittest application_lifecycle_test -v
```

如果要执行 `start/stop` 回归，还需要额外提供：

- `MAGICTEST_PANEL_APP_UUID`

如果要执行 `subscription` 的增强回归，还需要按场景提供：

- `MAGICTEST_PANEL_SUBSCRIPTION_ID`
- `MAGICTEST_PANEL_MUTABLE_SUBSCRIPTION_ID`
- `MAGICTEST_PANEL_ALLOW_STATUS_MUTATION=true`

如果要执行 `definition` 的增强回归，还需要按场景提供：

- `MAGICTEST_PANEL_APPLICATION_DEFINITION_ID`
- `MAGICTEST_PANEL_ENTITY_DEFINITION_ID`
- `MAGICTEST_PANEL_ALLOW_DEFINITION_MUTATION=true`

## 当前边界

- 当前只落了生命周期组的安全入口，不默认执行安装/卸载
- `subscription` 组默认只跑读路径；写路径只在显式提供可变更对象时执行
- `definition` 组默认只跑读路径；写路径只在显式提供允许变更时执行
- `profile` 组当前全部为只读 smoke，不引入额外副作用
- 安装/卸载、schema、subscription、definition、feedback、notification 的专项回归分组设计见 `magicRunner/docs/design-panel-regression-plan.md`
