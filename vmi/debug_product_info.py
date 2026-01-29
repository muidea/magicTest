#!/usr/bin/env python3
"""
调试productInfo问题
"""

import sys
import os
import json

# 设置环境路径
sys.path.insert(0, '/home/rangh/codespace/magicTest')
sys.path.insert(0, '/home/rangh/codespace/magicTest/cas')
sys.path.insert(0, '/home/rangh/codespace/magicTest/vmi')

import logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

from session import session
from cas.cas import Cas

def debug_product_info():
    """调试productInfo问题"""
    print("调试productInfo问题...")
    
    # 创建session
    work_session = session.MagicSession('https://autotest.local.vpc', '')
    cas_session = Cas(work_session)
    
    if not cas_session.login('administrator', 'administrator'):
        print("CAS登录失败")
        return False
    
    work_session.bind_token(cas_session.get_session_token())
    
    # 直接使用session发送请求，绕过SDK
    print("\n1. 测试直接发送请求...")
    
    # 先创建product
    print("创建product...")
    product_data = {
        'name': '调试产品',
        'description': '调试产品描述',
        'status': {'id': 19}
    }
    
    # 使用session直接发送请求
    from session import common
    # 尝试使用单数路径，避免MagicEntity的复数转换bug
    product_entity = common.MagicEntity('/api/v1/vmi/product', work_session)
    
    try:
        product = product_entity.insert(product_data)
        print(f"创建product成功: {product}")
        product_id = product.get('id') if product else None
    except Exception as e:
        print(f"创建product失败: {e}")
        return False
    
    if not product_id:
        print("无法获取product ID")
        return False
    
    # 测试1: 使用当前参数
    print("\n2. 测试创建productInfo...")
    test_cases = [
        {
            'name': '测试1: 当前参数',
            'data': {
                'sku': '1001',
                'description': '测试SKU描述',
                'product': {'id': product_id},
                'status': {'id': 19}
            }
        },
        {
            'name': '测试2: 简化参数',
            'data': {
                'sku': '1001',
                'product': {'id': product_id}
            }
        },
        {
            'name': '测试3: 只有sku',
            'data': {
                'sku': '1001'
            }
        },
        {
            'name': '测试4: 数字sku',
            'data': {
                'sku': 1001,
                'product': {'id': product_id}
            }
        },
        {
            'name': '测试5: 包含id字段',
            'data': {
                'id': 0,  # 尝试提供id字段
                'sku': '1001',
                'product': {'id': product_id}
            }
        }
    ]
    
    # 尝试不同的路径格式，避免MagicEntity的复数转换bug
    # 测试1: 使用单数
    product_info_entity1 = common.MagicEntity('/api/v1/vmi/product/productInfo', work_session)
    # 测试2: 使用不同的格式
    product_info_entity2 = common.MagicEntity('/api/v1/vmi/productInfo', work_session)
    # 测试3: 使用带斜杠的路径
    product_info_entity3 = common.MagicEntity('/api/v1/vmi/product/productInfo/', work_session)
    
    for i, test_case in enumerate(test_cases):
        print(f"\n{test_case['name']}:")
        print(f"  数据: {json.dumps(test_case['data'], ensure_ascii=False)}")
        
        try:
            result = product_info_entity.insert(test_case['data'])
            if result:
                print(f"  成功: {result}")
                # 清理
                product_info_entity.delete(result.get('id'))
                break
            else:
                print("  失败: 返回None")
        except Exception as e:
            print(f"  异常: {e}")
    
    # 清理
    print(f"\n清理product: {product_id}")
    try:
        product_entity.delete(product_id)
    except Exception as e:
        print(f"清理product失败: {e}")
    
    return True

if __name__ == '__main__':
    success = debug_product_info()
    if success:
        print("\n✅ 调试完成")
    else:
        print("\n❌ 调试失败")
    sys.exit(0 if success else 1)