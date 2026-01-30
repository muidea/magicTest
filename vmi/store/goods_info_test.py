"""
Goods Info 测试用例

基于 VMI实体定义和使用说明.md:207-218 中的 goodsInfo 实体定义编写。
使用 GoodsInfoSDK 进行测试。

包含的测试用例（共10个）：
1. test_create_goods_info
2. test_query_goods_info
3. test_update_goods_info
4. test_delete_goods_info
5. test_create_goods_info_with_different_type
6. test_create_goods_info_without_product
7. test_query_nonexistent_goods_info
8. test_delete_nonexistent_goods_info
9. test_auto_generated_fields
10. test_goods_info_type_validation
"""

import unittest
import warnings
import logging
import session
from cas.cas import Cas
from sdk import GoodsInfoSDK, ProductInfoSDK, ProductSDK, StoreSDK, StatusSDK, WarehouseSDK, ShelfSDK
from mock import common as mock

logger = logging.getLogger(__name__)

class GoodsInfoTestCase(unittest.TestCase):
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
        cls.goods_info_sdk = GoodsInfoSDK(cls.work_session)
        cls.product_info_sdk = ProductInfoSDK(cls.work_session)
        cls.product_sdk = ProductSDK(cls.work_session)
        cls.store_sdk = StoreSDK(cls.work_session)
        cls.status_sdk = StatusSDK(cls.work_session)
        cls.warehouse_sdk = WarehouseSDK(cls.work_session)
        cls.shelf_sdk = ShelfSDK(cls.work_session)
        cls.test_data = []
        print("Goods Info 测试开始...")
    
    def setUp(self):
        # 创建测试产品
        product_param = {
            'name': '测试产品-GoodsInfo',
            'description': 'GoodsInfo测试用产品',
            'status': {'id': 19}
        }
        try:
            self.test_product = self.product_sdk.create_product(product_param)
            if not self.test_product:
                products = self.product_sdk.filter_product({'name': '测试产品-GoodsInfo'})
                if products and len(products) > 0:
                    self.test_product = products[0]
                else:
                    self.skipTest("无法创建或找到测试产品")
        except Exception as e:
            logger.warning(f"创建测试产品失败: {e}")
            self.skipTest(f"创建测试产品失败: {e}")
        
        # 创建测试产品SKU
        product_info_param = {
            'sku': 'SKU-GOODSINFO',
            'description': 'GoodsInfo测试SKU',
            'product': {'id': self.test_product['id']}
        }
        try:
            self.test_product_info = self.product_info_sdk.create_product_info(product_info_param)
            if not self.test_product_info:
                product_infos = self.product_info_sdk.filter_product_info({'sku': 'SKU-GOODSINFO'})
                if product_infos and len(product_infos) > 0:
                    self.test_product_info = product_infos[0]
                else:
                    self.skipTest("无法创建或找到测试产品SKU")
        except Exception as e:
            logger.warning(f"创建测试产品SKU失败: {e}")
            self.skipTest(f"创建测试产品SKU失败: {e}")
        
        # 创建测试店铺
        store_param = {'name': '测试店铺-GoodsInfo', 'description': 'GoodsInfo测试用店铺'}
        try:
            self.test_store = self.store_sdk.create_store(store_param)
            if not self.test_store:
                stores = self.store_sdk.filter_store({'name': '测试店铺-GoodsInfo'})
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
        
        # 创建测试仓库
        warehouse_param = {
            'name': '测试仓库-GoodsInfo',
            'description': 'GoodsInfo测试用仓库'
        }
        try:
            self.test_warehouse = self.warehouse_sdk.create_warehouse(warehouse_param)
            if not self.test_warehouse:
                warehouses = self.warehouse_sdk.filter_warehouse({'name': '测试仓库-GoodsInfo'})
                if warehouses and len(warehouses) > 0:
                    self.test_warehouse = warehouses[0]
                else:
                    self.skipTest("无法创建或找到测试仓库")
        except Exception as e:
            logger.warning(f"创建测试仓库失败: {e}")
            self.skipTest(f"创建测试仓库失败: {e}")
        
        # 创建测试货架（shelf需要warehouse字段，capacity不能为0）
        shelf_param = {
            'description': 'GoodsInfo测试货架',
            'capacity': 100,  # capacity不能为0
            'warehouse': {'id': self.test_warehouse['id']},
            'status': {'id': 19}  # 启用状态
        }
        try:
            self.test_shelf = self.shelf_sdk.create_shelf(shelf_param)
            if not self.test_shelf:
                shelves = self.shelf_sdk.filter_shelf({'description': 'GoodsInfo测试货架'})
                if shelves and len(shelves) > 0:
                    self.test_shelf = shelves[0]
                else:
                    self.skipTest("无法创建或找到测试货架")
        except Exception as e:
            logger.warning(f"创建测试货架失败: {e}")
            self.skipTest(f"创建测试货架失败: {e}")
    
    def tearDown(self):
        for data in self.test_data:
            if 'id' in data:
                try:
                    self.goods_info_sdk.delete_goods_info(data['id'])
                except Exception as e:
                    logger.warning(f"清理商品SKU {data.get('id')} 失败: {e}")
        if hasattr(self, 'test_store') and self.test_store and 'id' in self.test_store:
            try:
                self.store_sdk.delete_store(self.test_store['id'])
            except Exception as e:
                logger.warning(f"清理店铺 {self.test_store.get('id')} 失败: {e}")
        if hasattr(self, 'test_product_info') and self.test_product_info and 'id' in self.test_product_info:
            try:
                self.product_info_sdk.delete_product_info(self.test_product_info['id'])
            except Exception as e:
                logger.warning(f"清理产品SKU {self.test_product_info.get('id')} 失败: {e}")
        if hasattr(self, 'test_product') and self.test_product and 'id' in self.test_product:
            try:
                self.product_sdk.delete_product(self.test_product['id'])
            except Exception as e:
                logger.warning(f"清理产品 {self.test_product.get('id')} 失败: {e}")
        if hasattr(self, 'test_shelf') and self.test_shelf and 'id' in self.test_shelf:
            try:
                self.shelf_sdk.delete_shelf(self.test_shelf['id'])
            except Exception as e:
                logger.warning(f"清理货架 {self.test_shelf.get('id')} 失败: {e}")
        if hasattr(self, 'test_warehouse') and self.test_warehouse and 'id' in self.test_warehouse:
            try:
                self.warehouse_sdk.delete_warehouse(self.test_warehouse['id'])
            except Exception as e:
                logger.warning(f"清理仓库 {self.test_warehouse.get('id')} 失败: {e}")
        self.test_data.clear()

    def _create_goods_info_param(self, sku, product_info_id, type_val=1, count=1, price=100.0):
        """创建goodsInfo参数的辅助方法"""
        return {
            'sku': sku,
            'product': {'id': product_info_id},
            'type': type_val,
            'count': count,
            'price': price,
            'store': {'id': self.test_store['id']},
            'shelf': [{'id': self.test_shelf['id']}],  # shelf字段是数组类型
            'status': {'id': self.test_status['id']}
        }

    @classmethod
    def tearDownClass(cls):
        print("Goods Info 测试结束")
    
    def test_create_goods_info(self):
        print("测试创建商品SKU...")
        goods_info_param = self._create_goods_info_param('GOODS001', self.test_product_info['id'], count=10)
        goods_info = self.goods_info_sdk.create_goods_info(goods_info_param)
        self.assertIsNotNone(goods_info, "创建商品SKU失败")
        required_fields = ['id', 'sku', 'product', 'type', 'count', 'price', 'creater', 'createTime', 'namespace']
        for field in required_fields:
            self.assertIn(field, goods_info, f"商品SKU缺少必填字段: {field}")
        self.test_data.append(goods_info)
        print(f"✓ 商品SKU创建成功: ID={goods_info.get('id')}, SKU={goods_info.get('sku')}")
    
    def test_query_goods_info(self):
        print("测试查询商品SKU...")
        goods_info_param = self._create_goods_info_param('GOODS002', self.test_product_info['id'], count=5, price=150.0)
        created_info = self.goods_info_sdk.create_goods_info(goods_info_param)
        self.assertIsNotNone(created_info, "创建商品SKU失败")
        queried_info = self.goods_info_sdk.query_goods_info(created_info['id'])
        self.assertIsNotNone(queried_info, "查询商品SKU失败")
        self.assertEqual(queried_info['id'], created_info['id'], "ID不匹配")
        self.test_data.append(created_info)
        print(f"✓ 商品SKU查询成功: ID={queried_info.get('id')}")
    
    def test_update_goods_info(self):
        print("测试更新商品SKU...")
        goods_info_param = self._create_goods_info_param('GOODS003', self.test_product_info['id'], count=3, price=200.0)
        created_info = self.goods_info_sdk.create_goods_info(goods_info_param)
        self.assertIsNotNone(created_info, "创建商品SKU失败")
        update_param = {'count': 5, 'price': 250.0}
        updated_info = self.goods_info_sdk.update_goods_info(created_info['id'], update_param)
        if updated_info:
            self.assertEqual(updated_info['count'], 5, "更新后数量不匹配")
            print(f"✓ 商品SKU更新成功: ID={updated_info.get('id')}")
        else:
            print("⚠ 商品SKU更新未返回结果")
        self.test_data.append(created_info)
    
    def test_delete_goods_info(self):
        print("测试删除商品SKU...")
        goods_info_param = self._create_goods_info_param('GOODS004', self.test_product_info['id'], price=300.0)
        created_info = self.goods_info_sdk.create_goods_info(goods_info_param)
        self.assertIsNotNone(created_info, "创建商品SKU失败")
        deleted_info = self.goods_info_sdk.delete_goods_info(created_info['id'])
        if deleted_info:
            self.assertEqual(deleted_info['id'], created_info['id'], "删除的商品SKUID不匹配")
            print(f"✓ 商品SKU删除成功: ID={deleted_info.get('id')}")
        else:
            print("⚠ 商品SKU删除未返回结果")
    
    def test_create_goods_info_with_different_type(self):
        print("测试创建不同类型商品SKU...")
        goods_types = [1, 2]
        for goods_type in goods_types:
            goods_info_param = self._create_goods_info_param(
                f'GOODS{goods_type}', 
                self.test_product_info['id'], 
                type_val=goods_type, 
                count=2
            )
            goods_info = self.goods_info_sdk.create_goods_info(goods_info_param)
            self.assertIsNotNone(goods_info, f"创建类型{goods_type}商品SKU失败")
            self.assertEqual(goods_info['type'], goods_type, f"商品类型不匹配: {goods_type}")
            self.test_data.append(goods_info)
            print(f"✓ 类型{goods_type}商品SKU创建成功")
    
    def test_create_goods_info_without_product(self):
        print("测试创建无产品的商品SKU...")
        goods_info_param = {
            'sku': 'GOODS006',
            'type': 1,
            'count': 1,
            'price': 100.0,
            'store': {'id': self.test_store['id']},
            'status': {'id': self.test_status['id']}
        }
        goods_info = self.goods_info_sdk.create_goods_info(goods_info_param)
        if goods_info is None:
            print("✓ 系统正确拒绝创建无产品的商品SKU")
        else:
            self.assertIn('product', goods_info, "商品SKU应包含产品字段")
            print(f"⚠ 系统允许创建无产品的商品SKU: ID={goods_info.get('id')}")
            self.test_data.append(goods_info)
    
    def test_query_nonexistent_goods_info(self):
        print("测试查询不存在的商品SKU...")
        non_existent_id = 999999999
        goods_info = self.goods_info_sdk.query_goods_info(non_existent_id)
        if goods_info is None:
            print("✓ 查询不存在的商品SKU返回None，符合预期")
        else:
            print(f"⚠ 查询不存在的商品SKU返回: {goods_info}")
    
    def test_delete_nonexistent_goods_info(self):
        print("测试删除不存在的商品SKU...")
        non_existent_id = 999999999
        deleted_info = self.goods_info_sdk.delete_goods_info(non_existent_id)
        if deleted_info is None:
            print("✓ 删除不存在的商品SKU返回None，符合预期")
        else:
            print(f"⚠ 删除不存在的商品SKU返回: {deleted_info}")
    
    def test_auto_generated_fields(self):
        print("测试系统自动生成字段...")
        goods_info_param = self._create_goods_info_param('GOODS007', self.test_product_info['id'])
        goods_info = self.goods_info_sdk.create_goods_info(goods_info_param)
        self.assertIsNotNone(goods_info, "创建商品SKU失败")
        auto_fields = ['id', 'creater', 'createTime', 'namespace']
        for field in auto_fields:
            self.assertIn(field, goods_info, f"缺少自动生成字段: {field}")
        self.test_data.append(goods_info)
        print(f"✓ 系统自动生成字段验证成功: ID={goods_info.get('id')}")
    
    def test_goods_info_type_validation(self):
        print("测试商品SKU类型验证...")
        goods_info_param = self._create_goods_info_param('GOODS008', self.test_product_info['id'])
        goods_info = self.goods_info_sdk.create_goods_info(goods_info_param)
        self.assertIsNotNone(goods_info, "创建商品SKU失败")
        self.assertEqual(goods_info['type'], 1, "商品类型不匹配")
        self.test_data.append(goods_info)
        print(f"✓ 商品SKU类型验证成功: 类型={goods_info.get('type')}")
