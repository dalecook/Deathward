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

"""Hold-to-walk.

A turn-based game should not be a typing exercise. A tap is one step; hold the key
and the hero keeps walking in that direction until you let go, something blocks the
way, or the world stops being safe to walk through.

The logic lives here, away from pygame, so it can be tested without a keyboard.
"""

from . import config


class Repeater:
    def __init__(self, delay=None, interval=None):
        self.delay = config.MOVE_REPEAT_DELAY if delay is None else delay
        self.interval = config.MOVE_REPEAT_INTERVAL if interval is None else interval
        self.key = None
        self.next_t = 0.0

    def start(self, key, t):
        """The key just went down. The first step has already been taken by the
        KEYDOWN handler, so the next one is not due until the hold delay is up."""
        self.key = key
        self.next_t = t + self.delay

    def stop(self):
        self.key = None

    @property
    def active(self):
        return self.key is not None

    def poll(self, t, is_down):
        """Return the key to repeat this frame, or None.

        `is_down(key) -> bool` reports whether the key is still physically held.
        """
        if self.key is None:
            return None
        if not is_down(self.key):
            self.key = None
            return None
        if t >= self.next_t:
            self.next_t = t + self.interval
            return self.key
        return None
