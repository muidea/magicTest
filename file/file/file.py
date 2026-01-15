"""File client implementation based on magicFile/pkg/client/client.go"""

import os
import logging
from typing import Optional, Dict, Any, List, Union
from session import session
from cas import cas
from mock import common

# 配置日志
logger = logging.getLogger(__name__)

# 常量定义 (从 magicFile/pkg/common/const.go 和 file.go 提取)
API_VERSION = "/api/v1"
KEY_NAME_TAG = "key-name"
FILE_SOURCE_TAG = "fileSource"
FILE_PATH_TAG = "filePath"
FILE_TOKEN_TAG = "fileToken"
FILE_NAME_TAG = "fileName"
FILE_SCOPE_TAG = "fileScope"

# API 端点 (从 magicFile/pkg/common/file.go 提取)
UPLOAD_FILE_URL = "/static/"
DOWNLOAD_FILE_URL = "/static/"
UPLOAD_FILE_STREAM_URL = "/files/stream/"
VIEW_FILE_URL = "/files/view/"
UPDATE_FILE_URL = "/files/:id"
DELETE_FILE_URL = "/files/:id"
QUERY_FILE_URL = "/files/:id"
EXPLORER_FILE_URL = "/files/"
COMMIT_FILE_URL = "/files/commit/:id"

# 文件项标签
FILE_ITEM = "fileItem"


class Client:
    """File client matching Go client interface"""
    
    def __init__(self, server_url: str, work_session: Optional[session.MagicSession] = None):
        """初始化客户端
        
        Args:
            server_url: 服务器基础URL
            work_session: 可选的工作会话，如果提供则复用其认证状态
        """
        if work_session is not None:
            # 复用现有会话的认证状态
            self.base_client = work_session
        else:
            self.base_client = session.MagicSession(server_url)
        self.file_source = ""
        self.file_scope = ""
        self._assign_namespace = ""
    
    def bind_source(self, source: str) -> None:
        """绑定文件来源"""
        self.file_source = source
    
    def unbind_source(self) -> None:
        """解绑文件来源"""
        self.file_source = ""
    
    def bind_scope(self, scope: str) -> None:
        """绑定文件范围"""
        self.file_scope = scope
    
    def unbind_scope(self) -> None:
        """解绑文件范围"""
        self.file_scope = ""
    
    def assign_namespace(self, namespace: str) -> None:
        """分配命名空间"""
        self._assign_namespace = namespace
    
    def _get_context_values(self) -> Dict[str, str]:
        """获取上下文值（用于请求头）"""
        vals = {}
        if self._assign_namespace:
            vals['X-Mp-Namespace'] = self._assign_namespace
        return vals
    
    def _build_url(self, endpoint: str) -> str:
        """构建完整URL"""
        # 如果端点以 /static/ 开头，不需要添加 API_VERSION
        if endpoint.startswith("/static/"):
            return endpoint
        # 否则添加 API_VERSION 前缀
        return API_VERSION + endpoint
    
    def _add_query_params(self, params: Dict[str, str]) -> Dict[str, str]:
        """添加文件来源和范围到查询参数"""
        if self.file_source:
            params[FILE_SOURCE_TAG] = self.file_source
        if self.file_scope:
            params[FILE_SCOPE_TAG] = self.file_scope
        return params
    
    def upload_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        """上传文件（对应 UploadFile）
        
        将文件上传至文件服务，并以文件方式进行保存。
        
        参数说明（通过 Query 参数传递）：
        - source (fileSource): 必选，文件源，需通过 bind_source() 提前设置
        - scope (fileScope): 可选，作用域，未指定时文件为共享，需通过 bind_scope() 提前设置
        - path (filePath): 可选，存储路径，未指定时默认以年月日作为路径
        - name: 必选，文件名，自动从上传的文件字段获取
        - needCommit (needSubmit): 可选，是否需要 CommitFile，默认为 false
        
        Args:
            file_path: 本地文件路径
            
        Returns:
            上传结果字典，包含 token 等信息，失败返回 None
        """
        params = {
            KEY_NAME_TAG: FILE_ITEM
        }
        self._add_query_params(params)
        
        url = self._build_url(UPLOAD_FILE_URL)
        
        try:
            with open(file_path, 'rb') as f:
                files = {FILE_ITEM: f}
                result = self.base_client.upload(url, files=files, params=params)
                
                # 处理响应：可能是 response 对象或解析后的 JSON
                if hasattr(result, 'json'):
                    # 如果是 response 对象，解析 JSON
                    try:
                        json_result = result.json()
                        if json_result and json_result.get('error') is None:
                            return json_result.get('value')
                        else:
                            error_msg = json_result.get('reason', '未知错误') if json_result else '未知错误'
                            logger.error('上传文件失败: %s', error_msg)
                            return None
                    except Exception as e:
                        logger.error('解析上传响应失败: %s', str(e))
                        return None
                elif isinstance(result, dict):
                    # 已经是解析后的 JSON
                    if result and result.get('error') is None:
                        return result.get('value')
                    else:
                        error_msg = result.get('reason', '未知错误') if result else '未知错误'
                        logger.error('上传文件失败: %s', error_msg)
                        return None
                else:
                    logger.error('上传文件返回未知类型: %s', type(result))
                    return None
        except Exception as e:
            logger.error('上传文件异常: %s', str(e))
            return None
    
    def upload_stream(self, dst_path: str, dst_name: str, byte_val: bytes) -> Optional[str]:
        """上传文件流（对应 UploadStream）
        
        将字节流上传至文件服务，并以文件方式进行保存。
        
        参数说明（通过 Query 参数传递）：
        - source (fileSource): 必选，文件源，需通过 bind_source() 提前设置
        - scope (fileScope): 可选，作用域，未指定时文件为共享，需通过 bind_scope() 提前设置
        - path (filePath): 可选，存储路径，未指定时默认以年月日作为路径
        - name (fileName): 必选，文件名
        
        Args:
            dst_path: 目标路径（对应 filePath）
            dst_name: 目标文件名（对应 fileName）
            byte_val: 文件内容字节
            
        Returns:
            文件token，失败返回 None
        """
        params = {
            KEY_NAME_TAG: FILE_ITEM,
            FILE_PATH_TAG: dst_path,
            FILE_NAME_TAG: dst_name
        }
        self._add_query_params(params)
        
        url = self._build_url(UPLOAD_FILE_STREAM_URL)
        
        # 由于 session 模块没有直接支持流上传，我们使用 multipart/form-data 上传
        # 这里简化实现：将字节作为文件上传
        try:
            # 创建一个临时文件
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, suffix='.tmp') as tmp:
                tmp.write(byte_val)
                tmp_path = tmp.name
            
            try:
                with open(tmp_path, 'rb') as f:
                    files = {FILE_ITEM: f}
                    result = self.base_client.upload(url, files=files, params=params)
                    
                    # 处理响应：可能是 response 对象或解析后的 JSON
                    if hasattr(result, 'json'):
                        # 如果是 response 对象，解析 JSON
                        try:
                            json_result = result.json()
                            # 检查是否是字符串（直接返回的token）
                            if isinstance(json_result, str):
                                return json_result
                            # 检查是否是字典
                            elif isinstance(json_result, dict):
                                if json_result.get('error') is None:
                                    value = json_result.get('value')
                                    # value 可能是字符串（直接是token）或字典（包含token字段）
                                    if isinstance(value, dict):
                                        token = value.get('token')
                                        if not token:
                                            token = value  # 如果value不是字典，可能是其他类型
                                    else:
                                        token = value  # 直接是token字符串
                                    return token
                                else:
                                    error_msg = json_result.get('reason', '未知错误') if json_result else '未知错误'
                                    logger.error('上传文件流失败: %s', error_msg)
                                    return None
                            else:
                                logger.error('上传文件流返回未知JSON类型: %s', type(json_result))
                                return None
                        except Exception as e:
                            logger.error('解析上传流响应失败: %s', str(e))
                            return None
                    elif isinstance(result, dict):
                        # 已经是解析后的 JSON
                        if result and result.get('error') is None:
                            value = result.get('value')
                            # value 可能是字符串（直接是token）或字典（包含token字段）
                            if isinstance(value, dict):
                                token = value.get('token')
                                if not token:
                                    token = value  # 如果value不是字典，可能是其他类型
                            else:
                                token = value  # 直接是token字符串
                            return token
                        else:
                            error_msg = result.get('reason', '未知错误') if result else '未知错误'
                            logger.error('上传文件流失败: %s', error_msg)
                            return None
                    elif isinstance(result, str):
                        # 直接返回的token字符串
                        return result
                    else:
                        logger.error('上传文件流返回未知类型: %s', type(result))
                        return None
            finally:
                os.unlink(tmp_path)
        except Exception as e:
            logger.error('上传文件流异常: %s', str(e))
            return None
    
    def download_file(self, file_token: str, file_path: str) -> Optional[str]:
        """下载文件（通过 token 访问文件）
        
        通过文件 token 下载文件到本地路径。
        
        参数说明（通过 Query 参数传递）：
        - token (fileToken): 必选，文件访问 token
        - scope (fileScope): 可选，访问范围，未指定 scope 时只允许下载共享文件
        - source (fileSource): 可选，文件源，需通过 bind_source() 提前设置
        
        Args:
            file_token: 文件访问 token
            file_path: 本地保存路径
            
        Returns:
            保存的文件路径，失败返回 None
        """
        params = {
            FILE_TOKEN_TAG: file_token
        }
        self._add_query_params(params)
        
        url = self._build_url(DOWNLOAD_FILE_URL)
        
        result = self.base_client.download(url, file_path, params)
        if isinstance(result, str) and os.path.exists(result):
            return result
        else:
            logger.error('下载文件失败')
            return None
    
    def view_file(self, file_token: str) -> Optional[Dict[str, Any]]:
        """查看文件信息（通过 fileToken 查看文件信息）
        
        通过文件 token 查看文件的详细信息。
        
        参数说明（通过 Query 参数传递）：
        - fileToken: 必选，文件访问 token
        - source (fileSource): 必选，文件源，需通过 bind_source() 提前设置
        
        Args:
            file_token: 文件访问 token
            
        Returns:
            文件信息字典，失败返回 None
        """
        params = {
            FILE_TOKEN_TAG: file_token
        }
        if self.file_source:
            params[FILE_SOURCE_TAG] = self.file_source
        
        url = self._build_url(VIEW_FILE_URL)
        
        result = self.base_client.get(url, params)
        if result and result.get('error') is None:
            return result.get('value')
        else:
            error_msg = result.get('reason', '未知错误') if result else '未知错误'
            logger.error('查看文件失败: %s', error_msg)
            return None
    
    def update_file(self, file_id: int, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """更新文件（对应 UpdateFile）
        
        更新文件信息（名称、描述、TTL、标签等）。
        
        参数说明：
        - id: 必选，文件 ID（通过 URL 路径传递）
        - source (fileSource): 必选，文件源，需通过 bind_source() 提前设置
        - 其他参数: 可选，通过 JSON Body 传递更新字段（如 name, description, ttl, tags 等）
        
        Args:
            file_id: 文件ID
            param: 文件参数（JSON Body 内容）
            
        Returns:
            更新后的文件信息，失败返回 None
        """
        query_params = {}
        if self.file_source:
            query_params[FILE_SOURCE_TAG] = self.file_source
        
        url = self._build_url(UPDATE_FILE_URL.replace(":id", str(file_id)))
        
        # 将查询参数添加到 URL
        if query_params:
            import urllib.parse
            query_string = urllib.parse.urlencode(query_params)
            url = f"{url}?{query_string}"
        
        result = self.base_client.put(url, param)
        if result and result.get('error') is None:
            return result.get('value')
        else:
            error_msg = result.get('reason', '未知错误') if result else '未知错误'
            logger.error('更新文件失败: %s', error_msg)
            return None
    
    def delete_file(self, file_id: int) -> Optional[Dict[str, Any]]:
        """删除文件（对应 DeleteFile）
        
        删除指定文件。
        
        参数说明：
        - id: 必选，文件 ID（通过 URL 路径传递）
        - source (fileSource): 必选，文件源，需通过 bind_source() 提前设置
        
        Args:
            file_id: 文件ID
            
        Returns:
            删除的文件信息，失败返回 None
        """
        query_params = {}
        if self.file_source:
            query_params[FILE_SOURCE_TAG] = self.file_source
        
        url = self._build_url(DELETE_FILE_URL.replace(":id", str(file_id)))
        
        # 将查询参数添加到 URL
        if query_params:
            import urllib.parse
            query_string = urllib.parse.urlencode(query_params)
            url = f"{url}?{query_string}"
        
        result = self.base_client.delete(url, query_params)
        if result and result.get('error') is None:
            return result.get('value')
        else:
            error_msg = result.get('reason', '未知错误') if result else '未知错误'
            logger.error('删除文件失败: %s', error_msg)
            return None
    
    def query_file(self, file_id: int) -> Optional[Dict[str, Any]]:
        """查询文件（对应 QueryFile）
        
        查看文件信息。
        
        参数说明：
        - id: 必选，文件 ID（通过 URL 路径传递）
        - source (fileSource): 必选，文件源，需通过 bind_source() 提前设置
        
        Args:
            file_id: 文件ID
            
        Returns:
            文件信息，失败返回 None
        """
        query_params = {}
        if self.file_source:
            query_params[FILE_SOURCE_TAG] = self.file_source
        
        url = self._build_url(QUERY_FILE_URL.replace(":id", str(file_id)))
        
        # 将查询参数添加到 URL
        if query_params:
            import urllib.parse
            query_string = urllib.parse.urlencode(query_params)
            url = f"{url}?{query_string}"
        
        result = self.base_client.get(url, query_params)
        if result and result.get('error') is None:
            return result.get('value')
        else:
            error_msg = result.get('reason', '未知错误') if result else '未知错误'
            logger.error('查询文件失败: %s', error_msg)
            return None
    
    def commit_file(self, file_id: int, ttl: int = 0) -> Optional[Dict[str, Any]]:
        """提交文件（对应 CommitFile）
        
        确认文件上传完成，以便将临时文件转为正式文件。
        该功能配合 UploadFile 使用，在 UploadFile 时可通过 needCommit 参数决定是否需要进行 CommitFile 操作。
        UploadStream 不支持 CommitFile。
        
        参数说明：
        - id: 必选，文件 ID（通过 URL 路径传递）
        - source (fileSource): 必选，文件源，需通过 bind_source() 提前设置
        - ttl: 可选，有效期（单位：秒），通过 JSON Body 传递
        
        Args:
            file_id: 文件ID
            ttl: 有效期（单位：秒），0 表示永久
            
        Returns:
             提交后的文件信息，失败返回 None
        """
        query_params = {}
        if self.file_source:
            query_params[FILE_SOURCE_TAG] = self.file_source
        
        url = self._build_url(COMMIT_FILE_URL.replace(":id", str(file_id)))
        
        # 将查询参数添加到 URL
        if query_params:
            import urllib.parse
            query_string = urllib.parse.urlencode(query_params)
            url = f"{url}?{query_string}"
        
        # 根据 Go 客户端，参数名是 TTL（大写）
        param = {"TTL": ttl}
        result = self.base_client.put(url, param)
        if result and result.get('error') is None:
            return result.get('value')
        else:
            error_msg = result.get('reason', '未知错误') if result else '未知错误'
            logger.error('提交文件失败: %s', error_msg)
            return None
    
    def filter_file(self, params: Optional[Dict[str, Any]] = None) -> Optional[List[Dict[str, Any]]]:
        """过滤/浏览文件（对应 ExplorerFile）
        
        逐级浏览对应 namespace 下的文件列表和所有共享的文件列表。
        
        参数说明（通过 Query 参数传递）：
        - source (fileSource): 可选，文件源，需通过 bind_source() 提前设置
        - scope (fileScope): 可选，浏览范围，未指定 scope 时只允许浏览共享文件
        - path (filePath): 可选，浏览路径
        
        Args:
            params: 过滤参数（可包含 source, scope, path 等）
            
        Returns:
            文件列表，失败返回 None
        """
        if not params:
            params = {}
        
        self._add_query_params(params)
        
        url = self._build_url(EXPLORER_FILE_URL)
        
        result = self.base_client.get(url, params)
        if result and result.get('error') is None:
            # 服务器返回的是 {"error": null, "value": {"files": [...], "dirs": [...]}}
            value = result.get('value', {})
            if isinstance(value, dict):
                return value.get('files', [])
            return []
        else:
            error_msg = result.get('reason', '未知错误') if result else '未知错误'
            logger.error('过滤文件失败: %s', error_msg)
            return None


# 向后兼容的 File 类（包装 Client）
class File:
    """向后兼容的 File 类"""
    
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
        # 创建内部客户端，复用工作会话的认证状态
        self.client = Client(work_session.base_url, work_session)
        self.client.bind_scope(scope)
        self.client.bind_source(source)
        # 设置命名空间
        if work_session.namespace:
            self.client.assign_namespace(work_session.namespace)
    
    def filter_file(self, params: Optional[Dict[str, Any]] = None) -> Optional[List[Dict[str, Any]]]:
        """过滤文件"""
        return self.client.filter_file(params)
    
    def query_file(self, file_id: int, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """查询文件"""
        return self.client.query_file(file_id)
    
    def delete_file(self, file_id: int, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """删除文件"""
        return self.client.delete_file(file_id)
    
    def view_file(self, file_token: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """查看文件"""
        return self.client.view_file(file_token)
    
    def upload_file(self, file_path: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """上传文件"""
        return self.client.upload_file(file_path)
    
    def download_file(self, file_token: str, file_path: str, params: Optional[Dict[str, Any]] = None) -> Optional[Any]:
        """下载文件"""
        return self.client.download_file(file_token, file_path)
    
    def update_file(self, file_id: int, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """更新文件"""
        return self.client.update_file(file_id, param)
    
    def commit_file(self, file_id: int, ttl: int) -> Optional[Dict[str, Any]]:
        """提交文件（设置有效期）"""
        return self.client.commit_file(file_id, ttl)
    
    def upload_stream(self, dst_path: str, dst_name: str, byte_val: bytes) -> Optional[str]:
        """上传文件流"""
        return self.client.upload_stream(dst_path, dst_name, byte_val)


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
    # CAS 登录
    cas_session = cas.Cas(work_session)
    if not cas_session.login('administrator', 'administrator'):
        logger.error('CAS登录失败')
        return False
    
    work_session.bind_token(cas_session.get_session_token())
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

    # 更新文件描述
    new_description = common.sentence()
    update_param = {
        'description': new_description
    }
    updated_file = app.update_file(new_file['id'], update_param)
    if not updated_file:
        logger.error('更新文件失败')
        return False

    # 再次查询验证更新
    cur_file = app.query_file(new_file['id'])
    if not cur_file:
        logger.error('查询文件失败')
        return False
    if cur_file.get('description') != new_description:
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
