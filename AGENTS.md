# AGENTS.md - MagicTest 代码库指南

## 项目概述
MagicTest 是一个测试集项目，主要用来完成平台测试工作。基于Python3开发，使用Pytest进行测试。运行在~/codespace/venv 管理的python环境里。

当前包含的测试如下：
1. session: 基础会话管理，属于辅助功能
2. cas: 测试平台接入认证
3. mock：mock数据辅助功能
4. file: 测试平台文件管理服务
5. platform: 测试平台基础服务
6. vmi: 测试vmi应用功能，包括会员，产品，仓库，货架，店铺，出库，入库，商品，积分等功能测试


## 环境设置

### 虚拟环境（必须）
```bash
# 激活虚拟环境
source ~/codespace/venv/bin/activate

# 验证环境
python3 -c "import sys; print(f'Python {sys.version}')"
```

### 依赖安装
```bash
# VMI测试系统依赖
cd vmi
pip install -r requirements.txt

# 可选：性能监控依赖
pip install psutil matplotlib numpy
```

## 构建/测试命令

### VMI测试系统（主要工作区）
```bash
cd vmi

# 运行所有测试（推荐）
python3 run_all_tests.py --all

# 快速测试（基础+会话）
python3 run_all_tests.py --quick

# 运行特定测试类型
python3 run_all_tests.py --basic      # 基础功能测试
python3 run_all_tests.py --concurrent # 并发测试
python3 run_all_tests.py --scenario   # 场景测试
python3 run_all_tests.py --session    # 会话管理器测试
python3 run_all_tests.py --product    # product.delete测试

# 老化测试（支持分钟单位）
python3 run_all_tests.py --aging 1    # 1分钟测试
python3 run_all_tests.py --aging 60   # 60分钟测试

# 带性能监控
python3 run_all_tests.py --all --performance --report performance_report.json

# 查看帮助
python3 run_all_tests.py --help
```

### 运行单个测试文件
```bash
# 使用Python直接运行
python3 concurrent_test_simple.py
python3 scenario_test.py
python3 aging_test_simple.py

# 使用unittest运行特定测试类
python3 -m unittest concurrent_test_simple.TestConcurrentOperations
```

### 测试运行器（旧版）
```bash
# 使用统一测试运行器（支持环境切换）
python3 test_runner.py --env test      # 测试环境
python3 test_runner.py --env remote    # 远程环境
python3 test_runner.py --env dev       # 开发环境
python3 test_runner.py --mode basic    # 基础测试模式
python3 test_runner.py --mode concurrent # 并发测试模式
```

## 代码风格指南

### 导入顺序
1. 标准库导入
2. 第三方库导入
3. 本地模块导入
4. 相对导入

```python
# 正确示例
import os
import sys
import time
import logging
from typing import Dict, List, Optional
from datetime import datetime

import requests
import concurrent.futures

from session_manager import SessionManager
from test_base_with_session_manager import TestBaseWithSessionManager
from sdk.base import MagicEntity
```

### 命名约定
- **类名**: `PascalCase` - `TestBaseWithSessionManager`, `ConcurrentTestRunner`
- **函数/方法名**: `snake_case` - `run_concurrent_test`, `ensure_session_valid`
- **变量名**: `snake_case` - `max_workers`, `session_manager`
- **常量**: `UPPER_SNAKE_CASE` - `MAX_RETRY_COUNT`, `SESSION_TIMEOUT`
- **私有成员**: `_leading_underscore` - `_private_method`, `_internal_variable`

### 类型提示
```python
from typing import Dict, List, Optional, Any, Callable

def create_entity(
    entity_type: str,
    data: Dict[str, Any],
    retry_count: int = 3
) -> Optional[Dict[str, Any]]:
    """创建实体并返回结果"""
    pass
```

### 错误处理
```python
try:
    result = session_manager.create_session()
    if not result:
        logger.error("创建会话失败")
        return False
except ConnectionError as e:
    logger.error(f"连接错误: {e}")
    raise
except Exception as e:
    logger.error(f"未知错误: {e}")
    # 重新抛出或处理
    return False
finally:
    # 清理资源
    session_manager.cleanup()
```

### 日志记录
```python
import logging

logger = logging.getLogger(__name__)

def some_function():
    logger.debug("详细调试信息")
    logger.info("常规操作信息")
    logger.warning("警告信息")
    logger.error("错误信息")
    logger.critical("严重错误")
```

### 测试编写规范
```python
import unittest

class TestExample(unittest.TestCase):
    """测试类文档字符串"""
    
    @classmethod
    def setUpClass(cls):
        """类级别初始化"""
        pass
    
    def setUp(self):
        """测试方法前初始化"""
        pass
    
    def test_something(self):
        """测试方法 - 描述测试内容"""
        # 准备
        expected = 42
        
        # 执行
        result = calculate_something()
        
        # 断言
        self.assertEqual(result, expected)
        self.assertIsNotNone(result)
        self.assertIn("key", result)
    
    def tearDown(self):
        """测试方法后清理"""
        pass
    
    @classmethod
    def tearDownClass(cls):
        """类级别清理"""
        pass
```

### 文档字符串
```python
def complex_function(param1: str, param2: int = 10) -> Dict[str, Any]:
    """函数功能描述
    
    Args:
        param1: 参数1描述
        param2: 参数2描述，默认10
        
    Returns:
        返回结果描述，包含键值说明
        
    Raises:
        ValueError: 当参数无效时
        ConnectionError: 当连接失败时
        
    Examples:
        >>> result = complex_function("test", 20)
        >>> print(result["status"])
    """
    pass
```

## 项目结构

### VMI测试系统 (`vmi/`)
```
vmi/
├── run_all_tests.py          # 统一测试运行器（主入口）
├── test_runner.py           # 旧版测试运行器
├── session_manager.py       # 会话管理
├── test_base_with_session_manager.py  # 测试基类
├── test_base.py             # 基础测试类
├── concurrent_test_simple.py # 简化并发测试
├── concurrent_test_v2.py    # 完整并发测试
├── scenario_test.py         # 场景测试
├── aging_test_simple.py     # 老化测试
├── performance_monitor.py   # 性能监控
├── config_helper.py         # 配置管理
├── sdk/                     # SDK模块
│   ├── base.py
│   ├── warehouse.py
│   ├── product.py
│   └── ...
├── test_config.json         # 测试配置
└── requirements.txt         # 依赖
```

### 其他重要目录
- `cas/` - CAS认证系统
- `file/` - 文件处理模块
- `platform/` - 平台核心模块
- `session/` - 会话管理
- `mock/` - 模拟数据

## 开发工作流

### 1. 创建新测试
```python
# 基于现有测试基类
from test_base_with_session_manager import TestBaseWithSessionManager

class NewFeatureTest(TestBaseWithSessionManager):
    def test_new_feature(self):
        # 使用会话管理器确保会话有效
        if not self.ensure_session_before_operation():
            self.fail("会话无效")
        
        # 使用SDK执行操作
        result = self.execute_with_session_check(
            self.product_sdk.some_operation,
            operation_data
        )
        
        # 断言验证
        self.assertIsNotNone(result)
        self.assertIn("expected_key", result)
```

### 2. 运行和调试
```bash
# 激活环境
source ~/codespace/venv/bin/activate

# 运行新测试
cd vmi
python3 -m unittest -v path.to.NewFeatureTest

# 调试模式
python3 -m pdb run_all_tests.py --basic
```

### 3. 代码质量
- 使用类型提示
- 添加适当的文档字符串
- 遵循现有代码风格
- 添加适当的错误处理
- 使用现有的日志记录模式

## 注意事项

### 关键要求
1. **必须在虚拟环境中运行测试**
2. **会话管理**: 使用 `session_manager.py` 处理会话刷新（9分钟间隔）
3. **错误恢复**: 实现适当的重试和错误处理机制
4. **资源清理**: 测试完成后清理创建的资源

### 性能考虑
- 并发测试使用 `ThreadPoolExecutor` 而不是创建过多线程
- 使用连接池管理HTTP连接
- 避免在测试中创建过多数据
- 及时清理测试数据

### 安全考虑
- 不在代码中硬编码凭证
- 使用配置文件管理敏感信息
- 遵循最小权限原则
- 验证输入数据

## 故障排除

### 常见问题
1. **导入错误**: 确保在虚拟环境中，并正确设置PYTHONPATH
2. **会话超时**: 检查 `session_manager.py` 的刷新配置
3. **连接失败**: 验证 `test_config.json` 中的服务器地址
4. **依赖缺失**: 运行 `pip install -r requirements.txt`

### 调试技巧
```python
# 启用详细日志
import logging
logging.basicConfig(level=logging.DEBUG)

# 添加调试输出
logger.debug(f"变量值: {variable}")

# 使用pdb调试
import pdb; pdb.set_trace()
```

---

*最后更新: 2026-01-31*  
*适用于所有在MagicTest代码库工作的AI助手*