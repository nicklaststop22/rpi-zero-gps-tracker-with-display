# rpi-zero-gps-tracker-with-display

A pocket GPS tracker built on a **Raspberry Pi Zero 2 W**, an **Adafruit Ultimate GPS HAT**, and a **Waveshare 2.13" e-Paper HAT** with **one button**. (The original 4-button Adafruit PiTFT version is still here as `gpslog/app_pitft.py`.) It shows your live position on screen and records your route to the SD card as **CSV and GPX**, ready to drop onto Google Maps.

No WiFi needed while tracking. Everything runs on the Pi.

## Features

- Live e-ink readout: fix, satellites, latitude/longitude, speed (mph), altitude (ft), UTC, points logged and track time
- E-ink is readable in sunlight and keeps its picture with no power
- Records to **CSV** (survives power cuts) and **GPX** (opens in mapping apps) at the same time
- Point every **10 seconds**, timestamped from **GPS time** (the Pi Zero has no clock battery, so its own clock can be wrong offline)
- **One button**: tap to start/stop a track, **hold 3 s** to close the track and shut down safely
- Starts on boot as a systemd service
- `tools/convert_tracks.py` repairs tracks and makes a simplified **KML for Google My Maps**

## Hardware

| Part | Notes |
|---|---|
| Raspberry Pi Zero 2 W | WiFi is 2.4 GHz only |
| Adafruit Ultimate GPS HAT (MTK3339) | runs on **3.3 V**, not 5 V |
| Waveshare 2.13" e-Paper HAT (V4 panel, SSD1680, 250x122) | SPI0 CE0, RST 17, DC 25, BUSY 24, PWR 18 |
| Momentary push button | GPIO 27 (pin 13) to GND (pin 14) |
| 5 V / 2.5 A power supply | weak supplies make the WiFi drop out first |

### Button and display wiring

| Button | Action |
|---|---|
| tap | start a track / stop and save it |
| hold 3 s | save the track, then shut the Pi down (screen keeps showing POWERED OFF) |

The e-Paper HAT covers the whole header, so connect it with its **8-wire cable** instead and leave the header free for the GPS and button:

| HAT wire | Pi pin |
|---|---|
| VCC | 17 (3.3 V) |
| GND | 20 |
| DIN | 19 (MOSI) |
| CLK | 23 (SCLK) |
| CS | 24 (CE0) |
| DC | 22 (GPIO25) |
| RST | 11 (GPIO17) |
| BUSY | 18 (GPIO24) |

### Wiring the GPS

> [!WARNING]
> **If you wire the GPS HAT separately, power it from 3.3 V (Pi pin 1), not 5 V.**
> The HAT has no regulator. It normally takes the Pi's 3.3 V straight from the header, and the GPS chip's absolute maximum is about 4.3 V. On 5 V it can be damaged, and its TX line will push 5 V into the Pi's RX pin (GPIO15), which is only rated for 3.3 V. (The separate Ultimate GPS *breakout* board is different: its VIN pin accepts 3.3 to 5 V.)

The display sits on the 40-pin header. The GPS HAT connects with **4 jumper wires** from the HAT's own header holes to the same pin numbers on the Pi:

| GPS HAT header hole | Pi header pin |
|---|---|
| 1 (3.3 V) | 1 (3.3 V) |
| 6 (GND) | 6 (GND) |
| 8 (TXD) | 8 (GPIO14 TXD) |
| 10 (RXD) | 10 (GPIO15 RXD) |

Wire them **pin number to pin number**. The HAT already crosses TX/RX in its own traces, so crossing them again breaks it. Only cross TX/RX if you wire to the GPS module's own TX/RX pads instead.

Do **not** feed the GPS 5 V. It's a 3.3 V part, and at 5 V its TX line also sends 5 V into the Pi's RX pin.

## Pi setup

Tested on Raspberry Pi OS (Debian 13, 32-bit) flashed with Raspberry Pi Imager.

**1. `/boot/firmware/config.txt`**, add:
```ini
enable_uart=1
dtoverlay=disable-bt
dtparam=spi=on
```
For the old PiTFT version instead, add `dtoverlay=pitft28-capacitive,rotate=90,speed=32000000,fps=25` and run `app_pitft.py`.
`disable-bt` moves the good UART (`ttyAMA0`) from Bluetooth to the GPIO pins for the GPS.

**2. No serial console** on the GPS port: `cmdline.txt` should have `console=tty1` and no `console=serial0`.

**3. Copy the app and install the service** (replace `unlucky` with your username in `systemd/gpslog.service`):
```bash
scp -r gpslog <user>@<pi>:~/
sudo cp systemd/gpslog.service /etc/systemd/system/
sudo systemctl disable --now gpsd.socket gpsd.service
sudo systemctl mask gpsd.socket          # the app owns /dev/serial0, not gpsd
sudo systemctl daemon-reload
sudo systemctl enable --now gpslog.service
```
Holding the button runs `sudo -n systemctl poweroff`, so the user needs passwordless sudo (the default first user on Raspberry Pi OS has it). Your user must also be in the `spi`, `gpio`, and `dialout` groups (the default first user already is). Python needs `pillow`, `spidev`, `gpiozero`, and `pyserial` (plus `numpy` for the PiTFT version), which are all preinstalled on Raspberry Pi OS.

**WiFi via cloud-init (optional):** `boot/network-config.example` and `boot/user-data.example` show the files Imager writes to the boot partition. Fill in your own SSID, password, and password hash.

## Getting your tracks

Tracks are saved on the Pi as `~/gpslog/logs/track_<date>_<time>.csv` and `.gpx`.

- **Over WiFi:** `scp '<user>@<pi>:~/gpslog/logs/track_*' .`
- **Without WiFi:** put the SD card in a Linux machine, mount the `rootfs` partition read-only, and copy `home/<user>/gpslog/logs/`. Windows can't read that partition by itself.

### Onto Google Maps

```bash
mkdir mytracks && cp tools/convert_tracks.py mytracks/ && mkdir mytracks/raw
# copy the track_*.csv files into mytracks/raw/, then:
python mytracks/convert_tracks.py      # optional arg: simplify tolerance in metres (default 5)
```
This writes a clean `.gpx` and a simplified `.kml` per track and prints distance, duration, moving time, and top speed. Import the `.kml` at **mymaps.google.com** → Create a new map → Import.

## Gotchas learned the hard way

- **Cutting power without STOP** leaves the GPX unclosed with junk (NUL) bytes at the end. The CSV stays clean, and `convert_tracks.py` rebuilds the GPX from it.
- **Only one program can use the serial port.** If `cgps` works but the screen says NO FIX (or the other way round), the other program has the port.
- **FIX LED:** blinking once a second means searching; once every ~15 seconds means it has a fix.
- **Two HATs need a stacking header.** Female-to-female doesn't mate, and the header looks mirrored from underneath. Always line up pin 1 (the square pad).

## Files

| Path | What |
|---|---|
| `gpslog/app.py` | main loop: one button, e-ink updates, logging |
| `gpslog/epaper.py` | small SSD1680 driver for the 2.13" e-Paper HAT (no vendor library needed) |
| `gpslog/ui_epaper.py` | draws the 250x122 e-ink screen |
| `gpslog/app_pitft.py` | older PiTFT version: 4 buttons, screen sleep |
| `gpslog/gpsreader.py` | reads NMEA from `/dev/serial0` (GGA + RMC) |
| `gpslog/logger.py` | writes CSV + GPX |
| `gpslog/ui.py` | draws the 320x240 PiTFT screen |
| `gpslog/fb.py` | pushes frames to `/dev/fb1` (RGB565); no pygame needed |
| `gpslog/locus.py` | PMTK commands for the GPS chip's own flash logger (unused backup) |
| `systemd/gpslog.service` | starts the app on boot |
| `tools/convert_tracks.py` | CSV to clean GPX + Google-ready KML, with stats |

## License

MIT. See [LICENSE](LICENSE).

## Disclaimer

For educational purposes only. See [DISCLAIMER.md](DISCLAIMER.md).
