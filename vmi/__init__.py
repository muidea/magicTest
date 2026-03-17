import os
import sys
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(PACKAGE_DIR)

for component in ("session", "cas", "mock"):
    component_path = os.path.join(PROJECT_ROOT, component)
    if component_path not in sys.path:
        sys.path.insert(0, component_path)

if PACKAGE_DIR not in sys.path:
    sys.path.insert(0, PACKAGE_DIR)
