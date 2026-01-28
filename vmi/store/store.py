"""Store"""

import logging
from session import session
from cas import cas
from mock import common as mock
from sdk import StoreSDK

# 配置日志
logger = logging.getLogger(__name__)


def mock_store_param():
    """模拟店铺参数

    Returns:
        店铺参数字典
    """
    return {
        'name': 'STORE' + mock.name(),
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
    cas_session = Cas(work_session)
    if not cas_session.login('administrator', 'administrator'):
        logger.error('CAS登录失败')
        return False

    work_session.bind_token(cas_session.get_session_token())

    # 使用 StoreSDK
    store_sdk = StoreSDK(work_session)
    store_param = mock_store_param()
    
    # 创建店铺
    new_store = store_sdk.create_store(store_param)
    if not new_store:
        logger.error('创建店铺失败')
        return False

    # 验证创建返回的店铺包含所有必要字段
    required_fields = ['id', 'name', 'description']
    for field in required_fields:
        if field not in new_store:
            logger.error('创建店铺失败, 缺少字段: %s', field)
            return False

    # 过滤店铺
    filter_value = {
        'name': new_store['name'],
    }

    store_list = store_sdk.filter_store(filter_value)
    if not store_list or len(store_list) != 1:
        logger.error('过滤店铺失败')
        return False
    if store_list[0]['name'] != new_store['name']:
        logger.error('过滤店铺失败, 店铺不匹配')
        return False

    # 查询店铺
    cur_store = store_sdk.query_store(new_store['id'])
    if not cur_store:
        logger.error('查询店铺失败')
        return False

    # 更新店铺
    cur_store["description"] = mock.sentence()
    updated_store = store_sdk.update_store(new_store['id'], cur_store)
    if not updated_store:
        logger.error('更新店铺失败')
        return False

    # 验证更新结果
    if updated_store['description'] != cur_store['description']:
        logger.error("更新店铺失败, 描述不匹配")
        return False

    # 再次查询验证更新
    cur_store = store_sdk.query_store(updated_store['id'])
    if not cur_store:
        logger.error('查询店铺失败')
        return False
    if updated_store['description'] != cur_store['description']:
        logger.error("更新店铺失败, 查询的描述不匹配")
        return False

    # 删除店铺
    deleted_store = store_sdk.delete_store(updated_store['id'])
    if not deleted_store:
        logger.error('删除店铺失败')
        return False
    if deleted_store['id'] != cur_store['id']:
        logger.error('删除店铺失败, 店铺ID不匹配')
        return False

    return True
