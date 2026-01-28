#!/usr/bin/env python3
"""验证测试是否真的在服务器上创建了数据"""

import sys
import os
import logging
import time
import urllib3

# 禁用SSL警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 设置详细日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

print("=== 验证测试数据创建 ===")

# 添加路径
sys.path.insert(0, '/home/rangh/codespace/magicTest/session')
sys.path.insert(0, '/home/rangh/codespace/magicTest/cas/cas')

try:
    # 导入模块
    from session import MagicSession
    import common
    
    print("✓ 导入模块成功")
    
    # 创建session
    server_url = 'https://autotest.local.vpc'
    work_session = MagicSession(server_url, '')
    print(f"✓ 创建 MagicSession: {server_url}")
    
    # 导入并修复cas模块
    cas_file = '/home/rangh/codespace/magicTest/cas/cas/cas.py'
    with open(cas_file, 'r', encoding='utf-8') as f:
        cas_content = f.read()
    
    # 临时修复导入
    if 'from session import session' in cas_content:
        cas_content = cas_content.replace('from session import session', 'from session import MagicSession as session')
        with open(cas_file, 'w', encoding='utf-8') as f:
            f.write(cas_content)
        print("✓ 临时修复cas模块导入")
    
    from cas.cas import Cas
    
    # 创建CAS实例并登录
    cas_session = Cas(work_session)
    print("✓ 创建 Cas 实例")
    
    print("尝试登录...")
    login_result = cas_session.login('administrator', 'administrator')
    print(f"登录结果: {login_result}")
    
    if login_result:
        token = cas_session.get_session_token()
        work_session.bind_token(token)
        print("✓ 登录成功并绑定token")
        
        # 创建MagicEntity
        entity = common.MagicEntity('/api/v1/vmi/store', work_session)
        print("✓ 创建 MagicEntity")
        
        # 获取当前店铺数量
        print("\n=== 获取当前店铺数量 ===")
        stores_before = entity.filter({})
        count_before = len(stores_before) if stores_before else 0
        print(f"测试前店铺数量: {count_before}")
        
        # 运行一个测试
        print("\n=== 运行store测试 ===")
        import subprocess
        result = subprocess.run(
            ['python', '-m', 'pytest', 'store/store_test.py::StoreTestCase::test_create_store', '-v', '-s'],
            capture_output=True,
            text=True,
            cwd='/home/rangh/codespace/magicTest/vmi'
        )
        
        print("测试输出:")
        print(result.stdout)
        if result.stderr:
            print("测试错误:")
            print(result.stderr)
        
        # 等待一下让数据同步
        time.sleep(1)
        
        # 获取测试后的店铺数量
        print("\n=== 获取测试后店铺数量 ===")
        stores_after = entity.filter({})
        count_after = len(stores_after) if stores_after else 0
        print(f"测试后店铺数量: {count_after}")
        
        # 比较数量
        if count_after > count_before:
            print(f"✓ 测试创建了 {count_after - count_before} 个新店铺")
            print("新创建的店铺:")
            for store in stores_after:
                if stores_before is None or store not in (stores_before or []):
                    print(f"  ID: {store.get('id')}, Name: {store.get('name')}, Code: {store.get('code')}")
        elif count_after == count_before:
            print("⚠ 店铺数量没有变化，可能测试数据被清理了")
        else:
            print("⚠ 店铺数量减少了，可能有其他操作")
            
        # 检查测试是否真的调用了API
        print("\n=== 检查网络请求日志 ===")
        # 重新运行测试并捕获urllib3日志
        import io
        from contextlib import redirect_stdout, redirect_stderr
        
        # 设置urllib3日志级别
        urllib3_logger = logging.getLogger('urllib3')
        urllib3_logger.setLevel(logging.DEBUG)
        
        # 捕获输出
        output = io.StringIO()
        
        # 运行测试
        print("重新运行测试并捕获网络请求...")
        test_result = subprocess.run(
            ['python', '-m', 'pytest', 'store/store_test.py::StoreTestCase::test_create_store', '-v', '--tb=short'],
            capture_output=True,
            text=True,
            cwd='/home/rangh/codespace/magicTest/vmi',
            env={**os.environ, 'PYTHONPATH': '/home/rangh/codespace/magicTest/session:/home/rangh/codespace/magicTest/cas/cas'}
        )
        
        # 检查输出中是否有网络请求
        if 'autotest.local.vpc' in test_result.stdout or 'autotest.local.vpc' in test_result.stderr:
            print("✓ 测试中检测到对 autotest.local.vpc 的网络请求")
            
            # 提取相关日志
            lines = test_result.stdout.split('\n') + test_result.stderr.split('\n')
            request_lines = [line for line in lines if 'autotest.local.vpc' in line]
            
            if request_lines:
                print("网络请求日志:")
                for line in request_lines[:10]:  # 只显示前10行
                    print(f"  {line}")
            else:
                print("⚠ 没有找到具体的网络请求日志")
        else:
            print("✗ 测试中没有检测到网络请求")
            
    else:
        print("✗ CAS登录失败")
        
except Exception as e:
    print(f"✗ 测试过程中出现异常: {e}")
    import traceback
    traceback.print_exc()

print("\n=== 验证完成 ===")