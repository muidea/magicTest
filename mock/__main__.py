"""Mock module entry point"""

import sys
import common


def main():
    """Main function for mock module"""
    print("Mock data generation utilities")
    print("==============================")
    
    # 演示各种mock函数
    print(f"随机单词: {common.word()}")
    print(f"随机句子: {common.sentence()}")
    print(f"随机数字: {common.random_int(1, 100)}")
    print(f"随机邮箱: {common.email()}")
    print(f"随机URL: {common.url()}")
    print(f"随机IP地址: {common.ip_address()}")
    print(f"随机时间戳: {common.current_time()}")
    
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)