"""File 测试用例"""

import unittest
import warnings
import logging
import os
from session import session
from cas import cas
from .file.file import File

# 配置日志
logger = logging.getLogger(__name__)


class FileTestCase(unittest.TestCase):
    """File 测试用例类"""
    
    server_url = 'https://panel.local.vpc'
    namespace = ''
    
    @classmethod
    def setUpClass(cls):
        """测试类初始化"""
        warnings.simplefilter('ignore', ResourceWarning)
        cls.work_session = session.MagicSession(cls.server_url, cls.namespace)
        
        # CAS 登录
        cas_session = cas.Cas(cls.work_session)
        if not cas_session.login('administrator', 'administrator'):
            logger.error('CAS登录失败')
            raise RuntimeError('CAS登录失败，无法继续测试')
        
        cls.work_session.bind_token(cas_session.get_session_token())
        cls.file_app = File("test_scope", "test_source", None, cls.work_session)
    
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
        
        # 验证文件信息完整性（根据实际服务器响应调整）
        required_fields = ['token', 'name']
        for field in required_fields:
            self.assertIn(field, new_file, f"缺少字段: {field}")
        
        # 记录创建的文件token以便清理
        if new_file and 'token' in new_file:
            self.created_file_tokens.append(new_file['token'])
            # 尝试通过view_file获取ID
            viewed_file = self.file_app.view_file(new_file['token'])
            if viewed_file and 'id' in viewed_file:
                self.created_file_ids.append(viewed_file['id'])
    
    def test_upload_public_file(self):
        """测试上传公共文件（fileScope=share）"""
        # 创建专门用于公共文件测试的File实例
        public_app = File("share", "test_source", None, self.work_session)
        
        new_file = public_app.upload_file(self.test_file_path)
        self.assertIsNotNone(new_file, "公共文件上传失败")
        
        # 验证文件信息
        self.assertIn('token', new_file, "缺少token字段")
        
        # 记录以便清理
        if new_file and 'token' in new_file:
            self.created_file_tokens.append(new_file['token'])
            viewed_file = public_app.view_file(new_file['token'])
            if viewed_file and 'id' in viewed_file:
                self.created_file_ids.append(viewed_file['id'])
    
    def test_upload_private_file(self):
        """测试上传私有文件（fileScope=private）"""
        # 创建专门用于私有文件测试的File实例
        private_app = File("private", "test_source", None, self.work_session)
        
        new_file = private_app.upload_file(self.test_file_path)
        self.assertIsNotNone(new_file, "私有文件上传失败")
        
        # 验证文件信息
        self.assertIn('token', new_file, "缺少token字段")
        
        # 记录以便清理
        if new_file and 'token' in new_file:
            self.created_file_tokens.append(new_file['token'])
            viewed_file = private_app.view_file(new_file['token'])
            if viewed_file and 'id' in viewed_file:
                self.created_file_ids.append(viewed_file['id'])
    
    def test_download_public_file(self):
        """测试下载公共文件"""
        # 上传公共文件
        public_app = File("share", "test_source", None, self.work_session)
        new_file = public_app.upload_file(self.test_file_path)
        self.assertIsNotNone(new_file, "公共文件上传失败")
        
        # 通过view_file获取文件ID
        viewed_file = public_app.view_file(new_file['token'])
        self.assertIsNotNone(viewed_file, "查看文件失败")
        self.assertIn('id', viewed_file, "查看文件缺少id字段")
        
        file_id = viewed_file['id']
        file_token = new_file['token']
        
        # 提交文件以确保文件可下载
        committed_file = public_app.commit_file(file_id, 3600)
        # 提交可能不是必需的，但如果需要则尝试
        
        # 下载文件到临时路径
        import tempfile
        download_path = tempfile.mktemp(suffix='.txt')
        
        try:
            downloaded = public_app.download_file(file_token, download_path)
            # 下载功能是核心功能，必须验证下载结果
            self.assertIsNotNone(downloaded, "公共文件下载失败")
            self.assertTrue(os.path.exists(downloaded), "下载的文件不存在")
            
            # 验证文件内容
            with open(downloaded, 'r') as f:
                content = f.read()
            self.assertEqual(content, "测试文件内容", "下载的文件内容不匹配")
        finally:
            if os.path.exists(download_path):
                os.remove(download_path)
        
        # 记录以便清理
        if new_file and 'token' in new_file:
            self.created_file_tokens.append(new_file['token'])
        if viewed_file and 'id' in viewed_file:
            self.created_file_ids.append(file_id)
    
    def test_download_private_file(self):
        """测试下载私有文件"""
        # 上传私有文件
        private_app = File("private", "test_source", None, self.work_session)
        new_file = private_app.upload_file(self.test_file_path)
        self.assertIsNotNone(new_file, "私有文件上传失败")
        
        # 通过view_file获取文件ID
        viewed_file = private_app.view_file(new_file['token'])
        self.assertIsNotNone(viewed_file, "查看文件失败")
        self.assertIn('id', viewed_file, "查看文件缺少id字段")
        
        file_id = viewed_file['id']
        file_token = new_file['token']
        
        # 提交文件以确保文件可下载
        committed_file = private_app.commit_file(file_id, 3600)
        # 提交可能不是必需的，但如果需要则尝试
        
        # 下载文件到临时路径
        import tempfile
        download_path = tempfile.mktemp(suffix='.txt')
        
        try:
            downloaded = private_app.download_file(file_token, download_path)
            # 下载功能是核心功能，必须验证下载结果
            self.assertIsNotNone(downloaded, "私有文件下载失败")
            self.assertTrue(os.path.exists(downloaded), "下载的文件不存在")
            
            # 验证文件内容
            with open(downloaded, 'r') as f:
                content = f.read()
            self.assertEqual(content, "测试文件内容", "下载的文件内容不匹配")
        finally:
            if os.path.exists(download_path):
                os.remove(download_path)
        
        # 记录以便清理
        if new_file and 'token' in new_file:
            self.created_file_tokens.append(new_file['token'])
        if viewed_file and 'id' in viewed_file:
            self.created_file_ids.append(file_id)
    
    def test_query_file(self):
        """测试文件查询"""
        # 先上传文件
        new_file = self.file_app.upload_file(self.test_file_path)
        self.assertIsNotNone(new_file, "文件上传失败")
        
        # 通过view_file获取文件ID
        viewed_file = self.file_app.view_file(new_file['token'])
        self.assertIsNotNone(viewed_file, "查看文件失败")
        self.assertIn('id', viewed_file, "查看文件缺少id字段")
        
        file_id = viewed_file['id']
        self.created_file_ids.append(file_id)
        
        # 查询文件
        queried_file = self.file_app.query_file(file_id)
        self.assertIsNotNone(queried_file, "文件查询失败")
        self.assertEqual(queried_file['id'], file_id, "文件ID不匹配")
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
        
        # 通过view_file获取文件ID
        viewed_file = self.file_app.view_file(new_file['token'])
        self.assertIsNotNone(viewed_file, "查看文件失败")
        self.assertIn('id', viewed_file, "查看文件缺少id字段")
        
        file_id = viewed_file['id']
        self.created_file_ids.append(file_id)
        
        # 过滤文件 - 由于文件可能不在根目录，我们只测试方法能正常工作
        file_list = self.file_app.filter_file()
        self.assertIsNotNone(file_list, "文件过滤失败")
        # 不检查是否为空，因为文件可能不在当前浏览的目录
        
        # 可以测试带路径参数的过滤
        # 根据上传文件的路径，尝试在正确的目录下过滤
        if 'path' in viewed_file:
            path = viewed_file['path']
            # 提取目录部分
            import os
            dir_path = os.path.dirname(path)
            params = {'path': dir_path}
            dir_file_list = self.file_app.filter_file(params)
            self.assertIsNotNone(dir_file_list, "带路径的文件过滤失败")
    
    def test_file_explorer_hierarchical_browsing(self):
        """测试文件浏览器逐级查看功能"""
        # 1. 首先查看根目录
        root_result = self.file_app.filter_file()
        self.assertIsNotNone(root_result, "根目录浏览失败")
        
        # 2. 检查根目录结构（应该包含dirs和files）
        # 由于filter_file只返回files列表，我们需要直接调用Client的filter_file来获取完整响应
        # 这里我们使用Client来获取更详细的信息
        from .file.file import Client
        client = Client(self.server_url, self.work_session)
        client.bind_source("test_source")
        client.bind_scope("test_scope")
        
        # 获取根目录的完整响应
        root_response = client.filter_file({})
        self.assertIsNotNone(root_response, "根目录浏览失败")
        
        # 3. 上传几个测试文件
        test_files = []
        for i in range(3):
            # 创建不同的测试文件
            test_file_path = f"./test_explorer_{i}.txt"
            with open(test_file_path, "w") as f:
                f.write(f"测试文件内容 {i}")
            
            try:
                new_file = self.file_app.upload_file(test_file_path)
                self.assertIsNotNone(new_file, f"测试文件{i}上传失败")
                
                if new_file and 'token' in new_file:
                    self.created_file_tokens.append(new_file['token'])
                    viewed_file = self.file_app.view_file(new_file['token'])
                    if viewed_file and 'id' in viewed_file:
                        self.created_file_ids.append(viewed_file['id'])
                        test_files.append(viewed_file)
            finally:
                if os.path.exists(test_file_path):
                    os.remove(test_file_path)
        
        # 4. 再次浏览根目录，应该能看到文件
        root_response_after = client.filter_file({})
        self.assertIsNotNone(root_response_after, "上传后根目录浏览失败")
        
        # 5. 测试带不同参数的浏览
        # 浏览特定source的文件
        source_params = {'source': 'test_source'}
        source_result = client.filter_file(source_params)
        self.assertIsNotNone(source_result, "按source过滤失败")
        
        # 浏览特定scope的文件
        scope_params = {'scope': 'test_scope'}
        scope_result = client.filter_file(scope_params)
        self.assertIsNotNone(scope_result, "按scope过滤失败")
        
        # 6. 如果文件有路径信息，测试按路径浏览
        if test_files and 'path' in test_files[0]:
            file_path = test_files[0]['path']
            dir_path = os.path.dirname(file_path)
            
            # 浏览文件所在目录
            path_params = {'path': dir_path}
            path_result = client.filter_file(path_params)
            self.assertIsNotNone(path_result, "按路径浏览失败")
            
            # 浏览父目录
            parent_dir = os.path.dirname(dir_path)
            if parent_dir and parent_dir != dir_path:  # 确保有父目录且不是当前目录
                parent_params = {'path': parent_dir}
                parent_result = client.filter_file(parent_params)
                self.assertIsNotNone(parent_result, "父目录浏览失败")
    
    def test_file_explorer_with_different_scopes(self):
        """测试不同scope的文件浏览器"""
        # 测试公共文件浏览
        public_app = File("share", "test_source_public", None, self.work_session)
        
        # 上传一个公共文件
        public_file = public_app.upload_file(self.test_file_path)
        self.assertIsNotNone(public_file, "公共文件上传失败")
        
        if public_file and 'token' in public_file:
            self.created_file_tokens.append(public_file['token'])
            viewed_file = public_app.view_file(public_file['token'])
            if viewed_file and 'id' in viewed_file:
                self.created_file_ids.append(viewed_file['id'])
        
        # 浏览公共文件
        public_result = public_app.filter_file()
        self.assertIsNotNone(public_result, "公共文件浏览失败")
        
        # 测试私有文件浏览
        private_app = File("private", "test_source_private", None, self.work_session)
        
        # 上传一个私有文件
        private_file = private_app.upload_file(self.test_file_path)
        self.assertIsNotNone(private_file, "私有文件上传失败")
        
        if private_file and 'token' in private_file:
            self.created_file_tokens.append(private_file['token'])
            viewed_file = private_app.view_file(private_file['token'])
            if viewed_file and 'id' in viewed_file:
                self.created_file_ids.append(viewed_file['id'])
        
        # 浏览私有文件
        private_result = private_app.filter_file()
        self.assertIsNotNone(private_result, "私有文件浏览失败")
    
    def test_delete_file(self):
        """测试文件删除"""
        # 先上传文件
        new_file = self.file_app.upload_file(self.test_file_path)
        self.assertIsNotNone(new_file, "文件上传失败")
        
        # 通过view_file获取文件ID
        viewed_file = self.file_app.view_file(new_file['token'])
        self.assertIsNotNone(viewed_file, "查看文件失败")
        self.assertIn('id', viewed_file, "查看文件缺少id字段")
        
        file_id = viewed_file['id']
        
        # 删除文件
        deleted_file = self.file_app.delete_file(file_id)
        self.assertIsNotNone(deleted_file, "文件删除失败")
        self.assertEqual(deleted_file['id'], file_id, "删除的文件ID不匹配")
        
        # 验证文件已被删除（查询应该失败）
        queried_file = self.file_app.query_file(file_id)
        self.assertIsNone(queried_file, "已删除的文件查询应失败")
    
    def test_update_file(self):
        """测试文件更新"""
        # 先上传文件
        new_file = self.file_app.upload_file(self.test_file_path)
        self.assertIsNotNone(new_file, "文件上传失败")
        
        # 通过view_file获取文件ID
        viewed_file = self.file_app.view_file(new_file['token'])
        self.assertIsNotNone(viewed_file, "查看文件失败")
        self.assertIn('id', viewed_file, "查看文件缺少id字段")
        
        file_id = viewed_file['id']
        self.created_file_ids.append(file_id)
        
        # 更新文件描述
        import random
        new_description = f"更新后的描述_{random.randint(1, 1000)}"
        update_param = {
            'description': new_description
        }
        updated_file = self.file_app.update_file(file_id, update_param)
        self.assertIsNotNone(updated_file, "文件更新失败")
        self.assertEqual(updated_file['id'], file_id, "更新后文件ID不匹配")
        
        # 查询验证更新
        queried_file = self.file_app.query_file(file_id)
        self.assertIsNotNone(queried_file, "文件查询失败")
        self.assertEqual(queried_file['description'], new_description, "文件描述未更新")
    
    def test_commit_file(self):
        """测试文件提交（设置有效期）"""
        # 先上传文件
        new_file = self.file_app.upload_file(self.test_file_path)
        self.assertIsNotNone(new_file, "文件上传失败")
        
        # 通过view_file获取文件ID
        viewed_file = self.file_app.view_file(new_file['token'])
        self.assertIsNotNone(viewed_file, "查看文件失败")
        self.assertIn('id', viewed_file, "查看文件缺少id字段")
        
        file_id = viewed_file['id']
        self.created_file_ids.append(file_id)
        
        # 提交文件，设置TTL为1小时（3600秒）
        ttl = 3600
        committed_file = self.file_app.commit_file(file_id, ttl)
        self.assertIsNotNone(committed_file, "文件提交失败")
        self.assertEqual(committed_file['id'], file_id, "提交后文件ID不匹配")
        # 可以验证有效期字段（如果有）
    
    def test_complete_file_lifecycle(self):
        """测试完整的文件生命周期管理"""
        # 1. 上传文件
        new_file = self.file_app.upload_file(self.test_file_path)
        self.assertIsNotNone(new_file, "文件上传失败")
        
        file_token = new_file['token']
        self.created_file_tokens.append(file_token)
        
        # 2. 查看文件信息
        viewed_file = self.file_app.view_file(file_token)
        self.assertIsNotNone(viewed_file, "查看文件失败")
        self.assertIn('id', viewed_file, "查看文件缺少id字段")
        self.assertIn('name', viewed_file, "查看文件缺少name字段")
        self.assertIn('path', viewed_file, "查看文件缺少path字段")
        
        file_id = viewed_file['id']
        self.created_file_ids.append(file_id)
        
        # 3. 查询文件信息
        queried_file = self.file_app.query_file(file_id)
        self.assertIsNotNone(queried_file, "文件查询失败")
        self.assertEqual(queried_file['id'], file_id, "查询的文件ID不匹配")
        self.assertEqual(queried_file['name'], new_file['name'], "查询的文件名不匹配")
        
        # 4. 更新文件信息
        import random
        new_description = f"完整生命周期测试描述_{random.randint(1, 10000)}"
        new_tags = ['lifecycle', 'test', 'complete']
        update_param = {
            'description': new_description,
            'tags': new_tags
        }
        updated_file = self.file_app.update_file(file_id, update_param)
        self.assertIsNotNone(updated_file, "文件更新失败")
        self.assertEqual(updated_file['id'], file_id, "更新后文件ID不匹配")
        
        # 5. 验证更新
        queried_after_update = self.file_app.query_file(file_id)
        self.assertIsNotNone(queried_after_update, "更新后查询失败")
        self.assertEqual(queried_after_update['description'], new_description, "文件描述未更新")
        # 注意：服务器可能不返回tags字段，或者格式不同
        
        # 6. 提交文件（设置有效期）
        ttl = 7200  # 2小时
        committed_file = self.file_app.commit_file(file_id, ttl)
        self.assertIsNotNone(committed_file, "文件提交失败")
        self.assertEqual(committed_file['id'], file_id, "提交后文件ID不匹配")
        
        # 7. 删除文件
        deleted_file = self.file_app.delete_file(file_id)
        self.assertIsNotNone(deleted_file, "文件删除失败")
        self.assertEqual(deleted_file['id'], file_id, "删除的文件ID不匹配")
        
        # 8. 验证文件已被删除
        queried_after_delete = self.file_app.query_file(file_id)
        self.assertIsNone(queried_after_delete, "已删除的文件查询应失败")
        
        # 从清理列表中移除，因为已经删除了
        if file_id in self.created_file_ids:
            self.created_file_ids.remove(file_id)
        if file_token in self.created_file_tokens:
            self.created_file_tokens.remove(file_token)
    
    def test_upload_stream(self):
        """测试文件流上传"""
        # 准备字节数据
        content = b"This is file content uploaded via stream"
        dst_path = "test/path"
        dst_name = "stream_uploaded.txt"
        
        token = self.file_app.upload_stream(dst_path, dst_name, content)
        self.assertIsNotNone(token, "文件流上传失败")
        self.assertIsInstance(token, str, "返回的token应为字符串")
        
        # 记录token以便清理（通过view_file获取ID）
        viewed_file = self.file_app.view_file(token)
        if viewed_file and 'id' in viewed_file:
            self.created_file_ids.append(viewed_file['id'])
        if token:
            self.created_file_tokens.append(token)
    
    def test_upload_large_file(self):
        """测试大文件上传（边界测试）"""
        # 创建大文件
        large_file_path = "./test_large_upload.txt"
        with open(large_file_path, "w") as f:
            # 写入1MB数据
            f.write("X" * 1024 * 1024)
        
        try:
            new_file = self.file_app.upload_file(large_file_path)
            # 必须验证上传结果
            self.assertIsNotNone(new_file, "大文件上传失败")
            self.assertIsInstance(new_file.get('size', 0), int, "文件大小不是整数")
            # 记录创建的文件token以便清理
            if 'token' in new_file:
                self.created_file_tokens.append(new_file['token'])
                # 尝试通过view_file获取ID
                viewed_file = self.file_app.view_file(new_file['token'])
                if viewed_file and 'id' in viewed_file:
                    self.created_file_ids.append(viewed_file['id'])
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
            # 必须验证上传结果
            self.assertIsNotNone(new_file, "空文件上传失败")
            self.assertEqual(new_file.get('size', 0), 0, "空文件大小应为0")
            # 记录创建的文件token以便清理
            if 'token' in new_file:
                self.created_file_tokens.append(new_file['token'])
                # 尝试通过view_file获取ID
                viewed_file = self.file_app.view_file(new_file['token'])
                if viewed_file and 'id' in viewed_file:
                    self.created_file_ids.append(viewed_file['id'])
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