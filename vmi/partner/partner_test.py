"""Partner 测试用例"""

import unittest
import warnings
import logging
from session import session, common
from cas.cas import cas
from mock import common as mock

# 配置日志
logger = logging.getLogger(__name__)


class PartnerTestCase(unittest.TestCase):
    """Partner 测试用例类"""
    
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
        cls.partner_instance = common.MagicEntity('/vmi/partner', cls.work_session)
    
    def setUp(self):
        """每个测试用例前的准备"""
        # 记录测试创建的合作伙伴ID以便清理
        self.created_partner_ids = []
    
    def tearDown(self):
        """每个测试用例后的清理"""
        # 清理所有测试创建的合作伙伴
        for partner_id in self.created_partner_ids:
            try:
                self.partner_instance.delete(partner_id)
            except Exception as e:
                logger.warning(f"清理合作伙伴 {partner_id} 失败: {e}")
        
        self.created_partner_ids.clear()
    
    def mock_partner_param(self):
        """模拟合作伙伴参数"""
        return {
            'name': mock.name(),
            'telephone': mock.name(),
            'wechat': mock.name(),
            'description': mock.sentence(),
            'status': {
                'id': 3
            },
        }
    
    def test_create_partner(self):
        """测试创建合作伙伴"""
        partner_param = self.mock_partner_param()
        new_partner = self.partner_instance.insert(partner_param)
        self.assertIsNotNone(new_partner, "创建合作伙伴失败")
        
        # 验证合作伙伴信息完整性
        required_fields = ['id', 'name', 'telephone', 'wechat', 'description', 'status']
        for field in required_fields:
            self.assertIn(field, new_partner, f"缺少字段: {field}")
        
        # 记录创建的合作伙伴ID以便清理
        if new_partner and 'id' in new_partner:
            self.created_partner_ids.append(new_partner['id'])
    
    def test_query_partner(self):
        """测试查询合作伙伴"""
        # 先创建合作伙伴
        partner_param = self.mock_partner_param()
        new_partner = self.partner_instance.insert(partner_param)
        self.assertIsNotNone(new_partner, "创建合作伙伴失败")
        
        if new_partner and 'id' in new_partner:
            self.created_partner_ids.append(new_partner['id'])
        
        # 查询合作伙伴
        queried_partner = self.partner_instance.query(new_partner['id'])
        self.assertIsNotNone(queried_partner, "查询合作伙伴失败")
        self.assertEqual(queried_partner['id'], new_partner['id'], "合作伙伴ID不匹配")
        self.assertEqual(queried_partner['name'], new_partner['name'], "合作伙伴名不匹配")
    
    def test_update_partner(self):
        """测试更新合作伙伴"""
        # 先创建合作伙伴
        partner_param = self.mock_partner_param()
        new_partner = self.partner_instance.insert(partner_param)
        self.assertIsNotNone(new_partner, "创建合作伙伴失败")
        
        if new_partner and 'id' in new_partner:
            self.created_partner_ids.append(new_partner['id'])
        
        # 更新合作伙伴
        update_param = new_partner.copy()
        update_param['description'] = "更新后的描述"
        
        updated_partner = self.partner_instance.update(new_partner['id'], update_param)
        self.assertIsNotNone(updated_partner, "更新合作伙伴失败")
        self.assertEqual(updated_partner['description'], "更新后的描述", "描述更新失败")
    
    def test_delete_partner(self):
        """测试删除合作伙伴"""
        # 先创建合作伙伴
        partner_param = self.mock_partner_param()
        new_partner = self.partner_instance.insert(partner_param)
        self.assertIsNotNone(new_partner, "创建合作伙伴失败")
        
        # 删除合作伙伴
        deleted_partner = self.partner_instance.delete(new_partner['id'])
        self.assertIsNotNone(deleted_partner, "删除合作伙伴失败")
        self.assertEqual(deleted_partner['id'], new_partner['id'], "删除的合作伙伴ID不匹配")
        
        # 验证合作伙伴已被删除（查询应该失败）
        queried_partner = self.partner_instance.query(new_partner['id'])
        self.assertIsNone(queried_partner, "已删除的合作伙伴查询应失败")
    
    def test_create_partner_with_long_name(self):
        """测试创建超长名称合作伙伴（边界测试）"""
        partner_param = self.mock_partner_param()
        partner_param['name'] = 'a' * 255  # 超长名称
        
        new_partner = self.partner_instance.insert(partner_param)
        if new_partner is not None:
            self.assertIsInstance(new_partner['name'], str, "合作伙伴名不是字符串")
            # 记录创建的合作伙伴ID以便清理
            if 'id' in new_partner:
                self.created_partner_ids.append(new_partner['id'])
    
    def test_create_duplicate_partner(self):
        """测试创建重复合作伙伴名（异常测试）"""
        partner_param = self.mock_partner_param()
        
        first_partner = self.partner_instance.insert(partner_param)
        self.assertIsNotNone(first_partner, "第一次创建合作伙伴失败")
        
        # 记录第一次创建的合作伙伴ID以便清理
        if first_partner and 'id' in first_partner:
            self.created_partner_ids.append(first_partner['id'])
        
        # 第二次创建相同合作伙伴名应该失败
        second_partner = self.partner_instance.insert(partner_param)
        # 期望创建失败，返回None或错误响应
        self.assertIsNone(second_partner, "重复合作伙伴名创建应失败")
    
    def test_query_nonexistent_partner(self):
        """测试查询不存在的合作伙伴（异常测试）"""
        nonexistent_partner_id = 999999
        queried_partner = self.partner_instance.query(nonexistent_partner_id)
        # 期望查询失败，返回None或错误响应
        self.assertIsNone(queried_partner, "查询不存在的合作伙伴应失败")
    
    def test_delete_nonexistent_partner(self):
        """测试删除不存在的合作伙伴（异常测试）"""
        nonexistent_partner_id = 999999
        deleted_partner = self.partner_instance.delete(nonexistent_partner_id)
        # 期望删除失败，返回None或错误响应
        self.assertIsNone(deleted_partner, "删除不存在的合作伙伴应失败")
    
    def test_partner_status_validation(self):
        """测试合作伙伴状态验证"""
        partner_param = self.mock_partner_param()
        new_partner = self.partner_instance.insert(partner_param)
        self.assertIsNotNone(new_partner, "创建合作伙伴失败")
        
        if new_partner and 'id' in new_partner:
            self.created_partner_ids.append(new_partner['id'])
        
        # 验证状态字段
        self.assertIn('status', new_partner, "合作伙伴缺少状态字段")
        self.assertIn('id', new_partner['status'], "状态缺少id字段")
        self.assertEqual(new_partner['status']['id'], 3, "状态ID不匹配")


if __name__ == '__main__':
    unittest.main()