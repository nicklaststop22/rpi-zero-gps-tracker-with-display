"""Background serial reader for a UART NMEA GPS on /dev/serial0.

Owns the serial port directly (pyserial) so the app can BOTH read NMEA for the
live display AND write vendor logging commands. Parses the common GGA + RMC
sentences into a thread-safe snapshot dict.
"""
import threading
import time
import serial


def nmea_checksum(body: str) -> str:
    """XOR checksum of everything between '$' and '*'. Returns 2 hex chars."""
    cs = 0
    for ch in body:
        cs ^= ord(ch)
    return f"{cs:02X}"


def build_sentence(body: str) -> bytes:
    """body e.g. 'PMTK185,0' -> b'$PMTK185,0*<cs>\\r\\n'."""
    return f"${body}*{nmea_checksum(body)}\r\n".encode("ascii")


def _dm_to_deg(dm: str, hemi: str):
    """NMEA ddmm.mmmm + hemisphere -> signed decimal degrees."""
    if not dm:
        return None
    dot = dm.find(".")
    deg_len = dot - 2  # minutes are always 2 digits left of the dot
    deg = float(dm[:deg_len])
    minutes = float(dm[deg_len:])
    val = deg + minutes / 60.0
    if hemi in ("S", "W"):
        val = -val
    return val


class GPSReader(threading.Thread):
    def __init__(self, port="/dev/serial0", baud=9600):
        super().__init__(daemon=True)
        self.port = port
        self.baud = baud
        self._ser = None
        self._stop = False
        self._wlock = threading.Lock()
        self._dlock = threading.Lock()
        self.data = {
            "fix": 0, "lat": None, "lon": None, "alt": None,
            "sats": 0, "speed_kn": None, "utc": None, "date": None,
            "last_rx": 0.0,
        }
        self.last_raw = ""  # most recent raw line, handy for a debug view

    # ---- lifecycle -------------------------------------------------
    def _open(self):
        self._ser = serial.Serial(self.port, self.baud, timeout=1)

    def run(self):
        while not self._stop:
            try:
                if self._ser is None:
                    self._open()
                raw = self._ser.readline().decode("ascii", "replace").strip()
                if raw:
                    self.last_raw = raw
                if raw.startswith("$"):
                    self._parse(raw)
            except Exception:
                time.sleep(1.0)
                try:
                    if self._ser:
                        self._ser.close()
                except Exception:
                    pass
                self._ser = None

    def stop(self):
        self._stop = True

    # ---- writing vendor commands -----------------------------------
    def send(self, body: str) -> bytes:
        """Send a '$...*cs' sentence from a bare body like 'PMTK185,0'."""
        pkt = build_sentence(body)
        with self._wlock:
            if self._ser is not None:
                self._ser.write(pkt)
                self._ser.flush()
        return pkt

    def snapshot(self):
        with self._dlock:
            return dict(self.data)

    # ---- parsing ---------------------------------------------------
    def _parse(self, line):
        parts = line.split("*")[0].split(",")
        talker = parts[0][3:] if len(parts[0]) >= 6 else parts[0][1:]
        try:
            if talker == "GGA" and len(parts) >= 10:
                upd = {
                    "utc": parts[1] or None,
                    "lat": _dm_to_deg(parts[2], parts[3]),
                    "lon": _dm_to_deg(parts[4], parts[5]),
                    "fix": int(parts[6] or 0),
                    "sats": int(parts[7] or 0),
                    "alt": float(parts[9]) if parts[9] else None,
                    "last_rx": time.time(),
                }
                with self._dlock:
                    self.data.update(upd)
            elif talker == "RMC" and len(parts) >= 10:
                upd = {
                    "utc": parts[1] or None,
                    "speed_kn": float(parts[7]) if parts[7] else None,
                    "date": parts[9] or None,  # ddmmyy - only RMC carries the date
                    "last_rx": time.time(),
                }
                if parts[2] == "A":  # valid fix flag
                    upd["lat"] = _dm_to_deg(parts[3], parts[4])
                    upd["lon"] = _dm_to_deg(parts[5], parts[6])
                with self._dlock:
                    self.data.update(upd)
        except (ValueError, IndexError):
            pass  # a malformed/partial sentence - just skip it
