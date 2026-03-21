# VMI 测试架构说明

本文档面向维护者，描述 `magicTest/vmi` 当前测试基础设施的分层、职责边界和稳定基线，便于维护与回归。

## 1. 设计目标

当前测试体系同时承担三类职责：

- 验证真实部署服务的业务行为
- 提供基础设施级的离线验证，避免改动基础代码后立即依赖远端环境
- 为并发、老化和多租户场景提供可复用的测试骨架

因此它不是纯单元测试仓库，而是“集成回归 + 基础设施自检 + 长稳验证”的混合体。

## 2. 分层结构

### 2.1 启动与路径层

- [test_bootstrap.py](/home/rangh/codespace/magicTest/vmi/test_bootstrap.py)

职责：

- 自动向 `sys.path` 注入共享依赖路径
- 统一抑制 `InsecureRequestWarning`
- 避免各测试文件重复做路径修补

### 2.2 配置层

- [config_helper.py](/home/rangh/codespace/magicTest/vmi/config_helper.py)
- [tenant_config_helper.py](/home/rangh/codespace/magicTest/vmi/tenant_config_helper.py)
- [test_config.json](/home/rangh/codespace/magicTest/vmi/test_config.json)

职责：

- 提供统一配置读取入口
- 将单租户配置扩展为多租户视图
- 让测试代码只依赖 helper，不直接散落解析 JSON

现状约束：

- `config_helper.py` 使用 `_config_cache`
- 测试修改配置文件后，需要显式清理缓存
- 多租户 helper 当前默认始终补 `autotest` 租户，保证兼容旧测试

### 2.3 会话层

- [session_manager.py](/home/rangh/codespace/magicTest/vmi/session_manager.py)

职责：

- 创建 `MagicSession`
- 通过 `Cas` 完成登录
- 管理自动刷新和重连
- 对上层测试隐藏 token 生命周期细节

设计约束：

- 默认刷新间隔 540 秒
- 默认会话超时 1800 秒
- 并发测试为每个线程建立独立会话，避免共享状态污染

### 2.4 测试基础设施层

- [test_vmi_base.py](/home/rangh/codespace/magicTest/vmi/test_vmi_base.py)
- [test_dependency_helper.py](/home/rangh/codespace/magicTest/vmi/test_dependency_helper.py)
- [test_base_with_session_manager.py](/home/rangh/codespace/magicTest/vmi/test_base_with_session_manager.py)
- [test_base_multi_tenant.py](/home/rangh/codespace/magicTest/vmi/test_base_multi_tenant.py)

职责划分：

- `test_vmi_base.py`
  面向实体测试，负责统一日志、清理注册表、数量统计和清理逻辑
- `test_dependency_helper.py`
  负责构造库存、商品、状态等复合依赖数据
- `test_base_with_session_manager.py`
  提供会话测试基类与性能监视辅助
- `test_base_multi_tenant.py`
  在会话测试基类之上扩展多租户能力

当前结构：

- 实体测试统一通过 `test_vmi_base.py` 管理日志、清理注册表和数量统计
- 依赖构造统一通过 `test_dependency_helper.py` 组织
- 多租户与会话管理测试通过 `test_base_with_session_manager.py` 和 `test_base_multi_tenant.py` 组织

## 3. 用例层分类

### 3.1 离线验证

- [test_complete_validation.py](/home/rangh/codespace/magicTest/vmi/test_complete_validation.py)
- [test_multi_tenant.py](/home/rangh/codespace/magicTest/vmi/test_multi_tenant.py)
- [test_multi_tenant_example.py](/home/rangh/codespace/magicTest/vmi/test_multi_tenant_example.py)

特点：

- 尽量用 mock 替代真实网络
- 验证配置契约、导入链路和多租户基础能力
- 适合作为最先执行的烟雾测试

### 3.2 实体级集成测试

- `credit/`
- `order/`
- `partner/`
- `product/`
- `status/`
- `store/`
- `warehouse/`

特点：

- 直接调用 SDK 与真实服务交互
- 使用真实依赖实体
- 需要明确清理策略，避免污染后续用例

### 3.3 场景与性能测试

- [scenario_test.py](/home/rangh/codespace/magicTest/vmi/scenario_test.py)
- [concurrent_test_v2.py](/home/rangh/codespace/magicTest/vmi/concurrent_test_v2.py)
- [aging_test_simple.py](/home/rangh/codespace/magicTest/vmi/aging_test_simple.py)

特点：

- 更关注整体行为、稳定性和性能
- 可接受一定环境波动
- 输出中允许存在 observation 或性能提示，不必全部转为失败断言

## 4. 运行路径

统一入口是 [run_tests.py](/home/rangh/codespace/magicTest/vmi/run_tests.py)。

执行模型：

1. 读取 `test_config.json`
2. 根据参数选择 `validation`、`multi-tenant`、`concurrent`、`scenario`、`module` 或 `aging`
3. 通过 `subprocess.run` 调用具体脚本或 `pytest`
4. 汇总每个测试套件的成功状态和耗时

执行特征：

- 使用统一入口方便日常操作
- 统一汇总各测试套件的成功状态和耗时

## 5. 当前断言策略

为了让回归更稳，当前测试策略有明确分层：

- 明确业务约束：严格断言
- 当前系统允许但设计未收敛的行为：记录 observation，不直接失败
- 环境瞬时抖动：优先识别为环境噪声，而不是功能回归

近期保留为 observation 的行为包括：

- 同一会员可存在多条 `credit report`
- `productInfo.sku` 当前可重复
- 部分接口不返回完整关联字段
- 部分更新不返回 `modifyTime`

## 6. 最近整理后的改进点

本轮已完成：

- 统一引导逻辑收敛到 `test_bootstrap.py`
- 依赖构造收敛到 `test_dependency_helper.py`
- 清理和统计逻辑收敛到 `test_vmi_base.py`
- 现有实体测试已统一切换到清理注册表模式，不再保留分散的类级/用例级清理记录写法
- 2026-03-20 已通过 `run_tests.py --all` 全量回归，验证、多租户、并发、场景和模块测试全部通过
- 大量测试文件去掉非结构化 `print`
- 多租户离线测试改成更稳定的 mock 驱动
- `run_tests.py`、`concurrent_test_v2.py`、`cas_mock/cas.py` 统一改为日志输出
