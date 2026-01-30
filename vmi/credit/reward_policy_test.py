"""
Reward Policy 测试用例

基于 VMI实体定义和使用说明.md:115-124 中的 rewardPolicy 实体定义编写。
使用 RewardPolicySDK 进行测试。

包含的测试用例（共12个）：
1. test_create_reward_policy
2. test_query_reward_policy
3. test_update_reward_policy
4. test_delete_reward_policy
5. test_create_reward_policy_with_long_name
6. test_create_reward_policy_with_long_description
7. test_create_reward_policy_without_status
8. test_query_nonexistent_reward_policy
9. test_delete_nonexistent_reward_policy
10. test_auto_generated_fields
11. test_modify_time_auto_update
12. test_reward_policy_status_validation
"""

import unittest
import warnings
import logging
import time
import session
from cas.cas import Cas
from mock import common as mock
from sdk import RewardPolicySDK, StatusSDK

logger = logging.getLogger(__name__)

class RewardPolicyTestCase(unittest.TestCase):
    namespace = ''
    
    @classmethod
    def setUpClass(cls):
        # 从config_helper获取配置

        # 从config_helper获取配置
        from config_helper import get_server_url, get_credentials
        cls.server_url = get_server_url()
        cls.credentials = get_credentials()
        
        warnings.simplefilter('ignore', ResourceWarning)
        cls.work_session = session.MagicSession(cls.server_url, cls.namespace)
        cls.cas_session = Cas(cls.work_session)
        if not cls.cas_session.login(cls.credentials['username'], cls.credentials['password']):
            logger.error('CAS登录失败')
            raise Exception('CAS登录失败')
        cls.work_session.bind_token(cls.cas_session.get_session_token())
        cls.reward_policy_sdk = RewardPolicySDK(cls.work_session)
        cls.status_sdk = StatusSDK(cls.work_session)
        cls.test_data = []
        print("Reward Policy 测试开始...")
    
    def setUp(self):
        # 获取状态信息
        try:
            statuses = self.status_sdk.filter_status({})
            if statuses and len(statuses) > 0:
                self.test_status = statuses[0]
            else:
                self.skipTest("无法获取状态信息")
        except Exception as e:
            logger.warning(f"获取状态信息失败: {e}")
            self.skipTest(f"获取状态信息失败: {e}")
    
    def tearDown(self):
        for data in self.test_data:
            if 'id' in data:
                try:
                    self.reward_policy_sdk.delete_reward_policy(data['id'])
                except Exception as e:
                    logger.warning(f"清理积分策略 {data.get('id')} 失败: {e}")
        self.test_data.clear()
    
    @classmethod
    def tearDownClass(cls):
        print("Reward Policy 测试结束")
    
    def test_create_reward_policy(self):
        print("测试创建积分策略...")
        reward_policy_param = {
            'name': '测试积分策略',
            'description': '测试策略描述',
            'policy': '{"type": "fixed", "points": 100}',
            'status': {'id': self.test_status['id']}
        }
        reward_policy = self.reward_policy_sdk.create_reward_policy(reward_policy_param)
        self.assertIsNotNone(reward_policy, "创建积分策略失败")
        required_fields = ['id', 'name', 'description', 'policy', 'status', 'creater', 'createTime', 'namespace']
        for field in required_fields:
            self.assertIn(field, reward_policy, f"积分策略缺少必填字段: {field}")
        self.test_data.append(reward_policy)
        print(f"✓ 积分策略创建成功: ID={reward_policy.get('id')}")
    
    def test_query_reward_policy(self):
        print("测试查询积分策略...")
        reward_policy_param = {
            'name': '查询测试策略',
            'description': '查询测试描述',
            'policy': '{"type": "percentage", "rate": 0.1}',
            'status': {'id': self.test_status['id']}
        }
        created_policy = self.reward_policy_sdk.create_reward_policy(reward_policy_param)
        self.assertIsNotNone(created_policy, "创建积分策略失败")
        queried_policy = self.reward_policy_sdk.query_reward_policy(created_policy['id'])
        self.assertIsNotNone(queried_policy, "查询积分策略失败")
        self.assertEqual(queried_policy['id'], created_policy['id'], "ID不匹配")
        self.test_data.append(created_policy)
        print(f"✓ 积分策略查询成功: ID={queried_policy.get('id')}")
    
    def test_update_reward_policy(self):
        print("测试更新积分策略...")
        reward_policy_param = {
            'name': '更新前策略',
            'description': '更新前描述',
            'policy': '{"type": "fixed", "points": 50}',
            'status': {'id': self.test_status['id']}
        }
        created_policy = self.reward_policy_sdk.create_reward_policy(reward_policy_param)
        self.assertIsNotNone(created_policy, "创建积分策略失败")
        update_param = {'name': '更新后策略', 'description': '更新后描述'}
        updated_policy = self.reward_policy_sdk.update_reward_policy(created_policy['id'], update_param)
        if updated_policy:
            self.assertEqual(updated_policy['name'], '更新后策略', "更新后名称不匹配")
            print(f"✓ 积分策略更新成功: ID={updated_policy.get('id')}")
        else:
            print("⚠ 积分策略更新未返回结果")
        self.test_data.append(created_policy)
    
    def test_delete_reward_policy(self):
        print("测试删除积分策略...")
        reward_policy_param = {
            'name': '删除测试策略',
            'description': '删除测试描述',
            'policy': '{"type": "fixed", "points": 200}',
            'status': {'id': self.test_status['id']}
        }
        created_policy = self.reward_policy_sdk.create_reward_policy(reward_policy_param)
        self.assertIsNotNone(created_policy, "创建积分策略失败")
        deleted_policy = self.reward_policy_sdk.delete_reward_policy(created_policy['id'])
        if deleted_policy:
            self.assertEqual(deleted_policy['id'], created_policy['id'], "删除的积分策略ID不匹配")
            print(f"✓ 积分策略删除成功: ID={deleted_policy.get('id')}")
        else:
            print("⚠ 积分策略删除未返回结果")
    
    def test_create_reward_policy_with_long_name(self):
        print("测试创建超长名称积分策略...")
        long_name = '超长名称积分策略' * 10
        reward_policy_param = {
            'name': long_name,
            'description': '超长名称测试',
            'policy': '{"type": "fixed", "points": 100}',
            'status': {'id': self.test_status['id']}
        }
        reward_policy = self.reward_policy_sdk.create_reward_policy(reward_policy_param)
        self.assertIsNotNone(reward_policy, "创建超长名称积分策略失败")
        self.assertEqual(reward_policy['name'], long_name, "超长名称不匹配")
        self.test_data.append(reward_policy)
        print(f"✓ 超长名称积分策略创建成功: 名称长度={len(reward_policy.get('name'))}")
    
    def test_create_reward_policy_with_long_description(self):
        print("测试创建超长描述积分策略...")
        long_description = '超长描述积分策略' * 20
        reward_policy_param = {
            'name': '超长描述测试',
            'description': long_description,
            'policy': '{"type": "fixed", "points": 100}',
            'status': {'id': self.test_status['id']}
        }
        reward_policy = self.reward_policy_sdk.create_reward_policy(reward_policy_param)
        self.assertIsNotNone(reward_policy, "创建超长描述积分策略失败")
        self.assertEqual(reward_policy['description'], long_description, "超长描述不匹配")
        self.test_data.append(reward_policy)
        print(f"✓ 超长描述积分策略创建成功: 描述长度={len(reward_policy.get('description'))}")
    
    def test_create_reward_policy_without_status(self):
        print("测试创建无状态积分策略...")
        reward_policy_param = {
            'name': '无状态测试',
            'description': '无状态描述',
            'policy': '{"type": "fixed", "points": 100}'
        }
        reward_policy = self.reward_policy_sdk.create_reward_policy(reward_policy_param)
        if reward_policy is None:
            print("✓ 系统正确拒绝创建无状态积分策略")
        else:
            self.assertIn('status', reward_policy, "积分策略应包含状态字段")
            print(f"⚠ 系统允许创建无状态积分策略: ID={reward_policy.get('id')}")
            self.test_data.append(reward_policy)
    
    def test_query_nonexistent_reward_policy(self):
        print("测试查询不存在的积分策略...")
        non_existent_id = 999999999
        reward_policy = self.reward_policy_sdk.query_reward_policy(non_existent_id)
        if reward_policy is None:
            print("✓ 查询不存在的积分策略返回None，符合预期")
        else:
            print(f"⚠ 查询不存在的积分策略返回: {reward_policy}")
    
    def test_delete_nonexistent_reward_policy(self):
        print("测试删除不存在的积分策略...")
        non_existent_id = 999999999
        deleted_policy = self.reward_policy_sdk.delete_reward_policy(non_existent_id)
        if deleted_policy is None:
            print("✓ 删除不存在的积分策略返回None，符合预期")
        else:
            print(f"⚠ 删除不存在的积分策略返回: {deleted_policy}")
    
    def test_auto_generated_fields(self):
        print("测试系统自动生成字段...")
        reward_policy_param = {
            'name': '自动字段测试',
            'description': '自动字段描述',
            'policy': '{"type": "fixed", "points": 100}',
            'status': {'id': self.test_status['id']}
        }
        reward_policy = self.reward_policy_sdk.create_reward_policy(reward_policy_param)
        self.assertIsNotNone(reward_policy, "创建积分策略失败")
        auto_fields = ['id', 'creater', 'createTime', 'namespace']
        for field in auto_fields:
            self.assertIn(field, reward_policy, f"缺少自动生成字段: {field}")
        self.test_data.append(reward_policy)
        print(f"✓ 系统自动生成字段验证成功: ID={reward_policy.get('id')}")
    
    def test_modify_time_auto_update(self):
        print("测试修改时间自动更新...")
        reward_policy_param = {
            'name': '时间测试策略',
            'description': '时间测试描述',
            'policy': '{"type": "fixed", "points": 100}',
            'status': {'id': self.test_status['id']}
        }
        created_policy = self.reward_policy_sdk.create_reward_policy(reward_policy_param)
        self.assertIsNotNone(created_policy, "创建积分策略失败")
        if 'modifyTime' in created_policy:
            original_modify_time = created_policy['modifyTime']
            update_param = {'description': '时间更新描述'}
            updated_policy = self.reward_policy_sdk.update_reward_policy(created_policy['id'], update_param)
            if updated_policy and 'modifyTime' in updated_policy:
                updated_modify_time = updated_policy['modifyTime']
                self.assertNotEqual(updated_modify_time, original_modify_time, "修改时间未自动更新")
                print(f"✓ 修改时间自动更新验证成功")
            else:
                print("⚠ 更新后未返回modifyTime字段")
        else:
            print("⚠ 积分策略不包含modifyTime字段")
        self.test_data.append(created_policy)
    
    def test_reward_policy_status_validation(self):
        print("测试积分策略状态验证...")
        reward_policy_param = {
            'name': '状态验证策略',
            'description': '状态验证描述',
            'policy': '{"type": "fixed", "points": 100}',
            'status': {'id': self.test_status['id']}
        }
        reward_policy = self.reward_policy_sdk.create_reward_policy(reward_policy_param)
        self.assertIsNotNone(reward_policy, "创建积分策略失败")
        self.assertEqual(reward_policy['status']['id'], self.test_status['id'], "状态ID不匹配")
        self.test_data.append(reward_policy)
        print(f"✓ 积分策略状态验证成功: 状态ID={reward_policy.get('status', {}).get('id')}")

if __name__ == '__main__':
    unittest.main()
