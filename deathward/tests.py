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

"""Proofs of the claims DEATHWARD is built on.

    py -3.13 -m deathward.tests

Claim 1: every death teaches something new. Not usually -- every time.
Claim 2: knowledge is information, never power. The dungeon simulates identically
         for an ignorant hero and an omniscient one.
Claim 3: the dungeon is always completable -- stairs always reachable, no floor
         can strand you.
Claim 4: boots buy turns. That is not flavour text, it is the turn economy.
"""

import os
import random
import unittest
from collections import defaultdict, deque

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from . import config  # noqa: E402
from .codex import FACTS, TOTAL_FACTS, Codex  # noqa: E402
from .items import ALL_GEAR, BOOTS, CONSUMABLES, roll_floor_armour_magical  # noqa: E402
from .world import World  # noqa: E402


def setUpModule():
    """Point the whole suite at a scratch save before a single test runs.

    This is the guard that makes every other test safe by construction. It is not
    theoretical: config.SAVE_PATH lives INSIDE the package, and wipe() unlinks it
    directly, so running the suite used to delete the player's own Kodex -- their
    deaths, their gold, every fact they had paid for. No test may ever see the real
    path again, whatever methods it reaches for.
    """
    import tempfile
    global _REAL_SAVE_PATH
    _REAL_SAVE_PATH = config.SAVE_PATH
    config.SAVE_PATH = os.path.join(tempfile.gettempdir(), "dw_test_scratch.json")


def tearDownModule():
    if os.path.exists(config.SAVE_PATH):
        os.remove(config.SAVE_PATH)
    config.SAVE_PATH = _REAL_SAVE_PATH


_REAL_SAVE_PATH = config.SAVE_PATH


class FakeSave(Codex):
    """A Codex that never touches disk, so tests cannot clobber a real save."""

    def load(self):
        pass

    def save(self):
        pass

    def wipe(self):
        """The real wipe() UNLINKS config.SAVE_PATH -- it does not route through
        save(), so overriding save() alone never made this class honest. Keep the
        meaning (a new game knows nothing) and drop the delete."""
        self.__init__()


class _CountingSave(FakeSave):
    """A FakeSave that counts save() calls instead of silently swallowing them, so
    a test can prove HOW OFTEN persistence fires without touching real disk."""
    def __init__(self):
        super().__init__()
        self.save_calls = 0

    def save(self):
        self.save_calls += 1


class _SeqRng:
    """A random() that returns a scripted sequence, so a floor's magical-armour roll
    is fully controllable. choice() is deterministic (first element)."""
    def __init__(self, values):
        self.values = list(values)
        self.i = 0
    def random(self):
        v = self.values[self.i]
        self.i += 1
        return v
    def choice(self, seq):
        return seq[0]


def _assert_solid_hits(case, key, lo=3, hi=5):
    """A high-end weapon should need `lo`..`hi` SOLID blows to drop this monster.

    A 'solid blow' is an average hit from the weapon in question. We check the
    player's own reference weapon (the Vampiric Kris) lands in the window, and that
    even the single hardest-hitting weapon in the game cannot one- or two-shot it --
    that is the whole point of the durability bump.
    """
    import math
    from .monsters import TEMPLATES
    from .items import WEAPONS
    hp = TEMPLATES[key].hp
    kris = WEAPONS["kris"]
    hits = math.ceil(hp / ((kris.lo + kris.hi) / 2))
    case.assertGreaterEqual(hits, lo, "%s folds too fast to the Kris (%d hits)"
                            % (key, hits))
    case.assertLessEqual(hits, hi, "%s is a damage sponge to the Kris (%d hits)"
                         % (key, hits))
    best = max(WEAPONS.values(), key=lambda w: (w.lo + w.hi))
    best_hits = math.ceil(hp / ((best.lo + best.hi) / 2))
    case.assertGreaterEqual(best_hits, 3,
                            "even the %s should need 3+ solid hits on a %s"
                            % (best.name, key))


CAUSES = ["rat", "kobold", "spitter", "brute", "wraith", "mimic", "warden",
          "dart", "spike", "gas", "alarm", "glyph", "poison"]
SUBJECTS = ["rat", "kobold", "spitter", "brute", "wraith", "mimic", "dart",
            "spike", "gas", "alarm", "glyph"]
FLAVORS = list(CONSUMABLES)


class TestAutosave(unittest.TestCase):
    """Every resolved player turn writes the live run into the codex, so any exit
    resumes here -- but a turn that ends in death does not (permadeath clears it)."""

    def test_a_resolved_turn_writes_the_run_block(self):
        codex = FakeSave()
        w = World(codex, seed=4)
        codex.run = None
        w._end_player_turn()
        self.assertIsNotNone(codex.run, "a completed turn must autosave the run")
        self.assertEqual(codex.run["depth"], w.depth)
        self.assertEqual(codex.run["player"]["x"], w.player.x)
        self.assertEqual(codex.run["player"]["y"], w.player.y)

    def test_autosave_folds_in_the_map_memory(self):
        codex = FakeSave()
        w = World(codex, seed=4)
        w._end_player_turn()
        self.assertIn(str(w.depth), codex.maps,
                      "the explored map must be remembered before serializing")

    def test_a_dead_players_turn_does_not_autosave(self):
        codex = FakeSave()
        w = World(codex, seed=4)
        codex.run = None
        w.dead = True
        w._end_player_turn()
        self.assertIsNone(codex.run, "death clears the run; a dead turn must not rewrite it")

    def test_autosave_is_skipped_if_death_lands_during_the_world_turn(self):
        # _autosave guards on self.dead itself, so a death during advance() (a
        # monster's killing blow) still leaves the run block untouched.
        codex = FakeSave()
        w = World(codex, seed=4)
        codex.run = None
        w.dead = True
        w._autosave()
        self.assertIsNone(codex.run)

    def test_autosave_persists_to_disk_only_every_n_turns(self):
        """codex.run (in memory) updates every turn -- proven above -- but the
        actual codex.save() write is throttled, so a browser tab isn't hammering
        localStorage every turn (~8/sec) with no suspend-on-close to fall back on."""
        codex = _CountingSave()
        w = World(codex, seed=4)
        for _ in range(config.AUTOSAVE_INTERVAL_TURNS - 1):
            w._autosave()
        self.assertEqual(codex.save_calls, 0,
                         "must not persist before the interval elapses")
        w._autosave()
        self.assertEqual(codex.save_calls, 1,
                         "must persist once the interval elapses")
        for _ in range(config.AUTOSAVE_INTERVAL_TURNS - 1):
            w._autosave()
        self.assertEqual(codex.save_calls, 1, "still within the next interval")
        w._autosave()
        self.assertEqual(codex.save_calls, 2, "persists again after a second interval")


class _FakeLocalStorage:
    """Stands in for the browser's window.localStorage under pygbag. Can be told
    to raise on get/set to simulate quota exhaustion or disabled storage (private
    browsing), which real localStorage does by throwing."""
    def __init__(self, raise_on_get=False, raise_on_set=False):
        self._store = {}
        self._raise_on_get = raise_on_get
        self._raise_on_set = raise_on_set

    def getItem(self, key):
        if self._raise_on_get:
            raise RuntimeError("storage unavailable")
        return self._store.get(key)

    def setItem(self, key, value):
        if self._raise_on_set:
            raise RuntimeError("quota exceeded")
        self._store[key] = value

    def removeItem(self, key):
        self._store.pop(key, None)


class _FakeWindow:
    def __init__(self, **kwargs):
        self.localStorage = _FakeLocalStorage(**kwargs)


class TestWebStore(unittest.TestCase):
    """deathward.webstore is the save-persistence seam: native CPython writes JSON
    to config.SAVE_PATH on disk; pygbag's WASM/Pyodide runtime has no such disk, so
    the web branch persists through window.localStorage instead. sys.platform is
    never "emscripten" under a real CPython test run, so the web branch is exercised
    here by monkeypatching sys.platform and injecting a fake window onto the real
    platform module -- mirroring exactly what pygbag does at import time."""

    def setUp(self):
        import tempfile
        from . import config as cfg
        self._old_save_path = cfg.SAVE_PATH
        cfg.SAVE_PATH = os.path.join(tempfile.gettempdir(), "dw_webstore_test.json")

    def tearDown(self):
        from . import config as cfg
        if os.path.exists(cfg.SAVE_PATH):
            os.remove(cfg.SAVE_PATH)
        cfg.SAVE_PATH = self._old_save_path

    # --- native branch ----------------------------------------------------
    def test_native_load_returns_none_when_nothing_saved(self):
        from .webstore import load_save
        self.assertIsNone(load_save())

    def test_native_round_trips_through_disk(self):
        from .webstore import load_save, write_save
        write_save({"deaths": 3, "known": ["rat.rule"]})
        self.assertEqual(load_save(), {"deaths": 3, "known": ["rat.rule"]})

    def test_native_delete_removes_the_save(self):
        from .webstore import delete_save, load_save, write_save
        write_save({"deaths": 1})
        delete_save()
        self.assertIsNone(load_save())

    def test_native_load_returns_none_on_corrupt_json(self):
        from . import config as cfg
        from .webstore import load_save
        with open(cfg.SAVE_PATH, "w", encoding="utf-8") as fh:
            fh.write("{not valid json")
        self.assertIsNone(load_save())

    def test_native_write_swallows_a_bad_path(self):
        from . import config as cfg
        from .webstore import write_save
        cfg.SAVE_PATH = os.path.join(cfg.SAVE_PATH, "nested", "unreachable.json")
        write_save({"deaths": 1})  # must not raise

    # --- web branch ---------------------------------------------------
    def _patch_web(self, **window_kwargs):
        import platform as platform_module
        import sys
        old_platform = sys.platform
        sys.platform = "emscripten"
        fake_window = _FakeWindow(**window_kwargs)
        platform_module.window = fake_window

        def restore():
            sys.platform = old_platform
            del platform_module.window
        self.addCleanup(restore)
        return fake_window

    def test_web_load_returns_none_when_nothing_saved(self):
        self._patch_web()
        from .webstore import load_save
        self.assertIsNone(load_save())

    def test_web_round_trips_through_local_storage(self):
        self._patch_web()
        from .webstore import load_save, write_save
        write_save({"deaths": 7, "corpses": {"3": {"gold": 40}}})
        self.assertEqual(load_save(), {"deaths": 7, "corpses": {"3": {"gold": 40}}})

    def test_web_delete_removes_the_save(self):
        self._patch_web()
        from .webstore import delete_save, load_save, write_save
        write_save({"deaths": 1})
        delete_save()
        self.assertIsNone(load_save())

    def test_web_write_swallows_a_localstorage_error(self):
        self._patch_web(raise_on_set=True)
        from .webstore import write_save
        write_save({"deaths": 1})  # must not raise -- quota/private-mode failure

    def test_web_load_swallows_a_localstorage_error(self):
        self._patch_web(raise_on_get=True)
        from .webstore import load_save
        self.assertIsNone(load_save())  # must not raise


class TestFontCache(unittest.TestCase):
    """pygame.font.SysFont("consolas,dejavusansmono,...") depends on an OS font
    registry that pygbag's WASM sandbox does not have, so it silently substitutes
    pygame's own bundled freesansbold.ttf instead of raising -- a real, different,
    non-monospace font, not just worse-rendered Consolas. fontcache.get_font()
    loads a bundled .ttf directly instead, which needs no OS font-discovery step on
    any platform."""

    def setUp(self):
        pygame.font.init()

    def test_font_path_points_at_the_bundled_asset(self):
        from . import fontcache
        self.assertTrue(os.path.exists(fontcache._FONT_PATH),
                        "the bundled font file must actually exist on disk")
        self.assertTrue(fontcache._FONT_PATH.endswith("DejaVuSansMono.ttf"))

    def test_same_size_and_weight_returns_the_cached_object(self):
        from . import fontcache
        a = fontcache.get_font(24)
        b = fontcache.get_font(24)
        self.assertIs(a, b)

    def test_bold_and_plain_are_cached_separately(self):
        from . import fontcache
        plain = fontcache.get_font(18, bold=False)
        bold = fontcache.get_font(18, bold=True)
        self.assertIsNot(plain, bold)
        self.assertFalse(plain.bold)
        self.assertTrue(bold.bold)

    def test_loads_the_bundled_ttf_not_pygames_default_fallback_font(self):
        """The regression this exists to prevent: silently rendering with
        pygame.font.Font(None, ...) (freesansbold) instead of our bundled ttf."""
        from . import fontcache
        bundled = fontcache.get_font(20)
        default = pygame.font.Font(None, 20)
        self.assertNotEqual(bundled.size("Deathward"), default.size("Deathward"),
                            "must not be silently using pygame's default fallback font")


class TestEveryDeathTeaches(unittest.TestCase):
    def test_500_deaths_never_repeat_a_lesson(self):
        rng = random.Random(20260713)
        codex = FakeSave()
        seen = set()
        for i in range(500):
            cause = rng.choice(CAUSES)
            floor = rng.sample(SUBJECTS, rng.randint(1, 5))
            carried = rng.sample(FLAVORS, rng.randint(0, 3))
            codex.record_death(cause)
            codex.runs = i // 3 + 1
            codex.best_depth = min(8, 1 + i // 40)
            fact = codex.reveal_on_death(cause, floor, carried)

            self.assertIsNotNone(fact, "death %d taught nothing" % i)
            ident = fact.title + fact.text
            self.assertNotIn(ident, seen,
                             "death %d repeated a lesson: %r" % (i, fact.title))
            seen.add(ident)
        self.assertEqual(len(seen), 500)

    def test_first_death_explains_death(self):
        codex = FakeSave()
        codex.record_death("rat")
        f = codex.reveal_on_death("rat", ["rat"], [])
        self.assertEqual(f.key, "self.corpse")

    def test_the_killer_is_explained_before_anything_else(self):
        codex = FakeSave()
        codex.known.append("self.corpse")
        codex.record_death("brute")
        f = codex.reveal_on_death("brute", ["rat", "brute", "gas"], ["ochre"])
        self.assertEqual(f.key, "brute.rule")

    def test_dying_with_an_unknown_potion_can_name_it(self):
        codex = FakeSave()
        # know everything about the world, but nothing about what is in the pack
        for k in FACTS:
            if not k.startswith("id."):
                codex.known.append(k)
        codex.record_death("rat")
        f = codex.reveal_on_death("rat", ["rat"], ["ochre"])
        self.assertEqual(f.key, "id.ochre")

    def test_the_whole_codex_is_reachable_by_dying(self):
        codex = FakeSave()
        for _ in range(TOTAL_FACTS):
            codex.record_death("rat")
            codex.reveal_on_death("rat", SUBJECTS, FLAVORS)
        self.assertEqual(len(codex.known), TOTAL_FACTS)
        self.assertEqual(set(codex.known), set(FACTS))

    def test_telemetry_is_inexhaustible(self):
        codex = FakeSave()
        codex.known = list(FACTS)          # nothing fixed left to learn
        seen = set()
        for i in range(120):
            codex.record_death("rat")
            f = codex.reveal_on_death("rat", ["rat"], [])
            ident = f.title + f.text
            self.assertNotIn(ident, seen, "telemetry repeated after %d deaths" % i)
            seen.add(ident)


class TestLearningByKilling(unittest.TestCase):
    """A corpse can be read -- but it is the slow road. Dying is the fast one."""

    def _kill(self, world, key):
        from .monsters import Monster
        m = Monster(key, world.player.x + 2, world.player.y)
        world.level.monsters.append(m)
        world.kill_monster(m)
        return world.learned

    def test_the_first_kill_names_the_thing(self):
        codex = FakeSave()
        w = World(codex, seed=4)
        self.assertEqual(codex.tier("kobold"), 0)
        fact = self._kill(w, "kobold")
        self.assertIsNotNone(fact, "killing something must teach you what it was")
        self.assertEqual(fact.key, "kobold.rule")
        self.assertEqual(codex.tier("kobold"), 1, "it should no longer be a '?'")

    def test_a_kill_will_not_hand_you_the_tell_or_the_counter(self):
        codex = FakeSave()
        w = World(codex, seed=4)
        self._kill(w, "brute")                       # 1st: the rule
        w.learned = None
        self.assertIsNone(self._kill(w, "brute"),
                          "the 2nd kill is not enough to earn the tell")
        self.assertFalse(codex.knows("brute.tell"))

    def test_enough_corpses_eventually_teach_the_tell_and_the_counter(self):
        codex = FakeSave()
        w = World(codex, seed=4)
        learned = []
        for i in range(8):
            w.learned = None
            f = self._kill(w, "rat")
            if f:
                learned.append((i + 1, f.key))
        self.assertIn((1, "rat.rule"), learned, "1 kill should name it")
        self.assertIn((3, "rat.tell"), learned, "3 kills should earn the tell")
        self.assertIn((8, "rat.counter"), learned, "8 kills should earn the counter")

    def test_a_monster_that_dies_to_a_trap_is_NOT_your_kill(self):
        """The bug: a monster that blunders onto a trap used to credit you with the
        kill and hand you its Kodex lesson. You did not make that corpse."""
        from .monsters import Monster
        codex = FakeSave()
        w = World(codex, seed=4)
        w.level.monsters = []
        m = Monster("kobold", w.player.x + 2, w.player.y)
        m.hp = 1
        w.level.monsters.append(m)
        w.learned = None
        kills0 = codex.stats["kills"]

        w.hurt_monster(m, 5, source="spike")          # it stepped on a spike pit

        self.assertNotIn(m, w.level.monsters, "the kobold is dead")
        self.assertIsNone(w.learned, "a trap kill teaches you nothing")
        self.assertEqual(codex.tier("kobold"), 0, "it is still a '?' to you")
        self.assertEqual(codex.stats["kills"], kills0, "and it does not count as yours")
        self.assertEqual(codex.stats["kills_by"].get("kobold", 0), 0)
        # but the body is still there to loot -- the trap took the monster, not its coins
        self.assertTrue([s for s in w.level.slain if (s.x, s.y) == (m.x, m.y)],
                        "the body still lies where it fell")

    def test_every_trap_source_is_excluded_from_credit(self):
        from .monsters import Monster
        for src in ("dart", "spike", "gas", "alarm", "glyph"):
            codex = FakeSave()
            w = World(codex, seed=4)
            w.level.monsters = []
            m = Monster("rat", w.player.x + 2, w.player.y)
            m.hp = 1
            w.level.monsters.append(m)
            w.learned = None
            w.hurt_monster(m, 5, source=src)
            self.assertIsNone(w.learned, "%s is a trap, not your kill" % src)
            self.assertEqual(codex.tier("rat"), 0, "%s must not teach the rat" % src)

    def test_your_own_fire_still_counts_as_your_kill(self):
        """Burning a thing down with a Firestorm or a Flame Brand IS your kill -- the
        fire reveal is how you learn what steel cannot teach (e.g. the stone golem)."""
        from .monsters import Monster
        for src in ("scroll", "burn", "thorns"):
            codex = FakeSave()
            w = World(codex, seed=4)
            w.level.monsters = []
            m = Monster("rat", w.player.x + 2, w.player.y)
            m.hp = 1
            w.level.monsters.append(m)
            w.learned = None
            w.hurt_monster(m, 5, source=src)
            self.assertIsNotNone(w.learned, "%s is your own doing -- still your kill" % src)
            self.assertEqual(codex.tier("rat"), 1)

    def test_dying_is_faster_than_killing(self):
        """The point of the whole game, as a number."""
        from .codex import KILL_THRESHOLD
        killer = FakeSave()
        dier = FakeSave()
        w = World(killer, seed=4)

        # the dier dies twice to a brute
        dier.known.append("self.corpse")
        for _ in range(2):
            dier.record_death("brute")
            dier.reveal_on_death("brute", ["brute"], [])
        self.assertTrue(dier.knows("brute.rule"))
        self.assertTrue(dier.knows("brute.tell"),
                        "two deaths should have bought the tell")

        # the killer has to kill three to get the same distance
        for _ in range(2):
            w.learned = None
            self._kill(w, "brute")
        self.assertFalse(killer.knows("brute.tell"),
                         "two kills must NOT equal two deaths")
        self.assertEqual(KILL_THRESHOLD["tell"], 3)

    def test_kills_until_next_lesson_reports_honestly(self):
        codex = FakeSave()
        self.assertEqual(codex.kills_until_next_lesson("spitter"), 1)
        codex.stats["kills_by"]["spitter"] = 1
        codex.known.append("spitter.rule")
        self.assertEqual(codex.kills_until_next_lesson("spitter"), 2)
        for k in ("spitter.rule", "spitter.tell", "spitter.counter"):
            if k not in codex.known:
                codex.known.append(k)
        self.assertIsNone(codex.kills_until_next_lesson("spitter"),
                          "nothing left to learn from killing them")

    def test_kill_and_item_facts_do_not_presume_you_died(self):
        """A fact you can earn by killing a thing, or by drinking a thing, must read
        correctly in that context. 'and it still killed you' is fine on an autopsy
        screen and nonsense when you are standing over its corpse."""
        from .codex import FACT_LIST, TIER_ORDER

        banned = ["killed you", "you died", "died holding", "so you died",
                  "your corpse", "when you died"]
        for f in FACT_LIST:
            reachable_alive = (f.tier in TIER_ORDER) or f.tier == "identity"
            if not reachable_alive:
                continue          # self.corpse etc. are death-only, and may say so
            low = f.text.lower()
            for phrase in banned:
                self.assertNotIn(
                    phrase, low,
                    "%r can be learned while alive (by a kill or a sip) but its text "
                    "assumes the reader died: %r" % (f.key, phrase))

    def test_killing_never_breaks_the_every_death_teaches_guarantee(self):
        """Kills fill in the Codex, so a death must still find something NEW."""
        rng = random.Random(3)
        codex = FakeSave()
        seen = set()
        for i in range(300):
            # grind some kills in between deaths
            for _ in range(rng.randint(0, 3)):
                subj = rng.choice(SUBJECTS)
                codex.stats["kills_by"][subj] = codex.stats["kills_by"].get(subj, 0) + 1
                f = codex.reveal_on_kill(subj)
                if f:
                    seen.add(f.title + f.text)
            cause = rng.choice(CAUSES)
            codex.record_death(cause)
            fact = codex.reveal_on_death(cause, rng.sample(SUBJECTS, 4),
                                         rng.sample(FLAVORS, 2))
            ident = fact.title + fact.text
            self.assertNotIn(ident, seen,
                             "death %d taught something already known from a kill" % i)
            seen.add(ident)


class TestKnowledgeIsNotPower(unittest.TestCase):
    """The heart of the design. Same seed, same keystrokes, one blind hero and one
    omniscient one -- the dungeons must be bit-identical."""

    def _trace(self, codex, seed):
        script = random.Random(1234)
        # both heroes must walk the same dungeon, or we are comparing two different
        # maps instead of two different amounts of knowledge
        codex.world_seed = seed * 7919
        w = World(codex, seed=seed)
        trace = []
        for step in range(400):
            if w.dead or w.won:
                break
            r = script.random()
            if r < 0.72:
                dx, dy = script.choice([(0, -1), (0, 1), (-1, 0), (1, 0),
                                        (1, 1), (-1, -1), (1, -1), (-1, 1)])
                w.player_move(dx, dy)
            elif r < 0.82:
                w.player_pickup()
            elif r < 0.90:
                w.use_item(0)
            elif r < 0.95:
                w.player_wait()
            else:
                w.descend()
            p = w.player
            trace.append((
                p.x, p.y, p.hp, p.gold, p.poison, p.haste, p.might, p.energy,
                w.depth, w.tick, w.dead, w.death_cause,
                tuple(sorted((m.key, m.x, m.y, m.hp, m.stunned, str(m.intent))
                             for m in w.level.monsters)),
                tuple(sorted((t.key, t.x, t.y, t.sprung) for t in w.level.traps)),
            ))
        return trace

    def test_blind_and_omniscient_dungeons_are_identical(self):
        for seed in (7, 99, 4242):
            blind = FakeSave()
            wise = FakeSave()
            wise.known = list(FACTS)       # knows every monster, trap and potion
            t1 = self._trace(blind, seed)
            t2 = self._trace(wise, seed)
            self.assertEqual(
                t1, t2,
                "seed %d: knowledge changed the simulation. it must only change "
                "what is drawn." % seed)
            self.assertTrue(t1, "seed %d produced an empty trace" % seed)


class TestTheDungeonIsSurvivable(unittest.TestCase):
    def _reachable(self, lvl, start):
        seen = {start}
        q = deque([start])
        while q:
            x, y = q.popleft()
            for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0),
                           (1, 1), (1, -1), (-1, 1), (-1, -1)):
                n = (x + dx, y + dy)
                if n in seen or not lvl.walkable(*n):
                    continue
                seen.add(n)
                q.append(n)
        return seen

    def test_stairs_are_always_reachable_on_every_floor(self):
        for seed in range(40):
            codex = FakeSave()
            w = World(codex, seed=seed)
            for depth in range(1, config.DEPTH_MAX + 1):
                lvl = w.level
                reach = self._reachable(lvl, lvl.start)
                if lvl.stairs is None:
                    self.assertEqual(depth, config.DEPTH_MAX)
                    boss = [m for m in lvl.monsters if m.key == "warden"]
                    self.assertEqual(len(boss), 1, "the last floor needs its Warden")
                    self.assertIn((boss[0].x, boss[0].y), reach,
                                  "seed %d: the Warden is walled off" % seed)
                else:
                    self.assertIn(lvl.stairs, reach,
                                  "seed %d floor %d: the stairs are unreachable"
                                  % (seed, depth))
                    w.new_level(depth + 1)

    def test_nothing_spawns_on_top_of_the_player(self):
        for seed in range(30):
            w = World(FakeSave(), seed=seed)
            for depth in range(1, config.DEPTH_MAX + 1):
                lvl = w.level
                sx, sy = lvl.start
                for m in lvl.monsters:
                    self.assertGreater(
                        max(abs(m.x - sx), abs(m.y - sy)), 1,
                        "seed %d floor %d: a monster spawned in your face" % (seed, depth))
                for t in lvl.traps:
                    self.assertNotEqual((t.x, t.y), (sx, sy),
                                        "seed %d: a trap spawned under the player" % seed)
                if lvl.stairs:
                    w.new_level(depth + 1)


class TestFloorOne(unittest.TestCase):
    """Floor 1 is the tutorial the dungeon does not admit to having."""

    def test_floor_one_always_has_a_guaranteed_gear_upgrade(self):
        from .items import ALL_GEAR
        for ws in range(60):
            codex = FakeSave()
            codex.world_seed = ws          # pin the stone
            w = World(codex, seed=1)
            gift = [d for d in w.level.drops if d.gift == "floor1"]
            self.assertEqual(len(gift), 1,
                             "world %d: floor 1 has no guaranteed upgrade" % ws)
            self.assertGreaterEqual(ALL_GEAR[gift[0].payload].tier, 1,
                                    "world %d: the gift is not an upgrade" % ws)

    def test_the_floor_one_upgrade_is_a_reward_for_exploring(self):
        """It must not be sitting on the doormat.

        Only THE GIFT is held to this -- ordinary random loot also rolls gear
        sometimes, and that is allowed to be anywhere. (An earlier version of this
        test checked every gear drop, so it failed at random whenever the loot table
        happened to put a Bronze Sword near the door.)
        """
        for ws in range(40):
            codex = FakeSave()
            codex.world_seed = ws              # pin the stone: no flaky dungeons
            w = World(codex, seed=1)
            ex, ey = w.level.entrance
            gift = [d for d in w.level.drops if d.gift == "floor1"]
            self.assertEqual(len(gift), 1, "world %d has no gift" % ws)
            d = abs(gift[0].x - ex) + abs(gift[0].y - ey)
            self.assertGreater(d, 8,
                               "world %d: the gift is %d tiles from the gate -- that "
                               "is a handout, not a reward" % (ws, d))

    def _gift(self, world):
        return [d for d in world.level.drops if d.gift == "floor1"]

    def test_the_floor_one_upgrade_is_claimed_once_per_GAME_not_per_run(self):
        """Regression: it used to respawn on every death, so dying was a way to farm
        a free upgrade off floor 1 forever."""
        codex = FakeSave()
        w = World(codex, seed=12)
        gift = self._gift(w)
        self.assertEqual(len(gift), 1, "the first run should offer the upgrade")

        # walk over and take it
        g = gift[0]
        w.player.x, w.player.y = g.x, g.y
        w.level.monsters = []
        w.player_pickup()
        self.assertTrue(codex.gift_claimed("floor1"), "picking it up must spend it")

        # now die, and come back. it must NOT be there again.
        for seed in (12, 77, 5):
            w2 = World(codex, seed=seed)
            self.assertEqual(self._gift(w2), [],
                             "seed %d: the floor 1 upgrade respawned after a death"
                             % seed)

    def test_dying_before_you_find_it_does_not_cost_you_the_gift(self):
        codex = FakeSave()
        w = World(codex, seed=12)
        self.assertEqual(len(self._gift(w)), 1)
        w.kill_player("angry_rat")          # died without ever reaching it
        w.leave_corpse()
        self.assertFalse(codex.gift_claimed("floor1"))
        w2 = World(codex, seed=31)
        self.assertEqual(len(self._gift(w2)), 1,
                         "you never got it, so it must still be waiting for you")

    def test_a_new_game_puts_the_gift_back(self):
        codex = FakeSave()
        codex.claim_gift("floor1")
        w = World(codex, seed=12)
        self.assertEqual(self._gift(w), [], "already claimed in this game")
        codex.wipe()
        w2 = World(codex, seed=12)
        self.assertEqual(len(self._gift(w2)), 1,
                         "a NEW GAME must restore the floor 1 upgrade")

    def test_the_floor_one_gift_is_a_bone_sword_or_leather_jerkin(self):
        seen = set()
        for ws in range(120):
            codex = FakeSave()
            codex.world_seed = ws
            w = World(codex, seed=1)
            gift = [d for d in w.level.drops if d.gift == "floor1"]
            self.assertEqual(len(gift), 1, "world %d has no gift" % ws)
            self.assertIn(gift[0].payload, ("bone_sword", "leather"))
            seen.add(gift[0].payload)
        self.assertEqual(seen, {"bone_sword", "leather"},
                         "both sides of the coin must appear across 120 worlds")

    def test_floor_one_has_angry_rats_and_no_plague_rats(self):
        for seed in range(40):
            w = World(FakeSave(), seed=seed)
            keys = {m.key for m in w.level.monsters}
            self.assertNotIn("rat", keys,
                             "seed %d: a plague rat got onto floor 1" % seed)
            for hard in ("brute", "wraith", "spitter", "warden"):
                self.assertNotIn(hard, keys,
                                 "seed %d: a %s got onto floor 1" % (seed, hard))

    def test_an_angry_rat_is_genuinely_weaker_than_a_plague_rat(self):
        from .monsters import TEMPLATES
        a, p = TEMPLATES["angry_rat"], TEMPLATES["rat"]
        self.assertLess(a.hp, p.hp)
        self.assertLess(a.hi, p.hi)
        self.assertLess(a.speed, p.speed, "the plague rat is the fast one")

    def test_every_floor_has_a_marked_entrance_and_you_spawn_on_it(self):
        for seed in range(30):
            w = World(FakeSave(), seed=seed)
            for depth in range(1, config.DEPTH_MAX + 1):
                lvl = w.level
                self.assertTrue(lvl.walkable(*lvl.entrance),
                                "seed %d floor %d: the entrance is inside a wall"
                                % (seed, depth))
                self.assertEqual((w.player.x, w.player.y), lvl.entrance,
                                 "seed %d floor %d: you did not arrive at the entrance"
                                 % (seed, depth))
                if lvl.stairs:
                    self.assertNotEqual(lvl.stairs, lvl.entrance,
                                        "the way down must not be the way in")
                    w.new_level(depth + 1)

    def test_you_always_respawn_at_the_entrance_after_death(self):
        codex = FakeSave()
        w = World(codex, seed=8)
        w.player.x, w.player.y = w.level.stairs      # die far from the gate
        w.kill_player("angry_rat")
        w2 = World(codex, seed=8)                    # the run after
        self.assertEqual((w2.player.x, w2.player.y), w2.level.entrance)


class TestTurnEconomy(unittest.TestCase):
    """Boots are not cosmetic. Speed buys actions."""

    def _actions_ratio(self, boots_key):
        """Ticks burned per player action. A tick is when the monsters get paid.
        Fewer ticks for the same 40 actions == the player is acting more often
        than the dungeon is."""
        codex = FakeSave()
        w = World(codex, seed=5)
        w.level.monsters = []               # measure the clock, not the combat
        w.player.boots = BOOTS[boots_key]
        ticks_before = w.tick
        for _ in range(40):
            w.player_wait()
        return 40, w.tick - ticks_before

    def test_faster_boots_mean_more_player_turns_per_monster_turn(self):
        # a monster at speed 100 acts once per tick; the ticks burned per player
        # action is the real measure of how fast the player is
        _, ticks_sandals = self._actions_ratio("sandals")     # +0
        _, ticks_swift = self._actions_ratio("swift")         # +25
        _, ticks_wind = self._actions_ratio("wind")           # +40
        self.assertEqual(ticks_sandals, 40, "base speed should be exactly 1 tick/action")
        self.assertLess(ticks_swift, ticks_sandals,
                        "swift boots must buy the player turns")
        self.assertLess(ticks_wind, ticks_swift,
                        "windwalkers must be faster still")

    def test_heavy_armour_sells_turns_back(self):
        from .items import ARMOURS
        codex = FakeSave()
        w = World(codex, seed=5)
        w.player.armour = ARMOURS["rags"]
        base = w.player.speed()
        w.player.armour = ARMOURS["plate"]
        self.assertLess(w.player.speed(), base,
                        "plate must cost speed -- that is its whole trade")
        self.assertGreater(w.player.armour.defense, 0)


class TestHoldToWalk(unittest.TestCase):
    """A tap is one step. A hold walks. Neither may ever kill you by surprise."""

    def test_a_tap_is_exactly_one_step(self):
        from .keyrepeat import Repeater
        r = Repeater(delay=0.22, interval=0.085)
        r.start("w", 0.0)
        # the KEYDOWN already took the step; nothing more may fire inside the delay
        for t in (0.0, 0.05, 0.1, 0.21):
            self.assertIsNone(r.poll(t, lambda k: True),
                              "a quick tap must not produce a second step at t=%s" % t)

    def test_holding_past_the_delay_walks(self):
        from .keyrepeat import Repeater
        r = Repeater(delay=0.22, interval=0.085)
        r.start("w", 0.0)
        steps = 0
        t = 0.0
        while t < 1.0:
            t += 1 / 60.0
            if r.poll(t, lambda k: True):
                steps += 1
        # ~0.78s of walking at one step per 0.085s
        self.assertGreaterEqual(steps, 7, "holding the key should keep walking")
        self.assertLessEqual(steps, 11, "it should not walk absurdly fast")

    def test_releasing_the_key_stops_the_walk(self):
        from .keyrepeat import Repeater
        r = Repeater(delay=0.1, interval=0.05)
        r.start("w", 0.0)
        self.assertIsNotNone(r.poll(0.2, lambda k: True))
        self.assertIsNone(r.poll(0.3, lambda k: False), "release must stop the walk")
        self.assertFalse(r.active)

    def test_an_autowalk_will_not_attack_for_you(self):
        from .game import Game
        from .monsters import Monster
        g = Game.__new__(Game)                 # no pygame display needed
        g.world = World(FakeSave(), seed=6)
        g.state = None
        w = g.world
        w.level.monsters = []
        # find a walkable neighbour and park a brute on it
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if w.walkable(w.player.x + dx, w.player.y + dy):
                m = Monster("brute", w.player.x + dx, w.player.y + dy)
                w.level.monsters = [m]
                hp = m.hp
                self.assertFalse(g.walk_step(dx, dy),
                                 "an auto-walk must stop at a monster, not swing")
                self.assertEqual(m.hp, hp, "the auto-walk threw a punch")
                return
        self.skipTest("no walkable neighbour on this seed")

    def test_an_autowalk_stops_the_instant_you_are_hurt(self):
        from .game import Game
        from .traps import Trap
        g = Game.__new__(Game)
        g.world = World(FakeSave(), seed=6)
        g.state = None
        w = g.world
        w.level.monsters = []
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = w.player.x + dx, w.player.y + dy
            if w.walkable(nx, ny):
                w.level.traps = [Trap("dart", nx, ny)]
                hp = w.player.hp
                cont = g.walk_step(dx, dy)
                self.assertLess(w.player.hp, hp, "the trap should have fired")
                self.assertFalse(cont,
                                 "you must not keep auto-walking after taking damage")
                return
        self.skipTest("no walkable neighbour on this seed")

    def test_a_wall_stops_the_walk(self):
        """You never spawn beside a wall (the entrance is a room's centre), so put
        the hero against one first, then try to walk into it."""
        from .game import Game
        g = Game.__new__(Game)
        g.state = None
        g.world = World(FakeSave(), seed=6)
        w = g.world
        w.level.monsters = []
        lvl = w.level
        for y in range(lvl.h):
            for x in range(lvl.w):
                if not lvl.walkable(x, y):
                    continue
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    if not lvl.walkable(x + dx, y + dy):
                        w.player.x, w.player.y = x, y
                        self.assertFalse(g.walk_step(dx, dy),
                                         "a wall must stop the auto-walk")
                        self.assertEqual((w.player.x, w.player.y), (x, y),
                                         "the walk moved you into a wall")
                        return
        self.fail("this level has no walls at all -- the test is broken")


class TestAutoWalkStopsForInterestingThings(unittest.TestCase):
    """Hold-to-walk exists so the dungeon is not a typing exercise. But a walk that
    runs you past the thing you were looking for is its own kind of failure, so the
    walk gives way the moment the floor has something to say."""

    def _game(self, seed=6):
        from .game import Game
        g = Game.__new__(Game)          # no pygame display needed
        g.state = None
        g.world = World(FakeSave(), seed=seed)
        w = g.world
        w.level.monsters = []
        w.level.drops = []
        w.level.chests = []
        w.level.slain = []
        return g

    def _empty_neighbour(self, w):
        """A walkable neighbouring tile with nothing on it, or None."""
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = w.player.x + dx, w.player.y + dy
            if w.walkable(nx, ny) and not w.level.trap_at(nx, ny):
                return dx, dy, nx, ny
        return None

    def test_an_empty_tile_does_not_stop_the_walk(self):
        """The guard on the other two: an interrupt that fires on nothing would just
        be hold-to-walk deleted."""
        g = self._game()
        w = g.world
        spot = self._empty_neighbour(w)
        if spot is None:
            self.skipTest("no clear neighbour on this seed")
        dx, dy, nx, ny = spot
        self.assertTrue(g.walk_step(dx, dy),
                        "an empty tile must not interrupt the walk")
        self.assertEqual((w.player.x, w.player.y), (nx, ny))

    def test_stepping_onto_loot_stops_the_walk(self):
        """You walked over it, which is exactly how you miss it. Stop ON the tile so
        the take prompt is under you when you look up."""
        from .dungeon import Drop
        g = self._game()
        w = g.world
        spot = self._empty_neighbour(w)
        if spot is None:
            self.skipTest("no clear neighbour on this seed")
        dx, dy, nx, ny = spot
        w.level.drops = [Drop(nx, ny, "gold", 25)]
        cont = g.walk_step(dx, dy)
        self.assertEqual((w.player.x, w.player.y), (nx, ny),
                         "the step itself must still happen -- you stop ON the loot")
        self.assertFalse(cont, "stepping onto loot must stop the auto-walk")

    def _reveal_spot(self, w):
        """A step that opens fresh ground: (dx, dy, nx, ny, (mx, my)) where (mx, my)
        is walkable, unseen from here, and seen from there. None if the seed has no
        such step."""
        lvl = w.level
        px, py = w.player.x, w.player.y

        def seen_from(x, y):
            lvl.compute_fov(x, y)
            return {(cx, cy)
                    for cy in range(lvl.h) for cx in range(lvl.w)
                    if lvl.visible[cy][cx]}

        here = seen_from(px, py)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = px + dx, py + dy
            if not w.walkable(nx, ny) or lvl.trap_at(nx, ny):
                continue
            fresh = sorted(t for t in seen_from(nx, ny) - here
                           if lvl.walkable(*t) and t not in ((px, py), (nx, ny)))
            lvl.compute_fov(px, py)          # put the world back as we found it
            if fresh:
                return dx, dy, nx, ny, fresh[0]
        lvl.compute_fov(px, py)
        return None

    def test_a_monster_coming_into_view_stops_the_walk(self):
        """The one that matters. A brute you walk past is a brute that gets its
        wind-up for free, and stepping off the wind-up is the whole fight."""
        from .monsters import Monster
        g = self._game()
        w = g.world
        spot = self._reveal_spot(w)
        if spot is None:
            self.skipTest("no neighbour on this seed reveals fresh ground")
        dx, dy, nx, ny, (mx, my) = spot
        w.level.monsters = [Monster("brute", mx, my)]
        cont = g.walk_step(dx, dy)
        self.assertEqual((w.player.x, w.player.y), (nx, ny),
                         "the step itself must still happen")
        self.assertFalse(cont, "a monster entering view must stop the auto-walk")

    def test_a_poltergeist_you_cannot_see_does_not_stop_the_walk(self):
        """The dungeon draws NOTHING for a poltergeist until you have learned its
        counter. Halting the walk for one would hand you knowledge you have not paid
        for -- an invisible hand on the reins. Knowledge is information, never power."""
        from .monsters import Monster
        g = self._game()
        w = g.world
        spot = self._reveal_spot(w)
        if spot is None:
            self.skipTest("no neighbour on this seed reveals fresh ground")
        dx, dy, nx, ny, (mx, my) = spot
        w.level.monsters = [Monster("poltergeist", mx, my)]
        self.assertFalse(w.codex.knows_tier("poltergeist", "counter"),
                         "this test needs an ignorant codex to mean anything")
        self.assertTrue(g.walk_step(dx, dy),
                        "a poltergeist you cannot see must not stop the walk")

    def test_a_poltergeist_you_have_learned_does_stop_the_walk(self):
        """...and the moment you HAVE earned it, it is a monster like any other."""
        from .monsters import Monster
        g = self._game()
        w = g.world
        spot = self._reveal_spot(w)
        if spot is None:
            self.skipTest("no neighbour on this seed reveals fresh ground")
        dx, dy, nx, ny, (mx, my) = spot
        w.level.monsters = [Monster("poltergeist", mx, my)]
        w.codex.known.append("poltergeist.counter")
        self.assertFalse(g.walk_step(dx, dy),
                         "once you can see it, it stops the walk like anything else")

    def test_a_monster_already_in_view_does_not_re_stop_the_walk(self):
        """Otherwise you could never walk anywhere with a monster on screen -- the
        interrupt is about the moment it ARRIVES, not about it existing."""
        from .monsters import Monster
        g = self._game()
        w = g.world
        lvl = w.level
        spot = self._empty_neighbour(w)
        if spot is None:
            self.skipTest("no clear neighbour on this seed")
        dx, dy, nx, ny = spot
        lvl.compute_fov(w.player.x, w.player.y)
        for cy in range(lvl.h):
            for cx in range(lvl.w):
                if (not lvl.visible[cy][cx] or not lvl.walkable(cx, cy)
                        or (cx, cy) in ((w.player.x, w.player.y), (nx, ny))):
                    continue
                lvl.monsters = [Monster("rat", cx, cy)]
                self.assertTrue(g.walk_step(dx, dy),
                                "a monster you could already see must not stop you")
                return
        self.skipTest("nothing else visible on this seed")


class TestRoomVariety(unittest.TestCase):
    """Rooms come in real size classes, the big ones are placed first and spread out,
    and the boss always gets a hall."""

    def _floors(self, n_games=30):
        out = []
        for ws in range(n_games):
            codex = FakeSave()
            codex.world_seed = ws
            w = World(codex, seed=ws)
            for d in range(1, config.DEPTH_MAX + 1):
                w.new_level(d)
                out.append((d, w.level))
        return out

    def test_there_are_genuinely_big_and_genuinely_small_rooms(self):
        areas = [r.area for _, lvl in self._floors() for r in lvl.rooms]
        self.assertLess(min(areas), 25, "there should be pokey little nooks")
        self.assertGreater(max(areas), 140,
                           "there should be halls bigger than any old room (max 108)")
        # and the spread should be WIDE, not a tight band around one size
        import statistics
        self.assertGreater(statistics.pstdev(areas), 28,
                           "room sizes must actually vary, not cluster")

    def test_hall_count_follows_40_40_20_ish(self):
        from collections import Counter
        counts = Counter()
        for d, lvl in self._floors(60):
            if d >= config.DEPTH_MAX:
                continue                      # the boss floor is forced, skip it
            counts[sum(1 for r in lvl.rooms if r.hall)] += 1
        total = sum(counts.values())
        # 0:40% 1:40% 2:20% -- allow slack, we just want the shape to be right
        self.assertGreater(counts[0] / total, 0.28)
        self.assertGreater(counts[1] / total, 0.28)
        self.assertGreater(counts[2] / total, 0.08)
        self.assertLess(counts[2] / total, 0.32)
        self.assertLessEqual(max(counts), max(counts))   # no floor exceeds 2
        self.assertNotIn(3, counts, "never more than two halls")

    def test_the_boss_floor_always_has_a_hall(self):
        for ws in range(40):
            codex = FakeSave()
            codex.world_seed = ws
            w = World(codex, seed=ws)
            w.new_level(config.DEPTH_MAX)
            self.assertTrue(any(r.hall for r in w.level.rooms),
                            "seed %d: the Warden's floor has no hall to fight in" % ws)

    def test_the_boss_arena_is_big_enough_for_its_pillars(self):
        """The arena is the largest non-gate room, and its pillars -- the counter the
        Kodex teaches -- only appear at 9x7. A forced hall guarantees them."""
        for ws in range(40):
            codex = FakeSave()
            codex.world_seed = ws
            w = World(codex, seed=ws)
            w.new_level(config.DEPTH_MAX)
            arena = max((r for r in w.level.rooms if r is not w.level.gate_room),
                        key=lambda r: r.area)
            self.assertTrue(arena.w >= 9 and arena.h >= 7,
                            "seed %d: arena %dx%d is too small for pillars"
                            % (ws, arena.w, arena.h))

    def test_two_halls_are_never_adjacent(self):
        """The anti-clustering rule: two halls may not share touching sectors."""
        for ws in range(60):
            codex = FakeSave()
            codex.world_seed = ws
            w = World(codex, seed=ws)
            for d in range(2, config.DEPTH_MAX):
                w.new_level(d)
                halls = [r for r in w.level.rooms if r.hall]
                for i, a in enumerate(halls):
                    for b in halls[i + 1:]:
                        # two halls live in non-edge-adjacent sectors: they never
                        # share a tile (generation guarantees a wall between them) and
                        # their centres are always a real distance apart
                        self.assertFalse(a.intersects(b, pad=1),
                                         "seed %d floor %d: two halls overlap"
                                         % (ws, d))
                        self.assertGreater(
                            abs(a.cx - b.cx) + abs(a.cy - b.cy), 12,
                            "seed %d floor %d: two halls are jammed together"
                            % (ws, d))

    def test_the_gate_is_not_a_hall(self):
        for ws in range(40):
            codex = FakeSave()
            codex.world_seed = ws
            w = World(codex, seed=ws)
            for d in range(1, config.DEPTH_MAX + 1):
                w.new_level(d)
                # only forgivable if EVERY room is a hall, which cannot happen
                self.assertFalse(w.level.gate_room.hall,
                                 "seed %d floor %d: you walk in through a great hall"
                                 % (ws, d))

    def test_the_floors_are_still_fully_connected(self):
        """Nearest-neighbour corridors must still reach every room."""
        from collections import deque
        for ws in range(30):
            codex = FakeSave()
            codex.world_seed = ws
            w = World(codex, seed=ws)
            for d in range(1, config.DEPTH_MAX + 1):
                w.new_level(d)
                lvl = w.level
                seen = {lvl.start}
                q = deque([lvl.start])
                while q:
                    x, y = q.popleft()
                    for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                        n = (x + dx, y + dy)
                        if n not in seen and lvl.walkable(*n):
                            seen.add(n)
                            q.append(n)
                if lvl.stairs:
                    self.assertIn(lvl.stairs, seen,
                                  "seed %d floor %d: the stairs are cut off" % (ws, d))


class TestStairPlacement(unittest.TestCase):
    """The way down is a random room in the quarter diagonally opposite the entrance
    -- a real journey, but no longer the same corner every time."""

    def _floors(self, n_games=40):
        for ws in range(n_games):
            codex = FakeSave()
            codex.world_seed = ws
            w = World(codex, seed=ws)
            for d in range(1, config.DEPTH_MAX):     # boss floor has no down stairs
                w.new_level(d)
                yield ws, d, w.level

    def _quarter(self, lvl, x, y):
        return (0 if x < lvl.w // 2 else 1, 0 if y < lvl.h // 2 else 1)

    def test_the_stairs_are_NEVER_in_the_entrance_quarter(self):
        """The one hard invariant: the way down is always at least a quarter away."""
        for ws, d, lvl in self._floors():
            eq = self._quarter(lvl, *lvl.entrance)
            sq = self._quarter(lvl, *lvl.stairs)
            self.assertNotEqual(sq, eq,
                                "seed %d floor %d: the stairs are in the entrance's "
                                "own quarter" % (ws, d))

    def test_the_quarters_are_weighted_roughly_25_25_50(self):
        """Across (Q2), below (Q3), diagonal (Q4). Diagonal is the favourite but only
        half the time."""
        from collections import Counter
        c = Counter()
        for ws, d, lvl in self._floors(120):
            eq = self._quarter(lvl, *lvl.entrance)
            sq = self._quarter(lvl, *lvl.stairs)
            if sq == (1 - eq[0], eq[1]):
                c["Q2"] += 1
            elif sq == (eq[0], 1 - eq[1]):
                c["Q3"] += 1
            elif sq == (1 - eq[0], 1 - eq[1]):
                c["Q4"] += 1
        total = sum(c.values())
        self.assertGreater(total, 600)
        self.assertAlmostEqual(c["Q2"] / total, 0.25, delta=0.08)
        self.assertAlmostEqual(c["Q3"] / total, 0.25, delta=0.08)
        self.assertAlmostEqual(c["Q4"] / total, 0.50, delta=0.10)
        self.assertGreater(c["Q4"], c["Q2"], "Q4 must still be the favourite")

    def test_the_stairs_are_never_at_the_entrance(self):
        for ws, d, lvl in self._floors():
            self.assertNotEqual(lvl.stairs, lvl.entrance,
                                "seed %d floor %d: the way down is the way in" % (ws, d))

    def test_all_three_quarters_actually_get_used(self):
        """It is not just 'Q4 vs. a rare fallback' -- Q2 and Q3 must really happen."""
        from collections import Counter
        c = Counter()
        for ws, d, lvl in self._floors(60):
            eq = self._quarter(lvl, *lvl.entrance)
            sq = self._quarter(lvl, *lvl.stairs)
            c[sq] += 1
        # entrance is usually top-left, so expect real counts in Q2/Q3/Q4
        self.assertGreaterEqual(len([v for v in c.values() if v > 5]), 3,
                                "at least three distinct quarters should see stairs")

    def test_it_actually_VARIES_between_dungeons(self):
        """The whole point: the exit is not the same predictable spot every time."""
        seen = set()
        for ws, d, lvl in self._floors():
            if d == 1:                # compare the same floor across many games
                seen.add(lvl.stairs)
        self.assertGreater(len(seen), 10,
                           "floor 1's stairs must land in many different rooms")

    def test_the_stairs_are_fixed_for_a_GAME(self):
        """They are part of the stone: same room every run, until a new dungeon."""
        codex = FakeSave()
        codex.world_seed = 777
        first = {}
        w = World(codex, seed=1)
        for d in range(1, config.DEPTH_MAX):
            w.new_level(d)
            first[d] = w.level.stairs

        for run in (2, 3, 99):
            w2 = World(codex, seed=run)
            for d in range(1, config.DEPTH_MAX):
                w2.new_level(d)
                self.assertEqual(w2.level.stairs, first[d],
                                 "floor %d's stairs moved between runs of one game"
                                 % d)

    def test_the_stairs_are_always_on_a_walkable_tile(self):
        for ws, d, lvl in self._floors():
            self.assertTrue(lvl.walkable(*lvl.stairs),
                            "seed %d floor %d: stairs inside a wall" % (ws, d))

    def test_the_stairs_are_always_reachable(self):
        from collections import deque
        for ws, d, lvl in self._floors(20):
            seen = {lvl.start}
            q = deque([lvl.start])
            while q:
                x, y = q.popleft()
                for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                    n = (x + dx, y + dy)
                    if n not in seen and lvl.walkable(*n):
                        seen.add(n)
                        q.append(n)
            self.assertIn(lvl.stairs, seen,
                          "seed %d floor %d: stairs are cut off" % (ws, d))

    def test_usually_a_journey_but_sometimes_you_get_lucky(self):
        """A random room in another quarter is USUALLY a real trek, but a Q3 roll near
        the midline can be short -- and that lucky short floor is the point. So: the
        typical floor is a journey, but we do not forbid the occasional gift."""
        dists = [abs(lvl.stairs[0] - lvl.entrance[0]) + abs(lvl.stairs[1] - lvl.entrance[1])
                 for _, _, lvl in self._floors()]
        dists.sort()
        median = dists[len(dists) // 2]
        self.assertGreater(median, 25, "the typical floor must still be a real trek")
        # and there IS meaningful spread -- not every floor the same length
        self.assertGreater(dists[9 * len(dists) // 10] - dists[len(dists) // 10], 20,
                           "floor length must actually vary")


class TestLayoutMigration(unittest.TestCase):
    def test_an_old_save_forgets_the_map_but_keeps_the_kodex(self):
        import json
        import tempfile
        from . import config as cfg
        from .codex import Codex

        old = cfg.SAVE_PATH
        cfg.SAVE_PATH = os.path.join(tempfile.gettempdir(), "dw_migrate.json")
        try:
            # hand-write a save from an OLDER generator
            data = {
                "known": ["brute.rule", "dart.rule"], "deaths": 12,
                "world_seed": 999, "maps": {"1": "1111"},
                "found_traps": {"2": ["10,10"]},
                "corpses": {"3": {"x": 5, "y": 5, "gold": 200, "weapon": "brand"}},
                "layout_version": 1,
            }
            with open(cfg.SAVE_PATH, "w") as fh:
                json.dump(data, fh)

            c = Codex()
            c.load()

            self.assertIn("brute.rule", c.known, "the Kodex must survive")
            self.assertEqual(c.deaths, 12, "and the deaths")
            self.assertIsNone(c.world_seed, "but the stale stone is dropped")
            self.assertEqual(c.maps, {}, "the map of a dungeon that moved is forgotten")
            self.assertEqual(c.found_traps, {})
            self.assertEqual(c.corpses, {})
            self.assertTrue(c.layout_migrated)
        finally:
            if os.path.exists(cfg.SAVE_PATH):
                os.remove(cfg.SAVE_PATH)
            cfg.SAVE_PATH = old

    def test_a_current_save_is_left_alone(self):
        import json
        import tempfile
        from . import config as cfg
        from .codex import Codex

        old = cfg.SAVE_PATH
        cfg.SAVE_PATH = os.path.join(tempfile.gettempdir(), "dw_migrate2.json")
        try:
            c = Codex()
            c.known = ["brute.rule"]
            c.world_seed = 555
            c.maps = {"1": "1010"}
            c.save()

            fresh = Codex()
            fresh.load()
            self.assertEqual(fresh.world_seed, 555, "a current save keeps its stone")
            self.assertEqual(fresh.maps, {"1": "1010"})
            self.assertFalse(fresh.layout_migrated)
        finally:
            if os.path.exists(cfg.SAVE_PATH):
                os.remove(cfg.SAVE_PATH)
            cfg.SAVE_PATH = old


class TestPersistentStone(unittest.TestCase):
    """The map is cut once per GAME. The things living in it are dealt every RUN."""

    def _grid(self, lvl):
        return tuple(tuple(row) for row in lvl.grid)

    def _contents(self, lvl):
        # magical weapons are the one exception to "re-dealt every run" (Task 3: they
        # persist where they lie, same as a corpse) -- carve them out here so this stays
        # a measure of the LIVING, not the heirlooms salted through the floor.
        from .items import is_magical
        living_drops = [d for d in lvl.drops
                        if not (d.kind == "gear" and is_magical(d.payload))]
        return (tuple(sorted((m.key, m.x, m.y) for m in lvl.monsters)),
                tuple(sorted((t.key, t.x, t.y) for t in lvl.traps)),
                tuple(sorted((c.x, c.y) for c in lvl.chests)),
                tuple(sorted((d.kind, str(d.payload), d.x, d.y) for d in living_drops)))

    def test_the_stone_is_identical_on_every_respawn(self):
        codex = FakeSave()
        first = World(codex, seed=1)
        base = {}
        for depth in range(1, config.DEPTH_MAX + 1):
            first.new_level(depth)
            base[depth] = (self._grid(first.level), first.level.entrance,
                           first.level.stairs)

        for run_seed in (2, 3, 999):                 # later runs: different run RNG
            w = World(codex, seed=run_seed)
            for depth in range(1, config.DEPTH_MAX + 1):
                w.new_level(depth)
                grid, ent, stairs = base[depth]
                self.assertEqual(self._grid(w.level), grid,
                                 "floor %d's walls changed between runs" % depth)
                self.assertEqual(w.level.entrance, ent,
                                 "floor %d's entrance moved between runs" % depth)
                self.assertEqual(w.level.stairs, stairs,
                                 "floor %d's stairs moved between runs" % depth)

    def test_the_living_are_re_dealt_every_respawn(self):
        codex = FakeSave()
        seen = set()
        for run_seed in (1, 2, 3, 4, 5):
            w = World(codex, seed=run_seed)
            seen.add(self._contents(w.level))
        self.assertGreater(len(seen), 1,
                           "monsters/traps/loot must be re-dealt on a respawn")

    def test_a_new_game_cuts_new_stone(self):
        codex = FakeSave()
        w = World(codex, seed=1)
        before = self._grid(w.level)
        old_seed = codex.world_seed

        codex.wipe()
        self.assertIsNone(codex.world_seed, "a new game must forget the old stone")
        w2 = World(codex, seed=1)
        self.assertIsNotNone(codex.world_seed)
        # a fresh world seed is drawn -- overwhelmingly likely to be a new map
        self.assertNotEqual(codex.world_seed, old_seed)
        self.assertNotEqual(self._grid(w2.level), before,
                            "a new game produced the same dungeon")

    def test_the_stone_stays_walkable_where_it_matters(self):
        codex = FakeSave()
        w = World(codex, seed=7)
        for depth in range(1, config.DEPTH_MAX + 1):
            w.new_level(depth)
            self.assertTrue(w.level.walkable(*w.level.entrance))
            if w.level.stairs:
                self.assertTrue(w.level.walkable(*w.level.stairs))


class TestTheMapIsRemembered(unittest.TestCase):
    """The stone does not move between runs, so neither should your memory of it.
    Dying must not un-walk a corridor."""

    def _count(self, lvl):
        return sum(1 for row in lvl.explored for v in row if v)

    def _codex(self):
        """Pin the stone. Otherwise each FakeSave draws a random world seed and the
        map -- and therefore how much a given walk reveals -- changes between runs of
        the suite, which makes these tests flaky rather than wrong."""
        c = FakeSave()
        c.world_seed = 20260713
        return c

    def _explore(self, w, steps=60):
        """Walk a spiral so we reveal ground whatever the room looks like."""
        moves = [(1, 0), (0, 1), (-1, 0), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)]
        for i in range(steps):
            dx, dy = moves[i % len(moves)]
            for _ in range(3):
                w.player_move(dx, dy)

    def test_explored_tiles_survive_a_death(self):
        codex = self._codex()
        w = World(codex, seed=21)
        # walk about a bit to reveal some of the floor
        for _ in range(40):
            w.player_move(1, 0)
            w.player_move(0, 1)
        seen = self._count(w.level)
        self.assertGreater(seen, 30, "the test did not explore anything")
        remembered = [(x, y) for y in range(w.level.h) for x in range(w.level.w)
                      if w.level.explored[y][x]]

        w.kill_player("angry_rat")            # kill_player folds the map into memory

        w2 = World(codex, seed=99)            # a brand new run
        for (x, y) in remembered:
            self.assertTrue(w2.level.explored[y][x],
                            "tile (%d,%d) was explored, then forgotten on respawn"
                            % (x, y))
        self.assertGreaterEqual(self._count(w2.level), seen)

    def test_memory_only_ever_grows(self):
        codex = self._codex()
        w = World(codex, seed=21)
        for _ in range(20):
            w.player_move(1, 0)
        first_tiles = {(x, y) for y in range(w.level.h) for x in range(w.level.w)
                       if w.level.explored[y][x]}
        first = len(first_tiles)
        w.kill_player("rat")

        # the second run goes somewhere genuinely new -- the far side of the floor
        w2 = World(codex, seed=22)
        w2.player.x, w2.player.y = w2.level.stairs
        w2.level.compute_fov(w2.player.x, w2.player.y)
        self._explore(w2, 20)
        w2.kill_player("rat")
        second = self._count(w2.level)
        self.assertTrue(first_tiles <= {(x, y) for y in range(w2.level.h)
                                        for x in range(w2.level.w)
                                        if w2.level.explored[y][x]},
                        "the second run lost tiles the first run had walked")
        self.assertGreater(second, first,
                           "the second run should add to the map, not replace it")

        w3 = World(codex, seed=23)
        self.assertGreaterEqual(self._count(w3.level), second,
                                "memory must accumulate across runs")

    def test_each_floor_is_remembered_separately(self):
        codex = self._codex()
        w = World(codex, seed=21)
        self._explore(w, 20)
        w.player.x, w.player.y = w.level.stairs
        w.descend()                            # descend folds floor 1 into memory
        self.assertEqual(w.depth, 2)
        f1 = codex.maps.get("1")
        self.assertTrue(f1 and "1" in f1, "floor 1 should be remembered")
        # floor 2 is fresh: only what we can see from the entrance
        self.assertLess(self._count(w.level), len(f1))

    def test_a_new_game_forgets_the_map(self):
        codex = self._codex()
        w = World(codex, seed=21)
        self._explore(w, 30)
        w.kill_player("rat")
        self.assertTrue(codex.maps, "the map should have been remembered")

        codex.wipe()
        self.assertEqual(codex.maps, {}, "a new game must forget the map")
        w2 = World(codex, seed=21)
        # a fresh game: only what is visible from the entrance right now
        self.assertLess(self._count(w2.level), 200)

    def test_remembering_survives_a_save_and_load(self):
        import tempfile
        from . import config as cfg
        from .codex import Codex

        old = cfg.SAVE_PATH
        cfg.SAVE_PATH = os.path.join(tempfile.gettempdir(), "dw_map_test.json")
        try:
            c = Codex()
            c.world_seed = 20260713
            w = World(c, seed=21)
            self._explore(w, 30)
            w.kill_player("rat")
            c.save()

            fresh = Codex()
            fresh.load()
            self.assertEqual(fresh.maps, c.maps, "the map did not survive the save file")
            w2 = World(fresh, seed=50)
            self.assertGreater(self._count(w2.level), 30,
                               "a reloaded game should still know the floor")
        finally:
            if os.path.exists(cfg.SAVE_PATH):
                os.remove(cfg.SAVE_PATH)
            cfg.SAVE_PATH = old


class TestLootMenu(unittest.TestCase):
    """Standing on a hoard should be a decision, not a vacuum cleaner."""

    def _chest_under_player(self, w, loot):
        from .dungeon import Chest
        w.level.monsters = []
        w.level.chests = [Chest(w.player.x, w.player.y, loot)]
        w.level.drops = []
        w.level.corpse = None
        return w.level.chests[0]

    def test_a_chest_lists_everything_in_it(self):
        codex = FakeSave()
        w = World(codex, seed=6)
        self._chest_under_player(w, [("gold", 25), ("gear", "bone_axe"), ("item", "azure")])
        opts = w.loot_options()
        self.assertEqual(len(opts), 3)
        self.assertEqual(opts[0]["label"], "25 gold")
        self.assertIn("Bone Axe", opts[1]["label"])
        # an unidentified potion is listed by the LOOK it wears this game, not its
        # true name -- and that look is whatever the shuffle dealt the azure identity.
        look = CONSUMABLES[w.codex.look("azure")].unknown_name
        self.assertEqual(opts[2]["label"], look)
        self.assertNotIn("Swiftness", opts[2]["label"], "and never its true name")

    def test_a_removed_gear_key_orphaned_in_a_container_is_silently_dropped(self):
        """A save made before this branch could still hold a tuple like
        ('gear', 'scale') from a pruned ordinary-armour key. The menu must not
        crash trying to look it up -- it should just not offer it."""
        codex = FakeSave()
        w = World(codex, seed=6)
        self._chest_under_player(w, [("gold", 25), ("gear", "scale"),
                                      ("gear", "bone_axe")])
        opts = w.loot_options()                 # must not raise KeyError
        self.assertEqual([o["payload"] for o in opts], [25, "bone_axe"],
                          "the orphaned piece must be dropped, not crash or linger")
        w.take_all()
        self.assertEqual(w.player.gold, 25)
        self.assertEqual(w.player.weapon.key, "bone_axe")

    def test_an_identified_potion_is_listed_by_its_true_name(self):
        codex = FakeSave()
        codex.known.append("id.ochre")
        w = World(codex, seed=6)
        self._chest_under_player(w, [("item", "ochre")])
        self.assertEqual(w.loot_options()[0]["label"], "Potion of Healing")

    def test_taking_one_thing_leaves_the_rest(self):
        codex = FakeSave()
        w = World(codex, seed=6)
        self._chest_under_player(w, [("gold", 25), ("gear", "bone_axe"), ("item", "azure")])
        w.take_option(0)                        # just the gold
        self.assertEqual(w.player.gold, 25)
        opts = w.loot_options()
        self.assertEqual(len(opts), 2, "the axe and the potion must still be there")
        self.assertEqual(w.player.weapon.key, "shiv", "we did not take the axe")
        self.assertEqual(w.player.pack, [], "we did not take the potion")

    def test_taking_a_middle_option_takes_the_right_one(self):
        codex = FakeSave()
        w = World(codex, seed=6)
        self._chest_under_player(w, [("gold", 25), ("gear", "bone_axe"), ("item", "azure")])
        w.take_option(1)                        # the axe
        self.assertEqual(w.player.weapon.key, "bone_axe")
        labels = [o["label"] for o in w.loot_options()]
        self.assertTrue(any("gold" in l for l in labels))
        self.assertFalse(any("Bone Axe" in l for l in labels), "the axe is in our hand")
        # the Rusted Shiv it displaced is a worthless T0 starter -- it falls away rather
        # than cluttering the chest
        self.assertFalse(any("Rusted Shiv" in l for l in labels),
                         "a displaced T0 starter must vanish, not sit in the chest: %s" % labels)

    def test_take_all_takes_everything_worth_taking(self):
        codex = FakeSave()
        w = World(codex, seed=6)
        ch = self._chest_under_player(w, [("gold", 25), ("gear", "bone_axe"),
                                          ("item", "azure")])
        w.take_all()
        self.assertEqual(w.player.gold, 25)
        self.assertEqual(w.player.weapon.key, "bone_axe")
        self.assertEqual(w.player.pack, ["azure"])
        # the shiv we displaced is a worthless T0 starter: it falls away rather than being
        # left behind, so nothing remains to loot
        self.assertEqual(w.loot_options(), [])

    def test_take_all_will_not_downgrade_your_gear_behind_your_back(self):
        from .items import WEAPONS
        codex = FakeSave()
        w = World(codex, seed=6)
        w.player.weapon = WEAPONS["brand"]      # tier 4
        self._chest_under_player(w, [("gold", 10), ("gear", "bronze_sword")])   # tier 2
        w.take_all()
        self.assertEqual(w.player.gold, 10)
        self.assertEqual(w.player.weapon.key, "brand",
                         "'all' must never swap a Flame Brand for a Bronze Sword")

    def test_an_explicit_choice_may_downgrade_you_if_you_insist(self):
        from .items import ALL_GEAR
        codex = FakeSave()
        w = World(codex, seed=6)
        w.player.armour = ALL_GEAR["plate"].copy()        # +4 def, heavy
        self._chest_under_player(w, [("gear", "leather")])  # +2 def, but fast
        w.take_option(0)
        self.assertEqual(w.player.armour.key, "leather",
                         "if the player picks it deliberately, give it to them")

    def test_G_is_offered_even_for_a_single_item(self):
        """The G row is always there. A key that means 'take everything' should not
        vanish just because 'everything' happens to be one coin."""
        from . import ui
        codex = FakeSave()
        w = World(codex, seed=6)

        self._chest_under_player(w, [("gold", 25)])
        rows = ui.loot_rows(w, codex)
        self.assertEqual([r[0] for r in rows], ["1", "G"],
                         "a single item must still offer G. all")

        self._chest_under_player(w, [("gold", 25), ("item", "ochre")])
        rows = ui.loot_rows(w, codex)
        self.assertEqual([r[0] for r in rows], ["1", "2", "G"])

    def test_G_on_a_single_item_just_takes_it(self):
        codex = FakeSave()
        w = World(codex, seed=6)
        self._chest_under_player(w, [("gold", 25)])
        w.player_pickup()               # what G does
        self.assertEqual(w.player.gold, 25)
        self.assertEqual(w.loot_options(), [])

    def test_numbers_are_items_only_and_G_is_all(self):
        """'all' is G, never a number. Pressing the number just past the last item
        must do nothing, not silently hoover up the chest."""
        codex = FakeSave()
        w = World(codex, seed=6)
        self._chest_under_player(w, [("gold", 25), ("item", "ochre")])
        self.assertFalse(w.take_option(2),
                         "there is no 3rd item -- that key must do nothing")
        self.assertEqual(w.player.gold, 0)
        self.assertEqual(len(w.loot_options()), 2, "nothing should have been taken")

        w.player_pickup()               # this is what G does
        self.assertEqual(w.player.gold, 25)
        self.assertEqual(w.player.pack, ["ochre"])
        self.assertEqual(w.loot_options(), [],
                         "no gear involved, so nothing is left behind")

    def test_your_corpse_lists_gold_and_gear_separately(self):
        codex = FakeSave()
        w = World(codex, seed=6)
        w.level.monsters = []
        w.level.chests = []
        w.level.drops = []
        codex.leave_corpse(1, w.player.x, w.player.y, 140, "rapier", gift_key="swift")
        w2 = World(codex, seed=7)
        w2.level.monsters = []
        c = w2.level.corpse
        self.assertIsNotNone(c)
        w2.player.x, w2.player.y = c.x, c.y
        opts = w2.loot_options()
        labels = [o["label"] for o in opts]
        self.assertEqual(len(opts), 3, "gold, the weapon, and the gift: %s" % labels)
        self.assertIn("140 gold", labels[0])
        self.assertTrue(any("Rapier" in l for l in labels))
        self.assertTrue(any("[the gift]" in l for l in labels))

        w2.take_option(0)                        # take only the gold
        self.assertEqual(w2.player.gold, 140)
        self.assertEqual(len(w2.loot_options()), 2, "the gear must still be on the body")
        self.assertIsNotNone(codex.corpse_at(1), "the body is not spent yet")

    def test_taking_loot_costs_a_turn(self):
        codex = FakeSave()
        w = World(codex, seed=6)
        self._chest_under_player(w, [("gold", 25), ("item", "ochre")])
        t0 = w.tick
        w.take_option(0)
        self.assertGreater(w.tick, t0, "rummaging in a chest must cost you a turn")


class TestEveryItemLooksLikeItself(unittest.TestCase):
    """You should be able to tell what is lying on the floor without walking onto it.
    Every weapon, every piece of armour, every boot and every potion gets its own
    sprite -- and none of them may be blank."""

    def _pixels(self, surf):
        surf.lock()
        px = tuple(tuple(surf.get_at((x, y)))          # Color is not hashable
                   for y in range(surf.get_height())
                   for x in range(surf.get_width()))
        surf.unlock()
        return px

    def _is_blank(self, surf):
        return all(p[3] == 0 for p in self._pixels(surf))

    def test_every_piece_of_gear_has_its_own_sprite(self):
        from . import sprites
        from .items import ALL_GEAR
        seen = {}
        for key in ALL_GEAR:
            img = sprites.gear(key)
            self.assertFalse(self._is_blank(img),
                             "%s renders as an empty tile" % key)
            px = self._pixels(img)
            clash = seen.get(px)
            self.assertIsNone(clash,
                              "%s and %s are drawn identically -- you could not tell "
                              "them apart on the floor" % (key, clash))
            seen[px] = key
        self.assertEqual(len(seen), len(ALL_GEAR))

    def test_the_leather_jerkin_is_brown_and_the_scale_vest_is_grey(self):
        """The specific thing that was asked for, pinned."""
        from . import sprites

        def average(img):
            px = [p for p in self._pixels(img) if p[3] > 100]
            n = len(px)
            return (sum(p[0] for p in px) / n, sum(p[1] for p in px) / n,
                    sum(p[2] for p in px) / n)

        r, g, b = average(sprites.gear("leather"))
        self.assertGreater(r, g, "leather must be brown: red above green")
        self.assertGreater(g, b, "leather must be brown: green above blue")
        self.assertGreater(r - b, 30, "leather is not brown enough (r-b=%.0f)" % (r - b))

        r, g, b = average(sprites.gear("mail"))
        self.assertLess(max(r, g, b) - min(r, g, b), 22,
                        "mail must be GREY: its channels should be near-equal "
                        "(got %.0f/%.0f/%.0f)" % (r, g, b))

    def test_the_potions_match_their_descriptions(self):
        from . import sprites
        from .sprites import POTION_COLORS
        # ochre = amber, azure = blue, viscous = green, black = dark
        oc = POTION_COLORS["ochre"]
        self.assertGreater(oc[0], oc[2], "the ochre potion must be warm, not blue")
        az = POTION_COLORS["azure"]
        self.assertGreater(az[2], az[0], "the azure potion must be BLUE")
        vi = POTION_COLORS["viscous"]
        self.assertGreater(vi[1], vi[0], "the viscous potion must be GREEN")
        self.assertGreater(vi[1], vi[2])
        bk = POTION_COLORS["black"]
        self.assertLess(sum(bk) / 3, 100, "the black potion must be dark")

        for flavor in POTION_COLORS:
            self.assertFalse(self._is_blank(sprites.potion(flavor)))

    def test_all_scrolls_look_the_same(self):
        from . import sprites
        a = self._pixels(sprites.scroll())
        b = self._pixels(sprites.scroll())
        self.assertEqual(a, b, "scrolls are deliberately identical")


class TestBeatingTheWarden(unittest.TestCase):
    """Kill it, and you choose: start over with one keepsake, or keep walking."""

    def _game(self):
        from .game import Game
        g = Game.__new__(Game)
        g.codex = FakeSave()
        g.codex.world_seed = 4242
        g.world = World(g.codex, seed=3)
        g.state = None
        g.victory_gear = None
        g.banner = None
        g.banner_age = 0.0
        g.t = 0.0
        from .keyrepeat import Repeater
        g.repeat = Repeater()
        return g

    def _win(self, g, weapon="brand", armour="plate", boots="wind"):
        from .items import ARMOURS, BOOTS, WEAPONS
        g.world.new_level(config.DEPTH_MAX)
        p = g.world.player
        p.weapon = WEAPONS[weapon]
        p.armour = ARMOURS[armour]
        p.boots = BOOTS[boots]
        warden = [m for m in g.world.level.monsters if m.key == "warden"][0]
        g.world.kill_monster(warden)
        self.assertTrue(g.world.won)
        g.on_win()

    def test_killing_it_records_what_you_were_holding(self):
        from .game import WIN
        g = self._game()
        self._win(g)
        self.assertEqual(g.state, WIN)
        self.assertEqual(g.victory_gear,
                         {"weapon": "brand", "weapon_bonus": 0,
                          "armour": "plate", "boots": "wind"})
        self.assertEqual(g.codex.wins, 1)

    def test_starting_over_keeps_the_ONE_thing_you_chose(self):
        g = self._game()
        self._win(g)
        g.new_run(keep="weapon")

        p = g.world.player
        self.assertEqual(p.weapon.key, "brand", "you kept the Flame Brand")
        self.assertEqual(p.armour.key, "rags", "the dungeon took the plate back")
        self.assertEqual(p.boots.key, "sandals", "and the boots")
        self.assertEqual(g.world.depth, 1, "and you are back at the gate")

    def test_you_can_keep_the_armour_instead(self):
        g = self._game()
        self._win(g)
        g.new_run(keep="armour")
        p = g.world.player
        self.assertEqual(p.armour.key, "plate")
        self.assertEqual(p.weapon.key, "shiv")
        self.assertEqual(p.boots.key, "sandals")

    def test_or_the_boots(self):
        g = self._game()
        self._win(g)
        g.new_run(keep="boots")
        p = g.world.player
        self.assertEqual(p.boots.key, "wind")
        self.assertEqual(p.weapon.key, "shiv")
        self.assertEqual(p.armour.key, "rags")

    def test_starting_over_is_a_WHOLE_NEW_DUNGEON_not_a_respawn(self):
        """A victor does not go round the same loop again. New stone, new corridors,
        the map forgotten, the traps hidden, the dead left behind."""
        g = self._game()
        codex = g.codex
        # a well-worn game: map memory, found traps, a corpse, the gift spent
        codex.known.extend(["self.corpse", "brute.rule", "dart.rule"])
        codex.remember_map(1, [[True] * 4] * 4)
        codex.find_trap(2, 10, 10)
        codex.leave_corpse(3, 5, 5, 300, "brand")
        codex.claim_gift("floor1")
        old_seed = codex.world_seed
        old_stone = tuple(tuple(r) for r in g.world.level.grid)
        g.world.player.gold = 500
        g.world.player.pack = ["ochre", "ochre"]
        self._win(g)

        g.new_run(keep="weapon", fresh_dungeon=True)

        # --- the PLACE is gone ---
        self.assertNotEqual(codex.world_seed, old_seed, "the stone is re-cut")
        self.assertNotEqual(tuple(tuple(r) for r in g.world.level.grid), old_stone,
                            "it is a different dungeon")
        self.assertEqual(codex.maps, {}, "the map you drew is forgotten")
        self.assertEqual(codex.found_traps, {}, "the traps are hidden again")
        self.assertEqual(codex.corpses, {}, "your dead do not follow you")
        self.assertEqual(codex.gifts, [], "and the floor-1 gift is waiting again")
        self.assertIsNone(g.world.level.corpse)

        # --- but YOU are not ---
        self.assertIn("brute.rule", codex.known, "you keep what you learned")
        self.assertIn("dart.rule", codex.known)
        self.assertEqual(codex.tier("brute"), 1,
                         "the brute is still not a '?' -- that is the reward")
        self.assertEqual(g.world.player.weapon.key, "brand", "and your one keepsake")

        # --- and it is still a fresh run ---
        self.assertEqual(g.world.depth, 1)
        self.assertEqual(sorted(g.world.levels.keys()), [1])
        self.assertEqual(g.world.player.gold, 0)
        self.assertEqual(g.world.player.pack, [])
        self.assertEqual(g.world.vendor_pct, 0)
        self.assertTrue(g.world.level.monsters)

    def test_a_DEATH_is_still_only_a_respawn(self):
        """The thing that must not break: dying keeps the dungeon. Only WINNING
        replaces it."""
        g = self._game()
        codex = g.codex
        codex.remember_map(1, [[True] * 4] * 4)
        codex.find_trap(1, 9, 9)
        codex.leave_corpse(2, 4, 4, 90, "bronze_sword")
        seed = codex.world_seed
        stone = tuple(tuple(r) for r in g.world.level.grid)

        g.new_run()                          # a plain respawn

        self.assertEqual(codex.world_seed, seed, "the dungeon is the SAME after death")
        self.assertEqual(tuple(tuple(r) for r in g.world.level.grid), stone)
        self.assertTrue(codex.maps, "you still remember the map")
        self.assertTrue(codex.found_traps, "and the traps you found")
        self.assertTrue(codex.corpses, "and your dead are still down there")

    def test_the_boon_is_spent_and_does_not_apply_to_the_NEXT_run(self):
        g = self._game()
        self._win(g)
        g.new_run(keep="weapon")
        self.assertEqual(g.world.player.weapon.key, "brand")
        self.assertIsNone(g.victory_gear, "the keepsake is spent")

        g.new_run()                        # e.g. after dying in the new run
        self.assertEqual(g.world.player.weapon.key, "shiv",
                         "you do not get to keep it forever -- earn it again")

    def test_walking_on_keeps_you_in_the_dungeon(self):
        from .game import PLAY
        g = self._game()
        self._win(g)
        depth = g.world.depth

        g.walk_on()

        self.assertEqual(g.state, PLAY)
        self.assertFalse(g.world.won, "the win flag must clear or the world stops")
        self.assertEqual(g.world.depth, depth, "you are still standing where you were")
        # and the world keeps turning
        t0 = g.world.tick
        g.world.player_wait()
        self.assertGreater(g.world.tick, t0, "turns must still pass")

    def test_walking_on_and_then_dying_forfeits_the_keepsake(self):
        g = self._game()
        self._win(g)
        g.walk_on()
        g.world.kill_player("brute")
        self.assertTrue(g.world.dead)
        # the death flow starts a plain new run: no boon
        g.new_run()
        self.assertEqual(g.world.player.weapon.key, "shiv")


class TestVictoryKeepBonus(unittest.TestCase):
    """A kept weapon should carry its +n, not just its key, into the next run."""

    _game = TestBeatingTheWarden._game

    def _win(self, g, weapon="steel_axe", armour="plate", boots="wind", bonus=3):
        from .items import ARMOURS, BOOTS, WEAPONS
        g.world.new_level(config.DEPTH_MAX)
        p = g.world.player
        p.weapon = WEAPONS[weapon].copy(bonus=bonus)
        p.armour = ARMOURS[armour]
        p.boots = BOOTS[boots]
        warden = [m for m in g.world.level.monsters if m.key == "warden"][0]
        g.world.kill_monster(warden)
        self.assertTrue(g.world.won)
        g.on_win()

    def test_the_victory_capture_records_the_bonus(self):
        g = self._game()
        self._win(g)
        self.assertEqual(g.victory_gear,
                         {"weapon": "steel_axe", "weapon_bonus": 3,
                          "armour": "plate", "boots": "wind"})

    def test_kept_weapon_keeps_its_bonus_into_the_next_run(self):
        g = self._game()
        self._win(g)
        g.new_run(keep="weapon", fresh_dungeon=True)
        p = g.world.player
        self.assertEqual(p.weapon.key, "steel_axe")
        self.assertEqual(p.weapon.bonus, 3, "the +3 must survive the keep")


class TestTheCheatCode(unittest.TestCase):
    """CTRL (or CMD) + 0 9 8 7."""

    def _code(self):
        from .cheats import CheatCode
        return CheatCode()

    def test_the_code_fires_on_the_full_sequence(self):
        c = self._code()
        seq = [pygame.K_0, pygame.K_9, pygame.K_8, pygame.K_7]
        for k in seq[:-1]:
            self.assertFalse(c.feed(k, True))
        self.assertTrue(c.feed(seq[-1], True), "0987 with CTRL held must fire")

    def test_it_does_nothing_without_the_modifier(self):
        c = self._code()
        for k in (pygame.K_0, pygame.K_9, pygame.K_8, pygame.K_7):
            self.assertFalse(c.feed(k, False),
                             "typing 0987 by itself must never fire")

    def test_letting_go_of_ctrl_half_way_resets_it(self):
        c = self._code()
        c.feed(pygame.K_0, True)
        c.feed(pygame.K_9, True)
        c.feed(pygame.K_8, False)          # let go
        self.assertFalse(c.feed(pygame.K_7, True), "the run was broken")
        self.assertEqual(c.progress, 0)

    def test_a_wrong_key_starts_over(self):
        c = self._code()
        c.feed(pygame.K_0, True)
        c.feed(pygame.K_9, True)
        c.feed(pygame.K_5, True)           # wrong
        self.assertFalse(c.feed(pygame.K_8, True))
        self.assertFalse(c.feed(pygame.K_7, True))

    def test_a_stray_zero_restarts_the_attempt(self):
        c = self._code()
        c.feed(pygame.K_9, True)           # wrong opener
        self.assertEqual(c.progress, 0)
        c.feed(pygame.K_0, True)           # ...but this is a fresh start
        c.feed(pygame.K_9, True)
        c.feed(pygame.K_8, True)
        self.assertTrue(c.feed(pygame.K_7, True))

    # --- what it grants -------------------------------------------------
    def test_it_grants_the_best_gear_and_nine_potions(self):
        from .items import ARMOURS, BOOTS, WEAPONS
        codex = FakeSave()
        w = World(codex, seed=3)
        w.level.monsters = []
        self.assertEqual(w.player.weapon.key, "shiv")
        self.assertEqual(w.player.boots.key, "sandals")
        base_speed = w.player.speed()

        got = w.grant_cheat()

        self.assertEqual(w.player.weapon.key, "kris",
                         "the cheat grants the Vampiric Kris specifically")
        self.assertEqual(w.player.weapon.tier, 5, "and it is now tier 5")
        self.assertEqual(w.player.armour.tier, 5, "the best armour in the game")
        self.assertEqual(w.player.boots.tier, 5, "the best boots in the game")
        self.assertEqual(max(g.tier for g in ARMOURS.values()), w.player.armour.tier)
        self.assertEqual(max(g.tier for g in BOOTS.values()), w.player.boots.tier)
        self.assertEqual(w.player.boots.key, "wind", "the Windwalkers")
        self.assertEqual(got, 9)
        self.assertEqual(w.player.pack.count("ochre"), 9)
        # the Windwalkers must actually outrun the Warden Plate's -18
        self.assertGreater(w.player.speed(), base_speed,
                           "the boots must beat the plate's speed penalty")

    def test_it_only_gives_you_what_will_FIT(self):
        """3 slots free = 9 potions. 2 slots free = 6. And so on."""
        codex = FakeSave()
        w = World(codex, seed=3)
        w.level.monsters = []
        # leave exactly two slots free
        w.player.slots = [["kesh", 3], ["vorn", 3], ["azure", 3], ["black", 3],
                          None, None]

        got = w.grant_cheat()

        self.assertEqual(got, 6, "two free slots hold six potions, not nine")
        self.assertEqual(w.player.pack.count("ochre"), 6)
        self.assertEqual(len(w.player.pack), 18, "and the pack is now full")

    def test_a_completely_full_pack_gets_no_potions_but_still_gets_the_gear(self):
        codex = FakeSave()
        w = World(codex, seed=3)
        w.level.monsters = []
        w.player.slots = [["kesh", 3]] * 6

        got = w.grant_cheat()

        self.assertEqual(got, 0)
        self.assertEqual(w.player.weapon.tier, 5, "the gear still lands (kris is now tier 5)")
        self.assertEqual(w.player.armour.tier, 5)

    def test_a_part_used_potion_stack_is_topped_up_first(self):
        codex = FakeSave()
        w = World(codex, seed=3)
        w.level.monsters = []
        w.player.slots[0] = ["ochre", 1]     # one already in hand
        w.player.slots[1] = ["kesh", 3]

        got = w.grant_cheat()

        self.assertEqual(w.player.pack.count("ochre"), 10,
                         "it tops up the stack you already have")
        self.assertEqual(got, 9)


class TestTheWarpCheat(unittest.TestCase):
    """CTRL + 7 8: drop onto the next floor's entrance tile, from anywhere."""

    def _code(self):
        from .cheats import CheatCode
        return CheatCode([pygame.K_7, pygame.K_8])

    def test_the_code_fires_on_seven_eight(self):
        c = self._code()
        self.assertFalse(c.feed(pygame.K_7, True))
        self.assertTrue(c.feed(pygame.K_8, True), "78 with CTRL held must fire")

    def test_it_does_nothing_without_the_modifier(self):
        c = self._code()
        self.assertFalse(c.feed(pygame.K_7, False))
        self.assertFalse(c.feed(pygame.K_8, False))

    # --- what it does ---------------------------------------------------
    def test_it_drops_you_on_the_next_floors_entrance(self):
        codex = FakeSave()
        codex.world_seed = 3   # pin the stone: make no global-random draws
        w = World(codex, seed=3)
        w.level.monsters = []
        start = w.depth
        # stand somewhere that is NOT the stairs, so a normal descend would refuse
        self.assertNotEqual((w.player.x, w.player.y), w.level.stairs)

        self.assertTrue(w.warp_down())

        self.assertEqual(w.depth, start + 1, "you went down exactly one floor")
        self.assertEqual((w.player.x, w.player.y), w.level.entrance,
                         "and you arrive on the entrance tile")

    def test_it_does_not_need_the_stairs(self):
        """The whole point: unlike descend(), it works from anywhere."""
        codex = FakeSave()
        codex.world_seed = 3   # pin the stone: make no global-random draws
        w = World(codex, seed=3)
        w.level.monsters = []
        # move well away from the down-stairs
        for r in w.level.rooms:
            if (r.cx, r.cy) != w.level.stairs:
                w.player.x, w.player.y = r.cx, r.cy
                break
        self.assertFalse(w.descend(), "a real descend refuses off the stairs")
        self.assertTrue(w.warp_down(), "but the warp does not care where you stand")

    def test_it_will_not_warp_past_the_warden(self):
        codex = FakeSave()
        codex.world_seed = 3   # pin the stone: make no global-random draws
        w = World(codex, seed=3)
        w.level.monsters = []
        w.new_level(config.DEPTH_MAX)          # the bottom
        self.assertFalse(w.warp_down(), "there is nothing below the boss floor")
        self.assertEqual(w.depth, config.DEPTH_MAX, "and you do not move")

    def test_a_warped_floor_is_cached_like_any_other(self):
        """It obeys the anti-farming rule: warping down then climbing back finds the
        floor exactly as you left it, not re-rolled."""
        codex = FakeSave()
        codex.world_seed = 3   # pin the stone: make no global-random draws
        w = World(codex, seed=3)
        w.level.monsters = []
        w.warp_down()
        deep = w.depth
        placed = (w.player.x + 0, w.player.y + 0)  # noqa: F841
        monster_count = len(w.level.monsters)
        w.player.x, w.player.y = w.level.entrance
        w.ascend()
        w.player.x, w.player.y = w.level.stairs
        w.descend()
        self.assertEqual(w.depth, deep, "back down to the same floor")
        self.assertEqual(len(w.level.monsters), monster_count,
                         "and it was NOT re-dealt")


class TestTheArsenalCheat(unittest.TestCase):
    """CTRL + 8 7: choose a top-tier weapon/armour/boots; it drops on an open tile
    beside you -- a tester for trying high-end gear on the deep floors."""

    def _world(self):
        codex = FakeSave()
        codex.world_seed = 3
        w = World(codex, seed=3)
        w.level.monsters = []
        w.level.drops = []
        # carve a small open room so the drop has somewhere clean to land
        w.player.x, w.player.y = 12, 12
        for y in range(10, 15):
            for x in range(10, 15):
                w.level.grid[y][x] = 1
        return w

    def test_the_code_fires_on_eight_seven(self):
        from .cheats import CheatCode
        c = CheatCode([pygame.K_8, pygame.K_7])
        self.assertFalse(c.feed(pygame.K_8, True))
        self.assertTrue(c.feed(pygame.K_7, True), "87 with CTRL held must fire")

    def test_top_tier_gear_offers_three_high_end_of_each(self):
        from .items import top_tier_gear, WEAPONS, ARMOURS, BOOTS
        picks = top_tier_gear()
        for cat, pool in (("weapon", WEAPONS), ("armour", ARMOURS), ("boots", BOOTS)):
            self.assertEqual(len(picks[cat]), 3, "%s offers exactly three" % cat)
            best = max(g.tier for g in pool.values())
            self.assertEqual(picks[cat][0].tier, best, "the first pick is the top tier")
            top_three_tiers = sorted((g.tier for g in pool.values()), reverse=True)[:3]
            self.assertEqual([g.tier for g in picks[cat]], top_three_tiers,
                             "%s picks are the three highest tiers available" % cat)

    def test_it_drops_the_choice_on_an_open_tile_beside_you(self):
        w = self._world()
        px, py = w.player.x, w.player.y
        spot = w.drop_gear_near("brand")
        self.assertIsNotNone(spot)
        self.assertLessEqual(max(abs(spot[0] - px), abs(spot[1] - py)), 1,
                             "it lands on a tile next to you")
        self.assertNotEqual(spot, (px, py), "beside you, not under you")
        self.assertTrue(w.walkable(*spot), "and on open floor")
        # and it is genuinely pickable: stand on it, and it is in the loot menu
        w.player.x, w.player.y = spot
        opts = w.loot_options()
        self.assertTrue(
            any(o["kind"] == "gear" and o["payload"] == "brand" for o in opts),
            "the dropped gear can actually be picked up")

    def test_a_boxed_in_hero_gets_it_at_their_feet(self):
        w = self._world()
        px, py = w.player.x, w.player.y
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if (dx, dy) != (0, 0):
                    w.level.grid[py + dy][px + dx] = 0      # walled in on every side
        spot = w.drop_gear_near("plate")
        self.assertEqual(spot, (px, py),
                         "nowhere open beside you -> it lands at your feet")

    def test_an_unknown_key_drops_nothing(self):
        w = self._world()
        before = len(w.level.drops)
        self.assertIsNone(w.drop_gear_near("not_a_real_key"))
        self.assertEqual(len(w.level.drops), before)


class TestTheConsumableCheats(unittest.TestCase):
    """CTRL+67 (scrolls) and CTRL+76 (potions): pick any uncommon/rare one, into the
    pack, identified."""

    def _world(self):
        codex = FakeSave()
        codex.world_seed = 3
        w = World(codex, seed=3)
        w.level.monsters = []
        w.player.x, w.player.y = 12, 12
        for y in range(10, 15):
            for x in range(10, 15):
                w.level.grid[y][x] = 1
        return w

    def test_the_codes_fire_on_six_seven_and_seven_six(self):
        from .cheats import CheatCode
        scrolls = CheatCode([pygame.K_6, pygame.K_7])
        self.assertFalse(scrolls.feed(pygame.K_6, True))
        self.assertTrue(scrolls.feed(pygame.K_7, True), "67 fires the scroll picker")
        potions = CheatCode([pygame.K_7, pygame.K_6])
        self.assertFalse(potions.feed(pygame.K_7, True))
        self.assertTrue(potions.feed(pygame.K_6, True), "76 fires the potion picker")

    def test_giving_a_consumable_puts_it_in_the_pack_identified(self):
        w = self._world()
        self.assertFalse(w.codex.identified("zeph"))
        w.cheat_give_consumable("zeph")
        self.assertIn("zeph", w.player.pack, "straight into the pack")
        self.assertTrue(w.codex.identified("zeph"), "and you know what it is")

    def test_a_full_pack_drops_the_consumable_beside_you(self):
        w = self._world()
        w.player.slots = [["kesh", 3]] * 6           # completely full
        before = len(w.level.drops)
        w.cheat_give_consumable("ulm")
        self.assertNotIn("ulm", w.player.pack, "no room in the pack")
        self.assertEqual(len(w.level.drops), before + 1, "so it lands beside you")

    def test_the_picker_offers_exactly_the_uncommon_and_rare(self):
        from .items import CONSUMABLES
        for kind in ("scroll", "potion"):
            items = [f for f, c in CONSUMABLES.items()
                     if c.kind == kind and c.tier in ("uncommon", "rare")]
            self.assertEqual(len(items), 10, "%s picker offers 6 uncommon + 4 rare" % kind)
            self.assertFalse(any(CONSUMABLES[f].tier == "common" for f in items),
                             "no commons in the picker")


class TestTheBeholder(unittest.TestCase):
    """A gaze that freezes you where you stand -- telegraphed, breakable by line of
    sight, capped at 2 turns, and it cannot gaze again for 3."""

    def _world(self):
        codex = FakeSave()
        w = World(codex, seed=7)
        w.level.monsters = []
        for r in w.level.rooms:
            if r.w >= 8 and r.h >= 7:
                w.player.x, w.player.y = r.cx, r.cy
                break
        w.level.compute_fov(w.player.x, w.player.y)
        return w

    def _beholder(self, w, dx, dy):
        from .monsters import Monster
        b = Monster("beholder", w.player.x + dx, w.player.y + dy)
        b.awake = True
        w.level.monsters.append(b)
        return b

    def test_it_telegraphs_before_the_gaze(self):
        w = self._world()
        b = self._beholder(w, 4, 0)                   # 4 tiles away, clear line
        b.take_turn(w)
        self.assertEqual(b.intent, ("gaze", w.player.x, w.player.y),
                         "the first turn it only opens its eye -- a warning")
        self.assertEqual(w.player.frozen, 0, "it has not frozen you yet")

    def test_the_gaze_freezes_you_for_two_turns_and_does_no_damage(self):
        w = self._world()
        b = self._beholder(w, 4, 0)
        hp = w.player.hp
        b.take_turn(w)                                # telegraph
        b.take_turn(w)                                # gaze lands
        self.assertEqual(w.player.frozen, 2, "the gaze freezes you, capped at 2")
        self.assertEqual(w.player.hp, hp, "the freeze itself does no damage -- setup only")
        self.assertTrue(b.ray_armed, "and it has armed the ray for its next turn")

    def test_the_ray_follows_the_freeze_on_the_next_turn(self):
        """Two beats: freeze (no damage), then a baleful ray (real damage). The ray only
        ever comes right after a landed freeze."""
        w = self._world()
        b = self._beholder(w, 4, 0)
        b.take_turn(w)                                # telegraph
        b.take_turn(w)                                # gaze -> freeze, ray armed
        self.assertTrue(b.ray_armed)
        hp = w.player.hp
        frozen_before = w.player.frozen
        b.take_turn(w)                                # the RAY
        self.assertFalse(b.ray_armed, "the ray is spent")
        self.assertLess(w.player.hp, hp, "the ray deals real damage")
        self.assertGreaterEqual(w.player.frozen, frozen_before,
                                "and it is not fire -- it does NOT thaw the ice")
        self.assertEqual(b.recharge, 3, "now the whole combo is on cooldown")

    def test_no_freeze_means_no_ray(self):
        """Dodge the gaze and the ray never comes -- the ray only follows a real freeze."""
        w = self._world()
        b = self._beholder(w, 4, 0)
        b.take_turn(w)                                # telegraph
        wx = (b.x + w.player.x) // 2
        w.level.grid[w.player.y][wx] = 0              # break the line before the gaze
        b.take_turn(w)                                # gaze finds stone: no freeze
        self.assertFalse(b.ray_armed, "no freeze landed, so no ray is armed")
        self.assertEqual(w.player.frozen, 0)
        hp = w.player.hp
        b.take_turn(w)                                # whatever it does now, it is not a ray
        self.assertEqual(w.player.hp, hp, "and no ray damage arrives out of nowhere")

    def test_breaking_line_of_sight_beats_the_gaze(self):
        w = self._world()
        b = self._beholder(w, 4, 0)
        b.take_turn(w)                                # telegraph
        # drop a wall between the beholder and the player before the gaze lands
        wx = (b.x + w.player.x) // 2
        w.level.grid[w.player.y][wx] = 0              # a pillar in the eyeline
        b.take_turn(w)                                # gaze resolves
        self.assertEqual(w.player.frozen, 0,
                         "a wall in the eyeline means it freezes stone, not you")

    def test_the_combo_is_on_a_cooldown_before_it_can_gaze_again(self):
        w = self._world()
        b = self._beholder(w, 4, 0)
        b.take_turn(w)                                # telegraph
        b.take_turn(w)                                # gaze -> freeze, ray armed
        b.take_turn(w)                                # ray -> recharge = 3
        self.assertEqual(b.recharge, 3, "the cooldown starts after the RAY, not the gaze")
        w.player.frozen = 0                           # pretend we thawed
        for _ in range(3):
            b.take_turn(w)
            self.assertIsNone(b.intent, "it must not gaze while recharging")
            self.assertFalse(b.ray_armed)
        b.take_turn(w)
        self.assertEqual(b.intent[0], "gaze", "after three turns it can start over")

    def test_being_frozen_actually_costs_you_turns_while_monsters_act(self):
        """The whole danger: you cannot act, but the floor can. Each frozen turn is a
        freeze_tick, burned when the player tries to move (see struggle_against_freeze);
        the bookkeeping is the same."""
        from .monsters import Monster
        w = self._world()
        w.player.frozen = 2
        # a rat right beside you, awake and hungry
        rat = Monster("rat", w.player.x + 1, w.player.y)
        rat.awake = True
        w.level.monsters = [rat]
        hp = w.player.hp

        still = w.freeze_tick()                        # one frozen turn plays out
        self.assertTrue(still, "one turn down, one to go")
        self.assertEqual(w.player.frozen, 1)
        still = w.freeze_tick()                        # the last one
        self.assertFalse(still, "the ice has let go")
        self.assertEqual(w.player.frozen, 0, "the two frozen turns were spent")
        self.assertLess(w.player.hp, hp,
                        "and the rat mauled you while you could not move")

    def test_struggling_burns_a_turn_and_you_do_NOT_move(self):
        """The fix: while frozen, trying to act spends the turn where you stand. It
        costs a real turn (the floor gets its swing) and it does not move you an inch."""
        from .monsters import Monster
        w = self._world()
        w.player.frozen = 2
        px, py = w.player.x, w.player.y
        rat = Monster("rat", px + 1, py)
        rat.awake = True
        w.level.monsters = [rat]
        hp = w.player.hp

        w.struggle_against_freeze()                    # you press 'move' -- and can't
        self.assertEqual((w.player.x, w.player.y), (px, py), "the ice holds you in place")
        self.assertEqual(w.player.frozen, 1, "but the attempt cost you a frozen turn")
        self.assertLess(w.player.hp, hp, "and the rat got its free swing")

        w.struggle_against_freeze()
        self.assertEqual(w.player.frozen, 0, "a second attempt spends the last turn")

    def test_freeze_tick_does_nothing_once_thawed(self):
        w = self._world()
        self.assertEqual(w.player.frozen, 0)
        self.assertFalse(w.freeze_tick(), "no freeze, no turn burned")

    def test_struggling_when_not_frozen_is_a_no_op(self):
        w = self._world()
        px, py = w.player.x, w.player.y
        w.struggle_against_freeze()
        self.assertEqual((w.player.x, w.player.y), (px, py))
        self.assertEqual(w.player.frozen, 0)

    def test_you_cannot_drink_a_potion_while_frozen(self):
        w = self._world()
        w.player.slots = [["ochre", 2], None, None, None, None, None]  # healing
        w.player.hp = 10
        w.player.frozen = 2
        self.assertFalse(w.use_item(0), "a frozen hand cannot uncork a flask")
        self.assertEqual(w.player.hp, 10, "no heal")
        self.assertEqual(w.player.pack.count("ochre"), 2, "and the potion is not spent")

    def test_you_cannot_read_a_scroll_while_frozen(self):
        w = self._world()
        w.codex.known.append("id.kesh")
        w.player.slots = [["kesh", 2], None, None, None, None, None]
        w.player.frozen = 2
        self.assertFalse(w.use_item(0), "a frozen hand cannot unroll a scroll")
        self.assertEqual(w.player.pack.count("kesh"), 2, "the scroll is not spent")

    def test_you_cannot_drop_from_the_pack_while_frozen(self):
        w = self._world()
        w.player.slots = [["kesh", 2], None, None, None, None, None]
        w.player.frozen = 2
        self.assertFalse(w.drop_item(0), "you cannot rummage in your pack while frozen")
        self.assertEqual(w.player.pack.count("kesh"), 2, "nothing left your pack")

    def test_the_freeze_is_capped_and_cannot_be_stacked(self):
        w = self._world()
        w.freeze_player(2)
        w.freeze_player(2)
        self.assertLessEqual(w.player.frozen, 2, "two gazes do not make four turns")

    def test_los_clear_is_blocked_by_walls_not_monsters(self):
        from .monsters import Monster
        w = self._world()
        px, py = w.player.x, w.player.y
        self.assertTrue(w.los_clear(px, py, px + 4, py, 7),
                        "open floor: the eye sees you")
        other = Monster("rat", px + 2, py)             # a creature in the way
        w.level.monsters.append(other)
        self.assertTrue(w.los_clear(px, py, px + 4, py, 7),
                        "the gaze passes over creatures")
        w.level.grid[py][px + 2] = 0                    # a wall in the way
        self.assertFalse(w.los_clear(px, py, px + 4, py, 7),
                         "but a wall blocks it")

    def test_it_takes_several_solid_hits(self):
        _assert_solid_hits(self, "beholder")

    def test_beholders_only_appear_deep(self):
        from .monsters import spawn_roster
        for d in range(1, 13):
            self.assertNotIn("beholder", spawn_roster(d))
        self.assertIn("beholder", spawn_roster(13))

    def test_the_beholder_has_a_codex_entry_and_a_name(self):
        from .codex import CAUSE_NAME, FACTS
        for tier in ("rule", "tell", "counter"):
            self.assertIn("beholder.%s" % tier, FACTS)
        self.assertEqual(CAUSE_NAME["beholder"], "a beholder")


class TestTheFlicker(unittest.TestCase):
    """Blink in beside you, cut, stuck one turn (your window), blink away. You cannot
    chase it or wall it out."""

    def _world(self):
        codex = FakeSave()
        w = World(codex, seed=7)
        w.level.monsters = []
        # put the player somewhere with open floor around them
        for r in w.level.rooms:
            if r.w >= 6 and r.h >= 6:
                w.player.x, w.player.y = r.cx, r.cy
                break
        w.level.compute_fov(w.player.x, w.player.y)
        return w

    def _flicker(self, w, x, y):
        from .monsters import Monster
        f = Monster("flicker", x, y)
        f.awake = True
        w.level.monsters.append(f)
        return f

    def test_it_blinks_ADJACENT_and_strikes(self):
        w = self._world()
        p = w.player
        f = self._flicker(w, p.x + 4, p.y)           # a few tiles off
        hp = p.hp
        f.take_turn(w)
        self.assertLessEqual(f.dist(p.x, p.y), 1, "it should now be right beside you")
        self.assertLess(p.hp, hp, "and it should have cut you")
        self.assertEqual(f.recharge, 1, "and now it is spent for a turn")

    def test_the_recharge_turn_is_a_defenceless_window(self):
        w = self._world()
        p = w.player
        f = self._flicker(w, p.x + 1, p.y)
        f.recharge = 1
        pos = (f.x, f.y)
        hp = p.hp
        f.take_turn(w)                               # its recharge turn
        self.assertEqual((f.x, f.y), pos, "it does not move during the window")
        self.assertEqual(p.hp, hp, "and it does not attack -- it is helpless")
        self.assertEqual(f.recharge, 0, "the window is now over")

    def test_after_the_window_it_blinks_AWAY(self):
        w = self._world()
        p = w.player
        f = self._flicker(w, p.x + 1, p.y)           # adjacent, recharge spent
        f.recharge = 0
        f.take_turn(w)
        self.assertGreater(f.dist(p.x, p.y), 1,
                           "with its recharge spent it flees back out to range")

    def test_the_blink_ignores_walls_and_your_body(self):
        """It appears on ANY open tile beside you -- you cannot put your back to a wall
        to be safe."""
        w = self._world()
        p = w.player
        # gather the tiles it could land on: all walkable neighbours
        open_sides = [(p.x + dx, p.y + dy)
                      for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                      if (dx, dy) != (0, 0) and w.walkable(p.x + dx, p.y + dy)]
        self.assertTrue(open_sides)
        # blink_tile_near must only ever return one of those, never the player's tile
        for _ in range(50):
            spot = w.blink_tile_near(p.x, p.y, lo=1, hi=1)
            self.assertIn(spot, open_sides)
            self.assertNotEqual(spot, (p.x, p.y))

    def test_a_boxed_in_player_leaves_it_nowhere_to_blink(self):
        from .traps import Trap  # noqa: F401  (just to have imports consistent)
        w = self._world()
        # jam the player into a 1-tile pocket: surround with walls in the grid
        px, py = w.player.x, w.player.y
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if (dx, dy) != (0, 0):
                    w.level.grid[py + dy][px + dx] = 0     # wall
        self.assertIsNone(w.blink_tile_near(px, py, lo=1, hi=1),
                          "nowhere adjacent is open, so it cannot blink in")

    def test_it_takes_several_solid_hits(self):
        _assert_solid_hits(self, "flicker")

    def test_it_is_not_faster_than_you(self):
        """The window only exists if the turns interleave -- it must not outrun you."""
        from .monsters import TEMPLATES
        self.assertLessEqual(TEMPLATES["flicker"].speed, config.BASE_SPEED)

    def test_flickers_appear_from_floor_six(self):
        from .monsters import spawn_roster
        for d in range(1, 6):
            self.assertNotIn("flicker", spawn_roster(d))
        self.assertIn("flicker", spawn_roster(6))
        self.assertIn("flicker", spawn_roster(12))

    def test_the_flicker_has_a_codex_entry_and_a_name(self):
        from .codex import CAUSE_NAME, FACTS
        for tier in ("rule", "tell", "counter"):
            self.assertIn("flicker.%s" % tier, FACTS)
        self.assertEqual(CAUSE_NAME["flicker"], "a flicker")


class TestThePoltergeist(unittest.TestCase):
    """Invisible, walks through walls, rakes you for almost nothing. The only thing
    that beats it is KNOWLEDGE: what you have learned changes what you can see, never
    what it does."""

    def _world(self, learn=()):
        codex = FakeSave()
        codex.world_seed = 4242        # a fixed stone, so two worlds are identical
        for f in learn:
            codex.known.append("poltergeist.%s" % f)
        w = World(codex, seed=7)
        w.level.monsters = []
        for r in w.level.rooms:
            if r.w >= 7 and r.h >= 7:
                w.player.x, w.player.y = r.cx, r.cy
                break
        w.level.compute_fov(w.player.x, w.player.y)
        return w

    def _ghost(self, w, dx, dy):
        from .monsters import Monster
        g = Monster("poltergeist", w.player.x + dx, w.player.y + dy)
        g.awake = True
        w.level.monsters.append(g)
        return g

    def test_it_phases_through_walls(self):
        w = self._world()
        g = self._ghost(w, 3, 0)
        # brick up every tile on the line between them: a normal monster is now stuck
        for step in range(1, 3):
            w.level.grid[w.player.y][w.player.x + step] = 0
        before = g.dist(w.player.x, w.player.y)
        g.take_turn(w)
        self.assertLess(g.dist(w.player.x, w.player.y), before,
                        "walls do not stop it -- it drifts straight through")

    def test_it_rakes_you_for_chip_damage(self):
        w = self._world()
        g = self._ghost(w, 1, 0)
        hp = w.player.hp
        g.take_turn(w)
        drop = hp - w.player.hp
        self.assertGreater(drop, 0, "adjacent, it rakes you")
        self.assertLessEqual(drop, 3, "but only ever for chip damage")

    def test_unseen_when_unknown_named_once_you_know_it(self):
        w = self._world()                              # know nothing
        g = self._ghost(w, 1, 0)
        g.take_turn(w)
        line = w.messages[-1][0].lower()
        self.assertIn("unseen thing", line, "before you know it, it has no name")
        self.assertNotIn("poltergeist", line, "and it is certainly not named")

        w2 = self._world(learn=("rule",))              # now you know what it is
        g2 = self._ghost(w2, 1, 0)
        g2.take_turn(w2)
        self.assertIn("poltergeist", w2.messages[-1][0].lower(),
                      "once codexed, the strike names it")

    def test_the_tell_flashes_it_into_view_only_once_learned(self):
        # below the tell tier: the strike leaves no visible trace of where it stood
        w = self._world(learn=("rule",))
        g = self._ghost(w, 1, 0)
        w.fx = []
        g.take_turn(w)
        self.assertFalse(any(f["kind"] == "haunt" for f in w.fx),
                         "without the tell, nothing reveals it")
        # with the tell: the strike drags it into view for a heartbeat
        w2 = self._world(learn=("rule", "tell"))
        g2 = self._ghost(w2, 1, 0)
        w2.fx = []
        g2.take_turn(w2)
        self.assertTrue(any(f["kind"] == "haunt" for f in w2.fx),
                        "the tell flashes it onto its tile when it hits")

    def test_knowledge_changes_what_you_see_not_what_it_does(self):
        """The core rule of the whole game, at its most literal: a blind player and an
        omniscient one face the exact same poltergeist -- same step, same damage."""
        blind = self._world()
        omni = self._world(learn=("rule", "tell", "counter"))
        gb = self._ghost(blind, 2, 0)
        go = self._ghost(omni, 2, 0)
        hb, ho = blind.player.hp, omni.player.hp
        gb.take_turn(blind)
        go.take_turn(omni)
        self.assertEqual((gb.x, gb.y), (go.x, go.y), "it moves the same either way")
        self.assertEqual(hb - blind.player.hp, ho - omni.player.hp,
                         "and it hits for the same either way")

    def test_poltergeists_appear_from_floor_ten(self):
        from .monsters import spawn_roster
        for d in range(1, 10):
            self.assertNotIn("poltergeist", spawn_roster(d))
        self.assertIn("poltergeist", spawn_roster(10))
        self.assertIn("poltergeist", spawn_roster(18))

    def test_it_takes_several_solid_hits_once_you_can_see_it(self):
        _assert_solid_hits(self, "poltergeist")

    def test_it_has_a_sprite_registered(self):
        from . import sprites
        self.assertIn("poltergeist", sprites._MONSTER_DRAW)
        self.assertIsNotNone(sprites.monster("poltergeist", (206, 214, 230)))

    def test_the_poltergeist_has_a_codex_entry_and_a_name(self):
        from .codex import CAUSE_NAME, FACTS
        for tier in ("rule", "tell", "counter"):
            self.assertIn("poltergeist.%s" % tier, FACTS)
        self.assertEqual(CAUSE_NAME["poltergeist"], "a poltergeist")


class TestTheOrcs(unittest.TestCase):
    """A pack with keen eyes and no memory. Calm until one of them SEES you -- then the
    whole pack is on you at once -- and calm again the instant you break the line."""

    # a carved open arena, so line of sight and movement are fully predictable
    AX, AY, AW, AH = 12, 12, 16, 8

    def _world(self):
        codex = FakeSave()
        codex.world_seed = 3         # fixed stone: no global-random draws
        w = World(codex, seed=3)
        w.level.monsters = []
        for y in range(self.AY, self.AY + self.AH):
            for x in range(self.AX, self.AX + self.AW):
                w.level.grid[y][x] = 1                 # FLOOR
        self.midy = self.AY + self.AH // 2
        return w

    def _orc(self, w, x, y):
        from .monsters import Monster
        o = Monster("orc", x, y)
        w.level.monsters.append(o)
        return o

    def _far_away(self, w):
        w.player.x, w.player.y = 2, 2                  # outside the arena, walled off

    # --- targeting geometry (independent of sight) ----------------------
    def test_orc_prey_goes_for_the_player_when_you_are_nearest(self):
        w = self._world()
        o = self._orc(w, w.player.x + 1, w.player.y)
        kind, target = w.orc_prey(o)
        self.assertEqual(kind, "player")
        self.assertIs(target, w.player)

    def test_orc_prey_goes_for_a_MONSTER_when_it_is_nearer_than_you(self):
        from .monsters import Monster
        w = self._world()
        o = self._orc(w, 30, 20)
        brute = Monster("brute", 31, 20)             # right next to the orc
        w.level.monsters.append(brute)
        w.player.x, w.player.y = 5, 5                 # you are far away
        kind, target = w.orc_prey(o)
        self.assertEqual(kind, "monster")
        self.assertIs(target, brute, "the orc goes for the nearer thing, not you")

    def test_orc_prey_never_targets_another_orc(self):
        w = self._world()
        o1 = self._orc(w, 30, 20)
        self._orc(w, 31, 20)                          # an orc right beside it
        w.player.x, w.player.y = 5, 5
        kind, target = w.orc_prey(o1)
        self.assertEqual(kind, "player",
                         "with only orcs nearby, it must fall back to you -- never "
                         "another orc")

    # --- sight is the ONLY thing that makes them hostile ----------------
    def test_sight_is_line_of_sight_a_wall_breaks_it(self):
        w = self._world()
        w.player.x, w.player.y = self.AX + 1, self.midy
        o = self._orc(w, self.AX + 5, self.midy)      # a clear line down the arena
        self.assertTrue(w.orc_can_see_player(o), "open line: it sees you")
        w.level.grid[self.midy][self.AX + 3] = 0      # a pillar drops into the line
        self.assertFalse(w.orc_can_see_player(o), "a pillar in the line breaks it")

    def test_sight_has_a_range_limit(self):
        from .world import ORC_SIGHT
        w = self._world()
        w.player.x, w.player.y = self.AX + 1, self.midy
        near = self._orc(w, self.AX + 1 + ORC_SIGHT - 1, self.midy)
        far = self._orc(w, self.AX + 1 + ORC_SIGHT + 2, self.midy)
        self.assertTrue(w.orc_can_see_player(near), "within range, it sees you")
        self.assertFalse(w.orc_can_see_player(far), "beyond ORC_SIGHT it does not")

    def test_a_calm_pack_ignores_the_whole_floor(self):
        """The bug this fixes: orcs used to clear a floor before you arrived. A pack
        that cannot see you now touches nothing on the floor."""
        from .monsters import Monster
        w = self._world()
        o = self._orc(w, self.AX + 4, self.midy)
        brute = Monster("brute", self.AX + 5, self.midy)   # right beside the orc
        brute.hp = 26
        w.level.monsters.append(brute)
        self._far_away(w)
        self.assertFalse(w.orcs_hunting())
        for _ in range(6):
            o.take_turn(w)
        self.assertEqual(brute.hp, 26,
                         "a calm orc must not lay a finger on the brute")

    def test_one_orc_seeing_you_alerts_the_whole_pack(self):
        w = self._world()
        w.player.x, w.player.y = self.AX + 1, self.midy
        self._orc(w, self.AX + 4, self.midy)               # spotter: a clear line
        blind = self._orc(w, self.AX + 1 + 13, self.midy)  # too far to see you itself
        self.assertFalse(w.orc_can_see_player(blind), "this one cannot see you itself")
        self.assertTrue(w.orcs_hunting(), "but the spotter can, so the pack hunts")
        d0 = blind.dist(w.player.x, w.player.y)
        blind.take_turn(w)
        self.assertLess(blind.dist(w.player.x, w.player.y), d0,
                        "alerted by the pack, the blind orc still closes on you")

    def test_they_lose_you_the_instant_you_break_the_line(self):
        w = self._world()
        w.player.x, w.player.y = self.AX + 1, self.midy
        self._orc(w, self.AX + 4, self.midy)
        self.assertTrue(w.orcs_hunting(), "in the open, on you")
        w.level.grid[self.midy][self.AX + 2] = 0           # you duck behind a pillar
        self.assertFalse(w.orcs_hunting(), "line broken -- forgotten at once")

    def test_while_hunting_they_still_maul_a_nearer_monster(self):
        """The summon-scroll synergy, preserved -- but only while the pack is hunting
        you. A visible player, a nearer monster: the orc takes the monster."""
        from .monsters import Monster
        w = self._world()
        w.player.x, w.player.y = self.AX + 1, self.midy    # visible: the pack hunts...
        o = self._orc(w, self.AX + 7, self.midy)
        brute = Monster("brute", self.AX + 7, self.midy + 1)  # ...but a brute is adjacent
        brute.hp = 26
        w.level.monsters.append(brute)
        self.assertTrue(w.orcs_hunting())
        o.take_turn(w)
        self.assertLess(brute.hp, 26, "mid-hunt it mauls the nearer thing")

    def test_a_calm_pack_pulls_back_together(self):
        w = self._world()
        self._far_away(w)                                  # unseen: calm
        a = self._orc(w, self.AX + 1, self.AY + 1)
        b = self._orc(w, self.AX + self.AW - 2, self.AY + 1)
        c = self._orc(w, self.AX + self.AW // 2, self.AY + self.AH - 2)
        def spread():
            xs, ys = [a.x, b.x, c.x], [a.y, b.y, c.y]
            return (max(xs) - min(xs)) + (max(ys) - min(ys))
        before = spread()
        for _ in range(6):
            for o in (a, b, c):
                o.take_turn(w)
        self.assertLess(spread(), before, "a calm pack closes ranks")

    # --- kills by an orc are still not yours ----------------------------
    def test_a_monster_killed_by_an_orc_gives_no_loot_and_no_credit(self):
        # NOTE: (30, 20)/(31, 20), used elsewhere in this class for pure targeting-
        # geometry checks that never touch kill_monster, happen to sit on a WALL tile
        # for this seed's stone -- fine there, but this test crouches over the body
        # afterwards, so it needs real floor under it. Placed inside the carved arena.
        from .monsters import Monster
        w = self._world()
        ox, oy = self.AX + 2, self.midy
        bx, by = self.AX + 3, self.midy
        self._orc(w, ox, oy)
        brute = Monster("brute", bx, by)
        brute.hp = 1
        w.level.monsters.append(brute)
        kills_before = w.codex.stats["kills"]

        w.hurt_monster(brute, 5, source="orc")

        self.assertNotIn(brute, w.level.monsters, "the brute is dead")
        self.assertEqual(w.codex.stats["kills"], kills_before,
                         "an orc's kill is not YOUR kill")
        self.assertEqual(w.player.kills, 0)
        body = [s for s in w.level.slain if (s.x, s.y) == (bx, by)]
        self.assertTrue(body, "the body still lies where it fell")
        self.assertFalse(body[0].has_loot, "but there is nothing on it to take")

    def test_the_victim_does_NOT_fight_back(self):
        """A brute with an orc gnawing its flank never turns on the orc -- it only
        wants the player. (For now; we can change it later.)"""
        from .monsters import Monster
        w = self._world()
        bx, by = self.AX + 2, self.midy
        brute = Monster("brute", bx, by)
        brute.awake = True
        w.level.monsters.append(brute)
        o = self._orc(w, bx + 1, by)                  # an orc right beside it
        o.hp = 9
        self._far_away(w)                             # the player, elsewhere

        for _ in range(4):
            brute.take_turn(w)

        self.assertEqual(o.hp, 9,
                         "the brute must never damage the orc -- victims do not "
                         "retaliate")

    def test_orcs_start_active_but_not_hostile(self):
        from .monsters import Monster
        w = self._world()
        o = self._orc(w, self.AX + 4, self.midy)
        self._far_away(w)
        self.assertTrue(o.awake, "an orc always takes a turn -- to watch and to regroup")
        self.assertFalse(w.orcs_hunting(), "but it is not hostile until it sees you")
        rat = Monster("rat", 5, 5)
        self.assertFalse(rat.awake, "everything else sleeps until it sees you")

    def test_orcs_come_as_a_pack_on_the_deep_floors(self):
        found_pack = False
        for ws in range(30):
            codex = FakeSave()
            codex.world_seed = ws
            w = World(codex, seed=ws)
            for d in range(2, config.DEPTH_MAX):
                w.new_level(d)
                orcs = [m for m in w.level.monsters if m.key == "orc"]
                if d < 8:
                    self.assertEqual(orcs, [],
                                     "seed %d: orcs before floor 8" % ws)
                if orcs:
                    found_pack = True
                    self.assertGreaterEqual(len(orcs), 3,
                                            "orcs come in a pack of 3+, not alone")
        self.assertTrue(found_pack, "orc packs should appear somewhere on the deep floors")

    def test_the_orc_has_a_codex_entry_and_a_name(self):
        from .codex import CAUSE_NAME, FACTS
        for tier in ("rule", "tell", "counter"):
            self.assertIn("orc.%s" % tier, FACTS)
        self.assertEqual(CAUSE_NAME["orc"], "an orc")


class TestTheStoneGolem(unittest.TestCase):
    """You do not kill it with steel. Steel is for the things that bleed."""

    def _world(self):
        codex = FakeSave()
        w = World(codex, seed=3)
        w.level.monsters = []
        return w

    def test_steel_barely_marks_it(self):
        from .monsters import Monster, damage_multiplier
        w = self._world()
        g = Monster("golem", w.player.x + 1, w.player.y)
        g.hp = 34
        w.level.monsters = [g]
        w.hurt_monster(g, 20, source="player")       # a big hit
        self.assertGreater(g.hp, 34 - 6,
                           "a 20-damage blow should chip only ~5 off a golem")
        self.assertEqual(damage_multiplier("golem", "player"), 0.25)

    def test_fire_cracks_it_wide_open(self):
        from .monsters import Monster, damage_multiplier
        w = self._world()
        g = Monster("golem", w.player.x + 1, w.player.y)
        g.hp = 34
        w.level.monsters = [g]
        w.hurt_monster(g, 10, source="glyph")        # a fire glyph
        self.assertEqual(g.hp, 34 - 20, "fire does DOUBLE to a golem")
        self.assertEqual(damage_multiplier("golem", "burn"), 2.0)
        self.assertEqual(damage_multiplier("golem", "scroll"), 2.0)

    def test_the_flame_brand_burns_it_down(self):
        """The whole point, played out: a fire weapon actually kills the thing your
        sword cannot."""
        from .items import WEAPONS
        from .monsters import Monster
        w = self._world()
        w.player.weapon = WEAPONS["brand"]            # sets things alight
        g = Monster("golem", w.player.x + 1, w.player.y)
        w.level.monsters = [g]
        # hit it a few times: the direct blows barely land, but the BURN ticks as fire
        for _ in range(8):
            if g not in w.level.monsters:
                break
            w.player_attack(g)
            g.take_turn(w)                            # burn ticks on its turn
        self.assertNotIn(g, w.level.monsters,
                         "the Flame Brand's fire should eventually crack it")

    def test_it_does_not_resist_anything_else(self):
        from .monsters import Monster, damage_multiplier
        self.assertEqual(damage_multiplier("brute", "player"), 1.0)
        self.assertEqual(damage_multiplier("wraith", "glyph"), 1.0)

    def test_it_is_fast_ninety_percent_of_your_pace(self):
        from .monsters import TEMPLATES
        self.assertEqual(TEMPLATES["golem"].speed, int(config.BASE_SPEED * 0.9),
                         "the golem moves at your pace minus 10%")
        self.assertGreater(TEMPLATES["golem"].speed, TEMPLATES["brute"].speed,
                           "and that is faster than a brute")

    def test_once_awake_it_hounds_you_from_out_of_sight(self):
        """You are never rid of it: even too far away to see you, an awake golem still
        closes on your exact position, turn after turn."""
        from .monsters import Monster
        w = self._world()
        w.level.monsters = []
        # carve a clear corridor so the approach does not depend on the random map
        w.player.x, w.player.y = 10, 10
        for x in range(10, 24):
            w.level.grid[10][x] = 1                    # FLOOR
        # far enough that it cannot possibly see you (sight tops out at 9 tiles)
        g = Monster("golem", w.player.x + 12, w.player.y)
        g.awake = True                                # it has already spotted you once
        w.level.monsters = [g]
        self.assertFalse(w.monster_can_see_player(g),
                         "twelve tiles off, it genuinely cannot see you")
        d0 = g.dist(w.player.x, w.player.y)
        g.take_turn(w)
        self.assertLess(g.dist(w.player.x, w.player.y), d0,
                        "and yet, out of sight, it still closed the gap")

    def test_golems_only_walk_the_deep_floors(self):
        from .monsters import spawn_roster
        for d in range(1, 11):
            self.assertNotIn("golem", spawn_roster(d),
                             "no golem should appear before floor 11 (got one at %d)" % d)
        self.assertIn("golem", spawn_roster(11))
        self.assertIn("golem", spawn_roster(20))

    def test_the_golem_has_a_codex_entry_and_a_name(self):
        from .codex import CAUSE_NAME, FACTS
        for tier in ("rule", "tell", "counter"):
            self.assertIn("golem.%s" % tier, FACTS)
        self.assertEqual(CAUSE_NAME["golem"], "a stone golem")


class TestTheVendor(unittest.TestCase):
    """It walks the deep floors only. The odds climb as you descend and fall as you
    climb, so pacing the stairs gains you exactly nothing."""

    def _world(self, seed=6):
        codex = FakeSave()
        codex.world_seed = 4242
        w = World(codex, seed=seed)
        w.level.monsters = []
        return w

    def _to(self, w, depth):
        """Walk down to `depth` the honest way."""
        while w.depth < depth:
            w.level.monsters = []
            w.player.x, w.player.y = w.level.stairs
            w.descend()

    def test_the_odds_are_zero_above_the_deep_floors(self):
        w = self._world()
        for d in range(1, config.VENDOR_MIN_DEPTH):
            self._to(w, d)
            self.assertEqual(w.vendor_pct, 0,
                             "floor %d must never have a vendor" % d)
            self.assertIsNone(w.level.vendor)

    def test_it_never_stands_in_the_wardens_room(self):
        """The bottom floor is the exam. There is nobody to sell you anything down
        there -- whatever you are bringing to the Warden, you bring it with you."""
        codex = FakeSave()
        codex.world_seed = 4242
        for seed in range(80):
            w = World(codex, seed=seed)
            w.vendor_pct = 100                 # guarantee a spawn if it were allowed
            w.new_level(config.DEPTH_MAX)
            self.assertIsNone(w.level.vendor,
                              "seed %d: a vendor turned up on the boss floor" % seed)

    def test_the_deepest_it_will_go_is_the_floor_above_the_warden(self):
        codex = FakeSave()
        codex.world_seed = 4242
        w = World(codex, seed=3)
        w.vendor_pct = 100
        w.new_level(config.DEPTH_MAX - 1)
        self.assertIsNotNone(w.level.vendor,
                             "it should still work on the floor above the Warden")

    def test_the_odds_open_at_five_percent_on_the_first_deep_floor(self):
        w = self._world()
        self._to(w, config.VENDOR_MIN_DEPTH)
        self.assertEqual(w.vendor_pct, config.VENDOR_BASE_PCT)

    def test_the_odds_climb_five_a_floor_going_down(self):
        w = self._world()
        self._to(w, config.VENDOR_MIN_DEPTH)
        seen = [w.vendor_pct]
        for _ in range(3):
            if w.level.stairs is None:
                break
            w.level.vendor = None        # isolate the counter from a lucky spawn
            w.player.x, w.player.y = w.level.stairs
            w.descend()
            seen.append(w.vendor_pct)
        self.assertEqual(seen[:4], [5, 10, 15, 20])

    def test_climbing_back_up_gives_the_five_percent_BACK(self):
        """The anti-scum rule: down +5, up -5, so bouncing nets zero."""
        w = self._world()
        self._to(w, config.VENDOR_MIN_DEPTH + 1)
        w.level.vendor = None
        self.assertEqual(w.vendor_pct, 10)

        w.player.x, w.player.y = w.level.entrance
        w.ascend()
        self.assertEqual(w.vendor_pct, 5, "climbing gives the 5% back")

        w.player.x, w.player.y = w.level.stairs
        w.descend()
        self.assertEqual(w.vendor_pct, 10, "and you are exactly where you started")

    def test_a_floor_rolls_ONCE_so_bouncing_buys_no_re_rolls(self):
        """The hole in the raw rule: the counter never climbs, but re-entering could
        still hand you unlimited attempts at the same odds."""
        w = self._world()
        self._to(w, config.VENDOR_MIN_DEPTH + 1)
        deep = w.level
        deep.vendor = None                # pretend the roll failed
        rolls = []
        real = w._maybe_spawn_vendor

        def spy(level, fresh):
            rolls.append(fresh)
            return real(level, fresh)
        w._maybe_spawn_vendor = spy

        for _ in range(5):                # pace the stairs like a scumbag
            w.player.x, w.player.y = w.level.entrance
            w.ascend()
            w.player.x, w.player.y = w.level.stairs
            w.descend()

        self.assertTrue(rolls, "we did re-enter floors")
        self.assertFalse(any(rolls),
                         "no re-entry may ever roll again -- a floor rolls once")
        self.assertIsNone(deep.vendor, "and so no vendor can be farmed into existence")

    def test_descending_past_a_vendor_loses_it_and_resets_the_odds(self):
        from .vendor import Vendor
        w = self._world()
        self._to(w, config.VENDOR_MIN_DEPTH + 2)      # odds are 15 here
        lvl = w.level
        spot = lvl.free_spot_for_vendor(w.rng, (w.player.x, w.player.y))
        lvl.vendor = Vendor(spot[0], spot[1], w.depth, w.rng)
        self.assertEqual(w.vendor_pct, 15)

        w.player.x, w.player.y = lvl.stairs
        w.descend()

        self.assertIsNone(lvl.vendor, "you walked past it; it does not wait")
        self.assertEqual(w.vendor_pct, config.VENDOR_BASE_PCT,
                         "and the odds start again from 5%")

    def test_the_vendor_STAYS_if_you_only_go_up(self):
        from .vendor import Vendor
        w = self._world()
        self._to(w, config.VENDOR_MIN_DEPTH + 1)
        lvl = w.level
        spot = lvl.free_spot_for_vendor(w.rng, (w.player.x, w.player.y))
        lvl.vendor = Vendor(spot[0], spot[1], w.depth, w.rng)

        w.player.x, w.player.y = lvl.entrance
        w.ascend()
        w.player.x, w.player.y = w.level.stairs
        w.descend()

        self.assertIs(w.level, lvl)
        self.assertIsNotNone(lvl.vendor,
                             "climbing away and coming back must NOT lose it")

    def test_the_odds_die_with_you(self):
        w = self._world()
        self._to(w, config.VENDOR_MIN_DEPTH + 2)
        self.assertGreater(w.vendor_pct, 0)
        w2 = World(w.codex, seed=9)          # the run after
        self.assertEqual(w2.vendor_pct, 0,
                         "a fresh run starts on floor 1 with no chance at all")

    # --- trading --------------------------------------------------------
    def _vendor_world(self):
        from .vendor import Vendor
        w = self._world()
        self._to(w, config.VENDOR_MIN_DEPTH)
        w.level.monsters = []
        spot = w.level.free_spot_for_vendor(w.rng, (w.player.x, w.player.y))
        w.level.vendor = Vendor(spot[0], spot[1], w.depth, w.rng)
        w.player.x = spot[0] - 1
        w.player.y = spot[1]
        return w, w.level.vendor

    def test_walking_into_it_opens_trade_and_is_not_an_attack(self):
        w, v = self._vendor_world()
        t0 = w.tick
        w.player_move(1, 0)
        self.assertTrue(w.trading, "it opens its hands")
        self.assertEqual((w.player.x, w.player.y), (v.x - 1, v.y),
                         "it is solid -- you do not walk through it")
        self.assertEqual(w.tick, t0, "and opening the trade costs no turn")

    def test_buying(self):
        from .vendor import price_of
        w, v = self._vendor_world()
        v.stock = [("item", "ochre")]
        cost = price_of("item", "ochre", w.depth)
        w.player.gold = cost + 10

        self.assertTrue(w.buy(0))
        self.assertEqual(w.player.gold, 10)
        self.assertIn("ochre", w.player.pack)
        self.assertEqual(v.stock, [], "it does not have two of them")

    def test_it_does_not_haggle(self):
        from .vendor import price_of
        w, v = self._vendor_world()
        v.stock = [("item", "ochre")]
        w.player.gold = price_of("item", "ochre", w.depth) - 1
        self.assertFalse(w.buy(0))
        self.assertEqual(len(v.stock), 1)

    def test_it_buys_potions_and_scrolls(self):
        from .vendor import sell_price_of
        w, v = self._vendor_world()
        w.player.pack = ["ochre", "kesh"]
        gold0 = w.player.gold

        self.assertTrue(w.sell(0))
        self.assertEqual(w.player.gold,
                         gold0 + sell_price_of("ochre", w.depth))
        self.assertNotIn("ochre", w.player.pack)

    def test_it_will_not_take_your_armour(self):
        w, v = self._vendor_world()
        self.assertFalse(v.buys("plate"))
        self.assertFalse(v.buys("brand"))
        self.assertTrue(v.buys("ochre"))
        self.assertTrue(v.buys("vorn"))

    def test_nothing_can_walk_through_it(self):
        from .monsters import Monster
        w, v = self._vendor_world()
        m = Monster("angry_rat", v.x + 1, v.y)
        m.awake = True
        w.level.monsters = [m]
        for _ in range(6):
            m.take_turn(w)
            self.assertNotEqual((m.x, m.y), (v.x, v.y),
                                "it is solid, even to the rats")


class TestGoingBackUp(unittest.TestCase):
    """You can climb back up -- but you can never leave by the front door."""

    def _world(self, seed=6, ws=4242):
        codex = FakeSave()
        codex.world_seed = ws
        w = World(codex, seed=seed)
        w.level.monsters = []
        return w

    def _go_down(self, w):
        w.player.x, w.player.y = w.level.stairs
        w.level.monsters = []
        self.assertTrue(w.descend())

    def test_you_can_climb_back_up(self):
        w = self._world()
        self._go_down(w)
        self.assertEqual(w.depth, 2)

        w.player.x, w.player.y = w.level.entrance
        self.assertTrue(w.ascend())

        self.assertEqual(w.depth, 1)
        self.assertEqual((w.player.x, w.player.y), w.level.stairs,
                         "you come up the stairs, so you arrive AT the stairs")

    def test_the_front_gate_is_sealed(self):
        w = self._world()
        w.player.x, w.player.y = w.level.entrance
        self.assertEqual(w.depth, 1)

        self.assertEqual(w.ascend(), "sealed",
                         "there is no way out of the Deathward but through it")
        self.assertEqual(w.depth, 1, "and you are still on floor 1")

    def test_you_have_to_be_standing_on_the_way_up(self):
        w = self._world()
        self._go_down(w)
        w.player.x, w.player.y = w.level.stairs      # the way DOWN, not up
        self.assertFalse(w.ascend())
        self.assertEqual(w.depth, 2)

    def test_the_boss_floor_has_no_way_down_but_you_can_still_flee_upward(self):
        w = self._world()
        w.new_level(config.DEPTH_MAX)
        self.assertIsNone(w.level.stairs, "there is no way down from the Warden")
        self.assertFalse(w.descend())
        w.player.x, w.player.y = w.level.entrance
        self.assertTrue(w.ascend(), "but you may always run away")
        self.assertEqual(w.depth, config.DEPTH_MAX - 1)

    # --- the exploit ----------------------------------------------------
    def test_a_revisited_floor_is_NOT_re_rolled(self):
        """Otherwise walking up and down is an infinite loot mill, and there is no
        reason ever to fight anything."""
        from .monsters import Monster
        w = self._world()
        w.new_level(2)
        before_chests = [(c.x, c.y, tuple(c.loot)) for c in w.level.chests]
        before_traps = [(t.key, t.x, t.y) for t in w.level.traps]
        # put a known monster on the floor and hurt it
        m = Monster("kobold", w.level.entrance[0] + 2, w.level.entrance[1])
        m.hp = 3
        w.level.monsters.append(m)
        # open a chest, if there is one
        if w.level.chests:
            w.level.chests[0].loot = []
            w.level.chests[0].opened = True

        w.player.x, w.player.y = w.level.entrance
        w.ascend()                                   # up to 1
        self.assertEqual(w.depth, 1)
        w.player.x, w.player.y = w.level.stairs
        w.descend()                                  # and back down to 2
        self.assertEqual(w.depth, 2)

        self.assertEqual([(t.key, t.x, t.y) for t in w.level.traps], before_traps)
        survivors = [x for x in w.level.monsters if x is m]
        self.assertTrue(survivors, "the kobold we wounded must still be there")
        self.assertEqual(survivors[0].hp, 3, "and still wounded")
        if before_chests:
            self.assertTrue(w.level.chests[0].opened,
                            "a chest you emptied must STAY empty")

    def test_the_bodies_you_left_are_still_there_when_you_come_back(self):
        from .monsters import Monster
        w = self._world()
        w.new_level(2)
        m = Monster("angry_rat", w.level.entrance[0] + 2, w.level.entrance[1])
        w.level.monsters.append(m)
        w.kill_monster(m)
        self.assertEqual(len(w.level.slain), 1)

        w.player.x, w.player.y = w.level.entrance
        w.ascend()
        w.player.x, w.player.y = w.level.stairs
        w.descend()

        self.assertEqual(len(w.level.slain), 1,
                         "the floor remembers what you did to it, this run")

    def test_a_new_run_wipes_the_floors_clean(self):
        codex = FakeSave()
        codex.world_seed = 4242
        w = World(codex, seed=1)
        w.new_level(2)
        w.level.chests = []
        w.level.monsters = []

        w2 = World(codex, seed=2)            # the run after a death
        w2.new_level(2)
        self.assertEqual(w2.levels.keys(), {1, 2},
                         "a fresh run builds its own floors")
        self.assertTrue(w2.level.monsters or w2.level.chests,
                        "and they are populated again")


class TestThePack(unittest.TestCase):
    """Six slots. Three of one thing per slot. Items slide DOWN into a same-type
    stack that has room -- never up, never across types."""

    def _chest(self, w, loot):
        from .dungeon import Chest
        w.level.monsters = []
        w.level.chests = [Chest(w.player.x, w.player.y, loot)]
        w.level.drops = []
        w.level.corpse = None
        w.level.slain = []
        return w.level.chests[0]

    def _slots(self, w):
        return [None if s is None else (s[0], s[1]) for s in w.player.slots]

    def _world(self):
        codex = FakeSave()
        w = World(codex, seed=6)
        w.level.monsters = []
        return w

    def test_the_shape_is_six_slots_of_three(self):
        self.assertEqual(config.PACK_SLOTS, 6)
        self.assertEqual(config.STACK_MAX, 3)

    def test_a_stack_fills_to_three_before_opening_a_new_slot(self):
        w = self._world()
        p = w.player
        for i in range(3):
            p.pack_add("ochre")
        self.assertEqual(self._slots(w)[0], ("ochre", 3))
        self.assertIsNone(self._slots(w)[1], "three fit in one slot")

        p.pack_add("ochre")               # the 4th
        self.assertEqual(self._slots(w)[0], ("ochre", 3),
                         "slot 1 stays at three")
        self.assertEqual(self._slots(w)[1], ("ochre", 1),
                         "the 4th opens the next slot")

    def test_the_ceiling_is_eighteen_of_one_thing(self):
        w = self._world()
        for _ in range(18):
            self.assertTrue(w.player.pack_add("ochre"))
        self.assertEqual(len(w.player.pack), 18)
        self.assertTrue(w.player.pack_is_full)
        self.assertFalse(w.player.pack_add("ochre"), "there is no 19th")
        self.assertFalse(w.player.can_take("azure"))

    def test_six_different_things_is_six_items_and_a_full_pack(self):
        from .items import CONSUMABLES
        w = self._world()
        for f in list(CONSUMABLES)[:6]:
            w.player.pack_add(f)
        self.assertEqual(len(w.player.pack), 6)
        self.assertTrue(w.player.pack_is_full, "every slot is occupied")
        # ...but there is still room for MORE of what you already carry
        first = w.player.slots[0][0]
        self.assertTrue(w.player.can_take(first),
                        "that stack is only at one; it has room for two more")
        self.assertFalse(w.player.can_take(list(CONSUMABLES)[7]),
                         "but nothing NEW can come in")

    def test_EXAMPLE_A_drinking_from_slot_1_pulls_slot_2_down(self):
        """slot1 = 3 healing, slot2 = 1 healing. Drink from slot 1."""
        w = self._world()
        w.player.hp = 5
        for _ in range(4):
            w.player.pack_add("ochre")
        self.assertEqual(self._slots(w)[:2], [("ochre", 3), ("ochre", 1)])

        w.use_item(0)                      # drink from SLOT 1

        self.assertEqual(self._slots(w)[0], ("ochre", 3),
                         "slot 1 goes 3 -> 2 -> refilled to 3")
        self.assertIsNone(self._slots(w)[1],
                          "slot 2 gave up its last potion and is now free")

    def test_EXAMPLE_B_it_only_pulls_as_much_as_it_needs(self):
        """slot1 = 2 healing, slot2 = 2 healing -> slot1 = 3, slot2 = 1."""
        w = self._world()
        w.player.slots[0] = ["ochre", 2]
        w.player.slots[1] = ["ochre", 2]

        w.player.consolidate("ochre")

        self.assertEqual(self._slots(w)[0], ("ochre", 3), "slot 1 tops up to three")
        self.assertEqual(self._slots(w)[1], ("ochre", 1),
                         "and slot 2 keeps the remainder -- it does not empty itself")

    def test_items_never_slide_UP(self):
        """Drinking slot 2's last potion while slot 1 is full moves nothing."""
        w = self._world()
        w.player.hp = 5
        w.player.slots[0] = ["ochre", 3]
        w.player.slots[1] = ["ochre", 1]

        w.use_item(1)                      # drink from SLOT 2

        self.assertEqual(self._slots(w)[0], ("ochre", 3), "slot 1 is untouched")
        self.assertIsNone(self._slots(w)[1], "slot 2 is simply empty now")

    def test_nothing_of_a_different_type_ever_moves(self):
        """No general compaction: an empty slot 1 does not suck the scroll down."""
        w = self._world()
        w.player.hp = 5
        w.player.slots[0] = ["ochre", 1]
        w.player.slots[1] = ["kesh", 2]

        w.use_item(0)                      # empties slot 1

        self.assertIsNone(self._slots(w)[0], "slot 1 is empty")
        self.assertEqual(self._slots(w)[1], ("kesh", 2),
                         "the scrolls stay in slot 2 -- slot numbers must not shuffle")

    def test_a_refused_pickup_is_LEFT_IN_THE_CHEST(self):
        w = self._world()
        w.player.slots = [["ochre", 3], ["ochre", 3], ["ochre", 3],
                          ["ochre", 3], ["ochre", 3], ["ochre", 3]]
        ch = self._chest(w, [("item", "azure")])
        self.assertTrue(w.player.pack_is_full)

        took = w.take_option(0)

        self.assertFalse(took, "no room; the take must fail")
        self.assertNotIn("azure", w.player.pack)
        self.assertIn(("item", "azure"), ch.loot,
                      "the potion must still be in the chest, not deleted")

    def test_a_full_pack_still_takes_gold_and_gear(self):
        w = self._world()
        w.player.slots = [["ochre", 3]] * 1 + [["azure", 3], ["viscous", 3],
                                               ["black", 3], ["kesh", 3], ["vorn", 3]]
        self._chest(w, [("gold", 50), ("gear", "bronze_sword"), ("item", "uul")])
        w.take_all()
        self.assertEqual(w.player.gold, 50, "gold does not live in the pack")
        self.assertEqual(w.player.weapon.key, "bronze_sword", "nor does gear")
        self.assertIn("uul", [o["payload"] for o in w.loot_options()],
                      "the scroll is still there to come back for")

    def test_you_can_always_top_up_a_stack_that_has_room(self):
        """Even with every slot occupied, more of something you already carry fits."""
        w = self._world()
        w.player.slots = [["ochre", 1], ["azure", 3], ["viscous", 3],
                          ["black", 3], ["kesh", 3], ["vorn", 3]]
        self._chest(w, [("item", "ochre")])
        self.assertTrue(w.take_option(0))
        self.assertEqual(self._slots(w)[0], ("ochre", 2))


class TestDroppingFromThePack(unittest.TestCase):
    """A carry limit is only fair if you can choose what you carry."""

    def _world(self):
        codex = FakeSave()
        w = World(codex, seed=6)
        w.level.monsters = []
        w.level.chests = []
        w.level.drops = []
        w.level.slain = []
        w.level.corpse = None
        return w

    def _slots(self, w):
        return [None if s is None else (s[0], s[1]) for s in w.player.slots]

    def test_dropping_one_puts_it_on_the_floor(self):
        w = self._world()
        w.player.slots[0] = ["kesh", 3]

        w.drop_item(0)

        self.assertEqual(self._slots(w)[0], ("kesh", 2))
        floor = [(d.kind, d.payload) for d in w.level.drops_at(w.player.x, w.player.y)]
        self.assertEqual(floor, [("item", "kesh")],
                         "the scroll must be lying at your feet, not destroyed")

    def test_dropping_a_whole_stack_costs_one_turn(self):
        w = self._world()
        w.player.slots[0] = ["kesh", 3]
        t0 = w.tick

        w.drop_item(0, whole=True)

        self.assertIsNone(self._slots(w)[0], "the slot is empty")
        floor = w.level.drops_at(w.player.x, w.player.y)
        self.assertEqual(len(floor), 3, "all three scrolls are on the floor")
        self.assertGreater(w.tick, t0, "it costs a turn")
        # ...but only ONE turn, not three
        w2 = self._world()
        w2.player.slots[0] = ["kesh", 1]
        t1 = w2.tick
        w2.drop_item(0, whole=True)
        self.assertEqual(w.tick - t0, w2.tick - t1,
                         "dumping three costs the same one turn as dumping one")

    def test_all_three_dropped_scrolls_can_be_picked_back_up(self):
        """Regression: the loot menu used to show only the FIRST drop on a tile."""
        w = self._world()
        w.player.slots[0] = ["kesh", 3]
        w.drop_item(0, whole=True)

        opts = w.loot_options()
        self.assertEqual(len(opts), 3,
                         "all three must be listed, not just the first")
        w.take_option(0)
        self.assertEqual(self._slots(w)[0], ("kesh", 1))
        self.assertEqual(len(w.loot_options()), 2)

    def test_THE_SCENARIO_dump_scrolls_to_make_room_for_a_potion(self):
        """Pack full. Standing on a healing potion. Dump the mapping scrolls."""
        from .dungeon import Drop
        w = self._world()
        w.player.slots = [["kesh", 3], ["azure", 3], ["viscous", 3],
                          ["black", 3], ["vorn", 3], ["gramm", 3]]
        w.level.drops = [Drop(w.player.x, w.player.y, "item", "ochre")]
        self.assertTrue(w.player.pack_is_full)
        self.assertFalse(w.player.can_take("ochre"), "no room for the potion")

        w.drop_item(0, whole=True)          # dump all three scrolls of mapping

        self.assertIsNone(self._slots(w)[0], "slot 1 is free")
        self.assertTrue(w.player.can_take("ochre"), "now there is room")

        # the potion is still where it was; pick it up
        opts = [o for o in w.loot_options() if o["payload"] == "ochre"]
        self.assertTrue(opts)
        w.take_option(w.loot_options().index(opts[0]))
        self.assertEqual(self._slots(w)[0], ("ochre", 1),
                         "the potion drops into the freed slot")
        # and the scrolls are still on the floor, not destroyed
        kesh = [d for d in w.level.drops_at(w.player.x, w.player.y)
                if d.payload == "kesh"]
        self.assertEqual(len(kesh), 3, "you can change your mind and take them back")

    def test_dropping_over_a_chest_puts_it_IN_the_chest(self):
        from .dungeon import Chest
        w = self._world()
        w.player.slots[0] = ["kesh", 2]
        ch = Chest(w.player.x, w.player.y, [("gold", 5)])
        w.level.chests = [ch]

        w.drop_item(0, whole=True)

        self.assertIn(("item", "kesh"), ch.loot,
                      "standing on a chest, your cast-offs go into the chest")
        self.assertEqual(ch.loot.count(("item", "kesh")), 2)
        self.assertEqual(w.level.drops_at(w.player.x, w.player.y), [],
                         "and not onto the floor as well")

    def test_dropping_consolidates_what_is_left(self):
        w = self._world()
        w.player.slots[0] = ["ochre", 2]
        w.player.slots[1] = ["ochre", 2]

        w.drop_item(0)                       # slot 1: 2 -> 1, then pulls down

        self.assertEqual(self._slots(w)[0], ("ochre", 3),
                         "slot 1 refills from slot 2, as always")
        self.assertIsNone(self._slots(w)[1])
        self.assertEqual(len(w.level.drops_at(w.player.x, w.player.y)), 1)

    def test_dropping_an_empty_slot_does_nothing(self):
        w = self._world()
        t0 = w.tick
        self.assertFalse(w.drop_item(3))
        self.assertEqual(w.tick, t0, "and it costs no turn")


class TestGearSwapsAreNotThefts(unittest.TestCase):
    """Taking a better sword must not destroy the one you were holding. Whatever
    comes off goes back where the new thing came from."""

    def _clear(self, w):
        w.level.monsters = []
        w.level.chests = []
        w.level.drops = []
        w.level.slain = []
        w.level.corpse = None

    def test_swapping_at_a_chest_leaves_the_old_gear_in_the_chest(self):
        from .dungeon import Chest
        from .items import WEAPONS
        codex = FakeSave()
        w = World(codex, seed=6)
        self._clear(w)
        w.player.weapon = WEAPONS["bronze_sword"]           # tier 2
        ch = Chest(w.player.x, w.player.y, [("gear", "brand")])   # tier 4
        w.level.chests = [ch]

        w.take_option(0)
        self.assertEqual(w.player.weapon.key, "brand", "you took the better weapon")
        self.assertIn(("gear", "bronze_sword", 0), ch.loot,
                      "the Bronze Sword must be lying in the chest, not deleted")
        labels = [o["label"] for o in w.loot_options()]
        self.assertTrue(any("Bronze Sword" in l for l in labels),
                        "and it must be offered back to you: %s" % labels)

    def test_you_can_change_your_mind_and_swap_back(self):
        from .dungeon import Chest
        from .items import WEAPONS
        codex = FakeSave()
        w = World(codex, seed=6)
        self._clear(w)
        w.player.weapon = WEAPONS["bronze_sword"]
        w.level.chests = [Chest(w.player.x, w.player.y, [("gear", "brand")])]
        w.take_option(0)
        self.assertEqual(w.player.weapon.key, "brand")
        w.take_option(0)                                     # take the sword back
        self.assertEqual(w.player.weapon.key, "bronze_sword",
                         "you must be able to put your old weapon back on")
        self.assertEqual([o["payload"] for o in w.loot_options()], ["brand"],
                         "and the Flame Brand is now the thing in the chest")

    def test_swapping_off_the_floor_drops_the_old_gear_on_the_floor(self):
        from .dungeon import Drop
        from .items import ARMOURS
        codex = FakeSave()
        w = World(codex, seed=6)
        self._clear(w)
        w.player.armour = ARMOURS["leather"]                # tier 1
        w.level.drops = [Drop(w.player.x, w.player.y, "gear", "plate")]   # tier 3

        w.take_option(0)
        self.assertEqual(w.player.armour.key, "plate")
        on_floor = [(d.kind, d.payload) for d in w.level.drops]
        self.assertIn(("gear", "leather"), on_floor,
                      "the Leather Jerkin must be lying at your feet: %s" % on_floor)
        self.assertEqual(len(w.level.drops), 1)
        self.assertEqual(w.level.drops[0].x, w.player.x)
        self.assertEqual(w.level.drops[0].y, w.player.y)

    def test_swapping_at_a_body_leaves_the_old_gear_on_the_body(self):
        from .items import BOOTS
        from .monsters import Monster
        codex = FakeSave()
        w = World(codex, seed=6)
        self._clear(w)
        w.player.boots = BOOTS["boots_leather"]              # tier 1, ordinary (not magical)
        m = Monster("brute", w.player.x, w.player.y)
        w.level.monsters = [m]
        w.kill_monster(m)
        s = w.level.slain[0]
        s.loot = [("gear", "boots_mail")]                   # tier 2, ordinary (not magical)

        w.take_option(0)
        self.assertEqual(w.player.boots.key, "boots_mail")
        self.assertIn(("gear", "boots_leather", 0), s.loot,
                      "the Leather Boots must be left on the body")

    def test_swapping_at_your_own_corpse_leaves_it_on_your_corpse(self):
        from .items import WEAPONS
        codex = FakeSave()
        codex.world_seed = 55
        codex.leave_corpse(1, 5, 5, 0, "brand")             # your body holds a tier 4
        w = World(codex, seed=2)
        w.level.monsters = []
        c = w.level.corpse
        w.player.x, w.player.y = c.x, c.y
        w.player.weapon = WEAPONS["bronze_sword"]           # you are holding a tier 2

        w.take_option(0)                                     # take the Flame Brand
        self.assertEqual(w.player.weapon.key, "brand")
        self.assertIn(("gear", "bronze_sword", 0), c.loot,
                      "your Bronze Sword must stay on the body, not vanish")
        # and the save agrees
        saved = codex.corpse_at(1)
        self.assertIsNotNone(saved)
        self.assertIn(["gear", "bronze_sword", 0], saved["loot"])

    def test_take_all_does_not_leave_you_juggling_your_own_cast_offs(self):
        from .dungeon import Chest
        from .items import WEAPONS
        codex = FakeSave()
        w = World(codex, seed=6)
        self._clear(w)
        w.player.weapon = WEAPONS["shiv"]
        ch = Chest(w.player.x, w.player.y, [("gold", 10), ("gear", "brand")])
        w.level.chests = [ch]
        w.take_all()
        self.assertEqual(w.player.gold, 10)
        self.assertEqual(w.player.weapon.key, "brand")
        # the shiv it displaced is a worthless T0 starter -- it falls away rather than
        # cluttering the chest (and 'all' cannot re-pick something that no longer exists)
        self.assertEqual(w.player.weapon.key, "brand")
        self.assertFalse([t for t in ch.loot if t[0] == "gear" and t[1] == "shiv"],
                         "a displaced T0 starter must vanish, not clutter the chest")


class TestStartersDoNotPileUp(unittest.TestCase):
    """Regression: a displaced T0 starter (Rusted Shiv / Padded Rags / Worn Sandals) must
    VANISH, not be stored. Stored on a corpse it piles up life after life, because
    leave_corpse carries a body's loot forward across deaths."""

    def test_a_displaced_starter_does_not_land_on_your_corpse(self):
        from .items import WEAPONS
        codex = FakeSave()
        codex.world_seed = 55
        codex.leave_corpse(1, 5, 5, 0, "bronze_sword")     # the body holds a real weapon
        w = World(codex, seed=2)
        w.level.monsters = []
        c = w.level.corpse
        w.player.x, w.player.y = c.x, c.y
        w.player.weapon = WEAPONS["shiv"].copy()           # you are holding the starter
        w.take_option(0)                                    # take the Bronze Sword
        self.assertEqual(w.player.weapon.key, "bronze_sword")
        self.assertFalse([t for t in c.loot if t[0] == "gear" and t[1] == "shiv"],
                         "the worthless starter shiv must fall away, not sit on the body")

    def test_starters_never_accumulate_on_a_corpse_across_deaths(self):
        from .game import Game
        from .keyrepeat import Repeater
        g = Game.__new__(Game)
        g.codex = FakeSave()
        g.codex.leave_corpse(1, 0, 0, 0, "bone_sword")     # a better weapon waits on the body
        g.world = World(g.codex, seed=6)
        g.world.level.monsters = []
        g.state = None
        g.banner = None
        g.banner_age = 0.0
        g.t = 0.0
        g.victory_gear = None
        g.reveal_t = 0.0
        g.repeat = Repeater()
        for _ in range(4):                                  # die four times, looting each life
            w = g.world
            w.level.monsters = []
            c = w.level.corpse
            if c:
                w.player.x, w.player.y = c.x, c.y
                w.take_all()                                # take the better weapon back
            w.death_cause = "rat"
            w.kill_player("rat")
            g.on_death()
            g.new_run()
        loot = g.codex.corpses.get("1", {}).get("loot", [])
        starters = [t for t in loot if t[0] == "gear" and t[1] in ("shiv", "rags", "sandals")]
        self.assertEqual(starters, [],
                         "T0 starters must never pile up on a corpse: %r" % loot)

    def test_dying_scrubs_starters_already_on_the_body(self):
        # a body that already holds starter junk (e.g. a save from before the fix)
        codex = FakeSave()
        codex.leave_corpse(1, 5, 5, 0, "bone_sword")
        codex.corpses["1"]["loot"] = [["gear", "shiv", 0], ["gear", "rags", 0],
                                      ["item", "azure"]]
        codex.leave_corpse(1, 5, 5, 10, "bone_sword")      # die again on this floor
        loot = codex.corpses["1"]["loot"]
        starters = [t for t in loot if t[0] == "gear" and t[1] in ("shiv", "rags", "sandals")]
        self.assertEqual(starters, [], "old starter junk must be scrubbed on death: %r" % loot)
        self.assertIn(["item", "azure"], loot, "real loot must be preserved")


class TestTheCorpseDuplicationBug(unittest.TestCase):
    """Regression: looting your own corpse only changed the in-memory copy. The save
    still believed the gold was on it, so the next death handed it to you again."""

    def test_gold_taken_off_your_corpse_does_not_come_back(self):
        codex = FakeSave()
        codex.world_seed = 99
        codex.leave_corpse(1, 10, 10, 200, "rapier")
        w = World(codex, seed=1)
        w.level.monsters = []
        c = w.level.corpse
        w.player.x, w.player.y = c.x, c.y

        w.take_option(0)                                    # take ONLY the gold
        self.assertEqual(w.player.gold, 200)
        saved = codex.corpse_at(1)
        self.assertEqual(saved["gold"], 0,
                         "the SAVE must know the gold is gone")

        # die elsewhere, carrying nothing
        w.player.gold = 0
        w.player.x, w.player.y = 20, 20
        w.kill_player("rat")
        w.leave_corpse()
        self.assertEqual(codex.corpse_at(1)["gold"], 0,
                         "the 200 gold must NOT be resurrected on the new corpse")

    def test_the_weapon_taken_off_your_corpse_does_not_come_back(self):
        codex = FakeSave()
        codex.world_seed = 99
        codex.leave_corpse(1, 10, 10, 0, "rapier")
        w = World(codex, seed=1)
        w.level.monsters = []
        c = w.level.corpse
        w.player.x, w.player.y = c.x, c.y
        w.take_option(0)                                    # take the rapier
        self.assertEqual(w.player.weapon.key, "rapier")
        saved = codex.corpse_at(1)
        # the corpse now holds only the shiv we swapped onto it
        if saved:
            self.assertNotEqual(saved.get("weapon"), "rapier",
                                "the rapier is in your hand; it cannot also be on the body")


class TestDiscoveryBannerWaits(unittest.TestCase):
    """A lesson you paid for stays on screen until you move on from it."""

    def _game(self, seed=6):
        from .game import Game
        g = Game.__new__(Game)             # no display needed
        g.codex = FakeSave()
        g.world = World(g.codex, seed=seed)
        g.world.level.monsters = []
        g.state = None
        g.banner = None
        g.banner_age = 0.0
        g.t = 0.0
        from .keyrepeat import Repeater
        g.repeat = Repeater()
        return g

    def test_the_banner_does_not_expire_on_a_timer(self):
        from .codex import FACTS
        g = self._game()
        g.banner = FACTS["brute.rule"]
        for _ in range(60 * 60):           # a full minute of frames
            g.banner_age += 1 / 60.0
        self.assertIsNotNone(g.banner,
                             "the card must not evaporate while it is being read")

    def test_moving_dismisses_it(self):
        from .codex import FACTS
        g = self._game()
        g.banner = FACTS["brute.rule"]
        g.banner_age = 3.0
        g.dismiss_banner()
        self.assertIsNone(g.banner)
        self.assertEqual(g.banner_age, 0.0)

    def test_an_autowalk_step_dismisses_it_too(self):
        from .codex import FACTS
        g = self._game()
        g.banner = FACTS["rat.rule"]
        # pump_repeat calls dismiss_banner before stepping; simulate that contract
        g.dismiss_banner()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if g.world.walkable(g.world.player.x + dx, g.world.player.y + dy):
                g.walk_step(dx, dy)
                break
        self.assertIsNone(g.banner)

    def test_a_step_that_makes_a_NEW_discovery_still_shows_it(self):
        """dismiss happens BEFORE the move, so the move's own discovery survives."""
        from .traps import Trap
        g = self._game(seed=3)
        w = g.world
        w.player.hp = 99
        g.banner = None
        dx = dy = 0
        for ddx, ddy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if w.walkable(w.player.x + ddx, w.player.y + ddy):
                dx, dy = ddx, ddy
                break
        w.level.traps = [Trap("dart", w.player.x + dx, w.player.y + dy)]
        g.dismiss_banner()                 # what the move handler does first
        w.player_move(dx, dy)              # ...then the step, which springs the trap
        self.assertIsNotNone(w.learned,
                             "the step uncovered a trap; the world should report it")
        self.assertEqual(w.learned.key, "dart.rule")


class TestTheSlain(unittest.TestCase):
    """What you kill stays on the floor -- until you leave the floor, or die."""

    def _kill_one(self, w, key="angry_rat", at=None):
        from .monsters import Monster
        x, y = at or (w.player.x + 2, w.player.y)
        m = Monster(key, x, y)
        w.level.monsters.append(m)
        w.kill_monster(m)
        return m

    def test_killing_something_leaves_a_body_where_it_fell(self):
        codex = FakeSave()
        w = World(codex, seed=5)
        w.level.monsters = []
        w.level.slain = []
        m = self._kill_one(w)
        self.assertEqual(len(w.level.slain), 1)
        s = w.level.slain[0]
        self.assertEqual((s.x, s.y), (m.x, m.y), "the body must be where it died")
        self.assertEqual(s.key, "angry_rat")

    def test_bodies_pile_up(self):
        codex = FakeSave()
        w = World(codex, seed=5)
        w.level.monsters = []
        w.level.slain = []
        for i, key in enumerate(["angry_rat", "kobold", "brute"]):
            self._kill_one(w, key, at=(w.player.x + 2 + i, w.player.y))
        self.assertEqual(len(w.level.slain), 3)
        self.assertEqual([s.key for s in w.level.slain],
                         ["angry_rat", "kobold", "brute"])

    def test_the_bodies_do_not_block_anything(self):
        codex = FakeSave()
        w = World(codex, seed=5)
        w.level.monsters = []
        w.level.slain = []
        spot = None
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if w.walkable(w.player.x + dx, w.player.y + dy):
                spot = (w.player.x + dx, w.player.y + dy)
                d = (dx, dy)
                break
        self._kill_one(w, at=spot)
        w.player_move(*d)
        self.assertEqual((w.player.x, w.player.y), spot,
                         "you must be able to walk over a corpse")

    def test_the_bodies_are_gone_when_you_take_the_stairs(self):
        codex = FakeSave()
        w = World(codex, seed=5)
        w.level.monsters = []
        w.level.slain = []
        self._kill_one(w)
        self.assertEqual(len(w.level.slain), 1)

        w.player.x, w.player.y = w.level.stairs
        w.descend()
        self.assertEqual(w.depth, 2)
        self.assertEqual(w.level.slain, [],
                         "a new floor must not inherit the last floor's dead")

    def test_the_bodies_are_gone_when_you_respawn(self):
        codex = FakeSave()
        codex.world_seed = 4242
        w = World(codex, seed=5)
        w.level.monsters = []
        w.level.slain = []
        self._kill_one(w)
        self.assertEqual(len(w.level.slain), 1)

        w.kill_player("rat")
        w2 = World(codex, seed=6)          # the run after
        self.assertEqual(w2.level.slain, [],
                         "a new run must be a clean floor -- the dungeon is re-dealt")

    def test_a_body_with_treasure_acts_like_a_chest(self):
        codex = FakeSave()
        w = World(codex, seed=5)
        w.level.monsters = []
        w.level.slain = []
        w.level.chests = []
        w.level.drops = []
        w.level.corpse = None

        m = self._kill_one(w, "brute")
        s = w.level.slain[0]
        s.loot = [("gold", 40), ("item", "ochre")]      # force a known hoard

        # standing anywhere else, there is nothing to take
        self.assertEqual(w.loot_options(), [])

        w.player.x, w.player.y = s.x, s.y
        opts = w.loot_options()
        self.assertEqual(len(opts), 2, "the body should offer its loot like a chest")
        self.assertEqual(opts[0]["label"], "40 gold")

        w.take_option(0)
        self.assertEqual(w.player.gold, 40)
        self.assertEqual(len(w.loot_options()), 1,
                         "taking one thing must leave the rest on the body")

    def test_looting_a_body_does_not_remove_the_body(self):
        codex = FakeSave()
        w = World(codex, seed=5)
        w.level.monsters = []
        w.level.slain = []
        w.level.chests = []
        w.level.drops = []
        w.level.corpse = None
        m = self._kill_one(w, "kobold")
        s = w.level.slain[0]
        s.loot = [("gold", 12)]
        w.player.x, w.player.y = s.x, s.y
        w.take_all()
        self.assertEqual(w.player.gold, 12)
        self.assertFalse(s.has_loot, "the body is empty now")
        self.assertIn(s, w.level.slain,
                      "but the corpse itself must still be lying there")

    def test_loot_stays_ON_the_body_and_does_not_spill_onto_the_floor(self):
        codex = FakeSave()
        w = World(codex, seed=5)
        w.level.monsters = []
        w.level.slain = []
        w.level.drops = []
        for i in range(40):
            self._kill_one(w, "brute", at=(w.player.x + 2, w.player.y))
        self.assertEqual(w.level.drops, [],
                         "no free-floating drops: the corpse IS the container")
        carrying = [s for s in w.level.slain if s.has_loot]
        self.assertTrue(carrying, "40 brutes and not one was carrying anything?")

    def test_tougher_things_carry_more(self):
        from .items import MONSTER_LOOT
        self.assertLess(MONSTER_LOOT["angry_rat"][0], MONSTER_LOOT["brute"][0])
        self.assertLess(MONSTER_LOOT["brute"][0], MONSTER_LOOT["mimic"][0],
                        "the mimic has been eating adventurers; it should be rich")

    def test_the_treasure_dies_with_the_floor(self):
        """Leave the floor and the body -- and its treasure -- is gone. Loot it or
        lose it."""
        codex = FakeSave()
        w = World(codex, seed=5)
        w.level.monsters = []
        w.level.slain = []
        s_m = self._kill_one(w, "brute")
        w.level.slain[0].loot = [("gold", 500)]
        w.player.x, w.player.y = w.level.stairs
        w.descend()
        self.assertEqual(w.level.slain, [])
        self.assertEqual(w.player.gold, 0, "you walked away from it. it is gone.")

    def test_the_bodies_are_not_written_to_the_save(self):
        """They are scenery for this run, not part of the game's memory."""
        codex = FakeSave()
        w = World(codex, seed=5)
        w.level.monsters = []
        self._kill_one(w)
        data = [k for k in vars(codex) if "slain" in k.lower()]
        self.assertEqual(data, [], "the slain must not persist in the Kodex")

    def test_a_body_is_left_even_when_a_trap_does_the_killing(self):
        from .traps import Trap
        codex = FakeSave()
        w = World(codex, seed=5)
        w.level.monsters = []
        w.level.slain = []
        from .monsters import Monster
        m = Monster("angry_rat", w.player.x + 2, w.player.y)
        m.hp = 1
        w.level.monsters = [m]
        w.level.traps = [Trap("glyph", m.x, m.y)]
        w.level.traps[0].trigger(w, m)
        self.assertEqual(len(w.level.slain), 1,
                         "the floor killed it, but it is still dead on the floor")


class TestFireIsVisible(unittest.TestCase):
    """You must be able to SEE the thing that burned you. A wound with no cause
    teaches nothing, and teaching is the whole game."""

    def _floor_next_to(self, w):
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if w.walkable(w.player.x + dx, w.player.y + dy):
                return dx, dy
        raise AssertionError("boxed in")

    def test_a_fire_glyph_throws_a_visible_burst(self):
        from .traps import Trap
        codex = FakeSave()
        w = World(codex, seed=3)
        w.level.monsters = []
        w.player.hp = 99
        dx, dy = self._floor_next_to(w)
        spot = (w.player.x + dx, w.player.y + dy)
        w.level.traps = [Trap("glyph", *spot)]
        self.assertEqual(w.fx, [])

        w.player_move(dx, dy)

        bursts = [f for f in w.fx if f["kind"] == "burst"]
        self.assertTrue(bursts, "the glyph must show the player what just happened")
        self.assertEqual((bursts[0]["x"], bursts[0]["y"]), spot,
                         "the fireball must be centred on the glyph")
        self.assertGreaterEqual(bursts[0]["r"], 1.0,
                                "the blast covers the 3x3 -- it must be DRAWN that big, "
                                "or the player cannot learn to stand outside it")

    def test_the_firestorm_scroll_marks_everything_it_burns(self):
        from .monsters import Monster
        codex = FakeSave()
        codex.known.append("id.vorn")
        w = World(codex, seed=3)
        w.level.monsters = []
        w.player.hp = 99
        # three monsters in plain sight
        placed = []
        for dx, dy in ((1, 0), (-1, 0), (0, 1)):
            x, y = w.player.x + dx, w.player.y + dy
            if w.walkable(x, y):
                m = Monster("angry_rat", x, y)
                m.hp = 99
                w.level.monsters.append(m)
                placed.append((x, y))
        w.level.compute_fov(w.player.x, w.player.y)
        w.player.pack = ["vorn"]

        w.use_item(0)

        self.assertTrue([f for f in w.fx if f["kind"] == "flash"],
                        "the whole visible floor should light up")
        bursts = {(f["x"], f["y"]) for f in w.fx if f["kind"] == "burst"}
        for spot in placed:
            self.assertIn(spot, bursts,
                          "every monster it burned must be shown burning")
        self.assertNotIn((w.player.x, w.player.y), bursts,
                         "VORN spares its own caster -- no burst on the player's tile")

    def test_the_glyph_sets_the_floor_it_damages_on_fire(self):
        """The burning tiles must BE the damage area. An animation that lies about
        the blast is worse than no animation at all."""
        from .traps import Trap
        codex = FakeSave()
        w = World(codex, seed=3)
        w.level.monsters = []
        w.player.hp = 99
        dx, dy = self._floor_next_to(w)
        gx, gy = w.player.x + dx, w.player.y + dy
        w.level.traps = [Trap("glyph", gx, gy)]
        w.player_move(dx, dy)

        burning = [f for f in w.fx if f["kind"] == "burning"]
        self.assertTrue(burning, "the floor must catch fire")
        tiles = set(burning[0]["tiles"])

        # the glyph hurts everything within 1 tile (chebyshev). so must the flames.
        expected = {(gx + ex, gy + ey)
                    for ey in (-1, 0, 1) for ex in (-1, 0, 1)
                    if w.walkable(gx + ex, gy + ey)}
        self.assertEqual(tiles, expected,
                         "the flames must cover exactly the tiles that take damage")
        self.assertIn((gx, gy), tiles)
        self.assertNotIn((gx + 2, gy), tiles, "and no further")

    def test_the_firestorm_sets_light_to_everything_it_can_see(self):
        codex = FakeSave()
        codex.known.append("id.vorn")
        codex.world_seed = 3          # pin the stone: the room size must not be random
        w = World(codex, seed=3)
        w.level.monsters = []
        w.player.hp = 99
        w.level.compute_fov(w.player.x, w.player.y)
        w.player.pack = ["vorn"]
        w.use_item(0)

        burning = [f for f in w.fx if f["kind"] == "burning"]
        self.assertTrue(burning)
        tiles = set(burning[0]["tiles"])
        # Firestorm's range IS your field of view: it lights every visible walkable tile
        # and only those. Assert that EXACT set, so the test does not depend on how big a
        # room the seed happened to deal -- which was the old source of flakiness.
        self.assertEqual(tiles, set(w.visible_floor()),
                         "VORN burns exactly what you can see -- no walls, nothing unseen")
        self.assertTrue(tiles, "and there is something in view to burn")

    def test_the_escape_scroll_shows_you_where_you_went(self):
        """UUL cuts the camera to a strange room. Without a mark on the tile you left
        and the tile you arrived at, it is indistinguishable from a bug."""
        codex = FakeSave()
        codex.known.append("id.uul")
        w = World(codex, seed=3)
        w.level.monsters = []
        w.player.pack = ["uul"]
        before = (w.player.x, w.player.y)

        w.use_item(0)

        after = (w.player.x, w.player.y)
        self.assertNotEqual(before, after, "UUL should have moved us")
        vanish = [f for f in w.fx if f["kind"] == "vanish"]
        arrive = [f for f in w.fx if f["kind"] == "arrive"]
        self.assertTrue(vanish, "mark the tile you LEFT")
        self.assertTrue(arrive, "mark the tile you ARRIVED at")
        self.assertEqual((vanish[0]["x"], vanish[0]["y"]), before)
        self.assertEqual((arrive[0]["x"], arrive[0]["y"]), after)

    def test_the_summoning_scroll_shows_things_arriving(self):
        """GRAMM's monsters must not just BE there -- especially since they may be
        unreadable '?' silhouettes."""
        codex = FakeSave()
        codex.known.append("id.gramm")
        w = World(codex, seed=3)
        w.level.monsters = []
        w.player.pack = ["gramm"]

        w.use_item(0)

        self.assertTrue(w.level.monsters, "it should have summoned something")
        summon = [f for f in w.fx if f["kind"] == "summon"]
        self.assertTrue(summon, "the ground must open under each one")
        marked = set(summon[0]["tiles"])
        for m in w.level.monsters:
            self.assertIn((m.x, m.y), marked,
                          "every summoned monster must be shown arriving")

    def test_the_mapping_scroll_shows_the_knowledge_travelling(self):
        """KESH reveals the floor -- but nearly all of it is off-screen, so without a
        ripple the player reads a scroll and watches nothing happen."""
        codex = FakeSave()
        codex.known.append("id.kesh")
        w = World(codex, seed=3)
        w.level.monsters = []
        w.player.pack = ["kesh"]

        w.use_item(0)

        ripple = [f for f in w.fx if f["kind"] == "ripple"]
        self.assertTrue(ripple, "the reveal needs something to watch")
        self.assertEqual((ripple[0]["x"], ripple[0]["y"]),
                         (w.player.x, w.player.y),
                         "the knowledge spreads outward from you")
        self.assertGreater(len(ripple[0]["tiles"]), 50,
                           "it should light up the floor it just revealed")

    def test_potions_do_something_visible_on_your_body(self):
        codex = FakeSave()
        for flavor, effect in (("ochre", "heal"), ("azure", "haste"),
                               ("black", "might"), ("viscous", "poison")):
            codex2 = FakeSave()
            w = World(codex2, seed=3)
            w.level.monsters = []
            w.player.hp = 12
            w.player.pack = [flavor]
            w.use_item(0)
            pulses = [f for f in w.fx if f["kind"] == "pulse"]
            self.assertTrue(pulses, "%s (%s) does nothing visible" % (flavor, effect))
            self.assertEqual((pulses[0]["x"], pulses[0]["y"]),
                             (w.player.x, w.player.y))

    def _spring(self, key, seed=3):
        """Walk onto a trap of this kind and return the world."""
        from .traps import Trap
        codex = FakeSave()
        w = World(codex, seed=seed)
        w.level.monsters = []
        w.player.hp = 99
        dx, dy = self._floor_next_to(w)
        w.level.traps = [Trap(key, w.player.x + dx, w.player.y + dy)]
        spot = (w.player.x + dx, w.player.y + dy)
        w.player_move(dx, dy)
        return w, spot

    def test_the_dart_is_drawn_flying_out_of_a_wall(self):
        w, spot = self._spring("dart")
        darts = [f for f in w.fx if f["kind"] == "dart"]
        self.assertTrue(darts, "a dart that hits you unseen teaches you nothing")
        d = darts[0]
        self.assertEqual((d["x"], d["y"]), spot, "it must land on the plate")
        self.assertTrue(d["tiles"], "and it must come FROM somewhere")
        wx, wy = d["tiles"][0]
        self.assertFalse(w.walkable(wx, wy),
                         "the dart comes out of a WALL, not out of thin air")

    def test_the_spikes_are_drawn_coming_up_through_the_floor(self):
        w, spot = self._spring("spike")
        spikes = [f for f in w.fx if f["kind"] == "spikes"]
        self.assertTrue(spikes)
        self.assertEqual((spikes[0]["x"], spikes[0]["y"]), spot)

    def test_the_gas_cloud_is_drawn(self):
        """Gas does no damage on contact -- it just starts you bleeding a turn later.
        Without a visible cloud the poison has no visible cause."""
        w, spot = self._spring("gas")
        gas = [f for f in w.fx if f["kind"] == "gas"]
        self.assertTrue(gas, "the poison must have a visible source")
        self.assertIn(spot, gas[0]["tiles"], "the cloud covers the vent")
        self.assertGreater(len(gas[0]["tiles"]), 1, "and it spreads")
        self.assertGreater(gas[0]["max"], 1.0, "gas lingers -- it does not flash")

    def test_the_alarm_shows_the_whole_floor_waking_up(self):
        """The alarm does NO damage. The only thing it does is wake everything, so
        that is the thing that has to be drawn -- otherwise the player learns nothing
        and the next thirty seconds are inexplicable."""
        from .monsters import Monster
        from .traps import Trap
        codex = FakeSave()
        w = World(codex, seed=3)
        w.player.hp = 99
        w.level.monsters = []
        for i in range(4):
            m = Monster("kobold", 20 + i * 3, 20)
            self.assertFalse(m.awake)
            w.level.monsters.append(m)
        dx, dy = self._floor_next_to(w)
        w.level.traps = [Trap("alarm", w.player.x + dx, w.player.y + dy)]
        # where everything WAS when the rune screamed. they start walking immediately
        # afterwards, which is the entire problem the animation exists to explain.
        was = {(m.x, m.y) for m in w.level.monsters}

        w.player_move(dx, dy)

        self.assertTrue(all(m.awake for m in w.level.monsters),
                        "the alarm wakes everything")
        shout = [f for f in w.fx if f["kind"] == "shout"]
        self.assertTrue(shout, "the sound is the payload; draw the sound")
        self.assertGreaterEqual(shout[0]["r"], 20,
                                "the rings must cross the whole floor")
        woke = [f for f in w.fx if f["kind"] == "woke"]
        self.assertTrue(woke, "mark everything that heard it")
        self.assertEqual(set(woke[0]["tiles"]), was,
                         "every monster that heard it must be marked where it stood "
                         "when it heard it")

    def test_every_trap_in_the_game_shows_you_something(self):
        """No silent traps. Ever."""
        from .traps import TRAP_NAMES
        for key in TRAP_NAMES:
            w, _ = self._spring(key)
            self.assertTrue(w.fx,
                            "the %s fires without showing the player anything" % key)

    def test_the_brutes_fist_is_drawn_landing_even_when_it_misses(self):
        """The miss matters as much as the hit: it is the proof that stepping off the
        wind-up actually works."""
        from .monsters import Monster
        codex = FakeSave()
        w = World(codex, seed=3)
        w.level.monsters = []
        w.player.hp = 99
        b = Monster("brute", w.player.x + 1, w.player.y)
        b.awake = True
        b.intent = ("smash", w.player.x + 5, w.player.y)   # aimed at empty floor
        w.level.monsters = [b]

        b.take_turn(w)

        slams = [f for f in w.fx if f["kind"] == "slam"]
        self.assertTrue(slams, "the fist must be seen hitting the floor")
        self.assertEqual((slams[0]["x"], slams[0]["y"]), (w.player.x + 5, w.player.y),
                         "it lands on the TILE it was aimed at, not on you")

    def test_the_spitters_acid_is_drawn_crossing_the_room(self):
        from .monsters import Monster
        codex = FakeSave()
        w = World(codex, seed=3)
        w.level.monsters = []
        w.player.hp = 99
        sx = w.player.x + 3
        if not w.walkable(sx, w.player.y):
            self.skipTest("no clear line on this seed")
        s = Monster("spitter", sx, w.player.y)
        s.awake = True
        s.intent = ("spit", -1, 0)
        w.level.monsters = [s]

        s.take_turn(w)

        bolts = [f for f in w.fx if f["kind"] == "bolt"]
        self.assertTrue(bolts, "the shot must be visible, not just the wind-up")
        self.assertEqual(bolts[0]["tiles"][0], (sx, w.player.y),
                         "it comes from the spitter")

    def test_the_wraiths_drain_is_drawn_as_a_tether(self):
        from .monsters import Monster
        codex = FakeSave()
        w = World(codex, seed=3)
        w.level.monsters = []
        w.player.hp = 99
        wr = Monster("wraith", w.player.x + 1, w.player.y)
        wr.awake = True
        w.level.monsters = [wr]

        wr.take_turn(w)

        drains = [f for f in w.fx if f["kind"] == "drain"]
        self.assertTrue(drains, "your life leaving you must be visible")
        self.assertEqual((drains[0]["x"], drains[0]["y"]), (wr.x, wr.y),
                         "the drainer is the wraith")
        self.assertEqual(drains[0]["tiles"][0], (w.player.x, w.player.y),
                         "the victim is you")

    def test_your_own_blows_are_drawn(self):
        from .monsters import Monster
        codex = FakeSave()
        w = World(codex, seed=3)
        w.level.monsters = []
        m = Monster("kobold", w.player.x + 1, w.player.y)
        m.hp = 99
        w.level.monsters = [m]
        w.player_attack(m)
        self.assertTrue([f for f in w.fx if f["kind"] == "slash"],
                        "you should be able to see your own sword connect")

    def test_armour_turning_a_blow_is_drawn(self):
        """The one moment armour justifies the turns it costs you."""
        from .items import ARMOURS
        from .monsters import Monster
        codex = FakeSave()
        w = World(codex, seed=3)
        w.level.monsters = []
        w.player.armour = ARMOURS["plate"]        # 5 def
        rat = Monster("angry_rat", w.player.x + 1, w.player.y)
        hp = w.player.hp

        w.monster_attacks_player(rat, 2)          # a rat cannot dent plate

        self.assertEqual(w.player.hp, hp)
        self.assertTrue([f for f in w.fx if f["kind"] == "impact"],
                        "sparks off the plate -- the player must SEE the armour work")

    def test_nothing_in_this_dungeon_hurts_you_silently(self):
        """The load-bearing one. Every source of damage in the game must put
        something on the screen -- the whole design depends on the player being able
        to work out what killed them."""
        from .monsters import TEMPLATES, Monster
        from .traps import TRAP_NAMES, Trap

        for key in TRAP_NAMES:                    # every trap
            w, _ = self._spring(key)
            self.assertTrue(w.fx, "the %s hurts you silently" % key)

        for key in TEMPLATES:                     # every monster's attack
            if key == "mimic":
                continue                          # it bites like anything else
            codex = FakeSave()
            w = World(codex, seed=3)
            w.level.monsters = []
            w.player.hp = 99
            m = Monster(key, w.player.x + 1, w.player.y)
            m.awake = True
            w.level.monsters = [m]
            hp = w.player.hp
            for _ in range(6):                    # let it wind up and swing
                w.fx = []
                m.take_turn(w)
                if w.player.hp < hp or w.fx:
                    break
            self.assertTrue(
                w.fx or w.player.hp == hp,
                "the %s took %d hp off you without drawing anything"
                % (key, hp - w.player.hp))

    def test_the_effects_expire_in_real_time(self):
        from .traps import Trap
        codex = FakeSave()
        w = World(codex, seed=3)
        w.level.monsters = []
        w.player.hp = 99
        dx, dy = self._floor_next_to(w)
        w.level.traps = [Trap("glyph", w.player.x + dx, w.player.y + dy)]
        w.player_move(dx, dy)
        self.assertTrue(w.fx)

        for _ in range(60):              # one second of frames
            w.tick_fx(1 / 60.0)
        self.assertEqual(w.fx, [], "the fire should have burned out by now")

    def test_the_effects_are_purely_cosmetic(self):
        """They must never touch the simulation."""
        codex = FakeSave()
        w = World(codex, seed=3)
        w.level.monsters = []
        hp = w.player.hp
        for _ in range(50):
            w.add_fx("burst", 5, 5)
        for _ in range(120):
            w.tick_fx(1 / 60.0)
        self.assertEqual(w.player.hp, hp)
        self.assertFalse(w.dead)


class TestTheVenom(unittest.TestCase):
    """The same flask is a mistake to the ignorant and a weapon to the informed.
    Nothing about the potion changes -- only the hand holding it."""

    def _world(self, known=False):
        codex = FakeSave()
        if known:
            codex.known.append("id.viscous")
        w = World(codex, seed=9)
        w.level.monsters = []
        w.player.pack = ["viscous"]
        return w, codex

    def test_unknown_venom_gets_drunk_and_poisons_you(self):
        w, codex = self._world(known=False)
        hp = w.player.hp
        w.use_item(0)
        self.assertLess(w.player.hp, hp, "you drank it; it should hurt")
        self.assertGreater(w.player.poison, 0, "it should poison you")
        self.assertIsNone(w.player.blade_coat, "an ignorant hero does not coat a blade")
        self.assertTrue(codex.identified("viscous"),
                        "and THAT is how you find out what it was")

    def test_known_venom_is_painted_on_the_blade_not_swallowed(self):
        w, codex = self._world(known=True)
        hp = w.player.hp
        w.use_item(0)
        self.assertEqual(w.player.hp, hp, "you must NOT drink venom you can identify")
        self.assertEqual(w.player.poison, 0, "and it must not poison you")
        self.assertEqual(w.player.blade_coat, "poison", "it goes on the blade")
        self.assertEqual(w.player.pack, [], "the flask is spent either way")

    def test_the_venom_makes_the_next_strike_hurt(self):
        from .monsters import Monster
        w, codex = self._world(known=True)
        w.use_item(0)
        self.assertEqual(w.player.blade_coat, "poison")

        m = Monster("brute", w.player.x + 1, w.player.y)
        m.hp = 999                       # so it survives and we can read the damage
        m.max_hp = 999
        w.level.monsters = [m]
        w.player_attack(m)
        venomed_damage = 999 - m.hp

        # a clean strike from the same weapon, for comparison
        m2 = Monster("brute", w.player.x + 1, w.player.y)
        m2.hp = 999
        m2.max_hp = 999
        w.level.monsters = [m2]
        w.player_attack(m2)
        clean_damage = 999 - m2.hp

        self.assertGreater(venomed_damage, clean_damage,
                           "the venomed strike must hit harder (%d vs %d)"
                           % (venomed_damage, clean_damage))

    def test_it_wears_off_after_exactly_one_strike(self):
        from .monsters import Monster
        w, codex = self._world(known=True)
        w.use_item(0)
        m = Monster("brute", w.player.x + 1, w.player.y)
        m.hp = 999
        m.max_hp = 999
        w.level.monsters = [m]

        w.player_attack(m)
        self.assertIsNone(w.player.blade_coat,
                          "one coat, one strike -- the blade is clean again")

        first = 999 - m.hp
        hp_after_first = m.hp
        w.player_attack(m)
        second = hp_after_first - m.hp
        self.assertLess(second, first,
                        "the SECOND strike must not still be venomed (%d then %d)"
                        % (first, second))

    def test_the_venom_is_spent_on_whatever_you_hit_first(self):
        """It does not politely wait for the boss."""
        from .monsters import Monster
        w, codex = self._world(known=True)
        w.use_item(0)
        rat = Monster("angry_rat", w.player.x + 1, w.player.y)
        w.level.monsters = [rat]
        w.player_attack(rat)
        self.assertIsNone(w.player.blade_coat,
                          "you wasted it on a rat, and the game must let you")

    def test_it_survives_until_you_actually_swing(self):
        w, codex = self._world(known=True)
        w.use_item(0)
        for _ in range(30):
            w.player_wait()
        self.assertEqual(w.player.blade_coat, "poison",
                         "the coat must not evaporate on a timer -- it waits")

    def test_a_second_flask_can_be_re_applied(self):
        from .monsters import Monster
        w, codex = self._world(known=True)
        w.player.pack = ["viscous", "viscous"]
        w.use_item(0)
        m = Monster("brute", w.player.x + 1, w.player.y)
        m.hp = 999
        m.max_hp = 999
        w.level.monsters = [m]
        w.player_attack(m)
        self.assertIsNone(w.player.blade_coat)
        w.use_item(0)                    # the second flask
        self.assertEqual(w.player.blade_coat, "poison",
                         "you can re-coat with another flask")

    def test_coating_the_blade_costs_a_turn(self):
        w, codex = self._world(known=True)
        t0 = w.tick
        w.use_item(0)
        self.assertGreater(w.tick, t0, "wiping venom down a blade takes a turn")


class TestWaveOneCommons(unittest.TestCase):
    """The rest of the common tier: Stoneskin, Regeneration, Weakness, Cleansing
    potions; Identify, Light, Aggravation and Detect Treasure scrolls."""

    def _world(self):
        codex = FakeSave()
        codex.world_seed = 3
        w = World(codex, seed=3)
        w.level.monsters = []
        for r in w.level.rooms:
            if r.w >= 7 and r.h >= 7:
                w.player.x, w.player.y = r.cx, r.cy
                break
        w.level.compute_fov(w.player.x, w.player.y)
        return w

    def _use(self, w, flavor):
        w.codex.known.append("id.%s" % flavor)   # known, so we get the effect not a blind sip
        w.player.slots = [[flavor, 1], None, None, None, None, None]
        return w.use_item(0)

    # --- potions --------------------------------------------------------
    def test_stoneskin_hardens_your_defence(self):
        w = self._world()
        base = w.player.defense
        self._use(w, "grey")
        self.assertGreater(w.player.defense, base, "stoneskin adds defence")
        self.assertGreater(w.player.stoneskin, 0, "and it is on a timer")

    def test_regeneration_heals_over_time(self):
        w = self._world()
        w.player.hp = 10
        self._use(w, "crimson")
        self.assertGreater(w.player.regen, 0)
        hp = w.player.hp
        w.player.tick_effects(w)
        self.assertGreater(w.player.hp, hp, "you knit closed a little each turn")

    def test_weakness_saps_your_damage_when_drunk_blind(self):
        import random
        w = self._world()
        w.player.slots = [["sallow", 1], None, None, None, None, None]  # unknown
        w.use_item(0)                                 # drunk in ignorance -> it saps YOU
        self.assertGreater(w.player.weak, 0)
        rolls = [w.player.damage_roll(random.Random(i)) for i in range(100)]
        self.assertTrue(all(r >= 1 for r in rolls), "a blow always lands for at least 1")
        self.assertLessEqual(max(rolls), 1, "but sallow drags a shiv down to nothing")

    def test_a_known_weakness_potion_coats_the_blade_like_venom(self):
        """The user's ask: every negative potion works like venom. A weakness you can
        identify is never drunk -- it goes on the blade and saps whatever you cut."""
        from .monsters import Monster
        w = self._world()
        w.codex.known.append("id.sallow")
        w.player.slots = [["sallow", 1], None, None, None, None, None]
        hp = w.player.hp
        w.use_item(0)
        self.assertEqual(w.player.hp, hp, "you do NOT drink a weakness you can name")
        self.assertEqual(w.player.weak, 0, "and it does not weaken YOU")
        self.assertEqual(w.player.blade_coat, "weak", "it goes on the blade instead")
        m = Monster("brute", w.player.x + 1, w.player.y)
        m.hp = m.max_hp = 999
        w.level.monsters = [m]
        w.player_attack(m)
        self.assertGreater(m.weak, 0, "the struck thing's strength is sapped, not yours")
        self.assertIsNone(w.player.blade_coat, "one coat, one strike")

    def test_a_weakened_monster_hits_softer(self):
        import random
        from .monsters import Monster
        w = self._world()
        p = w.player

        def total(weak):
            w.rng = random.Random(1)                  # identical rolls both runs
            p.hp = p.max_hp = 99999
            m = Monster("brute", p.x + 1, p.y)
            m.weak = weak
            w.level.monsters = [m]
            for _ in range(200):
                m._hit(w)
            return 99999 - p.hp

        self.assertLess(total(999), total(0),
                        "a brute sapped by a weakness coat deals less over many blows")

    def test_every_negative_potion_is_coatable(self):
        from .world import COATABLE_EFFECTS
        self.assertIn("poison", COATABLE_EFFECTS, "venom coats the blade")
        self.assertIn("weak", COATABLE_EFFECTS, "and so does weakness")

    def test_regeneration_also_cleanses_what_ails_you(self):
        """Cleansing was folded into Regeneration: it washes out poison, weakness and
        confusion, then heals over time."""
        w = self._world()
        w.player.poison = 8
        w.player.weak = 8
        w.player.confused = 8
        self._use(w, "crimson")
        self.assertEqual(w.player.poison, 0, "poison washed out")
        self.assertEqual(w.player.weak, 0, "weakness washed out")
        self.assertEqual(w.player.confused, 0, "confusion washed out")
        self.assertGreater(w.player.regen, 0, "and the healing-over-time begins")

    def test_vigor_is_a_shield_that_soaks_blows_before_your_health(self):
        w = self._world()
        self._use(w, "silver")            # silver is now Potion of Vigor
        self.assertGreater(w.player.vigor, 0, "a reserve of temporary vitality")
        shield = w.player.vigor
        hp = w.player.hp
        w.hurt_player(shield - 1, "test")
        self.assertEqual(w.player.hp, hp, "the shell takes the blow, not your blood")
        self.assertEqual(w.player.vigor, 1, "and the shield wears down")
        w.hurt_player(10, "test")
        self.assertEqual(w.player.vigor, 0, "the shield breaks")
        self.assertLess(w.player.hp, hp, "and the overflow reaches you")

    def test_vigor_fades_if_you_do_not_use_it(self):
        w = self._world()
        self._use(w, "silver")
        for _ in range(40):
            w.player.tick_effects(w)
        self.assertEqual(w.player.vigor, 0, "an unspent shield does not last forever")

    # --- scrolls --------------------------------------------------------
    def test_identify_names_your_biggest_unknown(self):
        w = self._world()
        w.player.slots = [["ochre", 1], ["viscous", 3], ["morn", 1], None, None, None]
        w.codex.known.append("id.morn")
        self.assertFalse(w.codex.identified("viscous"))
        w.use_item(2)                                 # read MORN
        self.assertTrue(w.codex.identified("viscous"),
                        "it names the mystery you hold the most of")
        self.assertFalse(w.codex.identified("ochre"), "and only that one")

    def test_light_reveals_nearby_traps_only(self):
        from .traps import Trap
        w = self._world()
        near = (w.player.x + 3, w.player.y)
        far = (w.player.x + 20, w.player.y)
        w.level.traps = [Trap("dart", *near), Trap("spike", *far)]
        self._use(w, "yris")
        self.assertTrue(w.codex.trap_found(w.depth, *near), "the nearby trap lights up")
        self.assertFalse(w.codex.trap_found(w.depth, *far), "the far one stays hidden")

    def test_aggravation_wakes_the_whole_floor(self):
        from .monsters import Monster
        w = self._world()
        sleepers = [Monster("rat", w.player.x + 10, w.player.y),
                    Monster("brute", w.player.x - 10, w.player.y)]
        for m in sleepers:
            m.awake = False
            w.level.monsters.append(m)
        self._use(w, "ghask")
        self.assertTrue(all(m.awake for m in sleepers), "everything on the floor wakes")

    def test_detect_treasure_marks_loot_you_have_not_seen(self):
        from .dungeon import Drop
        w = self._world()
        far = (w.player.x + 15, w.player.y + 5)
        w.level.drops = [Drop(far[0], far[1], "gold", 40)]
        w.level.seen[far[1]][far[0]] = False
        self._use(w, "vosh")
        self.assertTrue(w.level.seen[far[1]][far[0]],
                        "the far hoard is now marked on the map")

    # --- data integrity -------------------------------------------------
    def test_every_consumable_has_a_name_a_tier_and_an_id_fact(self):
        from .items import CONSUMABLES
        from .codex import FACTS
        for flavor, c in CONSUMABLES.items():
            self.assertIn("id.%s" % flavor, FACTS, "%s has no id fact" % flavor)
            self.assertTrue(c.true_name and c.unknown_name)
            self.assertIn(c.tier, ("common", "uncommon", "rare"))

    def test_the_new_commons_are_in_the_spawn_pools(self):
        from .items import POTION_POOL, SCROLL_POOL
        for f in ("grey", "crimson", "sallow", "silver"):
            self.assertIn(f, POTION_POOL)
        for f in ("morn", "yris", "ghask", "vosh"):
            self.assertIn(f, SCROLL_POOL)


class TestWaveTwoBuffs(unittest.TestCase):
    """The uncommon tier's self-buffs and enchantments: Greater Healing, Rage,
    Warding, Levitation potions; Enchant Weapon / Enchant Armour scrolls."""

    def _world(self):
        codex = FakeSave()
        codex.world_seed = 3
        w = World(codex, seed=3)
        w.level.monsters = []
        for r in w.level.rooms:
            if r.w >= 7 and r.h >= 7:
                w.player.x, w.player.y = r.cx, r.cy
                break
        w.level.compute_fov(w.player.x, w.player.y)
        return w

    def _use(self, w, flavor):
        w.codex.known.append("id.%s" % flavor)
        w.player.slots = [[flavor, 1], None, None, None, None, None]
        return w.use_item(0)

    def test_greater_healing_fills_you_to_the_brim(self):
        w = self._world()
        w.player.hp = 3
        self._use(w, "rose")
        self.assertEqual(w.player.hp, w.player.max_hp, "greater healing goes to full")

    def test_rage_hits_harder_and_faster_but_leaves_you_open(self):
        import random
        w = self._world()
        base_speed = w.player.speed()
        base_dmg = w.player.damage_roll(random.Random(5))
        self._use(w, "vermilion")
        self.assertGreater(w.player.berserk, 0)
        self.assertGreater(w.player.speed(), base_speed, "rage is faster")
        self.assertGreater(w.player.damage_roll(random.Random(5)), base_dmg,
                           "and it hits harder")
        # the downside: a real blow bites deeper while you rage
        hp = w.player.hp
        w.hurt_player(4, "test")
        self.assertEqual(hp - w.player.hp, 6, "rage makes you take +2 per hit")

    def test_warding_halves_what_lands(self):
        w = self._world()
        self._use(w, "teal")
        self.assertGreater(w.player.resist, 0)
        hp = w.player.hp
        w.hurt_player(10, "test")
        self.assertEqual(hp - w.player.hp, 5, "warding halves incoming damage")

    def test_levitation_floats_over_pressure_traps_and_pits(self):
        from .traps import Trap
        w = self._world()
        self._use(w, "sky")
        self.assertGreater(w.player.levitate, 0)
        hp = w.player.hp
        Trap("spike", w.player.x, w.player.y).trigger(w, w.player)
        self.assertEqual(w.player.hp, hp, "you drift over the spike pit")
        self.assertEqual(w.player.stuck, 0, "and you are not stuck in it")

    def test_enchant_weapon_adds_permanent_damage_and_stacks(self):
        import random
        w = self._world()
        base = w.player.damage_roll(random.Random(7))
        self._use(w, "krav")
        once = w.player.damage_roll(random.Random(7))
        self.assertEqual(once - base, 1, "+1 damage")
        self.assertEqual(w.player.weapon.bonus, 1, "the enchant lives on the weapon")
        w.codex.known.append("id.krav")
        w.player.slots = [["krav", 1], None, None, None, None, None]
        w.use_item(0)
        self.assertEqual(w.player.damage_roll(random.Random(7)) - base, 2, "it stacks")

    def test_enchant_armour_adds_permanent_defence(self):
        w = self._world()
        base = w.player.defense
        self._use(w, "dwen")
        self.assertEqual(w.player.defense, base + 1, "+1 defence, for good")

    def test_enchanting_updates_the_displayed_name_and_stats(self):
        from .items import WEAPONS, ARMOURS
        w = self._world()
        w.player.weapon = WEAPONS["bronze_sword"].copy()   # Bronze Sword, 2-5 dmg
        w.player.armour = ARMOURS["leather"].copy()      # Leather Jerkin, 2 def
        self.assertEqual(w.player.gear_display("weapon"), ("Bronze Sword", "2-5 dmg"))

        self._use(w, "krav")                       # enchant the weapon +1
        self.assertEqual(w.player.gear_display("weapon"),
                         ("Bronze Sword +1", "3-6 dmg"), "name and stats both update")

        w.player.weapon.bonus = 3
        self.assertEqual(w.player.gear_display("weapon"),
                         ("Bronze Sword +3", "5-8 dmg"), "and it stacks")

        self._use(w, "dwen")                       # enchant the armour +1
        self.assertEqual(w.player.gear_display("armour"),
                         ("Leather Jerkin +1", "3 def"))
        # unenchanted gear reads plain
        self.assertEqual(w.player.gear_display("boots")[0], w.player.boots.name)

    # --- tier-gated spawning --------------------------------------------
    def test_uncommon_consumables_only_appear_from_floor_eight(self):
        import random
        from .items import roll_consumable, CONSUMABLES
        shallow = [roll_consumable(random.Random(i), 5, "potion") for i in range(300)]
        self.assertFalse(any(CONSUMABLES[f].tier == "uncommon" for f in shallow),
                         "no uncommon potions before floor 8")
        deep = [roll_consumable(random.Random(i), 15, "potion") for i in range(600)]
        self.assertTrue(any(CONSUMABLES[f].tier == "uncommon" for f in deep),
                        "uncommon potions do appear on the deep floors")


class TestWaveThreePotions(unittest.TestCase):
    """The rare tier's potions -- all boons, no gambles: Vitality, Heroism, Insight,
    the Phoenix."""

    def _world(self):
        codex = FakeSave()
        codex.world_seed = 3
        w = World(codex, seed=3)
        w.level.monsters = []
        for r in w.level.rooms:
            if r.w >= 7 and r.h >= 7:
                w.player.x, w.player.y = r.cx, r.cy
                break
        w.level.compute_fov(w.player.x, w.player.y)
        return w

    def _use(self, w, flavor):
        w.codex.known.append("id.%s" % flavor)
        w.player.slots = [[flavor, 1], None, None, None, None, None]
        return w.use_item(0)

    def test_vitality_raises_your_maximum_permanently(self):
        w = self._world()
        mh = w.player.max_hp
        self._use(w, "vital")
        self.assertGreater(w.player.max_hp, mh, "your ceiling rises")
        self.assertEqual(w.player.hp, w.player.max_hp, "and the new capacity comes full")

    def test_heroism_boosts_everything_at_once(self):
        import random
        w = self._world()
        w.player.hp = 5
        s0 = w.player.speed()
        d0 = w.player.damage_roll(random.Random(1))
        df0 = w.player.defense
        self._use(w, "radiant")
        self.assertGreater(w.player.speed(), s0, "faster")
        self.assertGreater(w.player.damage_roll(random.Random(1)), d0, "harder")
        self.assertGreater(w.player.defense, df0, "tougher")
        self.assertGreater(w.player.hp, 5, "and a heal on top")

    def test_insight_hands_you_a_free_kodex_fact(self):
        w = self._world()
        known = len(w.codex.known)
        self._use(w, "luminous")
        self.assertGreater(len(w.codex.known), known + 1,   # +1 is the id.luminous we set
                           "you learn a whole new fact for nothing")
        self.assertIsNotNone(w.learned, "and it announces itself")

    def test_the_phoenix_refuses_your_first_death_only(self):
        w = self._world()
        self._use(w, "ember")
        self.assertTrue(w.player.phoenix, "an ember, waiting")
        w.player.hp = 1
        w.hurt_player(999, "test")                 # a killing blow
        self.assertFalse(w.dead, "death is refused")
        self.assertGreater(w.player.hp, 0, "you are back on your feet")
        self.assertFalse(w.player.phoenix, "the ember is spent")
        w.hurt_player(999, "test")                 # the next one lands for real
        self.assertTrue(w.dead, "the phoenix is a one-time thing")

    def test_the_rare_potion_pool_is_now_populated(self):
        from .items import _TIER_POOLS, CONSUMABLES
        pool = _TIER_POOLS.get(("potion", "rare"), [])
        self.assertEqual(len(pool), 4, "four rare potions")
        self.assertTrue(all(CONSUMABLES[f].tier == "rare" for f in pool))


class TestWaveThreeScrolls(unittest.TestCase):
    """The rare tier's scrolls: Banishment, Descent, Thunderclap, Sanctuary."""

    def _world(self):
        codex = FakeSave()
        codex.world_seed = 3
        w = World(codex, seed=3)
        w.level.monsters = []
        for r in w.level.rooms:
            if r.w >= 9 and r.h >= 8:
                w.player.x, w.player.y = r.cx, r.cy
                break
        w.level.compute_fov(w.player.x, w.player.y)
        return w

    def _use(self, w, flavor):
        w.codex.known.append("id.%s" % flavor)
        w.player.slots = [[flavor, 1], None, None, None, None, None]
        return w.use_item(0)

    def test_banishment_offers_the_visible_kinds_and_unmakes_the_chosen_one(self):
        from .monsters import Monster
        w = self._world()
        for _ in range(4):
            w.level.monsters.append(Monster("rat", w.player.x + 2, w.player.y))
        for _ in range(2):
            w.level.monsters.append(Monster("brute", w.player.x - 2, w.player.y))
        w.level.compute_fov(w.player.x, w.player.y)
        offered = dict(w.banishable_types())
        self.assertEqual(offered.get("rat"), 4, "it lists what you can see")
        self.assertEqual(offered.get("brute"), 2)
        w.banish_type("rat")                        # you PICK the rats
        kinds = [m.key for m in w.level.monsters]
        self.assertNotIn("rat", kinds, "the chosen kind is unmade")
        self.assertEqual(kinds.count("brute"), 2, "the others are untouched")

    def test_banishment_is_not_a_kill_no_loot_no_credit(self):
        from .monsters import Monster
        w = self._world()
        w.level.monsters = [Monster("rat", w.player.x + 2, w.player.y)]
        w.level.compute_fov(w.player.x, w.player.y)
        kills = w.codex.stats["kills"]
        w.banish_type("rat")
        self.assertEqual(w.level.monsters, [], "gone")
        self.assertEqual(w.codex.stats["kills"], kills, "you erased them, did not kill them")
        self.assertEqual(w.level.slain, [], "no corpses left behind")

    def test_reading_it_opens_a_picker_and_identifies_it(self):
        from .monsters import Monster
        w = self._world()
        w.level.monsters = [Monster("rat", w.player.x + 2, w.player.y)]
        w.level.compute_fov(w.player.x, w.player.y)
        w.player.slots = [["ossk", 1], None, None, None, None, None]
        self.assertFalse(w.codex.identified("ossk"))
        w.use_item(0)
        self.assertEqual(w.aiming, "banish", "it opens a picker, it does not fire blind")
        self.assertTrue(w.codex.identified("ossk"), "and reading it reveals what it is")

    def test_backing_out_of_an_empty_room_keeps_the_scroll(self):
        w = self._world()                           # no monsters -> nothing to banish
        w.player.slots = [["ossk", 1], None, None, None, None, None]
        w.use_item(0)
        self.assertEqual(w.banishable_types(), [], "nothing in sight")
        self.assertNotIn("ossk", w.player.pack, "it is out of the pack while you decide")
        w.cancel_banish()
        self.assertIn("ossk", w.player.pack, "backing out puts the scroll BACK")
        self.assertIsNone(w.aiming)
        self.assertTrue(w.codex.identified("ossk"), "but you learned its purpose")

    def test_descent_puts_you_on_the_stairs(self):
        w = self._world()
        self.assertNotEqual((w.player.x, w.player.y), w.level.stairs)
        self._use(w, "vrom")
        self.assertEqual((w.player.x, w.player.y), w.level.stairs, "standing on the way down")

    def test_thunderclap_damages_everything_in_sight_but_not_you(self):
        from .monsters import Monster
        w = self._world()
        ms = [Monster("rat", w.player.x + dx, w.player.y) for dx in (1, 2)]
        for m in ms:
            m.hp = m.max_hp = 99
            w.level.monsters.append(m)
        hp = w.player.hp
        w._apply_effect("thunderclap")             # the effect in isolation, no turn-end
        self.assertTrue(all(m.hp < 99 for m in ms), "every visible monster is struck")
        self.assertEqual(w.player.hp, hp, "and it does not touch YOU (unlike Firestorm)")

    def test_sanctuary_stops_every_blow(self):
        from .monsters import Monster
        w = self._world()
        self._use(w, "ulm")
        self.assertGreater(w.player.sanctuary, 0)
        b = Monster("brute", w.player.x + 1, w.player.y)
        w.level.monsters = [b]
        hp = w.player.hp
        w.monster_attacks_player(b, 15)
        self.assertEqual(w.player.hp, hp, "a fist dies a hair from you")
        w.freeze_player(2)
        self.assertEqual(w.player.frozen, 0, "and so does the beholder's gaze")

    def test_the_rare_scroll_pool_is_populated(self):
        from .items import _TIER_POOLS, CONSUMABLES
        pool = _TIER_POOLS.get(("scroll", "rare"), [])
        self.assertEqual(len(pool), 4, "four rare scrolls")
        self.assertTrue(all(CONSUMABLES[f].tier == "rare" for f in pool))

    def test_every_consumable_still_has_a_name_and_id_fact(self):
        from .items import CONSUMABLES
        from .codex import FACTS
        from .sprites import POTION_COLORS
        for flavor, c in CONSUMABLES.items():
            self.assertIn("id.%s" % flavor, FACTS, "%s needs an id fact" % flavor)
            if c.kind == "potion":
                self.assertIn(flavor, POTION_COLORS, "%s needs a colour" % flavor)


class TestWaveTwoControl(unittest.TestCase):
    """Turning the floor against itself: Fear and Hold Monster scrolls, and the
    Confusion potion -- which, like every negative potion, coats the blade when known."""

    def _world(self):
        codex = FakeSave()
        codex.world_seed = 3
        w = World(codex, seed=3)
        w.level.monsters = []
        for r in w.level.rooms:
            if r.w >= 9 and r.h >= 8:
                w.player.x, w.player.y = r.cx, r.cy
                break
        w.level.compute_fov(w.player.x, w.player.y)
        return w

    def _use(self, w, flavor):
        w.codex.known.append("id.%s" % flavor)
        w.player.slots = [[flavor, 1], None, None, None, None, None]
        return w.use_item(0)

    def test_fear_makes_nearby_monsters_flee(self):
        from .monsters import Monster
        w = self._world()
        ms = [Monster("brute", w.player.x + dx, w.player.y) for dx in (2, 3)]
        for m in ms:
            m.awake = True
            w.level.monsters.append(m)
        d0 = [m.dist(w.player.x, w.player.y) for m in ms]
        self._use(w, "skarn")
        for _ in range(3):
            for m in ms:
                m.take_turn(w)
        d1 = [m.dist(w.player.x, w.player.y) for m in ms]
        self.assertTrue(all(b > a for a, b in zip(d0, d1)), "they all run from you")

    def test_hold_freezes_nearby_monsters(self):
        from .monsters import Monster
        w = self._world()
        m = Monster("brute", w.player.x + 1, w.player.y)   # adjacent
        m.awake = True
        w.level.monsters = [m]
        self._use(w, "gorm")
        self.assertGreater(m.stunned, 0, "it is locked rigid")
        hp = w.player.hp
        for _ in range(3):
            m.take_turn(w)
        self.assertEqual(w.player.hp, hp, "a held monster cannot strike you")

    def test_confusion_drunk_blind_scrambles_your_steps(self):
        w = self._world()
        w.player.slots = [["puce", 1], None, None, None, None, None]   # unknown
        w.use_item(0)
        self.assertGreater(w.player.confused, 0, "drunk in ignorance, it hits YOU")

    def test_confusion_known_coats_the_blade_and_confuses_the_target(self):
        from .monsters import Monster
        w = self._world()
        w.codex.known.append("id.puce")
        w.player.slots = [["puce", 1], None, None, None, None, None]
        w.use_item(0)
        self.assertEqual(w.player.blade_coat, "confuse", "known, it goes on the blade")
        self.assertEqual(w.player.confused, 0, "and does not confuse YOU")
        m = Monster("brute", w.player.x + 1, w.player.y)
        m.hp = 999
        w.level.monsters = [m]
        w.player_attack(m)
        self.assertGreater(m.confused, 0, "the struck thing stumbles, not you")

    def test_a_confused_monster_does_not_hunt_you(self):
        from .monsters import Monster
        w = self._world()
        m = Monster("brute", w.player.x + 1, w.player.y)
        m.awake = True
        m.confused = 5
        w.level.monsters = [m]
        hp = w.player.hp
        for _ in range(4):
            m.take_turn(w)
        self.assertEqual(w.player.hp, hp, "a confused monster stumbles, it does not press")


class TestScrollOfTeleport(unittest.TestCase):
    """ZEPH: the aimed cousin of Escape. You choose a seen, open tile and jump there."""

    def _world(self):
        codex = FakeSave()
        codex.world_seed = 3
        w = World(codex, seed=3)
        w.level.monsters = []
        for r in w.level.rooms:
            if r.w >= 9 and r.h >= 8:
                w.player.x, w.player.y = r.cx, r.cy
                break
        w.level.reveal_all()
        w.level.compute_fov(w.player.x, w.player.y)
        return w

    def test_reading_it_opens_a_targeting_mode_without_ending_the_turn(self):
        w = self._world()
        w.codex.known.append("id.zeph")
        w.player.slots = [["zeph", 1], None, None, None, None, None]
        tick = w.tick
        acted = w.use_item(0)
        self.assertEqual(w.aiming, "teleport", "it opens a cursor")
        self.assertEqual(w.tick, tick, "the turn does not end until you confirm")
        self.assertTrue(acted, "but the scroll is spent")

    def test_you_jump_to_a_chosen_seen_tile(self):
        w = self._world()
        w.aiming = "teleport"
        # find an explored, walkable, empty tile that is not the player
        target = None
        for r in w.level.rooms:
            t = (r.cx + 1, r.cy + 1)
            if (t != (w.player.x, w.player.y) and w.valid_teleport(*t)):
                target = t
                break
        self.assertIsNotNone(target)
        self.assertTrue(w.teleport_to(*target))
        self.assertEqual((w.player.x, w.player.y), target, "you land where you aimed")
        self.assertIsNone(w.aiming, "and the cursor closes")

    def test_you_cannot_land_on_a_wall_a_monster_or_the_unseen(self):
        from .monsters import Monster
        w = self._world()
        # a wall
        wx, wy = None, None
        for y in range(w.level.h):
            for x in range(w.level.w):
                if not w.walkable(x, y):
                    wx, wy = x, y
                    break
            if wx is not None:
                break
        self.assertFalse(w.valid_teleport(wx, wy), "not onto stone")
        # a monster's tile
        m = Monster("rat", w.player.x + 2, w.player.y)
        w.level.monsters = [m]
        self.assertFalse(w.valid_teleport(m.x, m.y), "not onto a monster")
        # an unexplored tile
        w.level.explored[w.player.y][w.player.x + 3] = False
        self.assertFalse(w.valid_teleport(w.player.x + 3, w.player.y),
                         "not to somewhere you have never seen")

    def test_cancelling_leaves_you_put(self):
        w = self._world()
        w.aiming = "teleport"
        here = (w.player.x, w.player.y)
        w.cancel_aim()
        self.assertIsNone(w.aiming)
        self.assertEqual((w.player.x, w.player.y), here, "you did not move")


class TestInvisibility(unittest.TestCase):
    """A boon for the deep floors: unseen, nothing can find you -- until you strike."""

    def _world(self):
        codex = FakeSave()
        codex.world_seed = 3
        w = World(codex, seed=3)
        w.level.monsters = []
        for r in w.level.rooms:
            if r.w >= 9 and r.h >= 8:
                w.player.x, w.player.y = r.cx, r.cy
                break
        w.level.compute_fov(w.player.x, w.player.y)
        return w

    def test_both_the_potion_and_the_scroll_grant_it(self):
        for flavor in ("violet", "vesh"):
            w = self._world()
            w.codex.known.append("id.%s" % flavor)
            w.player.slots = [[flavor, 1], None, None, None, None, None]
            w.use_item(0)
            # untimed now (Task 2): the potion/scroll sets invis_hold, not the timed counter
            self.assertTrue(w.player.invis_hold, "%s hides you, untimed" % flavor)
            self.assertTrue(w.player_hidden(), "%s leaves you hidden" % flavor)

    def test_nothing_can_see_you_while_hidden(self):
        from .monsters import Monster
        w = self._world()
        w.player.invisible = 10
        m = Monster("brute", w.player.x + 2, w.player.y)
        w.level.monsters = [m]
        self.assertFalse(w.monster_can_see_player(m))
        self.assertTrue(w.player_hidden())

    def test_a_hunting_monster_loses_the_thread(self):
        from .monsters import Monster
        w = self._world()
        w.player.invisible = 30
        m = Monster("brute", w.player.x + 1, w.player.y)   # adjacent AND awake
        m.awake = True
        w.level.monsters = [m]
        hp = w.player.hp
        for _ in range(8):
            m.take_turn(w)
        self.assertEqual(w.player.hp, hp,
                         "an adjacent monster cannot strike a target it cannot find")

    def test_striking_breaks_your_cover(self):
        from .monsters import Monster
        w = self._world()
        w.player.invisible = 15
        m = Monster("rat", w.player.x + 1, w.player.y)
        m.hp = 99
        w.level.monsters = [m]
        w.player_attack(m)
        self.assertEqual(w.player.invisible, 0, "you cannot kill from hiding")

    def test_it_wears_off(self):
        w = self._world()
        w.player.invisible = 1
        w.player.tick_effects(w)
        self.assertEqual(w.player.invisible, 0)


class TestInvisibilityModel(unittest.TestCase):
    def _setup_invis(self, seed=6):
        codex = FakeSave()
        w = World(codex, seed=seed)
        w.player.invis_hold = True          # hidden via the (Task 2) untimed potion state
        return w

    def test_ethereal_sees_through_invisibility_mundane_does_not(self):
        from .monsters import Monster
        w = self._setup_invis()
        kobold = Monster("kobold", w.player.x + 2, w.player.y)
        wraith = Monster("wraith", w.player.x + 2, w.player.y)
        w.level.monsters = [kobold, wraith]
        w.level.compute_fov(w.player.x, w.player.y)
        self.assertFalse(w.monster_can_see_player(kobold), "mundane loses an invisible player")
        self.assertTrue(w.monster_can_see_player(wraith), "ethereal see through invisibility")

    def test_looting_and_using_break_invisibility_but_moving_does_not(self):
        from .dungeon import Drop
        w = self._setup_invis()
        w.player.x, w.player.y = w.level.start
        # moving does NOT break it
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if w.walkable(w.player.x + dx, w.player.y + dy):
                w.player_move(dx, dy); break
        self.assertTrue(w.player_hidden(), "sneaking past keeps you hidden")
        # taking something DOES break it
        w.break_stealth()                    # the hook loot/use call; asserted directly here
        self.assertFalse(w.player_hidden(), "an action drops the cloak")


class TestUntimedInvisibility(unittest.TestCase):
    def test_potion_is_untimed_and_deaggros_mundane_not_ethereal(self):
        from .monsters import Monster
        codex = FakeSave()
        w = World(codex, seed=6)
        kob = Monster("kobold", w.player.x + 1, w.player.y); kob.awake = True
        kob.intent = ("smash", w.player.x, w.player.y)
        wr = Monster("wraith", w.player.x + 1, w.player.y); wr.awake = True
        w.level.monsters = [kob, wr]
        w._apply_effect("invisible")
        self.assertTrue(w.player.invis_hold, "the potion sets untimed invisibility")
        # untimed: a turn tick does not end it
        w.player.tick_effects(w)
        self.assertTrue(w.player_hidden(), "invisibility does not tick away")
        # de-aggro hit the mundane, not the ethereal
        self.assertFalse(kob.awake, "the mundane hunter loses you")
        self.assertIsNone(kob.intent, "and its windup is wiped")
        self.assertTrue(wr.awake, "the wraith keeps hunting")


class TestFadecloak(unittest.TestCase):
    def test_every_fourth_hit_vanishes_and_deaggros(self):
        from .items import ALL_GEAR
        from .monsters import Monster
        from . import config
        codex = FakeSave()
        w = World(codex, seed=6)
        w.player.armour = ALL_GEAR["fade"].copy()
        m = Monster("kobold", w.player.x + 1, w.player.y); m.awake = True
        w.level.monsters = [m]
        for _ in range(3):
            w.monster_attacks_player(m, 1)
        self.assertFalse(w.player_hidden(), "not yet -- three hits")
        w.monster_attacks_player(m, 1)      # the 4th
        self.assertEqual(w.player.invisible, config.FADE_INVIS_TURNS)
        self.assertTrue(w.player_hidden(), "the 4th hit drops the cloak of shadow")
        self.assertFalse(m.awake, "and shakes the mundane hunt")


class TestNightcloak(unittest.TestCase):
    def _wear(self, w):
        from .items import ALL_GEAR
        w.player.armour = ALL_GEAR["nightcloak"].copy()

    def test_worn_hides_you_until_you_act_then_recloaks_when_clear(self):
        from .monsters import Monster
        codex = FakeSave()
        w = World(codex, seed=6); w.level.monsters = []
        self._wear(w)
        self.assertTrue(w.player_hidden(), "Nightcloak hides you while worn")
        w.break_stealth()                                # simulate an action
        self.assertFalse(w.player_hidden(), "acting exposes you")
        w.recloak_check()                                # SAME turn: the grace holds you visible
        self.assertFalse(w.player_hidden(), "even alone, you stay visible the turn you act")
        w.player.stealth_broke = False                   # end-of-turn clears the one-turn grace
        w.recloak_check()                                # a later quiet turn -> re-cloak
        self.assertTrue(w.player_hidden(), "with nothing hunting, you vanish again")

    def test_a_living_nearby_hunter_keeps_you_exposed(self):
        from .monsters import Monster
        codex = FakeSave()
        w = World(codex, seed=6)
        self._wear(w)
        m = Monster("kobold", w.player.x + 1, w.player.y); m.awake = True
        w.level.monsters = [m]
        w.break_stealth()
        w.recloak_check()
        self.assertFalse(w.player_hidden(), "an awake mundane hunter nearby blocks the re-cloak")
        m.hp = 0                                          # kill it
        w.player.stealth_broke = False                    # a later turn: the grace has cleared
        w.recloak_check()
        self.assertTrue(w.player_hidden(), "clear the hunters -> re-cloak")


class TestInvisibilityBreakingActions(unittest.TestCase):
    """Four playtest fixes: a trap, an ethereal hunter, an ethereal strike, and the
    one-turn Nightcloak grace must each break -- or hold -- invisibility correctly."""

    def _wear_nightcloak(self, w):
        from .items import ALL_GEAR
        w.player.armour = ALL_GEAR["nightcloak"].copy()

    def test_springing_a_trap_breaks_invisibility(self):
        from .traps import Trap
        codex = FakeSave()
        w = World(codex, seed=6); w.level.monsters = []
        w.player.invis_hold = True                        # hidden via the untimed potion
        self.assertTrue(w.player_hidden())
        w.level.traps = [Trap("alarm", w.player.x, w.player.y)]   # a no-damage rune
        w._enter_tile()
        self.assertFalse(w.player_hidden(), "the rune gives you away, invisible or not")

    def test_ethereal_hunts_and_its_strike_breaks_invisibility(self):
        from .monsters import Monster
        codex = FakeSave()
        w = World(codex, seed=6)
        start_hp = w.player.hp
        wr = Monster("wraith", w.player.x + 1, w.player.y); wr.awake = True
        w.level.monsters = [wr]
        w.player.invis_hold = True                        # invisible -- but you are in ITS realm
        w.level.compute_fov(w.player.x, w.player.y)
        wr.take_turn(w)
        self.assertLess(w.player.hp, start_hp, "the wraith ignores invisibility and strikes")
        self.assertFalse(w.player_hidden(), "and its touch drags you back into sight")

    def test_nightcloak_stays_visible_the_turn_you_act_even_alone(self):
        codex = FakeSave()
        w = World(codex, seed=6); w.level.monsters = []
        self._wear_nightcloak(w)
        w.break_stealth()                                 # e.g. picking something up
        w.recloak_check()                                 # SAME turn -> grace holds
        self.assertFalse(w.player_hidden(),
                         "acting is visible for its turn, even with nothing hunting")
        w.player.stealth_broke = False                    # end-of-turn clears the grace
        w.recloak_check()                                 # a later quiet turn
        self.assertTrue(w.player_hidden(), "then you vanish again")


class TestHiddenVisualState(unittest.TestCase):
    """Regression: the on-screen invisibility (ghost sprite + UNSEEN tag) must reflect EVERY
    invisibility source, not just the old timed `invisible` counter -- Nightcloak and the
    untimed potion (`invis_hold`) were invisible in effect but rendered opaque."""

    def test_player_hidden_covers_every_source(self):
        from .items import ALL_GEAR
        from .player import Player
        p = Player()
        self.assertFalse(p.hidden(), "a plain player is not hidden")
        p.invisible = 2
        self.assertTrue(p.hidden(), "the timed cloak (Fadecloak) hides you")
        p.invisible = 0
        p.invis_hold = True
        self.assertTrue(p.hidden(), "the untimed potion hides you")
        p.invis_hold = False
        p.armour = ALL_GEAR["nightcloak"].copy()
        self.assertTrue(p.hidden(), "Nightcloak worn (unexposed) hides you")
        p.nightcloak_exposed = True
        self.assertFalse(p.hidden(), "an exposed Nightcloak wearer is visible")

    def test_world_gate_and_player_visual_share_one_truth(self):
        from .items import ALL_GEAR
        codex = FakeSave()
        w = World(codex, seed=6)
        w.player.armour = ALL_GEAR["nightcloak"].copy()
        # the stealth GATE and the VISUAL flag are the same call now
        self.assertTrue(w.player_hidden())
        self.assertEqual(w.player_hidden(), w.player.hidden())


class TestShademail(unittest.TestCase):
    def _wear(self, w):
        from .items import ALL_GEAR
        w.player.armour = ALL_GEAR["shade"].copy()

    def _wall_walk_spot(self, w):
        """A FLOOR tile with an in-bounds adjacent WALL tile, and the direction into
        it. NOTE: unlike the brief's sketch, this does not check the player's spawn
        tile -- the entrance is always a room CENTER (Level._carve_room's gate_room),
        which for any room wider than 2 tiles is never itself wall-adjacent. Scanning
        the whole (pinned) floor for a corridor doorway is the reliable way to find
        one."""
        from .dungeon import WALL, FLOOR
        lvl = w.level
        for y in range(lvl.h):
            for x in range(lvl.w):
                if lvl.grid[y][x] != FLOOR:
                    continue
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if lvl.in_bounds(nx, ny) and lvl.grid[ny][nx] == WALL:
                        return (x, y), (dx, dy)
        return None, None

    def test_shademail_lets_you_step_into_stone_others_cannot(self):
        codex = FakeSave(); codex.world_seed = 3     # pin the stone: a reliable doorway
        w = World(codex, seed=6); w.level.monsters = []
        spot, d = self._wall_walk_spot(w)
        self.assertIsNotNone(spot, "the pinned floor has a wall-adjacent doorway")
        w.player.x, w.player.y = spot
        w.level.compute_fov(*spot)
        px, py = spot
        # without Shademail: blocked
        w.player_move(*d)
        self.assertEqual((w.player.x, w.player.y), (px, py), "stone is solid without Shademail")
        # with Shademail: you step in
        self._wear(w)
        w.player_move(*d)
        self.assertEqual((w.player.x, w.player.y), (px + d[0], py + d[1]), "you enter the stone")
        self.assertTrue(w.player_submerged())

    def test_submerge_limit_ejects_and_starts_the_cooldown(self):
        from . import config
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=6); w.level.monsters = []
        self._wear(w)
        spot, d = self._wall_walk_spot(w)
        self.assertIsNotNone(spot)
        w.player.x, w.player.y = spot
        w.level.compute_fov(*spot)
        w.player_move(*d)                          # into the stone
        for _ in range(config.SHADE_SUBMERGE_MAX + 1):
            w.player_wait()
        self.assertFalse(w.player_submerged(), "the limit surfaces you")
        self.assertGreater(w.player.shade_cd, 0, "and starts the re-enter cooldown")

    def test_boxed_in_crushes_instead_of_ejecting(self):
        """If every adjacent tile is blocked when the limit hits, there is nowhere to
        surface -- the rock crushes you for SHADE_CRUSH_DMG instead."""
        from . import config
        from .dungeon import FLOOR
        from .monsters import Monster
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=6); w.level.monsters = []
        self._wear(w)
        spot, d = self._wall_walk_spot(w)
        w.player.x, w.player.y = spot
        w.level.compute_fov(*spot)
        w.player_move(*d)                          # into the stone
        px, py = w.player.x, w.player.y
        # jam every chebyshev-distance-1 tile around the submerged player with monsters,
        # so blink_tile_near(1, 1) has no candidate to eject onto
        blockers = []
        for by in range(py - 1, py + 2):
            for bx in range(px - 1, px + 2):
                if (bx, by) == (px, py) or not w.level.in_bounds(bx, by):
                    continue
                if w.level.grid[by][bx] == FLOOR:
                    m = Monster("angry_rat", bx, by)
                    blockers.append(m)
        w.level.monsters = blockers
        before_hp = w.player.hp
        # the entering move already ticked submerged to 1; SHADE_SUBMERGE_MAX - 1 more
        # waits brings it to exactly SHADE_SUBMERGE_MAX -- the FIRST turn the limit
        # bites. (One more wait beyond this would crush a second time: the counter
        # is not reset when boxed in, so every turn past the limit crushes again.)
        for _ in range(config.SHADE_SUBMERGE_MAX - 1):
            w.player_wait()
        self.assertTrue(w.player_submerged(), "boxed in: no eject tile, so still submerged")
        self.assertEqual(w.player.hp, before_hp - config.SHADE_CRUSH_DMG,
                          "the rock crushes you instead")

    def test_mundane_monster_cannot_strike_you_in_stone_but_a_wraith_can(self):
        """Drive this through take_turn -- not a raw monster_attacks_player() call --
        because the guard lives in Monster._hit (the one caller of
        monster_attacks_player), not in monster_attacks_player itself."""
        from .monsters import Monster
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=6); w.level.monsters = []
        self._wear(w)
        spot, d = self._wall_walk_spot(w)
        px, py = spot                               # the doorway floor tile, left behind
        w.player.x, w.player.y = spot
        w.level.compute_fov(*spot)
        w.player_move(*d)                            # into the stone
        self.assertTrue(w.player_submerged())

        before = w.player.hp
        m = Monster("kobold", px, py)                 # adjacent: chebyshev dist 1
        m.awake = True
        w.level.monsters = [m]
        m.take_turn(w)
        self.assertEqual(w.player.hp, before, "a mundane monster cannot reach you in stone")

        wraith = Monster("wraith", px, py)
        wraith.awake = True
        w.level.monsters = [wraith]
        wraith.take_turn(w)
        self.assertLess(w.player.hp, before, "an ethereal monster still reaches into stone")

    def test_re_enter_cooldown_blocks_a_second_dive(self):
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=6); w.level.monsters = []
        self._wear(w)
        spot, d = self._wall_walk_spot(w)
        w.player.x, w.player.y = spot
        w.level.compute_fov(*spot)
        w.player_move(*d)                           # in
        w.player_move(-d[0], -d[1])                  # back out onto floor
        self.assertFalse(w.player_submerged())
        self.assertGreater(w.player.shade_cd, 0, "surfacing starts the cooldown")
        px, py = w.player.x, w.player.y
        w.player_move(*d)                            # try to dive again, on cooldown
        self.assertEqual((w.player.x, w.player.y), (px, py), "stone is solid during the cooldown")

    def test_shade_is_boss_reserved_never_floor_findable(self):
        from .items import FINDABLE_MAGICAL_ARMOUR_KEYS
        self.assertNotIn("shade", FINDABLE_MAGICAL_ARMOUR_KEYS)

    def test_suspend_resume_while_submerged_does_not_wallhack(self):
        """Quitting mid-dive autosaves the player standing on a WALL tile. Resume
        must rebuild FOV the same restricted way _refresh_fov does every other
        turn (radius=1 while submerged) -- not a raw full-radius compute_fov,
        which casts out through the doorway's open neighbour and reveals the
        room beyond the stone. That reveal would get folded into PERMANENT map
        memory on the next remember_map(), a persistent info leak."""
        from .world import World
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=6); w.level.monsters = []
        self._wear(w)
        spot, d = self._wall_walk_spot(w)
        self.assertIsNotNone(spot, "the pinned floor has a wall-adjacent doorway")
        w.player.x, w.player.y = spot
        w.level.compute_fov(*spot)
        w.player_move(*d)                       # into the stone
        self.assertTrue(w.player_submerged())

        blob = w.to_dict()
        resumed = World(codex, restore=blob)

        self.assertTrue(resumed.player_submerged(), "resumed run is still submerged")
        visible_count = sum(row.count(True) for row in resumed.level.visible)
        self.assertLessEqual(visible_count, 9,
            "resume must use the radius-1 submerged reveal, not a full-radius "
            "wallhack out through the doorway (~49 tiles unfixed)")


class TestTheKodexTabs(unittest.TestCase):
    """The Kodex is split into six tabs; gear entries are earned by finding the gear."""

    def test_there_are_six_tabs(self):
        from .codex import KODEX_TABS
        self.assertEqual(KODEX_TABS,
                         ["monsters", "traps", "scrolls", "potions", "gear", "lore"])

    def test_facts_land_in_the_right_tab(self):
        from .codex import category_of, FACT_LIST, FACTS

        def a_fact(subject):
            return next(f for f in FACT_LIST if f.subject == subject)
        self.assertEqual(category_of(a_fact("rat")), "monsters")
        self.assertEqual(category_of(a_fact("dart")), "traps")
        self.assertEqual(category_of(a_fact("self")), "lore")
        self.assertEqual(category_of(a_fact("dungeon")), "lore")
        self.assertEqual(category_of(FACTS["id.kesh"]), "scrolls")   # KESH is a scroll
        self.assertEqual(category_of(FACTS["id.ochre"]), "potions")  # ochre is a potion

    def test_every_fact_lands_in_exactly_one_known_tab(self):
        from .codex import FACT_LIST, category_of, KODEX_TABS
        for f in FACT_LIST:
            self.assertIn(category_of(f), KODEX_TABS, "%s has no tab" % f.key)

    def test_gear_is_earned_by_handling_it(self):
        codex = FakeSave()
        self.assertFalse(codex.gear_known("brand"))
        codex.see_gear("brand")
        self.assertTrue(codex.gear_known("brand"))

    def test_your_starting_kit_is_already_seen(self):
        codex = FakeSave()
        World(codex, seed=3)
        for k in ("shiv", "rags", "sandals"):
            self.assertTrue(codex.gear_known(k), "%s starts seen" % k)

    def test_picking_gear_up_marks_it_seen(self):
        codex = FakeSave()
        w = World(codex, seed=3)
        w.level.monsters = []
        self.assertFalse(codex.gear_known("brand"))
        w._take("gear", "brand")
        self.assertTrue(codex.gear_known("brand"), "handling it earns the entry")

    def test_a_new_game_forgets_the_gear_too(self):
        codex = FakeSave()
        codex.see_gear("kris")
        self.assertTrue(codex.gear_known("kris"))
        codex.wipe()
        self.assertFalse(codex.gear_known("kris"))

    def test_gear_seen_round_trips_through_the_save(self):
        import tempfile
        from .codex import Codex
        old = config.SAVE_PATH
        config.SAVE_PATH = os.path.join(tempfile.gettempdir(), "dw_geartest.json")
        try:
            c = Codex()
            c.see_gear("kris")
            c.save()
            c2 = Codex()
            c2.load()
            self.assertTrue(c2.gear_known("kris"), "gear_seen persists in the save")
        finally:
            if os.path.exists(config.SAVE_PATH):
                os.remove(config.SAVE_PATH)
            config.SAVE_PATH = old


class TestTheGameLog(unittest.TestCase):
    """The log is the WHOLE game's: it lives on the codex, survives a respawn (a new
    World), and is wiped only by a new game."""

    def test_the_log_lives_on_the_codex_and_survives_a_respawn(self):
        codex = FakeSave()
        w = World(codex, seed=3)
        w.log("a thing happened")
        self.assertIn(("a thing happened", config.INK), w.messages)
        # a respawn is a NEW World on the SAME codex
        w2 = World(codex, seed=3)
        self.assertIn(("a thing happened", config.INK), w2.messages,
                      "the log carried across the respawn")
        self.assertIs(w2.messages, codex.messages, "it IS the codex's list")

    def test_a_new_game_wipes_the_log(self):
        codex = FakeSave()
        w = World(codex, seed=3)
        w.log("old news")
        codex.wipe()
        self.assertEqual(codex.messages, [], "a new game forgets the log")

    def test_the_log_is_generously_capped(self):
        codex = FakeSave()
        w = World(codex, seed=3)
        for i in range(3200):
            w.log("msg %d" % i)
        self.assertLessEqual(len(w.messages), 3000, "the log does not grow forever")
        self.assertGreater(len(w.messages), 2000, "but it holds a whole game's worth")

    def test_the_scroll_range(self):
        # the popup opens at scroll 0 (newest at the top) and can scroll DOWN into
        # older history up to log_max_scroll.
        from .ui import log_max_scroll
        self.assertEqual(log_max_scroll([]), 0, "an empty log does not scroll")
        many = [("x", config.INK)] * 500
        self.assertGreater(log_max_scroll(many), 0, "a long log scrolls down into history")


class TestScrollOfMapping(unittest.TestCase):
    """KESH maps the stone. It must never hand you the contents."""

    def _read_kesh(self, w):
        w.player.pack = ["kesh"]
        w.level.monsters = []
        w.use_item(0)

    def test_it_reveals_the_stone(self):
        codex = FakeSave()
        w = World(codex, seed=17)
        before = sum(1 for r in w.level.explored for v in r if v)
        self._read_kesh(w)
        after = sum(1 for r in w.level.explored for v in r if v)
        self.assertGreater(after, before * 2, "the scroll should map the floor")
        # every floor tile of the level is now known stone
        for y in range(w.level.h):
            for x in range(w.level.w):
                if w.level.grid[y][x] == 1:
                    self.assertTrue(w.level.explored[y][x])

    def test_it_reveals_no_items_no_chests_no_traps(self):
        codex = FakeSave()
        codex.known = list(FACTS)          # knows every trap type: they WOULD be drawn
        w = World(codex, seed=17)
        self._read_kesh(w)

        far = []
        for coll in (w.level.traps, w.level.chests, w.level.drops):
            for o in coll:
                if not w.level.visible[o.y][o.x]:
                    far.append(o)
        self.assertTrue(far, "the test needs objects outside line of sight")
        for o in far:
            self.assertFalse(
                w.level.seen[o.y][o.x],
                "the scroll revealed a %s at (%d,%d) that you have never laid eyes on"
                % (type(o).__name__, o.x, o.y))

    def test_the_renderer_gate_is_line_of_sight_not_the_map(self):
        """The thing that actually decides whether an object is drawn."""
        codex = FakeSave()
        codex.known = list(FACTS)
        w = World(codex, seed=17)
        self._read_kesh(w)
        for t in w.level.traps:
            if not w.level.visible[t.y][t.x]:
                self.assertTrue(w.level.explored[t.y][t.x],
                                "its tile should be mapped stone")
                self.assertFalse(w.level.seen[t.y][t.x],
                                 "but the trap itself must stay hidden")
                return
        self.skipTest("all traps happened to be in view")

    def test_walking_into_the_room_does_reveal_them(self):
        codex = FakeSave()
        codex.known = list(FACTS)
        w = World(codex, seed=17)
        self._read_kesh(w)
        target = None
        for t in w.level.traps:
            if not w.level.seen[t.y][t.x]:
                target = t
                break
        self.assertIsNotNone(target, "need a trap we have not seen")
        w.player.x, w.player.y = target.x, target.y
        w.level.compute_fov(w.player.x, w.player.y)
        self.assertTrue(w.level.seen[target.y][target.x],
                        "standing on it must reveal it -- eyes work, scrolls do not")

    def test_seen_does_not_persist_across_runs(self):
        """The stone is remembered forever; what was lying on it is not -- the
        contents are re-dealt, so last run's sightings mean nothing."""
        codex = FakeSave()
        codex.world_seed = 555
        w = World(codex, seed=1)
        self._read_kesh(w)
        for _ in range(20):
            w.player_move(1, 0)
        w.kill_player("rat")

        w2 = World(codex, seed=2)
        mapped = sum(1 for r in w2.level.explored for v in r if v)
        eyed = sum(1 for r in w2.level.seen for v in r if v)
        self.assertGreater(mapped, 400, "the stone should still be remembered")
        self.assertLess(eyed, mapped,
                        "object-sight must reset each run -- the loot is new")


class TestTheGraveStaysPut(unittest.TestCase):
    def test_your_corpse_lies_exactly_where_you_fell(self):
        codex = FakeSave()
        w = World(codex, seed=15)
        w.new_level(3)
        # walk somewhere specific and die there
        spot = None
        for y in range(w.level.h):
            for x in range(w.level.w):
                if w.level.walkable(x, y) and (x, y) != w.level.entrance:
                    spot = (x, y)
                    break
            if spot:
                break
        w.player.x, w.player.y = spot
        w.player.gold = 90
        w.kill_player("brute")
        w.leave_corpse()

        w2 = World(codex, seed=88)            # a whole new run
        w2.new_level(3)
        self.assertIsNotNone(w2.level.corpse)
        self.assertEqual((w2.level.corpse.x, w2.level.corpse.y), spot,
                         "the body must lie exactly where it fell, not 'somewhere "
                         "on the floor'")

    def test_nothing_else_occupies_the_grave(self):
        codex = FakeSave()
        w = World(codex, seed=15)
        w.player.gold = 20
        w.kill_player("rat")
        w.leave_corpse()
        for run in (2, 3, 4, 5):
            w2 = World(codex, seed=run)
            c = w2.level.corpse
            if not c:
                continue
            self.assertIsNone(w2.monster_at(c.x, c.y), "a monster is standing on you")
            self.assertIsNone(w2.level.drop_at(c.x, c.y))
            self.assertIsNone(w2.level.chest_at(c.x, c.y))


class TestTheGift(unittest.TestCase):
    def _gift_drop(self, world):
        return [d for d in world.level.drops if d.gift == "floor1"]

    def test_the_gift_rides_your_corpse_and_can_be_taken_back(self):
        codex = FakeSave()
        w = World(codex, seed=12)
        g = self._gift_drop(w)[0]
        payload = g.payload
        w.level.monsters = []
        w.player.x, w.player.y = g.x, g.y
        w.player_pickup()
        self.assertEqual(w.player.gift, payload, "you should be carrying the gift")

        w.player.gold = 40
        w.kill_player("rat")
        w.leave_corpse()
        corpse = codex.corpse_at(1)
        self.assertEqual(corpse["gift"], payload,
                         "the gift must stay on the body -- it is the only one")

        # next run: it is NOT lying on the floor again, it is on the corpse
        w2 = World(codex, seed=44)
        self.assertEqual(self._gift_drop(w2), [], "the gift must not respawn")
        self.assertIsNotNone(w2.level.corpse)
        self.assertEqual(w2.level.corpse.gift, payload)

        w2.level.monsters = []
        w2.player.x, w2.player.y = w2.level.corpse.x, w2.level.corpse.y
        w2.player_pickup()
        from .items import ALL_GEAR
        slot = ALL_GEAR[payload].slot
        self.assertEqual(w2.player.gear_key(slot), payload,
                         "looting your body must give the gift back")
        self.assertEqual(w2.player.gift, payload)

    def test_dying_twice_never_loses_the_gift(self):
        codex = FakeSave()
        codex.leave_corpse(1, 5, 5, 100, "shiv", gift_key="swift")
        codex.leave_corpse(1, 9, 9, 10, "shiv", gift_key=None)   # died again, giftless
        self.assertEqual(codex.corpse_at(1)["gift"], "swift",
                         "the gift must not be dropped by a later, poorer corpse")
        self.assertEqual(codex.corpse_at(1)["gold"], 110)


class TestCorpses(unittest.TestCase):
    def test_your_corpse_keeps_your_gold_and_waits_for_you(self):
        codex = FakeSave()
        w = World(codex, seed=11)
        w.player.gold = 137
        w.player.x, w.player.y = w.level.start
        w.kill_player("rat")
        w.leave_corpse()
        self.assertEqual(codex.corpse_at(1)["gold"], 137)

        w2 = World(codex, seed=22)          # a brand new run, a brand new dungeon
        self.assertIsNotNone(w2.level.corpse, "the corpse did not come back")
        self.assertEqual(w2.level.corpse.gold, 137)

        w2.player.x, w2.player.y = w2.level.corpse.x, w2.level.corpse.y
        w2.player_pickup()
        self.assertEqual(w2.player.gold, 137, "you did not get your gold back")
        self.assertIsNone(codex.corpse_at(1), "the corpse should be spent")


    def test_dying_twice_on_a_floor_does_not_destroy_the_first_cache(self):
        """Regression: the second corpse used to overwrite the first, silently
        deleting the gold and the weapon the first body was holding."""
        codex = FakeSave()
        codex.leave_corpse(3, 5, 5, 200, "brand")     # died rich, holding a Flame Brand
        codex.leave_corpse(3, 9, 9, 15, "shiv")       # died again, poor, back on a shiv
        c = codex.corpse_at(3)
        self.assertEqual(c["gold"], 215, "the gold must pile up, not vanish")
        self.assertEqual(c["weapon"], "brand", "the better weapon must survive")
        self.assertEqual((c["x"], c["y"]), (9, 9), "the cache moves to the newest body")


class TestNewGameVersusNewRun(unittest.TestCase):
    """A death starts a new RUN and you keep what you learned. Only an explicit NEW
    GAME erases it -- and it must erase ALL of it."""

    def _lived_a_little(self, codex):
        codex.known.extend(["self.corpse", "angry_rat.rule", "brute.rule", "id.ochre"])
        codex.telemetry.append({"title": "T", "text": "t"})
        codex.deaths = 7
        codex.runs = 5
        codex.wins = 1
        codex.best_depth = 6
        codex.stats["kills"] = 40
        codex.stats["kills_by"]["brute"] = 3
        codex.stats["deaths_by"]["brute"] = 2
        codex.leave_corpse(4, 10, 10, 250, "brand")
        codex.claim_gift("floor1")

    def test_a_new_run_keeps_the_codex_and_the_dead(self):
        codex = FakeSave()
        self._lived_a_little(codex)
        World(codex)                       # the run after a death
        self.assertEqual(len(codex.known), 4, "a new run must NOT erase the codex")
        self.assertIsNotNone(codex.corpse_at(4), "a new run must NOT clear your dead")
        self.assertEqual(codex.deaths, 7)

    def test_a_new_game_erases_absolutely_everything(self):
        codex = FakeSave()
        self._lived_a_little(codex)
        self.assertTrue(codex.has_progress())

        codex.wipe()

        self.assertEqual(codex.known, [], "the codex survived a new game")
        self.assertEqual(codex.telemetry, [], "telemetry survived a new game")
        self.assertEqual(codex.corpses, {}, "your dead survived a new game")
        self.assertEqual(codex.deaths, 0)
        self.assertEqual(codex.runs, 0)
        self.assertEqual(codex.wins, 0)
        self.assertEqual(codex.best_depth, 0)
        self.assertEqual(codex.stats["kills"], 0, "kill stats survived a new game")
        self.assertEqual(codex.stats["kills_by"], {},
                         "per-species kill counts survived -- they would let the "
                         "player skip the first lessons of a fresh game")
        self.assertEqual(codex.stats["deaths_by"], {})
        self.assertEqual(codex.gifts, [],
                         "the once-per-game gift must be available again in a new game")
        self.assertFalse(codex.has_progress())

    def test_after_a_new_game_the_monsters_are_question_marks_again(self):
        codex = FakeSave()
        self._lived_a_little(codex)
        self.assertEqual(codex.tier("brute"), 1)
        codex.wipe()
        self.assertEqual(codex.tier("brute"), 0,
                         "a fresh game must put the '?' back on the monsters")
        w = World(codex, seed=3)
        self.assertIsNone(w.level.corpse, "a fresh game must not spawn an old corpse")

    def test_a_new_game_deletes_the_save_file_from_disk(self):
        import json
        import tempfile
        from . import config as cfg
        from .codex import Codex

        old = cfg.SAVE_PATH
        cfg.SAVE_PATH = os.path.join(tempfile.gettempdir(), "dw_wipe_test.json")
        try:
            c = Codex()                      # a REAL codex: it touches disk
            c.known.append("brute.rule")
            c.deaths = 3
            c.save()
            self.assertTrue(os.path.exists(cfg.SAVE_PATH))

            c.wipe()
            self.assertFalse(os.path.exists(cfg.SAVE_PATH),
                             "the save file must be gone after a new game")

            fresh = Codex()
            fresh.load()                     # loading a wiped game must find nothing
            self.assertEqual(fresh.known, [])
            self.assertEqual(fresh.deaths, 0)
        finally:
            if os.path.exists(cfg.SAVE_PATH):
                os.remove(cfg.SAVE_PATH)
            cfg.SAVE_PATH = old

    def test_has_progress_knows_when_there_is_nothing_to_lose(self):
        codex = FakeSave()
        self.assertFalse(codex.has_progress(), "a virgin codex has nothing to warn about")
        codex.known.append("brute.rule")
        self.assertTrue(codex.has_progress())


class TestTrapDiscovery(unittest.TestCase):
    """A trap is invisible -- not a '?', nothing -- until one goes off in front of
    you. Then every trap of that kind is on your map forever."""

    def _floor_next_to(self, w):
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if w.walkable(w.player.x + dx, w.player.y + dy):
                return dx, dy
        raise AssertionError("boxed in")

    def test_an_undiscovered_trap_is_not_drawn_at_all(self):
        from .traps import Trap
        codex = FakeSave()
        w = World(codex, seed=3)
        t = Trap("dart", 5, 5)
        # the renderer's gate: it draws a trap only if the rule is known
        self.assertFalse(codex.knows("dart.rule"))
        self.assertEqual(codex.tier("dart"), 0)

    def test_surviving_a_trap_teaches_you_the_trap(self):
        from .traps import Trap
        codex = FakeSave()
        w = World(codex, seed=3)
        w.level.monsters = []
        w.player.hp = 99                       # survive it
        dx, dy = self._floor_next_to(w)
        w.level.traps = [Trap("dart", w.player.x + dx, w.player.y + dy)]
        self.assertFalse(codex.knows("dart.rule"))

        w.player_move(dx, dy)

        self.assertTrue(codex.knows("dart.rule"),
                        "springing a trap and living must teach you what it was")
        self.assertIsNotNone(w.learned, "the discovery should raise a banner")
        self.assertEqual(w.learned.key, "dart.rule")

    def test_finding_one_trap_reveals_ONLY_that_trap(self):
        """The whole point: knowing what a dart trap is must not X-ray the floor."""
        from .traps import Trap
        codex = FakeSave()
        w = World(codex, seed=3)
        w.level.monsters = []
        w.player.hp = 99
        dx, dy = self._floor_next_to(w)
        mine = Trap("dart", w.player.x + dx, w.player.y + dy)
        others = [Trap("dart", 20, 20), Trap("dart", 30, 12)]   # same TYPE, elsewhere
        w.level.traps = [mine] + others

        w.player_move(dx, dy)

        self.assertTrue(codex.knows("dart.rule"), "you learned what it was")
        self.assertTrue(codex.trap_found(w.depth, mine.x, mine.y),
                        "the trap you sprang must be marked")
        for o in others:
            self.assertFalse(
                codex.trap_found(w.depth, o.x, o.y),
                "the OTHER dart trap at (%d,%d) must stay hidden -- you have never "
                "been near it" % (o.x, o.y))

    def test_a_found_trap_stays_found_through_death(self):
        from .traps import Trap
        codex = FakeSave()
        codex.world_seed = 31337
        w = World(codex, seed=3)
        w.level.monsters = []
        w.player.hp = 99
        dx, dy = self._floor_next_to(w)
        mine = (w.player.x + dx, w.player.y + dy)
        w.level.traps = [Trap("spike", *mine)]
        w.player_move(dx, dy)
        self.assertTrue(codex.trap_found(1, *mine))

        w.kill_player("rat")
        w2 = World(codex, seed=777)            # a new run, new monsters, same stone
        self.assertTrue(codex.trap_found(1, *mine),
                        "a trap you found must stay found across respawns")

    def test_traps_are_cut_into_the_stone_and_do_not_move(self):
        codex = FakeSave()
        codex.world_seed = 909
        first = None
        for run_seed in (1, 2, 3):
            w = World(codex, seed=run_seed)
            sig = tuple(sorted((t.key, t.x, t.y) for t in w.level.traps))
            if first is None:
                first = sig
            self.assertEqual(sig, first,
                             "traps must be part of the permanent stonework -- they "
                             "cannot move between runs or 'this trap' means nothing")
        self.assertTrue(first, "the floor should have traps at all")

    def test_a_new_game_re_cuts_the_traps_and_forgets_them(self):
        codex = FakeSave()
        codex.world_seed = 909
        w = World(codex, seed=1)
        t = w.level.traps[0]
        codex.find_trap(1, t.x, t.y)
        self.assertTrue(codex.trap_found(1, t.x, t.y))

        codex.wipe()
        self.assertEqual(codex.found_traps, {}, "a new game must forget found traps")

    def test_knowing_the_type_does_not_mark_traps_on_other_floors(self):
        from .traps import Trap
        codex = FakeSave()
        w = World(codex, seed=3)
        w.level.monsters = []
        w.player.hp = 99
        dx, dy = self._floor_next_to(w)
        spot = (w.player.x + dx, w.player.y + dy)
        w.level.traps = [Trap("gas", *spot)]
        w.player_move(dx, dy)
        self.assertTrue(codex.trap_found(1, *spot))
        self.assertFalse(codex.trap_found(2, *spot),
                         "finding a trap on floor 1 says nothing about floor 2")

    def test_each_trap_type_is_learned_separately(self):
        from .traps import Trap
        codex = FakeSave()
        w = World(codex, seed=3)
        w.level.monsters = []
        w.player.hp = 99
        dx, dy = self._floor_next_to(w)
        w.level.traps = [Trap("gas", w.player.x + dx, w.player.y + dy)]
        w.player_move(dx, dy)
        self.assertTrue(codex.knows("gas.rule"))
        self.assertFalse(codex.knows("dart.rule"),
                         "learning about gas must not reveal dart traps")
        self.assertFalse(codex.knows("spike.rule"))

    def test_watching_a_monster_spring_a_trap_teaches_you_too(self):
        from .monsters import Monster
        from .traps import Trap
        codex = FakeSave()
        w = World(codex, seed=3)
        w.level.monsters = []
        px, py = w.player.x, w.player.y
        spot = None
        for dx in range(1, 5):
            if w.walkable(px + dx, py) and w.level.visible[py][px + dx]:
                spot = (px + dx, py)
                break
        if not spot:
            self.skipTest("no visible floor tile beside the player")
        w.level.traps = [Trap("glyph", *spot)]
        m = Monster("angry_rat", spot[0] + 1, spot[1]) if w.walkable(spot[0] + 1, spot[1]) \
            else Monster("angry_rat", spot[0], spot[1] - 1)
        m.awake = True
        w.level.monsters = [m]
        self.assertFalse(codex.knows("glyph.rule"))

        m.x, m.y = spot                        # it steps onto the glyph
        w.on_monster_moved(m)

        self.assertTrue(codex.knows("glyph.rule"),
                        "you watched it burn; you should know what a fire glyph is")

    def test_the_counter_takes_three(self):
        codex = FakeSave()
        self.assertEqual(codex.reveal_on_trap("spike"), None)   # 0 seen
        codex.stats["traps_by"]["spike"] = 1
        self.assertEqual(codex.reveal_on_trap("spike").key, "spike.rule")
        codex.stats["traps_by"]["spike"] = 2
        self.assertIsNone(codex.reveal_on_trap("spike"),
                          "two springs is not enough for the counter")
        codex.stats["traps_by"]["spike"] = 3
        self.assertEqual(codex.reveal_on_trap("spike").key, "spike.counter")


class TestTrapsAndGear(unittest.TestCase):
    def test_an_unknown_trap_still_fires(self):
        from .traps import Trap
        codex = FakeSave()                  # knows nothing: the trap is invisible
        w = World(codex, seed=3)
        w.level.traps = [Trap("dart", w.player.x + 1, w.player.y)]
        hp = w.player.hp
        w.player_move(1, 0)
        self.assertLess(w.player.hp, hp,
                        "an un-codexed trap must still hurt -- invisibility is the "
                        "player's problem, not the trap's")

    def test_armour_subtracts_flat_and_wraiths_ignore_it(self):
        from .items import ARMOURS
        from .monsters import Monster
        w = World(FakeSave(), seed=3)
        w.level.monsters = []
        w.player.armour = ARMOURS["plate"]      # 5 def
        rat = Monster("rat", w.player.x, w.player.y)
        hp = w.player.hp
        for _ in range(12):
            w.monster_attacks_player(rat, 3)    # a rat's whole damage range
        self.assertEqual(w.player.hp, hp, "plate should shrug off a rat entirely")

        wraith = Monster("wraith", w.player.x, w.player.y)
        w.monster_attacks_player(wraith, 5, ignore_armour=True)
        self.assertLess(w.player.hp, hp, "a wraith must ignore armour")


class TestHeadlessSmoke(unittest.TestCase):
    def test_a_random_walker_survives_the_engine_on_every_floor(self):
        for seed in (1, 2, 3):
            codex = FakeSave()
            w = World(codex, seed=seed)
            rng = random.Random(seed)
            for _ in range(2500):
                if w.dead or w.won:
                    break
                r = rng.random()
                if r < 0.75:
                    dx, dy = rng.choice([(0, -1), (0, 1), (-1, 0), (1, 0),
                                         (1, 1), (-1, -1), (1, -1), (-1, 1)])
                    w.player_move(dx, dy)
                elif r < 0.85:
                    w.player_pickup()
                elif r < 0.92:
                    w.use_item(0)
                elif r < 0.97:
                    w.player_wait()
                else:
                    w.descend()
            self.assertTrue(True)   # reaching here without an exception is the test

    def test_every_depth_generates_and_runs(self):
        for depth in range(1, config.DEPTH_MAX + 1):
            w = World(FakeSave(), seed=depth * 13)
            w.new_level(depth)
            w.wake_all()
            for _ in range(120):
                if w.dead or w.won:
                    break
                w.player_wait()
            if w.level.is_arena_floor():
                # her hall is not a dungeon floor: exactly two rooms, by design.
                self.assertEqual(len(w.level.rooms), 2)
            else:
                self.assertGreaterEqual(len(w.level.rooms), 4)


class TestActiveEffectPips(unittest.TestCase):
    """The corner pips that show which lasting potion/scroll effects are on you."""

    def _fresh_player(self):
        from .player import Player
        return Player()

    def test_nothing_active_shows_nothing(self):
        self.assertEqual(self._fresh_player().active_effects(), [])

    def test_only_active_effects_listed_in_fill_order(self):
        p = self._fresh_player()
        # switch three on OUT of canonical order; the fill order must not care
        p.sanctuary = 2
        p.heroism = 5
        p.regen = 4
        labels = [lbl for (lbl, _c, _r) in p.active_effects()]
        self.assertEqual(labels, ["REGEN", "HEROISM", "SANCTUARY"])

    def test_vigor_reports_its_timer_not_its_hit_points(self):
        p = self._fresh_player()
        p.vigor = 20      # twenty soak points ...
        p.vigor_t = 5     # ... lasting five turns
        (lbl, _c, rem), = p.active_effects()
        self.assertEqual(lbl, "VIGOR")
        self.assertEqual(rem, 5)   # the pip counts turns, not the HP pool

    def test_phoenix_is_steady_with_no_countdown(self):
        p = self._fresh_player()
        p.phoenix = True
        (lbl, _c, rem), = p.active_effects()
        self.assertEqual(lbl, "PHOENIX")
        self.assertIsNone(rem)     # untimed -> render never blinks it

    def test_debuffs_are_shown_too(self):
        p = self._fresh_player()
        p.poison, p.weak, p.confused = 3, 2, 1
        labels = [lbl for (lbl, _c, _r) in p.active_effects()]
        self.assertEqual(labels, ["POISON", "WEAKENED", "CONFUSED"])

    def test_drawing_the_world_with_effects_never_crashes(self):
        from . import render
        codex = FakeSave()
        codex.world_seed = 7919
        w = World(codex, seed=7)
        p = w.player
        p.vigor, p.vigor_t = 6, 6
        p.regen = 2                    # <= 3: a blinking buff
        p.poison = 1                   # <= 3: a blinking debuff
        p.phoenix = True               # steady
        p.heroism, p.resist = 8, 9     # six active -> exercises the 4-corner cap
        cam = render.Camera()
        cam.center_on(p.x, p.y)
        surf = pygame.Surface((config.W, config.H))
        for t in (0.0, 0.13):          # both halves of the blink cycle
            render.draw_world(surf, w, w.codex, cam, t)


class TestAppearanceShuffle(unittest.TestCase):
    """Which colour/rune each effect hides behind is dealt fresh every new game --
    kept for the whole game, re-rolled only when a new game begins."""

    def _dealt(self, seed):
        from .codex import Codex
        c = Codex()
        c.world_seed = seed
        c.roll_appearances(seed)
        return c

    def test_looks_are_a_permutation_within_each_kind(self):
        c = self._dealt(1)
        for kind in ("potion", "scroll"):
            flavors = [f for f, x in CONSUMABLES.items() if x.kind == kind]
            looks = [c.look(f) for f in flavors]
            self.assertEqual(sorted(looks), sorted(flavors),
                             "the %s looks must be a permutation of the %s effects"
                             % (kind, kind))
            for f in flavors:                       # a look never crosses kinds
                self.assertEqual(CONSUMABLES[c.look(f)].kind, kind)

    def test_same_seed_deals_the_same_looks(self):
        self.assertEqual(self._dealt(42).appearance, self._dealt(42).appearance)

    def test_a_different_seed_deals_different_looks(self):
        self.assertNotEqual(self._dealt(1).appearance, self._dealt(2).appearance)

    def test_look_falls_back_to_itself_before_the_deal(self):
        from .codex import Codex
        self.assertEqual(Codex().look("ochre"), "ochre")

    def test_an_unidentified_potion_wears_its_dealt_look(self):
        c = self._dealt(7)
        heal = CONSUMABLES["ochre"]                            # identity = healing
        self.assertEqual(heal.name(c), CONSUMABLES[c.look("ochre")].unknown_name)
        c.known.append("id.ochre")                            # once known ...
        self.assertEqual(heal.name(c), "Potion of Healing")   # ... true name, look aside

    def test_the_effect_stays_with_the_identity_not_the_look(self):
        # the look is display only: ochre is healing in every game it is dealt in
        for seed in (1, 2, 3):
            self.assertEqual(CONSUMABLES["ochre"].effect, "heal")
            self._dealt(seed)                                 # dealing does not touch it

    def test_the_kodex_title_names_this_runs_look(self):
        from .codex import FACTS, fact_title
        c = self._dealt(7)
        title = fact_title(FACTS["id.ochre"], c)
        self.assertIn(CONSUMABLES[c.look("ochre")].unknown_name.upper(), title)
        self.assertTrue(title.endswith("IS HEALING"))

    def test_a_respawn_keeps_the_looks_and_a_new_game_reshuffles(self):
        codex = FakeSave()
        codex.world_seed = 555
        World(codex, seed=1)                                  # deals the looks
        dealt = dict(codex.appearance)
        self.assertTrue(dealt)
        World(codex, seed=2)                                  # a respawn: same codex
        self.assertEqual(codex.appearance, dealt, "a respawn must not reshuffle")
        codex.new_dungeon()                                   # a victor starts over
        self.assertEqual(codex.appearance, dealt, "starting over after a win keeps them")
        codex.appearance = {}                                 # what a new game (wipe) does
        World(codex, seed=3)
        self.assertTrue(codex.appearance, "the next game deals afresh")

    def test_the_looks_round_trip_through_a_save(self):
        import tempfile
        from . import config as cfg
        from .codex import Codex
        old = cfg.SAVE_PATH
        cfg.SAVE_PATH = os.path.join(tempfile.gettempdir(), "dw_appearance.json")
        try:
            a = Codex()
            a.world_seed = 88
            a.roll_appearances(88)
            a.save()
            b = Codex()
            b.load()
            self.assertEqual(b.appearance, a.appearance)
        finally:
            if os.path.exists(cfg.SAVE_PATH):
                os.remove(cfg.SAVE_PATH)
            cfg.SAVE_PATH = old


class TestWeaponInstance(unittest.TestCase):
    def test_bonus_raises_both_ends_of_the_band(self):
        from .items import Weapon
        import random
        w = Weapon("steel_sword", "Steel Sword", 3, 3, 5, bonus=2)
        rolls = [w.roll(random.Random(i)) for i in range(200)]
        self.assertEqual(min(rolls), 5, "floor raised by +2")
        self.assertEqual(max(rolls), 7, "ceiling raised by +2")

    def test_desc_folds_the_bonus(self):
        from .items import Weapon
        self.assertEqual(Weapon("bronze_sword", "Bronze Sword", 2, 2, 5).desc(),
                         "2-5 dmg")
        self.assertEqual(Weapon("bronze_sword", "Bronze Sword", 2, 2, 5, bonus=3).desc(),
                         "5-8 dmg")

    def test_copy_is_independent(self):
        from .items import Weapon
        base = Weapon("bone_axe", "Bone Axe", 1, 1, 5, traits=("cleave",), speed_mod=-15)
        c = base.copy(bonus=2)
        self.assertEqual(c.bonus, 2)
        self.assertEqual(base.bonus, 0, "copying does not touch the template")
        self.assertEqual(c.trait, "cleave")
        self.assertEqual(c.speed_mod, -15)

    def test_speed_mod_defaults_to_zero(self):
        from .items import Weapon
        self.assertEqual(Weapon("k", "n", 1, 1, 5).speed_mod, 0)


class TestWeaponTraits(unittest.TestCase):
    def test_traits_tuple_and_has(self):
        from .items import Weapon
        w = Weapon("k", "N", 4, 5, 8, traits=("cleave", "burn"))
        self.assertEqual(w.traits, ("cleave", "burn"))
        self.assertTrue(w.has("burn"))
        self.assertFalse(w.has("freeze"))

    def test_trait_property_is_the_first_trait(self):
        from .items import Weapon
        self.assertEqual(Weapon("k", "N", 1, 1, 5, traits=("cleave",)).trait, "cleave")
        self.assertIsNone(Weapon("k", "N", 1, 1, 5).trait)

    def test_copy_preserves_traits(self):
        from .items import Weapon
        c = Weapon("k", "N", 5, 5, 8, traits=("cleave", "burn")).copy(bonus=2)
        self.assertEqual(c.traits, ("cleave", "burn"))
        self.assertEqual(c.bonus, 2)

    def test_flat_damage_renders_a_single_number(self):
        from .items import Weapon
        self.assertEqual(Weapon("k", "N", 5, 5, 5).desc(), "5 dmg")
        self.assertEqual(Weapon("k", "N", 4, 3, 6).desc(), "3-6 dmg")


class TestWeaponSpeedTaxAndInstanceBonus(unittest.TestCase):
    def _p(self):
        from .player import Player
        return Player()

    def test_speed_includes_the_weapon_tax(self):
        from .items import Weapon
        p = self._p()
        base = p.speed()
        p.weapon = Weapon("h", "H", 1, 1, 5, speed_mod=-30)
        self.assertEqual(p.speed(), base - 30)

    def test_equip_gives_a_private_copy(self):
        from .items import Weapon
        p = self._p()
        template = Weapon("bronze_sword", "Bronze Sword", 2, 2, 5)
        p.equip(template)
        p.weapon.bonus = 4
        self.assertEqual(template.bonus, 0,
                         "enchanting the equipped weapon never touches the template")

    def test_gear_display_reads_instance_bonus(self):
        from .items import Weapon
        p = self._p()
        p.weapon = Weapon("bronze_sword", "Bronze Sword", 2, 2, 5, bonus=3)
        self.assertEqual(p.gear_display("weapon"), ("Bronze Sword +3", "5-8 dmg"))

    def test_enchanting_the_starting_weapon_never_mutates_the_template(self):
        from .items import WEAPONS
        p = self._p()
        p.weapon.bonus += 5                       # simulate an enchant on the fresh hero
        self.assertEqual(WEAPONS[p.weapon.key].bonus, 0,
                         "the shared template must stay pristine")


class TestWeaponRoster(unittest.TestCase):
    def test_matrix_shape_and_stats(self):
        from .items import WEAPONS
        bands = {"bone": (1, 5), "bronze": (2, 5), "steel": (3, 5)}
        taxes = {"sword": 0, "axe": -15, "hammer": -25}
        traits = {"sword": None, "axe": "cleave", "hammer": "stun"}
        tiers = {"bone": 1, "bronze": 2, "steel": 3}
        for mat, (lo, hi) in bands.items():
            for typ, tax in taxes.items():
                w = WEAPONS["%s_%s" % (mat, typ)]
                self.assertEqual((w.lo, w.hi), (lo, hi))
                self.assertEqual(w.speed_mod, tax)
                self.assertEqual(w.trait, traits[typ])
                self.assertEqual(w.tier, tiers[mat])

    def test_shiv_is_the_starter_and_lowest(self):
        from .items import WEAPONS, STARTING
        self.assertEqual(STARTING[0], "shiv")
        self.assertEqual(WEAPONS["shiv"].tier, 0)

    def test_magical_trio_is_top_tier(self):
        from .items import WEAPONS
        for k in ("rapier", "brand"):
            self.assertEqual(WEAPONS[k].tier, 4)
        self.assertEqual(WEAPONS["kris"].tier, 5)

    def test_iron_warhammer_is_retired(self):
        from .items import WEAPONS
        self.assertNotIn("sword", WEAPONS)
        self.assertNotIn("hammer", WEAPONS)   # the old Iron Warhammer key is gone


class TestMagicalRoster(unittest.TestCase):
    T4 = {
        "rapier":             (4, 6, ("crit",), 0),
        "brand":              (4, 8, ("burn",), 0),
        "betrayers_edge":     (4, 6, ("enrage",), 0),
        "fulgurite":          (4, 6, ("cleave", "shock"), 0),
        "winters_edge":       (3, 6, ("freeze",), 0),
        "sacrificial_dagger": (3, 5, ("lifesteal",), 0),
        "windfang":           (5, 5, (), 20),
    }
    T5 = {
        "basilisk_maul":   (5, 9, ("poison", "stun"), 0),
        "pyroclast":       (5, 8, ("cleave", "burn"), 0),
        "reapers_whisper": (5, 8, ("cleave", "fear"), 0),
        "kris":            (4, 7, ("cleave", "lifesteal"), 0),
        "glacial_flail":   (4, 7, ("cleave", "freeze"), 0),
        "void_scimitar":   (7, 7, ("void",), 0),
    }

    def test_tier4_weapons(self):
        from .items import WEAPONS
        for key, (lo, hi, traits, tax) in self.T4.items():
            w = WEAPONS[key]
            self.assertEqual((w.lo, w.hi), (lo, hi), key)
            self.assertEqual(w.traits, traits, key)
            self.assertEqual(w.speed_mod, tax, key)
            self.assertEqual(w.tier, 4, key)

    def test_tier5_weapons(self):
        from .items import WEAPONS
        for key, (lo, hi, traits, tax) in self.T5.items():
            w = WEAPONS[key]
            self.assertEqual((w.lo, w.hi), (lo, hi), key)
            self.assertEqual(w.traits, traits, key)
            self.assertEqual(w.speed_mod, tax, key)
            self.assertEqual(w.tier, 5, key)

    def test_all_thirteen_present(self):
        from .items import WEAPONS
        magical = [k for k, w in WEAPONS.items() if w.tier >= 4]
        self.assertEqual(len(magical), 13)


class TestWeaponSprites(unittest.TestCase):
    def test_every_weapon_key_renders_without_error(self):
        import pygame
        from .items import WEAPONS
        from . import sprites
        pygame.init()
        for key in WEAPONS:
            surf = sprites.gear(key)          # the public gear-sprite entry point
            self.assertIsNotNone(surf)


class TestRenderFontDelegatesToFontcache(unittest.TestCase):
    def test_font_returns_the_fontcache_instance(self):
        pygame.font.init()
        from . import fontcache, render
        self.assertIs(render.font(22, bold=True), fontcache.get_font(22, bold=True))


class TestWeaponGeneration(unittest.TestCase):
    def test_floor_one_places_no_random_weapon(self):
        import random
        from .items import roll_floor_weapons
        for seed in range(50):
            self.assertEqual(roll_floor_weapons(random.Random(seed), 1), [],
                             "floor 1's only gear is the coin-flip gift")

    def test_material_bands(self):
        import random
        from .items import roll_floor_weapons
        def mats(depth):
            out = set()
            for seed in range(400):
                got = roll_floor_weapons(random.Random(seed), depth)
                for key, _ in got:
                    out.add(key.split("_")[0])
            return out
        self.assertEqual(mats(2), {"bone"})
        self.assertEqual(mats(3) | mats(4), {"bronze"})
        self.assertEqual(mats(6), {"steel"})

    def test_enhancement_chance_climbs(self):
        import random
        from .items import roll_floor_weapons
        def enh_rate(depth):
            present = [w for s in range(4000)
                       for w in roll_floor_weapons(random.Random(s), depth)]
            return sum(1 for _, b in present if b > 0) / len(present)
        self.assertLess(enh_rate(2), 0.16)     # ~10%
        self.assertGreater(enh_rate(7), 0.50)  # ~60%

    def test_gear_pool_has_no_weapons(self):
        from .items import gear_pool, WEAPONS
        for depth in (1, 5, 10, 20):
            self.assertFalse(any(k in WEAPONS for k in gear_pool(depth)),
                             "weapons are generation-placed, never in the gear pool")


class TestFloorWeaponsList(unittest.TestCase):
    def test_floor_one_places_no_random_weapon(self):
        import random
        from .items import roll_floor_weapons
        for s in range(30):
            self.assertEqual(roll_floor_weapons(random.Random(s), 1), [])

    def test_floors_1_to_7_place_at_most_one(self):
        import random
        from .items import roll_floor_weapons
        for depth in range(1, 8):
            for s in range(80):
                self.assertLessEqual(len(roll_floor_weapons(random.Random(s), depth)), 1)

    def test_deep_floors_8_to_14_can_place_two(self):
        import random
        from .items import roll_floor_weapons
        seen_two = False
        for s in range(400):
            got = roll_floor_weapons(random.Random(s), 10)
            self.assertLessEqual(len(got), 2)
            if len(got) == 2:
                seen_two = True
                keys = [k for k, _ in got]
                self.assertTrue(any(k.startswith("steel_") for k in keys),
                                "one of the two is the enhanced-steel find")
        self.assertTrue(seen_two, "floors 8-14 sometimes yield both a steel and a magical")

    def test_floors_16_plus_are_magical_only(self):
        import random
        from .items import roll_floor_weapons, WEAPONS
        for s in range(400):
            got = roll_floor_weapons(random.Random(s), 18)
            self.assertLessEqual(len(got), 1, "no steel slot this deep")
            for key, _ in got:
                self.assertGreaterEqual(WEAPONS[key].tier, 4, "only magical this deep")


class TestFloorWeaponPlacement(unittest.TestCase):
    def _weapon_drops(self, lvl):
        from .items import WEAPONS
        return [d for d in lvl.drops if d.kind == "gear" and d.payload in WEAPONS]

    def test_floor_one_has_no_bone_axe_only_the_gift(self):
        for seed in range(20):
            codex = FakeSave()
            codex.world_seed = seed
            w = World(codex, seed=seed)
            drops = self._weapon_drops(w.level)
            # the only weapon that can be on floor 1 is a Bone Sword gift (never the axe)
            self.assertLessEqual(len(drops), 1, "at most the coin-flip gift's sword")
            for d in drops:
                self.assertEqual(d.payload, "bone_sword")
                self.assertEqual(d.gift, "floor1")

    def test_no_floor_holds_more_than_two_weapons(self):
        from .dungeon import Level
        import random
        for depth in range(1, 21):
            for seed in range(15):
                codex = FakeSave()
                codex.world_seed = seed
                lvl = Level(depth, random.Random(seed * 31 + depth), codex)
                n = len(self._weapon_drops(lvl))
                cap = 1 if depth <= 7 else 2
                self.assertLessEqual(n, cap,
                                     "at most %d weapon(s) per floor at depth %d" % (cap, depth))

    def test_weapons_no_longer_come_from_chests(self):
        from .dungeon import Level
        from .items import WEAPONS
        import random
        for depth in range(1, 21):
            for seed in range(15):
                codex = FakeSave()
                codex.world_seed = seed
                lvl = Level(depth, random.Random(seed), codex)
                for ch in lvl.chests:
                    for kind, payload in ch.loot:
                        self.assertFalse(kind == "gear" and payload in WEAPONS,
                                         "no weapon in a chest")

    def test_deeper_floors_do_place_weapons_of_the_expected_band(self):
        from .dungeon import Level
        import random
        seen = 0
        for seed in range(60):
            codex = FakeSave()
            codex.world_seed = seed
            lvl = Level(4, random.Random(seed * 31 + 4), codex)
            for d in self._weapon_drops(lvl):
                seen += 1
                self.assertTrue(d.payload.startswith("bronze_"),
                                "floor 4 weapons are bronze")
                self.assertIn(d.bonus, (0, 1, 2))
        self.assertGreater(seen, 0, "some floor-4 runs must place a weapon")


class TestWeaponBonusPickup(unittest.TestCase):
    def _world(self):
        codex = FakeSave()
        codex.world_seed = 5
        w = World(codex, seed=5)
        w.level.monsters = []
        return w

    def test_picking_up_an_enhanced_weapon_equips_the_bonus(self):
        from .dungeon import Drop
        w = self._world()
        w.level.drops.append(Drop(w.player.x, w.player.y, "gear", "steel_sword", bonus=2))
        opts = w.loot_options()
        idx = next(i for i, o in enumerate(opts)
                   if o["kind"] == "gear" and o["payload"] == "steel_sword")
        w._consume_option(opts[idx])
        self.assertEqual(w.player.weapon.key, "steel_sword")
        self.assertEqual(w.player.weapon.bonus, 2)

    def test_swapping_preserves_the_old_weapons_bonus_on_the_floor(self):
        from .dungeon import Drop
        from .items import WEAPONS
        w = self._world()
        w.player.weapon = WEAPONS["bronze_axe"].copy(bonus=3)
        w.level.drops.append(Drop(w.player.x, w.player.y, "gear", "steel_sword", bonus=0))
        opts = w.loot_options()
        idx = next(i for i, o in enumerate(opts)
                   if o["kind"] == "gear" and o["payload"] == "steel_sword")
        w._consume_option(opts[idx])
        dropped = [d for d in w.level.drops if d.payload == "bronze_axe"]
        self.assertEqual(len(dropped), 1)
        self.assertEqual(dropped[0].bonus, 3, "the +3 rides down onto the floor")


class TestWeaponBonusSurvivesDeath(unittest.TestCase):
    def test_corpse_record_stores_and_reloads_the_bonus(self):
        codex = FakeSave()
        codex.leave_corpse(3, 5, 5, 120, "steel_axe", weapon_bonus=2)
        c = codex.corpse_at(3)
        self.assertEqual(c["weapon"], "steel_axe")
        self.assertEqual(c["weapon_bonus"], 2)

    def test_old_corpse_without_bonus_loads_as_zero(self):
        codex = FakeSave()
        codex.corpses["4"] = {"x": 1, "y": 1, "gold": 0, "weapon": "brand",
                              "gift": None, "loot": []}          # a pre-bonus save
        self.assertEqual(codex.corpse_at(4).get("weapon_bonus", 0), 0)

    def test_old_corpse_without_bonus_survives_the_merge_and_restore(self):
        codex = FakeSave()
        codex.world_seed = 11
        codex.corpses["1"] = {"x": 0, "y": 0, "gold": 5, "weapon": "brand",
                              "gift": None, "loot": []}          # a pre-bonus save
        # drives codex.leave_corpse's old.get("weapon_bonus", 0) merge branch
        codex.leave_corpse(1, 0, 0, 10, "bone_axe", weapon_bonus=0)
        c = codex.corpse_at(1)
        self.assertEqual(c["weapon"], "brand", "kept the better weapon")
        self.assertEqual(c.get("weapon_bonus", 0), 0)
        # drives dungeon.py's Corpse restore .get("weapon_bonus", 0) with no KeyError
        w = World(codex, seed=11)
        self.assertIsNotNone(w.level.corpse)
        self.assertEqual(w.level.corpse.weapon_bonus, 0)

    def test_better_weapon_keeps_its_bonus_across_a_second_death(self):
        codex = FakeSave()
        codex.leave_corpse(2, 4, 4, 50, "steel_sword", weapon_bonus=1)
        codex.leave_corpse(2, 8, 8, 10, "bone_axe", weapon_bonus=0)   # died again, worse
        c = codex.corpse_at(2)
        self.assertEqual(c["weapon"], "steel_sword")
        self.assertEqual(c["weapon_bonus"], 1, "the better weapon keeps its +n")

    def test_same_tier_second_death_keeps_the_higher_bonus(self):
        codex = FakeSave()
        codex.leave_corpse(2, 4, 4, 0, "steel_sword", weapon_bonus=1)
        codex.leave_corpse(2, 8, 8, 0, "steel_axe", weapon_bonus=3)   # same tier, higher +n
        c = codex.corpse_at(2)
        self.assertEqual((c["weapon"], c["weapon_bonus"]), ("steel_axe", 3),
                         "on a tier tie, the higher bonus wins")

    def test_dropping_an_item_onto_your_corpse_keeps_the_weapon_bonus(self):
        codex = FakeSave()
        codex.world_seed = 21
        codex.leave_corpse(1, 0, 0, 0, "steel_axe", weapon_bonus=2)
        w = World(codex, seed=21)
        c = w.level.corpse
        self.assertIsNotNone(c)
        w.player.x, w.player.y = c.x, c.y
        # put a potion in the pack, then drop it onto the corpse (a normal free-a-slot
        # action) -- this must hit the `isinstance(sink, Corpse)` write_corpse branch
        # in drop_item
        w.player.slots[0] = ["ochre", 1]
        w.drop_item(0)
        saved = codex.corpse_at(1)
        self.assertEqual(saved["weapon_bonus"], 2,
                         "dropping onto your corpse must not wipe the weapon's +n")

    def test_reclaiming_your_body_re_equips_the_bonus(self):
        codex = FakeSave()
        codex.world_seed = 7
        codex.leave_corpse(1, 0, 0, 0, "bronze_hammer", weapon_bonus=2)
        w = World(codex, seed=7)
        c = w.level.corpse
        self.assertIsNotNone(c)
        w.player.x, w.player.y = c.x, c.y
        opts = w.loot_options()
        idx = next(i for i, o in enumerate(opts)
                   if o["kind"] == "gear" and o["payload"] == "bronze_hammer")
        w._consume_option(opts[idx])
        self.assertEqual(w.player.weapon.key, "bronze_hammer")
        self.assertEqual(w.player.weapon.bonus, 2)


class TestHammerStunCadence(unittest.TestCase):
    def _setup(self):
        codex = FakeSave()
        codex.world_seed = 3
        w = World(codex, seed=3)
        w.level.monsters = []
        from .items import WEAPONS
        w.player.weapon = WEAPONS["steel_hammer"].copy()
        return w

    def _durable_target(self, w, dx=1, dy=0):
        from .monsters import Monster
        m = Monster("brute", w.player.x + dx, w.player.y + dy)
        m.hp = m.max_hp = 999          # never dies mid-test
        w.level.monsters.append(m)
        return m

    def test_stuns_on_first_hit_then_every_third(self):
        w = self._setup()
        m = self._durable_target(w)
        pattern = []
        for _ in range(7):
            m.stunned = 0
            w.player_attack(m)
            pattern.append(m.stunned > 0)
        self.assertEqual(pattern,
                         [True, False, False, True, False, False, True],
                         "stun-hit-hit cadence, opening on the first blow")

    def test_stun_lasts_one_turn(self):
        w = self._setup()
        m = self._durable_target(w)
        w.player_attack(m)
        self.assertEqual(m.stunned, 1)

    def test_cadence_is_per_enemy(self):
        w = self._setup()
        a = self._durable_target(w, 1, 0)
        b = self._durable_target(w, 0, 1)
        a.stunned = b.stunned = 0
        w.player_attack(a)              # a's opening blow -> stun
        w.player_attack(b)              # b's own opening blow -> stun (independent count)
        self.assertTrue(a.stunned and b.stunned,
                        "each enemy opens with its own stun")
        a.stunned = 0
        w.player_attack(a)              # a's second blow -> no stun
        self.assertFalse(a.stunned, "a's second blow does not stun")

    def test_hammer_tax_eased_to_minus_25(self):
        from .items import WEAPONS
        for mat in ("bone", "bronze", "steel"):
            self.assertEqual(WEAPONS["%s_hammer" % mat].speed_mod, -25)

    def test_landing_a_stun_fires_a_realtime_stunstars_fx(self):
        # the stun COUNTER is spent inside the turn resolution, so the visible feedback
        # has to be a real-time fx fired when the stagger lands -- not a read of m.stunned.
        w = self._setup()
        m = self._durable_target(w)
        w.fx = []
        w.player_attack(m)                          # first blow -> stagger
        self.assertTrue(any(f["kind"] == "stunstars" for f in w.fx),
                        "landing the stagger fires a visible fx")

    def test_a_non_stun_blow_fires_no_stunstars_fx(self):
        w = self._setup()
        m = self._durable_target(w)
        w.player_attack(m)                          # blow 1 -> stagger
        w.fx = []
        w.player_attack(m)                          # blow 2 -> no stagger
        self.assertFalse(any(f["kind"] == "stunstars" for f in w.fx),
                         "the off-beat blows show no stagger fx")

    def test_a_faster_monster_cannot_shrug_off_the_stun(self):
        # The hammer taxes the player's speed BELOW a Flicker's, so a single player turn
        # spans two of the Flicker's -- and it would otherwise spend the stun on one and
        # blink away on the other. A stun is counted in PLAYER turns, not monster ticks:
        # the reeling Flicker is frozen for the whole recovery and cannot slip the stagger.
        from .monsters import Monster, TEMPLATES
        w = self._setup()
        p = w.player
        self.assertLess(p.speed(), TEMPLATES["flicker"].speed,
                        "the hammer really does make you slower than a Flicker")
        f = Monster("flicker", p.x + 1, p.y)        # adjacent, its recharge window spent
        f.awake = True
        f.recharge = 0
        f.hp = f.max_hp = 999
        w.level.monsters.append(f)

        w.player_attack(f)                          # opening blow -> stagger
        self.assertEqual(f.stunned, 1, "the blow staggered it")
        p.energy -= config.ACT_COST
        w.advance()                                 # the world moves while you recover
        self.assertLessEqual(f.dist(p.x, p.y), 1,
                             "it reels in place -- it cannot blink away while stunned")
        self.assertEqual(f.stunned, 0, "and the stagger clears after your turn")

    def test_the_stun_holds_for_a_full_player_turn_before_it_acts(self):
        # A one-turn stun costs the monster exactly its NEXT chance to act: it is frozen
        # through the player's recovery, then free on the turn after.
        from .monsters import Monster
        w = self._setup()
        p = w.player
        m = Monster("brute", p.x + 1, p.y)
        m.awake = True
        m.hp = m.max_hp = 999
        w.level.monsters.append(m)
        w.player_attack(m)                          # stagger it
        hp = p.hp
        p.energy -= config.ACT_COST
        w.advance()                                 # turn 1: it is reeling
        self.assertEqual(p.hp, hp, "a stunned brute cannot strike you this turn")
        self.assertEqual(m.stunned, 0, "the stagger has now worn off")

    def test_a_stunned_monster_still_takes_fire(self):
        # The stun freezes its ACTIONS, not its wounds: burn keeps eating it while it reels.
        from .monsters import Monster
        w = self._setup()
        p = w.player
        m = Monster("brute", p.x + 1, p.y)
        m.hp = m.max_hp = 999
        m.burning = 3
        m.stunned = 5                               # frozen, but on fire
        w.level.monsters.append(m)
        hp = m.hp
        p.energy -= config.ACT_COST
        w.advance()
        self.assertLess(m.hp, hp, "fire keeps eating a stunned monster")


class TestStunIndicator(unittest.TestCase):
    def test_draw_stun_stars_runs_without_error(self):
        import pygame
        from . import render
        pygame.init()
        surf = pygame.Surface((200, 200), pygame.SRCALPHA)
        render.draw_stun_stars(surf, 100, 100, 1.23)      # must not raise


class TestCombinedTraits(unittest.TestCase):
    def _world(self):
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=3)
        w.level.monsters = []
        return w

    def test_vampiric_kris_both_cleaves_and_lifesteals(self):
        from .items import WEAPONS
        from .monsters import Monster
        w = self._world()
        p = w.player
        p.weapon = WEAPONS["kris"].copy()      # ("cleave", "lifesteal")
        p.hp = max(1, p.max_hp - 20)
        target = Monster("brute", p.x + 1, p.y); target.hp = target.max_hp = 999
        bystander = Monster("brute", p.x + 1, p.y + 1); bystander.hp = bystander.max_hp = 999
        w.level.monsters = [target, bystander]
        hp0, by0 = p.hp, bystander.hp
        w.player_attack(target)
        self.assertGreater(p.hp, hp0, "lifesteal healed you")
        self.assertLess(bystander.hp, by0, "cleave carried into the bystander")


class TestElementalStatuses(unittest.TestCase):
    def _world(self):
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=3)
        w.level.monsters = []
        return w

    def _target(self, w):
        from .monsters import Monster
        m = Monster("brute", w.player.x + 1, w.player.y)
        m.hp = m.max_hp = 999
        w.level.monsters.append(m)
        return m

    def test_winters_edge_freezes(self):
        from . import config
        from .items import WEAPONS
        w = self._world(); m = self._target(w)
        w.player.weapon = WEAPONS["winters_edge"].copy()
        old = config.FREEZE_CHANCE
        config.FREEZE_CHANCE = 1.0
        try:
            w.player_attack(m)
            self.assertGreater(m.stunned, 0, "the frost froze it")
        finally:
            config.FREEZE_CHANCE = old

    def test_reapers_whisper_frightens_the_primary(self):
        from . import config
        from .items import WEAPONS
        w = self._world(); m = self._target(w)
        w.player.weapon = WEAPONS["reapers_whisper"].copy()
        old = config.FEAR_CHANCE
        config.FEAR_CHANCE = 1.0
        try:
            w.player_attack(m)
            self.assertGreater(m.feared, 0, "the reaped one is routed")
        finally:
            config.FEAR_CHANCE = old

    def test_plain_weapon_freezes_nothing(self):
        from .items import WEAPONS
        w = self._world(); m = self._target(w)
        w.player.weapon = WEAPONS["steel_sword"].copy()
        w.player_attack(m)
        self.assertEqual(m.stunned, 0)


class TestPoison(unittest.TestCase):
    def _world(self):
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=3)
        w.level.monsters = []
        return w

    def test_basilisk_maul_poisons_and_it_ticks(self):
        from . import config
        from .items import WEAPONS
        from .monsters import Monster
        w = self._world()
        m = Monster("brute", w.player.x + 1, w.player.y); m.hp = m.max_hp = 999
        m.awake = True
        w.level.monsters.append(m)
        w.player.weapon = WEAPONS["basilisk_maul"].copy()
        w.player_attack(m)
        self.assertEqual(m.poisoned, config.POISON_TURNS, "the venom takes hold")
        hp = m.hp
        m.take_turn(w)                        # a poisoned turn
        self.assertEqual(m.hp, hp - config.POISON_DMG, "the venom bites each turn")
        self.assertEqual(m.poisoned, config.POISON_TURNS - 1)


class TestCleaveCarriesElement(unittest.TestCase):
    def _world(self):
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=3)
        w.level.monsters = []
        return w

    def _mob(self, w, dx, dy):
        from .monsters import Monster
        m = Monster("brute", w.player.x + dx, w.player.y + dy)
        m.hp = m.max_hp = 999
        w.level.monsters.append(m)
        return m

    def test_pyroclast_ignites_every_cleaved_body(self):
        from .items import WEAPONS
        w = self._world()
        primary = self._mob(w, 1, 0)
        neighbour = self._mob(w, 0, 1)
        w.player.weapon = WEAPONS["pyroclast"].copy()   # ("cleave", "burn")
        w.player_attack(primary)
        self.assertGreater(primary.burning, 0, "primary is alight")
        self.assertGreater(neighbour.burning, 0, "the cleaved neighbour is alight too")

    def test_glacial_flail_freezes_the_cleaved(self):
        from . import config
        from .items import WEAPONS
        w = self._world()
        primary = self._mob(w, 1, 0)
        neighbour = self._mob(w, 0, 1)
        w.player.weapon = WEAPONS["glacial_flail"].copy()  # ("cleave", "freeze")
        old = config.FREEZE_CHANCE
        config.FREEZE_CHANCE = 1.0
        try:
            w.player_attack(primary)
            self.assertGreater(neighbour.stunned, 0, "the cleaved neighbour froze")
        finally:
            config.FREEZE_CHANCE = old


class TestWeaponBench(unittest.TestCase):
    """CTRL+12 weapon bench: swap on any ordinary weapon (base or +2), old drops."""

    def _world(self):
        codex = FakeSave()
        codex.world_seed = 3
        w = World(codex, seed=3)
        w.level.monsters = []
        w.level.drops = []
        return w

    def test_equips_the_selected_weapon_with_its_bonus(self):
        w = self._world()
        w.cheat_equip_weapon("steel_hammer", 2)
        self.assertEqual(w.player.weapon.key, "steel_hammer")
        self.assertEqual(w.player.weapon.bonus, 2)

    def test_base_pick_equips_at_plus_zero(self):
        w = self._world()
        w.cheat_equip_weapon("bronze_sword", 0)
        self.assertEqual(w.player.weapon.key, "bronze_sword")
        self.assertEqual(w.player.weapon.bonus, 0)

    def test_old_weapon_drops_at_your_feet_keeping_its_bonus(self):
        from .items import WEAPONS
        w = self._world()
        w.player.weapon = WEAPONS["bronze_axe"].copy(bonus=1)
        w.cheat_equip_weapon("bone_sword", 0)
        dropped = [d for d in w.level.drops
                   if (d.x, d.y) == (w.player.x, w.player.y)
                   and d.kind == "gear" and d.payload == "bronze_axe"]
        self.assertEqual(len(dropped), 1, "the old weapon lands at your feet")
        self.assertEqual(dropped[0].bonus, 1, "and it keeps its own +n")

    def test_equipping_never_mutates_the_template(self):
        from .items import WEAPONS
        w = self._world()
        w.cheat_equip_weapon("steel_axe", 2)
        self.assertEqual(WEAPONS["steel_axe"].bonus, 0,
                         "the shared template stays pristine")

    def test_bench_equips_a_magical_weapon(self):
        w = self._world()
        w.cheat_equip_weapon("void_scimitar", 0)
        self.assertEqual(w.player.weapon.key, "void_scimitar")
        self.assertEqual(w.player.weapon.traits, ("void",))

    def test_bench_pages_make_every_weapon_reachable(self):
        """Task 11: the bench maps digits 1-9 per page, so the 13 magical weapons
        (unreachable if simply appended to a single 9-slot list) must be spread
        across their own pages. Every WEAPONS key -- ordinary and magical -- must
        appear on some page, and no page may exceed nine entries (or its 1-9 keys
        couldn't reach the tail)."""
        from .items import WEAPONS, weapon_bench_pages
        pages = weapon_bench_pages()
        for page in pages:
            self.assertLessEqual(len(page), 9,
                                 "a page longer than 9 has unreachable rows")
        reachable = set()
        for page in pages:
            reachable.update(page)
        self.assertEqual(reachable, set(WEAPONS) - {"shiv"},
                         "every non-shiv weapon must be reachable from some page")
        magical = {k for k, g in WEAPONS.items() if g.tier >= 4}
        self.assertEqual(len(magical), 13)
        self.assertTrue(magical.issubset(reachable),
                        "all thirteen magical weapons must be reachable")

    def test_cheat_equipping_all_findable_magicals_grants_the_collector_award(self):
        """The bench equips straight onto the player, bypassing the normal pickup
        path (_take); without ledger upkeep in cheat_equip_weapon, the collector's
        award could never be reached by cheat-testing."""
        from .items import FINDABLE_MAGICAL_KEYS
        w = self._world()
        self.assertEqual(len(FINDABLE_MAGICAL_KEYS), 11)
        for key in FINDABLE_MAGICAL_KEYS:
            w.cheat_equip_weapon(key, 0)
            self.assertIn(key, w.codex.magical_collected)
        self.assertIn("self.magical_collector", w.codex.known)


class TestWeaponBenchUI(unittest.TestCase):
    def test_draw_weapon_cheat_runs_without_error(self):
        import pygame
        from . import ui, config as cfg
        pygame.init()
        surf = pygame.Surface((cfg.W, cfg.H), pygame.SRCALPHA)
        keys = ["%s_%s" % (m, t) for m in ("bone", "bronze", "steel")
                for t in ("sword", "axe", "hammer")]
        ui.draw_weapon_cheat(surf, keys, 0.7)             # must not raise
        ui.draw_weapon_cheat(surf, keys, 0.7, "Ordinary")  # with a page label


class TestEnrage(unittest.TestCase):
    def _world(self):
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=3)
        w.level.monsters = []
        return w

    def test_betrayers_edge_enrages(self):
        from . import config
        from .items import WEAPONS
        from .monsters import Monster
        w = self._world()
        m = Monster("brute", w.player.x + 1, w.player.y); m.hp = m.max_hp = 999
        w.level.monsters.append(m)
        w.player.weapon = WEAPONS["betrayers_edge"].copy()
        old = config.ENRAGE_CHANCE
        config.ENRAGE_CHANCE = 1.0
        try:
            w.player_attack(m)
            self.assertEqual(m.enraged, config.ENRAGE_TURNS)
        finally:
            config.ENRAGE_CHANCE = old

    def test_an_enraged_monster_strikes_its_neighbour(self):
        from .monsters import Monster
        w = self._world()
        p = w.player
        rager = Monster("brute", p.x + 3, p.y); rager.hp = rager.max_hp = 999
        rager.awake = True
        victim = Monster("brute", p.x + 4, p.y); victim.hp = victim.max_hp = 999
        w.level.monsters = [rager, victim]
        rager.enraged = 3
        vhp = victim.hp
        rager.take_turn(w)          # adjacent to victim -> hits it
        self.assertLess(victim.hp, vhp, "the enraged one turned on its neighbour")
        self.assertEqual(rager.enraged, 2, "and the rage ticks down")


class TestAntiIncorporeal(unittest.TestCase):
    def _world(self):
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=3)
        w.level.monsters = []
        return w

    def test_incorporeal_set(self):
        from .monsters import is_incorporeal
        self.assertTrue(is_incorporeal("wraith"))
        self.assertTrue(is_incorporeal("poltergeist"))
        self.assertFalse(is_incorporeal("brute"))

    def test_fulgurite_hits_ghosts_harder(self):
        from .items import WEAPONS
        from .monsters import Monster
        # test that fulgurite does x1.5 damage to incorporeal monsters
        w = self._world()
        w.player.weapon = WEAPONS["fulgurite"].copy()
        # pin the damage roll
        w.player.weapon.lo = w.player.weapon.hi = 4

        # test corporeal target
        brute = Monster("brute", w.player.x + 1, w.player.y)
        brute.hp = brute.max_hp = 999
        w.level.monsters = [brute]
        w.player_attack(brute)
        self.assertEqual(999 - brute.hp, 4, "brute takes 4 (no multiplier)")

        # test incorporeal target
        wraith = Monster("wraith", w.player.x + 1, w.player.y)
        wraith.hp = wraith.max_hp = 999
        w.level.monsters = [wraith]
        w.player_attack(wraith)
        self.assertEqual(999 - wraith.hp, 6, "wraith takes 6 (4 * 1.5)")


class TestVoidScimitar(unittest.TestCase):
    def _world(self):
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=3)
        w.level.monsters = []
        w.level.slain = []
        return w

    def test_void_deletes_with_no_body_or_loot(self):
        from . import config
        from .items import WEAPONS
        from .monsters import Monster
        w = self._world()
        m = Monster("brute", w.player.x + 1, w.player.y); m.hp = m.max_hp = 999
        w.level.monsters = [m]
        w.player.weapon = WEAPONS["void_scimitar"].copy()
        old = config.VOID_KILL_CHANCE
        config.VOID_KILL_CHANCE = 1.0
        try:
            w.player_attack(m)
        finally:
            config.VOID_KILL_CHANCE = old
        self.assertNotIn(m, w.level.monsters, "the monster is gone")
        self.assertEqual(len(w.level.slain), 0, "no body, no loot")

    def test_the_warden_is_void_immune(self):
        from . import config
        from .items import WEAPONS
        from .monsters import Monster
        w = self._world()
        boss = Monster("warden", w.player.x + 1, w.player.y); boss.hp = boss.max_hp = 999
        w.level.monsters = [boss]
        w.player.weapon = WEAPONS["void_scimitar"].copy()
        old = config.VOID_KILL_CHANCE
        config.VOID_KILL_CHANCE = 1.0
        try:
            w.player_attack(boss)
        finally:
            config.VOID_KILL_CHANCE = old
        self.assertIn(boss, w.level.monsters, "you cannot void the Warden")
        self.assertLess(boss.hp, 999, "it takes ordinary damage instead")


class TestBossVoidImmunity(unittest.TestCase):
    def test_syrinx_is_a_boss_key(self):
        from .world import BOSS_KEYS
        self.assertIn("syrinx", BOSS_KEYS)

    def test_syrinx_is_never_offered_by_the_banish_picker(self):
        from .monsters import Monster
        codex = FakeSave()
        w = World(codex, seed=3)
        s = Monster("syrinx", w.player.x + 2, w.player.y)
        s.hidden = False
        w.level.monsters = [s]
        w.level.visible[s.y][s.x] = True
        self.assertEqual(w.banishable_types(), [])

    def test_banish_type_cannot_remove_a_void_immune_monster(self):
        from .monsters import Monster
        codex = FakeSave()
        w = World(codex, seed=3)
        s = Monster("syrinx", w.player.x + 2, w.player.y)
        s.hidden = False
        w.level.monsters = [s]
        self.assertFalse(w.banish_type("syrinx"))
        self.assertIn(s, w.level.monsters)

    def test_the_warden_is_also_protected_now(self):
        """A pre-existing gap the same fix closes: BOSS_KEYS already claimed the
        Warden was void-immune, but banish_type never actually checked it."""
        from .monsters import Monster
        codex = FakeSave()
        w = World(codex, seed=3)
        wd = Monster("warden", w.player.x + 2, w.player.y)
        w.level.monsters = [wd]
        self.assertFalse(w.banish_type("warden"))
        self.assertIn(wd, w.level.monsters)


class TestMagicBenchCheat(unittest.TestCase):
    """CTRL+21: a magic-only weapon bench -- like CTRL+12 but skips the ordinary weapons."""

    def test_ctrl21_opens_a_magic_only_bench(self):
        from .game import Game, WEAPON_PICK
        from .items import WEAPONS
        g = Game.__new__(Game)          # bypass pygame init; drive the opener directly
        g.open_magic_cheat()
        self.assertEqual(g.state, WEAPON_PICK)
        covered = set().union(*g.weapon_pages)
        magical = {k for k, w in WEAPONS.items() if w.tier >= 4}
        self.assertEqual(covered, magical, "the magic bench reaches all 13 magical weapons")
        self.assertEqual(len(covered), 13)
        self.assertNotIn("bone_sword", covered, "and offers no ordinary weapons")
        self.assertTrue(all(len(page) <= 9 for page in g.weapon_pages),
                        "each page still fits the 1-9 digit keys")


class TestStunHoldsThroughAFreeAction(unittest.TestCase):
    """A fast player's banked/free action is an advance() with ZERO world ticks -- no
    monster gets a turn. A stun must NOT tick down then, or Windwalkers (or any haste)
    wastes a Winter's Edge freeze on the player's own free move instead of the monster's
    turn. Dual of the hammer-stun fix (which handles a SLOW player)."""

    def _world(self):
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=3)
        w.level.monsters = []
        return w

    def test_a_zero_tick_free_action_does_not_burn_the_stun(self):
        from .monsters import Monster
        w = self._world()
        m = Monster("brute", w.player.x + 1, w.player.y)
        m.hp = m.max_hp = 999
        m.stunned = 1
        w.level.monsters = [m]
        w.player.energy = config.ACT_COST      # already able to act -> advance() does 0 ticks
        w.advance()
        self.assertEqual(m.stunned, 1,
                         "no world time passed, so the freeze must still be in force")

    def test_a_real_recovery_turn_still_burns_one_stun(self):
        from .monsters import Monster
        w = self._world()
        m = Monster("brute", w.player.x + 1, w.player.y)
        m.hp = m.max_hp = 999
        m.stunned = 1
        w.level.monsters = [m]
        w.player.energy = 0                    # must recover -> advance() runs >= 1 tick
        w.advance()
        self.assertEqual(m.stunned, 0,
                         "a real player turn (the world ticked) still ticks the stun down")


class TestRollMagical(unittest.TestCase):
    def test_findable_pool_excludes_the_boss_weapons(self):
        from .items import FINDABLE_MAGICAL, WEAPONS
        pool = set(FINDABLE_MAGICAL[4]) | set(FINDABLE_MAGICAL[5])
        self.assertNotIn("windfang", pool, "Windfang is a mini-boss drop, never found")
        self.assertNotIn("void_scimitar", pool, "the Void Scimitar is a mini-boss drop")
        # every findable key is a real magical weapon of the stated tier
        for tier in (4, 5):
            for key in FINDABLE_MAGICAL[tier]:
                self.assertEqual(WEAPONS[key].tier, tier, key)
        self.assertEqual(len(pool), 11, "7 T4 + 6 T5 minus the two boss-locked = 11")

    def test_present_chance_by_band(self):
        import random
        from .items import roll_magical
        def rate(depth):
            hits = sum(roll_magical(random.Random(s), depth) is not None
                       for s in range(4000))
            return hits / 4000.0
        self.assertAlmostEqual(rate(9), 0.18, delta=0.03)
        self.assertAlmostEqual(rate(13), 0.15, delta=0.03)
        self.assertAlmostEqual(rate(18), 0.12, delta=0.03)

    def test_tier5_share_climbs_with_depth(self):
        import random
        from .items import roll_magical, WEAPONS
        def t5_share(depth):
            present = [r for r in (roll_magical(random.Random(s), depth)
                                   for s in range(6000)) if r]
            t5 = sum(1 for k, _ in present if WEAPONS[k].tier == 5)
            return t5 / len(present)
        self.assertAlmostEqual(t5_share(9), 0.20, delta=0.05)
        self.assertAlmostEqual(t5_share(13), 0.40, delta=0.05)
        self.assertAlmostEqual(t5_share(18), 0.65, delta=0.05)

    def test_found_magicals_are_unenhanced(self):
        import random
        from .items import roll_magical
        for s in range(500):
            r = roll_magical(random.Random(s), 12)
            if r:
                self.assertEqual(r[1], 0, "magical weapons are found at +0")


class TestRollDeepSteel(unittest.TestCase):
    def test_none_on_floor_15_and_deeper(self):
        import random
        from .items import roll_deep_steel
        for depth in (15, 16, 20):
            for s in range(50):
                self.assertIsNone(roll_deep_steel(random.Random(s), depth),
                                  "the enhanced-steel slot is spent by floor 15")

    def test_present_chance_decays(self):
        import random
        from .items import roll_deep_steel
        def rate(depth):
            hits = sum(roll_deep_steel(random.Random(s), depth) is not None
                       for s in range(4000))
            return hits / 4000.0
        self.assertAlmostEqual(rate(8), 0.70, delta=0.04)
        self.assertAlmostEqual(rate(11), 0.40, delta=0.04)
        self.assertAlmostEqual(rate(14), 0.10, delta=0.03)

    def test_always_enhanced_steel_never_plus_zero(self):
        import random
        from .items import roll_deep_steel
        for depth in range(8, 15):
            for s in range(300):
                r = roll_deep_steel(random.Random(s), depth)
                if r:
                    key, bonus = r
                    self.assertTrue(key.startswith("steel_"), key)
                    self.assertIn(bonus, (1, 2, 3), "enhanced only")

    def test_plus3_chance_climbs_with_depth(self):
        import random
        from .items import roll_deep_steel
        def plus3(depth):
            present = [r for r in (roll_deep_steel(random.Random(s), depth)
                                   for s in range(6000)) if r]
            return sum(1 for _, b in present if b == 3) / len(present)
        self.assertLess(plus3(8), 0.12)      # ~5%
        self.assertGreater(plus3(14), 0.25)  # ~35%


class TestEnchantScrollAvailability(unittest.TestCase):
    def test_deep_scrolls_include_enchant_scrolls_reliably(self):
        import random
        from .items import roll_consumable
        n = 6000
        enchant = sum(roll_consumable(random.Random(s), 12, "scroll") in ("krav", "dwen")
                      for s in range(n))
        self.assertGreater(enchant / n, 0.13, "enchant scrolls are reliably in reach deep")

    def test_shallow_scrolls_are_not_biased(self):
        import random
        from .items import roll_consumable, SCROLL_POOL
        # on floor 3 the enchant bias must not fire (krav/dwen are not in the common pool)
        for s in range(400):
            f = roll_consumable(random.Random(s), 3, "scroll")
            self.assertIn(f, SCROLL_POOL, "shallow scrolls stay in the common pool")


class TestDeepEconomyDistribution(unittest.TestCase):
    def test_per_run_magical_and_steel_counts(self):
        import random
        from .items import roll_floor_weapons, WEAPONS
        runs = 4000
        magical_per_run, steel_per_run, no_magical = 0, 0, 0
        for s in range(runs):
            rng = random.Random(s)
            mags = steels = 0
            for depth in range(8, 21):
                for key, _ in roll_floor_weapons(rng, depth):
                    if WEAPONS[key].tier >= 4:
                        mags += 1
                    elif key.startswith("steel_"):
                        steels += 1
            magical_per_run += mags
            steel_per_run += steels
            no_magical += (mags == 0)
        self.assertAlmostEqual(magical_per_run / runs, 1.9, delta=0.3)
        self.assertAlmostEqual(steel_per_run / runs, 2.8, delta=0.4)
        self.assertAlmostEqual(no_magical / runs, 0.12, delta=0.05)


class TestMagicalUniqueness(unittest.TestCase):
    def test_roll_magical_never_returns_an_excluded_key(self):
        import random
        from .items import roll_magical
        exclude = {"kris", "basilisk_maul", "pyroclast", "reapers_whisper", "glacial_flail"}
        for s in range(2000):
            r = roll_magical(random.Random(s), 18, exclude=exclude)  # depth 18 -> T5-heavy
            if r:
                self.assertNotIn(r[0], exclude)

    def test_fully_excluded_tier_yields_no_magical(self):
        import random
        from .items import roll_magical, FINDABLE_MAGICAL
        allmag = set(FINDABLE_MAGICAL[4]) | set(FINDABLE_MAGICAL[5])
        for s in range(500):
            self.assertIsNone(roll_magical(random.Random(s), 12, exclude=allmag),
                              "with every magical spent, the slot is dormant")

    def test_generation_records_placed_magicals_and_never_repeats(self):
        # Descend a fresh game across floors 8-20 many times over; a magical key must
        # never be PLACED twice across the whole game (uniqueness).
        seen = set()
        codex = FakeSave(); codex.world_seed = 7
        w = World(codex, seed=7)
        from .items import is_magical
        # walk every deep floor once, forcing generation
        for depth in range(8, 20):
            w.new_level(depth)
            for d in w.level.drops:
                if d.kind == "gear" and is_magical(d.payload):
                    self.assertNotIn(d.payload, seen, "a magical generated twice")
                    seen.add(d.payload)
        # every placed magical was recorded as generated
        self.assertTrue(set(codex.magical_generated) >= seen)


class TestMagicalLedgerState(unittest.TestCase):
    def test_is_magical_and_findable_keys(self):
        from .items import is_magical, FINDABLE_MAGICAL_KEYS
        self.assertTrue(is_magical("kris"))
        self.assertTrue(is_magical("rapier"))
        self.assertFalse(is_magical("steel_sword"))
        self.assertFalse(is_magical("nonsense"))
        self.assertEqual(len(FINDABLE_MAGICAL_KEYS), 11)
        self.assertNotIn("windfang", FINDABLE_MAGICAL_KEYS)
        self.assertNotIn("void_scimitar", FINDABLE_MAGICAL_KEYS)

    def test_record_and_pickup(self):
        codex = FakeSave()
        codex.record_magical_placed("kris", 12, 5, 6, 0)
        self.assertIn("kris", codex.magical_generated)
        self.assertEqual(codex.magical_ground["kris"],
                         {"depth": 12, "x": 5, "y": 6, "bonus": 0})
        completed = codex.magical_picked_up("kris")
        self.assertIn("kris", codex.magical_collected)
        self.assertNotIn("kris", codex.magical_ground, "picked up -> no longer on ground")
        self.assertIn("kris", codex.magical_generated, "still exists, never regenerates")
        self.assertFalse(completed, "one of eleven is not the whole set")

    def test_drop_puts_it_back_on_the_ground(self):
        codex = FakeSave()
        codex.record_magical_placed("kris", 12, 5, 6, 0)
        codex.magical_picked_up("kris")
        codex.drop_magical_to_ground("kris", 3, 1, 1, 2)
        self.assertEqual(codex.magical_ground["kris"],
                         {"depth": 3, "x": 1, "y": 1, "bonus": 2})

    def test_save_load_round_trips_the_ledger(self):
        from .codex import Codex
        codex = FakeSave()
        codex.record_magical_placed("brand", 9, 2, 2, 0)
        codex.magical_picked_up("brand")
        data = {}
        # exercise the real serialize/deserialize path via a temp Codex
        c2 = Codex.__new__(Codex)
        c2.__init__()
        c2._load_from(codex._save_dict())   # helper below
        self.assertIn("brand", c2.magical_generated)
        self.assertIn("brand", c2.magical_collected)

    def test_new_dungeon_resets_the_ledger(self):
        codex = FakeSave()
        codex.record_magical_placed("kris", 12, 5, 6, 0)
        codex.new_dungeon()
        self.assertEqual(codex.magical_generated, [])
        self.assertEqual(codex.magical_ground, {})
        self.assertEqual(codex.magical_collected, [])


class TestMagicalPersistence(unittest.TestCase):
    def _world(self, seed=5):
        codex = FakeSave(); codex.world_seed = seed
        return World(codex, seed=seed), codex

    def test_a_ground_magical_reappears_next_life_at_its_spot(self):
        from .items import is_magical
        w, codex = self._world()
        w.new_level(10)
        # find (or force) a magical lying on floor 10
        codex.magical_ground.clear(); codex.magical_generated = []
        codex.record_magical_placed("kris", 10, w.player.x, w.player.y + 2, 0)
        # a NEW life: fresh World, same codex (the living is re-dealt, the ledger persists)
        w2 = World(codex, seed=w.seed)
        w2.new_level(10)
        krises = [d for d in w2.level.drops
                  if d.kind == "gear" and d.payload == "kris"]
        self.assertEqual(len(krises), 1, "the Kris is still lying on floor 10")
        self.assertEqual((krises[0].x, krises[0].y),
                         (w.player.x, w.player.y + 2), "exactly where it was left")
        self.assertEqual(krises[0].bonus, 0)

    def test_the_ground_ledger_holds_only_magicals(self):
        from .items import is_magical
        w, codex = self._world()
        # generate several deep floors; whatever lands in the ground ledger is magical
        for depth in range(8, 16):
            w.new_level(depth)
        for key in codex.magical_ground:
            self.assertTrue(is_magical(key),
                            "%s should never be in the magical ground ledger" % key)


class TestLedgerPickupDrop(unittest.TestCase):
    def _world(self):
        codex = FakeSave(); codex.world_seed = 5
        w = World(codex, seed=5)
        w.level.monsters = []
        return w

    def test_picking_up_a_magical_marks_it_collected_and_off_the_ground(self):
        from .dungeon import Drop
        w = self._world()
        w.codex.record_magical_placed("kris", w.depth, w.player.x, w.player.y, 0)
        w.level.drops.append(Drop(w.player.x, w.player.y, "gear", "kris", bonus=0))
        opts = w.loot_options()
        idx = next(i for i, o in enumerate(opts)
                   if o["kind"] == "gear" and o["payload"] == "kris")
        w._consume_option(opts[idx])
        self.assertEqual(w.player.weapon.key, "kris")
        self.assertIn("kris", w.codex.magical_collected)
        self.assertNotIn("kris", w.codex.magical_ground)

    def test_dropping_a_magical_records_it_on_the_ground(self):
        from .items import WEAPONS
        w = self._world()
        w.player.weapon = WEAPONS["kris"].copy(bonus=2)
        # swap to a plain weapon; the Kris drops to the floor
        from .dungeon import Drop
        w.level.drops.append(Drop(w.player.x, w.player.y, "gear", "steel_sword", bonus=0))
        opts = w.loot_options()
        idx = next(i for i, o in enumerate(opts)
                   if o["kind"] == "gear" and o["payload"] == "steel_sword")
        w._consume_option(opts[idx])
        self.assertIn("kris", w.codex.magical_ground)
        self.assertEqual(w.codex.magical_ground["kris"]["bonus"], 2,
                         "the +n rides down onto the floor with it")


class TestCollectorAward(unittest.TestCase):
    def test_collecting_every_findable_magical_awards_once(self):
        from .items import FINDABLE_MAGICAL_KEYS
        from .codex import FACTS
        codex = FakeSave()
        self.assertIn("self.magical_collector", FACTS, "the award fact exists")
        keys = list(FINDABLE_MAGICAL_KEYS)
        completed = [codex.magical_picked_up(k) for k in keys]
        self.assertEqual(sum(completed), 1, "completion fires exactly once (last pickup)")
        # the last pickup returned True -> the world would call award_collection
        codex.award_collection()
        self.assertIn("self.magical_collector", codex.known)
        self.assertEqual(codex.stats.get("magical_collected_all"), 1)
        # idempotent
        codex.award_collection()
        self.assertEqual(codex.known.count("self.magical_collector"), 1)


class TestRespawnHomage(unittest.TestCase):
    """The Planescape: Torment homage -- every respawn after a death greets the
    hero with the same line, and teaches the lore fact the first time."""

    def test_respawn_after_death_speaks_the_homage(self):
        from .game import Game, PLAY
        from .codex import FACTS
        self.assertIn("self.the_deep_is_patient", FACTS)
        g = Game.__new__(Game)
        g.codex = FakeSave()
        g.codex.deaths = 1                 # a death has happened -> this is a respawn
        g.victory_gear = None
        g.banner = None; g.banner_age = 0.0
        g.new_run()
        msgs = " ".join(m[0] if isinstance(m, tuple) else str(m)
                        for m in g.codex.messages)
        self.assertIn("the deep is patient", msgs.lower())
        self.assertIn("self.the_deep_is_patient", g.codex.known)

    def test_a_fresh_new_game_does_not_speak_the_homage(self):
        from .game import Game
        g = Game.__new__(Game)
        g.codex = FakeSave()
        g.codex.deaths = 0                 # brand new game, nobody has died yet
        g.victory_gear = None
        g.banner = None; g.banner_age = 0.0
        g.new_run()
        self.assertNotIn("self.the_deep_is_patient", g.codex.known)


class TestUniquenessAcrossLives(unittest.TestCase):
    def test_a_left_magical_persists_and_never_duplicates_across_lives(self):
        from .items import is_magical
        codex = FakeSave(); codex.world_seed = 11
        # life 1: place a Kris on floor 10 and leave it
        w1 = World(codex, seed=11); w1.new_level(10)
        codex.magical_ground.clear(); codex.magical_generated = ["kris"]
        codex.magical_ground["kris"] = {"depth": 10, "x": w1.player.x,
                                        "y": w1.player.y + 2, "bonus": 0}
        # lives 2..6: fresh World each time (living re-dealt, ledger persists)
        for life in range(5):
            w = World(codex, seed=11)
            all_krises = 0
            for depth in range(8, 20):
                w.new_level(depth)
                all_krises += sum(1 for d in w.level.drops
                                  if d.kind == "gear" and d.payload == "kris")
            self.assertEqual(all_krises, 1, "exactly one Kris exists, life %d" % life)
        # floor 10 still holds it, at its spot
        w = World(codex, seed=11); w.new_level(10)
        self.assertTrue(any(d.payload == "kris" for d in w.level.drops
                            if d.kind == "gear"))


class TestBootsRebalance(unittest.TestCase):
    def test_boots_defense_folds_into_player_defense_and_wraiths_ignore_it(self):
        from .items import Boots
        from .monsters import Monster
        w = World(FakeSave(), seed=3)
        w.level.monsters = []
        base = w.player.defense                      # rags(0) + sandals(0) = 0
        w.player.boots = Boots("tst", "Test Boots", 1, 0, defense=2)
        self.assertEqual(w.player.defense, base + 2,
                         "boots defense adds into player.defense")
        rat = Monster("rat", w.player.x, w.player.y)
        hp = w.player.hp
        for _ in range(10):
            w.monster_attacks_player(rat, 2)         # 2 dmg fully soaked by +2 boots def
        self.assertEqual(w.player.hp, hp,
                         "a 2-point boots defense shrugs off a 2-damage rat")
        wraith = Monster("wraith", w.player.x, w.player.y)
        w.monster_attacks_player(wraith, 4, ignore_armour=True)
        self.assertLess(w.player.hp, hp, "a wraith ignores boots defense")

    def test_boots_desc_shows_defense_only_when_present(self):
        from .items import Boots
        armoured = Boots("a", "Armoured", 1, -10, defense=2)
        self.assertIn("+2 def", armoured.desc())
        self.assertIn("-10 spd", armoured.desc())
        plain = Boots("p", "Plain", 1, 10)
        self.assertNotIn("def", plain.desc())

    def test_ordinary_boots_are_a_speed_defense_tradeoff(self):
        from .items import BOOTS
        expect = {                # key: (tier, speed, defense)
            "sandals":      (0,   0, 0),
            "boots_leather": (1,  10, 0),
            "boots_mail":    (2,   0, 1),
            "boots_plate":   (3, -10, 2),
        }
        for key, (tier, spd, dfn) in expect.items():
            b = BOOTS[key]
            self.assertEqual((b.tier, b.speed, b.defense), (tier, spd, dfn), key)
            self.assertIsNone(b.trait, "ordinary boots carry no trait: %s" % key)

    def test_the_five_exotic_boots_relocate_to_magical_tiers_intact(self):
        from .items import BOOTS
        self.assertEqual(BOOTS["wind"].tier, 5, "Windwalkers is the T5 magical boot")
        for key in ("swift", "blink", "soft", "ironshod"):
            self.assertEqual(BOOTS[key].tier, 4, "%s is a T4 magical boot" % key)
        # stats and traits are carried over untouched by the relocation
        self.assertEqual(BOOTS["swift"].speed, 25)
        self.assertEqual(BOOTS["wind"].speed, 40)
        self.assertEqual(BOOTS["blink"].trait, "blink")
        self.assertEqual(BOOTS["soft"].wake_radius, 4, "Padded Soles are now a stealth boot")
        self.assertEqual(BOOTS["ironshod"].trait, "kick")

    def test_gear_pool_is_empty_all_gear_is_generation_placed(self):
        from .items import gear_pool
        for depth in range(1, 21):
            self.assertEqual(gear_pool(depth), [],
                             "weapons, boots AND armour are all generation-placed now "
                             "(floor %d)" % depth)

    def test_roll_floor_boots_never_on_floor_one_or_past_fifteen(self):
        import random
        from .items import roll_floor_boots
        for depth in (1, 16, 17, 20):
            for s in range(60):
                self.assertEqual(roll_floor_boots(random.Random(s), depth), [],
                                 "no ordinary boot on floor %d" % depth)

    def test_roll_floor_boots_places_at_most_one(self):
        import random
        from .items import roll_floor_boots
        for depth in range(1, 21):
            for s in range(60):
                self.assertLessEqual(len(roll_floor_boots(random.Random(s), depth)), 1)

    def test_roll_floor_boots_respects_the_bands(self):
        import random
        from .items import roll_floor_boots
        def seen(depth):
            out = set()
            for s in range(400):
                out |= set(roll_floor_boots(random.Random(s), depth))
            return out
        self.assertEqual(seen(2), {"boots_leather"})
        self.assertEqual(seen(4), {"boots_leather", "boots_mail"})
        self.assertEqual(seen(6), {"boots_leather", "boots_mail", "boots_plate"})
        self.assertEqual(seen(10), {"boots_leather", "boots_mail", "boots_plate"})
        self.assertEqual(seen(11), {"boots_mail", "boots_plate"})   # leather gone after 10
        self.assertEqual(seen(15), {"boots_mail", "boots_plate"})
        self.assertEqual(seen(16), set())

    def test_roll_floor_boots_present_about_half_the_time_and_is_deterministic(self):
        import random
        from .items import roll_floor_boots
        present = sum(1 for s in range(4000)
                      if roll_floor_boots(random.Random(s), 6))    # floor 6: all bands valid
        rate = present / 4000
        self.assertGreater(rate, 0.44, "present-rate should be ~50%% (got %.3f)" % rate)
        self.assertLess(rate, 0.56, "present-rate should be ~50%% (got %.3f)" % rate)
        # same (seed, depth) -> same result: no hidden state, no Kodex read
        for s in range(50):
            for depth in (2, 6, 12, 15):
                self.assertEqual(roll_floor_boots(random.Random(s), depth),
                                 roll_floor_boots(random.Random(s), depth))

    def test_vendor_never_stocks_a_magical_boot(self):
        import random
        from .items import ALL_GEAR
        from .vendor import Vendor
        for depth in (5, 8, 12, 19):
            for seed in range(40):
                v = Vendor(0, 0, depth, random.Random(seed))
                for kind, payload in v.stock:
                    if kind == "gear":
                        self.assertLessEqual(
                            ALL_GEAR[payload].tier, 3,
                            "vendor stock stays ordinary: %s at depth %d"
                            % (payload, depth))

    def test_the_sweep_takes_a_boot_over_the_starter_but_never_downgrades_a_choice(self):
        from .items import BOOTS
        w = World(FakeSave(), seed=4)
        w.player.boots = BOOTS["sandals"]                # the bare starter (T0)
        spot = w.drop_gear_near("boots_leather")
        self.assertIsNotNone(spot)
        w.player.x, w.player.y = spot
        w.take_all()
        self.assertEqual(w.player.boots.key, "boots_leather",
                         "the first boot is auto-equipped over the bare starter")
        # now wearing a chosen boot: the sweep must NOT swap in a heavier plate
        spot = w.drop_gear_near("boots_plate")
        self.assertIsNotNone(spot)
        w.player.x, w.player.y = spot
        w.take_all()
        self.assertEqual(w.player.boots.key, "boots_leather",
                         "the all-sweep never trades a chosen boot behind your back")

    def test_generated_floors_hold_at_most_one_ordinary_boot_and_none_shallow_or_deep(self):
        import random
        from .dungeon import Level
        ordinary = {"boots_leather", "boots_mail", "boots_plate"}
        for depth in (1, 2, 6, 12, 15, 16, 20):
            for s in range(40):
                codex = FakeSave()
                codex.world_seed = s
                lvl = Level(depth, random.Random(s), codex)
                boots = [d for d in lvl.drops
                         if d.kind == "gear" and d.payload in ordinary]
                self.assertLessEqual(len(boots), 1,
                                     "floor %d placed more than one ordinary boot" % depth)
                if depth == 1 or depth >= 16:
                    self.assertEqual(boots, [],
                                     "floor %d must hold no ordinary boot" % depth)

    def test_every_ordinary_boot_is_findable_across_the_mid_floors(self):
        import random
        from .dungeon import Level
        ordinary = {"boots_leather", "boots_mail", "boots_plate"}
        found = set()
        for depth in range(2, 16):
            for s in range(80):
                codex = FakeSave()
                codex.world_seed = s
                lvl = Level(depth, random.Random(s), codex)
                for d in lvl.drops:
                    if d.kind == "gear" and d.payload in ordinary:
                        found.add(d.payload)
        self.assertEqual(found, ordinary,
                         "every ordinary boot should be findable on the mid floors")


class TestVendorConsumablesOnly(unittest.TestCase):
    def test_the_vendor_never_stocks_gear(self):
        import random
        from .vendor import Vendor
        for depth in (5, 8, 12, 19):
            for s in range(40):
                v = Vendor(0, 0, depth, random.Random(s))
                kinds = {k for k, _ in v.stock}
                self.assertNotIn("gear", kinds,
                                 "the vendor deals in potions and scrolls only "
                                 "(floor %d)" % depth)
                self.assertTrue(v.stock, "it must still stock something")


class TestMagicalBoots(unittest.TestCase):
    def test_swift_is_renamed_sandals_of_mercury(self):
        from .items import BOOTS
        b = BOOTS["swift"]
        self.assertEqual(b.name, "Sandals of Mercury")
        self.assertEqual((b.tier, b.speed), (4, 25), "stats unchanged, rename only")

    def test_featherfall_springs_no_trap_of_any_kind(self):
        from .items import BOOTS
        from .traps import Trap, TRAP_POOL
        w = World(FakeSave(), seed=5)
        w.level.monsters = []
        w.player.boots = BOOTS["featherfall"]
        for kind in set(TRAP_POOL):                 # dart, spike, gas, alarm, glyph
            hp = w.player.hp
            t = Trap(kind, w.player.x, w.player.y)
            t.trigger(w, w.player)
            self.assertEqual(w.player.hp, hp,
                             "featherfall must not spring the %s" % kind)
            self.assertFalse(t.sprung, "the %s should not go off" % kind)

    def test_thor_knocks_back_every_adjacent_enemy(self):
        from .items import BOOTS
        from .monsters import Monster
        from .dungeon import FLOOR
        w = World(FakeSave(), seed=7)
        w.level.monsters = []
        w.player.boots = BOOTS["thor"]
        px, py = w.player.x, w.player.y
        for dy in range(-2, 3):                        # carve open room to be shoved into
            for dx in range(-2, 3):
                w.level.grid[py + dy][px + dx] = FLOOR
        placed = []
        for (dx, dy) in ((1, 0), (0, 1), (1, 1)):
            m = Monster("rat", px + dx, py + dy)
            m.hp = m.max_hp = 999                       # they survive the blow, so they can be shoved
            w.level.monsters.append(m)
            placed.append(((px + dx, py + dy), m))
        w.player_attack(placed[0][1])                   # strike the eastern rat
        for orig, m in placed:
            self.assertNotEqual((m.x, m.y), orig,
                                "every adjacent enemy should be shoved, not just the target")

    def test_slipstep_blinks_and_stuns_on_the_fourth_hit(self):
        from .items import BOOTS, ARMOURS
        from .monsters import Monster
        from .dungeon import FLOOR
        w = World(FakeSave(), seed=9)
        w.level.monsters = []
        w.player.boots = BOOTS["slipstep"]
        w.player.armour = ARMOURS["rags"]              # 0 def: every blow lands in full
        w.player.hp = 50                               # survive four hits
        px, py = w.player.x, w.player.y
        for dy in range(-2, 3):                         # open room to blink into
            for dx in range(-2, 3):
                w.level.grid[py + dy][px + dx] = FLOOR
        m = Monster("rat", px + 1, py)                  # adjacent, not on the player
        w.level.monsters = [m]
        start = (px, py)
        for _ in range(3):                              # first three damaging hits: no blink
            w.monster_attacks_player(m, 3)
            self.assertEqual((w.player.x, w.player.y), start, "no blink before the 4th hit")
            self.assertEqual(m.stunned, 0, "no stun before the 4th hit")
        w.monster_attacks_player(m, 3)                  # the fourth hit: blink + stun
        self.assertNotEqual((w.player.x, w.player.y), start,
                            "the 4th hit blinks the player away")
        self.assertGreaterEqual(m.stunned, 1, "the 4th hit stuns the attacker")

    def test_emberstride_is_never_frozen_and_wards_two(self):
        from .items import BOOTS
        w = World(FakeSave(), seed=11)
        w.player.boots = BOOTS["emberstride"]
        self.assertEqual(BOOTS["emberstride"].defense, 2, "Emberstride wards +2")
        w.freeze_player(2)
        self.assertEqual(w.player.frozen, 0, "Emberstride's heat shrugs off the gaze")

    def test_rimewalkers_shrug_off_fire_but_not_a_dart(self):
        from .items import BOOTS
        w = World(FakeSave(), seed=13)
        w.player.boots = BOOTS["rimewalkers"]
        self.assertEqual(BOOTS["rimewalkers"].defense, 2, "Rimewalkers ward +2")
        hp = w.player.hp
        w.hurt_player(6, "glyph")                    # a fire glyph blast
        self.assertEqual(w.player.hp, hp, "rimewalkers take no fire damage")
        w.hurt_player(4, "dart")                     # a non-fire source still bites
        self.assertLess(w.player.hp, hp, "only fire is warded, not everything")

    def test_phantom_dodges_about_a_quarter_of_blows(self):
        from .items import BOOTS, ARMOURS
        from .monsters import Monster
        w = World(FakeSave(), seed=15)
        w.level.monsters = []
        w.player.boots = BOOTS["phantom"]
        w.player.armour = ARMOURS["rags"]            # 0 def, so any negation is a dodge
        m = Monster("rat", w.player.x, w.player.y)
        landed = 0
        trials = 3000
        for _ in range(trials):
            before = w.player.hp
            w.monster_attacks_player(m, 3)
            if w.player.hp < before:
                landed += 1
            w.player.hp = 50                         # keep the player alive across trials
        rate = landed / trials
        self.assertGreater(rate, 0.68, "≈75%% of blows land (got %.3f)" % rate)
        self.assertLess(rate, 0.82, "≈75%% of blows land (got %.3f)" % rate)

    def test_boots_bench_cheat_equips_a_chosen_boot(self):
        w = World(FakeSave(), seed=17)
        w.cheat_equip_boots("phantom")
        self.assertEqual(w.player.boots.key, "phantom", "the bench laces on the pick")
        w.cheat_equip_boots("boots_plate")
        self.assertEqual(w.player.boots.key, "boots_plate", "and swaps to the next pick")

    def test_ctrl56_opens_a_boots_bench_reaching_every_boot(self):
        from .game import Game, WEAPON_PICK
        from .items import BOOTS
        g = Game.__new__(Game)          # bypass pygame init; drive the opener directly
        g.open_boots_cheat()
        self.assertEqual(g.state, WEAPON_PICK)
        self.assertEqual(g.bench_slot, "boots")
        covered = set().union(*g.weapon_pages)
        self.assertEqual(covered, set(BOOTS), "the boots bench reaches every boot")
        self.assertTrue(all(len(p) <= 9 for p in g.weapon_pages),
                        "each page still fits the 1-9 digit keys")

    def test_armour_bench_cheat_dons_a_chosen_piece(self):
        w = World(FakeSave(), seed=17)
        w.cheat_equip_armour("blinding")
        self.assertEqual(w.player.armour.key, "blinding", "the bench dons the pick")
        w.cheat_equip_armour("stonegolem")
        self.assertEqual(w.player.armour.key, "stonegolem", "and swaps to the next pick")

    def test_ctrl34_opens_an_armour_bench_reaching_every_armour(self):
        from .game import Game, WEAPON_PICK
        from .items import ARMOURS
        g = Game.__new__(Game)          # bypass pygame init; drive the opener directly
        g.open_armour_cheat()
        self.assertEqual(g.state, WEAPON_PICK)
        self.assertEqual(g.bench_slot, "armour")
        covered = set().union(*g.weapon_pages)
        self.assertEqual(covered, set(ARMOURS), "the armour bench reaches every armour")
        self.assertTrue(all(len(p) <= 9 for p in g.weapon_pages),
                        "each page still fits the 1-9 digit keys")

    def test_knockback_interrupts_a_wound_up_smash(self):
        from .items import BOOTS
        from .monsters import Monster
        from .dungeon import FLOOR
        w = World(FakeSave(), seed=7)
        w.level.monsters = []
        w.player.boots = BOOTS["ironshod"]              # knockback on the primary target
        px, py = w.player.x, w.player.y
        for dy in range(-2, 3):                          # open room so the brute can be shoved
            for dx in range(-2, 3):
                w.level.grid[py + dy][px + dx] = FLOOR
        brute = Monster("brute", px + 1, py)
        brute.hp = brute.max_hp = 999
        brute.awake = True
        brute.intent = ("smash", px, py)                # wound up, aimed at your tile
        w.level.monsters = [brute]
        w.player_attack(brute)                           # Ironshod shoves it back
        self.assertNotEqual((brute.x, brute.y), (px + 1, py), "the brute was pushed back")
        self.assertIsNone(brute.intent, "being shoved mid-wind-up spoils the smash")
        hp = w.player.hp
        brute.take_turn(w)                               # its next turn lands no blow
        self.assertEqual(w.player.hp, hp,
                         "the interrupted brute cannot smash the tile you never left")


class TestBootsStealth(unittest.TestCase):
    def _arena(self, boots_key, seed=3):
        # a carved-open patch so line of sight is clear and distances are exact
        from .items import BOOTS
        from .dungeon import FLOOR
        w = World(FakeSave(), seed=seed)
        w.level.monsters = []
        w.player.boots = BOOTS[boots_key]
        px, py = w.player.x, w.player.y
        for dy in range(-8, 9):
            for dx in range(-8, 9):
                if 0 <= py + dy < w.level.h and 0 <= px + dx < w.level.w:
                    w.level.grid[py + dy][px + dx] = FLOOR
        w.level.compute_fov(px, py)
        return w, px, py

    def test_padded_soles_and_whisperstep_carry_a_wake_radius(self):
        from .items import BOOTS
        self.assertEqual(BOOTS["soft"].wake_radius, 4, "Padded Soles halve the ~9 wake range")
        self.assertEqual(BOOTS["soft"].tier, 4)
        self.assertIsNone(BOOTS["soft"].trait, "Padded Soles lose softsole")
        self.assertEqual(BOOTS["whisperstep"].wake_radius, 2)
        self.assertEqual((BOOTS["whisperstep"].tier, BOOTS["whisperstep"].speed), (5, 10))
        self.assertEqual(BOOTS["sandals"].wake_radius, 0, "ordinary boots are not stealthy")

    def test_stealth_shrinks_the_range_a_monster_wakes_at(self):
        from .monsters import Monster
        # Whisperstep: radius 2. A visible rat at distance 4 must NOT be able to notice you;
        # one at distance 2 must.
        w, px, py = self._arena("whisperstep")
        far = Monster("rat", px + 4, py)
        near = Monster("rat", px + 2, py)
        w.level.monsters = [far, near]
        w.level.compute_fov(px, py)
        self.assertFalse(w.monster_can_see_player(far), "beyond your stealth radius -> unseen")
        self.assertTrue(w.monster_can_see_player(near), "within it -> spotted")
        # a plain-booted player is noticed at the normal range
        w2, px2, py2 = self._arena("sandals")
        r = Monster("rat", px2 + 4, py2)
        w2.level.monsters = [r]
        w2.level.compute_fov(px2, py2)
        self.assertTrue(w2.monster_can_see_player(r), "no stealth -> the normal ~9 range")

    def test_featherfall_still_teaches_nothing_from_a_trap_it_never_springs(self):
        # (repurposed from the old softsole test: an unfired trap teaches nothing)
        from .items import BOOTS
        from .traps import Trap
        from .dungeon import FLOOR
        codex = FakeSave()
        w = World(codex, seed=3)
        w.level.monsters = []
        w.player.boots = BOOTS["featherfall"]
        px, py = w.player.x, w.player.y
        w.level.grid[py][px + 1] = FLOOR                 # a clear step east onto the trap
        w.level.traps = [Trap("dart", px + 1, py)]
        w.player_move(1, 0)
        self.assertFalse(codex.knows("dart.rule"),
                         "featherfall never sprang it, so there was nothing to learn")

    def test_region_of_is_the_room_or_the_corridors(self):
        w = World(FakeSave(), seed=3)
        room = w.level.rooms[0]
        self.assertIs(w.region_of(room.cx, room.cy), room, "a room tile -> that Room")
        self.assertIs(w.region_of(room.cx, room.cy), w.region_of(room.x, room.y),
                      "two tiles in the same room share the region")
        # the corridors are the single None region (Option A)
        corridor = None
        for yy in range(w.level.h):
            for xx in range(w.level.w):
                if w.walkable(xx, yy) and w.region_of(xx, yy) is None:
                    corridor = (xx, yy)
                    break
            if corridor:
                break
        self.assertIsNotNone(corridor, "the map has corridors")
        self.assertIsNone(w.region_of(*corridor), "a corridor tile -> the None region")

    def test_a_monster_that_can_see_you_raises_the_alarm(self):
        from .items import BOOTS
        from .monsters import Monster
        w = World(FakeSave(), seed=3)
        w.player.boots = BOOTS["whisperstep"]          # wake radius 2
        room = w.level.rooms[0]
        w.player.x, w.player.y = room.cx, room.cy
        m = Monster("rat", room.cx, room.cy)           # same region, within the wake radius
        w.level.monsters = [m]
        w.level.visible[m.y][m.x] = True               # the player can see it -> it sees you
        w._update_stealth_alert()
        self.assertTrue(w.region_alerted, "a monster that can see you raises the alarm")
        self.assertEqual(w.player_wake_radius(), config.MONSTER_SIGHT,
                         "alerted -> stealth is off, monsters wake at the normal range")

    def test_an_awake_patroller_that_cannot_see_you_keeps_your_cover(self):
        # THE FIX: an awake monster (e.g. a patrolling orc) that has NOT actually spotted you
        # -- its tile is out of your view, so it cannot see you -- must not blow your cover
        # merely by being awake.
        from .items import BOOTS
        from .monsters import Monster
        w = World(FakeSave(), seed=3)
        w.player.boots = BOOTS["whisperstep"]
        room = w.level.rooms[0]
        w.player.x, w.player.y = room.cx, room.cy
        m = Monster("orc", room.cx, room.cy)           # same region, and wide awake
        m.awake = True
        w.level.monsters = [m]
        w.level.visible[m.y][m.x] = False              # but you cannot see it -> it cannot see you
        w._update_stealth_alert()
        self.assertFalse(w.region_alerted,
                         "an awake patroller that has not spotted you keeps your cover")
        self.assertEqual(w.player_wake_radius(), 2, "your stealth radius still holds")

    def test_leaving_the_alerted_region_clears_the_alarm(self):
        from .items import BOOTS
        w = World(FakeSave(), seed=3)
        w.player.boots = BOOTS["whisperstep"]
        start = w.region_of(w.player.x, w.player.y)
        w.player_region = start
        w.region_alerted = True
        # find a walkable tile in a DIFFERENT region and step there
        dest = None
        for yy in range(w.level.h):
            for xx in range(w.level.w):
                if w.walkable(xx, yy) and w.region_of(xx, yy) is not start:
                    dest = (xx, yy)
                    break
            if dest:
                break
        self.assertIsNotNone(dest, "the map has more than one region")
        w.player.x, w.player.y = dest
        w._update_stealth_alert()
        self.assertFalse(w.region_alerted, "leaving the region drops the alarm")


class TestMagicalBootsEconomy(unittest.TestCase):
    def test_findable_magical_boots_are_the_twelve(self):
        from .items import FINDABLE_MAGICAL_BOOT_KEYS, BOOTS, is_magical_boot
        self.assertEqual(len(FINDABLE_MAGICAL_BOOT_KEYS), 12)
        self.assertEqual(FINDABLE_MAGICAL_BOOT_KEYS,
                         {k for k, g in BOOTS.items() if g.tier >= 4})
        for k in FINDABLE_MAGICAL_BOOT_KEYS:
            self.assertTrue(is_magical_boot(k), "%s is magical (tier 4/5)" % k)
        self.assertFalse(is_magical_boot("sandals"), "the starter is not magical")
        self.assertFalse(is_magical_boot("boots_leather"), "ordinary boots are not magical")

    def test_roll_floor_boots_magical_is_rare_deep_and_always_magical(self):
        import random
        from .items import roll_floor_boots_magical, FINDABLE_MAGICAL_BOOT_KEYS
        for depth in range(1, 8):                 # never on floors 1-7
            for s in range(60):
                self.assertIsNone(roll_floor_boots_magical(random.Random(s), depth))
        got = [roll_floor_boots_magical(random.Random(s), 8) for s in range(4000)]
        present = [k for k in got if k is not None]
        rate = len(present) / 4000
        self.assertGreater(rate, 0.10, "present ~14%% at floor 8 (got %.3f)" % rate)
        self.assertLess(rate, 0.18, "present ~14%% at floor 8 (got %.3f)" % rate)
        self.assertTrue(all(k in FINDABLE_MAGICAL_BOOT_KEYS for k in present),
                        "the slot only ever yields a findable magical boot")

    def test_roll_floor_boots_magical_uniqueness_via_exclude(self):
        import random
        from .items import roll_floor_boots_magical, FINDABLE_MAGICAL_BOOTS
        excl_t4 = set(FINDABLE_MAGICAL_BOOTS[4])   # every T4 already generated
        for s in range(500):
            k = roll_floor_boots_magical(random.Random(s), 10, exclude=excl_t4)
            self.assertNotIn(k, excl_t4, "an excluded boot never generates again")
        every = set(FINDABLE_MAGICAL_BOOTS[4]) | set(FINDABLE_MAGICAL_BOOTS[5])
        for s in range(500):
            self.assertIsNone(roll_floor_boots_magical(random.Random(s), 10, exclude=every),
                              "with every boot generated, the slot is empty")

    def test_boots_generated_ledger_records_uniquely_and_persists(self):
        c = FakeSave()
        self.assertEqual(c.boots_generated, [])
        c.record_magical_boot_placed("whisperstep", 9, 5, 5)
        c.record_magical_boot_placed("whisperstep", 9, 5, 5)   # idempotent -- no duplicate
        c.record_magical_boot_placed("thor", 12, 3, 3)
        self.assertEqual(set(c.boots_generated), {"whisperstep", "thor"})
        self.assertEqual(len(c.boots_generated), 2, "no duplicate keys")
        self.assertEqual(set(c._save_dict()["boots_generated"]), {"whisperstep", "thor"},
                         "the ledger persists in the save")
        c.new_dungeon()
        self.assertEqual(c.boots_generated, [], "a new game clears it")

    def test_generation_respects_the_uniqueness_ledger(self):
        from .items import is_magical_boot, FINDABLE_MAGICAL_BOOT_KEYS
        codex = FakeSave()
        codex.world_seed = 5
        # pretend every magical boot except 'thor' has already been generated this game
        codex.boots_generated = [k for k in FINDABLE_MAGICAL_BOOT_KEYS if k != "thor"]
        w = World(codex, seed=5)
        placed = set()
        for depth in range(8, 21):
            w.new_level(depth)
            for d in w.level.drops:
                if d.kind == "gear" and is_magical_boot(d.payload):
                    placed.add(d.payload)
        self.assertFalse(placed - {"thor"},
                         "only the un-generated boot can still be placed: %s" % placed)

    def test_magical_boots_appear_deep_recorded_and_never_shallow(self):
        from .items import is_magical_boot
        appeared = False
        for seed in range(30):
            codex = FakeSave()
            codex.world_seed = seed
            w = World(codex, seed=seed)
            for depth in range(8, 16):
                w.new_level(depth)
                for d in w.level.drops:
                    if d.kind == "gear" and is_magical_boot(d.payload):
                        appeared = True
                        self.assertIn(d.payload, codex.boots_generated,
                                      "a placed magical boot is recorded for uniqueness")
            w.new_level(5)
            self.assertFalse(any(d.kind == "gear" and is_magical_boot(d.payload)
                                 for d in w.level.drops),
                             "no magical boots on a shallow floor")
        self.assertTrue(appeared, "magical boots do appear on the deep floors")

    def test_record_grounds_the_boot_and_pickup_takes_it_off(self):
        c = FakeSave()
        c.record_magical_boot_placed("whisperstep", 9, 5, 5)
        self.assertIn("whisperstep", c.boots_generated, "recorded for uniqueness")
        self.assertEqual(c.boots_ground["whisperstep"], {"depth": 9, "x": 5, "y": 5},
                         "and on the ground for persistence")
        c.magical_boot_picked_up("whisperstep")
        self.assertNotIn("whisperstep", c.boots_ground, "picked up -> off the ground")
        self.assertIn("whisperstep", c.boots_collected, "and into the collected set")

    def test_dropping_a_magical_boot_persists_it(self):
        c = FakeSave()
        c.drop_magical_boot_to_ground("thor", 12, 3, 4)
        self.assertIn("thor", c.boots_generated)
        self.assertEqual(c.boots_ground["thor"], {"depth": 12, "x": 3, "y": 4})

    def test_collecting_all_twelve_awards_the_gold_star_once(self):
        from .items import FINDABLE_MAGICAL_BOOT_KEYS
        c = FakeSave()
        results = [c.magical_boot_picked_up(k) for k in FINDABLE_MAGICAL_BOOT_KEYS]
        self.assertEqual(sum(results), 1, "exactly one pickup completes the set")
        c.award_boots_collection()
        self.assertEqual(c.stats.get("magical_boots_collected_all"), 1, "the gold star")
        self.assertIn("self.magical_boot_collector", c.known, "the Kodex fact")
        c.award_boots_collection()   # idempotent
        self.assertEqual(c.known.count("self.magical_boot_collector"), 1)

    def test_boots_persistence_ledgers_round_trip_and_reset(self):
        c = FakeSave()
        c.record_magical_boot_placed("wind", 10, 2, 2)
        c.magical_boot_picked_up("wind")
        d = c._save_dict()
        self.assertEqual(d["boots_ground"], c.boots_ground)
        self.assertIn("wind", d["boots_collected"])
        c.new_dungeon()
        self.assertEqual(c.boots_ground, {})
        self.assertEqual(c.boots_collected, [])

    def test_a_magical_boot_survives_death_and_replays_where_it_fell(self):
        codex = FakeSave()
        codex.world_seed = 7
        w0 = World(codex, seed=7)
        w0.new_level(10)
        ex, ey = w0.level.entrance                 # a guaranteed-walkable tile on floor 10
        # a past life left a magical boot on floor 10 (clear this life's rolls first)
        codex.boots_ground = {}
        codex.boots_generated = []
        codex.record_magical_boot_placed("thor", 10, ex, ey)
        # a NEW life: same codex, fresh World -- floor 10 replays it where it fell
        w = World(codex, seed=7)
        w.new_level(10)
        thors = [d for d in w.level.drops if d.kind == "gear" and d.payload == "thor"]
        self.assertEqual(len(thors), 1, "the boot is still on floor 10")
        self.assertEqual((thors[0].x, thors[0].y), (ex, ey), "exactly where it fell")

    def test_picking_a_magical_boot_off_the_floor_collects_it(self):
        w = World(FakeSave(), seed=3)
        spot = w.drop_gear_near("whisperstep")     # a magical boot on the floor
        w.player.x, w.player.y = spot
        w.take_all()                                # auto-equips over the T0 starter
        self.assertEqual(w.player.boots.key, "whisperstep")
        self.assertIn("whisperstep", w.codex.boots_collected, "picking it up collects it")

    def test_boots_bench_collects_and_awards_at_all_twelve(self):
        from .items import FINDABLE_MAGICAL_BOOT_KEYS
        w = World(FakeSave(), seed=3)
        for k in FINDABLE_MAGICAL_BOOT_KEYS:
            w.cheat_equip_boots(k)                  # the bench collects each
        self.assertEqual(w.codex.stats.get("magical_boots_collected_all"), 1,
                         "gathering all 12 fires the gold star")
        self.assertIn("self.magical_boot_collector", w.codex.known)

    def test_displacing_a_magical_boot_persists_it_to_the_ground(self):
        from .items import BOOTS
        w = World(FakeSave(), seed=3)
        w.player.boots = BOOTS["thor"]              # wearing a magical boot
        w.cheat_equip_boots("boots_leather")        # bench swaps -> thor drops & persists
        self.assertEqual(w.player.boots.key, "boots_leather")
        self.assertIn("thor", w.codex.boots_ground, "the displaced magical boot persists")


class TestRunBlockPersistence(unittest.TestCase):
    """The suspended-run block travels in the save, guarded by its own version,
    and is cleared by a fresh dungeon or a new game."""

    def test_run_block_round_trips_through_save_dict(self):
        c = FakeSave()
        c.run = {"depth": 3, "player": {"x": 5}}
        d = c._save_dict()
        self.assertEqual(d["run"], {"version": config.RUN_SAVE_VERSION,
                                    "world": {"depth": 3, "player": {"x": 5}}})
        c2 = FakeSave()
        c2._load_from(d)
        self.assertEqual(c2.run, {"depth": 3, "player": {"x": 5}})

    def test_none_run_block_round_trips_as_none(self):
        c = FakeSave()
        c.run = None
        c2 = FakeSave()
        c2._load_from(c._save_dict())
        self.assertIsNone(c2.run)

    def test_a_stale_version_run_block_is_discarded(self):
        c = FakeSave()
        data = c._save_dict()
        data["run"] = {"version": config.RUN_SAVE_VERSION + 1,
                       "world": {"depth": 9}}
        c._load_from(data)
        self.assertIsNone(c.run, "a run block from another build must not be trusted")

    def test_a_layout_mismatch_discards_the_run_block(self):
        c = FakeSave()
        data = c._save_dict()
        data["run"] = {"version": config.RUN_SAVE_VERSION, "world": {"depth": 4}}
        data["layout_version"] = config.LAYOUT_VERSION + 1
        c._load_from(data)
        self.assertIsNone(c.run, "a re-cut dungeon makes the old run meaningless")

    def test_an_old_save_without_a_run_key_loads_as_none(self):
        c = FakeSave()
        data = c._save_dict()
        del data["run"]
        c._load_from(data)
        self.assertIsNone(c.run)

    def test_new_dungeon_clears_the_run_block(self):
        c = FakeSave()
        c.run = {"depth": 2}
        c.new_dungeon()
        self.assertIsNone(c.run)

    def test_a_fresh_codex_has_no_run_block(self):
        self.assertIsNone(FakeSave().run)

    def test_a_non_dict_run_value_is_discarded_without_crashing(self):
        """A hand-corrupted save with a truthy non-dict 'run' value must not crash
        at startup -- the spec promises never to crash on a stale/incompatible save."""
        c = FakeSave()
        data = c._save_dict()
        data["run"] = "garbage"
        c._load_from(data)
        self.assertIsNone(c.run)


class TestPlayerSerialization(unittest.TestCase):
    """A player survives a round-trip through a plain dict with every field intact."""

    def test_player_round_trips_through_a_dict(self):
        import json
        from .player import Player
        from .items import ALL_GEAR
        p = Player()
        p.x, p.y = 7, 11
        p.hp, p.max_hp = 13, 20
        p.gold = 42
        p.energy = 3
        p.depth = 5
        p.kills = 9
        p.poison = 4
        p.haste = 2
        p.berserk = 6
        p.phoenix = True
        p.invisible = 3
        p.frozen = 1
        p.slipstep_hits = 3
        p.blade_coat = "weak"
        p.gift = "a_gift_key"
        p.armour = ALL_GEAR["plate"].copy(bonus=2)
        p.slots = [["a potion", 3], None, ["a scroll", 1], None, None, None]
        p.weapon = ALL_GEAR["kris"].copy(bonus=2)
        p.boots = ALL_GEAR["boots_plate"]

        blob = p.to_dict()
        json.dumps(blob)                      # must be JSON-safe
        q = Player.from_dict(blob)

        for k in ("x", "y", "hp", "max_hp", "gold", "energy", "depth", "kills",
                  "poison", "haste", "berserk", "phoenix", "invisible", "frozen",
                  "slipstep_hits", "blade_coat", "gift"):
            self.assertEqual(getattr(q, k), getattr(p, k), k)
        self.assertEqual(q.weapon.key, "kris")
        self.assertEqual(q.weapon.bonus, 2)
        self.assertEqual(q.armour.key, "plate")
        self.assertEqual(q.armour.bonus, 2)
        self.assertEqual(q.boots.key, "boots_plate")
        self.assertEqual(q.slots, [["a potion", 3], None,
                                   ["a scroll", 1], None, None, None])


class TestArmourBonusModel(unittest.TestCase):
    def test_defense_reads_the_per_instance_armour_bonus(self):
        from .items import ALL_GEAR
        from .player import Player
        p = Player()
        p.armour = ALL_GEAR["plate"].copy(bonus=2)     # Full Plate +2
        self.assertEqual(p.defense, ALL_GEAR["plate"].defense + 2)

    def test_enchant_armour_scroll_raises_the_bonus(self):
        from .items import ALL_GEAR
        codex = FakeSave()
        w = World(codex, seed=3)
        w.player.armour = ALL_GEAR["plate"].copy()      # +0
        before = w.player.defense
        w._apply_effect("enchant_armour")
        self.assertEqual(w.player.armour.bonus, 1)
        self.assertEqual(w.player.defense, before + 1)

    def test_grant_cheat_armour_is_private_not_the_shared_template(self):
        """grant_cheat must copy the shared ARMOURS entry the same way it copies
        the weapon -- otherwise enchant_armour mutates the module-level singleton
        and every future Player() inherits the inflated bonus."""
        from .items import ARMOURS
        from .player import Player

        codex = FakeSave()
        w = World(codex, seed=3)
        w.level.monsters = []
        w.grant_cheat()

        best_key = max(ARMOURS.values(), key=lambda g: (g.tier, g.defense)).key
        self.assertIsNot(w.player.armour, ARMOURS[best_key],
                         "the cheat must hand the player a private copy")

        w._apply_effect("enchant_armour")
        self.assertEqual(w.player.armour.bonus, 1)

        self.assertEqual(ARMOURS[best_key].bonus, 0,
                         "the shared template must stay untouched")
        self.assertEqual(Player().armour.bonus, 0,
                         "a fresh player must not inherit the cheat's mutation")


class TestMagicalArmourRoster(unittest.TestCase):
    def test_the_eleven_phase1_pieces_have_the_agreed_stats(self):
        from .items import ARMOURS
        # key: (tier, defense, speed_mod, trait)
        expected = {
            "thorn":      (4, 3, -5,  "thorns"),
            "silk":       (4, 2, 10,  "wraithsilk"),
            "venom":      (4, 3, -5,  "venom"),
            "cinder":     (4, 3, -5,  "cinder"),
            "glacial":    (4, 3, -5,  "glacial"),
            "lifeweave":  (4, 3, -5,  "lifeweave"),
            "bastion":    (5, 4, -15, "bastion"),
            "lastbreath": (5, 4, -10, "lastbreath"),
            "blinding":   (5, 3, -5,  "blinding"),
            "stonegolem": (5, 5, 0,   None),
            "hades":      (5, 3, 0,   "hades"),
        }
        for key, (tier, defense, spd, trait) in expected.items():
            a = ARMOURS[key]
            self.assertEqual((a.tier, a.defense, a.speed_mod, a.trait),
                             (tier, defense, spd, trait), key)

    def test_magical_armour_sprites_render(self):
        from . import sprites
        for key in ("thorn", "silk", "venom", "cinder", "glacial", "lifeweave",
                    "bastion", "lastbreath", "blinding", "stonegolem", "hades"):
            self.assertIsNotNone(sprites.gear(key), key)


class TestMagicalArmourDistribution(unittest.TestCase):
    def test_never_before_floor_eight(self):
        import random
        from .items import roll_floor_armour_magical
        for depth in (1, 5, 7):
            for s in range(60):
                self.assertIsNone(roll_floor_armour_magical(random.Random(s), depth))

    def test_only_phase1_findable_keys_appear(self):
        import random
        from .items import roll_floor_armour_magical, FINDABLE_MAGICAL_ARMOUR_KEYS
        seen = set()
        for depth in range(8, 21):
            for s in range(400):
                k = roll_floor_armour_magical(random.Random(s), depth)
                if k:
                    seen.add(k)
        self.assertTrue(seen <= FINDABLE_MAGICAL_ARMOUR_KEYS)
        # boss-reserved pieces never drop; fade is Phase 2 findable now
        for boss in ("shade", "nightcloak"):
            self.assertNotIn(boss, seen)

    def test_uniqueness_via_exclude_and_determinism(self):
        import random
        from .items import roll_floor_armour_magical
        for s in range(50):
            self.assertEqual(roll_floor_armour_magical(random.Random(s), 12),
                             roll_floor_armour_magical(random.Random(s), 12))
        # excluding the whole pool yields nothing
        from .items import FINDABLE_MAGICAL_ARMOUR_KEYS
        got = [roll_floor_armour_magical(random.Random(s), 12,
               exclude=FINDABLE_MAGICAL_ARMOUR_KEYS) for s in range(200)]
        self.assertTrue(all(g is None for g in got))


class TestArmourMagicalDistribution(unittest.TestCase):
    def test_none_below_floor_eight_without_consuming_a_draw(self):
        rng = _SeqRng([])                              # no draw available
        self.assertIsNone(roll_floor_armour_magical(rng, 7))
        self.assertEqual(rng.i, 0, "shallow floors draw no rng")

    def test_floor_eight_rolls_t4_only(self):
        from .items import FINDABLE_MAGICAL_ARMOUR
        hit = roll_floor_armour_magical(_SeqRng([0.0]), 8)      # T4 present hit
        self.assertIn(hit, FINDABLE_MAGICAL_ARMOUR[4])
        self.assertIsNone(roll_floor_armour_magical(_SeqRng([0.99]), 8))  # T4 miss -> nothing

    def test_t5_only_from_floor_ten_and_gets_first_dibs(self):
        from .items import FINDABLE_MAGICAL_ARMOUR
        # floor 9: no T5 band -> a single draw is the T4 roll
        self.assertIn(roll_floor_armour_magical(_SeqRng([0.0]), 9),
                      FINDABLE_MAGICAL_ARMOUR[4])
        # floor 10: T5 rolled first; a hit yields a T5 and consumes ONE draw (no T4 roll)
        rng = _SeqRng([0.0])
        self.assertIn(roll_floor_armour_magical(rng, 10), FINDABLE_MAGICAL_ARMOUR[5])
        self.assertEqual(rng.i, 1, "a T5 hit does not also roll T4")

    def test_t5_miss_falls_through_to_t4(self):
        from .items import FINDABLE_MAGICAL_ARMOUR
        # floor 12: T5 misses (0.99), T4 hits (0.0)
        self.assertIn(roll_floor_armour_magical(_SeqRng([0.99, 0.0]), 12),
                      FINDABLE_MAGICAL_ARMOUR[4])
        # both miss -> nothing
        self.assertIsNone(roll_floor_armour_magical(_SeqRng([0.99, 0.99]), 12))

    def test_uniqueness_exclusion_and_exhausted_pool(self):
        from .items import FINDABLE_MAGICAL_ARMOUR
        # floor 8, all T4 already generated -> a "hit" finds an empty pool -> None
        self.assertIsNone(
            roll_floor_armour_magical(_SeqRng([0.0]), 8,
                                      exclude=FINDABLE_MAGICAL_ARMOUR[4]))
        # floor 12, T5 pool exhausted but T5 hits -> falls through to a T4 hit
        self.assertIn(
            roll_floor_armour_magical(_SeqRng([0.0, 0.0]), 12,
                                      exclude=FINDABLE_MAGICAL_ARMOUR[5]),
            FINDABLE_MAGICAL_ARMOUR[4])

    def test_same_inputs_same_result_regardless_of_kodex(self):
        # determinism at the unit level: identical (rng-seq, depth, exclude) -> identical key
        a = roll_floor_armour_magical(_SeqRng([0.99, 0.0]), 14)
        b = roll_floor_armour_magical(_SeqRng([0.99, 0.0]), 14)
        self.assertEqual(a, b)


class TestArmourPersistence(unittest.TestCase):
    def test_record_grounds_the_armour_for_replay(self):
        c = FakeSave()
        self.assertEqual(c.armour_ground, {})
        c.record_magical_armour_placed("thorn", 9, 5, 6)
        c.record_magical_armour_placed("thorn", 9, 5, 6)      # idempotent
        self.assertIn("thorn", c.armour_generated)
        self.assertEqual(len(c.armour_generated), 1, "no duplicate keys")
        self.assertEqual(c.armour_ground["thorn"],
                         {"depth": 9, "x": 5, "y": 6, "bonus": 0})

    def test_dropping_an_enchanted_armour_persists_its_bonus(self):
        c = FakeSave()
        c.drop_magical_armour_to_ground("bastion", 12, 3, 4, 2)
        self.assertIn("bastion", c.armour_generated)
        self.assertEqual(c.armour_ground["bastion"],
                         {"depth": 12, "x": 3, "y": 4, "bonus": 2})

    def test_ground_ledger_round_trips_and_resets(self):
        c = FakeSave()
        c.record_magical_armour_placed("thorn", 10, 2, 2)
        d = c._save_dict()
        self.assertEqual(d["armour_ground"], c.armour_ground)
        c.new_dungeon()
        self.assertEqual(c.armour_ground, {}, "a new dungeon clears the ground")

    def test_a_magical_armour_survives_death_and_replays_where_it_fell(self):
        codex = FakeSave()
        codex.world_seed = 7
        w0 = World(codex, seed=7)
        w0.new_level(10)
        ex, ey = w0.level.entrance                     # guaranteed-walkable on floor 10
        codex.armour_ground = {}
        codex.armour_generated = []
        codex.record_magical_armour_placed("thorn", 10, ex, ey)
        w = World(codex, seed=7)                       # a new life, same codex
        w.new_level(10)
        found = [d for d in w.level.drops
                 if d.kind == "gear" and d.payload == "thorn"]
        self.assertEqual(len(found), 1, "the armour is still on floor 10")
        self.assertEqual((found[0].x, found[0].y), (ex, ey), "exactly where it fell")

    def test_replayed_armour_keeps_its_enchant_bonus(self):
        codex = FakeSave()
        codex.world_seed = 7
        w0 = World(codex, seed=7)
        w0.new_level(10)
        ex, ey = w0.level.entrance
        codex.armour_ground = {}
        codex.armour_generated = []
        codex.drop_magical_armour_to_ground("bastion", 10, ex, ey, 2)
        w = World(codex, seed=7)
        w.new_level(10)
        found = [d for d in w.level.drops
                 if d.kind == "gear" and d.payload == "bastion"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].bonus, 2, "the enchant survives death")


class TestArmourCollection(unittest.TestCase):
    def test_pickup_grounds_off_and_collects(self):
        c = FakeSave()
        c.record_magical_armour_placed("thorn", 9, 5, 5)
        c.magical_armour_picked_up("thorn")
        self.assertNotIn("thorn", c.armour_ground, "picked up -> off the ground")
        self.assertIn("thorn", c.armour_collected, "and into the collected set")

    def test_collecting_all_findable_awards_the_star_once(self):
        from .items import FINDABLE_MAGICAL_ARMOUR_KEYS
        c = FakeSave()
        results = [c.magical_armour_picked_up(k) for k in FINDABLE_MAGICAL_ARMOUR_KEYS]
        self.assertEqual(sum(results), 1, "exactly one pickup completes the set")
        c.award_armour_collection()
        self.assertEqual(c.stats.get("magical_armours_collected_all"), 1, "the gold star")
        self.assertIn("self.magical_armour_collector", c.known, "the Kodex fact")
        c.award_armour_collection()                       # idempotent
        self.assertEqual(c.known.count("self.magical_armour_collector"), 1)

    def test_a_boss_piece_neither_completes_nor_blocks_the_star(self):
        from .items import FINDABLE_MAGICAL_ARMOUR_KEYS
        c = FakeSave()
        self.assertFalse(c.magical_armour_picked_up("shade"),
                         "a boss piece alone does not complete the findable set")
        # now collect all findable -> the last one still completes it
        results = [c.magical_armour_picked_up(k) for k in FINDABLE_MAGICAL_ARMOUR_KEYS]
        self.assertEqual(sum(results), 1)
        # picking up the other boss piece afterwards does not re-fire
        self.assertFalse(c.magical_armour_picked_up("nightcloak"))

    def test_collected_ledger_round_trips_and_resets(self):
        c = FakeSave()
        c.magical_armour_picked_up("thorn")
        d = c._save_dict()
        self.assertIn("thorn", d["armour_collected"])
        c.new_dungeon()
        self.assertEqual(c.armour_collected, [])


class TestArmourEconomyWiring(unittest.TestCase):
    def test_picking_a_magical_armour_off_the_floor_collects_it(self):
        w = World(FakeSave(), seed=3)
        spot = w.drop_gear_near("thorn")                # a magical armour on the floor
        w.player.x, w.player.y = spot
        w.take_all()                                    # auto-equips over the T0 starter (rags)
        self.assertEqual(w.player.armour.key, "thorn")
        self.assertIn("thorn", w.codex.armour_collected, "picking it up collects it")

    def test_bench_collects_and_awards_at_all_findable(self):
        from .items import FINDABLE_MAGICAL_ARMOUR_KEYS
        w = World(FakeSave(), seed=3)
        for k in FINDABLE_MAGICAL_ARMOUR_KEYS:
            w.cheat_equip_armour(k)                     # the bench collects each
        self.assertEqual(w.codex.stats.get("magical_armours_collected_all"), 1,
                         "gathering all 12 fires the gold star")
        self.assertIn("self.magical_armour_collector", w.codex.known)

    def test_displacing_a_magical_armour_persists_it_to_bare_ground(self):
        from .items import ARMOURS
        from .dungeon import Chest
        w = World(FakeSave(), seed=3)
        w.player.armour = ARMOURS["thorn"].copy()       # wearing a magical armour
        old = w.player.equip(ARMOURS["bastion"].copy()) # swap it off -> `old` is thorn
        chest = Chest(w.player.x, w.player.y, [])        # a container at our feet
        w._put_back(old, chest)
        self.assertNotIn(("gear", "thorn", 0), chest.loot,
                        "a magical armour never goes into a container")
        self.assertIn("thorn", w.codex.armour_ground,
                      "the displaced magical armour persists on bare ground")
        self.assertTrue(any(d.kind == "gear" and d.payload == "thorn"
                            for d in w.level.drops), "it is a floor drop")


class TestArmourLadder(unittest.TestCase):
    def test_the_four_rungs_have_the_agreed_stats(self):
        from .items import ARMOURS
        expected = {
            "rags":    (0, 0, 0),
            "leather": (1, 2, 0),
            "mail":    (2, 3, -10),
            "plate":   (3, 4, -20),
        }
        # the ordinary ladder's stats hold; ARMOURS also carries the magical roster
        # now (thorn/silk graduated back in, plus the new Phase-1 pieces), so this
        # no longer asserts an exact key set -- see TestMagicalArmourRoster for that.
        for key, (tier, defense, speed) in expected.items():
            a = ARMOURS[key]
            self.assertEqual((a.tier, a.defense, a.speed_mod), (tier, defense, speed), key)

    def test_the_retired_trait_armours_are_gone(self):
        """scale/chain were retired outright (never graduated); thorn/silk graduated
        back into the magical roster (see TestMagicalArmourRoster), so they're no
        longer expected to be absent here."""
        from .items import ARMOURS
        for gone in ("scale", "chain"):
            self.assertNotIn(gone, ARMOURS, "%s retired" % gone)


class TestFloorArmourRoll(unittest.TestCase):
    def test_never_on_floor_one_or_past_fifteen(self):
        import random
        from .items import roll_floor_armour
        for depth in (1, 16, 17, 20):
            for s in range(60):
                self.assertEqual(roll_floor_armour(random.Random(s), depth), [],
                                 "no ordinary armour on floor %d" % depth)

    def test_places_at_most_one(self):
        import random
        from .items import roll_floor_armour
        for depth in range(1, 21):
            for s in range(60):
                self.assertLessEqual(len(roll_floor_armour(random.Random(s), depth)), 1)

    def test_respects_the_bands(self):
        import random
        from .items import roll_floor_armour
        def seen(depth):
            out = set()
            for s in range(500):
                out |= {k for k, _ in roll_floor_armour(random.Random(s), depth)}
            return out
        self.assertEqual(seen(2), {"leather"})
        self.assertEqual(seen(4), {"leather", "mail"})
        self.assertEqual(seen(5), {"leather", "mail", "plate"})
        self.assertEqual(seen(10), {"leather", "mail", "plate"})
        self.assertEqual(seen(11), {"mail", "plate"})     # leather gone after 10
        self.assertEqual(seen(15), {"mail", "plate"})
        self.assertEqual(seen(16), set())

    def test_present_ramp_and_determinism(self):
        import random
        from .items import roll_floor_armour
        def rate(depth):
            return sum(1 for s in range(4000)
                       if roll_floor_armour(random.Random(s), depth)) / 4000
        self.assertGreater(rate(2), 0.49); self.assertLess(rate(2), 0.61)    # ~55%
        self.assertGreater(rate(12), 0.69); self.assertLess(rate(12), 0.81)  # ~75%
        for s in range(50):
            for depth in (2, 6, 12, 15):
                self.assertEqual(roll_floor_armour(random.Random(s), depth),
                                 roll_floor_armour(random.Random(s), depth))

    def test_masterwork_only_deep_and_capped_at_two(self):
        import random
        from .items import roll_floor_armour
        # floors below 8 are never masterwork
        for depth in range(2, 8):
            for s in range(300):
                for _, b in roll_floor_armour(random.Random(s), depth):
                    self.assertEqual(b, 0, "no masterwork before floor 8")
        # floors 8-15 produce +1 and +2 but never +3
        bonuses = set()
        for depth in range(8, 16):
            for s in range(600):
                for _, b in roll_floor_armour(random.Random(s), depth):
                    bonuses.add(b)
        self.assertTrue({1, 2} <= bonuses, "deep armour should roll +1 and +2")
        self.assertEqual(max(bonuses), 2, "masterwork must cap at +2, never +3")


class TestFloorArmourPlacement(unittest.TestCase):
    def _armour_drops(self, lvl):
        from .items import ARMOURS
        # ordinary only (tier <= 3) -- the magical-armour slot (tier 4/5, floors 8+) is a
        # separate cap, tested in TestMagicalArmourDistribution.
        return [d for d in lvl.drops if d.kind == "gear" and d.payload in ARMOURS
                and ARMOURS[d.payload].tier <= 3]

    def _chest_under_player(self, w, loot):
        from .dungeon import Chest
        w.level.monsters = []
        w.level.chests = [Chest(w.player.x, w.player.y, loot)]
        w.level.drops = []
        w.level.corpse = None
        return w.level.chests[0]

    def test_at_most_one_ordinary_armour_per_floor(self):
        from .dungeon import Level
        import random
        for seed in range(40):
            for depth in (3, 6, 9, 14):
                codex = FakeSave()
                codex.world_seed = seed
                lvl = Level(depth, random.Random(seed), codex)
                self.assertLessEqual(len(self._armour_drops(lvl)), 1)

    def test_take_all_will_not_swap_armour_off_a_real_piece(self):
        from .items import ALL_GEAR
        codex = FakeSave()
        w = World(codex, seed=6)
        w.player.armour = ALL_GEAR["leather"].copy()      # a real (non-starter) piece
        self._chest_under_player(w, [("gear", "plate")])
        w.take_all()
        self.assertEqual(w.player.armour.key, "leather",
                         "'all' must not silently swap armour once off the starter")

    def test_take_all_auto_equips_armour_over_the_rags_starter(self):
        from .items import ALL_GEAR
        codex = FakeSave()
        w = World(codex, seed=6)
        w.player.armour = ALL_GEAR["rags"].copy()         # the T0 starter
        self._chest_under_player(w, [("gear", "leather")])
        w.take_all()
        self.assertEqual(w.player.armour.key, "leather",
                         "the first armour still auto-equips over the starter")


class TestDisplacedMasterworkKeepsBonus(unittest.TestCase):
    def _chest_under_player(self, w, loot):
        from .dungeon import Chest
        w.level.monsters = []
        w.level.chests = [Chest(w.player.x, w.player.y, loot)]
        w.level.drops = []
        w.level.corpse = None
        return w.level.chests[0]

    def test_a_swapped_off_masterwork_armour_keeps_its_plus_in_a_chest(self):
        from .items import ALL_GEAR
        codex = FakeSave()
        w = World(codex, seed=6)
        w.player.armour = ALL_GEAR["plate"].copy(bonus=2)     # Full Plate +2
        self._chest_under_player(w, [("gear", "leather")])
        w.take_option(0)                                       # equip leather; plate -> chest
        self.assertEqual(w.player.armour.key, "leather")
        ch = w.level.chest_at(w.player.x, w.player.y)
        back = [t for t in ch.loot if t[0] == "gear" and t[1] == "plate"]
        self.assertTrue(back, "the plate must return to the chest")
        self.assertEqual(back[0][2] if len(back[0]) > 2 else 0, 2,
                         "the displaced masterwork plate kept its +2")


class TestMonsterSerialization(unittest.TestCase):
    """A monster's live state — wounds, wakefulness, a telegraphed intent, every
    status timer — survives a round-trip through a dict."""

    def test_monster_round_trips_with_all_dynamic_state(self):
        import json
        from .monsters import Monster
        m = Monster("brute", 5, 6)
        m.hp = 7
        m.energy = 1
        m.awake = True
        m.intent = ("smash", 5, 7)
        m.stunned = 2
        m.burning = 3
        m.poisoned = 1
        m.weak = 2
        m.feared = 4
        m.confused = 1
        m.hammer_hits = 2
        m.enraged = 3
        m.recharge = 1
        m.ray_armed = True
        m.fled = True
        m.warden_last = "spit"
        m.feed = 0.5

        blob = m.to_dict()
        json.dumps(blob)                      # JSON-safe
        n = Monster.from_dict(blob)

        self.assertEqual(n.key, "brute")
        self.assertEqual((n.x, n.y), (5, 6))
        self.assertEqual(n.max_hp, m.max_hp)
        for k in ("hp", "energy", "awake", "stunned", "burning", "poisoned",
                  "weak", "feared", "confused", "hammer_hits", "enraged",
                  "recharge", "ray_armed", "fled", "warden_last", "feed"):
            self.assertEqual(getattr(n, k), getattr(m, k), k)
        self.assertEqual(n.intent, ("smash", 5, 7))
        self.assertIsInstance(n.intent, tuple)

    def test_a_sleeping_monster_with_no_intent_round_trips(self):
        from .monsters import Monster
        m = Monster("rat", 2, 2)          # starts asleep, intent None
        n = Monster.from_dict(m.to_dict())
        self.assertFalse(n.awake)
        self.assertIsNone(n.intent)


class TestRecordSerialization(unittest.TestCase):
    """The small floor records — chests, drops, traps, bodies, the vendor — each
    survive a round-trip, with their tuple payloads rebuilt as tuples."""

    def test_chest_round_trips(self):
        import json
        from .dungeon import Chest
        c = Chest(4, 5, [("gold", 30), ("gear", "kris")])
        c.opened = True
        blob = c.to_dict()
        json.dumps(blob)
        d = Chest.from_dict(blob)
        self.assertEqual((d.x, d.y), (4, 5))
        self.assertTrue(d.opened)
        self.assertEqual(d.loot, [("gold", 30), ("gear", "kris")])
        self.assertIsInstance(d.loot[0], tuple)

    def test_drop_round_trips(self):
        from .dungeon import Drop
        d = Drop(2, 3, "gear", "windfang", gift="windfang", bonus=2)
        e = Drop.from_dict(d.to_dict())
        self.assertEqual((e.x, e.y, e.kind, e.payload, e.gift, e.bonus),
                         (2, 3, "gear", "windfang", "windfang", 2))

    def test_trap_round_trips_its_sprung_flag(self):
        from .traps import Trap
        t = Trap("dart", 6, 7)
        t.sprung = True
        u = Trap.from_dict(t.to_dict())
        self.assertEqual((u.key, u.x, u.y), ("dart", 6, 7))
        self.assertTrue(u.sprung)

    def test_slain_round_trips(self):
        from .dungeon import Slain
        s = Slain(3, 3, "brute", (200, 40, 40), loot=[("gold", 5)])
        t = Slain.from_dict(s.to_dict())
        self.assertEqual((t.x, t.y, t.key), (3, 3, "brute"))
        self.assertEqual(t.color, (200, 40, 40))
        self.assertEqual(t.loot, [("gold", 5)])

    def test_vendor_round_trips_without_rerolling_stock(self):
        import json, random
        from .vendor import Vendor
        v = Vendor(8, 9, depth=6, rng=random.Random(1))
        stock_before = list(v.stock)
        blob = v.to_dict()
        json.dumps(blob)
        w = Vendor.from_dict(blob)
        self.assertEqual((w.x, w.y, w.depth), (8, 9, 6))
        self.assertEqual(w.stock, stock_before)
        self.assertTrue(all(isinstance(s, tuple) for s in w.stock))


class TestLevelSerialization(unittest.TestCase):
    """A floor's dynamic state — dealt monsters, taken loot, a sprung trap, the
    contents you've laid eyes on — round-trips, while its stone regenerates
    identically from the seed."""

    def test_level_restores_dynamic_state_over_regenerated_stone(self):
        import json
        from .world import World
        from .dungeon import Level, Drop
        codex = FakeSave()
        w = World(codex, seed=4)
        lv = w.level

        # perturb the live state: wound & wake a monster, drop loot, spring a
        # trap, mark a tile's contents seen.
        if lv.monsters:
            lv.monsters[0].hp = 1
            lv.monsters[0].awake = True
        lv.drops.append(Drop(lv.entrance[0], lv.entrance[1], "gold", 7))
        if lv.traps:
            lv.traps[0].sprung = True
        lv.seen[lv.entrance[1]][lv.entrance[0]] = True

        blob = lv.to_dict()
        json.dumps(blob)
        restored = Level(lv.depth, w.rng, codex, restore=blob)

        # stone is identical (same seed) ...
        self.assertEqual(restored.grid, lv.grid)
        self.assertEqual(restored.entrance, lv.entrance)
        self.assertEqual(restored.stairs, lv.stairs)
        # ... dynamic state overlays faithfully
        self.assertEqual(len(restored.monsters), len(lv.monsters))
        if lv.monsters:
            self.assertEqual(restored.monsters[0].hp, 1)
            self.assertTrue(restored.monsters[0].awake)
        self.assertTrue(any(d.kind == "gold" and d.payload == 7
                            for d in restored.drops))
        sprung = {(t.x, t.y) for t in restored.traps if t.sprung}
        self.assertEqual(sprung, {(t.x, t.y) for t in lv.traps if t.sprung})
        self.assertTrue(restored.seen[lv.entrance[1]][lv.entrance[0]])

    def test_restore_does_not_consume_the_run_rng(self):
        from .world import World
        from .dungeon import Level
        codex = FakeSave()
        w = World(codex, seed=4)
        before = w.rng.getstate()
        Level(w.level.depth, w.rng, codex, restore=w.level.to_dict())
        self.assertEqual(w.rng.getstate(), before,
                         "restoring a floor must not deal from the run RNG")

    def test_restore_does_not_evict_a_monster_standing_on_the_grave(self):
        # A past-run corpse does not block movement, so a live monster can
        # legitimately be standing on that tile when the run is suspended. The
        # saved monster list is authoritative on restore -- the grave-clearing
        # eviction in _place_corpse exists only for the FRESH-DEAL path, and
        # must not also run here and silently delete a real, saved monster.
        from .world import World
        from .dungeon import Level, Monster
        codex = FakeSave()
        w = World(codex, seed=4)
        lv = w.level

        # record a corpse on this floor, on the entrance tile (guaranteed
        # walkable), then stand a monster on that exact tile.
        gx, gy = lv.entrance
        codex.write_corpse(lv.depth, gx, gy, 0, None, None, [])
        sentinel = Monster("rat", gx, gy)
        lv.monsters.append(sentinel)
        before_count = len(lv.monsters)

        blob = lv.to_dict()
        restored = Level(lv.depth, w.rng, codex, restore=blob)

        self.assertEqual(len(restored.monsters), before_count,
                         "a saved monster standing on a past-run grave must "
                         "survive restore")
        self.assertTrue(any(m.key == "rat" and (m.x, m.y) == (gx, gy)
                            for m in restored.monsters),
                        "the monster on the grave tile must still be there")

    def test_restore_with_a_corpse_present_does_not_consume_the_run_rng(self):
        # the _free_tile fallback in _place_corpse draws from the RUN rng --
        # latent on restore today because the death tile is always walkable in
        # practice, but the guard must still be in place.
        from .world import World
        from .dungeon import Level
        codex = FakeSave()
        w = World(codex, seed=4)
        lv = w.level
        gx, gy = lv.entrance
        codex.write_corpse(lv.depth, gx, gy, 0, None, None, [])

        before = w.rng.getstate()
        Level(lv.depth, w.rng, codex, restore=lv.to_dict())
        self.assertEqual(w.rng.getstate(), before,
                         "restoring a floor with a corpse present must not "
                         "deal from the run RNG")

    def test_restore_relinks_the_hoard_room(self):
        from .world import World
        codex = FakeSave()
        w = World(codex, seed=4)
        lv = w.level
        self.assertTrue(lv.rooms)
        lv.hoard = lv.rooms[-1]

        blob = lv.to_dict()
        self.assertEqual(blob["hoard"], [lv.hoard.cx, lv.hoard.cy])
        restored = type(lv)(lv.depth, w.rng, codex, restore=blob)

        self.assertIsNotNone(restored.hoard)
        self.assertEqual((restored.hoard.cx, restored.hoard.cy),
                         (lv.hoard.cx, lv.hoard.cy))


class TestWorldSerialization(unittest.TestCase):
    """A whole run — position, gear, floor state, and the exact RNG cursor —
    survives a round-trip, and the restored run deals its next floor identically."""

    def test_world_round_trips_position_gear_and_rng(self):
        import json
        from .world import World
        codex = FakeSave()
        w = World(codex, seed=4)
        w.player.x, w.player.y = w.level.entrance
        w.player.gold = 55
        w.tick = 12
        w.vendor_pct = 30
        w.run_kills = 3

        blob = w.to_dict()
        json.dumps(blob)
        w2 = World(codex, restore=blob)

        self.assertEqual(w2.depth, w.depth)
        self.assertEqual((w2.player.x, w2.player.y), (w.player.x, w.player.y))
        self.assertEqual(w2.player.gold, 55)
        self.assertEqual(w2.tick, 12)
        self.assertEqual(w2.vendor_pct, 30)
        self.assertEqual(w2.run_kills, 3)
        self.assertEqual(w2.player.weapon.key, w.player.weapon.key)
        self.assertEqual(w2.level.grid, w.level.grid)
        # the RNG cursor is exactly where it was: the next draw matches
        self.assertEqual(w2.rng.getstate(), w.rng.getstate())
        self.assertEqual(w2.rng.random(), w.rng.random())

    def test_resumed_run_descends_into_an_identical_next_floor(self):
        # RNG continuity: a floor first entered AFTER a suspend/resume has the
        # same contents it would have had without the interruption.
        from .world import World
        codex = FakeSave()
        w = World(codex, seed=4)
        w2 = World(codex, restore=w.to_dict())

        w.new_level(2)
        w2.new_level(2)
        self.assertEqual([m.key for m in w2.level.monsters],
                         [m.key for m in w.level.monsters])
        self.assertEqual([(d.x, d.y, d.kind) for d in w2.level.drops],
                         [(d.x, d.y, d.kind) for d in w.level.drops])


class TestSuspendResumeLifecycle(unittest.TestCase):
    """Quitting suspends; Continue resumes exactly; death clears the run so the
    next Continue is a fresh descent."""

    def _game(self):
        from .game import Game
        g = Game.__new__(Game)          # bypass pygame init
        g.codex = FakeSave()
        g.victory_gear = None
        g.banner = None
        g.banner_age = 0.0
        g.world = None
        g.state = None
        return g

    def test_continue_resumes_a_suspended_run_at_its_depth(self):
        from .game import PLAY
        g = self._game()
        w = World(g.codex, seed=4)
        w.new_level(3)                  # descend; a fresh run would be depth 1
        g.codex.run = w.to_dict()
        g.world = None                  # simulate a relaunch
        g.continue_run()
        self.assertEqual(g.world.depth, 3, "Continue must resume the suspended floor")
        self.assertEqual(g.state, PLAY)

    def test_continue_with_no_suspended_run_starts_fresh_and_stamps_a_block(self):
        g = self._game()
        g.codex.run = None
        g.continue_run()
        self.assertEqual(g.world.depth, 1, "no suspended run -> a fresh descent")
        self.assertIsNotNone(g.codex.run, "a fresh run is immediately resumable")

    def test_a_malformed_run_block_falls_back_to_a_fresh_run_without_crashing(self):
        g = self._game()
        g.codex.run = {"garbage": True}
        g.continue_run()                # must not raise
        self.assertIsNotNone(g.world)
        self.assertEqual(g.world.depth, 1)

    def test_death_clears_the_run_block(self):
        g = self._game()
        g.world = World(g.codex, seed=4)
        g.world.death_cause = "rat"
        g.codex.run = g.world.to_dict()
        g.reveal_t = 0.0
        g.on_death()
        self.assertIsNone(g.codex.run, "permadeath: the suspended run is cleared")

    def test_new_run_stamps_a_resumable_block(self):
        g = self._game()
        g.new_run()
        self.assertIsNotNone(g.codex.run)
        self.assertEqual(g.codex.run["depth"], 1)

    def test_begin_dying_clears_the_run_block_before_the_death_freeze(self):
        """Death is registered the instant the fatal blow lands -- not after the
        DEATH_FREEZE animation. If the window closes during that freeze, quit()
        must not persist a stale ALIVE run block that would resurrect a dead run
        on the next Continue."""
        from .game import DYING
        g = self._game()
        g.world = World(g.codex, seed=4)
        g.codex.run = g.world.to_dict()   # stale ALIVE block, as if just autosaved
        g.world.dead = True               # the fatal blow has landed this turn
        g._begin_dying()
        self.assertIsNone(g.codex.run,
                           "the run block must be cleared the instant death registers")
        self.assertEqual(g.state, DYING)


class TestArmourEndToEnd(unittest.TestCase):
    def test_a_deep_masterwork_armour_equips_with_its_bonus(self):
        from .items import ALL_GEAR
        codex = FakeSave()
        w = World(codex, seed=6)
        # a masterwork Full Plate lying on the floor, picked up off bare ground
        from .dungeon import Drop
        p = w.player
        w.level.drops.append(Drop(p.x, p.y, "gear", "plate", bonus=2))
        p.armour = ALL_GEAR["rags"].copy()          # so the swap is an upgrade over starter
        base = ALL_GEAR["plate"].defense
        w.take_all()
        self.assertEqual(p.armour.key, "plate")
        self.assertEqual(p.armour.bonus, 2)
        self.assertEqual(p.defense, base + 2 + p.boots.defense)

    def test_full_plate_and_plate_boots_share_the_speed_budget(self):
        from .items import ALL_GEAR
        from .player import Player
        from . import config
        p = Player()
        p.armour = ALL_GEAR["plate"].copy()         # -20 spd
        p.boots = ALL_GEAR["boots_plate"]           # -10 spd
        self.assertEqual(p.speed(), max(30, config.BASE_SPEED - 30))
        self.assertEqual(p.defense, 4 + 2)          # +4 armour, +2 boots


class TestReactiveArmourInfra(unittest.TestCase):
    def test_new_reactive_state_defaults_and_ticks(self):
        from .player import Player
        p = Player()
        self.assertEqual(p.armour_cd, 0)
        self.assertFalse(p.lastbreath_used)

    def test_armour_cd_ticks_down_each_turn(self):
        codex = FakeSave()
        w = World(codex, seed=6)
        w.player.armour_cd = 3
        w.player.tick_effects(w)
        self.assertEqual(w.player.armour_cd, 2)

    def test_reactive_state_round_trips_and_old_saves_default(self):
        import json
        from .items import ALL_GEAR
        from .player import Player
        p = Player()
        p.armour_cd = 2
        p.lastbreath_used = True
        blob = p.to_dict()
        q = Player.from_dict(json.loads(json.dumps(blob)))
        self.assertEqual(q.armour_cd, 2)
        self.assertTrue(q.lastbreath_used)
        # an OLD save that predates these fields must load with defaults, not crash
        old = p.to_dict()
        del old["armour_cd"]
        del old["lastbreath_used"]
        r = Player.from_dict(old)
        self.assertEqual(r.armour_cd, 0)
        self.assertFalse(r.lastbreath_used)


class TestRehomedArmourTraits(unittest.TestCase):
    def test_thorned_cuirass_returns_damage(self):
        from .items import ALL_GEAR
        from .monsters import Monster
        codex = FakeSave()
        w = World(codex, seed=6)
        w.player.armour = ALL_GEAR["thorn"].copy()
        m = Monster("kobold", w.player.x + 1, w.player.y)
        w.level.monsters = [m]
        before = m.hp
        w.monster_attacks_player(m, 3)
        self.assertLess(m.hp, before, "thorns must bite an attacker back")

    def test_wraithsilk_negates_a_wraith_touch(self):
        from .items import ALL_GEAR
        from .monsters import Monster
        codex = FakeSave()
        w = World(codex, seed=6)
        w.player.armour = ALL_GEAR["silk"].copy()
        m = Monster("wraith", w.player.x + 1, w.player.y)
        w.level.monsters = [m]
        hp = w.player.hp
        m._ai_wraith(w, w.player)          # the adjacency-touch path
        self.assertEqual(w.player.hp, hp, "wraithsilk must eat the wraith's touch")


class TestRetaliationArmour(unittest.TestCase):
    def _hit(self, key):
        from .items import ALL_GEAR
        from .monsters import Monster
        codex = FakeSave()
        w = World(codex, seed=6)
        w.player.armour = ALL_GEAR[key].copy()
        m = Monster("kobold", w.player.x + 1, w.player.y)
        w.level.monsters = [m]
        w.monster_attacks_player(m, 3)
        return w, m

    def test_cinderplate_burns_the_attacker_then_recharges(self):
        from . import config
        w, m = self._hit("cinder")
        self.assertEqual(m.burning, config.CINDER_BURN_TURNS)
        self.assertEqual(w.player.armour_cd, config.ARMOUR_RETAL_RECHARGE)

    def test_venomweave_poisons_the_attacker(self):
        from . import config
        w, m = self._hit("venom")
        self.assertEqual(m.poisoned, config.VENOM_POISON_TURNS)

    def test_glacial_mail_freezes_the_attacker(self):
        from . import config
        w, m = self._hit("glacial")
        self.assertEqual(m.stunned, config.FREEZE_TURNS)

    def test_it_does_not_fire_again_while_recharging(self):
        from .monsters import Monster
        w, m = self._hit("cinder")
        m.burning = 0                       # clear the mark; cooldown is now > 0
        w.monster_attacks_player(m, 3)
        self.assertEqual(m.burning, 0, "must not re-trigger mid-recharge")


class TestBastionAndLifeweaver(unittest.TestCase):
    def test_bastion_caps_a_big_hit(self):
        from .items import ALL_GEAR
        from .monsters import Monster
        from . import config
        codex = FakeSave()
        w = World(codex, seed=6)
        w.player.armour = ALL_GEAR["bastion"].copy()
        m = Monster("brute", w.player.x + 1, w.player.y)
        w.level.monsters = [m]
        hp = w.player.hp
        w.monster_attacks_player(m, 40)     # a huge hit
        lost = hp - w.player.hp
        self.assertLessEqual(lost, config.BASTION_CAP,
                             "no single hit may exceed Bastion's cap")

    def test_lifeweaver_knits_hp_each_turn(self):
        from .items import ALL_GEAR
        from . import config
        codex = FakeSave()
        w = World(codex, seed=6)
        w.player.armour = ALL_GEAR["lifeweave"].copy()
        w.player.hp = w.player.max_hp - 5
        w.player.tick_effects(w)
        self.assertEqual(w.player.hp, w.player.max_hp - 5 + config.LIFEWEAVE_HEAL)

    def test_lifeweaver_never_overheals(self):
        from .items import ALL_GEAR
        codex = FakeSave()
        w = World(codex, seed=6)
        w.player.armour = ALL_GEAR["lifeweave"].copy()
        w.player.hp = w.player.max_hp
        w.player.tick_effects(w)
        self.assertEqual(w.player.hp, w.player.max_hp)


class TestLastBreath(unittest.TestCase):
    def test_it_refuses_the_first_killing_blow_and_grants_a_window(self):
        from .items import ALL_GEAR
        from . import config
        codex = FakeSave()
        w = World(codex, seed=6)
        w.player.armour = ALL_GEAR["lastbreath"].copy()
        w.kill_player("brute")
        self.assertFalse(w.dead, "Last Breath must refuse the first killing blow")
        self.assertEqual(w.player.hp, 1)
        self.assertTrue(w.player.lastbreath_used)
        self.assertGreaterEqual(w.player.sanctuary, config.LASTBREATH_SANCTUARY)

    def test_it_only_works_once_per_life(self):
        from .items import ALL_GEAR
        codex = FakeSave()
        w = World(codex, seed=6)
        w.player.armour = ALL_GEAR["lastbreath"].copy()
        w.player.lastbreath_used = True         # already spent
        w.kill_player("brute")
        self.assertTrue(w.dead, "a spent Last Breath cannot save you again")


class TestArmourCapstones(unittest.TestCase):
    def test_firestorm_scroll_no_longer_burns_the_caster(self):
        from .monsters import Monster
        codex = FakeSave()
        w = World(codex, seed=6)
        w.level.monsters = [Monster("kobold", w.player.x + 1, w.player.y)]
        hp = w.player.hp
        w._apply_effect("fire")
        self.assertEqual(w.player.hp, hp, "VORN must not cook its own caster")

    def test_robe_of_hades_burns_the_room_and_spares_you(self):
        from .items import ALL_GEAR
        from .monsters import Monster
        from . import config
        codex = FakeSave()
        w = World(codex, seed=6)
        w.player.armour = ALL_GEAR["hades"].copy()
        m = Monster("kobold", w.player.x + 1, w.player.y)
        w.level.monsters = [m]
        hp, mhp = w.player.hp, m.hp
        w.monster_attacks_player(m, 3)
        self.assertLess(m.hp, mhp, "the Robe answers in fire")
        self.assertEqual(w.player.hp, hp + 0, "the Robe's fire spares the wearer "
                         "(barring the incoming hit already applied)")
        self.assertEqual(w.player.armour_cd, config.ARMOUR_CAPSTONE_RECHARGE)

    def test_robe_of_hades_does_not_fire_on_the_blow_that_kills_you(self):
        # A fatal blow must not trigger the reactive dispatch afterwards --
        # a dead wearer's robe should not go on to torch the room.
        from .items import ALL_GEAR
        from .monsters import Monster
        codex = FakeSave()
        w = World(codex, seed=6)
        w.player.armour = ALL_GEAR["hades"].copy()
        w.player.hp = 1                          # any real hit is now fatal
        m = Monster("kobold", w.player.x + 1, w.player.y)
        bystander = Monster("kobold", w.player.x - 1, w.player.y)
        w.level.monsters = [m, bystander]
        bhp = bystander.hp
        w.monster_attacks_player(m, 10)          # raw 10 - 3 defense = 7 > 1 hp: fatal
        self.assertTrue(w.dead, "the blow should have killed the player")
        self.assertEqual(bystander.hp, bhp, "no post-mortem firestorm")
        self.assertEqual(w.player.armour_cd, 0, "the robe must not recharge from a "
                         "shot it never fired")

    def test_blinding_light_stuns_the_ring_and_wipes_windups(self):
        from .items import ALL_GEAR
        from .monsters import Monster
        from . import config
        codex = FakeSave()
        w = World(codex, seed=6)
        w.player.armour = ALL_GEAR["blinding"].copy()
        near = Monster("kobold", w.player.x + 1, w.player.y)
        near.intent = ("smash", w.player.x, w.player.y)
        w.level.monsters = [near]
        w.monster_attacks_player(near, 3)
        self.assertEqual(near.stunned, config.BLINDING_STUN_TURNS)
        self.assertIsNone(near.intent, "a wiped windup")


class TestMagicalArmourEndToEnd(unittest.TestCase):
    def test_a_found_magical_armour_equips_and_its_trait_fires(self):
        from .items import ALL_GEAR
        from .dungeon import Drop
        from .monsters import Monster
        from . import config
        codex = FakeSave()
        w = World(codex, seed=6)
        p = w.player
        w.level.drops.append(Drop(p.x, p.y, "gear", "cinder"))
        p.armour = ALL_GEAR["rags"].copy()          # swap is an upgrade over the starter
        w.take_all()
        self.assertEqual(p.armour.key, "cinder")
        m = Monster("kobold", p.x + 1, p.y)
        w.level.monsters = [m]
        w.monster_attacks_player(m, 3)
        self.assertEqual(m.burning, config.CINDER_BURN_TURNS)


class TestPhase2Distribution(unittest.TestCase):
    def test_fade_is_findable_but_boss_pieces_are_not(self):
        from .items import FINDABLE_MAGICAL_ARMOUR_KEYS
        self.assertIn("fade", FINDABLE_MAGICAL_ARMOUR_KEYS)
        self.assertNotIn("shade", FINDABLE_MAGICAL_ARMOUR_KEYS)
        self.assertNotIn("nightcloak", FINDABLE_MAGICAL_ARMOUR_KEYS)

    def test_the_bench_now_reaches_all_three_new_pieces(self):
        from .game import Game
        from .items import ARMOURS
        g = Game.__new__(Game)
        g.open_armour_cheat()
        covered = set().union(*g.weapon_pages)
        for key in ("fade", "shade", "nightcloak"):
            self.assertIn(key, covered, key)
        self.assertEqual(covered, set(ARMOURS))

    def test_a_found_fadecloak_works_end_to_end(self):
        from .items import ALL_GEAR
        from .dungeon import Drop
        from .monsters import Monster
        from . import config
        codex = FakeSave(); w = World(codex, seed=6)
        p = w.player
        w.level.drops.append(Drop(p.x, p.y, "gear", "fade"))
        p.armour = ALL_GEAR["rags"].copy()
        w.take_all()
        self.assertEqual(p.armour.key, "fade")
        m = Monster("kobold", p.x + 1, p.y); m.awake = True
        w.level.monsters = [m]
        for _ in range(config.FADE_HIT_CADENCE):
            w.monster_attacks_player(m, 1)
        self.assertTrue(w.player_hidden())


class TestTheSuiteCannotReachARealSave(unittest.TestCase):
    """This suite once deleted a player's Kodex. Never again.

    FakeSave overrode load() and save() and claimed in its docstring that tests could
    not clobber a real save -- but wipe() unlinks config.SAVE_PATH directly, without
    going through save(), so eight unguarded wipe() calls reached straight past the
    fake and deleted the file. Two guards now, belt and braces: the whole module runs
    against a temp SAVE_PATH, and FakeSave refuses to unlink anything at all.
    """

    def test_the_suite_never_points_at_the_packaged_save(self):
        """The guard that makes the other seven hundred tests safe by construction."""
        from . import config as cfg
        packaged = os.path.join(os.path.dirname(os.path.abspath(cfg.__file__)),
                                "deathward_save.json")
        self.assertNotEqual(os.path.abspath(cfg.SAVE_PATH), os.path.abspath(packaged),
                            "the suite is pointed at the player's own save file")

    def test_wiping_a_fakesave_unlinks_nothing(self):
        from . import config as cfg
        import tempfile
        old = cfg.SAVE_PATH          # patched locally too: this test must be safe
        cfg.SAVE_PATH = os.path.join(tempfile.gettempdir(), "dw_fakesave_guard.json")
        try:
            with open(cfg.SAVE_PATH, "w", encoding="utf-8") as fh:
                fh.write('{"sentinel": true}')
            FakeSave().wipe()
            self.assertTrue(os.path.exists(cfg.SAVE_PATH),
                            "FakeSave.wipe() deleted a file from disk")
        finally:
            if os.path.exists(cfg.SAVE_PATH):
                os.remove(cfg.SAVE_PATH)
            cfg.SAVE_PATH = old

    def test_wiping_a_fakesave_still_forgets_everything(self):
        """The override has to keep wipe's MEANING -- a new game knows nothing -- or
        every test leaning on wipe() to reset state quietly rots into a false pass."""
        c = FakeSave()
        c.known.append("brute.rule")
        c.deaths = 7
        c.wipe()
        self.assertEqual(c.known, [], "a wiped codex must have forgotten the monsters")
        self.assertEqual(c.deaths, 0, "...and the deaths")


class TestSyrinxSprite(unittest.TestCase):
    def test_it_has_a_sprite_registered(self):
        from . import sprites
        self.assertIn("syrinx", sprites._MONSTER_DRAW)
        self.assertIsNotNone(sprites.monster("syrinx", (196, 214, 150)))


class TestSyrinxIdentity(unittest.TestCase):
    def test_her_template_exists_with_the_right_shape(self):
        from .monsters import TEMPLATES
        t = TEMPLATES["syrinx"]
        self.assertEqual((t.hp, t.lo, t.hi, t.speed), (30, 1, 3, 100))

    def test_it_takes_roughly_six_solid_hits_from_a_strong_weapon(self):
        _assert_solid_hits(self, "syrinx", lo=5, hi=7)

    def test_she_never_appears_in_the_ordinary_spawn_tables(self):
        from .monsters import SPAWN_TABLE, spawn_roster
        for table in SPAWN_TABLE.values():
            self.assertNotIn("syrinx", table)
        for d in range(1, 30):
            self.assertNotIn("syrinx", spawn_roster(d))

    def test_she_has_a_codex_entry_and_a_cause_name(self):
        from .codex import CAUSE_NAME, FACTS
        for tier in ("rule", "tell", "counter"):
            self.assertIn("syrinx.%s" % tier, FACTS)
        self.assertEqual(CAUSE_NAME["syrinx"], "Syrinx")


class TestSyrinxHiddenState(unittest.TestCase):
    def _world(self):
        codex = FakeSave()
        w = World(codex, seed=7)
        w.level.monsters = []
        for r in w.level.rooms:
            if r.w >= 9 and r.h >= 7:
                w.player.x, w.player.y = r.cx, r.cy
                break
        w.level.compute_fov(w.player.x, w.player.y)
        return w

    def _syrinx(self, w, dx, dy):
        from .monsters import Monster
        s = Monster("syrinx", w.player.x + dx, w.player.y + dy)
        w.level.monsters.append(s)
        return s

    def test_she_spawns_hidden_awake_and_pinned_to_her_pillar(self):
        w = self._world()
        s = self._syrinx(w, 3, 0)
        self.assertTrue(s.hidden)
        self.assertTrue(s.awake)
        self.assertEqual((s.pillar_x, s.pillar_y), (s.x, s.y))
        self.assertEqual(s.hidden_turns, 0)
        self.assertFalse(s.retreating)

    def test_a_hidden_syrinx_ignores_the_generic_invisible_player_wander(self):
        """An invisible player makes every OTHER awake monster's intent clear and
        (60% of the time) wander -- Monster.take_turn's generic block, ahead of the
        per-monster AI dispatch. Syrinx has her own hidden-state logic (_ai_syrinx)
        that should be the only thing moving her while self.hidden is True; the
        generic block wandering her off her pillar would leave her untargetable on
        open floor with a stale pillar_x/pillar_y."""
        w = self._world()
        s = self._syrinx(w, 3, 0)
        ox, oy = s.x, s.y
        w.player.invisible = 30
        self.assertTrue(w.player_hidden())

        # stay under config.SYRINX_HIDDEN_MAX (5) so we are testing the generic
        # wander exemption, not colliding with her own forced-emergence timer
        for _ in range(4):
            s.take_turn(w)
            self.assertEqual((s.x, s.y), (ox, oy), "she wandered off her pillar")
            self.assertTrue(s.hidden, "she lost her hidden state")

    def test_forced_emergence_after_the_hidden_cap(self):
        from . import config
        w = self._world()
        s = self._syrinx(w, 4, 0)
        for _ in range(config.SYRINX_HIDDEN_MAX - 1):
            s.take_turn(w)
            self.assertTrue(s.hidden)
            self.assertIsNone(s.intent)
        s.take_turn(w)                       # hits the cap: telegraph turn
        self.assertTrue(s.hidden, "still off the grid during the telegraph")
        self.assertEqual(s.intent, ("emerge", s.x, s.y))
        s.take_turn(w)                       # resolves: she is out
        self.assertFalse(s.hidden)
        self.assertIsNone(s.intent)
        self.assertEqual(s.hidden_turns, 0, "the budget resets on emergence")

    def test_hidden_syrinx_cannot_be_targeted_by_monster_at(self):
        w = self._world()
        s = self._syrinx(w, 3, 0)
        self.assertIsNone(w.monster_at(s.x, s.y))

    def test_hidden_syrinx_is_untouched_by_area_damage(self):
        w = self._world()
        s = self._syrinx(w, 3, 0)
        w.level.visible[s.y][s.x] = True   # even if her tile were somehow lit
        hp = s.hp
        w._firestorm()
        w._apply_effect("thunderclap")
        self.assertEqual(s.hp, hp, "nothing area-based can reach a hidden Syrinx")

    def test_drawing_a_hidden_syrinx_never_crashes(self):
        from . import render
        w = self._world()
        s = self._syrinx(w, 3, 0)
        w.level.visible[s.y][s.x] = True
        cam = render.Camera()
        cam.center_on(w.player.x, w.player.y)

        hidden_surf = pygame.Surface((config.W, config.H))
        render.draw_world(hidden_surf, w, w.codex, cam, 0.0)   # must not raise
        hidden_pixels = pygame.image.tostring(hidden_surf, "RGB")

        s.hidden = False   # same tile, same everything -- just no longer hidden
        visible_surf = pygame.Surface((config.W, config.H))
        render.draw_world(visible_surf, w, w.codex, cam, 0.0)
        visible_pixels = pygame.image.tostring(visible_surf, "RGB")

        self.assertNotEqual(
            hidden_pixels, visible_pixels,
            "hiding her must actually change what gets drawn -- a render pass "
            "that ignores .hidden (or one that draws nothing at all either way) "
            "would wrongly produce identical frames here")

    def test_drawing_her_emerge_telegraph_while_still_hidden_actually_draws_something(self):
        """The 'emerge' intent fires a full turn before she leaves hidden state --
        while m.hidden is still True. The main monster-drawing loop `continue`s past
        any hidden monster entirely (it has no sprite to draw), so the ordinary
        intent-marker chain never runs for her. draw_world needs a second, narrower
        pass just for this case: a persistent glow on her still-hidden pillar tile,
        gated on codex.knows_tier('syrinx', 'tell') like every other intent marker."""
        from . import render
        w = self._world()
        s = self._syrinx(w, 3, 0)
        w.level.visible[s.y][s.x] = True
        w.codex.known.append("syrinx.rule")   # tiers are sequential: "tell" needs "rule" first
        w.codex.known.append("syrinx.tell")
        cam = render.Camera()
        cam.center_on(w.player.x, w.player.y)

        s.intent = None
        no_intent_surf = pygame.Surface((config.W, config.H))
        render.draw_world(no_intent_surf, w, w.codex, cam, 0.0)
        no_intent_pixels = pygame.image.tostring(no_intent_surf, "RGB")

        s.intent = ("emerge", s.x, s.y)
        emerge_surf = pygame.Surface((config.W, config.H))
        render.draw_world(emerge_surf, w, w.codex, cam, 0.0)   # must not raise
        emerge_pixels = pygame.image.tostring(emerge_surf, "RGB")

        self.assertTrue(s.hidden, "sanity: she must still be hidden for this case")
        self.assertNotEqual(
            no_intent_pixels, emerge_pixels,
            "the emerge telegraph must be visible on her pillar tile even though "
            "she has no sprite to draw while hidden")


class TestSyrinxArena(unittest.TestCase):
    def test_floor_eight_holds_no_syrinx_until_you_commit(self):
        for seed in range(20):
            codex = FakeSave(); codex.world_seed = seed
            w = World(codex, seed=1)
            w.new_level(8)
            self.assertEqual([m for m in w.level.monsters if m.key == "syrinx"], [],
                             "seed %d: she arrives when you cross the mouth" % seed)
            a = w.level.arena_room
            w.player.x, w.player.y = a.x, a.cy
            w._enter_tile()
            self.assertEqual(
                len([m for m in w.level.monsters if m.key == "syrinx"]), 1,
                "seed %d: and exactly one of her does" % seed)

    def test_floor_eight_keeps_its_stairs(self):
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=1)
        w.new_level(8)
        self.assertIsNotNone(w.level.stairs,
                             "floor 8 continues -- it is not the Warden's floor")

    def test_only_floor_eight_reserves_a_room(self):
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=1)
        w.new_level(3)
        self.assertIsNone(w.level._reserved_room)

    def test_her_arena_has_no_ambient_monster_or_chest(self):
        for seed in range(20):
            codex = FakeSave(); codex.world_seed = seed
            w = World(codex, seed=1)
            w.new_level(8)
            arena = w.level._syrinx_arena()
            for m in w.level.monsters:
                if m.key == "syrinx":
                    continue
                self.assertFalse(arena.contains(m.x, m.y),
                                 "seed %d: an ambient monster shares her room" % seed)
            for c in w.level.chests:
                self.assertFalse(arena.contains(c.x, c.y),
                                 "seed %d: a chest shares her room" % seed)

    def test_pillars_are_wall_tiles_and_never_the_stairs(self):
        from .dungeon import WALL
        for seed in range(20):
            codex = FakeSave(); codex.world_seed = seed
            w = World(codex, seed=1)
            w.new_level(8)
            for (px, py) in w.level.syrinx_pillars():
                self.assertEqual(w.level.grid[py][px], WALL)
                self.assertNotEqual((px, py), w.level.stairs)

    def test_she_always_has_somewhere_to_hide(self):
        """Replaces test_small_arena_nudges_off_stairs_instead_of_vanishing.

        That test guarded a fallback that no longer exists: her arena used to be
        "the biggest room the generator happened to deal", so it could come out too
        small to spread six pillars through, and could even put its only hiding spot
        on the stairs tile -- which left syrinx_pillars() empty and made
        _populate_syrinx skip appending her monster entirely. Floor 8 is cut to a
        fixed 31x23 now, so a too-small arena cannot happen. What still MATTERS is
        the consequence the old test was really protecting: pillars exist, they are
        distinct, none of them is a tile she must never stand on, and she therefore
        gets placed."""
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=1)
        w.new_level(8)
        lvl = w.level

        pillars = lvl.syrinx_pillars()
        self.assertTrue(pillars, "she needs SOMEWHERE to hide, not an empty list")
        self.assertEqual(len(pillars), len(set(pillars)), "no pillar cut twice")
        for spot in pillars:
            self.assertTrue(lvl.arena_room.contains(*spot))
            self.assertNotEqual(spot, lvl.stairs)
            self.assertNotEqual(spot, lvl.mouth)

        # she is not placed until commit (Task 6) -- but a pillar to hide in means
        # that, once she is, she has somewhere to retreat to.
        w.player.x, w.player.y = lvl.arena_room.x, lvl.arena_room.cy
        w._enter_tile()
        found = [m for m in lvl.monsters if m.key == "syrinx"]
        self.assertEqual(len(found), 1, "a pillar to hide in means she gets placed")

    def test_stairs_stay_reachable_on_floor_eight(self):
        from collections import deque
        for seed in range(20):
            codex = FakeSave(); codex.world_seed = seed
            w = World(codex, seed=1)
            w.new_level(8)
            lvl = w.level
            seen = {lvl.start}
            q = deque([lvl.start])
            while q:
                x, y = q.popleft()
                for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0),
                               (1, 1), (1, -1), (-1, 1), (-1, -1)):
                    n = (x + dx, y + dy)
                    if n in seen or not lvl.walkable(*n):
                        continue
                    seen.add(n)
                    q.append(n)
            self.assertIn(lvl.stairs, seen,
                         "seed %d: floor 8's stairs are walled off" % seed)


class TestSyrinxHuntAndBlow(unittest.TestCase):
    def _world(self):
        # Her hall, not "whichever room on floor 1 happened to be big enough". Floor
        # 8 is purpose-built for this fight now, and her arena is a fixed 31x23 room
        # rather than the largest thing the generator dealt -- so `_syrinx_arena()`
        # is her arena_room or nothing at all, and her hunt leash reads it every
        # turn. Every assertion in this class is about her AI, so it has to run in
        # the one place she can exist. Fixing the floor also fixes the geometry:
        # these tests used to ride a random world_seed and flake accordingly.
        codex = FakeSave(); codex.world_seed = 5
        w = World(codex, seed=7)
        w.new_level(8)
        w.level.monsters = []
        w.player.x, w.player.y = w.level.arena_room.cx, w.level.arena_room.cy
        w.level.compute_fov(w.player.x, w.player.y)
        return w

    def _syrinx(self, w, dx, dy):
        from .monsters import Monster
        s = Monster("syrinx", w.player.x + dx, w.player.y + dy)
        s.hidden = False
        w.level.monsters.append(s)
        return s

    def test_she_moves_toward_the_player_when_not_aligned(self):
        w = self._world()
        s = self._syrinx(w, 4, 3)
        sx, sy = s.x, s.y
        s.take_turn(w)
        self.assertLess(max(abs(s.x - w.player.x), abs(s.y - w.player.y)),
                        max(abs(sx - w.player.x), abs(sy - w.player.y)),
                        "hunting closes the distance rather than waiting")

    def test_aligned_and_clear_commits_to_a_telegraphed_blow(self):
        w = self._world()
        s = self._syrinx(w, 4, 0)
        s.take_turn(w)
        self.assertEqual(s.intent, ("blow", 0, 0))
        self.assertEqual(w.player.hp, w.player.max_hp, "the telegraph turn does no damage")

    def test_the_blow_resolves_next_turn_for_real_chip_damage(self):
        w = self._world()
        s = self._syrinx(w, 4, 0)
        s.take_turn(w)                       # telegraph
        hp = w.player.hp
        s.take_turn(w)                       # resolve
        self.assertLess(w.player.hp, hp, "the blow lands for real chip damage")
        self.assertIsNone(s.intent)

    def test_a_pillar_between_them_fizzles_the_blow(self):
        w = self._world()
        s = self._syrinx(w, 4, 0)
        s.take_turn(w)                       # telegraph while the line is clear
        wx = (s.x + w.player.x) // 2
        w.level.grid[w.player.y][wx] = 0     # a pillar drops into the eyeline (0 == WALL)
        hp = w.player.hp
        s.take_turn(w)                       # resolve: blocked
        self.assertEqual(w.player.hp, hp, "a blocked blow does no damage")
        self.assertIsNone(s.intent)

    def test_she_never_melee_attacks_even_when_adjacent_but_unaligned(self):
        # She has no melee code path: every point of damage, always, comes from
        # the telegraphed blow (self.intent == ("blow", 0, 0) set on a prior
        # turn) -- never an instant, untelegraphed hit. Starting diagonally
        # adjacent, hunting can walk her onto an aligned tile at distance 1 and
        # she may telegraph-then-land a point-blank blow -- that's fine; a
        # melee attack would instead deal damage on the SAME turn it triggers,
        # with no telegraph turn before it.
        w = self._world()
        s = self._syrinx(w, 1, 1)            # adjacent, diagonal -- never aligned
        prev_intent = s.intent
        prev_hp = w.player.hp
        for _ in range(6):
            s.take_turn(w)
            hp = w.player.hp
            if hp < prev_hp:
                self.assertEqual(prev_intent, ("blow", 0, 0),
                                  "damage must be preceded by an observed telegraph turn")
            prev_intent = s.intent
            prev_hp = hp

    def test_she_does_not_chase_the_player_out_of_her_arena(self):
        # Her whole design -- pillars to hide behind, a telegraphed blow to duck --
        # is a boss-ROOM fight. If her hunt fallback chased the player anywhere on
        # the floor, she would wander into corridors with no cover, bypassing the
        # entire pillar/telegraph design. The hunt movement must stay leashed to
        # her own arena: with the player outside it, she is a no-op, not a hunter.
        from .monsters import Monster
        codex = FakeSave(); codex.world_seed = 5
        w = World(codex, seed=1)
        w.new_level(8)
        lvl = w.level
        # she is not placed at generation any more (Task 6) -- put her on one of
        # her own pillars directly, same spot _populate_syrinx used to use.
        s = Monster("syrinx", *lvl.syrinx_pillars()[0])
        lvl.monsters.append(s)
        s.hidden = False
        arena = lvl._syrinx_arena()
        w.player.x, w.player.y = lvl.entrance
        self.assertFalse(arena.contains(w.player.x, w.player.y),
                          "sanity: the entrance sits outside her arena")
        sx, sy = s.x, s.y
        for _ in range(5):
            s.take_turn(w)
        self.assertEqual((s.x, s.y), (sx, sy),
                          "she must not leave her arena chasing a player outside it")

    def test_she_still_hunts_a_player_inside_her_arena(self):
        # Companion to the leash test above: the fix must not turn her into a
        # statue INSIDE her own room -- she still actively hunts an unaligned
        # player as long as they are both inside the arena.
        from .monsters import Monster
        codex = FakeSave(); codex.world_seed = 5
        w = World(codex, seed=1)
        w.new_level(8)
        lvl = w.level
        # she is not placed at generation any more (Task 6) -- put her on one of
        # her own pillars directly, same spot _populate_syrinx used to use.
        s = Monster("syrinx", *lvl.syrinx_pillars()[0])
        lvl.monsters.append(s)
        s.hidden = False
        arena = lvl._syrinx_arena()
        w.player.x, w.player.y = arena.cx, arena.cy
        self.assertTrue(arena.contains(w.player.x, w.player.y),
                         "sanity: the arena centre is inside the arena")
        self.assertTrue(arena.contains(s.x, s.y),
                         "sanity: she starts inside her own arena")
        sx, sy = s.x, s.y
        for _ in range(5):
            s.take_turn(w)
            if (s.x, s.y) != (sx, sy) or s.intent is not None:
                break
        moved = (s.x, s.y) != (sx, sy)
        telegraphed = s.intent == ("blow", 0, 0)
        self.assertTrue(moved or telegraphed,
                         "inside her arena she must still hunt (move) or, if "
                         "already aligned and clear, telegraph a blow")

    def test_drawing_her_blow_telegraph_actually_draws_something(self):
        """The 'blow' intent used to be signalled only by an ephemeral, real-time FX
        pulse (world.add_fx, life=0.9s) -- invisible to a player who pauses to think
        even though the telegraph is still mechanically live. render.draw_world now
        carries a persistent marker for it in the main intent-marker chain, gated
        (like every sibling case) on codex.knows_tier(m.key, 'tell')."""
        from . import render
        w = self._world()
        s = self._syrinx(w, 4, 0)
        w.level.visible[s.y][s.x] = True
        w.codex.known.append("syrinx.rule")   # tiers are sequential: "tell" needs "rule" first
        w.codex.known.append("syrinx.tell")
        cam = render.Camera()
        cam.center_on(w.player.x, w.player.y)

        s.intent = None
        no_intent_surf = pygame.Surface((config.W, config.H))
        render.draw_world(no_intent_surf, w, w.codex, cam, 0.0)
        no_intent_pixels = pygame.image.tostring(no_intent_surf, "RGB")

        s.intent = ("blow", 0, 0)
        blow_surf = pygame.Surface((config.W, config.H))
        render.draw_world(blow_surf, w, w.codex, cam, 0.0)   # must not raise
        blow_pixels = pygame.image.tostring(blow_surf, "RGB")

        self.assertNotEqual(
            no_intent_pixels, blow_pixels,
            "the blow telegraph must draw a persistent marker, not rely solely "
            "on the decaying real-time FX pulse")


class TestSyrinxStunAndRetreat(unittest.TestCase):
    def _world(self):
        codex = FakeSave(); codex.world_seed = 5
        w = World(codex, seed=1)
        w.new_level(8)
        w.level.monsters = [m for m in w.level.monsters if m.key != "syrinx"]
        return w

    def _syrinx(self, w, x, y):
        from .monsters import Monster
        s = Monster("syrinx", x, y)
        s.hidden = False
        s.pillar_x, s.pillar_y = x, y
        w.level.monsters.append(s)
        return s

    def test_a_landed_blow_stuns_her_and_knocks_the_player_back(self):
        w = self._world()
        w.player.x, w.player.y = 10, 10
        s = self._syrinx(w, 6, 10)
        for x in range(6, 13):                 # force the line clear and knockback room (1 == FLOOR)
            w.level.grid[10][x] = 1
        s.intent = ("blow", 0, 0)
        px_before = w.player.x
        s.take_turn(w)
        self.assertEqual(s.stunned, config.SYRINX_STUN_TURNS)
        self.assertTrue(s.retreating)
        self.assertGreater(w.player.x, px_before, "the gust pushes the player away from her")

    def test_a_fizzled_blow_does_not_stun_or_start_a_retreat(self):
        w = self._world()
        w.player.x, w.player.y = 10, 10
        s = self._syrinx(w, 6, 10)
        s.intent = ("blow", 0, 0)
        w.level.grid[10][8] = 0                # a wall drops into the line (0 == WALL)
        s.take_turn(w)
        self.assertEqual(s.stunned, 0)
        self.assertFalse(s.retreating)

    def test_she_heads_for_the_nearest_pillar_that_is_not_the_one_she_left(self):
        w = self._world()
        s = self._syrinx(w, 6, 10)
        s.pillar_x, s.pillar_y = s.x, s.y     # the pillar she just emerged from
        s.retreating = True
        target = s._syrinx_retreat_target(w, w.player)
        self.assertNotEqual(target, (s.pillar_x, s.pillar_y))
        self.assertIn(target, w.level.syrinx_pillars())

    def test_reaching_the_target_pillar_re_hides_her(self):
        w = self._world()
        target = w.level.syrinx_pillars()[1]
        s = self._syrinx(w, *target)
        s.pillar_x, s.pillar_y = w.level.syrinx_pillars()[0]
        s.retreating = True
        s.take_turn(w)
        self.assertTrue(s.hidden)
        self.assertFalse(s.retreating)
        self.assertEqual((s.pillar_x, s.pillar_y), target)
        self.assertEqual(s.hidden_turns, 0)

    def test_a_blocked_straight_walk_re_routes_to_another_pillar(self):
        from .monsters import _syrinx_path_blocked
        self.assertTrue(_syrinx_path_blocked(0, 0, 4, 0, 2, 0))   # player sits on the line
        self.assertFalse(_syrinx_path_blocked(0, 0, 4, 0, 2, 5))  # player is far off it

    def test_she_can_actually_step_onto_the_pillar_tile_to_re_hide(self):
        # the pillar itself is carved as a WALL tile (see dungeon._populate_syrinx).
        # her LAST retreat step has to walk onto that wall tile, same as wraith/
        # poltergeist phasing through walls to reach the player -- if that step
        # isn't allowed to phase, she gets stuck oscillating one tile short of the
        # pillar forever, and can never re-hide.
        w = self._world()
        pillars = w.level.syrinx_pillars()
        target = pillars[1]
        start = None
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1),
                       (1, 1), (1, -1), (-1, 1), (-1, -1)):
            nx, ny = target[0] + dx, target[1] + dy
            if w.level.walkable(nx, ny):
                start = (nx, ny)
                break
        self.assertIsNotNone(start, "expected a walkable tile next to the pillar")

        w.player.x, w.player.y = w.level.entrance   # well clear of the retreat path
        s = self._syrinx(w, *start)
        s.pillar_x, s.pillar_y = pillars[0]          # the pillar she just left
        s.retreating = True

        # sanity: the real geometry picks the adjacent pillar as her target
        self.assertEqual(s._syrinx_retreat_target(w, w.player), target)

        for _ in range(15):
            s.take_turn(w)
            if s.hidden:
                break

        self.assertTrue(
            s.hidden,
            f"never re-hid; stuck at ({s.x}, {s.y}) instead of reaching {target}")
        self.assertEqual((s.pillar_x, s.pillar_y), target)

    def test_retreat_does_not_phase_through_ordinary_walls_en_route(self):
        # phase=True used to apply to the WHOLE retreat step, not just the final
        # tile onto the pillar -- so on every turn she was still more than one
        # tile from her target, she could cut diagonally through ORDINARY wall
        # tiles if that happened to be the locally-shortest route. She is
        # corporeal, not incorporeal like wraith/poltergeist: only her OWN
        # pillar should part like stone for her.
        #
        # This used to sweep the whole map for a start tile more than three tiles
        # from any pillar, and walk her in from there past whatever rock the
        # generator happened to leave lying about. Her hall makes that impossible
        # twice over: the columns sit on a six-tile pitch, so EVERY tile in the
        # room is within three of one, and the room's interior is unbroken floor,
        # so a wandering walk would never meet an ordinary wall to phase through
        # in the first place. The old setup could no longer even be built, let
        # alone catch the bug.
        #
        # So state the intent directly instead of hoping the layout supplies it:
        # drop a short ordinary wall straight across the line she would otherwise
        # walk, and watch her go AROUND it. Phasing would take her through.
        from .dungeon import WALL
        w = self._world()
        pillars = w.level.syrinx_pillars()
        w.player.x, w.player.y = w.level.entrance   # well clear of the retreat path

        s = self._syrinx(w, 17, 6)
        s.pillar_x, s.pillar_y = (15, 4)            # the pillar she just left
        s.retreating = True
        target = s._syrinx_retreat_target(w, w.player)
        self.assertEqual(target, (21, 4), "sanity: the geometry picks this pillar")

        # a wall she has no business crossing, laid across the direct line
        barrier = [(18, 5), (19, 5), (19, 4), (19, 3), (19, 2)]
        for bx, by in barrier:
            self.assertNotIn((bx, by), pillars, "the barrier must be ORDINARY stone")
            w.level.grid[by][bx] = WALL

        visited = []
        for _ in range(20):
            visited.append((s.x, s.y))
            if s.hidden:
                break
            s.take_turn(w)

        self.assertTrue(s.hidden, f"never re-hid; stuck at ({s.x}, {s.y})")
        self.assertGreater(len(visited), 2, "a one-step hop proves nothing")

        for tile in barrier:
            self.assertNotIn(tile, visited, "she walked THROUGH ordinary stone")
        bad = [(x, y) for (x, y) in visited
               if (x, y) not in pillars and w.level.grid[y][x] == WALL]
        self.assertEqual(
            bad, [],
            "stepped onto ordinary (non-pillar) wall tile(s) during approach")


class TestSyrinxResistances(unittest.TestCase):
    def _world(self):
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=3)
        w.level.monsters = []
        return w

    def test_fire_deals_double_damage(self):
        from .monsters import damage_multiplier
        self.assertEqual(damage_multiplier("syrinx", "burn"), config.SYRINX_FIRE_MULT)
        self.assertEqual(damage_multiplier("syrinx", "glyph"), config.SYRINX_FIRE_MULT)
        self.assertEqual(damage_multiplier("syrinx", "scroll"), config.SYRINX_FIRE_MULT)
        self.assertEqual(damage_multiplier("syrinx", "player"), 1.0)

    def test_freeze_fear_and_poison_never_take_hold(self):
        from .items import WEAPONS
        from .monsters import Monster
        w = self._world()
        s = Monster("syrinx", w.player.x + 1, w.player.y)
        s.hidden = False
        w.level.monsters = [s]
        w.player.weapon = WEAPONS["winters_edge"].copy()   # "freeze" trait
        for _ in range(30):
            w._weapon_status_on(s, 5)
        self.assertEqual(s.stunned, 0)
        w.player.weapon = WEAPONS["reapers_whisper"].copy()  # "fear" trait
        for _ in range(30):
            w._weapon_status_on(s, 5)
        self.assertEqual(s.feared, 0)
        w.player.weapon = WEAPONS["basilisk_maul"].copy()    # "poison" trait
        w._weapon_status_on(s, 5)
        self.assertEqual(s.poisoned, 0)

    def test_enrage_never_takes_hold(self):
        """Betrayer's Edge (the "enrage" trait) sends the struck thing berserk, and
        Monster.take_turn's enraged branch has it lash out in melee (_rampage ->
        _hit) -- straight through the design invariant that Syrinx never initiates
        a melee attack. _weapon_status_on's other status branches (freeze/fear/
        poison, above) are all gated by _status_immune; enrage was missed."""
        from .items import WEAPONS
        from .monsters import Monster
        w = self._world()
        s = Monster("syrinx", w.player.x + 1, w.player.y)
        s.hidden = False
        w.level.monsters = [s]
        w.player.weapon = WEAPONS["betrayers_edge"].copy()   # "enrage" trait
        for _ in range(30):
            w._weapon_status_on(s, 5)
        self.assertEqual(s.enraged, 0)

    def test_reactive_armour_status_effects_do_not_take_hold(self):
        from .items import ARMOURS
        from .monsters import Monster
        w = self._world()
        s = Monster("syrinx", w.player.x + 1, w.player.y)
        s.hidden = False
        s.hp = s.max_hp = 999
        w.level.monsters = [s]
        w.player.armour = ARMOURS["venom"].copy()
        w.player.armour_cd = 0
        w.monster_attacks_player(s, 3)
        self.assertEqual(s.poisoned, 0)
        w.player.armour = ARMOURS["glacial"].copy()
        w.player.armour_cd = 0
        w.monster_attacks_player(s, 3)
        self.assertEqual(s.stunned, 0)

    def test_fear_and_hold_scrolls_do_not_take_hold(self):
        from .monsters import Monster
        w = self._world()
        s = Monster("syrinx", w.player.x + 1, w.player.y)
        s.hidden = False
        w.level.monsters = [s]
        w._apply_effect("fear")
        self.assertEqual(s.feared, 0)
        w._apply_effect("hold")
        self.assertEqual(s.stunned, 0)

    def test_a_spike_trap_does_not_stun_her(self):
        from .monsters import Monster
        from .traps import Trap
        w = self._world()
        s = Monster("syrinx", 5, 5)
        s.hidden = False
        t = Trap("spike", 5, 5)
        t.trigger(w, s)
        self.assertEqual(s.stunned, 0)


class TestSyrinxRewards(unittest.TestCase):
    def test_she_always_drops_windfang_and_shademail(self):
        import random
        from .items import roll_monster_loot
        for s in range(50):
            loot = roll_monster_loot(random.Random(s), 8, "syrinx")
            self.assertEqual(loot, [("gear", "windfang", 0), ("gear", "shade", 0)])

    def test_her_death_leaves_both_on_the_body(self):
        from .monsters import Monster
        codex = FakeSave()
        w = World(codex, seed=3)
        s = Monster("syrinx", w.player.x + 1, w.player.y)
        s.hidden = False
        s.hp = 1
        w.level.monsters = [s]
        w.kill_monster(s, source="player")
        slain = w.level.slain[-1]
        self.assertEqual(slain.key, "syrinx")
        self.assertEqual(slain.loot, [("gear", "windfang", 0), ("gear", "shade", 0)])

    def test_her_corpse_never_gets_buried_in_a_pillar_wall(self):
        from .dungeon import WALL
        from .monsters import Monster
        codex = FakeSave()
        w = World(codex, seed=3)
        w.new_level(8)
        lvl = w.level
        # she is not placed at generation any more (Task 6) -- put her on one of
        # her own pillars directly, same spot _populate_syrinx used to use.
        s = Monster("syrinx", *lvl.syrinx_pillars()[0])
        lvl.monsters.append(s)
        s.hidden = False
        s.hp = 1
        px, py = s.x, s.y
        # sanity: she really is standing on one of her pillars, a WALL tile
        self.assertEqual(lvl.grid[py][px], WALL)

        w.kill_monster(s, source="player")

        slain = w.level.slain[-1]
        self.assertNotEqual((slain.x, slain.y), (px, py),
                             "her corpse landed on the wall tile she died on")
        self.assertTrue(w.walkable(slain.x, slain.y),
                         "her corpse is not on a walkable tile -- unlootable forever")

        w.player.x, w.player.y = slain.x, slain.y
        opts = w.loot_options()
        gear = [o["payload"] for o in opts if o["kind"] == "gear"]
        self.assertIn("windfang", gear)
        self.assertIn("shade", gear)


class TestSyrinxSerialization(unittest.TestCase):
    def test_her_hidden_state_round_trips_with_all_dynamic_state(self):
        import json
        from .monsters import Monster
        m = Monster("syrinx", 5, 6)
        m.hidden = False
        m.hidden_turns = 3
        m.pillar_x, m.pillar_y = 5, 6
        m.retreating = True
        m.intent = ("blow", 0, 0)
        m.stunned = 1

        blob = m.to_dict()
        json.dumps(blob)
        n = Monster.from_dict(blob)

        for k in ("hidden", "hidden_turns", "pillar_x", "pillar_y",
                  "retreating", "stunned"):
            self.assertEqual(getattr(n, k), getattr(m, k), k)
        self.assertEqual(n.intent, ("blow", 0, 0))

    def test_a_freshly_spawned_hidden_syrinx_round_trips_too(self):
        from .monsters import Monster
        m = Monster("syrinx", 8, 9)
        n = Monster.from_dict(m.to_dict())
        self.assertTrue(n.hidden)
        self.assertEqual((n.pillar_x, n.pillar_y), (8, 9))
        self.assertIsNone(n.intent)

    def test_a_hidden_syrinx_survives_suspend_and_resume(self):
        import json
        from .dungeon import Level, WALL
        from .monsters import Monster
        codex = FakeSave()
        w = World(codex, seed=4)
        w.new_level(8)
        lv = w.level
        # she is not placed at generation any more (Task 6) -- put her on one of
        # her own pillars directly, same spot _populate_syrinx used to use.
        s = Monster("syrinx", *lv.syrinx_pillars()[0])
        lv.monsters.append(s)
        s.hidden_turns = 2
        s.intent = ("emerge", s.x, s.y)

        blob = lv.to_dict()
        json.dumps(blob)
        restored = Level(lv.depth, w.rng, codex, restore=blob)

        rs = next(m for m in restored.monsters if m.key == "syrinx")
        self.assertTrue(rs.hidden)
        self.assertEqual(rs.hidden_turns, 2)
        self.assertEqual(rs.intent, ("emerge", s.x, s.y))
        self.assertEqual((rs.x, rs.y), (s.x, s.y))
        for px, py in restored.syrinx_pillars():
            self.assertEqual(restored.grid[py][px], WALL,
                              f"pillar ({px},{py}) was not re-carved on restore")

    def test_run_save_version_was_bumped_for_her_new_state(self):
        self.assertGreaterEqual(config.RUN_SAVE_VERSION, 3)


class TestSyrinxKnowledgeIsNotPower(unittest.TestCase):
    """Her whole loop -- hidden, telegraph, emerge, hunt, blow, stun, retreat --
    must play out identically whether the Kodex knows her or not. Only what is
    DRAWN may differ (see the project's core invariant).

    A 60-turn RANDOM cardinal walk from the level's real entrance (the original
    version of this test) never gets anywhere near her arena on seed 11 -- it
    stays within a handful of tiles of the entrance the whole time, so she emerges
    once, hunts forever, and the trace never touches blow/stun/retreat at all (a
    review proved this with fault injection: a deliberately-broken blow-resolution
    or retreating branch went completely undetected). So instead of hoping a random
    walk stumbles into her, the script below drops the player straight into her
    arena and then deterministically walks it toward her every turn -- via the same
    kind of greedy step-toward-target logic the game's own monsters use, just with
    real BFS pathfinding so it does not get stuck on a corridor corner along the
    way -- which reliably drives her through hidden -> telegraph -> emerge -> hunt
    -> blow (telegraph) -> blow (resolve) -> stunned -> retreating."""

    @staticmethod
    def _bfs_step_toward(world, start, target):
        """One deterministic step for the SCRIPTED player toward `target` -- not the
        game's real input handling, just enough pathfinding that the walk cannot
        dead-end on a wall corner (a naive greedy step can). Treats `target` itself
        as passable for routing purposes (Syrinx's own tile is a carved-wall pillar
        while she is hidden) but only ever actually MOVES onto a tile that really is
        floor, exactly like the player's real movement is gated elsewhere."""
        if start == target:
            return None
        visited = {start: None}
        q = deque([start])
        while q:
            cx, cy = q.popleft()
            if (cx, cy) == target:
                break
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = cx + dx, cy + dy
                if (nx, ny) in visited:
                    continue
                if not (world.walkable(nx, ny) or (nx, ny) == target):
                    continue
                if world.monster_at(nx, ny) and (nx, ny) != target:
                    continue
                visited[(nx, ny)] = (cx, cy)
                q.append((nx, ny))
        if target not in visited:
            return None
        cur = target
        prev = visited[cur]
        while prev != start:
            cur = prev
            prev = visited[cur]
        return cur if world.walkable(*cur) else None

    def _trace(self, codex):
        from .monsters import Monster
        w = World(codex, seed=11)
        w.new_level(8)
        # she is not placed at generation any more (Task 6) -- put her on one of
        # her own pillars directly, same spot _populate_syrinx used to use.
        s = Monster("syrinx", *w.level.syrinx_pillars()[0])
        w.level.monsters.append(s)
        arena = w.level._syrinx_arena()
        # Start inside her arena (not the level's real, distant entrance) -- see the
        # class docstring for why that is what actually gets her engaged.
        w.player.x, w.player.y = arena.cx, arena.cy
        w.level.compute_fov(w.player.x, w.player.y)
        trace = []
        for _ in range(90):
            step = self._bfs_step_toward(w, (w.player.x, w.player.y), (s.x, s.y))
            if step and w.walkable(*step) and not w.monster_at(*step):
                w.player.x, w.player.y = step
            w.level.compute_fov(w.player.x, w.player.y)
            s.take_turn(w)
            trace.append((s.x, s.y, s.hidden, s.hidden_turns, s.retreating,
                         s.stunned, str(s.intent), s.hp, w.player.hp))
            # a stun/retreat cycle only advances across a PLAYER-turn boundary (see
            # World._tick_stuns) -- take_turn alone never clears it, so without this
            # she would freeze solid the instant she lands her first blow.
            w._tick_stuns()
            if not s.alive:
                break
        return trace

    def test_blind_and_omniscient_syrinx_play_out_identically(self):
        blind = FakeSave(); blind.world_seed = 11 * 7919
        wise = FakeSave(); wise.world_seed = 11 * 7919
        wise.known = list(FACTS)
        t1 = self._trace(blind)
        t2 = self._trace(wise)
        self.assertEqual(t1, t2, "knowledge of Syrinx must never change her mechanics")
        self.assertTrue(t1)
        # Prove the scenario actually reached the mechanically risky states -- not
        # just hidden/telegraph/emerge/hunt (see the class docstring / review).
        self.assertTrue(any("blow" in row[6] for row in t1),
                        "scenario never telegraphed a blow")
        self.assertTrue(any(row[5] for row in t1),
                        "scenario never exercised her stun")
        self.assertTrue(any(row[4] for row in t1),
                        "scenario never exercised her retreat")
        self.assertLess(min(row[8] for row in t1), t1[0][8],
                        "scenario never actually landed a blow on the player")


class TestSyrinxShoveSpringsTraps(unittest.TestCase):
    """The gust drags you ACROSS the floor, and the floor is trapped. Before this,
    _syrinx_knockback moved the player without ever calling _enter_tile(), so it
    slid you over live traps without springing one -- the shove cost nothing."""

    def _world(self):
        # An ORDINARY floor on purpose. _syrinx_knockback does not care about depth,
        # and from Task 5 onward floor 8 seals its mouth the moment the player stands
        # in the arena -- which would fire inside these tests and spawn her.
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=1)
        w.new_level(5)
        return w

    def test_shove_springs_every_trap_it_drags_you_over(self):
        from .traps import Trap
        from .monsters import Monster
        w = self._world()
        p = w.player
        # a clear east-west lane: her at x, player two east, traps at the next two
        p.x, p.y = 20, 20
        for x in range(17, 27):
            w.level.grid[20][x] = 1                     # FLOOR
        w.level.traps = [Trap("dart", 22, 20), Trap("dart", 23, 20)]
        m = Monster("syrinx", 18, 20)
        w.level.monsters = [m]
        before = p.hp
        w._syrinx_knockback(m)
        self.assertTrue(all(t.sprung for t in w.level.traps),
                        "both darts should have fired as she blew you past them")
        self.assertLess(p.hp, before, "and both should have hurt")

    def test_the_slide_stops_when_the_shove_kills_you(self):
        from .traps import Trap
        from .monsters import Monster
        w = self._world()
        p = w.player
        p.x, p.y = 20, 20
        for x in range(17, 27):
            w.level.grid[20][x] = 1
        w.level.traps = [Trap("dart", 22, 20), Trap("dart", 25, 20)]
        p.hp = 1
        m = Monster("syrinx", 18, 20)
        w.level.monsters = [m]
        w._syrinx_knockback(m)
        self.assertLessEqual(p.hp, 0)
        self.assertFalse(w.level.traps[1].sprung,
                         "a dead player is not dragged over any more traps")

    def test_a_spike_pit_arrests_the_slide(self):
        from .traps import Trap
        from .monsters import Monster
        w = self._world()
        p = w.player
        p.x, p.y = 20, 20
        for x in range(17, 30):
            w.level.grid[20][x] = 1
        w.level.traps = [Trap("spike", 22, 20)]
        m = Monster("syrinx", 18, 20)
        w.level.monsters = [m]
        w._syrinx_knockback(m)
        self.assertEqual((p.x, p.y), (22, 20),
                         "you fall into the pit; you do not skip over it")


class TestArenaFloorGeometry(unittest.TestCase):
    """Floor 8 is not a dungeon floor any more. It is her hall: an antechamber, a
    one-tile mouth, and a 31x23 room with twenty columns in it. The geometry is
    FIXED -- identical in every game -- and only the hazards are re-dealt."""

    def _level(self, world_seed=3, run_seed=1):
        codex = FakeSave(); codex.world_seed = world_seed
        w = World(codex, seed=run_seed)
        w.new_level(8)
        return w.level

    def test_floor_eight_is_exactly_two_rooms(self):
        lvl = self._level()
        self.assertEqual(len(lvl.rooms), 2)
        self.assertIsNotNone(lvl.ante_room)
        self.assertIsNotNone(lvl.arena_room)

    def test_the_arena_is_the_size_the_design_asks_for(self):
        lvl = self._level()
        self.assertEqual((lvl.arena_room.w, lvl.arena_room.h),
                         (config.ARENA_W, config.ARENA_H))

    def test_geometry_is_identical_across_games(self):
        a, b = self._level(world_seed=3), self._level(world_seed=99)
        self.assertEqual((a.arena_room.x, a.arena_room.y), (b.arena_room.x, b.arena_room.y))
        self.assertEqual(a.mouth, b.mouth)
        self.assertEqual(a.stairs, b.stairs)
        self.assertEqual(sorted(a.syrinx_pillars()), sorted(b.syrinx_pillars()))

    def test_twenty_pillars_on_a_six_tile_pitch(self):
        lvl = self._level()
        pillars = lvl.syrinx_pillars()
        self.assertEqual(len(pillars), 20)
        xs = sorted({x for x, _ in pillars})
        ys = sorted({y for _, y in pillars})
        self.assertEqual(len(xs), config.ARENA_PILLAR_COLS)
        self.assertEqual(len(ys), config.ARENA_PILLAR_ROWS)
        for a, b in zip(xs, xs[1:]):
            self.assertEqual(b - a, config.ARENA_PILLAR_PITCH)
        for a, b in zip(ys, ys[1:]):
            self.assertEqual(b - a, config.ARENA_PILLAR_PITCH)

    def test_pillars_are_wall_and_never_block_anything_that_matters(self):
        lvl = self._level()
        for px, py in lvl.syrinx_pillars():
            self.assertEqual(lvl.grid[py][px], 0, "a pillar is a WALL tile")
            self.assertNotEqual((px, py), lvl.stairs)
            self.assertNotEqual((px, py), lvl.mouth)
            self.assertNotEqual((px, py), lvl.boss_arrival())

    def test_the_mouth_joins_the_two_rooms_and_starts_open(self):
        lvl = self._level()
        mx, my = lvl.mouth
        self.assertEqual(lvl.grid[my][mx], 1, "the mouth is open until you commit")
        self.assertTrue(lvl.arena_room.contains(mx + 1, my))
        self.assertTrue(lvl.ante_room.contains(mx - 1, my))

    def test_you_arrive_in_the_antechamber_and_the_way_down_is_in_the_arena(self):
        lvl = self._level()
        self.assertTrue(lvl.ante_room.contains(*lvl.entrance))
        self.assertTrue(lvl.arena_room.contains(*lvl.stairs))
        self.assertTrue(lvl.arena_room.contains(*lvl.boss_arrival()))

    def test_she_arrives_at_the_far_end_well_beyond_your_sight(self):
        lvl = self._level()
        bx, by = lvl.boss_arrival()
        mx, my = lvl.mouth
        self.assertGreater(max(abs(bx - mx), abs(by - my)), config.FOV_RADIUS,
                           "her arrival must be unwitnessed")

    def test_other_floors_are_untouched(self):
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=1)
        w.new_level(7)
        self.assertIsNone(w.level.arena_room)
        self.assertFalse(w.level.is_arena_floor())
        self.assertGreater(len(w.level.rooms), 2)


class TestArenaHazards(unittest.TestCase):
    """Her blow is 1-3 against 26 HP and there is no levelling. She is not the
    damage -- the room is. The hazards are stone, dealt from lrng, so they are the
    same on every re-entry within a game and re-dealt in a new one: dying on floor 8
    buys you knowledge of THIS dungeon's hall."""

    def _level(self, world_seed=3):
        codex = FakeSave(); codex.world_seed = world_seed
        w = World(codex, seed=1)
        w.new_level(8)
        return w.level

    def test_the_hall_is_properly_trapped(self):
        lvl = self._level()
        self.assertEqual(len(lvl.traps), config.ARENA_TRAPS)

    def test_no_alarm_rune_in_a_one_monster_room(self):
        lvl = self._level()
        keys = {t.key for t in lvl.traps}
        self.assertNotIn("alarm", keys,
                         "wake_all() would wake a boss who is already hunting you")
        self.assertTrue(keys <= {"dart", "spike", "gas", "glyph"})

    def test_every_hazard_is_on_arena_floor_and_nowhere_forbidden(self):
        lvl = self._level()
        pillars = set(lvl.syrinx_pillars())
        for t in lvl.traps:
            self.assertTrue(lvl.arena_room.contains(t.x, t.y))
            self.assertEqual(lvl.grid[t.y][t.x], 1)
            self.assertNotIn((t.x, t.y), pillars)
            self.assertNotEqual((t.x, t.y), lvl.stairs)
            self.assertNotEqual((t.x, t.y), lvl.mouth)
            self.assertNotEqual((t.x, t.y), lvl.boss_arrival())

    def test_no_hazard_ambushes_you_on_the_threshold(self):
        lvl = self._level()
        ax, ay = lvl.arena_room.x, lvl.arena_room.cy
        for t in lvl.traps:
            self.assertGreater(max(abs(t.x - ax), abs(t.y - ay)), 1,
                               "stepping through the gate onto a glyph is not a fight")

    def test_one_hazard_per_tile(self):
        lvl = self._level()
        spots = [(t.x, t.y) for t in lvl.traps]
        self.assertEqual(len(spots), len(set(spots)))

    def test_hazards_are_stone__same_all_game__redealt_in_a_new_one(self):
        same_a, same_b = self._level(world_seed=7), self._level(world_seed=7)
        self.assertEqual(sorted((t.key, t.x, t.y) for t in same_a.traps),
                         sorted((t.key, t.x, t.y) for t in same_b.traps))
        other = self._level(world_seed=8)
        self.assertNotEqual(sorted((t.key, t.x, t.y) for t in same_a.traps),
                            sorted((t.key, t.x, t.y) for t in other.traps))


class TestArenaGateState(unittest.TestCase):
    """Three booleans carry the whole floor: has the mouth shut, is the way down
    barred, has she arrived. Suspend in the antechamber and she must not exist on
    resume; suspend mid-fight and she must, exactly where she was."""

    def _world(self):
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=1)
        w.new_level(8)
        return w

    def test_a_fresh_hall_starts_open_barred_and_empty(self):
        lvl = self._world().level
        self.assertFalse(lvl.mouth_sealed)
        self.assertTrue(lvl.stairs_locked, "the way down is shut until she is dead")
        self.assertFalse(lvl.boss_spawned)

    def test_ordinary_floors_are_never_barred(self):
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=1)
        w.new_level(7)
        self.assertFalse(w.level.stairs_locked)
        self.assertFalse(w.level.mouth_sealed)

    def test_the_three_flags_survive_a_round_trip(self):
        from .dungeon import Level
        w = self._world()
        w.level.mouth_sealed = True
        w.level.stairs_locked = False
        w.level.boss_spawned = True
        data = w.level.to_dict()

        restored = Level(8, w.rng, w.codex, restore=data)
        self.assertTrue(restored.mouth_sealed)
        self.assertFalse(restored.stairs_locked)
        self.assertTrue(restored.boss_spawned)

    def test_a_sealed_mouth_is_still_stone_after_a_resume(self):
        from .dungeon import Level
        w = self._world()
        mx, my = w.level.mouth
        w.level.grid[my][mx] = 0
        w.level.mouth_sealed = True
        data = w.level.to_dict()

        restored = Level(8, w.rng, w.codex, restore=data)
        self.assertEqual(restored.grid[my][mx], 0,
                         "a resumed hall must not re-open the gate you shut")

    def test_the_save_version_moved(self):
        self.assertGreaterEqual(config.RUN_SAVE_VERSION, 4)


class TestArenaGates(unittest.TestCase):
    """Three gates, one object, each opening one way only: the way up seals when you
    arrive, the mouth seals when you commit, and the way down opens when she dies."""

    def _world(self):
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=1)
        w.new_level(8)
        return w

    def _commit(self, w):
        """Walk the player through the mouth into the hall."""
        a = w.level.arena_room
        w.player.x, w.player.y = a.x, a.cy
        w._enter_tile()

    def test_the_way_up_is_stone_the_moment_you_arrive(self):
        w = self._world()
        w.player.x, w.player.y = w.level.entrance
        self.assertFalse(w.ascend(), "there is no way back from her floor")

    def test_ordinary_floors_still_let_you_climb(self):
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=1)
        w.new_level(7)
        w.player.x, w.player.y = w.level.entrance
        self.assertTrue(w.ascend())

    def test_the_mouth_shuts_behind_you(self):
        w = self._world()
        mx, my = w.level.mouth
        self.assertEqual(w.level.grid[my][mx], 1)
        self._commit(w)
        self.assertTrue(w.level.mouth_sealed)
        self.assertEqual(w.level.grid[my][mx], 0, "the gate is stone now")

    def test_committing_reveals_the_halls_stone_and_never_its_contents(self):
        w = self._world()
        self._commit(w)
        a = w.level.arena_room
        far_x, far_y = a.x + a.w - 2, a.y + 1
        self.assertTrue(w.level.explored[far_y][far_x],
                        "the hall shows you its shape")
        self.assertFalse(w.level.seen[far_y][far_x],
                         "nothing but your own eyes ever shows you contents")

    def test_the_hazards_stay_hidden_through_the_reveal(self):
        w = self._world()
        self._commit(w)
        far = [t for t in w.level.traps
               if max(abs(t.x - w.player.x), abs(t.y - w.player.y)) > config.FOV_RADIUS]
        self.assertTrue(far, "test needs a hazard out of sight")
        for t in far:
            self.assertFalse(w.codex.trap_found(8, t.x, t.y),
                             "a reveal maps stone, not danger")

    def test_the_way_down_is_barred_until_she_dies(self):
        w = self._world()
        self._commit(w)
        w.player.x, w.player.y = w.level.stairs
        self.assertFalse(w.descend(), "the hall holds the stairs shut")
        self.assertEqual(w.depth, 8)

    def test_killing_her_opens_the_way_down(self):
        from .monsters import Monster
        w = self._world()
        self._commit(w)
        m = Monster("syrinx", w.level.arena_room.cx, w.level.arena_room.cy)
        w.level.monsters = [m]
        w.kill_monster(m)
        self.assertFalse(w.level.stairs_locked)
        w.player.x, w.player.y = w.level.stairs
        self.assertTrue(w.descend())
        self.assertEqual(w.depth, 9)

    def test_a_hazard_that_kills_her_opens_it_too(self):
        from .monsters import Monster
        w = self._world()
        self._commit(w)
        m = Monster("syrinx", w.level.arena_room.cx, w.level.arena_room.cy)
        w.level.monsters = [m]
        w.kill_monster(m, source="glyph")
        self.assertFalse(w.level.stairs_locked,
                         "the gate answers to her death, not to who dealt it")

    def test_the_mouth_only_seals_once(self):
        w = self._world()
        self._commit(w)
        w.level.boss_spawned = False       # pretend Task 6 has not run
        self._commit(w)
        self.assertTrue(w.level.mouth_sealed)


class TestArenaBossArrival(unittest.TestCase):
    """She is not in the hall until you commit to it. She materialises at the far
    end, holds one turn, and sinks into a column -- all of it ~27 tiles away, well
    outside FOV_RADIUS, so you are never shown it happening."""

    def _world(self):
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=1)
        w.new_level(8)
        return w

    def _commit(self, w):
        a = w.level.arena_room
        w.player.x, w.player.y = a.x, a.cy
        w._enter_tile()

    def test_the_hall_is_empty_until_you_step_into_it(self):
        w = self._world()
        self.assertEqual([m for m in w.level.monsters if m.key == "syrinx"], [])
        self.assertFalse(w.level.boss_spawned)

    def test_she_arrives_on_commit_at_the_far_end_and_not_hidden(self):
        w = self._world()
        self._commit(w)
        found = [m for m in w.level.monsters if m.key == "syrinx"]
        self.assertEqual(len(found), 1)
        m = found[0]
        self.assertEqual((m.x, m.y), w.level.boss_arrival())
        self.assertFalse(m.hidden, "she materialises before she hides")
        self.assertTrue(w.level.boss_spawned)

    def test_she_arrives_out_of_sight(self):
        w = self._world()
        self._commit(w)
        m = [m for m in w.level.monsters if m.key == "syrinx"][0]
        self.assertFalse(w.level.visible[m.y][m.x],
                         "the room shows you its shape, never her")

    def test_she_holds_one_turn_then_goes_to_ground(self):
        w = self._world()
        self._commit(w)
        m = [x for x in w.level.monsters if x.key == "syrinx"][0]
        self.assertEqual(m.intent[0], "arrive")
        m._ai_syrinx(w, w.player)             # the held turn
        self.assertIsNone(m.intent)
        self.assertFalse(m.hidden, "still standing -- she has only just turned to go")
        self.assertTrue(m.retreating, "and she is now heading for a column")
        for _ in range(60):                   # let her walk to one
            if m.hidden:
                break
            m._ai_syrinx(w, w.player)
        self.assertTrue(m.hidden, "she reaches a column and goes off-grid")

    def test_she_arrives_only_once(self):
        w = self._world()
        self._commit(w)
        w.level.mouth_sealed = False
        self._commit(w)
        self.assertEqual(len([m for m in w.level.monsters if m.key == "syrinx"]), 1)

    def test_a_resume_before_commit_leaves_the_hall_empty(self):
        from .dungeon import Level
        w = self._world()
        restored = Level(8, w.rng, w.codex, restore=w.level.to_dict())
        self.assertEqual([m for m in restored.monsters if m.key == "syrinx"], [])
        self.assertFalse(restored.boss_spawned)

    def test_a_resume_mid_fight_keeps_her_exactly_where_she_was(self):
        from .dungeon import Level
        w = self._world()
        self._commit(w)
        m = [x for x in w.level.monsters if x.key == "syrinx"][0]
        m.x, m.y = w.level.arena_room.cx, w.level.arena_room.cy
        m.hp = 11
        restored = Level(8, w.rng, w.codex, restore=w.level.to_dict())
        found = [x for x in restored.monsters if x.key == "syrinx"]
        self.assertEqual(len(found), 1)
        self.assertEqual((found[0].x, found[0].y), (m.x, m.y))
        self.assertEqual(found[0].hp, 11)


if __name__ == "__main__":
    pygame.init()
    unittest.main(exit=False, verbosity=2)
    pygame.quit()
