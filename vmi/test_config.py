#!/usr/bin/env python3
"""
测试配置模块
"""

class TestConfig:
    def __init__(self):
        self.config = {
            'test_mode': 'functional',
            'base_url': 'https://autotest.local.vpc',
            'max_workers': 10,
            'username': 'administrator',
            'password': 'administrator'
        }
    
    def get(self, key, default=None):
        return self.config.get(key, default)
    
    def set_mode(self, mode):
        self.config['test_mode'] = mode
    
    def load_config(self, config_path):
        # 简单实现，实际可以从文件加载
        pass