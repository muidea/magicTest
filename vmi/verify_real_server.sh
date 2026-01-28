#!/bin/bash
# VMI测试框架 - 真实服务器端到端验证脚本
# 用法: ./verify_real_server.sh

set -e

echo "================================================"
echo "VMI测试框架 - 真实服务器端到端验证"
echo "================================================"
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 函数：打印带颜色的状态
print_status() {
    local status=$1
    local message=$2
    
    case $status in
        "success")
            echo -e "${GREEN}✅ ${message}${NC}"
            ;;
        "warning")
            echo -e "${YELLOW}⚠️  ${message}${NC}"
            ;;
        "error")
            echo -e "${RED}❌ ${message}${NC}"
            ;;
        "info")
            echo -e "${BLUE}ℹ️  ${message}${NC}"
            ;;
    esac
}

# 函数：运行命令并检查状态
run_check() {
    local step_name=$1
    local command=$2
    
    echo -e "\n${BLUE}${step_name}...${NC}"
    if eval "$command"; then
        print_status "success" "$step_name 通过"
        return 0
    else
        print_status "error" "$step_name 失败"
        return 1
    fi
}

# 1. 基础环境检查
echo "=== 第1阶段：基础环境检查 ==="

run_check "检查Python环境" "python --version"
run_check "检查虚拟环境" "[ -f '/home/rangh/codespace/venv/bin/activate' ]"

# 激活虚拟环境
source /home/rangh/codespace/venv/bin/activate 2>/dev/null || true

run_check "检查依赖包" "python -c \"import pytest; import coverage; import matplotlib; import numpy; print('依赖包正常')\""

# 2. 真实服务器环境检查
echo -e "\n=== 第2阶段：真实服务器环境检查 ==="

run_check "检查环境设置脚本" "python setup_env.py --verify 2>&1 | grep -q '环境设置成功'"

run_check "验证真实模块路径" "python -c \"
import sys
magic_paths = [p for p in sys.path if 'magicTest' in p]
if len(magic_paths) >= 2:
    print('找到', len(magic_paths), '个magicTest路径')
    for p in magic_paths[:2]:
        print('  -', p)
else:
    print('magicTest路径不足')
    exit(1)
\""

run_check "检查真实模块导入" "python -c \"
import sys
sys.path.insert(0, '/home/rangh/codespace/magicTest')
sys.path.insert(0, '/home/rangh/codespace/magicTest/cas')
try:
    from cas.cas import Cas
    print('CAS模块导入成功')
except Exception as e:
    print('CAS模块导入失败:', e)
    exit(1)
\""

# 3. 服务器连接检查
echo -e "\n=== 第3阶段：服务器连接检查 ==="

run_check "检查服务器可访问性" "curl -k -s -o /dev/null -w '%{http_code}' https://autotest.local.vpc | grep -q '200\|301\|302'"

run_check "测试服务器登录" "python -c \"
import sys
sys.path.insert(0, '/home/rangh/codespace/magicTest')
sys.path.insert(0, '/home/rangh/codespace/magicTest/cas')
sys.path.insert(0, '.')
try:
    from test_base import TestBase
    test = TestBase()
    test.setUp()
    if hasattr(test, 'session') and test.session:
        print('服务器登录成功')
        test.tearDown()
    else:
        print('服务器登录失败')
        exit(1)
except Exception as e:
    print('服务器登录异常:', e)
    exit(1)
\""

# 4. 测试框架功能检查
echo -e "\n=== 第4阶段：测试框架功能检查 ==="

run_check "检查测试基类" "python -c \"
import sys
sys.path.insert(0, '/home/rangh/codespace/magicTest')
sys.path.insert(0, '/home/rangh/codespace/magicTest/cas')
sys.path.insert(0, '.')
try:
    from test_base import TestBase
    print('测试基类导入成功')
except Exception as e:
    print('测试基类导入失败:', e)
    exit(1)
\""

run_check "检查配置管理" "python -c \"
import sys
sys.path.insert(0, '.')
try:
    from test_config import TestConfig
    config = TestConfig()
    print('配置管理正常，当前模式:', config.get_test_mode())
except Exception as e:
    print('配置管理异常:', e)
    exit(1)
\""

# 5. 测试执行检查
echo -e "\n=== 第5阶段：测试执行检查 ==="

# 清理旧的测试报告
rm -f test_report_*.json 2>/dev/null || true

run_check "运行现有测试（真实服务器）" "python run_tests.py --test-file store/store_test.py --test-class StoreTestCase --test-method test_create_store --quiet 2>&1 | grep -q '测试通过\|OK'"

run_check "运行并发测试（真实服务器）" "python run_tests.py --concurrent --quiet 2>&1 | grep -q '所有并发测试通过\|OK'"

run_check "检查测试报告生成" "ls test_report_*.json 1>/dev/null 2>&1 && echo '找到测试报告: ' \$(ls -t test_report_*.json | head -1)"

# 6. 性能检查
echo -e "\n=== 第6阶段：性能检查 ==="

run_check "检查服务器响应时间" "python -c \"
import sys
import time
import requests
sys.path.insert(0, '/home/rangh/codespace/magicTest')
sys.path.insert(0, '/home/rangh/codespace/magicTest/cas')
sys.path.insert(0, '.')

try:
    from test_config import TestConfig
    config = TestConfig()
    server_url = config.get_server_url()
    
    start_time = time.time()
    response = requests.get(server_url, verify=False, timeout=10)
    end_time = time.time()
    
    response_time = end_time - start_time
    print(f'服务器响应时间: {response_time:.2f}秒')
    
    if response_time < 5:
        print('响应时间正常')
    else:
        print('响应时间较慢')
        exit(1)
        
except Exception as e:
    print('性能检查异常:', e)
    exit(1)
\""

# 7. 最终汇总
echo -e "\n=== 验证结果汇总 ==="
echo ""

# 检查所有关键文件
echo "关键文件检查:"
important_files=(
    "README.md"
    "QUICK_START.md"
    "SETUP_SUMMARY.md"
    "test_base.py"
    "test_config.py"
    "concurrent_test.py"
    "test_runner.py"
    "setup_env.py"
    "run_tests.py"
    "verify_setup.sh"
    "verify_real_server.sh"
)

for file in "${important_files[@]}"; do
    if [ -f "$file" ]; then
        print_status "success" "$file 存在"
    else
        print_status "error" "$file 缺失"
    fi
done

echo ""
echo "================================================"
echo "验证完成！"
echo "================================================"
echo ""
echo -e "${GREEN}🎉 VMI测试框架真实服务器端到端验证通过！${NC}"
echo ""
echo "下一步操作："
echo "1. 查看真实服务器文档: cat README.md | grep -A 10 '真实服务器交互系统'"
echo "2. 运行完整测试套件: python run_tests.py --all"
echo "3. 查看服务器性能: python run_tests.py --performance"
echo "4. 查看帮助: python run_tests.py --help"
echo ""
echo "重要提醒："
echo "  • 测试会在真实服务器上创建数据，请确保有数据清理机制"
echo "  • 建议使用测试专用命名空间: export TEST_NAMESPACE=vmi_test"
echo "  • 监控服务器性能，避免过载"
echo ""
echo "如有问题，请参考："
echo "  cat SETUP_SUMMARY.md | grep -A 30 '故障排除'"
echo "================================================"

# 清理测试报告
rm -f test_report_*.json 2>/dev/null || true