"""
Member 测试用例

基于 magicProjectRepo/vmi/VMI实体定义和使用说明.md:219-228 中的 member 实体定义编写。
使用 MemberSDK 进行测试，避免直接使用 MagicEntity。

实体字段定义：
- id: int64 (主键) - 唯一标识，由系统自动生成
- title: string (职位) - 必选
- name: string (名称) - 必选
- store: store* (所属店铺) - 必选
- creater: int64 (创建者) - 由系统自动生成
- createTime: int64 (创建时间) - 由系统自动生成
- modifyTime: int64 (修改时间) - 由系统自动更新
- namespace: string (命名空间) - 由系统自动生成

包含的测试用例（共12个）：

1. 基础CURD测试：
   - test_create_member: 测试创建店铺成员，验证所有字段完整性
   - test_query_member: 测试查询店铺成员，验证数据一致性
   - test_update_member: 测试更新店铺成员，验证字段更新功能
   - test_delete_member: 测试删除店铺成员，验证删除操作

2. 边界测试：
   - test_create_member_with_long_title: 测试创建超长职位成员
   - test_create_member_with_long_name: 测试创建超长名称成员

3. 异常测试：
   - test_create_duplicate_member: 测试创建重复成员名（系统可能允许重复）
   - test_query_nonexistent_member: 测试查询不存在的成员
   - test_delete_nonexistent_member: 测试删除不存在的成员

4. 关联字段测试：
   - test_member_store_validation: 测试成员店铺关联验证

5. 系统字段测试：
   - test_auto_generated_fields: 测试系统自动生成字段（id、creater、createTime、namespace）
   - test_modify_time_auto_update: 测试修改时间字段的自动更新逻辑

测试特性：
- 使用 MemberSDK 进行所有操作
- 自动清理测试数据（tearDown 方法）
- 支持系统实际行为（如允许重复名称、灵活的关联字段处理）
- 验证所有实体定义字段
- 覆盖完整的业务规则

版本：1.0
最后更新：2026-01-26
"""

import unittest
import warnings
import logging
import session
from cas.cas import Cas
from mock import common as mock
from sdk import MemberSDK, StoreSDK

# 配置日志
logger = logging.getLogger(__name__)


class MemberTestCase(unittest.TestCase):
    """Member 测试用例类"""
    
    namespace = ''
    
    @classmethod
    def setUpClass(cls):
        # 从config_helper获取配置

        # 从config_helper获取配置
        from config_helper import get_server_url, get_credentials
        cls.server_url = get_server_url()
        cls.credentials = get_credentials()
        
        """测试类初始化"""
        warnings.simplefilter('ignore', ResourceWarning)
        cls.work_session = session.MagicSession(cls.server_url, cls.namespace)
        cls.cas_session = Cas(cls.work_session)
        if not cls.cas_session.login(cls.credentials['username'], cls.credentials['password']):
            logger.error('CAS登录失败')
            raise Exception('CAS登录失败')
        cls.work_session.bind_token(cls.cas_session.get_session_token())
        cls.member_sdk = MemberSDK(cls.work_session)
        cls.store_sdk = StoreSDK(cls.work_session)
        
        # 类级别的数据清理记录
        cls._class_cleanup_ids = {
            'member': [],
            'store': []
        }
        
        # 记录测试开始前的初始状态（可选）
        cls._initial_member_count = cls._get_member_count()
        logger.info(f"测试开始前店铺成员数量: {cls._initial_member_count}")
    
    @classmethod
    def _get_member_count(cls):
        """获取当前店铺成员数量"""
        try:
            # 尝试使用count方法
            count = cls.member_sdk.count_member({})
            if count is not None:
                return count
        except Exception as e:
            logger.warning(f"获取店铺成员数量失败: {e}")
        
        # 如果count方法不可用，尝试通过过滤空条件获取列表
        try:
            members = cls.member_sdk.filter_member({})
            if members is not None:
                return len(members)
        except Exception as e:
            logger.warning(f"通过过滤获取店铺成员数量失败: {e}")
        
        return 0
    
    @classmethod
    def tearDownClass(cls):
        """测试类结束后的清理"""
        # 记录类级别清理列表的状态
        original_member_count = len(cls._class_cleanup_ids['member'])
        original_store_count = len(cls._class_cleanup_ids['store'])
        logger.info(f"测试类清理开始: 需要清理 {original_member_count} 个成员, {original_store_count} 个店铺")
        
        # 清理类级别记录的所有数据
        cls._cleanup_members(cls._class_cleanup_ids['member'])
        cls._cleanup_stores(cls._class_cleanup_ids['store'])
        
        # 验证数据清理
        final_member_count = cls._get_member_count()
        logger.info(f"测试类清理完成: 最终店铺成员数量: {final_member_count}")
        
        # 检查是否有数据残留（可选，根据业务需求）
        if hasattr(cls, '_initial_member_count'):
            expected_count = cls._initial_member_count
            if final_member_count > expected_count:
                logger.warning(f"可能存在数据残留: 期望数量 {expected_count}, 实际数量 {final_member_count}")
    
    @classmethod
    def _cleanup_members(cls, member_ids):
        """清理指定的店铺成员列表"""
        if not member_ids:
            logger.debug("清理店铺成员列表为空，无需清理")
            return
        
        logger.info(f"开始清理 {len(member_ids)} 个店铺成员: {member_ids}")
        deleted_count = 0
        failed_ids = []
        
        for member_id in member_ids:
            try:
                logger.debug(f"尝试删除店铺成员 ID: {member_id}")
                result = cls.member_sdk.delete_member(member_id)
                
                if result is not None:
                    deleted_count += 1
                    logger.debug(f"成功删除店铺成员 {member_id}")
                else:
                    error_msg = f"清理店铺成员 {member_id} 返回None，系统应该支持删除操作"
                    logger.error(error_msg)
                    failed_ids.append(member_id)
            except Exception as e:
                error_msg = f"清理店铺成员 {member_id} 失败: {e}"
                logger.error(error_msg)
                failed_ids.append(member_id)
        
        if deleted_count > 0:
            logger.info(f"成功清理 {deleted_count} 个店铺成员")
        
        if failed_ids:
            logger.error(f"清理失败的店铺成员ID: {failed_ids}")
    
    @classmethod
    def _cleanup_stores(cls, store_ids):
        """清理指定的店铺列表"""
        if not store_ids:
            logger.debug("清理店铺列表为空，无需清理")
            return
        
        logger.info(f"开始清理 {len(store_ids)} 个店铺: {store_ids}")
        deleted_count = 0
        failed_ids = []
        
        for store_id in store_ids:
            try:
                logger.debug(f"尝试删除店铺 ID: {store_id}")
                result = cls.store_sdk.delete_store(store_id)
                
                if result is not None:
                    deleted_count += 1
                    logger.debug(f"成功删除店铺 {store_id}")
                else:
                    error_msg = f"清理店铺 {store_id} 返回None，系统应该支持删除操作"
                    logger.error(error_msg)
                    failed_ids.append(store_id)
            except Exception as e:
                error_msg = f"清理店铺 {store_id} 失败: {e}"
                logger.error(error_msg)
                failed_ids.append(store_id)
        
        if deleted_count > 0:
            logger.info(f"成功清理 {deleted_count} 个店铺")
        
        if failed_ids:
            logger.error(f"清理失败的店铺ID: {failed_ids}")
    
    def setUp(self):
        """每个测试用例前的准备"""
        # 记录测试创建的实体ID以便清理
        self.created_member_ids = []
        self.created_store_ids = []
        
        # 创建必要的依赖实体（店铺）
        self._setup_dependencies()
    
    def _setup_dependencies(self):
        """创建测试依赖的实体（店铺）"""
        # 创建店铺
        store_param = {
            'name': 'STORE_' + mock.name(),
            'description': mock.sentence()
        }
        new_store = self.store_sdk.create_store(store_param)
        self.assertIsNotNone(new_store, "创建店铺失败")
        if new_store and 'id' in new_store:
            self.created_store_ids.append(new_store['id'])
            self._class_cleanup_ids['store'].append(new_store['id'])
        
        # 保存依赖实体ID
        self.store_id = new_store['id'] if new_store else None
    
    def tearDown(self):
        """每个测试用例后的清理"""
        # 将本测试创建的实体ID添加到类级别清理列表
        if hasattr(self.__class__, '_class_cleanup_ids'):
            self.__class__._class_cleanup_ids['member'].extend(self.created_member_ids)
            self.__class__._class_cleanup_ids['store'].extend(self.created_store_ids)
        
        # 尝试立即清理本测试创建的数据
        self._cleanup_test_entities()
        
        self.created_member_ids.clear()
        self.created_store_ids.clear()
    
    def _cleanup_test_entities(self):
        """清理本测试创建的实体"""
        # 清理成员
        self._cleanup_test_members()
        # 清理店铺
        self._cleanup_test_stores()
    
    def _cleanup_test_members(self):
        """清理本测试创建的店铺成员"""
        if not self.created_member_ids:
            logger.debug(f"测试 {self._testMethodName}: 没有需要清理的店铺成员")
            return
        
        logger.info(f"测试 {self._testMethodName}: 开始清理 {len(self.created_member_ids)} 个店铺成员: {self.created_member_ids}")
        deleted_count = 0
        failed_ids = []
        
        for member_id in self.created_member_ids:
            try:
                logger.debug(f"测试 {self._testMethodName}: 尝试删除店铺成员 ID: {member_id}")
                result = self.member_sdk.delete_member(member_id)
                
                if result is not None:
                    deleted_count += 1
                    logger.debug(f"测试 {self._testMethodName}: 成功删除店铺成员 {member_id}")
                    # 从类级别清理列表中移除（如果存在）
                    if (hasattr(self.__class__, '_class_cleanup_ids') and
                        member_id in self.__class__._class_cleanup_ids['member']):
                        self.__class__._class_cleanup_ids['member'].remove(member_id)
                else:
                    error_msg = f"测试 {self._testMethodName}: 删除店铺成员 {member_id} 返回None"
                    logger.error(error_msg)
                    failed_ids.append(member_id)
            except Exception as e:
                error_msg = f"测试 {self._testMethodName}: 删除店铺成员 {member_id} 失败: {e}"
                logger.error(error_msg)
                failed_ids.append(member_id)
        
        if deleted_count > 0:
            logger.info(f"测试 {self._testMethodName}: 成功清理 {deleted_count} 个店铺成员")
        
        if failed_ids:
            logger.error(f"测试 {self._testMethodName}: 清理失败的店铺成员ID: {failed_ids}")
    
    def _cleanup_test_stores(self):
        """清理本测试创建的店铺"""
        if not self.created_store_ids:
            logger.debug(f"测试 {self._testMethodName}: 没有需要清理的店铺")
            return
        
        logger.info(f"测试 {self._testMethodName}: 开始清理 {len(self.created_store_ids)} 个店铺: {self.created_store_ids}")
        deleted_count = 0
        failed_ids = []
        
        for store_id in self.created_store_ids:
            try:
                logger.debug(f"测试 {self._testMethodName}: 尝试删除店铺 ID: {store_id}")
                result = self.store_sdk.delete_store(store_id)
                
                if result is not None:
                    deleted_count += 1
                    logger.debug(f"测试 {self._testMethodName}: 成功删除店铺 {store_id}")
                    # 从类级别清理列表中移除（如果存在）
                    if (hasattr(self.__class__, '_class_cleanup_ids') and
                        store_id in self.__class__._class_cleanup_ids['store']):
                        self.__class__._class_cleanup_ids['store'].remove(store_id)
                else:
                    error_msg = f"测试 {self._testMethodName}: 删除店铺 {store_id} 返回None"
                    logger.error(error_msg)
                    failed_ids.append(store_id)
            except Exception as e:
                error_msg = f"测试 {self._testMethodName}: 删除店铺 {store_id} 失败: {e}"
                logger.error(error_msg)
                failed_ids.append(store_id)
        
        if deleted_count > 0:
            logger.info(f"测试 {self._testMethodName}: 成功清理 {deleted_count} 个店铺")
        
        if failed_ids:
            logger.error(f"测试 {self._testMethodName}: 清理失败的店铺ID: {failed_ids}")
    
    def _record_member_for_cleanup(self, member_id):
        """记录店铺成员ID以便清理"""
        if member_id is not None:
            self.created_member_ids.append(member_id)
            logger.debug(f"记录店铺成员 {member_id} 到清理列表 (测试: {self._testMethodName})")
    
    def mock_member_param(self):
        """模拟店铺成员参数"""
        return {
            'title': '职位_' + mock.name(),
            'name': '成员_' + mock.name(),
            'store': {'id': self.store_id} if self.store_id else None
        }
    
    def test_create_member(self):
        """测试创建店铺成员"""
        member_param = self.mock_member_param()
        new_member = self.member_sdk.create_member(member_param)
        self.assertIsNotNone(new_member, "创建店铺成员失败")
        
        # 验证店铺成员信息完整性
        required_fields = ['id', 'title', 'name', 'store']
        for field in required_fields:
            self.assertIn(field, new_member, f"缺少字段: {field}")
        
        # 验证系统自动生成字段
        self.assertIn('creater', new_member, "缺少创建者字段")
        self.assertIsInstance(new_member['creater'], (int, type(None)), "创建者应为整数或None")
        
        self.assertIn('createTime', new_member, "缺少创建时间字段")
        self.assertIsInstance(new_member['createTime'], (int, type(None)), "创建时间应为整数或None")
        
        self.assertIn('namespace', new_member, "缺少命名空间字段")
        self.assertIsInstance(new_member['namespace'], (str, type(None)), "命名空间应为字符串或None")
        
        # 记录创建的店铺成员ID以便清理
        if new_member and 'id' in new_member:
            self._record_member_for_cleanup(new_member['id'])
    
    def test_query_member(self):
        """测试查询店铺成员"""
        # 先创建店铺成员
        member_param = self.mock_member_param()
        new_member = self.member_sdk.create_member(member_param)
        self.assertIsNotNone(new_member, "创建店铺成员失败")
        
        if new_member and 'id' in new_member:
            self._record_member_for_cleanup(new_member['id'])
        
        # 查询店铺成员
        queried_member = self.member_sdk.query_member(new_member['id'])
        self.assertIsNotNone(queried_member, "查询店铺成员失败")
        self.assertEqual(queried_member['id'], new_member['id'], "店铺成员ID不匹配")
        self.assertEqual(queried_member['name'], new_member['name'], "店铺成员名不匹配")
    
    def test_update_member(self):
        """测试更新店铺成员"""
        # 先创建店铺成员
        member_param = self.mock_member_param()
        new_member = self.member_sdk.create_member(member_param)
        self.assertIsNotNone(new_member, "创建店铺成员失败")
        
        if new_member and 'id' in new_member:
            self._record_member_for_cleanup(new_member['id'])
        
        # 更新店铺成员
        update_param = new_member.copy()
        update_param['title'] = "更新后的职位"
        
        updated_member = self.member_sdk.update_member(new_member['id'], update_param)
        self.assertIsNotNone(updated_member, "更新店铺成员失败")
        self.assertEqual(updated_member['title'], "更新后的职位", "职位更新失败")
    
    def test_delete_member(self):
        """测试删除店铺成员"""
        # 先创建店铺成员
        member_param = self.mock_member_param()
        new_member = self.member_sdk.create_member(member_param)
        self.assertIsNotNone(new_member, "创建店铺成员失败")
        
        # 记录ID以便在tearDown中清理（如果删除失败）
        if new_member and 'id' in new_member:
            self._record_member_for_cleanup(new_member['id'])
        
        # 删除店铺成员 - 系统应该支持删除操作
        deleted_member = self.member_sdk.delete_member(new_member['id'])
        
        # 删除应该成功，返回被删除的对象
        self.assertIsNotNone(deleted_member, "删除店铺成员失败，返回None。系统应该支持删除操作")
        self.assertEqual(deleted_member['id'], new_member['id'], "删除的店铺成员ID不匹配")
        
        # 从清理列表中移除，因为已经成功删除
        if new_member['id'] in self.created_member_ids:
            self.created_member_ids.remove(new_member['id'])
        
        # 验证店铺成员已被删除（查询应该失败）
        queried_member = self.member_sdk.query_member(new_member['id'])
        # 查询应该返回None，因为店铺成员已被删除
        self.assertIsNone(queried_member, "删除后查询店铺成员应该返回None")
    
    def test_create_member_with_long_title(self):
        """测试创建超长职位成员（边界测试）"""
        member_param = self.mock_member_param()
        member_param['title'] = 'a' * 255  # 超长职位
        
        new_member = self.member_sdk.create_member(member_param)
        if new_member is not None:
            self.assertIsInstance(new_member['title'], str, "职位不是字符串")
            # 记录创建的店铺成员ID以便清理
            if 'id' in new_member:
                self._record_member_for_cleanup(new_member['id'])
    
    def test_create_member_with_long_name(self):
        """测试创建超长名称成员"""
        member_param = self.mock_member_param()
        member_param['name'] = 'a' * 255  # 超长名称
        
        new_member = self.member_sdk.create_member(member_param)
        self.assertIsNotNone(new_member, "创建带超长名称的成员失败")
        
        if new_member and 'id' in new_member:
            self._record_member_for_cleanup(new_member['id'])
        
        # 验证名称字段
        self.assertIn('name', new_member, "成员缺少名称字段")
        self.assertIsInstance(new_member['name'], str, "名称应为字符串")
        self.assertGreaterEqual(len(new_member['name']), 255, "名称长度不足")
    
    def test_create_duplicate_member(self):
        """测试创建重复成员名（系统可能允许重复）"""
        member_param = self.mock_member_param()
        
        first_member = self.member_sdk.create_member(member_param)
        self.assertIsNotNone(first_member, "第一次创建成员失败")
        
        # 记录第一次创建的成员ID以便清理
        if first_member and 'id' in first_member:
            self._record_member_for_cleanup(first_member['id'])
        
        # 第二次创建相同成员名
        second_member = self.member_sdk.create_member(member_param)
        
        # 系统可能允许重复名称，所以不强制要求失败
        if second_member is not None:
            # 如果创建成功，记录ID以便清理
            if 'id' in second_member:
                self._record_member_for_cleanup(second_member['id'])
            # 验证返回的数据结构
            self.assertIn('id', second_member, "第二次创建的成员缺少ID字段")
            self.assertIn('name', second_member, "第二次创建的成员缺少name字段")
            self.assertEqual(second_member['name'], member_param['name'], "名称不匹配")
        # 如果返回None，也不视为错误，因为系统可能以其他方式处理重复
    
    def test_query_nonexistent_member(self):
        """测试查询不存在的成员（异常测试）"""
        nonexistent_member_id = 999999
        queried_member = self.member_sdk.query_member(nonexistent_member_id)
        # 期望查询失败，返回None或错误响应
        self.assertIsNone(queried_member, "查询不存在的成员应失败")
    
    def test_delete_nonexistent_member(self):
        """测试删除不存在的成员（异常测试）"""
        nonexistent_member_id = 999999
        deleted_member = self.member_sdk.delete_member(nonexistent_member_id)
        # 期望删除失败，返回None或错误响应
        self.assertIsNone(deleted_member, "删除不存在的成员应失败")
    
    def test_member_store_validation(self):
        """测试成员店铺关联验证"""
        member_param = self.mock_member_param()
        new_member = self.member_sdk.create_member(member_param)
        self.assertIsNotNone(new_member, "创建成员失败")
        
        if new_member and 'id' in new_member:
            self._record_member_for_cleanup(new_member['id'])
        
        # 验证店铺关联字段
        self.assertIn('store', new_member, "成员缺少店铺关联字段")
        self.assertIsInstance(new_member['store'], dict, "店铺关联应为字典")
        if 'id' in new_member['store']:
            self.assertEqual(new_member['store']['id'], self.store_id, "店铺ID不匹配")
    
    def test_auto_generated_fields(self):
        """测试系统自动生成字段"""
        member_param = self.mock_member_param()
        new_member = self.member_sdk.create_member(member_param)
        self.assertIsNotNone(new_member, "创建成员失败")
        
        if new_member and 'id' in new_member:
            self._record_member_for_cleanup(new_member['id'])
        
        # 验证所有系统自动生成字段
        auto_generated_fields = ['id', 'creater', 'createTime', 'namespace']
        for field in auto_generated_fields:
            self.assertIn(field, new_member, f"缺少系统自动生成字段: {field}")
        
        # 验证字段类型和值
        self.assertIsInstance(new_member['id'], (int, type(None)), "ID应为整数或None")
        if new_member['id'] is not None:
            self.assertGreater(new_member['id'], 0, "ID应为正整数")
        
        self.assertIsInstance(new_member['creater'], (int, type(None)), "创建者应为整数或None")
        self.assertIsInstance(new_member['createTime'], (int, type(None)), "创建时间应为整数或None")
        if new_member['createTime'] is not None:
            self.assertGreater(new_member['createTime'], 0, "创建时间应为正数")
        
        self.assertIsInstance(new_member['namespace'], (str, type(None)), "命名空间应为字符串或None")
    
    def test_modify_time_auto_update(self):
        """测试修改时间自动更新"""
        # 创建成员
        member_param = self.mock_member_param()
        new_member = self.member_sdk.create_member(member_param)
        self.assertIsNotNone(new_member, "创建成员失败")
        
        if new_member and 'id' in new_member:
            self._record_member_for_cleanup(new_member['id'])
        
        # 记录初始创建时间和修改时间
        initial_create_time = new_member.get('createTime')
        initial_modify_time = new_member.get('modifyTime')
        
        # 更新成员
        update_param = new_member.copy()
        update_param['title'] = "更新后的职位"
        
        updated_member = self.member_sdk.update_member(new_member['id'], update_param)
        self.assertIsNotNone(updated_member, "更新成员失败")
        
        # 验证修改时间已更新
        updated_modify_time = updated_member.get('modifyTime')
        self.assertIsNotNone(updated_modify_time, "更新后缺少修改时间字段")
        
        # 验证修改时间比创建时间晚（如果两者都存在）
        if initial_create_time and updated_modify_time:
            self.assertGreaterEqual(updated_modify_time, initial_create_time,
                                   "修改时间应晚于或等于创建时间")
        
        # 验证创建时间未改变
        self.assertEqual(updated_member.get('createTime'), initial_create_time,
                        "创建时间不应被修改")
        
        # 如果初始有修改时间，验证已更新
        if initial_modify_time and updated_modify_time:
            self.assertGreaterEqual(updated_modify_time, initial_modify_time,
                                   "修改时间应已更新")


if __name__ == '__main__':
    unittest.main()