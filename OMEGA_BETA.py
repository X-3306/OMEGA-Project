import sys
import time

from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPixmap, QColor
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QProgressBar, QGraphicsOpacityEffect
)

from omega_protocol.ui.app import run
from omega_protocol.runtime import packaged_resource


class OmegaSplash(QWidget):
    def __init__(self):
        super().__init__()

        self.setFixedSize(500, 300)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setStyleSheet("""
            QWidget {
                background-color: #0a0a0a;
                border-radius: 12px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)

        # 🔵 ICON (FIX)
        self.icon = QLabel()
        icon_path = packaged_resource("omega_protocol.ui", "omega.png")

        if icon_path and icon_path.exists():
            pixmap = QPixmap(str(icon_path)).scaled(
                80, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self.icon.setPixmap(pixmap)
        else:
            self.icon.setText("Ω")
            self.icon.setStyleSheet("color: white; font-size: 40px;")

        self.icon.setAlignment(Qt.AlignCenter)

        # 🔵 TITLE
        self.title = QLabel("OMEGA PROTOCOL")
        self.title.setStyleSheet("""
            color: white;
            font-size: 18px;
            letter-spacing: 2px;
        """)
        self.title.setAlignment(Qt.AlignCenter)

        # 🔵 STATUS TEXT
        self.status = QLabel("Initializing...")
        self.status.setStyleSheet("color: #888; font-size: 12px;")
        self.status.setAlignment(Qt.AlignCenter)

        # 🔵 PROGRESS BAR (DOXBIN STYLE)
        self.progress = QProgressBar()
        self.progress.setFixedHeight(6)
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 100)

        self.progress.setStyleSheet("""
            QProgressBar {
                background-color: #111;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background-color: #00ffcc;
                border-radius: 3px;
            }
        """)

        layout.addWidget(self.icon)
        layout.addSpacing(10)
        layout.addWidget(self.title)
        layout.addSpacing(5)
        layout.addWidget(self.status)
        layout.addSpacing(15)
        layout.addWidget(self.progress)

        self._center()

        # 🔵 FADE IN
        self.opacity = QGraphicsOpacityEffect()
        self.setGraphicsEffect(self.opacity)

        self.fade = QPropertyAnimation(self.opacity, b"opacity")
        self.fade.setDuration(800)
        self.fade.setStartValue(0)
        self.fade.setEndValue(1)
        self.fade.setEasingCurve(QEasingCurve.OutCubic)

        # 🔵 PROGRESS TIMER
        self.timer = QTimer()
        self.timer.timeout.connect(self._update)

        self.value = 0

    def _center(self):
        screen = QApplication.primaryScreen().geometry()
        self.move(
            (screen.width() - self.width()) // 2,
            (screen.height() - self.height()) // 2,
        )

    def start(self):
        self.fade.start()
        self.timer.start(35)

    def _update(self):
        self.value += 1.5
        self.progress.setValue(int(self.value))

        messages = [
            "Initializing core...",
            "Loading modules...",
            "Securing runtime...",
            "Injecting subsystems...",
            "Finalizing..."
        ]

        index = min(len(messages) - 1, int(self.value // 20))
        self.status.setText(messages[index])

        if self.value >= 100:
            self.timer.stop()
            QTimer.singleShot(300, self.close)


if __name__ == "__main__":
    app = QApplication(sys.argv)

    splash = OmegaSplash()
    splash.show()
    splash.start()

    # wait until splash closes
    while splash.isVisible():
        app.processEvents()
        time.sleep(0.01)

    try:
        raise SystemExit(run())
    except Exception as e:
        print(f"Application error: {e}")
        raise