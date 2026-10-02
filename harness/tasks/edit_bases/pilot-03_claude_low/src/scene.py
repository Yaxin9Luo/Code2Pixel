"""Night Japanese alley: red lanterns, glowing vending machines, rain-wet stone path.

Pure procedural: geometry is drawn with pycairo in a simple one-point
perspective camera, the wet stone ground (reflections, puddles, ripples,
light pools), bloom and rain are computed with numpy / OpenCV.
"""
import math
import os
import sys

import cairo
import cv2
import numpy as np

W, H = 1536, 1024
CX, HY = 768.0, 470.0      # vanishing point
F = 820.0                  # focal length (px)
CAMX, CAMH = -0.3, 1.45    # camera position
XL, XR = -2.0, 2.2         # alley walls
ZEND = 38.0                # building closing the alley
rng = np.random.default_rng(7)
FONT = "Noto Serif CJK JP"
FONT_S = "Noto Sans CJK JP"


# ----------------------------------------------------------------- camera
def P(X, Y, Z):
    return (CX + F * (X - CAMX) / Z, HY - F * (Y - CAMH) / Z)


def poly(ctx, pts):
    x, y = P(*pts[0])
    ctx.move_to(x, y)
    for p in pts[1:]:
        ctx.line_to(*P(*p))
    ctx.close_path()


def fill(ctx, pts, col, a=1.0):
    poly(ctx, pts)
    ctx.set_source_rgba(*col, a)
    ctx.fill()


def wall_x(side, d=0.0):
    """x coordinate of a plane parallel to a side wall, d metres toward centre"""
    return (XL + d) if side < 0 else (XR - d)


def wquad(side, z0, z1, y0, y1, d=0.0):
    X = wall_x(side, d)
    return [(X, y0, z0), (X, y1, z0), (X, y1, z1), (X, y0, z1)]


def wfill(ctx, side, z0, z1, y0, y1, col, d=0.0, a=1.0):
    fill(ctx, wquad(side, z0, z1, y0, y1, d), col, a)


def wgrad(ctx, side, z0, z1, y0, y1, c_top, c_bot, d=0.0):
    poly(ctx, wquad(side, z0, z1, y0, y1, d))
    X = wall_x(side, d)
    zm = (z0 + z1) / 2
    _, ya = P(X, y1, zm)
    _, yb = P(X, y0, zm)
    g = cairo.LinearGradient(0, ya, 0, yb)
    g.add_color_stop_rgb(0, *c_top)
    g.add_color_stop_rgb(1, *c_bot)
    ctx.set_source(g)
    ctx.fill()


def wall_affine(ctx, side, z, y, d=0.0):
    """Set cairo matrix so that local (u right, v down) metres map onto the wall."""
    X = wall_x(side, d)
    e = 1e-3
    su = 1 if side < 0 else -1
    p0 = np.array(P(X, y, z))
    pu = (np.array(P(X, y, z + su * e)) - p0) / e
    pv = (np.array(P(X, y - e, z)) - p0) / e
    ctx.set_matrix(cairo.Matrix(pu[0], pu[1], pv[0], pv[1], p0[0], p0[1]))


def text_v(ctx, s, size, col, bold=True, font=FONT, a=1.0):
    """vertical text centred on origin (local coords)"""
    ctx.select_font_face(font, cairo.FONT_SLANT_NORMAL,
                         cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(size)
    n = len(s)
    step = size * 1.05
    y = -step * n / 2
    ctx.set_source_rgba(*col, a)
    for ch in s:
        ext = ctx.text_extents(ch)
        ctx.move_to(-ext.x_advance / 2, y + size * 0.88)
        ctx.show_text(ch)
        y += step


def text_h(ctx, s, size, col, bold=True, font=FONT, a=1.0):
    ctx.select_font_face(font, cairo.FONT_SLANT_NORMAL,
                         cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
    ctx.set_font_size(size)
    ext = ctx.text_extents(s)
    ctx.move_to(-ext.x_advance / 2, size * 0.36)
    ctx.set_source_rgba(*col, a)
    ctx.show_text(s)


def glow(ctx, x, y, r, col, a):
    g = cairo.RadialGradient(x, y, 0, x, y, r)
    g.add_color_stop_rgba(0, *col, a)
    g.add_color_stop_rgba(0.35, *col, a * 0.35)
    g.add_color_stop_rgba(1, *col, 0)
    ctx.set_source(g)
    ctx.arc(x, y, r, 0, 2 * math.pi)
    ctx.fill()


# point lights for the ground lighting pass: (X, Y, Z, (r,g,b), power)
LIGHTS = []

WOOD = (0.10, 0.060, 0.042)
WOOD_D = (0.055, 0.034, 0.026)
PLASTER = (0.115, 0.112, 0.130)
ROOF = (0.045, 0.048, 0.060)
SHOJI = (1.0, 0.72, 0.40)


# ------------------------------------------------------------------- sky
def draw_sky(ctx):
    g = cairo.LinearGradient(0, 0, 0, HY + 40)
    g.add_color_stop_rgb(0, 0.015, 0.02, 0.05)
    g.add_color_stop_rgb(0.55, 0.04, 0.05, 0.10)
    g.add_color_stop_rgb(1, 0.16, 0.12, 0.17)
    ctx.set_source(g)
    ctx.rectangle(0, 0, W, H)
    ctx.fill()
    # low clouds lit by the city
    for _ in range(60):
        x = rng.uniform(300, 1240)
        y = rng.uniform(40, 330)
        r = rng.uniform(40, 140)
        g = cairo.RadialGradient(x, y, 0, x, y, r)
        k = 1 - y / 400
        g.add_color_stop_rgba(0, 0.20, 0.13, 0.16, 0.05 + 0.05 * (1 - k))
        g.add_color_stop_rgba(1, 0.20, 0.13, 0.16, 0)
        ctx.set_source(g)
        ctx.save()
        ctx.translate(x, y)
        ctx.scale(1.8, 0.6)
        ctx.translate(-x, -y)
        ctx.arc(x, y, r, 0, 2 * math.pi)
        ctx.restore()
        ctx.fill()


def draw_far_building(ctx):
    z = ZEND
    fill(ctx, [(-9, 0, z), (-9, 11, z), (9, 11, z), (9, 0, z)], (0.07, 0.065, 0.085))
    # roof line
    fill(ctx, [(-9, 11, z), (-8, 11.6, z), (8, 11.6, z), (9, 11, z)], (0.04, 0.04, 0.055))
    for fy in range(4):
        for wx in np.arange(-8, 8, 1.6):
            if rng.random() < 0.5:
                c = [(1.0, 0.75, 0.45), (0.7, 0.85, 1.0), (1.0, 0.55, 0.3)][rng.integers(3)]
                a = rng.uniform(0.35, 0.9)
            else:
                c, a = (0.05, 0.05, 0.07), 1
            y0 = 3.2 + fy * 2.0
            fill(ctx, [(wx, y0, z), (wx, y0 + 1.1, z), (wx + 1.0, y0 + 1.1, z), (wx + 1.0, y0, z)], c, a)
    # ground floor shop with glowing frontage
    fill(ctx, [(-3, 0, z), (-3, 2.4, z), (3, 2.4, z), (3, 0, z)], (0.9, 0.62, 0.36), 0.9)
    for xs in np.arange(-3, 3.01, 0.5):
        fill(ctx, [(xs - 0.03, 0, z), (xs - 0.03, 2.4, z), (xs + 0.03, 2.4, z), (xs + 0.03, 0, z)], WOOD_D)
    fill(ctx, [(-3.4, 2.4, z), (-3.4, 2.9, z), (3.4, 2.9, z), (3.4, 2.4, z)], (0.05, 0.04, 0.05))
    # sign
    fill(ctx, [(-1.6, 3.0, z), (-1.6, 3.8, z), (1.6, 3.8, z), (1.6, 3.0, z)], (0.95, 0.92, 0.85))
    x, y = P(0, 3.4, z)
    ctx.save()
    ctx.translate(x, y)
    s = F / z
    ctx.scale(s, s)
    text_h(ctx, "湯", 0.6, (0.75, 0.1, 0.08))
    ctx.restore()
    LIGHTS.append((0, 1.2, z - 1.0, (1.0, 0.7, 0.4), 6.0))


# --------------------------------------------------------------- facades
def eave(ctx, side, z0, z1, y, depth, thick=0.12):
    """Sloped little roof sticking out of the wall, seen from below."""
    X0 = wall_x(side)
    X1 = wall_x(side, depth)
    under = [(X0, y + 0.25, z0), (X0, y + 0.25, z1), (X1, y, z1), (X1, y, z0)]
    fill(ctx, under, (0.035, 0.028, 0.03))
    # rafters
    ctx.set_line_width(1.0)
    for zz in np.arange(z0 + 0.15, z1, 0.3):
        a = P(X0, y + 0.25, zz)
        b = P(X1, y, zz)
        ctx.move_to(*a)
        ctx.line_to(*b)
    ctx.set_source_rgba(0.09, 0.06, 0.05, 1)
    ctx.stroke()
    # fascia board / tile edge
    fill(ctx, [(X1, y, z0), (X1, y - thick, z0), (X1, y - thick, z1), (X1, y, z1)], (0.07, 0.07, 0.085))
    fill(ctx, [(X1, y + 0.05, z0), (X1, y, z0), (X1, y, z1), (X1, y + 0.05, z1)], (0.16, 0.17, 0.2))
    # near end cap
    fill(ctx, [(X0, y + 0.25, z0), (X1, y, z0), (X1, y - thick, z0), (X0, y + 0.25 - thick, z0)], ROOF)


def lattice(ctx, side, z0, z1, y0, y1, spacing=0.05, col=WOOD_D, back=None):
    if back is not None:
        wgrad(ctx, side, z0, z1, y0, y1, *back)
    for zz in np.arange(z0, z1, spacing):
        wfill(ctx, side, zz, zz + spacing * 0.45, y0, y1, col)
    wfill(ctx, side, z0, z1, y0, y0 + 0.08, col)
    wfill(ctx, side, z0, z1, y1 - 0.06, y1, col)


def shoji(ctx, side, z0, z1, y0, y1, bright=1.0):
    c1 = tuple(min(1, v * bright) for v in SHOJI)
    c2 = tuple(min(1, v * bright * 0.75) for v in (1.0, 0.55, 0.28))
    wgrad(ctx, side, z0, z1, y0, y1, c2, c1)
    ctx.set_line_width(1)
    for zz in np.linspace(z0, z1, max(2, int((z1 - z0) / 0.22)) + 1):
        wfill(ctx, side, zz - 0.012, zz + 0.012, y0, y1, WOOD_D)
    for yy in np.linspace(y0, y1, int((y1 - y0) / 0.28) + 1):
        wfill(ctx, side, z0, z1, yy - 0.012, yy + 0.012, WOOD_D)
    # frame
    for zz in (z0, z1):
        wfill(ctx, side, zz - 0.04, zz + 0.04, y0, y1, WOOD)


def noren(ctx, side, z0, z1, y0, y1, col, text, tcol=(0.95, 0.93, 0.88)):
    n = max(2, len(text))
    w = (z1 - z0) / n
    for i in range(n):
        a = z0 + i * w + 0.015
        b = z0 + (i + 1) * w - 0.015
        wgrad(ctx, side, a, b, y0, y1, col, tuple(v * 0.7 for v in col), d=0.02)
    ctx.save()
    for i, ch in enumerate(text):
        zc = z0 + (i + 0.5) * w
        wall_affine(ctx, side, zc, (y0 + y1) / 2 + 0.05, d=0.025)
        text_h(ctx, ch, min(w * 0.75, (y1 - y0) * 0.55), tcol)
    ctx.restore()


def shutter(ctx, side, z0, z1, y0, y1):
    wgrad(ctx, side, z0, z1, y0, y1, (0.17, 0.18, 0.2), (0.10, 0.11, 0.13))
    for yy in np.arange(y0, y1, 0.07):
        wfill(ctx, side, z0, z1, yy, yy + 0.015, (0.06, 0.065, 0.075))
    wfill(ctx, side, z0, z1, y1 - 0.25, y1, (0.08, 0.08, 0.09))


def window_upper(ctx, side, z0, z1, y0, y1, lit):
    wfill(ctx, side, z0 - 0.06, z1 + 0.06, y0 - 0.06, y1 + 0.06, WOOD_D)
    if lit > 0:
        c = (1.0 * lit, 0.68 * lit, 0.38 * lit)
        wgrad(ctx, side, z0, z1, y0, y1, c, tuple(v * 0.7 for v in c))
    else:
        wgrad(ctx, side, z0, z1, y0, y1, (0.05, 0.06, 0.09), (0.03, 0.035, 0.05))
    for zz in np.arange(z0, z1, 0.06):
        wfill(ctx, side, zz, zz + 0.025, y0, y1, WOOD_D)


def facade(ctx, side, z0, z1, kind, top, seed):
    r = np.random.default_rng(seed)
    # upper plaster + structure
    wgrad(ctx, side, z0, z1, 2.8, top, (0.07, 0.07, 0.085), PLASTER if kind != "dark" else (0.08, 0.08, 0.09))
    wfill(ctx, side, z0, z1, 0, 2.8, WOOD)
    # pillars
    wfill(ctx, side, z0, z0 + 0.14, 0, top, WOOD_D)
    wfill(ctx, side, z1 - 0.14, z1, 0, top, WOOD_D)
    L = z1 - z0
    # second floor windows
    if top > 4.5:
        nwin = max(1, int(L / 2.2))
        for i in range(nwin):
            a = z0 + (i + 0.25) * L / nwin
            b = z0 + (i + 0.75) * L / nwin
            lit = r.choice([0, 0, 0.55, 0.8]) if kind != "dark" else 0
            window_upper(ctx, side, a, b, 3.5, 4.5, lit)
            if lit:
                LIGHTS.append((wall_x(side, 0.1), 4.0, (a + b) / 2, (1, .7, .4), 0.6 * lit))
    if kind == "izakaya":
        d0, d1 = z0 + 0.3 * L, z0 + 0.85 * L
        lattice(ctx, side, z0 + 0.18, d0 - 0.05, 0.1, 2.1, back=((0.35, 0.2, 0.1), (0.6, 0.35, 0.16)))
        shoji(ctx, side, d0, d1, 0.05, 2.1, bright=r.uniform(0.85, 1.0))
        wfill(ctx, side, z0, z1, 2.1, 2.25, WOOD_D)
        ncol = [(0.08, 0.12, 0.28), (0.45, 0.06, 0.05), (0.08, 0.08, 0.09)][seed % 3]
        noren(ctx, side, d0 - 0.05, d1 + 0.05, 1.45, 2.12, ncol,
              ["やきとり", "酒処", "おでん", "小料理", "らーめん"][seed % 5])
        LIGHTS.append((wall_x(side, 0.4), 1.0, (d0 + d1) / 2, (1.0, 0.65, 0.35), 2.2))
        # long sign board above the door
        wfill(ctx, side, d0, d1, 2.35, 2.7, (0.06, 0.04, 0.03), d=0.03)
        ctx.save()
        wall_affine(ctx, side, (d0 + d1) / 2, 2.525, d=0.035)
        text_h(ctx, ["鳥よし", "酒肴 まる", "一福", "華月", "とん平"][seed % 5], 0.24, (0.92, 0.85, 0.6))
        ctx.restore()
    elif kind == "koshi":
        lattice(ctx, side, z0 + 0.15, z1 - 0.15, 0.05, 2.5, spacing=0.045,
                back=((0.25, 0.14, 0.07), (0.5, 0.29, 0.13)))
        LIGHTS.append((wall_x(side, 0.4), 1.0, (z0 + z1) / 2, (1.0, 0.6, 0.3), 0.9))
    elif kind == "shutter":
        shutter(ctx, side, z0 + 0.15, z1 - 0.15, 0.0, 2.6)
    elif kind == "dark":
        lattice(ctx, side, z0 + 0.15, z1 - 0.15, 0.05, 2.5, spacing=0.07,
                back=((0.04, 0.035, 0.035), (0.06, 0.05, 0.045)))
    # roof eaves
    eave(ctx, side, z0, z1, 2.8, 0.55)
    if top > 4.5:
        eave(ctx, side, z0, z1, top, 0.7, thick=0.18)


def sign_box(ctx, side, z, y0, y1, text, bg, fg, d0=0.15, d1=0.6, lit=True):
    """Vertical lit signboard sticking out of the wall, facing the camera."""
    X0, X1 = wall_x(side, d0), wall_x(side, d1)
    xa, xb = sorted([X0, X1])
    # bracket
    fill(ctx, [(wall_x(side), y1 - 0.1, z), (wall_x(side), y1, z), (X0, y1, z), (X0, y1 - 0.1, z)], (0.1, 0.1, 0.1))
    # side thickness
    xs = xb if side > 0 else xa
    fill(ctx, [(xs, y0, z), (xs, y1, z), (xs, y1, z + 0.12), (xs, y0, z + 0.12)],
         tuple(v * 0.5 for v in bg))
    fill(ctx, [(xa, y0, z), (xa, y1, z), (xb, y1, z), (xb, y0, z)], bg)
    xc = (xa + xb) / 2
    yc = (y0 + y1) / 2
    x, y = P(xc, yc, z)
    ctx.save()
    ctx.translate(x, y)
    s = F / z
    ctx.scale(s, s)
    sz = min((xb - xa) * 0.75, (y1 - y0) / (len(text) * 1.12))
    text_v(ctx, text, sz, fg)
    ctx.restore()
    if lit:
        glow(ctx, x, y, (y1 - y0) * F / z * 0.9, bg, 0.18)
        LIGHTS.append((xc, yc, z, bg, 1.4))


# --------------------------------------------------------------- lanterns
def lantern(ctx, X, Y, Z, text, rr=0.2, hh=0.3, col=(0.95, 0.12, 0.05), wire=None):
    s = F / Z
    x, y = P(X, Y, Z)
    rw, rh = rr * s, hh * s
    if wire is not None:
        ctx.move_to(x, y - rh * 1.15)
        ctx.line_to(*P(X, wire, Z))
        ctx.set_source_rgba(0.05, 0.05, 0.05, 1)
        ctx.set_line_width(max(1, 0.012 * s))
        ctx.stroke()
    # warm glow onto surroundings (light, additive)
    ctx.save()
    ctx.set_operator(cairo.OPERATOR_ADD)
    glow(ctx, x, y, rh * 4.5, (0.9, 0.25, 0.08), 0.22)
    ctx.restore()
    # body path: barrel shape
    def body():
        ctx.save()
        ctx.translate(x, y)
        ctx.scale(rw, rh)
        ctx.move_to(-0.62, -1.0)
        ctx.curve_to(-1.25, -0.75, -1.25, 0.75, -0.62, 1.0)
        ctx.line_to(0.62, 1.0)
        ctx.curve_to(1.25, 0.75, 1.25, -0.75, 0.62, -1.0)
        ctx.close_path()
        ctx.restore()
    body()
    g = cairo.RadialGradient(x - rw * 0.15, y - rh * 0.1, 0, x, y, rw * 1.15)
    g.add_color_stop_rgb(0, 1.0, 0.78, 0.45)
    g.add_color_stop_rgb(0.35, *[min(1, c * 1.15 + 0.12) for c in col])
    g.add_color_stop_rgb(0.8, *col)
    g.add_color_stop_rgb(1, col[0] * 0.45, col[1] * 0.3, col[2] * 0.3)
    ctx.set_source(g)
    ctx.fill_preserve()
    ctx.save()
    ctx.clip()
    # ribs
    ctx.set_line_width(max(0.6, 0.006 * s))
    for k in np.linspace(-0.85, 0.85, 11):
        ctx.save()
        ctx.translate(x, y + k * rh)
        ctx.scale(rw * 1.2, rh * 0.09)
        ctx.arc(0, 0, 1, 0, math.pi)
        ctx.restore()
        ctx.set_source_rgba(0.35, 0.03, 0.02, 0.45)
        ctx.stroke()
    # text
    ctx.save()
    ctx.translate(x, y)
    ctx.scale(s, s)
    sz = min(rr * 1.05, hh * 1.75 / max(1, len(text)) / 1.05)
    text_v(ctx, text, sz, (0.08, 0.02, 0.02), a=0.9)
    ctx.restore()
    ctx.restore()
    # caps
    for sgn in (-1, 1):
        cy = y + sgn * rh * 1.0
        ctx.rectangle(x - rw * 0.66, cy - rh * 0.08, rw * 1.32, rh * 0.16)
        ctx.set_source_rgb(0.03, 0.025, 0.02)
        ctx.fill()
    # tassel
    ctx.rectangle(x - rw * 0.06, y + rh * 1.08, rw * 0.12, rh * 0.35)
    ctx.set_source_rgb(0.25, 0.03, 0.02)
    ctx.fill()
    LIGHTS.append((X, Y, Z, (1.0, 0.28, 0.1), 1.6 * (rr / 0.2) ** 2))


def wire_lanterns(ctx, z, n, y_attach=4.2, sag=0.5, texts="祭"):
    """A string of small lanterns across the alley."""
    xs = np.linspace(XL, XR, 80)
    t = (xs - XL) / (XR - XL)
    ys = y_attach - sag * 4 * t * (1 - t)
    pts = [P(x, yy, z) for x, yy in zip(xs, ys)]
    ctx.move_to(*pts[0])
    for p in pts[1:]:
        ctx.line_to(*p)
    ctx.set_source_rgba(0.03, 0.03, 0.035, 1)
    ctx.set_line_width(max(1, 0.015 * F / z))
    ctx.stroke()
    for i in range(n):
        tt = (i + 0.5) / n
        X = XL + tt * (XR - XL)
        yw = y_attach - sag * 4 * tt * (1 - tt)
        lantern(ctx, X, yw - 0.3, z, texts[i % len(texts)], rr=0.13, hh=0.19, wire=yw)


# ---------------------------------------------------------- vending machine
def vending(ctx, z0, z1, body, accent, seed, side_ad=False):
    side = 1
    dfront = 0.72
    Xf = wall_x(side, dfront)
    Xw = wall_x(side)
    top = 1.83
    r = np.random.default_rng(seed)
    # near side panel (faces camera)
    fill(ctx, [(Xf, 0, z0), (Xf, top, z0), (Xw, top, z0), (Xw, 0, z0)], tuple(v * 0.75 for v in body))
    if side_ad:
        # lit advertisement on the side panel
        xa, xb = Xf + 0.06, Xw - 0.06
        x0, y0 = P(xa, top - 0.08, z0)
        x1, y1 = P(xb, 0.35, z0)
        g = cairo.LinearGradient(0, y0, 0, y1)
        g.add_color_stop_rgb(0, 0.05, 0.35, 0.8)
        g.add_color_stop_rgb(0.6, 0.3, 0.65, 0.92)
        g.add_color_stop_rgb(1, 0.7, 0.85, 0.95)
        ctx.rectangle(x0, y0, x1 - x0, y1 - y0)
        ctx.set_source(g)
        ctx.fill()
        s = F / z0
        # big can graphic
        cxp, cyp = (x0 + x1) / 2, y0 + (y1 - y0) * 0.52
        cw, ch = 0.2 * s, 0.5 * s
        g = cairo.LinearGradient(cxp - cw, 0, cxp + cw, 0)
        g.add_color_stop_rgb(0, 0.55, 0.05, 0.05)
        g.add_color_stop_rgb(0.35, 1.0, 0.35, 0.3)
        g.add_color_stop_rgb(1, 0.5, 0.03, 0.03)
        ctx.rectangle(cxp - cw, cyp - ch / 2, 2 * cw, ch)
        ctx.set_source(g)
        ctx.fill()
        for sg in (-1, 1):
            ctx.save()
            ctx.translate(cxp, cyp + sg * ch / 2)
            ctx.scale(cw, cw * 0.25)
            ctx.arc(0, 0, 1, 0, 2 * math.pi)
            ctx.restore()
            ctx.set_source_rgb(0.75, 0.75, 0.8) if sg < 0 else ctx.set_source_rgb(0.45, 0.04, 0.04)
            ctx.fill()
        ctx.save()
        ctx.translate(cxp, cyp)
        ctx.scale(s, s)
        text_v(ctx, "炭酸", 0.13, (1, 1, 1), font=FONT_S)
        ctx.restore()
        ctx.save()
        ctx.translate((x0 + x1) / 2, y0 + (y1 - y0) * 0.1)
        ctx.scale(s, s)
        text_h(ctx, "つめた〜い", 0.085, (1, 1, 1), font=FONT_S)
        ctx.restore()
        ctx.save()
        ctx.translate((x0 + x1) / 2, y0 + (y1 - y0) * 0.9)
        ctx.scale(s, s)
        text_h(ctx, "ICE COLD", 0.08, (0.1, 0.3, 0.7), font=FONT_S)
        ctx.restore()
    # front body
    fill(ctx, [(Xf, 0, z0), (Xf, top, z0), (Xf, top, z1), (Xf, 0, z1)], body)
    L = z1 - z0

    def fq(u0, u1, v0, v1, col, a=1.0, d=0.0):
        fill(ctx, wquad(side, z0 + u0 * L, z0 + u1 * L, v0, v1, dfront + d), col, a)

    # header light strip
    fq(0.05, 0.95, 1.62, 1.78, accent)
    # display window
    fq(0.05, 0.95, 0.98, 1.58, (0.92, 0.97, 1.0))
    pal = [(0.85, 0.1, 0.1), (0.1, 0.35, 0.8), (0.95, 0.75, 0.1), (0.1, 0.6, 0.3),
           (0.95, 0.95, 0.95), (0.4, 0.2, 0.1), (0.9, 0.4, 0.1), (0.2, 0.2, 0.25)]
    for row, vb in enumerate([1.40, 1.21, 1.02]):
        n = 7
        for i in range(n):
            u0 = 0.08 + i * 0.84 / n
            u1 = u0 + 0.84 / n * 0.7
            c = pal[r.integers(len(pal))]
            fq(u0, u1, vb, vb + 0.13, c, d=0.01)
            fq(u0 + 0.01, u0 + 0.03, vb + 0.02, vb + 0.11, (1, 1, 1), 0.5, d=0.012)
            # buttons
            fq(u0 + 0.01, u1 - 0.01, vb - 0.02, vb - 0.005, (0.2, 1.0, 0.4) if r.random() < 0.8 else (1, 0.2, 0.1), d=0.01)
    # panel area
    fq(0.62, 0.9, 0.62, 0.92, (0.15, 0.15, 0.17))
    fq(0.66, 0.86, 0.78, 0.86, (0.1, 0.9, 0.3), 0.9, d=0.005)
    fq(0.68, 0.74, 0.66, 0.74, (0.6, 0.6, 0.62), d=0.005)
    fq(0.1, 0.55, 0.65, 0.9, tuple(min(1, v * 1.3) for v in body), d=0.003)
    # take-out slot
    fq(0.12, 0.88, 0.12, 0.38, (0.03, 0.03, 0.035))
    fq(0.12, 0.88, 0.36, 0.38, (0.3, 0.3, 0.32))
    # plinth
    fq(0, 1, 0, 0.07, (0.05, 0.05, 0.055))
    # top
    fill(ctx, [(Xf, top, z0), (Xw, top, z0), (Xw, top, z1), (Xf, top, z1)], tuple(v * 0.5 for v in body))
    LIGHTS.append((Xf - 0.15, 0.9, (z0 + z1) / 2, (0.75, 0.9, 1.0), 4.0))


# ---------------------------------------------------------------- props
def pole_and_wires(ctx):
    # utility pole on the left
    z = 7.5
    X = XL + 0.25
    a = P(X - 0.13, 0, z)
    b = P(X + 0.13, 9, z)
    ctx.rectangle(a[0], b[1], b[0] - a[0], a[1] - b[1])
    g = cairo.LinearGradient(a[0], 0, b[0], 0)
    g.add_color_stop_rgb(0, 0.05, 0.05, 0.055)
    g.add_color_stop_rgb(0.7, 0.16, 0.15, 0.16)
    g.add_color_stop_rgb(1, 0.06, 0.06, 0.06)
    ctx.set_source(g)
    ctx.fill()
    # cross arm + transformer
    fill(ctx, [(X - 0.7, 8.2, z), (X - 0.7, 8.32, z), (X + 0.9, 8.32, z), (X + 0.9, 8.2, z)], (0.05, 0.05, 0.06))
    fill(ctx, [(X + 0.15, 6.3, z), (X + 0.15, 7.2, z), (X + 0.6, 7.2, z), (X + 0.6, 6.3, z)], (0.09, 0.09, 0.1))
    # pole number plate
    fill(ctx, [(X - 0.1, 2.0, z - 0.14), (X - 0.1, 2.5, z - 0.14), (X + 0.1, 2.5, z - 0.14), (X + 0.1, 2.0, z - 0.14)], (0.55, 0.55, 0.5))
    # wires: from pole going down the alley and across
    ctx.set_source_rgba(0.02, 0.02, 0.025, 0.95)
    for (x1, y1, x2, y2, z2) in [(X - 0.6, 8.25, XR + 0.5, 7.5, 30), (X + 0.8, 8.25, XR - 0.2, 7.0, 16),
                                 (X - 0.3, 8.25, XL - 1, 7.5, 34), (X, 7.6, XR, 6.5, 9.5),
                                 (X + 0.5, 8.25, XL + 1.0, 8.0, 38)]:
        pts = []
        for t in np.linspace(0, 1, 60):
            zz = z + (z2 - z) * t
            xx = x1 + (x2 - x1) * t
            yy = y1 + (y2 - y1) * t - 0.9 * 4 * t * (1 - t)
            pts.append(P(xx, yy, zz))
        ctx.move_to(*pts[0])
        for p in pts[1:]:
            ctx.line_to(*p)
        ctx.set_line_width(1.6)
        ctx.stroke()
    # wires crossing to near camera, out of frame
    for (y1, y2) in [(8.0, 7.2), (7.4, 6.6)]:
        pts = [P(X + (XR + 1 - X) * t, y1 + (y2 - y1) * t - 0.6 * 4 * t * (1 - t), z + (2.0 - z) * t)
               for t in np.linspace(0, 1, 60)]
        ctx.move_to(*pts[0])
        for p in pts[1:]:
            ctx.line_to(*p)
        ctx.set_line_width(2.5)
        ctx.stroke()


def potted_plants(ctx, side, z, n=3):
    for i in range(n):
        zz = z + i * 0.35
        X = wall_x(side, 0.25)
        a = P(X - 0.13, 0, zz)
        b = P(X + 0.13, 0.32, zz)
        ctx.rectangle(a[0], b[1], b[0] - a[0], a[1] - b[1])
        ctx.set_source_rgb(0.12, 0.08, 0.06)
        ctx.fill()
        s = F / zz
        x, y = P(X, 0.32, zz)
        for k in range(14):
            ang = rng.uniform(-2.6, -0.5)
            ln = rng.uniform(0.15, 0.4) * s
            ctx.move_to(x, y)
            ctx.curve_to(x + math.cos(ang) * ln * 0.3, y + math.sin(ang) * ln * 0.6,
                         x + math.cos(ang) * ln, y + math.sin(ang) * ln * 0.9,
                         x + math.cos(ang) * ln * 1.1, y + math.sin(ang) * ln * 0.7)
            ctx.set_line_width(max(1, 0.03 * s))
            ctx.set_source_rgb(0.03, 0.07 + 0.04 * rng.random(), 0.04)
            ctx.stroke()


def bicycle(ctx, side, z):
    X = wall_x(side, 0.45)
    s = F / z
    ctx.set_source_rgba(0.02, 0.02, 0.025, 1)
    ctx.set_line_width(max(1, 0.025 * s))
    w1 = P(X, 0.33, z)
    w2 = P(X, 0.33, z + 1.0)
    for (wx, wy), zz in ((w1, z), (w2, z + 1.0)):
        ctx.save()
        ctx.translate(wx, wy)
        ctx.scale(0.06 * F / zz, 0.33 * F / zz)
        ctx.arc(0, 0, 1, 0, 2 * math.pi)
        ctx.restore()
        ctx.stroke()
    pts = [P(X, 0.33, z), P(X, 0.85, z + 0.55), P(X, 0.33, z + 1.0), P(X, 0.95, z + 0.15), P(X, 0.85, z + 0.55)]
    ctx.move_to(*pts[0])
    for p in pts[1:]:
        ctx.line_to(*p)
    ctx.stroke()


# ---------------------------------------------------------------- scene
def build_scene():
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    ctx = cairo.Context(surf)
    draw_sky(ctx)
    draw_far_building(ctx)

    left = [(0.4, 2.4, "dark", 6.2), (2.4, 5.8, "izakaya", 5.6), (5.8, 7.6, "koshi", 6.0), (7.6, 10.5, "izakaya", 7.0),
            (10.5, 13.0, "shutter", 5.4), (13.0, 16.5, "izakaya", 6.0), (16.5, 19.5, "koshi", 6.8),
            (19.5, 23.0, "izakaya", 5.8), (23.0, 26.0, "dark", 6.4), (26.0, 30.0, "izakaya", 6.0),
            (30.0, 34.0, "koshi", 7.0), (34.0, 38.0, "izakaya", 6.2)]
    right = [(0.4, 2.7, "dark", 6.6), (2.7, 5.2, "shutter", 6.0), (5.2, 8.8, "izakaya", 6.4),
             (8.8, 11.8, "koshi", 5.6), (11.8, 15.5, "izakaya", 7.2), (15.5, 18.0, "dark", 6.0),
             (18.0, 21.5, "izakaya", 6.4), (21.5, 25.0, "koshi", 5.8), (25.0, 29.0, "izakaya", 6.6),
             (29.0, 33.0, "shutter", 6.0), (33.0, 38.0, "izakaya", 6.8)]

    # items to draw after walls, sorted by depth (far first)
    items = []
    lt = ["酒", "焼鳥", "おでん", "祭", "居酒屋", "酒", "やきとり", "祭"]
    k = 0
    for side, shops in ((-1, left), (1, right)):
        for i, (z0, z1, kind, top) in enumerate(shops):
            items.append((z1, "facade", (side, z0, z1, kind, top, i * 7 + (side > 0) * 3)))
            if kind == "izakaya":
                zl = z0 + 0.22 * (z1 - z0)
                if not (side < 0 and zl < 4.0):
                    items.append((zl, "lantern", (wall_x(side, 0.38), 2.15, zl, lt[k % len(lt)])))
                k += 1
                if z1 - z0 > 3.4:
                    zl2 = z0 + 0.92 * (z1 - z0)
                    items.append((zl2, "lantern", (wall_x(side, 0.38), 2.15, zl2, lt[k % len(lt)])))
                    k += 1
    signs = [(-1, 9.6, 3.0, 5.0, "スナック", (0.95, 0.92, 0.82), (0.7, 0.05, 0.05)),
             (1, 13.2, 3.1, 5.3, "居酒屋", (0.85, 0.08, 0.06), (1, 0.95, 0.85)),
             (-1, 18.0, 3.0, 4.8, "小料理", (0.95, 0.85, 0.55), (0.15, 0.05, 0.02)),
             (1, 22.0, 3.0, 4.6, "BAR", (0.2, 0.55, 0.9), (1, 1, 1)),
             (-1, 27.0, 3.0, 4.8, "旅館", (0.95, 0.92, 0.82), (0.1, 0.1, 0.1)),
             (1, 30.5, 3.0, 4.8, "麻雀", (0.9, 0.3, 0.1), (1, 1, 0.9)),
             (1, 6.0, 3.1, 5.6, "酒場", (0.95, 0.93, 0.85), (0.75, 0.05, 0.04))]
    for s in signs:
        items.append((s[1], "sign", s))
    for zw, n in ((11.0, 6), (20.0, 7), (29.0, 7)):
        items.append((zw, "wire", (zw, n)))
    items.append((2.5, "lantern", (XL + 0.5, 2.25, 2.5, "提灯")))
    items.append((3.85, "vending2", None))
    items.append((2.9, "vending1", None))
    items.append((7.5, "pole", None))
    items.append((15.0, "plants", (-1, 14.0)))
    items.append((6.0, "plants", (-1, 5.2)))
    items.append((24.0, "bike", (1, 23.0)))

    items.sort(key=lambda t: -t[0])
    for _, kind, a in items:
        if kind == "facade":
            facade(ctx, *a)
        elif kind == "lantern":
            lantern(ctx, *a, wire=2.8)
        elif kind == "sign":
            side, z, y0, y1, text, bg, fg = a
            sign_box(ctx, side, z, y0, y1, text, bg, fg)
        elif kind == "wire":
            wire_lanterns(ctx, a[0], a[1], texts="祭")
        elif kind == "vending1":
            vending(ctx, 2.9, 3.8, (0.78, 0.8, 0.84), (0.2, 0.5, 1.0), 1, side_ad=True)
        elif kind == "vending2":
            vending(ctx, 3.85, 4.75, (0.8, 0.08, 0.08), (1.0, 0.9, 0.8), 2)
        elif kind == "pole":
            pole_and_wires(ctx)
        elif kind == "plants":
            potted_plants(ctx, *a)
        elif kind == "bike":
            bicycle(ctx, *a)

    buf = np.frombuffer(surf.get_data(), np.uint8).reshape(H, W, 4)
    img = buf[:, :, [2, 1, 0]].astype(np.float32) / 255.0
    return img


# --------------------------------------------------------------- ground
def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def hash2(a, b):
    v = np.sin(a * 127.1 + b * 311.7) * 43758.5453
    return v - np.floor(v)


def base_line():
    """per-column screen y where vertical objects meet the ground (for mirroring)"""
    x = np.arange(W, dtype=np.float64) + 0.5
    dx = x - CX
    yb = np.full(W, HY + F * CAMH / ZEND)
    with np.errstate(divide="ignore", invalid="ignore"):
        yl = HY + CAMH * dx / (XL - CAMX)
        yr = HY + CAMH * dx / (XR - CAMX)
    yb = np.where(dx < 0, np.maximum(yb, yl), np.maximum(yb, yr))
    # vending machines (front face + near side face)
    Xf = XR - 0.72
    for z0, z1 in ((2.9, 3.8), (3.85, 4.75)):
        xa, _ = P(Xf, 0, z1)
        xb, _ = P(Xf, 0, z0)
        m = (x >= xa) & (x <= xb)
        yv = HY + CAMH * dx / (Xf - CAMX)
        yb = np.where(m, np.maximum(yb, yv), yb)
    xb0, yb0 = P(Xf, 0, 2.9)
    xb1, _ = P(XR, 0, 2.9)
    m = (x >= xb0) & (x <= xb1)
    yb = np.where(m, np.maximum(yb, yb0), yb)
    return yb.astype(np.float32)


def noise2(shape, sigma, seed):
    r = np.random.default_rng(seed)
    n = cv2.GaussianBlur(r.standard_normal(shape).astype(np.float32), (0, 0), sigma)
    return n / (n.std() + 1e-6)


def ground_pass(scene):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    xx += 0.5
    yy += 0.5
    yb = base_line()
    gmask = yy > yb[None, :]
    dy = np.maximum(yy - HY, 0.5)
    Z = F * CAMH / dy
    X = CAMX + (xx - CX) * Z / F
    pix = Z / F  # metres per pixel

    # --- stones: staggered rows of irregular slabs
    rowh = 0.42
    r = np.floor(Z / rowh)
    off = hash2(r, 1.0) * 0.9
    sw = 0.5 + 0.35 * hash2(r, 2.0)
    c = np.floor((X + off) / sw)
    fx = (X + off) / sw - c
    fz = Z / rowh - r
    d = np.minimum.reduce([fx * sw, (1 - fx) * sw, fz * rowh, (1 - fz) * rowh])
    jw = 0.010
    pz = pix * (Z / CAMH)  # vertical footprint grows with depth
    aa = np.maximum(pix, 0.5 * pz) + 1e-4
    joint = 1 - smoothstep(jw - aa, jw + aa, d)
    # beyond resolution, average joints in
    far = smoothstep(0.012, 0.05, aa)
    joint = joint * (1 - far) + 0.12 * far
    hs = hash2(r * 3.1 + 0.7, c * 1.7 + 0.3)
    hs2 = hash2(r * 5.3, c * 2.9)
    # fine grain in world space via screen noise scaled roughly
    grain = noise2((H, W), 1.2, 3) * 0.5 + noise2((H, W), 4, 4) * 0.5
    tone = 0.6 + 0.8 * hs ** 1.5 + 0.12 * grain
    alb = np.stack([0.085 * tone, 0.085 * tone * (0.97 + 0.05 * hs2), 0.09 * tone * (1.0 + 0.06 * hs2)], -1)
    bevel = smoothstep(0.0, 0.06, d)  # stones slightly domed -> darker edges
    alb *= (0.6 + 0.4 * bevel)[..., None]
    alb = alb * (1 - 0.7 * joint[..., None]) + np.array([0.03, 0.03, 0.033]) * 0.7 * joint[..., None]

    # --- puddles: low-frequency noise in world coords
    gx = np.clip((X - XL) / (XR - XL), -0.2, 1.2)
    nz = noise2((256, 64), 3.0, 11)
    pu = cv2.remap(nz, (gx * 63).astype(np.float32), (np.clip(Z / 40.0, 0, 1) * 255).astype(np.float32),
                   cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    nz2 = noise2((512, 128), 4.0, 12)
    pu2 = cv2.remap(nz2, (gx * 127).astype(np.float32), (np.clip(Z / 40.0, 0, 1) * 511).astype(np.float32),
                    cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    centre = 1 - np.abs(gx - 0.5) * 2  # puddles collect in the middle (worn path)
    pval = 0.75 * pu + 0.35 * pu2 + 0.6 * centre - 0.25
    puddle = smoothstep(0.15, 0.65, pval + 0.3 * joint)
    # far ground is effectively all mirror (grazing angle)

    # --- lighting of the ground (diffuse)
    amb = np.array([0.06, 0.07, 0.11], np.float32)
    light = np.zeros((H, W, 3), np.float32) + amb
    for (lx, ly, lz, col, pw) in LIGHTS:
        d2 = (X - lx) ** 2 + (Z - lz) ** 2 + ly ** 2
        cosv = ly / np.sqrt(d2)
        light += (pw * cosv / d2)[..., None] * np.array(col, np.float32) * 0.9
    diffuse = alb * light * 2.2

    # --- ripples (rain drops on the wet surface): height field in screen space
    hfield = np.zeros((H, W), np.float32)
    nr = 2600
    for _ in range(nr):
        rz = 1.2 + (37.0 - 1.2) * rng.random() ** 2.2
        rx = XL + (XR - XL) * rng.random()
        R = rng.uniform(0.02, 0.16)
        wv = 0.022
        ext = R + 3 * wv
        x0, y0 = P(rx - ext, 0, rz + ext)
        x1, y1 = P(rx + ext, 0, rz - ext)
        i0, i1 = int(max(0, math.floor(x0))), int(min(W, math.ceil(x1) + 1))
        j0, j1 = int(max(0, math.floor(y0))), int(min(H, math.ceil(y1) + 1))
        if i1 - i0 < 2 or j1 - j0 < 1:
            continue
        Xs = X[j0:j1, i0:i1]
        Zs = Z[j0:j1, i0:i1]
        dd = np.sqrt((Xs - rx) ** 2 + (Zs - rz) ** 2)
        amp = 1.0 / (1 + 12 * R)
        amp *= float(np.clip((0.035 * F / rz - 2.0) / 3.0, 0, 1))  # fade sub-pixel ripples
        if amp <= 0:
            continue
        hfield[j0:j1, i0:i1] += amp * np.sin((dd - R) * 2 * math.pi / 0.035) * np.exp(-((dd - R) / wv) ** 2)
    gyh, gxh = np.gradient(hfield)
    wet_ripple = 0.35 + 0.65 * puddle
    dxs = gxh * 6.0 * wet_ripple
    dys = gyh * 10.0 * wet_ripple

    # --- reflection of the scene: mirror about the base line per column
    src_y = 2 * yb[None, :] - yy + dys
    src_x = xx - 0.5 + dxs
    # surface waviness of stones (non puddle) -> small jitter
    jit = noise2((H, W), 1.5, 21) * (1 - puddle) * 1.5
    refl_sharp = cv2.remap(scene, src_x.astype(np.float32), (src_y + jit - 0.5).astype(np.float32),
                           cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    # glossy (blurred, vertically streaked) reflection for wet stone
    refl_blur = cv2.GaussianBlur(refl_sharp, (0, 0), sigmaX=2.5, sigmaY=14)
    refl_blur2 = cv2.GaussianBlur(refl_sharp, (0, 0), sigmaX=6, sigmaY=30)
    rough = (1 - puddle)
    refl = refl_sharp * puddle[..., None] + (0.6 * refl_blur + 0.4 * refl_blur2) * rough[..., None]
    # Fresnel-ish: more reflective toward grazing angles (far)
    cos_t = CAMH / np.sqrt(CAMH ** 2 + Z ** 2)
    fres = 0.04 + 0.96 * (1 - cos_t) ** 5
    k_stone = np.clip(0.30 + 0.5 * fres, 0, 1) * (1 - 0.6 * joint)
    k_pud = np.clip(0.62 + 0.38 * fres, 0, 1)
    R = k_stone * (1 - puddle) + k_pud * puddle
    # puddles are dark water: reduce diffuse
    diffuse = diffuse * (1 - 0.7 * puddle[..., None])
    ground = diffuse * (1 - 0.5 * R[..., None]) + refl * R[..., None]
    # specular glints from ripples catching light
    glint = np.clip(hfield, 0, None) * puddle * 0.25
    ground += glint[..., None] * cv2.GaussianBlur(refl_sharp, (0, 0), 6)

    out = np.where(gmask[..., None], ground, scene)
    # soft contact shadow / AO along the base of walls
    ao = smoothstep(0, 22, (yy - yb[None, :])) * 0.4 + 0.6
    out = np.where(gmask[..., None], out * ao[..., None], out)
    return out, gmask


# ----------------------------------------------------------------- post
def add_haze(img):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt(((xx - CX) / 1.3) ** 2 + ((yy - HY + 40) * 1.0) ** 2)
    h = np.exp(-d / 210.0) * 0.22
    col = np.array([0.55, 0.42, 0.5], np.float32)
    return img * (1 - 0.5 * h[..., None]) + col * h[..., None]


def bloom(img):
    lum = img.max(-1)
    bright = img * smoothstep(0.55, 1.0, lum)[..., None]
    out = img.copy()
    for s, w in ((4, 0.35), (12, 0.35), (32, 0.35), (80, 0.3)):
        out += cv2.GaussianBlur(bright, (0, 0), s) * w
    return out


def rain(img):
    surf = cairo.ImageSurface(cairo.FORMAT_A8, W, H)
    ctx = cairo.Context(surf)
    ctx.set_line_cap(cairo.LINE_CAP_ROUND)
    for layer, (n, lmin, lmax, wdt, amin, amax) in enumerate(
            [(3500, 8, 22, 0.8, 0.08, 0.25), (1300, 25, 60, 1.1, 0.08, 0.22), (120, 80, 160, 2.0, 0.05, 0.12)]):
        for _ in range(n):
            x = rng.uniform(-100, W + 50)
            y = rng.uniform(-100, H)
            ln = rng.uniform(lmin, lmax)
            ang = math.radians(rng.normal(9, 1.5))
            ctx.move_to(x, y)
            ctx.line_to(x + math.sin(ang) * ln, y + math.cos(ang) * ln)
            ctx.set_line_width(wdt)
            ctx.set_source_rgba(0, 0, 0, rng.uniform(amin, amax))
            ctx.stroke()
    a = np.frombuffer(surf.get_data(), np.uint8).reshape(H, surf.get_stride())[:, :W].astype(np.float32) / 255
    a = cv2.GaussianBlur(a, (0, 0), 0.6)
    env = cv2.GaussianBlur(img, (0, 0), 25)
    col = 0.10 + 1.6 * env
    return img + a[..., None] * col


def tonemap(img):
    x = np.clip(img, 0, None)
    # soft shoulder
    y = np.where(x < 0.8, x, 0.8 + 0.2 * (1 - np.exp(-(x - 0.8) / 0.2)))
    return np.clip(y, 0, 1)


def vignette(img):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
    v = 1 - 0.38 * smoothstep(0.6, 1.45, d)
    return img * v[..., None]


def main(out_path):
    scene = build_scene()
    img, gmask = ground_pass(scene)
    img = add_haze(img)
    img = bloom(img)
    img = rain(img)
    img = vignette(img)
    img = tonemap(img)
    # gentle grain
    img += noise2((H, W), 0.6, 99)[..., None] * 0.006
    out = (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    cv2.imwrite(out_path, out[:, :, ::-1])
    print("wrote", out_path, out.shape)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "out/final.png")
