# F033-003：独立卸载中断恢复夹具

本流程准备真实 Live 验证，不修改历史判定。采用新部署的独立实例建立新一轮验证；已清理的历史对象不能用于恢复原证明，普通卸载成功也不满足此用例。

## 新实例验证约定

1. 创建新的应用交付输入和部署申请，以新 installationId/deploymentId 区分本轮，不复用历史终态回执。
2. 为模型实例 A、B 分别新部署 Base/Gateway；A 为目标，B 为不受影响的对照，审批时明确选择不同承载。
3. 先验证新实例安装、业务调用、同名数据隔离及 owner 身份。每次操作前读取当前条件版本；首次错误留证，禁止盲目重放写请求。
4. 普通新实例验证与中断恢复分别记录。若只执行普通流程，保留 F033-003 待验/阻塞；只有新 A 实际发生中断并恢复同一卸载意图，才形成新的恢复证明。

原生承载夹具的 `providerApplicationUuid` 用于核对容器运行身份，应取安装回执的 `packagedReceipt.runtimeApplicationUuid`，不能取发布包的 `applicationUuid`。同一原生包的两个安装实例具有不同运行 UUID。

## 环境与前置证明

使用独立候选环境，创建 `accept-` 前缀模型 A、独占的原生 Base/Gateway，另建不使用这些承载的对照实例 B。冻结当前不可变镜像、配置指纹、namespace、installationId、deploymentId、应用/运行 UUID、制品摘要及资源 ID。不得中断承载已有业务的 core Base/CAS/Panel/Gateway。

通过 owner API 完整分页读取 assignment，不提交手工挑选的子集；Docker 只做容器/启动合同归属核对。使用现有工具检查 provider 专属范围、代际、mount startup 及所有承载：

```bash
python3 ~/codespace/magicTest/tools/runtime_fixture_preflight.py fixtures.json assignment-inventory.json
```

任一 owner 或隔离范围无法核对，保持阻塞。预检是只读结果，不表示故障恢复通过。

## 真实中断点

在隔离环境通过 UI/正常 `POST /panel/application/installations/:id/uninstall` 发起 A 的卸载。提交当前 expectedUpdateTime、expectedDigest、明确 retain/destroy 数据策略、确认和原因，不直接修改持久表、receipt 或 phase。

用隔离环境的请求故障代理在确定的元数据清理请求边界暂停/拒绝一次调用，并保留命中的请求类型和时间；代理不得记录 Bearer、API Key、密码或完整业务内容。先确认 revoked assignment、Base stopped 回执与 Gateway 已撤销路由，再观察安装为 uninstallFailed/uninstalling，且 uninstallation 已开始但未完成。必须保留实际未完成阶段；没有抓到中断、请求尚未提交、已卸载完成均不算该场景。

故障点优先放在实体/管理元数据退役之前，已有运行 drain 和服务清理已由正常流程完成。按照当前实例阶段核对 capabilities/services/assignment 等资源，不通过伪造 completedSteps 推进。已确认 drain 后，只能通过正常运维退役接口停止/移除独占承载，不能强制绕过未 drain 检查。

## 原意图与 drain 检查

把 API 实际返回值整理为 `magic.acceptance.uninstall-checkpoint/v1`：包含 environmentFingerprint、installation（含结构化 receipt）、assignment、runtimeReceipt。保留原 HTTP 文件、owner 回查及摘要；这份组合只用于检查，不回写服务器。

```bash
python3 ~/codespace/magicTest/tools/runtime_fixture_preflight.py fixtures.json \
  --uninstall-checkpoint checkpoint.json
```

工具拒绝普通/完成卸载、不同实例/候选、错误 epoch/grant/generation、缺少 stopped receipt 或 Gateway route 未撤销。输出始终 `livePassed:false`；它检查身份一致性，不证明日志真实性、实际退役、最终资源清理或 B 未受影响。

## 继续与最终判定

移除测试代理故障并重新认证。在“已部署应用”继续同一个卸载，重新读取条件版本，保持原 dataDisposition 与实例身份。再次调用正常 uninstall 入口；不能另建安装/改 approved 摘要以绕开原回执。

通过必须同时确认：

- 原安装最终 uninstalled，未完成卸载阶段收敛，原执行身份没有换成其他 epoch/grant/owner。
- 承载已退役后不再向其执行元数据清理 RPC；已确认 completedSteps 不重复执行。日志只有网络恢复不构成失败，实际业务错误仍保留首次结果。
- 管理元数据、实体、能力、服务、订阅、入口及存储绑定按 scope/实例正常清理，数据按 retain/destroy 约定保留或清除；不删除反重放所需证明。
- 另一实例 B 的数据和业务调用前后相同。恢复后再次读取/继续不能制造新卸载副作用。
- 最终完整分页、Docker/目录、应用读取、数据验证、敏感日志扫描与测试资源清理均留证。

将实际证据交给 `platform_acceptance.py`，绑定目标候选，仅当完整 Live 条件满足才标记 F033-003 passed。源码的 `TestMaterializedModelUninstallResumesWithoutRetiredOwners` 和夹具校验单测不能代替上述现场结果。
