"""Application"""

import logging
from typing import Optional, Dict, Any, List
from session import session
from mock import common as mock

# 配置日志
logger = logging.getLogger(__name__)


class DatabaseDeclare:
    def __init__(self, id, db_server, db_name, username, password, char_set, max_conn_num):
        self.id = id
        self.db_server = db_server
        self.db_name = db_name
        self.username = username
        self.password = password
        self.char_set = char_set
        self.max_conn_num = max_conn_num

    def to_dict(self):
        return {
            "id": self.id,
            "dbServer": self.db_server,
            "dbName": self.db_name,
            "username": self.username,
            "password": self.password,
            "charSet": self.char_set,
            "maxConnNum": self.max_conn_num
        }


class ApplicationDeclare:
    def __init__(self, id, uuid, name, show_name, pkg_prefix, icon, catalog, domain, email, author, description, database, hosted_by, artifact, status):
        self.id = id
        self.uuid = uuid
        self.name = name
        self.show_name = show_name
        self.pkg_prefix = pkg_prefix
        self.icon = icon
        self.catalog = catalog
        self.domain = domain
        self.email = email
        self.author = author
        self.description = description
        self.database = database
        self.hosted_by = hosted_by
        self.artifact = artifact
        self.status = status

    def to_dict(self):
        return {
            "id": self.id,
            "uuid": self.uuid,
            "name": self.name,
            "showName": self.show_name,
            "pkgPrefix": self.pkg_prefix,
            "icon": self.icon,
            "catalog": self.catalog,
            "domain": self.domain,
            "email": self.email,
            "author": self.author,
            "description": self.description,
            "database": self.database.to_dict() if self.database else None,
            "hostedBy": self.hosted_by,
            "artifact": self.artifact,
            "status": self.status
        }


class Application:
    """Application"""

    def __init__(self, work_session: session.MagicSession) -> None:
        self.session = work_session

    def get_system_config(self) -> Optional[Dict[str, Any]]:
        """获取系统配置
        
        Returns:
            系统配置字典或None（失败时）
        """
        val = self.session.get('/core/system/config')
        if val is None or val.get('error') is not None:
            if val:
                logger.error('获取系统配置错误')
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('获取系统配置请求失败: 无响应')
            return None
        return val.get('config')

    def filter_application(self, param: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        """过滤应用
        
        Args:
            param: 过滤参数
            
        Returns:
            应用列表或None（失败时）
        """
        val = self.session.post('/core/applications', param)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('过滤应用错误')
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('过滤应用请求失败: 无响应')
            return None
        return val.get('values')

    def query_application(self, id: int) -> Optional[Dict[str, Any]]:
        """查询应用
        
        Args:
            id: 应用ID
            
        Returns:
            应用信息或None（失败时）
        """
        val = self.session.get('/core/applications/{0}'.format(id))
        if val is None or val.get('error') is not None:
            if val:
                logger.error('查询应用错误, ID: %s', id)
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('查询应用请求失败: 无响应, ID: %s', id)
            return None
        return val.get('value')

    def create_application(self, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """创建应用
        
        Args:
            param: 应用参数
            
        Returns:
            创建的应用信息或None（失败时）
        """
        val = self.session.post('/core/applications', param)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('创建应用错误, 应用: %s', param.get('name', '未知'))
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('创建应用请求失败: 无响应, 应用: %s', param.get('name', '未知'))
            return None
        return val.get('value')

    def update_application(self, id: int, param: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """更新应用
        
        Args:
            id: 应用ID
            param: 应用参数
            
        Returns:
            更新的应用信息或None（失败时）
        """
        val = self.session.put('/core/applications/{0}'.format(id), param)
        if val is None or val.get('error') is not None:
            if val:
                logger.error('更新应用错误, ID: %s', id)
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('更新应用请求失败: 无响应, ID: %s', id)
            return None
        return val.get('value')

    def destroy_application(self, id: int) -> Optional[Dict[str, Any]]:
        """销毁应用
        
        Args:
            id: 应用ID
            
        Returns:
            销毁的应用信息或None（失败时）
        """
        val = self.session.delete('/core/applications/{0}'.format(id))
        if val is None or val.get('error') is not None:
            if val:
                logger.error('销毁应用错误, ID: %s', id)
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('销毁应用请求失败: 无响应, ID: %s', id)
            return None
        return val.get('value')

    def start_application(self, id: int) -> Optional[Dict[str, Any]]:
        """启动应用
        
        Args:
            id: 应用ID
            
        Returns:
            启动的应用信息或None（失败时）
        """
        val = self.session.get('/core/applications/{0}/start'.format(id))
        if val is None or val.get('error') is not None:
            if val:
                logger.error('启动应用错误, ID: %s', id)
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('启动应用请求失败: 无响应, ID: %s', id)
            return None
        return val.get('value')

    def stop_application(self, id: int) -> Optional[Dict[str, Any]]:
        """停止应用
        
        Args:
            id: 应用ID
            
        Returns:
            停止的应用信息或None（失败时）
        """
        val = self.session.get('/core/applications/{0}/stop'.format(id))
        if val is None or val.get('error') is not None:
            if val:
                logger.error('停止应用错误, ID: %s', id)
                logger.error('错误代码: %s, 错误消息: %s', val['error']['code'], val['error']['message'])
            else:
                logger.error('停止应用请求失败: 无响应, ID: %s', id)
            return None
        return val.get('value')


def mock_application_param() -> Dict[str, Any]:
    """模拟应用参数
    
    Returns:
        应用参数字典
    """
    database = DatabaseDeclare(
        id=1,
        db_server='mysql:3306',
        db_name='testdb',
        username='root',
        password='rootkit',
        char_set='utf8',
        max_conn_num=10
    )

    return ApplicationDeclare(
        id=1,
        uuid=mock.uuid(),
        name=mock.word(),
        show_name='Test Application',
        pkg_prefix='com.test',
        icon='icon.png',
        catalog='Test',
        domain=mock.url(),
        email=mock.email(),
        author='TestAuthor',
        description=mock.sentence(),
        database=database,
        hosted_by='magicMock',
        artifact='magicMock@v1.3.0',
        status=1
    ).to_dict()


def main(server_url: str, namespace: str) -> bool:
    """主函数
    
    Args:
        server_url: 服务器URL
        namespace: 命名空间
        
    Returns:
        成功返回True，失败返回False
    """
    work_session = session.MagicSession('{0}'.format(server_url), namespace)
    app = Application(work_session)

    # 获取系统配置
    config = app.get_system_config()
    if not config:
        logger.error('获取系统配置失败')
        return False

    # 创建新应用
    new_app = app.create_application(mock_application_param())
    if not new_app:
        logger.error('创建应用失败')
        return False

    # 查询应用
    queried_app = app.query_application(new_app['id'])
    if not queried_app:
        logger.error('查询应用失败')
        return False

    # 更新应用
    queried_app['description'] = mock.sentence()
    updated_app = app.update_application(queried_app['id'], queried_app)
    if not updated_app:
        logger.error('更新应用失败')
        return False

    # 启动应用
    started_app = app.start_application(updated_app['id'])
    if not started_app:
        logger.error('启动应用失败')
        return False

    # 停止应用
    stopped_app = app.stop_application(updated_app['id'])
    if not stopped_app:
        logger.error('停止应用失败')
        return False

    # 过滤应用
    filter_value = {
        'name': updated_app['name'],
        'uuid': updated_app['uuid'],
    }
    app_list = app.filter_application(filter_value)
    if not app_list or len(app_list) != 1:
        logger.error('过滤应用失败')
        return False

    # 销毁应用
    destroyed_app = app.destroy_application(updated_app['id'])
    if not destroyed_app:
        logger.error('销毁应用失败')
        return False

    logger.info('所有应用操作测试通过')
    return True


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="运行应用测试")
    parser.add_argument("--server_url", type=str, required=True, help="服务器URL")
    parser.add_argument("--namespace", type=str, required=True, help="命名空间")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    success = main(args.server_url, args.namespace)
    exit(0 if success else 1)