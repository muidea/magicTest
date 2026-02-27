#!/usr/bin/env python3
"""
配置助手模块 - 从统一配置文件读取服务器地址和认证信息
所有配置统一从 test_config.json 读取
"""

import os
import json

_config_cache = None

def get_config():
    """获取统一配置文件"""
    global _config_cache
    
    if _config_cache is not None:
        return _config_cache
    
    config_file = 'test_config.json'
    
    default_config = {
        'server': {
            'url': 'https://autotest.local.vpc',
            'namespace': 'autotest',
            'environment': 'local'
        },
        'credentials': {
            'username': 'administrator',
            'password': 'administrator'
        },
        'session': {
            'refresh_interval': 540,
            'timeout': 1800
        },
        'concurrent': {
            'max_workers': 10,
            'timeout': 30,
            'retry_count': 3
        },
        'aging': {
            'duration_hours': 24,
            'concurrent_threads': 10,
            'operation_interval': 1.0,
            'max_data_count': 1000,
            'performance_degradation_threshold': 20.0,
            'report_interval_minutes': 30
        }
    }
    
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                file_config = json.load(f)
                _config_cache = file_config
                return _config_cache
        except Exception as e:
            print(f"警告: 读取配置文件失败，使用默认配置: {e}")
    
    _config_cache = default_config
    return _config_cache

def get_server_url():
    """获取服务器地址"""
    config = get_config()
    return config.get('server', {}).get('url', 'https://autotest.local.vpc')

def get_credentials():
    """获取认证信息"""
    config = get_config()
    creds = config.get('credentials', {})
    server = config.get('server', {})
    return {
        'username': creds.get('username', 'administrator'),
        'password': creds.get('password', 'administrator'),
        'namespace': server.get('namespace', 'autotest')
    }

def get_username():
    """获取用户名"""
    return get_credentials()['username']

def get_password():
    """获取密码"""
    return get_credentials()['password']

def get_namespace():
    """获取命名空间"""
    config = get_config()
    return config.get('server', {}).get('namespace', 'autotest')

def get_aging_params():
    """获取老化测试参数"""
    config = get_config()
    return config.get('aging', {})

def get_session_config():
    """获取会话配置"""
    config = get_config()
    return config.get('session', {})

def get_concurrent_config():
    """获取并发配置"""
    config = get_config()
    return config.get('concurrent', {})

def get_test_mode():
    """获取测试模式"""
    config = get_config()
    return config.get('server', {}).get('environment', 'local')

def get_environment():
    """获取环境"""
    config = get_config()
    return config.get('server', {}).get('environment', 'local')

def get_max_workers():
    """获取最大工作线程数"""
    return get_concurrent_config().get('max_workers', 10)

def get_timeout():
    """获取超时时间"""
    return get_concurrent_config().get('timeout', 30)

def get_retry_count():
    """获取重试次数"""
    return get_concurrent_config().get('retry_count', 3)

def update_config(server_url=None, username=None, password=None, namespace=None):
    """更新配置文件"""
    global _config_cache
    
    config_file = 'test_config.json'
    
    config = get_config()
    
    if 'server' not in config:
        config['server'] = {}
    if 'credentials' not in config:
        config['credentials'] = {}
    
    if server_url:
        config['server']['url'] = server_url
    if username:
        config['credentials']['username'] = username
    if password:
        config['credentials']['password'] = password
    if namespace:
        config['server']['namespace'] = namespace
    
    try:
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        _config_cache = None
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