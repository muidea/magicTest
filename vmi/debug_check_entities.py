#!/usr/bin/env python3
"""
检查服务器上可用的实体
"""

import sys
import os
import logging

# 设置环境路径
sys.path.insert(0, '/home/rangh/codespace/magicTest')
sys.path.insert(0, '/home/rangh/codespace/magicTest/cas')
sys.path.insert(0, '/home/rangh/codespace/magicTest/vmi')

logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

from session import session
from cas.cas import Cas

def check_entities():
    """检查服务器实体"""
    print("检查服务器上可用的实体...")
    
    # 创建session
    work_session = session.MagicSession('https://autotest.local.vpc', '')
    cas_session = Cas(work_session)
    
    if not cas_session.login('administrator', 'administrator'):
        print("CAS登录失败")
        return False
    
    work_session.bind_token(cas_session.get_session_token())
    
    # 测试不同实体路径
    test_entities = [
        '/api/v1/vmi/products/',
        '/api/v1/vmi/product/productInfos/',
        '/api/v1/vmi/product/productInfo/',
        '/api/v1/vmi/productInfos/',
        '/api/v1/vmi/productInfo/',
        '/api/v1/vmi/store/goodsInfos/',
        '/api/v1/vmi/store/goodsInfo/',
        '/api/v1/vmi/orders/',
        '/api/v1/vmi/order/',
    ]
    
    results = []
    for entity_path in test_entities:
        print(f"\n测试实体路径: {entity_path}")
        
        # 尝试查询（使用不存在的ID，看错误类型）
        test_id = 999999999
        try:
            response = work_session.get(f'{entity_path}{test_id}')
            print(f"  GET响应: {response}")
            
            # 尝试创建（使用最小参数）
            if 'product' in entity_path:
                create_param = {'sku': 'TEST123', 'description': '测试'}
            elif 'goodsInfo' in entity_path:
                create_param = {'sku': 'TEST456', 'type': 1, 'count': 1}
            else:
                create_param = {'name': '测试'}
                
            create_response = work_session.post(entity_path, create_param)
            print(f"  POST响应: {create_response}")
            
            results.append({'path': entity_path, 'get': response, 'post': create_response})
            
        except Exception as e:
            print(f"  错误: {e}")
            results.append({'path': entity_path, 'error': str(e)})
    
    # 输出总结
    print("\n" + "="*50)
    print("实体检查结果总结:")
    print("="*50)
    
    for result in results:
        path = result['path']
        if 'error' in result:
            print(f"❌ {path}: 错误 - {result['error']}")
        else:
            get_result = "成功" if result.get('get') else "失败"
            post_result = "成功" if result.get('post') else "失败"
            print(f"✓ {path}: GET={get_result}, POST={post_result}")
    
    return True

if __name__ == '__main__':
    success = check_entities()
    sys.exit(0 if success else 1)