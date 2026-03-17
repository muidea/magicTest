"""Shared bootstrap for VMI tests and utilities."""

from __future__ import annotations

import os
import sys
import warnings
from typing import Iterable

try:
    import urllib3
    from urllib3.exceptions import InsecureRequestWarning
except Exception:  # pragma: no cover - optional dependency in local tooling only
    urllib3 = None
    InsecureRequestWarning = None


def _find_project_root(current_file: str) -> str:
    current_dir = os.path.dirname(os.path.abspath(current_file))
    project_root = current_dir

    required_components = ("session", "cas", "mock", "vmi")
    while True:
        if all(os.path.exists(os.path.join(project_root, item)) for item in required_components):
            return project_root

        parent = os.path.dirname(project_root)
        if parent == project_root:
            break
        project_root = parent

    return os.path.dirname(current_dir)


def ensure_test_paths(current_file: str, components: Iterable[str] = ("vmi",)) -> str:
    """Add shared VMI test dependencies to ``sys.path`` exactly once."""
    project_root = _find_project_root(current_file)

    required_paths = [project_root]
    required_paths.extend(os.path.join(project_root, component) for component in components)

    for path in required_paths:
        if path not in sys.path:
            sys.path.insert(0, path)

    if urllib3 and InsecureRequestWarning:
        warnings.filterwarnings("ignore", category=InsecureRequestWarning)
        urllib3.disable_warnings(InsecureRequestWarning)

    return project_root
