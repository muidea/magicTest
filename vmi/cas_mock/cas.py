"""
模拟cas模块，用于测试框架
"""

class CAS:
    def __init__(self, work_session=None):
        self.work_session = work_session
        self.data = {}
    
    def login(self, username, password):
        """模拟登录"""
        print(f"模拟登录: {username}")
        return True
    
    def get_session_token(self):
        """获取会话令牌"""
        return "mock_session_token"
    
    def refresh(self):
        """刷新会话"""
        return True
    
    def get(self, key, default=None):
        return self.data.get(key, default)
    
    def set(self, key, value):
        self.data[key] = value
    
    def delete(self, key):
        if key in self.data:
            del self.data[key]
    
    def clear(self):
        self.data.clear()

# 创建全局cas实例
cas = CAS()

# 导出Cas类（注意大小写，现有测试使用Cas）
Cas = CAS