"""Totalizator"""

import logging
from typing import Optional, Dict, Any, List
from session import session
from mock import common as mock

# 配置日志
logger = logging.getLogger(__name__)


class Totalizator:
    """Totalizator"""

    def __init__(self, work_session: session.MagicSession) -> None:
        self.session = work_session

    def filter_totalizator(self, param: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """过滤总计器
        
        Args:
            param: 过滤参数
            
        Returns:
            总计器列表或None（失败时）
        """
        val = self.session.post('/core/totalizator/filter/', param)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('过滤总计器错误')
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('过滤总计器请求失败: 无响应')
            return None
        return val.get('values')

    def query_totalizator_summary(self, param: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """查询总计器摘要
        
        Args:
            param: 摘要参数
            
        Returns:
            摘要列表或None（失败时）
        """
        val = self.session.post('/core/totalizator/summary/', param)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('查询总计器摘要错误')
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('查询总计器摘要请求失败: 无响应')
            return None
        return val.get('summary')

    def register_totalizator(self, param: Dict[str, Any]) -> bool:
        """注册总计器
        
        Args:
            param: 注册参数
            
        Returns:
            成功返回True，失败返回False
        """
        val = self.session.post('/core/totalizator/register/', param)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('注册总计器错误')
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('注册总计器请求失败: 无响应')
            return False
        return True

    def unregister_totalizator(self, param: Dict[str, Any]) -> bool:
        """取消注册总计器
        
        Args:
            param: 取消注册参数
            
        Returns:
            成功返回True，失败返回False
        """
        val = self.session.post('/core/totalizator/unregister/', param)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('取消注册总计器错误')
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('取消注册总计器请求失败: 无响应')
            return False
        return True

    def refresh_totalizator(self, param: Dict[str, Any]) -> bool:
        """刷新总计器
        
        Args:
            param: 刷新参数
            
        Returns:
            成功返回True，失败返回False
        """
        val = self.session.post('/core/totalizator/refresh/', param)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('刷新总计器错误')
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('刷新总计器请求失败: 无响应')
            return False
        return True


def mock_totalizator_param() -> Dict[str, Any]:
    """模拟总计器参数
    
    Returns:
        总计器参数字典
    """
    return {
        'name': mock.word(),
        'scope': mock.word(),
        'metric': mock.word(),
        'threshold': mock.int(1, 100),
    }


def mock_totalizator_summary_param() -> Dict[str, Any]:
    """模拟总计器摘要参数
    
    Returns:
        摘要参数字典
    """
    return {
        'startTime': mock.time(),
        'endTime': mock.time(),
        'interval': 'hour',
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
    totalizator = Totalizator(work_session)

    # 注册总计器
    reg_param = mock_totalizator_param()
    if not totalizator.register_totalizator(reg_param):
        logger.error('注册总计器失败')
        return False

    # 过滤总计器
    filter_param = {
        'params': {
            'items': {
                'name': '{0}|='.format(reg_param['name'])
            }
        }
    }
    totalizator_list = totalizator.filter_totalizator(filter_param)
    if not totalizator_list or len(totalizator_list) == 0:
        logger.error('过滤总计器失败')
        return False

    # 查询摘要
    summary_param = mock_totalizator_summary_param()
    summary = totalizator.query_totalizator_summary(summary_param)
    if summary is None:
        logger.error('查询总计器摘要失败')
        return False

    # 刷新总计器
    refresh_param = {
        'name': reg_param['name'],
        'metric': reg_param['metric'],
        'value': mock.int(1, 100),
    }
    if not totalizator.refresh_totalizator(refresh_param):
        logger.error('刷新总计器失败')
        return False

    # 取消注册总计器
    if not totalizator.unregister_totalizator(reg_param):
        logger.error('取消注册总计器失败')
        return False

    logger.info('所有总计器操作测试通过')
    return True


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="运行总计器测试")
    parser.add_argument("--server_url", type=str, required=True, help="服务器URL")
    parser.add_argument("--namespace", type=str, required=True, help="命名空间")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    success = main(args.server_url, args.namespace)
    exit(0 if success else 1)