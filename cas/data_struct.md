# 系统参数结构体依赖定义 (Data Structures Dependency Map)

## 1. 核心实体关系图

为了准确生成测试数据（Mock Data），需遵循以下引用顺序：
**Role (基础)** → **Account (依赖 Role)** → **Endpoint (依赖 Account & Role)**
*Namespace 为独立管理实体，但在权限校验逻辑中常与 Scope 字段关联。*

---

## 2. 详细依赖说明

### A. Role (角色) - 基础实体

* **结构体**: `Role`
* **依赖项**: 引用了外部包 `bc.Privilege`。
* **单元测试注意**:
* 测试时需要 Mock `bc.Privilege` 对象列表。
* `Status` 字段通常作为过滤条件（2: 启用, 1: 禁用）。



### B. Account (账户) - 二级实体

* **结构体**: `Account`
* **依赖项**: 关联 `RoleLite` 指针。
* **关联约束**:
* 在创建账户测试用例时，应确保引用的 `Role` ID 在系统中已存在或已 Mock。
* `Password` 字段在测试中可能涉及加密解密逻辑。

### C. Endpoint (端点) - 高级关联实体
* **结构体**: `Endpoint`
* **核心依赖**:
1. `AccountLite`: 关联账户信息。
2. `RoleLite`: 关联角色信息。

* **时效性约束**:
* 测试用例必须覆盖时间逻辑：`StartTime` < 当前时间 < `ExpireTime` 为有效，反之为过期。
* 单位为 **UTC 毫秒**。

### D. Namespace (命名空间) - 权限范围实体

* **结构体**: `Namespace`
* **Scope 逻辑约束**:
* `"*"`: 全局访问。
* `"n1,n2"`: 跨空间访问。
* `""` (空): 仅限自身。

* **单元测试注意**: 测试权限隔离（Scope）时，需构造符合上述字符串格式的测试向量。

---

## 3. 字段类型及 Mock 规则参考表

| 字段名 | 类型 | 常用测试值建议 | 说明 |
| --- | --- | --- | --- |
| **Status** | `int` | `2` (Active), `1` (Disabled) | 状态控制 |
| **Timestamp** | `int64` | `1736500000000` | 需注意毫秒级单位 |
| **Scope** | `string` | `"*"` 或 `"namespace_a,namespace_b"` | 权限作用域 |
| ***Lite** | `Struct` | `&RoleLite{ID: 1, Name: "Admin"}` | 简化版的关联对象 |

---
