#!/bin/bash
# VMI测试框架启动脚本
# 自动检查环境并启动测试框架

set -e

echo "========================================="
echo "VMI测试框架启动"
echo "========================================="

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "当前目录: $(pwd)"

# 检查是否在虚拟环境中
if [ -z "$VIRTUAL_ENV" ]; then
    echo "❌ 错误：未在虚拟环境中运行"
    echo ""
    echo "要求：必须在激活的Python虚拟环境中运行"
    echo ""
    echo "请按照以下步骤操作："
    echo ""
    echo "1. 创建虚拟环境（如果尚未创建）："
    echo "   python -m venv venv"
    echo ""
    echo "2. 激活虚拟环境："
    echo "   source venv/bin/activate  # Linux/Mac"
    echo "   # 或 venv\\Scripts\\activate  # Windows"
    echo ""
    echo "3. 安装依赖："
    echo "   pip install -r requirements.txt"
    echo ""
    echo "4. 重新运行此脚本"
    echo ""
    exit 1
fi

echo "✅ 虚拟环境检测通过: $VIRTUAL_ENV"

# 检查Python版本
PYTHON_VERSION=$(python --version 2>&1)
echo "Python版本: $PYTHON_VERSION"

# 检查依赖
echo ""
echo "检查依赖包..."
python -c "
try:
    import pytest
    import coverage
    import matplotlib
    import numpy
    import requests
    print('✅ 所有核心依赖包已安装')
except ImportError as e:
    print(f'❌ 依赖包缺失: {e}')
    print('请运行: pip install -r requirements.txt')
    exit(1)
"

# 设置环境
echo ""
echo "设置环境路径..."
python setup_env.py
if [ $? -ne 0 ]; then
    echo "❌ 环境设置失败"
    exit 1
fi

echo ""
echo "✅ 环境准备完成"
echo "========================================="
echo ""
echo "可用命令："
echo ""
echo "1. 运行完整测试套件："
echo "   python test_runner.py --mode all"
echo ""
echo "2. 验证服务器连接："
echo "   ./verify_real_server.sh"
echo ""
echo "3. 验证部署："
echo "   python deploy_verification.py"
echo ""
echo "4. 运行基础测试："
echo "   python -m unittest discover -p '*test.py' -v"
echo ""
echo "5. 查看帮助："
echo "   python test_runner.py --help"
echo ""
echo "========================================="
echo "🎉 VMI测试框架已准备就绪！"
echo "========================================="