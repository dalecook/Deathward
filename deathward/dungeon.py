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

"""Dungeon generation and field of view.

Rooms and corridors, connected in a spanning chain so the level is always fully
traversable, plus one "hoard" room per floor from depth 2: visibly richer, and
guarded proportionally. The dungeon puts its gold where its teeth are.

FOV is recursive shadowcasting over the eight octants -- symmetric, so if you can
see a monster, it can see you.
"""

import random

from . import config
from .items import (is_magical, roll_chest, roll_floor_armour, roll_floor_armour_magical,
                    roll_floor_boots, roll_floor_boots_magical, roll_floor_weapons,
                    roll_loot)
from .monsters import Monster, spawn_count, spawn_roster
from .traps import TRAP_POOL, Trap

WALL, FLOOR = 0, 1

# --- room shapes ---------------------------------------------------------
# Rooms used to be a uniform roll of 6-12 by 5-9. They were not, though: because a
# room is placed by trying a random rectangle and throwing it away if it overlaps
# something, the BIG ones failed that test far more often and got squeezed out. Half
# of all rooms came out between 45 and 72 tiles -- a dozen near-identical boxes.
#
# So: roll a size CLASS, and place the big ones FIRST, while there is still room for
# them.
#
#   name      w         h        area       what it is
HALL   = ("hall",   (14, 20), (9, 13))    # 126-260. bigger than your field of view.
LARGE  = ("large",  (11, 14), (7, 9))     # 77-126
MEDIUM = ("medium", (8, 11),  (6, 8))     # 48-88
SMALL  = ("small",  (5, 7),   (4, 6))     # 20-42
NOOK   = ("nook",   (3, 5),   (3, 4))     # 9-20. a cupboard with something in it.

# what the ordinary rooms roll for. halls are not in here -- they are placed first,
# deliberately, by a separate pass.
FILLER_CLASSES = [LARGE] * 20 + [MEDIUM] * 40 + [SMALL] * 30 + [NOOK] * 10

# how many halls a floor gets: 0 (40%), 1 (40%), 2 (20%).
HALL_WEIGHTS = [0] * 40 + [1] * 40 + [2] * 20

# the map is cut into sectors, and two halls never share one (nor touch). that is
# what stops them both landing in the middle.
SECTOR_COLS, SECTOR_ROWS = 3, 2


class Room:
    def __init__(self, x, y, w, h):
        self.x, self.y, self.w, self.h = x, y, w, h
        self.hall = False          # one of the big ones, placed first

    @property
    def area(self):
        return self.w * self.h

    @property
    def cx(self):
        return self.x + self.w // 2

    @property
    def cy(self):
        return self.y + self.h // 2

    def intersects(self, o, pad=1):
        return (self.x - pad < o.x + o.w and self.x + self.w + pad > o.x and
                self.y - pad < o.y + o.h and self.y + self.h + pad > o.y)

    def tiles(self):
        for yy in range(self.y, self.y + self.h):
            for xx in range(self.x, self.x + self.w):
                yield xx, yy

    def contains(self, x, y):
        return self.x <= x < self.x + self.w and self.y <= y < self.y + self.h


class Chest:
    def __init__(self, x, y, loot):
        self.x, self.y = x, y
        self.loot = list(loot)    # a LIST of ("gold", n) | ("item", f) | ("gear", k)
        self.opened = False

    def to_dict(self):
        return {"x": self.x, "y": self.y,
                "loot": [list(t) for t in self.loot], "opened": self.opened}

    @classmethod
    def from_dict(cls, data):
        c = cls(data["x"], data["y"], [tuple(t) for t in data["loot"]])
        c.opened = data["opened"]
        return c


class Drop:
    """An item lying on the floor."""

    def __init__(self, x, y, kind, payload, gift=None, bonus=0):
        self.x, self.y = x, y
        self.kind = kind          # "gold" | "item" | "gear"
        self.payload = payload
        self.gift = gift          # a one-time-per-GAME reward, spent on pickup
        self.bonus = bonus        # a weapon's masterwork/enchant +n, for placed weapons

    def to_dict(self):
        return {"x": self.x, "y": self.y, "kind": self.kind,
                "payload": self.payload, "gift": self.gift, "bonus": self.bonus}

    @classmethod
    def from_dict(cls, data):
        return cls(data["x"], data["y"], data["kind"], data["payload"],
                   gift=data["gift"], bonus=data["bonus"])


class Slain:
    """Something YOU killed, lying where it fell -- and still holding whatever it was
    carrying.

    A body with treasure on it IS a chest. You have to walk to it, stand on it, and
    spend the turn looting it, which means a fight is never quite over the moment the
    thing stops moving: the reward is lying out in the open, in the room you just made
    a lot of noise in.

    It blocks nothing. It lasts for as long as you are on this floor, and no longer:
    take the stairs, or die, and the dungeon is dealt fresh.
    """

    def __init__(self, x, y, key, color, loot=None):
        self.x, self.y = x, y
        self.key = key
        self.color = color
        self.loot = list(loot or [])

    @property
    def has_loot(self):
        return bool(self.loot)

    def to_dict(self):
        return {"x": self.x, "y": self.y, "key": self.key,
                "color": list(self.color),
                "loot": [list(t) for t in self.loot]}

    @classmethod
    def from_dict(cls, data):
        return cls(data["x"], data["y"], data["key"], tuple(data["color"]),
                   loot=[tuple(t) for t in data["loot"]])


class Corpse:
    """You, from a previous run. Still lying exactly where you fell, still holding
    everything you were holding."""

    def __init__(self, x, y, gold, weapon, gift=None, loot=None, weapon_bonus=0):
        self.x, self.y = x, y
        self.gold = gold
        self.weapon = weapon
        self.weapon_bonus = weapon_bonus
        self.gift = gift
        # anything else on the body -- including gear you swapped off while standing
        # over it. a corpse is a container like any other.
        self.loot = [tuple(t) for t in (loot or [])]
        self.taken = False


class Level:
    """A floor of the dungeon.

    TWO RANDOM NUMBER GENERATORS, and the difference between them is the whole
    design of this game's persistence:

        self.lrng  -- the STONE. Seeded from the game's world seed, so a floor's
                      rooms, corridors, entrance and stairs are cut once per GAME
                      and are identical every time you walk back in. Floor 4 is a
                      place. You can learn it.

        self.rng   -- the LIVING. Seeded per RUN, so the monsters, traps, chests,
                      potions and gold are dealt fresh every time you come back
                      down. The map is memorised; the danger is not.
    """

    def __init__(self, depth, rng, codex, restore=None):
        self.depth = depth
        self.rng = rng                                    # contents: per RUN
        self.lrng = random.Random(codex.layout_seed(depth))   # stone: per GAME
        self.w, self.h = config.MAP_W, config.MAP_H
        self.grid = [[WALL] * self.w for _ in range(self.h)]
        self.rooms = []
        self.monsters = []
        self.traps = []
        self.chests = []
        self.drops = []
        self.slain = []            # the things you have killed on this floor, this run
        self.vendor = None         # the thing that trades, if it came to this floor
        self.corpse = None
        self.stairs = (0, 0)
        self.start = (0, 0)
        self.entrance = (0, 0)     # where you came in, and where you always come in
        self.hoard = None
        # Syrinx's arena, if this is floor 8 -- reserved BEFORE the ordinary
        # population pass runs, so nothing ambient lands in it. None everywhere else.
        self._reserved_room = None
        self.visible = [[False] * self.w for _ in range(self.h)]
        # THE STONE you have seen, in any previous run of this game. A death does not
        # un-draw your map, and a Scroll of Mapping fills this in for the whole floor.
        self.explored = (codex.recall_map(depth, self.w, self.h)
                         or [[False] * self.w for _ in range(self.h)])
        # THE CONTENTS you have actually laid eyes on, THIS run. Deliberately separate
        # from `explored`: a map tells you where the rooms are, not what is sitting in
        # them. Nothing but your own line of sight ever sets this -- no scroll does.
        # It is per-run, because the contents are re-dealt every run.
        self.seen = [[False] * self.w for _ in range(self.h)]
        if restore is None:
            self._generate(codex)
        else:
            self._restore(codex, restore)

    # --- generation -----------------------------------------------------
    def _carve_room(self, r):
        for x, y in r.tiles():
            self.grid[y][x] = FLOOR

    def _carve_h(self, x1, x2, y):
        for x in range(min(x1, x2), max(x1, x2) + 1):
            self.grid[y][x] = FLOOR

    def _carve_v(self, y1, y2, x):
        for y in range(min(y1, y2), max(y1, y2) + 1):
            self.grid[y][x] = FLOOR

    # --- rooms ----------------------------------------------------------
    def _sector_bounds(self, sx, sy):
        w = self.w // SECTOR_COLS
        h = self.h // SECTOR_ROWS
        return sx * w, sy * h, w, h

    def _try_room(self, rng, size_class, sector=None):
        """One attempt at a room of this class, optionally inside a sector."""
        _, (wlo, whi), (hlo, hhi) = size_class
        w = rng.randint(wlo, whi)
        h = rng.randint(hlo, hhi)
        if sector is None:
            x = rng.randint(1, max(1, self.w - w - 2))
            y = rng.randint(1, max(1, self.h - h - 2))
        else:
            sx, sy, sw, sh = self._sector_bounds(*sector)
            x = rng.randint(max(1, sx), max(1, min(sx + sw - w, self.w - w - 2)))
            y = rng.randint(max(1, sy), max(1, min(sy + sh - h, self.h - h - 2)))
        r = Room(x, y, w, h)
        if r.x + r.w >= self.w - 1 or r.y + r.h >= self.h - 1:
            return None
        if any(r.intersects(o) for o in self.rooms):
            return None
        return r

    def _place_halls(self, rng):
        """THE HALLS GO IN FIRST, while there is still space for them.

        This is the whole point. Placing them last means they collide with everything
        already down and get thrown away, which is exactly why big rooms used to be
        so rare. Each hall gets its own sector of the map -- and with two halls, the
        sectors may not touch -- so they never both end up in the middle.
        """
        want = 1 if self.depth >= config.DEPTH_MAX else rng.choice(HALL_WEIGHTS)
        if not want:
            return
        sectors = [(sx, sy) for sy in range(SECTOR_ROWS) for sx in range(SECTOR_COLS)]
        rng.shuffle(sectors)
        placed = []
        for sec in sectors:
            if len(placed) >= want:
                break
            # two halls must not sit in EDGE-adjacent sectors (diagonal is fine, and
            # forbidding diagonals too was starving the 2-hall case).
            if any(abs(sec[0] - p[0]) + abs(sec[1] - p[1]) == 1 for p in placed):
                continue
            for _ in range(40):
                r = self._try_room(rng, HALL, sector=sec)
                if r:
                    self._carve_room(r)
                    self.rooms.append(r)
                    r.hall = True
                    placed.append(sec)
                    break

    def _quarter_of(self, x, y):
        """(col, row) in a 2x2 split of the map: (0,0) top-left .. (1,1) bottom-right."""
        return (0 if x < self.w // 2 else 1, 0 if y < self.h // 2 else 1)

    def _place_stairs(self, rng):
        """The way down goes in a RANDOM room of one of three quarters: the one across
        from the entrance (Q2), the one below it (Q3), or the diagonal (Q4) -- weighted
        25 / 25 / 50, so it is usually the long diagonal haul but often not. It is
        never in the entrance's own quarter, so it is always at least a quarter away.

        A random room within whichever quarter is chosen, so the spot is genuinely
        unpredictable -- sometimes a room right on the far edge, sometimes one you can
        almost see from the door. Uses the LAYOUT rng, so it is part of the permanent
        stone: the same room every run of this game, moving only when a new dungeon is
        cut.

        If a quarter has no rooms its weight is dropped and shared among the others --
        so 'often in Q4' stays true instead of falling back to a predictable corner.
        """
        ecol, erow = self._quarter_of(*self.entrance)
        quarters = [((1 - ecol, erow), 25),          # Q2: across
                    ((ecol, 1 - erow), 25),          # Q3: below
                    ((1 - ecol, 1 - erow), 50)]      # Q4: diagonal

        pools = []
        for q, weight in quarters:
            rooms = [r for r in self.rooms
                     if r is not self.gate_room and self._quarter_of(r.cx, r.cy) == q]
            if rooms:
                pools.append((weight, rooms))

        if not pools:                                # nothing anywhere but Q1 -- rare
            far = max((r for r in self.rooms if r is not self.gate_room),
                      key=lambda r: abs(r.cx - self.entrance[0])
                      + abs(r.cy - self.entrance[1]), default=self.gate_room)
            return (far.cx, far.cy)

        roll = rng.randint(1, sum(w for w, _ in pools))
        acc = 0
        chosen = pools[-1][1]
        for weight, rooms in pools:
            acc += weight
            if roll <= acc:
                chosen = rooms
                break
        r = rng.choice(chosen)
        return (r.cx, r.cy)

    def _cut_stone(self, codex):
        # --- the stone: cut once per GAME, identical on every respawn ----
        rng = self.lrng

        self._place_halls(rng)

        want = 9 + min(5, self.depth)
        attempts = 400
        while len(self.rooms) < want and attempts > 0:
            attempts -= 1
            r = self._try_room(rng, rng.choice(FILLER_CLASSES))
            if r is None:
                continue
            self._carve_room(r)
            self.rooms.append(r)

        # CORRIDORS. Rooms used to be joined in creation order, which was harmless
        # when they were placed at random -- but the halls now go in first, so
        # creation order would drag a corridor from one hall clear across the map to
        # the other before doubling back. Join each room to its NEAREST unconnected
        # neighbour instead: short corridors, wherever the rooms happen to be.
        if self.rooms:
            order = [self.rooms[0]]
            rest = self.rooms[1:]
            while rest:
                a = order[-1]
                b = min(rest, key=lambda r: (r.cx - a.cx) ** 2 + (r.cy - a.cy) ** 2)
                rest.remove(b)
                order.append(b)
            self.rooms = order

        for i in range(1, len(self.rooms)):
            a, b = self.rooms[i - 1], self.rooms[i]
            if rng.random() < 0.5:
                self._carve_h(a.cx, b.cx, a.cy)
                self._carve_v(a.cy, b.cy, b.cx)
            else:
                self._carve_v(a.cy, b.cy, a.cx)
                self._carve_h(a.cx, b.cx, b.cy)
        # a couple of loops so the level is not a pure tree (corridors matter)
        for _ in range(2):
            a, b = rng.sample(self.rooms, 2) if len(self.rooms) >= 2 else (None, None)
            if a and b:
                self._carve_h(a.cx, b.cx, a.cy)
                self._carve_v(a.cy, b.cy, b.cx)

        # THE ENTRANCE. Every floor has one marked arrival point, and the player
        # always starts -- and after a death, always restarts -- standing on it. On
        # floor 1 it is the gate you walked in through. It is never a guess.
        # the gate stays humble: a threshold, not a hall. it is the top-leftmost room
        # that is NOT one of the big ones, if there is one.
        modest = [r for r in self.rooms if not r.hall] or self.rooms
        gate_room = min(modest, key=lambda r: r.cx + r.cy)
        self.entrance = (gate_room.cx, gate_room.cy)
        self.start = self.entrance

        self.gate_room = gate_room
        self.stairs = self._place_stairs(rng)

        # traps belong to the STONE, not the contents. They are cut into the floor
        # once per game and they do not move -- which is the only reason "I found the
        # dart trap outside the treasury" can mean anything across runs.
        self._install_traps()

    def _place_corpse(self, codex, evict=True):
        # your own dead, from a previous run
        # Your body is where you left it. Not "somewhere on this floor" -- the exact
        # tile you fell on. The stone does not move between runs, so that tile still
        # means something, and walking back to it is walking back to the place it
        # happened.
        #
        # `evict` is False on the RESTORE path: there, the saved monster/drop/chest
        # lists are AUTHORITATIVE -- a past-run corpse does not block movement, so a
        # live monster can legitimately be standing on that tile at suspend time, and
        # clearing it here would silently delete real, saved state. It stays True on
        # the GENERATE path, where fresh-dealt content must not land on the grave.
        c = codex.corpse_at(self.depth)
        if c:
            cx, cy = c.get("x", 0), c.get("y", 0)
            if evict and not self.walkable(cx, cy):
                spot = self._free_tile()          # only if the stone changed under it
                cx, cy = spot if spot else self.entrance
            self.corpse = Corpse(cx, cy, c.get("gold", 0), c.get("weapon"),
                                 c.get("gift"), c.get("loot"),
                                 weapon_bonus=c.get("weapon_bonus", 0))
            if evict:
                # nothing else may occupy the grave
                self.monsters = [m for m in self.monsters if (m.x, m.y) != (cx, cy)]
                self.drops = [d for d in self.drops if (d.x, d.y) != (cx, cy)]
                self.chests = [ch for ch in self.chests if (ch.x, ch.y) != (cx, cy)]

    def _generate(self, codex):
        self._cut_stone(codex)

        # snapshot the persisted ground magicals BEFORE this floor's fresh rolls, so a
        # weapon rolled THIS life (which _populate records into codex.magical_ground) is
        # not also replayed as if it were an heirloom.
        persisted_magicals = dict(codex.magical_ground)
        persisted_boots = dict(codex.boots_ground)
        persisted_armours = dict(codex.armour_ground)
        if self.depth >= config.DEPTH_MAX:
            self._populate_boss()
        elif self.depth == config.SYRINX_DEPTH:
            # her arena is reserved BEFORE the ordinary pass runs, so _free_tile
            # (and the hoard/orc-pack room picks) never put ambient content in it.
            self._reserved_room = self._syrinx_arena()
            self._populate(codex)
            self._populate_syrinx()
        else:
            self._populate(codex)
        self._replay_magicals(persisted_magicals)
        self._replay_magicals(persisted_boots)
        self._replay_magicals(persisted_armours)

        self._place_corpse(codex)

    def _restore(self, codex, data):
        """Parallel to _generate: cut the same stone, then overlay the saved
        dynamic state instead of dealing a fresh floor. The run RNG is untouched."""
        from .monsters import Monster
        from .vendor import Vendor
        self._cut_stone(codex)
        if self.depth == config.SYRINX_DEPTH:
            # her pillar WALL tiles are not part of the stone _cut_stone lays down --
            # they must be re-carved here, exactly as _populate_syrinx does on the
            # generate path, or a resumed floor 8 loses her arena's terrain.
            self._carve_syrinx_pillars()
        self.monsters = [Monster.from_dict(m) for m in data["monsters"]]
        self.drops = [Drop.from_dict(d) for d in data["drops"]]
        self.chests = [Chest.from_dict(c) for c in data["chests"]]
        self.slain = [Slain.from_dict(s) for s in data["slain"]]
        self.vendor = Vendor.from_dict(data["vendor"]) if data["vendor"] else None
        # traps were re-cut by _cut_stone (same stone); restore which have sprung
        sprung = {(t["key"], t["x"], t["y"]) for t in data["traps"] if t["sprung"]}
        for tr in self.traps:
            if (tr.key, tr.x, tr.y) in sprung:
                tr.sprung = True
        # the fog of CONTENTS you had laid eyes on this run
        self.seen = [row[:] for row in data["seen"]]
        # the hoard marker: re-link to the room at the saved centre
        self.hoard = None
        if data["hoard"] is not None:
            hx, hy = data["hoard"]
            for r in self.rooms:
                if (r.cx, r.cy) == (hx, hy):
                    self.hoard = r
                    break
        self._place_corpse(codex, evict=False)

    def to_dict(self):
        return {
            "depth": self.depth,
            "monsters": [m.to_dict() for m in self.monsters],
            "drops": [d.to_dict() for d in self.drops],
            "chests": [c.to_dict() for c in self.chests],
            "slain": [s.to_dict() for s in self.slain],
            "vendor": self.vendor.to_dict() if self.vendor else None,
            "traps": [t.to_dict() for t in self.traps],
            "hoard": [self.hoard.cx, self.hoard.cy] if self.hoard else None,
            "seen": [row[:] for row in self.seen],
        }

    def _replay_magicals(self, persisted):
        """Magical weapons AND boots persist where they lie, across every life -- the
        trophies of your past selves, salted through the dungeon. Re-place this floor's,
        clearing whatever the fresh deal put on their tiles, exactly like a corpse."""
        for key, loc in persisted.items():
            if loc["depth"] != self.depth:
                continue
            mx, my = loc["x"], loc["y"]
            if not self.walkable(mx, my):
                continue
            self.monsters = [m for m in self.monsters if (m.x, m.y) != (mx, my)]
            self.drops = [d for d in self.drops if (d.x, d.y) != (mx, my)]
            self.chests = [ch for ch in self.chests if (ch.x, ch.y) != (mx, my)]
            self.drops.append(Drop(mx, my, "gear", key, bonus=loc.get("bonus", 0)))

    def _free_tile(self, avoid_start=False, room=None, rng=None):
        """A free floor tile, or None if there isn't one.

        `rng` selects which clock this placement runs on: pass the layout rng for
        things cut into the stone (traps), or leave it for the per-run rng.

        This used to fall back to returning `self.start` when it ran out of tries,
        which quietly spawned monsters ON the player. Returning None and making the
        callers skip the placement is the only honest failure here.
        """
        rng = rng or self.rng
        for _ in range(500):
            if room:
                x = rng.randint(room.x, room.x + room.w - 1)
                y = rng.randint(room.y, room.y + room.h - 1)
            else:
                r = rng.choice(self.rooms)
                x = rng.randint(r.x, r.x + r.w - 1)
                y = rng.randint(r.y, r.y + r.h - 1)
            if self.grid[y][x] != FLOOR:
                continue
            if (x, y) == self.stairs:
                continue
            if (room is None and self._reserved_room is not None
                    and self._reserved_room.contains(x, y)):
                continue          # Syrinx's arena: nothing ambient may land in it
            if avoid_start and max(abs(x - self.start[0]), abs(y - self.start[1])) < 7:
                continue
            if any(m.x == x and m.y == y for m in self.monsters):
                continue
            if any(t.x == x and t.y == y for t in self.traps):
                continue
            if any(c.x == x and c.y == y for c in self.chests):
                continue
            if any(d.x == x and d.y == y for d in self.drops):
                continue
            return x, y
        return None

    def _far_room_spot(self):
        """A free tile in the room farthest (Manhattan) from the entrance, skipping
        the gate room; None if no such tile is free. Used for floor 1's guaranteed
        placements, which sit as far from the gate as the level allows."""
        far_rooms = sorted(
            (r for r in self.rooms if r is not self.gate_room),
            key=lambda r: -(abs(r.cx - self.entrance[0]) +
                            abs(r.cy - self.entrance[1])))
        for room in far_rooms:
            spot = self._free_tile(avoid_start=True, room=room)
            if spot:
                return spot
        return None

    def _install_traps(self):
        """Cut the traps into the floor. Uses the LAYOUT rng, so floor 4's dart trap
        is in the same doorway in every run of this game."""
        rng = self.lrng
        d = self.depth
        n = (4 if d >= config.DEPTH_MAX else 3 + d // 2 + rng.randint(0, 2))
        for _ in range(n):
            spot = self._free_tile(avoid_start=True, rng=rng)
            if spot:
                self.traps.append(Trap(rng.choice(TRAP_POOL), *spot))

    def _populate(self, codex):
        rng = self.rng
        d = self.depth
        table = spawn_roster(d)

        for _ in range(spawn_count(d, rng)):
            spot = self._free_tile(avoid_start=True)
            if spot:
                self.monsters.append(Monster(rng.choice(table), *spot))

        for _ in range(2 + rng.randint(0, 2)):
            spot = self._free_tile(avoid_start=True)
            if spot:
                self.chests.append(Chest(spot[0], spot[1], roll_chest(rng, d)))

        for _ in range(1 + rng.randint(0, 2)):
            spot = self._free_tile(avoid_start=True)
            if spot:
                kind, payload = roll_loot(rng, d)
                self.drops.append(Drop(spot[0], spot[1], kind, payload))

        # THE FLOOR'S WEAPONS. Scarce and generation-placed: floors 1-7 hold at most one,
        # decided by roll_floor_weapons; floors 8-14 can hold two (an enhanced-Steel find
        # plus a rare magical). Floor 1 is a guaranteed Bone Axe, placed as far from the
        # gate as the level allows -- a reward for exploring, and the safety valve against
        # a run of empty floors stranding you on the shiv. This is unconditional (never
        # gated on Kodex state) and separate from the floor-1 gear GIFT below: the gift is
        # a once-per-GAME armour/boots upgrade (gear_pool no longer includes weapons), so
        # the two coexist without overlap.
        for wkey, wbonus in roll_floor_weapons(rng, d, exclude=codex.magical_generated):
            # floor 1's single Bone Axe goes as far from the gate as the level allows (a
            # reward for exploring); the deep floors' finds land on any free tile.
            spot = self._far_room_spot() if d == 1 else None
            if spot is None:
                spot = self._free_tile(avoid_start=True)
            if spot:
                self.drops.append(Drop(spot[0], spot[1], "gear", wkey, bonus=wbonus))
                if is_magical(wkey):
                    # it now EXISTS: never rolls again, and lies here until picked up.
                    codex.record_magical_placed(wkey, d, spot[0], spot[1], wbonus)

        # THE FLOOR'S ORDINARY BOOT. Like the weapons: scarce, generation-placed, at most one
        # per floor -- never from the generic loot pool, never sold or gifted. Banded to floors
        # 2-15 by roll_floor_boots; placed on any free tile away from the gate.
        for bkey in roll_floor_boots(rng, d):
            spot = self._free_tile(avoid_start=True)
            if spot:
                self.drops.append(Drop(spot[0], spot[1], "gear", bkey))

        # THE FLOOR'S MAGICAL BOOT (floors 8+). The rare slot, like the magical weapons:
        # scarce, one-per-game unique (exclude the already-generated), generation-placed --
        # never from the generic loot pool.
        mbkey = roll_floor_boots_magical(rng, d, exclude=codex.boots_generated)
        if mbkey:
            spot = self._free_tile(avoid_start=True)
            if spot:
                self.drops.append(Drop(spot[0], spot[1], "gear", mbkey))
                # it now EXISTS: never rolls again this game (persistence lands in Plan B).
                codex.record_magical_boot_placed(mbkey, d, spot[0], spot[1])

        # THE FLOOR'S ORDINARY ARMOUR. Like the boots: scarce, generation-placed, at most
        # one per floor -- never from the generic loot pool, never sold or gifted. Banded to
        # floors 2-15 by roll_floor_armour; deep floors may make it masterwork (+1/+2).
        for akey, abonus in roll_floor_armour(rng, d):
            spot = self._free_tile(avoid_start=True)
            if spot:
                self.drops.append(Drop(spot[0], spot[1], "gear", akey, bonus=abonus))

        # THE FLOOR'S MAGICAL ARMOUR (floors 8+). The rare slot, like the magical boots:
        # scarce, one-per-game unique, generation-placed. Boss-reserved pieces are excluded.
        makey = roll_floor_armour_magical(rng, d, exclude=codex.armour_generated)
        if makey:
            spot = self._free_tile(avoid_start=True)
            if spot:
                self.drops.append(Drop(spot[0], spot[1], "gear", makey))
                codex.record_magical_armour_placed(makey, d, spot[0], spot[1])

        # FLOOR 1 PAYS FOR CURIOSITY -- ONCE. Exactly one guaranteed gift, placed as far
        # from the gate as the level allows, so it is a reward for exploring rather than a
        # handout at the door. It is a 50/50 coin-flip: a Bone Sword (start better at
        # killing) or a Leather Jerkin (start better at surviving) -- the whole triad
        # thesis in the first pickup. Claimed once per GAME: it must not regrow on every
        # respawn, or death becomes a way to farm it.
        if d == 1 and not codex.gift_claimed("floor1"):
            spot = self._far_room_spot()
            if spot:
                gkey = "bone_sword" if rng.random() < 0.5 else "leather"
                self.drops.append(Drop(spot[0], spot[1], "gear", gkey, gift="floor1"))

        # one chest per floor from depth 2 is not a chest
        if d >= 2 and self.chests and rng.random() < 0.55:
            c = rng.choice(self.chests)
            m = Monster("mimic", c.x, c.y)
            self.monsters.append(m)
            self.chests.remove(c)

        # the hoard: visibly richer, and guarded in proportion. never the room you
        # walk in on -- its guards would be standing on the welcome mat.
        hoard_rooms = [r for r in self.rooms
                       if r is not self.gate_room and r is not self._reserved_room
                       and not r.contains(*self.stairs)]
        if d >= 2 and hoard_rooms:
            # the dungeon puts its gold where its teeth are: a hall, if there is one
            halls = [r for r in hoard_rooms if r.hall]
            room = rng.choice(halls if halls and rng.random() < 0.7 else hoard_rooms)
            self.hoard = room
            # gold keeps scaling with depth -- a deep hoard is a rich hoard. the
            # GUARDS, though, are capped: without this a floor-19 hoard alone adds
            # eight monsters on top of an already-full floor.
            for _ in range(2 + min(d, 10) // 2):
                spot = self._free_tile(avoid_start=True, room=room)
                if spot:
                    self.drops.append(Drop(spot[0], spot[1], "gold",
                                           rng.randint(12, 30) + d * 5))
            for _ in range(2 + min(d, 9) // 3):
                spot = self._free_tile(avoid_start=True, room=room)
                if spot:
                    self.monsters.append(Monster(rng.choice(table), *spot))
            spot = self._free_tile(avoid_start=True, room=room)
            if spot:
                self.chests.append(Chest(spot[0], spot[1], roll_chest(rng, d + 2)))

        self._place_orc_packs(rng, d)

    def _place_orc_packs(self, rng, d):
        """Orcs arrive as a PACK, clustered in one room -- not scattered a tile at a
        time like everything else. A floor deep enough gets one pack, and the deepest
        floors sometimes get two. They start clustered and calm; they come for you only
        once one of them actually SEES you (see _ai_orc).
        """
        if d < 8:
            return
        packs = 1 if rng.random() < 0.5 else 0
        if d >= 14 and rng.random() < 0.4:
            packs += 1
        # a pack needs elbow room -- a nook cannot hold five orcs, so pick a room big
        # enough that the whole pack lands (and never the gate).
        rooms = [r for r in self.rooms
                 if r is not self.gate_room and r is not self._reserved_room
                 and r.area >= 18]
        rooms = (rooms
                 or [r for r in self.rooms
                     if r is not self.gate_room and r is not self._reserved_room]
                 or self.rooms)
        for _ in range(packs):
            room = rng.choice(rooms)
            placed = 0
            for _ in range(rng.randint(3, 5)):
                # prefer the pack's own room; if it is too crowded to seat the orc,
                # drop it anywhere free rather than losing it -- a short pack is worse
                # than a slightly scattered one, and the pack regroups anyway.
                spot = (self._free_tile(avoid_start=True, room=room)
                        or self._free_tile(avoid_start=True))
                if spot:
                    self.monsters.append(Monster("orc", *spot))
                    placed += 1
            # a "pack" of one or two is not a pack. top it up to the promised three.
            while placed < 3:
                spot = self._free_tile(avoid_start=True)
                if not spot:
                    break
                self.monsters.append(Monster("orc", *spot))
                placed += 1

    def _populate_boss(self):
        rng = self.rng
        # the arena is the biggest room that is not the one you walk in on. it must
        # be keyed off the GATE room, not rooms[0] -- the entrance is the top-leftmost
        # room, which is not necessarily the first one generated, and getting this
        # wrong spawns the Warden on the player's face.
        candidates = [r for r in self.rooms if r is not self.gate_room] or self.rooms
        arena = max(candidates, key=lambda r: r.w * r.h)
        x, y = arena.cx, arena.cy
        self.monsters.append(Monster("warden", x, y))

        # pillars: the room hands you exactly the cover the Kodex told you to use.
        # they must never touch the Warden's own tile, or it gets entombed in rock
        # and the game becomes unwinnable.
        if arena.w >= 9 and arena.h >= 7:
            for px, py in [(arena.x + 2, arena.y + 2),
                           (arena.x + arena.w - 3, arena.y + 2),
                           (arena.x + 2, arena.y + arena.h - 3),
                           (arena.x + arena.w - 3, arena.y + arena.h - 3)]:
                if (px, py) == (x, y) or max(abs(px - x), abs(py - y)) <= 1:
                    continue
                if 0 < px < self.w - 1 and 0 < py < self.h - 1:
                    self.grid[py][px] = WALL
        self.grid[y][x] = FLOOR      # belt and braces: the Warden always has a floor
        table = spawn_roster(self.depth)
        for _ in range(4):
            spot = self._free_tile(avoid_start=True)
            if spot:
                self.monsters.append(Monster(rng.choice(table), *spot))
        for _ in range(2):
            spot = self._free_tile(avoid_start=True)
            if spot:
                self.chests.append(Chest(spot[0], spot[1], roll_chest(rng, 8)))
        self.stairs = None      # there is no down from here. there is only the Warden.

    def _syrinx_arena(self):
        """The biggest room that is not the gate room -- same rule as the Warden's
        arena. A pure function of the STONE (self.rooms/self.gate_room never change
        after generation), so population, a resumed run and the AI's retreat target
        all recompute the identical room without anything about it being saved."""
        candidates = [r for r in self.rooms if r is not self.gate_room] or self.rooms
        return max(candidates, key=lambda r: r.w * r.h)

    def syrinx_pillars(self):
        """Six tiles scattered through her arena -- her hiding spots, the surface
        her emergence telegraph appears on, and the line-of-sight cover the player
        can use against her blow. Never the stairs tile, so carving them can never
        wall off the way down. A freak arena too small for the spread falls back to
        just its centre, so she always has SOMEWHERE to hide -- and if that centre
        happens to BE the stairs tile (real: the stairs always sit on some room's
        exact centre, and this fires whenever that room is also the small arena),
        nudge one tile off it instead of leaving her with nowhere at all."""
        arena = self._syrinx_arena()
        if arena.w < 7 or arena.h < 6:
            cx, cy = arena.cx, arena.cy
            if (cx, cy) != self.stairs:
                return [(cx, cy)]
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = cx + dx, cy + dy
                if (arena.x <= nx < arena.x + arena.w
                        and arena.y <= ny < arena.y + arena.h
                        and (nx, ny) != self.stairs):
                    return [(nx, ny)]
            return []
        xs = [arena.x + 2, arena.x + arena.w // 2, arena.x + arena.w - 3]
        ys = [arena.y + 2, arena.y + arena.h - 3]
        spots = [(x, y) for y in ys for x in xs]
        return [(x, y) for x, y in spots if (x, y) != self.stairs]

    def _carve_syrinx_pillars(self):
        """Cut her pillar tiles into the grid. Called on both the GENERATE path (via
        _populate_syrinx) and the RESTORE path -- her arena's WALL tiles are not part
        of the stone _cut_stone lays down, so a resumed run must re-carve them itself
        or she ends up hidden on open floor (see the suspend/resume bug this fixes)."""
        for px, py in self.syrinx_pillars():
            self.grid[py][px] = WALL

    def _populate_syrinx(self):
        """Her arena, carved AFTER the floor's ordinary pass (see _generate) -- floor
        8 is not the Warden's floor: it keeps its stairs and everything else."""
        spots = self.syrinx_pillars()
        if not spots:
            return
        self._carve_syrinx_pillars()
        self.monsters.append(Monster("syrinx", *spots[0]))

    # --- queries --------------------------------------------------------
    def in_bounds(self, x, y):
        return 0 <= x < self.w and 0 <= y < self.h

    def walkable(self, x, y):
        return self.in_bounds(x, y) and self.grid[y][x] == FLOOR

    def opaque(self, x, y):
        return not self.in_bounds(x, y) or self.grid[y][x] == WALL

    def trap_at(self, x, y):
        for t in self.traps:
            if t.x == x and t.y == y:
                return t
        return None

    def chest_at(self, x, y):
        for c in self.chests:
            if c.x == x and c.y == y and not c.opened:
                return c
        return None

    def drop_at(self, x, y):
        for d in self.drops:
            if d.x == x and d.y == y:
                return d
        return None

    def free_spot_for_vendor(self, rng, avoid):
        """Somewhere to stand: not the entrance, not the stairs, not on top of the
        player, and not on anything else."""
        for _ in range(400):
            r = rng.choice(self.rooms)
            x = rng.randint(r.x, r.x + r.w - 1)
            y = rng.randint(r.y, r.y + r.h - 1)
            if not self.walkable(x, y):
                continue
            if (x, y) in (self.entrance, self.stairs, avoid):
                continue
            if self.trap_at(x, y) or self.chest_at(x, y) or self.drop_at(x, y):
                continue
            if any(m.x == x and m.y == y for m in self.monsters):
                continue
            if self.corpse and (self.corpse.x, self.corpse.y) == (x, y):
                continue
            return x, y
        return None

    def drops_at(self, x, y):
        """ALL of them. You can dump a stack of three scrolls on one tile, and all
        three have to be listed and retrievable -- not just the first."""
        return [d for d in self.drops if d.x == x and d.y == y]

    # --- field of view --------------------------------------------------
    def compute_fov(self, px, py, radius=config.FOV_RADIUS):
        for row in self.visible:
            for i in range(len(row)):
                row[i] = False
        self.visible[py][px] = True
        self.explored[py][px] = True
        self.seen[py][px] = True
        for octant in range(8):
            self._cast(px, py, 1, 1.0, 0.0, radius, octant)

    _MULT = [
        (1, 0, 0, -1), (0, 1, -1, 0), (0, -1, -1, 0), (-1, 0, 0, -1),
        (-1, 0, 0, 1), (0, -1, 1, 0), (0, 1, 1, 0), (1, 0, 0, 1),
    ]

    def _cast(self, cx, cy, row, start, end, radius, octant):
        if start < end:
            return
        xx, xy, yx, yy = self._MULT[octant]
        radius2 = radius * radius
        for j in range(row, radius + 1):
            dx, dy = -j - 1, -j
            blocked = False
            new_start = start
            while dx <= 0:
                dx += 1
                mx = cx + dx * xx + dy * xy
                my = cy + dx * yx + dy * yy
                l_slope = (dx - 0.5) / (dy + 0.5)
                r_slope = (dx + 0.5) / (dy - 0.5)
                if start < r_slope:
                    continue
                if end > l_slope:
                    break
                if dx * dx + dy * dy <= radius2 and self.in_bounds(mx, my):
                    self.visible[my][mx] = True
                    self.explored[my][mx] = True
                    self.seen[my][mx] = True
                if blocked:
                    if self.opaque(mx, my):
                        new_start = r_slope
                        continue
                    blocked = False
                    start = new_start
                else:
                    if self.opaque(mx, my) and j < radius:
                        blocked = True
                        self._cast(cx, cy, j + 1, start, l_slope, radius, octant)
                        new_start = r_slope
            if blocked:
                break

    def reveal_all(self):
        """A Scroll of Mapping. It unrolls the STONE -- rooms, corridors, the stairs.

        It touches `explored` and never `seen`, which is the whole point: a map is a
        map. It does not tell you where the gold is, it does not tell you which chest
        is a mimic, and it very deliberately does not tell you where the traps are.
        You still have to walk in there and find out.
        """
        for y in range(self.h):
            for x in range(self.w):
                if self.grid[y][x] == FLOOR:
                    self.explored[y][x] = True
                    for dx in (-1, 0, 1):
                        for dy in (-1, 0, 1):
                            if self.in_bounds(x + dx, y + dy):
                                self.explored[y + dy][x + dx] = True
