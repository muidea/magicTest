"""
测试配置管理系统

支持不同环境的测试配置：
1. 开发环境：快速测试，小规模数据
2. 测试环境：完整功能测试，中等规模数据
3. 压力测试环境：并发压力测试，大规模数据
4. 生产验证环境：生产环境验证，完整规模数据
"""

import os
import json
from enum import Enum
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class TestMode(Enum):
    """测试模式枚举"""
    DEVELOPMENT = "development"      # 开发测试模式，快速执行
    FUNCTIONAL = "functional"        # 功能测试模式，完整验证
    PRESSURE = "pressure"           # 压力测试模式，高并发
    PRODUCTION = "production"       # 生产验证模式，完整规模


class TestConfig:
    """测试配置类"""
    
    # 默认配置
    DEFAULT_CONFIG = {
        # 服务器配置
        "server_url": "https://autotest.local.vpc",
        "username": "administrator",
        "password": "administrator",
        "namespace": "",
        
        # 测试模式配置
        "test_mode": TestMode.DEVELOPMENT.value,
        
        # 基础测试参数（开发模式）
        "development": {
            "warehouse_count": 1,
            "shelf_count": 20,
            "store_count": 10,
            "product_count": 50,           # 从5w减少到50
            "products_per_store": 10,      # 从500减少到10
            "stockin_quantity_per_product": 12,
            "stockin_price_per_product": 100,
            "stockin_shelf_price_per_product": 150,
            "stockin_times": 10,
            "stockout_products_per_store": 5,  # 从100减少到5
            "stockout_quantity_per_product": 5,
            "stockout_price_per_product": 120,
            "stockout_times": 2,
            "interval_val": 0.01,          # 操作间隔
        },
        
        # 功能测试参数
        "functional": {
            "warehouse_count": 1,
            "shelf_count": 20,
            "store_count": 10,
            "product_count": 1000,         # 中等规模
            "products_per_store": 50,      # 中等规模
            "stockin_quantity_per_product": 12,
            "stockin_price_per_product": 100,
            "stockin_shelf_price_per_product": 150,
            "stockin_times": 10,
            "stockout_products_per_store": 20,  # 中等规模
            "stockout_quantity_per_product": 5,
            "stockout_price_per_product": 120,
            "stockout_times": 2,
            "interval_val": 0.05,          # 稍长间隔
        },
        
        # 压力测试参数
        "pressure": {
            "warehouse_count": 2,
            "shelf_count": 40,
            "store_count": 20,
            "product_count": 5000,         # 较大规模
            "products_per_store": 100,     # 较大规模
            "stockin_quantity_per_product": 12,
            "stockin_price_per_product": 100,
            "stockin_shelf_price_per_product": 150,
            "stockin_times": 10,
            "stockout_products_per_store": 50,  # 较大规模
            "stockout_quantity_per_product": 5,
            "stockout_price_per_product": 120,
            "stockout_times": 2,
            "interval_val": 0.02,          # 较短间隔
        },
        
        # 生产验证参数（完整规模）
        "production": {
            "warehouse_count": 1,
            "shelf_count": 20,
            "store_count": 10,
            "product_count": 50000,        # 完整5w规模
            "products_per_store": 500,     # 完整500规模
            "stockin_quantity_per_product": 12,
            "stockin_price_per_product": 100,
            "stockin_shelf_price_per_product": 150,
            "stockin_times": 10,
            "stockout_products_per_store": 100,  # 完整100规模
            "stockout_quantity_per_product": 5,
            "stockout_price_per_product": 120,
            "stockout_times": 2,
            "interval_val": 0.1,           # 较长间隔，避免过载
        },
        
        # 并发测试配置
        "concurrent": {
            "development": {
                "threads": 5,
                "products_per_thread": 20,
                "stockin_orders_per_thread": 3,
                "stockout_orders_per_thread": 2,
                "max_workers": 10,
                "timeout": 300,  # 5分钟
            },
            "functional": {
                "threads": 10,
                "products_per_thread": 50,
                "stockin_orders_per_thread": 5,
                "stockout_orders_per_thread": 3,
                "max_workers": 20,
                "timeout": 600,  # 10分钟
            },
            "pressure": {
                "threads": 50,
                "products_per_thread": 100,
                "stockin_orders_per_thread": 10,
                "stockout_orders_per_thread": 5,
                "max_workers": 100,
                "timeout": 1800,  # 30分钟
            },
            "production": {
                "threads": 20,
                "products_per_thread": 200,
                "stockin_orders_per_thread": 20,
                "stockout_orders_per_thread": 10,
                "max_workers": 50,
                "timeout": 3600,  # 60分钟
            }
        },
        
        # 性能监控配置
        "monitoring": {
            "enable_perf_monitoring": True,
            "collect_metrics": True,
            "metrics_interval": 5,  # 秒
            "log_level": "INFO",
            "report_format": "json",
        },
        
        # 清理配置
        "cleanup": {
            "enable_auto_cleanup": True,
            "cleanup_timeout": 300,  # 5分钟
            "max_retries": 3,
            "batch_size": 50,
        }
    }
    
    # 配置文件路径
    CONFIG_FILE = "test_config.json"
    
    def __init__(self, config_file: Optional[str] = None):
        """初始化配置
        
        Args:
            config_file: 配置文件路径，如果为None则使用默认配置
        """
        self.config = self.DEFAULT_CONFIG.copy()
        
        if config_file and os.path.exists(config_file):
            self.load_config(config_file)
        elif os.path.exists(self.CONFIG_FILE):
            self.load_config(self.CONFIG_FILE)
        
        # 从环境变量覆盖配置
        self._load_from_env()
        
        # 设置当前模式参数
        self._set_mode_params()
    
    def _load_from_env(self):
        """从环境变量加载配置"""
        env_mapping = {
            "TEST_SERVER_URL": "server_url",
            "TEST_USERNAME": "username",
            "TEST_PASSWORD": "password",
            "TEST_NAMESPACE": "namespace",
            "TEST_MODE": "test_mode",
        }
        
        for env_var, config_key in env_mapping.items():
            if env_var in os.environ:
                self.config[config_key] = os.environ[env_var]
    
    def _set_mode_params(self):
        """设置当前测试模式的参数"""
        mode = self.config["test_mode"]
        mode_config = self.config.get(mode, {})
        
        # 将模式特定参数合并到根配置
        for key, value in mode_config.items():
            self.config[key] = value
        
        # 设置并发配置
        concurrent_config = self.config["concurrent"].get(mode, {})
        self.config["concurrent_params"] = concurrent_config
    
    def load_config(self, config_file: str):
        """从文件加载配置
        
        Args:
            config_file: 配置文件路径
        """
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                file_config = json.load(f)
            
            # 深度合并配置
            self._deep_merge(self.config, file_config)
            logger.info(f"从文件加载配置: {config_file}")
            
        except Exception as e:
            logger.warning(f"加载配置文件失败: {e}, 使用默认配置")
    
    def save_config(self, config_file: Optional[str] = None):
        """保存配置到文件
        
        Args:
            config_file: 配置文件路径，如果为None则使用默认路径
        """
        save_file = config_file or self.CONFIG_FILE
        try:
            with open(save_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            logger.info(f"配置已保存到: {save_file}")
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
    
    def _deep_merge(self, target: Dict, source: Dict):
        """深度合并字典
        
        Args:
            target: 目标字典
            source: 源字典
        """
        for key, value in source.items():
            if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                self._deep_merge(target[key], value)
            else:
                target[key] = value
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值
        
        Args:
            key: 配置键
            default: 默认值
            
        Returns:
            配置值
        """
        return self.config.get(key, default)
    
    def set(self, key: str, value: Any):
        """设置配置值
        
        Args:
            key: 配置键
            value: 配置值
        """
        self.config[key] = value
    
    def set_mode(self, mode: str):
        """设置测试模式
        
        Args:
            mode: 测试模式
        """
        if mode in [m.value for m in TestMode]:
            self.config["test_mode"] = mode
            self._set_mode_params()
            logger.info(f"测试模式已设置为: {mode}")
        else:
            logger.warning(f"无效的测试模式: {mode}")
    
    def get_mode_params(self) -> Dict:
        """获取当前模式的参数
        
        Returns:
            当前模式的参数字典
        """
        mode = self.config["test_mode"]
        return self.config.get(mode, {})
    
    def get_concurrent_params(self) -> Dict:
        """获取并发测试参数
        
        Returns:
            并发测试参数字典
        """
        return self.config.get("concurrent_params", {})
    
    def get_server_config(self) -> Dict:
        """获取服务器配置
        
        Returns:
            服务器配置字典
        """
        return {
            "server_url": self.config["server_url"],
            "username": self.config["username"],
            "password": self.config["password"],
            "namespace": self.config["namespace"],
        }
    
    def __getitem__(self, key: str) -> Any:
        """支持字典式访问"""
        return self.config[key]
    
    def __setitem__(self, key: str, value: Any):
        """支持字典式设置"""
        self.config[key] = value
    
    def __contains__(self, key: str) -> bool:
        """支持in操作符"""
        return key in self.config


# 全局配置实例
_config_instance: Optional[TestConfig] = None


def get_config(config_file: Optional[str] = None) -> TestConfig:
    """获取全局配置实例
    
    Args:
        config_file: 配置文件路径
        
    Returns:
        配置实例
    """
    global _config_instance
    if _config_instance is None:
        _config_instance = TestConfig(config_file)
    return _config_instance


def create_config_file():
    """创建示例配置文件"""
    config = TestConfig()
    config.save_config("test_config.example.json")
    logger.info("示例配置文件已创建: test_config.example.json")


if __name__ == "__main__":
    # 创建示例配置文件
    create_config_file()
    
    # 演示使用
    config = get_config()
    print(f"当前测试模式: {config['test_mode']}")
    print(f"服务器URL: {config['server_url']}")
    print(f"产品数量: {config.get('product_count', 'N/A')}")
    print(f"并发线程数: {config.get_concurrent_params().get('threads', 'N/A')}")