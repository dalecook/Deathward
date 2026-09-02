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
    # floor 8's mini-boss: a reed-nymph who hides inside the arena's pillars and
    # only ever fights at range -- a gust that is mostly knockback, with a little
    # real chip damage. Brittle (roughly six solid hits from a strong weapon --
    # 30 / ((4+7)/2 Vampiric Kris average) = 5.45, rounds up to 6) and
    # fire-vulnerable; catching her mid-blow is the whole fight (see _ai_syrinx).
    "syrinx":  Template("syrinx", "Syrinx", "y", (196, 214, 150), 30, 1, 3, 100),
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
    if monster_key == "syrinx" and source in FIRE_SOURCES:
        return config.SYRINX_FIRE_MULT     # wind and stone; fire cracks her wide open
    return 1.0


INCORPOREAL = {"wraith", "poltergeist"}     # walk through walls, ignore armour


def is_incorporeal(key):
    return key in INCORPOREAL


def _syrinx_path_blocked(x0, y0, x1, y1, px, py):
    """Does the player's body sit on, or diagonally beside, the straight walk from
    (x0,y0) to (x1,y1)? A cheap per-turn re-route trigger, not real pathfinding --
    the design spec leaves the exact heuristic as an implementation choice; this one
    reacts to being blocked, which is the actual requirement."""
    x, y = x0, y0
    while (x, y) != (x1, y1):
        if max(abs(x - px), abs(y - py)) <= 1:
            return True
        x += (x1 > x) - (x1 < x)
        y += (y1 > y) - (y1 < y)
    return max(abs(x1 - px), abs(y1 - py)) <= 1

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
    "hidden", "hidden_turns", "pillar_x", "pillar_y", "retreating",
    "just_forced_close",
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
        # Syrinx is the same: her hidden-turn budget must tick down from the moment
        # she is placed, whether or not the player has ever laid eyes on her.
        self.awake = key in ("orc", "syrinx")
        self.recharge = 0         # flicker/beholder: turns before it can act again
        self.ray_armed = False    # beholder: its freeze landed -> next turn is the ray
        self.weak = 0             # turns of sapped strength (a weakness-coated blade)
        self.feared = 0           # turns fleeing (a scroll of Fear)
        self.confused = 0         # turns stumbling at random (a confusion-coated blade)
        self.hammer_hits = 0      # stun-weapon blows landed on it -> the stagger cadence
        self.enraged = 0          # turns spent attacking whatever is nearest (Betrayer's Edge)
        # Syrinx only: she starts hidden in the pillar she is built at. hidden_turns
        # counts turns spent hidden this cycle, toward the forced-emergence cap.
        # pillar_x/pillar_y remember which pillar that is, so a retreat never re-picks
        # the one she just left. retreating is true from the moment her post-blow stun
        # ends until she reaches a pillar and re-hides. See _ai_syrinx.
        self.hidden = (key == "syrinx")
        self.hidden_turns = 0
        self.pillar_x, self.pillar_y = (x, y) if key == "syrinx" else (-1, -1)
        self.retreating = False
        # Syrinx only: set for exactly the one turn after her sidestep's own
        # fallback-of-last-resort close (Rule 3b) lands her somewhere rule 1
        # would otherwise immediately recoil her off of, undoing the close
        # before it can accomplish anything. See _ai_syrinx's rule 1 comment
        # for the full reasoning and the stall it fixes.
        self.just_forced_close = False

    @property
    def name(self):
        return self.t.name

    @property
    def alive(self):
        return self.hp > 0

    def dist(self, x, y):
        return max(abs(self.x - x), abs(self.y - y))   # chebyshev: 8-way grid

    def speed_now(self, world):
        """Energy gained per tick (see World.advance / freeze_tick). Almost always
        just self.speed -- a fixed number baked in from the Template at spawn.

        Syrinx is the one exception. Her own design spec (_ai_syrinx's docstring)
        says she "moves at the player's own speed", but self.speed alone cannot
        express that: it is fixed at 100 (== config.BASE_SPEED) forever, while the
        player's actual speed swings turn to turn with boots, armour, weapon, and
        the haste/berserk/heroism buffs. Hard-coding her at 100 quietly broke the
        stated design the moment a player wore anything but bare feet -- measured:
        Swift boots (125 speed) act 1.25x per her tick, Blink (115) 1.15x, which
        plays as "she is delayed" even though nothing about her is actually slow.
        She matches the player's CURRENT speed instead, buffs included -- you
        cannot outrun the wind by drinking a potion. That is deliberate.
        """
        if self.key == "syrinx":
            return world.player.speed()
        return self.speed

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
        # ethereal monsters are exempt: invisibility puts you in THEIR realm, so a
        # wraith or poltergeist sees you plainly and keeps hunting.
        # Syrinx is exempt outright, by key, not by a self.hidden check -- she runs
        # her own complete state machine in _ai_syrinx (arrive/hidden/telegraph/
        # emerge/hunt/blow/stun/retreat) and this generic wander has nothing to
        # offer her in ANY of those states. It used to be gated on "and not
        # self.hidden" instead, which covered her while hidden but reopened the
        # instant a later change (her un-hidden ARRIVE beat) put her on the grid
        # un-hidden -- an invisible player standing near the mouth would eat her
        # held arrival turn and send her wandering the floor forever, arrive-intent
        # dropped, retreating never set. Second time this exact branch has caught
        # her out; exclude her for good instead of chasing the next state -- any
        # future addition to her state machine would only be a third state shape
        # for a by-state guard to miss, so the exclusion is pinned to the one thing
        # about her that never changes: her key.
        #
        # The side effect is deliberate, not incidental: invisibility does NOTHING
        # against her, full stop, whether she is emerged and hunting or mid-telegraph.
        # She is already immune to poison, freeze and fear (see TestSyrinxResistances
        # in tests.py) on the same fiction -- wind and stone do not hunt by sight, so
        # a cloak that blinds a mundane hunter's eyes gives her nothing to lose. This
        # was a ratified design call (2026-08-31), pinned by
        # TestSyrinxResistances.test_invisibility_does_nothing_against_her (and its
        # brute contrast case, proving the immunity is hers specifically and not a
        # broken invisibility system) -- both drive her through take_turn, not
        # _ai_syrinx directly, for the same reason this comment exists: calling the
        # AI method directly skips this exact guard.
        if (world.player_hidden() and not is_incorporeal(self.key)
                and not self.hidden and self.key != "syrinx"):
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

    def _syrinx_retreat_target(self, world, p):
        """The pillar to head for once the stun ends: nearest first, never the one
        she just emerged from, skipped in favour of the next-nearest whenever the
        player's body sits on the straight walk to it."""
        pillars = world.level.syrinx_pillars()
        candidates = [sp for sp in pillars
                     if sp != (self.pillar_x, self.pillar_y)] or pillars
        ranked = sorted(candidates, key=lambda sp: self.dist(*sp))
        for sp in ranked:
            if not _syrinx_path_blocked(self.x, self.y, sp[0], sp[1], p.x, p.y):
                return sp
        return ranked[0] if ranked else None

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

    def _ai_syrinx(self, world, p):
        """Hide/telegraph/emerge/hunt/blow/stun/retreat -- her whole loop, from the
        design spec:
          0. ARRIVE: one held turn on materialising, then straight to RETREAT.
          1. HIDDEN: off the grid, ticking toward a forced emergence.
          2. TELEGRAPH: one turn's warning on the pillar she is already standing in.
          3. EMERGE: targetable, moves at the player's own speed, never melees.
          4. HUNT: not a chase -- the gate down does not open until she is dead, so
             the player has to come to her, and she does not need to close the
             distance herself. Five rules, checked in this order every turn she is
             emerged and not retreating:
               a. player adjacent and diagonal (not aligned) -- she cannot gust from
                  there, so she steps away rather than stand and take it. Suppressed
                  for exactly the one turn right after rule d's own fallback close
                  (below) forces her onto such a tile -- otherwise the close and the
                  recoil undo each other forever. See rule a's own inline comment.
               b. player aligned, within SYRINX_BLOW_RANGE, clear line -- telegraphs.
               c. player aligned, clear line, within SYRINX_STANDOFF (so beyond
                  SYRINX_BLOW_RANGE, or rule b would already have fired) -- she
                  already has the shot lined up, so closing IS taking it: she walks
                  the lane toward the player, one tile. There is no "hold" state
                  left in her -- a lineup she is not yet close enough to fire is
                  something to close, not something to wait on.
               d. player aligned but the line is blocked (a pillar fizzles it), OR
                  not aligned at all, and within SYRINX_STANDOFF -- she manoeuvres
                  instead of closing: tries, in order, the smaller-offset axis
                  toward the player, then the other axis toward the player,
                  taking the first that (i) is free, (ii) does not reduce her
                  distance to the player, and (iii) does not leave her aligned on
                  a still-blocked lane. If neither candidate survives all three,
                  she closes rather than freezing -- a close always reduces
                  distance, so it cannot repeat forever the way a hold could, and
                  in practice it is what finally opens a lane a pillar was
                  shielding. That close also arms the one-turn rule-a suppression
                  above (`just_forced_close`): the tile a plain nearest-neighbour
                  close lands on is sometimes diagonally adjacent to the player,
                  and letting rule a recoil off it immediately would undo the
                  close before it accomplished anything, reopening the exact
                  stall this fallback exists to prevent. (An away-from-player
                  fallback on each axis was
                  tried and rejected: with "away" available, the smaller axis's
                  toward-tile and away-tile become a stable two-tile orbit around
                  a permanently blocked lane, so the two candidates that could
                  actually break it never get exhausted. See the sidestep's own
                  comment for the reproduction.) This is the real leash: not a
                  chase radius, a refusal to close a lane she cannot use.
               e. player beyond SYRINX_STANDOFF -- steps toward, one tile, just
                  enough to drag them back into the band she actually fights in.
          5. BLOW: a telegraph-then-resolve pair (self.intent), same shape as the
             Warden's spit; a pillar in the eyeline fizzles it.
          6. STUNNED: fully vulnerable for one turn (config.SYRINX_STUN_TURNS) --
             handled generically by Monster.take_turn's self.stunned early-return.
          7. RETREAT: heads for the nearest pillar that is not the one she just left,
             re-routing per turn if the player's body blocks the straight walk to it.
          8. RE-HIDE: reaching it, she goes off-grid again and the budget resets.
        """
        if self.intent and self.intent[0] == "arrive":
            # the held beat: she has just come out of nothing at the far end of the
            # hall. One turn standing, then she turns for a column. If the player is
            # somehow close enough to witness it, they have been taught her whole
            # mechanic for the price of one turn.
            self.intent = None
            self.retreating = True
            return

        if self.hidden:
            if self.intent and self.intent[0] == "emerge":
                self.intent = None
                self.hidden = False
                self.hidden_turns = 0
                world.add_fx("arrive", self.x, self.y, color=self.t.color, life=0.5)
                return
            self.hidden_turns += 1
            if self.hidden_turns >= config.SYRINX_HIDDEN_MAX:
                self.intent = ("emerge", self.x, self.y)
                world.add_fx("pulse", self.x, self.y, color=self.t.color, life=0.9)
            return

        if self.intent and self.intent[0] == "blow":
            self.intent = None
            if world.line_clear(self.x, self.y, p.x, p.y, config.SYRINX_BLOW_RANGE):
                world.add_fx("beam", p.x, p.y, color=self.t.color, life=0.4,
                             tiles=[(self.x, self.y)])
                self._hit(world, verb="buffets")
                world._syrinx_knockback(self)
                self.stunned = max(self.stunned, config.SYRINX_STUN_TURNS)
                self.retreating = True
            else:
                world.log("Syrinx's gust dies against the stone.", config.DIM)
            return

        if self.retreating:
            target = self._syrinx_retreat_target(world, p)
            if target is None:
                return                       # boxed in this turn; try again next turn
            if (self.x, self.y) == target:
                self.hidden = True
                self.retreating = False
                self.pillar_x, self.pillar_y = target
                self.hidden_turns = 0
                world.add_fx("vanish", self.x, self.y, color=self.t.color, life=0.5)
                return
            # the pillar itself is a WALL tile -- same reason wraith/poltergeist
            # phase to reach the player, she has to phase to reach IT, or her
            # last step never lands and she oscillates one tile short forever.
            # but she is corporeal, not incorporeal like them: only HER OWN
            # pillar parts like stone for her (the Shademail flavour this is
            # modeled on), so phase ONLY the final step onto it -- every
            # approach step before that stays on real floor, same as her hunt
            # movement, or phase=True (which loosens EVERY neighbor this turn,
            # not just the destination) lets her cut through ordinary walls
            # en route whenever that is locally shortest.
            if self.dist(*target) <= 1:
                self.x, self.y = target
                world.on_monster_moved(self)
            else:
                self._step_toward(world, *target)
            return

        aligned = (self.x == p.x or self.y == p.y)
        d = self.dist(p.x, p.y)

        # Rule 1: diagonal adjacency is the blind spot. Aligned means same row or
        # column, and a diagonal neighbour is neither -- she cannot gust them from
        # there, and standing still while adjacent-but-unable-to-hit would make her
        # free damage. She recoils instead. This is the one case where she moves
        # AWAY regardless of range band; everything below only ever moves her
        # sideways or closer.
        #
        # One deliberate, one-turn exception: `just_forced_close`. Rule 3b's own
        # fallback-of-last-resort close (below, "nothing survived: close instead
        # of holding") picks whichever legal neighbour is nearest the player and
        # nothing else -- it has no opinion on which tile AT that minimum
        # distance she lands on, because everything that needs an opinion (the
        # blocked-lane test, the never-reduce invariant) already ran, and failed,
        # for both sidestep candidates. On a pillar-adjacent tile the single
        # closest legal neighbour sometimes turns out to be diagonally adjacent
        # to the player -- distance 1, unaligned -- which is precisely rule 1's
        # own trigger. Recoiling off it on the very next turn hands her straight
        # back to (or past) the tile she just forced her way off of, and the
        # close and the recoil become each other's fallback: a second, smaller
        # stall sitting directly on top of the one the sidestep fix above
        # already closed. Confirmed on the report's own worked example --
        # (15,11) player, Syrinx from (13,9) -- which orbits
        # (13,9) -> (14,9) -> (14,10) -> (13,9) forever without this exception,
        # and a full-arena sweep in which every surviving stall was this exact
        # 3-cycle shape, always pinned to a pillar's own column.
        #
        # A memoryless fix was tried first and rejected: making the fallback
        # close itself refuse a diagonal-adjacent landing (preferring the
        # nearest legal tile that ISN'T one) sounds like the same idea without
        # new state, but it silently changes what the close's own contract
        # depends on. The close's fallback-close guarantee ("a close always
        # reduces distance, so unlike a hold it cannot repeat forever") assumes
        # it takes the true nearest legal tile; filtering that choice can leave
        # only a same-distance tile behind, which is no longer a close at all --
        # on this exact worked example the diagonal-adjacent tile is the UNIQUE
        # distance-reducing neighbour, so avoiding it only trades the 3-cycle
        # for a fresh 2-cycle between two tiles that never reduce distance
        # either (verified by simulation, not assumed). The one-turn suppression
        # below is what actually lets the close finish what it started: she is
        # trusted to have had a real reason for landing where she is (a lane a
        # sidestep could not use), and rules 2-4 get one clear turn to act on
        # that landing before rule 1 is allowed an opinion again.
        #
        # Costs a field (`just_forced_close`, in `_MONSTER_STATE`, round-tripped
        # through to_dict/from_dict like every other scalar here) rather than
        # zero new state -- the one tradeoff this fix makes deliberately, because
        # the zero-state alternative does not actually work. Read-and-cleared
        # unconditionally, right here, every turn, so it can never suppress more
        # than the single turn immediately following the close that set it --
        # it is a missed heartbeat, not a mode.
        suppress_recoil, self.just_forced_close = self.just_forced_close, False
        if d == 1 and not aligned and not suppress_recoil:
            self._step_away(world, p.x, p.y)
            return

        # Rule 2: aligned, close enough, and nothing in the eyeline -- the blow
        # telegraphs. SYRINX_BLOW_RANGE is short and deliberate: the shove is what
        # actually hurts (SYRINX_PUSH_DIST tiles across a trapped floor), so the
        # gust itself only needs to reach point-blank-ish, not across the hall.
        if (aligned and d <= config.SYRINX_BLOW_RANGE
                and world.line_clear(self.x, self.y, p.x, p.y, config.SYRINX_BLOW_RANGE)):
            self.intent = ("blow", 0, 0)
            return

        # Rule 3: inside the standoff band. She never just holds here -- "hold when
        # already aligned" was the exploit (see the design brief): a player parked
        # aligned at distance 4-6 was ignored forever, and World._firestorm hits
        # every visible monster including her, at SYRINX_FIRE_MULT, on the Robe of
        # Hades' own recharge timer -- a park-and-farm free kill. Two branches now:
        #
        #   - aligned AND the line is clear: she already has the shot lined up,
        #     just out of blow range (rule b above would have fired already if she
        #     were close enough). Waiting on a lineup she already has is not
        #     patience, it is a free turn -- so she walks the lane toward the
        #     player, one tile. Stepping out of the lane is the player's answer;
        #     that breaks alignment and drops her straight back to the sidestep
        #     branch below, so this is real cat-and-mouse, not a one-way close.
        #
        #   - everything else within the band (not aligned at all, OR aligned but
        #     a pillar fizzles the line): nothing to shoot, so she manoeuvres
        #     instead. See the sidestep block below for how -- it used to be a
        #     single hand-picked tile, which is exactly what went wrong.
        #
        # Neither branch calls _step_toward with the real or a crafted one-axis
        # target -- that helper's chebyshev search ties a DIAGONAL DIRS8
        # neighbour against the straight in-lane/in-axis one exactly when an axis
        # offset is already 0 (this fight's whole standoff geometry, in both
        # branches), and DIRS8's iteration order resolves that tie toward the
        # diagonal FIRST. Left to the helper, "close down the lane" would drift
        # diagonally off it, and "sidestep" would silently close the gap it
        # exists to hold open -- the bug that bit the first pass at this fight.
        # Manual tiles, walked through the same walkable/monster/vendor/player
        # guard every other manual step in this method already uses (see RETREAT
        # above), sidestep the ambiguity instead of fighting the helper's
        # tie-break.
        if d <= config.SYRINX_STANDOFF:
            if aligned and world.line_clear(self.x, self.y, p.x, p.y, d):
                # Closing the lane: unchanged, and not what broke. One
                # candidate, walked if it is free, held if it is not -- a
                # blocked closing step just means try again next turn; the
                # pillar cannot move, and whatever transiently blocked this
                # tile (a monster wandering through, the player's own body)
                # usually will.
                if self.y == p.y:
                    nx, ny = self.x + (1 if p.x > self.x else -1), self.y
                else:
                    nx, ny = self.x, self.y + (1 if p.y > self.y else -1)
                if (world.walkable(nx, ny) and not world.monster_at(nx, ny)
                        and not world.vendor_at(nx, ny) and (nx, ny) != (p.x, p.y)):
                    self.x, self.y = nx, ny
                    world.on_monster_moved(self)
                # else: the candidate tile is blocked this turn -- she holds and
                # tries again next turn, same as a boxed-in retreat does above.
                return

            # --- the sidestep: manoeuvre without closing ------------------
            #
            # This used to be ONE hand-picked candidate tile -- step along
            # whichever axis has the smaller offset, toward the player -- with
            # no fallback and no memory of what she just tried. That produced
            # two permanent dead states, both leaving her emerged, visible and
            # unhidden: a free kill via World._firestorm (the VORN scroll, and
            # the Robe of Hades' automatic recharge -- SYRINX_FIRE_MULT hits her
            # for double).
            #
            #   (a) TWO-CYCLE ON A BLOCKED LANE. Aligned-but-blocked falls in
            #       here -- the "aligned and line_clear" test just above failed.
            #       The aligned axis sits at offset 0, which is always the
            #       "smaller" one, so the single candidate peeled her one tile
            #       off the lane... and the very next turn, the OTHER axis was
            #       now the smaller offset (it hadn't moved), so the single
            #       candidate walked her straight back onto the lane she'd just
            #       left. Two tiles, forever, intent never set.
            #   (b) FROZEN ON A BLOCKED CANDIDATE. When the one candidate landed
            #       on a pillar (or a monster, or the player), the old
            #       "else: hold" fallback repeated identically every turn --
            #       her position never changed, so the candidate it computed
            #       never changed either. A single unlucky pick was a permanent
            #       stall, not a one-turn stumble.
            #
            # The fix is not a cleverer single tile, it is giving the sidestep
            # somewhere else to go when its first idea does not pan out:
            #
            #   1. Never step into a lane she cannot shoot down. A candidate
            #      that would leave her aligned with the player AND still
            #      blocked is rejected outright -- that is precisely what let
            #      (a) cycle: she kept treating a shielded lane as somewhere
            #      worth returning to.
            #   2. Two ordered candidates, not one: the smaller-offset axis
            #      toward the player (her old and still-preferred move), then
            #      the other axis toward the player. Both also have to pass
            #      the distance invariant below -- a sidestep may tie her
            #      chebyshev distance, never reduce it -- and stepping TOWARD
            #      the player on whichever axis is currently DOMINANT (already
            #      equal to the chebyshev distance) is exactly a reduction, so
            #      it is filtered out the same as a blocked tile would be. In
            #      practice the smaller-offset axis almost always wins
            #      outright; the other axis only ever wins when the two
            #      offsets are tied, since then neither axis is uniquely
            #      dominant and stepping either one still only ties.
            #
            #      An EARLIER version of this fix also tried the opposite
            #      (away-from-player) direction on each axis, as two further
            #      fallbacks, before giving up. A probe script caught why that
            #      is actively wrong, not just unnecessary: once "away" is a
            #      legal answer, the smaller axis's toward-tile and away-tile
            #      are each other's fallback. Reproduction (a) below settles
            #      into peeling one tile off the lane, discovering next turn
            #      that stepping back onto it is the blocked lane rule 1 just
            #      excluded, retreating one tile further out, discovering THAT
            #      tile's own toward-step is free again next turn, and
            #      returning -- a stable two-tile orbit between the two
            #      states adjacent to the blocked lane, forever, because nothing
            #      in a memoryless, position-only decision ever prefers
            #      continuing outward over trying inward again. The dominant
            #      axis (the one that would actually break the deadlock) can
            #      never be touched without reducing distance, which the
            #      invariant forbids -- so with "away" on the table, the
            #      exhaustion this rule needs to reach point 3 never happens.
            #      Dropping the away fallbacks removes that trap: now the only
            #      way off the smaller axis is real closing, via point 3.
            #   3. If both candidates are rejected, close instead of freezing.
            #      A close always reduces distance, so unlike a hold it cannot
            #      repeat forever -- it terminates at blow range or adjacency,
            #      where rules 1 and 2 take back over. That is exactly what (b)
            #      needed: a permanent hold IS the bug, so the fallback of last
            #      resort must never be "do nothing". It is also what actually
            #      resolves (a): a couple of turns spent closing down the
            #      blocked axis is what finally opens a lane she CAN use.
            adx, ady = abs(p.x - self.x), abs(p.y - self.y)
            x_toward = (1 if p.x > self.x else -1)
            y_toward = (1 if p.y > self.y else -1)
            # smaller/other, not "primary/secondary" -- match the naming the
            # rest of this docstring already uses for "whichever axis has the
            # SMALLER offset". Ties go to x, same as the single-candidate code
            # this replaces did.
            if adx <= ady:
                smaller, other = (x_toward, 0), (0, y_toward)
            else:
                smaller, other = (0, y_toward), (x_toward, 0)
            candidates = [smaller, other]

            for cdx, cdy in candidates:
                nx, ny = self.x + cdx, self.y + cdy
                if not (world.walkable(nx, ny) and not world.monster_at(nx, ny)
                        and not world.vendor_at(nx, ny) and (nx, ny) != (p.x, p.y)):
                    continue                      # occupied/solid this turn
                new_d = max(abs(nx - p.x), abs(ny - p.y))
                if new_d < d:
                    continue                      # that would be a close, not a sidestep
                new_aligned = (nx == p.x or ny == p.y)
                if new_aligned and not world.line_clear(nx, ny, p.x, p.y, new_d):
                    continue                      # would walk right back onto a dead lane
                self.x, self.y = nx, ny
                world.on_monster_moved(self)
                return

            # Nothing survived: every free tile would have either closed the
            # gap or dropped her back onto a blocked lane. Close for real
            # rather than freeze -- see point 3 above. Same call Rule 4 makes
            # below; it is always safe here because it always terminates --
            # PROVIDED rule 1 does not immediately undo it. See the
            # just_forced_close flag set below, and its own comment at the top
            # of this method, for why that provision needed enforcing.
            self._step_toward(world, p.x, p.y)
            self.just_forced_close = True
            return

        # Rule 4: out past the standoff band, she is not a statue -- she closes one
        # tile, just enough to drag the player back toward the range where she
        # actually fights. She still is not chasing to melee: closing only ever
        # feeds rules 1-3 above, never a strike of her own.
        self._step_toward(world, p.x, p.y)


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
