#!/usr/bin/env python3
"""GPS logger front-end for the Waveshare 2.13" e-Paper HAT + one button.

Starts logging automatically as soon as the Pi boots.
Pressing the button finishes the track and shuts the Pi down cleanly.

The button goes between GPIO 27 (pin 13) and GND (pin 14). The e-ink keeps its
last picture with no power, so after power-off it still shows "POWERED OFF".
Power-off needs passwordless sudo for `systemctl poweroff`.

The old PiTFT version (4 buttons, colour screen) is app_pitft.py.

Run:  python3 app.py        (stop gpsd first - this app owns /dev/serial0)
"""
import os
import time
import queue
import signal
import subprocess

from gpiozero import Button

from epaper import EPaper
from gpsreader import GPSReader
from logger import DualLogger
import ui_epaper as ui

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
BUTTON_GPIO = 27
LOG_INTERVAL = 10.0     # seconds between logged track points
MIN_REDRAW = 30.0       # seconds between e-ink updates; each refresh runs the
                        # panel's HV booster, which is noisy right above the GPS antenna
FULL_EVERY = 60         # partial refreshes between full ones (clears ghosting)


class App:
    def __init__(self):
        self.gps = GPSReader()
        self.log = DualLogger(LOG_DIR, min_interval=LOG_INTERVAL)
        self.epd = EPaper()
        self.events = queue.Queue()
        self.toast, self.toast_until = None, 0.0
        self._last_img = None
        self._last_draw = 0.0
        self._partials = 0

    def _wire_button(self):
        self.button = Button(BUTTON_GPIO, pull_up=True, bounce_time=0.05)
        self.button.when_pressed = lambda: self.events.put("POWEROFF")

    def _flash(self, msg, secs=4.0):
        self.toast, self.toast_until = msg, time.time() + secs

    def _draw(self, force=False):
        now = time.time()
        toast = self.toast if now < self.toast_until else None
        elapsed = now - self.log.started_at if self.log.running else 0
        img = ui.render(self.gps.snapshot(), self.log.running,
                        self.log.points, elapsed, toast)
        raw = img.tobytes()
        if raw == self._last_img or (not force and now - self._last_draw < MIN_REDRAW):
            return
        full = self._partials >= FULL_EVERY
        self.epd.show(img, full=full)
        self._partials = 0 if full else self._partials + 1
        self._last_img, self._last_draw = raw, now

    def _power_off(self):
        points = self.log.points if self.log.running else None
        self.log.stop()
        subprocess.run(
            ["sh", "-c", "mkdir -p /boot/firmware/gpslogs && cp -f /home/unlucky/gpslog/logs/* /boot/firmware/gpslogs/ 2>/dev/null; sync"],
            check=False,
        )
        self.epd.show(ui.render_shutdown(points), full=True)
        self.epd.close()
        subprocess.run(["sudo", "-n", "/usr/bin/systemctl", "poweroff"], check=False)

    def run(self):
        # systemd stops us with SIGTERM on any shutdown/reboot; turn it into a
        # normal exit so the finally block below still closes an open track
        signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(SystemExit(0)))
        self.gps.start()
        self.log.start()
        self._wire_button()
        # flash black then white first: one full refresh doesn't fully erase an
        # image that sat on the panel for a long time (ghosting)
        from PIL import Image
        for fill in (0, 255):
            self.epd.show(Image.new("1", (ui.W, ui.H), fill), full=True)
        self.epd.show(ui.render(self.gps.snapshot(), True, 0, 0), full=True)
        try:
            while True:
                try:
                    ev = self.events.get(timeout=0.25)
                except queue.Empty:
                    ev = None
                if ev == "POWEROFF":
                    self._power_off()
                    return
                self.log.log_fix(self.gps.snapshot())
                self._draw(force=ev is not None)
        except KeyboardInterrupt:
            pass
        finally:
            self.log.stop()
            self.gps.stop()
            try:
                self.epd.close()
            except Exception:
                pass


if __name__ == "__main__":
    App().run()
