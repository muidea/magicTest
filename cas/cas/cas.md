# CAS (Central Authentication Service) Python 客户端

## 概述

`Cas` 类是一个用于与 CAS (Central Authentication Service) 服务进行交互的 Python 客户端。它提供了用户认证、会话管理、权限获取等核心功能，通过 HTTP 请求与后端 CAS API 通信。

**文件位置**: [`magicTest/cas/cas/cas.py`](magicTest/cas/cas/cas.py)

## 类定义

```python
class Cas:
    """Cas"""
    
    def __init__(self, work_session):
        self.session = work_session
        self.session_token = None
        self.current_entity = None
```

### 构造函数参数
- `work_session`: 一个 `MagicSession` 实例，用于处理 HTTP 请求和认证。

### 属性
- `session`: 绑定的 `MagicSession` 实例
- `session_token`: 当前会话令牌（登录后获取），有效期10分钟，10分钟内必须要调用 `refresh()` 方法刷新会话令牌
- `current_entity`: 当前登录的实体信息

## 方法详细说明

### 1. `get_session_token()`
**功能**: 获取当前会话令牌
**返回**: `str` 或 `None` - 当前会话令牌，如果未登录则为 `None`

### 2. `get_current_entity()`
**功能**: 获取当前登录的实体信息
**返回**: `dict` 或 `None` - 实体信息，包含用户/组织等详细信息

### 3. `login(account, password)`
**功能**: 使用账户和密码登录 CAS 系统

**参数**:
- `account`: `str` - 用户名/账户
- `password`: `str` - 密码

**返回**: `bool` - 登录成功返回 `True`，失败返回 `False`

**内部流程**:
1. 发送 POST 请求到 `/cas/session/login/`
2. 检查响应中的错误信息
3. 成功时提取 `sessionToken` 和 `entity` 并存储
4. 记录相应的日志信息

**API 端点**: `POST /cas/session/login/`

### 4. `logout(session_token)`
**功能**: 注销当前会话

**参数**:
- `session_token`: `str` - 要注销的会话令牌

**返回**: `bool` - 注销成功返回 `True`，失败返回 `False`

**内部流程**:
1. 绑定令牌到会话
2. 发送 DELETE 请求到 `/cas/session/logout/`
3. 检查响应错误
4. 记录日志

**API 端点**: `DELETE /cas/session/logout/`

### 5. `refresh(session_token)`
**功能**: 刷新会话令牌（文档中误标为 "verify"）

**参数**:
- `session_token`: `str` - 要刷新的会话令牌

**返回**: `str` 或 `None` - 新的会话令牌，失败返回 `None`

**内部流程**:
1. 绑定令牌到会话
2. 发送 GET 请求到 `/cas/session/refresh/`
3. 检查响应错误
4. 成功时更新 `session_token` 和 `current_entity`
5. 记录日志

**API 端点**: `GET /cas/session/refresh/`

### 6. `get_system_all_privileges()`
**功能**: 获取当前系统所有的权限列表

**返回**: `list` 或 `None` - 权限列表，失败返回 `None`

**内部流程**:
1. 发送 GET 请求到 `/cas/privileges/`
2. 检查响应错误
3. 成功时返回 `values` 字段
4. 失败时记录错误日志

**API 端点**: `GET /cas/privileges/`

## 错误处理机制

`Cas` 类实现了完善的错误处理：

1. **HTTP 请求错误**: 检查 `val` 是否为 `None` 或包含 `error` 字段
2. **响应数据验证**: 检查 `value` 字段是否存在
3. **详细日志记录**: 使用 Python `logging` 模块记录不同级别的日志
   - `logger.error()`: 记录错误详情，包括错误代码和消息
   - `logger.info()`: 记录成功操作
   - `logger.debug()`: 在 `MagicSession` 中记录调试信息

4. **错误返回类型**:
   - `login()`: 返回 `False`
   - `logout()`: 返回 `False`
   - `refresh()`: 返回 `None`
   - `get_privileges()`: 返回 `None`

## 依赖关系

### 核心依赖
- `session.MagicSession`: HTTP 客户端会话管理
- `logging`: Python 标准日志模块

### 导入语句
```python
import logging
from session import session
```

## 使用示例

### 基本用法
```python
from session import session
from cas.cas import Cas

# 创建会话
work_session = session.MagicSession('https://api.example.com', 'your-namespace')

# 创建 CAS 客户端
cas_client = Cas(work_session)

# 登录
if cas_client.login('username', 'password'):
    print(f"登录成功，令牌: {cas_client.get_session_token()}")
    print(f"实体信息: {cas_client.get_current_entity()}")
    
    # 刷新会话
    new_token = cas_client.refresh(cas_client.get_session_token())
    
    # 获取权限
    privileges = cas_client.get_privileges()
    print(f"权限列表: {privileges}")
    
    # 注销
    cas_client.logout(cas_client.get_session_token())
else:
    print("登录失败")
```

### 主函数示例
文件中包含的 `main()` 函数展示了完整的使用流程：

```python
def main(server_url, namespace):
    work_session = session.MagicSession('{0}'.format(server_url), namespace)
    app = Cas(work_session)
    app.login('administrator', 'administrator')
    app.refresh(app.session_token)
    privileges = app.get_privileges()
    print('权限列表: %s', privileges)
    app.logout(app.session_token)
```

## 注意事项

1. **会话管理**: `Cas` 类不自动管理令牌过期，需要调用 `refresh()` 方法手动刷新
2. **线程安全**: 未明确说明线程安全性，建议每个线程使用独立的 `Cas` 实例
3. **错误处理**: 调用方需要检查每个方法的返回值以确定操作是否成功
4. **日志配置**: 需要预先配置 Python logging 以查看日志输出
5. **MagicSession 配置**: `MagicSession` 需要正确配置 SSL 验证和超时设置

## API 端点总结

| 方法 | HTTP 方法 | 端点 | 功能 |
|------|-----------|------|------|
| `login()` | POST | `/cas/session/login/` | 用户登录 |
| `logout()` | DELETE | `/cas/session/logout/` | 用户注销 |
| `refresh()` | GET | `/cas/session/refresh/` | 会话刷新 |
| `get_privileges()` | GET | `/cas/privileges/` | 获取权限 |

## 扩展建议

1. **添加令牌自动刷新**: 实现令牌过期前的自动刷新机制
2. **增加重试逻辑**: 对网络请求添加重试机制
3. **支持更多认证方式**: 扩展支持 OAuth、API Key 等认证方式
4. **添加类型提示**: 为方法参数和返回值添加类型提示
5. **完善文档字符串**: 补充更详细的文档字符串说明