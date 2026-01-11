"""File 测试用例"""

import unittest
import warnings
import logging
import os
from session import session
from file import file

# 配置日志
logger = logging.getLogger(__name__)


class FileTestCase(unittest.TestCase):
    """File 测试用例类"""
    
    server_url = 'https://autotest.local.vpc/api/v1'
    namespace = ''
    
    @classmethod
    def setUpClass(cls):
        """测试类初始化"""
        warnings.simplefilter('ignore', ResourceWarning)
        cls.work_session = session.MagicSession(cls.server_url, cls.namespace)
        cls.file_app = file.File("test_scope", "test_source", None, cls.work_session)
    
    def setUp(self):
        """每个测试用例前的准备"""
        # 记录测试创建的文件ID以便清理
        self.created_file_ids = []
        self.created_file_tokens = []
        
        # 创建测试文件
        self.test_file_path = "./test_upload.txt"
        with open(self.test_file_path, "w") as f:
            f.write("测试文件内容")
    
    def tearDown(self):
        """每个测试用例后的清理"""
        # 清理所有测试创建的文件
        for file_id in self.created_file_ids:
            try:
                self.file_app.delete_file(file_id)
            except Exception as e:
                logger.warning(f"清理文件 {file_id} 失败: {e}")
        
        for file_token in self.created_file_tokens:
            try:
                # 如果有token清理方法，可以在这里调用
                pass
            except Exception as e:
                logger.warning(f"清理文件token {file_token} 失败: {e}")
        
        self.created_file_ids.clear()
        self.created_file_tokens.clear()
        
        # 删除测试文件
        if os.path.exists(self.test_file_path):
            os.remove(self.test_file_path)
    
    def test_upload_file(self):
        """测试文件上传"""
        new_file = self.file_app.upload_file(self.test_file_path)
        self.assertIsNotNone(new_file, "文件上传失败")
        
        # 验证文件信息完整性
        required_fields = ['id', 'token', 'name', 'size', 'type']
        for field in required_fields:
            self.assertIn(field, new_file, f"缺少字段: {field}")
        
        # 记录创建的文件ID和token以便清理
        if new_file and 'id' in new_file:
            self.created_file_ids.append(new_file['id'])
        if new_file and 'token' in new_file:
            self.created_file_tokens.append(new_file['token'])
    
    def test_query_file(self):
        """测试文件查询"""
        # 先上传文件
        new_file = self.file_app.upload_file(self.test_file_path)
        self.assertIsNotNone(new_file, "文件上传失败")
        
        if new_file and 'id' in new_file:
            self.created_file_ids.append(new_file['id'])
        
        # 查询文件
        queried_file = self.file_app.query_file(new_file['id'])
        self.assertIsNotNone(queried_file, "文件查询失败")
        self.assertEqual(queried_file['id'], new_file['id'], "文件ID不匹配")
        self.assertEqual(queried_file['name'], new_file['name'], "文件名不匹配")
    
    def test_view_file(self):
        """测试文件查看"""
        # 先上传文件
        new_file = self.file_app.upload_file(self.test_file_path)
        self.assertIsNotNone(new_file, "文件上传失败")
        
        if new_file and 'id' in new_file:
            self.created_file_ids.append(new_file['id'])
        if new_file and 'token' in new_file:
            self.created_file_tokens.append(new_file['token'])
        
        # 查看文件
        viewed_file = self.file_app.view_file(new_file['token'])
        self.assertIsNotNone(viewed_file, "文件查看失败")
        self.assertIn('path', viewed_file, "查看文件缺少path字段")
    
    def test_filter_file(self):
        """测试文件过滤"""
        # 先上传文件
        new_file = self.file_app.upload_file(self.test_file_path)
        self.assertIsNotNone(new_file, "文件上传失败")
        
        if new_file and 'id' in new_file:
            self.created_file_ids.append(new_file['id'])
        
        # 过滤文件
        file_list = self.file_app.filter_file()
        self.assertIsNotNone(file_list, "文件过滤失败")
        self.assertGreater(len(file_list), 0, "过滤结果为空")
        
        # 验证新上传的文件在过滤结果中
        found = False
        for file_item in file_list:
            if file_item['id'] == new_file['id']:
                found = True
                break
        self.assertTrue(found, "新上传的文件未在过滤结果中找到")
    
    def test_delete_file(self):
        """测试文件删除"""
        # 先上传文件
        new_file = self.file_app.upload_file(self.test_file_path)
        self.assertIsNotNone(new_file, "文件上传失败")
        
        # 删除文件
        deleted_file = self.file_app.delete_file(new_file['id'])
        self.assertIsNotNone(deleted_file, "文件删除失败")
        self.assertEqual(deleted_file['id'], new_file['id'], "删除的文件ID不匹配")
        
        # 验证文件已被删除（查询应该失败）
        queried_file = self.file_app.query_file(new_file['id'])
        self.assertIsNone(queried_file, "已删除的文件查询应失败")
    
    def test_upload_large_file(self):
        """测试大文件上传（边界测试）"""
        # 创建大文件
        large_file_path = "./test_large_upload.txt"
        with open(large_file_path, "w") as f:
            # 写入1MB数据
            f.write("X" * 1024 * 1024)
        
        try:
            new_file = self.file_app.upload_file(large_file_path)
            if new_file is not None:
                self.assertIsInstance(new_file['size'], int, "文件大小不是整数")
                # 记录创建的文件ID以便清理
                if 'id' in new_file:
                    self.created_file_ids.append(new_file['id'])
        finally:
            # 清理大文件
            if os.path.exists(large_file_path):
                os.remove(large_file_path)
    
    def test_upload_empty_file(self):
        """测试空文件上传"""
        empty_file_path = "./test_empty_upload.txt"
        with open(empty_file_path, "w") as f:
            pass  # 创建空文件
        
        try:
            new_file = self.file_app.upload_file(empty_file_path)
            if new_file is not None:
                self.assertEqual(new_file['size'], 0, "空文件大小应为0")
                # 记录创建的文件ID以便清理
                if 'id' in new_file:
                    self.created_file_ids.append(new_file['id'])
        finally:
            # 清理空文件
            if os.path.exists(empty_file_path):
                os.remove(empty_file_path)
    
    def test_query_nonexistent_file(self):
        """测试查询不存在的文件（异常测试）"""
        nonexistent_file_id = 999999
        queried_file = self.file_app.query_file(nonexistent_file_id)
        # 期望查询失败，返回None或错误响应
        self.assertIsNone(queried_file, "查询不存在的文件应失败")
    
    def test_delete_nonexistent_file(self):
        """测试删除不存在的文件（异常测试）"""
        nonexistent_file_id = 999999
        deleted_file = self.file_app.delete_file(nonexistent_file_id)
        # 期望删除失败，返回None或错误响应
        self.assertIsNone(deleted_file, "删除不存在的文件应失败")


if __name__ == '__main__':
    unittest.main()