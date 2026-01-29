# VMI测试快速参考

## 🚀 快速命令

### 运行测试
```bash
# 完整测试套件
python test_runner.py

# 特定实体测试
python -m unittest product.product_info_test.ProductInfoTestCase
python -m unittest store.goods_info_test.GoodsInfoTestCase
python -m unittest warehouse.shelf_test.ShelfTestCase

# 详细输出
python -m unittest product.product_info_test.ProductInfoTestCase -v
```

### 检查状态
```bash
# 查看测试结果
python test_runner.py 2>&1 | grep -A5 "总体统计"

# 查看最新报告
cat $(ls -t test_report_*.json | head -1) | python -m json.tool | head -20
```

## 📊 测试统计
- **总测试**: 220个 ✅
- **通过率**: 100% ✅
- **基础测试**: 215个
- **并发测试**: 5个

## 🔧 关键修复

### productInfo
- **问题**: sku字段类型错误
- **修复**: 字符串类型 ✓
- **测试**: 12个全部通过

### goodsInfo  
- **问题**: 缺少shelf字段
- **修复**: 添加shelf字段（数组格式）
- **格式**: `'shelf': [{'id': shelf_id}]`
- **测试**: 10个全部通过

### shelf
- **注意**: capacity不能为0
- **测试**: 16个全部通过

## ⚠️ 常见错误

| 错误代码 | 含义 | 解决方法 |
|----------|------|----------|
| 2 | 记录不存在 | 检查ID是否正确 |
| 4 | 必填字段缺失 | 检查实体定义 |
| 6 | 字段值无效 | 检查字段约束 |

## 📞 调试命令
```bash
# 运行单个测试
python -m unittest store.goods_info_test.GoodsInfoTestCase.test_create_goods_info -v

# 查看错误详情
python test_runner.py 2>&1 | grep -B5 "FAIL\|ERROR"
```

## 🎯 验证命令
```bash
# 验证所有测试通过
python test_runner.py 2>&1 | grep "✓ 所有测试通过"

# 验证关键实体
python -m unittest product.product_info_test.ProductInfoTestCase 2>&1 | grep "OK"
python -m unittest store.goods_info_test.GoodsInfoTestCase 2>&1 | grep "OK"
```

---

**状态**: ✅ 所有测试通过  
**文档**: 查看 TEST_USAGE_GUIDE.md 获取完整指南  
**更新**: 2026-01-29