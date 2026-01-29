# VMI 测试框架

## 📋 概述

这是一个完整的VMI（供应商管理库存）系统测试框架，提供统一的测试管理、并发压力测试、性能监控和报告生成功能。

## 🚀 快速开始

### 1. 环境准备

```bash
# 1. 创建并激活Python虚拟环境（如果尚未创建）
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 2. 安装依赖包
pip install pytest coverage matplotlib numpy
```

### 2. 验证测试框架

```bash
# 运行框架验证脚本
python test_framework_validation.py
```

### 3. 运行完整测试套件

```bash
# 运行所有测试（基础+并发+场景）
python test_runner.py --mode all --env test

# 或使用pytest直接运行
python -m pytest concurrent_test.py -v
```

## 📁 项目结构

```
vmi/
├── README.md                      # 本文档
├── test_config.py                 # 统一配置管理系统（增强版）
├── config_helper.py               # 配置助手模块
├── test_base.py                   # 测试基类和工具函数
├── concurrent_test.py             # 并发压力测试模块
├── scenario_test.py               # 业务场景测试
├── test_runner.py                 # 测试执行脚本（主入口）
├── test_adapter.py                # 测试适配器（迁移现有测试）
├── performance_report.py          # 性能监控和报告系统
├── test_framework_validation.py   # 框架验证脚本
├── TEST_FRAMEWORK_README.md       # 详细技术文档
├── setup_env.py                   # 环境设置脚本（新增）
├── run_tests.py                   # 测试运行包装器（新增）
├── session_mock.py                # 备份的模拟session模块
├── cas_mock/                      # 备份的模拟cas模块
├── warehouse/                     # 仓库相关测试
├── store/                         # 店铺相关测试
├── product/                       # 产品相关测试
├── partner/                       # 合作伙伴测试
└── credit/                        # 信用相关测试
├── aging_test.py                  # 完整老化测试（原始版本）
├── aging_test_simple.py           # 简化版老化测试（推荐使用）
└── test_simple_aging.py           # 老化测试验证脚本
```

## 🛠️ 核心功能

### 1. 真实服务器交互系统

**重要更新**：测试框架现在与真实的VMI服务器进行交互，不再使用模拟模块。

**真实模块路径**：
- Session模块：`../session/`（相对于vmi目录）
- CAS模块：`../cas/cas/cas.py`（相对于vmi目录）

**服务器配置**：
- 服务器URL：`https://autotest.local.vpc`
- 默认凭证：`administrator` / `administrator`
- 命名空间：`default`

**环境设置**：
```bash
# 使用环境设置脚本
python setup_env.py

# 或使用测试包装器
python run_tests.py --test-file store/store_test.py
```

### 2. 统一配置管理系统 (`test_config.py`)

**增强功能**：所有测试现在使用统一的配置管理系统，支持：

**配置特性**：
- ✅ **单例模式**：全局统一的配置实例
- ✅ **环境变量覆盖**：支持通过环境变量动态调整配置
- ✅ **配置文件支持**：支持从JSON文件加载配置
- ✅ **类型安全**：自动类型转换（字符串→整数/浮点数/布尔值）
- ✅ **配置分组**：服务器配置、并发配置、老化测试配置等

**配置分类**：
- **服务器配置**：服务器URL、登录凭证、命名空间
- **测试模式配置**：测试模式（functional, pressure, aging, scenario）、环境（dev, test, stress, prod）
- **并发测试配置**：最大工作线程数、超时时间、重试次数
- **老化测试配置**：持续时间、并发线程数、操作间隔、数据量限制、性能阈值
- **性能阈值配置**：响应时间、成功率、吞吐量阈值
- **日志配置**：日志级别、日志格式

**使用方式**：
```python
# 方式1：直接使用配置实例
from test_config import config
server_url = config.get('server_url')

# 方式2：使用配置助手（推荐）
from config_helper import get_server_url, get_credentials, get_aging_params
server_url = get_server_url()
credentials = get_credentials()
aging_config = get_aging_params()
```

### 2. 统一测试基类 (`test_base.py`)

所有测试继承 `TestBase` 类，提供：
- 统一的会话管理
- 自动配置加载
- 性能监控集成
- 数据清理工具

### 3. 并发压力测试 (`concurrent_test.py`)

包含5个并发测试场景：
1. `test_concurrent_store_creation` - 并发创建店铺（50个请求）
2. `test_concurrent_goods_operations` - 并发商品操作（30个请求）
3. `test_mixed_concurrent_operations` - 混合并发操作（100个请求）
4. `test_concurrent_shelf_management` - 并发货架管理（20个请求）
5. `test_concurrent_stock_operations` - 并发库存操作（60个请求）

### 4. 性能监控 (`performance_report.py`)

自动收集性能指标：
- 响应时间（平均、最小、最大）
- 吞吐量（请求/秒）
- 成功率
- 错误详情

## 📊 使用方法

### 方法1：使用测试运行器（推荐）

```bash
# 运行所有测试
python test_runner.py --mode all --env test

# 只运行并发测试
python test_runner.py --mode concurrent --env stress

# 只运行基础功能测试
python test_runner.py --mode basic --env test

# 只运行场景测试
python test_runner.py --mode scenario --env test

# 查看帮助
python test_runner.py --help
```

### 方法2：使用pytest

```bash
# 运行所有并发测试
python -m pytest concurrent_test.py -v

# 运行特定测试类
python -m pytest concurrent_test.py::ConcurrentStoreTest -v

# 运行单个测试方法
python -m pytest concurrent_test.py::ConcurrentStoreTest::test_concurrent_store_creation -v

# 运行现有测试
python -m pytest store/store_test.py::StoreTestCase::test_create_store -v
```

### 方法3：直接运行测试文件

```bash
# 运行并发测试
python concurrent_test.py

# 运行框架验证
python test_framework_validation.py

# 运行测试适配器
python test_adapter.py --migrate

# 运行老化测试（简化版）
python aging_test_simple.py --duration 1 --threads 3

# 验证老化测试功能
python test_simple_aging.py
```

## 🔧 配置说明

### 统一配置系统

所有测试现在使用 `test_config.py` 统一配置管理系统：

**配置文件结构**：
```python
# test_config.py 中的配置结构
config = {
    # 服务器配置
    'server_url': 'https://autotest.local.vpc',
    'username': 'administrator',
    'password': 'administrator',
    'namespace': 'autotest',
    
    # 测试模式配置
    'test_mode': 'functional',  # functional, pressure, aging, scenario
    'environment': 'test',      # dev, test, stress, prod
    
    # 并发测试配置
    'max_workers': 10,
    'concurrent_timeout': 30,
    'retry_count': 3,
    
    # 老化测试配置
    'aging_duration_hours': 24,
    'aging_concurrent_threads': 10,
    'aging_operation_interval': 1.0,
    'aging_max_data_count': 1000,  # 万条
    'aging_performance_degradation_threshold': 20.0,  # 百分比
    'aging_report_interval_minutes': 30,
    
    # 性能阈值
    'performance_thresholds': {
        'avg_response_time': 2.0,  # 秒
        'success_rate': 95.0,      # 百分比
        'throughput': 10.0         # 请求/秒
    }
}
```

### 环境变量覆盖

支持通过环境变量动态覆盖配置：

```bash
# 服务器配置
export TEST_SERVER_URL=https://test.example.com
export TEST_USERNAME=testuser
export TEST_PASSWORD=testpass
export TEST_NAMESPACE=vmi_test

# 测试模式配置
export TEST_MODE=pressure
export TEST_ENVIRONMENT=stress

# 并发测试配置
export TEST_MAX_WORKERS=5
export TEST_TIMEOUT=60
export TEST_RETRY_COUNT=5

# 老化测试配置
export AGING_DURATION_HOURS=12
export AGING_CONCURRENT_THREADS=5
export AGING_OPERATION_INTERVAL=2.0
export AGING_MAX_DATA_COUNT=500
export AGING_PERFORMANCE_THRESHOLD=15.0
export AGING_REPORT_INTERVAL=60

# 日志配置
export TEST_LOG_LEVEL=DEBUG
```

### 配置文件支持

支持从JSON配置文件加载配置：
```bash
# 创建配置文件
cat > test_config.json << EOF
{
  "server_url": "https://custom.example.com",
  "username": "custom_user",
  "aging_duration_hours": 48,
  "aging_concurrent_threads": 20
}
EOF

# 配置会自动从 test_config.json 加载
```

### 代码中使用配置

```python
# 方式1：使用配置助手（推荐）
from config_helper import get_server_url, get_credentials, get_aging_params

server_url = get_server_url()
credentials = get_credentials()
aging_config = get_aging_params()

# 方式2：直接使用配置实例
from test_config import config

server_url = config.get('server_url')
username = config.get('username')
duration_hours = config.get('aging_duration_hours')

# 方式3：在测试基类中自动使用
from test_base import TestBase

class MyTest(TestBase):
    def test_example(self):
        # 自动使用配置的服务器URL和凭证
        result = self.perform_operation()
```

## 📈 测试报告

### 自动生成的报告

每次测试运行会自动生成JSON格式的报告文件：
```
test_report_YYYYMMDD_HHMMSS.json
```

报告内容包含：
- 测试执行时间
- 各测试类型结果
- 性能指标
- 环境配置
- 总体统计

### 查看报告

```bash
# 查看最新报告
ls -la test_report_*.json

# 查看报告内容
cat test_report_20260128_183051.json | python -m json.tool
```

### 性能报告示例

```json
{
  "timestamp": "2026-01-28T18:30:51.942887",
  "total_duration": 0.313372,
  "test_results": [
    {
      "test_type": "concurrent",
      "total_tests": 5,
      "failures": 0,
      "errors": 0,
      "successful": 5,
      "success_rate": 100.0
    }
  ],
  "summary": {
    "total_tests": 5,
    "total_successful": 5,
    "total_failures": 0,
    "total_errors": 0,
    "overall_success_rate": 100.0,
    "status": "PASS"
  }
}
```

## 🧪 测试类型说明

### 1. 基础功能测试

测试VMI系统的核心功能：
- 店铺管理（创建、查询、更新、删除）
- 商品管理
- 库存管理（入库、出库）
- 仓库管理
- 货架管理
- 合作伙伴管理
- 产品管理

### 2. 并发压力测试

模拟多用户并发场景：
- 并发创建实体
- 并发更新操作
- 混合读写操作
- 数据一致性验证

### 3. 业务场景测试

基于真实业务场景：
- 单租户完整业务流程
- 端到端测试
- 业务规则验证

### 4. 长期老化测试

**新增功能**：长期稳定性测试框架，用于验证系统在持续负载下的稳定性。

**核心特性**：
- **五类实体完整测试**：partner, product, goods, stockin, stockout
- **并发持续运行**：多线程长时间执行CRUD操作
- **数据依赖管理**：自动处理实体间依赖关系（Product → Goods → Stockin/Stockout）
- **智能错误恢复**：指数退避重试机制（最多3次重试）
- **性能劣化监控**：检测响应时间增长超过阈值（默认20%）
- **数据量限制**：控制测试数据总量不超过设定限制（默认1000万条）
- **详细报告生成**：JSON和文本格式的完整测试报告
- **统一配置管理**：使用 `test_config.py` 统一配置系统

**老化测试配置**：
```python
# 配置存储在 test_config.py 中，支持环境变量覆盖
# 默认配置：
duration_hours = 24           # 测试持续时间（小时）
concurrent_threads = 10       # 并发线程数
operation_interval = 1.0      # 操作间隔（秒）
max_data_count = 1000         # 最大数据量（万条）
performance_degradation_threshold = 20.0  # 性能劣化阈值（百分比）
report_interval_minutes = 30  # 报告生成间隔（分钟）
```

**运行老化测试**：
```bash
# 使用默认配置运行24小时测试
python aging_test_simple.py

# 通过命令行参数自定义配置
python aging_test_simple.py \
  --duration 12 \
  --threads 5 \
  --interval 2.0 \
  --max-data 500 \
  --degradation-threshold 15.0 \
  --report-interval 60

# 通过环境变量自定义配置
export AGING_DURATION_HOURS=12
export AGING_CONCURRENT_THREADS=5
export AGING_OPERATION_INTERVAL=2.0
python aging_test_simple.py
```

**数据格式修复**：
- **Stockin/Stockout API**：需要完整的goodsInfo对象，包含sku, product, type, count, price, shelf字段
- **Goods API**：需要shelf数组和store字段
- **类型字段**：type字段应为整数（入库=1，出库=2）

## 🔍 故障排除

### 常见问题

1. **真实服务器连接失败**
   ```bash
   # 检查服务器可访问性
   curl -k https://autotest.local.vpc
   
   # 检查Python路径设置
   python setup_env.py --verify
   
    # 验证真实模块导入
    python -c "
    import sys
    import os
    
    # 自动计算项目路径
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    
    sys.path.insert(0, project_root)
    sys.path.insert(0, os.path.join(project_root, 'cas'))
    
    try:
        from cas.cas import Cas
        print('✅ CAS模块导入成功')
        print(f'   项目根目录: {project_root}')
    except Exception as e:
        print('❌ CAS模块导入失败:', e)
        print(f'   尝试的路径: {project_root}, {os.path.join(project_root, "cas")}')
    "
   ```

2. **老化测试数据格式错误**
   ```bash
   # Stockin/Stockout API需要完整的goodsInfo对象
   # 错误格式: goodsInfo: [{'id': goods_id}]
   # 正确格式: goodsInfo: [{'id': goods_id, 'sku': 'SKU_001', 'product': {'id': 1}, 'type': 1, 'count': 10, 'price': 100.0, 'shelf': [{'id': 1}]}]
   
   # 验证数据格式
   python test_api_validation.py
   ```

3. **Python虚拟环境问题**
   ```bash
   # 使用正确的虚拟环境路径
   source ~/codespace/venv/bin/activate
   
   # 验证Python环境
   which python3
   python3 --version
   pip list | grep requests
   ```

4. **配置加载问题**
   ```bash
   # 验证配置加载
   python3 -c "from test_config import config; print(config.get('server_url'))"
   
   # 验证配置助手
   python3 -c "from config_helper import get_server_url; print(get_server_url())"
   
   # 检查环境变量
   env | grep -E "(TEST_|AGING_)"
   ```

5. **SSL证书警告**
   ```bash
   # 测试环境使用自签名证书，警告正常
   # 如需禁用SSL验证（仅测试环境）
   export TEST_DISABLE_SSL_VERIFY=true
   ```

6. **并发测试失败：服务器负载过高**
   ```bash
   # 减少并发数
   export TEST_MAX_WORKERS=5
   export TEST_CONCURRENT_REQUESTS=10
   
   # 增加超时时间
   export TEST_TIMEOUT=60
   ```

7. **测试数据清理问题**
   ```bash
   # 测试会在服务器上创建真实数据
   # 确保有适当的数据清理机制
   # 或使用测试专用命名空间
   export TEST_NAMESPACE=vmi_test
   ```

8. **老化测试线程停止问题**
   ```bash
   # 检查线程同步机制
   # 确保使用正确的stop_event设置
   # 验证线程daemon设置
   
   # 查看线程状态
   ps aux | grep python | grep aging
   ```

9. **配置不生效问题**
   ```bash
   # 检查配置优先级：环境变量 > 配置文件 > 默认配置
   # 重新导入配置模块
   python3 -c "
   import sys
   if 'test_config' in sys.modules:
       del sys.modules['test_config']
   from test_config import config
   print('当前服务器URL:', config.get('server_url'))
   "
   
   # 检查配置助手
   python3 -c "from config_helper import get_server_url; print('配置助手URL:', get_server_url())"
   ```

### 调试模式

```bash
# 启用详细日志
export TEST_DEBUG=true

# 启用性能详细日志
export PERFORMANCE_DEBUG=true

# 运行测试
python test_runner.py --mode all --env test
```

## 📝 编写新测试

### 继承TestBase

```python
from test_base import TestBase

class MyNewTest(TestBase):
    def setUp(self):
        super().setUp()
        # 初始化测试数据
    
    def test_my_feature(self):
        # 编写测试逻辑
        result = self.perform_operation()
        self.assertTrue(result)
    
    def tearDown(self):
        # 清理测试数据
        super().tearDown()
```

### 使用并发测试框架

```python
from test_base import TestBase, ConcurrentTestMixin
from concurrent_test import ConcurrentTestRunner, ConcurrentTestFactory

class MyConcurrentTest(TestBase, ConcurrentTestMixin):
    def test_concurrent_operation(self):
        runner = ConcurrentTestRunner(max_workers=10)
        
        def operation(worker_id: int):
            return {"data": f"test_{worker_id}"}
        
        test_func = ConcurrentTestFactory.create_create_test(
            self.__class__, 'entity_type', operation
        )
        
        result = runner.run_concurrent_test(
            test_func,
            'my_concurrent_test',
            num_requests=50
        )
        
        self.assertGreaterEqual(result.successful_requests, 45)
```

### 使用性能监控

```python
from performance_report import PerformanceMonitor

class MyPerformanceTest(TestBase):
    def test_performance(self):
        monitor = PerformanceMonitor()
        
        with monitor.measure('my_operation'):
            # 执行需要监控的操作
            result = self.expensive_operation()
        
        metrics = monitor.get_metrics()
        self.assertLess(metrics['my_operation']['avg_time'], 1.0)
```

## 🔄 迁移现有测试

### 自动迁移

```bash
# 运行测试适配器
python test_adapter.py --migrate
```

### 手动适配

现有测试无需修改即可运行，但如果需要集成新功能：

```python
# 在现有测试中添加
from test_adapter import LegacyTestAdapter

class MyExistingTest(LegacyTestAdapter):
    # 现在可以使用所有新框架功能
    def test_with_new_features(self):
        # 使用性能监控
        self.performance_monitor.record_metric('my_metric', 0.5)
        
        # 使用配置管理
        mode = self._config.get_test_mode()
        print(f"当前测试模式: {mode}")
```

## 🎯 最佳实践

### 1. 真实服务器测试
- **环境隔离**：在专用测试环境运行
- **数据管理**：测试后清理创建的数据
- **凭证安全**：使用测试专用账户
- **监控告警**：监控服务器性能和资源使用

### 2. 并发测试优化
- **渐进式负载**：从低并发开始，逐步增加
- **性能基准**：建立性能基准线
- **错误重试**：实现智能重试机制
- **资源监控**：监控服务器CPU、内存、网络

### 3. 测试数据策略
- **测试专用数据**：使用专用测试数据
- **数据隔离**：使用测试命名空间
- **自动清理**：实现测试数据自动清理
- **数据验证**：验证服务器数据一致性

### 4. 错误处理与调试
- **详细日志**：记录完整的请求/响应信息
- **错误分类**：区分网络错误、服务器错误、业务错误
- **重试策略**：对临时性错误实现自动重试（指数退避）
- **调试工具**：提供专门的调试脚本和工具
- **错误统计**：按实体类型和操作类型分类统计错误

### 5. 老化测试最佳实践
- **渐进式负载**：从低并发开始，逐步增加线程数
- **性能基准**：建立初始性能基线，监控劣化趋势
- **数据管理**：控制测试数据总量，避免数据库过载
- **监控告警**：设置性能劣化阈值，自动停止测试
- **报告分析**：定期生成测试报告，分析系统稳定性趋势

## 📞 支持与反馈

### 获取帮助

```bash
# 查看框架文档
cat TEST_FRAMEWORK_README.md

# 运行帮助命令
python test_runner.py --help
python test_adapter.py --help
```

### 报告问题

遇到问题时，请提供：
1. 完整的错误信息
2. 测试命令和参数
3. 环境信息（Python版本、操作系统）
4. 相关配置文件

### 贡献指南

1. Fork项目
2. 创建功能分支
3. 编写测试用例
4. 运行现有测试确保通过
5. 提交Pull Request

## 📄 许可证

本项目遵循MIT许可证。详见LICENSE文件。

## 🏆 致谢

感谢所有贡献者和测试人员，特别感谢：
- 测试框架设计团队
- 性能优化贡献者
- 文档编写人员

## 🔄 更新日志

### 版本 2.2.0 (2026-01-29)
**统一配置系统**：
- ✅ 增强的 `test_config.py` 配置管理系统
- ✅ 单例模式全局配置实例
- ✅ 环境变量动态配置覆盖
- ✅ 配置文件支持（JSON格式）
- ✅ 配置助手模块 `config_helper.py`
- ✅ 类型安全的配置值转换

**配置整合**：
- ✅ 所有测试文件使用统一配置
- ✅ 老化测试配置集成到统一系统
- ✅ 服务器URL和凭证集中管理
- ✅ 并发测试参数统一配置
- ✅ 性能阈值集中管理

### 版本 2.1.0 (2026-01-29)
**新增功能**：
- ✅ 长期老化测试框架
- ✅ 五类实体完整测试支持
- ✅ 数据依赖管理（Product → Goods → Stockin/Stockout）
- ✅ 智能错误恢复和重试机制
- ✅ 性能劣化监控和告警
- ✅ 详细的测试报告生成

**修复问题**：
- ✅ Stockin/Stockout API数据格式修复
- ✅ Goods API字段要求修复
- ✅ 线程执行问题修复
- ✅ Python虚拟环境路径修复

**技术改进**：
- ✅ 改进的错误分类和统计
- ✅ 指数退避重试策略
- ✅ 数据量限制控制
- ✅ 更详细的性能监控

### 版本 2.0.0 (2026-01-28)
- 初始版本：真实服务器交互测试框架

---
**最后更新**: 2026-01-29  
**版本**: 2.2.0  
**状态**: ✅ 生产就绪（包含统一配置和老化测试）