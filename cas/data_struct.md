# 系统参数结构体依赖定义 (Data Structures Dependency Map)

## 1. 核心实体关系图

为了准确生成测试数据（Mock Data），需遵循以下引用顺序：
**Role (基础)** → **Account (依赖 Role)** → **Endpoint (依赖 Account & Role)**
*Namespace 为独立管理实体，但在权限校验逻辑中常与 Scope 字段关联。*

---

## 2. 详细依赖说明

### A. Role (角色) - 基础实体

* **结构体**: `Role`
* 可以通过 `role` 模块进行CURD 操作
* **依赖项**: 引用了外部包 `bc.Privilege`，可以通过 `cas/get_privileges()` 查询系统所有权限清单
* `Status` 字段通常作为过滤条件（2: 启用, 1: 禁用）。
* 可以通过 `role`包进行 CURD 操作。
* 在新建 `Role` 对象时可以通过 `cas/get_privileges()` 查询系统所有权限清单，并选取其中部分权限列表作为 `Role` 对应的权限列表。


### B. Account (账户) - 二级实体

* **结构体**: `Account`
* 可以通过 `account` 模块进行CURD 操作
* **依赖项**: 关联 `RoleLite` 指针。
* **关联约束**:
* 在创建账户时，应确保引用的 `Role` ID, 在系统中已存在, 可以通过 `role/filter_role()` 查询系统当前定义的所有角色
* `Status` 字段通常作为过滤条件（2: 启用, 1: 禁用）。

### C. Endpoint (端点) - 高级关联实体
* **结构体**: `Endpoint`
* 可以通过 `endpoint` 模块进行CURD 操作
* **核心依赖**:
1. `AccountLite`: 关联账户信息，可以通过 `account/filter_account()` 获取系统当前所有账户信息。
2. `RoleLite`: 关联角色信息，可以通过 `role/filter_role()` 获取系统当前所有角色信息。

* **时效性约束**:
* 单位为 **UTC 毫秒**。

### D. Namespace (命名空间) - 权限范围实体

* **结构体**: `Namespace`
* 可以通过 `namespace` 模块进行CURD 操作
* **Scope 逻辑约束**:
* `"*"`: 全局访问。
* `"n1,n2"`: 跨空间访问。
* `""` (空): 仅限自身。

---
