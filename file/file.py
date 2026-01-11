"""File"""

import logging
from session import session
from file import file
from mock import common

# 配置日志
logger = logging.getLogger(__name__)


def mock_file_param():
    return {
        'name': common.word(),
        'path': common.word(),
        'size': common.number(100, 10000),
        'type': common.word()
    }


def main(server_url, namespace):
    """main"""
    work_session = session.MagicSession('{0}'.format(server_url), namespace)
    app = file.File("test_scope", "test_source", None, work_session)
    
    # 创建测试文件
    test_file_path = "./test_upload.txt"
    try:
        with open(test_file_path, "w") as f:
            f.write("测试文件内容")
        
        # 上传文件
        new_file = app.upload_file(test_file_path)
        if not new_file:
            logger.error('上传文件失败')
            return False
        
        # 过滤文件
        file_list = app.filter_file()
        if not file_list or len(file_list) <= 0:
            logger.error('过滤文件失败')
            return False
        
        # 查询文件
        queried_file = app.query_file(new_file['id'])
        if not queried_file:
            logger.error('查询文件失败')
            return False
        
        # 查看文件
        viewed_file = app.view_file(new_file['token'])
        if not viewed_file:
            logger.error('查看文件失败')
            return False
        
        # 删除文件
        deleted_file = app.delete_file(new_file['id'])
        if not deleted_file:
            logger.error('删除文件失败')
            return False
        
        return True
        
    except Exception as e:
        logger.error('文件操作失败: %s', e)
        return False
    finally:
        # 清理测试文件
        import os
        if os.path.exists(test_file_path):
            os.remove(test_file_path)


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("用法: python file.py <server_url> <namespace>")
        sys.exit(1)
    
    server_url = sys.argv[1]
    namespace = sys.argv[2]
    
    success = main(server_url, namespace)
    sys.exit(0 if success else 1)