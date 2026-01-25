# Role Python 客户端

## 概述

`Role` 类是一个用于管理 CAS (Central Authentication Service) 角色的 Python 客户端。它提供了角色的完整 CRUD 操作（创建、读取、更新、删除）以及过滤查询功能，通过 HTTP 请求与后端 CAS API 通信。角色是权限的集合，用于定义用户的访问权限。

**文件位置**: [`magicTest/cas/role/role.py`](magicTest/cas/role/role.py)

## 类定义

```python
class Role:
    """Role"""

    def __init__(self, work_session):
        self.session = work_session
```

### 构造函数参数

- `work_session`: 一个 `MagicSession` 实例，用于处理 HTTP 请求和认证。

### 属性

- `session`: 绑定的 `MagicSession` 实例

## 方法详细说明

### 1. `filter_role(param)`

**功能**: 过滤查询角色列表

**参数**:

- `param`: `dict` - 过滤条件参数，支持按名称、状态、组别等字段过滤

**返回**: `list` 或 `None` - 匹配的角色列表，失败返回 `None`

**内部流程**:

1. 发送 GET 请求到 `/cas/roles/` 并传递过滤参数
2. 检查响应中的错误信息
3. 成功时返回 `values` 字段中的角色列表
4. 失败时记录详细的错误日志

**API 端点**: `GET /cas/roles/`

**示例**:

```python
filter_param = {'name': 'admin', 'status': 2}
roles = role_app.filter_role(filter_param)
```

### 2. `query_role(param)`

**功能**: 查询单个角色的详细信息

**参数**:

- `param`: `str` - 角色的唯一标识符（ID）

**返回**: `dict` 或 `None` - 角色的详细信息，失败返回 `None`

**内部流程**:

1. 发送 GET 请求到 `/cas/roles/{id}`
2. 检查响应中的错误信息
3. 成功时返回 `value` 字段中的角色数据
4. 失败时记录详细的错误日志

**API 端点**: `GET /cas/roles/{id}`

**示例**:

```python
role_id = "1234567890abcdef"
role_info = role_app.query_role(role_id)
```

### 3. `create_role(param)`

**功能**: 创建新的角色

**参数**:

- `param`: `dict` - 角色创建参数，包含以下字段：
  - `name`: `str` - 角色名称（必填）
  - `description`: `str` - 角色描述
  - `group`: `str` - 角色所属组别（如 "admin"、"user"）
  - `privilege`: `list` - 权限列表，每个权限包含以下字段：
    - `id`: `int` - 权限ID
    - `module`: `str` - 模块名称
    - `uriPath`: `str` - URI路径
    - `value`: `int` - 权限值（1=读，2=写，3=执行等）
    - `description`: `str` - 权限描述
  - `status`: `int` - 状态（1=禁用，2=启用）

**返回**: `dict` 或 `None` - 创建的角色信息，失败返回 `None`

**内部流程**:

1. 发送 POST 请求到 `/cas/roles/`
2. 检查响应中的错误信息
3. 成功时返回 `value` 字段中的角色数据
4. 失败时记录详细的错误日志

**API 端点**: `POST /cas/roles/`

**示例**:

```python
param = {
    'name': '管理员',
    'description': '系统管理员角色',
    'group': 'admin',
    'privilege': [
        {
            'id': 1,
            'module': 'magicCas',
            'uriPath': '/api/v1/totalizators',
            'value': 2,
            'description': '用户管理权限'
        }
    ],
    'status': 2
}
new_role = role_app.create_role(param)
```

### 4. `update_role(param)`

**功能**: 更新现有角色

**参数**:

- `param`: `dict` - 角色更新参数，必须包含 `id` 字段

**返回**: `dict` 或 `None` - 更新后的角色信息，失败返回 `None`

**内部流程**:

1. 发送 PUT 请求到 `/cas/roles/{id}`
2. 检查响应中的错误信息
3. 成功时返回 `value` 字段中的角色数据
4. 失败时记录详细的错误日志

**API 端点**: `PUT /cas/roles/{id}`

**示例**:

```python
update_param = {
    'id': '1234567890abcdef',
    'name': '更新后的角色名',
    'description': '更新后的描述',
    'group': 'user',
    'status': 1
}
updated_role = role_app.update_role(update_param)
```

### 5. `delete_role(param)`

**功能**: 删除角色

**参数**:

- `param`: `str` - 要删除的角色 ID

**返回**: `dict` 或 `None` - 被删除的角色信息，失败返回 `None`

**内部流程**:

1. 发送 DELETE 请求到 `/cas/roles/{id}`
2. 检查响应中的错误信息
3. 成功时返回 `value` 字段中的角色数据
4. 失败时记录详细的错误日志

**API 端点**: `DELETE /cas/roles/{id}`

**示例**:

```python
role_id = "1234567890abcdef"
deleted_role = role_app.delete_role(role_id)
```

## 辅助函数

### `mock_role_param(namespace)`

**功能**: 生成模拟的角色参数，用于测试

**参数**:

- `namespace`: `str` - 命名空间标识符（当前未使用）

**返回**: `dict` - 包含随机生成的角色参数

**参数说明**:

- 使用 `mock.common` 模块生成随机名称和描述
- 默认组别为 "admin"
- 包含一个示例权限列表
- 默认状态为启用（2）

**示例**:

```python
from role.role import mock_role_param
param = mock_role_param("test-namespace")
```

### `main(server_url, namespace)`

**功能**: 主函数，演示完整的角色操作流程

**参数**:

- `server_url`: `str` - CAS 服务器 URL
- `namespace`: `str` - 命名空间标识符

**流程**:

1. 创建会话并登录 CAS
2. 生成模拟参数并创建角色
3. 验证创建结果
4. 创建重复角色（测试重复名称处理）
5. 过滤查询角色
6. 查询单个角色
7. 更新角色
8. 删除角色
9. 返回操作结果

## 错误处理机制

`Role` 类实现了完善的错误处理：

1. **HTTP 请求错误**: 检查响应是否为 `None` 或包含 `error` 字段
2. **响应数据验证**: 检查 `value` 或 `values` 字段是否存在
3. **详细日志记录**: 使用 Python `logging` 模块记录不同级别的日志
   - `logger.error()`: 记录错误详情，包括错误代码和消息
   - `logger.info()`: 记录成功操作
4. **错误返回类型**: 所有方法在失败时返回 `None`

## 角色数据结构

### 核心字段

| 字段名        | 类型   | 描述                   | 示例                                     |
| ------------- | ------ | ---------------------- | ---------------------------------------- |
| `id`          | `int`  | 角色唯一标识符         | `12345`                                  |
| `name`        | `str`  | 角色名称               | `"管理员"`                               |
| `description` | `str`  | 角色描述               | `"系统管理员角色"`                       |
| `group`       | `str`  | 角色所属组别           | `"admin"`, `"user"`                      |
| `privilege`   | `list` | 权限列表               | `[{"id": 1, "module": "magicCas", ...}]` |
| `status`      | `int`  | 状态（1=禁用，2=启用） | `2`                                      |

### 权限对象结构

| 字段名        | 类型  | 描述                         | 示例                     |
| ------------- | ----- | ---------------------------- | ------------------------ |
| `id`          | `int` | 权限ID                       | `1`                      |
| `module`      | `str` | 模块名称                     | `"magicCas"`             |
| `uriPath`     | `str` | URI路径                      | `"/api/v1/totalizators"` |
| `value`       | `int` | 权限值（1=读，2=写，3=执行） | `2`                      |
| `description` | `str` | 权限描述                     | `"用户管理权限"`         |

### 状态说明

- `1`: 禁用状态，角色不可用
- `2`: 启用状态，角色可用

## 依赖关系

### 核心依赖

- `session.MagicSession`: HTTP 客户端会话管理
- `cas.Cas`: CAS 认证客户端
- `mock.common`: 模拟数据生成
- `logging`: Python 标准日志模块

### 导入语句

```python
import logging
from session import session
from cas import cas
from mock import common
```

## 使用示例

### 基本用法

```python
from session import session
from cas import cas
from role.role import Role

# 创建会话并登录
server_url = 'https://autotest.local.vpc/api/v1'
work_session = session.MagicSession(server_url, '')
cas_session = cas.Cas(work_session)
if not cas_session.login('administrator', 'administrator'):
    print("CAS登录失败")
    exit(1)

work_session.bind_token(cas_session.get_session_token())

# 创建 Role 客户端
role_app = Role(work_session)

# 创建角色
from role.role import mock_role_param
param = mock_role_param("")
new_role = role_app.create_role(param)
if new_role:
    print(f"创建成功: {new_role['name']} (ID: {new_role['id']})")

    # 查询角色
    queried_role = role_app.query_role(new_role['id'])
    print(f"查询结果: {queried_role['description']}")

    # 更新角色
    update_param = new_role.copy()
    update_param['description'] = '更新后的描述'
    update_param['group'] = 'user'
    updated_role = role_app.update_role(update_param)

    # 删除角色
    deleted_role = role_app.delete_role(new_role['id'])
    print(f"删除成功: {deleted_role['name']}")
```

## API 端点总结

| 方法            | HTTP 方法 | 端点              | 功能             |
| --------------- | --------- | ----------------- | ---------------- |
| `filter_role()` | GET       | `/cas/roles/`     | 过滤查询角色列表 |
| `query_role()`  | GET       | `/cas/roles/{id}` | 查询单个角色     |
| `create_role()` | POST      | `/cas/roles/`     | 创建角色         |
| `update_role()` | PUT       | `/cas/roles/{id}` | 更新角色         |
| `delete_role()` | DELETE    | `/cas/roles/{id}` | 删除角色         |

## 注意事项

1. **认证要求**: 所有操作需要有效的 CAS 会话令牌
2. **权限列表**: 权限列表是可选的，可以为空列表
3. **角色名称唯一性**: 角色名称在系统中应该是唯一的
4. **状态管理**: 禁用状态的角色可能无法被分配或使用
5. **错误处理**: 调用方需要检查每个方法的返回值
6. **日志配置**: 需要预先配置 Python logging 以查看日志输出

## 扩展建议

1. **添加批量操作**: 支持批量创建、更新、删除角色
2. **增加角色分配功能**: 添加将角色分配给用户或用户组的功能
3. **支持权限验证**: 添加验证用户是否拥有特定角色或权限的功能
4. **添加类型提示**: 为方法参数和返回值添加类型提示
5. **完善验证逻辑**: 增加输入参数验证和业务规则验证
6. **支持异步操作**: 添加异步 API 支持以提高性能
7. **添加缓存机制**: 对频繁查询的角色信息添加缓存

## 相关文件

- [`magicTest/cas/role/role.py`](magicTest/cas/role/role.py): 主实现文件
- [`magicTest/cas/role/role_test.py`](magicTest/cas/role/role_test.py): 单元测试文件
- [`magicTest/cas/role/test_cases.md`](magicTest/cas/role/test_cases.md): 测试用例文档
- [`magicTest/session/session.py`](magicTest/session/session.py): HTTP 会话管理
- [`magicTest/cas/cas/cas.py`](magicTest/cas/cas/cas.py): CAS 认证客户端
- [`magicTest/mock/common.py`](magicTest/mock/common.py): 模拟数据生成工具
- [`magicTest/cas/namespace/namespace_documentation.md`](magicTest/cas/namespace/namespace_documentation.md): Namespace 模块文档
