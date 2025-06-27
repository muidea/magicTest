import os
import sys

dir_path = os.path.dirname(os.path.abspath(__file__))

# cas
dir_path = os.path.dirname(dir_path)
sys.path.append(dir_path)

dir_path = os.path.dirname(dir_path)
sys.path.append(dir_path)
