# magicTest 测试导航

`magicTest` 当前已经包含多套不同目标的测试代码，但入口分散在 `cas / file / panel / platform / vmi` 各自目录中。  
本说明的目的不是重写现有测试，而是按“测试目标”重新整理现有资产，方便后续按需求快速选择测试入口。

---

## 1. 测试目标分层

当前测试代码按目标可分为 8 类：

| 测试目标 | 说明 | 主要目录 |
| --- | --- | --- |
| `foundation` | 会话、请求封装和测试基础设施自身验证 | `session/` |
| `auth` | CAS 认证、账号、角色、命名空间、注册审核 | `cas/` |
| `ui` | 真实浏览器层面的注册、登录与页面入口验收 | `ui/` |
| `file` | 文件服务基础能力验证 | `file/` |
| `platform-core` | `magicBase` 平台核心接口回归 | `platform/` |
| `panel-api` | `magicPanel` / `portal` 控制面与消费面接口回归 | `panel/` |
| `business-scenario` | 业务应用级场景与模块回归 | `vmi/` |
| `load` | 并发、热点、老化等压测入口 | `vmi/` |

这次整理后的原则是：

- 不打散现有稳定目录和 runner
- 在根目录提供统一导航和聚合入口
- 按“测试目标”而不是“历史目录名”来找测试

---

## 2. 当前统一入口

新增根层入口：

- [run_tests.py](/home/rangh/codespace/magicTest/run_tests.py)
- [test_catalog.py](/home/rangh/codespace/magicTest/test_catalog.py)

推荐先用它做导航和执行。`cas/platform/panel/vmi` 各子目录里的 `run_tests.py` 保留给高级调试，不再作为日常主入口。

### 2.1 查看测试目标

```bash
cd /home/rangh/codespace/magicTest
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

### `session/`

只放测试基础设施和 `MagicSession` 相关验证，不承载业务接口回归。

### `cas/`

只放认证与注册治理相关测试：

- 登录
- refresh
- 账号 / 角色 / 端点 / 命名空间
- 注册模板 / 注册策略 / 注册审核

### `ui/`

只放真实浏览器层面的页面链路验收：

- 注册页加载
- 注册申请提交
- 审核后登录
- 登录后进入 portal 首页

当前 `ui` 测试是可选增强套件，依赖 Playwright；日常接口回归仍以 `cas/` 和 `panel/` 为主。

### `file/`

只放 `magicFile` 相关基础回归。

### `platform/`

只放 `magicBase` 平台核心接口：

- application
- block
- entity
- value
- access_log
- operation_log
- totalizator

### `panel/`

只放 `magicplatform` 当前控制面 / 消费面接口回归：

- apps runtime
- 生命周期
- 定义与订阅
- profile / system context
- 服务访问主链

### `vmi/`

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

- [panel/README.md](/home/rangh/codespace/magicTest/panel/README.md)
- [platform/README.md](/home/rangh/codespace/magicTest/platform/README.md)
- [vmi/README.md](/home/rangh/codespace/magicTest/vmi/README.md)
- [session/USAGE.md](/home/rangh/codespace/magicTest/session/USAGE.md)
