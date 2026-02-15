
import sys
from PySide6.QtWidgets import QApplication

def test_mainwindow_init():
    if not QApplication.instance():
        app = QApplication(sys.argv)
    
    try:
        from gui.main_window import MainWindow
        win = MainWindow()
        print("MainWindow initialized successfully")
    except Exception as e:
        print(f"MainWindow initialization failed: {e}")
        raise e
