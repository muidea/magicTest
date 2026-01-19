"""Product"""

import logging
from session import session
from cas import cas
from mock import common as mock
from sdk import ProductSDK

# 配置日志
logger = logging.getLogger(__name__)


def mock_product_param():
    """模拟产品参数

    Returns:
        产品参数字典
    """
    return {
        'name': mock.name(),
        'description': mock.sentence(),
        'skuInfo': [{
            'sku': 'a001',
            'description': mock.sentence(),
            'image': [mock.url(), mock.url(), ],
        }],
        'image': [mock.url()],
        'expire': 100,
        'tags': ['a', 'b', 'c']
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

    # 使用 ProductSDK
    product_sdk = ProductSDK(work_session)
    product_param = mock_product_param()
    
    # 创建产品
    new_product = product_sdk.create_product(product_param)
    if not new_product:
        logger.error('创建产品失败')
        return False

    # 验证创建返回的产品包含所有必要字段
    required_fields = ['id', 'name', 'description', 'skuInfo', 'image', 'expire', 'tags']
    for field in required_fields:
        if field not in new_product:
            logger.error('创建产品失败, 缺少字段: %s', field)
            return False

    # 过滤产品
    filter_value = {
        'name': new_product['name'],
    }

    product_list = product_sdk.filter_product(filter_value)
    if not product_list or len(product_list) != 1:
        logger.error('过滤产品失败')
        return False
    if product_list[0]['name'] != new_product['name']:
        logger.error('过滤产品失败, 产品不匹配')
        return False

    # 查询产品
    cur_product = product_sdk.query_product(new_product['id'])
    if not cur_product:
        logger.error('查询产品失败')
        return False

    # 更新产品
    cur_product["description"] = mock.sentence()
    updated_product = product_sdk.update_product(new_product['id'], cur_product)
    if not updated_product:
        logger.error('更新产品失败')
        return False

    # 验证更新结果
    if updated_product['description'] != cur_product['description']:
        logger.error("更新产品失败, 描述不匹配")
        return False

    # 再次查询验证更新
    cur_product = product_sdk.query_product(updated_product['id'])
    if not cur_product:
        logger.error('查询产品失败')
        return False
    if updated_product['description'] != cur_product['description']:
        logger.error("更新产品失败, 查询的描述不匹配")
        return False

    # 删除产品
    deleted_product = product_sdk.delete_product(updated_product['id'])
    if not deleted_product:
        logger.error('删除产品失败')
        return False
    if deleted_product['id'] != cur_product['id']:
        logger.error('删除产品失败, 产品ID不匹配')
        return False

    return True
