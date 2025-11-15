from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QMessageBox, QFileDialog
)

from bmpfile import BMPFile
from compress import compress_image, decompress_image


class CompressionWidget(QWidget):
    """
    Simple UI wrapper for BMP compression/decompression.

    Usage:
        cw = CompressionWidget()
        cw.set_bmp(bmp)   # bmp is a BMPFile instance
    """
    def __init__(self, parent=None):
        super().__init__(parent)

        self.current_bmp: BMPFile | None = None
        self.original_grid = None      # 2D list of (r,g,b)
        self.compressed_bits = None    # list[int]
        self.width = 0
        self.height = 0
        self.original_filesize = 0

        self._build_ui()

    # ---------------- UI ---------------- #

    def _build_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        title = QLabel("Compression")
        title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title)

        # Buttons row
        btn_row = QHBoxLayout()
        self.compress_btn = QPushButton("Compress")
        self.decompress_btn = QPushButton("Decompress & Verify")

        self.compress_btn.clicked.connect(self.on_compress_clicked)
        self.decompress_btn.clicked.connect(self.on_decompress_clicked)

        btn_row.addWidget(self.compress_btn)
        btn_row.addWidget(self.decompress_btn)
        layout.addLayout(btn_row)

        # Info labels
        self.status_label = QLabel("Status: idle")
        self.size_label = QLabel("Compressed size: -")
        self.ratio_label = QLabel("Compression ratio: -")

        for lbl in (self.status_label, self.size_label, self.ratio_label):
            lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        layout.addWidget(self.status_label)
        layout.addWidget(self.size_label)
        layout.addWidget(self.ratio_label)

        self.save_btn = QPushButton("Save Compressed File")
        self.save_btn.clicked.connect(self.on_save_clicked)
        self.save_btn.setEnabled(False)
        layout.addWidget(self.save_btn)


        self.setLayout(layout)

        self.setStyleSheet("""
            QWidget {
                background-color: #f5f5f5;
                border: 1px solid #ccc;
                border-radius: 8px;
            }
            QPushButton {
                padding: 6px 10px;
            }
        """)

    # -------------- Public API -------------- #

    def set_bmp(self, bmp: BMPFile):
        """
        Tell the widget which BMP to work with.
        Call this from MainWindow.onBMPOpen().
        """
        self.current_bmp = bmp
        self.width = bmp.width
        self.height = abs(bmp.height)
        self.original_filesize = bmp.fileSize

        # Generate pixel grid if not already present
        if bmp.pixelmap:
            self.original_grid = bmp.pixelmap
        else:
            self.original_grid = bmp.generatePixelGrid()

        # Reset compression state
        self.compressed_bits = None
        self.status_label.setText("Status: ready (no compressed data yet)")
        self.size_label.setText("Compressed size: -")
        self.ratio_label.setText("Compression ratio: -")

    # -------------- Slots -------------- #

    def on_compress_clicked(self):
        if self.current_bmp is None or self.original_grid is None:
            self._set_status("No BMP loaded.", error=True)
            return

        try:
            self._set_status("Compressing...", busy=True)
            bits = compress_image(self.original_grid)
            self.compressed_bits = bits

            compressed_bytes = (len(bits) + 7) // 8
            self.size_label.setText(f"Compressed size: {compressed_bytes} bytes")

            if self.original_filesize > 0:
                ratio = self.original_filesize / compressed_bytes if compressed_bytes > 0 else 0
                self.ratio_label.setText(f"Compression ratio: {ratio:.2f}x")
            else:
                self.ratio_label.setText("Compression ratio: -")

            self.save_btn.setEnabled(True)
            self._set_status("Compression done.")
            
        except Exception as e:
            self._set_status(f"Compression error: {e}", error=True)

    def on_decompress_clicked(self):
        if self.current_bmp is None or self.original_grid is None:
            self._set_status("No BMP loaded.", error=True)
            return
        if self.compressed_bits is None:
            self._set_status("Nothing to decompress (run Compress first).", error=True)
            return

        try:
            self._set_status("Decompressing...", busy=True)
            decoded = decompress_image(self.compressed_bits, self.width, self.height)

            # Verify lossless reconstruction
            ok = self._compare_grids(self.original_grid, decoded)
            if ok:
                self._set_status("Decompression OK: image matches original.")
                QMessageBox.information(self, "Decompression", "Decompression successful.\nImage matches original.")
            else:
                self._set_status("Decompression mismatch: pixels differ!", error=True)
                QMessageBox.warning(self, "Decompression", "Decompression finished, but image differs from original.")
        except Exception as e:
            self._set_status(f"Decompression error: {e}", error=True)


    def on_save_clicked(self):
        if self.compressed_bits is None:
            QMessageBox.warning(self, "Save", "No compressed data. Please compress first.")
            return

        # Ask where to save
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Compressed File",
            "image.compress",
            "Compressed Files (*.bin);;All Files (*)"
        )
        if not path:
            return

        try:
            # Convert bitstream -> bytes
            data_bytes = self._bits_to_bytes(self.compressed_bits)

            # Minimal header: width & height (4 bytes each, little-endian)
            header = self.width.to_bytes(4, "little") + self.height.to_bytes(4, "little")

            with open(path, "wb") as f:
                f.write(header)
                f.write(data_bytes)

            QMessageBox.information(self, "Saved", f"Compressed file saved:\n{path}")
            self._set_status("File saved successfully.")
        except Exception as e:
            self._set_status(f"Save error: {e}", error=True)
            QMessageBox.critical(self, "Error Saving", str(e))

    # -------------- Helpers -------------- #

    def _set_status(self, text: str, error: bool = False, busy: bool = False):
        if error:
            self.status_label.setStyleSheet("color: red;")
        elif busy:
            self.status_label.setStyleSheet("color: #1565c0;")
        else:
            self.status_label.setStyleSheet("color: #333;")
        self.status_label.setText("Status: " + text)

    @staticmethod
    def _compare_grids(a, b):
        if len(a) != len(b):
            return False
        for row1, row2 in zip(a, b):
            if len(row1) != len(row2):
                return False
            for p1, p2 in zip(row1, row2):
                if p1 != p2:
                    return False
        return True
    
    @staticmethod
    def _bits_to_bytes(bits):
        out = bytearray()
        byte = 0
        count = 0
        for b in bits:
            byte = (byte << 1) | b
            count += 1
            if count == 8:
                out.append(byte)
                byte = 0
                count = 0
        if count > 0:
            byte <<= (8 - count)
            out.append(byte)
        return bytes(out)

