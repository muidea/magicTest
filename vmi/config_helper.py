#!/usr/bin/env python3
"""
配置助手模块 - 从配置文件读取服务器地址和认证信息
"""

import os
import json

def get_config():
    """获取配置文件"""
    config_file = 'test_config.json'
    
    # 默认配置
    default_config = {
        'server_url': 'https://autotest.local.vpc',
        'username': 'administrator',
        'password': 'administrator',
        'namespace': 'autotest'
    }
    
    # 如果配置文件存在，读取它
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                file_config = json.load(f)
                # 用文件配置更新默认配置
                default_config.update(file_config)
        except Exception as e:
            print(f"警告: 读取配置文件失败，使用默认配置: {e}")
    
    return default_config

def get_server_url():
    """获取服务器地址"""
    config = get_config()
    return config.get('server_url', 'https://autotest.local.vpc')

def get_credentials():
    """获取认证信息"""
    config = get_config()
    return {
        'username': config.get('username', 'administrator'),
        'password': config.get('password', 'administrator'),
        'namespace': config.get('namespace', 'autotest')
    }

def get_username():
    """获取用户名"""
    config = get_config()
    return config.get('username', 'administrator')

def get_password():
    """获取密码"""
    config = get_config()
    return config.get('password', 'administrator')

def get_namespace():
    """获取命名空间"""
    config = get_config()
    return config.get('namespace', 'autotest')

def get_aging_params():
    """获取老化测试参数"""
    config = get_config()
    
    # 默认老化测试配置
    default_aging_config = {
        'duration_hours': 24,
        'concurrent_threads': 10,
        'operation_interval': 1.0,
        'max_data_count': 1000,  # 万条
        'performance_degradation_threshold': 20.0,  # 百分比
        'report_interval_minutes': 30
    }
    
    # 从配置中获取老化测试参数
    aging_config = {}
    for key in default_aging_config.keys():
        config_key = f'aging_{key}'
        if config_key in config:
            aging_config[key] = config[config_key]
        else:
            aging_config[key] = default_aging_config[key]
    
    return aging_config

def get_test_mode():
    """获取测试模式"""
    config = get_config()
    return config.get('test_mode', 'functional')

def get_environment():
    """获取环境"""
    config = get_config()
    return config.get('environment', 'test')

def get_max_workers():
    """获取最大工作线程数"""
    config = get_config()
    return config.get('max_workers', 10)

def get_timeout():
    """获取超时时间"""
    config = get_config()
    return config.get('concurrent_timeout', 30)

def get_retry_count():
    """获取重试次数"""
    config = get_config()
    return config.get('retry_count', 3)

def update_config(server_url=None, username=None, password=None, namespace=None):
    """更新配置文件"""
    config_file = 'test_config.json'
    
    # 读取现有配置
    config = get_config()
    
    # 更新配置
    if server_url:
        config['server_url'] = server_url
    if username:
        config['username'] = username
    if password:
        config['password'] = password
    if namespace:
        config['namespace'] = namespace
    
    # 保存配置
    try:
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"错误: 保存配置文件失败: {e}")
        return False

# 测试代码
if __name__ == '__main__':
    print("当前配置:")
    print(f"  服务器地址: {get_server_url()}")
    print(f"  用户名: {get_username()}")
    print(f"  密码: {get_password()}")
    print(f"  命名空间: {get_namespace()}")