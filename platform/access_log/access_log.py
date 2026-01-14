"""Access Log"""

import logging
from typing import Optional, Dict, Any, List
from session import session
from mock import common as mock

# 配置日志
logger = logging.getLogger(__name__)


class AccessLog:
    """Access Log"""

    def __init__(self, work_session: session.MagicSession) -> None:
        self.session = work_session

    def filter_access_log(self, param: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """过滤访问日志
        
        Args:
            param: 过滤参数
            
        Returns:
            访问日志列表或None（失败时）
        """
        val = self.session.post('/core/accesslog/filter/', param)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('过滤访问日志错误')
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('过滤访问日志请求失败: 无响应')
            return None
        return val.get('values')

    def write_access_log(self, param: Dict[str, Any]) -> bool:
        """写入访问日志
        
        Args:
            param: 日志参数
            
        Returns:
            成功返回True，失败返回False
        """
        val = self.session.post('/core/accesslog/write/', param)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('写入访问日志错误')
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('写入访问日志请求失败: 无响应')
            return False
        return True


def mock_access_log_param() -> Dict[str, Any]:
    """模拟访问日志参数
    
    Returns:
        访问日志参数字典
    """
    return {
        'timestamp': mock.time(),
        'clientIP': mock.ip(),
        'userAgent': mock.sentence(),
        'method': mock.choice(['GET', 'POST', 'PUT', 'DELETE']),
        'path': mock.url(),
        'statusCode': mock.int(200, 500),
        'responseTime': mock.int(1, 1000),
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
    access_log = AccessLog(work_session)

    # 写入访问日志
    log_param = mock_access_log_param()
    if not access_log.write_access_log(log_param):
        logger.error('写入访问日志失败')
        return False

    # 过滤访问日志
    filter_param = {
        'params': {
            'items': {
                'clientIP': '{0}|='.format(log_param['clientIP'])
            }
        }
    }
    log_list = access_log.filter_access_log(filter_param)
    if not log_list or len(log_list) == 0:
        logger.error('过滤访问日志失败')
        return False

    logger.info('所有访问日志操作测试通过')
    return True


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="运行访问日志测试")
    parser.add_argument("--server_url", type=str, required=True, help="服务器URL")
    parser.add_argument("--namespace", type=str, required=True, help="命名空间")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    success = main(args.server_url, args.namespace)
    exit(0 if success else 1)