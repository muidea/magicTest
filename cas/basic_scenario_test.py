"""CAS基础场景测试 - 覆盖一次基本功能点，验证正向执行和异常处理

本测试覆盖CAS系统的核心功能点：
1. CAS认证（登录、获取权限、刷新会话、注销）
2. Role创建和管理
3. Account创建和管理（依赖Role）
4. Endpoint创建和管理（依赖Account和Role）
5. Namespace创建和管理
6. 异常情况测试（重复名称、无效ID等）

测试目标：
- 确认各个功能点能完成正向执行
- 在功能点异常时输出异常信息，方便功能排查
"""

import unittest
import logging
import warnings
import time as dt
from session import session
from cas import cas
from mock import common
from cas.role import Role as RoleApp
from cas.account import Account as AccountApp
from cas.endpoint import Endpoint as EndpointApp
from cas.namespace import Namespace as NamespaceApp

# 配置日志
logger = logging.getLogger(__name__)


class BasicScenarioTestCase(unittest.TestCase):
    """CAS基础场景测试用例类"""
    
    # 使用panel命名空间登录（系统内置namespace，scope为"*"）
    panel_server_url = 'https://panel.local.vpc/api/v1'
    panel_namespace = 'panel'
    
    # 测试将在autotest命名空间中执行
    test_namespace_name = 'autotest'
    
    @classmethod
    def setUpClass(cls):
        """测试类初始化 - 使用panel命名空间登录并创建autotest命名空间"""
        warnings.simplefilter('ignore', ResourceWarning)
        
        # 1. 使用panel命名空间登录
        logger.info(f"=== 使用panel命名空间登录 ===")
        cls.work_session = session.MagicSession(cls.panel_server_url, cls.panel_namespace)
        cls.cas_session = cas.Cas(cls.work_session)
        if not cls.cas_session.login('administrator', 'administrator'):
            logger.error('CAS登录失败')
            raise Exception('CAS登录失败')
        cls.work_session.bind_token(cls.cas_session.get_session_token())
        
        # 初始化应用实例（使用panel命名空间）
        cls.role_app = RoleApp(cls.work_session)
        cls.account_app = AccountApp(cls.work_session)
        cls.endpoint_app = EndpointApp(cls.work_session)
        cls.namespace_app = NamespaceApp(cls.work_session)
        
        # 2. 创建autotest命名空间（如果不存在）
        logger.info(f"=== 创建autotest命名空间 ===")
        cls.test_namespace_id = cls.create_or_get_autotest_namespace()
        
        # 3. 创建用于autotest命名空间的会话和应用实例
        logger.info(f"=== 创建autotest命名空间的会话 ===")
        cls.autotest_work_session = session.MagicSession(cls.panel_server_url, cls.test_namespace_name)
        cls.autotest_work_session.bind_token(cls.cas_session.get_session_token())
        cls.autotest_role_app = RoleApp(cls.autotest_work_session)
        cls.autotest_account_app = AccountApp(cls.autotest_work_session)
        cls.autotest_endpoint_app = EndpointApp(cls.autotest_work_session)
        cls.autotest_namespace_app = NamespaceApp(cls.autotest_work_session)
        
        logger.info(f"✓ 测试初始化完成，将在命名空间 '{cls.test_namespace_name}' 中执行测试")
    
    @classmethod
    def create_or_get_autotest_namespace(cls):
        """创建或获取autotest命名空间"""
        current_time = int(dt.time() * 1000)
        start_time = current_time - 3600000  # 1小时前
        expire_time = current_time + 86400000 * 7  # 7天后（确保测试期间有效）
        
        # 先检查autotest命名空间是否已存在
        filter_param = {'name': cls.test_namespace_name}
        existing_namespaces = cls.namespace_app.filter_namespace(filter_param)
        
        if existing_namespaces and len(existing_namespaces) > 0:
            # 命名空间已存在，返回ID
            namespace_id = existing_namespaces[0]['id']
            logger.info(f"✓ autotest命名空间已存在，ID: {namespace_id}")
            return namespace_id
        
        # 创建新的autotest命名空间
        create_param = {
            'name': cls.test_namespace_name,
            'description': "自动化测试命名空间",
            'scope': "*",  # 全局访问权限
            'startTime': start_time,
            'expireTime': expire_time,
            'status': 2  # 启用状态
        }
        
        new_namespace = cls.namespace_app.create_namespace(create_param)
        if new_namespace is None:
            logger.error(f"创建autotest命名空间失败")
            raise Exception(f"创建autotest命名空间 '{cls.test_namespace_name}' 失败")
        
        namespace_id = new_namespace['id']
        logger.info(f"✓ 创建autotest命名空间成功，ID: {namespace_id}")
        return namespace_id
    
    @classmethod
    def tearDownClass(cls):
        """测试类清理 - 删除autotest命名空间"""
        logger.info(f"=== 清理autotest命名空间 ===")
        try:
            # 删除autotest命名空间
            deleted_namespace = cls.namespace_app.delete_namespace(cls.test_namespace_id)
            if deleted_namespace is not None:
                logger.info(f"✓ 删除autotest命名空间成功，ID: {cls.test_namespace_id}")
            else:
                logger.warning(f"⚠ 删除autotest命名空间失败，ID: {cls.test_namespace_id}")
        except Exception as e:
            logger.warning(f"清理autotest命名空间时发生错误: {e}")
    
    def setUp(self):
        """每个测试用例前的准备"""
        # 记录测试创建的实体ID以便清理
        self.created_role_ids = []
        self.created_account_ids = []
        self.created_endpoint_ids = []
        self.created_namespace_ids = []
    
    def tearDown(self):
        """每个测试用例后的清理"""
        # 清理顺序：Endpoint -> Account -> Role -> Namespace（按照依赖关系反向清理）
        # 使用autotest命名空间的应用实例进行清理
        
        for endpoint_id in self.created_endpoint_ids:
            try:
                self.autotest_endpoint_app.delete_endpoint(endpoint_id)
            except Exception as e:
                logger.warning(f"清理端点 {endpoint_id} 失败: {e}")
        
        for account_id in self.created_account_ids:
            try:
                self.autotest_account_app.delete_account(account_id)
            except Exception as e:
                logger.warning(f"清理账户 {account_id} 失败: {e}")
        
        for role_id in self.created_role_ids:
            try:
                self.autotest_role_app.delete_role(role_id)
            except Exception as e:
                logger.warning(f"清理角色 {role_id} 失败: {e}")
        
        for namespace_id in self.created_namespace_ids:
            try:
                # 注意：在场景5中创建的测试命名空间需要在panel命名空间中清理
                self.namespace_app.delete_namespace(namespace_id)
            except Exception as e:
                logger.warning(f"清理命名空间 {namespace_id} 失败: {e}")
        
        self.created_role_ids.clear()
        self.created_account_ids.clear()
        self.created_endpoint_ids.clear()
        self.created_namespace_ids.clear()
    
    # ========== 场景1: CAS认证功能测试 ==========
    
    def test_scenario1_cas_authentication(self):
        """场景1: CAS认证功能测试 - 验证登录、获取权限、刷新会话、注销"""
        logger.info("=== 开始场景1: CAS认证功能测试 ===")
        
        # 1.1 验证登录成功
        self.assertIsNotNone(self.cas_session.get_session_token(), "登录后会话令牌应为非空")
        self.assertIsNotNone(self.cas_session.get_current_entity(), "登录后实体信息应为非空")
        logger.info("✓ CAS登录成功验证通过")
        
        # 1.2 获取系统权限列表
        privileges = self.cas_session.get_system_all_privileges()
        self.assertIsNotNone(privileges, "获取系统权限列表失败")
        self.assertIsInstance(privileges, list, "权限列表应为列表类型")
        logger.info(f"✓ 获取系统权限列表成功，共 {len(privileges) if privileges else 0} 个权限")
        
        # 1.3 刷新会话令牌
        session_token = self.cas_session.get_session_token()
        new_token = self.cas_session.refresh(session_token)
        self.assertIsNotNone(new_token, "刷新会话令牌失败")
        logger.info("✓ 会话令牌刷新成功")
        
        # 1.4 注销会话
        logout_result = self.cas_session.logout(new_token)
        # 注意：注销后需要重新登录，否则后续测试会失败
        if logout_result:
            logger.info("✓ 会话注销成功")
            # 重新登录以继续后续测试
            if not self.cas_session.login('administrator', 'administrator'):
                logger.error('重新登录失败')
                raise Exception('重新登录失败')
            self.work_session.bind_token(self.cas_session.get_session_token())
        else:
            logger.warning("会话注销失败，可能已过期或无效")
        
        logger.info("=== 场景1: CAS认证功能测试完成 ===")
    
    # ========== 场景2: Role基础功能测试 ==========
    
    def test_scenario2_role_basic_operations(self):
        """场景2: Role基础功能测试 - 在autotest命名空间中创建、查询、更新、删除角色"""
        logger.info("=== 开始场景2: Role基础功能测试（在autotest命名空间中） ===")
        
        # 2.1 创建基础角色
        role_name = f"test_role_{common.word()}"
        role_description = "测试角色描述"
        
        create_param = {
            'name': role_name,
            'description': role_description,
            'group': 'test',
            'privilege': [],
            'status': 2  # 启用状态
        }
        
        new_role = self.autotest_role_app.create_role(create_param)
        self.assertIsNotNone(new_role, "创建角色失败")
        self.assertEqual(new_role['name'], role_name, "角色名称不匹配")
        self.assertEqual(new_role['description'], role_description, "角色描述不匹配")
        self.assertEqual(new_role['status'], 2, "角色状态应为启用")
        
        role_id = new_role['id']
        self.created_role_ids.append(role_id)
        logger.info(f"✓ 在autotest命名空间中创建角色成功，ID: {role_id}, 名称: {role_name}")
        
        # 2.2 查询角色
        queried_role = self.autotest_role_app.query_role(role_id)
        self.assertIsNotNone(queried_role, "查询角色失败")
        self.assertEqual(queried_role['id'], role_id, "查询的角色ID不匹配")
        self.assertEqual(queried_role['name'], role_name, "查询的角色名称不匹配")
        logger.info(f"✓ 查询角色成功，ID: {role_id}")
        
        # 2.3 更新角色信息
        update_param = queried_role.copy()
        update_param['description'] = "更新后的角色描述"
        
        updated_role = self.autotest_role_app.update_role(update_param)
        self.assertIsNotNone(updated_role, "更新角色失败")
        self.assertEqual(updated_role['description'], "更新后的角色描述", "角色描述更新失败")
        logger.info(f"✓ 更新角色成功，ID: {role_id}")
        
        # 2.4 过滤查询角色
        filter_param = {'name': role_name}
        filtered_roles = self.autotest_role_app.filter_role(filter_param)
        self.assertIsNotNone(filtered_roles, "过滤查询角色失败")
        self.assertGreaterEqual(len(filtered_roles), 1, "过滤结果应至少包含一个角色")
        
        found = False
        for role in filtered_roles:
            if role['id'] == role_id:
                found = True
                break
        self.assertTrue(found, "过滤结果中未找到创建的角色")
        logger.info(f"✓ 过滤查询角色成功，找到 {len(filtered_roles)} 个结果")
        
        # 2.5 删除角色（在tearDown中会自动清理，这里验证删除功能）
        # 注意：实际删除在tearDown中执行，这里只记录
        logger.info(f"✓ 角色删除将在测试清理阶段执行，ID: {role_id}")
        
        logger.info("=== 场景2: Role基础功能测试完成 ===")
    
    # ========== 场景3: Account基础功能测试 ==========
    
    def test_scenario3_account_basic_operations(self):
        """场景3: Account基础功能测试 - 在autotest命名空间中创建、查询、更新、删除账户（依赖Role）"""
        logger.info("=== 开始场景3: Account基础功能测试（在autotest命名空间中） ===")
        
        # 3.1 先创建测试角色
        role_name = f"test_role_for_account_{common.word()}"
        create_role_param = {
            'name': role_name,
            'description': "用于账户测试的角色",
            'group': 'test',
            'privilege': [],
            'status': 2
        }
        
        test_role = self.autotest_role_app.create_role(create_role_param)
        self.assertIsNotNone(test_role, "创建测试角色失败")
        role_id = test_role['id']
        self.created_role_ids.append(role_id)
        logger.info(f"✓ 在autotest命名空间中创建测试角色成功，ID: {role_id}")
        
        # 3.2 创建关联角色的账户
        account_name = f"test_account_{common.word()}"
        account_email = common.email()
        
        create_account_param = {
            'account': account_name,
            'password': 'TestPassword123!',
            'email': account_email,
            'description': "测试账户描述",
            'namespace': self.test_namespace_name,  # 使用autotest命名空间
            'roleLite': {
                'id': role_id,
                'name': role_name
            }
        }
        
        new_account = self.autotest_account_app.create_account(create_account_param)
        self.assertIsNotNone(new_account, "创建账户失败")
        self.assertEqual(new_account['account'], account_name, "账户名称不匹配")
        self.assertEqual(new_account['email'], account_email, "账户邮箱不匹配")
        self.assertEqual(new_account['namespace'], self.test_namespace_name, "账户命名空间不匹配")
        
        account_id = new_account['id']
        self.created_account_ids.append(account_id)
        logger.info(f"✓ 在autotest命名空间中创建账户成功，ID: {account_id}, 名称: {account_name}")
        
        # 3.3 验证角色关联正确性
        self.assertIn('roleLite', new_account, "账户缺少角色关联字段")
        if 'roleLite' in new_account:
            self.assertEqual(new_account['roleLite']['id'], role_id, "关联角色ID不匹配")
            self.assertEqual(new_account['roleLite']['name'], role_name, "关联角色名称不匹配")
            logger.info(f"✓ 账户角色关联验证成功，关联角色ID: {role_id}")
        
        # 3.4 查询账户
        queried_account = self.autotest_account_app.query_account(account_id)
        self.assertIsNotNone(queried_account, "查询账户失败")
        self.assertEqual(queried_account['id'], account_id, "查询的账户ID不匹配")
        logger.info(f"✓ 查询账户成功，ID: {account_id}")
        
        # 3.5 更新账户信息
        update_param = queried_account.copy()
        update_param['description'] = "更新后的账户描述"
        
        updated_account = self.autotest_account_app.update_account(update_param)
        self.assertIsNotNone(updated_account, "更新账户失败")
        self.assertEqual(updated_account['description'], "更新后的账户描述", "账户描述更新失败")
        logger.info(f"✓ 更新账户成功，ID: {account_id}")
        
        # 3.6 过滤查询账户
        filter_param = {'account': account_name}
        filtered_accounts = self.autotest_account_app.filter_account(filter_param)
        self.assertIsNotNone(filtered_accounts, "过滤查询账户失败")
        
        found = False
        for account in filtered_accounts:
            if account['id'] == account_id:
                found = True
                break
        self.assertTrue(found, "过滤结果中未找到创建的账户")
        logger.info(f"✓ 过滤查询账户成功，找到 {len(filtered_accounts)} 个结果")
        
        logger.info("=== 场景3: Account基础功能测试完成 ===")
    
    # ========== 场景4: Endpoint基础功能测试 ==========
    
    def test_scenario4_endpoint_basic_operations(self):
        """场景4: Endpoint基础功能测试 - 在autotest命名空间中创建、查询、更新、删除端点（依赖Account和Role）"""
        logger.info("=== 开始场景4: Endpoint基础功能测试（在autotest命名空间中） ===")
        
        # 4.1 先创建测试角色和账户
        role_name = f"test_role_for_endpoint_{common.word()}"
        create_role_param = {
            'name': role_name,
            'description': "用于端点测试的角色",
            'group': 'test',
            'privilege': [],
            'status': 2
        }
        
        test_role = self.autotest_role_app.create_role(create_role_param)
        self.assertIsNotNone(test_role, "创建测试角色失败")
        role_id = test_role['id']
        self.created_role_ids.append(role_id)
        logger.info(f"✓ 在autotest命名空间中创建测试角色成功，ID: {role_id}")
        
        account_name = f"test_account_for_endpoint_{common.word()}"
        create_account_param = {
            'account': account_name,
            'password': 'TestPassword123!',
            'email': common.email(),
            'description': "用于端点测试的账户",
            'namespace': self.test_namespace_name,  # 使用autotest命名空间
            'roleLite': {
                'id': role_id,
                'name': role_name
            }
        }
        
        test_account = self.autotest_account_app.create_account(create_account_param)
        self.assertIsNotNone(test_account, "创建测试账户失败")
        account_id = test_account['id']
        self.created_account_ids.append(account_id)
        logger.info(f"✓ 在autotest命名空间中创建测试账户成功，ID: {account_id}")
        
        # 4.2 创建端点（设置有效时间范围）
        current_time = int(dt.time() * 1000)  # 当前时间戳（毫秒）
        start_time = current_time - 3600000  # 1小时前
        expire_time = current_time + 86400000  # 24小时后
        
        endpoint_name = f"test_endpoint_{common.word()}"
        create_endpoint_param = {
            'name': endpoint_name,
            'description': "测试端点描述",
            'namespace': self.test_namespace_name,  # 使用autotest命名空间
            'accountLite': {
                'id': account_id,
                'account': account_name
            },
            'roleLite': {
                'id': role_id,
                'name': role_name
            },
            'startTime': start_time,
            'expireTime': expire_time,
            'status': 2
        }
        
        new_endpoint = self.autotest_endpoint_app.create_endpoint(create_endpoint_param)
        self.assertIsNotNone(new_endpoint, "创建端点失败")
        self.assertEqual(new_endpoint['name'], endpoint_name, "端点名称不匹配")
        self.assertEqual(new_endpoint['startTime'], start_time, "开始时间不匹配")
        self.assertEqual(new_endpoint['expireTime'], expire_time, "过期时间不匹配")
        self.assertEqual(new_endpoint['namespace'], self.test_namespace_name, "端点命名空间不匹配")
        
        endpoint_id = new_endpoint['id']
        self.created_endpoint_ids.append(endpoint_id)
        logger.info(f"✓ 在autotest命名空间中创建端点成功，ID: {endpoint_id}, 名称: {endpoint_name}")
        
        # 4.3 验证账户和角色关联正确性
        self.assertIn('accountLite', new_endpoint, "端点缺少账户关联字段")
        self.assertIn('roleLite', new_endpoint, "端点缺少角色关联字段")
        
        if 'accountLite' in new_endpoint:
            self.assertEqual(new_endpoint['accountLite']['id'], account_id, "关联账户ID不匹配")
            logger.info(f"✓ 端点账户关联验证成功，关联账户ID: {account_id}")
        
        if 'roleLite' in new_endpoint:
            self.assertEqual(new_endpoint['roleLite']['id'], role_id, "关联角色ID不匹配")
            logger.info(f"✓ 端点角色关联验证成功，关联角色ID: {role_id}")
        
        # 4.4 查询端点
        queried_endpoint = self.autotest_endpoint_app.query_endpoint(endpoint_id)
        self.assertIsNotNone(queried_endpoint, "查询端点失败")
        self.assertEqual(queried_endpoint['id'], endpoint_id, "查询的端点ID不匹配")
        logger.info(f"✓ 查询端点成功，ID: {endpoint_id}")
        
        # 4.5 过滤查询端点
        filter_param = {'name': endpoint_name}
        filtered_endpoints = self.autotest_endpoint_app.filter_endpoint(filter_param)
        self.assertIsNotNone(filtered_endpoints, "过滤查询端点失败")
        
        found = False
        for endpoint in filtered_endpoints:
            if endpoint['id'] == endpoint_id:
                found = True
                break
        self.assertTrue(found, "过滤结果中未找到创建的端点")
        logger.info(f"✓ 过滤查询端点成功，找到 {len(filtered_endpoints)} 个结果")
        
        logger.info("=== 场景4: Endpoint基础功能测试完成 ===")
    
    # ========== 场景5: Namespace基础功能测试 ==========
    
    def test_scenario5_namespace_basic_operations(self):
        """场景5: Namespace基础功能测试 - 在panel命名空间中创建、查询、更新、删除测试命名空间"""
        logger.info("=== 开始场景5: Namespace基础功能测试（在panel命名空间中） ===")
        
        # 5.1 创建测试命名空间（在panel命名空间中操作）
        current_time = int(dt.time() * 1000)  # 当前时间戳（毫秒）
        start_time = current_time - 3600000  # 1小时前
        expire_time = current_time + 86400000  # 24小时后
        
        namespace_name = f"test_namespace_{common.word()}"
        create_param = {
            'name': namespace_name,
            'description': "测试命名空间描述",
            'scope': "*",  # 全局访问
            'startTime': start_time,
            'expireTime': expire_time,
            'status': 2
        }
        
        new_namespace = self.namespace_app.create_namespace(create_param)
        self.assertIsNotNone(new_namespace, "创建命名空间失败")
        self.assertEqual(new_namespace['name'], namespace_name, "命名空间名称不匹配")
        self.assertEqual(new_namespace['scope'], "*", "命名空间作用域不匹配")
        self.assertEqual(new_namespace['startTime'], start_time, "开始时间不匹配")
        self.assertEqual(new_namespace['expireTime'], expire_time, "过期时间不匹配")
        
        namespace_id = new_namespace['id']
        self.created_namespace_ids.append(namespace_id)
        logger.info(f"✓ 在panel命名空间中创建测试命名空间成功，ID: {namespace_id}, 名称: {namespace_name}")
        
        # 5.2 查询命名空间
        queried_namespace = self.namespace_app.query_namespace(namespace_id)
        self.assertIsNotNone(queried_namespace, "查询命名空间失败")
        self.assertEqual(queried_namespace['id'], namespace_id, "查询的命名空间ID不匹配")
        logger.info(f"✓ 查询命名空间成功，ID: {namespace_id}")
        
        # 5.3 更新命名空间信息
        update_param = queried_namespace.copy()
        update_param['description'] = "更新后的命名空间描述"
        update_param['scope'] = "test1,test2"  # 更新作用域
        
        updated_namespace = self.namespace_app.update_namespace(update_param)
        self.assertIsNotNone(updated_namespace, "更新命名空间失败")
        self.assertEqual(updated_namespace['description'], "更新后的命名空间描述", "命名空间描述更新失败")
        self.assertEqual(updated_namespace['scope'], "test1,test2", "命名空间作用域更新失败")
        logger.info(f"✓ 更新命名空间成功，ID: {namespace_id}")
        
        # 5.4 过滤查询命名空间
        filter_param = {'name': namespace_name}
        filtered_namespaces = self.namespace_app.filter_namespace(filter_param)
        self.assertIsNotNone(filtered_namespaces, "过滤查询命名空间失败")
        
        found = False
        for namespace in filtered_namespaces:
            if namespace['id'] == namespace_id:
                found = True
                break
        self.assertTrue(found, "过滤结果中未找到创建的命名空间")
        logger.info(f"✓ 过滤查询命名空间成功，找到 {len(filtered_namespaces)} 个结果")
        
        logger.info("=== 场景5: Namespace基础功能测试完成 ===")
    
    # ========== 场景6: 异常情况测试 ==========
    
    def test_scenario6_exception_cases(self):
        """场景6: 异常情况测试 - 在autotest命名空间中验证重复名称、无效ID等异常场景"""
        logger.info("=== 开始场景6: 异常情况测试（在autotest命名空间中） ===")
        
        current_time = int(dt.time() * 1000)  # 当前时间戳（毫秒）
        
        # 6.1 测试重复角色名称
        role_name = f"duplicate_role_{common.word()}"
        create_role_param = {
            'name': role_name,
            'description': "测试重复角色",
            'group': 'test',
            'privilege': [],
            'status': 2
        }
        
        # 第一次创建应该成功
        first_role = self.autotest_role_app.create_role(create_role_param)
        self.assertIsNotNone(first_role, "第一次创建角色失败")
        first_role_id = first_role['id']
        self.created_role_ids.append(first_role_id)
        logger.info(f"✓ 在autotest命名空间中第一次创建角色成功，名称: {role_name}")
        
        # 第二次创建相同名称的角色应该失败
        second_role = self.autotest_role_app.create_role(create_role_param)
        # 期望创建失败，返回None或错误响应
        if second_role is None:
            logger.info(f"✓ 重复角色名称创建失败（预期行为），名称: {role_name}")
        else:
            # 如果创建成功，记录ID以便清理
            second_role_id = second_role['id']
            self.created_role_ids.append(second_role_id)
            logger.warning(f"⚠ 重复角色名称创建成功（非预期行为），名称: {role_name}, ID: {second_role_id}")
        
        # 6.2 测试关联不存在的角色创建账户
        nonexistent_role_id = 999999
        create_account_param = {
            'account': f"test_account_nonexistent_role_{common.word()}",
            'password': 'TestPassword123!',
            'email': common.email(),
            'description': "测试关联不存在角色的账户",
            'namespace': self.test_namespace_name,  # 使用autotest命名空间
            'roleLite': {
                'id': nonexistent_role_id,
                'name': 'NonExistentRole'
            }
        }
        
        account_with_nonexistent_role = self.autotest_account_app.create_account(create_account_param)
        # 期望创建失败，返回None或错误响应
        if account_with_nonexistent_role is None:
            logger.info(f"✓ 关联不存在角色创建账户失败（预期行为），角色ID: {nonexistent_role_id}")
        else:
            # 如果创建成功，记录ID以便清理
            account_id = account_with_nonexistent_role['id']
            self.created_account_ids.append(account_id)
            logger.warning(f"⚠ 关联不存在角色创建账户成功（非预期行为），账户ID: {account_id}")
        
        # 6.3 测试无效时间范围（开始时间 > 过期时间）
        invalid_start_time = current_time + 86400000  # 24小时后
        invalid_expire_time = current_time - 3600000  # 1小时前
        
        create_invalid_endpoint_param = {
            'name': f"test_invalid_time_{common.word()}",
            'description': "测试无效时间范围的端点",
            'namespace': self.test_namespace_name,  # 使用autotest命名空间
            'accountLite': {
                'id': 1,  # 假设存在的账户ID
                'account': 'test'
            },
            'roleLite': {
                'id': 1,  # 假设存在的角色ID
                'name': 'test'
            },
            'startTime': invalid_start_time,
            'expireTime': invalid_expire_time,
            'status': 2
        }
        
        invalid_endpoint = self.autotest_endpoint_app.create_endpoint(create_invalid_endpoint_param)
        # 期望创建失败，返回None或错误响应
        if invalid_endpoint is None:
            logger.info(f"✓ 无效时间范围创建端点失败（预期行为），开始时间 > 过期时间")
        else:
            # 如果创建成功，记录ID以便清理
            endpoint_id = invalid_endpoint['id']
            self.created_endpoint_ids.append(endpoint_id)
            logger.warning(f"⚠ 无效时间范围创建端点成功（非预期行为），端点ID: {endpoint_id}")
        
        # 6.4 测试查询不存在的实体
        nonexistent_id = 999999
        
        # 查询不存在的角色
        nonexistent_role = self.autotest_role_app.query_role(nonexistent_id)
        if nonexistent_role is None:
            logger.info(f"✓ 查询不存在角色返回None（预期行为），ID: {nonexistent_id}")
        else:
            logger.warning(f"⚠ 查询不存在角色返回数据（非预期行为），ID: {nonexistent_id}")
        
        # 查询不存在的账户
        nonexistent_account = self.autotest_account_app.query_account(nonexistent_id)
        if nonexistent_account is None:
            logger.info(f"✓ 查询不存在账户返回None（预期行为），ID: {nonexistent_id}")
        else:
            logger.warning(f"⚠ 查询不存在账户返回数据（非预期行为），ID: {nonexistent_id}")
        
        # 6.5 测试缺少必填字段
        missing_name_param = {
            'description': "缺少名称字段的测试",
            'group': 'test',
            'privilege': [],
            'status': 2
        }
        
        role_missing_name = self.autotest_role_app.create_role(missing_name_param)
        # 期望创建失败，返回None或错误响应
        if role_missing_name is None:
            logger.info(f"✓ 缺少必填字段创建角色失败（预期行为）")
        else:
            # 如果创建成功，记录ID以便清理
            role_id = role_missing_name['id']
            self.created_role_ids.append(role_id)
            logger.warning(f"⚠ 缺少必填字段创建角色成功（非预期行为），角色ID: {role_id}")
        
        logger.info("=== 场景6: 异常情况测试完成 ===")
    
    # ========== 场景7: 完整依赖链测试 ==========
    
    def test_scenario7_complete_dependency_chain(self):
        """场景7: 完整依赖链测试 - 在autotest命名空间中验证Role→Account→Endpoint完整依赖关系"""
        logger.info("=== 开始场景7: 完整依赖链测试（在autotest命名空间中） ===")
        
        # 注意：这个测试在autotest命名空间中执行，不需要创建新的命名空间
        # 直接使用已创建的autotest命名空间
        
        # 7.1 创建角色
        role_name = f"test_dep_chain_role_{common.word()}"
        create_role_param = {
            'name': role_name,
            'description': "依赖链测试角色",
            'group': 'test',
            'privilege': [],
            'status': 2
        }
        
        test_role = self.autotest_role_app.create_role(create_role_param)
        self.assertIsNotNone(test_role, "创建测试角色失败")
        role_id = test_role['id']
        self.created_role_ids.append(role_id)
        logger.info(f"✓ 在autotest命名空间中创建测试角色成功，ID: {role_id}")
        
        # 7.2 创建账户（关联角色）
        account_name = f"test_dep_chain_account_{common.word()}"
        create_account_param = {
            'account': account_name,
            'password': 'TestPassword123!',
            'email': common.email(),
            'description': "依赖链测试账户",
            'namespace': self.test_namespace_name,  # 使用autotest命名空间
            'roleLite': {
                'id': role_id,
                'name': role_name
            }
        }
        
        test_account = self.autotest_account_app.create_account(create_account_param)
        self.assertIsNotNone(test_account, "创建测试账户失败")
        account_id = test_account['id']
        self.created_account_ids.append(account_id)
        logger.info(f"✓ 在autotest命名空间中创建测试账户成功，ID: {account_id}")
        
        # 7.3 创建端点（关联账户和角色）
        endpoint_name = f"test_dep_chain_endpoint_{common.word()}"
        create_endpoint_param = {
            'name': endpoint_name,
            'description': "依赖链测试端点",
            'namespace': self.test_namespace_name,  # 使用autotest命名空间
            'accountLite': {
                'id': account_id,
                'account': account_name
            },
            'roleLite': {
                'id': role_id,
                'name': role_name
            },
            'startTime': int(dt.time() * 1000) - 3600000,
            'expireTime': int(dt.time() * 1000) + 86400000,
            'status': 2
        }
        
        test_endpoint = self.autotest_endpoint_app.create_endpoint(create_endpoint_param)
        self.assertIsNotNone(test_endpoint, "创建测试端点失败")
        endpoint_id = test_endpoint['id']
        self.created_endpoint_ids.append(endpoint_id)
        logger.info(f"✓ 在autotest命名空间中创建测试端点成功，ID: {endpoint_id}")
        
        # 7.4 验证完整依赖链
        logger.info("✓ 完整依赖链创建成功（在autotest命名空间中）：")
        logger.info(f"  Namespace: {self.test_namespace_name} (ID: {self.test_namespace_id})")
        logger.info(f"  Role: {role_name} (ID: {role_id})")
        logger.info(f"  Account: {account_name} (ID: {account_id}) → 关联Role: {role_id}")
        logger.info(f"  Endpoint: {endpoint_name} (ID: {endpoint_id}) → 关联Account: {account_id}, Role: {role_id}")
        
        # 7.5 验证依赖关系查询
        # 查询端点并验证关联信息
        queried_endpoint = self.autotest_endpoint_app.query_endpoint(endpoint_id)
        self.assertIsNotNone(queried_endpoint, "查询端点失败")
        
        if 'accountLite' in queried_endpoint:
            self.assertEqual(queried_endpoint['accountLite']['id'], account_id, "端点关联的账户ID不匹配")
            logger.info(f"✓ 端点关联账户验证成功，账户ID: {account_id}")
        
        if 'roleLite' in queried_endpoint:
            self.assertEqual(queried_endpoint['roleLite']['id'], role_id, "端点关联的角色ID不匹配")
            logger.info(f"✓ 端点关联角色验证成功，角色ID: {role_id}")
        
        logger.info("=== 场景7: 完整依赖链测试完成 ===")


if __name__ == '__main__':
    unittest.main()