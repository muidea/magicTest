"""Credit Reward"""

import logging
from session import session
from cas import cas
from mock import common as mock
from sdk import CreditRewardSDK

# 配置日志
logger = logging.getLogger(__name__)


def mock_credit_reward_param():
    """模拟积分消费记录参数

    Returns:
        积分消费记录参数字典
    """
    return {
        'owner': {
            'id': 1  # 假设存在会员ID为1
        },
        'credit': 50,
        'memo': mock.sentence()
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
    
    # 使用 CreditRewardSDK
    credit_reward_sdk = CreditRewardSDK(work_session)
    credit_reward_param = mock_credit_reward_param()
    
    # 创建积分消费记录
    new_credit_reward = credit_reward_sdk.create_credit_reward(credit_reward_param)
    if not new_credit_reward:
        logger.error('创建积分消费记录失败')
        return False

    # 验证创建返回的积分消费记录包含所有必要字段
    required_fields = ['id', 'sn', 'owner', 'credit']
    for field in required_fields:
        if field not in new_credit_reward:
            logger.error('创建积分消费记录失败, 缺少字段: %s', field)
            return False

    # 过滤积分消费记录
    filter_value = {
        'owner': new_credit_reward['owner'],
        'credit': new_credit_reward['credit'],
    }

    credit_reward_list = credit_reward_sdk.filter_credit_reward(filter_value)
    if not credit_reward_list or len(credit_reward_list) < 1:
        logger.error('过滤积分消费记录失败')
        return False
    
    # 验证过滤结果包含创建的积分消费记录
    found = False
    for credit_reward in credit_reward_list:
        if credit_reward['id'] == new_credit_reward['id']:
            found = True
            break
    if not found:
        logger.error('过滤积分消费记录失败, 未找到创建的积分消费记录')
        return False

    # 查询积分消费记录
    cur_credit_reward = credit_reward_sdk.query_credit_reward(new_credit_reward['id'])
    if not cur_credit_reward:
        logger.error('查询积分消费记录失败')
        return False

    # 更新积分消费记录
    cur_credit_reward["memo"] = "更新后的备注"
    updated_credit_reward = credit_reward_sdk.update_credit_reward(new_credit_reward['id'], cur_credit_reward)
    if not updated_credit_reward:
        logger.error('更新积分消费记录失败')
        return False

    # 验证更新结果
    if updated_credit_reward['memo'] != "更新后的备注":
        logger.error("更新积分消费记录失败, 备注不匹配")
        return False

    # 再次查询验证更新
    cur_credit_reward = credit_reward_sdk.query_credit_reward(updated_credit_reward['id'])
    if not cur_credit_reward:
        logger.error('查询积分消费记录失败')
        return False
    if updated_credit_reward['memo'] != cur_credit_reward['memo']:
        logger.error("更新积分消费记录失败, 查询的备注不匹配")
        return False

    # 删除积分消费记录
    deleted_credit_reward = credit_reward_sdk.delete_credit_reward(updated_credit_reward['id'])
    if not deleted_credit_reward:
        logger.error('删除积分消费记录失败')
        return False
    if deleted_credit_reward['id'] != cur_credit_reward['id']:
        logger.error('删除积分消费记录失败, 积分消费记录ID不匹配')
        return False

    return True