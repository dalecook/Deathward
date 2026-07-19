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

"""The simulation: turn economy, combat, and the consequences of curiosity.

TURN ECONOMY
    Everything spends the same currency. Each tick, every actor gains `speed`
    energy and acts once per 100 it can afford. A player in Windwalkers (speed 140)
    banks 40 surplus a turn, and every few turns that surplus buys an action the
    monsters do not get to answer. That is what boots ARE. Heavy armour sells the
    same currency back.

KNOWLEDGE IS INFORMATION, NEVER POWER
    Nothing in this file reads the Kodex to decide an outcome. Damage rolls, AI,
    trap triggers and spawn tables are identical for an omniscient player and a
    blind one. The Kodex is consulted only by render.py and ui.py, to decide how
    much of the truth you are allowed to look at.
"""

import random

from . import config
from .codex import CAUSE_NAME, fact_title
from .dungeon import Chest, Corpse, Drop, Level, Slain
from .items import ALL_GEAR, CONSUMABLES, roll_loot, roll_monster_loot
from .monsters import DIRS8, Monster, TEMPLATES, damage_multiplier, is_incorporeal

MONSTER_NAME = {k: t.name for k, t in TEMPLATES.items()}

# damage sources that are ANOTHER MONSTER, not you. a kill from one of these earns
# you no loot (its killer took it) and no Kodex credit -- you did not do it.
MONSTER_SOURCES = {"orc", "enrage"}

# damage sources that are a TRAP the thing blundered onto -- not a blow you struck.
# a monster that dies to a trap is not your kill either: you get no Kodex lesson and
# no kill credit for it (its loot is still lying on the body, though -- nothing took
# it). These match the trap keys in traps.py.
TRAP_SOURCES = {"dart", "spike", "gas", "alarm", "glyph"}

# potion effects that are NEGATIVE, and so -- once you have identified the flask --
# are never drunk again but wiped down the blade to land on an enemy instead (see
# _coat_blade / player_attack). the venom rule, generalised to every bad potion.
COATABLE_EFFECTS = {"poison", "weak", "confuse"}

# how far an orc can see you down a clear, unobstructed line. a touch past your own
# view (FOV_RADIUS 8), because orcs have good eyes -- they tend to spot you a step
# before you spot them.
ORC_SIGHT = 10

BOSS_KEYS = {"warden"}      # void-immune; the mini-boss task adds its keys here
from .player import Player
from .vendor import Vendor, price_of, sell_price_of


class World:
    def __init__(self, codex, seed=None):
        self.codex = codex
        self.seed = seed if seed is not None else random.randrange(1 << 30)
        self.rng = random.Random(self.seed)      # the LIVING: re-dealt every run
        # the STONE: cut once, the first time this game is played, and kept until a
        # new game. every floor's rooms and corridors are derived from it. it is
        # drawn independently of the run seed -- the shape of the dungeon is a
        # property of the GAME, not of whichever run happened to open it.
        if codex.world_seed is None:
            codex.world_seed = random.randrange(1 << 30)
        # deal the looks of the unidentified for this game, if they have not been dealt
        # yet -- kept across respawns (the codex persists), re-rolled only on a new game.
        # generated on its own rng inside the codex, so it cannot perturb the stone above.
        if not codex.appearance:
            codex.roll_appearances(codex.world_seed)
        self.player = Player()
        self.tick = 0
        self.dead = False
        self.won = False
        self.death_cause = None
        self.shake_t = 0
        self.depth = 1
        self.level = None
        # every floor visited this run, kept as we left it. a new run throws the whole
        # dictionary away, because the contents are re-dealt on a respawn.
        self.levels = {}
        self.vendor_pct = 0        # per-RUN. a death takes it back to nothing.
        self.run_kills = 0
        self.learned = None       # a fact discovered mid-run; the UI shows a banner
        self.trading = False      # the UI raises the trade screen when this is set
        self.aiming = None        # a targeting mode is open ("teleport" | "banish"); the
                                  # UI raises a cursor/picker, turn ends on confirm
        self.aiming_flavor = None  # the scroll that opened it, in case we must refund it
        # Purely cosmetic effects, decaying in REAL time even though the game is
        # turn-based. A fire glyph that takes 9 hp off you and shows you nothing is
        # just an unexplained wound -- you have to SEE the thing that burned you, or
        # you cannot learn from it, and learning from it is the entire game.
        self.fx = []
        # the gear you start the run in is gear you have "seen" -- it earns its entry
        for g in (self.player.weapon, self.player.armour, self.player.boots):
            self.codex.see_gear(g.key)
        self.new_level(1)
        self.log("You descend to floor 1.", config.STAIRS)

    # --- the vendor -----------------------------------------------------
    def _vendor_step(self, new_depth, going_down):
        """Move the odds, then decide whether the thing is on this floor.

        The counter is per-RUN. Above VENDOR_MIN_DEPTH it is simply zero -- there is
        no point selling to a hero with no gold. Descending raises it, climbing lowers
        it, and descending away from a vendor resets it, so the only way to raise your
        chances is to go somewhere you have not been.
        """
        left = self.level                       # the floor we are leaving, if any

        if new_depth < config.VENDOR_MIN_DEPTH:
            self.vendor_pct = 0
        elif going_down:
            if left is not None and left.vendor is not None:
                # you walked past it. it does not follow, and it does not wait.
                left.vendor = None
                self.vendor_pct = config.VENDOR_BASE_PCT
            elif self.vendor_pct <= 0:
                self.vendor_pct = config.VENDOR_BASE_PCT
            else:
                self.vendor_pct = min(100, self.vendor_pct + config.VENDOR_STEP_PCT)
        else:                                   # climbing
            self.vendor_pct = max(config.VENDOR_BASE_PCT,
                                  self.vendor_pct - config.VENDOR_STEP_PCT)

    def _maybe_spawn_vendor(self, level, fresh):
        """A floor rolls ONCE, on your first arrival this run.

        Re-rolling on every entry would let you bounce between two floors for
        unlimited attempts at the same odds -- the +/-5% would be guarding the wrong
        door.
        """
        if not fresh or self.depth < config.VENDOR_MIN_DEPTH:
            return
        if self.depth >= config.DEPTH_MAX:
            return          # not in the Warden's room. it trades; it does not gawp.
        if self.vendor_pct <= 0:
            return
        if self.rng.randint(1, 100) > self.vendor_pct:
            return
        spot = level.free_spot_for_vendor(self.rng, (self.player.x, self.player.y))
        if spot:
            level.vendor = Vendor(spot[0], spot[1], self.depth, self.rng)

    def vendor_at(self, x, y):
        v = self.level.vendor
        return v if (v and (v.x, v.y) == (x, y)) else None

    # --- level flow -----------------------------------------------------
    def new_level(self, depth, arrive="entrance"):
        """Go to a floor. `arrive` says which end of it you come in at: the entrance
        (walking down into it) or the stairs (climbing back up into it).

        Floors you have already visited THIS RUN are kept exactly as you left them.
        Without that, walking up and back down would re-deal the monsters and re-roll
        every chest -- an infinite loot mill, and a very good reason never to fight
        anything.
        """
        going_down = depth > self.depth
        self._vendor_step(depth, going_down)     # BEFORE we swap self.level

        self.depth = depth
        self.player.depth = depth
        fresh = depth not in self.levels
        if fresh:
            self.level = Level(depth, self.rng, self.codex)
            self.levels[depth] = self.level
        else:
            self.level = self.levels[depth]
        self._maybe_spawn_vendor(self.level, fresh)

        spot = self.level.entrance if arrive == "entrance" else self.level.stairs
        self.player.x, self.player.y = spot or self.level.entrance
        self.level.compute_fov(self.player.x, self.player.y)
        self.codex.best_depth = max(self.codex.best_depth, depth)
        if depth == config.DEPTH_MAX:
            self.log("Something enormous shifts in the dark below you.", config.BLOOD)

    def descend(self):
        if self.level.stairs is None:
            self.log("There is no way down. There is only the Warden.", config.BLOOD)
            return False
        if (self.player.x, self.player.y) != self.level.stairs:
            self.log("You are not standing on the stairs.", config.DIM)
            return False
        self.remember_map()
        self.new_level(self.depth + 1, arrive="entrance")
        self.log("You descend to floor %d." % self.depth, config.STAIRS)
        return True

    def warp_down(self):
        """CTRL+78. Drop straight onto the NEXT floor's entrance tile, from anywhere,
        without finding or standing on the stairs. A testing shortcut for the deep
        floors -- it obeys every other rule (the level is cached if you have been
        there, the vendor odds step, the Warden floor is still the bottom)."""
        if self.depth >= config.DEPTH_MAX:
            self.log("[CHEAT] This is the bottom. There is only the Warden.",
                     config.BLOOD)
            return False
        self.remember_map()
        self.new_level(self.depth + 1, arrive="entrance")
        self.log("[CHEAT] You blink down to floor %d." % self.depth, config.GOLD)
        self.add_fx("pulse", self.player.x, self.player.y, color=config.GOLD, life=0.6)
        return True

    def ascend(self):
        """Climb back up. Returns True if you went, False if you are not on the way
        up, or the string 'sealed' if you are trying to leave the dungeon.
        """
        if (self.player.x, self.player.y) != self.level.entrance:
            self.log("You are not standing on the way up.", config.DIM)
            return False
        if self.depth <= 1:
            return "sealed"          # the gate you came in by. it is not a door now.
        self.remember_map()
        self.new_level(self.depth - 1, arrive="stairs")
        self.log("You climb back up to floor %d." % self.depth, config.STAIRS)
        return True

    def remember_map(self):
        """Fold this floor's explored tiles into the game's permanent memory."""
        if self.level:
            self.codex.remember_map(self.depth, self.level.explored)

    # --- logging / fx ---------------------------------------------------
    @property
    def messages(self):
        """The whole-game log lives on the codex, so it survives a respawn (a new
        World) and is cleared only by a new game."""
        return self.codex.messages

    def log(self, text, color=config.INK):
        self.messages.append((text, color))
        if len(self.messages) > 3000:      # a whole game's worth, generously capped
            del self.messages[0]

    def shake(self, n):
        self.shake_t = max(self.shake_t, n)

    # --- cosmetic effects -------------------------------------------------
    def add_fx(self, kind, x=0, y=0, radius=1.0, color=(255, 150, 60), life=0.55,
               tiles=None):
        self.fx.append({"kind": kind, "x": x, "y": y, "r": radius, "col": color,
                        "life": life, "max": life, "tiles": tiles or []})

    def burning_tiles(self, cx, cy, radius):
        """The floor a blast actually covers -- exactly the tiles that take damage."""
        out = []
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                x, y = cx + dx, cy + dy
                if self.walkable(x, y):
                    out.append((x, y))
        return out

    def visible_floor(self):
        lvl = self.level
        return [(x, y) for y in range(lvl.h) for x in range(lvl.w)
                if lvl.visible[y][x] and lvl.walkable(x, y)]

    def tick_fx(self, dt):
        """Advance the animations. Real seconds, not turns -- called every frame."""
        if not self.fx:
            return
        for f in self.fx:
            f["life"] -= dt
        self.fx = [f for f in self.fx if f["life"] > 0]

    # --- geometry -------------------------------------------------------
    def in_bounds(self, x, y):
        return self.level.in_bounds(x, y)

    def walkable(self, x, y):
        return self.level.walkable(x, y)

    def monster_at(self, x, y):
        for m in self.level.monsters:
            if m.alive and m.x == x and m.y == y:
                return m
        return None

    @property
    def monsters(self):
        return self.level.monsters

    def visible(self, x, y):
        return self.level.visible[y][x]

    def player_hidden(self):
        """True while the player cannot be seen or tracked by ANYTHING -- the whole
        floor loses them. Right now that means invisible; the poltergeist's `hidden`
        hook and future stealth would fold in here."""
        return self.player.invisible > 0

    def monster_can_see_player(self, m):
        # symmetric FOV: if the player can see it, it can see the player. unless the
        # player is hidden -- then nothing acquires them.
        if self.player_hidden():
            return False
        if not self.in_bounds(m.x, m.y):
            return False
        return self.level.visible[m.y][m.x] and m.dist(self.player.x, self.player.y) <= 9

    def line_clear(self, x0, y0, x1, y1, maxdist):
        """Straight orthogonal line, unobstructed by walls, within range."""
        if x0 != x1 and y0 != y1:
            return False
        d = max(abs(x1 - x0), abs(y1 - y0))
        if d > maxdist or d == 0:
            return False
        sx = (x1 > x0) - (x1 < x0)
        sy = (y1 > y0) - (y1 < y0)
        x, y = x0 + sx, y0 + sy
        while (x, y) != (x1, y1):
            if not self.walkable(x, y):
                return False
            if self.monster_at(x, y):
                return False
            x += sx
            y += sy
        return True

    def los_clear(self, x0, y0, x1, y1, maxdist):
        """True line of sight: a straight line between the points that passes only over
        open floor. WALLS block it -- monsters and your own body do not. This is the
        beholder's gaze, and it is why a pillar or a corner breaks the freeze.
        """
        if max(abs(x1 - x0), abs(y1 - y0)) > maxdist:
            return False
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        x, y = x0, y0
        while True:
            if (x, y) not in ((x0, y0), (x1, y1)) and not self.walkable(x, y):
                return False                            # a wall stands in the eyeline
            if (x, y) == (x1, y1):
                return True
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x += sx
            if e2 <= dx:
                err += dx
                y += sy

    def freeze_player(self, turns):
        """The beholder's gaze lands. The freeze is capped -- it never stacks past the
        cap, so a beholder cannot hold you forever, and its own recharge means it
        cannot re-apply it before you have had turns to move."""
        p = self.player
        if p.sanctuary > 0:
            self.log("The gaze reaches you and slides off the stillness.", config.MANA)
            return
        p.frozen = min(2, max(p.frozen, turns))
        self.log("The beholder's gaze locks you in ice -- you cannot move!", config.MANA)
        self.add_fx("freeze", p.x, p.y, color=(150, 210, 255), life=0.9)
        self.shake(5)

    def blink_tile_near(self, cx, cy, lo, hi):
        """A random walkable, empty tile whose chebyshev distance from (cx,cy) is in
        [lo, hi]. Used by the Flicker: the blink teleports, so there is NO line-of-
        sight or path check -- it ignores walls and your body, the tile just has to be
        open floor. Returns None only if the player is genuinely boxed in.
        """
        candidates = []
        for dy in range(-hi, hi + 1):
            for dx in range(-hi, hi + 1):
                d = max(abs(dx), abs(dy))
                if d < lo or d > hi:
                    continue
                x, y = cx + dx, cy + dy
                if (x, y) == (self.player.x, self.player.y):
                    continue
                if self.walkable(x, y) and not self.monster_at(x, y):
                    candidates.append((x, y))
        return self.rng.choice(candidates) if candidates else None

    def orc_prey(self, orc):
        """The nearest living thing an orc will go for: you, or any monster that is not
        an orc. Returns ('player', player) or ('monster', m), or None. Ties fall to
        whatever is checked first -- but a pack still splits, because each orc stands
        somewhere different and so has a different nearest thing.
        """
        best, bd, bkind = self.player, orc.dist(self.player.x, self.player.y), "player"
        if self.dead:
            best, bd, bkind = None, 10 ** 9, None
        for m in self.level.monsters:
            if m is orc or m.key == "orc" or not m.alive or m.disguised:
                continue
            d = orc.dist(m.x, m.y)
            if d < bd:
                best, bd, bkind = m, d, "monster"
        return (bkind, best) if best is not None else None

    def orc_can_see_player(self, orc):
        """An orc sees you only down a straight, unobstructed line, out to ORC_SIGHT.
        A wall, a pillar or a corner breaks it -- and so, later, will going unseen.
        This is the ONE thing that turns a pack hostile; losing it calms them again.
        """
        if self.dead:
            return False
        if self.player_hidden():
            return False              # you cannot be seen if you are not there to see
        return self.los_clear(orc.x, orc.y, self.player.x, self.player.y, ORC_SIGHT)

    def orcs_hunting(self):
        """The pack is hostile iff at least one living orc can see you RIGHT NOW. One
        set of eyes alerts them all; the instant the last pair loses you, they all go
        calm. There is no memory here -- orcs are not clever, and that is the counter.
        """
        return any(self.orc_can_see_player(m)
                   for m in self.level.monsters if m.key == "orc" and m.alive)

    def orc_pack_centroid(self):
        """The middle of the living pack -- where a calm orc drifts to regroup."""
        orcs = [m for m in self.level.monsters if m.key == "orc" and m.alive]
        if not orcs:
            return None
        return (round(sum(m.x for m in orcs) / len(orcs)),
                round(sum(m.y for m in orcs) / len(orcs)))

    def wake_all(self):
        for m in self.level.monsters:
            m.awake = True

    def wake_monsters_near(self, x, y, radius):
        for m in self.level.monsters:
            if max(abs(m.x - x), abs(m.y - y)) <= radius:
                m.awake = True

    # --- combat ---------------------------------------------------------
    def _weapon_status_on(self, m, dmg):
        """Apply the equipped weapon's spreadable on-hit statuses to one struck
        monster. Burn/freeze/fear/lifesteal ride a cleave onto neighbours (Task 5),
        so this is called for the primary target and for each cleaved target.
        Returns HP healed by lifesteal (0 otherwise)."""
        p = self.player
        traits = p.weapon.traits
        if "burn" in traits and m.alive:
            m.burning = max(m.burning, 3)
            self.log("The %s catches fire." % self._mname(m), (255, 150, 80))
            self.add_fx("burning", m.x, m.y, life=0.8, tiles=[(m.x, m.y)])
        if "freeze" in traits and m.alive and self.rng.random() < config.FREEZE_CHANCE:
            m.stunned = max(m.stunned, config.FREEZE_TURNS)
            self.log("The %s freezes solid for a beat." % self._mname(m),
                     (150, 210, 255))
            self.add_fx("freeze", m.x, m.y, color=(150, 210, 255), life=0.5)
        if "fear" in traits and m.alive and self.rng.random() < config.FEAR_CHANCE:
            m.feared = max(m.feared, config.FEAR_TURNS)
            m.awake = True
            self.log("The %s recoils in terror." % self._mname(m), (120, 100, 190))
        if "poison" in traits and m.alive:
            m.poisoned = max(m.poisoned, config.POISON_TURNS)
            self.log("The %s is envenomed." % self._mname(m), (150, 220, 130))
            self.add_fx("impact", m.x, m.y, color=(150, 220, 130), radius=0.9, life=0.4)
        if "enrage" in traits and m.alive and self.rng.random() < config.ENRAGE_CHANCE:
            m.enraged = max(m.enraged, config.ENRAGE_TURNS)
            m.awake = True
            self.log("The %s flies into a mindless rage." % self._mname(m),
                     (176, 120, 132))
        if "lifesteal" in traits:
            got = p.heal(dmg // 2)
            if got:
                self.log("The blade drinks. You recover %d." % got, config.HEAL)
                self.add_fx("drain", p.x, p.y, color=(226, 74, 96), life=0.5,
                            tiles=[(m.x, m.y)])
            return got
        return 0

    def player_attack(self, m):
        p = self.player
        if p.invisible > 0:
            p.invisible = 0          # you cannot strike from hiding and stay hidden
            self.log("You break cover to strike.", config.DIM)
        dmg = p.damage_roll(self.rng)
        traits = p.weapon.traits
        crit = False

        if "crit" in traits and self.rng.random() < 0.25:
            dmg *= 2
            crit = True

        # a blade coating is spent on the FIRST thing you hit, whatever that turns out
        # to be. it does not care that you were saving it for the brute. venom hits
        # HARDER; a weakness coat leaves the struck thing sapped -- its own blows
        # falter for a while.
        coat = p.blade_coat
        if coat == "poison":
            dmg += self.rng.randint(6, 10)
        p.blade_coat = None

        if ("void" in traits and m.alive and not self._void_immune(m)
                and self.rng.random() < config.VOID_KILL_CHANCE):
            self.log("The Scimitar passes through the %s and it is simply gone."
                     % self._mname(m), config.MANA)
            self.add_fx("vanish", m.x, m.y, color=(120, 100, 190), life=0.5)
            self.void_monster(m)
            return

        self.log("You %s the %s for %d.%s"
                 % ("CRIT" if crit else "hit", self._mname(m), dmg,
                    " !" if crit else ""),
                 config.INK if not crit else config.GOLD)
        # your blow lands, and you can see it land
        self.add_fx("slash", m.x, m.y,
                    color=config.GOLD if crit else (240, 246, 255),
                    radius=1.35 if crit else 1.0,
                    life=0.34 if crit else 0.26)
        if crit:
            self.shake(4)
        if coat == "poison":
            self.log("The venom goes in with it. The blade is clean again.",
                     (150, 220, 130))
            self.add_fx("impact", m.x, m.y, color=(150, 220, 130), radius=0.9,
                        life=0.45)
        elif coat == "weak":
            m.weak = max(m.weak, 20)
            self.log("The draught soaks into the wound. The %s's blows will falter."
                     % self._mname(m), (200, 190, 120))
            self.add_fx("impact", m.x, m.y, color=(200, 190, 120), radius=0.9,
                        life=0.45)
        elif coat == "confuse":
            m.confused = max(m.confused, 12)
            m.awake = True
            self.log("The draught muddies its head. The %s staggers, lost."
                     % self._mname(m), (176, 120, 132))
            self.add_fx("impact", m.x, m.y, color=(176, 120, 132), radius=0.9,
                        life=0.45)
        if "shock" in traits and is_incorporeal(m.key):
            dmg = int(round(dmg * config.FULGURITE_INCORP_MULT))
        self.hurt_monster(m, dmg, source="player")
        self._weapon_status_on(m, dmg)

        if "stun" in traits and m.alive:
            # a rhythm, not a gamble: the FIRST blow on a thing staggers it, then every
            # Nth blow after. Deterministic, so the control is legible -- and it costs no
            # rng draw, which keeps generation/combat reproducible.
            m.hammer_hits += 1
            if (m.hammer_hits - 1) % config.HAMMER_STUN_CADENCE == 0:
                m.stunned = max(m.stunned, config.HAMMER_STUN_TURNS)
                self.log("The hammer rings its skull. It reels.", config.GOLD)
                # a real-time fx, not a read of m.stunned: the counter is spent inside
                # this same turn resolution, so a state-based indicator never shows.
                self.add_fx("stunstars", m.x, m.y, color=config.GOLD, life=0.75)
                self.shake(4)
        if "cleave" in traits:
            for dx, dy in DIRS8:
                o = self.monster_at(p.x + dx, p.y + dy)
                if o and o is not m and o.alive:
                    extra = max(1, dmg // 2)
                    if "shock" in traits and is_incorporeal(o.key):
                        extra = int(round(extra * config.FULGURITE_INCORP_MULT))
                    self.log("The axe carries through the %s for %d."
                             % (self._mname(o), extra), config.INK)
                    # every thing the axe carries through gets cut, visibly
                    self.add_fx("slash", o.x, o.y, color=(230, 240, 255),
                                radius=0.9, life=0.26)
                    self.hurt_monster(o, extra, source="player")
                    self._weapon_status_on(o, extra)
        if p.boots.trait == "kick" and m.alive:
            self._knockback(m)

    def _knockback(self, m):
        dx = (m.x > self.player.x) - (m.x < self.player.x)
        dy = (m.y > self.player.y) - (m.y < self.player.y)
        nx, ny = m.x + dx, m.y + dy
        if self.walkable(nx, ny) and not self.monster_at(nx, ny):
            m.x, m.y = nx, ny
            self.on_monster_moved(m)

    def _void_immune(self, m):
        """The void cannot swallow a boss (the Warden, or a mini-boss)."""
        return m.key in BOSS_KEYS

    def void_monster(self, m):
        """Unmake a monster: removed outright, no body, no loot -- the cost that
        balances the Scimitar. Still counts as your kill."""
        if m not in self.level.monsters:
            return
        self.level.monsters.remove(m)
        self.player.kills += 1
        self.run_kills += 1
        self.codex.stats["kills"] += 1
        self.codex.stats["kills_by"][m.key] = self.codex.stats["kills_by"].get(m.key, 0) + 1
        self.log("The %s is unmade -- the void takes it whole. Nothing remains."
                 % self._mname(m), config.MANA)
        self.add_fx("vanish", m.x, m.y, color=(120, 100, 190), life=0.5)

    def hurt_monster(self, m, dmg, source="player"):
        # some things resist some damage -- the stone golem shrugs off steel and
        # cracks in fire. the multiplier is 1.0 for everything else.
        dmg = max(0, int(round(dmg * damage_multiplier(m.key, source))))
        m.hp -= dmg
        if source == "player":
            self.codex.stats["damage_dealt"] += dmg
        if m.hp <= 0:
            self.kill_monster(m, source)

    def kill_monster(self, m, source="player"):
        if m not in self.level.monsters:
            return
        self.level.monsters.remove(m)

        # a body killed by ANOTHER MONSTER is not your kill: its killer took the loot,
        # and it teaches you nothing. thinning the floor is the whole reward.
        if source in MONSTER_SOURCES:
            self.level.slain.append(Slain(m.x, m.y, m.key, m.t.color, []))
            if len(self.level.slain) > 120:
                del self.level.slain[0]
            self.log("The %s is torn apart." % self._mname(m), config.DIM)
            return

        # a body killed by a TRAP it wandered onto is not your kill either -- you do
        # not get to crouch over a corpse you did not make. NO Kodex lesson and NO kill
        # credit. its loot is still on it, though: the trap took the monster, not the
        # coins, so you can walk over and pick the body clean.
        if source in TRAP_SOURCES:
            loot = roll_monster_loot(self.rng, self.depth, m.key)
            self.level.slain.append(Slain(m.x, m.y, m.key, m.t.color, loot))
            if len(self.level.slain) > 120:
                del self.level.slain[0]
            self.log("The %s dies." % self._mname(m), config.DIM)
            return

        # leave the body where it fell, still holding what it was carrying. the body
        # is the container: no coins spraying across the floor, no free pickups.
        loot = roll_monster_loot(self.rng, self.depth, m.key)
        self.level.slain.append(Slain(m.x, m.y, m.key, m.t.color, loot))
        if len(self.level.slain) > 120:
            del self.level.slain[0]
        self.player.kills += 1
        self.run_kills += 1
        self.codex.stats["kills"] += 1
        self.codex.stats["kills_by"][m.key] = self.codex.stats["kills_by"].get(m.key, 0) + 1
        self.log("The %s dies." % self._mname(m), config.HEAL)

        # you can read a corpse. it will not tell you as much as dying to one did,
        # and it will make you kill several of them before it tells you anything.
        fact = self.codex.reveal_on_kill(m.key)
        if fact:
            self.learned = fact
            self.log("You crouch over the body. [%s]" % fact_title(fact, self.codex), config.GOLD)
            self.codex.save()

        if loot:
            self.log("It falls with something on it.", config.GOLD)

        if m.key == "warden":
            self.won = True
            self.log("THE WARDEN FALLS.", config.GOLD)
            return

    def monster_attacks_player(self, m, dmg, ignore_armour=False, verb="hits"):
        p = self.player
        if p.sanctuary > 0:
            self.log("The %s strikes -- and the blow dies a hair from you." %
                     self._mname(m), config.MANA)
            self.add_fx("impact", p.x, p.y, color=(150, 210, 255), radius=0.7, life=0.3)
            return
        raw = dmg
        if not ignore_armour:
            dmg = max(0, dmg - p.defense)
        if dmg == 0:
            self.log("The %s %s you -- your armour turns it." % (self._mname(m), verb),
                     config.DIM)
            # sparks off the plate. THIS is the moment armour justifies the turns it
            # costs you, so it has to be visible, not a line of grey text.
            self.add_fx("impact", p.x, p.y, color=(200, 212, 228), radius=0.75,
                        life=0.3)
        else:
            self.log("The %s %s you for %d.%s"
                     % (self._mname(m), verb, dmg,
                        "  (armour ignored)" if ignore_armour and p.defense else ""),
                     config.BLOOD)
            self.add_fx("impact", p.x, p.y, color=config.BLOOD,
                        radius=0.7 + min(0.8, dmg / 14.0), life=0.38)
            self.hurt_player(dmg, m.key)
        if p.armour.trait == "thorns" and raw > 0 and m.alive:
            self.hurt_monster(m, 2, source="thorns")
            if m.alive:
                self.log("Your thorns bite back for 2.", config.HEAL)
                self.add_fx("impact", m.x, m.y, color=config.HEAL, radius=0.6,
                            life=0.32)

    def hurt_player(self, dmg, cause, silent=False):
        p = self.player
        if p.berserk > 0 and not silent:
            dmg += 2                       # rage leaves you open -- every blow bites deeper
        if p.resist > 0:
            dmg = (dmg + 1) // 2           # warded: incoming damage halved (rounded up)
        if p.vigor > 0 and dmg > 0:
            soaked = min(p.vigor, dmg)     # a vigour shell takes the blow before your blood
            p.vigor -= soaked
            dmg -= soaked
            if not silent and soaked:
                self.log("Your vigour soaks %d." % soaked, config.MANA)
            if p.vigor == 0:
                p.vigor_t = 0
                self.log("Your vigour is spent.", config.DIM)
        p.hp -= dmg
        self.codex.stats["damage_taken"] += dmg
        self.shake(min(10, 3 + dmg // 2))
        if p.hp <= 0 and not self.dead:
            self.kill_player(cause)

    def kill_player(self, cause):
        p = self.player
        if p.phoenix:
            # the Phoenix draught refuses this one death. once.
            p.phoenix = False
            p.hp = max(1, p.max_hp // 2)
            p.poison = p.frozen = p.confused = p.weak = 0
            self.log("The ember in your chest FLARES. Death lets go of you -- this "
                     "once.", config.GOLD)
            self.add_fx("flash", color=(255, 170, 70), life=0.7)
            self.add_fx("pulse", p.x, p.y, color=(255, 170, 70), life=0.9)
            self.shake(9)
            return
        self.dead = True
        self.death_cause = cause
        p.hp = 0
        self.remember_map()      # you die, but you do not forget the way you came
        self.log("You die, %s." % ("killed by " + CAUSE_NAME.get(cause, cause)),
                 config.BLOOD)

    # --- names ----------------------------------------------------------
    def _mname(self, m):
        """A monster you have not codexed does not have a name yet."""
        if self.codex.tier(m.key) == 0:
            # the poltergeist is not merely nameless -- it is INVISIBLE. until you
            # know it exists, all you can say is that something you cannot see hit you.
            return "unseen thing" if m.key == "poltergeist" else "thing"
        return m.name.lower()

    # --- player actions (each costs a turn) -----------------------------
    def player_move(self, dx, dy):
        p = self.player
        if p.stuck > 0:
            p.stuck -= 1
            self.log("You haul yourself out of the pit.", config.DIM)
            return self._end_player_turn()

        if p.confused > 0 and (dx or dy):
            # the floor swims. your feet do not go where you point them.
            dx, dy = self.rng.choice(DIRS8)

        nx, ny = p.x + dx, p.y + dy

        # it is solid, and walking into it is not an attack -- there is no attacking
        # it. it simply opens its hands and waits.
        if self.vendor_at(nx, ny):
            self.trading = True
            return False                     # opening the trade costs you nothing

        m = self.monster_at(nx, ny)
        if m:
            if m.disguised:
                m.disguised = False
                m.awake = True
                self.log("The chest UNFOLDS. It has teeth.", config.BLOOD)
                return self._end_player_turn()
            self.player_attack(m)
            return self._end_player_turn()
        if not self.walkable(nx, ny):
            return False
        p.x, p.y = nx, ny
        self.codex.stats["steps"] += 1
        self._enter_tile()
        return self._end_player_turn()

    def player_blink(self, dx, dy):
        p = self.player
        if p.boots.trait != "blink":
            self.log("Your boots are not made for that.", config.DIM)
            return False
        tx, ty = p.x, p.y
        for _ in range(3):
            nx, ny = tx + dx, ty + dy
            if not self.walkable(nx, ny) or self.monster_at(nx, ny):
                break
            tx, ty = nx, ny
        if (tx, ty) == (p.x, p.y):
            return False
        p.x, p.y = tx, ty
        self.log("You blink across the floor.", config.MANA)
        self._enter_tile()
        return self._end_player_turn()

    def player_wait(self):
        return self._end_player_turn()

    # --- what is under your feet -----------------------------------------
    def loot_label(self, kind, payload):
        if kind == "gold":
            return "%d gold" % payload
        if kind == "gear":
            g = ALL_GEAR[payload]
            return "%s  (%s)" % (g.name, g.desc())
        c = CONSUMABLES[payload]
        return c.name(self.codex)          # a colour, until you know better

    def loot_options(self):
        """Everything you could take from the tile you are standing on, as a list of
        numbered options. The UI shows this; the player picks from it."""
        p, lvl = self.player, self.level
        opts = []

        c = lvl.corpse
        if c and not c.taken and (c.x, c.y) == (p.x, p.y):
            if c.gold:
                opts.append({"kind": "gold", "payload": c.gold,
                             "label": "%d gold" % c.gold, "src": ("corpse", "gold")})
            seen = set()
            for field in ("weapon", "gift"):
                key = getattr(c, field)
                if key and key in ALL_GEAR and key not in seen and ALL_GEAR[key].tier > 0:
                    seen.add(key)
                    label = self.loot_label("gear", key)
                    if field == "gift":
                        label += "   [the gift]"
                    bonus = c.weapon_bonus if field == "weapon" else 0
                    opts.append({"kind": "gear", "payload": key, "label": label,
                                 "bonus": bonus, "src": ("corpse", field)})
            for i, (kind, payload) in enumerate(c.loot):
                opts.append({"kind": kind, "payload": payload,
                             "label": self.loot_label(kind, payload),
                             "src": ("corpse_loot", c, i)})

        # a body you made, still holding what it was carrying: it is a chest with a
        # face on it
        for s in lvl.slain:
            if (s.x, s.y) != (p.x, p.y):
                continue
            for i, (kind, payload) in enumerate(s.loot):
                opts.append({"kind": kind, "payload": payload,
                             "label": self.loot_label(kind, payload),
                             "src": ("slain", s, i)})

        for d in lvl.drops_at(p.x, p.y):
            opts.append({"kind": d.kind, "payload": d.payload, "bonus": d.bonus,
                         "label": self.loot_label(d.kind, d.payload),
                         "src": ("drop", d)})

        ch = lvl.chest_at(p.x, p.y)
        if ch:
            for i, (kind, payload) in enumerate(ch.loot):
                opts.append({"kind": kind, "payload": payload,
                             "label": self.loot_label(kind, payload),
                             "src": ("chest", ch, i)})
        return opts

    def slain_at(self, x, y):
        for s in self.level.slain:
            if (s.x, s.y) == (x, y) and s.has_loot:
                return s
        return None

    def loot_source_name(self):
        p, lvl = self.player, self.level
        c = lvl.corpse
        if c and not c.taken and (c.x, c.y) == (p.x, p.y):
            return "YOUR BODY"
        s = self.slain_at(p.x, p.y)
        if s:
            name = "THE " + MONSTER_NAME.get(s.key, "BODY").upper()
            return name if self.codex.tier(s.key) else "THE BODY"
        if lvl.chest_at(p.x, p.y):
            return "CHEST"
        if lvl.drop_at(p.x, p.y):
            return "ON THE FLOOR"
        return ""

    def _corpse_is_spent(self, c):
        """Is there anything left on the body worth offering? A body still clutching
        a Rusted Shiv is an empty body -- the menu never offers starting gear, so it
        must not count as loot when deciding whether the grave is done."""
        if c.gold or c.loot:
            return False
        for field in ("weapon", "gift"):
            key = getattr(c, field)
            if key and key in ALL_GEAR and ALL_GEAR[key].tier > 0:
                return False
        return True

    def _consume_option(self, o, auto=False):
        """Take one option. `auto` is the 'take all' sweep, which refuses to swap a
        good piece of gear for a worse one behind your back -- an explicit choice is
        allowed to downgrade you, but 'all' never will."""
        p, lvl = self.player, self.level
        kind, payload, src = o["kind"], o["payload"], o["src"]

        # Room for THIS item specifically: a stack of it with space, or an empty slot.
        # Checked BEFORE anything is removed from its container, so a refused pickup
        # leaves the thing exactly where it was rather than quietly destroying it.
        if kind == "item" and not p.can_take(payload):
            self.log("No room for the %s -- every slot is full."
                     % CONSUMABLES[payload].name(self.codex), config.DIM)
            return False

        if kind == "gear" and auto:
            g = ALL_GEAR[payload]
            cur = {"weapon": p.weapon, "armour": p.armour, "boots": p.boots}[g.slot]
            if g.tier <= cur.tier:
                self.log("You leave the %s -- your %s is better." % (g.name, cur.name),
                         config.DIM)
                return False

        if src[0] == "corpse":
            c = lvl.corpse
            field = src[1]
            if field == "gold":
                p.gold += c.gold
                self.codex.stats["gold_banked"] += c.gold
                self.log("You take %d gold back off your own body." % c.gold,
                         config.CORPSE)
                c.gold = 0
            else:
                key = getattr(c, field)
                bonus = c.weapon_bonus if field == "weapon" else 0
                setattr(c, field, None)
                if field == "weapon":
                    c.weapon_bonus = 0
                self.log("You prise the %s from your own fingers."
                         % ALL_GEAR[key].name, config.CORPSE)
                self._take("gear", key, sink=c, bonus=bonus)   # what comes off stays on the body
            self._settle_corpse(c)

        elif src[0] == "corpse_loot":
            c, i = src[1], src[2]
            if i >= len(c.loot):
                return False
            k, pl = c.loot.pop(i)
            self._take(k, pl, sink=c)
            self._settle_corpse(c)

        elif src[0] == "drop":
            d = src[1]
            if d in lvl.drops:
                lvl.drops.remove(d)
            if d.gift:
                self.codex.claim_gift(d.gift)
                self.codex.gift_item = d.payload
                p.gift = d.payload
                self.codex.save()
            # taken off the bare floor: whatever comes off goes onto the bare floor
            self._take(d.kind, d.payload, sink=None, bonus=d.bonus)

        elif src[0] == "slain":
            s, i = src[1], src[2]
            if i >= len(s.loot):
                return False
            k, pl = s.loot.pop(i)
            self._take(k, pl, sink=s)   # the body stays; it just changes what it holds

        elif src[0] == "chest":
            ch, i = src[1], src[2]
            if i >= len(ch.loot):
                return False
            k, pl = ch.loot.pop(i)
            self._take(k, pl, sink=ch)  # _take may put your old gear back in first
            if not ch.loot:
                ch.opened = True
        return True

    def _settle_corpse(self, c):
        """Write the body's current state back to the save.

        Without this, looting your own corpse only changed the in-memory copy: the
        save still believed the gold was on it, and the next death would hand it to
        you a second time. And a third.
        """
        if self._corpse_is_spent(c):
            c.taken = True
            self.codex.take_corpse(self.depth)
        else:
            self.codex.write_corpse(self.depth, c.x, c.y, c.gold, c.weapon, c.gift,
                                    c.loot, weapon_bonus=c.weapon_bonus)
        self.codex.save()

    def take_option(self, index):
        """The player pressed a number. Take exactly that one thing.

        A refused take (a full pack) costs no turn -- the dungeon must not charge you
        for an action it did not let you perform.
        """
        opts = self.loot_options()
        if index < 0 or index >= len(opts):
            return False
        if not self._consume_option(opts[index]):
            return False
        return self._end_player_turn()

    def take_all(self):
        """The player pressed the 'all' option."""
        took = 0
        for _ in range(24):
            opts = self.loot_options()
            if not opts:
                break
            progressed = False
            for o in opts:
                if self._consume_option(o, auto=True):
                    took += 1
                    progressed = True
                    break                  # the list shifts under us; re-query
            if not progressed:
                break
        if not took:
            return False
        return self._end_player_turn()

    def player_pickup(self):
        """G: take everything worth taking. The numbered menu is the fine-grained
        version of this."""
        opts = self.loot_options()
        if not opts:
            self.log("There is nothing here.", config.DIM)
            return False
        if len(opts) == 1:
            self._consume_option(opts[0])
            return self._end_player_turn()
        return self.take_all()

    def _take(self, kind, payload, sink=None, bonus=0):
        """Put one thing into the hero's hands.

        Gear is a SWAP, not a purchase. Whatever comes off does not evaporate -- it
        goes back where the new thing came from: into the chest, onto the body, into
        your own corpse, or, if you picked the new thing up off the floor, onto the
        floor at your feet. You can always change your mind. `sink` is the container
        it came out of, or None for bare ground. `bonus` is a placed weapon's
        masterwork/enchant +n; it rides onto the equipped instance.
        """
        p = self.player
        if kind == "gold":
            p.gold += payload
            self.log("You pocket %d gold." % payload, config.GOLD)
        elif kind == "item":
            p.pack_add(payload)
            c = CONSUMABLES[payload]
            self.log("You take the %s." % c.name(self.codex), config.ITEM)
        elif kind == "gear":
            g = ALL_GEAR[payload]
            if g.slot == "weapon" and bonus:
                g = g.copy(bonus=bonus)          # carry the found/kept +n into the swap
            old = p.equip(g)
            self.codex.see_gear(payload)          # you have handled it -> a Kodex entry
            name, desc = p.gear_display(g.slot)   # shows any enchant it already carried
            self.log("You put on the %s.  (%s)" % (name, desc), config.ITEM)

            # keep the gift flag honest across a swap
            if old and p.gift == old.key:
                p.gift = None
            if payload == self.codex.gift_item:
                p.gift = payload

            if old:
                self._put_back(old, sink)

    # --- the cheat --------------------------------------------------------
    def grant_cheat(self):
        """CTRL+0987. Best weapon, best armour, best boots, and as many healing
        potions as will fit. For testing the deep floors without spending an evening
        earning them.

        The gear you displace is NOT dropped -- this is a debug tool, not a swap, and
        littering the floor with your old rags would just be noise.
        """
        from .items import ARMOURS, BOOTS, WEAPONS

        p = self.player
        best_w = WEAPONS["kris"]      # the Vampiric Kris, by request -- the lifesteal
                                      # matters more for testing than raw damage does
        best_a = max(ARMOURS.values(), key=lambda g: (g.tier, g.defense))
        best_b = max(BOOTS.values(), key=lambda g: (g.tier, g.speed))
        p.weapon = best_w.copy()
        p.armour = best_a
        p.boots = best_b
        for g in (best_w, best_a, best_b):
            self.codex.see_gear(g.key)

        got = 0
        for _ in range(9):
            if not p.can_take("ochre"):
                break                     # take whatever fits, and no more
            p.pack_add("ochre")
            got += 1

        self.log("[CHEAT] %s, %s, %s, and %d healing potion%s."
                 % (best_w.name, best_a.name, best_b.name, got,
                    "" if got == 1 else "s"),
                 config.GOLD)
        if got < 9:
            self.log("[CHEAT] Only %d would fit in the pack." % got, config.DIM)
        self.add_fx("pulse", p.x, p.y, color=config.GOLD, life=0.6)
        return got

    def _open_tile_near(self, x, y):
        """An empty walkable tile next to (x, y) with nothing already on it, or None."""
        for dx, dy in ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0),
                       (-1, 1), (0, 1), (1, 1)):
            nx, ny = x + dx, y + dy
            if (self.walkable(nx, ny) and not self.monster_at(nx, ny)
                    and not self.vendor_at(nx, ny) and not self.level.drops_at(nx, ny)):
                return (nx, ny)
        return None

    def cheat_equip_weapon(self, key, bonus=0):
        """CTRL+12 weapon bench: swap any ordinary weapon (base, or its +2 masterwork)
        straight onto the hero. Your current weapon drops at your feet, keeping its own
        +n, so nothing is lost and you can pick it back up."""
        from .items import WEAPONS
        if key not in WEAPONS:
            return
        g = WEAPONS[key].copy(bonus=bonus)
        old = self.player.equip(g)          # equip stores its own copy and returns the old
        self.codex.see_gear(key)
        name = "%s +%d" % (g.name, bonus) if bonus else g.name
        self.log("[CHEAT] You heft the %s.  (%s)" % (name, g.desc()), config.GOLD)
        self.add_fx("pulse", self.player.x, self.player.y, color=config.GOLD, life=0.6)
        if old:
            self._put_back(old, None)       # onto the floor at your feet, +n intact

    def drop_gear_near(self, gear_key):
        """CTRL+87 arsenal tester: lay a chosen piece of gear on an open tile right
        next to the player, so they can step onto it and try it. Prefers an empty
        adjacent floor tile; if the player is boxed in, it lands at their feet.
        Returns the (x, y) it dropped on, or None if the key is unknown."""
        from .items import ALL_GEAR
        if gear_key not in ALL_GEAR:
            return None
        p = self.player
        spot = self._open_tile_near(p.x, p.y) or (p.x, p.y)
        self.level.drops.append(Drop(spot[0], spot[1], "gear", gear_key))
        self.log("[CHEAT] A %s clatters onto the floor beside you."
                 % ALL_GEAR[gear_key].name, config.GOLD)
        self.add_fx("pulse", spot[0], spot[1], color=config.GOLD, life=0.6)
        return spot

    def cheat_give_consumable(self, flavor):
        """CTRL+67 / CTRL+76 testers: hand the player a chosen scroll/potion, already
        identified (you picked it by name, so you know it). Into the pack if it fits,
        otherwise onto an open tile beside you."""
        from .items import CONSUMABLES
        if flavor not in CONSUMABLES:
            return
        p = self.player
        self.codex.identify(flavor)
        name = CONSUMABLES[flavor].true_name
        if p.pack_add(flavor):
            self.log("[CHEAT] %s, into your pack." % name, config.GOLD)
        else:
            spot = self._open_tile_near(p.x, p.y) or (p.x, p.y)
            self.level.drops.append(Drop(spot[0], spot[1], "item", flavor))
            self.log("[CHEAT] Pack full -- %s dropped beside you." % name, config.GOLD)
        self.add_fx("pulse", p.x, p.y, color=config.GOLD, life=0.6)

    # --- trade ------------------------------------------------------------
    def buy(self, index):
        """Buy stock item `index`. Costs no turn -- it is a conversation, not a fight."""
        v = self.level.vendor
        p = self.player
        if not v or index < 0 or index >= len(v.stock):
            return False
        kind, payload = v.stock[index]
        cost = price_of(kind, payload, self.depth)
        if p.gold < cost:
            self.log("You cannot afford it. It does not haggle.", config.DIM)
            return False
        if kind == "item" and not p.can_take(payload):
            self.log("You have nowhere to put it.", config.DIM)
            return False

        p.gold -= cost
        v.stock.pop(index)
        # gear you displace drops at your feet -- it will not take it off your hands
        self._take(kind, payload, sink=None)
        self.log("You pay %d gold." % cost, config.GOLD)
        return True

    def sell(self, slot_index):
        """Sell one item out of a pack slot. It buys potions and scrolls. Nothing
        else -- do not offer it your boots."""
        v = self.level.vendor
        p = self.player
        if not v:
            return False
        slot = p.slot_of(slot_index)
        if not slot:
            return False
        flavor = slot[0]
        if not v.buys(flavor):
            self.log("It has no interest in that.", config.DIM)
            return False
        paid = sell_price_of(flavor, self.depth)
        p.pack_remove(slot_index)
        p.gold += paid
        self.log("It takes the %s and counts out %d gold."
                 % (CONSUMABLES[flavor].name(self.codex), paid), config.GOLD)
        return True

    def container_here(self):
        """The thing under your feet that can hold something, if any."""
        p, lvl = self.player, self.level
        c = lvl.corpse
        if c and not c.taken and (c.x, c.y) == (p.x, p.y):
            return c
        s = self.slain_at(p.x, p.y)
        if s:
            return s
        return lvl.chest_at(p.x, p.y)

    def drop_item(self, index, whole=False):
        """Dump one -- or the whole stack -- out of pack slot `index`.

        It goes into whatever container you are standing on, or onto the floor at your
        feet if there is none: the same rule as a gear swap, so there is one mental
        model for 'where did my stuff go'. Nothing is ever destroyed. A whole stack
        costs the same single turn as one item, so clearing space is not punished by
        the turn economy.
        """
        if self.player.frozen > 0:
            return False              # frozen solid: you cannot rummage in your pack either
        p = self.player
        slot = p.slot_of(index)
        if not slot:
            return False
        flavor = slot[0]
        n = slot[1] if whole else 1
        sink = self.container_here()

        for _ in range(n):
            if p.slot_of(index) is None:
                break
            p.slots[index][1] -= 1
            if p.slots[index][1] <= 0:
                p.slots[index] = None
            if sink is not None and hasattr(sink, "loot"):
                sink.loot.append(("item", flavor))
            else:
                self.level.drops.append(Drop(p.x, p.y, "item", flavor))

        p.consolidate(flavor)
        name = CONSUMABLES[flavor].name(self.codex)
        where = "into the chest" if sink is not None else "at your feet"
        self.log("You put %s%s %s." % (name, " x%d" % n if n > 1 else "", where),
                 config.DIM)
        if isinstance(sink, Corpse):
            self.codex.write_corpse(self.depth, sink.x, sink.y, sink.gold,
                                    sink.weapon, sink.gift, sink.loot,
                                    weapon_bonus=sink.weapon_bonus)
            self.codex.save()
        return self._end_player_turn()

    def _put_back(self, gear, sink):
        """The gear you took off. Back into the container you looted, or onto the ground.
        NOTE: a weapon returned to a container's loot LIST loses its +n this phase (the
        loot-tuple format is 2-wide); a weapon returned to bare GROUND keeps it. The
        death-corpse's own weapon slot preserves +n (see leave_corpse). The loot-list
        edge is closed when armour/boots join the per-instance model."""
        if sink is not None and hasattr(sink, "loot"):
            sink.loot.append(("gear", gear.key))
            where = ("chest" if isinstance(sink, Chest)
                     else "body" if isinstance(sink, Slain)
                     else "your own body")
            self.log("You leave the %s in the %s." % (gear.name, where), config.DIM)
        else:
            p = self.player
            bonus = getattr(gear, "bonus", 0)
            self.level.drops.append(Drop(p.x, p.y, "gear", gear.key, bonus=bonus))
            self.log("You drop the %s at your feet." % gear.name, config.DIM)

    def use_item(self, index):
        """`index` is a SLOT, 0-5. The number you press is the slot you drink from --
        not a position in an alphabetised list that shuffles under your fingers."""
        if self.player.frozen > 0:
            return False              # frozen hands cannot uncork a flask or unroll a scroll
        p = self.player
        slot = p.slot_of(index)
        if not slot:
            return False
        flavor = p.pack_remove(index)     # takes one, then consolidates downward
        if flavor is None:
            return False
        c = CONSUMABLES[flavor]
        was_known = self.codex.identified(flavor)

        # THE VENOM RULE, now for EVERY bad potion. This is the whole game in one
        # object.
        #
        # While you do not know what it is, "using" it means what using an unknown
        # flask always means: you put it in your mouth. It hurts you, and that is how
        # you find out.
        #
        # Once you KNOW it is a bad one, using it means something else entirely -- you
        # never drink it again. You paint it on your blade, and the next thing you hit
        # takes it instead of you: venom bites harder, weakness saps their strength.
        # The same object, unchanged, is a mistake to the ignorant and a weapon to the
        # informed. Nothing about the potion changed. You did.
        if was_known and c.kind == "potion" and c.effect in COATABLE_EFFECTS:
            return self._coat_blade(c)

        if c.kind == "potion":
            self.codex.stats["potions_drunk"] += 1
            self.log("You drink the %s." % c.name(self.codex), config.ITEM)
        else:
            self.log("You read the %s aloud." % c.name(self.codex), config.ITEM)

        self._apply_effect(c.effect)

        # using an unknown thing teaches you what it was -- the hard way, sometimes
        if not was_known:
            fact = self.codex.identify(flavor)
            if fact:
                self.learned = fact
                self.log("So THAT is what it was. [%s]" % fact_title(fact, self.codex), config.GOLD)
        if self.aiming:
            self.aiming_flavor = flavor   # remembered in case the mode is cancelled
            return True          # a targeting mode opened; the turn ends on confirm
        return self._end_player_turn()

    # --- targeted teleport (ZEPH) ---------------------------------------
    def valid_teleport(self, x, y):
        """A spot you may jump to: somewhere you have SEEN, that is open floor, and
        that has nothing standing on it."""
        return (self.in_bounds(x, y) and self.level.explored[y][x]
                and self.walkable(x, y) and not self.monster_at(x, y)
                and not self.vendor_at(x, y)
                and (x, y) != (self.player.x, self.player.y))

    def teleport_to(self, x, y):
        """Confirm the ZEPH cursor. Jumps there and ends the turn. Returns False (and
        keeps the cursor open) if the spot is not somewhere you can land."""
        if not self.valid_teleport(x, y):
            return False
        p = self.player
        self.add_fx("vanish", p.x, p.y, color=config.MANA, life=0.5)
        p.x, p.y = x, y
        self.add_fx("arrive", x, y, color=config.MANA, life=0.6)
        self.log("The door closes behind you. You are where you meant to be.",
                 config.MANA)
        self.aiming = self.aiming_flavor = None
        return self._end_player_turn()

    def cancel_aim(self):
        """Back out of the TELEPORT cursor. The scroll is already spent, and reading it
        cost you the turn either way."""
        self.aiming = self.aiming_flavor = None
        self.log("The door in the air folds shut, unused.", config.DIM)
        return self._end_player_turn()

    # --- selectable banishment (OSSK) -----------------------------------
    def banishable_types(self):
        """The distinct kinds among the monsters you can currently SEE -- the choices a
        Banishment offers. Returns [(key, count), ...], most numerous first. Empty if
        nothing is in sight (which is when you back out)."""
        seen = {}
        for m in self.level.monsters:
            if not m.disguised and self.visible(m.x, m.y):
                seen[m.key] = seen.get(m.key, 0) + 1
        return sorted(seen.items(), key=lambda kv: (-kv[1], kv[0]))

    def banish_type(self, key):
        """Confirm the picker: unmake EVERY monster of `key` on the whole floor (not
        just the ones in sight). No corpses, no loot, no credit. Ends the turn."""
        gone = [m for m in self.level.monsters if m.key == key]
        if not gone:
            return False
        for m in gone:
            self.add_fx("vanish", m.x, m.y, color=(184, 140, 220), life=0.5)
        name = self._mname(gone[0])
        self.level.monsters = [m for m in self.level.monsters if m.key != key]
        self.log("A word of unmaking. Every %s on this floor -- %d of them -- is "
                 "simply GONE." % (name, len(gone)), (184, 140, 220))
        self.shake(6)
        self.aiming = self.aiming_flavor = None
        return self._end_player_turn()

    def cancel_banish(self):
        """Stop, half a word in. The scroll is NOT spent -- it goes back in your pack --
        but you have read enough of it to know what it is (it was identified on use).
        No turn passes."""
        if self.aiming_flavor:
            if not self.player.pack_add(self.aiming_flavor):
                self.level.drops.append(
                    Drop(self.player.x, self.player.y, "item", self.aiming_flavor))
        self.log("You let the word die unspoken. The scroll is still yours -- but you "
                 "know its purpose now.", config.DIM)
        self.aiming = self.aiming_flavor = None
        return False

    def _coat_blade(self, c):
        """You know what this is now, so you do not drink it. You wipe it down the
        edge of your weapon and wait for something to walk into range. Works for ANY
        negative potion (see COATABLE_EFFECTS): the coat carries the potion's effect,
        and it lands on the next thing you strike -- them, not you."""
        p = self.player
        p.blade_coat = c.effect
        self.log("You wipe the %s down your %s. It glistens."
                 % (c.true_name.lower(), p.weapon.name), (200, 200, 150))
        self.log("The next thing you hit is going to feel it.", config.DIM)
        return self._end_player_turn()

    def _apply_effect(self, effect):
        p = self.player
        if effect == "heal":
            got = p.heal(self.rng.randint(10, 16))
            self.log("Warmth. You recover %d." % got, config.HEAL)
            self.add_fx("pulse", p.x, p.y, color=config.HEAL, life=0.55)
        elif effect == "haste":
            p.haste = 20
            self.log("The world slows down around you.", config.MANA)
            self.add_fx("pulse", p.x, p.y, color=config.MANA, life=0.55)
        elif effect == "might":
            p.might = 20
            self.log("Your arms fill with fury.", config.GOLD)
            self.add_fx("pulse", p.x, p.y, color=config.GOLD, life=0.55)
        elif effect == "poison":
            p.poison = max(p.poison, 10)
            self.log("It burns going down. You have been poisoned.", config.TRAP)
            self.add_fx("pulse", p.x, p.y, color=(140, 220, 120), life=0.7)
            self.hurt_player(3, "poison")
        elif effect == "map":
            # KESH: the reveal is mostly OFF-SCREEN, because the camera is looking at
            # you. Without something to watch, reading the scroll looks like reading
            # nothing. So send a ripple out through the stone -- you can see the
            # knowledge travelling away from you.
            newly = [(x, y) for y in range(self.level.h) for x in range(self.level.w)
                     if self.level.walkable(x, y) and not self.level.explored[y][x]]
            self.level.reveal_all()      # the stone only: never the contents
            self.log("The stone unrolls itself in your mind. Only the stone.",
                     config.MANA)
            self.add_fx("ripple", p.x, p.y, radius=26, color=config.MANA, life=0.9,
                        tiles=newly)
        elif effect == "fire":
            hit = [m for m in list(self.level.monsters) if self.visible(m.x, m.y)]
            self.log("Fire roars through everything you can see.", (255, 140, 70))
            self.shake(10)
            # the whole visible floor lights up, and every single thing it touches --
            # including you -- burns where it stands. VORN is indiscriminate, and the
            # player needs to watch it be indiscriminate. so: every tile it reaches
            # is literally set alight, which is also a precise map of its range.
            self.add_fx("flash", color=(255, 150, 70), life=0.55)
            self.add_fx("burning", life=1.1, tiles=self.visible_floor())
            for m in hit:
                self.add_fx("burst", m.x, m.y, radius=0.6, color=(255, 170, 70),
                            life=0.6)
                self.hurt_monster(m, self.rng.randint(8, 14), source="scroll")
            self.add_fx("burst", p.x, p.y, radius=0.6, color=(255, 110, 60), life=0.6)
            self.hurt_player(self.rng.randint(2, 5), "glyph")
        elif effect == "blink":
            # UUL: the camera cuts to somewhere else entirely. Without a mark on the
            # tile you LEFT and the tile you ARRIVED at, the player cannot tell a
            # teleport from a bug -- they just find themselves in a strange room.
            for _ in range(200):
                r = self.rng.choice(self.level.rooms)
                x = self.rng.randint(r.x, r.x + r.w - 1)
                y = self.rng.randint(r.y, r.y + r.h - 1)
                if self.walkable(x, y) and not self.monster_at(x, y):
                    self.add_fx("vanish", p.x, p.y, color=config.MANA, life=0.5)
                    p.x, p.y = x, y
                    self.add_fx("arrive", x, y, color=config.MANA, life=0.6)
                    self.log("The floor lurches. You are somewhere else.", config.MANA)
                    break
        elif effect == "summon":
            table = ["rat", "kobold", "spitter", "brute", "wraith"]
            n = 2 + self.depth // 3
            self.log("Something answers. Several somethings.", config.BLOOD)
            placed = 0
            spawned = []
            for dx, dy in DIRS8:
                if placed >= n:
                    break
                x, y = p.x + dx, p.y + dy
                if self.walkable(x, y) and not self.monster_at(x, y):
                    m = Monster(self.rng.choice(table[:2 + self.depth // 2]), x, y)
                    m.awake = True
                    self.level.monsters.append(m)
                    spawned.append((x, y))
                    placed += 1
            if spawned:
                # GRAMM: things must not simply BE there. show them arriving -- the
                # ground opens under each one, especially since they may still be
                # unreadable '?' silhouettes to a hero who has never met them.
                self.add_fx("summon", p.x, p.y, color=config.BLOOD, life=0.85,
                            tiles=spawned)
                self.shake(6)

        # --- WAVE 1: the rest of the common tier -------------------------
        elif effect == "stoneskin":
            p.stoneskin = 20
            self.log("Your skin hardens to stone. Blows will slide off it.",
                     (170, 174, 184))
            self.add_fx("pulse", p.x, p.y, color=(170, 174, 184), life=0.55)
        elif effect == "regen":
            # now also the cure: it washes out poison, weakness and confusion first,
            # then knits you closed a little each turn.
            ailed = p.poison > 0 or p.weak > 0 or p.confused > 0
            p.poison = 0
            p.weak = 0
            p.confused = 0
            p.regen = 20
            self.log("Your wounds begin to knit closed on their own.%s"
                     % (" Whatever ailed you lets go." if ailed else ""), config.HEAL)
            self.add_fx("pulse", p.x, p.y, color=config.HEAL, life=0.55)
        elif effect == "weak":
            p.weak = max(p.weak, 20)
            self.log("Your strength drains away. Everything feels heavier.", config.TRAP)
            self.add_fx("pulse", p.x, p.y, color=(150, 140, 90), life=0.7)
        elif effect == "vigor":
            p.vigor = 12
            p.vigor_t = 30
            self.log("Strength wells up under your skin -- a reserve that will take "
                     "the next blows before your own blood does.", config.MANA)
            self.add_fx("pulse", p.x, p.y, color=(200, 214, 234), life=0.6)
        # --- WAVE 3: the rare tier ---------------------------------------
        elif effect == "vitality":
            gain = 10
            p.max_hp += gain
            p.hp += gain                       # the new capacity comes filled
            self.log("Something in you deepens. You can hold %d more life than you "
                     "could -- for good." % gain, config.HEAL)
            self.add_fx("pulse", p.x, p.y, color=config.HEAL, life=0.8)
        elif effect == "heroism":
            p.heroism = 20
            p.heal(self.rng.randint(12, 18))
            self.log("You stand taller. Harder to hurt, faster, and every blow you "
                     "land carries all of it.", config.GOLD)
            self.add_fx("pulse", p.x, p.y, color=config.GOLD, life=0.8)
            self.shake(4)
        elif effect == "insight":
            fact = self.codex.reveal_random(self.rng)
            if fact:
                self.learned = fact
                self.log("Understanding arrives whole, unearned. [%s]" % fact_title(fact, self.codex),
                         config.GOLD)
                self.codex.save()
            else:
                self.log("You reach for a new truth and find you already hold them "
                         "all.", config.DIM)
            self.add_fx("pulse", p.x, p.y, color=(196, 240, 250), life=0.7)
        elif effect == "phoenix":
            p.phoenix = True
            self.log("An ember settles behind your ribs, patient. The next death that "
                     "comes for you will be turned away -- once.", (255, 170, 70))
            self.add_fx("pulse", p.x, p.y, color=(255, 170, 70), life=0.8)
        elif effect == "banish":
            # opens a picker: you choose WHICH kind to unmake (see banish_type). you
            # can also stop and keep the scroll -- but you have read it, so you now
            # know what it is (see cancel_banish).
            self.aiming = "banish"
            self.log("You begin a word of unmaking, and it waits on a name. Choose "
                     "what to erase -- or stop, and keep the scroll.", (184, 140, 220))
        elif effect == "descent":
            if self.level.stairs is None:
                self.log("There is no way down from here. Only the Warden.",
                         config.BLOOD)
            else:
                sx, sy = self.level.stairs
                self.add_fx("vanish", p.x, p.y, color=config.MANA, life=0.5)
                p.x, p.y = sx, sy
                self.level.compute_fov(p.x, p.y)
                self.add_fx("arrive", sx, sy, color=config.STAIRS, life=0.6)
                self.log("The floor runs downhill under you. You are standing on the "
                         "way down.", config.STAIRS)
        elif effect == "thunderclap":
            hit = [m for m in list(self.level.monsters) if self.visible(m.x, m.y)]
            self.log("You bring your hands together and the air itself CRACKS.",
                     (200, 220, 255))
            self.shake(10)
            self.add_fx("flash", color=(210, 225, 255), life=0.45)
            for m in hit:
                self.add_fx("burst", m.x, m.y, radius=0.6, color=(200, 220, 255),
                            life=0.5)
                self.hurt_monster(m, self.rng.randint(14, 22), source="scroll")
            if not hit:
                self.log("...but there is nothing in sight to feel it.", config.DIM)
        elif effect == "sanctuary":
            p.sanctuary = 12
            self.log("A stillness closes around you. For a while, nothing that reaches "
                     "you can land a blow.", (150, 210, 255))
            self.add_fx("pulse", p.x, p.y, color=(150, 210, 255), life=0.8)
        elif effect == "identify":
            # MORN: name the biggest unknown thing you are holding -- usually the one
            # you have been hoarding because you dared not risk it.
            counts = {}
            for f in p.pack:
                if not self.codex.identified(f):
                    counts[f] = counts.get(f, 0) + 1
            if not counts:
                self.log("The scroll spells out a name, but nothing you carry is a "
                         "mystery anymore.", config.DIM)
            else:
                target = max(counts, key=lambda f: (counts[f], -p.pack.index(f)))
                fact = self.codex.identify(target)
                self.log("The scroll spells out a true name: %s."
                         % CONSUMABLES[target].true_name, config.GOLD)
                if fact:
                    self.learned = fact
                self.add_fx("pulse", p.x, p.y, color=config.GOLD, life=0.55)
        elif effect == "light":
            # YRIS: a burst of revealing light -- the local stone, any traps in it, and
            # whatever is lurking nearby, all laid bare for this moment.
            R = 7
            lit = []
            for dy in range(-R, R + 1):
                for dx in range(-R, R + 1):
                    if dx * dx + dy * dy > R * R:
                        continue
                    x, y = p.x + dx, p.y + dy
                    if not self.in_bounds(x, y):
                        continue
                    self.level.explored[y][x] = True
                    self.level.seen[y][x] = True
                    self.level.visible[y][x] = True     # resets on your next step
                    lit.append((x, y))
            found = 0
            for tr in self.level.traps:
                if max(abs(tr.x - p.x), abs(tr.y - p.y)) <= R:
                    if self.codex.find_trap(self.depth, tr.x, tr.y):
                        found += 1
            self.log("Light floods out from you, and the dark gives up its secrets.",
                     config.MANA)
            if found:
                self.log("You catch the glint of %d trap%s nearby."
                         % (found, "" if found == 1 else "s"), config.TRAP)
            self.add_fx("ripple", p.x, p.y, radius=R + 2, color=(240, 236, 200),
                        life=0.8, tiles=lit)
        elif effect == "aggravate":
            # GHASK: the whole floor's head snaps up. every last thing is now awake and
            # coming. this is the scroll you never wanted to read.
            self.wake_all()
            self.log("A soundless shriek rolls through the whole floor. Everything "
                     "down here just woke up, and it knows where you are.", config.BLOOD)
            self.add_fx("shout", p.x, p.y, radius=30, color=config.BLOOD, life=1.0)
            self.shake(8)
        elif effect == "detect":
            # VOSH: every hoard on the floor lights up at once -- chests, dropped gear,
            # loose coin. it shows you WHERE the treasure is. never what guards it.
            marks = []
            for ch in self.level.chests:
                if not ch.opened:
                    self.level.explored[ch.y][ch.x] = True
                    self.level.seen[ch.y][ch.x] = True
                    marks.append((ch.x, ch.y))
            for d in self.level.drops:
                self.level.explored[d.y][d.x] = True
                self.level.seen[d.y][d.x] = True
                marks.append((d.x, d.y))
            self.log("Every hoard on the floor glimmers in your mind's eye. %d in all."
                     % len(marks) if marks else
                     "You reach out for treasure, and find the floor picked clean.",
                     config.GOLD)
            if marks:
                self.add_fx("ripple", p.x, p.y, radius=28, color=config.GOLD,
                            life=0.9, tiles=marks)

        # --- WAVE 2: uncommon self-buffs and enchantments ----------------
        elif effect == "greatheal":
            got = p.heal(p.max_hp)                 # all the way to full
            self.log("Warmth pours through you -- %s"
                     % ("every wound closes." if got else "but you were already whole."),
                     config.HEAL)
            if got:
                self.log("You recover %d." % got, config.HEAL)
            self.add_fx("pulse", p.x, p.y, color=config.HEAL, life=0.7)
        elif effect == "berserk":
            p.berserk = 18
            self.log("The world goes red. You will hit harder and move faster -- and "
                     "you have stopped caring what hits back.", (232, 92, 52))
            self.add_fx("pulse", p.x, p.y, color=(232, 92, 52), life=0.6)
            self.shake(5)
        elif effect == "resist":
            p.resist = 20
            self.log("A ward settles over your skin. Whatever lands will land softer.",
                     (60, 172, 158))
            self.add_fx("pulse", p.x, p.y, color=(60, 172, 158), life=0.6)
        elif effect == "levitate":
            p.levitate = 20
            p.stuck = 0                            # float straight up out of any pit
            self.log("You lift off the floor. Pressure plates and pits are somebody "
                     "else's problem now.", config.MANA)
            self.add_fx("pulse", p.x, p.y, color=(130, 206, 220), life=0.6)
        elif effect == "enchant_weapon":
            p.weapon.bonus += 1
            self.log("Your %s drinks the light and keeps it. +%d damage, for good."
                     % (p.weapon.name, p.weapon.bonus), config.GOLD)
            self.add_fx("pulse", p.x, p.y, color=config.GOLD, life=0.6)
        elif effect == "enchant_armour":
            key = p.armour.key
            p.enchants[key] = p.enchants.get(key, 0) + 1
            self.log("Your %s hardens with a light of its own. +%d defence, for good."
                     % (p.armour.name, p.enchants[key]), config.GOLD)
            self.add_fx("pulse", p.x, p.y, color=config.GOLD, life=0.6)
        elif effect == "invisible":
            p.invisible = 16
            self.log("The light bends around you. Nothing down here can find you now "
                     "-- until you strike, or it thins away.", (190, 200, 220))
            self.add_fx("pulse", p.x, p.y, color=(190, 200, 220), life=0.7)
        elif effect == "fear":
            hit = [m for m in self.level.monsters
                   if m.dist(p.x, p.y) <= 6 and not m.disguised]
            for m in hit:
                m.feared = max(m.feared, 8)
                m.awake = True
            self.log("A wave of dread rolls off you. %s"
                     % ("Everything nearby turns and runs." if hit
                        else "But there is nothing near to feel it."), config.MANA)
            self.add_fx("shout", p.x, p.y, radius=14, color=(120, 100, 190), life=0.9)
        elif effect == "hold":
            hit = [m for m in self.level.monsters
                   if m.dist(p.x, p.y) <= 6 and not m.disguised]
            for m in hit:
                m.stunned = max(m.stunned, 10)
                m.intent = None
            self.log("Time snags. %s"
                     % ("Everything near you locks rigid." if hit
                        else "But nothing near you is caught."), config.MANA)
            self.add_fx("shout", p.x, p.y, radius=14, color=(150, 210, 255), life=0.9)
        elif effect == "confuse":
            # drunk in ignorance -> YOU stumble. (known, it coats the blade instead.)
            p.confused = max(p.confused, 12)
            self.log("The room tilts and will not hold still. Your own feet stop "
                     "listening to you.", (176, 120, 132))
            self.add_fx("pulse", p.x, p.y, color=(176, 120, 132), life=0.7)
        elif effect == "teleport":
            # ZEPH: unlike the random Escape, YOU choose the spot. Opens a cursor; the
            # actual jump (and the turn) happens on confirm (see teleport_to).
            self.aiming = "teleport"
            self.log("The scroll leaves a door open in the air. Choose where it "
                     "leads.", config.MANA)

    def _enter_tile(self):
        p = self.player
        t = self.level.trap_at(p.x, p.y)
        if t and not (t.sprung and t.key in ("gas", "alarm", "glyph", "dart")):
            t.trigger(self, p)

    # --- the turn engine ------------------------------------------------
    def _end_player_turn(self):
        p = self.player
        p.energy -= config.ACT_COST
        p.tick_effects(self)
        self.level.compute_fov(p.x, p.y)
        if self.dead:
            return True
        self.advance()
        self.level.compute_fov(p.x, p.y)
        return True

    def advance(self):
        """Run the world forward until the player can act again."""
        guard = 0
        while self.player.energy < config.ACT_COST and not self.dead and not self.won:
            guard += 1
            if guard > 500:
                break
            self.tick += 1
            self.codex.stats["turns"] += 1
            self.player.energy += self.player.speed()
            for m in list(self.level.monsters):
                m.energy += m.speed
            for m in list(self.level.monsters):
                inner = 0
                while (m.energy >= config.ACT_COST and m.alive and not self.dead
                       and inner < 5):
                    inner += 1
                    m.energy -= config.ACT_COST
                    m.take_turn(self)
        # a stun is measured in PLAYER turns, not monster ticks. take_turn gates the
        # reeling monster out of its AI every tick above; here -- now that the player can
        # act again -- each stun ticks down by one. this holds the stagger across a whole
        # recovery window even when a hammer has slowed the player below the monster's
        # speed (see _tick_stuns).
        self._tick_stuns()
        if self.shake_t > 0:
            self.shake_t -= 1

    def _tick_stuns(self):
        """Burn one turn off every reeling monster's stun. Called once per player turn
        (from advance and freeze_tick), so 'stunned N' means 'frozen for your next N
        turns' regardless of how fast the monster is."""
        for m in list(self.level.monsters):
            if m.stunned > 0:
                m.stunned -= 1

    def struggle_against_freeze(self):
        """The player tried to ACT while frozen. The turn is spent thrashing against
        the ice: they do not move, the floor gets its free swing, and the freeze ticks
        down by one. This is what makes the freeze cost real TURNS -- press to move,
        and instead you lose the turn and take the hit -- rather than quietly melting
        away in real time between keypresses while you sit and think.
        """
        if self.player.frozen <= 0:
            return
        self.log("You strain against the ice -- it will not give.", config.MANA)
        self.add_fx("freeze", self.player.x, self.player.y, color=(150, 210, 255),
                    life=0.4)
        self.freeze_tick()

    def freeze_tick(self):
        """One turn spent frozen: the player does nothing, the world moves, poison
        still bleeds. Called once for each turn the player burns while frozen (see
        struggle_against_freeze), so the hits land one at a time and the FROZEN count
        ticks down with each attempt to move.
        """
        p = self.player
        if p.frozen <= 0:
            return False
        p.frozen -= 1
        p.tick_effects(self)
        self.tick += 1
        self.codex.stats["turns"] += 1
        for m in list(self.level.monsters):
            m.energy += m.speed
        for m in list(self.level.monsters):
            inner = 0
            while (m.energy >= config.ACT_COST and m.alive and not self.dead
                   and inner < 5):
                inner += 1
                m.energy -= config.ACT_COST
                m.take_turn(self)
        self._tick_stuns()          # a frozen turn is still one of the player's turns
        if p.frozen == 0 and not self.dead:
            self.log("The ice lets go. You can move again.", config.MANA)
        if self.shake_t > 0:
            self.shake_t -= 1
        return p.frozen > 0

    def discover_trap(self, trap):
        """A trap has just fired where you could see it.

        THIS trap -- the one at this spot, on this floor -- is now marked on your map
        for the rest of the game. It stays marked through every death. Every OTHER
        trap in the dungeon, including every other trap of the same kind, is still
        invisible and still waiting. Knowing what a dart trap is does not tell you
        where they are. You find them one at a time, and you pay for each one.
        """
        key = trap.key
        is_new = self.codex.find_trap(self.depth, trap.x, trap.y)
        self.codex.stats["traps_by"][key] = self.codex.stats["traps_by"].get(key, 0) + 1
        if is_new:
            self.codex.save()
        if self.dead:
            return          # let the autopsy do the teaching; do not stack banners
        fact = self.codex.reveal_on_trap(key)
        if fact:
            self.learned = fact
            self.log("So that is what that was. [%s]" % fact_title(fact, self.codex), config.GOLD)
            self.codex.save()

    def on_monster_moved(self, m):
        t = self.level.trap_at(m.x, m.y)
        if t and not t.sprung and m.key != "wraith":
            t.trigger(self, m)

    # --- death ----------------------------------------------------------
    def floor_subjects(self):
        """Everything on this floor worth learning about, monsters first."""
        subs = []
        for m in self.level.monsters:
            if m.key not in subs:
                subs.append(m.key)
        for t in self.level.traps:
            if t.key not in subs:
                subs.append(t.key)
        return subs

    def leave_corpse(self):
        p = self.player
        self.codex.leave_corpse(self.depth, p.x, p.y, p.gold, p.weapon.key,
                                gift_key=p.gift, weapon_bonus=p.weapon.bonus)
        self.codex.stats["gold_lost"] += p.gold
