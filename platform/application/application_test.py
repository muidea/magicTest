"""Application 测试用例"""

import unittest
import warnings
import logging
from session import session
from application import application
from mock import common as mock

# 配置日志
logger = logging.getLogger(__name__)


class ApplicationTestCase(unittest.TestCase):
    """Application 测试用例类"""
    
    server_url = 'https://autotest.remote.vpc/api/v1'
    namespace = ''
    
    @classmethod
    def setUpClass(cls):
        """测试类初始化"""
        warnings.simplefilter('ignore', ResourceWarning)
        cls.work_session = session.MagicSession(cls.server_url, cls.namespace)
        cls.app_instance = application.Application(cls.work_session)
    
    def setUp(self):
        """每个测试用例前的准备"""
        # 记录测试创建的应用程序ID以便清理
        self.created_app_ids = []
    
    def tearDown(self):
        """每个测试用例后的清理"""
        # 清理所有测试创建的应用程序
        for app_id in self.created_app_ids:
            try:
                self.app_instance.delete_application(app_id)
            except Exception as e:
                logger.warning(f"清理应用程序 {app_id} 失败: {e}")
        
        self.created_app_ids.clear()
    
    def test_create_application(self):
        """测试创建应用程序"""
        app_param = application.mock_application_param()
        new_app = self.app_instance.create_application(app_param)
        self.assertIsNotNone(new_app, "创建应用程序失败")
        
        # 验证应用程序信息完整性
        required_fields = ['id', 'uuid', 'name', 'showName', 'pkgPrefix', 'domain', 'email']
        for field in required_fields:
            self.assertIn(field, new_app, f"缺少字段: {field}")
        
        # 记录创建的应用程序ID以便清理
        if new_app and 'id' in new_app:
            self.created_app_ids.append(new_app['id'])
    
    def test_query_application(self):
        """测试查询应用程序"""
        # 先创建应用程序
        app_param = application.mock_application_param()
        new_app = self.app_instance.create_application(app_param)
        self.assertIsNotNone(new_app, "创建应用程序失败")
        
        if new_app and 'id' in new_app:
            self.created_app_ids.append(new_app['id'])
        
        # 查询应用程序
        queried_app = self.app_instance.query_application(new_app['id'])
        self.assertIsNotNone(queried_app, "查询应用程序失败")
        self.assertEqual(queried_app['id'], new_app['id'], "应用程序ID不匹配")
        self.assertEqual(queried_app['name'], new_app['name'], "应用程序名不匹配")
    
    def test_update_application(self):
        """测试更新应用程序"""
        # 先创建应用程序
        app_param = application.mock_application_param()
        new_app = self.app_instance.create_application(app_param)
        self.assertIsNotNone(new_app, "创建应用程序失败")
        
        if new_app and 'id' in new_app:
            self.created_app_ids.append(new_app['id'])
        
        # 更新应用程序
        update_param = new_app.copy()
        update_param['description'] = "更新后的描述"
        
        updated_app = self.app_instance.update_application(update_param['id'], update_param)
        self.assertIsNotNone(updated_app, "更新应用程序失败")
        self.assertEqual(updated_app['description'], "更新后的描述", "描述更新失败")
    
    def test_filter_application(self):
        """测试过滤应用程序"""
        # 先创建应用程序
        app_param = application.mock_application_param()
        new_app = self.app_instance.create_application(app_param)
        self.assertIsNotNone(new_app, "创建应用程序失败")
        
        if new_app and 'id' in new_app:
            self.created_app_ids.append(new_app['id'])
        
        # 过滤应用程序
        filter_param = {
            'params': {
                'items': {
                    "name": '{0}|='.format(new_app['name'])
                }
            }
        }
        
        app_list = self.app_instance.filter_application(filter_param)
        self.assertIsNotNone(app_list, "过滤应用程序失败")
        self.assertGreater(len(app_list), 0, "过滤结果为空")
        
        # 验证新创建的应用程序在过滤结果中
        found = False
        for app_item in app_list:
            if app_item['id'] == new_app['id']:
                found = True
                break
        self.assertTrue(found, "新创建的应用程序未在过滤结果中找到")
    
    def test_delete_application(self):
        """测试删除应用程序"""
        # 先创建应用程序
        app_param = application.mock_application_param()
        new_app = self.app_instance.create_application(app_param)
        self.assertIsNotNone(new_app, "创建应用程序失败")
        
        # 删除应用程序
        deleted_app = self.app_instance.delete_application(new_app['id'])
        self.assertIsNotNone(deleted_app, "删除应用程序失败")
        self.assertEqual(deleted_app['id'], new_app['id'], "删除的应用程序ID不匹配")
        
        # 验证应用程序已被删除（查询应该失败）
        queried_app = self.app_instance.query_application(new_app['id'])
        self.assertIsNone(queried_app, "已删除的应用程序查询应失败")
    
    def test_create_application_with_long_name(self):
        """测试创建超长名称应用程序（边界测试）"""
        app_param = application.mock_application_param()
        app_param['name'] = 'a' * 255  # 超长名称
        
        new_app = self.app_instance.create_application(app_param)
        if new_app is not None:
            self.assertIsInstance(new_app['name'], str, "应用程序名不是字符串")
            # 记录创建的应用程序ID以便清理
            if 'id' in new_app:
                self.created_app_ids.append(new_app['id'])
    
    def test_create_duplicate_application(self):
        """测试创建重复应用程序名（异常测试）"""
        app_param = application.mock_application_param()
        
        first_app = self.app_instance.create_application(app_param)
        self.assertIsNotNone(first_app, "第一次创建应用程序失败")
        
        # 记录第一次创建的应用程序ID以便清理
        if first_app and 'id' in first_app:
            self.created_app_ids.append(first_app['id'])
        
        # 第二次创建相同应用程序名应该失败
        second_app = self.app_instance.create_application(app_param)
        # 期望创建失败，返回None或错误响应
        self.assertIsNone(second_app, "重复应用程序名创建应失败")
    
    def test_create_application_with_invalid_email(self):
        """测试创建无效邮箱格式应用程序（异常测试）"""
        app_param = application.mock_application_param()
        app_param['email'] = 'invalid-email'
        
        new_app = self.app_instance.create_application(app_param)
        # 期望创建失败，返回None或错误响应
        self.assertIsNone(new_app, "无效邮箱格式创建应失败")
    
    def test_query_nonexistent_application(self):
        """测试查询不存在的应用程序（异常测试）"""
        nonexistent_app_id = 999999
        queried_app = self.app_instance.query_application(nonexistent_app_id)
        # 期望查询失败，返回None或错误响应
        self.assertIsNone(queried_app, "查询不存在的应用程序应失败")
    
    def test_delete_nonexistent_application(self):
        """测试删除不存在的应用程序（异常测试）"""
        nonexistent_app_id = 999999
        deleted_app = self.app_instance.delete_application(nonexistent_app_id)
        # 期望删除失败，返回None或错误响应
        self.assertIsNone(deleted_app, "删除不存在的应用程序应失败")
    
    def test_application_database_config(self):
        """测试应用程序数据库配置"""
        app_param = application.mock_application_param()
        new_app = self.app_instance.create_application(app_param)
        self.assertIsNotNone(new_app, "创建应用程序失败")
        
        if new_app and 'id' in new_app:
            self.created_app_ids.append(new_app['id'])
        
        # 验证数据库配置
        self.assertIn('database', new_app, "应用程序缺少数据库配置")
        if new_app['database'] is not None:
            db_fields = ['id', 'dbServer', 'dbName', 'username', 'charSet', 'maxConnNum']
            for field in db_fields:
                self.assertIn(field, new_app['database'], f"数据库配置缺少字段: {field}")


if __name__ == '__main__':
    unittest.main()