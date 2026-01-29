#!/usr/bin/env python3
"""
配置模板应用工具
用于快速应用预定义的配置模板
"""

import sys
import os
import json
import argparse

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from test_config import config

def load_template(template_name):
    """加载配置模板"""
    # 首先检查根目录
    template_file = os.path.join(current_dir, 'test_config_examples.json')
    
    # 如果根目录没有，检查docs目录
    if not os.path.exists(template_file):
        docs_template = os.path.join(current_dir, 'docs', 'config_examples.json')
        if os.path.exists(docs_template):
            template_file = docs_template
        else:
            print(f"注意: 模板文件不存在")
            print("可选模板文件位置:")
            print("  1. test_config_examples.json (项目根目录)")
            print("  2. docs/config_examples.json (文档目录)")
            print("\n或者直接使用环境变量设置配置:")
            print("  export TEST_SERVER_URL=https://your-server.com")
            print("  export TEST_USERNAME=your_username")
            return None
    
    try:
        with open(template_file, 'r', encoding='utf-8') as f:
            templates = json.load(f)
        
        if template_name not in templates['config_examples']:
            print(f"错误: 模板 '{template_name}' 不存在")
            print(f"可用模板: {', '.join(templates['config_examples'].keys())}")
            return None
        
        return templates['config_examples'][template_name]
    except Exception as e:
        print(f"加载模板失败: {e}")
        return None

def apply_template(template_name, save_to_file=False):
    """应用配置模板"""
    template = load_template(template_name)
    if not template:
        return False
    
    print("=" * 60)
    print(f"应用配置模板: {template_name}")
    print("=" * 60)
    print(f"描述: {template['description']}")
    print("-" * 60)
    
    # 应用配置
    template_config = template['config']
    for key, value in template_config.items():
        config.set(key, value)
        print(f"设置 {key}: {value}")
    
    # 验证配置
    print("\n验证配置...")
    validation = config.validate()
    
    if validation['errors']:
        print("❌ 配置验证失败:")
        for error in validation['errors']:
            print(f"  ✗ {error}")
        return False
    
    if validation['warnings']:
        print("⚠ 配置警告:")
        for warning in validation['warnings']:
            print(f"  ⚠ {warning}")
    
    print("✅ 配置验证通过")
    
    # 保存到文件
    if save_to_file:
        config_file = os.path.join(current_dir, 'test_config.json')
        if config.save_to_file(config_file):
            print(f"\n✅ 配置已保存到文件: {config_file}")
        else:
            print(f"\n❌ 保存配置文件失败")
            return False
    
    # 显示应用的环境变量命令
    print("\n应用的环境变量命令:")
    print("-" * 40)
    env_vars = [
        f"TEST_SERVER_URL={template_config.get('server_url', '')}",
        f"TEST_USERNAME={template_config.get('username', '')}",
        f"TEST_PASSWORD={template_config.get('password', '')}",
        f"TEST_MODE={template_config.get('test_mode', '')}",
        f"TEST_ENVIRONMENT={template_config.get('environment', '')}",
        f"AGING_DURATION_HOURS={template_config.get('aging_duration_hours', '')}",
        f"AGING_CONCURRENT_THREADS={template_config.get('aging_concurrent_threads', '')}"
    ]
    
    for env_var in env_vars:
        print(f"export {env_var}")
    
    return True

def list_templates():
    """列出所有可用模板"""
    template_file = os.path.join(current_dir, 'test_config_examples.json')
    
    if not os.path.exists(template_file):
        print(f"错误: 模板文件不存在: {template_file}")
        return False
    
    try:
        with open(template_file, 'r', encoding='utf-8') as f:
            templates = json.load(f)
        
        print("=" * 60)
        print("可用配置模板")
        print("=" * 60)
        
        for name, template in templates['config_examples'].items():
            print(f"\n{name}:")
            print(f"  描述: {template['description']}")
            print(f"  测试模式: {template['config'].get('test_mode', 'N/A')}")
            print(f"  环境: {template['config'].get('environment', 'N/A')}")
            print(f"  最大工作线程: {template['config'].get('max_workers', 'N/A')}")
            print(f"  老化测试时长: {template['config'].get('aging_duration_hours', 'N/A')}小时")
        
        print("\n使用示例:")
        print("  python apply_config_template.py --template development")
        print("  python apply_config_template.py --template testing --save")
        
        return True
    except Exception as e:
        print(f"列出模板失败: {e}")
        return False

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='应用配置模板')
    parser.add_argument('--template', '-t', help='要应用的模板名称')
    parser.add_argument('--save', '-s', action='store_true', help='保存配置到文件')
    parser.add_argument('--list', '-l', action='store_true', help='列出所有可用模板')
    
    args = parser.parse_args()
    
    if args.list:
        list_templates()
        return
    
    if not args.template:
        print("错误: 必须指定模板名称")
        print("\n使用 --list 查看可用模板")
        print("使用 --template <name> 应用模板")
        sys.exit(1)
    
    success = apply_template(args.template, args.save)
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main()