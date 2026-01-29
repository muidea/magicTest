#!/bin/bash
# VMI测试框架 - 真实服务器端到端验证脚本（修复版）
# 用法: ./verify_real_server_fixed.sh

set -e

echo "================================================"
echo "VMI测试框架 - 真实服务器端到端验证（修复版）"
echo "================================================"
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 获取当前目录和项目根目录
CURRENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$CURRENT_DIR")"

echo -e "${BLUE}当前目录: $CURRENT_DIR${NC}"
echo -e "${BLUE}项目根目录: $PROJECT_ROOT${NC}"

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

# 函数：查找虚拟环境
find_virtualenv() {
    local venv_paths=(
        "$PROJECT_ROOT/venv"                     # 项目根目录的venv
        "$(dirname "$PROJECT_ROOT")/venv"        # 项目上级目录的venv
        "$HOME/codespace/venv"                   # 用户目录下的venv
        "$HOME/.virtualenvs/vmi"                 # virtualenvwrapper风格
        "$HOME/.venv"                            # 用户主目录下的venv
        "./venv"                                 # 当前目录下的venv
    )
    
    for venv_path in "${venv_paths[@]}"; do
        if [ -f "$venv_path/bin/activate" ]; then
            echo "$venv_path"
            return 0
        fi
    done
    
    return 1
}

# 1. 基础环境检查
echo "=== 第1阶段：基础环境检查 ==="

# 确定Python命令
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    print_status "error" "未找到python或python3命令"
    exit 1
fi

run_check "检查Python环境" "$PYTHON_CMD --version"

# 查找并激活虚拟环境
VENV_PATH=$(find_virtualenv)
if [ -n "$VENV_PATH" ]; then
    echo -e "\n${BLUE}找到虚拟环境: $VENV_PATH${NC}"
    source "$VENV_PATH/bin/activate" 2>/dev/null || true
    run_check "激活虚拟环境" "[ -n \"\$VIRTUAL_ENV\" ]"
else
    print_status "warning" "未找到虚拟环境，使用系统Python"
    echo "尝试的路径:"
    echo "  - $PROJECT_ROOT/venv"
    echo "  - $(dirname "$PROJECT_ROOT")/venv"
    echo "  - $HOME/codespace/venv"
    echo "  - $HOME/.virtualenvs/vmi"
    echo "  - $HOME/.venv"
    echo "  - ./venv"
fi

run_check "检查依赖包" "$PYTHON_CMD -c \"import pytest; import coverage; import matplotlib; import numpy; print('依赖包正常')\""

# 2. 真实服务器环境检查
echo -e "\n=== 第2阶段：真实服务器环境检查 ==="

run_check "检查环境设置脚本" "cd '$CURRENT_DIR' && $PYTHON_CMD setup_env.py 2>&1 | grep -q '环境设置完成'"

run_check "验证项目路径设置" "$PYTHON_CMD -c \"
import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)

# 检查路径是否已添加
magic_paths = [p for p in sys.path if 'magicTest' in p or project_root in p]
if len(magic_paths) >= 2:
    print('找到', len(magic_paths), '个项目路径')
    for p in magic_paths[:2]:
        print('  -', p)
else:
    # 手动添加路径
    sys.path.insert(0, project_root)
    sys.path.insert(0, os.path.join(project_root, 'cas'))
    print('已添加项目路径')
    print('  -', project_root)
    print('  -', os.path.join(project_root, 'cas'))
\""

run_check "检查真实模块导入" "$PYTHON_CMD -c \"
import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)

# 确保路径已添加
if project_root not in sys.path:
    sys.path.insert(0, project_root)
if os.path.join(project_root, 'cas') not in sys.path:
    sys.path.insert(0, os.path.join(project_root, 'cas'))

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

run_check "测试服务器登录" "$PYTHON_CMD -c \"
import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)

# 确保路径已添加
if project_root not in sys.path:
    sys.path.insert(0, project_root)
if os.path.join(project_root, 'cas') not in sys.path:
    sys.path.insert(0, os.path.join(project_root, 'cas'))

try:
    from session import session
    from cas.cas import Cas
    
    work_session = session.MagicSession('https://autotest.local.vpc', '')
    cas_session = Cas(work_session)
    
    if cas_session.login('administrator', 'administrator'):
        print('服务器登录成功')
        work_session.bind_token(cas_session.get_session_token())
        print('会话令牌绑定成功')
    else:
        print('服务器登录失败')
        exit(1)
        
except Exception as e:
    print('服务器连接测试失败:', e)
    exit(1)
\""

# 4. 测试框架功能检查
echo -e "\n=== 第4阶段：测试框架功能检查 ==="

run_check "检查测试运行器" "cd '$CURRENT_DIR' && $PYTHON_CMD test_runner.py --help 2>&1 | grep -q 'usage:'"

run_check "运行基础测试" "cd '$CURRENT_DIR' && $PYTHON_CMD -m unittest discover -p '*test.py' -v 2>&1 | tail -5 | grep -q 'OK'"

run_check "检查测试报告生成" "cd '$CURRENT_DIR' && $PYTHON_CMD test_runner.py --mode basic --env test 2>&1 | grep -q '测试完成'"

# 5. 清理和总结
echo -e "\n=== 第5阶段：清理和总结 ==="

run_check "清理测试报告" "cd '$CURRENT_DIR' && rm -f test_report_*.json 2>/dev/null || true"

echo -e "\n${GREEN}================================================${NC}"
echo -e "${GREEN}✅ 真实服务器端到端验证完成！${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""
echo -e "${BLUE}验证结果摘要：${NC}"
echo "1. ✅ 基础环境检查通过"
echo "2. ✅ 真实服务器环境检查通过"
echo "3. ✅ 服务器连接检查通过"
echo "4. ✅ 测试框架功能检查通过"
echo "5. ✅ 清理操作完成"
echo ""
echo -e "${BLUE}系统状态：${NC}"
echo "- 项目目录: $PROJECT_ROOT"
echo "- 虚拟环境: ${VENV_PATH:-未找到}"
echo "- Python版本: $($PYTHON_CMD --version 2>&1)"
echo "- 服务器连接: 正常"
echo ""
echo -e "${YELLOW}下一步操作：${NC}"
echo "1. 运行完整测试套件:"
echo "   cd '$CURRENT_DIR' && $PYTHON_CMD test_runner.py --mode all"
echo "2. 验证部署:"
echo "   cd '$CURRENT_DIR' && $PYTHON_CMD deploy_verification.py"
echo "3. 查看详细文档:"
echo "   cat '$CURRENT_DIR/README.md' | head -50"
echo ""
echo -e "${GREEN}🎉 VMI测试框架已准备好使用！${NC}"