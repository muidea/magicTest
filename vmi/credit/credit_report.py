"""Credit Report"""

import logging
from session import session
from cas import cas
from mock import common as mock
from sdk import CreditReportSDK

# 配置日志
logger = logging.getLogger(__name__)


def mock_credit_report_param():
    """模拟积分报表参数

    Returns:
        积分报表参数字典
    """
    return {
        'owner': {
            'id': 1  # 假设存在会员ID为1
        },
        'credit': 1000,
        'available': 800
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
    
    # 使用 CreditReportSDK
    credit_report_sdk = CreditReportSDK(work_session)
    credit_report_param = mock_credit_report_param()
    
    # 创建积分报表
    new_credit_report = credit_report_sdk.create_credit_report(credit_report_param)
    if not new_credit_report:
        logger.error('创建积分报表失败')
        return False

    # 验证创建返回的积分报表包含所有必要字段
    required_fields = ['id', 'sn', 'owner', 'credit', 'available']
    for field in required_fields:
        if field not in new_credit_report:
            logger.error('创建积分报表失败, 缺少字段: %s', field)
            return False

    # 过滤积分报表
    filter_value = {
        'owner': new_credit_report['owner'],
    }

    credit_report_list = credit_report_sdk.filter_credit_report(filter_value)
    if not credit_report_list or len(credit_report_list) < 1:
        logger.error('过滤积分报表失败')
        return False
    
    # 验证过滤结果包含创建的积分报表
    found = False
    for credit_report in credit_report_list:
        if credit_report['id'] == new_credit_report['id']:
            found = True
            break
    if not found:
        logger.error('过滤积分报表失败, 未找到创建的积分报表')
        return False

    # 查询积分报表
    cur_credit_report = credit_report_sdk.query_credit_report(new_credit_report['id'])
    if not cur_credit_report:
        logger.error('查询积分报表失败')
        return False

    # 更新积分报表
    cur_credit_report["available"] = 600
    updated_credit_report = credit_report_sdk.update_credit_report(new_credit_report['id'], cur_credit_report)
    if not updated_credit_report:
        logger.error('更新积分报表失败')
        return False

    # 验证更新结果
    if updated_credit_report['available'] != 600:
        logger.error("更新积分报表失败, 可用积分不匹配")
        return False

    # 再次查询验证更新
    cur_credit_report = credit_report_sdk.query_credit_report(updated_credit_report['id'])
    if not cur_credit_report:
        logger.error('查询积分报表失败')
        return False
    if updated_credit_report['available'] != cur_credit_report['available']:
        logger.error("更新积分报表失败, 查询的可用积分不匹配")
        return False

    # 验证修改时间字段已更新
    if 'modifyTime' in updated_credit_report:
        if 'modifyTime' in new_credit_report:
            # 修改时间应该已更新
            if updated_credit_report['modifyTime'] <= new_credit_report['modifyTime']:
                logger.warning("修改时间字段可能未正确更新")
        else:
            # 新创建的记录可能没有modifyTime字段
            pass

    # 删除积分报表
    deleted_credit_report = credit_report_sdk.delete_credit_report(updated_credit_report['id'])
    if not deleted_credit_report:
        logger.error('删除积分报表失败')
        return False
    if deleted_credit_report['id'] != cur_credit_report['id']:
        logger.error('删除积分报表失败, 积分报表ID不匹配')
        return False

    return True