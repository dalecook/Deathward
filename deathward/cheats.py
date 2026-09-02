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

"""Cheat codes, for testing the deep floors without earning them.

Hold CTRL (or CMD on a Mac) and type a sequence. It must be typed in order and with
the modifier held the whole way through -- let go, or press anything else, and it
starts over. The codes in use:

    0 9 8 7   grant the best gear and nine healing potions
    7 8       drop onto the NEXT floor's entrance tile, from anywhere
    8 7       open the arsenal: pick a top-tier weapon/armour/boots to drop beside you
    6 7       pick any uncommon/rare SCROLL, straight into the pack
    7 6       pick any uncommon/rare POTION, straight into the pack
    1 2       open the weapon bench: swap on any weapon, ordinary or magical
    2 1       open the magic bench: the magical weapons only, no ordinary page
    5 6       open the boots bench: swap on any boot, ordinary or magical
    3 4       open the armour bench: swap on any armour, ordinary or magical

The four benches share one picker: TAB cycles the Ordinary / Tier 4 / Tier 5 pages,
a digit equips that row, and SHIFT+digit takes its +2 masterwork instead (weapons
only). A bench SWAPS -- what you were wearing drops at your feet. 0987 does not: it
overwrites, because littering the floor with your old rags would just be noise.

These exist so the deep floors can be reached in a few minutes instead of a few
hours. They are deliberately not reachable by accident: nothing in the game binds
CTRL, and no sequence here is one a hand produces by mistake. CheatCode is generic --
each code is one instance with its own sequence (see game.py, which is where the
codes are actually wired, and the thing to trust if this list ever drifts again).

The fuller reference, including what each code does NOT do, is docs/cheats.md.
"""

import pygame

SEQUENCE = [pygame.K_0, pygame.K_9, pygame.K_8, pygame.K_7]


class CheatCode:
    def __init__(self, sequence=None):
        self.sequence = list(sequence or SEQUENCE)
        self.progress = 0

    def reset(self):
        self.progress = 0

    def feed(self, key, held):
        """Feed one keypress. `held` is whether CTRL/CMD is down right now.

        Returns True on the keypress that completes the code.
        """
        if not held:
            self.progress = 0
            return False
        if key == self.sequence[self.progress]:
            self.progress += 1
            if self.progress >= len(self.sequence):
                self.progress = 0
                return True
            return False
        # a wrong key: start again -- but a wrong key that is the FIRST key of the
        # code should count as the start of a new attempt, not a dead end
        self.progress = 1 if key == self.sequence[0] else 0
        return False
