# VMI测试系统

## 概述
VMI（Virtual Machine Inventory）测试系统，用于自动化测试VMI系统的各项功能。

## 快速开始

### 1. 激活虚拟环境
```bash
source ~/codespace/venv/bin/activate
```

### 2. 使用统一测试运行器（推荐）
```bash
# 快速测试（基础+会话）
python3 run_all_tests.py --quick

# 运行所有测试
python3 run_all_tests.py --all

# 运行老化测试（60分钟）
python3 run_all_tests.py --aging 60

# 带性能监控的测试
python3 run_all_tests.py --all --performance --report performance_report.json

# 查看帮助
python3 run_all_tests.py --help
```

## 核心文件

### 测试运行器
- `run_all_tests.py` - 统一测试运行器（推荐），提供多种测试选项

### 会话管理
- `session_manager.py` - 会话管理器，自动处理会话刷新（9分钟间隔）

### 性能监控
- `performance_monitor.py` - 性能监控和报告工具

### 测试基础
- `test_base_with_session_manager.py` - 带会话管理的测试基类
- `base_test_case.py` - 基础测试类

### 测试用例
- `aging_test_simple.py` - 老化测试（集成会话管理）
- `concurrent_test.py` - 并发测试
- `scenario_test.py` - 场景测试

### 配置管理
- `test_config.py` - 配置管理系统
- `config_helper.py` - 配置辅助工具

## 使用方法

### 环境切换
通过 `--env` 参数切换测试环境：

| 环境参数 | 服务器地址 | SSL处理 | 说明 |
|---------|-----------|---------|------|
| `--env dev` | `http://localhost:8080` | 自动禁用 | 本地开发环境 |
| `--env test` | `https://autotest.local.vpc` | 自动判断 | 内部测试环境 |
| `--env remote` | `https://autotest.remote.vpc` | 自动禁用 | 远程测试环境 |
| `--env stress` | `https://autotest.stress.vpc` | 自动判断 | 压力测试环境 |
| `--env prod` | `https://autotest.prod.vpc` | 自动启用 | 生产验证环境 |

### 自定义配置
```bash
# 自定义服务器地址
python test_runner.py --server https://custom.server.com

# 自定义认证信息
python test_runner.py --username admin --password pass123

# 禁用SSL验证
python test_runner.py --no-ssl

# 调整性能参数
python test_runner.py --workers 20 --timeout 60
```

### 测试模式选择
```bash
# 只运行基础测试
python test_runner.py --mode basic

# 运行并发测试
python test_runner.py --mode concurrent

# 运行场景测试
python test_runner.py --mode scenario

# 运行老化测试
python test_runner.py --mode aging

# 运行所有测试（默认）
python test_runner.py --mode all
```

## 配置文件
测试运行器会自动创建和更新 `test_config.json` 文件，包含当前测试配置。

### 配置文件示例
```json
{
  "server_url": "https://autotest.remote.vpc",
  "username": "administrator",
  "password": "administrator",
  "namespace": "autotest",
  "test_mode": "functional",
  "environment": "remote",
  "max_workers": 10,
  "concurrent_timeout": 30,
  "retry_count": 3
}
```

## 工作原理

### 1. 配置更新
运行器根据命令行参数更新 `test_config.json` 文件。

### 2. SSL处理
根据服务器地址自动判断是否需要禁用SSL验证：
- 本地服务器（localhost）: 自动禁用SSL
- 远程服务器（remote.vpc）: 自动禁用SSL
- 生产服务器（prod.vpc）: 使用SSL验证

### 3. 老化测试说明
老化测试 (`--mode aging`) 用于长时间运行测试以验证系统稳定性：

#### 测试实体类型
- `partner`: 合作伙伴
- `product`: 产品
- `goods`: 商品
- `stockin`: 入库单
- `stockout`: 出库单

#### 操作类型
对于大多数实体，支持以下操作：
- `create`: 创建
- `read`: 读取
- `update`: 更新
- `delete`: 删除
- `list`: 列表

#### 特殊处理
由于服务器端API限制，以下实体跳过更新操作：
- `stockin`: 跳过update操作（服务器端要求完整的product字段）
- `stockout`: 跳过update操作（服务器端要求完整的product字段）

#### 配置参数
老化测试参数通过 `config_helper.get_aging_params()` 获取：
- `duration_hours`: 测试持续时间（小时）
- `concurrent_threads`: 并发线程数
- `operation_interval`: 操作间隔（秒）
- `max_data_count`: 最大数据量（万条）
- `performance_degradation_threshold`: 性能劣化阈值（百分比）

### 3. 测试执行
加载配置并执行相应的测试用例。

## 故障排除

### SSL证书错误
```bash
# 添加 --no-ssl 参数
python test_runner.py --env remote --no-ssl
```

### 连接超时
```bash
# 增加超时时间
python test_runner.py --timeout 60 --env remote
```

### 认证失败
```bash
# 指定正确的用户名密码
python test_runner.py --env remote --username admin --password correct_password
```

### 查看帮助
```bash
python test_runner.py --help
```

## 注意事项

1. **必须在虚拟环境中运行**
2. **生产环境建议使用SSL验证**
3. **配置文件会自动更新，无需手动修改**

## 文件结构
```
vmi/
├── run_all_tests.py              # 统一测试运行器（推荐）
├── session_manager.py            # 会话管理器
├── performance_monitor.py        # 性能监控工具
├── test_base_with_session_manager.py # 带会话管理的测试基类
├── aging_test_simple.py          # 老化测试（集成会话管理）
├── concurrent_test.py            # 并发测试
├── scenario_test.py              # 场景测试
├── base_test_case.py             # 基础测试类
├── test_config.py                # 配置管理系统
├── config_helper.py              # 配置辅助工具
├── test_config.json              # 配置文件（自动生成）
├── README.md                     # 本文件
├── TEST_GUIDE.md                 # 测试指南
├── DEPLOYMENT.md                 # 部署指南
└── backup_debug_files/           # 调试文件备份
```

## 核心功能说明

### 会话管理器 (`session_manager.py`)
- **自动刷新**: 每9分钟自动刷新会话，避免10分钟超时
- **状态监控**: 实时监控会话状态
- **错误恢复**: 自动尝试刷新和重新登录

### 统一测试运行器 (`run_all_tests.py`)
- **多种测试选项**: 支持基础测试、老化测试、会话测试等
- **性能监控**: 可选性能监控和报告生成
- **简化执行**: 单个命令运行多种测试组合

### 性能监控工具 (`performance_monitor.py`)
- **资源监控**: 监控CPU、内存使用情况
- **API统计**: 记录API调用次数和成功率
- **性能建议**: 自动分析并给出优化建议

## 技术支持
如有问题，请参考：
- `TEST_GUIDE.md` - 详细的测试指南
- `DEPLOYMENT.md` - 部署和配置指南