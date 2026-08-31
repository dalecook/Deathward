# Syrinx — Floor 8 Mini-Boss Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Syrinx, the floor-8 mini-boss — a hide-in-pillars, ranged-only reed-nymph who drops Windfang and Shademail on death — as a fully wired, tested monster consistent with the approved design spec.

**Architecture:** A new `Monster` key (`syrinx`) whose entire encounter loop (hidden → telegraph → emerge → hunt → blow → stunned → retreat → re-hide) lives in one new `_ai_syrinx` method, reusing existing primitives (`self.intent` for telegraphs, `self.stunned` for the punish window, `_step_toward`/`_step_away` for all movement, `world.line_clear` for the ranged gate) exactly as the Warden and beholder already do. A new `hidden` boolean is the untargetability gate, checked at the few real choke points (`world.monster_at`, area-effect target lists, rendering, banishment) rather than removing her from `level.monsters`, which keeps serialization and turn-processing free. Her arena is a deterministic function of the floor's room geometry (never itself saved), carved into a normal floor-8 generation pass that reserves one room from ordinary population instead of replacing the floor's population wholesale (unlike the Warden's).

**Tech Stack:** Pure Python (stdlib) + pygame, existing `deathward` package conventions. Tests via `py -3.13 -m deathward.tests`.

## Global Constraints

- Floor 15 / Void Scimitar / Nightcloak mini-boss is out of scope — do not touch.
- No ambient monsters or chests spawn in Syrinx's arena room (explicit spec decision for this version).
- On death she drops **both** Windfang and Shademail, guaranteed, every time.
- She **never** initiates a melee attack — her only offense is the ranged blow.
- All her movement uses the existing `_step_toward`/`_step_away` primitives — no new pathfinding.
- The retreat/re-route heuristic is an explicit implementation choice (per spec) — it only needs to react to being blocked, not solve real pathfinding.
- Exact tuning numbers are picked now as named `config.py` constants (never inline magic numbers), understood to be retuned later.
- Run the full suite with `py -3.13 -m deathward.tests` after every task; it must stay green.

---

### Task 1: Monster identity — template, stats, Kodex facts, spawn exclusion

**Files:**
- Modify: `deathward/monsters.py:90-91` (TEMPLATES), `deathward/monsters.py:166-170` (unaffected this task, read-only reference)
- Modify: `deathward/codex.py:307-321` (FACT_LIST, after the Warden's three facts), `deathward/codex.py:629` (CAUSE_NAME)
- Test: `deathward/tests.py` (new classes appended before `if __name__ == "__main__":` at line 9793)

**Interfaces:**
- Consumes: `monsters.Template`, `monsters.TEMPLATES`, `codex.Fact`/`_f`/`FACT_LIST`, `codex.CAUSE_NAME`.
- Produces: `TEMPLATES["syrinx"]` (hp=30, lo=1, hi=3, speed=100, glyph="y", color=(196,214,150)); `FACTS["syrinx.rule"/"tell"/"counter"]`; `CAUSE_NAME["syrinx"]`. Every later task relies on `TEMPLATES["syrinx"]` existing.

- [ ] **Step 1: Write the failing HP/stat test**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.13 -m deathward.tests TestSyrinxIdentity -v`
Expected: FAIL with `KeyError: 'syrinx'`

- [ ] **Step 3: Add her Template**

In `deathward/monsters.py`, inside the `TEMPLATES` dict, immediately before its closing `}` (after the `"warden"` line, currently line 90):

```python
    # floor 8's mini-boss: a reed-nymph who hides inside the arena's pillars and
    # only ever fights at range -- a gust that is mostly knockback, with a little
    # real chip damage. Brittle (roughly six solid hits from a strong weapon --
    # 30 / ((4+7)/2 Vampiric Kris average) = 5.45, rounds up to 6) and
    # fire-vulnerable; catching her mid-blow is the whole fight (see _ai_syrinx).
    "syrinx":  Template("syrinx", "Syrinx", "y", (196, 214, 150), 30, 1, 3, 100),
```

Do **not** add her to `SPAWN_TABLE` or `spawn_roster` — omission is the exclusion mechanism, matching how `warden` is already excluded.

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.13 -m deathward.tests TestSyrinxIdentity -v`
Expected: PASS

- [ ] **Step 5: Write the failing Kodex test**

```python
    def test_she_has_a_codex_entry_and_a_cause_name(self):
        from .codex import CAUSE_NAME, FACTS
        for tier in ("rule", "tell", "counter"):
            self.assertIn("syrinx.%s" % tier, FACTS)
        self.assertEqual(CAUSE_NAME["syrinx"], "Syrinx")
```

- [ ] **Step 6: Run test to verify it fails**

Run: `py -3.13 -m deathward.tests TestSyrinxIdentity.test_she_has_a_codex_entry_and_a_cause_name -v`
Expected: FAIL (`KeyError`)

- [ ] **Step 7: Add her Kodex facts and cause name**

In `deathward/codex.py`, immediately after the Warden's three facts (after `warden.counter`, before the `# --- TRAPS ---` comment, currently around line 321):

```python
    # --- SYRINX (floor 8 mini-boss) --------------------------------------
    _f("syrinx.rule", "syrinx", "rule", "SYRINX -- WHAT SHE IS",
       "A reed-nymph, not a spirit -- corporeal, and breakable. She lives inside "
       "the pillars of her own arena and cannot be reached while she is in the "
       "stone. She has no melee: her only attack is a gust of wind that knocks "
       "you back and does a little real damage. Catching her costs you nothing."),
    _f("syrinx.tell", "syrinx", "tell", "SYRINX -- THE TELL",
       "She cannot hide forever -- a pillar glows the turn before she is forced "
       "out, and that glow tells you exactly which one. When she is in the open "
       "and lines herself up on you, she is a turn from firing -- move, or put a "
       "pillar between you, before it lands."),
    _f("syrinx.counter", "syrinx", "counter", "SYRINX -- THE COUNTER",
       "The instant her gust lands, she is stunned and fully open -- the one "
       "guaranteed window in the whole fight. She is fire-vulnerable and immune "
       "to anything you would call cold, poison or fear -- burn her, hit her "
       "hard in that window, and she folds in about six solid blows."),
```

In `deathward/codex.py`, in the `CAUSE_NAME` dict (currently line 629), immediately after `"warden": "the Warden",`:

```python
    "syrinx": "Syrinx",
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `py -3.13 -m deathward.tests TestSyrinxIdentity -v`
Expected: PASS, all 4 tests.

- [ ] **Step 9: Run the full suite**

Run: `py -3.13 -m deathward.tests`
Expected: PASS (no regressions)

- [ ] **Step 10: Commit**

```bash
git add deathward/monsters.py deathward/codex.py deathward/tests.py
git commit -m "feat(syrinx): add monster template, stats, and Kodex identity"
```

---

### Task 2: Hidden / forced-emergence / telegraph state machine + untargetability

**Files:**
- Modify: `deathward/monsters.py:166-170` (`_MONSTER_STATE`), `:174-203` (`Monster.__init__`), append new `_ai_syrinx` method after `_ai_warden` (currently ends line 675, before `spawn_count` at line 678)
- Modify: `deathward/world.py:354-358` (`monster_at`), `:817-826` (`_firestorm`), `:~1937` (thunderclap in `_apply_effect`)
- Modify: `deathward/render.py:233-235` (monster draw loop)
- Modify: `deathward/config.py` (new constant, appended after `FULGURITE_INCORP_MULT` at line 171)
- Test: `deathward/tests.py`

**Interfaces:**
- Consumes: `TEMPLATES["syrinx"]` (Task 1).
- Produces: `Monster.hidden` (bool), `Monster.hidden_turns` (int), `Monster.pillar_x`/`pillar_y` (int), `Monster.retreating` (bool) — all in `_MONSTER_STATE`, so `to_dict`/`from_dict` round-trip them automatically. `config.SYRINX_HIDDEN_MAX`. `_ai_syrinx(self, world, p)` (first cut: hidden/telegraph/emerge only; Task 4 replaces its body wholesale, showing the full method again). `world.monster_at` and rendering now skip any monster with `.hidden == True`.

- [ ] **Step 1: Write the failing state-shape test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m deathward.tests TestSyrinxHiddenState.test_she_spawns_hidden_awake_and_pinned_to_her_pillar -v`
Expected: FAIL (`AttributeError: 'Monster' object has no attribute 'hidden'`)

- [ ] **Step 3: Add the new state fields**

In `deathward/monsters.py`, replace the `_MONSTER_STATE` tuple (currently lines 166-170):

```python
_MONSTER_STATE = (
    "x", "y", "hp", "max_hp", "energy", "awake", "stunned", "burning",
    "poisoned", "fled", "disguised", "warden_last", "feed", "recharge",
    "ray_armed", "weak", "feared", "confused", "hammer_hits", "enraged",
    "hidden", "hidden_turns", "pillar_x", "pillar_y", "retreating",
)
```

In `Monster.__init__`, change the existing line `self.awake = (key == "orc")` to:

```python
        # an orc is always ACTIVE -- it takes a turn every tick, to watch for you with
        # its good eyes and to keep its pack together -- but being active is not the
        # same as being HOSTILE. it turns hostile only when it actually SEES you (see
        # _ai_orc). so it starts awake, unlike everything else, which sleeps until seen.
        # Syrinx is the same: her hidden-turn budget must tick down from the moment
        # she is placed, whether or not the player has ever laid eyes on her.
        self.awake = key in ("orc", "syrinx")
```

Then, at the end of `__init__` (after the existing `self.enraged = 0` line), add:

```python
        # Syrinx only: she starts hidden in the pillar she is built at. hidden_turns
        # counts turns spent hidden this cycle, toward the forced-emergence cap.
        # pillar_x/pillar_y remember which pillar that is, so a retreat never re-picks
        # the one she just left. retreating is true from the moment her post-blow stun
        # ends until she reaches a pillar and re-hides. See _ai_syrinx.
        self.hidden = (key == "syrinx")
        self.hidden_turns = 0
        self.pillar_x, self.pillar_y = (x, y) if key == "syrinx" else (-1, -1)
        self.retreating = False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.13 -m deathward.tests TestSyrinxHiddenState.test_she_spawns_hidden_awake_and_pinned_to_her_pillar -v`
Expected: PASS

- [ ] **Step 5: Write the failing forced-emergence test**

```python
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
```

- [ ] **Step 6: Run test to verify it fails**

Run: `py -3.13 -m deathward.tests TestSyrinxHiddenState.test_forced_emergence_after_the_hidden_cap -v`
Expected: FAIL (`_ai_syrinx` does not exist yet, `take_turn`'s `getattr(self, "_ai_"+self.key, None)` returns `None`, so nothing changes and `s.intent` stays `None`)

- [ ] **Step 7: Add the config constant and the first cut of `_ai_syrinx`**

In `deathward/config.py`, immediately after `FULGURITE_INCORP_MULT = 1.5` (currently line 171):

```python

# --- Syrinx (floor 8 mini-boss) -------------------------------------------
SYRINX_HIDDEN_MAX = 5      # turns she may stay hidden before a forced emergence
```

In `deathward/monsters.py`, append after `_ai_warden` (currently ends line 675), before `def spawn_count(depth, rng):` (currently line 678):

```python
    def _ai_syrinx(self, world, p):
        """Hide/telegraph/emerge/hunt/blow/stun/retreat -- her whole loop, from the
        design spec. This first cut only covers hiding, the forced-emergence budget
        and the one-turn emergence telegraph (reusing self.intent, exactly like the
        Warden's smash/spit); hunt, the blow, and the stun/retreat/re-hide tail are
        filled in by later tasks, which show this method again in full.

        The telegraph is a REAL fact, not flavour: it marks the exact pillar she is
        already standing in -- an unmet player and a veteran face identical odds.
        """
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
        self._step_toward(world, p.x, p.y)
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `py -3.13 -m deathward.tests TestSyrinxHiddenState -v`
Expected: PASS, both tests.

- [ ] **Step 9: Write the failing untargetability test**

```python
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
        surf = pygame.Surface((config.W, config.H))
        render.draw_world(surf, w, w.codex, cam, 0.0)   # must not raise
```

- [ ] **Step 10: Run tests to verify they fail**

Run: `py -3.13 -m deathward.tests TestSyrinxHiddenState.test_hidden_syrinx_cannot_be_targeted_by_monster_at TestSyrinxHiddenState.test_hidden_syrinx_is_untouched_by_area_damage -v`
Expected: FAIL — `monster_at` returns her; `_firestorm`/`thunderclap` reduce her hp.

- [ ] **Step 11: Gate `monster_at`, `_firestorm`, and thunderclap on `.hidden`**

In `deathward/world.py`, replace `monster_at` (currently lines 354-358):

```python
    def monster_at(self, x, y):
        for m in self.level.monsters:
            if m.alive and not m.hidden and m.x == x and m.y == y:
                return m
        return None
```

In `_firestorm` (currently line 820), change:

```python
        hit = [m for m in list(self.level.monsters) if self.visible(m.x, m.y)]
```

to:

```python
        hit = [m for m in list(self.level.monsters)
               if self.visible(m.x, m.y) and not m.hidden]
```

In `_apply_effect`, in the `elif effect == "thunderclap":` branch (currently around line 1937), apply the same change to its `hit = [...]` line.

- [ ] **Step 12: Run tests to verify they pass**

Run: `py -3.13 -m deathward.tests TestSyrinxHiddenState -v`
Expected: FAIL only on the render test (render.py not yet touched) — PASS on the other four.

- [ ] **Step 13: Gate rendering on `.hidden`**

In `deathward/render.py`, in the monster-drawing loop (currently lines 233-235), change:

```python
    for m in lvl.monsters:
        if not lvl.visible[m.y][m.x] or not cam.on_screen(m.x, m.y):
            continue
```

to:

```python
    for m in lvl.monsters:
        if m.hidden or not lvl.visible[m.y][m.x] or not cam.on_screen(m.x, m.y):
            continue
```

- [ ] **Step 14: Run tests to verify they pass**

Run: `py -3.13 -m deathward.tests TestSyrinxHiddenState -v`
Expected: PASS, all 6 tests.

- [ ] **Step 15: Run the full suite**

Run: `py -3.13 -m deathward.tests`
Expected: PASS (no regressions — `monster_at`/`_firestorm`/thunderclap/render changes are no-ops for every monster that never sets `.hidden = True`, since it defaults `False` for everyone else)

- [ ] **Step 16: Commit**

```bash
git add deathward/monsters.py deathward/world.py deathward/render.py deathward/config.py deathward/tests.py
git commit -m "feat(syrinx): hidden/telegraph/forced-emergence state machine and untargetability"
```

---

### Task 3: Floor-8 arena — pillars, reserved room, stairs preserved

**Files:**
- Modify: `deathward/dungeon.py:215` (`Level.__init__`), `:438-453` (`_generate`), `:513-547` (`_free_tile`), `:672-673` (hoard room selection), `:710-712` (`_place_orc_packs`), append `_syrinx_arena`/`syrinx_pillars`/`_populate_syrinx` after `_populate_boss` (currently ends line 766, before `# --- queries ---` at line 768)
- Modify: `deathward/config.py` (new constant)
- Test: `deathward/tests.py`

**Interfaces:**
- Consumes: `Monster("syrinx", x, y)` (Task 1/2, spawns already `hidden=True`).
- Produces: `Level._syrinx_arena(self) -> Room`, `Level.syrinx_pillars(self) -> list[(x, y)]`, `Level._reserved_room` (a `Room` or `None`), `config.SYRINX_DEPTH`. Task 5's retreat logic and Task 9's tests depend on `syrinx_pillars()`.

- [ ] **Step 1: Write the failing "she spawns on floor 8" test**

```python
class TestSyrinxArena(unittest.TestCase):
    def test_floor_eight_places_exactly_one_hidden_syrinx(self):
        for seed in range(20):
            codex = FakeSave(); codex.world_seed = seed
            w = World(codex, seed=1)
            w.new_level(8)
            found = [m for m in w.level.monsters if m.key == "syrinx"]
            self.assertEqual(len(found), 1, "seed %d: floor 8 needs its Syrinx" % seed)
            self.assertTrue(found[0].hidden)

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.13 -m deathward.tests TestSyrinxArena -v`
Expected: `test_floor_eight_places_exactly_one_hidden_syrinx` FAILs (no Syrinx on floor 8 yet); `test_floor_eight_keeps_its_stairs` currently PASSes already (floor 8 is not special yet) — that's fine, it is here to lock in the requirement before we touch generation; `test_only_floor_eight_reserves_a_room` FAILs with `AttributeError: 'Level' object has no attribute '_reserved_room'`.

- [ ] **Step 3: Add `_reserved_room`, the arena/pillar geometry, and `_populate_syrinx`**

In `deathward/dungeon.py`, in `Level.__init__`, immediately after `self.hoard = None` (currently line 215):

```python
        # Syrinx's arena, if this is floor 8 -- reserved BEFORE the ordinary
        # population pass runs, so nothing ambient lands in it. None everywhere else.
        self._reserved_room = None
```

Append after `_populate_boss` (currently ends line 766), before `    # --- queries ---` (currently line 768):

```python
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
        just its centre, so she always has SOMEWHERE to hide."""
        arena = self._syrinx_arena()
        if arena.w < 7 or arena.h < 6:
            return [] if (arena.cx, arena.cy) == self.stairs else [(arena.cx, arena.cy)]
        xs = [arena.x + 2, arena.x + arena.w // 2, arena.x + arena.w - 3]
        ys = [arena.y + 2, arena.y + arena.h - 3]
        spots = [(x, y) for y in ys for x in xs]
        return [(x, y) for x, y in spots if (x, y) != self.stairs]

    def _populate_syrinx(self):
        """Her arena, carved AFTER the floor's ordinary pass (see _generate) -- floor
        8 is not the Warden's floor: it keeps its stairs and everything else."""
        spots = self.syrinx_pillars()
        if not spots:
            return
        for px, py in spots:
            self.grid[py][px] = WALL
        self.monsters.append(Monster("syrinx", *spots[0]))
```

In `_generate` (currently lines 438-453), change the dispatch:

```python
        if self.depth >= config.DEPTH_MAX:
            self._populate_boss()
        else:
            self._populate(codex)
```

to:

```python
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
```

In `deathward/config.py`, immediately after the `SYRINX_HIDDEN_MAX` line added in Task 2:

```python
SYRINX_DEPTH      = 8      # the floor her arena is on
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.13 -m deathward.tests TestSyrinxArena -v`
Expected: PASS, all 3 tests.

- [ ] **Step 5: Write the failing "no ambient content in her room" test**

```python
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
```

- [ ] **Step 6: Run test to verify it fails**

Run: `py -3.13 -m deathward.tests TestSyrinxArena.test_her_arena_has_no_ambient_monster_or_chest -v`
Expected: FAIL on at least some seeds (`_free_tile` does not yet respect `_reserved_room`)

- [ ] **Step 7: Make `_free_tile`, the hoard room, and orc packs respect `_reserved_room`**

In `_free_tile` (currently lines 513-547), immediately after the existing `if (x, y) == self.stairs: continue` line, insert:

```python
            if (room is None and self._reserved_room is not None
                    and self._reserved_room.contains(x, y)):
                continue          # Syrinx's arena: nothing ambient may land in it
```

In `_populate`, change the hoard-room filter (currently lines 672-673):

```python
        hoard_rooms = [r for r in self.rooms
                       if r is not self.gate_room and not r.contains(*self.stairs)]
```

to:

```python
        hoard_rooms = [r for r in self.rooms
                       if r is not self.gate_room and r is not self._reserved_room
                       and not r.contains(*self.stairs)]
```

In `_place_orc_packs`, change (currently lines 710-712):

```python
        rooms = [r for r in self.rooms
                 if r is not self.gate_room and r.area >= 18]
        rooms = rooms or [r for r in self.rooms if r is not self.gate_room] or self.rooms
```

to:

```python
        rooms = [r for r in self.rooms
                 if r is not self.gate_room and r is not self._reserved_room
                 and r.area >= 18]
        rooms = (rooms
                 or [r for r in self.rooms
                     if r is not self.gate_room and r is not self._reserved_room]
                 or self.rooms)
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `py -3.13 -m deathward.tests TestSyrinxArena -v`
Expected: PASS, all 4 tests.

- [ ] **Step 9: Write the failing pillar/reachability tests**

```python
    def test_pillars_are_wall_tiles_and_never_the_stairs(self):
        from .dungeon import WALL
        for seed in range(20):
            codex = FakeSave(); codex.world_seed = seed
            w = World(codex, seed=1)
            w.new_level(8)
            for (px, py) in w.level.syrinx_pillars():
                self.assertEqual(w.level.grid[py][px], WALL)
                self.assertNotEqual((px, py), w.level.stairs)

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
```

- [ ] **Step 10: Run tests to verify they pass**

Run: `py -3.13 -m deathward.tests TestSyrinxArena -v`
Expected: PASS, all 6 tests. (Scattered single-tile pillars in a room whose minimum size is already enforced by `syrinx_pillars()` cannot disconnect an open rectangle, so this is expected to pass without further changes; if it does not, the fix is to shrink the pillar-offset margins in `syrinx_pillars()`, not to add a new algorithm.)

- [ ] **Step 11: Run the full suite**

Run: `py -3.13 -m deathward.tests`
Expected: PASS (no regressions — `_reserved_room` is `None` on every other floor, so `_free_tile`/hoard/orc-pack behavior is unchanged there)

- [ ] **Step 12: Commit**

```bash
git add deathward/dungeon.py deathward/config.py deathward/tests.py
git commit -m "feat(syrinx): floor-8 arena with reserved pillar room, stairs preserved"
```

---

### Task 4: Hunt + blow (telegraph-resolve) + fizzle

**Files:**
- Modify: `deathward/monsters.py` — replace the whole `_ai_syrinx` body added in Task 2
- Test: `deathward/tests.py`

**Interfaces:**
- Consumes: `world.line_clear(x0, y0, x1, y1, maxdist)` (existing).
- Produces: updated `_ai_syrinx` with a `("blow", 0, 0)` intent kind (mirrors `("spit", 0, 0)`'s telegraph-then-resolve shape). Task 5 replaces this method again to add the stun/knockback/retreat tail.

- [ ] **Step 1: Write the failing hunt/blow/fizzle tests**

```python
class TestSyrinxHuntAndBlow(unittest.TestCase):
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
        w = self._world()
        s = self._syrinx(w, 1, 1)            # adjacent, diagonal -- never aligned
        hp = w.player.hp
        for _ in range(4):
            s.take_turn(w)
        self.assertEqual(w.player.hp, hp, "no melee code path exists for her at all")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.13 -m deathward.tests TestSyrinxHuntAndBlow -v`
Expected: FAIL — `_ai_syrinx` from Task 2 only steps toward the player and never sets a `"blow"` intent or deals damage.

- [ ] **Step 3: Replace `_ai_syrinx` with the hunt+blow version**

In `deathward/monsters.py`, replace the entire `_ai_syrinx` method body added in Task 2 with:

```python
    def _ai_syrinx(self, world, p):
        """Hide/telegraph/emerge/hunt/blow/stun/retreat -- her whole loop, from the
        design spec. This cut adds hunting and the ranged blow (a telegraph-then-
        resolve pair on self.intent, the exact same shape as the Warden's spit --
        see world.line_clear's docstring). The stun/knockback/retreat/re-hide tail
        is added by the next task, which shows this method again in full.
        """
        RANGE = 9

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

        # the blow: telegraphed one turn, resolved the next -- the player can still
        # break the line by moving or ducking behind a pillar in between.
        if self.intent and self.intent[0] == "blow":
            self.intent = None
            if world.line_clear(self.x, self.y, p.x, p.y, RANGE):
                world.add_fx("beam", p.x, p.y, color=self.t.color, life=0.4,
                             tiles=[(self.x, self.y)])
                self._hit(world, verb="buffets")
            else:
                world.log("Syrinx's gust dies against the stone.", config.DIM)
            return

        # hunt: actively seek an aligned, clear line -- never wait passively for one.
        aligned = (self.x == p.x or self.y == p.y)
        if (aligned and self.dist(p.x, p.y) <= RANGE
                and world.line_clear(self.x, self.y, p.x, p.y, RANGE)):
            self.intent = ("blow", 0, 0)
            return
        self._step_toward(world, p.x, p.y)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.13 -m deathward.tests TestSyrinxHuntAndBlow -v`
Expected: PASS, all 5 tests.

- [ ] **Step 5: Run the full suite**

Run: `py -3.13 -m deathward.tests`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add deathward/monsters.py deathward/tests.py
git commit -m "feat(syrinx): hunting and the telegraphed ranged blow with fizzle"
```

---

### Task 5: Stun + knockback + retreat + re-hide (pillar reroute)

**Files:**
- Modify: `deathward/monsters.py` — replace `_ai_syrinx` again (final version), add `_syrinx_retreat_target` method and `_syrinx_path_blocked` module-level helper
- Modify: `deathward/world.py` — add `_syrinx_knockback` method (near `_knockback`, currently lines 723-733)
- Modify: `deathward/config.py` — two new constants
- Test: `deathward/tests.py`

**Interfaces:**
- Consumes: `world.level.syrinx_pillars()` (Task 3).
- Produces: `world._syrinx_knockback(self, m)`; `Monster._syrinx_retreat_target(self, world, p) -> (x, y) | None`; module-level `_syrinx_path_blocked(x0, y0, x1, y1, px, py) -> bool`; the complete, final `_ai_syrinx`.

- [ ] **Step 1: Write the failing stun/knockback test**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.13 -m deathward.tests TestSyrinxStunAndRetreat -v`
Expected: FAIL — `s.stunned`/`s.retreating` stay at their defaults; `w.player.x` is unchanged (no knockback exists yet).

- [ ] **Step 3: Add the knockback helper and the config constants**

In `deathward/config.py`, immediately after `SYRINX_DEPTH` (added in Task 3):

```python
SYRINX_STUN_TURNS = 1      # turns fully vulnerable after her blow lands
SYRINX_PUSH_DIST  = 2      # tiles the gust shoves the player back
```

In `deathward/world.py`, immediately after `_knockback` (currently ends line 733), before `_void_immune`:

```python
    def _syrinx_knockback(self, m):
        """The gust: shove the player straight back along the line from her to you,
        tile by tile, stopping at the first wall or body. Reposition is the point --
        it can push you out of the cover you were using, or off her line entirely."""
        p = self.player
        dx = (p.x > m.x) - (p.x < m.x)
        dy = (p.y > m.y) - (p.y < m.y)
        if dx == 0 and dy == 0:
            return
        for _ in range(config.SYRINX_PUSH_DIST):
            nx, ny = p.x + dx, p.y + dy
            if not self.walkable(nx, ny) or self.monster_at(nx, ny):
                break
            p.x, p.y = nx, ny
        self.level.compute_fov(p.x, p.y)
```

In `deathward/monsters.py`, in the `_ai_syrinx` method's blow-resolution success branch, change:

```python
            if world.line_clear(self.x, self.y, p.x, p.y, RANGE):
                world.add_fx("beam", p.x, p.y, color=self.t.color, life=0.4,
                             tiles=[(self.x, self.y)])
                self._hit(world, verb="buffets")
            else:
```

to:

```python
            if world.line_clear(self.x, self.y, p.x, p.y, RANGE):
                world.add_fx("beam", p.x, p.y, color=self.t.color, life=0.4,
                             tiles=[(self.x, self.y)])
                self._hit(world, verb="buffets")
                world._syrinx_knockback(self)
                self.stunned = max(self.stunned, config.SYRINX_STUN_TURNS)
                self.retreating = True
            else:
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.13 -m deathward.tests TestSyrinxStunAndRetreat -v`
Expected: PASS, both tests.

- [ ] **Step 5: Write the failing retreat/re-hide tests**

```python
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
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `py -3.13 -m deathward.tests TestSyrinxStunAndRetreat.test_she_heads_for_the_nearest_pillar_that_is_not_the_one_she_left TestSyrinxStunAndRetreat.test_reaching_the_target_pillar_re_hides_her TestSyrinxStunAndRetreat.test_a_blocked_straight_walk_re_routes_to_another_pillar -v`
Expected: FAIL (`AttributeError`/`ImportError` — neither `_syrinx_retreat_target` nor `_syrinx_path_blocked` exist yet, and `take_turn` on a `retreating` Syrinx currently falls through to the hunt branch, which does not re-hide)

- [ ] **Step 7: Add the retreat helpers and the final `_ai_syrinx`**

In `deathward/monsters.py`, add this module-level helper immediately after `is_incorporeal` (currently ends line 112), before the `SPAWN_TABLE` comment block:

```python
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
```

In `Monster`, add `_syrinx_retreat_target` alongside the other shared helpers (immediately after `_step_away`, currently ends line 369):

```python
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
```

Replace the whole `_ai_syrinx` method with its final version:

```python
    def _ai_syrinx(self, world, p):
        """Hide/telegraph/emerge/hunt/blow/stun/retreat -- her whole loop, from the
        design spec:
          1. HIDDEN: off the grid, ticking toward a forced emergence.
          2. TELEGRAPH: one turn's warning on the pillar she is already standing in.
          3. EMERGE: targetable, moves at the player's own speed, never melees.
          4. HUNT: actively seeks an aligned, clear line -- never waits passively.
          5. BLOW: a telegraph-then-resolve pair (self.intent), same shape as the
             Warden's spit; a pillar in the eyeline fizzles it.
          6. STUNNED: fully vulnerable for one turn (config.SYRINX_STUN_TURNS) --
             handled generically by Monster.take_turn's self.stunned early-return.
          7. RETREAT: heads for the nearest pillar that is not the one she just left,
             re-routing per turn if the player's body blocks the straight walk to it.
          8. RE-HIDE: reaching it, she goes off-grid again and the budget resets.
        """
        RANGE = 9

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
            if world.line_clear(self.x, self.y, p.x, p.y, RANGE):
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
            self._step_toward(world, *target)
            return

        aligned = (self.x == p.x or self.y == p.y)
        if (aligned and self.dist(p.x, p.y) <= RANGE
                and world.line_clear(self.x, self.y, p.x, p.y, RANGE)):
            self.intent = ("blow", 0, 0)
            return
        self._step_toward(world, p.x, p.y)
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `py -3.13 -m deathward.tests TestSyrinxStunAndRetreat -v`
Expected: PASS, all 5 tests.

- [ ] **Step 9: Run the whole Syrinx test family plus the full suite**

Run: `py -3.13 -m deathward.tests TestSyrinxIdentity TestSyrinxHiddenState TestSyrinxArena TestSyrinxHuntAndBlow TestSyrinxStunAndRetreat -v`
Expected: PASS, all tests across every task so far.

Run: `py -3.13 -m deathward.tests`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add deathward/monsters.py deathward/world.py deathward/config.py deathward/tests.py
git commit -m "feat(syrinx): post-blow stun, knockback, and pillar retreat/re-hide"
```

---

### Task 6: Sprite

**Files:**
- Modify: `deathward/sprites.py` — add `_syrinx` draw function before `_MONSTER_DRAW` (currently line 497), add its dict entry (after `"warden": _warden,` currently line 510)
- Test: `deathward/tests.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `sprites._MONSTER_DRAW["syrinx"]`; `sprites.monster("syrinx", color)` now returns a real drawn surface instead of a blank one.

- [ ] **Step 1: Write the failing sprite test**

```python
class TestSyrinxSprite(unittest.TestCase):
    def test_it_has_a_sprite_registered(self):
        from . import sprites
        self.assertIn("syrinx", sprites._MONSTER_DRAW)
        self.assertIsNotNone(sprites.monster("syrinx", (196, 214, 150)))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m deathward.tests TestSyrinxSprite -v`
Expected: FAIL — `self.assertIn` fails, `"syrinx"` is not a key in `_MONSTER_DRAW` yet.

- [ ] **Step 3: Draw her**

In `deathward/sprites.py`, immediately before `_MONSTER_DRAW = {` (currently line 497):

```python
def _syrinx(s, S, body, dark):
    """A slender, unassuming figure -- nothing about her reads as a boss. Windswept
    hair trailing sideways and a thin, almost hollow robe, matching her theme:
    lightness (Windfang) and stone-hiding (Shademail)."""
    cx = S * 0.5
    # a slim robed body, narrower than any of the humanoid brutes
    _poly(s, body, [(cx - S * 0.16, S * 0.34), (cx + S * 0.16, S * 0.34),
                    (cx + S * 0.20, S * 0.86), (cx - S * 0.20, S * 0.86)])
    _poly(s, _shade(body, 0.82), [(cx - S * 0.09, S * 0.34), (cx + S * 0.09, S * 0.34),
                                  (cx + S * 0.11, S * 0.70), (cx - S * 0.11, S * 0.70)])
    # a small, plain head -- deliberately unremarkable
    _circ(s, _shade(body, 1.1), cx, S * 0.22, S * 0.12)
    # hair blown sideways -- the only unusual thing about her silhouette
    for dy in (-0.04, 0.02, 0.08):
        _curve(s, _shade(body, 0.85),
               [(cx - S * 0.02, S * (0.14 + dy)),
                (cx - S * 0.30, S * (0.10 + dy)),
                (cx - S * 0.46, S * (0.16 + dy))], S * 0.02)
    # thin arms, close to the body
    _line(s, _shade(body, 0.9), (cx - S * 0.16, S * 0.42), (cx - S * 0.24, S * 0.62), S * 0.045)
    _line(s, _shade(body, 0.9), (cx + S * 0.16, S * 0.42), (cx + S * 0.24, S * 0.62), S * 0.045)
    # two quiet eyes -- nothing predatory
    _circ(s, (30, 34, 26), cx - S * 0.045, S * 0.21, S * 0.018)
    _circ(s, (30, 34, 26), cx + S * 0.045, S * 0.21, S * 0.018)
```

In `_MONSTER_DRAW` (currently lines 497-511), immediately after `"warden": _warden,`:

```python
    "syrinx":    _syrinx,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.13 -m deathward.tests TestSyrinxSprite -v`
Expected: PASS

- [ ] **Step 5: Run the full suite**

Run: `py -3.13 -m deathward.tests`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add deathward/sprites.py deathward/tests.py
git commit -m "feat(syrinx): procedural sprite"
```

---

### Task 7: Fire vulnerability + status immunity

**Files:**
- Modify: `deathward/monsters.py:99-105` (`damage_multiplier`)
- Modify: `deathward/world.py:79` (`BOSS_KEYS` area), `:735-737` (add `_status_immune` after `_void_immune`), `:572-593` (`_weapon_status_on`), `:671-683` (`player_attack` blade coat), `:888-914` (reactive armour), `:2070-2089` (`fear`/`hold` scroll effects)
- Modify: `deathward/traps.py:130-140` (`_spike`)
- Modify: `deathward/config.py` — one new constant
- Test: `deathward/tests.py`

**Interfaces:**
- Consumes: `world.hurt_monster` (existing, already calls `damage_multiplier`).
- Produces: `config.SYRINX_FIRE_MULT`; `world.STATUS_IMMUNE_KEYS`; `world._status_immune(self, m) -> bool`.

- [ ] **Step 1: Write the failing fire-vulnerability test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m deathward.tests TestSyrinxResistances.test_fire_deals_double_damage -v`
Expected: FAIL (`AttributeError: module 'deathward.config' has no attribute 'SYRINX_FIRE_MULT'`)

- [ ] **Step 3: Add the fire multiplier**

In `deathward/config.py`, immediately after `SYRINX_PUSH_DIST` (added in Task 5):

```python
SYRINX_FIRE_MULT  = 2.0    # matches the stone golem's existing fire weakness
```

In `deathward/monsters.py`, in `damage_multiplier` (currently lines 99-105):

```python
def damage_multiplier(monster_key, source):
    if monster_key == "golem":
        if source in FIRE_SOURCES:
            return 2.0       # stone cracks in fire
        if source in ("player", "thorns", "dart", "spike"):
            return 0.25      # steel, darts, spikes -- it barely notices
    if monster_key == "syrinx" and source in FIRE_SOURCES:
        return config.SYRINX_FIRE_MULT     # wind and stone; fire cracks her wide open
    return 1.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.13 -m deathward.tests TestSyrinxResistances.test_fire_deals_double_damage -v`
Expected: PASS

- [ ] **Step 5: Write the failing status-immunity tests**

```python
    def test_freeze_fear_and_poison_never_take_hold(self):
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

    def test_reactive_armour_status_effects_do_not_take_hold(self):
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
        from .traps import Trap
        w = self._world()
        s = Monster("syrinx", 5, 5)
        s.hidden = False
        t = Trap("spike", 5, 5)
        t.trigger(w, s)
        self.assertEqual(s.stunned, 0)
```

(Add `from .monsters import Monster` at the top of the file only if not already imported at module scope in this position — mirror the existing per-test `from .monsters import Monster` style used throughout the file.)

- [ ] **Step 6: Run tests to verify they fail**

Run: `py -3.13 -m deathward.tests TestSyrinxResistances -v`
Expected: FAIL — `_status_immune` does not exist; `s.stunned`/`s.feared`/`s.poisoned` end up nonzero.

- [ ] **Step 7: Add `_status_immune` and gate every status-application site**

In `deathward/world.py`, immediately after the `BOSS_KEYS` line (currently line 79):

```python
BOSS_KEYS = {"warden"}      # void-immune; the mini-boss task adds its keys here
STATUS_IMMUNE_KEYS = {"syrinx"}    # poison/freeze/fear never take hold on her
```

Immediately after `_void_immune` (currently lines 735-737):

```python
    def _status_immune(self, m):
        """Poison, freeze and fear never take hold on Syrinx -- wind and stone have
        nothing in them to poison or frighten. Modeled directly on _void_immune.
        Fire and physical damage are untouched by this; it only ever gates a STATUS
        flag (poisoned/stunned-as-freeze/feared/weak/confused), never a hit."""
        return m.key in STATUS_IMMUNE_KEYS
```

In `_weapon_status_on` (currently lines 572-593), change the freeze/fear/poison conditions:

```python
        if "burn" in traits and m.alive:
            m.burning = max(m.burning, 3)
            self.log("The %s catches fire." % self._mname(m), (255, 150, 80))
            self.add_fx("burning", m.x, m.y, life=0.8, tiles=[(m.x, m.y)])
        if ("freeze" in traits and m.alive and not self._status_immune(m)
                and self.rng.random() < config.FREEZE_CHANCE):
            m.stunned = max(m.stunned, config.FREEZE_TURNS)
            self.log("The %s freezes solid for a beat." % self._mname(m),
                     (150, 210, 255))
            self.add_fx("freeze", m.x, m.y, color=(150, 210, 255), life=0.5)
        if ("fear" in traits and m.alive and not self._status_immune(m)
                and self.rng.random() < config.FEAR_CHANCE):
            m.feared = max(m.feared, config.FEAR_TURNS)
            m.awake = True
            self.log("The %s recoils in terror." % self._mname(m), (120, 100, 190))
        if "poison" in traits and m.alive and not self._status_immune(m):
            m.poisoned = max(m.poisoned, config.POISON_TURNS)
            self.log("The %s is envenomed." % self._mname(m), (150, 220, 130))
            self.add_fx("impact", m.x, m.y, color=(150, 220, 130), radius=0.9, life=0.4)
```

In `player_attack`, change the blade-coat chain (currently lines 671-683):

```python
        if coat == "poison":
            self.log("The venom goes in with it. The blade is clean again.",
                     (150, 220, 130))
            self.add_fx("impact", m.x, m.y, color=(150, 220, 130), radius=0.9,
                        life=0.45)
        elif coat == "weak" and not self._status_immune(m):
            m.weak = max(m.weak, 20)
            self.log("The draught soaks into the wound. The %s's blows will falter."
                     % self._mname(m), (200, 190, 120))
            self.add_fx("impact", m.x, m.y, color=(200, 190, 120), radius=0.9,
                        life=0.45)
        elif coat == "confuse" and not self._status_immune(m):
            m.confused = max(m.confused, 12)
            m.awake = True
            self.log("The draught muddies its head. The %s staggers, lost."
                     % self._mname(m), (176, 120, 132))
            self.add_fx("impact", m.x, m.y, color=(176, 120, 132), radius=0.9,
                        life=0.45)
        elif coat in ("weak", "confuse"):
            self.log("The draught finds nothing in the %s to take hold of."
                     % self._mname(m), config.DIM)
```

In `monster_attacks_player`'s reactive-armour block, change the `venom`/`glacial`/`blinding` branches (currently around lines 888-914):

```python
            elif t == "venom":
                p.armour_cd = config.ARMOUR_RETAL_RECHARGE
                if self._status_immune(m):
                    self.log("Your armour weeps venom -- and finds nothing in the "
                             "%s to poison." % self._mname(m), config.DIM)
                else:
                    m.poisoned = max(m.poisoned, config.VENOM_POISON_TURNS)
                    self.log("Your armour weeps venom -- the %s is envenomed."
                             % self._mname(m), (150, 220, 130))
                    self.add_fx("impact", m.x, m.y, color=(150, 220, 130), radius=0.9,
                                life=0.4)
            elif t == "glacial":
                p.armour_cd = config.ARMOUR_RETAL_RECHARGE
                if self._status_immune(m):
                    self.log("Your armour rimes over -- but the %s does not freeze."
                             % self._mname(m), config.DIM)
                else:
                    m.stunned = max(m.stunned, config.FREEZE_TURNS)
                    self.log("Your armour rimes over -- the %s freezes solid."
                             % self._mname(m), (150, 210, 255))
                    self.add_fx("freeze", m.x, m.y, color=(150, 210, 255), life=0.5)
            elif t == "blinding":
                for mm in self.level.monsters:
                    if (mm.alive and mm.dist(p.x, p.y) <= config.BLINDING_RADIUS
                            and not self._status_immune(mm)):
                        mm.stunned = max(mm.stunned, config.BLINDING_STUN_TURNS)
                        mm.intent = None
                self.log("Your armour ERUPTS with light. Everything near you reels.",
                         config.GOLD)
                self.add_fx("flash", color=(255, 250, 210), life=0.5)
                p.armour_cd = config.ARMOUR_CAPSTONE_RECHARGE
```

In `_apply_effect`, change the `fear` and `hold` branches (currently around lines 2070-2089) so both list comprehensions read:

```python
            hit = [m for m in self.level.monsters
                   if m.dist(p.x, p.y) <= 6 and not m.disguised
                   and not m.hidden and not self._status_immune(m)]
```

(apply this exact `hit = [...]` line to both the `fear` and `hold` branches, in place of their current `if m.dist(p.x, p.y) <= 6 and not m.disguised]` filter — the rest of each branch is unchanged).

In `deathward/traps.py`, in `_spike` (currently lines 130-140), change:

```python
        else:
            world.hurt_monster(victim, dmg, source="spike")
            victim.stunned = max(victim.stunned, 1)
```

to:

```python
        else:
            world.hurt_monster(victim, dmg, source="spike")
            if not world._status_immune(victim):
                victim.stunned = max(victim.stunned, 1)
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `py -3.13 -m deathward.tests TestSyrinxResistances -v`
Expected: PASS, all 5 tests.

- [ ] **Step 9: Run the full suite**

Run: `py -3.13 -m deathward.tests`
Expected: PASS (no regressions — `_status_immune`/`m.hidden` are `False` for every monster except Syrinx, so every gated branch behaves exactly as before for everyone else)

- [ ] **Step 10: Commit**

```bash
git add deathward/monsters.py deathward/world.py deathward/traps.py deathward/config.py deathward/tests.py
git commit -m "feat(syrinx): fire vulnerability and immunity to poison/freeze/fear"
```

---

### Task 8: Void-immunity (`BOSS_KEYS`) + banish-scroll gating

**Files:**
- Modify: `deathward/world.py:79` (`BOSS_KEYS`), `:1727-1751` (`banishable_types`, `banish_type`)
- Test: `deathward/tests.py`

**Interfaces:**
- Consumes: `world._void_immune` (existing).
- Produces: `BOSS_KEYS = {"warden", "syrinx"}`; `banishable_types`/`banish_type` now respect `_void_immune` (this also fixes a pre-existing gap where the Warden itself was never actually protected from the banish scroll).

- [ ] **Step 1: Write the failing void-immunity tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.13 -m deathward.tests TestBossVoidImmunity -v`
Expected: FAIL — `"syrinx" not in BOSS_KEYS`; both `banish_type` calls currently succeed and remove the monster.

- [ ] **Step 3: Add her to `BOSS_KEYS` and gate the banish scroll**

In `deathward/world.py`, change the `BOSS_KEYS` line (currently line 79):

```python
BOSS_KEYS = {"warden", "syrinx"}      # void-immune; the mini-boss task adds its keys here
```

Change `banishable_types` (currently lines 1727-1735):

```python
    def banishable_types(self):
        """The distinct kinds among the monsters you can currently SEE -- the choices a
        Banishment offers. Returns [(key, count), ...], most numerous first. Empty if
        nothing is in sight (which is when you back out). Void-immune bosses are never
        offered -- the whole point of BOSS_KEYS is that the fight cannot be skipped."""
        seen = {}
        for m in self.level.monsters:
            if (not m.disguised and not m.hidden and self.visible(m.x, m.y)
                    and not self._void_immune(m)):
                seen[m.key] = seen.get(m.key, 0) + 1
        return sorted(seen.items(), key=lambda kv: (-kv[1], kv[0]))
```

Change `banish_type` (currently lines 1737-1751), the first two lines:

```python
    def banish_type(self, key):
        """Confirm the picker: unmake EVERY monster of `key` on the whole floor (not
        just the ones in sight) -- except a void-immune boss, which the word simply
        does not reach. No corpses, no loot, no credit. Ends the turn."""
        gone = [m for m in self.level.monsters
                if m.key == key and not self._void_immune(m)]
        if not gone:
            return False
```

(the rest of the method body is unchanged)

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.13 -m deathward.tests TestBossVoidImmunity -v`
Expected: PASS, all 4 tests.

- [ ] **Step 5: Run the full suite**

Run: `py -3.13 -m deathward.tests`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add deathward/world.py deathward/tests.py
git commit -m "fix(boss): void-immune monsters can no longer be removed by the banish scroll"
```

---

### Task 9: Reward drop wiring — Windfang and Shademail

**Files:**
- Modify: `deathward/items.py:731-738` (`roll_monster_loot`)
- Test: `deathward/tests.py`

**Interfaces:**
- Consumes: `roll_monster_loot(rng, depth, key)` (existing signature, unchanged).
- Produces: `roll_monster_loot(rng, depth, "syrinx")` always returns `[("gear", "windfang", 0), ("gear", "shade", 0)]`.

- [ ] **Step 1: Write the failing loot tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.13 -m deathward.tests TestSyrinxRewards -v`
Expected: FAIL — `roll_monster_loot` currently falls through to the generic `(0.25, 1)` default and rarely/never returns the exact expected list.

- [ ] **Step 3: Special-case her loot**

In `deathward/items.py`, change `roll_monster_loot` (currently lines 731-738):

```python
def roll_monster_loot(rng, depth, key):
    """What is left ON THE BODY. A corpse with treasure is a container -- you have to
    walk to it, stand on it, and spend the turn -- which means the fight is never
    quite over just because the thing stopped moving."""
    if key == "syrinx":
        # her whole reason for existing: Windfang and Shademail, guaranteed, every
        # time -- the two boss-reserved rewards share her death rather than being
        # split across two encounters (see the design spec's Identity & Theme).
        return [("gear", "windfang", 0), ("gear", "shade", 0)]
    chance, n = MONSTER_LOOT.get(key, (0.25, 1))
    if rng.random() >= chance:
        return []
    return [roll_loot(rng, depth) for _ in range(rng.randint(1, n))]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.13 -m deathward.tests TestSyrinxRewards -v`
Expected: PASS, both tests.

- [ ] **Step 5: Run the full suite**

Run: `py -3.13 -m deathward.tests`
Expected: PASS (this also re-confirms the pre-existing exclusion tests around Windfang/Shademail keep passing unchanged, since `FINDABLE_MAGICAL`/`FINDABLE_MAGICAL_ARMOUR` already excluded both)

- [ ] **Step 6: Commit**

```bash
git add deathward/items.py deathward/tests.py
git commit -m "feat(syrinx): guaranteed Windfang and Shademail drop on death"
```

---

### Task 10: Serialization (RUN_SAVE_VERSION bump) + blind-vs-omniscient determinism

**Files:**
- Modify: `deathward/config.py:61` (`RUN_SAVE_VERSION`)
- Test: `deathward/tests.py`

**Interfaces:**
- Consumes: `Monster.to_dict`/`from_dict` (Task 2), `Level.to_dict`/restore (existing, unchanged code — only the new `_MONSTER_STATE` fields need proving), `config.RUN_SAVE_VERSION`.
- Produces: nothing new for later tasks — this is the closing task.

- [ ] **Step 1: Write the failing Monster round-trip test**

```python
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
```

- [ ] **Step 2: Run tests to verify they pass already**

Run: `py -3.13 -m deathward.tests TestSyrinxSerialization -v`
Expected: PASS already — `_MONSTER_STATE` and `to_dict`/`from_dict` needed no changes beyond Task 2's field additions (every field is a plain scalar). This step is a proof, not a fix; if either test fails, it means a field was missed in `_MONSTER_STATE` back in Task 2 and must be added there.

- [ ] **Step 3: Write the failing suspend/resume integration test**

```python
    def test_a_hidden_syrinx_survives_suspend_and_resume(self):
        import json
        from .dungeon import Level
        codex = FakeSave()
        w = World(codex, seed=4)
        w.new_level(8)
        lv = w.level
        s = next(m for m in lv.monsters if m.key == "syrinx")
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.13 -m deathward.tests TestSyrinxSerialization.test_a_hidden_syrinx_survives_suspend_and_resume -v`
Expected: PASS already (this exercises the exact same generic `Level`/`Monster` serialization machinery Task 2 already made complete — this test is the proof called out explicitly by the design spec's "serialization risk" note, not a new fix).

- [ ] **Step 5: Bump `RUN_SAVE_VERSION` and prove it**

In `deathward/config.py`, change (currently line 61):

```python
# Bumped when the run-save (suspend/resume) serialization shape changes. A save
# whose run block carries a different version is discarded -- Continue falls back
# to a fresh run -- exactly as LAYOUT_VERSION discards a stale map. Bumped for
# Syrinx's new Monster fields (hidden/hidden_turns/pillar_x/pillar_y/retreating).
RUN_SAVE_VERSION = 3
```

```python
    def test_run_save_version_was_bumped_for_her_new_state(self):
        self.assertGreaterEqual(config.RUN_SAVE_VERSION, 3)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `py -3.13 -m deathward.tests TestSyrinxSerialization -v`
Expected: PASS, all 4 tests.

Run: `py -3.13 -m deathward.tests TestRunBlockPersistence -v`
Expected: PASS (these tests are version-relative — `config.RUN_SAVE_VERSION + 1` — so the bump does not break them)

- [ ] **Step 7: Write the failing blind-vs-omniscient determinism test**

```python
class TestSyrinxKnowledgeIsNotPower(unittest.TestCase):
    """Her whole loop -- hidden, telegraph, emerge, hunt, blow, stun, retreat --
    must play out identically whether the Kodex knows her or not. Only what is
    DRAWN may differ (see the project's core invariant)."""

    def _trace(self, codex):
        w = World(codex, seed=11)
        w.new_level(8)
        s = next(m for m in w.level.monsters if m.key == "syrinx")
        script = random.Random(99)
        trace = []
        for _ in range(60):
            dx, dy = script.choice([(0, -1), (0, 1), (-1, 0), (1, 0)])
            nx, ny = w.player.x + dx, w.player.y + dy
            if w.walkable(nx, ny) and not w.monster_at(nx, ny):
                w.player.x, w.player.y = nx, ny
                w.level.compute_fov(w.player.x, w.player.y)
            s.take_turn(w)
            trace.append((s.x, s.y, s.hidden, s.hidden_turns, s.retreating,
                         s.stunned, str(s.intent), s.hp, w.player.hp))
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
```

- [ ] **Step 8: Run test to verify it passes**

Run: `py -3.13 -m deathward.tests TestSyrinxKnowledgeIsNotPower -v`
Expected: PASS already — `_ai_syrinx` never reads `world.codex` anywhere (mirrors every other monster's AI). If this fails, it means some earlier task accidentally branched her behavior on Kodex state, which must be fixed before proceeding.

- [ ] **Step 9: Run the entire Syrinx test surface plus the full suite**

Run: `py -3.13 -m deathward.tests TestSyrinxIdentity TestSyrinxHiddenState TestSyrinxArena TestSyrinxHuntAndBlow TestSyrinxStunAndRetreat TestSyrinxSprite TestSyrinxResistances TestBossVoidImmunity TestSyrinxRewards TestSyrinxSerialization TestSyrinxKnowledgeIsNotPower -v`
Expected: PASS, every test.

Run: `py -3.13 -m deathward.tests`
Expected: PASS, full suite (666+ new tests, zero regressions).

- [ ] **Step 10: Commit**

```bash
git add deathward/config.py deathward/tests.py
git commit -m "feat(syrinx): bump RUN_SAVE_VERSION and prove suspend/resume + determinism"
```

---

## Self-Review

**1. Spec coverage** — walking the design spec section by section:

- *Identity & theme* → Task 1 (Template, flavor text in Kodex facts referencing wind/stone/breakable), Task 9 (Windfang+Shademail share her death).
- *Arena (6 pillars, scattered, cover)* → Task 3 (`syrinx_pillars`, 3×2 scattered layout).
- *No ambient monsters/chests in her room* → Task 3 (`_reserved_room` threading through `_free_tile`/hoard/orc-packs).
- *Hidden, off the grid, untargetable* → Task 2 (`monster_at`, `_firestorm`/thunderclap, render gating).
- *Forced emergence (turn budget)* → Task 2 (`SYRINX_HIDDEN_MAX`).
- *Telegraph, specific pillar, one turn, deterministic* → Task 2 (`self.intent = ("emerge", self.x, self.y)`, no Kodex read).
- *Emerge at telegraphed pillar, targetable, player's speed, never melee* → Task 2 (emergence sets `hidden=False` in place), Task 1 (`speed=100`), Task 4 (no melee code path exists at all — explicitly tested).
- *Hunt: actively seeks LOS* → Task 4 (`_step_toward` when not aligned/clear).
- *Blow: line_clear gate, chip damage + knockback, fizzles on blocked pillar* → Task 4 (telegraph+resolve, fizzle log), Task 5 (`_syrinx_knockback`, chip damage via `t.lo=1, t.hi=3`).
- *Stunned one turn, fully vulnerable* → Task 5 (`self.stunned`, reuses generic infrastructure).
- *Retreat to nearest untried pillar, reroute if blocked* → Task 5 (`_syrinx_retreat_target`, `_syrinx_path_blocked`).
- *Re-hide, budget resets* → Task 5.
- *Never melee-attacks* → Task 4 (explicit test with an adjacent-but-unaligned Syrinx).
- *Brittle, ~6 solid hits* → Task 1 (HP=30, `_assert_solid_hits`).
- *Fire-vulnerable (2.0×, `FIRE_SOURCES`)* → Task 7.
- *Immune to other status effects (poison/freeze/fear + weak/confuse as "and similar"), not physical/her own blow* → Task 7 (all identified application sites gated; her own knockback/chip damage untouched).
- *Void-immune (`BOSS_KEYS`)* → Task 8 (also closes a real pre-existing gap in the banish scroll, explicitly called out by the spec's own "Void Scimitar/banish scroll" wording).
- *Rewards: both drop on death* → Task 9.
- *New monster key excluded from normal spawn tables* → Task 1.
- *New arena-population function, must not clear stairs* → Task 3 (explicit reachability + `stairs is not None` tests).
- *Serialization risk called out explicitly* → Task 10 (round-trip + suspend/resume + `RUN_SAVE_VERSION` bump).
- *Testing: blind-vs-omniscient, telegraph correctness, hunt, blow resolution, forced emergence, retreat/re-route, fire/status/void immunity, reward drop, spawn exclusion* → covered across Tasks 1-10 as itemized above.
- *Out of scope: floor 15/Void Scimitar, exact balance numbers, ambient monsters/chests* → not touched; all numeric constants are named and justified (HP math shown in Task 1; other numbers picked as reasonable defaults per the spec's explicit "tuned during playtesting" allowance).

No gaps found.

**2. Placeholder scan** — searched for "TBD", "similar to Task N", "fill in", "handle appropriately", code-less steps. None found: every code-touching step shows complete, real code (including full method bodies re-shown whenever a later task modifies an earlier task's method, per the "no diff fragments" rule). The one deliberately incremental item — `_ai_syrinx`'s body growing across Tasks 2/4/5 — always shows the complete current method, and each intermediate version is fully functional and independently tested, not a stub.

**3. Type/signature consistency** — checked across tasks:
- `Monster.hidden`/`hidden_turns`/`pillar_x`/`pillar_y`/`retreating` — defined once in Task 2, used identically (attribute access, no renaming) in Tasks 3-10.
- `Level.syrinx_pillars()` — defined in Task 3, called identically (`world.level.syrinx_pillars()`) in Task 5's `_syrinx_retreat_target`, and directly in Task 3/9's tests.
- `Level._syrinx_arena()` — defined in Task 3, used by `syrinx_pillars()` and by Task 3's own tests; not called from any other task.
- `Level._reserved_room` — defined in Task 3, read only in Task 3's `_free_tile`/hoard/orc-pack code; not touched elsewhere.
- `world._syrinx_knockback(self, m)` — defined in Task 5, called as `world._syrinx_knockback(self)` from `_ai_syrinx` (Task 5) with matching signature.
- `world._status_immune(self, m)` — defined in Task 7, called identically from every gated site in Task 7 and from `traps.py`'s `_spike` as `world._status_immune(victim)`.
- `_syrinx_path_blocked(x0, y0, x1, y1, px, py)` — module-level, defined and called with matching positional signature in Task 5.
- `damage_multiplier(monster_key, source)` — Task 7's edit preserves the existing two-parameter signature and return contract (float multiplier), matching every existing call site (`hurt_monster`).
- `roll_monster_loot(rng, depth, key)` — Task 9's edit preserves the existing three-parameter signature and list-of-tuples return contract used by `kill_monster`.
- `config.SYRINX_HIDDEN_MAX/DEPTH/STUN_TURNS/PUSH_DIST/FIRE_MULT` — each introduced exactly once (Tasks 2/3/5/5/7 respectively), referenced by name (never redefined or magic-numbered) everywhere else.
- `BOSS_KEYS`/`STATUS_IMMUNE_KEYS` — both are module-level sets in `world.py`, non-overlapping in purpose (void vs. status), never conflated.

No inconsistencies found.
