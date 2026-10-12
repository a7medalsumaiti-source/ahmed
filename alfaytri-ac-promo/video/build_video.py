#!/usr/bin/env python3
"""Render the finished 30 s Alfaytri promo as a flat-illustrated 2D animation (9:16, 1080x1920).

Follows STORYBOARD.md shot by shot, reuses the brand captions and end card from
animatic/build_branded.py, and adds a synthesized music bed and sound effects.

Output: ../exports/alfaytri_ac_promo_30s.mp4
Usage:  python3 build_video.py      (needs Pillow, numpy and ffmpeg)
"""
import math
import subprocess
import sys
import wave
from functools import lru_cache
from multiprocessing import Pool
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "animatic"))
import build_branded as bb  # noqa: E402

W, H, FPS, DUR = bb.W, bb.H, bb.FPS, 30
S = 2  # supersampling factor (drawn at 2x, downscaled for smooth edges)
ORANGE, GREY, WHITE = bb.ORANGE, bb.GREY, bb.WHITE
OUT = HERE.parent / "exports"

SKIN_R, SKIN_T, HAIR = (196, 148, 108), (176, 126, 90), (32, 27, 25)
GLOVE = (80, 140, 230)
RNG = np.random.default_rng(7)
DUST = RNG.random((520, 3))
SPECK = RNG.random((60, 3))


# ---------- helpers ----------

def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def lerp(a, b, t):
    return a + (b - a) * t


def lerpc(c1, c2, t):
    return tuple(int(lerp(a, b, t)) for a, b in zip(c1, c2))


def smooth(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


ease = bb.ease


@lru_cache(maxsize=None)
def font(weight, size):
    return bb.font(weight, size)


ROOM_VIEW = (1.25, -47)  # wide room shots: fill the frame, floor line just above the captions


class Cv:
    """Drawing surface in 1080x1920 design coordinates, rendered at S x resolution."""

    def __init__(self, bg, k=1.0, dy=0.0):
        """k scales the shot about the vertical centre line, dy moves it down (framing per shot)."""
        self.im = Image.new("RGB", (W * S, H * S), bg)
        self.d = ImageDraw.Draw(self.im, "RGBA")
        self.k, self.dy = k, dy

    def _p(self, x, y):
        return ((540 + (x - 540) * self.k) * S, (y * self.k + self.dy) * S)

    def _b(self, x0, y0, x1, y1):
        return (*self._p(x0, y0), *self._p(x1, y1))

    def _l(self, v):
        return v * self.k * S

    def rect(self, x0, y0, x1, y1, fill, r=0, outline=None, w=0):
        if r:
            self.d.rounded_rectangle(self._b(x0, y0, x1, y1), radius=self._l(r), fill=fill, outline=outline, width=int(self._l(w)))
        else:
            self.d.rectangle(self._b(x0, y0, x1, y1), fill=fill, outline=outline, width=int(self._l(w)))

    def ell(self, cx, cy, rx, ry=None, fill=None, outline=None, w=0):
        ry = rx if ry is None else ry
        self.d.ellipse(self._b(cx - rx, cy - ry, cx + rx, cy + ry), fill=fill, outline=outline, width=int(self._l(w)))

    def poly(self, pts, fill, outline=None):
        self.d.polygon([self._p(x, y) for x, y in pts], fill=fill, outline=outline)

    def line(self, pts, fill, w, caps=True):
        self.d.line([self._p(x, y) for x, y in pts], fill=fill, width=max(1, int(self._l(w))), joint="curve")
        if caps:
            for x, y in (pts[0], pts[-1]):
                self.ell(x, y, w / 2, fill=fill)

    def arc(self, cx, cy, rx, ry, a0, a1, fill, w):
        self.d.arc(self._b(cx - rx, cy - ry, cx + rx, cy + ry), a0, a1, fill=fill, width=max(1, int(self._l(w))))

    def chord(self, cx, cy, rx, ry, a0, a1, fill):
        self.d.chord(self._b(cx - rx, cy - ry, cx + rx, cy + ry), a0, a1, fill=fill)

    def text(self, x, y, s, size, fill, weight=700, anchor="mm"):
        self.d.text(self._p(x, y), s, font=font(weight, int(self._l(size))), fill=fill, anchor=anchor)

    def blur(self, r):
        self.im = self.im.filter(ImageFilter.GaussianBlur(r * S))
        self.d = ImageDraw.Draw(self.im, "RGBA")

    def done(self):
        return self.im.resize((W, H), Image.LANCZOS)


# ---------- props ----------

def draw_ac(c, cx, cy, sc=1.0, temp=None, louvre=1.0, dust=0.0, front=True, display=True):
    w, h = 460 * sc, 125 * sc
    x0, y0 = cx - w / 2, cy - h / 2
    c.rect(x0 + 6 * sc, y0 + 12 * sc, x0 + w + 6 * sc, y0 + h + 12 * sc, (0, 0, 0, 28), r=22 * sc)
    c.rect(x0, y0, x0 + w, y0 + h, (250, 250, 250), r=22 * sc, outline=(212, 212, 212), w=2 * sc)
    if front:
        c.rect(x0 + 12 * sc, y0 + 12 * sc, x0 + w - 12 * sc, y0 + 64 * sc, (243, 243, 243), r=12 * sc)
    # outlet and louvre
    c.rect(x0 + 20 * sc, y0 + h - 36 * sc, x0 + w - 20 * sc, y0 + h - 10 * sc, (58, 60, 64), r=10 * sc)
    ly = y0 + h - 36 * sc + lerp(2, 16, louvre) * sc
    c.rect(x0 + 24 * sc, ly, x0 + w - 24 * sc, ly + lerp(22, 7, louvre) * sc, (232, 232, 232), r=4 * sc)
    if dust > 0:
        for u, v, r in DUST[:140]:
            c.ell(x0 + 24 * sc + u * (w - 48 * sc), y0 + h - 40 * sc + v * 10 * sc, (1 + r * 2.5) * sc,
                  fill=(128, 120, 110, int(150 * dust)))
    if display and temp is not None:
        c.text(x0 + w - 62 * sc, y0 + 40 * sc, temp, 24 * sc, (45, 140, 255), weight=600)
    c.ell(x0 + w - 100 * sc, y0 + 40 * sc, 4 * sc, fill=(45, 140, 255) if display else (190, 190, 190))
    return x0, y0, w, h


def filter_mesh(c, x0, y0, x1, y1, dust_alpha):
    """dust_alpha(x, y) -> 0..255 for each dust speck."""
    c.rect(x0, y0, x1, y1, (236, 236, 234), r=10, outline=(200, 200, 198), w=4)
    step = 16
    for x in np.arange(x0 + step, x1, step):
        c.line([(x, y0 + 4), (x, y1 - 4)], (205, 205, 202), 2, caps=False)
    for y in np.arange(y0 + step, y1, step):
        c.line([(x0 + 4, y), (x1 - 4, y)], (205, 205, 202), 2, caps=False)
    for u, v, r in DUST:
        x, y = x0 + 8 + u * (x1 - x0 - 16), y0 + 8 + v * (y1 - y0 - 16)
        a = dust_alpha(x, y)
        if a > 2:
            c.ell(x, y, 3 + r * 6, fill=(132, 124, 112, int(a)))


def airflow(c, cx, y0, width, T, cool, strength=1.0):
    n = 7
    length = (420 if cool else 230) * strength
    for i in range(n):
        xb = cx - width / 2 + width * (i + 0.5) / n
        pts = []
        for k in range(16):
            dy = k * length / 15
            spread = dy * 0.25 * (i - (n - 1) / 2) / n
            pts.append((xb + spread + 12 * math.sin(dy / 45 - T * (6 if cool else 2.5) + i), y0 + dy))
        col = (150, 205, 255, int(120 * strength)) if cool else (255, 150, 60, int(85 * strength))
        c.line(pts, col, 6, caps=False)
    if cool:
        for j, (u, v, r) in enumerate(SPECK[:30]):
            ph = (T * 0.55 + v) % 1
            x = cx + (u - 0.5) * width * (1 + ph)
            c.ell(x, y0 + ph * length, 3 + r * 4, fill=(225, 242, 255, int(200 * (1 - ph) * strength)))


def heat_shimmer(c, x0, y0, x1, y1, T, k=1.0):
    for i in range(5):
        y = y0 + (y1 - y0) * (i + 0.5) / 5
        pts = [(x, y + 6 * math.sin(x / 30 + T * 4 + i)) for x in np.arange(x0, x1 + 1, 15)]
        c.line(pts, (255, 255, 240, int(70 * k)), 4, caps=False)


def item(c, kind, p, sc, T, spin=True):
    x, y = p
    if kind == "fan":
        c.line([(x, y), (x, y - 40 * sc)], (238, 238, 238), 13 * sc)
        cx, cy = x, y - 74 * sc
        c.ell(cx, cy, 36 * sc, fill=(250, 250, 250), outline=(185, 185, 185), w=3 * sc)
        a0 = T * 25 if spin else 0.4
        for k in range(3):
            a = a0 + k * 2.094
            c.line([(cx, cy), (cx + 28 * sc * math.cos(a), cy + 28 * sc * math.sin(a))], (160, 200, 235), 10 * sc)
        c.ell(cx, cy, 6 * sc, fill=(150, 150, 150))
    elif kind == "phone":
        c.rect(x - 14 * sc, y - 34 * sc, x + 14 * sc, y + 22 * sc, (28, 28, 32), r=6 * sc)
    elif kind == "bag":
        c.arc(x, y + 14 * sc, 30 * sc, 22 * sc, 180, 360, (40, 40, 42), 7 * sc)
        c.rect(x - 75 * sc, y + 12 * sc, x + 75 * sc, y + 92 * sc, GREY, r=12 * sc)
        c.rect(x - 75 * sc, y + 34 * sc, x + 75 * sc, y + 44 * sc, ORANGE)


def elbow(a, b, side, off):
    mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy) or 1
    px, py = -dy / L, dx / L
    if px * side < 0:
        px, py = -px, -py
    return mx + px * off, my + py * off


def person(c, x, y, sc, kind, sit=False, lh=None, rh=None, expr=0.0, brow=0.0, sweat=0.0, nod=0.0,
           item_l=None, item_r=None, T=0.0, gloves=False, spin=True):
    """Flat-style figure; (x, y) = feet position, local coordinates point up (negative y)."""
    P = lambda px, py: (x + px * sc, y + py * sc)  # noqa: E731
    hip = -150 if sit else -250
    sh = hip - 190
    hy = sh - 62 + nod * 10
    res = kind == "res"
    skin = SKIN_R if res else SKIN_T
    if res:
        for sx in (-36, 36):
            c.ell(*P(sx, -4), 26 * sc, 10 * sc, fill=(70, 55, 45))
        c.poly([P(-60, sh + 4), P(60, sh + 4), P(86, -12), P(-86, -12)], (246, 246, 243), outline=(205, 205, 200))
        if sit:
            c.line([P(-72, hip + 25), P(72, hip + 25)], (222, 222, 217), 3 * sc, caps=False)
        c.line([P(0, sh + 14), P(0, sh + 100)], (212, 212, 207), 3 * sc, caps=False)
    else:
        tr = (74, 73, 76)
        c.line([P(-24, hip), P(-30, -16)], tr, 46 * sc)
        c.line([P(24, hip), P(30, -16)], tr, 46 * sc)
        for sx in (-36, 36):
            c.ell(*P(sx, -6), 31 * sc, 12 * sc, fill=(105, 105, 108))
        c.poly([P(-60, sh), P(60, sh), P(54, hip + 14), P(-54, hip + 14)], GREY)
        c.rect(*P(-54, hip + 2), *P(54, hip + 16), (44, 43, 45))
        c.poly([P(-60, sh), P(-24, sh), P(-34, sh + 30), P(-62, sh + 38)], ORANGE)
        c.poly([P(60, sh), P(24, sh), P(34, sh + 30), P(62, sh + 38)], ORANGE)
        c.poly([P(-16, sh), P(16, sh), P(0, sh + 26)], ORANGE)
        c.rect(*P(18, sh + 50), *P(42, sh + 68), ORANGE, r=3 * sc)
    c.rect(*P(-14, sh - 24), *P(14, sh + 6), skin)
    # arms
    for side, hand, it in ((-1, lh, item_l), (1, rh, item_r)):
        s_ = P(side * 56, sh + 16)
        if hand is None:
            hand = (side * 72, hip + (30 if sit else 10))
        hp = P(*hand)
        e = elbow(s_, hp, side, 26 * sc)
        if res:
            c.line([s_, e], (246, 246, 243), 32 * sc)
            c.line([e, hp], (246, 246, 243), 28 * sc)
        else:
            cuff = (lerp(s_[0], e[0], 0.75), lerp(s_[1], e[1], 0.75))
            c.line([e, hp], skin, 24 * sc)
            c.line([cuff, e], skin, 26 * sc)
            c.line([s_, cuff], GREY, 32 * sc)
            cb = (lerp(s_[0], e[0], 0.62), lerp(s_[1], e[1], 0.62))
            c.line([cb, cuff], ORANGE, 32 * sc, caps=False)
        c.ell(*hp, 16 * sc, fill=GLOVE if (gloves and not res) else skin)
        if it:
            item(c, it, hp, sc, T, spin)
    # head
    hx, hyy = P(0, hy)
    for side in (-1, 1):
        c.ell(hx + side * 44 * sc, hyy + 6 * sc, 9 * sc, 13 * sc, fill=skin)
    c.ell(hx, hyy - 10 * sc, 47 * sc, 48 * sc if res else 45 * sc, fill=HAIR)
    c.ell(hx, hyy + 4 * sc, 43 * sc, 50 * sc, fill=skin)
    if res:
        c.chord(hx, hyy + 4 * sc, 43 * sc, 50 * sc, 8, 172, (50, 42, 38))
        c.ell(hx, hyy + 31 * sc, 17 * sc, 9 * sc, fill=skin)
        c.rect(hx - 16 * sc, hyy + 19 * sc, hx + 16 * sc, hyy + 24 * sc, (50, 42, 38), r=2 * sc)
    for side in (-1, 1):
        c.ell(hx + side * 16 * sc, hyy - 3 * sc, 5.5 * sc, fill=(35, 30, 28))
        c.line([(hx + side * 7 * sc, hyy - 18 * sc + brow * 7 * sc), (hx + side * 28 * sc, hyy - 21 * sc - brow * 2 * sc)],
               HAIR, 5 * sc)
    mc = (115, 52, 46)
    if expr >= 0.2:
        c.arc(hx, hyy + 27 * sc, 13 * sc, (5 + 7 * expr) * sc, 15, 165, mc, 4 * sc)
    elif expr <= -0.2:
        c.arc(hx, hyy + 37 * sc, 12 * sc, 7 * sc, 200, 340, mc, 4 * sc)
    else:
        c.line([(hx - 9 * sc, hyy + 32 * sc), (hx + 9 * sc, hyy + 32 * sc)], mc, 4 * sc)
    if sweat > 0:
        for side in (-1, 1):
            dy = ((T * 22 + side * 7) % 26) * sc
            sx, sy = hx + side * 36 * sc, hyy - 18 * sc + dy
            col = (110, 185, 255, int(230 * sweat))
            c.ell(sx, sy, 5 * sc, fill=col)
            c.poly([(sx - 5 * sc, sy - 1 * sc), (sx + 5 * sc, sy - 1 * sc), (sx, sy - 12 * sc)], col)
    return P


# ---------- room ----------

def room(c, T, cool=0.0, air=0.0, sheet=0.0, plastic=0.0, ac=None, fan_on_table=False):
    c.rect(0, 0, W, 1150, lerpc((243, 224, 196), (234, 240, 242), cool))
    c.rect(0, 1132, W, 1150, lerpc((224, 200, 168), (214, 222, 226), cool))
    c.rect(0, 1150, W, H, lerpc((212, 182, 146), (204, 192, 178), cool))
    for i in range(1, 9):
        y = 1150 + i * i * 11 + i * 20
        c.line([(0, y), (W, y)], lerpc((196, 165, 128), (190, 178, 164), cool), 3, caps=False)
    c.ell(540, 1330, 480, 115, fill=lerpc((192, 118, 78), (168, 150, 136), cool))
    # window
    c.rect(660, 300, 1010, 880, (250, 250, 248))
    c.rect(680, 320, 990, 860, lerpc((255, 204, 138), (176, 214, 240), cool))
    if cool < 1:
        c.ell(905, 420, 95, fill=(255, 240, 200, int(170 * (1 - cool))))
        c.ell(905, 420, 55, fill=(255, 250, 226))
        heat_shimmer(c, 685, 600, 985, 850, T, 1 - cool)
    c.rect(830, 320, 840, 860, (250, 250, 248))
    c.rect(680, 585, 990, 595, (250, 250, 248))
    for side in (0, 1):
        x_out, x_in = (640, 765) if side == 0 else (1030, 905)
        sway = air * 22 * math.sin(T * 2.2 + side * 1.3)
        pts = [(x_out, 292)]
        for y in range(292, 921, 26):
            k = (y - 292) / 628
            pts.append((x_in + sway * k + (5 + 7 * air) * math.sin(y / 38 + T * (1 + 3 * air)), y))
        pts.append((x_out, 920))
        c.poly(pts, (255, 255, 255, 120))
    c.rect(628, 282, 1042, 293, (120, 108, 96), r=4)
    # sofa
    sofa = lerpc((196, 198, 201), (201, 205, 210), cool)
    dark = lerpc((168, 170, 174), (172, 177, 183), cool)
    c.rect(110, 800, 630, 960, sofa, r=40)
    c.rect(160, 950, 590, 1062, sofa, r=24)
    c.line([(305, 960), (305, 1050)], dark, 4, caps=False)
    c.line([(445, 960), (445, 1050)], dark, 4, caps=False)
    c.rect(88, 900, 182, 1102, dark, r=30)
    c.rect(558, 900, 652, 1102, dark, r=30)
    for lx in (130, 592):
        c.rect(lx, 1100, lx + 18, 1136, (92, 72, 56))
    if sheet > 0:
        top = lerp(560, 785, ease(sheet))
        pts = [(80, top), (660, top)] + [(660 - i * 29, top + 330 + 12 * math.sin(i * 1.3 + T * 4)) for i in range(21)]
        c.poly(pts, (252, 252, 252, int(235 * min(1, sheet * 3))))
    if plastic > 0:
        c.rect(130, 470, 610, 790, (215, 232, 245, int(95 * plastic)))
        for xx in (130, 610):
            c.rect(xx - 6, 470, xx + 6, 790, (240, 200, 120, int(200 * plastic)))
    draw_ac(c, 370, 392, **(ac or {}))
    # coffee table (in front of the sofa)
    c.rect(548, 1052, 902, 1078, (122, 86, 60), r=8)
    for lx in (566, 868):
        c.rect(lx, 1078, lx + 16, 1166, (100, 70, 50))
    if fan_on_table:
        c.ell(760, 1046, 46, 12, fill=(250, 250, 250), outline=(185, 185, 185), w=3)
        c.line([(800, 1048), (850, 1052)], (238, 238, 238), 12)


# ---------- shots ----------
# each shot: f(t_local, T_global) -> Cv

def s1a(t, T):  # sitting, fanning, hot
    c = Cv((0, 0, 0), *ROOM_VIEW)
    room(c, T, ac=dict(temp="18°", dust=1))
    airflow(c, 370, 455, 340, T, cool=False, strength=0.6)
    person(c, 370, 1120, 1.05, "res", sit=True, rh=(62 + 8 * math.sin(T * 13), -400), item_r="fan",
           lh=(-60, -120), expr=-0.6, brow=0.8, sweat=1, T=T)
    return c


def s1b(t, T):  # remote insert
    c = Cv((236, 200, 160), dy=150)
    room(c, T, ac=dict(temp="18°", dust=1))
    c.blur(14)
    c.rect(0, 0, W, H, (255, 190, 120, 60))
    c.poly([(1080, 1920), (1080, 1500), (640, 1130), (520, 1260), (760, 1920)], (246, 246, 243))
    c.ell(560, 1120, 120, 92, fill=SKIN_R)
    c.rect(430, 700, 610, 1180, (247, 247, 247), r=44, outline=(175, 175, 175), w=4)
    presses = [0.3, 0.7, 1.1]
    n = sum(t >= p for p in presses)
    c.rect(458, 745, 582, 845, (35, 70, 80), r=10)
    c.text(520, 795, f"{22 - 2 * n}°", 54, (120, 230, 255), weight=600)
    for bx, by in ((480, 905), (560, 905), (480, 985), (560, 985)):
        c.ell(bx, by, 26, fill=(226, 226, 226), outline=(190, 190, 190), w=2)
    c.text(560, 985, "–", 40, (90, 90, 90))
    press = max([1 - abs(t - p) / 0.12 for p in presses] + [0])
    c.ell(600 - 12 * press, 1040 - 30 * press, 48, 62, fill=SKIN_R, outline=(170, 125, 90), w=3)
    for p in presses:
        k = (t - p) / 0.35
        if 0 <= k <= 1:
            for r in (40, 70):
                c.arc(520, 700, r + 60 * k, r + 60 * k, 220, 320, (255, 255, 255, int(220 * (1 - k))), 6)
    return c


def s1c(t, T):  # standing under the AC, warm air
    c = Cv((0, 0, 0), *ROOM_VIEW)
    room(c, T, ac=dict(temp="18°", dust=1))
    airflow(c, 370, 455, 340, T, cool=False, strength=0.9)
    person(c, 370, 1185, 1.12, "res", lh=(-12, -585), rh=(80, -250), item_r="fan", spin=False,
           expr=-0.8, brow=1, sweat=1, T=T)
    return c


def s1d(t, T):  # dusty filter close-up
    c = Cv((243, 224, 196), k=1.05, dy=200)
    x0, y0, w, h = 70, 560, 940, 260
    c.poly([(x0, y0), (x0 + w, y0), (x0 + w - 40, y0 - 210), (x0 + 40, y0 - 210)], (249, 249, 249), outline=(205, 205, 205))
    c.rect(x0, y0, x0 + w, y0 + h, (250, 250, 250), r=30, outline=(210, 210, 210), w=3)
    filter_mesh(c, x0 + 40, y0 + 22, x0 + w / 2 - 10, y0 + h - 70, lambda x, y: 185)
    filter_mesh(c, x0 + w / 2 + 10, y0 + 22, x0 + w - 40, y0 + h - 70, lambda x, y: 185)
    c.rect(x0 + 40, y0 + h - 52, x0 + w - 40, y0 + h - 16, (58, 60, 64), r=14)
    return c


def s2a(t, T):  # phone call, medium shot
    c = Cv((0, 0, 0), *ROOM_VIEW)
    room(c, T, ac=dict(temp="18°", dust=1))
    c.blur(10)
    P = person(c, 540, 1560, 2.0, "res", sit=True, rh=(54, -400), item_r="phone", lh=(-70, -110),
               expr=0.25, brow=0.3, sweat=0.5, T=T)
    px, py = P(54, -400)
    for k in range(3):
        ph = (t * 1.4 + k / 3) % 1
        c.arc(px, py, 40 + 120 * ph, 40 + 120 * ph, 280, 360, ORANGE + (int(230 * (1 - ph)),), 8)
    return c


def s2b(t, T):  # technician at the door
    c = Cv((243, 224, 196), k=1.1, dy=40)
    c.rect(0, 1150, W, H, (212, 182, 146))
    c.rect(250, 290, 830, 1260, (250, 250, 248))
    c.rect(270, 310, 810, 1250, (200, 228, 245))
    c.rect(270, 820, 810, 1250, (228, 206, 170))
    c.rect(270, 1150, 810, 1250, (196, 186, 170))
    c.line([(700, 1150), (700, 760)], (120, 90, 60), 18)
    for a in range(5):
        ang = math.radians(200 + a * 35)
        c.line([(700, 760), (700 + 150 * math.cos(ang), 760 + 90 * math.sin(ang))], (70, 130, 70), 16)
    hand_r = (8, -370) if t > 0.6 else (72, -240)
    person(c, 520, 1245, 1.2, "tech", lh=(-80, -230), item_l="bag", rh=hand_r, expr=0.9, T=T)
    door_w = lerp(540, 40, ease(t / 0.6))
    c.rect(270, 310, 270 + door_w, 1250, (92, 60, 40))
    if door_w > 120:
        c.ell(270 + door_w - 40, 790, 12, fill=(210, 180, 90))
    return c


def s2c(t, T):  # pointing at the AC
    c = Cv((0, 0, 0), *ROOM_VIEW)
    room(c, T, ac=dict(temp="18°", dust=1))
    person(c, 280, 1190, 1.06, "res", rh=(95, -600), lh=(-70, -240), expr=-0.2, brow=0.4, sweat=0.4, T=T)
    nod = math.sin(clamp(t / 0.6) * math.pi) * 0.8
    person(c, 760, 1205, 1.1, "tech", rh=(80, -230), item_r="bag", expr=0.6, nod=nod, T=T)
    return c


def thermometer(c, reading, warm_k, probe_to=(540, 700), alpha=1.0):
    a = int(255 * alpha)
    c.poly([(1080, 1250), (1080, 1080), (860, 960), (800, 1040)], GREY + (a,))
    c.ell(820, 1000, 50, fill=GLOVE + (a,))
    c.line([(760, 900), probe_to], (60, 60, 60, a), 6)
    c.rect(690, 860, 860, 1090, (50, 50, 54, a), r=18)
    c.rect(708, 880, 842, 960, (220, 240, 225, a), r=8)
    col = lerpc((80, 150, 255), (240, 120, 30), warm_k) + (a,)
    c.text(775, 920, f"{reading:.1f}°C", 34, col, weight=700)
    c.ell(775, 1020, 24, fill=(90, 90, 96, a))


def s3a(t, T):  # temperature check (warm)
    c = Cv((238, 234, 228), k=1.1, dy=110)
    draw_ac(c, 540, 520, 2.0, temp="18°", dust=0.8)
    airflow(c, 540, 640, 600, T, cool=False, strength=0.7)
    thermometer(c, 29.5, 1, probe_to=(560, 690))
    return c


def s3b(t, T):  # isolate power
    c = Cv((238, 234, 228), k=1.1, dy=120)
    c.rect(380, 520, 700, 900, (252, 252, 252), r=24, outline=(200, 200, 200), w=4)
    c.text(540, 565, "AC", 34, (120, 120, 120), weight=600)
    off = t > 0.35
    c.rect(480, 620, 600, 830, (230, 230, 230), r=14, outline=(190, 190, 190), w=3)
    if off:
        c.rect(486, 728, 594, 824, (200, 200, 200), r=10)
        c.text(540, 670, "O", 40, (120, 120, 120))
    else:
        c.rect(486, 626, 594, 722, (200, 200, 200), r=10)
        c.text(540, 780, "I", 40, ORANGE)
    k = clamp(t / 0.35)
    fx, fy = lerp(700, 560, k), lerp(560, 650 if not off else 760, k)
    c.poly([(1080, 330), (1080, 560), (fx + 30, fy + 30), (fx - 10, fy - 30)], GREY)
    c.ell(fx, fy, 42, 36, fill=GLOVE)
    if t > 0.45:
        sw = 18 * math.exp(-(t - 0.45) * 5) * math.sin((t - 0.45) * 18)
        c.line([(540, 900), (540 + sw, 940)], (90, 90, 90), 4)
        c.rect(450 + sw, 940, 630 + sw, 1050, (220, 40, 40), r=8)
        c.text(540 + sw, 975, "DO NOT", 28, WHITE)
        c.text(540 + sw, 1015, "SWITCH ON", 28, WHITE)
    return c


def s3c(t, T):  # protect sofa and wall
    c = Cv((0, 0, 0), *ROOM_VIEW)
    room(c, T, sheet=clamp(t / 0.8), plastic=clamp((t - 0.2) / 0.5), ac=dict(temp="", louvre=0, dust=0.8, display=False))
    person(c, 750, 1205, 1.1, "tech", lh=(-90, -470), rh=(70, -470), gloves=True, expr=0.4, T=T)
    return c


def s3d(t, T):  # filter wash
    c = Cv((228, 233, 236), dy=180)
    for x in range(0, W, 120):
        c.line([(x, 0), (x, 1000)], (210, 216, 220), 3, caps=False)
    for y in range(0, 1000, 120):
        c.line([(0, y), (W, y)], (210, 216, 220), 3, caps=False)
    c.rect(120, 1000, 960, 1190, (196, 201, 207), r=30)
    c.rect(500, 230, 560, 500, (205, 210, 215), r=12)
    c.rect(500, 230, 700, 280, (205, 210, 215), r=12)
    c.rect(510, 490, 550, 530, (170, 175, 182), r=6)
    sx = 530
    pts_l = [(sx - 18 + 4 * math.sin(y / 25 + T * 20), y) for y in range(530, 800, 15)]
    pts_r = [(sx + 18 + 4 * math.sin(y / 25 + T * 20 + 1), y) for y in range(785, 529, -15)]
    c.poly(pts_l + pts_r, (150, 200, 245, 170))
    c.line([(sx - 4, 540), (sx - 4, 790)], (235, 248, 255, 200), 5, caps=False)
    rad = 80 + 520 * ease((t - 0.1) / 1.3)

    def da(x, y):
        return 185 * clamp((math.hypot(x - sx, y - 820) - rad) / 60)
    filter_mesh(c, 230, 720, 850, 980, da)
    for u, v, r in SPECK[:24]:
        ph = (T * 3 + u) % 1
        ang = math.pi * (1.1 + 0.8 * v)
        c.ell(sx + math.cos(ang) * 160 * ph, 800 + math.sin(ang) * 90 * ph + 60 * ph * ph, 4 + 3 * r,
              fill=(170, 215, 250, int(200 * (1 - ph))))
    for hx in (215, 865):
        c.ell(hx, 850, 40, 52, fill=GLOVE)
    return c


def s3e(t, T):  # coil clean with protective bag
    c = Cv((238, 234, 228), dy=150)
    c.rect(60, 280, 1020, 760, (215, 232, 245, 90))
    x0, y0, w, h = 80, 380, 920, 250
    c.rect(x0, y0, x0 + w, y0 + h, (250, 250, 250), r=26, outline=(208, 208, 208), w=3)
    cx0, cx1 = x0 + 30, x0 + w - 200
    c.rect(cx0, y0 + 25, cx1, y0 + h - 30, (150, 155, 160))
    sweep = cx0 + (cx1 - cx0) * ease(t / 1.8)
    for x in np.arange(cx0 + 6, cx1, 9):
        dirty = x > sweep
        c.line([(x, y0 + 28), (x, y0 + h - 33)], (160, 150, 135) if dirty else (205, 212, 218), 4, caps=False)
    ex0 = cx1 + 20
    c.rect(ex0, y0 + 25, x0 + w - 25, y0 + h - 30, (70, 72, 78), r=8)
    c.rect(ex0 - 10, y0 + 15, x0 + w - 15, y0 + h - 20, (200, 225, 245, 150), r=12)
    for k in range(4):
        c.line([(ex0 + 10 + k * 35, y0 + 30), (ex0 + 40 + k * 35, y0 + h - 40)], (255, 255, 255, 170), 4, caps=False)
    bag = [(x0 - 10, y0 + h - 10), (x0 + w + 10, y0 + h - 10), (620, 1040), (460, 1040)]
    c.poly(bag, (205, 228, 242, 130), outline=(150, 190, 220))
    lvl = 10 + 40 * clamp(t / 2)
    c.poly([(470, 1040 - lvl), (610, 1040 - lvl), (620, 1040), (460, 1040)], (150, 150, 140, 170))
    c.line([(540, 1040), (540, 1090), (700, 1120), (760, 1150)], (90, 160, 210), 12, caps=False)
    c.poly([(720, 1130), (860, 1130), (845, 1230), (735, 1230)], (90, 150, 210))
    for u, v, r in SPECK[:20]:
        ph = (T * 1.6 + v) % 1
        dx = cx0 + u * (sweep - cx0)
        c.ell(dx, y0 + h + ph * 330 * (1 - abs(dx - 540) / 900), 5, fill=(140, 140, 130, int(220 * (1 - ph))))
    nx = sweep
    c.poly([(nx - 14, 900), (nx + 14, 900), (nx + 8, 760), (nx - 8, 760)], (80, 80, 86))
    c.rect(nx - 40, 900, nx + 40, 1000, (60, 60, 66), r=14)
    c.ell(nx + 40, 960, 38, fill=GLOVE)
    for u, v, r in SPECK:
        ph = (T * 4 + v * 3) % 1
        c.ell(nx + (u - 0.5) * 160 * ph, 755 - ph * 110, 3 + r * 3, fill=(235, 246, 255, int(210 * (1 - ph))))
    return c


def s3f(t, T):  # drain check outside
    c = Cv((150, 200, 240), k=1.1, dy=60)
    c.rect(0, 200, W, 1150, (226, 205, 170))
    c.rect(0, 1150, W, H, (190, 170, 140))
    for u, v, r in DUST[:80]:
        c.ell(u * W, 1160 + v * 120, 4 + r * 6, fill=(165, 145, 118))
    c.line([(480, 200), (480, 900), (520, 950), (600, 950)], (248, 248, 248), 34, caps=False)
    c.ell(600, 950, 17, fill=(225, 225, 225))
    flow = clamp((t - 0.15) / 0.3)
    if flow > 0:
        pts_l = [(608 + 10 * (y - 960) / 200, y) for y in range(960, 1160, 20)]
        pts = [(x - 7, y) for x, y in pts_l] + [(x + 7, y) for x, y in reversed(pts_l)]
        c.poly(pts, (170, 215, 250, int(190 * flow)))
        for u, v, r in SPECK[:14]:
            ph = (T * 2.5 + u) % 1
            c.ell(612 + (v - 0.5) * 80 * ph, 1150 - 20 * math.sin(ph * math.pi), 4, fill=(190, 225, 252, int(200 * (1 - ph))))
    return c


def gauge(c, cx, cy, rim, val):
    c.ell(cx, cy, 98, fill=rim)
    c.ell(cx, cy, 84, fill=(250, 250, 250))
    for k in range(11):
        a = math.radians(135 + k * 27)
        c.line([(cx + 66 * math.cos(a), cy + 66 * math.sin(a)), (cx + 78 * math.cos(a), cy + 78 * math.sin(a))], (60, 60, 60), 3, caps=False)
    a = math.radians(135 + val * 270)
    c.line([(cx, cy), (cx + 66 * math.cos(a), cy + 66 * math.sin(a))], (210, 40, 40), 5)
    c.ell(cx, cy, 9, fill=(60, 60, 60))


def s3g(t, T):  # outdoor unit + gauge check
    c = Cv((150, 200, 240), dy=120)
    c.rect(0, 200, W, 1150, (226, 205, 170))
    c.rect(0, 1150, W, H, (190, 170, 140))
    c.line([(150, 990), (930, 990)], (130, 130, 130), 12, caps=False)
    c.rect(150, 430, 930, 970, (236, 236, 233), r=20, outline=(200, 200, 198), w=4)
    c.ell(430, 700, 230, fill=(80, 82, 86))
    for k in range(3):
        a = 0.5 + k * 2.094
        c.poly([(430, 700), (430 + 200 * math.cos(a - 0.35), 700 + 200 * math.sin(a - 0.35)),
                (430 + 200 * math.cos(a + 0.2), 700 + 200 * math.sin(a + 0.2))], (120, 124, 130))
    for r in range(40, 231, 30):
        c.ell(430, 700, r, outline=(190, 190, 190), w=4)
    c.line([(200, 700), (660, 700)], (190, 190, 190), 4, caps=False)
    c.line([(430, 470), (430, 930)], (190, 190, 190), 4, caps=False)
    c.rect(800, 840, 860, 900, (150, 130, 60), r=6)
    on = clamp((t - 0.2) / 0.3)
    for col, end in (((40, 90, 210), (360, 1040)), ((210, 40, 40), (720, 1040))):
        pts = [(830, 900)] + [(lerp(830, end[0], k / 10), lerp(900, end[1], k / 10) + 70 * math.sin(k / 10 * math.pi)) for k in range(1, 11)]
        if on > 0:
            c.line(pts[: max(2, int(len(pts) * on))], col, 12, caps=False)
    c.rect(300, 1030, 780, 1090, (205, 208, 212), r=14)
    ksettle = clamp((t - 0.5) / 1.0)
    wob = math.exp(-ksettle * 4) * math.sin(ksettle * 25) * 0.08
    gauge(c, 400, 960, (40, 90, 210), lerp(0.05, 0.45, ease(ksettle)) + wob)
    gauge(c, 680, 960, (210, 40, 40), lerp(0.05, 0.55, ease(ksettle)) - wob)
    return c


def s3h(t, T):  # reassemble and test, temperature drops
    c = Cv((238, 234, 228), k=1.1, dy=110)
    on = t > 0.75
    draw_ac(c, 540, 520, 2.0, temp="24°" if on else None, louvre=ease((t - 0.8) / 0.5) if on else 0, display=on)
    if t < 0.7:
        fy = lerp(900, 560, ease(t / 0.55))
        filter_mesh(c, 200, fy, 880, fy + 120, lambda x, y: 0)
        c.ell(180, fy + 60, 36, fill=GLOVE)
        c.ell(900, fy + 60, 36, fill=GLOVE)
    if on:
        k = ease((t - 1.0) / 1.3)
        airflow(c, 540, 640, 600, T, cool=True, strength=0.3 + 0.5 * k)
        if t > 1.0:
            thermometer(c, lerp(29.5, 13.8, k), 1 - k, probe_to=(560, 690), alpha=clamp((t - 1.0) / 0.2))
    return c


def s4a(t, T):  # cool air, relief
    c = Cv((0, 0, 0), *ROOM_VIEW)
    room(c, T, cool=1, air=1, ac=dict(temp="24°"))
    airflow(c, 370, 455, 340, T, cool=True)
    person(c, 370, 1185, 1.12, "res", lh=(-12, -585), rh=(80, -250), item_r="fan", spin=False,
           expr=lerp(0.2, 1, ease(t / 0.8)), brow=0, T=T)
    return c


def s4b(t, T):  # sits down, puts the fan on the table
    c = Cv((0, 0, 0), *ROOM_VIEW)
    k = ease((t - 0.3) / 0.8)
    room(c, T, cool=1, air=1, ac=dict(temp="24°"), fan_on_table=k >= 1)
    airflow(c, 370, 455, 340, T, cool=True, strength=0.7)
    hand = (lerp(80, 205, k), lerp(-130, -78, k)) if k < 1 else (lerp(205, 70, ease((t - 1.1) / 0.3)), -110)
    person(c, 370, 1120, 1.05, "res", sit=True, rh=hand, item_r="fan" if k < 1 else None, spin=False,
           lh=(-70, -120), expr=1, T=T)
    return c


def s4c(t, T):  # thankful nod
    c = Cv((0, 0, 0), *ROOM_VIEW)
    room(c, T, cool=1, air=1, ac=dict(temp="24°"), fan_on_table=True)
    airflow(c, 370, 455, 340, T, cool=True, strength=0.6)
    nod = math.sin(clamp((t - 0.1) / 0.5) * math.pi)
    person(c, 330, 1120, 1.05, "res", sit=True, lh=(-70, -120), rh=(70, -120), expr=1, nod=nod, T=T)
    person(c, 750, 1205, 1.1, "tech", rh=(80, -230), item_r="bag", expr=0.9, nod=nod * 0.8, T=T)
    return c


SHOTS = [(0, 2, s1a), (2, 3.5, s1b), (3.5, 5.5, s1c), (5.5, 7, s1d),
         (7, 8.5, s2a), (8.5, 10, s2b), (10, 11, s2c),
         (11, 12.5, s3a), (12.5, 13.5, s3b), (13.5, 14.5, s3c), (14.5, 16, s3d), (16, 18, s3e),
         (18, 19, s3f), (19, 20.5, s3g), (20.5, 23, s3h),
         (23, 24.5, s4a), (24.5, 26, s4b), (26, 27, s4c)]
SCENE_CUTS = (7, 11, 23)
XF = 0.25

_yy, _xx = np.mgrid[0:H, 0:W]
_r = np.hypot((_xx - W / 2) / (W / 2), (_yy - H / 2) / (H / 2))
VIGNETTE = Image.fromarray(np.repeat((255 * (1 - 0.22 * np.clip(_r - 0.6, 0, None) ** 1.5))[..., None], 3, 2).astype(np.uint8))
WARM = Image.new("RGB", (W, H), (255, 160, 70))
COOL = Image.new("RGB", (W, H), (140, 200, 255))


def shot(T):
    T = min(T, 27 - 1e-3)
    a, b, f = next(s for s in SHOTS if s[0] <= T < s[1])
    t = T - a
    img = f(t, T).done()
    z = 1 + 0.04 * t / (b - a)
    cw, ch = W / z, H / z
    img = img.crop((int((W - cw) / 2), int((H - ch) / 2), int((W + cw) / 2), int((H + ch) / 2))).resize((W, H), Image.BICUBIC)
    if T < 11:
        img = Image.blend(img, WARM, 0.10 if T < 7 else 0.07)
    elif T >= 23:
        img = Image.blend(img, COOL, 0.07 * smooth((T - 23) / 0.6))
    return ImageChops.multiply(img, VIGNETTE)


def frame(i):
    T = i / FPS
    if T >= 27:
        img = bb.end_card(T - 27)
        if T < 27 + XF:
            img = Image.blend(shot(26.99).convert("RGBA"), img, (T - 27) / XF)
    else:
        img = shot(T)
        for cut in SCENE_CUTS:
            if cut <= T < cut + XF:
                img = Image.blend(shot(cut - 1 / FPS), img, (T - cut) / XF)
        img = img.convert("RGBA")
        bb.draw_captions(img, T)
    return img.convert("RGB").tobytes()


# ---------- audio ----------

SR = 44100


def build_audio(path):
    n = SR * DUR
    t = np.arange(n) / SR
    mus = np.zeros(n)
    sfx = np.zeros(n)
    rng = np.random.default_rng(3)

    def add(buf, t0, sig, gain=1.0):
        i0 = int(t0 * SR)
        sig = sig[: max(0, n - i0)]
        buf[i0:i0 + len(sig)] += sig * gain

    def env(d, a=0.005, r=None):
        m = int(d * SR)
        e = np.ones(m)
        ai = max(1, int(a * SR))
        e[:ai] = np.linspace(0, 1, ai)
        if r:
            ri = min(m, int(r * SR))
            e[-ri:] *= np.linspace(1, 0, ri)
        return e

    def tone(f, d, decay=None, harm=0.25):
        tt = np.arange(int(d * SR)) / SR
        s = np.sin(2 * np.pi * f * tt) + harm * np.sin(4 * np.pi * f * tt)
        if decay:
            s *= np.exp(-tt / decay)
        return s * env(d, r=0.01)

    def band(d, lo, hi):
        m = int(d * SR)
        spec = np.fft.rfft(rng.standard_normal(m))
        fr = np.fft.rfftfreq(m, 1 / SR)
        spec[(fr < lo) | (fr > hi)] = 0
        s = np.fft.irfft(spec, m)
        return s / (np.abs(s).max() + 1e-9)

    # music: 105 BPM, C - G - Am - F
    beat = 60 / 105
    chords = [[60, 64, 67], [55, 59, 62], [57, 60, 64], [53, 57, 60]]
    midi = lambda m: 440 * 2 ** ((m - 69) / 12)  # noqa: E731
    nb = int(27 / beat) + 1
    for b in range(nb):
        tb = b * beat
        ch = chords[(b // 4) % 4]
        for k in range(2):
            note = ch[(b * 2 + k) % 3] + 12
            add(mus, tb + k * beat / 2, tone(midi(note), 0.5, decay=0.22), 0.22)
        if b % 2 == 0:
            add(mus, tb, tone(midi(ch[0] - 24), beat * 1.9, decay=0.6, harm=0.1), 0.45)
        if tb >= 11:
            kk = np.arange(int(0.16 * SR)) / SR
            add(mus, tb, np.sin(2 * np.pi * (50 + 70 * np.exp(-kk * 30)) * kk) * np.exp(-kk * 18), 0.55)
            add(mus, tb + beat / 2, band(0.04, 6000, 12000) * env(0.04, r=0.03), 0.12)
            if tb >= 23 and b % 2 == 1:
                add(mus, tb, band(0.12, 1200, 5000) * np.exp(-np.arange(int(0.12 * SR)) / SR * 30), 0.25)
    for m in chords[0] + [chords[0][0] - 12]:
        add(mus, 27.0, tone(midi(m), 3.0, decay=1.4, harm=0.15), 0.18)
    # "heat" section: muffled and quieter until the work starts
    cut = int(11 * SR)
    spec = np.fft.rfft(mus[:cut])
    fr = np.fft.rfftfreq(cut, 1 / SR)
    spec *= 1 / (1 + (fr / 900) ** 2)
    mus[:cut] = np.fft.irfft(spec, cut) * 0.7
    mus[cut - 2205:cut + 2205] *= np.concatenate([np.ones(2205), np.linspace(0.7, 1, 2205)])

    # sound effects
    ci = band(7, 3500, 6500) * (0.6 + 0.4 * np.sin(2 * np.pi * 28 * np.arange(7 * SR) / SR))
    add(sfx, 0, ci * env(7, a=0.4, r=0.6), 0.10)
    add(sfx, 0, band(7, 60, 300) * env(7, a=0.3, r=0.5) * (0.7 + 0.3 * np.sin(np.arange(7 * SR) / SR * 9)), 0.15)
    for p in (2.3, 2.7, 3.1):
        add(sfx, p, tone(2100, 0.07, harm=0), 0.25)
    add(sfx, 3.5, band(2, 100, 900) * env(2, a=0.2, r=0.3), 0.25)
    add(sfx, 3.9, band(0.6, 200, 1500) * env(0.6, a=0.1, r=0.4), 0.18)  # sigh
    click = lambda: band(0.03, 1500, 8000) * env(0.03, r=0.02)  # noqa: E731
    for p, g in ((5.6, 0.5), (12.85, 0.7), (19.6, 0.4), (19.85, 0.4), (21.0, 0.5), (21.2, 0.5)):
        add(sfx, p, click(), g)
    for k in range(2):
        ring = (tone(440, 0.4, harm=0) + tone(480, 0.4, harm=0)) * 0.5
        add(sfx, 7.05 + k * 0.6, ring, 0.18)
    add(sfx, 8.6, tone(90, 0.25, decay=0.08, harm=0.5), 0.6)
    for p in (10.1, 10.5):
        add(sfx, p, tone(70, 0.12, decay=0.04, harm=0.5), 0.5)
    add(sfx, 11.35, tone(3000, 0.08, harm=0), 0.18)
    rust = band(0.8, 2000, 9000) * (rng.random(int(0.8 * SR)) > 0.0) * np.abs(np.sin(np.arange(int(0.8 * SR)) / SR * 40))
    add(sfx, 13.6, rust * env(0.8, a=0.05, r=0.2), 0.25)
    add(sfx, 14.55, band(1.45, 300, 3500) * env(1.45, a=0.1, r=0.3) * (0.8 + 0.2 * rng.random(int(1.45 * SR))), 0.30)
    add(sfx, 16.05, band(1.9, 3000, 11000) * env(1.9, a=0.1, r=0.2) * (0.75 + 0.25 * np.sin(np.arange(int(1.9 * SR)) / SR * 20)), 0.18)
    add(sfx, 18.2, band(0.8, 400, 3000) * env(0.8, a=0.15, r=0.2), 0.2)
    for p in (18.35, 18.6, 18.8):
        tt = np.arange(int(0.06 * SR)) / SR
        add(sfx, p, np.sin(2 * np.pi * (1400 - 6000 * tt) * tt) * np.exp(-tt * 60), 0.2)
    add(sfx, 21.4, tone(1600, 0.09, harm=0), 0.2)
    add(sfx, 21.52, tone(2000, 0.12, harm=0), 0.2)
    air = band(6, 80, 900)
    add(sfx, 21.5, air * env(6, a=1.2, r=0.8), 0.22)
    add(sfx, 24.7, band(0.7, 150, 1200) * env(0.7, a=0.2, r=0.45), 0.2)  # relaxed exhale
    add(sfx, 25.62, tone(140, 0.12, decay=0.03, harm=0.6), 0.5)
    wh = band(0.7, 400, 6000) * np.hanning(int(0.7 * SR))
    add(sfx, 26.75, wh, 0.35)

    mix = mus * 0.5 + sfx * 0.8
    mix *= np.concatenate([np.ones(n - int(0.6 * SR)), np.linspace(1, 0, int(0.6 * SR))])
    mix = mix / (np.abs(mix).max() + 1e-9) * 0.9
    pcm = (mix * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())


def main():
    OUT.mkdir(exist_ok=True)
    wav = HERE / "_audio.wav"
    raw = HERE / "_video.mp4"
    build_audio(wav)
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-crf", "19", "-preset", "medium",
           "-pix_fmt", "yuv420p", str(raw)]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    with Pool() as pool:
        for i, buf in enumerate(pool.imap(frame, range(DUR * FPS), chunksize=4)):
            p.stdin.write(buf)
            if i % 150 == 0:
                print(f"  frame {i}/{DUR * FPS}", flush=True)
    p.stdin.close()
    if p.wait():
        raise SystemExit("ffmpeg video encode failed")
    final = OUT / "alfaytri_ac_promo_30s.mp4"
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(raw), "-i", str(wav),
                    "-c:v", "copy", "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "160k",
                    "-ar", "48000", "-shortest", "-movflags", "+faststart", str(final)], check=True)
    wav.unlink()
    raw.unlink()
    print("Wrote", final)


if __name__ == "__main__":
    main()
