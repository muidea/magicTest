from pathlib import Path
import sys


def _append_path(path: Path) -> None:
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.append(path_str)


current_dir = Path(__file__).resolve().parent
workspace_file_dir = current_dir
session_dir = current_dir.parent / "session"

_append_path(workspace_file_dir)
_append_path(session_dir)
