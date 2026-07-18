import os
import sys

# Suppress OpenCV verbose backend probing before any cv2 import
os.environ["OPENCV_LOG_LEVEL"] = "OFF"
os.environ["OPENCV_VIDEOIO_DEBUG"] = "0"

from PySide6.QtWidgets import QApplication
from src.db.database import init_db


def main():
    init_db()

    app = QApplication(sys.argv)
    app.setApplicationName("AirWrite Capture")

    from src.ui.main_window import MainWindow
    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
