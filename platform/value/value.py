"""Value"""

import logging
from typing import Optional, Dict, Any, List
from session import session
from mock import common as mock

# 配置日志
logger = logging.getLogger(__name__)


def mock_basic_type_value(type_val: Dict[str, Any]) -> Any:
    """模拟基础类型值
    
    Args:
        type_val: 类型字典
        
    Returns:
        模拟值
    """
    if type_val['value'] == 100:
        return False
    elif type_val['value'] == 101:
        return mock.int(0, 125)
    elif type_val['value'] == 102:
        return mock.int(-254, 255)
    elif type_val['value'] == 103:
        return mock.int(0, 1024)
    elif type_val['value'] == 104:
        return mock.int(0, 4096)
    elif type_val['value'] == 105:
        return mock.int(0, 10240)
    elif type_val['value'] == 106:
        return mock.int(0, 500)
    elif type_val['value'] == 107:
        return mock.int(0, 500)
    elif type_val['value'] == 108:
        return mock.int(0, 1024)
    elif type_val['value'] == 109:
        return mock.int(0, 4096)
    elif type_val['value'] == 110:
        return mock.int(0, 10240)
    elif type_val['value'] == 111:
        return mock.int(0, 123450)
    elif type_val['value'] == 112:
        return mock.int(0, 1234567890)
    elif type_val['value'] == 113:
        return mock.sentence()
    elif type_val['value'] == 114:
        return mock.time()
    else:
        return None


def mock_field_value(field: Dict[str, Any]) -> Dict[str, Any]:
    """模拟字段值
    
    Args:
        field: 字段字典
        
    Returns:
        字段值字典
    """
    return {
        'name': field['name'],
        'value': mock_basic_type_value(field['type'])
    }


def mock_entity_value(entity: Dict[str, Any]) -> Dict[str, Any]:
    """模拟实体值
    
    Args:
        entity: 实体字典
        
    Returns:
        实体值字典
    """
    values = {
        'name': entity['name'],
        'pkgPath': entity['pkgPath'],
        'fields': [],
    }

    vals = []
    idx = 1
    while idx < len(entity['fields']):
        field_val = mock_field_value(entity['fields'][idx])
        vals.append(field_val)
        idx = idx + 1

    values['fields'] = vals
    return values


def update_value(entity: Dict[str, Any], value: Dict[str, Any]) -> Dict[str, Any]:
    """更新实体值
    
    Args:
        entity: 实体字典
        value: 值字典
        
    Returns:
        更新后的值字典
    """
    idx = 1
    while idx < len(entity['fields']):
        value['fields'][idx] = mock_field_value(entity['fields'][idx])
        idx = idx + 1
    return value


def mock_entity_query(entity: Dict[str, Any], value: Dict[str, Any]) -> Dict[str, Any]:
    """模拟实体查询
    
    Args:
        entity: 实体字典
        value: 值字典
        
    Returns:
        查询字典
    """
    query = {
        'name': entity['name'],
        'pkgPath': entity['pkgPath'],
        'fields': [],
    }

    vals = []
    idx = 1
    while idx < len(value['fields']) - 1:
        vals.append(value['fields'][idx])
        idx = idx + 1
    query['fields'] = vals
    return query


def mock_entity_filter(entity: Dict[str, Any], value: Dict[str, Any]) -> Dict[str, Any]:
    """模拟实体过滤
    
    Args:
        entity: 实体字典
        value: 值字典
        
    Returns:
        过滤字典
    """
    filter = {
        'pagination': {
            'pageSize': 10,
            'pageNum': 1,
        },
        'params': {
            'name': entity['name'],
            'pkgPath': entity['pkgPath'],
        },
    }
    return filter


class Value:
    """Value"""

    def __init__(self, work_session: session.MagicSession) -> None:
        self.session = work_session

    def filter_value(self, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """过滤值
        
        Args:
            param: 过滤参数
            
        Returns:
            过滤结果或None（失败时）
        """
        val = self.session.post('/core/value/filter/', param)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('过滤值错误')
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('过滤值请求失败: 无响应')
            return None
        return val.get('values')

    def query_value(self, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """查询值
        
        Args:
            param: 查询参数
            
        Returns:
            值信息或None（失败时）
        """
        val = self.session.post('/core/value/query/', param)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('查询值错误')
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('查询值请求失败: 无响应')
            return None
        return val.get('value')

    def insert_value(self, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """插入值
        
        Args:
            param: 值参数
            
        Returns:
            插入的值信息或None（失败时）
        """
        val = self.session.post('/core/value/insert/', param)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('插入值错误')
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('插入值请求失败: 无响应')
            return None
        return val.get('value')

    def update_value(self, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """更新值
        
        Args:
            param: 值参数
            
        Returns:
            更新的值信息或None（失败时）
        """
        val = self.session.post('/core/value/update/', param)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('更新值错误')
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('更新值请求失败: 无响应')
            return None
        return val.get('value')

    def delete_value(self, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """删除值
        
        Args:
            param: 值参数
            
        Returns:
            删除的值信息或None（失败时）
        """
        val = self.session.post('/core/value/delete/', param)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('删除值错误')
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('删除值请求失败: 无响应')
            return None
        return val.get('value')


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
    from entity import entity

    work_session = session.MagicSession('{0}'.format(server_url), namespace)

    # 创建应用、区块、实体作为依赖
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

    entity_instance = entity.Entity(work_session)
    entity_param = entity.mock_entity_param([new_block])
    new_entity = entity_instance.create_entity(entity_param)
    if not new_entity:
        logger.error('创建实体失败')
        block_instance.destroy_block(new_block['id'])
        app_instance.destroy_application(new_app['id'])
        return False

    entity_instance.enable_entity(new_entity['id'])

    value_instance = Value(work_session)

    # 插入值
    value001 = mock_entity_value(new_entity)
    new_value10 = value_instance.insert_value(value001)
    if not new_value10:
        logger.error('插入值失败')
        entity_instance.disable_entity(new_entity['id'])
        entity_instance.destroy_entity(new_entity['id'])
        block_instance.destroy_block(new_block['id'])
        app_instance.destroy_application(new_app['id'])
        return False

    # 更新值
    new_value10 = update_value(new_entity, new_value10)
    updated_value = value_instance.update_value(new_value10)
    if not updated_value:
        logger.error('更新值失败')
        return False

    # 查询值
    query_value = value_instance.query_value(mock_entity_query(new_entity, new_value10))
    if not query_value:
        logger.error('查询值失败')
        return False

    # 再次插入相同值（应成功）
    inserted_value = value_instance.insert_value(new_value10)
    if not inserted_value:
        logger.error('第二次插入值失败')
        return False

    # 过滤值
    value_list = value_instance.filter_value(mock_entity_filter(new_entity, new_value10))
    if not value_list or len(value_list.get('values', [])) != 2:
        logger.error('过滤值失败')
        return False

    # 删除值
    deleted_value = value_instance.delete_value(new_value10)
    if not deleted_value:
        logger.error('删除值失败')
        return False

    # 清理依赖
    entity_instance.disable_entity(new_entity['id'])
    entity_instance.destroy_entity(new_entity['id'])
    block_instance.destroy_block(new_block['id'])
    app_instance.destroy_application(new_app['id'])

    logger.info('所有值操作测试通过')
    return True


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="运行值测试")
    parser.add_argument("--server_url", type=str, required=True, help="服务器URL")
    parser.add_argument("--namespace", type=str, required=True, help="命名空间")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    success = main(args.server_url, args.namespace)
    exit(0 if success else 1)
