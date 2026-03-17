# VMI 测试指南

本文档面向日常使用和后续维护，目标是说明当前测试套件如何运行、如何扩展，以及哪些行为是刻意保持宽松的。

## 1. 运行前提

- Python 虚拟环境：`/home/rangh/codespace/venv`
- 默认目标服务：`https://autotest.local.vpc`
- 默认账号：`administrator / administrator`
- 默认命名空间：`autotest`

准备命令：

```bash
cd /home/rangh/codespace/magicTest/vmi
source /home/rangh/codespace/venv/bin/activate
```

如果环境中设置了代理，建议回归前显式清空：

```bash
HTTPS_PROXY= HTTP_PROXY= https_proxy= http_proxy= \
NO_PROXY=autotest.local.vpc no_proxy=autotest.local.vpc \
python3 -m unittest discover -s . -p '*_test.py' -v
```

## 2. 入口说明

统一入口是 [run_tests.py](/home/rangh/codespace/magicTest/vmi/run_tests.py)。

支持的主命令：

```bash
python3 run_tests.py --check-config
python3 run_tests.py --quick
python3 run_tests.py --validation
python3 run_tests.py --multi-tenant
python3 run_tests.py --concurrent
python3 run_tests.py --scenario
python3 run_tests.py --module
python3 run_tests.py --aging 30
python3 run_tests.py --all
python3 run_tests.py --pytest --all
```

行为说明：

- `--quick`
  只跑框架验证，适合部署后快速检查。
- `--validation`
  跑配置、导入、基类和多租户基础验证。
- `--multi-tenant`
  跑多租户配置和管理器测试。
- `--concurrent`
  跑并发测试。
- `--scenario`
  跑业务场景测试。
- `--module`
  跑所有模块级实体测试。
- `--aging N`
  跑 `N` 分钟老化测试，内部会转换为小时传给 `aging_test_simple.py`。
- `--all`
  组合执行验证、多租户、并发、场景和模块测试。

## 3. 测试结构

### 3.1 基础层

- [test_bootstrap.py](/home/rangh/codespace/magicTest/vmi/test_bootstrap.py)
  统一补齐路径和告警抑制。
- [config_helper.py](/home/rangh/codespace/magicTest/vmi/config_helper.py)
  读取统一配置。
- [tenant_config_helper.py](/home/rangh/codespace/magicTest/vmi/tenant_config_helper.py)
  读取和展开多租户配置。
- [session_manager.py](/home/rangh/codespace/magicTest/vmi/session_manager.py)
  会话创建、自动刷新、失效恢复。

### 3.2 测试基础设施层

- [test_vmi_base.py](/home/rangh/codespace/magicTest/vmi/test_vmi_base.py)
  为实体测试提供通用日志、清理和数量统计能力。
- [test_dependency_helper.py](/home/rangh/codespace/magicTest/vmi/test_dependency_helper.py)
  为库存相关测试构造依赖实体。
- [test_base_with_session_manager.py](/home/rangh/codespace/magicTest/vmi/test_base_with_session_manager.py)
  旧的通用会话测试基类，仍被多租户和部分场景使用。
- [test_base_multi_tenant.py](/home/rangh/codespace/magicTest/vmi/test_base_multi_tenant.py)
  多租户测试基类。

### 3.3 用例层

- `credit/`
- `order/`
- `partner/`
- `product/`
- `status/`
- `store/`
- `warehouse/`
- [scenario_test.py](/home/rangh/codespace/magicTest/vmi/scenario_test.py)
- [concurrent_test_v2.py](/home/rangh/codespace/magicTest/vmi/concurrent_test_v2.py)
- [aging_test_simple.py](/home/rangh/codespace/magicTest/vmi/aging_test_simple.py)

## 4. 配置说明

### 4.1 单租户配置

当前标准配置文件是 [test_config.json](/home/rangh/codespace/magicTest/vmi/test_config.json)：

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

### 4.2 多租户配置

如果启用多租户，需要追加 `multi_tenant`：

```json
{
  "multi_tenant": {
    "enabled": true,
    "default_tenant": "autotest",
    "tenants": [
      {
        "id": "autotest",
        "server_url": "https://autotest.local.vpc",
        "username": "administrator",
        "password": "administrator",
        "namespace": "autotest",
        "enabled": true
      },
      {
        "id": "tenant2",
        "server_url": "https://tenant2.local.vpc",
        "username": "administrator",
        "password": "administrator",
        "namespace": "tenant2",
        "enabled": true
      }
    ]
  }
}
```

注意：

- 当前 `tenant_config_helper.py` 始终会补一个默认 `autotest` 租户
- 多租户关闭时，测试只对 `autotest` 生效
- 多租户验证测试默认使用 mock，避免依赖真实多租户环境

## 5. 如何新增测试

### 5.1 新增实体测试

推荐模式：

1. 继承 [VMITestCase](/home/rangh/codespace/magicTest/vmi/test_vmi_base.py)
2. 使用 `build_cleanup_registry` 维护清理列表
3. 依赖实体优先走 [test_dependency_helper.py](/home/rangh/codespace/magicTest/vmi/test_dependency_helper.py)
4. 允许记录“当前系统行为观察”，但不要把未经确认的业务约束直接写死为失败断言

### 5.2 新增离线/框架测试

推荐放在根目录并使用：

- mock 替代真实登录和真实网络
- `_clear_config_cache()` 清理配置缓存
- 只断言接口契约和当前配置结构，不硬编码环境状态

## 6. 当前测试哲学

本套件不是纯单元测试，更接近“真实服务集成回归”。因此断言遵循以下原则：

- 真实业务约束明确时，使用严格断言
- 服务当前允许但设计上未最终收敛的行为，记录为 observation，不直接判失败
- 对偶发网络抖动保持容忍，避免把环境噪声误判成产品缺陷

当前已知保留项：

- 同一会员允许存在多条 `credit report`
- `productInfo.sku` 当前允许重复
- 某些接口创建或更新后不会返回完整关联字段
- 某些更新接口不会返回 `modifyTime`

## 7. 推荐回归顺序

日常开发后：

```bash
python3 run_tests.py --quick
python3 run_tests.py --module
```

改动会话、多租户或基础设施后：

```bash
python3 run_tests.py --validation
python3 run_tests.py --multi-tenant
python3 run_tests.py --module
```

改动并发、性能或清理逻辑后：

```bash
python3 run_tests.py --concurrent
python3 run_tests.py --scenario
python3 run_tests.py --aging 30
```

上线前完整回归：

```bash
python3 run_tests.py --all
python3 -m unittest discover -s . -p '*_test.py' -v
```

## 8. 结果判断

优先关注：

- 测试是否真正失败
- 是否出现大面积会话失效
- 是否出现依赖实体构造失败
- 是否出现清理不完整导致的级联失败

次级关注：

- observation 类警告
- 偶发单次超时但整体仍通过
- 个别接口返回字段不完整
