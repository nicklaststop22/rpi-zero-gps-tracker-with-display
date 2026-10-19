#!/usr/bin/env python3
"""Turn raw gpslog CSV tracks into map-ready files.

For each raw/track_*.csv with real points, writes next to this script:
  <name>.gpx  - clean, properly closed GPX rebuilt from the CSV (the Pi's own
                GPX can end in NUL bytes / missing tags after a power cut)
  <name>.kml  - simplified line + start/end pins, for Google My Maps / Earth
and prints drive stats. Standard library only.

Usage:  python convert_tracks.py [tolerance_m]   (default 5 m)
"""
import csv
import math
import os
import sys
from datetime import datetime
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw")
R_EARTH = 6371000.0
GAP_SECS = 60          # a jump in time bigger than this counts as signal loss
MOVING_KMH = 3.0       # below this we call it stopped (GPS jitter at rest)


def haversine(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * R_EARTH * math.asin(math.sqrt(h))


def load(path):
    with open(path, "rb") as fh:
        text = fh.read().replace(b"\x00", b"").decode("utf-8", "replace")
    pts = []
    for row in csv.DictReader(text.splitlines()):
        try:
            pts.append({
                "t": datetime.strptime(row["utc"], "%Y-%m-%dT%H:%M:%SZ"),
                "lat": float(row["lat"]), "lon": float(row["lon"]),
                "alt": float(row["alt_m"]) if row["alt_m"] else None,
                "kmh": float(row["speed_kmh"] or 0), "sats": int(row["sats"] or 0),
            })
        except (KeyError, ValueError, TypeError):
            continue  # skip a partial row from a power cut
    return pts


def rdp(coords, tol_m):
    """Iterative Ramer-Douglas-Peucker on (lat, lon); returns kept indices."""
    if len(coords) < 3:
        return list(range(len(coords)))
    lat0 = math.radians(sum(c[0] for c in coords) / len(coords))
    xy = [(math.radians(c[1]) * math.cos(lat0) * R_EARTH, math.radians(c[0]) * R_EARTH) for c in coords]
    keep = [False] * len(xy)
    keep[0] = keep[-1] = True
    stack = [(0, len(xy) - 1)]
    while stack:
        s, e = stack.pop()
        (x1, y1), (x2, y2) = xy[s], xy[e]
        dx, dy = x2 - x1, y2 - y1
        seg = math.hypot(dx, dy)
        best, idx = -1.0, -1
        for i in range(s + 1, e):
            px, py = xy[i]
            d = (abs(dy * px - dx * py + x2 * y1 - y2 * x1) / seg) if seg else math.hypot(px - x1, py - y1)
            if d > best:
                best, idx = d, i
        if best > tol_m:
            keep[idx] = True
            stack += [(s, idx), (idx, e)]
    return [i for i, k in enumerate(keep) if k]


def stats(pts, simplified):
    dist = sum(haversine((simplified[i]["lat"], simplified[i]["lon"]),
                         (simplified[i + 1]["lat"], simplified[i + 1]["lon"]))
               for i in range(len(simplified) - 1))
    moving = gaps = 0
    for a, b in zip(pts, pts[1:]):
        dt = (b["t"] - a["t"]).total_seconds()
        if dt > GAP_SECS:
            gaps += 1
        elif b["kmh"] >= MOVING_KMH:
            moving += dt
    speeds = sorted(p["kmh"] for p in pts)
    p99 = speeds[int(len(speeds) * 0.99) - 1] if speeds else 0
    return {"dist_km": dist / 1000, "duration": pts[-1]["t"] - pts[0]["t"],
            "moving_s": moving, "max_kmh": speeds[-1] if speeds else 0, "p99_kmh": p99, "gaps": gaps}


def write_gpx(path, name, pts):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<gpx version="1.1" creator="pitft-gpslog" xmlns="http://www.topografix.com/GPX/1/1">\n'
                f"<trk><name>{escape(name)}</name><trkseg>\n")
        for p in pts:
            ele = f"<ele>{p['alt']:.1f}</ele>" if p["alt"] is not None else ""
            f.write(f'<trkpt lat="{p["lat"]:.6f}" lon="{p["lon"]:.6f}">{ele}'
                    f'<time>{p["t"]:%Y-%m-%dT%H:%M:%SZ}</time></trkpt>\n')
        f.write("</trkseg></trk>\n</gpx>\n")


def write_kml(path, name, simplified, st):
    coords = " ".join(f"{p['lon']:.6f},{p['lat']:.6f}" for p in simplified)
    s, e = simplified[0], simplified[-1]
    desc = (f"{st['dist_km']:.1f} km, {st['duration']}, "
            f"moving {st['moving_s'] / 3600:.1f} h, top speed ~{st['p99_kmh']:.0f} km/h")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>{escape(name)}</name>
<Style id="route"><LineStyle><color>ff0000ff</color><width>4</width></LineStyle></Style>
<Placemark><name>Route</name><description>{escape(desc)}</description><styleUrl>#route</styleUrl>
<LineString><tessellate>1</tessellate><coordinates>{coords}</coordinates></LineString></Placemark>
<Placemark><name>Start {s['t']:%H:%M} UTC</name><Point><coordinates>{s['lon']:.6f},{s['lat']:.6f}</coordinates></Point></Placemark>
<Placemark><name>End {e['t']:%H:%M} UTC</name><Point><coordinates>{e['lon']:.6f},{e['lat']:.6f}</coordinates></Point></Placemark>
</Document></kml>
""")


def main():
    tol = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
    for fn in sorted(os.listdir(RAW)):
        if not fn.endswith(".csv"):
            continue
        pts = load(os.path.join(RAW, fn))
        if len(pts) < 2:
            print(f"{fn}: {len(pts)} points - skipped")
            continue
        name = fn[:-4]
        keep = rdp([(p["lat"], p["lon"]) for p in pts], tol)
        simp = [pts[i] for i in keep]
        st = stats(pts, simp)
        write_gpx(os.path.join(HERE, name + ".gpx"), name, pts)
        write_kml(os.path.join(HERE, name + ".kml"), name, simp, st)
        print(f"{fn}: {len(pts)} pts -> {len(simp)} in KML (tol {tol:g} m) | "
              f"{st['dist_km']:.1f} km | span {st['duration']} | moving {st['moving_s'] / 3600:.2f} h | "
              f"max {st['max_kmh']:.0f} km/h (99th pct {st['p99_kmh']:.0f}) | gaps>{GAP_SECS}s: {st['gaps']}")


if __name__ == "__main__":
    main()
