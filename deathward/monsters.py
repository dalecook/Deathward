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

"""The things that live down here.

Every monster obeys the design rule: **behaviour never depends on the player's
knowledge**. A brute winds up for exactly one turn whether or not you have ever
heard of a brute. What knowledge buys is the right to SEE the wind-up -- an
un-codexed monster is drawn as a '?' with no health bar and no readable intent.

Each monster is built around one idea, and each idea has a counter that is a
tactic rather than a stat:

    rat      arithmetic          -> fight them in a corridor, not a room
    kobold   consequences        -> do not let a wounded one escape
    spitter  geometry            -> break the straight line
    brute    tempo               -> step off the wind-up, then punish
    wraith   your assumptions    -> walls and armour are worthless; speed is not
    poltergeist  the unseen      -> you cannot fight it until you have LEARNED it
    mimic    trust               -> the chest opens you back
    warden   the exam            -> all of the above, at once
"""

import random

from . import config

DIRS8 = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]
DIRS4 = [(0, -1), (0, 1), (-1, 0), (1, 0)]


class Template:
    def __init__(self, key, name, glyph, color, hp, lo, hi, speed, xp=1, note=""):
        self.key, self.name, self.glyph, self.color = key, name, glyph, color
        self.hp, self.lo, self.hi, self.speed = hp, lo, hi, speed
        self.xp, self.note = xp, note


TEMPLATES = {
    # floor 1's creature: it bites, it is annoying, and it is survivable. it exists
    # so a first-time player learns the shape of a fight before the dungeon starts
    # charging for the lesson.
    "angry_rat": Template("angry_rat", "Angry Rat", "r", (188, 140, 108), 3, 1, 2, 115),
    "rat":     Template("rat", "Plague Rat", "r", (156, 176, 132), 4, 1, 3, 150),
    "kobold":  Template("kobold", "Kobold", "k", (150, 200, 120), 11, 3, 6, 100),
    "spitter": Template("spitter", "Bile Spitter", "s", (170, 230, 110), 9, 3, 6, 90),
    "brute":   Template("brute", "Brute", "B", (226, 140, 96), 26, 8, 15, 55),
    "wraith":  Template("wraith", "Wraith", "w", (186, 156, 240), 10, 4, 7, 70),
    "mimic":   Template("mimic", "Mimic", "m", (198, 152, 88), 18, 6, 11, 100),
    # comes in a pack with keen eyes: the moment one has a clear line to you the whole
    # pack is on you, going for the nearest living thing whether or not it is on your
    # side. slightly faster than you -- but break line of sight and it forgets you at
    # once and regroups, so a corner is as good as a weapon.
    "orc":     Template("orc", "Orc", "o", (108, 132, 76), 9, 2, 5, 105),
    # it will not stand and fight. it blinks to a random tile beside you, hits, and is
    # stuck one turn recovering -- that stuck turn is the ONLY moment you can land a
    # blow, and it takes several. it ignores your body and the walls when it blinks.
    "flicker": Template("flicker", "Flicker", "f", (150, 210, 236), 16, 3, 6, 100),
    # a slow floating eye, and a two-beat fighter. FIRST it gazes down its line of
    # sight and freezes you where you stand -- pure control, no damage, and while you
    # cannot move everything else on the floor closes in. THEN, on its very next turn,
    # it follows the freeze with a baleful ray for real damage (lo..hi below) -- so
    # even one-on-one it is not harmless. The ray only ever comes right after a freeze,
    # so the whole two-hit combo is on a cooldown.
    "beholder": Template("beholder", "Beholder", "e", (198, 120, 210), 20, 5, 9, 75),
    # a brute cut from stone: tougher, and it shrugs off steel. the only thing that
    # reliably hurts it is fire. it is NOT slow -- it moves at nine-tenths of your
    # pace, faster than any brute, and once it has seen you it never stops coming and
    # never loses you. you cannot outrun it and you cannot hide from it: you either
    # burn it down, or you leave the floor.
    "golem":   Template("golem", "Stone Golem", "G", (150, 150, 160), 34, 9, 16, 90),
    # you never see it coming. it walks through your walls and through your body and
    # does almost nothing per hit -- but you cannot see it, cannot wall it out, and
    # cannot swing at what you cannot find. knowledge is what drags it into the light;
    # even then it takes several blows, so seeing it is the start of the fight, not
    # the end.
    "poltergeist": Template("poltergeist", "Poltergeist", "p", (206, 214, 230), 16, 1, 3, 90),
    "warden":  Template("warden", "The Warden", "W", (250, 92, 110), 70, 7, 13, 95),
}

# --- damage rules --------------------------------------------------------
# The stone golem is the game's first "you do not kill this with your sword" lesson.
# Steel barely chips it; fire cracks it wide open. The source strings are the same
# ones the combat and traps already pass ("player", "burn", "glyph", "scroll", ...).
FIRE_SOURCES = ("burn", "glyph", "scroll")

def damage_multiplier(monster_key, source):
    if monster_key == "golem":
        if source in FIRE_SOURCES:
            return 2.0       # stone cracks in fire
        if source in ("player", "thorns", "dart", "spike"):
            return 0.25      # steel, darts, spikes -- it barely notices
    return 1.0


INCORPOREAL = {"wraith", "poltergeist"}     # walk through walls, ignore armour


def is_incorporeal(key):
    return key in INCORPOREAL

# what walks which floor. floor 1 is angry rats and the occasional kobold -- the
# plague rat (faster, sicker, and it comes in numbers) does not appear until 2.
#
# The first stretch is hand-tuned: each floor introduces exactly one new thing, in
# the order the Kodex expects to teach it. Past that, the roster is GENERATED from
# depth (see spawn_roster) so the dungeon can be any number of floors deep without a
# giant hand-written table -- the deeper you go, the more the weak things fall away
# and the more the roster is brutes and wraiths.
SPAWN_TABLE = {
    1: ["angry_rat", "angry_rat", "angry_rat", "angry_rat", "kobold"],
    2: ["angry_rat", "rat", "rat", "kobold", "kobold", "spitter"],
    3: ["rat", "kobold", "spitter", "spitter", "brute"],
    4: ["rat", "kobold", "kobold", "spitter", "brute", "wraith"],
    5: ["kobold", "spitter", "brute", "wraith", "wraith"],
    6: ["kobold", "spitter", "spitter", "brute", "flicker", "wraith"],
    7: ["spitter", "brute", "brute", "flicker", "wraith", "kobold"],
}

# the deepest hand-tuned floor. everything below is generated.
HAND_TUNED_DEPTH = max(SPAWN_TABLE)


def spawn_roster(depth):
    """The pool a floor draws its monsters from.

    Floors 1..HAND_TUNED_DEPTH are the carefully sequenced intro. Deeper than that,
    build a roster whose mix hardens with depth: the plague rats and kobolds thin out,
    the brutes and wraiths multiply. There are only so many kinds of monster, so past
    the intro the dungeon escalates by WEIGHT, not by variety -- until there is
    something new to put down here, a floor 15 is a floor 8 with more teeth.
    """
    if depth in SPAWN_TABLE:
        return SPAWN_TABLE[depth]

    over = depth - HAND_TUNED_DEPTH               # how far past the intro we are
    roster = []
    roster += ["kobold"] * max(0, 2 - over // 3)  # the soldiers fade out
    roster += ["spitter"] * 2
    roster += ["brute"] * (2 + over // 2)         # ...and the heavies pile up
    roster += ["flicker"] * 2                      # the blinker haunts every deep floor
    roster += ["wraith"] * (2 + over // 2)
    if depth >= 10:                               # the unseen thing haunts deep floors
        roster += ["poltergeist"] * (1 + over // 5)
    if depth >= 11:                               # stone golems join the deep floors
        roster += ["golem"] * (1 + over // 4)
    if depth >= 13:                               # and the beholders, rarely
        roster += ["beholder"]
    return roster


# Every plain scalar field of a live monster that round-trips verbatim. `key`
# rebuilds the derived template (t/speed/name); `intent` is handled specially.
_MONSTER_STATE = (
    "x", "y", "hp", "max_hp", "energy", "awake", "stunned", "burning",
    "poisoned", "fled", "disguised", "warden_last", "feed", "recharge",
    "ray_armed", "weak", "feared", "confused", "hammer_hits", "enraged",
)


class Monster:
    def __init__(self, key, x, y):
        t = TEMPLATES[key]
        self.key = key
        self.t = t
        self.x, self.y = x, y
        self.hp = t.hp
        self.max_hp = t.hp
        self.energy = 0
        self.speed = t.speed
        self.awake = False
        self.intent = None        # ("smash", x, y) | ("spit", dx, dy) -- telegraphed
        self.stunned = 0
        self.burning = 0
        self.poisoned = 0         # a venom DoT (Basilisk Maul), ticks like burning
        self.fled = False
        self.disguised = (key == "mimic")
        self.warden_last = None
        self.feed = 0.25          # wraiths brighten as they feed
        # an orc is always ACTIVE -- it takes a turn every tick, to watch for you with
        # its good eyes and to keep its pack together -- but being active is not the
        # same as being HOSTILE. it turns hostile only when it actually SEES you (see
        # _ai_orc). so it starts awake, unlike everything else, which sleeps until seen.
        self.awake = (key == "orc")
        self.recharge = 0         # flicker/beholder: turns before it can act again
        self.ray_armed = False    # beholder: its freeze landed -> next turn is the ray
        self.weak = 0             # turns of sapped strength (a weakness-coated blade)
        self.feared = 0           # turns fleeing (a scroll of Fear)
        self.confused = 0         # turns stumbling at random (a confusion-coated blade)
        self.hammer_hits = 0      # stun-weapon blows landed on it -> the stagger cadence
        self.enraged = 0          # turns spent attacking whatever is nearest (Betrayer's Edge)

    @property
    def name(self):
        return self.t.name

    @property
    def alive(self):
        return self.hp > 0

    def dist(self, x, y):
        return max(abs(self.x - x), abs(self.y - y))   # chebyshev: 8-way grid

    # --- serialization --------------------------------------------------
    def to_dict(self):
        d = {k: getattr(self, k) for k in _MONSTER_STATE}
        d["key"] = self.key
        d["intent"] = list(self.intent) if self.intent is not None else None
        return d

    @classmethod
    def from_dict(cls, data):
        m = cls(data["key"], data["x"], data["y"])
        for k in _MONSTER_STATE:
            setattr(m, k, data[k])
        m.intent = tuple(data["intent"]) if data["intent"] is not None else None
        return m

    # --- the turn -------------------------------------------------------
    def take_turn(self, world):
        if self.burning > 0:
            self.burning -= 1
            world.hurt_monster(self, 2, source="burn")
            if not self.alive:
                return
        if self.poisoned > 0:
            self.poisoned -= 1
            world.hurt_monster(self, config.POISON_DMG, source="poison")
            if not self.alive:
                return
        if self.weak > 0:
            self.weak -= 1        # a weakness-coated blow wearing off
        if self.stunned > 0:
            # reeling: no action this tick. the stun is NOT decremented here -- it is
            # counted in PLAYER turns and ticked down once per turn in World.advance /
            # freeze_tick. counting it per monster-tick let a fast monster (or one facing
            # a hammer-slowed player) spend the stun on one of its two ticks and act on
            # the other; per player-turn, the stagger holds across the whole recovery.
            return

        p = world.player
        seen = world.monster_can_see_player(self)
        if seen:
            self.awake = True
        if not self.awake:
            return

        # the player has gone unseen (invisible): even a monster that was hunting
        # loses the thread. it cannot approach, cannot strike -- it just casts about.
        if world.player_hidden():
            self.intent = None
            if world.rng.random() < 0.6:
                self._wander(world)
            return

        # routed by a scroll of Fear: it wants only to be somewhere you are not.
        if self.feared > 0:
            self.feared -= 1
            self.intent = None
            self._step_away(world, p.x, p.y)
            return

        # a confusion-coated blow: its own steps stagger at random.
        if self.confused > 0:
            self.confused -= 1
            self.intent = None
            self._wander(world)
            return

        # Betrayer's Edge: it lashes at the nearest thing -- another monster, or you.
        if self.enraged > 0:
            self.enraged -= 1
            self.intent = None
            self._rampage(world)
            return

        fn = getattr(self, "_ai_" + self.key, None)
        if fn:
            fn(world, p)

    def _rampage(self, world):
        """Enraged: strike the nearest creature. Another monster if one is closer than
        the player (no kill credit -- source 'enrage'); otherwise lash at the player."""
        p = world.player
        pd = self.dist(p.x, p.y)
        best, bd = None, 10 ** 9
        for o in world.level.monsters:
            if o is self or not o.alive:
                continue
            d = self.dist(o.x, o.y)
            if d < bd:
                best, bd = o, d
        if best is not None and bd <= pd:
            if bd <= 1:
                dmg = int(round(world.rng.randint(self.t.lo, self.t.hi)))
                world.log("The %s turns on the %s!"
                          % (world._mname(self), world._mname(best)), (176, 120, 132))
                world.hurt_monster(best, dmg, source="enrage")
            else:
                self._step_toward(world, best.x, best.y)
            return
        if pd <= 1:
            self._hit(world, verb="lashes wildly at")
        else:
            self._step_toward(world, p.x, p.y)

    def _wander(self, world):
        """A single aimless step -- for a monster that has lost track of the player."""
        dirs = list(DIRS8)
        world.rng.shuffle(dirs)
        for dx, dy in dirs:
            nx, ny = self.x + dx, self.y + dy
            if (world.walkable(nx, ny) and not world.monster_at(nx, ny)
                    and not world.vendor_at(nx, ny)
                    and (nx, ny) != (world.player.x, world.player.y)):
                self.x, self.y = nx, ny
                world.on_monster_moved(self)
                return

    # --- shared helpers -------------------------------------------------
    def _step_toward(self, world, tx, ty, phase=False):
        best, bd = None, 10 ** 9
        for dx, dy in DIRS8:
            nx, ny = self.x + dx, self.y + dy
            if not world.in_bounds(nx, ny):
                continue
            if not phase and not world.walkable(nx, ny):
                continue
            if world.monster_at(nx, ny):
                continue
            if world.vendor_at(nx, ny):
                continue                      # it is solid. even to them.
            if (nx, ny) == (world.player.x, world.player.y):
                continue
            d = max(abs(nx - tx), abs(ny - ty))
            if d < bd:
                best, bd = (nx, ny), d
        if best:
            self.x, self.y = best
            world.on_monster_moved(self)

    def _step_away(self, world, tx, ty):
        best, bd = None, -1
        for dx, dy in DIRS8:
            nx, ny = self.x + dx, self.y + dy
            if not world.in_bounds(nx, ny) or not world.walkable(nx, ny):
                continue
            if world.monster_at(nx, ny) or (nx, ny) == (world.player.x, world.player.y):
                continue
            d = max(abs(nx - tx), abs(ny - ty))
            if d > bd:
                best, bd = (nx, ny), d
        if best:
            self.x, self.y = best
            world.on_monster_moved(self)

    def _adjacent_to_player(self, world):
        return self.dist(world.player.x, world.player.y) <= 1

    def _hit(self, world, mult=1.0, ignore_armour=False, verb="hits"):
        # Shademail: the stone parts for its wearer alone -- a mundane thing standing
        # next to a submerged tile simply cannot reach into it. Only the ethereal
        # (wraith, poltergeist) already walk through walls, so stone is no obstacle
        # to them either. This is the single call site for every monster's strike
        # (see monster_attacks_player's only caller), so gating here covers all of them.
        if world.player_submerged() and not is_incorporeal(self.key):
            return
        dmg = int(round(world.rng.randint(self.t.lo, self.t.hi) * mult))
        if self.weak > 0:
            dmg = max(1, dmg - 3)     # sapped by a weakness-coated blow -- but always >=1
        world.monster_attacks_player(self, dmg, ignore_armour=ignore_armour, verb=verb)

    # --- per-monster AI -------------------------------------------------
    def _ai_rat(self, world, p):
        # fast and stupid: close and bite. the threat is that there are six.
        if self._adjacent_to_player(world):
            self._hit(world, verb="bites")
        else:
            self._step_toward(world, p.x, p.y)

    # an angry rat is a plague rat that has not learned to travel in a pack
    _ai_angry_rat = _ai_rat

    def _ai_kobold(self, world, p):
        # it fights well, and when it is losing it goes to get its friends
        if self.hp <= self.max_hp * 0.3 and not self.fled:
            self.intent = ("flee", 0, 0)
            if self._adjacent_to_player(world) and world.rng.random() < 0.35:
                self._hit(world)                      # a parting shot
                return
            self._step_away(world, p.x, p.y)
            world.wake_monsters_near(self.x, self.y, 9)   # the scream
            if self.dist(p.x, p.y) >= 7:
                self.fled = True
                self.intent = None
            return
        self.intent = None
        if self._adjacent_to_player(world):
            self._hit(world)
        else:
            self._step_toward(world, p.x, p.y)

    def _ai_spitter(self, world, p):
        # geometry: it only fires down a straight line, and it telegraphs
        if self.intent and self.intent[0] == "spit":
            _, dx, dy = self.intent
            self.intent = None
            if world.line_clear(self.x, self.y, p.x, p.y, 4):
                # the gob of acid actually crosses the room. the wind-up is drawn, so
                # the shot must be too, or the damage arrives from nowhere.
                world.add_fx("bolt", p.x, p.y, color=(170, 230, 110), radius=0.5,
                             life=0.30, tiles=[(self.x, self.y)])
                self._hit(world, ignore_armour=True, verb="spits acid at")
            else:
                # it still fires -- into the wall. show that too: it teaches the
                # player that breaking the line WORKS.
                bx, by = self.x + dx, self.y + dy
                while world.walkable(bx + dx, by + dy):
                    bx += dx
                    by += dy
                world.add_fx("bolt", bx, by, color=(170, 230, 110), radius=0.5,
                             life=0.30, tiles=[(self.x, self.y)])
                world.log("The spitter's acid splashes against stone.", config.DIM)
            return

        aligned = (self.x == p.x or self.y == p.y)
        d = self.dist(p.x, p.y)
        if aligned and d <= 4 and world.line_clear(self.x, self.y, p.x, p.y, 4):
            dx = (p.x > self.x) - (p.x < self.x)
            dy = (p.y > self.y) - (p.y < self.y)
            self.intent = ("spit", dx, dy)            # wind up: one free turn for you
            return
        if d <= 2:
            self._step_away(world, p.x, p.y)          # it does not want to be touched
        else:
            self._step_toward(world, p.x, p.y)

    def _ai_brute(self, world, p):
        # tempo: it plants, it winds up, it swings at a tile -- not at you
        if self.intent and self.intent[0] == "smash":
            _, tx, ty = self.intent
            self.intent = None
            # the fist lands on the TILE, whether or not you are still standing on it.
            # showing the miss is worth as much as showing the hit: it is proof that
            # stepping off the wind-up works.
            world.add_fx("slam", tx, ty, color=(226, 140, 96), life=0.5)
            if (p.x, p.y) == (tx, ty):
                self._hit(world, verb="SMASHES")
            else:
                world.log("The brute's fist buries itself in the floor.", config.DIM)
                world.shake(6)
            return
        if self._adjacent_to_player(world):
            self.intent = ("smash", p.x, p.y)         # aimed at where you ARE, now
        else:
            self._step_toward(world, p.x, p.y)

    def _ai_golem(self, world, p):
        # mechanically a brute -- the same plant-and-smash. its difference is not in
        # how it MOVES, it is in how it DIES: steel barely marks it, fire ends it.
        if self.intent and self.intent[0] == "smash":
            _, tx, ty = self.intent
            self.intent = None
            world.add_fx("slam", tx, ty, color=(150, 150, 160), life=0.55)
            if (p.x, p.y) == (tx, ty):
                self._hit(world, verb="POUNDS")
            else:
                world.log("The golem's fist cracks the flagstones.", config.DIM)
                world.shake(7)
            return
        if self._adjacent_to_player(world):
            self.intent = ("smash", p.x, p.y)
        else:
            self._step_toward(world, p.x, p.y)

    def _ai_orc(self, world, p):
        # a pack with no side and no subtlety, and two modes only:
        #
        #   HUNTING -- the moment ANY orc lays eyes on you (a straight, unobstructed
        #     line), the whole pack is on you at once. Only now does it have no side:
        #     it goes for the NEAREST living thing, you or a monster, and never its own
        #     kind -- which is what lets a summoned mob pull the pack off you.
        #   CALM -- the instant the last pair of eyes loses you (a corner, a pillar,
        #     the stairs, going unseen), every orc forgets you and pulls back toward
        #     the middle of the pack. A calm pack attacks nothing on the floor.
        if world.orcs_hunting():
            prey = world.orc_prey(self)
            if prey is None:
                return
            kind, target = prey
            if self.dist(target.x, target.y) <= 1:
                if kind == "player":
                    self._hit(world, verb="mauls")
                else:
                    dmg = world.rng.randint(self.t.lo, self.t.hi)
                    world.hurt_monster(target, dmg, source="orc")
            else:
                self._step_toward(world, target.x, target.y)
        else:
            c = world.orc_pack_centroid()
            if c and self.dist(c[0], c[1]) > 1:
                self._step_toward(world, c[0], c[1])   # regroup and wait

    def _ai_flicker(self, world, p):
        # the dance: blink to a random empty tile beside you (ignoring your body and
        # the walls) and strike -> stuck one turn, defenceless: your only window ->
        # blink away out of reach -> repeat. it never stands and fights.
        if self.recharge > 0:
            # the window. it is right next to you and it cannot move. hit it.
            self.recharge -= 1
            return

        if self._adjacent_to_player(world):
            # spent its recharge while adjacent -> flee: blink back out to range
            spot = world.blink_tile_near(p.x, p.y, lo=3, hi=6)
            if spot:
                world.add_fx("vanish", self.x, self.y, color=(150, 210, 236), life=0.35)
                self.x, self.y = spot
                world.add_fx("arrive", self.x, self.y, color=(150, 210, 236), life=0.35)
            return

        # at range: close the gap, and once near enough, blink in and strike
        if self.dist(p.x, p.y) <= 6:
            spot = world.blink_tile_near(p.x, p.y, lo=1, hi=1)   # a tile ADJACENT to you
            if spot:
                world.add_fx("vanish", self.x, self.y, color=(150, 210, 236), life=0.3)
                self.x, self.y = spot
                world.add_fx("arrive", self.x, self.y, color=(180, 230, 255), life=0.4)
                self._hit(world, verb="flickers in and cuts")
                self.recharge = 1                # now stuck for one turn -- the window
                return
        self._step_toward(world, p.x, p.y)

    def _ai_beholder(self, world, p):
        # a two-beat fighter. its combo, always in this order:
        #   1. open its eye  (a one-turn telegraph you can still dodge)
        #   2. the gaze lands -> you are FROZEN (no damage; the freeze IS the setup)
        #   3. its very next turn, a baleful RAY for real damage (the payoff) -- which
        #      is NOT fire, so it does not thaw the ice it just put you in
        #   4. recharge, so the whole combo is on a cooldown
        # break its line of sight at step 1 and none of it happens.
        RANGE = 7

        # STEP 3: the freeze landed last turn; this turn is the ray follow-up.
        if self.ray_armed:
            self.ray_armed = False
            self.recharge = 3                           # the whole combo goes on cooldown
            if world.los_clear(self.x, self.y, p.x, p.y, RANGE):
                world.add_fx("ray", p.x, p.y, color=(232, 62, 62), life=0.45,
                             tiles=[(self.x, self.y)])
                self._hit(world, verb="blasts")         # the baleful ray -- real damage
            else:
                world.log("The beholder's ray splashes against stone.", config.DIM)
            return

        # STEP 2: resolve the telegraphed gaze -> freeze, and ARM the ray for next turn.
        if self.intent and self.intent[0] == "gaze":
            self.intent = None
            if world.los_clear(self.x, self.y, p.x, p.y, RANGE):
                world.add_fx("beam", p.x, p.y, color=(150, 210, 255), life=0.4,
                             tiles=[(self.x, self.y)])
                world.freeze_player(2)
                self.ray_armed = True                   # the ray comes on its next turn
            else:
                world.log("The beholder's gaze finds only stone.", config.DIM)
                self.recharge = 3                       # a whiffed gaze -> straight to cooldown
            return

        if self.recharge > 0:
            self.recharge -= 1
            if not world.los_clear(self.x, self.y, p.x, p.y, RANGE):
                self._step_toward(world, p.x, p.y)      # sidle back into view
            return

        # STEP 1: ready -> if it can see you, open its eye (the telegraph). else reposition.
        if world.los_clear(self.x, self.y, p.x, p.y, RANGE):
            self.intent = ("gaze", p.x, p.y)
        else:
            self._step_toward(world, p.x, p.y)

    def _ai_poltergeist(self, world, p):
        # unseen, and it walks through everything. it drifts toward you straight
        # through your walls and rakes you for almost nothing -- the horror is not the
        # damage, it is that you cannot see it, cannot wall it out, and cannot swing at
        # what you cannot find. once you have read its TELL, the strike drags it into
        # view for a single heartbeat; who knows whether it is there the turn after.
        if self._adjacent_to_player(world):
            self._hit(world, verb="rakes")
            if world.codex.knows_tier("poltergeist", "tell"):
                world.add_fx("haunt", self.x, self.y, color=(214, 222, 238), life=0.5)
        else:
            self._step_toward(world, p.x, p.y, phase=True)

    def _ai_wraith(self, world, p):
        # it does not care about your walls or your plate
        self.feed = max(0.2, self.feed - 0.02)
        if self._adjacent_to_player(world):
            if world.player.armour.trait == "wraithsilk":
                world.log("Your wraithsilk drinks the touch. Nothing happens.", config.HEAL)
                world.add_fx("impact", p.x, p.y, color=(196, 180, 226), radius=0.7,
                             life=0.4)
                return
            self.feed = min(1.0, self.feed + 0.35)
            # a tether: your life, visibly leaving you and going into it. armour does
            # nothing here, and the player has to be able to SEE that it did nothing.
            world.add_fx("drain", self.x, self.y, color=(198, 156, 250), life=0.55,
                         tiles=[(p.x, p.y)])
            self._hit(world, ignore_armour=True, verb="drains")
        else:
            self._step_toward(world, p.x, p.y, phase=True)

    def _ai_mimic(self, world, p):
        # it waits. it has always been waiting.
        if self.disguised:
            return
        if self._adjacent_to_player(world):
            self._hit(world, verb="crushes")
        else:
            self._step_toward(world, p.x, p.y)

    def _ai_warden(self, world, p):
        # the exam: brute's wind-up, spitter's line, wraith's contempt for armour,
        # and it never repeats itself
        if self.intent:
            kind = self.intent[0]
            if kind == "smash":
                _, tx, ty = self.intent
                self.intent = None
                world.add_fx("slam", tx, ty, color=(250, 120, 130), life=0.6)
                if (p.x, p.y) == (tx, ty):
                    self._hit(world, mult=1.4, verb="BRINGS DOWN ITS FIST ON")
                else:
                    world.log("The Warden's fist cracks the flagstones.", config.DIM)
                    world.shake(10)
                return
            if kind == "spit":
                self.intent = None
                if world.line_clear(self.x, self.y, p.x, p.y, 9):
                    world.add_fx("beam", p.x, p.y, color=(255, 120, 140), life=0.35,
                                 tiles=[(self.x, self.y)])
                    self._hit(world, ignore_armour=True, verb="lances")
                else:
                    world.log("The Warden's bolt shatters on a pillar.", config.DIM)
                return

        d = self.dist(p.x, p.y)
        aligned = (self.x == p.x or self.y == p.y)
        can_line = aligned and d <= 9 and world.line_clear(self.x, self.y, p.x, p.y, 9)

        if d <= 1 and self.warden_last != "smash":
            self.intent = ("smash", p.x, p.y)
            self.warden_last = "smash"
        elif can_line and self.warden_last != "spit":
            self.intent = ("spit", 0, 0)
            self.warden_last = "spit"
        elif d <= 1:
            self._hit(world)
            self.warden_last = None
        else:
            self._step_toward(world, p.x, p.y)
            self.warden_last = None


def spawn_count(depth, rng):
    # floor 1 is deliberately thin. it is the tutorial the dungeon does not admit
    # to having.
    if depth == 1:
        return 4 + rng.randint(0, 2)
    # the count keeps climbing, but it EASES OFF deep down -- a floor 20 that spawned
    # 25 monsters would be a meat grinder the map can barely hold, not a fight. it
    # rises fast through the early floors, then flattens toward a busy-but-survivable
    # ceiling.
    base = 5 + depth if depth <= 10 else 15 + (depth - 10) // 2
    return base + rng.randint(0, 3)
