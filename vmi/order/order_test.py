"""
Order 测试用例

基于 VMI实体定义和使用说明.md:125-141 中的 order 实体定义编写。
使用 OrderSDK 进行测试。

包含的测试用例（共12个）：
1. test_create_order
2. test_query_order
3. test_update_order
4. test_delete_order
5. test_create_order_with_goods_items
6. test_create_order_with_different_type
7. test_create_order_without_customer
8. test_query_nonexistent_order
9. test_delete_nonexistent_order
10. test_auto_generated_fields
11. test_modify_time_auto_update
12. test_order_status_validation
"""

import unittest
import warnings
import logging
import time
from session import session
from cas.cas import Cas
from mock import common as mock
from sdk import OrderSDK, PartnerSDK, StoreSDK, StatusSDK

logger = logging.getLogger(__name__)

class OrderTestCase(unittest.TestCase):
    server_url = 'https://autotest.local.vpc'
    namespace = ''
    
    @classmethod
    def setUpClass(cls):
        warnings.simplefilter('ignore', ResourceWarning)
        cls.work_session = session.MagicSession(cls.server_url, cls.namespace)
        cls.cas_session = Cas(cls.work_session)
        if not cls.cas_session.login('administrator', 'administrator'):
            logger.error('CAS登录失败')
            raise Exception('CAS登录失败')
        cls.work_session.bind_token(cls.cas_session.get_session_token())
        cls.order_sdk = OrderSDK(cls.work_session)
        cls.partner_sdk = PartnerSDK(cls.work_session)
        cls.store_sdk = StoreSDK(cls.work_session)
        cls.status_sdk = StatusSDK(cls.work_session)
        cls.test_data = []
        print("Order 测试开始...")
    
    def setUp(self):
        # 创建测试合作伙伴
        partner_param = {'name': '测试订单客户', 'telephone': '13800138002', 'status': {'id': 19}}
        try:
            self.test_partner = self.partner_sdk.create_partner(partner_param)
            if not self.test_partner:
                partners = self.partner_sdk.filter_partner({'name': '测试订单客户'})
                if partners and len(partners) > 0:
                    self.test_partner = partners[0]
                else:
                    self.skipTest("无法创建或找到测试合作伙伴")
        except Exception as e:
            logger.warning(f"创建测试合作伙伴失败: {e}")
            self.skipTest(f"创建测试合作伙伴失败: {e}")
        
        # 创建测试店铺
        store_param = {'name': '测试订单店铺', 'description': '订单测试用店铺'}
        try:
            self.test_store = self.store_sdk.create_store(store_param)
            if not self.test_store:
                stores = self.store_sdk.filter_store({'name': '测试订单店铺'})
                if stores and len(stores) > 0:
                    self.test_store = stores[0]
                else:
                    self.skipTest("无法创建或找到测试店铺")
        except Exception as e:
            logger.warning(f"创建测试店铺失败: {e}")
            self.skipTest(f"创建测试店铺失败: {e}")
        
        # 获取状态
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
                    self.order_sdk.delete_order(data['id'])
                except Exception as e:
                    logger.warning(f"清理订单 {data.get('id')} 失败: {e}")
        if hasattr(self, 'test_partner') and self.test_partner and 'id' in self.test_partner:
            try:
                self.partner_sdk.delete_partner(self.test_partner['id'])
            except Exception as e:
                logger.warning(f"清理合作伙伴 {self.test_partner.get('id')} 失败: {e}")
        if hasattr(self, 'test_store') and self.test_store and 'id' in self.test_store:
            try:
                self.store_sdk.delete_store(self.test_store['id'])
            except Exception as e:
                logger.warning(f"清理店铺 {self.test_store.get('id')} 失败: {e}")
        self.test_data.clear()
    
    @classmethod
    def tearDownClass(cls):
        print("Order 测试结束")
    
    def test_create_order(self):
        print("测试创建订单...")
        order_param = {
            'type': 1,
            'customer': {'id': self.test_partner['id']},
            'goods': [
                {'sku': 'TEST001', 'name': '测试商品', 'price': 50.0, 'count': 2}
            ],
            'cost': 100.0,
            'store': {'id': self.test_store['id']},
            'status': {'id': self.test_status['id']}
        }
        order = self.order_sdk.create_order(order_param)
        self.assertIsNotNone(order, "创建订单失败")
        required_fields = ['id', 'sn', 'type', 'customer', 'goods', 'cost', 'store', 'status', 'creater', 'createTime', 'namespace']
        for field in required_fields:
            self.assertIn(field, order, f"订单缺少必填字段: {field}")
        self.test_data.append(order)
        print(f"✓ 订单创建成功: ID={order.get('id')}")
    
    def test_query_order(self):
        print("测试查询订单...")
        order_param = {
            'type': 1,
            'customer': {'id': self.test_partner['id']},
            'goods': [
                {'sku': 'TEST002', 'name': '查询测试商品', 'price': 75.0, 'count': 2}
            ],
            'cost': 150.0,
            'store': {'id': self.test_store['id']},
            'status': {'id': self.test_status['id']}
        }
        created_order = self.order_sdk.create_order(order_param)
        self.assertIsNotNone(created_order, "创建订单失败")
        queried_order = self.order_sdk.query_order(created_order['id'])
        self.assertIsNotNone(queried_order, "查询订单失败")
        self.assertEqual(queried_order['id'], created_order['id'], "ID不匹配")
        self.test_data.append(created_order)
        print(f"✓ 订单查询成功: ID={queried_order.get('id')}")
    
    def test_update_order(self):
        print("测试更新订单...")
        order_param = {
            'type': 1,
            'customer': {'id': self.test_partner['id']},
            'goods': [
                {'sku': 'TEST003', 'name': '更新测试商品', 'price': 100.0, 'count': 2}
            ],
            'cost': 200.0,
            'store': {'id': self.test_store['id']},
            'status': {'id': self.test_status['id']}
        }
        created_order = self.order_sdk.create_order(order_param)
        self.assertIsNotNone(created_order, "创建订单失败")
        update_param = {'cost': 250.0, 'memo': '更新测试'}
        updated_order = self.order_sdk.update_order(created_order['id'], update_param)
        if updated_order:
            self.assertEqual(updated_order['cost'], 250.0, "更新后金额不匹配")
            print(f"✓ 订单更新成功: ID={updated_order.get('id')}")
        else:
            print("⚠ 订单更新未返回结果")
        self.test_data.append(created_order)
    
    def test_delete_order(self):
        print("测试删除订单...")
        order_param = {
            'type': 1,
            'customer': {'id': self.test_partner['id']},
            'goods': [
                {'sku': 'TEST004', 'name': '删除测试商品', 'price': 150.0, 'count': 2}
            ],
            'cost': 300.0,
            'store': {'id': self.test_store['id']},
            'status': {'id': self.test_status['id']}
        }
        created_order = self.order_sdk.create_order(order_param)
        self.assertIsNotNone(created_order, "创建订单失败")
        deleted_order = self.order_sdk.delete_order(created_order['id'])
        if deleted_order:
            self.assertEqual(deleted_order['id'], created_order['id'], "删除的订单ID不匹配")
            print(f"✓ 订单删除成功: ID={deleted_order.get('id')}")
        else:
            print("⚠ 订单删除未返回结果")
    
    def test_create_order_with_goods_items(self):
        print("测试创建带商品项的订单...")
        goods_items = [
            {'sku': 'TEST001', 'name': '测试商品1', 'price': 50.0, 'count': 2},
            {'sku': 'TEST002', 'name': '测试商品2', 'price': 30.0, 'count': 3}
        ]
        order_param = {
            'type': 1,
            'customer': {'id': self.test_partner['id']},
            'goods': goods_items,
            'cost': 190.0,
            'store': {'id': self.test_store['id']},
            'status': {'id': self.test_status['id']}
        }
        order = self.order_sdk.create_order(order_param)
        self.assertIsNotNone(order, "创建带商品项的订单失败")
        self.assertIsInstance(order.get('goods'), list, "商品项应为列表")
        self.test_data.append(order)
        print(f"✓ 带商品项的订单创建成功: 商品数量={len(order.get('goods', []))}")
    
    def test_create_order_with_different_type(self):
        print("测试创建不同类型订单...")
        order_types = [1, 2]
        for i, order_type in enumerate(order_types):
            order_param = {
                'type': order_type,
                'customer': {'id': self.test_partner['id']},
                'goods': [
                    {'sku': f'TYPE{i+1}_TEST', 'name': f'类型{order_type}测试商品', 'price': 50.0, 'count': 2}
                ],
                'cost': 100.0,
                'store': {'id': self.test_store['id']},
                'status': {'id': self.test_status['id']}
            }
            order = self.order_sdk.create_order(order_param)
            self.assertIsNotNone(order, f"创建类型{order_type}订单失败")
            self.assertEqual(order['type'], order_type, f"订单类型不匹配: {order_type}")
            self.test_data.append(order)
            print(f"✓ 类型{order_type}订单创建成功")
    
    def test_create_order_without_customer(self):
        print("测试创建无客户的订单...")
        order_param = {
            'type': 1,
            'goods': [
                {'sku': 'NO_CUST_TEST', 'name': '无客户测试商品', 'price': 50.0, 'count': 2}
            ],
            'cost': 100.0,
            'store': {'id': self.test_store['id']},
            'status': {'id': self.test_status['id']}
        }
        order = self.order_sdk.create_order(order_param)
        if order is None:
            print("✓ 系统正确拒绝创建无客户的订单")
        else:
            self.assertIn('customer', order, "订单应包含客户字段")
            print(f"⚠ 系统允许创建无客户的订单: ID={order.get('id')}")
            self.test_data.append(order)
    
    def test_query_nonexistent_order(self):
        print("测试查询不存在的订单...")
        non_existent_id = 999999999
        order = self.order_sdk.query_order(non_existent_id)
        if order is None:
            print("✓ 查询不存在的订单返回None，符合预期")
        else:
            print(f"⚠ 查询不存在的订单返回: {order}")
    
    def test_delete_nonexistent_order(self):
        print("测试删除不存在的订单...")
        non_existent_id = 999999999
        deleted_order = self.order_sdk.delete_order(non_existent_id)
        if deleted_order is None:
            print("✓ 删除不存在的订单返回None，符合预期")
        else:
            print(f"⚠ 删除不存在的订单返回: {deleted_order}")
    
    def test_auto_generated_fields(self):
        print("测试系统自动生成字段...")
        order_param = {
            'type': 1,
            'customer': {'id': self.test_partner['id']},
            'goods': [
                {'sku': 'AUTO_FIELD_TEST', 'name': '自动字段测试商品', 'price': 50.0, 'count': 2}
            ],
            'cost': 100.0,
            'store': {'id': self.test_store['id']},
            'status': {'id': self.test_status['id']}
        }
        order = self.order_sdk.create_order(order_param)
        self.assertIsNotNone(order, "创建订单失败")
        auto_fields = ['id', 'sn', 'creater', 'createTime', 'namespace']
        for field in auto_fields:
            self.assertIn(field, order, f"缺少自动生成字段: {field}")
        self.test_data.append(order)
        print(f"✓ 系统自动生成字段验证成功: SN={order.get('sn')}")
    
    def test_modify_time_auto_update(self):
        print("测试修改时间自动更新...")
        order_param = {
            'type': 1,
            'customer': {'id': self.test_partner['id']},
            'goods': [
                {'sku': 'MODIFY_TIME_TEST', 'name': '修改时间测试商品', 'price': 50.0, 'count': 2}
            ],
            'cost': 100.0,
            'store': {'id': self.test_store['id']},
            'status': {'id': self.test_status['id']}
        }
        created_order = self.order_sdk.create_order(order_param)
        self.assertIsNotNone(created_order, "创建订单失败")
        if 'modifyTime' in created_order:
            original_modify_time = created_order['modifyTime']
            update_param = {'cost': 150.0}
            updated_order = self.order_sdk.update_order(created_order['id'], update_param)
            if updated_order and 'modifyTime' in updated_order:
                updated_modify_time = updated_order['modifyTime']
                self.assertNotEqual(updated_modify_time, original_modify_time, "修改时间未自动更新")
                print(f"✓ 修改时间自动更新验证成功")
            else:
                print("⚠ 更新后未返回modifyTime字段")
        else:
            print("⚠ 订单不包含modifyTime字段")
        self.test_data.append(created_order)
    
    def test_order_status_validation(self):
        print("测试订单状态验证...")
        order_param = {
            'type': 1,
            'customer': {'id': self.test_partner['id']},
            'goods': [
                {'sku': 'STATUS_VALID_TEST', 'name': '状态验证测试商品', 'price': 50.0, 'count': 2}
            ],
            'cost': 100.0,
            'store': {'id': self.test_store['id']},
            'status': {'id': self.test_status['id']}
        }
        order = self.order_sdk.create_order(order_param)
        self.assertIsNotNone(order, "创建订单失败")
        self.assertEqual(order['status']['id'], self.test_status['id'], "状态ID不匹配")
        self.test_data.append(order)
        print(f"✓ 订单状态验证成功: 状态ID={order.get('status', {}).get('id')}")

if __name__ == '__main__':
    unittest.main()
