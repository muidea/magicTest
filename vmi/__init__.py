import os
import sys

dir_path = os.path.dirname(os.path.abspath(__file__))
print('----------------------------------------------------')
print(dir_path)

sys.path.append(dir_path)

dir_path = os.path.dirname(dir_path)
print('----------------------------------------------------')
print(dir_path)

sys.path.append(dir_path + '/session')
sys.path.append(dir_path + '/cas')
print('----------------------------------------------------')
print(sys.path)
