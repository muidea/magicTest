from pathlib import Path
import sys


def _append_path(path: Path) -> None:
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.append(path_str)


current_dir = Path(__file__).resolve().parent
package_dir = current_dir.parent
project_dir = package_dir.parent

_append_path(package_dir)
_append_path(project_dir)
