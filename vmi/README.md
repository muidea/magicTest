# VMI 测试套件

`magicTest/vmi` 是面向已部署 VMI 服务的 Python 集成测试套件。当前测试默认连接真实服务，通过 CAS 登录、实体 SDK 调用和多模块业务链路验证服务行为。

## 当前入口

推荐统一入口：

```bash
source /home/rangh/codespace/venv/bin/activate
python3 run_tests.py --quick
python3 run_tests.py --all
python3 run_tests.py --module
python3 run_tests.py --aging 30
```

直接运行 `unittest`：

```bash
source /home/rangh/codespace/venv/bin/activate
python3 -m unittest discover -s . -p '*_test.py' -v
```

远端环境回归时，建议按实际目标域名显式关闭代理，例如：

```bash
source /home/rangh/codespace/venv/bin/activate
HTTPS_PROXY= HTTP_PROXY= https_proxy= http_proxy= \
NO_PROXY=autotest.local.vpc no_proxy=autotest.local.vpc \
python3 -m unittest discover -s . -p '*_test.py' -v
```

## 测试分层

- `test_complete_validation.py`
  验证配置、导入链路、测试基类和多租户基础能力，尽量不依赖真实网络。
- `test_multi_tenant.py`、`test_multi_tenant_example.py`
  验证多租户配置和管理器行为，主要依赖 mock。
- `scenario_test.py`
  校验业务场景和基础性能要求。
- `concurrent_test_v2.py`
  并发会话和并发实体操作测试。
- `aging_test_simple.py`
  长时间老化测试和性能劣化观测。
- `credit/`、`order/`、`partner/`、`product/`、`status/`、`store/`、`warehouse/`
  面向业务模块的实体级集成测试。

## 关键基础设施

- `test_bootstrap.py`
  统一补齐 `sys.path` 并关闭 `InsecureRequestWarning`。
- `session_manager.py`
  统一管理登录、刷新和重连。
- `test_vmi_base.py`
  提供通用日志、清理注册表、数量统计和清理辅助能力。
- `test_dependency_helper.py`
  统一构造店铺、仓库、货架、商品等依赖数据。
- `config_helper.py`
  从 `test_config.json` 读取服务、认证、并发和老化参数。
- `tenant_config_helper.py`
  在单租户配置之上扩展多租户视图，并保持默认 `autotest` 兼容。

## 配置文件

默认配置文件是 `test_config.json`。本地验证时，通常使用如下配置：

```json
{
  "server": {
    "url": "https://autotest.local.vpc",
    "namespace": "autotest",
    "environment": "local"
  },
  "credentials": {
    "username": "administrator",
    "password": "administrator"
  },
  "session": {
    "refresh_interval": 540,
    "timeout": 1800
  },
  "concurrent": {
    "max_workers": 10,
    "timeout": 30,
    "retry_count": 3
  },
  "aging": {
    "duration_hours": 0.5,
    "concurrent_threads": 10,
    "operation_interval": 1.0,
    "max_data_count": 1000,
    "performance_degradation_threshold": 20.0,
    "report_interval_minutes": 5
  }
}
```

如果当前工作区已经切到其他环境，回归前先把 `test_config.json` 调整到目标环境，再同步调整 `NO_PROXY`。

如果启用多租户，需要额外声明 `multi_tenant` 段，具体见 [TEST_GUIDE.md](/home/rangh/codespace/magicTest/vmi/TEST_GUIDE.md)。

## 常用命令

冒烟检查：

```bash
python3 run_tests.py --check-config
python3 run_tests.py --quick
```

模块回归：

```bash
python3 run_tests.py --module
python3 -m unittest warehouse.shelf_test order.order_test -v
```

并发和场景：

```bash
python3 run_tests.py --concurrent
python3 run_tests.py --scenario
python3 concurrent_test_v2.py
```

老化：

```bash
python3 run_tests.py --aging 30
python3 aging_test_simple.py --duration 0.5
```

## 文档索引

- [TEST_GUIDE.md](/home/rangh/codespace/magicTest/vmi/TEST_GUIDE.md)
  面向使用者和维护者的测试说明。
- [DEPLOYMENT.md](/home/rangh/codespace/magicTest/vmi/DEPLOYMENT.md)
  面向部署后验证的执行说明。
- [TEST_ARCHITECTURE.md](/home/rangh/codespace/magicTest/vmi/docs/TEST_ARCHITECTURE.md)
  面向维护者的测试架构与分层说明。

## 当前已知行为

以下现象在最近回归中出现，但当前不作为失败条件：

- 系统当前允许同一会员存在多条 `credit report`
- 系统当前允许重复 `productInfo.sku`
- 部分创建或更新接口不会返回完整关联字段或 `modifyTime`
- 真实环境偶发会出现单次 `count` 请求超时，但通常不影响整轮回归

当前回归状态补充：

- 2026-03-22 对 `https://autotest.local.vpc` 的 `run_tests.py --all` 回归中，验证、多租户、场景、模块测试通过
- 同日单独复跑 `concurrent_test_v2.py` 时，其余 4 个并发用例通过，仅 `test_concurrent_product_creation` 失败
- 当前唯一剩余失败为产品并发创建场景的性能阈值断言，实测 `avg_response_time = 3.141s`，阈值为 `< 3.0s`
