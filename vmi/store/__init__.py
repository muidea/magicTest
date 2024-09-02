import os
import sys

dir_path = os.path.dirname(os.path.abspath(__file__))

# vmi
dir_path = os.path.dirname(dir_path)
sys.path.append(dir_path)

dir_path = os.path.dirname(dir_path)
sys.path.append(dir_path)
