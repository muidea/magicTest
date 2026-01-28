"""Reward Policy"""

import logging
from session import session
from cas import cas
from mock import common as mock
from sdk import RewardPolicySDK

# 配置日志
logger = logging.getLogger(__name__)


def mock_reward_policy_param():
    """模拟积分策略参数

    Returns:
        积分策略参数字典
    """
    return {
        'name': '积分策略' + mock.name(),
        'description': mock.sentence(),
        'policy': '{"rule": "每消费10元获得1积分"}',
        'status': {
            'id': 3  # 假设状态ID为3
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
    
    # 使用 RewardPolicySDK
    reward_policy_sdk = RewardPolicySDK(work_session)
    reward_policy_param = mock_reward_policy_param()
    
    # 创建积分策略
    new_reward_policy = reward_policy_sdk.create_reward_policy(reward_policy_param)
    if not new_reward_policy:
        logger.error('创建积分策略失败')
        return False

    # 验证创建返回的积分策略包含所有必要字段
    required_fields = ['id', 'name', 'policy', 'status']
    for field in required_fields:
        if field not in new_reward_policy:
            logger.error('创建积分策略失败, 缺少字段: %s', field)
            return False

    # 过滤积分策略
    filter_value = {
        'name': new_reward_policy['name'],
    }

    reward_policy_list = reward_policy_sdk.filter_reward_policy(filter_value)
    if not reward_policy_list or len(reward_policy_list) < 1:
        logger.error('过滤积分策略失败')
        return False
    
    # 验证过滤结果包含创建的积分策略
    found = False
    for reward_policy in reward_policy_list:
        if reward_policy['id'] == new_reward_policy['id']:
            found = True
            break
    if not found:
        logger.error('过滤积分策略失败, 未找到创建的积分策略')
        return False

    # 查询积分策略
    cur_reward_policy = reward_policy_sdk.query_reward_policy(new_reward_policy['id'])
    if not cur_reward_policy:
        logger.error('查询积分策略失败')
        return False

    # 更新积分策略
    cur_reward_policy["description"] = "更新后的描述"
    updated_reward_policy = reward_policy_sdk.update_reward_policy(new_reward_policy['id'], cur_reward_policy)
    if not updated_reward_policy:
        logger.error('更新积分策略失败')
        return False

    # 验证更新结果
    if updated_reward_policy['description'] != "更新后的描述":
        logger.error("更新积分策略失败, 描述不匹配")
        return False

    # 再次查询验证更新
    cur_reward_policy = reward_policy_sdk.query_reward_policy(updated_reward_policy['id'])
    if not cur_reward_policy:
        logger.error('查询积分策略失败')
        return False
    if updated_reward_policy['description'] != cur_reward_policy['description']:
        logger.error("更新积分策略失败, 查询的描述不匹配")
        return False

    # 删除积分策略
    deleted_reward_policy = reward_policy_sdk.delete_reward_policy(updated_reward_policy['id'])
    if not deleted_reward_policy:
        logger.error('删除积分策略失败')
        return False
    if deleted_reward_policy['id'] != cur_reward_policy['id']:
        logger.error('删除积分策略失败, 积分策略ID不匹配')
        return False

    return True