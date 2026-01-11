"""File"""

import os
import logging
from typing import Optional, Dict, Any, List
from session import session
from mock import common

# 配置日志
logger = logging.getLogger(__name__)


class File:
    """File"""

    def __init__(self, scope: str, source: str, path: Optional[str], work_session: session.MagicSession) -> None:
        """初始化File类
        
        Args:
            scope: 文件范围
            source: 文件来源
            path: 文件路径（可选）
            work_session: 工作会话
        """
        self.scope = scope
        self.source = source
        self.path = path
        self.session = work_session

    def filter_file(self, params: Optional[Dict[str, Any]] = None) -> Optional[List[Dict[str, Any]]]:
        """过滤文件
        
        Args:
            params: 过滤参数（可选）
            
        Returns:
            文件列表或None（失败时）
        """
        if self.source:
            if not params:
                params = {'fileSource': self.source}
            else:
                params['fileSource'] = self.source
        if self.scope:
            if not params:
                params = {'fileScope': self.scope}
            else:
                params['fileScope'] = self.scope

        val = self.session.get('/api/v1/files/', params)
        if val is None or val.get('errorCode') != 0:
            if val:
                logger.error('过滤文件错误')
                logger.error('错误原因: %s', val.get('reason', '未知'))
            else:
                logger.error('过滤文件请求失败: 无响应')
            return None
        return val.get('values')

    def query_file(self, file_id: int, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """查询文件
        
        Args:
            file_id: 文件ID
            params: 查询参数（可选）
            
        Returns:
            文件信息或None（失败时）
        """
        if not params:
            params = {'fileSource': self.source}
        else:
            params['fileSource'] = self.source
        if self.scope:
            if not params:
                params = {'fileScope': self.scope}
            else:
                params['fileScope'] = self.scope

        val = self.session.get('/api/v1/files/{0}'.format(file_id), params)
        if val is None or val.get('errorCode') != 0:
            if val:
                logger.error('查询文件错误, ID: %s', file_id)
                logger.error('错误原因: %s', val.get('reason', '未知'))
            else:
                logger.error('查询文件请求失败: 无响应, ID: %s', file_id)
            return None
        return val.get('value')

    def delete_file(self, file_id: int, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """删除文件
        
        Args:
            file_id: 文件ID
            params: 删除参数（可选）
            
        Returns:
            删除的文件信息或None（失败时）
        """
        if not params:
            params = {'fileSource': self.source}
        else:
            params['fileSource'] = self.source
        if self.scope:
            if not params:
                params = {'fileScope': self.scope}
            else:
                params['fileScope'] = self.scope

        val = self.session.delete('/api/v1/files/{0}'.format(file_id), params)
        if val is None or val.get('errorCode') != 0:
            if val:
                logger.error('删除文件错误, ID: %s', file_id)
                logger.error('错误原因: %s', val.get('reason', '未知'))
            else:
                logger.error('删除文件请求失败: 无响应, ID: %s', file_id)
            return None
        return val.get('value')

    def view_file(self, file_token: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """查看文件
        
        Args:
            file_token: 文件令牌
            params: 查看参数（可选）
            
        Returns:
            文件信息或None（失败时）
        """
        if not params:
            params = {'fileSource': self.source}
        else:
            params['fileSource'] = self.source
        if self.scope:
            if not params:
                params = {'fileScope': self.scope}
            else:
                params['fileScope'] = self.scope
        if file_token:
            if not params:
                params = {'fileToken': file_token}
            else:
                params['fileToken'] = file_token
        val = self.session.get('/api/v1/static/file/view/', params)
        if val is None or val.get('errorCode') != 0:
            if val:
                logger.error('查看文件错误, Token: %s', file_token)
                logger.error('错误原因: %s', val.get('reason', '未知'))
            else:
                logger.error('查看文件请求失败: 无响应, Token: %s', file_token)
            return None
        return val.get('value')

    def upload_file(self, file_path: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """上传文件
        
        Args:
            file_path: 文件路径
            params: 上传参数（可选）
            
        Returns:
            上传的文件信息或None（失败时）
        """
        if not params:
            params = {'fileSource': self.source}
        else:
            params['fileSource'] = self.source
        if self.scope:
            if not params:
                params = {'fileScope': self.scope}
            else:
                params['fileScope'] = self.scope
        if self.path:
            if not params:
                params = {'filePath': self.path}
            else:
                params['filePath'] = self.path
        if not params:
            params = {'key-name': 'file'}
        else:
            params['key-name'] = 'file'

        try:
            with open(file_path, 'rb') as f:
                files = {'file': f}
                val = self.session.upload('/static/file/', files=files, params=params)
                if val is None or val.get('errorCode') != 0:
                    if val:
                        logger.error('上传文件错误, 路径: %s', file_path)
                        logger.error('错误原因: %s', val.get('reason', '未知'))
                    else:
                        logger.error('上传文件请求失败: 无响应, 路径: %s', file_path)
                    return None
                return val.get('value')
        except Exception as e:
            logger.error('上传文件异常, 路径: %s', file_path)
            logger.error('异常信息: %s', str(e))
            return None

    def download_file(self, file_token: str, file_path: str, params: Optional[Dict[str, Any]] = None) -> Optional[Any]:
        """下载文件
        
        Args:
            file_token: 文件令牌
            file_path: 保存的文件路径
            params: 下载参数（可选）
            
        Returns:
            下载结果或None（失败时）
        """
        if not params:
            params = {'fileSource': self.source}
        else:
            params['fileSource'] = self.source
        if self.scope:
            if not params:
                params = {'fileScope': self.scope}
            else:
                params['fileScope'] = self.scope
        if file_token:
            if not params:
                params = {'fileToken': file_token}
            else:
                params['fileToken'] = file_token

        val = self.session.download('/static/file/', file_path, params)
        if val is None:
            logger.error('下载文件失败, Token: %s, 保存路径: %s', file_token, file_path)
            return None
        return val


def mock_file_param(scope: str, source: str, path: Optional[str] = None) -> Dict[str, Any]:
    """模拟文件参数
    
    Args:
        scope: 文件范围
        source: 文件来源
        path: 文件路径（可选）
        
    Returns:
        文件参数字典
    """
    param = {
        'scope': scope,
        'source': source,
        'name': common.word() + '.txt',
        'description': common.sentence(),
        'size': common.int(100, 10000),
        'mimeType': 'text/plain'
    }
    if path:
        param['path'] = path
    return param


def main(server_url: str, namespace: str) -> bool:
    """主函数
    
    Args:
        server_url: 服务器URL
        namespace: 命名空间
        
    Returns:
        成功返回True，失败返回False
    """
    work_session = session.MagicSession('{0}'.format(server_url), namespace)
    app = File("test_scope", "test_source", None, work_session)
    
    # 创建测试文件
    test_file_path = "/tmp/test_file.txt"
    try:
        with open(test_file_path, 'w') as f:
            f.write("Test content for file upload")
    except Exception as e:
        logger.error('创建测试文件失败: %s', str(e))
        return False
    
    new_file = app.upload_file(test_file_path)
    if not new_file:
        logger.error('上传文件失败')
        return False
    
    # 清理测试文件
    try:
        os.remove(test_file_path)
    except:
        pass

    filter_value = {
        'scope': 'test_scope',
        'source': 'test_source',
    }

    file_list = app.filter_file(filter_value)
    if not file_list or len(file_list) != 1:
        logger.error('过滤文件失败')
        return False
    if file_list[0]['token'] != new_file['token']:
        logger.error('过滤文件失败, 文件不匹配')
        return False

    cur_file = app.query_file(new_file['id'])
    if not cur_file:
        logger.error('查询文件失败')
        return False

    cur_file["description"] = common.sentence()
    updated_file = app.upload_file(test_file_path, {'description': cur_file["description"]})
    if not updated_file:
        logger.error('更新文件失败')
        return False

    cur_file = app.query_file(new_file['id'])
    if not cur_file:
        logger.error('查询文件失败')
        return False
    if updated_file.get('description') != cur_file.get('description'):
        logger.error("更新文件失败, 描述不匹配")
        return False

    pre_file = app.view_file(new_file['token'])
    if not pre_file:
        logger.error('查看文件失败')
        return False

    new_file_path = "/tmp/downloaded_file.txt"
    file_val = app.download_file(new_file['token'], new_file_path)
    if not file_val:
        logger.error('下载文件失败')
        return False
    os.remove(new_file_path)

    old_file = app.delete_file(new_file['id'])
    if not old_file:
        logger.error('删除文件失败')
        return False
    if old_file['id'] != cur_file['id']:
        logger.error('删除文件失败, 文件ID不匹配')
        return False

    return True
