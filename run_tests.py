#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, Sequence

from test_catalog import (
    ENV_PROFILES,
    GOALS,
    PRESETS,
    TARGETS,
    preset_by_key,
    target_by_key,
    targets_by_goal,
)


def _format_command(command: Iterable[str]) -> str:
    return " ".join(command)


def _merge_proxy_hosts(base: Dict[str, str], hosts: Sequence[str]) -> None:
    if not hosts:
        return
    normalized = [host.strip() for host in hosts if host and host.strip()]
    if not normalized:
        return
    for key in ("NO_PROXY", "no_proxy"):
        existing = [item.strip() for item in base.get(key, "").split(",") if item.strip()]
        for host in normalized:
            if host not in existing:
                existing.append(host)
        if existing:
            base[key] = ",".join(existing)


def _resolved_profile(profile_key: str | None):
    if not profile_key:
        return None
    return ENV_PROFILES.get(profile_key)


def _merged_env(
    extra_env: Dict[str, str],
    profile_key: str | None = None,
    force_profile: bool = False,
    cli_env: Dict[str, str] | None = None,
) -> Dict[str, str]:
    env = os.environ.copy()
    profile = _resolved_profile(profile_key)
    if profile:
        for key, value in profile.env.items():
            if force_profile or key not in env or not env.get(key):
                env[key] = value
        _merge_proxy_hosts(env, profile.proxy_hosts)
    for key, value in (extra_env or {}).items():
        if key == "PYTHONPATH" and env.get("PYTHONPATH"):
            env[key] = value
        else:
            env[key] = value
    for key, value in (cli_env or {}).items():
        env[key] = value
    return env


def _run_target(
    target,
    dry_run: bool = False,
    env_profile: str | None = None,
    force_profile: bool = False,
    cli_env: Dict[str, str] | None = None,
) -> bool:
    active_profile = env_profile or target.default_env_profile
    print("=" * 72)
    print(f"[{target.key}] {target.title}")
    print(f"目标: {GOALS[target.goal].title}")
    print(f"说明: {target.description}")
    print(f"目录: {target.workdir}")
    if active_profile:
        profile = _resolved_profile(active_profile)
        if profile:
            print(f"环境: {profile.key} ({profile.title})")
    print(f"命令: {_format_command(target.command)}")
    if dry_run:
        return True

    start = time.time()
    result = subprocess.run(
        target.command,
        cwd=str(target.workdir),
        env=_merged_env(
            target.env,
            profile_key=active_profile,
            force_profile=force_profile,
            cli_env=cli_env,
        ),
    )
    elapsed = time.time() - start
    print(f"结果: {'通过' if result.returncode == 0 else '失败'} ({elapsed:.2f}s)")
    return result.returncode == 0


def _list_goals() -> None:
    print("magicTest 测试目标")
    print("=" * 72)
    for goal in GOALS.values():
        print(f"{goal.key:18s} {goal.title}")
        print(f"  {goal.description}")


def _list_envs() -> None:
    print("magicTest 环境配置")
    print("=" * 72)
    for profile in ENV_PROFILES.values():
        print(f"{profile.key:18s} {profile.title}")
        print(f"  {profile.description}")


def _list_presets() -> None:
    print("magicTest 常用执行预设")
    print("=" * 72)
    for preset in PRESETS.values():
        print(f"{preset.key:18s} {preset.title}")
        print(f"  {preset.description}")
        print(f"  targets: {', '.join(preset.target_keys)}")


def _list_targets(goal_key: str | None = None) -> None:
    print("magicTest 测试套件")
    print("=" * 72)
    targets = TARGETS if goal_key is None else targets_by_goal(goal_key)
    for target in targets:
        print(f"{target.key:20s} [{target.goal}] {target.title}")
        print(f"  {target.description}")
        print(f"  cwd: {target.workdir}")
        print(f"  cmd: {_format_command(target.command)}")
        if target.default_env_profile:
            print(f"  env: {target.default_env_profile}")


def _run_preset(
    preset,
    dry_run: bool = False,
    env_profile: str | None = None,
    force_profile: bool = False,
    cli_env: Dict[str, str] | None = None,
) -> bool:
    print("=" * 72)
    print(f"预设: [{preset.key}] {preset.title}")
    print(f"说明: {preset.description}")
    print(f"套件: {', '.join(preset.target_keys)}")
    success = True
    for target_key in preset.target_keys:
        target = target_by_key(target_key)
        if target is None:
            print(f"缺少测试套件定义: {target_key}", file=sys.stderr)
            success = False
            continue
        success = _run_target(
            target,
            dry_run=dry_run,
            env_profile=env_profile,
            force_profile=force_profile,
            cli_env=cli_env,
        ) and success
    return success


def _parse_cli_env(values: Sequence[str]) -> Dict[str, str]:
    env: Dict[str, str] = {}
    for item in values:
        if "=" not in item:
            raise ValueError(f"环境变量参数格式错误: {item}, 需要 KEY=VALUE")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"环境变量参数格式错误: {item}, KEY 不能为空")
        env[key] = value
    return env


def main() -> int:
    parser = argparse.ArgumentParser(
        description="magicTest 统一测试导航与聚合入口",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 run_tests.py --list-goals
  python3 run_tests.py --list-envs
  python3 run_tests.py --list-presets
  python3 run_tests.py --list
  python3 run_tests.py --preset panel-smoke
  python3 run_tests.py --preset panel-full --env-profile panel-local
  python3 run_tests.py --preset business-prepare-users --env MAGICTEST_TENANT_TARGETS=t001,t002 --env MAGICTEST_TENANT_USER_POOL_ENABLED=true --env MAGICTEST_USERS_PER_TENANT=3
  python3 run_tests.py --goal panel-api --dry-run
  python3 run_tests.py --target panel-service-api
  python3 run_tests.py --target vmi-hotspot
""".strip(),
    )
    parser.add_argument("--list-goals", action="store_true", help="列出所有测试目标")
    parser.add_argument("--list-envs", action="store_true", help="列出所有环境配置")
    parser.add_argument("--list-presets", action="store_true", help="列出所有常用执行预设")
    parser.add_argument("--list", action="store_true", help="列出所有测试套件")
    parser.add_argument("--preset", type=str, help="运行常用执行预设，例如 panel-smoke / business-smoke")
    parser.add_argument("--goal", type=str, help="按测试目标运行，例如 panel-api / load")
    parser.add_argument("--target", type=str, help="运行单个测试套件")
    parser.add_argument("--env-profile", type=str, help="显式指定环境配置，例如 panel-local / autotest-local")
    parser.add_argument(
        "--env",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="为本次执行追加环境变量，可重复传入",
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印命令，不实际执行")
    args = parser.parse_args()

    if args.list_goals:
        _list_goals()
        return 0

    if args.list_envs:
        _list_envs()
        return 0

    if args.list_presets:
        _list_presets()
        return 0

    if args.list:
        _list_targets(args.goal)
        return 0

    if args.goal and args.goal not in GOALS:
        print(f"未知测试目标: {args.goal}", file=sys.stderr)
        return 2

    if args.env_profile and args.env_profile not in ENV_PROFILES:
        print(f"未知环境配置: {args.env_profile}", file=sys.stderr)
        return 2

    try:
        cli_env = _parse_cli_env(args.env)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.preset:
        preset = preset_by_key(args.preset)
        if preset is None:
            print(f"未知执行预设: {args.preset}", file=sys.stderr)
            return 2
        return 0 if _run_preset(
            preset,
            dry_run=args.dry_run,
            env_profile=args.env_profile,
            force_profile=bool(args.env_profile),
            cli_env=cli_env,
        ) else 1

    if args.target:
        target = target_by_key(args.target)
        if target is None:
            print(f"未知测试套件: {args.target}", file=sys.stderr)
            return 2
        return 0 if _run_target(
            target,
            dry_run=args.dry_run,
            env_profile=args.env_profile,
            force_profile=bool(args.env_profile),
            cli_env=cli_env,
        ) else 1

    if args.goal:
        targets = targets_by_goal(args.goal)
        if not targets:
            print(f"测试目标下无可运行套件: {args.goal}", file=sys.stderr)
            return 2
        success = True
        for target in targets:
            success = _run_target(
                target,
                dry_run=args.dry_run,
                env_profile=args.env_profile,
                force_profile=bool(args.env_profile),
                cli_env=cli_env,
            ) and success
        return 0 if success else 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
