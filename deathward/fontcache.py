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

"""The one monospace font, loaded once, shared by render.py and sprites.py.

pygame.font.SysFont("consolas,dejavusansmono,couriernew,monospace", ...) depends
on the OS having a font registry to search by name. Native desktops usually have
one -- but pygbag's WASM/Pyodide sandbox does not, so SysFont silently falls back
to pygame's own bundled freesansbold.ttf instead of raising. That is a real,
different, proportional (non-monospace) font, not just worse-rendered Consolas.

Loading a bundled .ttf directly with pygame.font.Font sidesteps OS font-discovery
entirely, so it renders identically everywhere: native Windows/Mac/Linux and the
browser build alike. DejaVu Sans Mono is bundled (see assets/fonts/LICENSE-DejaVu.txt
for its license) -- it was already the second name in the old SysFont fallback list,
so it is the closest match to what most players already saw.
"""

import os

import pygame

_FONT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "assets", "fonts", "DejaVuSansMono.ttf")

_cache = {}


def get_font(size, bold=False):
    key = (size, bold)
    if key not in _cache:
        f = pygame.font.Font(_FONT_PATH, size)
        f.set_bold(bold)
        _cache[key] = f
    return _cache[key]
