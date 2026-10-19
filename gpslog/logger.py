"""Pi-side track logger - writes CSV and GPX simultaneously.

CSV is the robust primary (append-only, one complete line per fix, survives a
power cut). GPX is written alongside for drop-in use in mapping tools; its
closing tags are added on stop(), and a mid-session crash leaves an unclosed
but easily-repaired file.
"""
import os
import time
import datetime


def _utcnow_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _gps_iso(gps):
    """GPS date (ddmmyy, from RMC) + UTC time (hhmmss.sss) -> ISO 8601, or None.
    The Pi Zero has no RTC, so with no network its clock can be wrong; the GPS
    clock is always right once it has a fix."""
    d, t = gps.get("date"), gps.get("utc")
    if not d or not t or len(d) != 6 or len(t) < 6:
        return None
    return f"20{d[4:6]}-{d[2:4]}-{d[0:2]}T{t[0:2]}:{t[2:4]}:{t[4:6]}Z"


class DualLogger:
    def __init__(self, logdir, min_interval=1.0):
        self.logdir = logdir
        self.min_interval = min_interval          # seconds between logged points
        self.running = False
        self.points = 0
        self.started_at = None
        self._csv = None
        self._gpx = None
        self._csv_path = None
        self._gpx_path = None
        self._last_t = 0.0
        os.makedirs(logdir, exist_ok=True)

    # ---- control ---------------------------------------------------
    def start(self):
        if self.running:
            return
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self._csv_path = os.path.join(self.logdir, f"track_{stamp}.csv")
        self._gpx_path = os.path.join(self.logdir, f"track_{stamp}.gpx")
        self._csv = open(self._csv_path, "w", buffering=1)  # line-buffered
        self._csv.write("utc,lat,lon,alt_m,speed_kmh,sats\n")
        self._gpx = open(self._gpx_path, "w", buffering=1)
        self._gpx.write(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<gpx version="1.1" creator="pitft-gpslog" '
            'xmlns="http://www.topografix.com/GPX/1/1">\n'
            f'<trk><name>track_{stamp}</name><trkseg>\n')
        self.points = 0
        self.started_at = time.time()
        self.running = True

    def log_fix(self, gps):
        """Append one fix if running, has a valid position, and enough time has
        passed since the last logged point."""
        if not self.running:
            return
        if (gps.get("fix", 0) or 0) < 1 or gps.get("lat") is None or gps.get("lon") is None:
            return
        now = time.time()
        if now - self._last_t < self.min_interval:
            return
        self._last_t = now

        t = _gps_iso(gps) or _utcnow_iso()   # prefer GPS time; Pi clock fallback
        lat = gps["lat"]; lon = gps["lon"]
        alt = gps.get("alt")
        spd = (gps.get("speed_kn") or 0.0) * 1.852
        sats = gps.get("sats", 0)

        self._csv.write(f"{t},{lat:.6f},{lon:.6f},"
                        f"{'' if alt is None else f'{alt:.1f}'},{spd:.1f},{sats}\n")
        ele = f"<ele>{alt:.1f}</ele>" if alt is not None else ""
        self._gpx.write(f'<trkpt lat="{lat:.6f}" lon="{lon:.6f}">{ele}'
                        f'<time>{t}</time></trkpt>\n')
        self.points += 1

    def stop(self):
        if not self.running:
            return
        try:
            self._gpx.write("</trkseg></trk>\n</gpx>\n")
        except Exception:
            pass
        for f in (self._csv, self._gpx):
            try:
                f.close()
            except Exception:
                pass
        self._csv = self._gpx = None
        self.running = False

    # ---- read-back -------------------------------------------------
    def list_logs(self, limit=6):
        """Return [(name, points, kb)] for recent CSV logs, newest first."""
        out = []
        for name in sorted(os.listdir(self.logdir), reverse=True):
            if not name.endswith(".csv"):
                continue
            path = os.path.join(self.logdir, name)
            try:
                with open(path) as fh:
                    n = max(0, sum(1 for _ in fh) - 1)  # minus header
                kb = os.path.getsize(path) / 1024.0
                out.append((name, n, kb))
            except Exception:
                continue
            if len(out) >= limit:
                break
        return out
