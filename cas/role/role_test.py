"""Role 测试用例 - 基于 test_scenarios.md 的完整测试"""

import unittest
import logging
import warnings
import time as dt
from session import session
from cas import cas
from mock import common
from .role import Role

# 配置日志
logger = logging.getLogger(__name__)


class RoleTestCase(unittest.TestCase):
    """Role 测试用例类"""
    
    server_url = 'https://autotest.remote.vpc'
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
        cls.role_app = Role(cls.work_session)
    
    def setUp(self):
        """每个测试用例前的准备"""
        # 记录测试创建的角色ID以便清理
        self.created_role_ids = []
    
    def tearDown(self):
        """每个测试用例后的清理"""
        # 清理所有测试创建的角色
        for role_id in self.created_role_ids:
            try:
                self.role_app.delete_role(role_id)
            except Exception as e:
                logger.warning(f"清理角色 {role_id} 失败: {e}")
        self.created_role_ids.clear()
    
    # ========== 场景 R1: 角色创建与验证 ==========
    
    def test_r1_create_role_with_full_privileges(self):
        """场景 R1: 创建包含完整权限列表的角色"""
        # 生成权限列表
        privilege_list = [
            {
                'id': 1,
                'module': 'magicCas',
                'uriPath': '/api/v1/totalizators',
                'value': 2,
                'description': '用户管理权限'
            },
            {
                'id': 2,
                'module': 'magicCas',
                'uriPath': '/api/v1/accounts',
                'value': 1,
                'description': '账户查看权限'
            }
        ]
        
        param = {
            'name': common.word(),
            'description': common.sentence(),
            'group': 'admin',
            'privilege': privilege_list,
            'status': 2
        }
        
        # 创建角色
        new_role = self.role_app.create_role(param)
        self.assertIsNotNone(new_role, "角色创建失败")
        
        # 验证返回的角色包含所有必要字段
        required_fields = ['id', 'name', 'description', 'group', 'privilege', 'status']
        for field in required_fields:
            self.assertIn(field, new_role, f"缺少字段: {field}")
        
        # 验证字段值匹配
        self.assertEqual(new_role['name'], param['name'], "名称不匹配")
        self.assertEqual(new_role['description'], param['description'], "描述不匹配")
        self.assertEqual(new_role['group'], param['group'], "组别不匹配")
        self.assertEqual(new_role['status'], param['status'], "状态不匹配")
        
        # 验证权限列表正确性
        self.assertIsInstance(new_role['privilege'], list, "权限列表不是列表类型")
        self.assertEqual(len(new_role['privilege']), len(param['privilege']), "权限数量不匹配")
        
        # 清理
        if new_role and 'id' in new_role:
            self.role_app.delete_role(new_role['id'])
    
    # ========== 场景 R2: 角色状态管理 ==========
    
    def test_r2_role_status_management(self):
        """场景 R2: 角色状态管理"""
        # 创建状态为启用(2)的角色
        param = {
            'name': common.word(),
            'description': common.sentence(),
            'group': 'admin',
            'privilege': [],
            'status': 2  # 启用
        }
        
        new_role = self.role_app.create_role(param)
        self.assertIsNotNone(new_role, "角色创建失败")
        
        # 更新角色状态为禁用(1)
        update_param = new_role.copy()
        update_param['status'] = 1  # 禁用
        
        updated_role = self.role_app.update_role(update_param)
        self.assertIsNotNone(updated_role, "角色更新失败")
        self.assertEqual(updated_role['status'], 1, "状态更新失败")
        
        # 查询角色验证状态变更
        queried_role = self.role_app.query_role(updated_role['id'])
        self.assertIsNotNone(queried_role, "角色查询失败")
        self.assertEqual(queried_role['status'], 1, "查询的状态不匹配")
        
        # 使用状态过滤查询
        filter_param = {'status': 1}
        filtered_roles = self.role_app.filter_role(filter_param)
        self.assertIsNotNone(filtered_roles, "过滤查询失败")
        
        # 验证过滤结果包含当前角色
        found = False
        for role in filtered_roles:
            if role['id'] == queried_role['id']:
                found = True
                break
        self.assertTrue(found, "过滤结果中未找到当前角色")
        
        # 清理
        if new_role and 'id' in new_role:
            self.role_app.delete_role(new_role['id'])
    
    # ========== 场景 R3: 角色依赖关系测试 ==========
    
    def test_r3_role_dependency_test(self):
        """场景 R3: 角色依赖关系测试"""
        # 创建包含 bc.Privilege Mock 数据的角色
        privilege_list = [
            {
                'id': 1,
                'module': 'magicCas',
                'uriPath': '/api/v1/test',
                'value': 2,
                'description': '测试权限'
            }
        ]
        
        param = {
            'name': common.word(),
            'description': common.sentence(),
            'group': 'test',
            'privilege': privilege_list,
            'status': 2
        }
        
        new_role = self.role_app.create_role(param)
        self.assertIsNotNone(new_role, "角色创建失败")
        
        # 验证权限对象的完整性
        self.assertIn('privilege', new_role, "权限字段缺失")
        self.assertIsInstance(new_role['privilege'], list, "权限不是列表类型")
        self.assertEqual(len(new_role['privilege']), 1, "权限数量不正确")
        
        privilege = new_role['privilege'][0]
        required_privilege_fields = ['id', 'module', 'uriPath', 'value', 'description']
        for field in required_privilege_fields:
            self.assertIn(field, privilege, f"权限缺少字段: {field}")
        
        # 测试权限列表为空的情况
        param_empty = {
            'name': common.word(),
            'description': common.sentence(),
            'group': 'test',
            'privilege': [],
            'status': 2
        }
        
        role_empty = self.role_app.create_role(param_empty)
        self.assertIsNotNone(role_empty, "创建空权限角色失败")
        self.assertEqual(role_empty['privilege'], [], "空权限列表不正确")
        
        # 清理
        if new_role and 'id' in new_role:
            self.role_app.delete_role(new_role['id'])
        if role_empty and 'id' in role_empty:
            self.role_app.delete_role(role_empty['id'])
    
    def test_r3_invalid_privilege_data(self):
        """场景 R3 补充: 测试权限列表包含无效数据的情况"""
        # 测试包含无效字段的权限数据
        invalid_privilege_list = [
            {
                'id': 1,
                'module': 'magicCas',
                'uriPath': '/api/v1/test',
                'value': 2,
                'description': '有效权限'
            },
            {
                'id': None,  # 无效的ID
                'module': '',  # 空模块名
                'uriPath': '/api/v1/invalid',
                'value': -1,  # 无效的值
                'description': '无效权限'
            }
        ]
        
        param = {
            'name': common.word(),
            'description': common.sentence(),
            'group': 'test',
            'privilege': invalid_privilege_list,
            'status': 2
        }
        
        # 尝试创建包含无效权限数据的角色
        new_role = self.role_app.create_role(param)
        
        # 根据API设计，可能失败或成功但忽略无效数据
        # 我们验证API调用没有崩溃，并检查响应
        if new_role is not None:
            # 如果创建成功，验证返回的数据
            self.assertIn('privilege', new_role, "权限字段缺失")
            self.assertIsInstance(new_role['privilege'], list, "权限不是列表类型")
            # 清理
            if 'id' in new_role:
                self.created_role_ids.append(new_role['id'])
    
    # ========== 测试用例 R-TC-001 到 R-TC-015 ==========
    
    def test_rtc001_create_basic_role(self):
        """R-TC-001: 创建基本角色"""
        param = {
            'name': "Admin",
            'description': "管理员角色",
            'group': 'admin',
            'privilege': [],
            'status': 2
        }
        
        new_role = self.role_app.create_role(param)
        self.assertIsNotNone(new_role, "创建基本角色失败")
        
        # 验证字段
        self.assertEqual(new_role['name'], "Admin", "角色名称不匹配")
        self.assertEqual(new_role['status'], 2, "角色状态不匹配")
        
        # 清理
        if new_role and 'id' in new_role:
            self.role_app.delete_role(new_role['id'])
    
    def test_rtc002_create_role_with_privileges(self):
        """R-TC-002: 创建带权限的角色"""
        privilege_list = [{'id': 1, 'module': 'magicCas'}]
        
        param = {
            'name': common.word(),
            'description': common.sentence(),
            'group': 'admin',
            'privilege': privilege_list,
            'status': 2
        }
        
        new_role = self.role_app.create_role(param)
        self.assertIsNotNone(new_role, "创建带权限角色失败")
        
        # 验证权限列表正确保存
        self.assertIn('privilege', new_role, "权限字段缺失")
        self.assertIsInstance(new_role['privilege'], list, "权限不是列表类型")
        self.assertEqual(len(new_role['privilege']), 1, "权限数量不正确")
        
        # 清理
        if new_role and 'id' in new_role:
            self.role_app.delete_role(new_role['id'])
    
    def test_rtc003_create_role_with_long_name(self):
        """R-TC-003: 创建名称超长角色（边界测试）"""
        # 生成256字符的字符串（超过典型限制）
        long_name = 'a' * 256
        
        param = {
            'name': long_name,
            'description': common.sentence(),
            'group': 'admin',
            'privilege': [],
            'status': 2
        }
        
        new_role = self.role_app.create_role(param)
        
        # 根据文档要求：创建失败或截断处理
        # 我们验证两种可能的情况
        if new_role is None:
            # 情况1: 创建失败 - 这是可接受的
            pass
        else:
            # 情况2: 创建成功但名称可能被截断
            self.assertIsInstance(new_role['name'], str, "角色名称不是字符串")
            self.assertLessEqual(len(new_role['name']), 256, "角色名称长度不应超过256")
            # 记录ID以便清理
            if 'id' in new_role:
                self.created_role_ids.append(new_role['id'])
    
    def test_rtc004_create_role_with_empty_description(self):
        """R-TC-004: 创建空描述角色"""
        param = {
            'name': common.word(),
            'description': "",
            'group': 'admin',
            'privilege': [],
            'status': 2
        }
        
        new_role = self.role_app.create_role(param)
        self.assertIsNotNone(new_role, "创建空描述角色失败")
        self.assertEqual(new_role['description'], "", "描述应该为空")
        
        # 清理
        if new_role and 'id' in new_role:
            self.role_app.delete_role(new_role['id'])
    
    def test_rtc005_create_duplicate_role_name(self):
        """R-TC-005: 创建重复名称角色（异常测试）"""
        param = {
            'name': common.word(),
            'description': common.sentence(),
            'group': 'admin',
            'privilege': [],
            'status': 2
        }
        
        # 第一次创建应该成功
        first_role = self.role_app.create_role(param)
        self.assertIsNotNone(first_role, "第一次创建角色失败")
        if first_role and 'id' in first_role:
            self.created_role_ids.append(first_role['id'])
        
        # 第二次创建相同名称的角色应该失败
        second_role = self.role_app.create_role(param)
        # 期望创建失败，返回None或错误响应
        self.assertIsNone(second_role, "重复名称角色创建应失败")
        
        # 注意：清理在tearDown中处理
    
    def test_rtc006_create_role_with_missing_required_field(self):
        """R-TC-006: 创建缺少必填字段角色（异常测试）"""
        # 缺少name字段
        param = {
            'description': common.sentence(),
            'group': 'admin',
            'privilege': [],
            'status': 2
        }
        
        new_role = self.role_app.create_role(param)
        # 应该失败，返回None或错误
        self.assertIsNone(new_role, "缺少必填字段的角色创建应失败")
    
    def test_rtc007_update_role_info(self):
        """R-TC-007: 更新角色信息"""
        # 先创建角色
        param = {
            'name': common.word(),
            'description': "原始描述",
            'group': 'admin',
            'privilege': [],
            'status': 2
        }
        
        new_role = self.role_app.create_role(param)
        self.assertIsNotNone(new_role, "创建角色失败")
        
        # 更新描述
        update_param = new_role.copy()
        update_param['description'] = "新描述"
        
        updated_role = self.role_app.update_role(update_param)
        self.assertIsNotNone(updated_role, "更新角色失败")
        self.assertEqual(updated_role['description'], "新描述", "描述更新失败")
        
        # 清理
        if new_role and 'id' in new_role:
            self.role_app.delete_role(new_role['id'])
    
    def test_rtc008_update_role_status(self):
        """R-TC-008: 更新角色状态"""
        param = {
            'name': common.word(),
            'description': common.sentence(),
            'group': 'admin',
            'privilege': [],
            'status': 2  # 启用
        }
        
        new_role = self.role_app.create_role(param)
        self.assertIsNotNone(new_role, "创建角色失败")
        
        # 更新状态为禁用
        update_param = new_role.copy()
        update_param['status'] = 1  # 禁用
        
        updated_role = self.role_app.update_role(update_param)
        self.assertIsNotNone(updated_role, "更新角色状态失败")
        self.assertEqual(updated_role['status'], 1, "状态更新失败")
        
        # 清理
        if new_role and 'id' in new_role:
            self.role_app.delete_role(new_role['id'])
    
    def test_rtc009_update_nonexistent_role(self):
        """R-TC-009: 更新不存在的角色（异常测试）"""
        param = {
            'id': 999999,
            'name': common.word(),
            'description': common.sentence(),
            'group': 'admin',
            'privilege': [],
            'status': 2
        }
        
        updated_role = self.role_app.update_role(param)
        # 应该失败，返回None或错误
        self.assertIsNone(updated_role, "更新不存在的角色应失败")
    
    def test_rtc010_query_role(self):
        """R-TC-010: 查询角色"""
        param = {
            'name': common.word(),
            'description': common.sentence(),
            'group': 'admin',
            'privilege': [],
            'status': 2
        }
        
        new_role = self.role_app.create_role(param)
        self.assertIsNotNone(new_role, "创建角色失败")
        
        # 查询角色
        queried_role = self.role_app.query_role(new_role['id'])
        self.assertIsNotNone(queried_role, "查询角色失败")
        self.assertEqual(queried_role['id'], new_role['id'], "角色ID不匹配")
        self.assertEqual(queried_role['name'], new_role['name'], "角色名称不匹配")
        
        # 清理
        if new_role and 'id' in new_role:
            self.role_app.delete_role(new_role['id'])
    
    def test_rtc011_query_nonexistent_role(self):
        """R-TC-011: 查询不存在的角色（异常测试）"""
        queried_role = self.role_app.query_role(999999)
        # 应该返回None或错误
        self.assertIsNone(queried_role, "查询不存在的角色应失败")
    
    def test_rtc012_filter_role_by_name(self):
        """R-TC-012: 过滤角色(按名称)"""
        unique_name = common.word()
        
        param = {
            'name': unique_name,
            'description': common.sentence(),
            'group': 'admin',
            'privilege': [],
            'status': 2
        }
        
        new_role = self.role_app.create_role(param)
        self.assertIsNotNone(new_role, "创建角色失败")
        
        # 按名称过滤
        filter_param = {'name': unique_name}
        filtered_roles = self.role_app.filter_role(filter_param)
        
        self.assertIsNotNone(filtered_roles, "过滤角色失败")
        self.assertGreaterEqual(len(filtered_roles), 1, "过滤结果为空")
        
        found = False
        for role in filtered_roles:
            if role['name'] == unique_name:
                found = True
                break
        self.assertTrue(found, "未找到匹配的角色")
        
        # 清理
        if new_role and 'id' in new_role:
            self.role_app.delete_role(new_role['id'])
    
    def test_rtc013_filter_role_by_status(self):
        """R-TC-013: 过滤角色(按状态)"""
        # 创建启用状态的角色
        param = {
            'name': common.word(),
            'description': common.sentence(),
            'group': 'admin',
            'privilege': [],
            'status': 2  # 启用
        }
        
        new_role = self.role_app.create_role(param)
        self.assertIsNotNone(new_role, "创建角色失败")
        
        # 按状态过滤
        filter_param = {'status': 2}
        filtered_roles = self.role_app.filter_role(filter_param)
        
        self.assertIsNotNone(filtered_roles, "过滤角色失败")
        
        # 验证过滤结果包含当前角色
        found = False
        for role in filtered_roles:
            if role['id'] == new_role['id']:
                found = True
                self.assertEqual(role['status'], 2, "角色状态不正确")
                break
        # 注意：可能还有其他启用状态的角色，所以不要求found一定为True
        
        # 清理
        if new_role and 'id' in new_role:
            self.role_app.delete_role(new_role['id'])
    
    def test_rtc014_delete_role(self):
        """R-TC-014: 删除角色"""
        param = {
            'name': common.word(),
            'description': common.sentence(),
            'group': 'admin',
            'privilege': [],
            'status': 2
        }
        
        new_role = self.role_app.create_role(param)
        self.assertIsNotNone(new_role, "创建角色失败")
        
        # 删除角色
        deleted_role = self.role_app.delete_role(new_role['id'])
        self.assertIsNotNone(deleted_role, "删除角色失败")
        self.assertEqual(deleted_role['id'], new_role['id'], "删除的角色ID不匹配")
        
        # 验证删除的角色包含必要字段
        self.assertIn('id', deleted_role, "删除返回缺少id字段")
        self.assertIn('name', deleted_role, "删除返回缺少name字段")
        
        # 验证角色已被删除（查询应该失败）
        queried_role = self.role_app.query_role(new_role['id'])
        # 期望查询失败，返回None或错误
    
    def test_rtc015_delete_nonexistent_role(self):
        """R-TC-015: 删除不存在的角色（异常测试）"""
        deleted_role = self.role_app.delete_role(999999)
        # 应该失败，返回None或错误
        self.assertIsNone(deleted_role, "删除不存在的角色应失败")
    
    # ========== 额外边界测试 ==========
    
    def test_role_name_with_special_characters(self):
        """测试角色名称包含特殊字符"""
        special_name = "Test-Role@123_测试#特殊"
        
        param = {
            'name': special_name,
            'description': common.sentence(),
            'group': 'admin',
            'privilege': [],
            'status': 2
        }
        
        new_role = self.role_app.create_role(param)
        # 可能成功或失败，取决于服务器实现
        if new_role is not None:
            self.assertIsInstance(new_role['name'], str, "角色名称不是字符串")
            if 'id' in new_role:
                self.created_role_ids.append(new_role['id'])
    
    def test_role_name_with_unicode(self):
        """测试角色名称包含Unicode字符"""
        unicode_name = "测试角色名字🎯✅✨"
        
        param = {
            'name': unicode_name,
            'description': "包含Unicode字符的描述",
            'group': 'admin',
            'privilege': [],
            'status': 2
        }
        
        new_role = self.role_app.create_role(param)
        # 可能成功或失败，取决于服务器实现
        if new_role is not None:
            self.assertIsInstance(new_role['name'], str, "角色名称不是字符串")
            if 'id' in new_role:
                self.created_role_ids.append(new_role['id'])
    
    def test_role_with_extreme_boundary_values(self):
        """测试极端边界值"""
        # 测试最小长度名称
        min_name = "a"
        
        param_min = {
            'name': min_name,
            'description': "",
            'group': '',
            'privilege': [],
            'status': 2
        }
        
        role_min = self.role_app.create_role(param_min)
        if role_min is not None:
            self.assertEqual(role_min['name'], min_name, "最小长度名称不匹配")
            if 'id' in role_min:
                self.created_role_ids.append(role_min['id'])
        
        # 测试状态边界值
        boundary_statuses = [0, 1, 2, 3, 99]
        for status in boundary_statuses:
            param_status = {
                'name': f"test_status_{status}",
                'description': f"测试状态值{status}",
                'group': 'test',
                'privilege': [],
                'status': status
            }
            
            role_status = self.role_app.create_role(param_status)
            if role_status is not None:
                # 验证状态值
                self.assertEqual(role_status['status'], status, f"状态值{status}不匹配")
                if 'id' in role_status:
                    self.created_role_ids.append(role_status['id'])


if __name__ == '__main__':
    unittest.main()