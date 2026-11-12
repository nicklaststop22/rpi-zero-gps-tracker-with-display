"""Renders the 250x122 black/white e-ink screen as a PIL image.

Nothing on it ticks every second (no seconds in the clock), so the picture only
changes when something real changes and the panel isn't refreshed needlessly.
"""
from PIL import Image, ImageDraw, ImageFont

W, H = 250, 122
BLACK, WHITE = 0, 255


def _font(size, bold=False):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans%s.ttf" % ("-Bold" if bold else ""),
              "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


F_BIG = _font(18, bold=True)
F_MID = _font(14, bold=True)
F_SM = _font(11)


def _dur(secs):
    secs = int(secs)
    return f"{secs // 3600}:{secs % 3600 // 60:02d}"


# Only this many pixels from the left are drawn on. The right side of this
# particular panel is damaged; set to W for a healthy one.
USE_W = 110

F_UI = _font(16, bold=True)
F_XS = _font(12)


def render(gps, logging, points=0, elapsed=0, toast=None):
    img = Image.new("1", (W, H), WHITE)
    if USE_W >= W:
        return _render_wide(img, gps, logging, points, elapsed, toast)
    d = ImageDraw.Draw(img)
    fix = (gps.get("fix", 0) or 0) >= 1
    utc = gps.get("utc") or ""

    d.rectangle([0, 0, USE_W - 1, 15], fill=BLACK)
    d.text((3, 1), f"{'FIX' if fix else 'NO FIX'} {gps.get('sats', 0) or 0}sat",
           font=F_XS, fill=WHITE)

    lat, lon = gps.get("lat"), gps.get("lon")
    if fix and lat is not None and lon is not None:
        d.text((3, 18), f"{lat:.5f}", font=F_MID, fill=BLACK)
        d.text((3, 35), f"{lon:.5f}", font=F_MID, fill=BLACK)
        mph = (gps.get("speed_kn") or 0) * 1.852 * 0.621371
        d.text((3, 52), f"{mph:.0f} mph", font=F_MID, fill=BLACK)
    else:
        d.text((3, 24), "searching", font=F_MID, fill=BLACK)
        d.text((3, 42), "for sats...", font=F_MID, fill=BLACK)

    d.line([0, 70, USE_W - 1, 70], fill=BLACK)
    if toast:
        d.text((3, 76), toast.split(" ")[0], font=F_UI, fill=BLACK)
    elif logging:
        d.text((3, 74), "LOGGING", font=F_UI, fill=BLACK)
        d.text((3, 94), f"{points} pts {_dur(elapsed)}", font=F_XS, fill=BLACK)
    else:
        d.text((3, 74), "STOPPED", font=F_UI, fill=BLACK)
        d.text((3, 94), "tap = start", font=F_XS, fill=BLACK)
    if len(utc) >= 4:
        d.text((3, 108), f"UTC {utc[0:2]}:{utc[2:4]}", font=F_XS, fill=BLACK)
    return img


def _render_wide(img, gps, logging, points, elapsed, toast):
    d = ImageDraw.Draw(img)

    # top bar: fix + sats + UTC hh:mm
    fix = (gps.get("fix", 0) or 0) >= 1
    utc = gps.get("utc") or ""
    d.rectangle([0, 0, W - 1, 17], fill=BLACK)
    d.text((4, 2), "FIX" if fix else "NO FIX", font=F_MID, fill=WHITE)
    d.text((70, 3), f"{gps.get('sats', 0) or 0} sats", font=F_SM, fill=WHITE)
    if len(utc) >= 4:
        d.text((W - 72, 3), f"UTC {utc[0:2]}:{utc[2:4]}", font=F_SM, fill=WHITE)

    lat, lon = gps.get("lat"), gps.get("lon")
    if fix and lat is not None and lon is not None:
        d.text((4, 22), f"{lat:.5f}", font=F_BIG, fill=BLACK)
        d.text((4, 44), f"{lon:.5f}", font=F_BIG, fill=BLACK)
        kmh = (gps.get("speed_kn") or 0) * 1.852
        alt = gps.get("alt")
        d.text((150, 24), f"{kmh * 0.621371:.0f} mph", font=F_MID, fill=BLACK)
        if alt is not None:
            d.text((150, 46), f"{alt * 3.28084:.0f} ft", font=F_MID, fill=BLACK)
    else:
        d.text((4, 30), "searching for", font=F_MID, fill=BLACK)
        d.text((4, 48), "satellites...", font=F_MID, fill=BLACK)

    # bottom: logging state, the one thing you check at a glance
    d.line([0, 70, W - 1, 70], fill=BLACK)
    if toast:
        d.text((4, 78), toast, font=F_BIG, fill=BLACK)
    elif logging:
        d.text((4, 76), "● LOGGING", font=F_BIG, fill=BLACK)
        d.text((4, 100), f"{points} pts   {_dur(elapsed)}", font=F_MID, fill=BLACK)
    else:
        d.text((4, 76), "STOPPED", font=F_BIG, fill=BLACK)
        d.text((4, 100), "tap: start   hold 3s: off", font=F_SM, fill=BLACK)
    return img


def render_shutdown(saved_points=None):
    img = Image.new("1", (W, H), WHITE)
    d = ImageDraw.Draw(img)
    d.text((8, 20), "POWERED OFF", font=F_BIG, fill=BLACK)
    if saved_points is not None:
        d.text((8, 50), f"track saved ({saved_points} pts)", font=F_MID, fill=BLACK)
    d.text((8, 80), "safe to unplug once the", font=F_SM, fill=BLACK)
    d.text((8, 94), "green light stops blinking", font=F_SM, fill=BLACK)
    return img
