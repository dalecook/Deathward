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

"""Main loop and the state machine that turns a death into a lesson."""

import sys

import pygame

from . import config, render, ui
from .cheats import CheatCode
from .codex import Codex
from .keyrepeat import Repeater
from .render import Camera
from .world import World

(TITLE, PLAY, DYING, AUTOPSY, CODEX, HELP, WIN, CONFIRM_NEW, PACK,
 SEALED, TRADE, BOON, ARSENAL, TARGETING, BANISH, CHEAT_ITEMS, LOG,
 WEAPON_PICK) = range(18)
DEATH_FREEZE = 0.55

MOVES = {
    pygame.K_w: (0, -1), pygame.K_UP: (0, -1),
    pygame.K_s: (0, 1), pygame.K_DOWN: (0, 1),
    pygame.K_a: (-1, 0), pygame.K_LEFT: (-1, 0),
    pygame.K_d: (1, 0), pygame.K_RIGHT: (1, 0),
    pygame.K_q: (-1, -1), pygame.K_e: (1, -1),
    pygame.K_z: (-1, 1), pygame.K_c: (1, 1),
}
# QEZC are the roguelike diagonals. C is a MOVEMENT key and nothing else -- the
# Kodex is K. (C used to do both, and because the codex check ran first, the
# down-right diagonal simply never worked.)
NUMPAD = {
    pygame.K_KP1: (-1, 1), pygame.K_KP2: (0, 1), pygame.K_KP3: (1, 1),
    pygame.K_KP4: (-1, 0), pygame.K_KP6: (1, 0),
    pygame.K_KP7: (-1, -1), pygame.K_KP8: (0, -1), pygame.K_KP9: (1, -1),
    pygame.K_KP5: (0, 0),
}
# every key that would normally SPEND A TURN. while you are frozen, pressing any of
# these does not do the thing -- it burns a turn straining against the ice.
ACTION_KEYS = set(MOVES) | set(NUMPAD) | {
    pygame.K_SPACE, pygame.K_PERIOD, pygame.K_g,
    pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5,
    pygame.K_6, pygame.K_7, pygame.K_8, pygame.K_9,
    pygame.K_LESS, pygame.K_COMMA, pygame.K_GREATER,
    pygame.K_RETURN, pygame.K_KP_ENTER,
}


class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((config.W, config.H))
        pygame.display.set_caption("DEATHWARD")
        self.clock = pygame.time.Clock()
        self.codex = Codex()
        self.codex.load()
        self.cam = Camera()
        self.state = TITLE
        self.prev_state = TITLE
        self.world = None
        self.fact = None
        self.reveal_t = 0.0
        self.freeze_t = 0.0
        self.scroll = 0
        self.scroll_max = 0
        self.kodex_tab = 0         # which Kodex tab is showing (Monsters/Traps/...)
        self.t = 0.0
        self.repeat = Repeater()
        self.cheat = CheatCode()                              # CTRL+0987: best gear
        self.warp_cheat = CheatCode([pygame.K_7, pygame.K_8])  # CTRL+78: next floor
        self.arsenal_cheat = CheatCode([pygame.K_8, pygame.K_7])  # CTRL+87: gear picker
        self.scroll_cheat = CheatCode([pygame.K_6, pygame.K_7])   # CTRL+67: scroll picker
        self.potion_cheat = CheatCode([pygame.K_7, pygame.K_6])   # CTRL+76: potion picker
        self.weapon_cheat = CheatCode([pygame.K_1, pygame.K_2])   # CTRL+12: weapon bench
        self.magic_cheat = CheatCode([pygame.K_2, pygame.K_1])    # CTRL+21: magic-weapon bench
        self.weapon_pages = [[]]   # the weapon-bench pages (ordinary, tier 4, tier 5)
        self.weapon_page_labels = [""]
        self.weapon_page = 0
        self.weapon_picks = []     # the weapon keys offered by the current bench page
        self.arsenal = []          # the gear keys offered by the arsenal popup
        self.cheat_items = []      # the flavors offered by the scroll/potion picker
        self.cheat_items_kind = "scroll"
        self.aim = [0, 0]          # the teleport cursor while in the TARGETING state
        self.victory_gear = None     # what you were holding when the Warden fell
        # a fact learned mid-run (from a corpse, a sprung trap, or a sip). it stays
        # on screen until the player moves again -- a discovery is worth reading, and
        # nothing should snatch it away on a timer while they are still reading it.
        self.banner = None
        self.banner_age = 0.0

    # --- flow -----------------------------------------------------------
    def new_run(self, keep=None, fresh_dungeon=False):
        """A new RUN. The gear is back to basics, but the Kodex, the stone, your map
        memory and your corpses carry over. This is what a death costs you, and it is
        deliberately not everything.

        `keep` is the one slot ("weapon"/"armour"/"boots") a victor chose to carry out
        of the Deathward and back down into it. It is the only thing in this game that
        makes a run start stronger, and you have to kill the Warden to earn it.

        `fresh_dungeon` is what a victor gets instead of a respawn: the stone is
        re-cut, the map is forgotten, the traps hide again, the dead are gone. Only
        the Kodex survives. Beating the Warden does not send you round the same loop
        again -- it sends you somewhere new, with everything you have learned.
        """
        if fresh_dungeon:
            self.codex.new_dungeon()
        self.codex.runs += 1
        self.world = World(self.codex)
        if keep and self.victory_gear:
            from .items import ALL_GEAR
            key = self.victory_gear.get(keep)
            if key and key in ALL_GEAR:
                g = ALL_GEAR[key]
                if keep == "weapon" and self.victory_gear.get("weapon_bonus"):
                    g = g.copy(bonus=self.victory_gear["weapon_bonus"])
                self.world.player.equip(g)
                self.codex.see_gear(key)
                self.world.log("You kept the %s. Everything else, the dungeon took "
                               "back." % ALL_GEAR[key].name, config.GOLD)
        self.victory_gear = None
        self.banner = None
        self.banner_age = 0.0
        self.codex.save()
        self.state = PLAY

    def new_game(self):
        """A new GAME. Everything the player knows is erased first: the Kodex, the
        telemetry, the corpses, the counters. They walk back in ignorant, and the
        monsters are '?' again. Only ever called from behind a confirmation."""
        self.codex.wipe()
        self.new_run()

    def on_death(self):
        w = self.world
        cause = w.death_cause
        self.codex.record_death(cause)
        w.leave_corpse()
        self.fact = self.codex.reveal_on_death(
            cause, w.floor_subjects(), w.player.carried_flavors())
        self.codex.save()
        self.reveal_t = 0.0
        self.state = AUTOPSY

    def on_win(self):
        self.codex.wins += 1
        self.world.remember_map()
        # what you were holding when it fell. one of these you may keep.
        p = self.world.player
        self.victory_gear = {"weapon": p.weapon.key, "weapon_bonus": p.weapon.bonus,
                             "armour": p.armour.key, "boots": p.boots.key}
        self.codex.save()
        self.state = WIN

    def walk_on(self):
        """You beat it, and you would rather not leave. The Warden is dead; the floor
        is not. Clear the win flag so the world keeps turning."""
        self.world.won = False
        self.world.log("The Warden is dead. The Deathward is not.", config.DIM)
        self.state = PLAY

    def open_codex(self):
        self.prev_state = self.state
        self.scroll = 0
        self.state = CODEX

    def open_log(self):
        self.prev_state = self.state
        self.scroll = 0          # newest is at the top now, so open there
        self.state = LOG

    def open_arsenal(self):
        """CTRL+87. Offer the top three of each gear kind; the chosen one drops on an
        open tile beside you. A tester for trying high-end gear on the deep floors."""
        from .items import top_tier_gear
        picks = top_tier_gear()
        self.arsenal = ([g.key for g in picks["weapon"]]
                        + [g.key for g in picks["armour"]]
                        + [g.key for g in picks["boots"]])
        self.state = ARSENAL

    def open_weapon_cheat(self):
        """CTRL+12. The weapon bench: nine ordinary weapons plus the thirteen magical
        ones (Tasks 1-10), spread across pages of up to nine so every key 1-9 stays
        reachable. TAB cycles pages; a digit equips the base weapon on the current
        page, or hold SHIFT for its +2 masterwork. The chosen one goes straight onto
        you and your current weapon drops at your feet."""
        from .items import weapon_bench_pages
        self.weapon_pages = weapon_bench_pages()
        self.weapon_page_labels = ["Ordinary", "Magical -- Tier 4", "Magical -- Tier 5"]
        self.weapon_page = 0
        self.weapon_picks = self.weapon_pages[self.weapon_page]
        self.state = WEAPON_PICK

    def open_magic_cheat(self):
        """CTRL+21. The magic bench: the thirteen magical weapons only, split into a
        Tier 4 and a Tier 5 page (TAB switches). Like the weapon bench (CTRL+12) but
        skips the ordinary weapons. A digit equips the base; SHIFT+digit its +2."""
        from .items import weapon_bench_pages
        self.weapon_pages = weapon_bench_pages()[1:]     # drop the ordinary page
        self.weapon_page_labels = ["Magical -- Tier 4", "Magical -- Tier 5"]
        self.weapon_page = 0
        self.weapon_picks = self.weapon_pages[self.weapon_page]
        self.state = WEAPON_PICK

    def open_consumable_cheat(self, kind):
        """CTRL+67 (scrolls) / CTRL+76 (potions): pick any uncommon or rare one, and it
        goes into your pack (identified). For testing the deeper consumables."""
        from .items import CONSUMABLES
        tier_order = {"uncommon": 0, "rare": 1}
        items = [f for f, c in CONSUMABLES.items()
                 if c.kind == kind and c.tier in tier_order]
        items.sort(key=lambda f: tier_order[CONSUMABLES[f].tier])   # stable: uncommon, then rare
        self.cheat_items = items
        self.cheat_items_kind = kind
        self.state = CHEAT_ITEMS

    # --- input ----------------------------------------------------------
    def handle(self, e):
        if e.type == pygame.QUIT:
            self.quit()
        if e.type != pygame.KEYDOWN:
            return
        k = e.key
        mods = pygame.key.get_mods()
        shift = mods & pygame.KMOD_SHIFT

        if self.state == TITLE:
            if k in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.new_run()               # CONTINUE: keeps the kodex and the dead
            elif k == pygame.K_n:
                if self.codex.has_progress():
                    self.state = CONFIRM_NEW  # erasing it all is never one keystroke
                else:
                    self.new_game()           # nothing to lose
            elif k == pygame.K_k:
                self.open_codex()
            elif k in (pygame.K_SLASH, pygame.K_QUESTION, pygame.K_h):
                self.prev_state = TITLE
                self.state = HELP
            elif k == pygame.K_ESCAPE:
                self.quit()
            return

        if self.state == CONFIRM_NEW:
            if k == pygame.K_y:
                self.new_game()
            elif k in (pygame.K_n, pygame.K_ESCAPE):
                self.state = TITLE
            return

        if self.state == HELP:
            self.state = self.prev_state
            return

        if self.state == SEALED:
            self.state = PLAY
            return

        if self.state == TRADE:
            if k == pygame.K_ESCAPE:
                self.world.trading = False
                self.state = PLAY
            elif pygame.K_1 <= k <= pygame.K_9:
                idx = k - pygame.K_1
                if shift:
                    self.world.sell(idx)      # SHIFT + slot: it takes it off you
                else:
                    self.world.buy(idx)
            return

        if self.state == BANISH:
            w = self.world
            if k == pygame.K_ESCAPE:
                w.cancel_banish()       # keep the scroll -- but now you know what it is
                self.state = PLAY
            elif pygame.K_1 <= k <= pygame.K_9:
                idx = k - pygame.K_1
                types = w.banishable_types()
                if idx < len(types):
                    w.banish_type(types[idx][0])
                    self.state = PLAY
            return

        if self.state == TARGETING:
            w = self.world
            if k == pygame.K_ESCAPE:
                w.cancel_aim()
                self.state = PLAY
            elif k in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                if w.teleport_to(self.aim[0], self.aim[1]):
                    self.state = PLAY
                # otherwise the spot is no good -- stay in targeting
            else:
                step = MOVES.get(k) or NUMPAD.get(k)
                if step and step != (0, 0):
                    nx = max(0, min(w.level.w - 1, self.aim[0] + step[0]))
                    ny = max(0, min(w.level.h - 1, self.aim[1] + step[1]))
                    self.aim = [nx, ny]
            return

        if self.state == ARSENAL:
            if k == pygame.K_ESCAPE:
                self.state = PLAY
            elif pygame.K_1 <= k <= pygame.K_9:
                idx = k - pygame.K_1
                if idx < len(self.arsenal):
                    self.world.drop_gear_near(self.arsenal[idx])
                    self.state = PLAY
            return

        if self.state == WEAPON_PICK:
            if k == pygame.K_ESCAPE:
                self.state = PLAY
            elif k == pygame.K_TAB:
                self.weapon_page = (self.weapon_page + 1) % len(self.weapon_pages)
                self.weapon_picks = self.weapon_pages[self.weapon_page]
            elif pygame.K_1 <= k <= pygame.K_9:
                idx = k - pygame.K_1
                if idx < len(self.weapon_picks):
                    self.world.cheat_equip_weapon(self.weapon_picks[idx],
                                                  2 if shift else 0)
                    self.state = PLAY
            return

        if self.state == CHEAT_ITEMS:
            if k == pygame.K_ESCAPE:
                self.state = PLAY
            else:
                # 1-9 are the first nine; 0 is the tenth
                idx = k - pygame.K_1 if pygame.K_1 <= k <= pygame.K_9 else (
                    9 if k == pygame.K_0 else None)
                if idx is not None and idx < len(self.cheat_items):
                    self.world.cheat_give_consumable(self.cheat_items[idx])
                    self.state = PLAY
            return

        if self.state == PACK:
            if k in (pygame.K_ESCAPE, pygame.K_i, pygame.K_TAB):
                self.state = PLAY
            elif pygame.K_1 <= k <= pygame.K_6:
                # a whole stack costs the same one turn as a single item, so making
                # room is never punished by the turn economy
                if self.world.drop_item(k - pygame.K_1, whole=bool(shift)):
                    if self.world.dead:
                        self.freeze_t = DEATH_FREEZE
                        self.state = DYING
            return

        if self.state == CODEX:
            from .codex import KODEX_TABS
            if k in (pygame.K_ESCAPE, pygame.K_k):
                self.state = self.prev_state
            elif k == pygame.K_DOWN:
                self.scroll = min(self.scroll_max, self.scroll + 46)
            elif k == pygame.K_UP:
                self.scroll = max(0, self.scroll - 46)
            elif k == pygame.K_PAGEDOWN:
                self.scroll = min(self.scroll_max, self.scroll + 320)
            elif k == pygame.K_PAGEUP:
                self.scroll = max(0, self.scroll - 320)
            elif k == pygame.K_LEFT:
                self.kodex_tab = (self.kodex_tab - 1) % len(KODEX_TABS)
                self.scroll = 0
            elif k == pygame.K_RIGHT:
                self.kodex_tab = (self.kodex_tab + 1) % len(KODEX_TABS)
                self.scroll = 0
            elif pygame.K_1 <= k <= pygame.K_6:
                self.kodex_tab = k - pygame.K_1
                self.scroll = 0
            return

        if self.state == LOG:
            if k in (pygame.K_ESCAPE, pygame.K_l):
                self.state = self.prev_state
            elif k == pygame.K_DOWN:
                self.scroll = min(self.scroll_max, self.scroll + 44)
            elif k == pygame.K_UP:
                self.scroll = max(0, self.scroll - 44)
            elif k == pygame.K_PAGEDOWN:
                self.scroll = min(self.scroll_max, self.scroll + 300)
            elif k == pygame.K_PAGEUP:
                self.scroll = max(0, self.scroll - 300)
            return

        if self.state == AUTOPSY:
            if k in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                if self.reveal_t * 95 < len(self.fact.text):
                    self.reveal_t = 99.0        # first press finishes the typewriter
                else:
                    self.new_run()
            elif k == pygame.K_k:
                self.open_codex()
            elif k == pygame.K_ESCAPE:
                self.state = TITLE
            return

        if self.state == WIN:
            if k == pygame.K_k:
                self.open_codex()
            elif k == pygame.K_s:
                self.state = BOON          # start over, and choose your keepsake
            elif k == pygame.K_w:
                self.walk_on()             # stay in the dungeon
            elif k == pygame.K_ESCAPE:
                self.state = TITLE
            return

        if self.state == BOON:
            pick = {pygame.K_1: "weapon", pygame.K_2: "armour",
                    pygame.K_3: "boots"}.get(k)
            if pick:
                # a victor does not respawn. they go somewhere else entirely.
                self.new_run(keep=pick, fresh_dungeon=True)
            elif k == pygame.K_ESCAPE:
                self.state = WIN
            return

        if self.state != PLAY:
            return

        # --- in the dungeon ---------------------------------------------
        w = self.world

        # frozen solid. reading the Kodex or the help card costs no turn, so those still
        # work, alongside the escape hatch to the title menu. everything else is denied:
        # any real ACTION -- a step, a swing, a wait, a sip, a scroll -- is eaten by the
        # ice (you lose the turn, the floor gets a free swing, the freeze ticks down),
        # and you cannot even open the pack to drink or drop -- frozen hands do neither.
        # (Your pack is already listed on the HUD, so you lose nothing by looking.)
        if w.player.frozen > 0:
            if k == pygame.K_ESCAPE:
                w.remember_map()
                self.codex.save()
                self.state = TITLE
            elif k == pygame.K_k and not shift:
                self.open_codex()
            elif k == pygame.K_l and not shift:
                self.open_log()
            elif k in (pygame.K_SLASH, pygame.K_QUESTION):
                self.prev_state = PLAY
                self.state = HELP
            elif k in ACTION_KEYS:
                self.dismiss_banner()
                w.struggle_against_freeze()
                if w.dead:
                    self.freeze_t = DEATH_FREEZE
                    self.state = DYING
            return

        # The CTRL codes (CMD on a Mac). Checked BEFORE the digit bindings, or the
        # digits would be swallowed by the loot menu on the way past. Every held key
        # feeds ALL codes; when one completes, the others are reset so a shared digit
        # cannot leak a stray trigger. Gear (0987) is first, so its trailing "87"
        # completes the gear code, not the arsenal one.
        held = bool(mods & (pygame.KMOD_CTRL | pygame.KMOD_META))
        cheats = [
            (self.cheat, lambda: w.grant_cheat()),                     # 0987 best gear
            (self.warp_cheat, lambda: w.warp_down()),                  # 78   next floor
            (self.arsenal_cheat, lambda: self.open_arsenal()),         # 87   gear picker
            (self.scroll_cheat, lambda: self.open_consumable_cheat("scroll")),  # 67
            (self.potion_cheat, lambda: self.open_consumable_cheat("potion")),  # 76
            (self.weapon_cheat, lambda: self.open_weapon_cheat()),     # 12   weapon bench
            (self.magic_cheat, lambda: self.open_magic_cheat()),       # 21   magic bench
        ]
        if held or any(c.progress for c, _ in cheats):
            done = [c.feed(k, held) for c, _ in cheats]
            for i, ok in enumerate(done):
                if ok:
                    for j, (c, _) in enumerate(cheats):
                        if j != i:
                            c.reset()
                    cheats[i][1]()
                    return
            if held:
                return          # CTRL is not bound to anything else; swallow it

        if k == pygame.K_ESCAPE:
            w.remember_map()
            self.codex.save()
            self.state = TITLE
            return
        if k in (pygame.K_SLASH, pygame.K_QUESTION):
            self.prev_state = PLAY
            self.state = HELP
            return
        if k == pygame.K_k and not shift:
            self.open_codex()
            return
        if k == pygame.K_l and not shift:
            self.open_log()
            return
        if k in (pygame.K_i, pygame.K_TAB):
            self.state = PACK
            return

        acted = False
        if k in NUMPAD:
            dx, dy = NUMPAD[k]
            if (dx, dy) == (0, 0):
                acted = w.player_wait()
            else:
                self.dismiss_banner()
                acted = w.player_move(dx, dy)
                self.repeat.start(k, self.t)
        elif k in MOVES:
            dx, dy = MOVES[k]
            self.dismiss_banner()
            if shift:
                acted = w.player_blink(dx, dy)   # a leap is never auto-repeated
            else:
                acted = w.player_move(dx, dy)
                self.repeat.start(k, self.t)
        elif k in (pygame.K_SPACE, pygame.K_PERIOD):
            acted = w.player_wait()
        elif k == pygame.K_g:
            acted = w.player_pickup()
        elif pygame.K_1 <= k <= pygame.K_9:
            # while you are standing on loot, the numbers are the loot menu -- one
            # number, one thing. 'all' is G, never a number. the moment you step off
            # the loot, the numbers are your pack again.
            idx = k - pygame.K_1
            opts = w.loot_options()
            if opts:
                if idx < len(opts):
                    acted = w.take_option(idx)
            else:
                acted = w.use_item(idx)
        elif k in (pygame.K_LESS, pygame.K_COMMA):
            acted = self._go_up()
        elif k in (pygame.K_GREATER, pygame.K_PERIOD) and shift:
            acted = w.descend()
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_GREATER):
            # ENTER is context-sensitive: it takes whichever staircase you are on
            if (w.player.x, w.player.y) == w.level.entrance and w.depth > 1:
                acted = self._go_up()
            elif (w.player.x, w.player.y) == w.level.entrance and w.depth == 1:
                self.state = SEALED
                return
            else:
                acted = w.descend()

        if w.aiming == "teleport":
            self.aim = [w.player.x, w.player.y]   # a scroll opened a targeting cursor
            self.state = TARGETING
        elif w.aiming == "banish":
            self.state = BANISH
        elif w.trading:
            self.state = TRADE          # you walked into it; it opened its hands
        elif w.won:
            self.on_win()
        elif w.dead:
            self.freeze_t = DEATH_FREEZE
            self.state = DYING

    def quit(self):
        if self.world is not None:
            self.world.remember_map()
        self.codex.save()
        pygame.quit()
        sys.exit(0)

    def _go_up(self):
        """Climb. If we are standing at the gate on floor 1, the dungeon says no."""
        r = self.world.ascend()
        if r == "sealed":
            self.state = SEALED
            return False
        return bool(r)

    def dismiss_banner(self):
        """Cleared by MOVING, and by nothing else. Called before the move is made, so
        a step that itself uncovers something new still shows the new card."""
        self.banner = None
        self.banner_age = 0.0

    # --- hold-to-walk ----------------------------------------------------
    def walk_step(self, dx, dy):
        """One step of an auto-walk. Returns False if the walk should stop.

        Holding a key must never be able to kill you. An auto-walk therefore
        refuses to throw a punch -- if the next tile has something in it, the walk
        stops and you attack deliberately, with a keypress -- and it aborts the
        instant you take damage, so you cannot hold W straight through a spike pit
        and into a brute.
        """
        w = self.world
        if w.dead or w.won:
            return False
        p = w.player
        nx, ny = p.x + dx, p.y + dy
        if w.monster_at(nx, ny):
            return False                     # walk up to it, do not swing at it
        if not w.walkable(nx, ny):
            return False                     # a wall stops the walk
        hp_before = p.hp
        w.player_move(dx, dy)
        if p.hp < hp_before or w.dead:
            return False                     # something hurt you: stop walking
        return True

    def pump_repeat(self):
        if self.state != PLAY:
            self.repeat.stop()
            return
        if self.world is not None and self.world.player.frozen > 0:
            self.repeat.stop()          # a held key cannot walk you out of the ice
            return
        held = pygame.key.get_pressed()
        mods = pygame.key.get_mods()
        if mods & pygame.KMOD_SHIFT:
            self.repeat.stop()
            return
        key = self.repeat.poll(self.t, lambda k: bool(held[k]))
        if key is None:
            return
        dx, dy = MOVES.get(key) or NUMPAD.get(key, (0, 0))
        self.dismiss_banner()          # walking on dismisses the card, same as a step
        if (dx, dy) == (0, 0) or not self.walk_step(dx, dy):
            self.repeat.stop()
            return
        if self.world.won:
            self.on_win()
        elif self.world.dead:
            self.freeze_t = DEATH_FREEZE
            self.state = DYING

    # --- loop -----------------------------------------------------------
    def run(self):
        while True:
            dt = min(0.05, self.clock.tick(config.FPS) / 1000.0)
            self.t += dt
            for e in pygame.event.get():
                self.handle(e)

            self.pump_repeat()

            # fire burns in real time even though the dungeon thinks in turns
            if self.world is not None:
                self.world.tick_fx(dt)

            # a discovery made mid-run announces itself, and then WAITS
            if self.world is not None and self.world.learned is not None:
                self.banner = self.world.learned
                self.banner_age = 0.0
                self.world.learned = None
            if self.banner is not None:
                self.banner_age += dt

            if self.state == DYING:
                self.freeze_t -= dt
                if self.freeze_t <= 0:
                    self.on_death()
            elif self.state == AUTOPSY:
                self.reveal_t += dt

            self.draw()
            pygame.display.flip()

    def draw(self):
        if self.state == TITLE:
            ui.draw_title(self.screen, self.codex, self.t)
        elif self.state == CONFIRM_NEW:
            ui.draw_title(self.screen, self.codex, self.t)
            ui.draw_confirm_new(self.screen, self.codex, self.t)
        elif self.state == PACK:
            self._draw_dungeon()
            ui.draw_pack(self.screen, self.world, self.codex)
        elif self.state == ARSENAL:
            self._draw_dungeon()
            ui.draw_arsenal(self.screen, self.arsenal, self.t)
        elif self.state == WEAPON_PICK:
            self._draw_dungeon()
            ui.draw_weapon_cheat(self.screen, self.weapon_picks, self.t,
                                 self.weapon_page_labels[self.weapon_page])
        elif self.state == BANISH:
            self._draw_dungeon()
            ui.draw_banish(self.screen, self.world.banishable_types(), self.codex,
                           self.t)
        elif self.state == CHEAT_ITEMS:
            self._draw_dungeon()
            ui.draw_consumable_cheat(self.screen, self.cheat_items,
                                     self.cheat_items_kind, self.t, self.codex)
        elif self.state == TARGETING:
            self.cam.center_on(self.aim[0], self.aim[1])   # follow the cursor, not you
            render.draw_world(self.screen, self.world, self.codex, self.cam, self.t)
            ui.draw_log_line(self.screen, self.world)
            ui.draw_hud(self.screen, self.world, self.codex)
            ok = self.world.valid_teleport(self.aim[0], self.aim[1])
            render.draw_aim_cursor(self.screen, self.world, self.cam, self.aim, ok,
                                   self.t)
            ui.draw_aim_hint(self.screen, ok)
        elif self.state == SEALED:
            self._draw_dungeon()
            ui.draw_sealed(self.screen, self.t)
        elif self.state == TRADE:
            self._draw_dungeon()
            ui.draw_trade(self.screen, self.world, self.codex, self.t)
        elif self.state == CODEX:
            self.scroll_max = ui.draw_codex(self.screen, self.codex, self.scroll,
                                            self.t, self.kodex_tab)
        elif self.state == LOG:
            self._draw_dungeon()
            self.scroll_max = ui.draw_log(self.screen, self.world.messages,
                                          self.scroll, self.t)
        elif self.state == WIN:
            ui.draw_win(self.screen, self.codex, self.world, self.t)
        elif self.state == BOON:
            ui.draw_win(self.screen, self.codex, self.world, self.t)
            ui.draw_boon(self.screen, self.victory_gear, self.t)
        elif self.state == HELP:
            if self.world:
                self._draw_dungeon()
            else:
                self.screen.fill(config.BG)
            ui.draw_help(self.screen)
        else:
            self._draw_dungeon()
            if self.state == AUTOPSY:
                ui.draw_autopsy(self.screen, self.world, self.codex, self.fact,
                                self.world.death_cause, self.reveal_t)

    def _draw_dungeon(self):
        self.cam.center_on(self.world.player.x, self.world.player.y)
        render.draw_world(self.screen, self.world, self.codex, self.cam, self.t)
        ui.draw_log_line(self.screen, self.world)
        ui.draw_hud(self.screen, self.world, self.codex)
        if self.state == PLAY:
            ui.draw_loot_panel(self.screen, self.world, self.codex)
        if self.state == PLAY and self.banner is not None:
            ui.draw_learned_banner(self.screen, self.banner, self.banner_age,
                                   self.codex)


def main():
    Game().run()
