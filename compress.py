# compress.py
from bmpfile import BMPFile

# ===============================================================
#   Clean Arithmetic Coder (Witten-Neal-Cleary style)
#   - 32-bit range
#   - Correct E1/E2/E3 scaling
#   - Symmetric encoder/decoder
#   - Adaptive model for symbols 0..510 (residuals)
# ===============================================================

CODE_BITS = 32
FULL_RANGE = 1 << CODE_BITS          # 2^32
HALF       = FULL_RANGE >> 1         # 0.5
FIRST_QTR  = HALF >> 1               # 0.25
THIRD_QTR  = FIRST_QTR * 3           # 0.75


# ---------------------------------------------------------------
# Frequency model for symbols 0..(symbol_count-1)
# ---------------------------------------------------------------

class FrequencyTable:
    """
    Adaptive frequency table.
    Maintains:
      - freq[s] >= 1 for each symbol
      - cumulative table cum[i] = sum_{s < i} freq[s]
    """

    def __init__(self, symbol_count):
        self.symbol_count = symbol_count
        self.freq = [1] * symbol_count       # start with uniform counts
        self.cum = None                      # cumulative table
        self.total = symbol_count            # sum(freq)
    
    def _rebuild_cumulative(self):
        """Rebuilds cumulative frequencies from freq[]."""
        self.cum = [0] * (self.symbol_count + 1)
        s = 0
        for i in range(self.symbol_count):
            self.cum[i] = s
            s += self.freq[i]
        self.cum[self.symbol_count] = s
        self.total = s

    def _ensure_cum(self):
        if self.cum is None:
            self._rebuild_cumulative()

    # --- API used by encoder/decoder ---

    def get_total(self):
        self._ensure_cum()
        return self.total

    def get_low_high(self, symbol):
        """
        Returns (low, high) cumulative counts for the given symbol.
        low = sum_{s < symbol} freq[s]
        high = sum_{s <= symbol} freq[s]
        """
        self._ensure_cum()
        return self.cum[symbol], self.cum[symbol + 1]

    def get_symbol_for_value(self, value):
        """
        Given value in [0, total-1], returns the symbol such that:
          cum[symbol] <= value < cum[symbol+1]
        Uses binary search over cum[].
        """
        self._ensure_cum()
        lo, hi = 0, self.symbol_count
        while lo + 1 < hi:
            mid = (lo + hi) // 2
            if self.cum[mid] > value:
                hi = mid
            else:
                lo = mid
        return lo

    def increment(self, symbol):
        """
        Increment frequency of the given symbol.
        If counts get big, rescale to avoid overflow.
        """
        self.freq[symbol] += 1
        # When a single symbol grows large, total will too.
        # We rescale occasionally to keep totals reasonable.
        if self.freq[symbol] > 1_000_000:
            # Halve all frequencies (but keep >=1)
            for i in range(self.symbol_count):
                f = self.freq[i]
                f = (f + 1) // 2
                if f < 1:
                    f = 1
                self.freq[i] = f
        # Mark cumulative as dirty
        self.cum = None


# ---------------------------------------------------------------
# Arithmetic Encoder
# ---------------------------------------------------------------

class ArithmeticEncoder:
    def __init__(self):
        self.low = 0
        self.high = FULL_RANGE - 1
        self.pending = 0     # E3 underflow counter
        self.output_bits = []

    def _output_bit(self, bit):
        """Output one bit, then flush any pending opposite bits."""
        self.output_bits.append(bit)
        while self.pending > 0:
            self.output_bits.append(1 - bit)
            self.pending -= 1

    def encode_symbol(self, model: FrequencyTable, symbol: int):
        total = model.get_total()
        sym_low, sym_high = model.get_low_high(symbol)

        # Update [low, high] for this symbol
        range_ = self.high - self.low + 1
        self.high = self.low + (range_ * sym_high // total) - 1
        self.low  = self.low + (range_ * sym_low  // total)

        # Renormalize with E1/E2/E3 scaling
        while True:
            # E1: MSB 0
            if self.high < HALF:
                self._output_bit(0)
                self.low  = self.low * 2
                self.high = self.high * 2 + 1
            # E2: MSB 1
            elif self.low >= HALF:
                self._output_bit(1)
                self.low  = (self.low - HALF) * 2
                self.high = (self.high - HALF) * 2 + 1
            # E3: underflow region
            elif self.low >= FIRST_QTR and self.high < THIRD_QTR:
                self.pending += 1
                self.low  = (self.low - FIRST_QTR) * 2
                self.high = (self.high - FIRST_QTR) * 2 + 1
            else:
                break

        model.increment(symbol)

    def finish(self):
        """
        Flush final bits so decoder can disambiguate last interval.
        """
        self.pending += 1
        if self.low < FIRST_QTR:
            self._output_bit(0)
        else:
            self._output_bit(1)
        return self.output_bits


# ---------------------------------------------------------------
# Arithmetic Decoder
# ---------------------------------------------------------------

class ArithmeticDecoder:
    def __init__(self, bitstream):
        self.bitstream = bitstream
        self.pos = 0
        self.low = 0
        self.high = FULL_RANGE - 1
        self.code = 0

        # Init code with first CODE_BITS bits
        for _ in range(CODE_BITS):
            self.code = (self.code << 1) | self._read_bit()

    def _read_bit(self):
        if self.pos >= len(self.bitstream):
            # Past end of stream: pad with zeroes
            return 0
        b = self.bitstream[self.pos]
        self.pos += 1
        return b

    def decode_symbol(self, model: FrequencyTable) -> int:
        total = model.get_total()
        range_ = self.high - self.low + 1

        # Map code into [0, total-1]
        value = ((self.code - self.low + 1) * total - 1) // range_

        symbol = model.get_symbol_for_value(value)
        sym_low, sym_high = model.get_low_high(symbol)

        # Update interval
        self.high = self.low + (range_ * sym_high // total) - 1
        self.low  = self.low + (range_ * sym_low  // total)

        # Renormalize with E1/E2/E3 scaling
        while True:
            if self.high < HALF:
                # E1
                self.low  = self.low * 2
                self.high = self.high * 2 + 1
                self.code = (self.code * 2) + self._read_bit()
            elif self.low >= HALF:
                # E2
                self.low  = (self.low - HALF) * 2
                self.high = (self.high - HALF) * 2 + 1
                self.code = (self.code - HALF) * 2 + self._read_bit()
            elif self.low >= FIRST_QTR and self.high < THIRD_QTR:
                # E3
                self.low  = (self.low - FIRST_QTR) * 2
                self.high = (self.high - FIRST_QTR) * 2 + 1
                self.code = (self.code - FIRST_QTR) * 2 + self._read_bit()
            else:
                break

        model.increment(symbol)
        return symbol



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

MAX_RESIDUAL = 510        # residual in [0..510] after shifting by +255
SYMBOL_COUNT = MAX_RESIDUAL + 1  # 511 symbols


def compress_image(pixelmap):
    """Compress a full 2D pixel grid: [[(r,g,b), ...], ...]."""
    H = len(pixelmap)
    W = len(pixelmap[0])

    encoder = ArithmeticEncoder()
    model = FrequencyTable(SYMBOL_COUNT)

    # Work on copy to avoid modifying original
    pred_grid = [[(0, 0, 0)] * W for _ in range(H)]

    for y in range(H):
        for x in range(W):
            pr, pg, pb = loco_predictor(x, y, pred_grid)
            r, g, b = pixelmap[y][x]

            # residual in [-255..255] -> [0..510]
            dr = r - pr + 255
            dg = g - pg + 255
            db = b - pb + 255

            # safety clamp just in case (shouldn't be needed if predictor is sane)
            dr = max(0, min(MAX_RESIDUAL, dr))
            dg = max(0, min(MAX_RESIDUAL, dg))
            db = max(0, min(MAX_RESIDUAL, db))

            encoder.encode_symbol(model, dr)
            encoder.encode_symbol(model, dg)
            encoder.encode_symbol(model, db)

            pred_grid[y][x] = (r, g, b)

    return encoder.finish()


def decompress_image(bitstream, width, height):
    """Decompress into a pixel grid [[(r,g,b), ...], ...]."""
    decoder = ArithmeticDecoder(bitstream)
    model = FrequencyTable(SYMBOL_COUNT)

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

            # r,g,b should match original exactly if everything is correct.
            # We don't clamp here so mismatch shows up in verify step.
            grid[y][x] = (r, g, b)

    return grid


# Run compress.py directly for sanity check
if __name__ == "__main__":
    import random
    W, H = 16, 16
    img = [[(random.randint(0, 255),
             random.randint(0, 255),
             random.randint(0, 255)) for _ in range(W)] for _ in range(H)]
    bits = compress_image(img)
    dec = decompress_image(bits, W, H)
    print("Test OK:", img == dec)





        


