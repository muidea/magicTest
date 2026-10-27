# magicTest 开发规则

本文件直接规定本仓的职责、边界和开发要求；单独检出本仓即可阅读执行。仓库内位置均相对于仓库根目录，协作项目通过项目名和 Git 地址识别，不依赖固定工作区或外部规范文件才能理解规则。

## 功能定位与边界

- 提供公开 API、浏览器、业务场景和压力验证工具，以及测试目标目录、会话管理和报告；不成为产品业务事实、发行版本、权限策略或恢复流程的 owner。
- 根入口按 foundation、auth、ui、file、platform-core、panel-api、business-scenario、load 组织测试，子目录 runner 保留给专项调试；历史 VMI 测试不能代替最新设备管理／棋牌应用验收。
- 按原普通账号和 ApiKey Endpoint 的真实角色验证正反例，不使用管理员身份替代普通角色成功证明。撤权、租户／实例隔离、版本及原请求身份分别核对。
- 测试只通过 owner 公开接口／页面操作，不直接 SQL 改库、改回执、清运行目录或伪造成功。超时和取消不等于未提交，先查原请求，再按 owner 合同恢复及清理。
- 源码替身、离线包、隔离数据库、部署镜像和 Live 分别记录；保留候选身份、输入、执行日志、截图及独立 owner 回读，失败、跳过和未执行不能算通过。
- 先完成两个模拟应用所有主流程，再补细节；自动按证据判断，不逐项要求用户确认。发现新增平台／框架能力时记录证据、影响、owner 和方案，经统一确认后开发，测试工具不自行放宽权限。

## 协作项目

- magicRunner — https://github.com/muidea/magicRunner.git：应用定义、部署、Apps／Gateway／BFF 接口。
- magicCas — https://github.com/muidea/magicCas.git、magicBase — https://github.com/muidea/magicBase.git、magicFile — https://github.com/muidea/magicFile.git：各自事实的正式核验入口。
- magicWebPortal — https://github.com/muidea/magicWebPortal.git：真实交互与响应式页面。
- magicPlatform — https://github.com/muidea/magicPlatform.git：候选制品、部署入口及平台材料；应用资料仓库 docs 当前未配置 Git 远端，不推测地址。

## 结构、编码与验证

- 使用 Python 3 及已准备的虚拟环境；session／cas／mock 提供客户端与夹具，panel／platform／file／ui／vmi 按目标保存测试。导入沿用各套件入口，不要求所有新测试复制 VMI 的旧 sys.path 模板。
- snake_case 函数／变量、PascalCase 类、明确返回类型，复用现有会话与 SDK；旧 SDK 返回 None 或请求报错须显式失败，不能当空数据或成功。配置从选定环境／本地秘密读取，不提交账号密码。
- 从根目录用 `python3 run_tests.py --list-goals`、`--list`、`--list-presets`、`--list-envs` 核对目标；执行时显式选择 `--goal`、`--target` 或 `--preset`，先运行受影响套件，检查 dry-run 再进入有副作用场景。
- panel-local／autotest-local 是工具内置环境名，不是当前服务已可用的证明；以目标配置和实际健康状态确认，不能强依赖某用户虚拟环境或固定域名。
- 验证工具修改先检查参数、目标选择、错误／跳过报告及清理范围，使用对应 pytest／unittest 或入口回归；压力和远端执行仅在任务授权范围内进行。

## 交付

- 工具、SDK 和断言随公开合同同步；Go owner 变化由工作区同步并验证 vendor，不在测试仓修改其他项目依赖或产品状态。
- 新证据单独归档，历史结果和摘要保持。设计、实现、源码通过和 Live 通过分开；长期规则直接更新本文件，不依赖外部 AGENTS 或本机路径。
- 按仓库分别提交，不提交凭据、运行数据、浏览器会话或生成秘密；跨项目配合注明项目名及已核验 Git 地址。
