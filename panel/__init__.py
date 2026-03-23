from pathlib import Path
import sys


dir_path = Path(__file__).resolve().parent
magic_test_path = dir_path.parent

if str(magic_test_path) not in sys.path:
    sys.path.insert(0, str(magic_test_path))

if str(dir_path) not in sys.path:
    sys.path.append(str(dir_path))
