#!/usr/bin/env python3
"""运行测试并启用详细日志"""

import os
import sys
import logging

# 设置详细日志
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# 禁用SSL警告
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

print("=== 运行测试并启用详细日志 ===")

# 添加路径
sys.path.insert(0, '/home/rangh/codespace/magicTest/session')

# 运行测试
import subprocess

# 设置环境变量以启用详细日志
env = os.environ.copy()
env['PYTHONPATH'] = '/home/rangh/codespace/magicTest/session:/home/rangh/codespace/magicTest/cas/cas'
env['LOG_LEVEL'] = 'DEBUG'

print("运行 store 测试...")
result = subprocess.run(
    ['python', '-m', 'pytest', 'store/store_test.py::StoreTestCase::test_create_store', '-v', '-s'],
    capture_output=True,
    text=True,
    cwd='/home/rangh/codespace/magicTest/vmi',
    env=env
)

print("\n=== 测试输出 ===")
print(result.stdout)

if result.stderr:
    print("\n=== 测试错误 ===")
    print(result.stderr)

print("\n=== 分析网络请求 ===")

# 检查输出中是否有网络请求迹象
output = result.stdout + result.stderr

# 检查关键指标
indicators = [
    ('autotest.local.vpc', '服务器域名'),
    ('HTTPS', 'HTTPS协议'),
    ('POST', 'POST请求'),
    ('GET', 'GET请求'),
    ('urllib3', 'urllib3库'),
    ('connection', '网络连接'),
    ('session', 'session模块'),
    ('MagicSession', 'MagicSession类'),
    ('Cas', 'Cas类'),
    ('login', '登录操作'),
    ('token', 'token相关'),
    ('Authorization', '授权头')
]

found_indicators = []
for indicator, description in indicators:
    if indicator.lower() in output.lower():
        found_indicators.append((indicator, description))

if found_indicators:
    print("✓ 检测到网络请求迹象:")
    for indicator, description in found_indicators:
        print(f"  - {indicator}: {description}")
else:
    print("✗ 未检测到网络请求迹象")

# 检查是否有实际的请求日志
if 'Making' in output and 'request to' in output:
    print("✓ 检测到具体的网络请求日志")
    # 提取请求日志
    lines = output.split('\n')
    request_lines = [line for line in lines if 'Making' in line and 'request to' in line]
    for line in request_lines:
        print(f"  {line}")
else:
    print("⚠ 未检测到具体的网络请求日志")

print("\n=== 测试完成 ===")