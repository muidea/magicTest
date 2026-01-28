"""
模拟session模块，用于测试框架
"""

class Session:
    def __init__(self):
        self.data = {}
    
    def get(self, key, default=None):
        return self.data.get(key, default)
    
    def set(self, key, value):
        self.data[key] = value
    
    def delete(self, key):
        if key in self.data:
            del self.data[key]
    
    def clear(self):
        self.data.clear()

class MagicSession:
    def __init__(self, server_url=None, namespace=None):
        self.server_url = server_url
        self.namespace = namespace
        self.session = Session()
    
    def get_session(self):
        return self.session
    
    def close(self):
        self.session.clear()
    
    def bind_token(self, token):
        """绑定令牌"""
        self.session.set("token", token)
        return True

# 导出MagicSession类
MagicSession = MagicSession

# 创建全局session实例
session = Session()

# 导出MagicSession类
MagicSession = MagicSession

# 模拟common模块
class CommonModule:
    @staticmethod
    def get_current_user():
        return {"id": 1, "name": "test_user", "role": "admin"}
    
    @staticmethod
    def get_current_tenant():
        return {"id": 1, "name": "test_tenant"}
    
    @staticmethod
    def get_current_org():
        return {"id": 1, "name": "test_org"}

# 导出common模块
common = CommonModule()