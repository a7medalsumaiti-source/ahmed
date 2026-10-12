#!/usr/bin/env python3
"""Render the branded Alfaytri promo graphics (Changa font, #F7901E / #414042, official logo).

Outputs (in ../exports):
  end_card.mp4 / end_card.png         3 s animated brand card + still (Scene 5)
  overlays/*.png                      transparent 1080x1920 caption overlays to place over the footage
  alfaytri_ac_promo_animatic.mp4      30 s timing animatic with the final text styling

Usage: python3 build_branded.py        (needs Pillow and ffmpeg)
"""
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
BRAND = ROOT / "brand"
OUT = ROOT / "exports"
W, H, FPS = 1080, 1920, 30

ORANGE = (247, 144, 30)   # style sheet: F7901E
GREY = (65, 64, 66)       # style sheet: 414042
WHITE = (255, 255, 255)


def font(weight, size):
    return ImageFont.truetype(str(BRAND / "fonts" / f"Changa-latin-{weight}.ttf"), size)


def ease(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def fade(t, t_in, t_out, dur_in=0.3, dur_out=0.2):
    """Opacity 0..1 and a 0..1 slide-up progress for an element visible from t_in to t_out."""
    if t < t_in or t > t_out:
        return 0.0, 0.0
    a = ease((t - t_in) / dur_in)
    if t_out - t < dur_out:
        a *= max(0.0, (t_out - t) / dur_out)
    return a, ease((t - t_in) / dur_in)


# ---------- caption overlays ----------

def caption_card(lines, size=78):
    """Dark-grey rounded card, orange accent bar, white Changa SemiBold text (centred)."""
    f = font(600, size)
    pad_x, pad_y, gap, bar = 56, 34, int(size * 0.18), 14
    sizes = [f.getbbox(l) for l in lines]
    tw = max(b[2] - b[0] for b in sizes)
    lh = size + gap
    cw, ch = tw + 2 * pad_x + bar, lh * len(lines) - gap + 2 * pad_y + 10
    img = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, cw - 1, ch - 1), radius=26, fill=GREY + (230,))
    d.rounded_rectangle((0, 0, bar + 26, ch - 1), radius=26, fill=ORANGE + (255,))
    d.rectangle((bar, 0, bar + 26, ch - 1), fill=GREY + (230,))
    for i, l in enumerate(lines):
        lw = f.getbbox(l)[2] - f.getbbox(l)[0]
        d.text((bar + pad_x + (tw - lw) / 2, pad_y + i * lh - sizes[i][1] + 4), l, font=f, fill=WHITE)
    return img


def centred(img, cy):
    return ((W - img.width) // 2, int(cy - img.height / 2))


CAPTIONS = [  # (name, start, end, image, centre-y)
    ("s1_warm_air", 0.8, 7.0, caption_card(["AC blowing warm air?"]), 1300),
    ("s2_call", 7.3, 11.0, caption_card(["Call Alfaytri."]), 1300),
    ("s3_1_inspection", 11.5, 23.0, caption_card(["Professional inspection."], 70), 1230),
    ("s3_2_maintenance", 16.5, 23.0, caption_card(["Expert maintenance."], 70), 1390),
    ("s4_comfort", 23.3, 27.0, caption_card(["Back to comfort."]), 1300),
]
CAPTIONS = [(n, a, b, img, centred(img, cy)) for n, a, b, img, cy in CAPTIONS]


def paste(frame, img, pos, alpha, slide=1.0, dy=40):
    if alpha <= 0:
        return
    if alpha < 1:
        img = img.copy()
        img.putalpha(img.getchannel("A").point(lambda v: int(v * alpha)))
    frame.alpha_composite(img, (pos[0], int(pos[1] + (1 - slide) * dy)))


def draw_captions(frame, t):
    for _, a, b, img, pos in CAPTIONS:
        al, sl = fade(t, a, b)
        paste(frame, img, pos, al, sl)


# ---------- end card (Scene 5) ----------

LOGO = Image.open(BRAND / "logo" / "logo_main.png")
LOGO = LOGO.resize((400, int(LOGO.height * 400 / LOGO.width)), Image.LANCZOS)


def text_img(s, weight, size, color):
    f = font(weight, size)
    b = f.getbbox(s)
    img = Image.new("RGBA", (b[2] - b[0] + 4, b[3] - b[1] + 8), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((2 - b[0], 4 - b[1]), s, font=f, fill=color)
    return img


def pill(s):
    t = text_img(s, 700, 58, WHITE)
    img = Image.new("RGBA", (t.width + 120, 120), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle((0, 0, img.width - 1, 119), radius=60, fill=ORANGE + (255,))
    img.alpha_composite(t, ((img.width - t.width) // 2, (120 - t.height) // 2))
    return img


END_ITEMS = [  # (appear at, image, centre-y)
    (0.0, LOGO, 300 + LOGO.height // 2),
    (0.25, text_img("Alfaytri Maintenance Company", 600, 62, GREY), 1110),
    (0.5, text_img("“Keep your cool this summer.”", 400, 60, ORANGE), 1205),
    (0.75, text_img("Book your AC maintenance today.", 700, 58, GREY), 1300),
    (1.0, pill("[Phone / WhatsApp]"), 1450),  # placeholder: replace with the real number
]


def end_card(t):
    """t is seconds since the card started."""
    frame = Image.new("RGBA", (W, H), WHITE + (255,))
    d = ImageDraw.Draw(frame)
    # orange top and bottom bands in the style sheet's two colours
    d.rectangle((0, 0, W, 22), fill=ORANGE)
    d.rectangle((0, H - 22, W, H), fill=GREY)
    # thin orange divider grows under the logo
    grow = ease((t - 0.2) / 0.4)
    if grow > 0:
        half = int(180 * grow)
        d.rounded_rectangle((W // 2 - half, 1040, W // 2 + half, 1048), radius=4, fill=ORANGE)
    for t_in, img, cy in END_ITEMS:
        al, sl = fade(t, t_in, 99, dur_in=0.4)
        paste(frame, img, centred(img, cy), al, sl, dy=30)
    return frame


# ---------- animatic plates ----------

SCENES = [  # start, end, plate colour, label, description lines
    (0, 7, (200, 116, 46), "SCENE 1 · UNCOMFORTABLE AT HOME · 0–7s",
     ["Sweating · fanning · presses remote", "warm air from AC · dusty filters"]),
    (7, 11, (185, 138, 78), "SCENE 2 · CALLING ALFAYTRI · 7–11s", ["Phone call · technician at the door", "resident points to the AC"]),
    (11, 23, (107, 118, 128), "SCENE 3 · INSPECTION & REPAIR · 11–23s",
     ["Temp check · isolate power · protect", "filters · coil bag · drain · outdoor gauges · test"]),
    (23, 27, (46, 143, 163), "SCENE 4 · RELIEF & COMFORT · 23–27s",
     ["Cool airflow · smile · puts fan down", "thankful nod to technician"]),
]
PLATE_TEXT = {s[3]: [text_img(s[3], 600, 40, WHITE + (220,))] + [text_img(l, 400, 38, WHITE + (180,)) for l in s[4]]
              for s in SCENES}
PLACEHOLDER = text_img("[ footage placeholder — see STORYBOARD.md ]", 400, 32, WHITE + (150,))


def animatic_frame(t):
    if t >= 27:
        return end_card(t - 27)
    s = next(s for s in SCENES if s[0] <= t < s[1])
    frame = Image.new("RGBA", (W, H), s[2] + (255,))
    y = 300
    for img in PLATE_TEXT[s[3]]:
        frame.alpha_composite(img, ((W - img.width) // 2, y))
        y += img.height + 18
    frame.alpha_composite(PLACEHOLDER, ((W - PLACEHOLDER.width) // 2, 820))
    draw_captions(frame, t)
    return frame


def encode(path, n_frames, render, audio=True):
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-"]
    if audio:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-shortest", "-c:a", "aac", "-b:a", "64k"]
    cmd += ["-c:v", "libx264", "-crf", "20", "-preset", "medium", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(path)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(n_frames):
        p.stdin.write(render(i / FPS).convert("RGB").tobytes())
    p.stdin.close()
    if p.wait():
        raise SystemExit("ffmpeg failed")


def main():
    (OUT / "overlays").mkdir(parents=True, exist_ok=True)
    # Transparent full-frame caption overlays for the editor
    for old in (OUT / "overlays").glob("*.png"):
        old.unlink()
    for name, _, _, img, pos in CAPTIONS:
        o = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        o.alpha_composite(img, pos)
        o.save(OUT / "overlays" / f"{name}.png")
    end_card(5).convert("RGB").save(OUT / "end_card.png")
    encode(OUT / "end_card.mp4", 3 * FPS, end_card)
    encode(OUT / "alfaytri_ac_promo_animatic.mp4", 30 * FPS, animatic_frame)
    print("Wrote", *sorted(p.relative_to(ROOT) for p in OUT.rglob("*.*")), sep="\n  ")


if __name__ == "__main__":
    main()
