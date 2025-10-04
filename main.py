from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication, QPushButton, QMainWindow, QWidget,
    QVBoxLayout, QLabel, QHBoxLayout
)
import sys

from bmpfile import BMPFile
from debouncedSlider import DebouncedSlider
from imageView import ImageView

app = QApplication(sys.argv)


class FileDrop(QWidget):
    dropped = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)


        layout = QVBoxLayout()
        self.setLayout(layout)

        self.label = QLabel("📁 Drop BMP file here")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setFont(QFont("Segoe UI", 14, QFont.Bold))
        self.setMinimumSize(500, 350)
        layout.addWidget(self.label)

        # Default style
        self.setStyleSheet("""
            QWidget {
                background-color: #f9f9f9;
                border: 3px dashed #aaa;
                border-radius: 20px;
                transition: all 0.25s ease;
            }
            QLabel {
                color: #555;
                padding: 40px;
            }
        """)

        self.setMinimumSize(300, 200)

    def checkMimeData(self, event):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if len(urls) == 1 and urls[0].toLocalFile().endswith(".bmp"):
                return True
        return False

    def dragEnterEvent(self, event):
        if self.checkMimeData(event):
            event.accept()
            self.setHoverStyle(True)
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self.checkMimeData(event):
            event.accept()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.setHoverStyle(False)

    def dropEvent(self, event):
        self.setHoverStyle(False)
        if self.checkMimeData(event):
            event.accept()
            file_path = event.mimeData().urls()[0].toLocalFile()
            self.dropped.emit(file_path)
        else:
            event.ignore()

    def setHoverStyle(self, hovering: bool):
        if hovering:
            self.setStyleSheet("""
                QWidget {
                    background-color: #e3f2fd;
                    border: 3px solid #42a5f5;
                    border-radius: 20px;
                    box-shadow: 0px 0px 15px rgba(66, 165, 245, 0.4);
                    transition: all 0.25s ease;
                }
                QLabel {
                    color: #1e88e5;
                    padding: 40px;
                }
            """)
            self.label.setText("Drop your BMP file!")
        else:
            self.setStyleSheet("""
                QWidget {
                    background-color: #f9f9f9;
                    border: 3px dashed #aaa;
                    border-radius: 20px;
                    transition: all 0.25s ease;
                }
                QLabel {
                    color: #555;
                    padding: 40px;
                }
            """)
            self.label.setText("Drop BMP file here")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BMP Viewer")

        self.mainwidget = QWidget()
        layout = QVBoxLayout()

        # file info
        info_layout = QHBoxLayout()
        self.filename_label = QLabel("Filename: ")
        self.size_label = QLabel("Size: ")
        self.dimensions_label = QLabel("Dimensions: ")
        self.bpp_label = QLabel("Bits per pixel: ")
        for w in (self.filename_label, self.size_label, self.dimensions_label, self.bpp_label):
            info_layout.addWidget(w)
        layout.addLayout(info_layout)

        # file drop
        fdrop = FileDrop()
        fdrop.dropped.connect(self.onBMPOpen)
        layout.addWidget(fdrop)

        #test
        button = QPushButton("Click me to close")
        button.clicked.connect(app.quit)
        button.setFixedSize(200, 50)
        layout.addWidget(button)

        # scale slider
        self.scalelabel = QLabel("Scale: 100%")
        layout.addWidget(self.scalelabel)

        self.scale_slider = DebouncedSlider(Qt.Horizontal, delay=400)
        self.scale_slider.setRange(10, 200)     # 10..200 -> 5%..100%
        self.scale_slider.setValue(200)
        self.scale_slider.debouncedValueChanged.connect(self.apply_scale)
        layout.addWidget(self.scale_slider)

        # gamma slider
        gamma_row = QHBoxLayout()
        self.gammalabel = QLabel("Brightness: 1.00")
        gamma_row.addWidget(self.gammalabel)

        self.gamma_slider = DebouncedSlider(Qt.Horizontal, delay=400)
        self.gamma_slider.setRange(20, 300)
        self.gamma_slider.setValue(100)
        self.gamma_slider.setSingleStep(1)
        self.gamma_slider.debouncedValueChanged.connect(self.apply_gamma)
        gamma_row.addWidget(self.gamma_slider)
        layout.addLayout(gamma_row)

        self.ImageViewer = ImageView(300, 300)
        layout.addWidget(self.ImageViewer)

        # RGB toggle buttons
        rgb_layout = QHBoxLayout()
        self.red_btn = QPushButton("Red")
        self.green_btn = QPushButton("Green")
        self.blue_btn = QPushButton("Blue")

        self.red_btn.setStyleSheet("""
            QPushButton { background-color: lightgray; border: 1px solid gray; border-radius: 5px; }
            QPushButton:checked { background-color: red; color: white; }
        """)
        self.green_btn.setStyleSheet("""
            QPushButton { background-color: lightgray; border: 1px solid gray; border-radius: 5px; }
            QPushButton:checked { background-color: green; color: white; }
        """)
        self.blue_btn.setStyleSheet("""
            QPushButton { background-color: lightgray; border: 1px solid gray; border-radius: 5px; }
            QPushButton:checked { background-color: blue; color: white; }
        """)

        for btn in (self.red_btn, self.green_btn, self.blue_btn):
            btn.setCheckable(True)
            btn.setChecked(True)
            btn.setFixedWidth(60)
            rgb_layout.addWidget(btn)

        self.red_btn.clicked.connect(self.update_rgb)
        self.green_btn.clicked.connect(self.update_rgb)
        self.blue_btn.clicked.connect(self.update_rgb)
        layout.addLayout(rgb_layout)

        self.mainwidget.setLayout(layout)
        self.setCentralWidget(self.mainwidget)

    def _readableFileSizeScale(self, size):
        if size < 1000: return f"{size} bytes"
        if size < 1_000_000: return f"{size/1000:.2f} KB"
        if size < 1_000_000_000: return f"{size/1_000_000:.2f} MB"
        if size < 1_000_000_000_000: return f"{size/1_000_000_000:.2f} GB"
        return f"{size/1_000_000_000_000:.2f} TB"

    def showFileMetadata(self, filename, size, width, height, bpp):
        self.filename_label.setText("Filename: " + filename)
        self.size_label.setText("Size: " + self._readableFileSizeScale(size))
        self.dimensions_label.setText(f"Dimensions: {width}×{height}")
        self.bpp_label.setText("Bits per pixel: " + str(bpp))

    def onBMPOpen(self, url):
        bmp = BMPFile(url)
        self.showFileMetadata(bmp.filename, bmp.fileSize, bmp.width, bmp.height, bmp.bpp)
        self.ImageViewer.render_bmp(bmp)

    def apply_scale(self, slider_val):
        factor = slider_val / 200.0
        self.scalelabel.setText(f"Scale: {slider_val/2:.0f}%")
        self.ImageViewer.set_scale(factor)

    def apply_gamma(self, slider_val):
        gamma = max(0.01, slider_val / 100.0)
        self.gammalabel.setText(f"Brightness: {gamma:.2f}")
        self.ImageViewer.set_gamma(gamma)

    def update_rgb(self):
        self.ImageViewer.set_rgb_mask(
            red=self.red_btn.isChecked(),
            green=self.green_btn.isChecked(),
            blue=self.blue_btn.isChecked()
        )

if __name__ == '__main__':
    window = MainWindow()
    window.show()
    app.exec()

