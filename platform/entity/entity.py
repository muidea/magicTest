"""Entity"""

import logging
from typing import Optional, Dict, Any, List
from session import session
from mock import common as mock

# 配置日志
logger = logging.getLogger(__name__)


basic_type_element = [
    {
        'value': 100,
        'name': 'bool',
        'pkgPath': '',
    },
    {
        'value': 101,
        'name': 'int8',
        'pkgPath': '',
    },
    {
        'value': 102,
        'name': 'int16',
        'pkgPath': '',
    },
    {
        'value': 103,
        'name': 'int32',
        'pkgPath': '',
    },
    {
        'value': 104,
        'name': 'int',
        'pkgPath': '',
    },
    {
        'value': 105,
        'name': 'int64',
        'pkgPath': '',
    },
    {
        'value': 106,
        'name': 'uint8',
        'pkgPath': '',
    },
    {
        'value': 107,
        'name': 'uint16',
        'pkgPath': '',
    },
    {
        'value': 108,
        'name': 'uint32',
        'pkgPath': '',
    },
    {
        'value': 109,
        'name': 'uint',
        'pkgPath': '',
    },
    {
        'value': 110,
        'name': 'uint64',
        'pkgPath': '',
    },
    {
        'value': 111,
        'name': 'float32',
        'pkgPath': '',
    },
    {
        'value': 112,
        'name': 'float64',
        'pkgPath': '',
    },
    {
        'value': 113,
        'name': 'string',
        'pkgPath': '',
    },
    {
        'value': 114,
        'name': 'time',
        'pkgPath': '',
    },
]

compose_type_element = [
    {
        'value': 115,
        'name': 'struct',
        'pkgPath': '',
    },
    {
        'value': 116,
        'name': 'slice',
        'pkgPath': '',
    },
]


class Entity:
    """Entity"""

    def __init__(self, work_session: session.MagicSession) -> None:
        self.session = work_session

    def search_entity(self, pkg_key: str) -> Optional[Dict[str, Any]]:
        """搜索实体
        
        Args:
            pkg_key: 实体包键（格式：名称@包路径）
            
        Returns:
            实体信息或None（失败时）
        """
        # 分割 pkg_key
        parts = pkg_key.split('@')
        if len(parts) != 2:
            logger.error('无效的包键格式: %s', pkg_key)
            return None
        e_name, e_pkg_path = parts[0], parts[1]
        headers = {
            'Entity-Name': e_name,
            'Entity-PkgPath': e_pkg_path,
        }
        val = self.session.get('/core/entity/search', headers=headers)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('搜索实体错误, 包键: %s', pkg_key)
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('搜索实体请求失败: 无响应, 包键: %s', pkg_key)
            return None
        return val.get('value')

    def filter_entity(self, param: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """过滤实体
        
        Args:
            param: 过滤参数
            
        Returns:
            实体列表或None（失败时）
        """
        val = self.session.post('/core/entity/filter/', param)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('过滤实体错误')
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('过滤实体请求失败: 无响应')
            return None
        return val.get('values')

    def query_entity(self, id: int) -> Optional[Dict[str, Any]]:
        """查询实体
        
        Args:
            id: 实体ID
            
        Returns:
            实体信息或None（失败时）
        """
        val = self.session.get('/core/entity/query/{0}'.format(id))
        if val is None or val.get('error') is not None:
            if val:
                logger.error('查询实体错误, ID: %s', id)
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('查询实体请求失败: 无响应, ID: %s', id)
            return None
        return val.get('value')

    def create_entity(self, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """创建实体
        
        Args:
            param: 实体参数
            
        Returns:
            创建的实体信息或None（失败时）
        """
        val = self.session.post('/core/entity/create/', param)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('创建实体错误, 实体: %s', param.get('name', '未知'))
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('创建实体请求失败: 无响应, 实体: %s', param.get('name', '未知'))
            return None
        return val.get('value')

    def update_entity(self, id: int, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """更新实体
        
        Args:
            id: 实体ID
            param: 实体参数
            
        Returns:
            更新的实体信息或None（失败时）
        """
        val = self.session.put('/core/entity/update/{0}'.format(id), param)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('更新实体错误, ID: %s', id)
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('更新实体请求失败: 无响应, ID: %s', id)
            return None
        return val.get('value')

    def destroy_entity(self, id: int) -> Optional[Dict[str, Any]]:
        """销毁实体
        
        Args:
            id: 实体ID
            
        Returns:
            销毁的实体信息或None（失败时）
        """
        val = self.session.delete('/core/entity/destroy/{0}'.format(id))
        if val is None or val.get('error') is not None:
            if val:
                logger.error('销毁实体错误, ID: %s', id)
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('销毁实体请求失败: 无响应, ID: %s', id)
            return None
        return val.get('value')

    def enable_entity(self, id: int) -> Optional[Dict[str, Any]]:
        """启用实体
        
        Args:
            id: 实体ID
            
        Returns:
            启用的实体信息或None（失败时）
        """
        val = self.session.put('/core/entity/enable/{0}'.format(id), None)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('启用实体错误, ID: %s', id)
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('启用实体请求失败: 无响应, ID: %s', id)
            return None
        return val.get('value')

    def disable_entity(self, id: int) -> Optional[Dict[str, Any]]:
        """禁用实体
        
        Args:
            id: 实体ID
            
        Returns:
            禁用的实体信息或None（失败时）
        """
        val = self.session.put('/core/entity/disable/{0}'.format(id), None)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('禁用实体错误, ID: %s', id)
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('禁用实体请求失败: 无响应, ID: %s', id)
            return None
        return val.get('value')


def mock_basic_type() -> Dict[str, Any]:
    """模拟基础类型"""
    idx = mock.int(0, len(basic_type_element) - 1)
    return basic_type_element[idx]


def mock_field(idx: int) -> Dict[str, Any]:
    """模拟字段"""
    return {
        'index': idx,
        'name': mock.word(),
        "spec": {
            "viewDeclare": [1, 2],
        },
        'type': mock_basic_type(),
    }


def mock_entity_param(blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """模拟实体参数
    
    Args:
        blocks: 区块列表
        
    Returns:
        实体参数字典
    """
    val = {
        'name': mock.word(),
        'pkgPath': mock.word(),
        'isPtr': False,
        'block': blocks,
        'version': '0.0.1',
    }

    fields = [
        {
            "index": 0,
            "name": "id",
            "spec": {
                "primaryKey": True,
                "valueDeclare": 1,
                "viewDeclare": [1, 2],
            },
            "type": {
                "name": "int",
                "value": 104,
                "pkgPath": "",
                "isPtr": False,
            }
        },
    ]

    field_size = mock.int(2, 6)
    idx = 1
    while idx < field_size:
        fields.append(mock_field(idx))
        idx = idx + 1

    val['fields'] = fields
    return val


def main(server_url: str, namespace: str) -> bool:
    """主函数
    
    Args:
        server_url: 服务器URL
        namespace: 命名空间
        
    Returns:
        成功返回True，失败返回False
    """
    from application import application
    from block import block

    work_session = session.MagicSession('{0}'.format(server_url), namespace)

    # 创建应用和区块作为依赖
    app_instance = application.Application(work_session)
    app_param = application.mock_application_param()
    new_app = app_instance.create_application(app_param)
    if not new_app:
        logger.error('创建应用失败')
        return False

    block_instance = block.Block(work_session)
    block_param = block.mock_block_param()
    new_block = block_instance.create_block(block_param)
    if not new_block:
        logger.error('创建区块失败')
        app_instance.destroy_application(new_app['id'])
        return False

    work_session.bind_application(new_app['uuid'])

    entity_instance = Entity(work_session)

    # 搜索实体（应返回空）
    pkg_key = 'test@test'
    searched = entity_instance.search_entity(pkg_key)
    if searched is not None:
        logger.error('搜索实体应返回None')
        return False

    # 创建实体
    entity001 = mock_entity_param([new_block])
    new_entity10 = entity_instance.create_entity(entity001)
    if not new_entity10:
        logger.error('创建实体失败')
        block_instance.destroy_block(new_block['id'])
        app_instance.destroy_application(new_app['id'])
        return False

    # 搜索实体（应找到）
    pkg_key = '{0}@{1}'.format(new_entity10['name'], new_entity10['pkgPath'])
    searched = entity_instance.search_entity(pkg_key)
    if not searched:
        logger.error('搜索实体失败')
        return False

    # 更新实体
    new_entity10['version'] = '0.0.2'
    new_entity11 = entity_instance.update_entity(new_entity10['id'], new_entity10)
    if not new_entity11 or new_entity11['version'] != new_entity10['version']:
        logger.error('更新实体失败')
        return False

    # 创建第二个实体
    entity002 = mock_entity_param([new_block])
    new_entity20 = entity_instance.create_entity(entity002)
    if not new_entity20:
        logger.error('创建第二个实体失败')
        return False

    # 过滤实体
    entity_filter = {
        'params': {
            'items': {
                "name": '{0}|='.format(entity002['name'])
            }
        }
    }
    entity_list = entity_instance.filter_entity(entity_filter)
    if not entity_list or len(entity_list) != 1:
        logger.error('过滤实体失败')
        return False

    # 查询实体
    queried_entity = entity_instance.query_entity(new_entity10['id'])
    if not queried_entity:
        logger.error('查询实体失败')
        return False

    # 启用实体
    enabled_entity = entity_instance.enable_entity(new_entity10['id'])
    if not enabled_entity:
        logger.error('启用实体失败')
        return False

    # 禁用实体
    disabled_entity = entity_instance.disable_entity(new_entity10['id'])
    if not disabled_entity:
        logger.error('禁用实体失败')
        return False

    # 销毁实体
    deleted_entity1 = entity_instance.destroy_entity(new_entity10['id'])
    if not deleted_entity1:
        logger.error('销毁实体失败')
        return False

    deleted_entity2 = entity_instance.destroy_entity(new_entity20['id'])
    if not deleted_entity2:
        logger.error('销毁第二个实体失败')
        return False

    # 清理依赖
    block_instance.destroy_block(new_block['id'])
    app_instance.destroy_application(new_app['id'])

    logger.info('所有实体操作测试通过')
    return True


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="运行实体测试")
    parser.add_argument("--server_url", type=str, required=True, help="服务器URL")
    parser.add_argument("--namespace", type=str, required=True, help="命名空间")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    success = main(args.server_url, args.namespace)
    exit(0 if success else 1)
