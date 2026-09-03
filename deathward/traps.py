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

"""Traps.

An un-codexed trap is drawn as clean floor. It is not hidden by a dice roll and it
is not revealed by a search skill -- it is invisible because you do not know that
such a thing exists. The moment a death teaches you what a dart trap is, every
dart trap you ever walk near is drawn on your floor, forever, in every future run.

That is the sharpest form of the whole game's thesis: the trap did not change. You
did.

Monsters trigger traps too. The fire glyph in particular is not an obstacle -- once
you can see it, it is a weapon.
"""

from . import config

TRAP_COLORS = {
    "dart":  (232, 96, 120),
    "spike": (200, 120, 96),
    "gas":   (150, 220, 130),
    "alarm": (240, 200, 90),
    "glyph": (255, 130, 70),
}

TRAP_NAMES = {
    "dart":  "dart trap",
    "spike": "spike pit",
    "gas":   "gas vent",
    "alarm": "alarm rune",
    "glyph": "fire glyph",
}

# a soft-soled boot is too light to depress a plate. it does nothing about a vent
# or a rune, which are not weight-triggered at all.
PRESSURE = {"dart", "spike", "alarm"}

TRAP_POOL = ["dart", "dart", "spike", "spike", "gas", "alarm", "glyph"]


class Trap:
    def __init__(self, key, x, y):
        self.key = key
        self.x, self.y = x, y
        self.sprung = False       # spent traps stay visible as scorch/holes

    @property
    def name(self):
        return TRAP_NAMES[self.key]

    def to_dict(self):
        return {"key": self.key, "x": self.x, "y": self.y, "sprung": self.sprung}

    @classmethod
    def from_dict(cls, data):
        t = cls(data["key"], data["x"], data["y"])
        t.sprung = data["sprung"]
        return t

    def trigger(self, world, victim):
        """victim is world.player or a Monster. Traps do not care which."""
        is_player = victim is world.player
        if is_player and world.player.boots.trait == "featherfall":
            world.log("You drift above the %s -- your feet never touch it." % self.name,
                      config.MANA)
            return
        if is_player and self.key in PRESSURE:
            # you are not on it at all (levitation). the pit and the dart wait for
            # someone heavier.
            if world.player.levitate > 0:
                world.log("You drift over the plate. Your feet never touch it.",
                          config.MANA)
                return
        if self.key == "gas" and self.sprung:
            return

        # did the player SEE this happen? you learn a trap by watching one fire --
        # under you, or under something else while you are looking at it.
        witnessed = is_player or world.visible(self.x, self.y)

        fn = getattr(self, "_" + self.key)
        fn(world, victim, is_player)
        if is_player:
            world.codex.stats["traps_triggered"] += 1
        if witnessed:
            world.discover_trap(self)

    # --- the five ------------------------------------------------------
    def _wall_behind(self, world):
        """Which wall the dart comes out of. It has to come from somewhere, and the
        player should be able to see where."""
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            x, y = self.x, self.y
            for _ in range(12):
                x += dx
                y += dy
                if not world.walkable(x, y):
                    return (x, y)
        return (self.x - 1, self.y)

    def _dart(self, world, victim, is_player):
        self.sprung = True
        dmg = world.rng.randint(3, 7)
        # show the dart actually crossing the room. a wound with no visible cause is
        # a wound you cannot learn from.
        world.add_fx("dart", self.x, self.y, color=(255, 130, 130), life=0.34,
                     tiles=[self._wall_behind(world)])
        world.shake(3)
        if is_player:
            world.log("A dart whines out of the wall!", config.TRAP)
            world.hurt_player(dmg, "dart")
        else:
            world.log("A dart thuds into the %s." % victim.name, config.DIM)
            world.hurt_monster(victim, dmg, source="dart")

    def _spike(self, world, victim, is_player):
        dmg = world.rng.randint(4, 8)
        world.add_fx("spikes", self.x, self.y, color=(206, 168, 140), life=0.6)
        world.shake(4)
        if is_player:
            world.log("The floor gives way -- rusted iron!", config.TRAP)
            world.hurt_player(dmg, "spike")
            world.player.stuck = 1          # a turn spent climbing out
        else:
            world.hurt_monster(victim, dmg, source="spike")
            if not world._status_immune(victim):
                victim.stunned = max(victim.stunned, 1)

    def _gas(self, world, victim, is_player):
        self.sprung = True
        # the gas has to be SEEN to be understood: it does no damage on the tile, so
        # without a cloud the player just starts bleeding for no visible reason
        world.add_fx("gas", self.x, self.y, color=(150, 220, 130), life=1.6,
                     tiles=world.burning_tiles(self.x, self.y, 1))
        if is_player:
            world.log("A vent hisses. The air turns green.", config.TRAP)
            world.player.poison = max(world.player.poison, 8)
            world.player.poison_source = "gas"
        else:
            victim.hp -= 2

    def _alarm(self, world, victim, is_player):
        self.sprung = True
        # THE MOST IMPORTANT ONE. It does no damage at all -- the only thing that
        # happens is that every monster on the floor starts walking toward you, and
        # if the player does not SEE that happen, the trap taught them nothing and
        # the next thirty seconds are inexplicable.
        world.add_fx("shout", self.x, self.y, radius=30, color=(250, 214, 96),
                     life=1.15)
        if is_player:
            world.log("The rune SHRIEKS. Every ear on this floor just heard it.",
                      config.TRAP)
            world.wake_all()
            world.shake(8)
            # every thing that just woke up, marked where it stands
            world.add_fx("woke", life=1.3, color=config.BLOOD,
                         tiles=[(m.x, m.y) for m in world.level.monsters])

    def _glyph(self, world, victim, is_player):
        self.sprung = True
        world.log("The glyph ignites!", (255, 140, 70))
        world.shake(6)
        # SHOW IT. The blast covers the glyph and every tile touching it, so SET THAT
        # FLOOR ON FIRE -- the burning tiles are exactly the tiles that take damage,
        # so the player can see the shape of the thing that burned them and learn to
        # stand outside it.
        world.add_fx("burning", self.x, self.y, life=0.95,
                     tiles=world.burning_tiles(self.x, self.y, 1))
        world.add_fx("burst", self.x, self.y, radius=1.0, color=(255, 140, 60),
                     life=0.5)
        # it burns everything adjacent, including whatever set it off, including you
        for m in list(world.monsters):
            if max(abs(m.x - self.x), abs(m.y - self.y)) <= 1:
                world.hurt_monster(m, world.rng.randint(4, 9), source="glyph")
        p = world.player
        if max(abs(p.x - self.x), abs(p.y - self.y)) <= 1:
            world.hurt_player(world.rng.randint(4, 9), "glyph")
