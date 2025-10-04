import copy
import math
from PyQt5.QtWidgets import QLabel
from PyQt5.QtGui import QImage, QPixmap, QColor


class ImageView(QLabel):
    def __init__(self, width=200, height=200):
        super().__init__()
        self.width_ = width
        self.height_ = height

        self.bmp = None

        self.scale = 1.0
        self.mask_r = True
        self.mask_g = True
        self.mask_b = True
        self.gamma = 1.0

        # backing image
        self.image = QImage(width, height, QImage.Format_RGB32)
        self.image.fill(QColor(0, 0, 0))
        self.setPixmap(QPixmap.fromImage(self.image))


    def render_bmp(self, bmp):
        #Load a new BMP, render once
        self.bmp = bmp
        # Reset pipeline for new image
        self.scale = 1.0
        self.mask_r = self.mask_g = self.mask_b = True
        self.gamma = 1.0
        self.rebuild()

    def set_scale(self, factor: float):
        if not self.bmp:
            return
        self.scale = max(0.01, float(factor))
        self.rebuild()

    def set_rgb_mask(self, red=True, green=True, blue=True):
        if not self.bmp:
            return
        self.mask_r, self.mask_g, self.mask_b = bool(red), bool(green), bool(blue)
        self.rebuild()

    def set_gamma(self, gamma_value: float):
        if not self.bmp:
            return
        # keep it sane
        self.gamma = max(0.01, float(gamma_value))
        self.rebuild()


    def rebuild(self):
        if not self.bmp:
            return

        src = copy.deepcopy(self.bmp.pixelmap if self.bmp.pixelmap else self.bmp.generatePixelGrid())

        # Idk if this allowed, but its we do a low pass on the image with a gaussian kernel
        # to reduce dithering artifacts
        if self.bmp.bpp == 1 and self.scale < 1.0:
            src = gaussian_blur(src, radius=1, sigma=0.8)

        # 1) RGB channel toggles
        if not (self.mask_r and self.mask_g and self.mask_b):
            h, w = len(src), len(src[0])
            for y in range(h):
                row = src[y]
                for x in range(w):
                    r, g, b = row[x]
                    row[x] = (
                        r if self.mask_r else 0,
                        g if self.mask_g else 0,
                        b if self.mask_b else 0
                    )

        # 2) Accidently implemented gamma instead of YUV based brightness. Changed it last moent
        if abs(self.gamma - 1.0) > 1e-6:
            # Normalize gamma value (last moment change)
            brightness_scale = self.gamma / 1.5

            h, w = len(src), len(src[0])
            for y in range(h):
                row = src[y]
                for x in range(w):
                    r, g, b = row[x]
                    if self.bmp.numColors > 2 or self.bmp.bpp != 1:
                        Y = 0.299 * r + 0.587 * g + 0.114 * b
                        U = -0.14713 * r - 0.28886 * g + 0.436 * b
                        V = 0.615 * r - 0.51499 * g - 0.10001 * b

                        # Scale Y by normalized brightness
                        Y *= brightness_scale

                        # Convert back to RGB
                        r = int(Y + 1.13983 * V)
                        g = int(Y - 0.39465 * U - 0.58060 * V)
                        b = int(Y + 2.03211 * U)

                    else:
                        # For binary (1bpp) images, approximate brightness bump
                        factor = (brightness_scale - 1.0) * 127
                        r = int(r + factor)
                        g = int(g + factor)
                        b = int(b + factor)

                    # Clamp
                    r = max(0, min(255, r))
                    g = max(0, min(255, g))
                    b = max(0, min(255, b))
                    row[x] = (r, g, b)

        # 3) Scale. If factor around 1, keep as-is
        if self.scale <= 0:
            self.scale = 0.01
        src_h, src_w = len(src), len(src[0])
        new_w = max(1, int(src_w * self.scale))
        new_h = max(1, int(src_h * self.scale))

        if new_w != src_w or new_h != src_h:
            out = bilinear_resize(src, new_w, new_h, src_w, src_h, self.scale)
        else:
            out = src

        # 4) Render the image
        self._render_from_pixelgrid(out)


    def _render_from_pixelgrid(self, grid):
        h = len(grid)
        w = len(grid[0])
        self.setMinimumSize(w, h)
        self.image = QImage(w, h, QImage.Format_RGB32)

        for y in range(h):
            row = grid[y]
            for x in range(w):
                r, g, b = row[x]
                self.image.setPixel(x, y, QColor(r, g, b).rgb())

        self.setPixmap(QPixmap.fromImage(self.image))


# Nearest neighbhor causes aliasing since we sample below nyquist
# Average the surrounding pixels only allows you to do it in discrete steps.
# Bilinear interpolation is better cus you can sample any non-integer coordinate and get any scale you want
# has issues with dithering from the 1bpp images tho. If i had more time maybe I could do a low pass filter
# Rescales bmp.pixelgrid into self.pixelgrid
def bilinear_resize(src, new_w, new_h, src_w=None, src_h=None, scale=None):
    if src_h is None: src_h = len(src)
    if src_w is None: src_w = len(src[0])
    out = [[(0, 0, 0) for _ in range(new_w)] for _ in range(new_h)]

    # map output pixel centers back to source
    # derive scale if not provided
    if scale is None:
        scale_x = new_w / float(src_w)
        scale_y = new_h / float(src_h)
    else:
        scale_x = scale_y = scale

    for y_out in range(new_h):
        src_y = (y_out + 0.5) / scale_y - 0.5
        y0 = int(src_y)
        y1 = min(max(y0 + 1, 0), src_h - 1)
        wy = src_y - y0
        if y0 < 0: y0 = 0

        for x_out in range(new_w):
            src_x = (x_out + 0.5) / scale_x - 0.5
            x0 = int(src_x)
            x1 = min(max(x0 + 1, 0), src_w - 1)
            wx = src_x - x0
            if x0 < 0: x0 = 0

            c00 = src[y0][x0]
            c10 = src[y0][x1]
            c01 = src[y1][x0]
            c11 = src[y1][x1]

            r = int((1 - wx) * (1 - wy) * c00[0] + wx * (1 - wy) * c10[0] +
                    (1 - wx) * wy * c01[0] + wx * wy * c11[0])
            g = int((1 - wx) * (1 - wy) * c00[1] + wx * (1 - wy) * c10[1] +
                    (1 - wx) * wy * c01[1] + wx * wy * c11[1])
            b = int((1 - wx) * (1 - wy) * c00[2] + wx * (1 - wy) * c10[2] +
                    (1 - wx) * wy * c01[2] + wx * wy * c11[2])

            out[y_out][x_out] = (r, g, b)
    return out


def gaussian_kernel(radius=1, sigma=1.0):
    size = 2 * radius + 1
    kernel = [[0.0 for _ in range(size)] for _ in range(size)]
    sum_val = 0.0
    for y in range(-radius, radius + 1):
        for x in range(-radius, radius + 1):
            val = math.exp(-(x * x + y * y) / (2.0 * sigma * sigma))
            kernel[y + radius][x + radius] = val
            sum_val += val
    for j in range(size):
        for i in range(size):
            kernel[j][i] /= sum_val
    return kernel


def gaussian_blur(pixelgrid, radius=1, sigma=1.0):
    kernel = gaussian_kernel(radius, sigma)
    size = len(kernel)
    h = len(pixelgrid)
    w = len(pixelgrid[0])
    out = [[(0, 0, 0) for _ in range(w)] for _ in range(h)]
    for y in range(h):
        for x in range(w):
            r_acc = g_acc = b_acc = 0.0
            for j in range(size):
                for i in range(size):
                    yy = min(max(y + j - radius, 0), h - 1)
                    xx = min(max(x + i - radius, 0), w - 1)
                    kr = kernel[j][i]
                    r, g, b = pixelgrid[yy][xx]
                    r_acc += r * kr
                    g_acc += g * kr
                    b_acc += b * kr
            out[y][x] = (int(r_acc + 0.5), int(g_acc + 0.5), int(b_acc + 0.5))
    return out
