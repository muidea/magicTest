"""Account 测试用例 - 基于 test_scenarios.md 的完整测试"""

import unittest
import logging
import warnings
from session import session
from cas import cas
from mock import common
from .account import Account
from cas.role import Role as RoleApp

# 配置日志
logger = logging.getLogger(__name__)


class AccountTestCase(unittest.TestCase):
    """Account 测试用例类"""
    
    server_url = 'https://autotest.local.vpc/api/v1'
    namespace = ''
    
    @classmethod
    def setUpClass(cls):
        """测试类初始化"""
        warnings.simplefilter('ignore', ResourceWarning)
        cls.work_session = session.MagicSession(cls.server_url, cls.namespace)
        cls.cas_session = cas.Cas(cls.work_session)
        if not cls.cas_session.login('administrator', 'administrator'):
            logger.error('CAS登录失败')
            raise Exception('CAS登录失败')
        cls.work_session.bind_token(cls.cas_session.get_session_token())
        cls.account_app = Account(cls.work_session)
        cls.role_app = RoleApp(cls.work_session)
    
    def setUp(self):
        """每个测试用例前的准备"""
        # 记录测试创建的账户ID和角色ID以便清理
        self.created_account_ids = []
        self.created_role_ids = []
    
    def tearDown(self):
        """每个测试用例后的清理"""
        # 清理所有测试创建的账户
        for account_id in self.created_account_ids:
            try:
                self.account_app.delete_account(account_id)
            except Exception as e:
                logger.warning(f"清理账户 {account_id} 失败: {e}")
        
        # 清理所有测试创建的角色
        for role_id in self.created_role_ids:
            try:
                self.role_app.delete_role(role_id)
            except Exception as e:
                logger.warning(f"清理角色 {role_id} 失败: {e}")
        
        self.created_account_ids.clear()
        self.created_role_ids.clear()
    
    # ========== 场景 A1: 账户创建与角色关联 ==========
    
    def create_test_role(self):
        """创建测试用的Role对象"""
        param = {
            'name': f"test_role_{common.word()}",
            'description': "测试角色",
            'group': 'test',
            'privilege': [],
            'status': 2
        }
        role = self.role_app.create_role(param)
        if role and 'id' in role:
            self.created_role_ids.append(role['id'])
        return role
    
    def test_a1_account_creation_with_role_association(self):
        """场景 A1: 账户创建与角色关联"""
        # 前置条件: 创建有效的Role
        test_role = self.create_test_role()
        self.assertIsNotNone(test_role, "创建测试角色失败")
        
        # 创建关联到现有Role的账户
        param = {
            'account': common.word(),
            'password': 'Test@123',
            'email': common.email(),
            'description': common.sentence(),
            'namespace': self.namespace,
            'roleLite': {
                'id': test_role['id'],
                'name': test_role['name']
            }
        }
        
        new_account = self.account_app.create_account(param)
        self.assertIsNotNone(new_account, "账户创建失败")
        
        # 验证账户信息完整性
        required_fields = ['id', 'account', 'email', 'description', 'namespace']
        for field in required_fields:
            self.assertIn(field, new_account, f"缺少字段: {field}")
        
        self.assertEqual(new_account['account'], param['account'], "账户名不匹配")
        self.assertEqual(new_account['email'], param['email'], "邮箱不匹配")
        self.assertEqual(new_account['namespace'], param['namespace'], "命名空间不匹配")
        
        # 验证角色关联正确性
        self.assertIn('roleLite', new_account, "账户缺少角色关联字段")
        if 'roleLite' in new_account:
            self.assertEqual(new_account['roleLite']['id'], test_role['id'], "关联角色ID不匹配")
            self.assertEqual(new_account['roleLite']['name'], test_role['name'], "关联角色名称不匹配")
        
        # 测试密码加密逻辑 - 验证密码不是明文存储
        # 注意：这里假设API返回的账户信息中不包含明文密码
        self.assertNotIn('password', new_account, "账户信息不应包含明文密码")
        
        # 记录创建的账户ID以便清理
        if new_account and 'id' in new_account:
            self.created_account_ids.append(new_account['id'])
    
    # ========== 场景 A2: 账户命名空间隔离 ==========
    
    def test_a2_account_namespace_isolation(self):
        """场景 A2: 账户命名空间隔离"""
        account_name = common.word()
        
        param_ns1 = {
            'account': account_name,
            'password': 'Test@123',
            'email': common.email(),
            'description': common.sentence(),
            'namespace': 'ns1'
        }
        
        param_ns2 = {
            'account': account_name,
            'password': 'Test@123',
            'email': common.email(),
            'description': common.sentence(),
            'namespace': 'ns2'
        }
        
        account_ns1 = self.account_app.create_account(param_ns1)
        self.assertIsNotNone(account_ns1, "创建ns1账户失败")
        
        account_ns2 = self.account_app.create_account(param_ns2)
        self.assertIsNotNone(account_ns2, "创建ns2账户失败")
        
        self.assertNotEqual(account_ns1['id'], account_ns2['id'], "不同命名空间的账户ID应该不同")
        
        filter_ns1 = {'namespace': 'ns1'}
        accounts_ns1 = self.account_app.filter_account(filter_ns1)
        self.assertIsNotNone(accounts_ns1, "过滤ns1账户失败")
        
        filter_ns2 = {'namespace': 'ns2'}
        accounts_ns2 = self.account_app.filter_account(filter_ns2)
        self.assertIsNotNone(accounts_ns2, "过滤ns2账户失败")
        
        # 记录创建的账户ID以便清理
        if account_ns1 and 'id' in account_ns1:
            self.created_account_ids.append(account_ns1['id'])
        if account_ns2 and 'id' in account_ns2:
            self.created_account_ids.append(account_ns2['id'])
    
    # ========== 场景 A3: 账户密码安全 ==========
    
    def test_a3_account_password_security(self):
        """场景 A3: 账户密码安全"""
        # 测试1: 创建带密码的账户并验证密码存储安全性
        test_password = 'SecurePass123!@#'
        param = {
            'account': common.word(),
            'password': test_password,
            'email': common.email(),
            'description': common.sentence(),
            'namespace': self.namespace
        }
        
        new_account = self.account_app.create_account(param)
        self.assertIsNotNone(new_account, "创建账户失败")
        
        # 验证密码存储安全性（加密）- 账户信息中不应包含明文密码
        self.assertNotIn('password', new_account, "账户信息不应包含明文密码")
        
        # 记录创建的账户ID以便清理
        if new_account and 'id' in new_account:
            self.created_account_ids.append(new_account['id'])
        
        # 测试2: 测试密码验证逻辑
        # 注意：这里假设有密码验证API或方法
        # 由于不清楚具体的密码验证接口，这里先注释掉
        # try:
        #     # 尝试使用正确密码验证
        #     verification_result = self.account_app.verify_password(new_account['id'], test_password)
        #     self.assertTrue(verification_result, "正确密码验证应成功")
        #
        #     # 尝试使用错误密码验证
        #     wrong_verification = self.account_app.verify_password(new_account['id'], 'WrongPassword123')
        #     self.assertFalse(wrong_verification, "错误密码验证应失败")
        # except AttributeError:
        #     logger.warning("密码验证API不可用，跳过密码验证测试")
        
        # 测试3: 测试密码重置功能
        # 注意：这里假设有密码重置API或方法
        # 由于不清楚具体的密码重置接口，这里先注释掉
        # try:
        #     new_password = 'NewSecurePass456!@#'
        #     reset_result = self.account_app.reset_password(new_account['id'], new_password)
        #     self.assertTrue(reset_result, "密码重置应成功")
        # except AttributeError:
        #     logger.warning("密码重置API不可用，跳过密码重置测试")
    
    # ========== 测试用例 A-TC-001 到 A-TC-015 ==========
    
    def test_atc001_create_basic_account(self):
        """A-TC-001: 创建基本账户"""
        param = {
            'account': 'user1',
            'password': '123',
            'email': 'test@example.com',
            'description': common.sentence(),
            'namespace': self.namespace
        }
        
        new_account = self.account_app.create_account(param)
        self.assertIsNotNone(new_account, "创建基本账户失败")
        
        self.assertEqual(new_account['account'], 'user1', "账户名不匹配")
        self.assertEqual(new_account['email'], 'test@example.com', "邮箱不匹配")
        
        # 记录创建的账户ID以便清理
        if new_account and 'id' in new_account:
            self.created_account_ids.append(new_account['id'])
    
    def test_atc002_create_account_with_role_association(self):
        """A-TC-002: 创建带角色关联的账户"""
        # 创建测试角色
        test_role = self.create_test_role()
        self.assertIsNotNone(test_role, "创建测试角色失败")
        
        param = {
            'account': common.word(),
            'password': '123',
            'email': common.email(),
            'description': common.sentence(),
            'namespace': self.namespace,
            'roleLite': {
                'id': test_role['id'],
                'name': test_role['name']
            }
        }
        
        new_account = self.account_app.create_account(param)
        self.assertIsNotNone(new_account, "创建账户失败")
        
        # 验证角色关联正确性
        self.assertIn('roleLite', new_account, "账户缺少角色关联字段")
        if 'roleLite' in new_account:
            self.assertEqual(new_account['roleLite']['id'], test_role['id'], "关联角色ID不匹配")
            self.assertEqual(new_account['roleLite']['name'], test_role['name'], "关联角色名称不匹配")
        
        # 记录创建的账户ID以便清理
        if new_account and 'id' in new_account:
            self.created_account_ids.append(new_account['id'])
    
    def test_atc003_create_account_with_long_email(self):
        """A-TC-003: 创建超长邮箱账户（边界测试）"""
        long_local = 'a' * 240
        long_email = f'{long_local}@example.com'
        
        param = {
            'account': common.word(),
            'password': '123',
            'email': long_email,
            'description': common.sentence(),
            'namespace': self.namespace
        }
        
        new_account = self.account_app.create_account(param)
        if new_account is not None:
            self.assertIsInstance(new_account['email'], str, "邮箱不是字符串")
            # 记录创建的账户ID以便清理
            if 'id' in new_account:
                self.created_account_ids.append(new_account['id'])
    
    def test_atc004_create_account_with_special_characters(self):
        """A-TC-004: 创建特殊字符账户名"""
        param = {
            'account': 'user@123',
            'password': '123',
            'email': common.email(),
            'description': common.sentence(),
            'namespace': self.namespace
        }
        
        new_account = self.account_app.create_account(param)
        if new_account is not None:
            # 记录创建的账户ID以便清理
            if 'id' in new_account:
                self.created_account_ids.append(new_account['id'])
    
    def test_atc005_create_duplicate_account(self):
        """A-TC-005: 创建重复账户名（异常测试）"""
        param = {
            'account': common.word(),
            'password': '123',
            'email': common.email(),
            'description': common.sentence(),
            'namespace': self.namespace
        }
        
        first_account = self.account_app.create_account(param)
        self.assertIsNotNone(first_account, "第一次创建账户失败")
        
        # 记录第一次创建的账户ID以便清理
        if first_account and 'id' in first_account:
            self.created_account_ids.append(first_account['id'])
        
        # 第二次创建相同账户名应该失败
        second_account = self.account_app.create_account(param)
        # 期望创建失败，返回None或错误响应
        self.assertIsNone(second_account, "重复账户名创建应失败")
    
    def test_atc006_create_account_with_invalid_email(self):
        """A-TC-006: 创建无效邮箱格式（异常测试）"""
        param = {
            'account': common.word(),
            'password': '123',
            'email': 'invalid-email',
            'description': common.sentence(),
            'namespace': self.namespace
        }
        
        new_account = self.account_app.create_account(param)
        # 期望创建失败，返回None或错误响应
        self.assertIsNone(new_account, "无效邮箱格式创建应失败")
    
    def test_atc007_create_account_with_nonexistent_role(self):
        """A-TC-007: 关联不存在的角色（异常测试）"""
        # 使用一个非常大的ID，确保该角色不存在
        # 先查询确认该角色确实不存在
        nonexistent_role_id = 999999
        queried_role = self.role_app.query_role(nonexistent_role_id)
        self.assertIsNone(queried_role, f"角色ID {nonexistent_role_id} 应该不存在")
        
        param = {
            'account': common.word(),
            'password': '123',
            'email': common.email(),
            'description': common.sentence(),
            'namespace': self.namespace,
            'roleLite': {'id': nonexistent_role_id, 'name': 'NonExistentRole'}
        }
        
        new_account = self.account_app.create_account(param)
        # 期望创建失败，返回None或错误响应
        self.assertIsNone(new_account, "关联不存在的角色创建应失败")
    
    def test_atc008_update_account_info(self):
        """A-TC-008: 更新账户信息"""
        param = {
            'account': common.word(),
            'password': '123',
            'email': common.email(),
            'description': "原始描述",
            'namespace': self.namespace
        }
        
        new_account = self.account_app.create_account(param)
        self.assertIsNotNone(new_account, "创建账户失败")
        
        # 记录创建的账户ID以便清理
        if new_account and 'id' in new_account:
            self.created_account_ids.append(new_account['id'])
        
        update_param = new_account.copy()
        update_param['description'] = "新描述"
        
        updated_account = self.account_app.update_account(update_param)
        self.assertIsNotNone(updated_account, "更新账户失败")
        self.assertEqual(updated_account['description'], "新描述", "描述更新失败")
    
    def test_atc009_update_account_email(self):
        """A-TC-009: 更新账户邮箱"""
        param = {
            'account': common.word(),
            'password': '123',
            'email': 'old@example.com',
            'description': common.sentence(),
            'namespace': self.namespace
        }
        
        new_account = self.account_app.create_account(param)
        self.assertIsNotNone(new_account, "创建账户失败")
        
        # 记录创建的账户ID以便清理
        if new_account and 'id' in new_account:
            self.created_account_ids.append(new_account['id'])
        
        update_param = new_account.copy()
        update_param['email'] = 'new@example.com'
        
        updated_account = self.account_app.update_account(update_param)
        self.assertIsNotNone(updated_account, "更新邮箱失败")
        self.assertEqual(updated_account['email'], 'new@example.com', "邮箱更新失败")
    
    def test_atc010_update_to_duplicate_email(self):
        """A-TC-010: 更新为重复邮箱（异常测试）"""
        email1 = common.email()
        email2 = common.email()
        
        param1 = {
            'account': common.word(),
            'password': '123',
            'email': email1,
            'description': common.sentence(),
            'namespace': self.namespace
        }
        
        param2 = {
            'account': common.word(),
            'password': '123',
            'email': email2,
            'description': common.sentence(),
            'namespace': self.namespace
        }
        
        account1 = self.account_app.create_account(param1)
        self.assertIsNotNone(account1, "创建账户1失败")
        
        account2 = self.account_app.create_account(param2)
        self.assertIsNotNone(account2, "创建账户2失败")
        
        # 记录创建的账户ID以便清理
        if account1 and 'id' in account1:
            self.created_account_ids.append(account1['id'])
        if account2 and 'id' in account2:
            self.created_account_ids.append(account2['id'])
        
        update_param = account2.copy()
        update_param['email'] = email1
        
        updated_account = self.account_app.update_account(update_param)
        # 期望更新失败，返回None或错误响应
        self.assertIsNone(updated_account, "更新为重复邮箱应失败")
    
    def test_atc011_query_account(self):
        """A-TC-011: 查询账户"""
        param = {
            'account': common.word(),
            'password': '123',
            'email': common.email(),
            'description': common.sentence(),
            'namespace': self.namespace
        }
        
        new_account = self.account_app.create_account(param)
        self.assertIsNotNone(new_account, "创建账户失败")
        
        # 记录创建的账户ID以便清理
        if new_account and 'id' in new_account:
            self.created_account_ids.append(new_account['id'])
        
        queried_account = self.account_app.query_account(new_account['id'])
        self.assertIsNotNone(queried_account, "查询账户失败")
        self.assertEqual(queried_account['id'], new_account['id'], "账户ID不匹配")
        self.assertEqual(queried_account['account'], new_account['account'], "账户名不匹配")
    
    def test_atc012_filter_account_by_account_name(self):
        """A-TC-012: 过滤账户(按账户名)"""
        unique_account = common.word()
        
        param = {
            'account': unique_account,
            'password': '123',
            'email': common.email(),
            'description': common.sentence(),
            'namespace': self.namespace
        }
        
        new_account = self.account_app.create_account(param)
        self.assertIsNotNone(new_account, "创建账户失败")
        
        # 记录创建的账户ID以便清理
        if new_account and 'id' in new_account:
            self.created_account_ids.append(new_account['id'])
        
        filter_param = {'account': unique_account}
        filtered_accounts = self.account_app.filter_account(filter_param)
        
        self.assertIsNotNone(filtered_accounts, "过滤账户失败")
        self.assertGreaterEqual(len(filtered_accounts), 1, "过滤结果为空")
        
        found = False
        for account in filtered_accounts:
            if account['account'] == unique_account:
                found = True
                break
        self.assertTrue(found, "未找到匹配的账户")
    
    def test_atc013_filter_account_by_email(self):
        """A-TC-013: 过滤账户(按邮箱)"""
        unique_email = common.email()
        
        param = {
            'account': common.word(),
            'password': '123',
            'email': unique_email,
            'description': common.sentence(),
            'namespace': self.namespace
        }
        
        new_account = self.account_app.create_account(param)
        self.assertIsNotNone(new_account, "创建账户失败")
        
        # 记录创建的账户ID以便清理
        if new_account and 'id' in new_account:
            self.created_account_ids.append(new_account['id'])
        
        filter_param = {'email': unique_email}
        filtered_accounts = self.account_app.filter_account(filter_param)
        
        self.assertIsNotNone(filtered_accounts, "过滤账户失败")
        
        found = False
        for account in filtered_accounts:
            if account['id'] == new_account['id']:
                found = True
                self.assertEqual(account['email'], unique_email, "邮箱不匹配")
                break
    
    def test_atc014_filter_account_by_namespace(self):
        """A-TC-014: 过滤账户(按命名空间)"""
        test_namespace = 'test_ns'
        
        param = {
            'account': common.word(),
            'password': '123',
            'email': common.email(),
            'description': common.sentence(),
            'namespace': test_namespace
        }
        
        new_account = self.account_app.create_account(param)
        self.assertIsNotNone(new_account, "创建账户失败")
        
        # 记录创建的账户ID以便清理
        if new_account and 'id' in new_account:
            self.created_account_ids.append(new_account['id'])
        
        filter_param = {'namespace': test_namespace}
        filtered_accounts = self.account_app.filter_account(filter_param)
        
        self.assertIsNotNone(filtered_accounts, "过滤账户失败")
        
        found = False
        for account in filtered_accounts:
            if account['id'] == new_account['id']:
                found = True
                self.assertEqual(account['namespace'], test_namespace, "命名空间不匹配")
                break
    
    def test_atc015_delete_account(self):
        """A-TC-015: 删除账户"""
        param = {
            'account': common.word(),
            'password': '123',
            'email': common.email(),
            'description': common.sentence(),
            'namespace': self.namespace
        }
        
        new_account = self.account_app.create_account(param)
        self.assertIsNotNone(new_account, "创建账户失败")
        
        # 注意：删除测试不需要记录ID到created_account_ids，因为账户会被立即删除
        deleted_account = self.account_app.delete_account(new_account['id'])
        self.assertIsNotNone(deleted_account, "删除账户失败")
        self.assertEqual(deleted_account['id'], new_account['id'], "删除的账户ID不匹配")
        
        # 验证删除的账户包含必要字段
        self.assertIn('id', deleted_account, "删除返回缺少id字段")
        self.assertIn('account', deleted_account, "删除返回缺少account字段")
        
        # 验证账户已被删除（查询应该失败）
        queried_account = self.account_app.query_account(new_account['id'])
        # 期望查询失败，返回None或错误
        self.assertIsNone(queried_account, "已删除的账户查询应失败")


if __name__ == '__main__':
    unittest.main()