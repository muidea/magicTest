#!/usr/bin/env python3
"""离线联调正式发布/物化产物与 Base 真实解释器生命周期，不访问 Live。"""

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import stat
import socket
import secrets
import subprocess
import tempfile

from acceptance_evidence import EvidenceDirectory
from acceptance_candidate import bind_candidate


def archive_required_proofs(directory, evidence, names):
    """Keep each verified independent original after the temporary run is removed."""
    for name in names:
        source = Path(directory) / name
        if not source.is_file():
            raise RuntimeError(f"required independent proof missing: {name}")
        if evidence is None:
            continue
        # Replacement proofs already use this flattened archival name.
        archived_name = name.replace("/", "-")
        archived = evidence.directory / archived_name
        if not archived.exists():
            evidence.copy(source, archived_name)
        if archived.is_symlink() or archived.read_bytes() != source.read_bytes():
            raise RuntimeError(f"archived independent proof differs: {name}")


def private_journal_path(path, *, exporting):
    """Keep cross-run database credentials out of public acceptance artifacts."""
    path = path.absolute()
    parent = path.parent
    if parent.resolve() != parent or not parent.is_dir():
        raise ValueError("journal handoff parent must be a real private directory")
    info = parent.stat()
    if stat.S_IMODE(info.st_mode) != 0o700 or info.st_uid != os.getuid():
        raise ValueError("journal handoff directory must be owned by the current user with mode 0700")
    if path.is_symlink() or (exporting and path.exists()):
        raise ValueError("journal export must be new; handoff symlinks are forbidden")
    for ancestor in (parent, *parent.parents):
        if (ancestor / "SHA256SUMS").exists() or ancestor.name == "acceptance":
            raise ValueError("private journal credentials cannot enter acceptance evidence")
    if not exporting:
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_uid != os.getuid() or info.st_size > 65536:
            raise ValueError("journal input must be a bounded current-user private 0600 file")
    return path


def source_snapshot(workspace, panel_entities):
    """Bind a joint run to its owners, consumer code and declaration inputs."""
    paths = {Path(__file__).resolve(), Path(__file__).with_name("acceptance_evidence.py").resolve(),
             Path(__file__).with_name("acceptance_candidate.py").resolve()}
    for name in ("magicCommon", "magicEngine", "magicOrm", "magicModulesRepo", "magicBase", "magicCas", "magicFile", "magicRunner"):
        repository = workspace / name
        for directory, children, files in os.walk(repository):
            children[:] = [name for name in children if name not in (".git", "vendor", "node_modules", "bin")]
            for name in files:
                if name.endswith((".go", ".json", ".toml")) or name in ("go.mod", "go.sum"):
                    paths.add(Path(directory) / name)
    portal = workspace / "magicWebPortal"
    for directory in (portal / "src", portal / "scripts"):
        if directory.is_dir():
            for current, children, files in os.walk(directory):
                children[:] = [name for name in children if name not in (".umi", ".umi-production", ".umi-test")]
                paths.update(Path(current) / name for name in files)
    paths.update(path for path in (portal / "package.json", portal / "yarn.lock", portal / ".umirc.ts", portal / "tsconfig.json", portal / "vitest.config.ts") if path.is_file())
    paths.update(panel_entities.glob("*.json"))
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(paths)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.home() / "codespace")
    parser.add_argument("--race", action="store_true")
    parser.add_argument("--page-forms", action="store_true", help="冻结创建/编辑表单的真实作者与浏览器可靠写入，须配合 --page-navigation；不与 --page-exact-keys 混用")
    parser.add_argument("--page-tree-filter", action="store_true", help="正式树筛选组件、冻结后代范围及同页只读关系表格")
    parser.add_argument("--page-directory-filters", action="store_true", help="正式作者同页目录双关系绑定、树后代与分页分类选项的 AND 集合")
    parser.add_argument("--page-relation-filter", action="store_true", help="正式分页关系选择器、原主键复核与同页只读关系表格")
    parser.add_argument("--page-exact-keys", action="store_true", help="用合法自赋整数主键经正式业务创建验证安全整数外的持久化、树/关系/导航/动作")
    parser.add_argument("--page-navigation", action="store_true", help="正式只读目录到详情的精确实例 URL、刷新与返回证明")
    parser.add_argument("--page-relations", action="store_true", help="同页树选择、服务端后代展开与关系表格的真实三阶段验收")
    parser.add_argument("--page-tree", action="store_true", help="有界只读自引用树的真实作者、PostgreSQL与三阶段浏览器证明")
    parser.add_argument("--page-hour-buckets", action="store_true", help="UTC 保存/小时桶、三指标独立样本与业务时区展示，作者及真实数据库逐桶对账；须配合 --page-average-population")
    parser.add_argument("--page-average-population", action="store_true", help="同一正式安装的可空数值实体，空集与 null/zero/多行真实均值；须配合 --page-averages")
    parser.add_argument("--page-averages", action="store_true", help="实际数值均值作者/冻结发布安装/浏览器及独立 PostgreSQL 回读，须配合 --page-counts")
    parser.add_argument("--page-filters", action="store_true", help="实际列表和冻结 options 只读表格的标量等值筛选、空结果/清除，须配合 --pages --deployment-ui")
    parser.add_argument("--page-counts", action="store_true", help="实际统计作者/总数与分布页面/独立 Base 聚合回读，须配合 --pages --deployment-ui")
    parser.add_argument("--deployment-ui", action="store_true", help="实际模型申请/审批表单、成功响应丢失及原申请重开回查；须配合 --pages --business-ui")
    parser.add_argument("--record-action-ui", action="store_true", help="业务记录实际执行按钮/丢响应/原意图重开回查，须配合 --pages --business-ui")
    parser.add_argument("--business-ui", action="store_true", help="独立动作申请/审批实际 Portal 按钮，须配合 --browser-bff --entity-actions")
    parser.add_argument("--pages", action="store_true", help="真实可视化页面作者保存/再开、正式发布/安装、Chromium 真实数据 list/detail；须配合 --browser-bff --entity-actions --author-persistence")
    parser.add_argument("--shared-bff", action="store_true", help="two independent BFF processes share durable sessions; restart one while Chromium keeps its cookie; requires --browser-bff")
    parser.add_argument("--browser-bff", action="store_true", help="真实 Chromium/Portal 登录组件/BFF Cookie 申请与审批，须配合 --cas-mainline --submit-http --review-http")
    parser.add_argument("--export-retained-journal", type=Path, help="向私密新文件交付已公开卸载并保留的实际日志回读输入，须配合 --reference-data --retain-model-data")
    parser.add_argument("--retained-journal", type=Path, help="独立回读另一次实际保留安装的非空日志，须配合 --reference-data")
    parser.add_argument("--author-persistence", action="store_true", help="作者应用/实体/草稿/发布经 Base 持久化并回读，须配合 --storage-model --formal-review")
    parser.add_argument("--submit-http", action="store_true", help="经签名验签/权限路由提交并重复回查原申请，须配合 --formal-review")
    parser.add_argument("--ordinary-integers", action="store_true", help="正常激活后正式 Apps 普通新增/更新经 SDK、Base 和 PostgreSQL 精确整数回读；须配合 --cas-mainline --author-persistence，独立于 --entity-actions；不注入执行中断、不计调度重试验收")
    parser.add_argument("--entity-actions", action="store_true", help="同安装正式动作申请/审批/worker/CAS 赋权及空集撤销，须配合 --cas-mainline --author-persistence")
    parser.add_argument("--replacement-action-retirement", action="store_true", help="保留数据公开卸载后，同业务 Schema 新修订获批恢复，经真实 CAS apply authority 退役旧动作并恢复丢响应，须配合 --entity-actions --formal-review --submit-http --review-http --package-assets --retain-model-data")
    parser.add_argument("--active-action-uninstall", action="store_true", help="空集撤销验证后正式重授动作，独立确认有效绑定存在再公开卸载，须配合 --entity-actions")
    parser.add_argument("--reference-data", action="store_true", help="同正式产物参考数据作者/真实激活/独立 Apps 回读和退役，须配合 --package-assets")
    parser.add_argument("--package-assets", action="store_true", help="同产物正式资源作者/实际 File 持久化与私有读取/卸载释放，须配合 --entity-actions")
    parser.add_argument("--cas-mainline", action="store_true", help="同一主链启用 Base 持久化 CAS 正式凭证签发/验签及 worker 目录，须配合 --worker-scheduler --panel-database")
    parser.add_argument("--lose-capacity-response", action="store_true", help="丢弃已提交容量事务响应并恢复原预留，须配合 --allocate-storage")
    parser.add_argument("--allocate-storage", action="store_true", help="移除预绑定库/Schema/预留/绑定，由正式审批后的生产分配器创建，须配合 --formal-review --panel-database")
    parser.add_argument("--review-http", action="store_true", help="经正式签名验签/权限路由审批并从 Base PostgreSQL 回读 reviewer，须配合 --formal-review")
    parser.add_argument("--worker-scheduler", action="store_true", help="运行生产 BackgroundRoutine 定时扫描领取原重试任务，须配合 --formal-review")
    parser.add_argument("--panel-database", action="store_true", help="由 Panel 生产 database Block 创建真实独立库/账号并验证卸载停用及恢复，须配合 --storage-model")
    parser.add_argument("--lose-retirement-response", action="store_true", help="丢弃已提交退役响应并恢复原卸载，须配合 --storage-model")
    parser.add_argument("--formal-review", action="store_true", help="正式申请、审批、任务领取与物化联合，须配合 --postgres")
    parser.add_argument("--retain-model-data", action="store_true", help="存储型模型卸载保留数据分支，须配合 --storage-model")
    parser.add_argument("--storage-model", action="store_true", help="同一存储型模型产物的真实执行/Schema 退役，须配合 --postgres")
    parser.add_argument("--cas-authority", action="store_true", help="附加真实 CAS owner 经 Base 服务的 PostgreSQL 授权/撤销联合，须配合 --postgres")
    parser.add_argument("--evidence", type=Path, help="保存本轮结果与白名单证据到一个新目录，不覆盖历史证据")
    parser.add_argument("--candidate-delivery", type=Path, help="冻结的静态交付目录；联合前后检查文件/镜像/源码一致，使用其Panel实体声明")
    parser.add_argument("--candidate-image-evidence", type=Path, help="同候选冻结镜像构建证据目录，须配合 --candidate-delivery --postgres --evidence")
    parser.add_argument(
        "--panel-receipts", action="store_true",
        help="联合 Base 签名 HTTP、Panel Engine 入口、Gateway 本地路由及 Panel 完成确认",
    )
    parser.add_argument(
        "--postgres", action="store_true",
        help="显式使用 MAGIC_PUBLISHED_BLOCK_POSTGRES_DSN 的隔离控制库，必须配合 --panel-receipts",
    )
    parser.add_argument(
        "--panel-entities", type=Path,
        default=None,
        help="当前正式 Panel 部署实体声明，不读取旧 runtime 副本",
    )
    args = parser.parse_args()
    if bool(args.candidate_delivery) != bool(args.candidate_image_evidence):
        parser.error("--candidate-delivery 与 --candidate-image-evidence 必须同时指定")
    if args.candidate_delivery and not (args.postgres and args.evidence):
        parser.error("candidate-bound acceptance requires --postgres --evidence")
    if args.candidate_delivery:
        candidate_entities = args.candidate_delivery / "services/platform/deployments/magicPanel/entity"
        if args.panel_entities is not None and args.panel_entities.absolute() != candidate_entities.absolute():
            parser.error("--panel-entities must agree with --candidate-delivery")
        args.panel_entities = candidate_entities
    elif args.panel_entities is None:
        args.panel_entities = Path.home() / "dataspace/magicPlatform/services/platform/deployments/magicPanel/entity"
    if args.ordinary_integers and (not (args.cas_mainline and args.author_persistence) or args.entity_actions):
        parser.error("--ordinary-integers requires --cas-mainline --author-persistence, without --entity-actions")
    if args.page_forms and (not args.page_navigation or args.page_exact_keys):
        parser.error("--page-forms requires --page-navigation and owner-assigned keys (without --page-exact-keys)")
    if args.page_directory_filters and not (args.page_navigation and args.page_tree_filter and args.page_relation_filter):
        parser.error("--page-directory-filters requires --page-navigation --page-tree-filter --page-relation-filter")
    if args.page_relation_filter and not (args.page_tree and args.page_relations):
        parser.error("--page-relation-filter requires --page-tree --page-relations")
    if args.page_tree_filter and not (args.page_tree and args.page_relations):
        parser.error("--page-tree-filter requires --page-tree --page-relations")
    if args.page_exact_keys and not (args.page_navigation and args.page_tree and args.page_relations):
        parser.error("--page-exact-keys requires --page-navigation --page-tree --page-relations")
    if args.page_navigation and not (args.pages and args.deployment_ui):
        parser.error("--page-navigation requires --pages --deployment-ui")
    if args.page_relations and not args.page_tree:
        parser.error("--page-relations requires --page-tree")
    if args.page_tree and not (args.pages and args.deployment_ui):
        parser.error("--page-tree requires --pages --deployment-ui")
    if args.page_hour_buckets and not args.page_average_population:
        parser.error("--page-hour-buckets requires --page-average-population")
    if args.page_average_population and not args.page_averages:
        parser.error("--page-average-population 必须配合 --page-averages")
    if args.page_averages and not args.page_counts:
        parser.error("--page-averages requires --page-counts")
    if args.page_filters and not (args.pages and args.deployment_ui):
        parser.error("--page-filters requires --pages --deployment-ui")
    if args.page_counts and not (args.pages and args.deployment_ui):
        parser.error("--page-counts requires --pages --deployment-ui")
    if args.deployment_ui and not (args.pages and args.business_ui and args.allocate_storage):
        parser.error("--deployment-ui requires --pages --business-ui --allocate-storage")
    if args.record_action_ui and not (args.pages and args.business_ui):
        parser.error("--record-action-ui requires --pages --business-ui")
    if args.business_ui and not (args.browser_bff and args.entity_actions):
        parser.error("--business-ui requires --browser-bff --entity-actions")
    if args.pages and not (args.browser_bff and args.entity_actions and args.author_persistence):
        parser.error("--pages requires --browser-bff --entity-actions --author-persistence")

    if args.browser_bff and not (args.cas_mainline and args.submit_http and args.review_http):
        parser.error("--browser-bff 必须配合 --cas-mainline --submit-http --review-http")
    if args.replacement_action_retirement and not (args.entity_actions and args.formal_review and args.submit_http and args.review_http and args.package_assets and args.retain_model_data):
        parser.error("--replacement-action-retirement 必须配合 --entity-actions --formal-review --submit-http --review-http --package-assets --retain-model-data")
    if args.export_retained_journal and not (args.reference_data and args.retain_model_data):
        parser.error("--export-retained-journal 必须配合 --reference-data --retain-model-data")
    if args.retained_journal and not args.reference_data:
        parser.error("--retained-journal 必须配合 --reference-data")
    try:
        if args.export_retained_journal:
            args.export_retained_journal = private_journal_path(args.export_retained_journal, exporting=True)
        if args.retained_journal:
            args.retained_journal = private_journal_path(args.retained_journal, exporting=False)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    if args.active_action_uninstall and not args.entity_actions:
        parser.error("--active-action-uninstall 必须配合 --entity-actions")
    if args.reference_data and not args.package_assets:
        parser.error("--reference-data 必须配合 --package-assets")
    if args.package_assets and not args.entity_actions:
        parser.error("--package-assets 必须配合 --entity-actions")
    if args.entity_actions and not (args.cas_mainline and args.author_persistence):
        parser.error("--entity-actions 必须配合 --cas-mainline --author-persistence")
    if args.author_persistence and not (args.storage_model and args.formal_review):
        parser.error("--author-persistence 必须配合 --storage-model --formal-review")
    if args.submit_http and not args.formal_review:
        parser.error("--submit-http 必须配合 --formal-review")
    if args.cas_mainline and not (args.worker_scheduler and args.panel_database):
        parser.error("--cas-mainline 必须配合 --worker-scheduler --panel-database")
    if args.cas_mainline and args.cas_authority:
        parser.error("--cas-mainline 与独立 --cas-authority 探针应分开运行")
    if args.lose_capacity_response and not args.allocate_storage:
        parser.error("--lose-capacity-response 必须配合 --allocate-storage")
    if args.allocate_storage and not (args.formal_review and args.panel_database):
        parser.error("--allocate-storage 必须配合 --formal-review --panel-database")
    if args.review_http and not args.formal_review:
        parser.error("--review-http 必须配合 --formal-review")
    if args.worker_scheduler and not args.formal_review:
        parser.error("--worker-scheduler 必须配合 --formal-review")
    if args.panel_database and not args.storage_model:
        parser.error("--panel-database 必须配合 --storage-model")
    if args.lose_retirement_response and not args.storage_model:
        parser.error("--lose-retirement-response 必须配合 --storage-model")
    if args.formal_review and not args.postgres:
        parser.error("--formal-review 必须配合 --postgres")
    if args.postgres and not args.panel_receipts:
        parser.error("--postgres 必须配合 --panel-receipts")
    if args.retain_model_data and not args.storage_model:
        parser.error("--retain-model-data 必须配合 --storage-model")
    if args.storage_model and not args.postgres:
        parser.error("--storage-model 必须配合 --postgres")
    if args.cas_authority and not args.postgres:
        parser.error("--cas-authority 必须配合 --postgres")
    if args.postgres and not os.environ.get("MAGIC_PUBLISHED_BLOCK_POSTGRES_DSN"):
        parser.error("--postgres 需要显式隔离数据库环境变量")
    if args.postgres and not args.panel_entities.is_dir():
        parser.error("正式 Panel 实体目录不存在")
    if args.shared_bff and not args.browser_bff:
        parser.error("--shared-bff requires --browser-bff")
    workspace = args.workspace.resolve()
    runner, base = workspace / "magicRunner", workspace / "magicBase"
    for repository in (runner, base):
        if not (repository / "go.mod").is_file():
            parser.error(f"缺少源码仓库：{repository}")
    evidence = EvidenceDirectory(args.evidence) if args.evidence else None
    candidate_before = None
    if args.candidate_delivery:
        try:
            candidate_before = bind_candidate(workspace, args.candidate_delivery, args.candidate_image_evidence)
        except (OSError, ValueError, subprocess.CalledProcessError) as error:
            evidence.write_json("result.json", {"status": "failed", "reason": "candidate input preflight refused", "live": "not-run"})
            raise RuntimeError("candidate input preflight refused before owner or database calls") from error
        evidence.write_json("candidate-before.json", candidate_before)
    sources = source_snapshot(workspace, args.panel_entities)
    if evidence:
        evidence.write_json("source-sha256.json", sources)
    with tempfile.TemporaryDirectory(prefix="magic-published-block-") as directory:
        environment = dict(os.environ)
        if candidate_before:
            environment["GOFLAGS"] = "-mod=vendor"
            environment["GOWORK"] = "off"
        environment.pop("MAGIC_PUBLISHED_BLOCK_SHARED_BFF",None)
        if args.shared_bff: environment["MAGIC_PUBLISHED_BLOCK_SHARED_BFF"]="1"
        for key in ("MAGIC_PUBLISHED_BFF_INPUT", "MAGIC_PUBLISHED_BFF_PORT", "MAGIC_PUBLISHED_BFF_PORTAL"):
            environment.pop(key, None)
        environment.pop("MAGIC_PUBLISHED_BLOCK_PAGE_FORMS", None)
        if args.page_forms: environment["MAGIC_PUBLISHED_BLOCK_PAGE_FORMS"] = "1"
        environment.pop("MAGIC_PUBLISHED_BLOCK_PAGE_EXACT_KEYS", None)
        if args.page_exact_keys: environment["MAGIC_PUBLISHED_BLOCK_PAGE_EXACT_KEYS"] = "1"
        environment.pop("MAGIC_PUBLISHED_BLOCK_PAGE_NAVIGATION", None)
        if args.page_navigation: environment["MAGIC_PUBLISHED_BLOCK_PAGE_NAVIGATION"] = "1"
        environment.pop("MAGIC_PUBLISHED_BLOCK_PAGE_DIRECTORY_FILTERS", None)
        if args.page_directory_filters: environment["MAGIC_PUBLISHED_BLOCK_PAGE_DIRECTORY_FILTERS"] = "1"
        environment.pop("MAGIC_PUBLISHED_BLOCK_PAGE_RELATION_FILTER", None)
        if args.page_relation_filter: environment["MAGIC_PUBLISHED_BLOCK_PAGE_RELATION_FILTER"] = "1"
        environment.pop("MAGIC_PUBLISHED_BLOCK_PAGE_RELATIONS", None)
        if args.page_relations: environment["MAGIC_PUBLISHED_BLOCK_PAGE_RELATIONS"] = "1"
        environment.pop("MAGIC_PUBLISHED_BLOCK_PAGE_TREE", None)
        environment.pop("MAGIC_PUBLISHED_BLOCK_PAGE_TREE_ENTITY_ID", None)
        if args.page_tree: environment["MAGIC_PUBLISHED_BLOCK_PAGE_TREE"] = "1"
        environment.pop("MAGIC_PUBLISHED_BLOCK_PAGE_FILTERS", None)
        if args.page_filters:
            environment["MAGIC_PUBLISHED_BLOCK_PAGE_FILTERS"] = "1"
        environment.pop("MAGIC_PUBLISHED_BLOCK_PAGE_HOUR_BUCKETS",None)
        if args.page_hour_buckets: environment["MAGIC_PUBLISHED_BLOCK_PAGE_HOUR_BUCKETS"]="1"
        environment.pop("MAGIC_PUBLISHED_BLOCK_PAGE_AVERAGE_ENTITY_ID",None)
        environment.pop("MAGIC_PUBLISHED_BLOCK_PAGE_AVERAGE_POPULATION",None)
        if args.page_average_population:
            environment["MAGIC_PUBLISHED_BLOCK_PAGE_AVERAGE_POPULATION"]="1"
        environment.pop("MAGIC_PUBLISHED_BLOCK_PAGE_AVERAGES",None)
        if args.page_averages:
            environment["MAGIC_PUBLISHED_BLOCK_PAGE_AVERAGES"]="1"
        environment.pop("MAGIC_PUBLISHED_BLOCK_PAGE_COUNTS", None)
        if args.page_counts:
            environment["MAGIC_PUBLISHED_BLOCK_PAGE_COUNTS"] = "1"
        environment.pop("MAGIC_PUBLISHED_BLOCK_DEPLOYMENT_UI", None)
        if args.deployment_ui:
            environment["MAGIC_PUBLISHED_BLOCK_DEPLOYMENT_UI"] = "1"
        environment.pop("MAGIC_PUBLISHED_BLOCK_RECORD_ACTION_UI", None)
        if args.record_action_ui:
            environment["MAGIC_PUBLISHED_BLOCK_RECORD_ACTION_UI"] = "1"
        environment.pop("MAGIC_PUBLISHED_BLOCK_BUSINESS_UI", None)
        if args.business_ui:
            environment["MAGIC_PUBLISHED_BLOCK_BUSINESS_UI"] = "1"
        if args.browser_bff:
            # Bootstrap creates many ephemeral httptest listeners before BFF
            # starts. Choose outside the OS automatic range so one of those
            # listeners cannot consume the previously selected BFF port.
            automatic = (32768, 60999)
            range_file = Path("/proc/sys/net/ipv4/ip_local_port_range")
            if range_file.is_file():
                automatic = tuple(map(int, range_file.read_text().split()))
            for _ in range(128):
                browser_port = 20000 + secrets.randbelow(10000)
                if automatic[0] <= browser_port <= automatic[1]:
                    continue
                with socket.socket() as listener:
                    try:
                        listener.bind(("127.0.0.1", browser_port))
                    except OSError:
                        continue
                environment["MAGIC_PUBLISHED_BFF_PORT"] = str(browser_port)
                break
            else:
                raise RuntimeError("isolated BFF port outside automatic range unavailable")
            environment["MAGIC_PUBLISHED_BFF_PORTAL"] = str(workspace / "magicWebPortal")
        environment.pop("MAGIC_PUBLISHED_BLOCK_REPLACEMENT_ACTION_RETIREMENT", None)
        if args.replacement_action_retirement:
            environment["MAGIC_PUBLISHED_BLOCK_REPLACEMENT_ACTION_RETIREMENT"] = "1"
        environment.pop("MAGIC_PUBLISHED_BLOCK_EXPORT_RETAINED_JOURNAL", None)
        environment.pop("MAGIC_PUBLISHED_BLOCK_RETAINED_JOURNAL", None)
        if args.export_retained_journal:
            environment["MAGIC_PUBLISHED_BLOCK_EXPORT_RETAINED_JOURNAL"] = str(args.export_retained_journal)
        if args.retained_journal:
            environment["MAGIC_PUBLISHED_BLOCK_RETAINED_JOURNAL"] = str(args.retained_journal)
            retained_input_digest = hashlib.sha256(args.retained_journal.read_bytes()).hexdigest()
        environment.pop("MAGIC_PUBLISHED_BLOCK_INPUT", None)
        for variable in (
            "MAGIC_PUBLISHED_BLOCK_CONTROL", "MAGIC_PUBLISHED_BLOCK_BASE_REPOSITORY",
            "MAGIC_PUBLISHED_BLOCK_RACE", "MAGIC_PUBLISHED_BLOCK_GATEWAY_CONTROL",
            "MAGIC_PUBLISHED_BLOCK_ORM_INPUT",
            "MAGIC_PUBLISHED_BLOCK_METADATA_INPUT", "MAGIC_PUBLISHED_BLOCK_POSTGRES_SCHEMA",
            "MAGIC_PUBLISHED_BLOCK_PANEL_ENTITIES", "MAGIC_PUBLISHED_BLOCK_BASE_SERVICE",
            "MAGIC_PUBLISHED_BLOCK_STORAGE_MODEL", "MAGIC_PUBLISHED_BLOCK_RETAIN_MODEL_DATA",
            "MAGIC_PUBLISHED_BLOCK_FORMAL_REVIEW", "MAGIC_PUBLISHED_BLOCK_LOSE_RETIREMENT_RESPONSE",
            "MAGIC_PUBLISHED_BLOCK_CAS_REPOSITORY", "MAGIC_CAS_POSTGRES_BASE_ENDPOINT",
            "MAGIC_PUBLISHED_BLOCK_PANEL_DATABASE", "MAGIC_PUBLISHED_BLOCK_MODEL_DATABASE_FILE",
            "MAGIC_PUBLISHED_BLOCK_WORKER_SCHEDULER",
            "MAGIC_PUBLISHED_BLOCK_REVIEW_HTTP", "MAGIC_PUBLISHED_BLOCK_ALLOCATE_STORAGE",
            "MAGIC_PUBLISHED_BLOCK_LOSE_CAPACITY_RESPONSE",
            "MAGIC_PUBLISHED_BLOCK_AUTHOR_PERSISTENCE", "MAGIC_PUBLISHED_BLOCK_SUBMIT_HTTP",
            "MAGIC_PUBLISHED_BLOCK_CAS_MAINLINE", "MAGIC_PUBLISHED_BLOCK_CAS_SERVICE",
            "MAGIC_PUBLISHED_BLOCK_CAS_DATABASE_FILE", "MAGIC_PUBLISHED_BLOCK_ENTITY_ACTIONS",
            "MAGIC_PUBLISHED_BLOCK_EXECUTION_ADDRESS", "MAGIC_PUBLISHED_ACTION_INPUT",
            "MAGIC_PUBLISHED_BLOCK_ORDINARY_INTEGERS", "MAGIC_PUBLISHED_BLOCK_PAGES", "MAGIC_PUBLISHED_BLOCK_PACKAGE_ASSETS", "MAGIC_PUBLISHED_RESOURCE_INPUT", "MAGIC_PUBLISHED_ASSET_INPUT", "MAGIC_PUBLISHED_BLOCK_REFERENCE_DATA",
            "MAGIC_PUBLISHED_JOURNAL_INPUT",
            "MAGIC_PUBLISHED_BLOCK_ACTIVE_ACTION_UNINSTALL",
            "MAGIC_PUBLISHED_BLOCK_RECOVERED_EXECUTION",
        ):
            environment.pop(variable, None)
        if not args.postgres:
            environment.pop("MAGIC_PUBLISHED_BLOCK_POSTGRES_DSN", None)
        else:
            environment["MAGIC_PUBLISHED_BLOCK_PANEL_ENTITIES"] = str(args.panel_entities.resolve())
        environment["MAGIC_PUBLISHED_BLOCK_OUTPUT"] = directory
        if args.pages:
            environment["MAGIC_PUBLISHED_BLOCK_PAGES"] = "1"
        if args.active_action_uninstall:
            environment["MAGIC_PUBLISHED_BLOCK_ACTIVE_ACTION_UNINSTALL"] = "1"
        if args.page_tree_filter:
            environment["MAGIC_PUBLISHED_BLOCK_PAGE_TREE_FILTER"] = "1"
        if args.reference_data:
            environment["MAGIC_PUBLISHED_BLOCK_REFERENCE_DATA"] = "1"
        if args.package_assets:
            environment["MAGIC_PUBLISHED_BLOCK_PACKAGE_ASSETS"] = "1"
        if args.ordinary_integers:
            environment["MAGIC_PUBLISHED_BLOCK_ORDINARY_INTEGERS"] = "1"
        if args.entity_actions:
            environment["MAGIC_PUBLISHED_BLOCK_ENTITY_ACTIONS"] = "1"
        if args.author_persistence:
            environment["MAGIC_PUBLISHED_BLOCK_AUTHOR_PERSISTENCE"] = "1"
        if args.submit_http:
            environment["MAGIC_PUBLISHED_BLOCK_SUBMIT_HTTP"] = "1"
        if args.lose_capacity_response:
            environment["MAGIC_PUBLISHED_BLOCK_LOSE_CAPACITY_RESPONSE"] = "1"
        if args.allocate_storage:
            environment["MAGIC_PUBLISHED_BLOCK_ALLOCATE_STORAGE"] = "1"
        if args.review_http:
            environment["MAGIC_PUBLISHED_BLOCK_REVIEW_HTTP"] = "1"
        if args.worker_scheduler:
            environment["MAGIC_PUBLISHED_BLOCK_WORKER_SCHEDULER"] = "1"
        if args.panel_database:
            environment["MAGIC_PUBLISHED_BLOCK_PANEL_DATABASE"] = "1"
        if args.lose_retirement_response:
            environment["MAGIC_PUBLISHED_BLOCK_LOSE_RETIREMENT_RESPONSE"] = "1"
        if args.formal_review:
            environment["MAGIC_PUBLISHED_BLOCK_FORMAL_REVIEW"] = "1"
        if args.retain_model_data:
            environment["MAGIC_PUBLISHED_BLOCK_RETAIN_MODEL_DATA"] = "1"
        if args.storage_model:
            environment["MAGIC_PUBLISHED_BLOCK_STORAGE_MODEL"] = "1"
        if args.cas_authority or args.cas_mainline:
            environment["MAGIC_PUBLISHED_BLOCK_CAS_REPOSITORY"] = str(workspace / "magicCas")
        if args.cas_mainline:
            environment["MAGIC_PUBLISHED_BLOCK_CAS_MAINLINE"] = "1"
        if args.panel_receipts:
            environment["MAGIC_PUBLISHED_BLOCK_BASE_REPOSITORY"] = str(base)
            environment["MAGIC_PUBLISHED_BLOCK_RACE"] = "1" if args.race else "0"
        command = [
            "go", "-C", str(runner), "test",
            "./internal/modules/kernel/panel/biz",
            "-run", "^TestPublishedBlockThroughPanelHTTPAndGatewayRoutes$" if args.panel_receipts else "^TestPublishedFileBlockReachesApprovedInstallationWithoutSourceOrTransport$",
            "-count=1", "-timeout=600s" if args.deployment_ui or args.record_action_ui or args.package_assets or args.replacement_action_retirement else "-timeout=300s" if args.entity_actions else "-timeout=180s",
        ]
        if args.panel_receipts:
            command.append("-v")
        if args.race:
            command.append("-race")
        def run(command):
            if not args.evidence:
                subprocess.run(command, env=environment, check=True)
                return
            with evidence.open_log("joint.log") as log:
                result = subprocess.run(command, env=environment, stdout=log, stderr=subprocess.STDOUT)
            for name in ("page-author.json", "page-author-browser.json", "page-author-saved.png", "page-author-reopened.png", "page-runtime-ungranted.json", "page-runtime-ungranted.png", "page-runtime-grant.json", "page-runtime-grant.png", "page-runtime-revoked.json", "page-runtime-revoked.png", "browser-service.log", "browser-proof.json", "shared-bff-browser.json", "shared-bff-processes.json", "bff-session-storage.json", "browser-action-ungranted.json", "browser-action-grant.json", "browser-action-revoked.json", "requester-login.png", "reviewer-login.png", "base-service.log", "cas-service.log", "execution-service.log", "apps-service.log", "file-service.log", "asset-service.log", "journal-retirement.json", "sibling-journals-before.json", "sibling-journals-after.json", "role-retirement.json", "replacement-action-retirement.json", "recovery-schema-refusal.json", "recovery-retained-rows.json", "action-consumer-refusal.json", "user-ungranted-login-proof.json", "user-grant-login-proof.json", "user-revoked-login-proof.json", "gateway-authentication.json", "reviewer-login-proof.json", "requester-login-proof.json", "prepared-renewals.json"):
                service_log = Path(directory) / name
                if service_log.is_file():
                    evidence.copy(service_log)
            if args.page_forms:
                for name in ("frozen-form-browser.json", "frozen-form-created.png", "frozen-form-pending.png", "frozen-form-recovered.png"):
                    p = Path(directory) / name
                    if p.is_file(): evidence.copy(p)
            if args.page_tree:
                for stage in ("ungranted", "grant", "revoked"):
                    for name in (f"tree-{stage}.json", f"page-tree-{stage}.png", *((f"relations-{stage}.json", f"page-relations-{stage}.png") if args.page_relations else ())):
                        p = Path(directory) / name
                        if p.is_file(): evidence.copy(p)
            if args.page_directory_filters:
                for stage in ("ungranted", "grant", "revoked"):
                    for name in (f"directory-filters-{stage}.json", f"page-directory-filters-{stage}.png"):
                        p = Path(directory) / name
                        if p.is_file(): evidence.copy(p)
            if args.page_relation_filter:
                for stage in ("ungranted", "grant", "revoked"):
                    for name in (f"relation-filter-{stage}.json", f"page-relation-filter-{stage}.png"):
                        p = Path(directory) / name
                        if p.is_file(): evidence.copy(p)
            if args.page_filters:
                for stage in ("ungranted", "grant", "revoked"):
                    screenshot = Path(directory) / f"page-filters-{stage}.png"
                    if screenshot.is_file():
                        evidence.copy(screenshot)
                    screenshot = Path(directory) / f"page-options-{stage}.png"
                    if screenshot.is_file():
                        evidence.copy(screenshot)
            if args.page_averages:
                for stage in ("ungranted","grant","revoked"):
                    screenshot=Path(directory)/f"page-averages-{stage}.png"
                    if screenshot.is_file():evidence.copy(screenshot)
                    if args.page_average_population:
                        proof=Path(directory)/f"mean-population-{stage}.json"
                        if proof.is_file():evidence.copy(proof)
            if args.page_hour_buckets:
                for stage in ("ungranted","grant","revoked"):
                    for name in (f"hour-buckets-{stage}.json",f"page-hour-buckets-{stage}.png"):
                        p=Path(directory)/name
                        if p.is_file(): evidence.copy(p)
            if args.page_counts:
                for stage in ("ungranted", "grant", "revoked"):
                    screenshot = Path(directory) / f"page-counts-{stage}.png"
                    if screenshot.is_file():
                        evidence.copy(screenshot)
            if args.deployment_ui:
                for path in sorted(Path(directory).glob("deployment-*-ui*")):
                    if path.suffix in (".png", ".json"):
                        evidence.copy(path)
            if args.record_action_ui:
                for path in sorted(Path(directory).glob("record-action-ui*")):
                    if path.suffix in (".png", ".json"):
                        evidence.copy(path)
            if args.business_ui:
                for path in sorted(Path(directory).glob("action-ui-*")):
                    if path.suffix in (".png", ".json"):
                        evidence.copy(path)
            if args.replacement_action_retirement:
                for name in ("published-block.json", "execution-service.log", "ready.json", "journal-retirement.json", "role-retirement.json", "gateway-observations.json", "predecessor-receipt-refusal.json", "prepared-renewals.json"):
                    proof = Path(directory) / "replacement" / name
                    if proof.is_file():
                        evidence.copy(proof, "replacement-" + name)
            if result.returncode:
                evidence.write_json("result.json", {"status": "failed", "exitCode": result.returncode, "live": "not-run"})
                raise subprocess.CalledProcessError(result.returncode, command)
        run(command)
        required_proofs = []
        if args.browser_bff:
            required_proofs.extend(("browser-service.log", "browser-proof.json", "bff-session-storage.json", "requester-login.png", "reviewer-login.png"))
            if args.entity_actions:
                required_proofs.extend(f"browser-action-{stage}.json" for stage in ("ungranted", "grant", "revoked"))
            proof_path = Path(directory) / "browser-proof.json"
            if proof_path.is_file():
                browser_proof = json.loads(proof_path.read_text())
                if browser_proof.get("status") != "passed" or browser_proof.get("frontendAuthorizationHeaders") != 0 or len(browser_proof.get("sessions", [])) != 2:
                    raise RuntimeError("browser/BFF independent proof failed")
        if args.deployment_ui:
            proofs = []
            for stage in ("create", "review"):
                name = f"deployment-{stage}-ui"
                required_proofs.append(name + ".json")
                value = json.loads((Path(directory) / (name + ".json")).read_text())
                if value.get("status") != "passed" or value.get("writes") != 1 or value.get("originalReads", 0) < 2 or value.get("committedResponseLoss") != 1 or value.get("queryResponseLoss") != 1 or not value.get("productionForm") or not value.get("remountOriginalRecovery"):
                    raise RuntimeError("actual deployment form recovery proof incomplete")
                for screenshot in ("pending", "restored", "confirmed"):
                    filename = name + "-" + screenshot + ".png"
                    required_proofs.append(filename)
                    if not (Path(directory) / filename).read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
                        raise RuntimeError("actual deployment form screenshot is not PNG")
                proofs.append(value)
            if any(proofs[0].get(key) != proofs[1].get(key) for key in ("requestId", "deploymentId", "instanceKey")) or not proofs[1].get("operationId"):
                raise RuntimeError("deployment form request/review identity differs")
        if args.record_action_ui:
            required_proofs.extend(("record-action-ui.json", "record-action-ui-pending.png", "record-action-ui-restored.png", "record-action-ui-confirmed.png", "record-action-ui-read-error.png"))
            proof_path = Path(directory) / "record-action-ui.json"
            ui = json.loads(proof_path.read_text())
            if ui.get("frozenPageBinding") is not True or ui.get("samePageRefresh") is not True:
                raise RuntimeError("record action must use explicit frozen page binding")
            refresh = ui.get("confirmationRefresh", {})
            if refresh.get("newRequests") is not True or refresh.get("completed") is not True or len(refresh.get("sourceKeys", [])) != 2 or len(set(refresh["sourceKeys"])) != 2 or refresh.get("sourceReadFailures") != 1 or refresh.get("currentReadFailures") != 1 or refresh.get("receiptSurvived") is not True or refresh.get("readRetriesOnly") is not True:
                raise RuntimeError("record action confirmation must complete both fresh page source reads")
            if ui.get("status") != "passed" or ui.get("buttonUI") is not True or ui.get("productionDescriptor") is not True or ui.get("remountOriginalIntent") is not True or ui.get("independentCurrentRead") is not True or ui.get("executeCount") != 1 or ui.get("queryCount") != 2 or ui.get("executeCommittedResponseLoss") != 1 or ui.get("queryCommittedResponseLoss") != 1 or ui.get("frontendAuthorizationHeaders") != 0:
                raise RuntimeError("actual record action UI proof missing")
            for name in ("pending", "restored", "confirmed", "read-error"):
                if not (Path(directory) / f"record-action-ui-{name}.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
                    raise RuntimeError("actual record action UI screenshot is not PNG")
        if args.business_ui:
            browser_proof = json.loads((Path(directory) / "browser-proof.json").read_text())
            ui = browser_proof.get("entityActionUI", {})
            expected = 3 if args.active_action_uninstall else 2
            if ui.get("creates") != expected or ui.get("reviews") != expected or ui.get("reviewWrites") != expected or ui.get("operationReads") != expected or ui.get("createCommittedResponseLoss") != 1 or ui.get("reviewCommittedResponseLoss") != 1 or ui.get("reviewConfirmationReadFailures") != 1 or ui.get("reviewOriginalReadRecoveries") != 1 or ui.get("exactInt64IDs") is not True:
                raise RuntimeError("actual action submission/review UI proof missing")
            ui_artifacts = sorted(Path(directory).glob("action-ui-*.json"))
            if len(ui_artifacts) != expected * 2:
                raise RuntimeError("actual action UI artifact count mismatch")
            kinds = []
            for proof_path in ui_artifacts:
                proof = json.loads(proof_path.read_text())
                if proof.get("status") != "passed" or proof.get("buttonUI") is not True or proof.get("frontendAuthorizationHeaders") != 0 or not proof_path.with_suffix(".png").is_file():
                    raise RuntimeError("actual action UI screenshot or receipt missing")
                if not proof_path.with_suffix(".png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
                    raise RuntimeError("actual action UI screenshot is not PNG")
                kinds.append(proof.get("kind"))
            if kinds.count("create") != expected or kinds.count("review") != expected:
                raise RuntimeError("actual action UI artifact kind mismatch")
        if args.page_counts:
            for stage in ("ungranted", "grant", "revoked"):
                name = f"page-counts-{stage}.png"
                required_proofs.append(name)
                screenshot = Path(directory) / name
                if not screenshot.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
                    raise RuntimeError("actual count UI screenshot is not PNG")
                if evidence and (evidence.directory / name).read_bytes() != screenshot.read_bytes():
                    raise RuntimeError("archived count UI screenshot differs")
        if args.shared_bff:
            required_proofs.extend(["shared-bff-browser.json","shared-bff-processes.json"])
            browser=json.loads((Path(directory)/"shared-bff-browser.json").read_text())
            processes=json.loads((Path(directory)/"shared-bff-processes.json").read_text())
            if browser.get("status")!="passed" or len(browser.get("sessions",[]))!=2 or len(browser.get("uniqueReplicaIncarnations",[]))!=3 or not all(x.get("stableCookie") is True and len(x.get("visits",[]))==7 for x in browser.get("sessions",[])) or processes.get("status")!="passed" or len(set(processes.get("pids",[])))!=3 or processes.get("restarts")!=1:
                raise RuntimeError("shared BFF process/restart/browser proof incomplete")
        if args.page_forms:
            required_proofs.extend(("frozen-form-browser.json", "frozen-form-created.png", "frozen-form-pending.png", "frozen-form-recovered.png"))
            form = json.loads((Path(directory)/"frozen-form-browser.json").read_text())
            if form.get("status") != "passed" or form.get("executeCount") != 1 or form.get("receiptCount") != 2 or not all(form.get(k) is True for k in ("cancelWithoutWrite", "createWithoutRecordRead", "sparseUpdate", "immutableCodeReadonly", "exactOwnerAllocatedKey", "reloadQueryOnly", "exactOwnedCleanupConfirmed", "confirmedFormReread", "recoveredFormReread", "confirmedImmutableCodeShown", "confirmedFormHasNoErrors", "recoveredFormHasNoErrors")):
                raise RuntimeError("frozen form create/edit and original-operation recovery proof incomplete")
            if json.loads((Path(directory)/"page-author-browser.json").read_text()).get("formsExplicit") is not True:
                raise RuntimeError("frozen form visual author/save/reopen proof missing")
        if args.pages:
            required_proofs.extend(("page-author.json", "page-author-browser.json", "page-author-saved.png", "page-author-reopened.png"))
            required_proofs.extend(f"page-runtime-{stage}{suffix}" for stage in ("ungranted", "grant", "revoked") for suffix in (".json", ".png"))
            if args.page_tree_filter and json.loads((Path(directory) / "page-author-browser.json").read_text()).get("treeComponentType") != "tree-filter":
                raise RuntimeError("visual tree-filter author/save/reopen proof missing")
            if args.page_relation_filter and json.loads((Path(directory) / "page-author-browser.json").read_text()).get("relationFilterComponentType") != "relation-filter":
                raise RuntimeError("visual relation-filter author/save/reopen proof missing")
            for stage in ("ungranted", "grant", "revoked"):
                proof_path = Path(directory) / f"page-runtime-{stage}.json"
                if proof_path.is_file():
                    proof = json.loads(proof_path.read_text())
                    if proof.get("status") != "passed" or not proof.get("listAndExactDetailRendered") or not proof.get("staleGenerationRefused"):
                        raise RuntimeError("installed page browser proof failed")
                    if args.page_tree_filter and proof.get("treeComponentType") != "tree-filter":
                        raise RuntimeError("frozen tree-filter browser proof missing")
                    if args.page_tree:
                        name = f"tree-{stage}.json"
                        required_proofs.append(name)
                        owner = json.loads((Path(directory) / name).read_text())
                        tree = proof.get("tree", {})
                        nodes = owner.get("Nodes", [])
                        if owner.get("Status") != "passed" or owner.get("Stage") != stage or owner.get("Identity") != proof.get("identity") or owner.get("PageDigest") != proof.get("pageDigest") or len(nodes) != 3 or tree != {"nodes": nodes, "depth": 3, "complete": True}:
                            raise RuntimeError("tree browser differs from independent owner identity or original nodes")
                        if nodes[0]["parent"] != "" or nodes[1]["parent"] != nodes[0]["id"] or nodes[2]["parent"] != nodes[1]["id"] or len({n["id"] for n in nodes}) != 3:
                            raise RuntimeError("tree original allocated identities or hierarchy differ")
                        name = f"page-tree-{stage}.png"
                        required_proofs.append(name)
                        p = Path(directory) / name
                        if not p.read_bytes().startswith(b"\x89PNG\r\n\x1a\n") or (evidence and (evidence.directory / name).read_bytes() != p.read_bytes()):
                            raise RuntimeError("tree screenshot invalid or differs")
                    if args.page_hour_buckets:
                        name=f"detail-time-{stage}.json"
                        required_proofs.append(name)
                        owner=json.loads((Path(directory)/name).read_text())
                        utc=owner.get("UTC","")
                        display="—"
                        if utc:
                            instant=dt.datetime.fromisoformat(utc.replace("Z","+00:00"))
                            local=instant.astimezone(dt.timezone(dt.timedelta(hours=8)))
                            display=local.strftime("%Y-%m-%d %H:%M:%S.")+f"{local.microsecond//1000:03d} Asia/Shanghai"
                        if owner.get("Status")!="passed" or owner.get("Stage")!=stage or owner.get("RecordID")!=proof.get("recordId") or owner.get("Identity")!=proof.get("identity") or owner.get("PageDigest")!=proof.get("pageDigest") or owner.get("Kind")!=("datetime" if utc else "null") or proof.get("detailDatetime")!={"utc":utc,"display":display,"timezone":"Asia/Shanghai"}:
                            raise RuntimeError("detail business timezone differs from independent stored UTC oracle")
                    if args.page_exact_keys:
                        if proof.get("recordId") != "9007199254740993" or [n.get("id") for n in proof.get("tree",{}).get("nodes",[])] != ["9007199254740993", "9007199254740995", "9223372036854775001"]:
                            raise RuntimeError("actual stored business keys lost precision in browser proof")
                    if args.page_navigation:
                        navigation=proof.get("navigation",{})
                        if navigation!={"recordId":proof.get("recordId"),"deploymentId":proof.get("identity",{}).get("deploymentId"),"directoryToDetail":True,"reload":True,"back":True}:
                            raise RuntimeError("directory navigation/reload/back proof incomplete")
                    if args.page_relations:
                        name=f"relations-{stage}.json"
                        required_proofs.append(name)
                        owner=json.loads((Path(directory)/name).read_text())
                        relations=proof.get("relations",{})
                        if owner.get("Status")!="passed" or owner.get("Identity")!=proof.get("identity") or owner.get("PageDigest")!=proof.get("pageDigest") or relations.get("cases")!=owner.get("Cases") or relations.get("cursorReset") is not True or relations.get("combinedFilter") is not True:
                            raise RuntimeError("relation browser differs from frozen owner cases")
                        name=f"page-relations-{stage}.png"
                        required_proofs.append(name)
                        if not (Path(directory)/name).read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
                            raise RuntimeError("relation screenshot unavailable")
                    if args.page_directory_filters:
                        name=f"directory-filters-{stage}.json"
                        required_proofs.extend((name, f"page-directory-filters-{stage}.png"))
                        owner=json.loads((Path(directory)/name).read_text())
                        combination=proof.get("directoryFilters",{})
                        if owner.get("Status")!="passed" or owner.get("Identity")!=proof.get("identity") or owner.get("PageDigest")!=proof.get("pageDigest") or combination.get("cases")!=owner.get("Cases") or not all(combination.get(k) is True for k in ("cursorReset","combinedFilter","optionsPaged","viewsSwitched","noViewRead","cardDetail","treeDirectoryLayout")):
                            raise RuntimeError("directory combination browser differs from frozen owner cases")
                        if not (Path(directory)/f"page-directory-filters-{stage}.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
                            raise RuntimeError("directory combination screenshot unavailable")
                    if args.page_relation_filter:
                        name=f"relation-filter-{stage}.json"
                        required_proofs.extend((name, f"page-relation-filter-{stage}.png"))
                        owner=json.loads((Path(directory)/name).read_text())
                        relation=proof.get("relationFilter",{})
                        if owner.get("Status")!="passed" or owner.get("Identity")!=proof.get("identity") or owner.get("PageDigest")!=proof.get("pageDigest") or relation.get("cases")!=owner.get("Cases") or not all(relation.get(k) is True for k in ("cursorReset","combinedFilter","optionsPaged")) or relation.get("optionIDs")!=[n.get("id") for n in proof.get("tree",{}).get("nodes",[])]:
                            raise RuntimeError("relation-filter browser differs from frozen owner cases")
                        if not (Path(directory)/f"page-relation-filter-{stage}.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
                            raise RuntimeError("relation-filter screenshot unavailable")
                    if args.page_filters:
                        option = proof.get("options", {})
                        if option.get("mode") != "options" or option.get("recordId") != proof.get("recordId") or option.get("state") != proof.get("state") or [option.get(k) for k in ("matched", "empty", "cleared")] != [1, 0, 1]:
                            raise RuntimeError("installed frozen options UI differs from owner result")
                        option_name = f"page-options-{stage}.png"
                        required_proofs.append(option_name)
                        option_file = Path(directory) / option_name
                        if not option_file.read_bytes().startswith(b"\x89PNG\r\n\x1a\n") or (evidence and (evidence.directory / option_name).read_bytes() != option_file.read_bytes()):
                            raise RuntimeError("archived options screenshot invalid or differs")
                        if proof.get("filters") != {"matched": 1, "empty": 0, "cleared": 1}:
                            raise RuntimeError("installed scalar filter UI differs from owner query")
                        name = f"page-filters-{stage}.png"
                        required_proofs.append(name)
                        screenshot = Path(directory) / name
                        if not screenshot.read_bytes().startswith(b"\x89PNG\r\n\x1a\n") or (evidence and (evidence.directory / name).read_bytes() != screenshot.read_bytes()):
                            raise RuntimeError("archived filter screenshot invalid or differs")
                    if args.page_averages:
                        import re
                        average=proof.get("averages",{})
                        expected="1" if stage=="ungranted" else "2"
                        samples="1"
                        if args.page_average_population:
                            expected,samples=("—","0") if stage=="ungranted" else ("2.25","3")
                        suffix=r"0*" if "." in expected else r"(?:\.0+)?"
                        valid_mean=average.get("mean")=="—" if expected=="—" else bool(re.fullmatch(re.escape(expected)+suffix,average.get("mean","")))
                        if average.get("validSamples")!=samples or not valid_mean:
                            raise RuntimeError("installed mean differs from independent owner aggregate")
                        if args.page_average_population:
                            population_name=f"mean-population-{stage}.json"
                            required_proofs.append(population_name)
                            owner=json.loads((Path(directory)/population_name).read_text())
                            if owner.get("ReadIdentity")!=proof.get("identity") or owner.get("Status")!="passed" or owner.get("Stage")!=stage or owner.get("Samples")!=samples or len(owner.get("Rows",[]))!=(0 if stage=="ungranted" else 4):
                                raise RuntimeError("independent complete population proof differs")
                            if stage=="ungranted":
                                if owner.get("MeanKind")!="null" or owner.get("Mean")!="":raise RuntimeError("empty owner aggregate differs")
                            elif owner.get("MeanKind")!="decimal" or not re.fullmatch(r"2[.]25(?:0+)?",owner.get("Mean","")):
                                raise RuntimeError("independent multirow mean differs")
                        name=f"page-averages-{stage}.png"
                        required_proofs.append(name)
                        screenshot=Path(directory)/name
                        if not screenshot.read_bytes().startswith(b"\x89PNG\r\n\x1a\n") or (evidence and (evidence.directory/name).read_bytes()!=screenshot.read_bytes()):
                            raise RuntimeError("archived mean screenshot invalid or differs")
                    if args.page_hour_buckets:
                        h=proof.get("hourly",{});name=f"hour-buckets-{stage}.json";required_proofs.append(name)
                        owner=json.loads((Path(directory)/name).read_text())
                        if owner.get("Status")!="passed" or owner.get("Identity")!=proof.get("identity") or not all(h.get(k) for k in ("zeroRetained","emptyBucketDisconnected","rangeChanged")) or len(h.get("rows",[]))!=3 or len(h.get("shortRows",[]))!=1:
                            raise RuntimeError("hourly browser/independent owner proof differs")
                        if h.get("metricKeys") != ["amount", "vibration", "load"] or h.get("independentMetricSamples") is not True or h.get("displayTimezone") != "Asia/Shanghai":
                            raise RuntimeError("hourly metric samples or business display timezone differs")
                        expected_times=[] if stage=="ungranted" else ["2026-10-20T00:10:00Z", "2026-10-20T00:20:00Z", "2026-10-20T01:00:00Z", "2026-10-20T01:59:59.999Z"]
                        if owner.get("PersistedUTC") != expected_times:
                            raise RuntimeError("mixed business offsets were not persisted as the original UTC instants")
                        for key, count in (("Full",3),("Short",1)):
                            aggregate_rows=owner.get(key,{}).get("rows",[])
                            if len(aggregate_rows)!=count or any([metric.get("key") for metric in row.get("metrics",[])] != ["amount", "vibration", "load"] for row in aggregate_rows):
                                raise RuntimeError("independent owner three-metric bucket proof differs")
                        name=f"page-hour-buckets-{stage}.png";required_proofs.append(name);p=Path(directory)/name
                        if not p.read_bytes().startswith(b"\x89PNG\r\n\x1a\n") or (evidence and (evidence.directory/name).read_bytes()!=p.read_bytes()):raise RuntimeError("hourly screenshot archive differs")
                    if args.page_counts:
                        counts = proof.get("counts", {})
                        if counts != {"total": "1", "groupCount": "1", "group": "open" if stage == "ungranted" else "acknowledged"}:
                            raise RuntimeError("installed counts differ from independent owner aggregate")
        if args.replacement_action_retirement:
            required_proofs.extend(("replacement-action-retirement.json", "recovery-schema-refusal.json", "recovery-retained-rows.json", "action-consumer-refusal.json"))
            required_proofs.extend("replacement/" + name for name in ("published-block.json", "execution-service.log", "ready.json", "journal-retirement.json", "role-retirement.json", "gateway-observations.json", "predecessor-receipt-refusal.json", "prepared-renewals.json"))
        if args.retained_journal:
            if hashlib.sha256(args.retained_journal.read_bytes()).hexdigest() != retained_input_digest:
                raise RuntimeError("retained journal private input changed during the joint")
            required_proofs.extend(("sibling-journals-before.json", "sibling-journals-after.json"))
        if args.export_retained_journal:
            private_journal_path(args.export_retained_journal, exporting=False)
        if args.panel_receipts:
            required_proofs.append("prepared-renewals.json")
        if args.reference_data:
            required_proofs.append("journal-retirement.json")
        if args.cas_mainline:
            required_proofs.extend(("role-retirement.json", "gateway-authentication.json", "reviewer-login-proof.json"))
            if args.entity_actions or args.submit_http:
                required_proofs.append("requester-login-proof.json")
        if args.entity_actions:
            required_proofs.extend(f"user-{stage}-login-proof.json" for stage in ("ungranted", "grant", "revoked"))
        try:
            archive_required_proofs(directory, evidence, required_proofs)
        except RuntimeError as error:
            if evidence:
                evidence.write_json("result.json", {"status": "failed", "reason": str(error), "live": "not-run"})
            raise
        material = Path(directory) / "published-block.json"
        content = json.loads(material.read_bytes())
        if not args.panel_receipts:
            environment.pop("MAGIC_PUBLISHED_BLOCK_OUTPUT", None)
            environment["MAGIC_PUBLISHED_BLOCK_INPUT"] = str(material)
            command = [
                "go", "-C", str(base), "test",
                "./internal/modules/kernel/base/biz",
                "-run", "^TestPublishedMaterializedBlockRunsBaseLifecycle$",
                "-count=1", "-timeout=120s",
            ]
            if args.race:
                command.append("-race")
            run(command)
        if sources != source_snapshot(workspace, args.panel_entities):
            if evidence:
                evidence.write_json("result.json", {"status": "failed", "reason": "source or declaration inputs changed during joint validation", "live": "not-run"})
            raise RuntimeError("source or declaration inputs changed during joint validation")
        if candidate_before:
            try:
                candidate_after = bind_candidate(workspace, args.candidate_delivery, args.candidate_image_evidence)
                if candidate_after != candidate_before:
                    raise ValueError("candidate inputs changed")
            except (OSError, ValueError, subprocess.CalledProcessError) as error:
                evidence.write_json("result.json", {"status": "failed", "reason": "candidate inputs changed during joint validation", "live": "not-run"})
                raise RuntimeError("candidate inputs changed during joint validation") from error
            evidence.write_json("candidate-after.json", candidate_after)
        result = {
            "status": "passed",
            "candidateBinding": candidate_before or "not-run",
            "artifactDigest": content["artifactDigest"],
            "scope": "formal-publication-materialization-to-base-hub-interpreter-lifecycle",
            "storage": "postgresql-control-base-service-materialization" if args.postgres else "fixture",
            "initialManagementMetadata": "approved-panel-installation-base-service" if args.postgres else "fixture",
            "installationDecision": "production-submit-review-claim-base-postgresql" if args.formal_review else "approved-request-fixture" if args.panel_receipts else "fixture",
            "deploymentExecutor": "production-normal-installation-activation-no-interrupted-retry" if args.ordinary_integers else "production-original-operation-retry-executor-and-completion" if args.formal_review else "fixture",
            "reviewTransport": "production-signed-bearer-verifier-privilege-http-base-postgresql-reviewer" if args.review_http else "owner-command-authenticated-principal-fixture" if args.formal_review else "fixture",
            "reviewTokenIssuer": "production-cas-password-login-authorization-code-S256-PKCE-JWKS" if args.cas_mainline and args.review_http else "isolated-signer-jwks-fixture" if args.review_http else "not-run",
            "requestTokenIssuer": "production-cas-password-login-authorization-code-S256-PKCE-JWKS" if args.cas_mainline and args.submit_http else "isolated-signer-jwks-fixture" if args.submit_http else "not-run",
            "entityActionReviewTokenIssuer": "production-cas-password-login-authorization-code-S256-PKCE-JWKS" if args.entity_actions else "not-run",
            "executorScheduler": "not-run-integer-persistence-scenario" if args.ordinary_integers else "production-background-routine-periodic-namespace-keyset-scan-original-retry-checked-drain" if args.worker_scheduler else "not-run-direct-production-executor-entry" if args.formal_review else "not-run",
            "schedulerNamespaceDirectory": "not-run-integer-persistence-scenario" if args.ordinary_integers else "production-cas-client-credentials-token-verifier-directory-base-postgresql" if args.cas_mainline else "isolated-active-namespace-input" if args.worker_scheduler else "not-run",
            "namespaceAuthorization": "production-shared-route-registry-authorizer-explicit-action-target-owner-signed-scope" if args.cas_mainline else "isolated-test-adapter",
            "casBootstrap": "isolated-identities-service-bindings-catalog-policy-ephemeral-signing-key" if args.cas_mainline else "not-run",
            "initialCASAccess": "production-initial-administrator-grant-persisted-assignment-original-cas-epoch-readback" if args.cas_mainline else "fixture",
            "casAccessRetirement": "production-public-uninstall-cas-readback-original-grant-rejected-no-epoch-advance" if args.cas_mainline else "fixture",
            "ordinaryUninstallRolePolicy": "independent-signed-cas-binding-inventory-empty-retired-head-rejected-original-role-identities-retained-disabled" if args.cas_mainline else "not-run",
            "preUninstallActionBinding": "formally-approved-regrant-enabled-current-epoch-independent-tenant-cas-http-confirmation" if args.active_action_uninstall else "approved-empty-set-revoked-before-uninstall" if args.entity_actions else "not-run",
            "independentEntityActions": "production-signed-panel-http-review-periodic-worker-cas-short-authority-persistent-exact-grant-empty-set-revocation" if args.entity_actions else "not-run",
            "ordinaryIntegers": "ordinary-Apps-HTTP-SDK-Base-ORM-postgresql-create-update-independent-readback" if args.ordinary_integers else "not-run",
            "businessActionExecution": "production-apps-real-panel-eventhub-base-postgresql-action-independent-receipt-and-row-readback-fresh-revoked-user-denied" if args.entity_actions else "not-run",
            "businessUserAuthentication": "production-password-login-durable-browser-transaction-one-time-authorization-code-S256-PKCE-signed-OIDC-nonce-current-role-projection" if args.entity_actions else "not-run",
            "referenceData": "official-author-base-activation-postgresql-independent-apps-read-retirement" if args.reference_data else "not-run",
            "privateJournalRetirement": "independent-base-process-three-private-models-before-drain-after-public-uninstall-full-row-digests" if args.reference_data else "not-run",
            "retainedSiblingJournalIsolation": "distinct-actual-retained-installation-runtime-separate-storage-same-postgres-three-nonempty-journals-independent-process-before-after-full-row-digests" if args.retained_journal else "not-run",
            "replacementActionRoleRetirement": "official-next-publication-actual-predecessor-uninstall-approved-replacement-materialization-production-cas-apply-authority-committed-response-loss-original-confirmation" if args.replacement_action_retirement else "not-run",
            "browserBusinessAction": "same-Chromium-cookie-production-BFF-authority-refresh-Apps-HTTP-Base-action-original-receipt-replay-revocation" if args.browser_bff and args.entity_actions else "not-run",
            "browserDeploymentForms": "production-model-request-and-approval-original-intent-remount-cookie-BFF-CAS-Base-postgresql" if args.deployment_ui else "not-run",
            "browserRecordAction": "production-installed-page-button-original-intent-remount-recovery-cookie-BFF-CAS-Base-postgresql" if args.record_action_ui else "not-run",
            "browserEntityActionGovernance": "production-Portal-buttons-real-system-area-projection-cookie-BFF-CAS-owner-Base-postgresql" if args.business_ui else "not-run",
            "browserPageOptions": "production-visual-author-frozen-options-readonly-table-Apps-Base-postgresql-Chromium-exact-record-match-empty-clear" if args.page_filters else "not-run",
            "browserPageFilters": "production-visual-author-optional-scalar-equality-frozen-list-Apps-Base-postgresql-independent-query-and-browser-match-empty-clear" if args.page_filters else "not-run",
            "sharedBFF": "two-process-PostgreSQL-durable-session-shared-key-rolling-restart-real-Chromium-stable-cookie" if args.shared_bff else "not-run",
            "browserMeanPopulation": "same-published-nullable-entity-complete-empty-and-null-zero-multirow-Apps-Base-magicOrm-postgresql-Chromium" if args.page_average_population else "not-run",
            "browserDetailDatetime": "registered-datetime-UTC-projection-independent-business-read-Shanghai-display-null" if args.page_hour_buckets else "not-run",
            "browserPageExactKeys": "caller-assigned-int64-primary-keys-through-ordinary-Apps-Base-ORM-create-tree-relations-action-and-directory-reload-back" if args.page_exact_keys else "not-run",
            "browserPageNavigation": "frozen-readonly-directory-exact-record-detail-URL-reload-back" if args.page_navigation else "not-run",
            "browserPageRelations": "same-page-frozen-tree-server-descendants-reference-IN-filter-cursor-clear" if args.page_relations else "not-run",
            "browserPageDirectoryFilters": "visual-author-explicit-directory-tree-options-and-cursor-clear" if args.page_directory_filters else "not-run",
            "browserPageRelationFilter": "visual-author-frozen-options-selector-exact-authorized-primary-read-same-page-reference-filter-cursor-clear" if args.page_relation_filter else "not-run",
            "browserPageTreeFilter": "visual-author-frozen-tree-filter-same-page-readonly-reference-table-descendant-scope" if args.page_tree_filter else "not-run",
            "browserPageTree": "bounded-readonly-self-reference-exact-primary-parent-tokens-three-level-PostgreSQL" if args.page_tree else "not-run",
            "browserHourBuckets": "UTC-storage-mixed-offset-inputs-hour-three-means-independent-samples-business-timezone-display-PostgreSQL" if args.page_hour_buckets else "not-run",
            "browserPageAverages": "production-visual-author-exact-decimal-mean-valid-samples-frozen-publication-install-Apps-Base-postgresql-independent-readback" if args.page_averages else "not-run",
            "browserPageCounts": "production-visual-author-count-and-distribution-frozen-publication-install-Apps-Base-postgresql-independent-count-readback" if args.page_counts else "not-run",
            "browserPageLifecycle": "real-visual-author-save-reopen-formal-publication-frozen-install-Chromium-renderer-provider-Apps-Base-postgresql" if args.pages else "not-run",
            "browserBFF": "real-Chromium-Portal-login-CAS-PKCE-private-PostgreSQL-session-cookie-Panel-submit-review" if args.browser_bff else "not-run",
            "replacementExecution": "same-approved-new-revision-original-operation-base-postgresql-gateway-ready-original-row-read-public-uninstall" if args.replacement_action_retirement else "not-run",
            "packageAssets": "official-author-publication-actual-file-base-postgresql-private-apps-consumer-create-delete-response-loss-independent-file-process-sibling-preserved" if args.package_assets else "not-run",
            "fileServiceAuthentication": "production-cas-client-credentials-jwks-verification-declared-service-only-file-read-write" if args.package_assets else "not-run",
            "authorPersistence": "production-panel-create-entity-draft-preview-publication-base-postgresql-readback" if args.author_persistence else "fixture",
            "requestSubmission": "production-signed-bearer-verifier-privilege-http-original-request-base-postgresql-readback" if args.submit_http else "production-owner-command" if args.formal_review else "fixture",
            "materializationRecovery": "lost-application-and-entity-create-responses-original-operation" if args.postgres else "fixture",
            "modelBusinessStorage": "same-artifact-base-service-postgresql" if args.storage_model else "not-run",
            "modelDataDisposition": "retain" if args.retain_model_data else "destroy" if args.storage_model else "not-run",
            "storageAccountFence": "production-panel-database-block-nologin-drain-restore-base-rebind" if args.panel_database else "fixture" if args.storage_model else "not-run",
            "storageProvisioning": "production-panel-approved-admission-reservation-planning-create-and-binding" if args.allocate_storage else "production-panel-database-block-create-and-original-target-replay-prebound-catalog" if args.panel_database else "prebound-isolated-schema-fixture" if args.storage_model else "not-run",
            "storageCapacityRecovery": "lost-committed-base-transaction-response-original-reservation-no-double-charge" if args.lose_capacity_response else "not-run",
            "executionModelStorage": "production-base-orm" if args.storage_model else "fixture",
            "businessPersistence": "native-base-service-postgresql-ddl-relations-unique-preserve-retire" if args.postgres else "not-run",
            "assignment": "production-lifecycle-intent-base-sdk-postgresql-read" if args.postgres else "production-lifecycle-intent-fixture-read" if args.panel_receipts else "fixture",
            "lifecycleCoordination": "production",
            "panelLifecycle": "approved-activation-public-uninstall" if args.panel_receipts else "not-run",
            "retirementRecovery": "lost-committed-response-original-uninstall-absence-read-no-new-generation" if args.lose_retirement_response else "not-run",
            "baseRetirement": "production-owner-local-drain" if args.panel_receipts else "not-run",
            "metadataRetirement": "production-base-service-postgresql-storage-backed" if args.storage_model else "production-base-service-postgresql-storage-free" if args.postgres else "fixture" if args.panel_receipts else "not-run",
            "controlReader": "production-ormreader-postgresql" if args.postgres else "production-ormreader-fixture-store" if args.panel_receipts else "fixture",
            "receiptSubmission": "production-http-authenticated-owner-base-sdk-postgresql" if args.postgres else "production-http-authenticated-owner-fixture-store" if args.panel_receipts else "fixture",
            "panelHTTPAdapter": "production-engine-service" if args.panel_receipts else "not-run",
            "gatewayTokenIssuer": "production-cas-client-credentials-endpoint-role-projection-persistent-audit" if args.cas_mainline else "isolated-signer-jwks-fixture" if args.panel_receipts else "not-run",
            "gatewaySnapshot": "production" if args.panel_receipts else "not-run",
            "gatewayRouteApplication": "production-client-local-state" if args.panel_receipts else "not-run",
            "gatewayRouteReceipt": "production-http-conditional-commit" if args.panel_receipts else "not-run",
            "panelCompletionBarrier": "production" if args.panel_receipts else "not-run",
            "cas": "production-mainline-cas-with-isolated-bootstrap" if args.cas_mainline else "token-issuer-fixture-jwks-verifier-production" if args.panel_receipts else "fixture",
            "casPersistenceProbe": "production-role-authorization-account-base-service-postgresql" if args.cas_authority else "not-run",
            "crossProcessDeployment": "not-run",
            "database": "postgresql-control-and-model-business" if args.storage_model else "postgresql-control" if args.postgres else "not-run",
            "databaseAccess": "business-magicbase-service-magicorm;infrastructure-panel-database-block" if args.panel_database else "magicbase-service-magicorm" if args.postgres else "not-run",
            "controlTransactions": "concurrent-cas-rollback-identity-only-delete" if args.postgres else "not-run",
            "live": "not-run",
            "race": args.race,
        }
        if args.evidence:
            evidence.copy(material)
            evidence.write_json("result.json", result)
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
