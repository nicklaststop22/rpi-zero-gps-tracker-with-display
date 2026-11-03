"""Minimal driver for the Waveshare 2.13" e-Paper HAT (V3/V4 panel, SSD1680).

Only needs spidev + gpiozero (both preinstalled on Raspberry Pi OS), so there
is no vendor library to install. Panel is 122x250 portrait; show() takes a
250x122 landscape PIL image and rotates it.

Full refresh (~2 s, flashes black/white) clears ghosting; partial refresh
(~0.4 s, no flash) is used for normal updates. The image stays on the glass
with the power off, so there is no backlight to manage.

HAT pins (BCM): RST 17, DC 25, CS 8 (CE0), BUSY 24, PWR 18, SPI0 MOSI/SCLK.
"""
import time

import spidev
from gpiozero import DigitalInputDevice, DigitalOutputDevice

W, H = 250, 122            # landscape, as the app draws it
_PW, _PH = 122, 250        # native portrait
_ROW_BYTES = (_PW + 7) // 8


class EPaper:
    def __init__(self, rst=17, dc=25, busy=24, pwr=18, bus=0, device=0):
        self.pwr = DigitalOutputDevice(pwr, initial_value=True)   # Rev2.2+ power switch; harmless on older HATs
        self.rst = DigitalOutputDevice(rst, initial_value=True)
        self.dc = DigitalOutputDevice(dc)
        self.busy = DigitalInputDevice(busy, pull_up=False)
        self.spi = spidev.SpiDev()
        self.spi.open(bus, device)
        self.spi.max_speed_hz = 4_000_000
        self.spi.mode = 0
        self._base_set = False
        self._init()

    # ---- low level -------------------------------------------------
    def _cmd(self, c, *data):
        self.dc.off(); self.spi.writebytes([c])
        if data:
            self.dc.on(); self.spi.writebytes2(bytes(data))

    def _data(self, buf):
        self.dc.on(); self.spi.writebytes2(buf)

    def _wait(self, timeout=10.0):
        end = time.time() + timeout
        while self.busy.value and time.time() < end:   # BUSY high = working
            time.sleep(0.01)

    def _reset(self):
        self.rst.on(); time.sleep(0.02)
        self.rst.off(); time.sleep(0.002)
        self.rst.on(); time.sleep(0.02)

    def _window(self):
        self._cmd(0x44, 0x00, (_PW - 1) >> 3)                       # RAM x range (bytes)
        self._cmd(0x45, 0x00, 0x00, (_PH - 1) & 0xFF, (_PH - 1) >> 8)  # RAM y range
        self._cmd(0x4E, 0x00)                                       # x cursor
        self._cmd(0x4F, 0x00, 0x00)                                 # y cursor

    def _init(self):
        self._reset(); self._wait()
        self._cmd(0x12); self._wait()                        # software reset
        self._cmd(0x01, (_PH - 1) & 0xFF, (_PH - 1) >> 8, 0x00)  # gate lines
        self._cmd(0x11, 0x03)                                # x+, y+
        self._window()
        self._cmd(0x3C, 0x05)                                # border waveform
        self._cmd(0x21, 0x00, 0x80)                          # display update control
        self._cmd(0x18, 0x80)                                # internal temp sensor
        self._wait()
        self._base_set = False

    @staticmethod
    def _buffer(img):
        """250x122 landscape image -> 4000-byte panel buffer (1 = white)."""
        if img.size != (W, H):
            img = img.resize((W, H))
        return img.convert("1").rotate(90, expand=True).tobytes()

    # ---- public ----------------------------------------------------
    def show(self, img, full=False):
        buf = self._buffer(img)
        if full or not self._base_set:
            # write both RAM banks so the next partial refresh diffs against this
            self._window(); self._cmd(0x24); self._data(buf)
            self._window(); self._cmd(0x26); self._data(buf)
            self._cmd(0x22, 0xF7); self._cmd(0x20); self._wait()
            self._base_set = True
        else:
            self.rst.off(); time.sleep(0.001); self.rst.on()
            self._cmd(0x3C, 0x80)
            self._cmd(0x01, (_PH - 1) & 0xFF, (_PH - 1) >> 8, 0x00)
            self._cmd(0x11, 0x03)
            self._window(); self._cmd(0x24); self._data(buf)
            self._cmd(0x22, 0xFF); self._cmd(0x20); self._wait()

    def sleep(self):
        """Deep sleep: the picture stays, the panel draws ~0 current."""
        self._cmd(0x10, 0x01)
        time.sleep(0.1)
        self._base_set = False

    def close(self):
        try:
            self.sleep()
        finally:
            self.spi.close()
            for d in (self.rst, self.dc, self.busy, self.pwr):
                d.close()
