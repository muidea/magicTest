#!/usr/bin/env python3
"""
配置助手模块 - 提供便捷的配置访问接口
"""

from test_config import config

class ConfigHelper:
    """配置助手类"""
    
    @staticmethod
    def get_server_url():
        """获取服务器URL"""
        return config.get('server_url', 'https://autotest.local.vpc')
    
    @staticmethod
    def get_credentials():
        """获取登录凭证"""
        return {
            'username': config.get('username', 'administrator'),
            'password': config.get('password', 'administrator')
        }
    
    @staticmethod
    def get_namespace():
        """获取命名空间"""
        return config.get('namespace', 'autotest')
    
    @staticmethod
    def get_test_mode():
        """获取测试模式"""
        return config.get('test_mode', 'functional')
    
    @staticmethod
    def get_environment():
        """获取环境"""
        return config.get('environment', 'test')
    
    @staticmethod
    def get_concurrent_params():
        """获取并发参数"""
        return config.get_concurrent_config()
    
    @staticmethod
    def get_aging_params():
        """获取老化测试参数"""
        return config.get_aging_config()
    
    @staticmethod
    def get_performance_thresholds():
        """获取性能阈值"""
        return config.get_performance_thresholds()
    
    @staticmethod
    def get_log_config():
        """获取日志配置"""
        return {
            'level': config.get('log_level', 'INFO'),
            'format': config.get('log_format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        }
    
    @staticmethod
    def get_project_root():
        """获取项目根目录"""
        return config.get('project_root')
    
    @staticmethod
    def get_reports_dir():
        """获取报告目录"""
        return config.get('reports_dir', 'test_reports')
    
    @staticmethod
    def setup_session():
        """设置会话配置"""
        import sys
        import os
        
        # 添加项目根目录到路径
        project_root = ConfigHelper.get_project_root()
        if project_root and project_root not in sys.path:
            sys.path.insert(0, project_root)
        
        # 返回服务器配置
        return ConfigHelper.get_server_url()


# 便捷函数
def get_server_url():
    """获取服务器URL"""
    return ConfigHelper.get_server_url()

def get_credentials():
    """获取登录凭证"""
    return ConfigHelper.get_credentials()

def get_namespace():
    """获取命名空间"""
    return ConfigHelper.get_namespace()

def get_test_mode():
    """获取测试模式"""
    return ConfigHelper.get_test_mode()

def get_environment():
    """获取环境"""
    return ConfigHelper.get_environment()

def get_concurrent_params():
    """获取并发参数"""
    return ConfigHelper.get_concurrent_params()

def get_aging_params():
    """获取老化测试参数"""
    return ConfigHelper.get_aging_params()

def get_performance_thresholds():
    """获取性能阈值"""
    return ConfigHelper.get_performance_thresholds()

def setup_session():
    """设置会话配置"""
    return ConfigHelper.setup_session()