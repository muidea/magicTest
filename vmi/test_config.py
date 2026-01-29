#!/usr/bin/env python3
"""
测试配置模块 - 统一配置管理系统
"""

import os
import json

class TestConfig:
    """测试配置管理器"""
    
    # 单例实例
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        # 配置版本信息
        self.version = '2.2.0'
        self.version_history = {
            '2.0.0': '初始版本 - 基础配置',
            '2.1.0': '添加老化测试配置',
            '2.2.0': '统一配置系统，添加验证和版本管理'
        }
        
        # 默认配置
        self.config = {
            # 配置元数据
            'config_version': self.version,
            'config_timestamp': None,
            
            # 服务器配置
            'server_url': 'https://autotest.local.vpc',
            'username': 'administrator',
            'password': 'administrator',
            'namespace': 'autotest',
            
            # 测试模式配置
            'test_mode': 'functional',  # functional, pressure, aging, scenario
            'environment': 'test',      # dev, test, stress, prod
            
            # 并发测试配置
            'max_workers': 10,
            'concurrent_timeout': 30,
            'retry_count': 3,
            
            # 老化测试配置
            'aging_duration_hours': 24,
            'aging_concurrent_threads': 10,
            'aging_operation_interval': 1.0,
            'aging_max_data_count': 1000,  # 万条
            'aging_performance_degradation_threshold': 20.0,  # 百分比
            'aging_report_interval_minutes': 30,
            
            # 性能阈值
            'performance_thresholds': {
                'avg_response_time': 2.0,  # 秒
                'success_rate': 95.0,      # 百分比
                'throughput': 10.0         # 请求/秒
            },
            
            # 日志配置
            'log_level': 'INFO',
            'log_format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            
            # 路径配置
            'project_root': os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'reports_dir': 'test_reports'
        }
        
        # 从环境变量加载配置
        self._load_from_env()
        
        # 从配置文件加载（如果存在）
        config_file = os.path.join(os.path.dirname(__file__), 'test_config.json')
        if os.path.exists(config_file):
            self._load_from_file(config_file)
        
        self._initialized = True
    
    def _load_from_env(self):
        """从环境变量加载配置"""
        env_mappings = {
            'TEST_SERVER_URL': 'server_url',
            'TEST_USERNAME': 'username',
            'TEST_PASSWORD': 'password',
            'TEST_NAMESPACE': 'namespace',
            'TEST_MODE': 'test_mode',
            'TEST_ENVIRONMENT': 'environment',
            'TEST_MAX_WORKERS': 'max_workers',
            'TEST_TIMEOUT': 'concurrent_timeout',
            'TEST_RETRY_COUNT': 'retry_count',
            'AGING_DURATION_HOURS': 'aging_duration_hours',
            'AGING_CONCURRENT_THREADS': 'aging_concurrent_threads',
            'AGING_OPERATION_INTERVAL': 'aging_operation_interval',
            'AGING_MAX_DATA_COUNT': 'aging_max_data_count',
            'AGING_PERFORMANCE_THRESHOLD': 'aging_performance_degradation_threshold',
            'AGING_REPORT_INTERVAL': 'aging_report_interval_minutes',
            'TEST_LOG_LEVEL': 'log_level'
        }
        
        for env_var, config_key in env_mappings.items():
            value = os.environ.get(env_var)
            if value is not None:
                # 尝试转换类型
                try:
                    if value.lower() in ('true', 'false'):
                        self.config[config_key] = value.lower() == 'true'
                    elif '.' in value:
                        self.config[config_key] = float(value)
                    else:
                        self.config[config_key] = int(value)
                except ValueError:
                    self.config[config_key] = value
    
    def _load_from_file(self, config_path):
        """从配置文件加载配置"""
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                file_config = json.load(f)
                self.config.update(file_config)
        except Exception as e:
            print(f"警告: 加载配置文件失败: {e}")
    
    def get(self, key, default=None):
        """获取配置值"""
        return self.config.get(key, default)
    
    def set(self, key, value):
        """设置配置值"""
        self.config[key] = value
    
    def set_mode(self, mode):
        """设置测试模式"""
        self.config['test_mode'] = mode
    
    def set_environment(self, env):
        """设置环境"""
        self.config['environment'] = env
    
    def get_server_config(self):
        """获取服务器配置"""
        return {
            'server_url': self.get('server_url'),
            'username': self.get('username'),
            'password': self.get('password'),
            'namespace': self.get('namespace')
        }
    
    def get_concurrent_config(self):
        """获取并发测试配置"""
        return {
            'max_workers': self.get('max_workers'),
            'timeout': self.get('concurrent_timeout'),
            'retry_count': self.get('retry_count')
        }
    
    def get_aging_config(self):
        """获取老化测试配置"""
        return {
            'duration_hours': self.get('aging_duration_hours'),
            'concurrent_threads': self.get('aging_concurrent_threads'),
            'operation_interval': self.get('aging_operation_interval'),
            'max_data_count': self.get('aging_max_data_count'),
            'performance_degradation_threshold': self.get('aging_performance_degradation_threshold'),
            'report_interval_minutes': self.get('aging_report_interval_minutes')
        }
    
    def get_performance_thresholds(self):
        """获取性能阈值"""
        return self.get('performance_thresholds', {})
    
    def save_to_file(self, config_path=None):
        """保存配置到文件"""
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), 'test_config.json')
        
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"保存配置文件失败: {e}")
            return False
    
    def validate(self):
        """验证配置的有效性"""
        errors = []
        warnings = []
        
        # 服务器配置验证
        if not self.config.get('server_url'):
            errors.append("server_url 不能为空")
        if not self.config.get('username'):
            errors.append("username 不能为空")
        if not self.config.get('password'):
            errors.append("password 不能为空")
        
        # 数值范围验证
        if self.config.get('max_workers', 0) <= 0:
            errors.append("max_workers 必须大于0")
        elif self.config.get('max_workers', 0) > 100:
            warnings.append("max_workers 值过大，可能影响系统性能")
        
        if self.config.get('aging_duration_hours', 0) <= 0:
            errors.append("aging_duration_hours 必须大于0")
        elif self.config.get('aging_duration_hours', 0) > 720:  # 30天
            warnings.append("aging_duration_hours 值过大，建议不超过720小时(30天)")
        
        if self.config.get('aging_concurrent_threads', 0) <= 0:
            errors.append("aging_concurrent_threads 必须大于0")
        elif self.config.get('aging_concurrent_threads', 0) > 50:
            warnings.append("aging_concurrent_threads 值过大，可能影响系统性能")
        
        # 测试模式验证
        valid_modes = ['functional', 'pressure', 'aging', 'scenario']
        if self.config.get('test_mode') not in valid_modes:
            errors.append(f"test_mode 必须是以下值之一: {', '.join(valid_modes)}")
        
        # 环境验证
        valid_envs = ['dev', 'test', 'stress', 'prod']
        if self.config.get('environment') not in valid_envs:
            errors.append(f"environment 必须是以下值之一: {', '.join(valid_envs)}")
        
        # 性能阈值验证
        thresholds = self.config.get('performance_thresholds', {})
        if thresholds.get('avg_response_time', 0) <= 0:
            errors.append("performance_thresholds.avg_response_time 必须大于0")
        if thresholds.get('success_rate', 0) <= 0 or thresholds.get('success_rate', 0) > 100:
            errors.append("performance_thresholds.success_rate 必须在0-100之间")
        if thresholds.get('throughput', 0) <= 0:
            errors.append("performance_thresholds.throughput 必须大于0")
        
        return {
            'is_valid': len(errors) == 0,
            'errors': errors,
            'warnings': warnings,
            'config_summary': {
                'server_url': self.config.get('server_url'),
                'test_mode': self.config.get('test_mode'),
                'environment': self.config.get('environment'),
                'max_workers': self.config.get('max_workers'),
                'aging_duration_hours': self.config.get('aging_duration_hours'),
                'aging_concurrent_threads': self.config.get('aging_concurrent_threads')
            }
        }
    
    def get_validation_report(self):
        """获取配置验证报告"""
        validation = self.validate()
        report = []
        
        if validation['errors']:
            report.append("配置错误:")
            for error in validation['errors']:
                report.append(f"  ✗ {error}")
        
        if validation['warnings']:
            report.append("配置警告:")
            for warning in validation['warnings']:
                report.append(f"  ⚠ {warning}")
        
        if not validation['errors']:
            report.append("配置验证通过 ✓")
        
        report.append("\n配置摘要:")
        for key, value in validation['config_summary'].items():
            report.append(f"  {key}: {value}")
        
        return "\n".join(report)
    
    def get_version_info(self):
        """获取版本信息"""
        return {
            'current_version': self.version,
            'config_version': self.config.get('config_version'),
            'version_history': self.version_history,
            'is_compatible': self._check_version_compatibility()
        }
    
    def _check_version_compatibility(self):
        """检查配置版本兼容性"""
        config_version = self.config.get('config_version')
        if not config_version:
            return True  # 旧版本配置，没有版本信息
        
        # 简单的版本兼容性检查
        try:
            config_major = int(config_version.split('.')[0])
            config_minor = int(config_version.split('.')[1])
            current_major = int(self.version.split('.')[0])
            current_minor = int(self.version.split('.')[1])
            
            # 主要版本必须相同，次要版本可以向后兼容
            return config_major == current_major and config_minor <= current_minor
        except (ValueError, IndexError):
            return False
    
    def migrate_config(self, target_version=None):
        """迁移配置到指定版本"""
        if target_version is None:
            target_version = self.version
        
        config_version = self.config.get('config_version')
        if not config_version:
            # 旧版本配置，添加版本信息
            self.config['config_version'] = target_version
            self.config['config_timestamp'] = self._get_timestamp()
            return True
        
        if config_version == target_version:
            return True  # 已经是目标版本
        
        # 简单的版本迁移逻辑
        migrations = {
            '2.0.0': self._migrate_2_0_0_to_2_1_0,
            '2.1.0': self._migrate_2_1_0_to_2_2_0
        }
        
        try:
            # 应用迁移
            for version in sorted(self.version_history.keys()):
                if version > config_version and version <= target_version:
                    if version in migrations:
                        migrations[version]()
            
            self.config['config_version'] = target_version
            self.config['config_timestamp'] = self._get_timestamp()
            return True
        except Exception as e:
            print(f"配置迁移失败: {e}")
            return False
    
    def _migrate_2_0_0_to_2_1_0(self):
        """从2.0.0迁移到2.1.0"""
        # 添加老化测试配置
        if 'aging_duration_hours' not in self.config:
            self.config['aging_duration_hours'] = 24
        if 'aging_concurrent_threads' not in self.config:
            self.config['aging_concurrent_threads'] = 10
        if 'aging_operation_interval' not in self.config:
            self.config['aging_operation_interval'] = 1.0
        if 'aging_max_data_count' not in self.config:
            self.config['aging_max_data_count'] = 1000
        if 'aging_performance_degradation_threshold' not in self.config:
            self.config['aging_performance_degradation_threshold'] = 20.0
        if 'aging_report_interval_minutes' not in self.config:
            self.config['aging_report_interval_minutes'] = 30
    
    def _migrate_2_1_0_to_2_2_0(self):
        """从2.1.0迁移到2.2.0"""
        # 添加配置元数据
        if 'config_timestamp' not in self.config:
            self.config['config_timestamp'] = self._get_timestamp()
    
    def _get_timestamp(self):
        """获取时间戳"""
        import time
        return int(time.time())
    
    def save_to_file(self, config_path=None):
        """保存配置到文件"""
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), 'test_config.json')
        
        # 确保配置是最新版本
        self.migrate_config()
        
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"保存配置文件失败: {e}")
            return False
    
    def __str__(self):
        """字符串表示"""
        return json.dumps(self.config, indent=2, ensure_ascii=False)


# 全局配置实例
config = TestConfig()