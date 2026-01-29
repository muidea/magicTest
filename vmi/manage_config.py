#!/usr/bin/env python3
"""
配置管理工具
用于备份、恢复和管理测试配置
"""

import sys
import os
import argparse

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from test_config import config

def backup_config():
    """备份当前配置"""
    print("=" * 60)
    print("备份当前配置")
    print("=" * 60)
    
    backup_file = config.backup_config()
    if backup_file:
        print(f"✅ 配置已备份到: {backup_file}")
        
        # 显示备份信息
        backups = config.list_backups()
        if backups:
            print(f"\n当前备份数量: {len(backups)}")
            print("最新备份:")
            for i, backup in enumerate(backups[:3], 1):
                print(f"  {i}. {backup['name']} ({backup['timestamp']})")
        
        return True
    else:
        print("❌ 备份配置失败")
        return False

def restore_config(backup_name=None):
    """恢复配置"""
    print("=" * 60)
    print("恢复配置")
    print("=" * 60)
    
    backups = config.list_backups()
    if not backups:
        print("❌ 没有找到备份文件")
        return False
    
    if backup_name:
        # 查找指定备份
        backup_file = None
        for backup in backups:
            if backup['name'] == backup_name or backup['file'] == backup_name:
                backup_file = backup['file']
                break
        
        if not backup_file:
            print(f"❌ 未找到备份: {backup_name}")
            return False
    else:
        # 使用最新备份
        backup_file = backups[0]['file']
        backup_name = backups[0]['name']
    
    print(f"将恢复备份: {backup_name}")
    print("当前配置:")
    print("-" * 40)
    print(f"服务器: {config.get('server_url')}")
    print(f"用户名: {config.get('username')}")
    print(f"测试模式: {config.get('test_mode')}")
    print(f"环境: {config.get('environment')}")
    
    # 确认恢复
    confirm = input("\n确认恢复配置? (y/N): ")
    if confirm.lower() != 'y':
        print("取消恢复")
        return False
    
    if config.restore_config(backup_file):
        print("✅ 配置恢复成功")
        
        # 显示恢复后的配置
        print("\n恢复后的配置:")
        print("-" * 40)
        print(f"服务器: {config.get('server_url')}")
        print(f"用户名: {config.get('username')}")
        print(f"测试模式: {config.get('test_mode')}")
        print(f"环境: {config.get('environment')}")
        
        return True
    else:
        print("❌ 配置恢复失败")
        return False

def list_backups():
    """列出所有备份"""
    print("=" * 60)
    print("配置备份列表")
    print("=" * 60)
    
    backups = config.list_backups()
    if not backups:
        print("没有找到备份文件")
        return False
    
    print(f"备份数量: {len(backups)}")
    print("-" * 60)
    
    for i, backup in enumerate(backups, 1):
        print(f"{i}. {backup['name']}")
        print(f"   时间: {backup['timestamp']}")
        print(f"   路径: {backup['file']}")
        print()
    
    return True

def save_current_config():
    """保存当前配置到文件"""
    print("=" * 60)
    print("保存当前配置到文件")
    print("=" * 60)
    
    config_file = os.path.join(current_dir, 'test_config.json')
    
    print("当前配置:")
    print("-" * 40)
    print(f"服务器: {config.get('server_url')}")
    print(f"用户名: {config.get('username')}")
    print(f"测试模式: {config.get('test_mode')}")
    print(f"环境: {config.get('environment')}")
    print(f"最大工作线程: {config.get('max_workers')}")
    print(f"老化测试时长: {config.get('aging_duration_hours')}小时")
    
    # 确认保存
    confirm = input(f"\n保存配置到 {config_file}? (y/N): ")
    if confirm.lower() != 'y':
        print("取消保存")
        return False
    
    if config.save_to_file(config_file):
        print(f"✅ 配置已保存到: {config_file}")
        return True
    else:
        print("❌ 保存配置失败")
        return False

def show_current_config():
    """显示当前配置"""
    print("=" * 60)
    print("当前配置信息")
    print("=" * 60)
    
    # 显示版本信息
    version_info = config.get_version_info()
    print(f"系统版本: {version_info['current_version']}")
    print(f"配置版本: {version_info['config_version']}")
    print(f"版本兼容性: {'✓ 兼容' if version_info['is_compatible'] else '✗ 不兼容'}")
    
    # 显示主要配置
    print("\n主要配置:")
    print("-" * 40)
    print(f"服务器URL: {config.get('server_url')}")
    print(f"用户名: {config.get('username')}")
    print(f"命名空间: {config.get('namespace')}")
    print(f"测试模式: {config.get('test_mode')}")
    print(f"环境: {config.get('environment')}")
    print(f"最大工作线程: {config.get('max_workers')}")
    print(f"并发超时: {config.get('concurrent_timeout')}秒")
    print(f"重试次数: {config.get('retry_count')}")
    print(f"老化测试时长: {config.get('aging_duration_hours')}小时")
    print(f"老化并发线程: {config.get('aging_concurrent_threads')}")
    
    # 验证配置
    print("\n配置验证:")
    print("-" * 40)
    validation = config.validate()
    
    if validation['errors']:
        print("❌ 配置错误:")
        for error in validation['errors']:
            print(f"  ✗ {error}")
    else:
        print("✅ 配置验证通过")
    
    if validation['warnings']:
        print("⚠ 配置警告:")
        for warning in validation['warnings']:
            print(f"  ⚠ {warning}")
    
    return True

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='配置管理工具')
    parser.add_argument('--backup', '-b', action='store_true', help='备份当前配置')
    parser.add_argument('--restore', '-r', nargs='?', const=True, help='恢复配置（可指定备份名称）')
    parser.add_argument('--list', '-l', action='store_true', help='列出所有备份')
    parser.add_argument('--save', '-s', action='store_true', help='保存当前配置到文件')
    parser.add_argument('--show', action='store_true', help='显示当前配置')
    
    args = parser.parse_args()
    
    if args.backup:
        backup_config()
    elif args.restore:
        if args.restore is True:
            restore_config()
        else:
            restore_config(args.restore)
    elif args.list:
        list_backups()
    elif args.save:
        save_current_config()
    elif args.show:
        show_current_config()
    else:
        # 默认显示帮助
        print("配置管理工具 - 使用以下选项:")
        print("  --backup, -b     备份当前配置")
        print("  --restore, -r    恢复配置（可指定备份名称）")
        print("  --list, -l       列出所有备份")
        print("  --save, -s       保存当前配置到文件")
        print("  --show           显示当前配置")
        print("\n示例:")
        print("  python manage_config.py --backup")
        print("  python manage_config.py --restore")
        print("  python manage_config.py --list")
        print("  python manage_config.py --show")

if __name__ == "__main__":
    main()