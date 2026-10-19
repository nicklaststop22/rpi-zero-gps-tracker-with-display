"""Renders the 320x240 UI as a PIL image: GPS readout, logging status, and the
four physical-button labels (START / STOP / READ / STAY-AWAKE)."""
from PIL import Image, ImageDraw, ImageFont

W, H = 320, 240
BG = (0, 0, 0)
FG = (235, 235, 235)
DIM = (120, 120, 120)
GOOD = (60, 210, 90)
WARN = (235, 180, 40)
BAD = (230, 70, 70)
ACCENT = (70, 140, 235)

# Four buttons down the RIGHT edge (landscape, rotate=90), top->bottom. The
# label doubles as the action key in app.py, so order == physical order.
BUTTON_ROWS = [(17, "START"), (22, "STOP"), (23, "READ"), (24, "AWAKE")]
BTN_W = 90


def _font(size, bold=False):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans%s.ttf" % ("-Bold" if bold else ""),
              "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


F_H = _font(22, bold=True)
F_LBL = _font(15)
F_VAL = _font(20, bold=True)
F_BTN = _font(15, bold=True)
F_SM = _font(12)


def _fmt(v, nd=5, suffix=""):
    return f"{v:.{nd}f}{suffix}" if isinstance(v, (int, float)) else "--"


def _buttons(d, stay_awake):
    x0 = W - BTN_W
    rh = H // len(BUTTON_ROWS)
    for i, (gpio, label) in enumerate(BUTTON_ROWS):
        y0 = i * rh
        if label == "AWAKE":
            on = stay_awake
            top = "STAY ON" if on else "SLEEP 2m"
            box = GOOD if on else DIM
            d.rectangle([x0, y0, W - 1, y0 + rh - 2], outline=box,
                        fill=(12, 40, 20) if on else None)
            d.text((x0 + 8, y0 + rh // 2 - 14), top, font=F_BTN, fill=FG)
            d.text((x0 + 8, y0 + rh // 2 + 4), f"GPIO{gpio}", font=F_SM, fill=DIM)
        else:
            d.rectangle([x0, y0, W - 1, y0 + rh - 2], outline=ACCENT)
            d.text((x0 + 8, y0 + rh // 2 - 14), label, font=F_BTN, fill=FG)
            d.text((x0 + 8, y0 + rh // 2 + 4), f"GPIO{gpio}", font=F_SM, fill=DIM)


def render(gps, log_state, stay_awake=False, toast=None):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    content_w = W - BTN_W

    fix = gps.get("fix", 0) or 0
    fix_col = GOOD if fix >= 1 else BAD
    fix_txt = {0: "NO FIX", 1: "FIX", 2: "DGPS"}.get(fix, f"FIX{fix}")
    d.text((8, 6), "GPS LOGGER", font=F_H, fill=FG)
    d.text((8, 32), fix_txt, font=F_LBL, fill=fix_col)
    d.text((70, 32), f"{gps.get('sats', 0)} sats", font=F_LBL, fill=DIM)

    rows = [
        ("LAT", _fmt(gps.get("lat"), 6)),
        ("LON", _fmt(gps.get("lon"), 6)),
        ("ALT", _fmt(gps.get("alt"), 1, " m")),
        ("SPD", _fmt((gps.get("speed_kn") or 0) * 1.852, 1, " km/h")
                if gps.get("speed_kn") is not None else "--"),
        ("UTC", gps.get("utc") or "--"),
    ]
    y = 58
    for lbl, val in rows:
        d.text((8, y), lbl, font=F_LBL, fill=DIM)
        d.text((52, y - 2), val, font=F_VAL, fill=FG)
        y += 28

    d.rectangle([4, 202, content_w - 4, 234], outline=DIM)
    state_col = {"RUNNING": GOOD, "READING": ACCENT, "STOPPED": DIM}.get(log_state, WARN)
    d.text((10, 208), "LOG:", font=F_LBL, fill=DIM)
    d.text((48, 206), toast or log_state, font=F_VAL, fill=state_col)

    _buttons(d, stay_awake)
    return img


def render_logs(logs, stay_awake=False):
    """READ view: a list of recent logs (name, point count, size)."""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.text((8, 6), "LOGGED TRACKS", font=F_H, fill=FG)
    if not logs:
        d.text((8, 50), "No logs yet.", font=F_VAL, fill=DIM)
    else:
        y = 44
        for name, pts, kb in logs:
            d.text((8, y), name.replace("track_", "").replace(".csv", ""),
                   font=F_LBL, fill=FG)
            d.text((150, y), f"{pts} pts", font=F_LBL, fill=ACCENT)
            d.text((220, y), f"{kb:.0f} KB", font=F_LBL, fill=DIM)
            y += 26
    _buttons(d, stay_awake)
    return img
