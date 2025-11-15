from bmpfile import BMPFile

# ===============================================================
#   Arithmetic Encoder / Decoder with E1/E2 scaling
# ===============================================================

class ArithmeticModel:
    """Adaptive frequency model for residual values (0..510 if using signed)."""

    def __init__(self, max_symbol=511):
        self.max_symbol = max_symbol
        self.freq = [1] * (max_symbol + 2)  # +1 for sentinel
        self.cum = None
        self.total = (max_symbol + 1)

    def _rebuild_cumulative(self):
        self.cum = [0] * (self.max_symbol + 3)
        s = 0
        for i in range(self.max_symbol + 2):
            self.cum[i] = s
            s += self.freq[i]
        self.total = s

    def update(self, symbol):
        self.freq[symbol] += 1
        if self.freq[symbol] > 20000:  # prevent overflow
            self.freq = [max(f // 2, 1) for f in self.freq]
        self._rebuild_cumulative()

    def get_range(self, symbol):
        if self.cum is None:
            self._rebuild_cumulative()
        lo = self.cum[symbol]
        hi = self.cum[symbol + 1]
        return lo, hi, self.total


class ArithmeticEncoder:
    def __init__(self):
        self.low = 0
        self.high = (1 << 32) - 1
        self.pending = 0
        self.output = []

    def _emit_bit(self, bit):
        self.output.append(bit)
        while self.pending > 0:
            self.output.append(1 - bit)
            self.pending -= 1

    def encode_symbol(self, model, symbol):
        lo, hi, total = model.get_range(symbol)

        range_ = self.high - self.low + 1
        self.high = self.low + (range_ * hi // total) - 1
        self.low = self.low + (range_ * lo // total)

        # E1 scaling
        while (self.high & 0x80000000) == (self.low & 0x80000000):
            self._emit_bit((self.high >> 31) & 1)
            self.low = (self.low << 1) & 0xFFFFFFFF
            self.high = ((self.high << 1) | 1) & 0xFFFFFFFF

        # E2 underflow
        while (self.low & 0x40000000) and not (self.high & 0x40000000):
            self.pending += 1
            self.low = (self.low << 1) ^ 0x80000000
            self.high = ((self.high ^ 0x80000000) << 1) | 1

        model.update(symbol)

    def finish(self):
        self.pending += 1
        bit = (self.low >> 31) & 1
        self._emit_bit(bit)
        return self.output


class ArithmeticDecoder:
    def __init__(self, bitstream):
        self.bitstream = bitstream
        self.pos = 0
        self.low = 0
        self.high = (1 << 32) - 1
        self.code = 0
        for _ in range(32):
            self.code = (self.code << 1) | self._read_bit()

    def _read_bit(self):
        if self.pos >= len(self.bitstream):
            return 0
        b = self.bitstream[self.pos]
        self.pos += 1
        return b

    def decode_symbol(self, model):
        range_ = self.high - self.low + 1
        total = model.total
        value = ((self.code - self.low + 1) * total - 1) // range_

        # find symbol
        if model.cum is None:
            model._rebuild_cumulative()

        # binary search cumulative table
        lo, hi = 0, model.max_symbol + 1
        while lo + 1 < hi:
            mid = (lo + hi) // 2
            if model.cum[mid] > value:
                hi = mid
            else:
                lo = mid
        symbol = lo

        # update ranges
        lo_c, hi_c = model.cum[symbol], model.cum[symbol + 1]
        self.high = self.low + (range_ * hi_c // total) - 1
        self.low = self.low + (range_ * lo_c // total)

        # E1 scaling
        while (self.high & 0x80000000) == (self.low & 0x80000000):
            self.code = ((self.code << 1) & 0xFFFFFFFF) | self._read_bit()
            self.low = (self.low << 1) & 0xFFFFFFFF
            self.high = ((self.high << 1) | 1) & 0xFFFFFFFF

        # E2 underflow
        while (self.low & 0x40000000) and not (self.high & 0x40000000):
            self.code = (((self.code ^ 0x80000000) << 1) & 0xFFFFFFFF) | self._read_bit()
            self.low = ((self.low ^ 0x80000000) << 1) & 0xFFFFFFFF
            self.high = (((self.high ^ 0x80000000) << 1) | 1) & 0xFFFFFFFF

        model.update(symbol)
        return symbol


# ===============================================================
#   Predictor + Residual Transform
# ===============================================================

def loco_predictor(x, y, grid):
    """
    LOCO-I median edge detector predictor.
    For borders: return 0 or nearest neighbor.
    """
    if x == 0 and y == 0:
        return (0, 0, 0)
    if x == 0:
        return grid[y - 1][x]
    if y == 0:
        return grid[y][x - 1]

    L = grid[y][x - 1]
    T = grid[y - 1][x]
    TL = grid[y - 1][x - 1]

    pred = []
    for c in range(3):
        l, t, tl = L[c], T[c], TL[c]
        p = l + t - tl
        p = max(min(p, max(l, t)), min(l, t))
        pred.append(p)
    return tuple(pred)


# ===============================================================
#   High-Level API
# ===============================================================

def compress_image(pixelmap):
    """Compress a full 2D pixel grid."""
    H = len(pixelmap)
    W = len(pixelmap[0])

    encoder = ArithmeticEncoder()
    model = ArithmeticModel()

    # Work on copy to avoid modifying original
    pred_grid = [[(0, 0, 0)] * W for _ in range(H)]

    # Encode residuals
    for y in range(H):
        for x in range(W):
            pred = loco_predictor(x, y, pred_grid)
            r, g, b = pixelmap[y][x]
            pr, pg, pb = pred

            dr = r - pr + 255
            dg = g - pg + 255
            db = b - pb + 255

            encoder.encode_symbol(model, dr)
            encoder.encode_symbol(model, dg)
            encoder.encode_symbol(model, db)

            pred_grid[y][x] = (r, g, b)

    return encoder.finish()


def decompress_image(bitstream, width, height):
    """Decompress into a pixel grid."""
    decoder = ArithmeticDecoder(bitstream)
    model = ArithmeticModel()

    grid = [[(0, 0, 0)] * width for _ in range(height)]

    for y in range(height):
        for x in range(width):
            pr, pg, pb = loco_predictor(x, y, grid)

            dr = decoder.decode_symbol(model)
            dg = decoder.decode_symbol(model)
            db = decoder.decode_symbol(model)

            r = (dr - 255) + pr
            g = (dg - 255) + pg
            b = (db - 255) + pb

            grid[y][x] = (r, g, b)

    return grid





        


