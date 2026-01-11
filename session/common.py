
"""MagicEntity - Entity operations for RESTful APIs"""

import logging
from typing import Any, Dict, List, Optional, Union

# Configure logger
logger = logging.getLogger(__name__)


class MagicEntity:
    """Entity operations wrapper for RESTful APIs.
    
    This class provides CRUD operations for entities using a session.
    
    Attributes:
        session: MagicSession instance for HTTP requests
        base_url: Base URL for entity operations
    """

    def __init__(self, base_url: str, work_session: Any):
        """Initialize MagicEntity.
        
        Args:
            base_url: Base URL for entity operations
            work_session: MagicSession instance for HTTP requests
        """
        self.session = work_session
        self.base_url = base_url

    def _handle_response(self, response: Dict[str, Any], operation: str,
                        url: str, **context) -> Optional[Any]:
        """Handle API response with error checking and logging.
        
        Args:
            response: API response dictionary
            operation: Operation name for logging
            url: Request URL for logging
            **context: Additional context for logging
            
        Returns:
            Response data on success, None on error
        """
        if response and response.get('error') is None:
            return response.get('value') or response.get('values')
        
        if response:
            error = response['error']
            logger.error('%s操作错误, URL: %s, 上下文: %s',
                        operation, url, context)
            logger.error('错误代码: %s, 错误消息: %s',
                        error.get('code'), error.get('message'))
        else:
            logger.error('%s请求失败, URL: %s, 上下文: %s',
                        operation, url, context)
        
        return None

    def filter(self, filter_val: Dict[str, Any]) -> Optional[List[Any]]:
        """Filter entities based on criteria.
        
        Args:
            filter_val: Filter criteria dictionary
            
        Returns:
            List of entities on success, None on error
        """
        url = f'{self.base_url}s/'
        response = self.session.get(url, filter_val)
        return self._handle_response(response, '过滤', url, filter_val=filter_val)

    def query(self, id_val: Union[str, int]) -> Optional[Any]:
        """Query single entity by ID.
        
        Args:
            id_val: Entity ID
            
        Returns:
            Entity data on success, None on error
        """
        url = f'{self.base_url}s/{id_val}'
        response = self.session.get(url)
        return self._handle_response(response, '查询', url, id_val=id_val)

    def insert(self, param_val: Dict[str, Any]) -> Optional[Any]:
        """Insert new entity.
        
        Args:
            param_val: Entity data dictionary
            
        Returns:
            Created entity data on success, None on error
        """
        url = f'{self.base_url}s/'
        response = self.session.post(url, param_val)
        return self._handle_response(response, '插入', url, param_val=param_val)

    def update(self, id_val: Union[str, int], param_val: Dict[str, Any]) -> Optional[Any]:
        """Update existing entity.
        
        Args:
            id_val: Entity ID
            param_val: Updated entity data dictionary
            
        Returns:
            Updated entity data on success, None on error
        """
        url = f'{self.base_url}s/{id_val}'
        response = self.session.put(url, param_val)
        return self._handle_response(response, '更新', url, id_val=id_val, param_val=param_val)

    def delete(self, id_val: Union[str, int]) -> Optional[Any]:
        """Delete entity by ID.
        
        Args:
            id_val: Entity ID
            
        Returns:
            Deletion result on success, None on error
        """
        url = f'{self.base_url}s/{id_val}'
        response = self.session.delete(url)
        return self._handle_response(response, '删除', url, id_val=id_val)

    def create(self, param_val: Dict[str, Any]) -> Optional[Any]:
        """Create entity using special create endpoint.
        
        Note: URL pattern remains as per original requirement.
        
        Args:
            param_val: Entity data dictionary
            
        Returns:
            Created entity data on success, None on error
        """
        url = f'{self.base_url}/create/'
        response = self.session.post(url, param_val)
        return self._handle_response(response, '创建', url, param_val=param_val)

    def destroy(self, id_val: Union[str, int]) -> Optional[Any]:
        """Destroy entity using special destroy endpoint.
        
        Note: URL pattern remains as per original requirement.
        
        Args:
            id_val: Entity ID
            
        Returns:
            Destruction result on success, None on error
        """
        url = f'{self.base_url}/destroy/{id_val}'
        response = self.session.delete(url)
        return self._handle_response(response, '销毁', url, id_val=id_val)
