
import sys
try:
    import build123d
    print(f"build123d imported successfully: {build123d.__version__ if hasattr(build123d, '__version__') else 'unknown version'}")
except ImportError as e:
    print(f"Failed to import build123d: {e}")

try:
    import ocp
    print("ocp imported successfully")
except ImportError as e:
    print(f"Failed to import ocp: {e}")
    # try OCP
    try:
        import OCP
        print("OCP (caps) imported successfully")
    except ImportError as e:
        print(f"Failed to import OCP: {e}")

print(f"Python executable: {sys.executable}")
print(f"Python path: {sys.path}")
