import unittest
import sys
import os

from test_base import TestBase
from test_config import TestConfig


class LegacyTestAdapter(TestBase):
    def setUp(self):
        super().setUp()
        self.legacy_data = {}
    
    def create_test_store(self, name="测试店铺", code="STORE_001"):
        store_data = {
            'name': name,
            'code': code,
            'address': '测试地址',
            'contact': 'test@store.com',
            'status': 'active'
        }
        return self.create_entity('store', store_data)
    
    def create_test_warehouse(self, name="测试仓库", code="WAREHOUSE_001"):
        warehouse_data = {
            'name': name,
            'code': code,
            'address': '仓库地址',
            'contact': 'warehouse@test.com',
            'status': 'active'
        }
        return self.create_entity('warehouse', warehouse_data)
    
    def create_test_shelf(self, warehouse_id, code="SHELF_001", capacity=5000):
        shelf_data = {
            'warehouse_id': warehouse_id,
            'code': code,
            'capacity': capacity,
            'used_capacity': 0,
            'location': 'Zone 1',
            'status': 'active'
        }
        return self.create_entity('shelf', shelf_data)
    
    def create_test_product(self, name="测试产品", code="PRODUCT_001"):
        product_data = {
            'name': name,
            'code': code,
            'category': '电子',
            'description': '产品描述',
            'status': 'active'
        }
        return self.create_entity('product', product_data)
    
    def create_test_sku(self, product_id, sku_code="SKU_001"):
        sku_data = {
            'product_id': product_id,
            'sku': sku_code,
            'color': '红色',
            'size': 'M',
            'price': 100.0
        }
        return self.create_entity('sku', sku_data)
    
    def create_test_goods(self, store_id, product_id, sku_id, quantity=10):
        goods_data = {
            'store_id': store_id,
            'product_id': product_id,
            'sku_id': sku_id,
            'quantity': quantity,
            'price': 150.0,
            'status': 'onshelf',
            'shelf_id': None
        }
        return self.create_entity('goods', goods_data)
    
    def create_test_stockin(self, warehouse_id, store_id):
        stockin_data = {
            'warehouse_id': warehouse_id,
            'store_id': store_id,
            'type': 'in',
            'status': 'completed',
            'remark': '测试入库'
        }
        return self.create_entity('stockin', stockin_data)
    
    def create_test_stockout(self, warehouse_id, store_id):
        stockout_data = {
            'warehouse_id': warehouse_id,
            'store_id': store_id,
            'type': 'out',
            'status': 'completed',
            'remark': '测试出库'
        }
        return self.create_entity('stockout', stockout_data)


def migrate_legacy_tests():
    """迁移现有测试到新架构"""
    
    test_files = [
        'credit/credit_test.py',
        'store/store_test.py',
        'store/goods_test.py',
        'store/stockin_test.py',
        'store/stockout_test.py',
        'store/member_test.py',
        'warehouse/warehouse_test.py',
        'warehouse/shelf_test.py',
        'product/product_test.py',
        'partner/partner_test.py'
    ]
    
    for test_file in test_files:
        if os.path.exists(test_file):
            print(f"检查测试文件: {test_file}")
            
            with open(test_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            if 'BaseTestCase' in content:
                print(f"  - 需要迁移: {test_file}")
                
                new_content = content.replace(
                    'from base_test_case import BaseTestCase',
                    'from test_adapter import LegacyTestAdapter'
                ).replace(
                    'class CreditTest(BaseTestCase):',
                    'class CreditTest(LegacyTestAdapter):'
                ).replace(
                    'class StoreTest(BaseTestCase):',
                    'class StoreTest(LegacyTestAdapter):'
                ).replace(
                    'class GoodsTest(BaseTestCase):',
                    'class GoodsTest(LegacyTestAdapter):'
                ).replace(
                    'class StockinTest(BaseTestCase):',
                    'class StockinTest(LegacyTestAdapter):'
                ).replace(
                    'class StockoutTest(BaseTestCase):',
                    'class StockoutTest(LegacyTestAdapter):'
                ).replace(
                    'class MemberTest(BaseTestCase):',
                    'class MemberTest(LegacyTestAdapter):'
                ).replace(
                    'class WarehouseTest(BaseTestCase):',
                    'class WarehouseTest(LegacyTestAdapter):'
                ).replace(
                    'class ShelfTest(BaseTestCase):',
                    'class ShelfTest(LegacyTestAdapter):'
                ).replace(
                    'class ProductTest(BaseTestCase):',
                    'class ProductTest(LegacyTestAdapter):'
                ).replace(
                    'class PartnerTest(BaseTestCase):',
                    'class PartnerTest(LegacyTestAdapter):'
                )
                
                backup_file = test_file + '.backup'
                with open(backup_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                with open(test_file, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                
                print(f"  - 已迁移并备份到: {backup_file}")
            else:
                print(f"  - 无需迁移: {test_file}")


class IntegratedTestSuite:
    def __init__(self):
        self.test_suite = unittest.TestSuite()
    
    def load_all_tests(self):
        """加载所有测试"""
        
        loader = unittest.TestLoader()
        
        # 加载基础测试
        from test_adapter import LegacyTestAdapter
        from concurrent_test import ConcurrentStoreTest, ConcurrentWarehouseTest
        from scenario_test import SingleTenantScenarioTest
        
        # 加载现有模块测试
        test_modules = [
            'credit.credit_test',
            'store.store_test',
            'store.goods_test',
            'store.stockin_test',
            'store.stockout_test',
            'store.member_test',
            'warehouse.warehouse_test',
            'warehouse.shelf_test',
            'product.product_test',
            'partner.partner_test'
        ]
        
        for module_name in test_modules:
            try:
                module = __import__(module_name, fromlist=["*"])
                self.test_suite.addTests(loader.loadTestsFromModule(module))
                print(f"加载模块: {module_name}")
            except Exception as e:
                print(f"加载模块 {module_name} 失败: {e}")
        
        # 加载新架构测试
        self.test_suite.addTests(loader.loadTestsFromTestCase(ConcurrentStoreTest))
        self.test_suite.addTests(loader.loadTestsFromTestCase(ConcurrentWarehouseTest))
        self.test_suite.addTests(loader.loadTestsFromTestCase(SingleTenantScenarioTest))
        
        return self.test_suite
    
    def run_tests(self, verbosity=2):
        """运行所有测试"""
        
        runner = unittest.TextTestRunner(verbosity=verbosity)
        result = runner.run(self.test_suite)
        
        return {
            'total_tests': result.testsRun,
            'failures': len(result.failures),
            'errors': len(result.errors),
            'successful': result.testsRun - len(result.failures) - len(result.errors),
            'success_rate': (result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100 if result.testsRun > 0 else 0
        }


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='测试迁移工具')
    parser.add_argument('--migrate', action='store_true', help='迁移现有测试到新架构')
    parser.add_argument('--run', action='store_true', help='运行集成测试套件')
    parser.add_argument('--verbosity', type=int, default=2, help='测试输出详细程度')
    
    args = parser.parse_args()
    
    if args.migrate:
        print("开始迁移现有测试到新架构...")
        migrate_legacy_tests()
        print("迁移完成!")
    
    if args.run:
        print("运行集成测试套件...")
        suite = IntegratedTestSuite()
        suite.load_all_tests()
        result = suite.run_tests(verbosity=args.verbosity)
        
        print(f"\n测试结果:")
        print(f"  总测试数: {result['total_tests']}")
        print(f"  通过: {result['successful']}")
        print(f"  失败: {result['failures']}")
        print(f"  错误: {result['errors']}")
        print(f"  成功率: {result['success_rate']:.1f}%")