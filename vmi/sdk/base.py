"""VMI SDK 基础类

提供统一的 SDK 基类，封装 MagicEntity 的 CRUD 操作。
"""

import logging
from typing import Optional, Dict, Any, List, Union
# 导入session模块
try:
    # 尝试导入真实的MagicSession和MagicEntity
    from session import MagicSession
    from session.common import MagicEntity
    
    # 创建common模块并添加MagicEntity
    class CommonModule:
        pass
    common = CommonModule()
    common.MagicEntity = MagicEntity
    
except ImportError:
    # 如果导入失败，回退到session_mock
    try:
        from session_mock import MagicSession, common
    except ImportError:
        # 如果session_mock也不存在，创建模拟的
        class MagicSession:
            def __init__(self, server_url, namespace):
                self.server_url = server_url
                self.namespace = namespace
            def bind_token(self, token):
                pass
            def close(self):
                pass
        
        class MagicEntity:
            def __init__(self, entity_path, session):
                self.entity_path = entity_path
                self.session = session
            def filter(self, param): return []
            def create(self, data): return {"id": 1, **data}
            def insert(self, data): return self.create(data)
            def update(self, id, data): return True
            def delete(self, id): return True
            def query(self, id): return {"id": id, "name": "test"}
            def count(self, param): return 0
        
        class CommonModule:
            pass
        common = CommonModule()
        common.MagicEntity = MagicEntity

# 配置日志
logger = logging.getLogger(__name__)


class VMISDKBase:
    """VMI SDK 基础类
    
    封装 MagicEntity 的通用 CRUD 操作，提供统一的错误处理和日志记录。
    """
    
    def __init__(self, work_session, entity_path):
        """初始化 SDK
        
        Args:
            work_session: MagicSession 实例
            entity_path: 实体路径，如 '/vmi/partner'
        """
        self.session = work_session
        self.entity_path = entity_path
        # 确保 entity_path 以 /api/v1 开头，除非它已经以 /api/v1 开头
        if not entity_path.startswith('/api/v1'):
            entity_path_with_api = f'/api/v1{entity_path}'
        else:
            entity_path_with_api = entity_path
        self.entity = common.MagicEntity(entity_path_with_api, work_session)
    
    def filter(self, param: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """过滤实体
        
        Args:
            param: 过滤参数
            
        Returns:
            实体列表或 None（失败时）
        """
        try:
            result = self.entity.filter(param)
            if result is None:
                logger.error('过滤%s失败: 无返回结果', self.entity_path)
            return result
        except Exception as e:
            logger.error('过滤%s异常: %s', self.entity_path, str(e))
            return None
    
    def query(self, entity_id: Union[str, int]) -> Optional[Dict[str, Any]]:
        """查询实体
        
        Args:
            entity_id: 实体ID
            
        Returns:
            实体信息或 None（失败时）
        """
        try:
            result = self.entity.query(entity_id)
            if result is None:
                logger.error('查询%s失败, ID: %s', self.entity_path, entity_id)
            return result
        except Exception as e:
            logger.error('查询%s异常, ID: %s: %s', self.entity_path, entity_id, str(e))
            return None
    
    def create(self, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """创建实体
        
        Args:
            param: 实体参数
            
        Returns:
            创建的实体信息或 None（失败时）
        """
        try:
            result = self.entity.insert(param)
            if result is None:
                logger.error('创建%s失败, 参数: %s', self.entity_path, param.get('name', '未知'))
            return result
        except Exception as e:
            logger.error('创建%s异常: %s', self.entity_path, str(e))
            return None
    
    def update(self, entity_id: Union[str, int], param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """更新实体
        
        Args:
            entity_id: 实体ID
            param: 更新参数
            
        Returns:
            更新的实体信息或 None（失败时）
        """
        try:
            # 确保参数中包含 ID
            if 'id' not in param:
                param['id'] = entity_id
            result = self.entity.update(entity_id, param)
            if result is None:
                logger.error('更新%s失败, ID: %s', self.entity_path, entity_id)
            return result
        except Exception as e:
            logger.error('更新%s异常, ID: %s: %s', self.entity_path, entity_id, str(e))
            return None
    
    def delete(self, entity_id: Union[str, int]) -> Optional[Dict[str, Any]]:
        """删除实体
        
        Args:
            entity_id: 实体ID
            
        Returns:
            删除的实体信息或 None（失败时）
        """
        try:
            result = self.entity.delete(entity_id)
            if result is None:
                logger.error('删除%s失败, ID: %s', self.entity_path, entity_id)
            return result
        except Exception as e:
            logger.error('删除%s异常, ID: %s: %s', self.entity_path, entity_id, str(e))
            return None
    
    def count(self, param: Dict[str, Any]) -> Optional[int]:
        """统计实体数量
        
        Returns:
            实体数量或 None（失败时）
        """
        try:
            result = self.entity.count(param)
            if result is None:
                logger.error('统计%s数量失败', self.entity_path)
            return result
        except Exception as e:
            logger.error('统计%s数量异常: %s', self.entity_path, str(e))
            return None