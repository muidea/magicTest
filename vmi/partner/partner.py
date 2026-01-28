"""Partner"""

import logging
from session import session
from cas import cas
from mock import common as mock
from sdk import PartnerSDK

# 配置日志
logger = logging.getLogger(__name__)


def mock_partner_param():
    """模拟合作伙伴参数

    Returns:
        合作伙伴参数字典
    """
    return {
        'name': mock.name(),
        'telephone': mock.name(),
        'wechat': mock.name(),
        'description': mock.sentence(),
        'status': {
            'id': 3
        }
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
    
    # 使用 PartnerSDK
    partner_sdk = PartnerSDK(work_session)
    partner_param = mock_partner_param()
    
    # 创建合作伙伴
    new_partner = partner_sdk.create_partner(partner_param)
    if not new_partner:
        logger.error('创建合作伙伴失败')
        return False

    # 验证创建返回的合作伙伴包含所有必要字段
    required_fields = ['id', 'name', 'telephone', 'wechat', 'description', 'status']
    for field in required_fields:
        if field not in new_partner:
            logger.error('创建合作伙伴失败, 缺少字段: %s', field)
            return False

    # 过滤合作伙伴
    filter_value = {
        'name': new_partner['name'],
        'telephone': new_partner['telephone'],
    }

    partner_list = partner_sdk.filter_partner(filter_value)
    if not partner_list or len(partner_list) != 1:
        logger.error('过滤合作伙伴失败')
        return False
    if partner_list[0]['name'] != new_partner['name'] or partner_list[0]['telephone'] != new_partner['telephone']:
        logger.error('过滤合作伙伴失败, 合作伙伴不匹配')
        return False

    # 查询合作伙伴
    cur_partner = partner_sdk.query_partner(new_partner['id'])
    if not cur_partner:
        logger.error('查询合作伙伴失败')
        return False

    # 更新合作伙伴
    cur_partner["description"] = mock.sentence()
    updated_partner = partner_sdk.update_partner(new_partner['id'], cur_partner)
    if not updated_partner:
        logger.error('更新合作伙伴失败')
        return False

    # 验证更新结果
    if updated_partner['description'] != cur_partner['description']:
        logger.error("更新合作伙伴失败, 描述不匹配")
        return False

    # 再次查询验证更新
    cur_partner = partner_sdk.query_partner(updated_partner['id'])
    if not cur_partner:
        logger.error('查询合作伙伴失败')
        return False
    if updated_partner['description'] != cur_partner['description']:
        logger.error("更新合作伙伴失败, 查询的描述不匹配")
        return False

    # 删除合作伙伴
    deleted_partner = partner_sdk.delete_partner(updated_partner['id'])
    if not deleted_partner:
        logger.error('删除合作伙伴失败')
        return False
    if deleted_partner['id'] != cur_partner['id']:
        logger.error('删除合作伙伴失败, 合作伙伴ID不匹配')
        return False

    return True
