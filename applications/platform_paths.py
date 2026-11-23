#!/usr/bin/env python3
"""Resolve sibling magicPlatform model assets and workspace checkouts."""
from __future__ import annotations

import os
from pathlib import Path

APPLICATIONS_ROOT = Path(__file__).resolve().parent
MAGIC_TEST_ROOT = APPLICATIONS_ROOT.parent


def _resolve_platform_candidate(path: Path | str | None) -> Path | None:
    if not path:
        return None
    candidate = Path(path).expanduser().resolve()
    if (candidate / 'apps/models').is_dir():
        return candidate
    return None


def resolve_platform_root(explicit: Path | str | None = None) -> Path:
    """Locate magicPlatform checkout holding authoritative apps/models assets."""
    if explicit:
        found = _resolve_platform_candidate(explicit)
        if found is not None:
            return found
        raise FileNotFoundError(f'magicPlatform apps/models not found under {explicit}')

    for candidate in (
        os.environ.get('MAGICPLATFORM_ROOT'),
        Path.home() / 'dataspace/magicPlatform',
        MAGIC_TEST_ROOT.parent / 'magicPlatform',
    ):
        found = _resolve_platform_candidate(candidate)
        if found is not None:
            return found
    raise FileNotFoundError(
        'magicPlatform apps/models not found; set MAGICPLATFORM_ROOT or checkout ~/dataspace/magicPlatform'
    )


def resolve_app_model_root(app_name: str, explicit: Path | str | None = None) -> Path:
    """Locate apps/models/<app_name> inside magicPlatform."""
    model_root = resolve_platform_root(explicit) / 'apps/models' / app_name
    if not (model_root / 'definition').is_dir():
        raise FileNotFoundError(f'authoritative model definition missing: {model_root / "definition"}')
    return model_root


def resolve_workspace_root(explicit: Path | str | None = None) -> Path:
    """Locate codespace root containing sibling service checkouts."""
    if explicit:
        return Path(explicit).expanduser().resolve()
    env_root = os.environ.get('MAGIC_WORKSPACE_ROOT')
    if env_root:
        return Path(env_root).expanduser().resolve()
    return MAGIC_TEST_ROOT.parent
