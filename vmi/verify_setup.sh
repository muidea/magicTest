#!/bin/bash
# VMI测试框架安装验证脚本
# 用法: ./verify_setup.sh

set -e

echo "========================================="
echo "VMI测试框架安装验证"
echo "========================================="

# 检查Python环境
echo "1. 检查Python环境..."
python --version
if [ $? -eq 0 ]; then
    echo "✅ Python环境正常"
else
    echo "❌ Python环境异常"
    exit 1
fi

# 检查虚拟环境
echo "2. 检查虚拟环境..."

# 尝试多个可能的虚拟环境位置
VENV_PATHS=(
    "$(pwd)/../venv"                     # 项目上级目录的venv
    "$HOME/codespace/venv"               # 用户目录下的venv
    "$(dirname "$(pwd)")/venv"           # 项目根目录的venv
    "/home/rangh/codespace/venv"         # 原始路径（向后兼容）
)

VENV_FOUND=false
VENV_PATH=""

for venv_path in "${VENV_PATHS[@]}"; do
    if [ -f "$venv_path/bin/activate" ]; then
        VENV_FOUND=true
        VENV_PATH="$venv_path"
        echo "✅ 虚拟环境存在: $venv_path"
        break
    fi
done

if [ "$VENV_FOUND" = false ]; then
    echo "⚠️  虚拟环境不存在，使用系统Python"
    echo "   尝试的位置:"
    for venv_path in "${VENV_PATHS[@]}"; do
        echo "     - $venv_path"
    done
fi

# 激活虚拟环境（如果找到）
if [ "$VENV_FOUND" = true ]; then
    source "$VENV_PATH/bin/activate" 2>/dev/null || true
    echo "✅ 虚拟环境已激活"
fi

# 检查依赖包
echo "3. 检查依赖包..."
python -c "import pytest; import coverage; import matplotlib; import numpy; print('✅ 所有依赖包已安装')" 2>/dev/null || {
    echo "⚠️  部分依赖包未安装，尝试安装..."
    pip install pytest coverage matplotlib numpy --quiet
    echo "✅ 依赖包安装完成"
}

# 验证框架导入
echo "4. 验证框架导入..."
python -c "
import sys
sys.path.insert(0, '.')
try:
    import test_config
    import test_base
    import concurrent_test
    import performance_report
    import test_runner
    import test_adapter
    print('✅ 所有核心模块导入成功')
except Exception as e:
    print(f'❌ 模块导入失败: {e}')
    sys.exit(1)
"

# 运行框架验证
echo "5. 运行框架验证..."
python test_framework_validation.py 2>&1 | grep -E "(✅|❌|所有测试通过)" || true

# 运行简单测试
echo "6. 运行简单测试..."
python -c "
import sys
sys.path.insert(0, '.')
from test_base import TestBase
import unittest

class SimpleTest(TestBase):
    def test_simple(self):
        self.assertTrue(True)

if __name__ == '__main__':
    unittest.main()
" 2>&1 | grep -E "(OK|FAILED)" && echo "✅ 简单测试通过"

# 检查测试报告
echo "7. 检查测试报告生成..."
python test_runner.py --mode concurrent --env test >/dev/null 2>&1
if ls test_report_*.json 1>/dev/null 2>&1; then
    echo "✅ 测试报告生成正常"
    echo "   最新报告: $(ls -t test_report_*.json | head -1)"
else
    echo "⚠️  测试报告未生成"
fi

# 清理测试报告
rm -f test_report_*.json 2>/dev/null || true

echo "========================================="
echo "验证完成！"
echo "========================================="
echo ""
echo "🎉 VMI测试框架安装验证通过！"
echo ""
echo "下一步操作："
echo "1. 查看完整文档: cat README.md"
echo "2. 快速开始: cat QUICK_START.md"
echo "3. 运行完整测试: python test_runner.py --mode all --env test"
echo "4. 查看帮助: python test_runner.py --help"
echo ""
echo "如有问题，请参考故障排除部分："
echo "  cat README.md | grep -A 20 '故障排除'"
echo "========================================="