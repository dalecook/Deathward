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
