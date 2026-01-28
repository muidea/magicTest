# VMI 测试框架

## 📋 概述

这是一个完整的VMI（供应商管理库存）系统测试框架，提供统一的测试管理、并发压力测试、性能监控和报告生成功能。

## 🚀 快速开始

### 1. 环境准备

```bash
# 激活Python虚拟环境
source /home/rangh/codespace/venv/bin/activate

# 安装依赖包（如果尚未安装）
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
├── test_config.py                 # 配置管理系统
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
```

## 🛠️ 核心功能

### 1. 真实服务器交互系统

**重要更新**：测试框架现在与真实的VMI服务器进行交互，不再使用模拟模块。

**真实模块路径**：
- Session模块：`/home/rangh/codespace/magicTest/session/`
- CAS模块：`/home/rangh/codespace/magicTest/cas/cas/cas.py`

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

### 2. 配置管理系统 (`test_config.py`)

支持4种测试模式和4种环境配置：

**测试模式**：
- `development` - 开发环境（默认）
- `test` - 测试环境
- `pressure` - 压力测试环境
- `production` - 生产环境（只读）

**环境配置**：
- `dev` - 开发环境
- `test` - 测试环境
- `stress` - 压力测试环境
- `prod` - 生产环境

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
```

## 🔧 配置说明

### 配置文件

测试配置通过 `test_config.py` 管理，支持以下参数：

```python
# 服务器配置
server_url = "https://autotest.local.vpc"
namespace = "default"

# 并发测试参数
concurrent_params = {
    "max_workers": 10,
    "timeout": 30,
    "retry_count": 3
}

# 性能阈值
performance_thresholds = {
    "avg_response_time": 2.0,  # 秒
    "success_rate": 95.0,      # 百分比
    "throughput": 10.0         # 请求/秒
}
```

### 环境变量

可以通过环境变量覆盖配置：

```bash
# 设置测试模式
export TEST_MODE=pressure

# 设置服务器URL
export TEST_SERVER_URL=https://test.example.com

# 设置命名空间
export TEST_NAMESPACE=vmi_test
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
   sys.path.insert(0, '/home/rangh/codespace/magicTest')
   sys.path.insert(0, '/home/rangh/codespace/magicTest/cas')
   try:
       from cas.cas import Cas
       print('✅ CAS模块导入成功')
   except Exception as e:
       print('❌ CAS模块导入失败:', e)
   "
   ```

2. **SSL证书警告**
   ```bash
   # 测试环境使用自签名证书，警告正常
   # 如需禁用SSL验证（仅测试环境）
   export TEST_DISABLE_SSL_VERIFY=true
   ```

3. **并发测试失败：服务器负载过高**
   ```bash
   # 减少并发数
   export TEST_MAX_WORKERS=5
   export TEST_CONCURRENT_REQUESTS=10
   
   # 增加超时时间
   export TEST_TIMEOUT=60
   ```

4. **测试数据清理问题**
   ```bash
   # 测试会在服务器上创建真实数据
   # 确保有适当的数据清理机制
   # 或使用测试专用命名空间
   export TEST_NAMESPACE=vmi_test
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
- **重试策略**：对临时性错误实现自动重试
- **调试工具**：提供专门的调试脚本和工具

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

---

**最后更新**: 2026-01-28  
**版本**: 2.0.0  
**状态**: ✅ 生产就绪（真实服务器交互）