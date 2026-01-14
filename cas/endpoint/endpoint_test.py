"""Endpoint 测试用例 - 基于 test_scenarios.md 的完整测试"""

import unittest
import logging
import warnings
import time as dt
from session import session
from cas import cas
from mock import common
from .endpoint import Endpoint
from ..account.account import Account as AccountApp
from ..role.role import Role as RoleApp

# 配置日志
logger = logging.getLogger(__name__)


class EndpointTestCase(unittest.TestCase):
    """Endpoint 测试用例类"""
    
    server_url = 'https://autotest.local.vpc'
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
        cls.endpoint_app = Endpoint(cls.work_session)
        cls.account_app = AccountApp(cls.work_session)
        cls.role_app = RoleApp(cls.work_session)
    
    def setUp(self):
        """每个测试用例前的准备"""
        # 记录测试创建的端点、账户和角色ID以便清理
        self.created_endpoint_ids = []
        self.created_account_ids = []
        self.created_role_ids = []
    
    def tearDown(self):
        """每个测试用例后的清理"""
        # 清理所有测试创建的端点
        for endpoint_id in self.created_endpoint_ids:
            try:
                self.endpoint_app.delete_endpoint(endpoint_id)
            except Exception as e:
                logger.warning(f"清理端点 {endpoint_id} 失败: {e}")
        
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
        
        self.created_endpoint_ids.clear()
        self.created_account_ids.clear()
        self.created_role_ids.clear()
    
    # ========== 测试数据创建方法 ==========
    
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
    
    def create_test_account(self, role_id=None):
        """创建测试用的Account对象"""
        param = {
            'account': f"test_account_{common.word()}",
            'password': 'Test@123',
            'email': common.email(),
            'description': "测试账户",
            'namespace': self.namespace
        }
        
        if role_id:
            # 先查询角色信息获取名称
            role = self.role_app.query_role(role_id)
            if role:
                param['roleLite'] = {
                    'id': role_id,
                    'name': role['name']
                }
        
        account = self.account_app.create_account(param)
        if account and 'id' in account:
            self.created_account_ids.append(account['id'])
        return account
    
    def create_test_endpoint(self, account_id, role_id, scope='*', start_time_offset=-3600000, expire_time_offset=86400000):
        """创建测试用的Endpoint对象"""
        current_time_ms = int(dt.time() * 1000)
        
        # 查询账户和角色信息
        account = self.account_app.query_account(account_id)
        role = self.role_app.query_role(role_id)
        
        if not account or not role:
            return None
        
        param = {
            'name': common.word(),
            'description': common.sentence(),
            'account': {
                'id': account['id'],
                'account': account['account'],
                'status': account.get('status', 2)
            },
            'role': {
                'id': role['id'],
                'name': role['name'],
                'status': role.get('status', 2)
            },
            'scope': scope,
            'status': 2,
            'startTime': current_time_ms + start_time_offset,
            'expireTime': current_time_ms + expire_time_offset
        }
        
        endpoint = self.endpoint_app.create_endpoint(param)
        if endpoint and 'id' in endpoint:
            self.created_endpoint_ids.append(endpoint['id'])
        return endpoint
    
    # ========== 场景 E1: 端点时效性验证 ==========
    
    def test_e1_endpoint_timeliness_validation(self):
        """场景 E1: 端点时效性验证"""
        # 创建测试角色和账户
        test_role = self.create_test_role()
        self.assertIsNotNone(test_role, "创建测试角色失败")
        test_account = self.create_test_account(test_role['id'])
        self.assertIsNotNone(test_account, "创建测试账户失败")
        
        current_time_ms = int(dt.time() * 1000)
        
        # 1. 创建有效时间的端点 (StartTime < 当前时间 < ExpireTime)
        valid_endpoint = self.create_test_endpoint(
            test_account['id'], test_role['id'],
            start_time_offset=-3600000,  # 1小时前
            expire_time_offset=86400000  # 24小时后
        )
        self.assertIsNotNone(valid_endpoint, "创建有效时间端点失败")
        
        # 2. 创建已过期的端点 (ExpireTime < 当前时间)
        expired_endpoint_param = {
            'name': common.word(),
            'description': common.sentence(),
            'account': {
                'id': test_account['id'],
                'account': test_account['account'],
                'status': test_account.get('status', 2)
            },
            'role': {
                'id': test_role['id'],
                'name': test_role['name'],
                'status': test_role.get('status', 2)
            },
            'scope': '*',
            'status': 2,
            'startTime': current_time_ms - 172800000,  # 2天前
            'expireTime': current_time_ms - 86400000   # 1天前
        }
        expired_endpoint = self.endpoint_app.create_endpoint(expired_endpoint_param)
        # 可能成功创建，但业务逻辑上应该标记为无效
        if expired_endpoint and 'id' in expired_endpoint:
            self.created_endpoint_ids.append(expired_endpoint['id'])
        
        # 3. 创建未开始的端点 (StartTime > 当前时间)
        future_endpoint_param = {
            'name': common.word(),
            'description': common.sentence(),
            'account': {
                'id': test_account['id'],
                'account': test_account['account'],
                'status': test_account.get('status', 2)
            },
            'role': {
                'id': test_role['id'],
                'name': test_role['name'],
                'status': test_role.get('status', 2)
            },
            'scope': '*',
            'status': 2,
            'startTime': current_time_ms + 3600000,    # 1小时后
            'expireTime': current_time_ms + 172800000  # 2天后
        }
        future_endpoint = self.endpoint_app.create_endpoint(future_endpoint_param)
        if future_endpoint and 'id' in future_endpoint:
            self.created_endpoint_ids.append(future_endpoint['id'])
    
    # ========== 场景 E2: 端点权限关联 ==========
    
    def test_e2_endpoint_permission_association(self):
        """场景 E2: 端点权限关联"""
        # 创建测试角色和账户
        test_role = self.create_test_role()
        self.assertIsNotNone(test_role, "创建测试角色失败")
        test_account = self.create_test_account(test_role['id'])
        self.assertIsNotNone(test_account, "创建测试账户失败")
        
        # 创建关联Account和Role的端点
        endpoint = self.create_test_endpoint(test_account['id'], test_role['id'])
        self.assertIsNotNone(endpoint, "创建端点失败")
        
        # 验证关联对象完整性
        self.assertIn('account', endpoint, "端点缺少account字段")
        self.assertIn('role', endpoint, "端点缺少role字段")
        
        if 'account' in endpoint:
            self.assertEqual(endpoint['account']['id'], test_account['id'], "关联账户ID不匹配")
            self.assertEqual(endpoint['account']['account'], test_account['account'], "关联账户名不匹配")
        
        if 'role' in endpoint:
            self.assertEqual(endpoint['role']['id'], test_role['id'], "关联角色ID不匹配")
            self.assertEqual(endpoint['role']['name'], test_role['name'], "关联角色名称不匹配")
        
        # 测试更新关联对象
        update_param = endpoint.copy()
        update_param['description'] = "更新后的描述"
        
        updated_endpoint = self.endpoint_app.update_endpoint(update_param)
        self.assertIsNotNone(updated_endpoint, "更新端点失败")
        self.assertEqual(updated_endpoint['description'], "更新后的描述", "描述更新失败")
        
        # 验证关联对象在更新后保持不变
        self.assertEqual(updated_endpoint['account']['id'], test_account['id'], "更新后关联账户ID变化")
        self.assertEqual(updated_endpoint['role']['id'], test_role['id'], "更新后关联角色ID变化")
    
    # ========== 场景 E3: 端点作用域控制 ==========
    
    def test_e3_endpoint_scope_control(self):
        """场景 E3: 端点作用域控制"""
        # 创建测试角色和账户
        test_role = self.create_test_role()
        self.assertIsNotNone(test_role, "创建测试角色失败")
        test_account = self.create_test_account(test_role['id'])
        self.assertIsNotNone(test_account, "创建测试账户失败")
        
        current_time_ms = int(dt.time() * 1000)
        
        # 1. 创建全局作用域 ("*") 端点
        global_scope_param = {
            'name': common.word(),
            'description': common.sentence(),
            'account': {
                'id': test_account['id'],
                'account': test_account['account'],
                'status': test_account.get('status', 2)
            },
            'role': {
                'id': test_role['id'],
                'name': test_role['name'],
                'status': test_role.get('status', 2)
            },
            'scope': '*',
            'status': 2,
            'startTime': current_time_ms - 3600000,
            'expireTime': current_time_ms + 86400000
        }
        global_endpoint = self.endpoint_app.create_endpoint(global_scope_param)
        self.assertIsNotNone(global_endpoint, "创建全局作用域端点失败")
        if global_endpoint and 'id' in global_endpoint:
            self.created_endpoint_ids.append(global_endpoint['id'])
            self.assertEqual(global_endpoint['scope'], '*', "全局作用域设置失败")
        
        # 2. 创建多命名空间作用域 ("n1,n2") 端点
        multi_scope_param = {
            'name': common.word(),
            'description': common.sentence(),
            'account': {
                'id': test_account['id'],
                'account': test_account['account'],
                'status': test_account.get('status', 2)
            },
            'role': {
                'id': test_role['id'],
                'name': test_role['name'],
                'status': test_role.get('status', 2)
            },
            'scope': 'n1,n2,n3',
            'status': 2,
            'startTime': current_time_ms - 3600000,
            'expireTime': current_time_ms + 86400000
        }
        multi_endpoint = self.endpoint_app.create_endpoint(multi_scope_param)
        self.assertIsNotNone(multi_endpoint, "创建多命名空间作用域端点失败")
        if multi_endpoint and 'id' in multi_endpoint:
            self.created_endpoint_ids.append(multi_endpoint['id'])
            self.assertEqual(multi_endpoint['scope'], 'n1,n2,n3', "多命名空间作用域设置失败")
        
        # 3. 创建空作用域 ("") 端点
        empty_scope_param = {
            'name': common.word(),
            'description': common.sentence(),
            'account': {
                'id': test_account['id'],
                'account': test_account['account'],
                'status': test_account.get('status', 2)
            },
            'role': {
                'id': test_role['id'],
                'name': test_role['name'],
                'status': test_role.get('status', 2)
            },
            'scope': '',
            'status': 2,
            'startTime': current_time_ms - 3600000,
            'expireTime': current_time_ms + 86400000
        }
        empty_endpoint = self.endpoint_app.create_endpoint(empty_scope_param)
        if empty_endpoint and 'id' in empty_endpoint:
            self.created_endpoint_ids.append(empty_endpoint['id'])
            self.assertEqual(empty_endpoint['scope'], '', "空作用域设置失败")
    
    # ========== 重构现有测试用例 ==========
    
    def test_create_valid_endpoint(self):
        """E-TC-001: 创建有效时间端点"""
        # 创建测试角色和账户
        test_role = self.create_test_role()
        self.assertIsNotNone(test_role, "创建测试角色失败")
        test_account = self.create_test_account(test_role['id'])
        self.assertIsNotNone(test_account, "创建测试账户失败")
        
        endpoint = self.create_test_endpoint(test_account['id'], test_role['id'])
        self.assertIsNotNone(endpoint, "创建端点失败")
        
        # 验证端点包含必要字段
        required_fields = ['id', 'name', 'description', 'account', 'role', 'scope', 'status', 'startTime', 'expireTime']
        for field in required_fields:
            self.assertIn(field, endpoint, f"端点缺少字段: {field}")
    
    def test_update_endpoint(self):
        """E-TC-009: 更新端点时间 / E-TC-010: 更新端点作用域"""
        # 创建测试角色和账户
        test_role = self.create_test_role()
        self.assertIsNotNone(test_role, "创建测试角色失败")
        test_account = self.create_test_account(test_role['id'])
        self.assertIsNotNone(test_account, "创建测试账户失败")
        
        endpoint = self.create_test_endpoint(test_account['id'], test_role['id'])
        self.assertIsNotNone(endpoint, "创建端点失败")
        
        # 更新端点描述和作用域
        update_param = endpoint.copy()
        update_param['description'] = "更新后的描述"
        update_param['scope'] = 'n1,n2'
        
        updated_endpoint = self.endpoint_app.update_endpoint(update_param)
        self.assertIsNotNone(updated_endpoint, "更新端点失败")
        self.assertEqual(updated_endpoint['description'], "更新后的描述", "描述更新失败")
        self.assertEqual(updated_endpoint['scope'], 'n1,n2', "作用域更新失败")
    
    def test_query_endpoint(self):
        """E-TC-012: 查询端点"""
        # 创建测试角色和账户
        test_role = self.create_test_role()
        self.assertIsNotNone(test_role, "创建测试角色失败")
        test_account = self.create_test_account(test_role['id'])
        self.assertIsNotNone(test_account, "创建测试账户失败")
        
        endpoint = self.create_test_endpoint(test_account['id'], test_role['id'])
        self.assertIsNotNone(endpoint, "创建端点失败")
        
        queried_endpoint = self.endpoint_app.query_endpoint(endpoint['id'])
        self.assertIsNotNone(queried_endpoint, "查询端点失败")
        self.assertEqual(queried_endpoint['id'], endpoint['id'], "端点ID不匹配")
        self.assertEqual(queried_endpoint['name'], endpoint['name'], "端点路径不匹配")
    
    def test_filter_endpoint(self):
        """E-TC-013: 过滤端点(按路径)"""
        # 创建测试角色和账户
        test_role = self.create_test_role()
        self.assertIsNotNone(test_role, "创建测试角色失败")
        test_account = self.create_test_account(test_role['id'])
        self.assertIsNotNone(test_account, "创建测试账户失败")
        
        current_time_ms = int(dt.time() * 1000)
        unique_path = common.word()
        
        param = {
            'name': unique_path,
            'description': common.sentence(),
            'account': {
                'id': test_account['id'],
                'account': test_account['account'],
                'status': test_account.get('status', 2)
            },
            'role': {
                'id': test_role['id'],
                'name': test_role['name'],
                'status': test_role.get('status', 2)
            },
            'scope': '*',
            'status': 2,
            'startTime': current_time_ms,
            'expireTime': current_time_ms + 86400000
        }
        
        endpoint = self.endpoint_app.create_endpoint(param)
        self.assertIsNotNone(endpoint, "创建端点失败")
        if endpoint and 'id' in endpoint:
            self.created_endpoint_ids.append(endpoint['id'])
        
        filter_param = {'name': unique_path}
        filtered_endpoints = self.endpoint_app.filter_endpoint(filter_param)
        self.assertIsNotNone(filtered_endpoints, "过滤端点失败")
        
        found = False
        for ep in filtered_endpoints:
            if ep['name'] == unique_path:
                found = True
                break
        self.assertTrue(found, "未找到匹配的端点")
    
    def test_delete_endpoint(self):
        """E-TC-016: 删除端点"""
        # 创建测试角色和账户
        test_role = self.create_test_role()
        self.assertIsNotNone(test_role, "创建测试角色失败")
        test_account = self.create_test_account(test_role['id'])
        self.assertIsNotNone(test_account, "创建测试账户失败")
        
        endpoint = self.create_test_endpoint(test_account['id'], test_role['id'])
        self.assertIsNotNone(endpoint, "创建端点失败")
        
        # 从created_endpoint_ids中移除，因为我们要手动删除它
        if endpoint['id'] in self.created_endpoint_ids:
            self.created_endpoint_ids.remove(endpoint['id'])
        
        deleted_endpoint = self.endpoint_app.delete_endpoint(endpoint['id'])
        self.assertIsNotNone(deleted_endpoint, "删除端点失败")
        self.assertEqual(deleted_endpoint['id'], endpoint['id'], "删除的端点ID不匹配")
        
        # 验证端点已被删除（查询应该失败）
        queried_endpoint = self.endpoint_app.query_endpoint(endpoint['id'])
        self.assertIsNone(queried_endpoint, "已删除的端点查询应失败")
    
    # ========== 添加缺失的测试用例 ==========
    
    def test_etc002_create_global_scope_endpoint(self):
        """E-TC-002: 创建全局作用域端点"""
        test_role = self.create_test_role()
        self.assertIsNotNone(test_role, "创建测试角色失败")
        test_account = self.create_test_account(test_role['id'])
        self.assertIsNotNone(test_account, "创建测试账户失败")
        
        endpoint = self.create_test_endpoint(test_account['id'], test_role['id'], scope='*')
        self.assertIsNotNone(endpoint, "创建全局作用域端点失败")
        self.assertEqual(endpoint['scope'], '*', "全局作用域设置失败")
    
    def test_etc003_create_multi_namespace_endpoint(self):
        """E-TC-003: 创建多命名空间端点"""
        test_role = self.create_test_role()
        self.assertIsNotNone(test_role, "创建测试角色失败")
        test_account = self.create_test_account(test_role['id'])
        self.assertIsNotNone(test_account, "创建测试账户失败")
        
        endpoint = self.create_test_endpoint(test_account['id'], test_role['id'], scope='n1,n2,n3')
        self.assertIsNotNone(endpoint, "创建多命名空间端点失败")
        self.assertEqual(endpoint['scope'], 'n1,n2,n3', "多命名空间作用域设置失败")
    
    def test_etc004_create_time_boundary_endpoint(self):
        """E-TC-004: 创建时间边界端点"""
        test_role = self.create_test_role()
        self.assertIsNotNone(test_role, "创建测试角色失败")
        test_account = self.create_test_account(test_role['id'])
        self.assertIsNotNone(test_account, "创建测试账户失败")
        
        current_time_ms = int(dt.time() * 1000)
        # 创建 startTime = expireTime 的端点
        param = {
            'name': common.word(),
            'description': common.sentence(),
            'account': {
                'id': test_account['id'],
                'account': test_account['account'],
                'status': test_account.get('status', 2)
            },
            'role': {
                'id': test_role['id'],
                'name': test_role['name'],
                'status': test_role.get('status', 2)
            },
            'scope': '*',
            'status': 2,
            'startTime': current_time_ms,
            'expireTime': current_time_ms  # 零时长
        }
        
        endpoint = self.endpoint_app.create_endpoint(param)
        # 可能成功或失败，取决于服务器实现
        if endpoint and 'id' in endpoint:
            self.created_endpoint_ids.append(endpoint['id'])
    
    def test_etc005_create_long_path_endpoint(self):
        """E-TC-005: 创建超长端点路径"""
        test_role = self.create_test_role()
        self.assertIsNotNone(test_role, "创建测试角色失败")
        test_account = self.create_test_account(test_role['id'])
        self.assertIsNotNone(test_account, "创建测试账户失败")
        
        # 生成超长路径
        long_path = 'a' * 500
        
        param = {
            'name': long_path,
            'description': common.sentence(),
            'account': {
                'id': test_account['id'],
                'account': test_account['account'],
                'status': test_account.get('status', 2)
            },
            'role': {
                'id': test_role['id'],
                'name': test_role['name'],
                'status': test_role.get('status', 2)
            },
            'scope': '*',
            'status': 2,
            'startTime': int(dt.time() * 1000) - 3600000,
            'expireTime': int(dt.time() * 1000) + 86400000
        }
        
        endpoint = self.endpoint_app.create_endpoint(param)
        # 可能成功或失败，取决于服务器实现
        if endpoint and 'id' in endpoint:
            self.created_endpoint_ids.append(endpoint['id'])
    
    def test_etc006_create_invalid_time_logic_endpoint(self):
        """E-TC-006: 创建时间逻辑错误端点"""
        test_role = self.create_test_role()
        self.assertIsNotNone(test_role, "创建测试角色失败")
        test_account = self.create_test_account(test_role['id'])
        self.assertIsNotNone(test_account, "创建测试账户失败")
        
        current_time_ms = int(dt.time() * 1000)
        # 创建 startTime > expireTime 的端点
        param = {
            'name': common.word(),
            'description': common.sentence(),
            'account': {
                'id': test_account['id'],
                'account': test_account['account'],
                'status': test_account.get('status', 2)
            },
            'role': {
                'id': test_role['id'],
                'name': test_role['name'],
                'status': test_role.get('status', 2)
            },
            'scope': '*',
            'status': 2,
            'startTime': current_time_ms + 86400000,  # 1天后
            'expireTime': current_time_ms             # 现在
        }
        
        endpoint = self.endpoint_app.create_endpoint(param)
        # 期望创建失败，返回None或错误响应
        self.assertIsNone(endpoint, "时间逻辑错误的端点创建应失败")
    
    def test_etc007_create_endpoint_with_invalid_account(self):
        """E-TC-007: 创建关联无效账户的端点"""
        test_role = self.create_test_role()
        self.assertIsNotNone(test_role, "创建测试角色失败")
        
        # 使用不存在的账户ID
        nonexistent_account_id = 999999
        
        param = {
            'name': common.word(),
            'description': common.sentence(),
            'account': {
                'id': nonexistent_account_id,
                'account': 'nonexistent',
                'status': 2
            },
            'role': {
                'id': test_role['id'],
                'name': test_role['name'],
                'status': test_role.get('status', 2)
            },
            'scope': '*',
            'status': 2,
            'startTime': int(dt.time() * 1000) - 3600000,
            'expireTime': int(dt.time() * 1000) + 86400000
        }
        
        endpoint = self.endpoint_app.create_endpoint(param)
        # 期望创建失败，返回None或错误响应
        self.assertIsNone(endpoint, "关联无效账户的端点创建应失败")
    
    def test_etc008_create_endpoint_with_invalid_role(self):
        """E-TC-008: 创建关联无效角色的端点"""
        test_account = self.create_test_account()
        self.assertIsNotNone(test_account, "创建测试账户失败")
        
        # 使用不存在的角色ID
        nonexistent_role_id = 999999
        
        param = {
            'name': common.word(),
            'description': common.sentence(),
            'account': {
                'id': test_account['id'],
                'account': test_account['account'],
                'status': test_account.get('status', 2)
            },
            'role': {
                'id': nonexistent_role_id,
                'name': 'nonexistent',
                'status': 2
            },
            'scope': '*',
            'status': 2,
            'startTime': int(dt.time() * 1000) - 3600000,
            'expireTime': int(dt.time() * 1000) + 86400000
        }
        
        endpoint = self.endpoint_app.create_endpoint(param)
        # 期望创建失败，返回None或错误响应
        self.assertIsNone(endpoint, "关联无效角色的端点创建应失败")
    
    def test_etc011_update_endpoint_status(self):
        """E-TC-011: 更新端点状态"""
        test_role = self.create_test_role()
        self.assertIsNotNone(test_role, "创建测试角色失败")
        test_account = self.create_test_account(test_role['id'])
        self.assertIsNotNone(test_account, "创建测试账户失败")
        
        endpoint = self.create_test_endpoint(test_account['id'], test_role['id'])
        self.assertIsNotNone(endpoint, "创建端点失败")
        
        # 更新端点状态为禁用(1)
        update_param = endpoint.copy()
        update_param['status'] = 1
        
        updated_endpoint = self.endpoint_app.update_endpoint(update_param)
        self.assertIsNotNone(updated_endpoint, "更新端点状态失败")
        self.assertEqual(updated_endpoint['status'], 1, "端点状态更新失败")
    
    def test_etc014_filter_endpoint_by_status(self):
        """E-TC-014: 过滤端点(按状态)"""
        test_role = self.create_test_role()
        self.assertIsNotNone(test_role, "创建测试角色失败")
        test_account = self.create_test_account(test_role['id'])
        self.assertIsNotNone(test_account, "创建测试账户失败")
        
        # 创建启用状态的端点
        endpoint1 = self.create_test_endpoint(test_account['id'], test_role['id'])
        self.assertIsNotNone(endpoint1, "创建端点1失败")
        
        # 创建另一个端点并更新为禁用状态
        endpoint2 = self.create_test_endpoint(test_account['id'], test_role['id'])
        self.assertIsNotNone(endpoint2, "创建端点2失败")
        
        update_param = endpoint2.copy()
        update_param['status'] = 1
        endpoint2_disabled = self.endpoint_app.update_endpoint(update_param)
        self.assertIsNotNone(endpoint2_disabled, "更新端点2状态失败")
        
        # 过滤启用状态的端点
        filter_param = {'status': 2}
        filtered_endpoints = self.endpoint_app.filter_endpoint(filter_param)
        self.assertIsNotNone(filtered_endpoints, "按状态过滤端点失败")
        
        # 验证过滤结果包含启用状态的端点
        found_enabled = False
        for ep in filtered_endpoints:
            if ep['id'] == endpoint1['id']:
                found_enabled = True
                self.assertEqual(ep['status'], 2, "端点状态不匹配")
                break
        self.assertTrue(found_enabled, "未找到启用状态的端点")
    
    def test_etc015_filter_endpoint_by_time_range(self):
        """E-TC-015: 过滤端点(按时间范围)"""
        test_role = self.create_test_role()
        self.assertIsNotNone(test_role, "创建测试角色失败")
        test_account = self.create_test_account(test_role['id'])
        self.assertIsNotNone(test_account, "创建测试账户失败")
        
        current_time_ms = int(dt.time() * 1000)
        
        # 创建在当前时间范围内的端点
        param = {
            'name': common.word(),
            'description': common.sentence(),
            'account': {
                'id': test_account['id'],
                'account': test_account['account'],
                'status': test_account.get('status', 2)
            },
            'role': {
                'id': test_role['id'],
                'name': test_role['name'],
                'status': test_role.get('status', 2)
            },
            'scope': '*',
            'status': 2,
            'startTime': current_time_ms - 7200000,  # 2小时前
            'expireTime': current_time_ms + 43200000  # 12小时后
        }
        
        endpoint = self.endpoint_app.create_endpoint(param)
        self.assertIsNotNone(endpoint, "创建端点失败")
        if endpoint and 'id' in endpoint:
            self.created_endpoint_ids.append(endpoint['id'])
        
        # 按时间范围过滤
        filter_param = {
            'startTime': current_time_ms - 86400000,  # 1天前
            'expireTime': current_time_ms + 86400000   # 1天后
        }
        filtered_endpoints = self.endpoint_app.filter_endpoint(filter_param)
        self.assertIsNotNone(filtered_endpoints, "按时间范围过滤端点失败")


if __name__ == '__main__':
    unittest.main()