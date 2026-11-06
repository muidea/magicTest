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

配置可选`catalog`（唯一用例目录）、`cases`（常规用例ID数组，省略即全量）、`chrome`（已安装浏览器）。直接执行`python3 -B regression/run_standard.py --config <private-config> --dry-run`可只读核对实际选择，不访问部署。当前入口仍有尚未实现的常规分项，运行入口存在不代表完整套件交付。

每次在已登记运行目录下生成唯一子目录，保留`inputs.json`、`health-before`、`browser`、`health-after`、`results.json`和`report.json`。报告校验逐例证据摘要；只有常规分项全部通过、部署身份不变、前后健康、本次资源已独立确认清理且执行器成功，才返回成功。定向执行也报告完整常规目录覆盖率，其余项显示未执行；非零退出需根据逐例状态区分受阻、工具错误和产品失败。私密恢复状态自动留在仓库外，位置打印到终端，不归档其内容。当前浏览器夹具清理不代表历史基础设施登记器已全局核销。

同一HTTPS origin的常规执行串行进行。编排工具从预检到清理／报告持有本机排他锁，重复启动在业务操作前明确拒绝；不同用例的独立租户仍可能共享平台OAuth客户端，不能据此并发启动整组夹具。直接调用子执行器须由调用方保障同环境互斥；锁不协调其他机器或平台管理操作。

[注册执行器](~/codespace/magicTest/regression/registration_cases.cjs)通过真实匿名租户Host调用公开申请入口，管理策略路径为`policies`；管理代理不能替代匿名正例。[会话策略执行器](~/codespace/magicTest/regression/session_cases.cjs)保存平台及租户策略，独立读取BFF新旧会话身份和实际到期时间，并条件恢复平台原策略；自然到期仍按专项处理。[脚本执行器](~/codespace/magicTest/regression/script_cases.cjs)核对格式化、样例输出／日志、诊断及正式库保存回读；F017-002 另核对作者调试1—3000ms（0默认3000）的边界、超时和传输取消，运行绑定1—30000ms独立验证。浏览器取消不直接证明服务端已停止。[通知执行器](~/codespace/magicTest/regression/notification_cases.cjs)核对真实门户详情、受众与租户范围、下线／删除及读取失败后的旧缓存保护。各模块登记不表示用例已经通过。

租户正式删除后，BFF可能拒绝再查询该租户子资源，403不能作为不存在的证明。执行器保留子身份，结合原租户DELETE回执、公开持久退役记录和独立目录不存在证明，核对已审查的聚合清理合同；不声称逐个删除后仍可读取子资源。只读`--reconcile-cleanup`模式向唯一新attempt追加原失败资源的处置证明，不重放DELETE、不修改旧记录，也不会回落为常规执行。

[公开首跳探针](~/codespace/magicTest/regression/public_probe.cjs)在原浏览器页面使用原会话 Cookie，只读同源 GET；禁止自动跳转，记录 Chromium 原始首跳状态及 Location。301／302／307／308 后最终404不能满足统一404断言。普通登录流程仍按正式跳转执行。

[负例写入台账](~/codespace/magicTest/regression/negative_mutations.cjs)在 F051 创建分类及 F055 伪造目标提示／跨 Host 写平台品牌前持久化精确意图；意外成功也先登记返回身份，再抛出用例失败。分类按原返回 ID、完整目录和 owner 回读确认后清理；平台品牌只对本次已确认的精确资源ID与版本执行条件 PUT，原无覆盖时发送空标量并保留素材。响应丢失、版本冲突、分页不完整及缺少同一命令终态证明保持 cleanup 开放，不盲目重放，不以删除测试租户代替全局品牌恢复。状态目录须保留，禁止直接更改其 phase 制造 allCleaned。

工具自身回归（隔离 HTTP／真实 Chromium 与 handler 夹具，不计产品 Live 通过）：

```sh
node --test regression/public_probe.test.cjs regression/negative_mutations.test.cjs
python3 -B -m unittest regression.test_run_standard
```

### 常规分项浏览器执行器

[执行器](~/codespace/magicTest/regression/standard.cjs)读取权威目录，为所选常规分项逐项输出结果；[具体断言](~/codespace/magicTest/regression/standard_cases.cjs)只登记已有实现，未覆盖全部步骤、缺少夹具或没有执行器的分项明确受阻。它仍不是已交付的完整常规套件，不能以已注册handler数推断完整覆盖。

[身份与模板断言](~/codespace/magicTest/regression/identity_cases.cjs)使用正式登录／首次改密表单、错误密码提示、CAS会话与授权目录及BFF精确退出。CAS OAuth管理接口由同租户真实审计账号回读；平台治理账号不能代替租户本地OAuth身份。退出保留原BFF凭据副本验证服务端失效，并核对另一独立会话保持；该结果只证明当前会话退出。模板验证包含真实授权操作、委派上限、来源权限并集、撤回和在用删除门禁。

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
