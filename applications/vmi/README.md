# VMI 供应商管理库存模拟应用测试与打包套件

本目录维护新版 VMI 标准模型驱动应用（权威模型位于 `~/dataspace/magicPlatform/apps/models/vmi/`）的官方编码构建器、分域模拟器及单元测试。

- [tooling/package_tool.py](~/codespace/magicTest/applications/vmi/tooling/package_tool.py) / [tooling/package_codec_test.go.txt](~/codespace/magicTest/applications/vmi/tooling/package_codec_test.go.txt)：调用 `magicRunner` 官方 `modelpackage.Build/Parse`、`applicationpagecapability.Validate/Inspect`、`FreezeApplicationAuthorization`、`orm.PreflightSchemaChange` 及 `scripteffect.ValidateRuntimeModels` 进行全量离线校验与候选包构建。
- [tooling/simulation_tool.py](~/codespace/magicTest/applications/vmi/tooling/simulation_tool.py)：按 **6 个互不相交功能域服务**（`vmi_partner_service`、`vmi_catalog_service`、`vmi_warehouse_service`、`vmi_inventory_service`、`vmi_order_service`、`vmi_loyalty_service`）路由 18 类实体的 Gateway 写入、按需 `--domains` 筛选查询、`--service-map` 多服务路由与跨域隔离负例校验、Apps 受控动作执行及 `goodsInfo`/`goodsItem -> inventoryAlert` 阈值派生回读验证。
- [tooling/test_package_tool.py](~/codespace/magicTest/applications/vmi/tooling/test_package_tool.py) 与 [tooling/test_simulation_tool.py](~/codespace/magicTest/applications/vmi/tooling/test_simulation_tool.py)：离线单测套件（含模拟 6 域 Gateway 服务端隔离与全链路验证）。

```sh
cd ~/codespace/magicTest
python3 -B applications/vmi/tooling/package_tool.py check
python3 -B -m unittest applications/vmi/tooling/test_package_tool.py applications/vmi/tooling/test_simulation_tool.py applications/live_e2e/test_bootstrap_simulated_apps.py
python3 -B applications/vmi/tooling/simulation_tool.py --service-map /path/to/service-map.json --domains warehouse,order inspect
```
