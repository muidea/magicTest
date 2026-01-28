"""Credit"""

import logging
from session import session
from cas import cas
from mock import common as mock
from sdk import CreditSDK

# 配置日志
logger = logging.getLogger(__name__)


def mock_credit_param():
    """模拟积分信息参数

    Returns:
        积分信息参数字典
    """
    return {
        'owner': {
            'id': 1  # 假设存在会员ID为1
        },
        'memo': mock.sentence(),
        'credit': 100,
        'type': 1,
        'level': 1
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
    
    # 使用 CreditSDK
    credit_sdk = CreditSDK(work_session)
    credit_param = mock_credit_param()
    
    # 创建积分信息
    new_credit = credit_sdk.create_credit(credit_param)
    if not new_credit:
        logger.error('创建积分信息失败')
        return False

    # 验证创建返回的积分信息包含所有必要字段
    required_fields = ['id', 'sn', 'owner', 'credit', 'type', 'level']
    for field in required_fields:
        if field not in new_credit:
            logger.error('创建积分信息失败, 缺少字段: %s', field)
            return False

    # 过滤积分信息
    filter_value = {
        'owner': new_credit['owner'],
        'type': new_credit['type'],
    }

    credit_list = credit_sdk.filter_credit(filter_value)
    if not credit_list or len(credit_list) < 1:
        logger.error('过滤积分信息失败')
        return False
    
    # 验证过滤结果包含创建的积分信息
    found = False
    for credit in credit_list:
        if credit['id'] == new_credit['id']:
            found = True
            break
    if not found:
        logger.error('过滤积分信息失败, 未找到创建的积分信息')
        return False

    # 查询积分信息
    cur_credit = credit_sdk.query_credit(new_credit['id'])
    if not cur_credit:
        logger.error('查询积分信息失败')
        return False

    # 更新积分信息
    cur_credit["memo"] = mock.sentence()
    updated_credit = credit_sdk.update_credit(new_credit['id'], cur_credit)
    if not updated_credit:
        logger.error('更新积分信息失败')
        return False

    # 验证更新结果
    if updated_credit['memo'] != cur_credit['memo']:
        logger.error("更新积分信息失败, 备注不匹配")
        return False

    # 再次查询验证更新
    cur_credit = credit_sdk.query_credit(updated_credit['id'])
    if not cur_credit:
        logger.error('查询积分信息失败')
        return False
    if updated_credit['memo'] != cur_credit['memo']:
        logger.error("更新积分信息失败, 查询的备注不匹配")
        return False

    # 删除积分信息
    deleted_credit = credit_sdk.delete_credit(updated_credit['id'])
    if not deleted_credit:
        logger.error('删除积分信息失败')
        return False
    if deleted_credit['id'] != cur_credit['id']:
        logger.error('删除积分信息失败, 积分信息ID不匹配')
        return False

    return True