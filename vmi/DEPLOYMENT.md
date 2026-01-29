# VMI测试框架 - 部署与使用指南

## 📋 概述

本文档提供VMI测试框架的完整部署、配置和使用指南。测试框架与真实VMI服务器进行交互，用于验证系统功能和性能。

## 🚀 快速开始

### 5分钟快速部署

#### 第1步：环境准备（30秒）
```bash
# 1. 创建并激活Python虚拟环境（如果尚未创建）
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或 venv\Scripts\activate  # Windows

# 2. 验证Python环境
python --version
# 应该显示: Python 3.x.x

# 3. 设置环境路径
python setup_env.py
```

#### 第2步：验证连接（1分钟）
```bash
# 验证服务器连接
./verify_real_server.sh

# 或运行完整验证
./verify_setup.sh
```

#### 第3步：运行测试（2分钟）
```bash
# 运行完整测试套件
python test_runner.py

# 或运行特定测试模式
python test_runner.py --mode basic      # 基础功能测试
python test_runner.py --mode concurrent # 并发压力测试
python test_runner.py --mode scenario   # 业务场景测试
```

#### 第4步：验证部署（1分钟）
```bash
# 运行部署验证
python deploy_verification.py
```

## 🔧 详细部署指南

### 系统要求
- **Python**: 3.12.3 或更高版本
- **虚拟环境**: `~/codespace/venv`（推荐）
- **服务器**: 可访问 `https://autotest.local.vpc`
- **认证**: CAS (administrator/administrator)
- **网络**: 稳定的网络连接
- **磁盘空间**: 至少100MB可用空间

### 环境配置

#### 1. 基础环境设置
```bash
# 克隆或复制测试框架
cd vmi  # 进入VMI测试框架目录
cp -r vmi /path/to/deployment/

# 激活虚拟环境
source ~/codespace/venv/bin/activate

# 验证环境
python setup_env.py
```

#### 2. 服务器配置验证
```bash
# 验证服务器可访问性
curl -k https://autotest.local.vpc/health

# 验证CAS认证
python -c "import cas.cas; print('✅ CAS模块可用')"
```

#### 3. 测试框架验证
```bash
# 运行完整验证
./verify_setup.sh

# 验证结果应显示:
# ✅ Python环境验证通过
# ✅ 虚拟环境验证通过  
# ✅ 服务器连接验证通过
# ✅ 测试框架验证通过
```

### 部署验证

#### 部署后验证脚本
```bash
# 运行部署验证
python deploy_verification.py

# 验证内容包括:
# - 环境配置验证
# - 测试套件验证
# - 关键实体验证
# - 性能验证
# - 数据完整性验证
# - 错误处理验证
```

#### 验证报告
验证完成后会生成报告文件：
- `deployment_verification_YYYYMMDD_HHMMSS.json`
- 包含详细的验证结果和性能指标

## 🛠️ 测试框架使用

### 测试运行器

#### 主测试运行器
```bash
# 运行所有测试
python test_runner.py

# 指定测试模式
python test_runner.py --mode basic      # 基础功能测试
python test_runner.py --mode concurrent # 并发压力测试  
python test_runner.py --mode scenario   # 业务场景测试
python test_runner.py --mode all        # 所有测试（默认）

# 指定测试环境
python test_runner.py --env dev        # 开发环境
python test_runner.py --env test       # 测试环境（默认）
python test_runner.py --env stress     # 压力测试环境
python test_runner.py --env prod       # 生产环境
```

#### 测试报告
测试完成后生成：
- `test_report_YYYYMMDD_HHMMSS.json`
- 包含详细的测试结果和统计信息

### 测试类型说明

#### 1. 基础功能测试
- **测试数量**: 215个测试
- **覆盖范围**: 所有核心实体（productInfo, goodsInfo, shelf, warehouse, store, product等）
- **执行时间**: ~30秒
- **通过标准**: 100%通过率

#### 2. 并发压力测试
- **测试数量**: 5个测试
- **并发级别**: 10-15个并发线程
- **测试场景**: 并发创建、查询、更新操作
- **性能指标**: 响应时间、吞吐量、错误率

#### 3. 业务场景测试
- **测试数量**: 6个测试
- **场景覆盖**: 单租户完整业务流程
- **数据规模**: 模拟5万产品、15万SKU
- **验证要点**: 数据完整性、业务逻辑、性能要求

### 高级使用

#### 运行特定测试模块
```bash
# 运行特定实体测试
python -m unittest product.product_info_test
python -m unittest store.goods_info_test
python -m unittest warehouse.shelf_test

# 运行并发测试
python -m unittest concurrent_test.ConcurrentStoreTest
python -m unittest concurrent_test.ConcurrentWarehouseTest

# 运行业务场景测试
python -m unittest scenario_test.SingleTenantScenarioTest
```

#### 性能监控
```bash
# 生成性能报告
python performance_report.py

# 监控测试执行
python test_runner.py --mode all | grep -E "(耗时|通过率|错误)"
```

## 🔄 CI/CD集成

### 基本集成示例
```yaml
# .gitlab-ci.yml 示例
stages:
  - test
  - deploy
  - verify

test_vmi:
  stage: test
  script:
    - source ~/codespace/venv/bin/activate
    - python test_runner.py --mode all --env test
  artifacts:
    paths:
      - test_report_*.json
    when: always

deploy_verification:
  stage: verify
  script:
    - source ~/codespace/venv/bin/activate
    - python deploy_verification.py
  dependencies:
    - test_vmi
```

### 环境变量配置
```bash
# 建议配置的环境变量
export VMI_SERVER_URL="https://autotest.local.vpc"
export VMI_USERNAME="administrator"
export VMI_PASSWORD="administrator"
export VMI_TEST_MODE="functional"
export VMI_MAX_WORKERS="10"
```

## 🚨 故障排除

### 常见问题

#### 1. 服务器连接失败
```bash
# 检查网络连接
ping autotest.local.vpc

# 验证服务器状态
curl -k https://autotest.local.vpc/health

# 检查防火墙规则
iptables -L -n | grep 443
```

#### 2. 认证失败
```bash
# 验证CAS模块
python -c "import cas.cas; print(cas.cas.__version__)"

# 检查凭证
echo "用户名: administrator"
echo "密码: administrator"
```

#### 3. 测试执行失败
```bash
# 检查环境配置
python setup_env.py --verify

# 检查依赖模块
python -c "import session; import cas.cas; print('✅ 所有依赖可用')"

# 查看详细错误
python test_runner.py --mode basic 2>&1 | tail -50
```

#### 4. 性能问题
```bash
# 检查系统资源
top -b -n 1 | head -20

# 检查网络延迟
ping -c 5 autotest.local.vpc

# 优化测试参数
export VMI_MAX_WORKERS=5  # 减少并发数
```

### 调试工具

#### 环境验证脚本
```bash
# 运行完整环境验证
./verify_setup.sh

# 验证服务器连接
./verify_real_server.sh
```

#### 部署验证脚本
```bash
# 运行部署验证
python deploy_verification.py

# 查看验证报告
cat deployment_verification_*.json | jq '.summary'
```

## 📊 监控和维护

### 日常维护任务

#### 1. 定期测试执行
```bash
# 每日完整测试
0 2 * * * source ~/codespace/venv/bin/activate && cd /path/to/vmi && python test_runner.py >> /var/log/vmi_test.log 2>&1

# 每周部署验证
0 3 * * 0 source ~/codespace/venv/bin/activate && cd /path/to/vmi && python deploy_verification.py >> /var/log/vmi_deploy.log 2>&1
```

#### 2. 性能监控
```bash
# 监控测试执行时间
grep "总耗时" test_report_*.json

# 监控测试通过率
grep "成功率" test_report_*.json

# 监控错误率
grep "失败\|错误" test_report_*.json
```

#### 3. 日志管理
```bash
# 清理旧测试报告
find . -name "test_report_*.json" -mtime +7 -delete

# 清理旧部署报告
find . -name "deployment_verification_*.json" -mtime +30 -delete

# 查看最新日志
tail -f /var/log/vmi_test.log
```

### 告警配置

#### 测试失败告警
```bash
# 检查测试结果并发送告警
if python test_runner.py --mode basic | grep -q "✗"; then
  echo "测试失败！" | mail -s "VMI测试告警" admin@example.com
fi
```

#### 性能下降告警
```bash
# 检查测试执行时间
duration=$(python test_runner.py --mode basic 2>&1 | grep "总耗时" | awk '{print $2}' | cut -d'.' -f1)
if [ $duration -gt 60 ]; then
  echo "测试执行时间超过60秒：${duration}秒" | mail -s "VMI性能告警" admin@example.com
fi
```

## 📁 文件结构参考

```
vmi/
├── DEPLOYMENT.md                 # 本文档 - 部署与使用指南
├── TEST_GUIDE.md                # 测试框架详细指南
├── API_REFERENCE.md             # API参考文档
├── README.md                    # 项目概述
├── VMI实体定义和使用说明.md     # 实体定义文档
├── NEXT_STEPS_SUMMARY.md        # 下一步工作指南
├── test_runner.py               # 主测试运行器
├── deploy_verification.py       # 部署验证脚本
├── scenario_test.py             # 业务场景测试
├── concurrent_test.py           # 并发测试
├── base_test_case.py            # 测试基类
├── test_config.py               # 测试配置
├── test_base.py                 # 测试基础模块
├── test_adapter.py              # 测试适配器
├── setup_env.py                 # 环境设置
├── performance_report.py        # 性能报告
├── session_mock.py              # 会话模拟
├── verify_real_server.sh        # 服务器验证脚本
├── verify_setup.sh              # 环境验证脚本
└── [实体模块目录]/
    └── *_test.py                # 各实体测试文件
```

## 📞 支持与联系

### 文档资源
- **本文档**: 部署和使用指南
- **TEST_GUIDE.md**: 测试框架详细指南
- **API_REFERENCE.md**: API接口参考
- **README.md**: 项目概述

### 工具脚本
- `test_runner.py`: 主测试运行器
- `deploy_verification.py`: 部署验证
- `verify_*.sh`: 环境验证脚本

### 故障排查
1. 首先运行 `./verify_setup.sh` 验证环境
2. 查看 `test_report_*.json` 获取详细错误信息
3. 检查服务器连接和认证状态
4. 验证实体定义和API兼容性

---

**最后更新**: 2026-01-29  
**测试状态**: ✅ 所有测试通过 (226/226)  
**部署就绪**: ✅ 已验证通过