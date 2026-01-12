# CAS结构体定义

## 1. 核心实体关系图

**Role (基础)** → **Account (依赖 Role)** → **Endpoint (依赖 Account & Role)**

**Namespace** 为独立管理实体，但在权限校验逻辑中常与 Scope 字段关联

**Cas** 提供用户认证、会话管理、权限获取功能

---

## 2. 详细说明

### Cas (CAS)

参照文档[`magicTest/cas/cas/cas.md`](magicTest/cas/cas/cas.md)

### A. Role (角色)

* **结构体**: `Role`
* 可以通过 `role` 模块进行CURD 操作，参照文档[`magicTest/cas/role/role.md`](magicTest/cas/role/role.md)
* **依赖项**: 引用了外部包 `bc.Privilege`，可以通过 `cas/get_privileges()` 查询系统所有权限清单
* `Status` 字段通常作为过滤条件（2: 启用, 1: 禁用）。
* 可以通过 `role`包进行 CURD 操作。
* 在新建 `Role` 对象时可以通过 `cas/get_privileges()` 查询系统所有权限清单，并选取其中部分权限列表作为 `Role` 对应的权限列表。
* `Role` 要求在同一个namespace下name唯一

### B. Account (账户)

* **结构体**: `Account`
* 可以通过 `account` 模块进行CURD 操作，参照文档[`magicTest/cas/account/account.md`](magicTest/cas/account/account.md)
* **依赖项**: 关联 `RoleLite` 指针。
* **关联约束**:
* 在创建账户时，应确保引用的 `Role` ID, 在系统中已存在, 可以通过 `role/filter_role()` 查询系统当前定义的所有角色
* `Status` 字段通常作为过滤条件（2: 启用, 1: 禁用）。
* `Account` 要求在同一个namespace下name唯一, 邮箱不要求唯一


### C. Endpoint (端点)
* **结构体**: `Endpoint`
* 可以通过 `endpoint` 模块进行CURD 操作，参照文档[`magicTest/cas/endpoint/endpoint.md`](magicTest/cas/endpoint/endpoint.md)
* **核心依赖**:
1. `AccountLite`: 关联账户信息，可以通过 `account/filter_account()` 获取系统当前所有账户信息。
2. `RoleLite`: 关联角色信息，可以通过 `role/filter_role()` 获取系统当前所有角色信息。
* `Endpoint` 要求在同一个namespace下name唯一

### D. Namespace (命名空间)

* **结构体**: `Namespace`
* 可以通过 `namespace` 模块进行CURD 操作，，参照文档[`magicTest/cas/namespace/namespace.md`](magicTest/cas/namespace/namespace.md)
* **Scope 逻辑约束**:
* `"*"`: 全局访问。
* `"n1,n2"`: 跨空间访问。
* `""` (空): 仅限自身。
* 系统内置namespace: panel, 该namespace的scope为"*",可以访问所有其他namespace所涉及的数据
* namespace必须需要先创建后使用，并且只能在有效期时效内访问，未创建和已经失效的namespace将无法访问
* namespace在创建完成后可以通过域名访问，例如：panel.local.vpc表示访问panel命名空间下的数据，autotest.local.vpc表示访问autotest命名空间下的数据
* 允许通过namesapce访问其他有scope权限的namespace下的数据, 被访问的namespace也必须是有效的，并且在访问时，通过http的header头(X-Mp-Namespace)进行指定。
* namespace 要求name唯一

### E. 时间戳
* **单位** UTC 毫秒时戳。
* 新建实体对象时，如果要求输入类似startTime和endTime的字段，则应使用 `time.Now().UnixMilli()` 获取当前时间戳。并且结合有效期范围进行计算。
* 创建实体对象时，应确保时间范围正确，即 `startTime < expireTime`, 并且当前时间必须要在时间范围内，不在范围内则对应的实体对象无效，在业务中使用会导致业务错误。


### F. Status
* **状态** 0: 初始状态, 1: 禁用, 2: 启用
* Acount, Role, Endpoint, Namespace 均包含 `Status` 字段，如果状态为1则表示禁用，被禁用的实体对象只能被查询，无法通过被禁用的实例对象操作其他业务。被禁用的account和endpoint无法登录，被禁用的role所涉及的所有权限被禁止。使用该role的acccount和endpoint无法执行对应的权限操作。被禁用的namespace无法通过访问其对应的所有数据。
* 可以通过对实例对象状态的更新，调整status的值，来控制实例对象是否被禁用。
* 新建实体对象时默认状态为启用。

### G. 唯一性约束
* 如果`namesapce`,`role`,`account`,`endpoint`,`namespace`有name字段，则name字段必须唯一。

---
