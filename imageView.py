import copy
import sys, random
from PyQt5.QtWidgets import QApplication, QLabel
from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QImage, QPixmap, QColor
import math


class ImageView(QLabel):
    def __init__(self, width=200, height=200):
        super().__init__()
        self.width_ = width
        self.height_ = height
        self.pixelgrid = None

        # Create a blank black image (Were NOT using the QImage library stuff here. I just need to use it to output pixels cus otherwise I would be using opengl).
        self.image = QImage(width, height, QImage.Format_RGB32)
        self.image.fill(QColor(0, 0, 0))
        self.bmp = None

        # Set initial display
        self.setPixmap(QPixmap.fromImage(self.image))

        # Timer to add random pixels
        #self.timer = QTimer(self)
        #self.timer.timeout.connect(self.add_random_pixel)
        #self.timer.start(100)  # update every 500 ms

    def render_bmp(self, bmp):
        self.bmp = bmp
        # copy original pixel grid into our working grid
        self.pixelgrid = [row[:] for row in bmp.generatePixelGrid()]
        self.width_ = bmp.width
        self.height_ = bmp.height
        self.render_from_pixelgrid()



    def render_from_pixelgrid(self):
        h = len(self.pixelgrid)
        w = len(self.pixelgrid[0])
        self.setMinimumSize(w, h)
        self.image = QImage(w, h, QImage.Format_RGB32)

        for y in range(h):
            for x in range(w):
                r, g, b = self.pixelgrid[y][x]
                self.image.setPixel(x, y, QColor(r, g, b).rgb())

        self.setPixmap(QPixmap.fromImage(self.image))
        print(f"Rendered {w}x{h} scaled image")


    def rescale_img(self, scaleFactor):
        # Nearest neighbhor causes aliasing since we sample below nyquist
        # Average the surrounding pixels only allows you to do it in discrete steps.
        # Bilinear interpolation is better cus you can sample any non-integer coordinate and get any scale you want
        # has issues with dithering from the 1bpp images tho. If i had more time maybe I could do a low pass filter
        # Rescales bmp.pixelgrid into self.pixelgrid
        if not self.bmp:
            return

        src = copy.deepcopy(self.bmp.pixelmap)
        # to avoid dithering, do a low pass with gaussian kernel
        if self.bmp.bpp == 1:
            src = gaussian_blur(src, radius=1, sigma=0.8)  # tweak as needed

        src_h = self.bmp.height
        src_w = self.bmp.width

        new_w = max(1, int(src_w * scaleFactor))
        new_h = max(1, int(src_h * scaleFactor))

        out = [[(0, 0, 0) for _ in range(new_w)] for _ in range(new_h)]

        for y_out in range(new_h):
            for x_out in range(new_w):
                # Map destination pixel to source coordinates
                src_x = (x_out + 0.5) / scaleFactor - 0.5
                src_y = (y_out + 0.5) / scaleFactor - 0.5

                # Find surrounding integer coordinates
                x0 = int(src_x)
                x1 = min(x0 + 1, src_w - 1)
                y0 = int(src_y)
                y1 = min(y0 + 1, src_h - 1)

                # Fractional parts
                a = src_x - x0
                b = src_y - y0

                # Get 4 neighbors
                c00 = src[y0][x0]
                c10 = src[y0][x1]
                c01 = src[y1][x0]
                c11 = src[y1][x1]

                # Bilinear interpolation per channel
                r = int((1 - a) * (1 - b) * c00[0] + a * (1 - b) * c10[0] +
                        (1 - a) * b * c01[0] + a * b * c11[0])
                g = int((1 - a) * (1 - b) * c00[1] + a * (1 - b) * c10[1] +
                        (1 - a) * b * c01[1] + a * b * c11[1])
                b_ = int((1 - a) * (1 - b) * c00[2] + a * (1 - b) * c10[2] +
                         (1 - a) * b * c01[2] + a * b * c11[2])

                out[y_out][x_out] = (r, g, b_)

        self.pixelgrid = out
        self.render_from_pixelgrid()

    def apply_rgb_mask(self, red=True, green=True, blue=True):
        # Toggle the visibility of red, green, and blue channels
        if not self.bmp or not self.pixelgrid:
            return

        # Copy the original bmp pixel grid (not the potentially modified one)
        src = [row[:] for row in self.bmp.generatePixelGrid()]
        masked = [[(0, 0, 0) for _ in range(self.bmp.width)] for _ in range(self.bmp.height)]

        for y in range(self.bmp.height):
            for x in range(self.bmp.width):
                r, g, b = src[y][x]
                r = r if red else 0
                g = g if green else 0
                b = b if blue else 0
                masked[y][x] = (r, g, b)

        self.pixelgrid = masked
        self.render_from_pixelgrid()


def gaussian_kernel(radius=1, sigma=1.0):
    """Return a normalized 2D Gaussian kernel."""
    size = 2 * radius + 1
    kernel = [[0.0 for _ in range(size)] for _ in range(size)]
    sum_val = 0.0

    for y in range(-radius, radius + 1):
        for x in range(-radius, radius + 1):
            val = math.exp(-(x ** 2 + y ** 2) / (2 * sigma ** 2))
            kernel[y + radius][x + radius] = val
            sum_val += val

    # Normalize so sum = 1
    for y in range(size):
        for x in range(size):
            kernel[y][x] /= sum_val
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
            out[y][x] = (int(r_acc), int(g_acc), int(b_acc))

    return out

