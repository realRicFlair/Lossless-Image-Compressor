class BMPFile:
    def __init__(self, url):
        self.url = url
        self.bytes = None
        self.fileSize = 0
        self.filename = None
        self.height = 0           # can be negative (top-down)
        self.width = 0
        self.dataOffset = 0
        self.compression = None
        self.bpp = None
        self.colorTable = []      # list[(R,G,B,A)]
        self.numColors = 0
        self.pixelmap = []
        if self.url is not None:
            self.openFile()

    def openFile(self):
        with open(self.url, "rb") as f:
            self.filename = self.url.split("/")[-1]
            self.bytes = f.read()

        # --- File header / DIB header fields ---
        self.fileSize    = int.from_bytes(self.bytes[0x02:0x06], "little")
        self.dataOffset  = int.from_bytes(self.bytes[0x0A:0x0E], "little")  # bfOffBits
        self.width       = int.from_bytes(self.bytes[0x12:0x16], "little")
        self.height      = int.from_bytes(self.bytes[0x16:0x1A], "little")  # can be negative
        self.bpp         = int.from_bytes(self.bytes[0x1C:0x1E], "little")
        self.compression = int.from_bytes(self.bytes[0x1E:0x22], "little")

        if self.compression != 0:
            raise ValueError("Can't handle compressed BMP (compression != BI_RGB)")

        # Read the number of colors in the color table
        self.numColors = int.from_bytes(self.bytes[0x2E:0x32], "little")
        if self.numColors == 0 and self.bpp <= 8:
            # Default palette size for indexed formats
            self.numColors = 256 if self.bpp == 8 else (1 << self.bpp)

        # Read color table for indexed images (<= 8 bpp)
        self.colorTable.clear()
        if self.bpp <= 8 and self.numColors > 0:
            # Color table starts immediately after the headers; for classic BITMAPINFOHEADER it's 0x36,
            # but using bfOffBits - (numColors*4) is more robust.
            palette_bytes = self.numColors * 4
            colortable_offset = self.dataOffset - palette_bytes
            # Fallback if header used defaults (common case): try 0x36
            if colortable_offset < 0 or colortable_offset + palette_bytes > len(self.bytes):
                colortable_offset = 0x36
            # Clamp to file bounds
            palette_end = min(colortable_offset + palette_bytes, len(self.bytes))
            entries = (palette_end - colortable_offset) // 4
            for i in range(entries):
                b = self.bytes[colortable_offset + i*4 + 0]
                g = self.bytes[colortable_offset + i*4 + 1]
                r = self.bytes[colortable_offset + i*4 + 2]
                a = self.bytes[colortable_offset + i*4 + 3]  # usually 0
                self.colorTable.append((r, g, b, a))

        # Print info (optional)
        print("File size:", self.fileSize)
        print("Width:", self.width)
        print("Height:", self.height)
        print("Bits per pixel:", self.bpp)
        print("Compression:", self.compression)
        print("Data offset:", self.dataOffset)
        print("Palette entries:", len(self.colorTable))

    def generatePixelGrid(self):
        """Public interface to parse BMP into pixelmap."""
        if self.bpp == 1:
            return self._parse_1bpp()
        elif self.bpp == 4:
            return self._parse_4bpp()
        elif self.bpp == 8:
            return self._parse_8bpp()
        elif self.bpp == 24:
            return self._parse_24bpp()
        else:
            raise NotImplementedError(f"BPP={self.bpp} not supported yet")

    # ---------- Helpers ----------

    def _row_stride(self):
        """Row size in bytes (including 4-byte padding)."""
        return ((self.bpp * self.width + 31) // 32) * 4

    def _is_top_down(self):
        return self.height < 0

    def _abs_height(self):
        return abs(self.height)

    # ---------- Parsers ----------

    def _parse_1bpp(self):
        """Parse 1-bit BMP into Pixelmap (2D grid of RGB tuples)."""
        if len(self.colorTable) != 2:
            raise ValueError(f"Expected 2 color table entries for 1-bit BMP, got {len(self.colorTable)}")

        stride = self._row_stride()
        H = self._abs_height()
        top_down = self._is_top_down()

        color0 = self.colorTable[0]
        color1 = self.colorTable[1]

        grid = []
        for y in range(H):
            src_row = y if top_down else (H - 1 - y)
            row_offset = self.dataOffset + src_row * stride
            row_pixels = []
            for x in range(self.width):
                byte_index = x // 8
                bit_index = 7 - (x % 8)
                byte_value = self.bytes[row_offset + byte_index]
                bit = (byte_value >> bit_index) & 1
                c = color1 if bit else color0
                row_pixels.append((c[0], c[1], c[2]))
            grid.append(row_pixels)

        self.pixelmap = grid
        return grid

    def _parse_4bpp(self):
        """Parse 4-bit palettized BMP into Pixelmap (2D grid of RGB tuples)."""
        if len(self.colorTable) == 0:
            # For 4bpp, default palette size is 16 when header sets numColors=0 (already set in openFile)
            raise ValueError("4bpp BMP requires a color table (palette)")

        stride = self._row_stride()  # ((bpp*width + 31)//32)*4
        H = self._abs_height()
        top_down = self._is_top_down()

        grid = []
        for y in range(H):
            src_row = y if top_down else (H - 1 - y)
            row_offset = self.dataOffset + src_row * stride
            row_pixels = []

            # Two pixels per byte: high nibble = left pixel, low nibble = right pixel.
            # Example 0x1F => first pixel index=0x1 (2nd entry), second pixel index=0xF (16th entry).
            for x in range(self.width):
                byte_val = self.bytes[row_offset + (x // 2)]
                if (x % 2) == 0:
                    idx = (byte_val >> 4) & 0x0F  # high nibble
                else:
                    idx = byte_val & 0x0F  # low nibble

                if idx < len(self.colorTable):
                    r, g, b, _a = self.colorTable[idx]
                else:
                    r, g, b = 0, 0, 0  # guard against malformed palette/index
                row_pixels.append((r, g, b))
            grid.append(row_pixels)

        self.pixelmap = grid
        return grid

    def _parse_8bpp(self):
        """Parse 8-bit palettized BMP into Pixelmap (2D grid of RGB tuples)."""
        if len(self.colorTable) == 0:
            raise ValueError("8bpp BMP requires a color table (palette)")

        stride = self._row_stride()
        H = self._abs_height()
        top_down = self._is_top_down()

        grid = []
        for y in range(H):
            src_row = y if top_down else (H - 1 - y)
            row_offset = self.dataOffset + src_row * stride
            row_pixels = []
            # Each byte is an index into the palette
            for x in range(self.width):
                idx = self.bytes[row_offset + x]
                if idx >= len(self.colorTable):
                    # Guard against malformed files
                    r, g, b = 0, 0, 0
                else:
                    r, g, b, _a = self.colorTable[idx]
                row_pixels.append((r, g, b))
            grid.append(row_pixels)

        self.pixelmap = grid
        return grid

    def _parse_24bpp(self):
        """
        Parse 24-bit BMP (truecolor, BI_RGB) into Pixelmap (2D grid of RGB tuples).
        Each pixel is 3 bytes in B,G,R order; rows are padded to 4-byte boundaries.
        """
        if self.compression != 0:
            raise ValueError("24bpp parser supports only BI_RGB (no compression)")

        bytes_per_pixel = 3
        stride = self._row_stride()  # ((24*width + 31)//32)*4
        H = self._abs_height()
        top_down = self._is_top_down()

        grid = []
        for y in range(H):
            src_row = y if top_down else (H - 1 - y)
            row_offset = self.dataOffset + src_row * stride
            row_pixels = []

            # Walk the “payload” part of the row (ignore padding at the end)
            payload_len = self.width * bytes_per_pixel
            end = row_offset + payload_len

            # Safety clamp
            if end > len(self.bytes):
                raise ValueError("BMP pixel data truncated")

            i = row_offset
            for _x in range(self.width):
                b = self.bytes[i + 0]
                g = self.bytes[i + 1]
                r = self.bytes[i + 2]
                row_pixels.append((r, g, b))
                i += 3

            grid.append(row_pixels)

        self.pixelmap = grid
        return grid
