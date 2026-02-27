# AGENTS.md - MagicTest 代码库指南

## 项目概述
MagicTest 是 Python3 测试集项目，基于 pytest 运行。测试包括: session、cas、mock、file、platform、vmi 等模块。

## 统一配置文件

所有运行期配置统一在 `vmi/test_config.json` 中管理：

```json
{
  "server": { "url": "...", "namespace": "...", "environment": "..." },
  "credentials": { "username": "...", "password": "..." },
  "session": { "refresh_interval": 540, "timeout": 1800 },
  "pytest": { "markers": [...], "addopts": [...], "log_level": "..." },
  "concurrent": { "max_workers": 10, "timeout": 30, "retry_count": 3 },
  "aging": { "duration_hours": 24, "concurrent_threads": 10, ... },
  "coverage": { "source": ["."], "omit": [...] }
}
```

## 环境设置

```bash
# 激活虚拟环境（必须）
source ~/codespace/venv/bin/activate
cd vmi
pip install -r requirements.txt

# 安装开发依赖
pip install black isort flake8 mypy
```

## 测试命令

### 运行测试
```bash
cd vmi

# 统一测试运行器
python3 run_all_tests.py --all          # 所有测试
python3 run_all_tests.py --quick         # 快速测试
python3 run_all_tests.py --basic         # 基础功能测试
python3 run_all_tests.py --concurrent    # 并发测试
python3 run_all_tests.py --scenario      # 场景测试
python3 run_all_tests.py --aging 60      # 老化测试(60分钟)

# 使用 pytest
pytest                          # 运行所有测试
pytest -v                       # 详细输出
pytest -m "basic"               # 按标记运行
pytest -k "test_name"           # 按名称过滤
pytest --cov=. --cov-report=html  # 覆盖率
pytest -x                       # 失败即停
pytest --reruns 3               # 失败重试
```

### 运行单个测试
```bash
# 使用 pytest（推荐）
pytest test_file.py::TestClass::test_method -v

# 使用 unittest
python3 -m unittest path.to.TestClass.test_method
```

## Lint/代码检查

```bash
cd vmi

# 代码格式化
black . && isort . 

# 代码检查
flake8 . --max-line-length=120

# 类型检查
mypy . --ignore-missing-imports

# 完整检查
black . && isort . && flake8 . && mypy .
```

## 代码风格

### 导入顺序
1. 标准库 2. 第三方库 3. 本地模块

```python
import os
import sys
import logging
from typing import Dict, List, Optional

import requests

from session_manager import SessionManager
from sdk.base import MagicEntity
```

### 命名约定
- 类名: `PascalCase` (TestBaseWithSessionManager)
- 函数/方法: `snake_case` (run_concurrent_test)
- 变量: `snake_case` (max_workers)
- 常量: `UPPER_SNAKE_CASE` (MAX_RETRY_COUNT)
- 私有成员: `_leading_underscore`

### 类型提示
```python
def create_entity(
    entity_type: str,
    data: Dict[str, Any],
    retry_count: int = 3
) -> Optional[Dict[str, Any]]:
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
    return False
finally:
    session_manager.cleanup()
```

### 测试规范
```python
import unittest

class TestExample(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pass
    
    def setUp(self):
        pass
    
    def test_something(self):
        expected = 42
        result = calculate_something()
        self.assertEqual(result, expected)
        self.assertIsNotNone(result)
```

## 项目结构

```
vmi/
├── run_all_tests.py          # 主入口
├── test_config.json           # 统一配置文件
├── pyproject.toml             # 项目元数据/依赖
├── conftest.py                # pytest fixtures
├── session_manager.py         # 会话管理（9分钟刷新）
├── test_base_with_session_manager.py
├── concurrent_test_simple.py
├── scenario_test.py
├── performance_monitor.py
├── sdk/                      # SDK模块
└── requirements.txt
```

## 开发工作流

1. **创建测试**: 继承 `TestBaseWithSessionManager`
2. **确保会话**: 使用 `ensure_session_before_operation()`
3. **运行测试**: `pytest test_file.py::TestClass::test_method -v`
4. **修改配置**: 编辑 `test_config.json`

## 注意事项

- **必须**在虚拟环境中运行测试
- 会话管理: 9分钟自动刷新
- 不在代码中硬编码凭证
- 使用配置文件管理敏感信息

---

*适用于 MagicTest 代码库的 AI 助手*
