#!/usr/bin/env python3
"""GPS logger front-end for the Adafruit PiTFT Plus 2.8".

Live GPS readout on the panel. Four physical buttons (GPIO 17/22/23/24):
  START  - begin Pi-side logging (writes CSV + GPX together)
  STOP   - stop logging (finalizes the GPX)
  READ   - show a list of recorded tracks
  AWAKE  - toggle: screen stays on permanently  <->  auto-sleep after 2 min idle

Sleep turns the backlight off via GPIO 18; the GPS reader and logger keep
running underneath. When asleep, the first button press only wakes the screen.

Run:  python3 app.py        (stop gpsd first - this app owns /dev/serial0)
"""
import os
import time
import queue

from gpiozero import Button, OutputDevice

from fb import Framebuffer
from gpsreader import GPSReader
from logger import DualLogger
import ui

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
BACKLIGHT_GPIO = 18
SLEEP_AFTER = 120.0    # seconds of button inactivity before auto-sleep
READ_VIEW_SECS = 6.0   # how long the READ list stays up
LOG_INTERVAL = 10.0    # seconds between logged track points

ACTIONS = {label: gpio for gpio, label in ui.BUTTON_ROWS}


class App:
    def __init__(self):
        self.gps = GPSReader()
        self.fb = Framebuffer()
        self.log = DualLogger(LOG_DIR, min_interval=LOG_INTERVAL)
        self.backlight = OutputDevice(BACKLIGHT_GPIO, initial_value=True)
        self.events = queue.Queue()
        self._buttons = []

        self.log_state = "STOPPED"
        self.stay_awake = False
        self.asleep = False
        self.last_activity = time.time()
        self.toast = None
        self.toast_until = 0.0
        self.view = "live"           # or "logs"
        self.view_until = 0.0
        self.logs_cache = []

    def _flash(self, msg, secs=1.5):
        self.toast, self.toast_until = msg, time.time() + secs

    def _wire_buttons(self):
        for label, gpio in ACTIONS.items():
            b = Button(gpio, pull_up=True, bounce_time=0.05)
            b.when_pressed = (lambda lbl=label: self.events.put(lbl))
            self._buttons.append(b)

    def _wake(self):
        self.backlight.on()
        self.asleep = False
        self.last_activity = time.time()

    def _sleep(self):
        self.backlight.off()
        self.asleep = True

    # ---- actions ---------------------------------------------------
    def _do(self, label):
        if label == "START":
            self.log.start(); self.log_state = "RUNNING"; self._flash("logging")
        elif label == "STOP":
            self.log.stop(); self.log_state = "STOPPED"; self._flash("stopped")
        elif label == "READ":
            self.logs_cache = self.log.list_logs()
            self.view, self.view_until = "logs", time.time() + READ_VIEW_SECS
        elif label == "AWAKE":
            self.stay_awake = not self.stay_awake
            if self.stay_awake:
                self._wake(); self._flash("stay on")
            else:
                self.last_activity = time.time(); self._flash("auto-sleep 2m")

    # ---- main loop -------------------------------------------------
    def run(self):
        self.gps.start()
        self._wire_buttons()
        try:
            while True:
                now = time.time()

                # drain button presses
                while True:
                    try:
                        label = self.events.get_nowait()
                    except queue.Empty:
                        break
                    if self.asleep:
                        self._wake()          # first press only wakes
                    else:
                        self.last_activity = now
                        self._do(label)

                # keep logging regardless of screen state
                self.log.log_fix(self.gps.snapshot())

                # auto-sleep
                if not self.stay_awake and not self.asleep \
                        and now - self.last_activity > SLEEP_AFTER:
                    self._sleep()

                # expire the READ view
                if self.view == "logs" and now > self.view_until:
                    self.view = "live"

                # render only when awake
                if not self.asleep:
                    toast = self.toast if now < self.toast_until else None
                    if self.view == "logs":
                        img = ui.render_logs(self.logs_cache, self.stay_awake)
                    else:
                        img = ui.render(self.gps.snapshot(), self.log_state,
                                        self.stay_awake, toast)
                    self.fb.show(img)

                time.sleep(0.25)
        except KeyboardInterrupt:
            pass
        finally:
            self.log.stop()
            self.gps.stop()
            self.backlight.on()   # leave the screen lit on exit
            self.fb.close()


if __name__ == "__main__":
    App().run()
