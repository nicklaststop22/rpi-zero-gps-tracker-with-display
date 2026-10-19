"""Framebuffer driver for the Adafruit 2.8" PiTFT (fb_ili9340, 320x240, RGB565).

Draws by pushing raw little-endian RGB565 bytes to /dev/fb1. No pygame / SDL
needed - just Pillow + numpy, both already present on the Pi. The user running
this must be in the `video` group (unlucky already is).
"""
import numpy as np
from PIL import Image


class Framebuffer:
    def __init__(self, path="/dev/fb1", width=320, height=240):
        self.path = path
        self.width = width
        self.height = height
        self._f = open(path, "r+b")

    def show(self, img: Image.Image):
        """Blit a PIL image (any mode/size) to the panel."""
        if img.size != (self.width, self.height):
            img = img.resize((self.width, self.height))
        a = np.asarray(img.convert("RGB"), dtype=np.uint16)
        r = a[..., 0] >> 3
        g = a[..., 1] >> 2
        b = a[..., 2] >> 3
        rgb565 = ((r << 11) | (g << 5) | b).astype("<u2")  # little-endian
        self._f.seek(0)
        self._f.write(rgb565.tobytes())
        self._f.flush()

    def close(self):
        try:
            self._f.close()
        except Exception:
            pass
