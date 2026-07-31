# platform — magicBase 平台核心接口回归测试套件

`magicTest/platform` 用于回归 `magicBase` 的核心平台接口。默认目标环境是 `https://autotest.local.vpc/api/v1`，可通过 `MAGICTEST_PLATFORM_BASE_URL` / `MAGICTEST_PLATFORM_NAMESPACE` 覆盖。

日常执行优先使用根入口 [magicTest/run_tests.py](/home/rangh/codespace/magicTest/run_tests.py)：

```bash
cd /home/rangh/codespace/magicTest
python3 run_tests.py --preset platform-smoke
```

本目录下的 `run_tests.py` 保留给平台模块级调试。

## 覆盖范围

本套件覆盖 `magicBase` 自身的全部平台核心接口：

| 模块 | 覆盖操作 | 用例数 |
|------|---------|--------|
| `application` | create / query / update / filter / start / stop / destroy | 14 |
| `block` | create / query / update / filter / destroy | 11 |
| `entity` | create / search / query / update / filter / enable / disable / destroy | 17 |
| `value` | insert / query / update / filter / delete | 12 |
| `operation_log` | write / filter | 9 |
| `totalizator` | register / filter / summary / refresh / unregister | 9 |
| `platform_scenario` | 跨模块集成场景（10 个场景） | 10 |

**总计：约 80+ 个测试用例**，覆盖基本 CRUD、边界条件、异常场景和跨模块集成。

## 层级说明

这里要特别区分两层：

- 本目录覆盖的是 `magicBase` 自身的 `application/block/entity/value/operation_log/totalizator` 平台接口
- 不覆盖 `magicPanel` 中那组 `artifact application / entity / subscription / feedback / notification` 运行期对象入口

因此：

- `magicTest/platform` 的通过，不能直接等价为 `magicPanel` 运行期对象接口已完成回归
- `magicPanel` 对象语义应以 `magicRunner/docs/design-panel-runtime-objects.md` 为准

## 快速开始

### 日常执行

```bash
cd /home/rangh/codespace/magicTest
source ~/codespace/venv/bin/activate
python3 run_tests.py --preset platform-smoke
```

### 平台目录内高级调试

只有在需要缩到模块或场景时，才进入本目录：

```bash
cd /home/rangh/codespace/magicTest/platform
python3 run_tests.py --list
python3 run_tests.py --module application
python3 run_tests.py --module operation_log
python3 run_tests.py --skip totalizator
python3 -m unittest platform_scenario_test -v
```

## 测试层次

### 1. 模块级单元测试

每个平台模块有独立的 `*_test.py` 文件，覆盖：

- **基本流程**：CRUD 操作的基本成功路径
- **边界条件**：超长名称、空字段、特殊字符
- **异常场景**：操作不存在对象、重复创建、无效参数
- **幂等性**：重复启用/禁用、重复注册

### 2. 跨模块集成场景测试

[`platform_scenario_test.py`](platform_scenario_test.py) 包含 10 个跨模块场景：

1. **完整平台链路**：Application → Block → Entity → Value 的端到端编排
2. **应用启动停止链路**：创建 → 启动 → 停止
3. **实体状态转换**：启用 → 禁用 → 再次启用
4. **操作日志**：写入并过滤操作日志
5. **总计器与实体值交互**：验证跨模块无干扰
6. **应用更新与过滤**：创建 → 更新 → 过滤验证
7. **区块依赖验证**：含实体的区块的依赖管理
8. **值更新与过滤**：插入 → 更新 → 过滤验证
9. **多区块实体**：实体关联多个区块
10. **多种字段类型**：创建含多种字段类型的实体

## 运行建议

### 日常开发后

```bash
cd /home/rangh/codespace/magicTest
source ~/codespace/venv/bin/activate
python3 run_tests.py --preset platform-smoke
```

### 改动平台核心模块后

```bash
cd /home/rangh/codespace/magicTest/platform
python3 run_tests.py --module application
python3 run_tests.py --module entity
python3 run_tests.py --module value

python3 -m unittest platform_scenario_test -v
```

### 改动日志/总计器模块后

```bash
cd /home/rangh/codespace/magicTest/platform
python3 run_tests.py --module operation_log
python3 run_tests.py --module totalizator
```

### 上线前完整回归

```bash
cd /home/rangh/codespace/magicTest
source ~/codespace/venv/bin/activate
python3 run_tests.py --preset platform-smoke
```

## 环境变量

| 变量名 | 说明 | 默认值 |
|--------|------|--------|
| `MAGICTEST_PLATFORM_BASE_URL` | 目标服务地址 | `https://autotest.local.vpc/api/v1` |
| `MAGICTEST_PLATFORM_NAMESPACE` | 命名空间 | 空 |
| `VERIFY_SSL` | SSL 验证开关 | `false` |
| `REQUEST_TIMEOUT` | 请求超时秒数 | `30.0` |

## 当前测试哲学

本套件不是纯单元测试，更接近"真实服务集成回归"。因此断言遵循以下原则：

- **真实业务约束明确时**，使用严格断言
- **服务当前允许但设计上未最终收敛的行为**，记录为 observation，不直接判失败
- **对偶发网络抖动保持容忍**，避免把环境噪声误判成产品缺陷

## 新增测试指引

### 新增模块级测试

1. 在 `platform/` 下创建新目录（如 `new_module/`）
2. 创建 `new_module.py`（API 封装层）
3. 创建 `new_module_test.py`（继承 `unittest.TestCase`）
4. 创建 `__init__.py`（同现有模式）
5. 在 [`run_tests.py`](run_tests.py) 的 `PLATFORM_TEST_MODULES` 注册表中添加新模块

### 新增场景测试

直接在 [`platform_scenario_test.py`](platform_scenario_test.py) 中新增以 `test_scenario_` 开头的方法。

## 测试配置文件

[`test_config.json`](test_config.json) 提供运行环境配置，包括：

- 目标服务地址和命名空间
- 认证凭据
- 会话参数
- 测试模块列表
- 覆盖率最低通过率
