#!/usr/bin/env python3
"""
调试sku字段类型问题
"""

import sys
import os
import logging

# 设置环境路径
sys.path.insert(0, '/home/rangh/codespace/magicTest')
sys.path.insert(0, '/home/rangh/codespace/magicTest/cas')
sys.path.insert(0, '/home/rangh/codespace/magicTest/vmi')

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

from session import session
from cas.cas import Cas
from sdk import ProductInfoSDK, ProductSDK

def test_sku_types():
    """测试不同sku类型"""
    print("测试不同sku类型...")
    
    # 创建session
    work_session = session.MagicSession('https://autotest.local.vpc', '')
    cas_session = Cas(work_session)
    
    if not cas_session.login('administrator', 'administrator'):
        print("CAS登录失败")
        return False
    
    work_session.bind_token(cas_session.get_session_token())
    
    # 创建SDK实例
    product_sdk = ProductSDK(work_session)
    product_info_sdk = ProductInfoSDK(work_session)
    
    # 先创建product
    print("创建product...")
    product_param = {
        'name': 'SKU类型测试产品',
        'description': '测试sku字段类型',
        'status': {'id': 19}
    }
    product = product_sdk.create_product(product_param)
    if not product:
        print("创建product失败")
        return False
    print(f"创建product成功: ID={product.get('id')}")
    
    # 测试不同sku类型
    test_cases = [
        {'name': '纯数字字符串', 'sku': '1001'},
        {'name': '纯数字整数', 'sku': 1002},
        {'name': '字母数字混合', 'sku': 'ABC123'},
        {'name': '带前缀数字', 'sku': 'SKU1003'},
        {'name': '长数字', 'sku': '12345678901234567890'},
        {'name': '负数字符串', 'sku': '-1004'},
        {'name': '负数字整数', 'sku': -1005},
    ]
    
    results = []
    for i, test_case in enumerate(test_cases):
        print(f"\n测试用例 {i+1}: {test_case['name']}")
        print(f"sku值: {test_case['sku']} (类型: {type(test_case['sku']).__name__})")
        
        product_info_param = {
            'sku': test_case['sku'],
            'description': f'{test_case["name"]}测试',
            'product': {'id': product['id']}
        }
        
        try:
            product_info = product_info_sdk.create_product_info(product_info_param)
            if product_info:
                print(f"✓ 成功: ID={product_info.get('id')}")
                results.append({'test_case': test_case, 'success': True, 'result': product_info})
                # 清理
                product_info_sdk.delete_product_info(product_info['id'])
            else:
                print("✗ 失败: 返回None")
                results.append({'test_case': test_case, 'success': False, 'error': '返回None'})
        except Exception as e:
            print(f"✗ 异常: {e}")
            results.append({'test_case': test_case, 'success': False, 'error': str(e)})
    
    # 清理product
    product_sdk.delete_product(product['id'])
    
    # 输出总结
    print("\n" + "="*50)
    print("测试结果总结:")
    print("="*50)
    success_count = sum(1 for r in results if r['success'])
    print(f"总测试用例: {len(test_cases)}")
    print(f"成功: {success_count}")
    print(f"失败: {len(test_cases) - success_count}")
    
    for i, result in enumerate(results):
        status = "✓" if result['success'] else "✗"
        print(f"{status} {i+1}. {result['test_case']['name']}: {result['test_case']['sku']}")
        if not result['success']:
            print(f"   错误: {result.get('error', '未知错误')}")
    
    return success_count > 0

if __name__ == '__main__':
    success = test_sku_types()
    sys.exit(0 if success else 1)