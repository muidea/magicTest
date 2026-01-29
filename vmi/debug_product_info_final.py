#!/usr/bin/env python3
"""
最终调试productInfo问题
"""

import sys
import os
import json

# 设置环境路径
sys.path.insert(0, '/home/rangh/codespace/magicTest')
sys.path.insert(0, '/home/rangh/codespace/magicTest/cas')
sys.path.insert(0, '/home/rangh/codespace/magicTest/vmi')

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

from session import session
from cas.cas import Cas
from session import common

def test_different_paths():
    """测试不同的路径格式"""
    print("测试不同的路径格式...")
    
    # 创建session
    work_session = session.MagicSession('https://autotest.local.vpc', '')
    cas_session = Cas(work_session)
    
    if not cas_session.login('administrator', 'administrator'):
        print("CAS登录失败")
        return False
    
    work_session.bind_token(cas_session.get_session_token())
    
    # 先创建product
    print("创建product...")
    product_entity = common.MagicEntity('/api/v1/vmi/product', work_session)
    product_data = {
        'name': '测试产品',
        'description': '测试产品描述',
        'status': {'id': 19}
    }
    
    product = product_entity.insert(product_data)
    if not product or 'id' not in product:
        print("创建product失败")
        return False
    
    product_id = product['id']
    print(f"创建product成功: ID={product_id}")
    
    # 测试不同的路径
    test_paths = [
        '/api/v1/vmi/product/productInfo',  # 单数
        '/api/v1/vmi/productInfo',  # 没有product前缀
        '/api/v1/vmi/product/productInfo/',  # 带斜杠
        '/vmi/product/productInfo',  # 没有/api/v1前缀
        '/vmi/productInfo',  # 简写
    ]
    
    test_data = {
        'sku': '1001',
        'description': '测试SKU',
        'product': {'id': product_id},
        'status': {'id': 19}
    }
    
    for path in test_paths:
        print(f"\n测试路径: {path}")
        try:
            entity = common.MagicEntity(path, work_session)
            result = entity.insert(test_data)
            if result:
                print(f"  成功: ID={result.get('id')}")
                # 清理
                entity.delete(result.get('id'))
                break
            else:
                print("  失败: 返回None")
        except Exception as e:
            print(f"  异常: {e}")
    
    # 清理
    print(f"\n清理product: {product_id}")
    product_entity.delete(product_id)
    
    return True

def check_sdk_path():
    """检查SDK路径问题"""
    print("\n检查SDK路径问题...")
    
    # 检查product_info SDK的当前路径
    from sdk.product_info import ProductInfoSDK
    
    # 创建session
    work_session = session.MagicSession('https://autotest.local.vpc', '')
    cas_session = Cas(work_session)
    
    if not cas_session.login('administrator', 'administrator'):
        print("CAS登录失败")
        return False
    
    work_session.bind_token(cas_session.get_session_token())
    
    # 创建SDK实例
    sdk = ProductInfoSDK(work_session)
    
    # 检查entity路径
    print(f"SDK entity_path: {sdk.entity_path}")
    print(f"SDK entity对象: {sdk.entity}")
    
    # 尝试创建
    print("\n尝试使用SDK创建...")
    
    # 先创建product
    from sdk.product import ProductSDK
    product_sdk = ProductSDK(work_session)
    product = product_sdk.create_product({
        'name': 'SDK测试产品',
        'description': 'SDK测试',
        'status': {'id': 19}
    })
    
    if not product:
        print("创建product失败")
        return False
    
    product_id = product['id']
    print(f"创建product成功: ID={product_id}")
    
    # 尝试创建productInfo
    result = sdk.create_product_info({
        'sku': 'SDK1001',
        'description': 'SDK测试SKU',
        'product': {'id': product_id},
        'status': {'id': 19}
    })
    
    if result:
        print(f"创建productInfo成功: {result}")
        sdk.delete_product_info(result['id'])
    else:
        print("创建productInfo失败")
    
    # 清理
    product_sdk.delete_product(product_id)
    
    return result is not None

if __name__ == '__main__':
    print("=" * 60)
    print("productInfo问题调试")
    print("=" * 60)
    
    # test_different_paths()
    check_sdk_path()
    
    print("\n" + "=" * 60)
    print("调试完成")
    print("=" * 60)