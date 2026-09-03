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

"""The monospace font, resolved differently depending on where we are running.

Native desktops have an OS font registry, so pygame.font.SysFont can find real
Consolas by name. It is better hinted than anything we bundle, and every size
constant at every call site was tuned against it.

pygbag's WASM/Pyodide sandbox has no such registry -- and SysFont does not raise
there, it silently falls back to pygame's own freesansbold.ttf. That is a real,
different, PROPORTIONAL font, which is ruinous in a game drawn entirely from
glyphs on a grid. So the web build loads a bundled DejaVu Sans Mono directly with
pygame.font.Font, which needs no font-discovery step at all. (Its license is in
assets/fonts/LICENSE-DejaVu.txt; it was already the second name in the SysFont
list below, so it is the closest match to what native players see.)

DejaVu is not metrically identical to Consolas, though: its glyphs stand about
17% taller at the same nominal size, and every size constant in this game is a
Consolas number. So the web branch scales the request down by _WEB_SCALE before
loading. Consolas renders exactly `size` pixels tall, which makes the test for
this pleasingly direct -- web text must too, within a pixel. Note the scale
applies on the way to the loader and never to the cache key: a caller asking for
15 gets a 13px face, filed under 15.

The known cost of branching on platform rather than probing discovery: a native
macOS without fc-list fails lookup the same silent way (pygame #3156) and lands on
freesansbold rather than on the bundle. Mac is deferred; revisit with
pygame.font.match_font if it ever ships.
"""

import os
import sys

import pygame

_FONT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "assets", "fonts", "DejaVuSansMono.ttf")

_SYS_FONTS = "consolas,dejavusansmono,couriernew,monospace"

_WEB_SCALE = 0.85

_cache = {}


def _is_web():
    return sys.platform == "emscripten"


def get_font(size, bold=False):
    key = (size, bold)
    if key not in _cache:
        if _is_web():
            f = pygame.font.Font(_FONT_PATH, round(size * _WEB_SCALE))
            f.set_bold(bold)
        else:
            f = pygame.font.SysFont(_SYS_FONTS, size, bold=bold)
        _cache[key] = f
    return _cache[key]
