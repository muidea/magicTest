from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple


ROOT_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class TestGoal:
    key: str
    title: str
    description: str


@dataclass(frozen=True)
class TestTarget:
    key: str
    goal: str
    title: str
    description: str
    workdir: Path
    command: Tuple[str, ...]
    env: Dict[str, str] = field(default_factory=dict)
    default_env_profile: str | None = None


@dataclass(frozen=True)
class TestEnvProfile:
    key: str
    title: str
    description: str
    env: Dict[str, str] = field(default_factory=dict)
    proxy_hosts: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class TestPreset:
    key: str
    title: str
    description: str
    target_keys: Tuple[str, ...]


def _pythonpath_for(*relative_dirs: str) -> str:
    entries: List[str] = []
    for relative_dir in relative_dirs:
        entries.append(str((ROOT_DIR / relative_dir).resolve()))
    existing = os.getenv("PYTHONPATH", "").strip()
    if existing:
        entries.append(existing)
    return os.pathsep.join(entries)


GOALS: Dict[str, TestGoal] = {
    "foundation": TestGoal(
        key="foundation",
        title="基础能力验证",
        description="会话、请求封装和测试基础设施自身验证。",
    ),
    "auth": TestGoal(
        key="auth",
        title="CAS 认证与注册",
        description="账号、角色、命名空间、登录刷新、公开注册与审核链路。",
    ),
    "ui": TestGoal(
        key="ui",
        title="Portal / Panel 页面验收",
        description="真实浏览器层面的注册、登录、菜单显隐与入口跳转验证。",
    ),
    "file": TestGoal(
        key="file",
        title="文件服务",
        description="magicFile 基础文件能力和文件服务集成验证。",
    ),
    "platform-core": TestGoal(
        key="platform-core",
        title="magicBase 平台核心接口",
        description="application / entity / value / log / totalizator 平台核心接口。",
    ),
    "panel-api": TestGoal(
        key="panel-api",
        title="Panel 控制面接口",
        description="运行期对象、定义、订阅、服务访问、页面上下文等 panel API 验证。",
    ),
    "business-scenario": TestGoal(
        key="business-scenario",
        title="业务场景与 VMI 回归",
        description="面向具体业务应用的场景、模块和多租户集成测试。",
    ),
    "load": TestGoal(
        key="load",
        title="并发、热点与老化压测",
        description="VMI 现有并发、热点、老化、长稳态压测入口。",
    ),
}


ENV_PROFILES: Dict[str, TestEnvProfile] = {
    "panel-local": TestEnvProfile(
        key="panel-local",
        title="Panel 本地环境",
        description="panel / portal / cas 控制面默认使用 panel.local.vpc。",
        env={
            "MAGICTEST_CAS_BASE_URL": "https://panel.local.vpc",
            "MAGICTEST_PANEL_BASE_URL": "https://panel.local.vpc/api/v1",
        },
        proxy_hosts=("panel.local.vpc",),
    ),
    "autotest-local": TestEnvProfile(
        key="autotest-local",
        title="Autotest 本地环境",
        description="platform / file / vmi 业务验证默认使用 autotest.local.vpc。",
        env={
            "MAGICTEST_PLATFORM_BASE_URL": "https://autotest.local.vpc/api/v1",
            "MAGICTEST_FILE_BASE_URL": "https://autotest.local.vpc",
            "MAGICTEST_SERVER_URL": "https://autotest.local.vpc",
        },
        proxy_hosts=("autotest.local.vpc",),
    ),
}


TARGETS: Tuple[TestTarget, ...] = (
    TestTarget(
        key="session-foundation",
        goal="foundation",
        title="Session 基础验证",
        description="验证 MagicSession 的连接池、请求行为与基础优化。",
        workdir=ROOT_DIR / "session",
        command=(sys.executable, "-m", "unittest", "test_optimized", "-v"),
        env={"PYTHONPATH": _pythonpath_for(".", "session")},
    ),
    TestTarget(
        key="cas-api",
        goal="auth",
        title="CAS 基础接口回归",
        description="登录、账号、角色、命名空间等基础认证接口回归。",
        workdir=ROOT_DIR / "cas",
        command=(sys.executable, "-m", "unittest", "cas_api_test", "basic_scenario_test", "-v"),
        env={"PYTHONPATH": _pythonpath_for(".", "cas")},
        default_env_profile="panel-local",
    ),
    TestTarget(
        key="cas-registration",
        goal="auth",
        title="CAS 注册链路回归",
        description="公开注册、审核、审核后登录与 portal 基础权限验证。",
        workdir=ROOT_DIR / "cas",
        command=(sys.executable, "-m", "unittest", "registration_test", "-v"),
        env={"PYTHONPATH": _pythonpath_for(".", "cas")},
        default_env_profile="panel-local",
    ),
    TestTarget(
        key="portal-registration-ui",
        goal="ui",
        title="Portal 注册页面链路",
        description="使用真实浏览器验证注册页提交、审核后登录和 portal 首页可访问。",
        workdir=ROOT_DIR / "ui",
        command=(sys.executable, "-m", "unittest", "portal_registration_ui_test", "-v"),
        env={"PYTHONPATH": _pythonpath_for(".", "cas", "ui")},
        default_env_profile="panel-local",
    ),
    TestTarget(
        key="file-basic",
        goal="file",
        title="文件服务基础回归",
        description="magicFile 文件服务基础场景验证。",
        workdir=ROOT_DIR / "file",
        command=(sys.executable, "-m", "unittest", "basic_scenario_test", "-v"),
        env={"PYTHONPATH": _pythonpath_for(".", "file")},
        default_env_profile="autotest-local",
    ),
    TestTarget(
        key="platform-core-api",
        goal="platform-core",
        title="平台核心接口套件",
        description="magicBase 平台核心模块统一回归入口。",
        workdir=ROOT_DIR / "platform",
        command=(sys.executable, "run_tests.py", "--verbose"),
        default_env_profile="autotest-local",
    ),
    TestTarget(
        key="panel-runtime-api",
        goal="panel-api",
        title="Panel 运行期与生命周期接口",
        description="运行中应用、apps runtime、多实例安装卸载幂等回归。",
        workdir=ROOT_DIR / "panel",
        command=(
            sys.executable,
            "-m",
            "unittest",
            "application_lifecycle_test",
            "apps_runtime_test",
            "application_install_roundtrip_test",
            "-v",
        ),
        env={"PYTHONPATH": _pythonpath_for(".", "panel")},
        default_env_profile="panel-local",
    ),
    TestTarget(
        key="panel-governance-api",
        goal="panel-api",
        title="Panel 定义与订阅接口",
        description="应用定义、实体定义、订阅、endpoint 等治理接口回归。",
        workdir=ROOT_DIR / "panel",
        command=(
            sys.executable,
            "-m",
            "unittest",
            "definition_test",
            "subscription_test",
            "-v",
        ),
        env={"PYTHONPATH": _pythonpath_for(".", "panel")},
        default_env_profile="panel-local",
    ),
    TestTarget(
        key="panel-page-api",
        goal="panel-api",
        title="Panel / Portal 页面接口边界",
        description="profile、notification、system/context surface 过滤回归。",
        workdir=ROOT_DIR / "panel",
        command=(
            sys.executable,
            "-m",
            "unittest",
            "profile_test",
            "system_context_test",
            "-v",
        ),
        env={"PYTHONPATH": _pythonpath_for(".", "panel")},
        default_env_profile="panel-local",
    ),
    TestTarget(
        key="panel-service-api",
        goal="panel-api",
        title="服务访问与订阅主链接口",
        description="服务定义、调试元数据、gateway query/get/create/update 与订阅访问回归。",
        workdir=ROOT_DIR / "panel",
        command=(
            sys.executable,
            "-m",
            "unittest",
            "service_access_test",
            "service_roundtrip_test",
            "-v",
        ),
        env={"PYTHONPATH": _pythonpath_for(".", "panel")},
        default_env_profile="panel-local",
    ),
    TestTarget(
        key="vmi-quick",
        goal="business-scenario",
        title="VMI 快速验证",
        description="VMI 框架验证与快速业务冒烟入口。",
        workdir=ROOT_DIR / "vmi",
        command=(sys.executable, "run_tests.py", "--quick"),
        default_env_profile="autotest-local",
    ),
    TestTarget(
        key="vmi-scenario",
        goal="business-scenario",
        title="VMI 业务场景回归",
        description="VMI 场景测试与业务模块集成回归。",
        workdir=ROOT_DIR / "vmi",
        command=(sys.executable, "run_tests.py", "--scenario"),
        default_env_profile="autotest-local",
    ),
    TestTarget(
        key="vmi-tenant-user-prepare",
        goal="business-scenario",
        title="VMI 多租户多用户准备",
        description="按指定租户列表自动创建多用户测试账号，并输出后续测试可复用的用户矩阵。",
        workdir=ROOT_DIR / "vmi",
        command=(sys.executable, "run_tests.py", "--prepare-tenant-users"),
        default_env_profile="autotest-local",
    ),
    TestTarget(
        key="vmi-module",
        goal="business-scenario",
        title="VMI 模块级回归",
        description="VMI 模块测试入口，适合业务模块改动后复验。",
        workdir=ROOT_DIR / "vmi",
        command=(sys.executable, "run_tests.py", "--module"),
        default_env_profile="autotest-local",
    ),
    TestTarget(
        key="vmi-concurrent",
        goal="load",
        title="VMI 并发压测",
        description="VMI 并发链路验证，适合功能稳定后的短压。",
        workdir=ROOT_DIR / "vmi",
        command=(sys.executable, "run_tests.py", "--concurrent"),
        default_env_profile="autotest-local",
    ),
    TestTarget(
        key="vmi-hotspot",
        goal="load",
        title="VMI 热点压测",
        description="VMI 热点读写压测，适合结合后续 APM 观察热点链路。",
        workdir=ROOT_DIR / "vmi",
        command=(sys.executable, "run_tests.py", "--hotspot"),
        default_env_profile="autotest-local",
    ),
    TestTarget(
        key="vmi-aging",
        goal="load",
        title="VMI 老化压测",
        description="VMI 长稳态 / 老化测试入口，默认 30 分钟。",
        workdir=ROOT_DIR / "vmi",
        command=(sys.executable, "run_tests.py", "--aging", "30"),
        default_env_profile="autotest-local",
    ),
)


PRESETS: Dict[str, TestPreset] = {
    "auth-smoke": TestPreset(
        key="auth-smoke",
        title="认证基础回归",
        description="登录、角色、命名空间和注册审核主链。",
        target_keys=("cas-api", "cas-registration"),
    ),
    "auth-ui": TestPreset(
        key="auth-ui",
        title="认证页面回归",
        description="真实浏览器层面的注册、审核后登录和 portal 首页访问链路。",
        target_keys=("portal-registration-ui",),
    ),
    "panel-smoke": TestPreset(
        key="panel-smoke",
        title="Panel 主链回归",
        description="panel/portal 页面边界、运行期对象和服务访问主链。",
        target_keys=("panel-page-api", "panel-runtime-api", "panel-service-api"),
    ),
    "panel-full": TestPreset(
        key="panel-full",
        title="Panel 完整 API 回归",
        description="包含治理接口在内的 panel 全量 API 回归。",
        target_keys=(
            "panel-page-api",
            "panel-runtime-api",
            "panel-governance-api",
            "panel-service-api",
        ),
    ),
    "platform-smoke": TestPreset(
        key="platform-smoke",
        title="平台核心接口回归",
        description="magicBase 平台核心模块统一回归。",
        target_keys=("platform-core-api",),
    ),
    "file-smoke": TestPreset(
        key="file-smoke",
        title="文件服务基础回归",
        description="magicFile 基础能力验证。",
        target_keys=("file-basic",),
    ),
    "business-smoke": TestPreset(
        key="business-smoke",
        title="业务快速回归",
        description="业务应用快速验证与基础场景冒烟。",
        target_keys=("vmi-tenant-user-prepare", "vmi-quick"),
    ),
    "business-full": TestPreset(
        key="business-full",
        title="业务场景完整回归",
        description="业务模块与业务场景组合回归。",
        target_keys=("vmi-tenant-user-prepare", "vmi-module", "vmi-scenario"),
    ),
    "business-prepare-users": TestPreset(
        key="business-prepare-users",
        title="业务测试用户准备",
        description="在目标租户列表内准备多用户测试账号，不执行业务回归。",
        target_keys=("vmi-tenant-user-prepare",),
    ),
    "load-hotspot": TestPreset(
        key="load-hotspot",
        title="热点压测",
        description="热点链路短压入口。",
        target_keys=("vmi-hotspot",),
    ),
    "load-aging": TestPreset(
        key="load-aging",
        title="老化压测",
        description="默认 30 分钟老化测试入口。",
        target_keys=("vmi-aging",),
    ),
}


def targets_by_goal(goal: str) -> List[TestTarget]:
    return [item for item in TARGETS if item.goal == goal]


def target_by_key(key: str) -> TestTarget | None:
    for item in TARGETS:
        if item.key == key:
            return item
    return None


def preset_by_key(key: str) -> TestPreset | None:
    return PRESETS.get(key)
