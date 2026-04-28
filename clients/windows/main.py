import sys
from PyQt6.QtWidgets import QApplication, QLabel, QMainWindow
from PyQt6.QtCore import Qt

class SubtitleOverlay(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.label = QLabel("Subtitles will appear here", self)
        self.label.setStyleSheet("color: white; font-size: 24px; background-color: rgba(0, 0, 0, 150); padding: 10px;")
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCentralWidget(self.label)
        self.resize(800, 100)
        
    def update_text(self, text):
        self.label.setText(text)

def main():
    app = QApplication(sys.argv)
    overlay = SubtitleOverlay()
    overlay.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
