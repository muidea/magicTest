"""Block"""

import logging
from typing import Optional, Dict, Any, List
from session import session
from mock import common as mock

# 配置日志
logger = logging.getLogger(__name__)


class Block:
    """Block"""

    def __init__(self, work_session: session.MagicSession) -> None:
        self.session = work_session

    def filter_block(self, param: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """过滤区块
        
        Args:
            param: 过滤参数
            
        Returns:
            区块列表或None（失败时）
        """
        val = self.session.post('/core/blocks', param)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('过滤区块错误')
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('过滤区块请求失败: 无响应')
            return None
        return val.get('values')

    def query_block(self, id: str) -> Optional[Dict[str, Any]]:
        """查询区块
        
        Args:
            id: 区块ID
            
        Returns:
            区块信息或None（失败时）
        """
        val = self.session.get('/core/blocks/{0}'.format(id))
        if val is None or val.get('error') is not None:
            if val:
                logger.error('查询区块错误, ID: %s', id)
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('查询区块请求失败: 无响应, ID: %s', id)
            return None
        return val.get('value')

    def create_block(self, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """创建区块
        
        Args:
            param: 区块参数
            
        Returns:
            创建的区块信息或None（失败时）
        """
        val = self.session.post('/core/blocks', param)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('创建区块错误, 区块: %s', param.get('name', '未知'))
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('创建区块请求失败: 无响应, 区块: %s', param.get('name', '未知'))
            return None
        return val.get('value')

    def update_block(self, id: str, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """更新区块
        
        Args:
            id: 区块ID
            param: 区块参数
            
        Returns:
            更新的区块信息或None（失败时）
        """
        val = self.session.put('/core/blocks/{0}'.format(id), param)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('更新区块错误, ID: %s', id)
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('更新区块请求失败: 无响应, ID: %s', id)
            return None
        return val.get('value')

    def destroy_block(self, id: str) -> Optional[Dict[str, Any]]:
        """销毁区块
        
        Args:
            id: 区块ID
            
        Returns:
            销毁的区块信息或None（失败时）
        """
        val = self.session.delete('/core/blocks/{0}'.format(id))
        if val is None or val.get('error') is not None:
            if val:
                logger.error('销毁区块错误, ID: %s', id)
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('销毁区块请求失败: 无响应, ID: %s', id)
            return None
        return val.get('value')


def mock_block_param() -> Dict[str, Any]:
    """模拟区块参数
    
    Returns:
        区块参数字典
    """
    return {
        'name': mock.word(),
        'scope': mock.word(),
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
    block_instance = Block(work_session)

    # 创建区块
    block001 = mock_block_param()
    new_block10 = block_instance.create_block(block001)
    if not new_block10:
        logger.error('创建区块失败')
        return False

    # 更新区块
    new_block10['scope'] = mock.word()
    new_block11 = block_instance.update_block(new_block10['id'], new_block10)
    if not new_block11 or new_block11['scope'] != new_block10['scope']:
        logger.error('更新区块失败')
        return False

    # 创建第二个区块
    block002 = mock_block_param()
    new_block20 = block_instance.create_block(block002)
    if not new_block20:
        logger.error('创建第二个区块失败')
        return False

    # 过滤区块
    block_filter = {
        'params': {
            'items': {
                "name": '{0}|='.format(block002['name'])
            }
        }
    }
    block_list = block_instance.filter_block(block_filter)
    if not block_list or len(block_list) != 1:
        logger.error('过滤区块失败')
        return False

    # 查询区块
    queried_block = block_instance.query_block(new_block10['id'])
    if not queried_block:
        logger.error('查询区块失败')
        return False

    # 销毁区块
    deleted_block1 = block_instance.destroy_block(new_block10['id'])
    if not deleted_block1:
        logger.error('销毁区块失败')
        return False

    deleted_block2 = block_instance.destroy_block(new_block20['id'])
    if not deleted_block2:
        logger.error('销毁第二个区块失败')
        return False

    logger.info('所有区块操作测试通过')
    return True


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="运行区块测试")
    parser.add_argument("--server_url", type=str, required=True, help="服务器URL")
    parser.add_argument("--namespace", type=str, required=True, help="命名空间")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    success = main(args.server_url, args.namespace)
    exit(0 if success else 1)
