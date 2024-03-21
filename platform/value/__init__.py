import os
import sys

file_path = os.path.abspath(__file__)

# platform/value
dir_path = os.path.dirname(file_path)
sys.path.append(dir_path)

# platform
dir_path = os.path.dirname(dir_path)
sys.path.append(dir_path)

# mock
mock_path = os.path.dirname(dir_path + "/mock")
sys.path.append(mock_path)

# session
session_path = os.path.dirname(dir_path + "/session")
sys.path.append(session_path)

