from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPainter, QColor
from PyQt5.QtWidgets import QApplication, QPushButton, QMainWindow, QWidget, QVBoxLayout, QLabel, QHBoxLayout, QSlider
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
        textWidget = QLabel("Drop files here")
        textWidget.setAlignment(Qt.AlignCenter)
        self.setLayout(QVBoxLayout())
        self.layout().addWidget(textWidget)

    def checkMimeData(self, event):
        if event.mimeData().hasUrls():
            if not len(event.mimeData().urls()) > 1:
                #Check if BMP File
                for url in event.mimeData().urls():
                    if url.toLocalFile().endswith(".bmp"):
                        return True
        return False

    def dragEnterEvent(self, event):
        if self.checkMimeData(event):  # check if files are being dragged
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self.checkMimeData(event):  # check if files are being dragged
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        if self.checkMimeData(event):
            event.accept()
            event.setDropAction(Qt.CopyAction) #tell os to have copy cursor

            urls=[]
            for url in event.mimeData().urls():
                urls.append(str(url.toLocalFile()))
            x = urls[0]
            self.dropped.emit(x)
        else:
            event.ignore()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BMP Viewer")

        self.fdrop = FileDrop()
        self.mainwidget = QWidget()
        layout = QVBoxLayout()

        info_layout = QHBoxLayout()
        self.filename_label = QLabel("Filename: ")
        self.size_label = QLabel("Size: ")
        self.dimensions_label = QLabel("Dimensions: ")
        self.bpp_label = QLabel("Bits per pixel: ")
        info_layout.addWidget(self.filename_label)
        info_layout.addWidget(self.size_label)
        info_layout.addWidget(self.dimensions_label)
        info_layout.addWidget(self.bpp_label)
        layout.addLayout(info_layout)

        fdrop = FileDrop()
        fdrop.setFixedSize(200, 50)
        fdrop.dropped.connect(self.onBMPOpen)
        layout.addWidget(fdrop)

        button = QPushButton("Click me to close")
        # button.clicked.connect(app.quit)
        button.clicked.connect(closeApp)
        button.setFixedSize(200, 50)
        layout.addWidget(button)

        self.scalelabel = QLabel("Scale: 100%", self)
        layout.addWidget(self.scalelabel)

        self.slider = DebouncedSlider(Qt.Horizontal, delay=400)
        self.slider.setRange(10, 200)
        self.slider.setValue(100)
        layout.addWidget(self.slider)

        self.slider.debouncedValueChanged.connect(self.apply_scale)



        self.ImageViewer = ImageView(300, 300)
        layout.addWidget(self.ImageViewer)

        # RGB Toggle Buttons
        rgb_layout = QHBoxLayout()
        self.red_btn = QPushButton("Red")
        self.green_btn = QPushButton("Green")
        self.blue_btn = QPushButton("Blue")

        self.red_btn.setStyleSheet("""
            QPushButton {
                background-color: lightgray;
                border: 1px solid gray;
                border-radius: 5px;
            }
            QPushButton:checked {
                background-color: red;
                color: white;
            }
        """)

        self.green_btn.setStyleSheet("""
            QPushButton {
                background-color: lightgray;
                border: 1px solid gray;
                border-radius: 5px;
            }
            QPushButton:checked {
                background-color: green;
                color: white;
            }
        """)

        self.blue_btn.setStyleSheet("""
            QPushButton {
                background-color: lightgray;
                border: 1px solid gray;
                border-radius: 5px;
            }
            QPushButton:checked {
                background-color: blue;
                color: white;
            }
        """)

        # Make them togglable
        for btn in (self.red_btn, self.green_btn, self.blue_btn):
            btn.setCheckable(True)
            btn.setChecked(True)
            btn.setFixedWidth(60)
            rgb_layout.addWidget(btn)

        # Connect each to update_rgb
        self.red_btn.clicked.connect(self.update_rgb)
        self.green_btn.clicked.connect(self.update_rgb)
        self.blue_btn.clicked.connect(self.update_rgb)

        layout.addLayout(rgb_layout)

        self.mainwidget.setLayout(layout)
        self.setCentralWidget(self.mainwidget)

    def showFileMetadata(self, filename, size, width, height, bpp):
        self.filename_label.setText("Filename: " + filename)

        if 0 < size < 1000:
            self.size_label.setText("Size: " + str(size)[:5] + " bytes")
        elif 1000 < size < 1000000:
            self.size_label.setText("Size: " + str(size / 1000)[:5] + " KB")
        elif 1000000 < size < 1000000000:
            self.size_label.setText("Size: " + str(size / 1000000)[:5] + " MB")
        elif 1000000000 < size:
            self.size_label.setText("Size: " + str(size / 1000000000)[:5] + " GB")
        else:
            self.size_label.setText("Size: " + str(size / (1000000000 * 1000))[:5] + " TB")


        self.dimensions_label.setText("Dimensions: " + str(width) + "×" + str(height))
        self.bpp_label.setText("Bits per pixel: " + str(bpp))

    def onBMPOpen(self, url):
        bmp = BMPFile(url)
        self.showFileMetadata(bmp.filename, bmp.fileSize, bmp.width, bmp.height, bmp.bpp)
        self.ImageViewer.render_bmp(bmp)


    def apply_scale(self, scale):
        self.scalelabel.setText(f"Scale: {scale/2}%")
        if not getattr(self.ImageViewer, "pixelgrid", None):
            return
        if scale > 195:
            self.ImageViewer.render_bmp(self.ImageViewer.bmp)
        else:
            self.ImageViewer.rescale_img(scale / 200.0)

    def update_rgb(self):
        self.ImageViewer.apply_rgb_mask(
            red=self.red_btn.isChecked(),
            green=self.green_btn.isChecked(),
            blue=self.blue_btn.isChecked()
        )


def closeApp():
    app.quit()

if __name__ == '__main__':
    window = MainWindow()
    window.show()
    app.exec()



