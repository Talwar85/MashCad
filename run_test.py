import os
import sys

# Add DLL directories to PATH before any imports
vtk_libs = r'C:\Users\User\miniforge3\envs\cad_env\Lib\site-packages\vtk.libs'
ocp_libs = r'C:\Users\User\miniforge3\envs\cad_env\Lib\site-packages\cadquery_ocp.libs'

os.add_dll_directory(vtk_libs)
os.add_dll_directory(ocp_libs)

# Set PATH
os.environ['PATH'] = f"{vtk_libs};{ocp_libs};" + os.environ.get('PATH', '')

# Now try to import
sys.path.insert(0, r'c:\LiteCad')

import build123d as bd
print(f"build123d version: {bd.__version__}")

# Run the test
from test.test_boolean_feature import run_all_boolean_feature_tests
run_all_boolean_feature_tests()
