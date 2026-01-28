# VMI测试框架 - 快速开始指南

## ⚡ 5分钟快速开始

### 第1步：环境准备（30秒）
```bash
# 激活Python虚拟环境
source /home/rangh/codespace/venv/bin/activate

# 验证Python环境
python --version
# 应该显示: Python 3.12.3

# 设置真实服务器环境
python setup_env.py
# 应该显示: ✅ 环境设置成功
```

### 第2步：验证框架（1分钟）
```bash
# 运行框架验证（真实服务器）
python run_tests.py --verify
# 应该显示: ✅ 真实服务器连接成功

# 或运行完整验证
./verify_setup.sh
# 应该显示: ✅ 所有检查通过
```

### 第3步：运行测试（2分钟）
```bash
# 运行并发测试（真实服务器）
python run_tests.py --concurrent
# 应该显示: 所有并发测试通过！

# 或使用测试运行器
python test_runner.py --mode concurrent --env test
# 应该显示: ✓ 所有测试通过!

# 运行现有测试
python run_tests.py --test-file store/store_test.py
# 应该显示: 测试通过
```

### 第4步：查看结果（30秒）
```bash
# 查看生成的测试报告
ls -la test_report_*.json

# 查看最新报告内容
cat test_report_*.json | python -m json.tool | head -20
```

## 🎯 常用命令速查表

### 基础命令
```bash
# 1. 设置环境
python setup_env.py

# 2. 验证真实服务器连接
python run_tests.py --verify

# 3. 运行所有测试
python run_tests.py --all

# 4. 运行并发测试
python run_tests.py --concurrent

# 5. 运行现有测试
python run_tests.py --test-file store/store_test.py

# 6. 运行特定测试
python run_tests.py --test-file store/store_test.py --test-class StoreTestCase --test-method test_create_store
```

### 调试命令
```bash
# 启用调试模式
export TEST_DEBUG=true
python test_runner.py --mode all --env test

# 查看详细日志
python test_runner.py --mode concurrent --env test 2>&1 | grep -E "(ERROR|WARNING|INFO)"

# 运行单个测试
python -m pytest concurrent_test.py::ConcurrentStoreTest::test_concurrent_store_creation -v -s
```

### 维护命令
```bash
# 迁移现有测试
python test_adapter.py --migrate

# 清理测试报告
rm -f test_report_*.json

# 查看帮助
python test_runner.py --help
python test_adapter.py --help
```

## 🔧 故障快速修复

### 问题1：真实服务器连接失败
```
ConnectionError: 无法连接到服务器 https://autotest.local.vpc
```
**解决方案**：
```bash
# 检查服务器可访问性
curl -k https://autotest.local.vpc

# 验证环境设置
python setup_env.py --verify

# 检查Python路径
python -c "
import sys
print('Python路径:')
for p in sys.path:
    if 'magicTest' in p:
        print('  ✓', p)
"
```

### 问题2：SSL证书警告
```
SSL: CERTIFICATE_VERIFY_FAILED
```
**解决方案**：
```bash
# 测试环境使用自签名证书，警告正常
# 如需禁用SSL验证（仅测试环境）
export TEST_DISABLE_SSL_VERIFY=true
python run_tests.py --verify
```

### 问题3：性能测试超时
```
TimeoutError: 测试执行超时
```
**解决方案**：
```bash
# 减少并发数
export TEST_MAX_WORKERS=5
python test_runner.py --mode concurrent --env test

# 或增加超时时间
export TEST_TIMEOUT=60
python test_runner.py --mode concurrent --env stress
```

### 问题4：测试报告未生成
```
FileNotFoundError: test_report_*.json
```
**解决方案**：
```bash
# 检查文件权限
chmod 755 test_runner.py

# 重新运行测试
python test_runner.py --mode basic --env test
```

## 📊 性能基准

### 正常性能指标（真实服务器）
- **服务器响应时间**：平均<2秒，最大<5秒
- **并发测试**：5个测试应在5秒内完成
- **成功率**：应达到95%以上
- **网络延迟**：<100ms
- **服务器负载**：CPU<80%，内存<90%

### 性能优化
```bash
# 调整并发参数
export TEST_MAX_WORKERS=20
export TEST_TIMEOUT=30
export TEST_RETRY_COUNT=2

# 运行优化测试
python test_runner.py --mode concurrent --env stress
```

## 🧪 测试示例

### 示例1：快速验证（真实服务器）
```bash
# 验证真实服务器连接
python -c "
import sys
sys.path.insert(0, '/home/rangh/codespace/magicTest')
sys.path.insert(0, '/home/rangh/codespace/magicTest/cas')
sys.path.insert(0, '.')
try:
    from test_base import TestBase
    test = TestBase()
    test.setUp()
    print('✅ 真实服务器连接成功')
    test.tearDown()
except Exception as e:
    print('❌ 连接失败:', e)
"
```

### 示例2：创建新测试
```python
# 创建文件: my_test.py
from test_base import TestBase

class MySimpleTest(TestBase):
    def test_simple(self):
        self.assertTrue(True)
        print("✅ 简单测试通过")

if __name__ == '__main__':
    import unittest
    unittest.main()
```

### 示例3：运行自定义测试
```bash
# 运行自定义测试
python my_test.py

# 使用pytest运行
python -m pytest my_test.py -v
```

## 📞 紧急支持

### 快速诊断（真实服务器）
```bash
# 运行诊断脚本
python -c "
import sys
print('Python版本:', sys.version.split()[0])
print('工作目录:', sys.path[0])
print('\\n检查真实模块路径:')
for p in sys.path:
    if 'magicTest' in p:
        print('  ✓', p)

print('\\n验证服务器连接:')
try:
    import requests
    response = requests.get('https://autotest.local.vpc', verify=False, timeout=5)
    print(f'  ✓ 服务器可访问 (状态码: {response.status_code})')
except Exception as e:
    print(f'  ❌ 服务器不可访问: {e}')
"
```

### 重置环境
```bash
# 清理环境
rm -f test_report_*.json
rm -f *.pyc
rm -rf __pycache__

# 重新验证
python test_framework_validation.py
```

### 获取帮助
```bash
# 查看详细文档
cat TEST_FRAMEWORK_README.md | head -50

# 查看配置说明
grep -n "class TestConfig" test_config.py
```

---

## 🎉 恭喜！

您已成功设置VMI测试框架。现在可以：

1. ✅ **运行完整测试套件**
2. ✅ **监控性能指标**
3. ✅ **生成测试报告**
4. ✅ **调试问题**

如需更多帮助，请参考完整文档：[README.md](README.md)

**最后验证时间**: 2026-01-28  
**框架版本**: 2.0.0  
**状态**: ✅ 生产就绪（真实服务器交互）