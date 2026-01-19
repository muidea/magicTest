"""Warehouse"""

import logging
from session import session
from cas import cas
from mock import common as mock
from sdk import WarehouseSDK

# 配置日志
logger = logging.getLogger(__name__)


def mock_warehouse_param():
    """模拟仓库参数

    Returns:
        仓库参数字典
    """
    return {
        'name': 'CK' + mock.name(),
        'description': mock.sentence()
    }


def main(server_url: str, namespace: str) -> bool:
    """主函数
    
    Args:
        server_url: 服务器URL
        namespace: 命名空间
        
    Returns:
        成功返回True，失败返回False
    """
    work_session = session.MagicSession('{0}'.format(server_url), namespace)
    cas_session = cas.Cas(work_session)
    if not cas_session.login('administrator', 'administrator'):
        logger.error('CAS登录失败')
        return False

    work_session.bind_token(cas_session.get_session_token())

    # 使用 WarehouseSDK
    warehouse_sdk = WarehouseSDK(work_session)
    warehouse_param = mock_warehouse_param()
    
    # 创建仓库
    new_warehouse = warehouse_sdk.create_warehouse(warehouse_param)
    if not new_warehouse:
        logger.error('创建仓库失败')
        return False

    # 验证创建返回的仓库包含所有必要字段
    required_fields = ['id', 'name', 'description']
    for field in required_fields:
        if field not in new_warehouse:
            logger.error('创建仓库失败, 缺少字段: %s', field)
            return False

    # 过滤仓库
    filter_value = {
        'name': new_warehouse['name'],
    }

    warehouse_list = warehouse_sdk.filter_warehouse(filter_value)
    if not warehouse_list or len(warehouse_list) != 1:
        logger.error('过滤仓库失败')
        return False
    if warehouse_list[0]['name'] != new_warehouse['name']:
        logger.error('过滤仓库失败, 仓库不匹配')
        return False

    # 查询仓库
    cur_warehouse = warehouse_sdk.query_warehouse(new_warehouse['id'])
    if not cur_warehouse:
        logger.error('查询仓库失败')
        return False

    # 更新仓库
    cur_warehouse["description"] = mock.sentence()
    updated_warehouse = warehouse_sdk.update_warehouse(new_warehouse['id'], cur_warehouse)
    if not updated_warehouse:
        logger.error('更新仓库失败')
        return False

    # 验证更新结果
    if updated_warehouse['description'] != cur_warehouse['description']:
        logger.error("更新仓库失败, 描述不匹配")
        return False

    # 再次查询验证更新
    cur_warehouse = warehouse_sdk.query_warehouse(updated_warehouse['id'])
    if not cur_warehouse:
        logger.error('查询仓库失败')
        return False
    if updated_warehouse['description'] != cur_warehouse['description']:
        logger.error("更新仓库失败, 查询的描述不匹配")
        return False

    # 删除仓库
    deleted_warehouse = warehouse_sdk.delete_warehouse(updated_warehouse['id'])
    if not deleted_warehouse:
        logger.error('删除仓库失败')
        return False
    if deleted_warehouse['id'] != cur_warehouse['id']:
        logger.error('删除仓库失败, 仓库ID不匹配')
        return False

    return True
