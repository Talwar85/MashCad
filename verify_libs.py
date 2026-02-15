import sys
print(f"Python: {sys.executable}")
print(f"Version: {sys.version}")

try:
    import cv2
    print(f"OpenCV available: {cv2.__version__}")
except ImportError:
    print("OpenCV NOT found")

try:
    import pymeshlab
    print("PyMeshLab available")
except ImportError:
    print("PyMeshLab NOT found")

try:
    import meshlib.mrmeshpy as mrmeshpy
    print("MeshLib available")
except ImportError:
    try:
        import meshlib
        print("MeshLib (root) available")
    except ImportError:
        print("MeshLib NOT found")
