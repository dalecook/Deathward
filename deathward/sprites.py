# DEATHWARD -- a turn-based roguelike where failure is the only progression.
# Copyright (C) 2026 Dale Cook
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# this program. If not, see <https://www.gnu.org/licenses/>.

"""Procedural sprite art. No asset files -- every creature is drawn with polygons.

Each sprite is rendered once into a supersampled surface and smoothscaled down, so
it gets cheap anti-aliasing, and then cached forever. Per-frame cost is a blit.

The art has one job beyond looking like something: it must make a creature legible
at a glance, because this game is about reading the room. A rat reads as a rat. The
two rats read as *different* rats -- the angry rat is a small brown animal with a
grievance, the plague rat is a bloated green thing that travels in packs -- because
"which rat is that" is a decision the player has to make on floor 2.

The one thing deliberately NOT drawn well is a monster you have not codexed: it is a
featureless silhouette. That is not laziness, it is the entire game.
"""

import math

import pygame

from . import config, fontcache

SS = 3                            # supersample factor
_CACHE = {}


def _new(S):
    return pygame.Surface((S, S), pygame.SRCALPHA)


def _finish(big):
    return pygame.transform.smoothscale(big, (config.TILE, config.TILE))


def _shade(c, k):
    return (max(0, min(255, int(c[0] * k))),
            max(0, min(255, int(c[1] * k))),
            max(0, min(255, int(c[2] * k))))


def _dimmed(surf, k=0.45):
    out = surf.copy()
    dark = pygame.Surface(out.get_size(), pygame.SRCALPHA)
    dark.fill((0, 0, 0, int(255 * (1 - k))))
    out.blit(dark, (0, 0))
    return out


def _ell(s, col, cx, cy, rx, ry):
    pygame.draw.ellipse(s, col, (cx - rx, cy - ry, rx * 2, ry * 2))


def _circ(s, col, cx, cy, r):
    pygame.draw.circle(s, col, (int(cx), int(cy)), int(r))


def _poly(s, col, pts):
    pygame.draw.polygon(s, col, pts)


def _line(s, col, a, b, w):
    pygame.draw.line(s, col, a, b, int(w))


def _curve(s, col, pts, w):
    pygame.draw.lines(s, col, False, pts, int(w))


# ---------------------------------------------------------------- terrain
def floor(x, y, lit):
    v = (x * 73856093 ^ y * 19349663) % 4
    key = ("floor", v, lit)
    if key in _CACHE:
        return _CACHE[key]
    S = config.TILE * SS
    s = _new(S)
    base = config.FLOOR_LIT if lit else config.SEEN
    s.fill(base)
    # flagstone: a grout seam and a little grain, so the floor is not a flat colour
    grout = _shade(base, 0.82)
    pygame.draw.line(s, grout, (0, 0), (S, 0), SS)
    pygame.draw.line(s, grout, (0, 0), (0, S), SS)
    speck = _shade(base, 1.18)
    for i in range(3):
        px = (v * 17 + i * 29) % (S - SS * 4) + SS * 2
        py = (v * 41 + i * 53) % (S - SS * 4) + SS * 2
        pygame.draw.circle(s, speck, (px, py), SS)
    if v == 3:
        pygame.draw.line(s, _shade(base, 0.9), (S * 0.2, S * 0.7), (S * 0.5, S * 0.72), SS)
    _CACHE[key] = _finish(s)
    return _CACHE[key]


def wall(x, y, lit):
    v = (x * 83492791 ^ y * 29499439) % 3
    key = ("wall", v, lit)
    if key in _CACHE:
        return _CACHE[key]
    S = config.TILE * SS
    s = _new(S)
    base = config.WALL_LIT if lit else config.SEEN_WALL
    s.fill(base)
    mortar = _shade(base, 0.7)
    top = _shade(base, 1.15)
    # brick courses, offset every other row
    h = S // 3
    for row in range(3):
        yy = row * h
        pygame.draw.line(s, mortar, (0, yy), (S, yy), SS)
        off = (S // 2) if (row + v) % 2 else 0
        pygame.draw.line(s, mortar, (off, yy), (off, yy + h), SS)
        pygame.draw.line(s, top, (0, yy + SS), (S, yy + SS), 1)
    _CACHE[key] = _finish(s)
    return _CACHE[key]


# ---------------------------------------------------------------- creatures
def _rat(s, S, body, dark, eye, plague):
    """A rat. Bigger, greener and more bloated if it is the plague kind."""
    scale = 1.0 if not plague else 1.14
    cx, cy = S * 0.5, S * 0.58
    bw, bh = S * 0.30 * scale, S * 0.22 * scale

    # tail: a curl behind it
    tail = [(cx + bw * 0.9, cy + bh * 0.2),
            (cx + bw * 1.5, cy + bh * 0.5),
            (cx + bw * 1.9, cy - bh * 0.1),
            (cx + bw * 1.7, cy - bh * 0.6)]
    _curve(s, dark, tail, S * 0.035)

    # haunch and body
    _ell(s, body, cx + bw * 0.15, cy, bw * 0.95, bh)
    if plague:
        # sickly blotches
        _circ(s, _shade(body, 0.72), cx + bw * 0.4, cy - bh * 0.35, S * 0.045)
        _circ(s, _shade(body, 0.72), cx - bw * 0.2, cy + bh * 0.25, S * 0.035)

    # head, thrust forward-left
    hx, hy = cx - bw * 0.75, cy - bh * 0.25
    _ell(s, body, hx, hy, bw * 0.55, bh * 0.72)
    # snout
    _poly(s, body, [(hx - bw * 0.45, hy - bh * 0.05),
                    (hx - bw * 1.15, hy + bh * 0.30),
                    (hx - bw * 0.40, hy + bh * 0.45)])
    _circ(s, _shade(body, 0.6), hx - bw * 1.05, hy + bh * 0.28, S * 0.022)

    # ears
    _circ(s, _shade(body, 0.88), hx + bw * 0.05, hy - bh * 0.72, S * 0.075)
    _circ(s, _shade(body, 0.62), hx + bw * 0.05, hy - bh * 0.72, S * 0.042)
    _circ(s, _shade(body, 0.88), hx - bw * 0.5, hy - bh * 0.78, S * 0.06)

    # legs
    for lx in (cx - bw * 0.35, cx + bw * 0.6):
        _line(s, dark, (lx, cy + bh * 0.75), (lx, cy + bh * 1.25), S * 0.045)

    # eye
    _circ(s, eye, hx - bw * 0.25, hy - bh * 0.05, S * 0.045)
    _circ(s, (255, 255, 255), hx - bw * 0.28, hy - bh * 0.12, S * 0.016)

    if not plague:
        # an angry eyebrow. it is furious and it wants you to know.
        _line(s, dark, (hx - bw * 0.55, hy - bh * 0.55),
              (hx + bw * 0.05, hy - bh * 0.25), S * 0.035)
        # bared teeth
        _poly(s, (255, 255, 255), [(hx - bw * 0.95, hy + bh * 0.42),
                                   (hx - bw * 0.80, hy + bh * 0.42),
                                   (hx - bw * 0.88, hy + bh * 0.70)])


def _kobold(s, S, body, dark):
    """A small reptile soldier: snouted head, two pale horns, a spear, and the
    posture of something that will absolutely run for help."""
    cx = S * 0.5
    hide = _shade(body, 0.72)
    horn = (232, 224, 200)

    # spear first, so the body overlaps it
    _line(s, (146, 110, 74), (cx + S * 0.30, S * 0.10), (cx + S * 0.20, S * 0.94), S * 0.045)
    _poly(s, (214, 222, 232), [(cx + S * 0.31, S * 0.14), (cx + S * 0.24, S * 0.00),
                               (cx + S * 0.38, S * 0.06)])

    # torso + legs
    _poly(s, body, [(cx - S * 0.15, S * 0.78), (cx + S * 0.13, S * 0.78),
                    (cx + S * 0.10, S * 0.50), (cx - S * 0.12, S * 0.50)])
    _poly(s, hide, [(cx - S * 0.09, S * 0.74), (cx + S * 0.07, S * 0.74),
                    (cx + S * 0.05, S * 0.54), (cx - S * 0.07, S * 0.54)])
    _line(s, dark, (cx - S * 0.08, S * 0.78), (cx - S * 0.11, S * 0.93), S * 0.055)
    _line(s, dark, (cx + S * 0.07, S * 0.78), (cx + S * 0.10, S * 0.93), S * 0.055)
    # arm gripping the shaft
    _line(s, body, (cx + S * 0.08, S * 0.58), (cx + S * 0.24, S * 0.56), S * 0.05)

    # head: big enough to read, snout thrust forward
    hx, hy = cx - S * 0.02, S * 0.33
    _circ(s, body, hx, hy, S * 0.165)
    _poly(s, body, [(hx - S * 0.10, hy - S * 0.02), (hx - S * 0.32, hy + S * 0.08),
                    (hx - S * 0.09, hy + S * 0.13)])
    _circ(s, dark, hx - S * 0.29, hy + S * 0.07, S * 0.02)      # nostril
    # jaw line
    _line(s, dark, (hx - S * 0.28, hy + S * 0.09), (hx - S * 0.06, hy + S * 0.12), S * 0.02)

    # horns: pale, swept back, unmistakable
    _poly(s, horn, [(hx - S * 0.10, hy - S * 0.13), (hx - S * 0.24, hy - S * 0.34),
                    (hx - S * 0.02, hy - S * 0.17)])
    _poly(s, horn, [(hx + S * 0.09, hy - S * 0.13), (hx + S * 0.20, hy - S * 0.36),
                    (hx + S * 0.01, hy - S * 0.17)])

    # a mean yellow eye
    _circ(s, (252, 226, 96), hx - S * 0.05, hy - S * 0.01, S * 0.045)
    _circ(s, (20, 26, 16), hx - S * 0.05, hy - S * 0.01, S * 0.020)


def _spitter(s, S, body, dark):
    cx, cy = S * 0.5, S * 0.62
    # squat toad body
    _ell(s, body, cx, cy, S * 0.32, S * 0.24)
    _ell(s, _shade(body, 0.8), cx, cy + S * 0.06, S * 0.30, S * 0.16)
    # acid sacs
    _circ(s, _shade(body, 1.25), cx - S * 0.18, cy - S * 0.12, S * 0.07)
    _circ(s, _shade(body, 1.25), cx + S * 0.18, cy - S * 0.12, S * 0.07)
    # eyes on top
    for ex in (cx - S * 0.12, cx + S * 0.12):
        _circ(s, (245, 250, 230), ex, cy - S * 0.24, S * 0.075)
        _circ(s, (20, 30, 16), ex, cy - S * 0.24, S * 0.038)
    # wide mouth
    pygame.draw.arc(s, dark, (cx - S * 0.22, cy - S * 0.05, S * 0.44, S * 0.28),
                    math.pi, 2 * math.pi, int(S * 0.035))
    # a drip of acid
    _circ(s, _shade(body, 1.35), cx, cy + S * 0.22, S * 0.04)
    _poly(s, _shade(body, 1.35), [(cx - S * 0.03, cy + S * 0.20),
                                  (cx + S * 0.03, cy + S * 0.20),
                                  (cx, cy + S * 0.30)])
    # legs
    _line(s, dark, (cx - S * 0.28, cy + S * 0.14), (cx - S * 0.34, cy + S * 0.26), S * 0.05)
    _line(s, dark, (cx + S * 0.28, cy + S * 0.14), (cx + S * 0.34, cy + S * 0.26), S * 0.05)


def _brute(s, S, body, dark):
    cx = S * 0.5
    # the head sits DOWN in the shoulders -- no neck. it is all arm and no thought.
    _circ(s, _shade(body, 0.86), cx, S * 0.36, S * 0.135)
    # enormous sloped shoulders over the top of it
    _poly(s, body, [(cx - S * 0.36, S * 0.50), (cx - S * 0.20, S * 0.38),
                    (cx + S * 0.20, S * 0.38), (cx + S * 0.36, S * 0.50),
                    (cx + S * 0.24, S * 0.80), (cx - S * 0.24, S * 0.80)])
    # brow ridge and two small mean eyes under it
    _line(s, dark, (cx - S * 0.11, S * 0.33), (cx + S * 0.11, S * 0.33), S * 0.055)
    _circ(s, (255, 210, 120), cx - S * 0.05, S * 0.38, S * 0.028)
    _circ(s, (255, 210, 120), cx + S * 0.05, S * 0.38, S * 0.028)
    _line(s, dark, (cx - S * 0.05, S * 0.44), (cx + S * 0.05, S * 0.44), S * 0.025)
    # arms ending in fists the size of its head
    _line(s, _shade(body, 0.85), (cx - S * 0.30, S * 0.48), (cx - S * 0.40, S * 0.70), S * 0.10)
    _line(s, _shade(body, 0.85), (cx + S * 0.30, S * 0.48), (cx + S * 0.40, S * 0.70), S * 0.10)
    _circ(s, _shade(body, 1.1), cx - S * 0.41, S * 0.76, S * 0.115)
    _circ(s, _shade(body, 1.1), cx + S * 0.41, S * 0.76, S * 0.115)
    # legs
    _line(s, dark, (cx - S * 0.12, S * 0.80), (cx - S * 0.14, S * 0.94), S * 0.075)
    _line(s, dark, (cx + S * 0.12, S * 0.80), (cx + S * 0.14, S * 0.94), S * 0.075)


def _wraith(s, S, body, dark):
    cx = S * 0.5
    # hood and shoulders
    _poly(s, body, [(cx, S * 0.14), (cx + S * 0.26, S * 0.44), (cx + S * 0.30, S * 0.74),
                    (cx - S * 0.30, S * 0.74), (cx - S * 0.26, S * 0.44)])
    # tattered hem: it does not have feet
    hem = [(cx - S * 0.30, S * 0.74)]
    for i in range(6):
        x = cx - S * 0.30 + (S * 0.60) * (i / 5.0)
        hem.append((x, S * (0.86 if i % 2 else 0.76)))
    hem.append((cx + S * 0.30, S * 0.74))
    _poly(s, body, hem)
    # the dark inside the hood -- kept small, so it reads as a shadowed face and
    # not as an open mouth
    _ell(s, (14, 10, 22), cx, S * 0.37, S * 0.115, S * 0.135)
    # two cold eyes
    _circ(s, (220, 235, 255), cx - S * 0.05, S * 0.36, S * 0.032)
    _circ(s, (220, 235, 255), cx + S * 0.05, S * 0.36, S * 0.032)
    # a suggestion of hands
    _circ(s, _shade(body, 1.2), cx - S * 0.28, S * 0.58, S * 0.05)
    _circ(s, _shade(body, 1.2), cx + S * 0.28, S * 0.58, S * 0.05)


def _mimic(s, S, body, dark):
    cx, cy = S * 0.5, S * 0.58
    # a chest that has stopped pretending
    _poly(s, body, [(cx - S * 0.34, cy + S * 0.26), (cx + S * 0.34, cy + S * 0.26),
                    (cx + S * 0.30, cy - S * 0.06), (cx - S * 0.30, cy - S * 0.06)])
    # the lid, thrown back
    _poly(s, _shade(body, 0.8), [(cx - S * 0.32, cy - S * 0.10), (cx + S * 0.32, cy - S * 0.10),
                                 (cx + S * 0.36, cy - S * 0.36), (cx - S * 0.36, cy - S * 0.36)])
    # maw
    _poly(s, (30, 10, 14), [(cx - S * 0.28, cy - S * 0.08), (cx + S * 0.28, cy - S * 0.08),
                            (cx + S * 0.24, cy + S * 0.12), (cx - S * 0.24, cy + S * 0.12)])
    # teeth, top and bottom
    for i in range(6):
        x = cx - S * 0.26 + i * S * 0.104
        _poly(s, (250, 250, 240), [(x, cy - S * 0.08), (x + S * 0.08, cy - S * 0.08),
                                   (x + S * 0.04, cy + S * 0.02)])
        _poly(s, (250, 250, 240), [(x, cy + S * 0.12), (x + S * 0.08, cy + S * 0.12),
                                   (x + S * 0.04, cy + S * 0.02)])
    # tongue
    _ell(s, (200, 70, 90), cx, cy + S * 0.08, S * 0.09, S * 0.04)
    # eyes on the lid
    _circ(s, (255, 220, 120), cx - S * 0.14, cy - S * 0.24, S * 0.05)
    _circ(s, (255, 220, 120), cx + S * 0.14, cy - S * 0.24, S * 0.05)
    _circ(s, (20, 10, 10), cx - S * 0.14, cy - S * 0.24, S * 0.024)
    _circ(s, (20, 10, 10), cx + S * 0.14, cy - S * 0.24, S * 0.024)


def _flicker(s, S, body, dark):
    """A half-there thing of pale light -- a hunched sliver of a body, a wisp of a
    tail, and one bright blade-edge of an arm. Drawn faint, like it might not be
    fully here."""
    cx, cy = S * 0.5, S * 0.52
    glow = _shade(body, 1.2)
    # a soft halo -- it is not solid
    _circ(s, (*body[:3],), cx, cy, S * 0.30)
    _circ(s, _shade(body, 0.7), cx, cy, S * 0.30)
    # a narrow, tapering body that trails off into nothing
    _poly(s, glow, [(cx - S * 0.08, S * 0.30), (cx + S * 0.10, S * 0.32),
                    (cx + S * 0.06, S * 0.70), (cx - S * 0.02, S * 0.82),
                    (cx - S * 0.12, S * 0.66)])
    # trailing wisps at the hem
    for i in range(3):
        wx = cx - S * 0.10 + i * S * 0.10
        _line(s, _shade(body, 0.8), (wx, S * 0.68), (wx + S * 0.02, S * 0.90), S * 0.02)
    # a bright thin blade of an arm
    _line(s, (235, 250, 255), (cx + S * 0.06, S * 0.40), (cx + S * 0.30, S * 0.24),
          S * 0.025)
    # two pinprick eyes
    _circ(s, (255, 255, 255), cx - S * 0.05, S * 0.40, S * 0.028)
    _circ(s, (255, 255, 255), cx + S * 0.05, S * 0.40, S * 0.028)
    _circ(s, (90, 170, 210), cx - S * 0.05, S * 0.40, S * 0.012)
    _circ(s, (90, 170, 210), cx + S * 0.05, S * 0.40, S * 0.012)


def _orc(s, S, body, dark):
    """A hunched brute of a thing, jaw thrust forward, two white tusks jutting up out
    of it, a crude cleaver in one fist."""
    cx = S * 0.5
    hide = body
    # the cleaver, held out to one side
    _line(s, (110, 96, 78), (cx + S * 0.30, S * 0.30), (cx + S * 0.26, S * 0.78),
          S * 0.04)
    _poly(s, (168, 174, 184), [(cx + S * 0.22, S * 0.20), (cx + S * 0.42, S * 0.28),
                               (cx + S * 0.40, S * 0.44), (cx + S * 0.24, S * 0.40)])
    # a hunched, heavy body
    _poly(s, hide, [(cx - S * 0.24, S * 0.44), (cx + S * 0.20, S * 0.46),
                    (cx + S * 0.24, S * 0.82), (cx - S * 0.22, S * 0.82)])
    _poly(s, _shade(hide, 0.82), [(cx - S * 0.10, S * 0.50), (cx + S * 0.08, S * 0.51),
                                  (cx + S * 0.06, S * 0.74), (cx - S * 0.08, S * 0.74)])
    # legs
    _line(s, dark, (cx - S * 0.10, S * 0.82), (cx - S * 0.12, S * 0.93), S * 0.06)
    _line(s, dark, (cx + S * 0.10, S * 0.82), (cx + S * 0.12, S * 0.93), S * 0.06)
    # a low, forward-thrust head with a heavy jaw
    hx, hy = cx - S * 0.06, S * 0.36
    _circ(s, hide, hx, hy, S * 0.15)
    _poly(s, hide, [(hx - S * 0.13, hy + S * 0.02), (hx - S * 0.02, hy + S * 0.20),
                    (hx + S * 0.14, hy + S * 0.10)])         # jutting jaw
    # two tusks
    _poly(s, (232, 230, 216), [(hx - S * 0.06, hy + S * 0.14), (hx - S * 0.09, hy - S * 0.02),
                               (hx - S * 0.02, hy + S * 0.12)])
    _poly(s, (232, 230, 216), [(hx + S * 0.06, hy + S * 0.14), (hx + S * 0.09, hy - S * 0.02),
                               (hx + S * 0.02, hy + S * 0.12)])
    # a small red eye and a heavy brow
    _line(s, dark, (hx - S * 0.11, hy - S * 0.06), (hx + S * 0.05, hy - S * 0.04), S * 0.03)
    _circ(s, (230, 90, 70), hx - S * 0.04, hy, S * 0.03)


def _beholder(s, S, body, dark):
    """A single floating eye, lidded and lashed, trailing a few thin tendrils. The
    iris is a cold, pale blue -- the colour of what it does to you."""
    cx, cy = S * 0.5, S * 0.48
    flesh = body
    # the orb
    _circ(s, flesh, cx, cy, S * 0.30)
    _circ(s, _shade(flesh, 0.8), cx, cy + S * 0.04, S * 0.28)
    # veins
    for a in (0.4, 1.6, 2.8, 4.0, 5.2):
        _line(s, _shade(flesh, 0.7),
              (cx + math.cos(a) * S * 0.10, cy + math.sin(a) * S * 0.10),
              (cx + math.cos(a) * S * 0.28, cy + math.sin(a) * S * 0.28), S * 0.012)
    # the eye itself
    _ell(s, (240, 244, 250), cx, cy, S * 0.18, S * 0.14)
    _circ(s, (120, 180, 240), cx, cy, S * 0.095)         # cold blue iris
    _circ(s, (10, 14, 26), cx, cy, S * 0.045)            # pupil
    _circ(s, (255, 255, 255), cx - S * 0.03, cy - S * 0.03, S * 0.02)
    # a heavy lid
    pygame.draw.arc(s, _shade(flesh, 0.7),
                    (cx - S * 0.19, cy - S * 0.16, S * 0.38, S * 0.24),
                    0.2, math.pi - 0.2, int(S * 0.03))
    # trailing tendrils under it
    for dx in (-0.16, 0.0, 0.16):
        _curve(s, _shade(flesh, 0.75),
               [(cx + S * dx, cy + S * 0.26), (cx + S * (dx + 0.04), cy + S * 0.36),
                (cx + S * dx, cy + S * 0.46), (cx + S * (dx - 0.02), cy + S * 0.56)],
               S * 0.018)


def _golem(s, S, body, dark):
    """A slab of rock roughly shaped like a man. Blocky, cracked, mossy in the seams,
    with two dim green eyes buried in it."""
    cx = S * 0.5
    stone = body
    # a squat, wide, blocky body
    _poly(s, stone, [(cx - S * 0.32, S * 0.40), (cx + S * 0.32, S * 0.40),
                     (cx + S * 0.28, S * 0.84), (cx - S * 0.28, S * 0.84)])
    # slab shoulders and a head sunk between them
    _poly(s, _shade(stone, 1.12), [(cx - S * 0.34, S * 0.40), (cx - S * 0.18, S * 0.30),
                                   (cx + S * 0.18, S * 0.30), (cx + S * 0.34, S * 0.40)])
    _poly(s, _shade(stone, 0.9), [(cx - S * 0.14, S * 0.36), (cx + S * 0.14, S * 0.36),
                                  (cx + S * 0.11, S * 0.20), (cx - S * 0.11, S * 0.20)])
    # fists like boulders
    _circ(s, _shade(stone, 1.05), cx - S * 0.36, S * 0.66, S * 0.12)
    _circ(s, _shade(stone, 1.05), cx + S * 0.36, S * 0.66, S * 0.12)
    # cracks and moss in the seams
    for (ax, ay, bx, by) in ((-0.10, 0.44, -0.04, 0.64), (0.14, 0.46, 0.06, 0.70),
                             (-0.20, 0.54, -0.24, 0.72)):
        _line(s, dark, (cx + S * ax, S * ay), (cx + S * bx, S * by), S * 0.02)
    _circ(s, (96, 132, 80), cx - S * 0.16, S * 0.50, S * 0.02)    # moss
    _circ(s, (96, 132, 80), cx + S * 0.10, S * 0.60, S * 0.018)
    # two dim eyes
    _circ(s, (150, 210, 130), cx - S * 0.05, S * 0.27, S * 0.028)
    _circ(s, (150, 210, 130), cx + S * 0.05, S * 0.27, S * 0.028)


def _poltergeist(s, S, body, dark):
    """A formless wisp of a thing -- no solid edge anywhere. A pale, rounded veil that
    trails off into torn ribbons at the bottom, two hollow dark eyes, and a thin
    open mouth. Drawn to look barely condensed out of the air, so that even at full
    reveal it reads as 'not really here'."""
    cx = S * 0.5
    pale = _shade(body, 1.05)
    # a soft outer haze -- it has no skin, only a blur where it fades into the dark
    _circ(s, _shade(body, 0.7), cx, S * 0.44, S * 0.33)
    # the body: a rounded veil, widest at the head, tapering down
    _poly(s, pale, [(cx, S * 0.14),
                    (cx + S * 0.28, S * 0.34), (cx + S * 0.30, S * 0.60),
                    (cx + S * 0.22, S * 0.74), (cx - S * 0.22, S * 0.74),
                    (cx - S * 0.30, S * 0.60), (cx - S * 0.28, S * 0.34)])
    # torn ribbons at the hem, uneven, trailing away into nothing
    tatters = [(-0.24, 0.90), (-0.12, 0.80), (0.0, 0.92), (0.12, 0.82), (0.24, 0.90)]
    hem_y = 0.72
    for i in range(len(tatters) - 1):
        (ax, ay), (bx, by) = tatters[i], tatters[i + 1]
        _poly(s, _shade(pale, 0.9),
              [(cx + S * ax, S * hem_y), (cx + S * bx, S * hem_y),
               (cx + S * (ax + bx) * 0.5, S * max(ay, by))])
    # a lighter inner glow, so it isn't a flat blob
    _ell(s, _shade(body, 1.18), cx, S * 0.42, S * 0.16, S * 0.22)
    # two hollow eyes and a thin, drawn-down mouth -- a face half-forming
    _ell(s, (26, 30, 42), cx - S * 0.09, S * 0.40, S * 0.045, S * 0.075)
    _ell(s, (26, 30, 42), cx + S * 0.09, S * 0.40, S * 0.045, S * 0.075)
    _ell(s, (26, 30, 42), cx, S * 0.58, S * 0.05, S * 0.03)


def _warden(s, S, body, dark):
    cx = S * 0.5
    # a big armoured silhouette with a horned helm
    _poly(s, body, [(cx - S * 0.36, S * 0.46), (cx + S * 0.36, S * 0.46),
                    (cx + S * 0.26, S * 0.86), (cx - S * 0.26, S * 0.86)])
    _poly(s, _shade(body, 0.75), [(cx - S * 0.20, S * 0.46), (cx + S * 0.20, S * 0.46),
                                  (cx + S * 0.14, S * 0.78), (cx - S * 0.14, S * 0.78)])
    # pauldrons
    _circ(s, _shade(body, 1.12), cx - S * 0.34, S * 0.48, S * 0.11)
    _circ(s, _shade(body, 1.12), cx + S * 0.34, S * 0.48, S * 0.11)
    # helm
    _poly(s, _shade(body, 0.92), [(cx - S * 0.15, S * 0.36), (cx + S * 0.15, S * 0.36),
                                  (cx + S * 0.12, S * 0.16), (cx - S * 0.12, S * 0.16)])
    # horns
    _poly(s, (240, 230, 220), [(cx - S * 0.13, S * 0.20), (cx - S * 0.34, S * 0.04),
                               (cx - S * 0.16, S * 0.10)])
    _poly(s, (240, 230, 220), [(cx + S * 0.13, S * 0.20), (cx + S * 0.34, S * 0.04),
                               (cx + S * 0.16, S * 0.10)])
    # a visor slit full of light
    pygame.draw.rect(s, (255, 240, 150),
                     (cx - S * 0.10, S * 0.27, S * 0.20, S * 0.035))
    # fists
    _circ(s, _shade(body, 1.05), cx - S * 0.40, S * 0.74, S * 0.10)
    _circ(s, _shade(body, 1.05), cx + S * 0.40, S * 0.74, S * 0.10)


def _syrinx(s, S, body, dark):
    """A slender, unassuming figure -- nothing about her reads as a boss. Windswept
    hair trailing sideways and a thin, almost hollow robe, matching her theme:
    lightness (Windfang) and stone-hiding (Shademail)."""
    cx = S * 0.5
    # a slim robed body, narrower than any of the humanoid brutes
    _poly(s, body, [(cx - S * 0.16, S * 0.34), (cx + S * 0.16, S * 0.34),
                    (cx + S * 0.20, S * 0.86), (cx - S * 0.20, S * 0.86)])
    _poly(s, _shade(body, 0.82), [(cx - S * 0.09, S * 0.34), (cx + S * 0.09, S * 0.34),
                                  (cx + S * 0.11, S * 0.70), (cx - S * 0.11, S * 0.70)])
    # a small, plain head -- deliberately unremarkable
    _circ(s, _shade(body, 1.1), cx, S * 0.22, S * 0.12)
    # hair blown sideways -- the only unusual thing about her silhouette
    for dy in (-0.04, 0.02, 0.08):
        _curve(s, _shade(body, 0.85),
               [(cx - S * 0.02, S * (0.14 + dy)),
                (cx - S * 0.30, S * (0.10 + dy)),
                (cx - S * 0.46, S * (0.16 + dy))], S * 0.02)
    # thin arms, close to the body
    _line(s, _shade(body, 0.9), (cx - S * 0.16, S * 0.42), (cx - S * 0.24, S * 0.62), S * 0.045)
    _line(s, _shade(body, 0.9), (cx + S * 0.16, S * 0.42), (cx + S * 0.24, S * 0.62), S * 0.045)
    # two quiet eyes -- nothing predatory
    _circ(s, (30, 34, 26), cx - S * 0.045, S * 0.21, S * 0.018)
    _circ(s, (30, 34, 26), cx + S * 0.045, S * 0.21, S * 0.018)


_MONSTER_DRAW = {
    "angry_rat": lambda s, S, c, d: _rat(s, S, c, d, (240, 90, 70), plague=False),
    "rat":       lambda s, S, c, d: _rat(s, S, c, d, (230, 230, 140), plague=True),
    "kobold":    _kobold,
    "spitter":   _spitter,
    "brute":     _brute,
    "wraith":    _wraith,
    "mimic":     _mimic,
    "orc":       _orc,
    "flicker":   _flicker,
    "beholder":  _beholder,
    "golem":     _golem,
    "poltergeist": _poltergeist,
    "warden":    _warden,
    "syrinx":    _syrinx,
}


def monster(key, color, alpha=255):
    ck = ("mon", key, color, alpha)
    if ck in _CACHE:
        return _CACHE[ck]
    S = config.TILE * SS
    s = _new(S)
    fn = _MONSTER_DRAW.get(key)
    if fn:
        fn(s, S, color, _shade(color, 0.55))
    out = _finish(s)
    if alpha < 255:
        out.set_alpha(alpha)
    _CACHE[ck] = out
    return out


def dimmed(surf, k=0.45):
    """A cached darkened copy -- for things remembered but not currently in sight."""
    ck = ("dim", id(surf), k)
    if ck not in _CACHE:
        _CACHE[ck] = _dimmed(surf, k)
    return _CACHE[ck]


def slain(key, color):
    """A monster you killed: tipped onto its side, drained of colour, in a pool.

    Rotating the whole creature 90 degrees is the most legible "this thing is dead"
    signal available -- a body lying down reads instantly, at a glance, from across
    the room, for every creature in the game and without redrawing a single face.
    """
    ck = ("slain", key, color)
    if ck in _CACHE:
        return _CACHE[ck]

    S = config.TILE * SS
    body = _new(S)
    fn = _MONSTER_DRAW.get(key)
    if fn:
        # drained, but not so dark that the silhouette stops reading. a corpse has to
        # be identifiable -- "what did I kill here" is a real question.
        grey = sum(color) / 3.0
        dead = tuple(int(c * 0.55 + grey * 0.18) for c in color)
        fn(body, S, dead, _shade(dead, 0.5))

    out = _new(S)
    # THE POOL. This is what stops a corpse reading as "a monster standing still".
    # It is deliberately large and deliberately red.
    _ell(out, (74, 20, 26), S * 0.5, S * 0.70, S * 0.44, S * 0.22)
    _ell(out, (116, 30, 38), S * 0.5, S * 0.69, S * 0.37, S * 0.17)
    _ell(out, (150, 42, 48), S * 0.44, S * 0.66, S * 0.16, S * 0.07)
    # a couple of spatters, so it does not read as a neat disc
    _circ(out, (100, 26, 32), S * 0.20, S * 0.80, S * 0.05)
    _circ(out, (100, 26, 32), S * 0.82, S * 0.62, S * 0.04)

    # tip it over. it is lying down. it is not getting back up.
    lying = pygame.transform.rotate(body, 90)
    lying = pygame.transform.smoothscale(
        lying, (int(lying.get_width() * 0.92), int(lying.get_height() * 0.92)))
    r = lying.get_rect(center=(S * 0.5, S * 0.55))
    out.blit(lying, r)

    _CACHE[ck] = _finish(out)
    return _CACHE[ck]


def vendor(dim=False):
    """It is not a shopkeeper. It is too tall, it has too many hands, and there is
    nothing inside the hood but two coins where the eyes should be."""
    ck = ("vendor", dim)
    if ck in _CACHE:
        return _CACHE[ck]
    S = config.TILE * SS
    s = _new(S)
    cloth = (74, 62, 92)
    trim = config.VENDOR_COLOR
    cx = S * 0.5

    # a tall robe, wider at the hem than any person is
    _poly(s, cloth, [(cx, S * 0.10),
                     (cx + S * 0.22, S * 0.34),
                     (cx + S * 0.34, S * 0.92),
                     (cx - S * 0.34, S * 0.92),
                     (cx - S * 0.22, S * 0.34)])
    _poly(s, _shade(cloth, 0.72), [(cx, S * 0.10), (cx + S * 0.22, S * 0.34),
                                   (cx, S * 0.46), (cx - S * 0.22, S * 0.34)])
    # gold trim at the hem
    _line(s, trim, (cx - S * 0.34, S * 0.90), (cx + S * 0.34, S * 0.90), S * 0.035)

    # the hood, and the nothing inside it
    _ell(s, (12, 10, 18), cx, S * 0.30, S * 0.14, S * 0.16)
    # two coins where the eyes should be
    _circ(s, trim, cx - S * 0.055, S * 0.29, S * 0.045)
    _circ(s, trim, cx + S * 0.055, S * 0.29, S * 0.045)
    _circ(s, _shade(trim, 0.55), cx - S * 0.055, S * 0.29, S * 0.018)
    _circ(s, _shade(trim, 0.55), cx + S * 0.055, S * 0.29, S * 0.018)

    # too many hands, held open
    for (hx, hy, r) in ((-0.30, 0.56, 0.055), (0.30, 0.56, 0.055),
                        (-0.24, 0.72, 0.045), (0.24, 0.72, 0.045)):
        _circ(s, _shade(cloth, 1.35), cx + S * hx, S * hy, S * r)
    # a coin balanced on one of them
    _circ(s, trim, cx + S * 0.30, S * 0.50, S * 0.05)
    _circ(s, _shade(trim, 1.25), cx + S * 0.285, S * 0.49, S * 0.02)

    out = _finish(s)
    _CACHE[ck] = _dimmed(out) if dim else out
    return _CACHE[ck]


def unknown():
    """A monster you cannot explain. A hole in the world, walking toward you."""
    ck = ("unknown",)
    if ck in _CACHE:
        return _CACHE[ck]
    S = config.TILE * SS
    s = _new(S)
    cx, cy = S * 0.5, S * 0.55
    pts = []
    for i in range(11):
        a = i / 11.0 * math.tau
        r = S * (0.34 if i % 2 else 0.30)
        pts.append((cx + math.cos(a) * r, cy + math.sin(a) * r * 1.05))
    _poly(s, config.UNKNOWN, pts)
    pygame.draw.polygon(s, config.UNKNOWN_EDGE, pts, int(S * 0.02))
    f = fontcache.get_font(int(S * 0.42), bold=True)
    img = f.render("?", True, config.UNKNOWN_EDGE)
    s.blit(img, img.get_rect(center=(cx, cy)))
    _CACHE[ck] = _finish(s)
    return _CACHE[ck]


def player(weapon_tier, armour_tier):
    ck = ("player", weapon_tier, armour_tier)
    if ck in _CACHE:
        return _CACHE[ck]
    S = config.TILE * SS
    s = _new(S)
    cx = S * 0.5
    body = config.PLAYER
    armour_col = [(96, 110, 130), (120, 140, 160), (170, 185, 205), (225, 235, 245)][
        min(3, armour_tier)]
    blade = [(150, 150, 160), (200, 205, 215), (235, 240, 250), (255, 210, 120)][
        min(3, weapon_tier)]

    # cloak
    _poly(s, _shade(body, 0.42), [(cx - S * 0.24, S * 0.44), (cx + S * 0.24, S * 0.44),
                                  (cx + S * 0.28, S * 0.88), (cx - S * 0.28, S * 0.88)])
    # torso / cuirass -- brightens with armour tier
    _poly(s, armour_col, [(cx - S * 0.17, S * 0.44), (cx + S * 0.17, S * 0.44),
                          (cx + S * 0.13, S * 0.74), (cx - S * 0.13, S * 0.74)])
    _line(s, _shade(armour_col, 0.7), (cx, S * 0.46), (cx, S * 0.72), S * 0.02)
    # legs
    _line(s, _shade(body, 0.5), (cx - S * 0.08, S * 0.74), (cx - S * 0.09, S * 0.90), S * 0.055)
    _line(s, _shade(body, 0.5), (cx + S * 0.08, S * 0.74), (cx + S * 0.09, S * 0.90), S * 0.055)
    # helm with a visor slit
    _circ(s, armour_col, cx, S * 0.30, S * 0.135)
    pygame.draw.rect(s, (20, 30, 34), (cx - S * 0.10, S * 0.28, S * 0.20, S * 0.04))
    _circ(s, body, cx, S * 0.30, S * 0.135, )
    pygame.draw.circle(s, armour_col, (int(cx), int(S * 0.30)), int(S * 0.135), int(S * 0.035))
    pygame.draw.rect(s, (16, 24, 28), (cx - S * 0.09, S * 0.28, S * 0.18, S * 0.045))
    _circ(s, (170, 250, 245), cx - S * 0.045, S * 0.30, S * 0.016)
    _circ(s, (170, 250, 245), cx + S * 0.045, S * 0.30, S * 0.016)
    # the sword, held out
    _line(s, (110, 84, 60), (cx + S * 0.24, S * 0.68), (cx + S * 0.30, S * 0.56), S * 0.05)
    _line(s, blade, (cx + S * 0.29, S * 0.58), (cx + S * 0.40, S * 0.18), S * 0.055)
    _line(s, _shade(blade, 1.2), (cx + S * 0.30, S * 0.56), (cx + S * 0.38, S * 0.24), S * 0.018)
    _line(s, (90, 70, 50), (cx + S * 0.20, S * 0.64), (cx + S * 0.34, S * 0.60), S * 0.035)
    _CACHE[ck] = _finish(s)
    return _CACHE[ck]


# ---------------------------------------------------------------- objects
def chest(dim=False):
    ck = ("chest", dim)
    if ck in _CACHE:
        return _CACHE[ck]
    S = config.TILE * SS
    s = _new(S)
    wood = config.CHEST
    cx, cy = S * 0.5, S * 0.58
    _poly(s, wood, [(cx - S * 0.32, cy + S * 0.24), (cx + S * 0.32, cy + S * 0.24),
                    (cx + S * 0.32, cy - S * 0.06), (cx - S * 0.32, cy - S * 0.06)])
    pygame.draw.arc(s, _shade(wood, 1.12),
                    (cx - S * 0.32, cy - S * 0.30, S * 0.64, S * 0.48),
                    0, math.pi, int(S * 0.14))
    # iron bands and a lock
    for bx in (cx - S * 0.18, cx + S * 0.18):
        _line(s, _shade(wood, 0.55), (bx, cy - S * 0.24), (bx, cy + S * 0.24), S * 0.045)
    pygame.draw.rect(s, (230, 200, 110),
                     (cx - S * 0.05, cy - S * 0.06, S * 0.10, S * 0.13))
    _circ(s, (60, 44, 24), cx, cy + S * 0.01, S * 0.022)
    out = _finish(s)
    _CACHE[ck] = _dimmed(out) if dim else out
    return _CACHE[ck]


def stairs(dim=False):
    ck = ("stairs", dim)
    if ck in _CACHE:
        return _CACHE[ck]
    S = config.TILE * SS
    s = _new(S)
    for i in range(4):
        k = i / 4.0
        col = _shade(config.STAIRS, 0.35 + 0.2 * i)
        pygame.draw.rect(s, col,
                         (S * (0.16 + 0.08 * i), S * (0.20 + 0.16 * i),
                          S * (0.68 - 0.16 * i), S * 0.16))
    out = _finish(s)
    _CACHE[ck] = _dimmed(out) if dim else out
    return _CACHE[ck]


def entrance(dim=False):
    """FLOOR 1's gate: the way you came in, with the portcullis DOWN.

    It is drawn shut, because it is shut. The bars go all the way to the floor and
    there is no dark doorway behind them -- there is nothing behind them. This is not
    a way out and it should never look like one.
    """
    ck = ("entrance", dim)
    if ck in _CACHE:
        return _CACHE[ck]
    S = config.TILE * SS
    s = _new(S)
    col = config.ENTRANCE
    stone = _shade(col, 0.55)

    # the arch and its jambs
    pygame.draw.arc(s, col, (S * 0.14, S * 0.16, S * 0.72, S * 0.76),
                    0, math.pi, int(S * 0.07))
    _line(s, col, (S * 0.17, S * 0.52), (S * 0.17, S * 0.92), S * 0.07)
    _line(s, col, (S * 0.83, S * 0.52), (S * 0.83, S * 0.92), S * 0.07)
    # the black behind the grate
    _poly(s, (12, 12, 18), [(S * 0.24, S * 0.90), (S * 0.76, S * 0.90),
                            (S * 0.76, S * 0.34), (S * 0.24, S * 0.34)])
    # PORTCULLIS DOWN: bars all the way to the ground, with cross-braces
    for i in range(4):
        x = S * (0.30 + i * 0.14)
        _line(s, stone, (x, S * 0.30), (x, S * 0.90), S * 0.045)
    for j in range(3):
        y = S * (0.44 + j * 0.20)
        _line(s, stone, (S * 0.24, y), (S * 0.76, y), S * 0.035)
    # spiked feet, resting on the flagstones
    for i in range(4):
        x = S * (0.30 + i * 0.14)
        _poly(s, _shade(stone, 1.2), [(x - S * 0.035, S * 0.88),
                                      (x + S * 0.035, S * 0.88),
                                      (x, S * 0.96)])
    out = _finish(s)
    _CACHE[ck] = _dimmed(out) if dim else out
    return _CACHE[ck]


def stairs_up(dim=False):
    """The way back up, on floors 2 and below. Steps climbing away from you."""
    ck = ("stairs_up", dim)
    if ck in _CACHE:
        return _CACHE[ck]
    S = config.TILE * SS
    s = _new(S)
    col = config.ENTRANCE
    for i in range(4):
        # narrower and brighter as they recede upward
        k = i / 4.0
        c = _shade(col, 0.45 + 0.20 * i)
        pygame.draw.rect(s, c,
                         (S * (0.16 + 0.08 * i), S * (0.72 - 0.16 * i),
                          S * (0.68 - 0.16 * i), S * 0.16))
    # an up-arrow, so it can never be confused with the way down
    _poly(s, (236, 244, 255), [(S * 0.50, S * 0.10), (S * 0.60, S * 0.26),
                               (S * 0.40, S * 0.26)])
    out = _finish(s)
    _CACHE[ck] = _dimmed(out) if dim else out
    return _CACHE[ck]


def corpse(dim=False):
    ck = ("corpse", dim)
    if ck in _CACHE:
        return _CACHE[ck]
    S = config.TILE * SS
    s = _new(S)
    bone = (222, 216, 226)
    cx, cy = S * 0.5, S * 0.56
    # crossed bones
    for a in (0.6, -0.6):
        dx, dy = math.cos(a) * S * 0.26, math.sin(a) * S * 0.26
        _line(s, _shade(bone, 0.7), (cx - dx, cy - dy + S * 0.10),
              (cx + dx, cy + dy + S * 0.10), S * 0.06)
    # skull
    _circ(s, bone, cx, cy - S * 0.02, S * 0.20)
    _poly(s, bone, [(cx - S * 0.11, cy + S * 0.12), (cx + S * 0.11, cy + S * 0.12),
                    (cx + S * 0.08, cy + S * 0.24), (cx - S * 0.08, cy + S * 0.24)])
    _circ(s, (30, 20, 36), cx - S * 0.08, cy - S * 0.03, S * 0.055)
    _circ(s, (30, 20, 36), cx + S * 0.08, cy - S * 0.03, S * 0.055)
    _poly(s, (30, 20, 36), [(cx, cy + S * 0.04), (cx - S * 0.03, cy + S * 0.11),
                            (cx + S * 0.03, cy + S * 0.11)])
    out = _finish(s)
    _CACHE[ck] = _dimmed(out) if dim else out
    return _CACHE[ck]


def gold(dim=False):
    ck = ("gold", dim)
    if ck in _CACHE:
        return _CACHE[ck]
    S = config.TILE * SS
    s = _new(S)
    for (dx, dy) in ((-0.10, 0.10), (0.10, 0.10), (0.0, -0.02)):
        cx, cy = S * (0.5 + dx), S * (0.62 + dy)
        _ell(s, _shade(config.GOLD, 0.7), cx, cy + S * 0.02, S * 0.13, S * 0.09)
        _ell(s, config.GOLD, cx, cy, S * 0.13, S * 0.09)
        _ell(s, _shade(config.GOLD, 1.25), cx - S * 0.03, cy - S * 0.02,
             S * 0.05, S * 0.03)
    out = _finish(s)
    _CACHE[ck] = _dimmed(out) if dim else out
    return _CACHE[ck]


POTION_COLORS = {
    "ochre":   (222, 156, 62),
    "azure":   (86, 168, 240),
    "viscous": (126, 208, 96),
    "black":   (72, 62, 92),
    "grey":    (150, 152, 160),
    "crimson": (200, 70, 80),
    "sallow":  (198, 188, 110),
    "silver":  (214, 224, 232),
    "rose":    (236, 120, 168),
    "vermilion": (232, 92, 52),
    "teal":    (60, 172, 158),
    "sky":     (130, 206, 220),
    "violet":  (176, 150, 214),
    "puce":    (166, 104, 116),
    "vital":   (214, 40, 66),
    "radiant": (248, 208, 96),
    "luminous": (200, 240, 250),
    "ember":   (252, 140, 48),
}


def potion(flavor, dim=False):
    ck = ("potion", flavor, dim)
    if ck in _CACHE:
        return _CACHE[ck]
    S = config.TILE * SS
    s = _new(S)
    col = POTION_COLORS.get(flavor, (180, 180, 190))
    glass = (206, 226, 236)
    cx = S * 0.5
    # flask
    _circ(s, glass, cx, S * 0.66, S * 0.21)
    pygame.draw.rect(s, glass, (cx - S * 0.07, S * 0.32, S * 0.14, S * 0.22))
    # the liquid -- you can ALWAYS see the colour; what you cannot see is what it does.
    # `flavor` here is the LOOK a potion is wearing (the caller resolves it through the
    # per-game shuffle), so which effect hides behind a given colour changes every game.
    # the looks themselves are honest: an ochre look really is ochre, a viscous one
    # really is a thick green.
    _circ(s, col, cx, S * 0.68, S * 0.165)
    pygame.draw.rect(s, col, (cx - S * 0.05, S * 0.46, S * 0.10, S * 0.14))
    _circ(s, _shade(col, 1.35), cx - S * 0.06, S * 0.62, S * 0.04)

    if flavor == "black":                       # BUBBLING black
        for (dx, dy, r) in ((-0.05, 0.60, 0.030), (0.04, 0.66, 0.022),
                            (0.0, 0.54, 0.018), (0.06, 0.56, 0.014)):
            _circ(s, (168, 150, 200), cx + S * dx, S * dy, S * r)
            _circ(s, (60, 52, 78), cx + S * dx, S * dy, S * r * 0.55)
    elif flavor == "viscous":                   # VISCOUS: it clings
        _poly(s, _shade(col, 0.8), [(cx - S * 0.14, S * 0.60), (cx - S * 0.10, S * 0.76),
                                    (cx - S * 0.05, S * 0.60)])
        _circ(s, _shade(col, 0.8), cx + S * 0.09, S * 0.74, S * 0.03)
    elif flavor == "ochre":                     # MURKY: sediment
        _circ(s, _shade(col, 0.70), cx + S * 0.04, S * 0.76, S * 0.05)
        _circ(s, _shade(col, 0.70), cx - S * 0.07, S * 0.78, S * 0.035)

    # cork
    pygame.draw.rect(s, (156, 116, 74), (cx - S * 0.08, S * 0.24, S * 0.16, S * 0.10))
    out = _finish(s)
    _CACHE[ck] = _dimmed(out) if dim else out
    return _CACHE[ck]


def scroll(dim=False):
    ck = ("scroll", dim)
    if ck in _CACHE:
        return _CACHE[ck]
    S = config.TILE * SS
    s = _new(S)
    parch = (226, 214, 178)
    pygame.draw.rect(s, parch, (S * 0.24, S * 0.30, S * 0.52, S * 0.42))
    _ell(s, _shade(parch, 0.78), S * 0.24, S * 0.51, S * 0.07, S * 0.22)
    _ell(s, _shade(parch, 0.78), S * 0.76, S * 0.51, S * 0.07, S * 0.22)
    for i in range(3):
        y = S * (0.40 + i * 0.10)
        _line(s, (120, 100, 76), (S * 0.34, y), (S * 0.66, y), S * 0.025)
    out = _finish(s)
    _CACHE[ck] = _dimmed(out) if dim else out
    return _CACHE[ck]


# --- one look per item ---------------------------------------------------
# A Leather Jerkin is brown. Scale is grey. The Flame Brand burns. You should be
# able to tell what is lying on the floor from across the room, without walking onto
# it -- deciding whether a pickup is worth the turns it costs is a real decision, and
# you cannot make it if every weapon is the same grey sword.

def _w_blade(s, S, blade, hilt, guard, length=0.50, width=0.09, tip=0.08):
    cx = S * 0.5
    _line(s, blade, (cx, S * (0.66 - length)), (cx, S * 0.66), S * width)
    _poly(s, blade, [(cx - S * width / 2, S * (0.68 - length)), (cx, S * tip),
                     (cx + S * width / 2, S * (0.68 - length))])
    _line(s, _shade(blade, 1.25), (cx - S * 0.015, S * (0.62 - length)),
          (cx - S * 0.015, S * 0.62), S * 0.016)
    _line(s, guard, (cx - S * 0.16, S * 0.68), (cx + S * 0.16, S * 0.68), S * 0.06)
    _line(s, hilt, (cx, S * 0.66), (cx, S * 0.86), S * 0.06)
    _circ(s, guard, cx, S * 0.88, S * 0.05)


_MATERIAL = {                       # (blade, hilt, guard) per material
    "bone":   ((236, 230, 212), (172, 150, 118), (200, 190, 168)),
    "bronze": ((206, 150, 74), (120, 84, 52), (162, 116, 60)),
    "steel":  ((216, 224, 236), (60, 62, 72), (176, 182, 196)),
}


def _weapon_sprite(key, s, S):
    cx = S * 0.5
    if key == "shiv":                       # rusted, short, pitiful
        rust = (150, 106, 78)
        _w_blade(s, S, rust, (86, 70, 60), (110, 92, 74), length=0.30, width=0.07,
                 tip=0.28)
        _circ(s, _shade(rust, 0.7), cx + S * 0.02, S * 0.45, S * 0.02)
        _circ(s, _shade(rust, 0.7), cx - S * 0.02, S * 0.55, S * 0.015)
        return
    if "_" in key and key.split("_")[0] in _MATERIAL:
        mat, typ = key.split("_")
        blade, hilt, guard = _MATERIAL[mat]
        if typ == "sword":
            _w_blade(s, S, blade, hilt, guard)
        elif typ == "axe":
            haft = hilt
            _line(s, haft, (cx - S * 0.10, S * 0.16), (cx - S * 0.02, S * 0.90), S * 0.055)
            head = [(cx - S * 0.08, S * 0.16), (cx + S * 0.10, S * 0.13),
                    (cx + S * 0.30, S * 0.24), (cx + S * 0.34, S * 0.40),
                    (cx + S * 0.20, S * 0.34), (cx + S * 0.04, S * 0.36),
                    (cx - S * 0.06, S * 0.34)]
            _poly(s, blade, head)
            pygame.draw.lines(s, _shade(blade, 0.72), True,
                              [(int(x), int(y)) for x, y in head], int(S * 0.018))
            _line(s, _shade(blade, 1.25), (cx + S * 0.12, S * 0.16),
                  (cx + S * 0.31, S * 0.27), S * 0.022)
        elif typ == "hammer":
            _line(s, hilt, (cx, S * 0.30), (cx, S * 0.90), S * 0.07)
            pygame.draw.rect(s, blade, (cx - S * 0.28, S * 0.14, S * 0.56, S * 0.26),
                             border_radius=int(S * 0.04))
            pygame.draw.rect(s, _shade(blade, 0.7),
                             (cx - S * 0.28, S * 0.14, S * 0.56, S * 0.26),
                             int(S * 0.025), border_radius=int(S * 0.04))
            _line(s, _shade(blade, 1.25), (cx - S * 0.22, S * 0.20),
                  (cx + S * 0.22, S * 0.20), S * 0.02)
        return
    if key == "rapier":                     # long, thin, bright steel; swept guard
        _w_blade(s, S, (232, 240, 250), (60, 60, 70), (200, 200, 214),
                 length=0.58, width=0.045, tip=0.04)
        pygame.draw.arc(s, (200, 200, 214),
                        (cx - S * 0.16, S * 0.62, S * 0.32, S * 0.18),
                        math.pi, 2 * math.pi, int(S * 0.03))
    elif key == "brand":                    # it is on fire
        _w_blade(s, S, (255, 168, 72), (90, 60, 40), (200, 110, 50), length=0.52)
        for i, (dx, dy, r) in enumerate(((-0.06, 0.30, 0.05), (0.06, 0.22, 0.04),
                                         (0.0, 0.12, 0.035))):
            _circ(s, (255, 216 - i * 30, 110 - i * 30), cx + S * dx, S * dy, S * r)
        _line(s, (255, 240, 190), (cx, S * 0.20), (cx, S * 0.60), S * 0.02)
    elif key == "kris":                     # wavy, dark, thirsty
        dark = (78, 66, 92)
        pts_l, pts_r = [], []
        for i in range(7):
            t = i / 6.0
            y = S * (0.64 - 0.48 * t)
            wob = math.sin(t * 9.0) * S * 0.045
            pts_l.append((cx - S * 0.035 + wob, y))
            pts_r.append((cx + S * 0.035 + wob, y))
        _poly(s, (196, 190, 214), pts_l + pts_r[::-1])
        _line(s, dark, (cx - S * 0.14, S * 0.68), (cx + S * 0.14, S * 0.68), S * 0.055)
        _line(s, dark, (cx, S * 0.66), (cx, S * 0.86), S * 0.055)
        _circ(s, (196, 60, 76), cx, S * 0.88, S * 0.055)     # the ruby that drinks
        _circ(s, (255, 150, 160), cx - S * 0.015, S * 0.87, S * 0.018)
    # --- Tier 4 magical weapons -----------------------------------------------
    elif key == "betrayers_edge":           # twisted dagger
        _w_blade(s, S, (210, 100, 120), (60, 40, 50), (160, 80, 100),
                 length=0.42, width=0.055, tip=0.05)
        _circ(s, (140, 60, 80), cx, S * 0.75, S * 0.08)     # twisted guard
    elif key == "fulgurite":                # electric blade
        _w_blade(s, S, (200, 220, 255), (80, 80, 100), (150, 200, 255), length=0.50)
        for i in range(3):                  # electricity effects
            _circ(s, (100, 150, 255), cx - S * 0.07 + i * S * 0.07, S * 0.30 + i * S * 0.10,
                  S * 0.03)
    elif key == "winters_edge":             # frost-covered blade
        _w_blade(s, S, (180, 220, 255), (100, 120, 140), (200, 240, 255), length=0.52)
        for i in range(4):                  # ice crystals
            y = S * (0.20 + i * 0.13)
            _circ(s, (200, 240, 255), cx - S * 0.10, y, S * 0.028)
            _circ(s, (200, 240, 255), cx + S * 0.10, y, S * 0.028)
    elif key == "sacrificial_dagger":       # dark, blood-stained
        _w_blade(s, S, (100, 60, 80), (40, 30, 40), (120, 70, 90),
                 length=0.38, width=0.045, tip=0.06)
        _circ(s, (150, 40, 60), cx, S * 0.78, S * 0.06)     # blood drop
    elif key == "windfang":                 # light, ethereal
        _w_blade(s, S, (220, 200, 255), (140, 130, 160), (240, 220, 255),
                 length=0.54, width=0.035, tip=0.02)
        _line(s, (200, 180, 240), (cx - S * 0.12, S * 0.35), (cx - S * 0.05, S * 0.70),
              S * 0.014)
        _line(s, (200, 180, 240), (cx + S * 0.12, S * 0.35), (cx + S * 0.05, S * 0.70),
              S * 0.014)
    # --- Tier 5 magical weapons -----------------------------------------------
    elif key == "basilisk_maul":            # heavy, scaled head
        _line(s, (100, 80, 60), (cx - S * 0.12, S * 0.20), (cx - S * 0.12, S * 0.80),
              S * 0.065)
        pygame.draw.rect(s, (140, 100, 80), (cx - S * 0.22, S * 0.16, S * 0.44, S * 0.22),
                         border_radius=int(S * 0.05))
        for i in range(3):                  # poison scales
            for j in range(2):
                _circ(s, (80, 160, 80), cx - S * 0.14 + j * S * 0.28, S * 0.18 + i * S * 0.08,
                      S * 0.035)
    elif key == "pyroclast":                # volcanic blade
        _w_blade(s, S, (255, 120, 40), (80, 50, 30), (220, 100, 50), length=0.52)
        for i in range(3):                  # lava effects
            _circ(s, (255, 180, 60), cx - S * 0.08 + i * S * 0.08, S * 0.25 + i * S * 0.12,
                  S * 0.04)
    elif key == "reapers_whisper":          # skeletal, dark
        _w_blade(s, S, (140, 120, 160), (60, 40, 70), (170, 140, 190), length=0.50)
        _circ(s, (60, 50, 70), cx - S * 0.08, S * 0.75, S * 0.065)  # skull
        _circ(s, (60, 50, 70), cx + S * 0.08, S * 0.75, S * 0.065)
        _circ(s, (80, 70, 90), cx, S * 0.75, S * 0.045)
    elif key == "glacial_flail":            # chained, icy
        _line(s, (140, 120, 100), (cx, S * 0.30), (cx, S * 0.70), S * 0.045)
        for i in range(3):                  # chain links
            y = S * (0.35 + i * 0.12)
            _circ(s, (180, 200, 220), cx - S * 0.12, y, S * 0.035)
            _circ(s, (180, 200, 220), cx + S * 0.12, y, S * 0.035)
        pygame.draw.rect(s, (200, 220, 255), (cx - S * 0.18, S * 0.74, S * 0.36, S * 0.16),
                         border_radius=int(S * 0.04))
    elif key == "void_scimitar":            # curved, dark, empty
        y_top, y_bot = S * 0.25, S * 0.78
        pts = [(cx + S * 0.08, y_top), (cx + S * 0.30, y_top + S * 0.15),
               (cx + S * 0.28, y_bot - S * 0.05), (cx, y_bot),
               (cx - S * 0.20, y_bot - S * 0.10), (cx - S * 0.12, y_top + S * 0.10)]
        _poly(s, (40, 20, 50), pts)
        _line(s, (100, 60, 120), (cx - S * 0.16, y_top + S * 0.08), (cx - S * 0.08, y_bot),
              S * 0.022)


def _armour_sprite(key, s, S):
    cx = S * 0.5

    def cuirass(col, edge=None):
        _poly(s, col, [(cx - S * 0.26, S * 0.28), (cx + S * 0.26, S * 0.28),
                       (cx + S * 0.20, S * 0.80), (cx, S * 0.88),
                       (cx - S * 0.20, S * 0.80)])
        _circ(s, _shade(col, 1.12), cx - S * 0.26, S * 0.32, S * 0.075)
        _circ(s, _shade(col, 1.12), cx + S * 0.26, S * 0.32, S * 0.075)
        if edge:
            pygame.draw.lines(s, edge, True,
                              [(cx - S * 0.26, S * 0.28), (cx + S * 0.26, S * 0.28),
                               (cx + S * 0.20, S * 0.80), (cx, S * 0.88),
                               (cx - S * 0.20, S * 0.80)], int(S * 0.022))

    if key == "rags":                       # sackcloth, frayed
        cloth = (176, 158, 128)
        cuirass(cloth, _shade(cloth, 0.7))
        for i in range(3):
            y = S * (0.42 + i * 0.14)
            _line(s, _shade(cloth, 0.72), (cx - S * 0.18, y), (cx + S * 0.16, y - S * 0.02),
                  S * 0.02)
        _poly(s, _shade(cloth, 0.6), [(cx + S * 0.08, S * 0.80), (cx + S * 0.18, S * 0.80),
                                      (cx + S * 0.12, S * 0.92)])
    elif key == "leather":                  # BROWN
        hide = (150, 100, 60)
        cuirass(hide, _shade(hide, 0.65))
        _line(s, _shade(hide, 0.62), (cx, S * 0.30), (cx, S * 0.84), S * 0.025)
        for i in range(4):                  # stitching
            y = S * (0.38 + i * 0.13)
            _circ(s, (206, 170, 120), cx - S * 0.10, y, S * 0.018)
            _circ(s, (206, 170, 120), cx + S * 0.10, y, S * 0.018)
    elif key == "mail":                     # grey chainmail rings
        steel = (138, 144, 156)
        cuirass(steel, _shade(steel, 0.6))
        for row in range(5):
            for col in range(5):
                x = cx - S * 0.18 + col * S * 0.09 + (S * 0.045 if row % 2 else 0)
                y = S * 0.34 + row * S * 0.10
                pygame.draw.circle(s, _shade(steel, 1.3), (int(x), int(y)),
                                   int(S * 0.028), int(S * 0.012))
    elif key == "scale":                    # GREY scales
        grey = (146, 152, 162)
        cuirass(grey, _shade(grey, 0.62))
        for row in range(4):
            for col in range(4):
                x = cx - S * 0.15 + col * S * 0.10 + (S * 0.05 if row % 2 else 0)
                y = S * 0.36 + row * S * 0.12
                _circ(s, _shade(grey, 1.18), x, y, S * 0.045)
                _circ(s, _shade(grey, 0.78), x, y + S * 0.012, S * 0.032)
    elif key == "chain":                    # rings
        steel = (128, 136, 150)
        cuirass(steel, _shade(steel, 0.6))
        for row in range(5):
            for col in range(5):
                x = cx - S * 0.18 + col * S * 0.09 + (S * 0.045 if row % 2 else 0)
                y = S * 0.34 + row * S * 0.10
                pygame.draw.circle(s, _shade(steel, 1.3), (int(x), int(y)),
                                   int(S * 0.028), int(S * 0.012))
    elif key == "thorn":                    # dark, and covered in spikes
        dark = (96, 84, 96)
        cuirass(dark, (60, 50, 62))
        for (dx, dy) in ((-0.14, 0.40), (0.14, 0.40), (0.0, 0.54),
                         (-0.12, 0.66), (0.12, 0.66)):
            _poly(s, (226, 214, 226), [(cx + S * (dx - 0.035), S * (dy + 0.05)),
                                       (cx + S * (dx + 0.035), S * (dy + 0.05)),
                                       (cx + S * dx, S * (dy - 0.09))])
    elif key == "plate":                    # bright, heavy, ridged
        steel = (222, 230, 242)
        cuirass(steel, (150, 158, 172))
        _line(s, (150, 158, 172), (cx, S * 0.30), (cx, S * 0.86), S * 0.03)
        for i in range(3):
            y = S * (0.44 + i * 0.14)
            pygame.draw.arc(s, (150, 158, 172),
                            (cx - S * 0.20, y - S * 0.06, S * 0.40, S * 0.14),
                            math.pi, 2 * math.pi, int(S * 0.022))
    elif key == "silk":                     # pale, ghostly, barely there
        silk = (196, 180, 226)
        cuirass(silk, (232, 224, 250))
        for i in range(4):
            y = S * (0.36 + i * 0.13)
            pygame.draw.arc(s, (240, 236, 255),
                            (cx - S * 0.18, y, S * 0.36, S * 0.10),
                            0, math.pi, int(S * 0.016))
        _circ(s, (250, 250, 255), cx, S * 0.52, S * 0.03)
    elif key == "venom":                    # sickly green
        cuirass((92, 150, 96), (54, 96, 60))
    elif key == "cinder":                   # ember red-orange
        cuirass((176, 84, 56), (110, 48, 34))
    elif key == "glacial":                  # pale ice blue
        cuirass((150, 196, 226), (96, 140, 178))
    elif key == "lifeweave":                # living green-gold
        cuirass((120, 168, 96), (78, 120, 62))
    elif key == "bastion":                  # heavy dark steel
        cuirass((96, 104, 118), (56, 62, 74))
    elif key == "lastbreath":               # ashen white
        cuirass((210, 214, 220), (150, 156, 168))
    elif key == "blinding":                 # radiant gold-white
        cuirass((236, 224, 150), (196, 176, 96))
    elif key == "stonegolem":               # grey stone
        cuirass((140, 134, 124), (92, 86, 78))
    elif key == "hades":                    # dark robe, ember trim
        cuirass((70, 54, 66), (150, 70, 50))
    elif key == "fade":                     # dim violet-grey, half-there
        cuirass((132, 120, 150), (84, 76, 100))
    elif key == "nightcloak":               # near-black, star-flecked
        cuirass((34, 32, 48), (12, 12, 22))
    elif key == "shade":                    # slate grey, stone-toned
        cuirass((96, 96, 104), (52, 52, 60))


def _boots_sprite(key, s, S):
    cx = S * 0.5

    def boot(col, sole=None):
        _poly(s, col, [(cx - S * 0.20, S * 0.24), (cx + S * 0.04, S * 0.24),
                       (cx + S * 0.04, S * 0.62), (cx + S * 0.30, S * 0.62),
                       (cx + S * 0.30, S * 0.78), (cx - S * 0.20, S * 0.78)])
        _line(s, sole or _shade(col, 0.55),
              (cx - S * 0.23, S * 0.80), (cx + S * 0.33, S * 0.80), S * 0.06)

    if key == "sandals":                    # worn, strappy, tan
        tan = (176, 142, 100)
        _line(s, _shade(tan, 0.6), (cx - S * 0.22, S * 0.72), (cx + S * 0.30, S * 0.72),
              S * 0.07)
        for i in range(3):
            x = cx - S * 0.12 + i * S * 0.14
            _line(s, tan, (x, S * 0.44), (x + S * 0.06, S * 0.68), S * 0.035)
        _line(s, tan, (cx - S * 0.16, S * 0.48), (cx + S * 0.24, S * 0.44), S * 0.035)
    elif key == "swift":                    # light, blue leather
        boot((92, 132, 196))
        _line(s, (170, 206, 245), (cx - S * 0.16, S * 0.34), (cx, S * 0.34), S * 0.028)
        _poly(s, (200, 226, 250), [(cx - S * 0.20, S * 0.52), (cx - S * 0.34, S * 0.46),
                                   (cx - S * 0.20, S * 0.44)])
    elif key == "soft":                     # padded, grey, quiet
        felt = (150, 148, 156)
        boot(felt, (110, 108, 118))
        for i in range(3):
            y = S * (0.34 + i * 0.12)
            pygame.draw.arc(s, _shade(felt, 1.25), (cx - S * 0.18, y, S * 0.26, S * 0.10),
                            0, math.pi, int(S * 0.02))
        for i in range(4):                  # the quiet sole
            _circ(s, (196, 194, 202), cx - S * 0.14 + i * S * 0.13, S * 0.80, S * 0.02)
    elif key == "blink":                    # purple, and not entirely here
        boot((138, 104, 200))
        for i, (dx, dy, r) in enumerate(((-0.28, 0.36, 0.035), (0.30, 0.44, 0.028),
                                         (-0.32, 0.62, 0.022))):
            _circ(s, (226, 200, 255), cx + S * dx, S * dy, S * r)
        _poly(s, (236, 220, 255), [(cx + S * 0.16, S * 0.28), (cx + S * 0.24, S * 0.40),
                                   (cx + S * 0.16, S * 0.38), (cx + S * 0.20, S * 0.50),
                                   (cx + S * 0.08, S * 0.36), (cx + S * 0.16, S * 0.37)])
    elif key == "ironshod":                 # dark leather, iron toecap
        boot((96, 86, 78))
        iron = (150, 156, 168)
        _poly(s, iron, [(cx + S * 0.04, S * 0.62), (cx + S * 0.30, S * 0.62),
                        (cx + S * 0.30, S * 0.78), (cx + S * 0.04, S * 0.78)])
        _line(s, _shade(iron, 1.25), (cx + S * 0.08, S * 0.66), (cx + S * 0.28, S * 0.66),
              S * 0.02)
        for i in range(3):
            _circ(s, _shade(iron, 0.65), cx + S * (0.10 + i * 0.08), S * 0.74, S * 0.018)
    elif key == "emberstride":              # dark boot, ember glow
        boot((104, 66, 58), (66, 40, 36))
        for (dx, dy, r) in ((-0.10, 0.42, 0.05), (0.10, 0.54, 0.04), (-0.02, 0.64, 0.03)):
            _circ(s, (255, 150, 60), cx + S * dx, S * dy, S * r)
            _circ(s, (255, 216, 120), cx + S * dx, S * dy, S * r * 0.45)
    elif key == "rimewalkers":              # pale ice-blue, frost crystals
        boot((180, 210, 230), (120, 152, 180))
        rime = (232, 246, 255)
        for (dx, dy) in ((-0.12, 0.36), (0.08, 0.46), (-0.02, 0.60)):
            _line(s, rime, (cx + S * dx, S * (dy - 0.05)), (cx + S * dx, S * (dy + 0.05)),
                  S * 0.02)
            _line(s, rime, (cx + S * (dx - 0.05), S * dy), (cx + S * (dx + 0.05), S * dy),
                  S * 0.02)
    elif key == "wind":                     # white, winged
        boot((236, 240, 248), (190, 200, 214))
        wing = (170, 236, 240)
        for i in range(3):
            y = S * (0.30 + i * 0.07)
            _poly(s, wing, [(cx - S * 0.18, y), (cx - S * 0.40, y - S * 0.03),
                            (cx - S * 0.16, y + S * 0.045)])
        _line(s, (140, 220, 226), (cx - S * 0.14, S * 0.36), (cx, S * 0.36), S * 0.025)
    elif key == "featherfall":              # pale sky-blue, floating feathers
        boot((150, 196, 236), (96, 140, 190))
        for i in range(3):                  # feathers rising off the heel
            y = S * (0.30 + i * 0.06)
            _poly(s, (214, 234, 250), [(cx - S * 0.22, y), (cx - S * 0.40, y - S * 0.02),
                                       (cx - S * 0.20, y + S * 0.05)])
        _circ(s, (230, 244, 255), cx + S * 0.10, S * 0.30, S * 0.03)
    elif key == "boots_leather":            # plain brown work boot
        boot((150, 100, 62), (96, 62, 36))
        _line(s, (188, 140, 96), (cx - S * 0.16, S * 0.34),
              (cx, S * 0.34), S * 0.028)                    # cuff stitch
        for i in range(3):                                  # laces up the front
            y = S * (0.40 + i * 0.09)
            _line(s, (206, 168, 120), (cx - S * 0.14, y),
                  (cx - S * 0.02, y), S * 0.02)
    elif key == "boots_mail":               # steel-grey, ringed chain mesh
        steel = (128, 136, 150)
        boot(steel, (84, 90, 104))
        for r in range(3):
            for c in range(3):
                _circ(s, _shade(steel, 1.35),
                      cx - S * 0.14 + c * S * 0.11,
                      S * (0.36 + r * 0.11), S * 0.022)
    elif key == "boots_plate":              # bright, heavy, ridged steel
        steel = (178, 184, 198)
        boot(steel, (118, 124, 138))
        cap = (208, 214, 226)
        _poly(s, cap, [(cx + S * 0.04, S * 0.58), (cx + S * 0.30, S * 0.58),
                       (cx + S * 0.30, S * 0.78), (cx + S * 0.04, S * 0.78)])  # toecap
        for i in range(3):                                  # ridged shin plates
            y = S * (0.30 + i * 0.09)
            _line(s, _shade(steel, 0.65), (cx - S * 0.18, y),
                  (cx + S * 0.02, y), S * 0.02)
    elif key == "thor":                     # storm-slate, a yellow bolt
        boot((86, 96, 120), (52, 60, 82))
        bolt = (250, 224, 90)
        _poly(s, bolt, [(cx - S * 0.02, S * 0.28), (cx - S * 0.14, S * 0.50),
                        (cx - S * 0.02, S * 0.48), (cx - S * 0.10, S * 0.68),
                        (cx + S * 0.12, S * 0.42), (cx + S * 0.00, S * 0.44)])
    elif key == "slipstep":                 # teal, with a motion afterimage
        boot((80, 180, 150), (48, 120, 100))
        ghost = (150, 226, 206)
        for i in range(3):                  # trailing streak behind the heel
            x = cx - S * (0.24 + i * 0.06)
            _line(s, ghost, (x, S * 0.40), (x, S * 0.70), S * 0.02)
    elif key == "phantom":                  # faded grey, a shifted ghost double
        boot((170, 175, 190), (120, 124, 140))
        ghost = (206, 210, 224)
        _poly(s, ghost, [(cx - S * 0.14, S * 0.24), (cx + S * 0.10, S * 0.24),
                         (cx + S * 0.10, S * 0.62), (cx + S * 0.36, S * 0.62),
                         (cx + S * 0.36, S * 0.78), (cx - S * 0.14, S * 0.78)])
    elif key == "whisperstep":              # muffled grey-violet, a soft hush
        boot((120, 116, 140), (78, 74, 96))
        for i in range(3):                  # faint sound-rings fading off the heel
            r = S * (0.10 + i * 0.06)
            pygame.draw.arc(s, (176, 170, 200), (cx - S * 0.36, S * 0.34, r * 2, r * 2),
                            0.6, 2.5, max(1, int(S * 0.015)))


_GEAR_DRAW = {"weapon": _weapon_sprite, "armour": _armour_sprite, "boots": _boots_sprite}


def gear(key, dim=False):
    """One sprite per ITEM, not per slot. A Leather Jerkin is brown, Scale is grey,
    the Flame Brand is on fire, and the Windwalkers have wings."""
    from .items import ALL_GEAR

    ck = ("gear", key, dim)
    if ck in _CACHE:
        return _CACHE[ck]
    S = config.TILE * SS
    s = _new(S)
    g = ALL_GEAR.get(key)
    if g is not None:
        _GEAR_DRAW[g.slot](key, s, S)
    out = _finish(s)
    _CACHE[ck] = _dimmed(out) if dim else out
    return _CACHE[ck]


# ---------------------------------------------------------------- traps
def trap(key, sprung=False, dim=False):
    ck = ("trap", key, sprung, dim)
    if ck in _CACHE:
        return _CACHE[ck]
    S = config.TILE * SS
    s = _new(S)
    cx, cy = S * 0.5, S * 0.5

    if key == "dart":
        plate = (150, 92, 108)
        pygame.draw.rect(s, plate, (S * 0.16, S * 0.16, S * 0.68, S * 0.68),
                         int(S * 0.05), border_radius=int(S * 0.06))
        for (dx, dy) in ((-0.14, -0.14), (0.14, -0.14), (-0.14, 0.14), (0.14, 0.14)):
            _circ(s, (40, 20, 26), cx + S * dx, cy + S * dy, S * 0.045)
        _circ(s, plate, cx, cy, S * 0.07)
    elif key == "spike":
        # a hole, and rusted iron standing up out of the dark inside it
        _ell(s, (120, 86, 72), cx, cy, S * 0.38, S * 0.32)
        _ell(s, (10, 8, 12), cx, cy + S * 0.015, S * 0.33, S * 0.27)
        for i in range(5):
            x = S * (0.26 + i * 0.12)
            h = S * (0.30 if i % 2 else 0.24)
            _poly(s, (206, 168, 140),
                  [(x - S * 0.045, cy + S * 0.17), (x + S * 0.045, cy + S * 0.17),
                   (x, cy + S * 0.17 - h)])
            _line(s, (240, 214, 190), (x, cy + S * 0.15),
                  (x - S * 0.012, cy + S * 0.17 - h * 0.85), S * 0.016)
        pygame.draw.ellipse(s, (150, 110, 92), (cx - S * 0.38, cy - S * 0.32,
                                                S * 0.76, S * 0.64), int(S * 0.035))
    elif key == "gas":
        grate = (110, 150, 110)
        pygame.draw.rect(s, grate, (S * 0.22, S * 0.30, S * 0.56, S * 0.44),
                         int(S * 0.05), border_radius=int(S * 0.05))
        for i in range(3):
            x = S * (0.32 + i * 0.18)
            _line(s, grate, (x, S * 0.32), (x, S * 0.72), S * 0.04)
        for i, (dx, r) in enumerate(((-0.16, 0.06), (0.02, 0.08), (0.18, 0.05))):
            _circ(s, (150, 220, 130), cx + S * dx, S * (0.22 - i * 0.03), S * r)
    elif key == "alarm":
        col = (240, 200, 90)
        pygame.draw.circle(s, col, (int(cx), int(cy)), int(S * 0.30), int(S * 0.05))
        pygame.draw.circle(s, col, (int(cx), int(cy)), int(S * 0.16), int(S * 0.04))
        for i in range(8):
            a = i / 8.0 * math.tau
            _line(s, col, (cx + math.cos(a) * S * 0.32, cy + math.sin(a) * S * 0.32),
                  (cx + math.cos(a) * S * 0.42, cy + math.sin(a) * S * 0.42), S * 0.035)
    elif key == "glyph":
        col = (255, 130, 70)
        pygame.draw.circle(s, col, (int(cx), int(cy)), int(S * 0.32), int(S * 0.05))
        # a flame rune
        _poly(s, col, [(cx, cy - S * 0.24), (cx + S * 0.14, cy + S * 0.02),
                       (cx + S * 0.06, cy + S * 0.02), (cx + S * 0.10, cy + S * 0.20),
                       (cx - S * 0.12, cy - S * 0.02), (cx - S * 0.02, cy - S * 0.02)])
    out = _finish(s)
    if sprung:
        out = _dimmed(out, 0.35)
    _CACHE[ck] = _dimmed(out) if dim else out
    return _CACHE[ck]
