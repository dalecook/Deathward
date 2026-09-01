# Mini-boss Arena Floors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rework floor 8 from an ordinary dungeon floor with Syrinx standing in the biggest room into a purpose-built sealed arena that she gates — three one-way gates, an antechamber to prepare in, a fixed 31×23 columned hall, and a trapped floor her shove throws you across.

**Architecture:** Floor 8 branches away from `_cut_stone` into a bespoke cutter that lays two rooms (antechamber, arena) joined by a one-tile mouth. Three gates reuse behaviour that already exists: `ascend()` already refuses at depth 1, `descend()` already refuses on the Warden's floor, and `sprites.entrance()` is already a shut portcullis. Her shove starts calling `_enter_tile()` on every tile it drags the player over, which turns the existing trap system into the fight's damage source. She is no longer placed at generation; she spawns when the player commits through the mouth.

**Tech Stack:** Python 3.11+, pygame, standard library only. No new dependencies. Tests are `unittest`, all in the single file `deathward/tests.py`.

**Spec:** `docs/superpowers/specs/2026-09-01-miniboss-arena-floors-design.md`

## Global Constraints

- **Standard library + pygame only.** No new dependencies, ever, in this project.
- **Run the suite with `py -3.13 -m deathward.tests`.** It is safe: `setUpModule` (tests.py:44) redirects `config.SAVE_PATH` to a temp scratch file before any test runs, so the suite cannot touch the player's real save. Do not add a test that writes to `config.SAVE_PATH` directly.
- **Run one test with** `py -3.13 -m unittest deathward.tests.ClassName.test_name -v`.
- **718 tests pass on `main` today.** Every task must end with the whole suite green.
- **Two rngs, and the difference matters.** `self.lrng` is the STONE (seeded per *game* from `codex.layout_seed(depth)`) — rooms, corridors, stairs, traps. `self.rng` is the LIVING (per *run*) — monsters, loot, chests. Arena geometry and arena traps use `lrng`. Getting this backwards breaks the game's whole persistence model.
- **Balance numbers are config constants, not literals.** They are deliberately untested and tuned by playing. Never write a test that asserts a specific balance value.
- **Branch:** `feature/miniboss-arena-floors`, already created. Commit after every task.
- **Tile constants** are `WALL, FLOOR = 0, 1` in `deathward/dungeon.py`.

---

## File Structure

| File | Responsibility for this feature |
|---|---|
| `deathward/config.py` | New arena geometry + balance constants. `RUN_SAVE_VERSION` bump. |
| `deathward/dungeon.py` | The bespoke floor-8 cutter, the pillar lattice, the arena trap pass, the gate/spawn state and its serialization. |
| `deathward/world.py` | The three gates' rules, the arrival sequence, the reworked knockback, scroll containment, unlocking the stairs on her death. |
| `deathward/monsters.py` | One new `"arrive"` beat at the top of `_ai_syrinx`. |
| `deathward/render.py` | Portcullis drawn on the three gates. |
| `deathward/tests.py` | All tests. Existing `TestSyrinx*` classes get updated in the tasks that change their assumptions. |

---

### Task 1: The shove springs what it drags you across

Independent of everything else — it is a fix to the existing fight and is valuable on its own. Do it first.

**Files:**
- Modify: `deathward/config.py:178`
- Modify: `deathward/world.py:763-778` (`_syrinx_knockback`)
- Test: `deathward/tests.py` (new class `TestSyrinxShoveSpringsTraps`, add at the end of the file)

**Interfaces:**
- Consumes: nothing.
- Produces: `config.SYRINX_PUSH_DIST` (int, now 5). `World._syrinx_knockback(m)` unchanged signature, new behaviour: springs every trap crossed, halts on death or on being stuck.

- [ ] **Step 1: Write the failing test**

Add at the end of `deathward/tests.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -3.13 -m unittest deathward.tests.TestSyrinxShoveSpringsTraps -v`

Expected: FAIL. `test_shove_springs_every_trap_it_drags_you_over` fails on `assertTrue(all(t.sprung ...))` — the traps are never sprung today.

- [ ] **Step 3: Raise the push distance**

In `deathward/config.py`, change line 178:

```python
SYRINX_PUSH_DIST  = 5      # tiles the gust shoves the player back. long enough that
                           # the slide crosses real floor -- and her arena's floor is
                           # trapped, which is where her damage actually comes from.
```

- [ ] **Step 4: Make the shove spring what it crosses**

Replace `_syrinx_knockback` in `deathward/world.py` (currently lines 763-778) with:

```python
    def _syrinx_knockback(self, m):
        """The gust: shove the player straight back along the line from her to you,
        tile by tile, stopping at the first wall or body. Reposition is the point --
        it can push you out of the cover you were using, or off her line entirely.

        And the slide is not free. Each tile you are dragged over is a tile you
        ENTER, so its trap fires: her own blow is 1-3 against 26 HP, and the floor
        of her hall is what actually kills you. Three things stop the slide early --
        stone, a body, and the spike pit, which you fall into rather than skate over
        (it sets player.stuck). A player killed partway is not dragged any further.
        """
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
            self._enter_tile()
            if p.hp <= 0 or p.stuck:
                break
        self.level.compute_fov(p.x, p.y)
```

- [ ] **Step 5: Run the new tests**

Run: `py -3.13 -m unittest deathward.tests.TestSyrinxShoveSpringsTraps -v`
Expected: PASS, 3 tests.

- [ ] **Step 6: Run the whole suite**

Run: `py -3.13 -m deathward.tests`
Expected: OK. If a existing Syrinx test asserts a 2-tile push, it was asserting a balance constant — read it, and if it hard-codes `2` rather than `config.SYRINX_PUSH_DIST`, change it to read the constant. Do not change the constant back.

- [ ] **Step 7: Commit**

```bash
git add deathward/config.py deathward/world.py deathward/tests.py
git commit -m "fix(syrinx): her shove springs every trap it drags you across, and reaches 5 tiles"
```

---

### Task 2: The arena floor — bespoke cutter, geometry, pillar lattice

Floor 8 stops using `_cut_stone`. She is still placed at generation in this task (Task 6 moves her to the commit); keeping her placement here is what lets the suite stay green between tasks.

**Files:**
- Modify: `deathward/config.py` (append to the Syrinx block near line 175-179)
- Modify: `deathward/dungeon.py` — `Level.__init__` (~line 198-231), `_cut_stone` (line 350), `_generate` (line 441), `_syrinx_arena` (line 790), `syrinx_pillars` (line 798), `_carve_syrinx_pillars` (line 824)
- Test: `deathward/tests.py` (new class `TestArenaFloorGeometry`; update `TestSyrinxArena`)

**Interfaces:**
- Consumes: `config.SYRINX_DEPTH` (existing, 8).
- Produces:
  - `config.ARENA_W = 31`, `ARENA_H = 23`, `ARENA_PILLAR_PITCH = 6`, `ARENA_PILLAR_COLS = 5`, `ARENA_PILLAR_ROWS = 4`, `ARENA_MARGIN_X = 3`, `ARENA_MARGIN_Y = 2`, `ANTE_W = 9`, `ANTE_H = 7`
  - `Level.ante_room` (`Room` or `None`), `Level.arena_room` (`Room` or `None`), `Level.mouth` (`(x, y)` or `None`)
  - `Level.is_arena_floor()` -> bool
  - `Level.boss_arrival()` -> `(x, y)`
  - `Level.syrinx_pillars()` -> `list[(x, y)]` — now the 20-pillar lattice (name kept: `monsters.py` calls it)
  - `Level._syrinx_arena()` -> `Room` — now returns `self.arena_room` (name kept: `monsters.py` leash calls it)

- [ ] **Step 1: Write the failing test**

Add at the end of `deathward/tests.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -3.13 -m unittest deathward.tests.TestArenaFloorGeometry -v`
Expected: FAIL with `AttributeError: 'Level' object has no attribute 'ante_room'`.

- [ ] **Step 3: Add the geometry constants**

In `deathward/config.py`, in the Syrinx block (after line 179), add:

```python
# --- floor 8: her hall ----------------------------------------------------
# The geometry is FIXED -- cut identically in every game -- and only the hazards are
# re-dealt per game. 31x23 is ~2.7x the largest room the generator can make (a 20x13
# hall), because every part of this fight needs open floor: pillars are walls, and the
# shove stops at the first one, so a dense lattice would cut every push short and the
# trapped floor would never get crossed.
ARENA_W, ARENA_H          = 31, 23
ARENA_PILLAR_PITCH        = 6      # one column every 6th tile, both axes
ARENA_PILLAR_COLS         = 5
ARENA_PILLAR_ROWS         = 4      # 5 x 4 = twenty single-tile columns
ARENA_MARGIN_X            = 3      # floor between the outer columns and the walls
ARENA_MARGIN_Y            = 2
ANTE_W, ANTE_H            = 9, 7   # the prep room. a vendor stands here one day.
```

Check the arithmetic: columns span `(5-1)*6+1 = 25`, plus `2*3` margin = **31**. Rows span `(4-1)*6+1 = 19`, plus `2*2` = **23**.

- [ ] **Step 4: Add the new Level attributes**

In `deathward/dungeon.py`, in `Level.__init__`, immediately after the `self._reserved_room = None` line (~line 213), add:

```python
        # Floor 8 only: her hall. All None elsewhere, and `is_arena_floor()` is the
        # single check every arena rule keys off.
        self.ante_room = None      # the prep room you arrive in
        self.arena_room = None     # her hall
        self.mouth = None          # the one tile joining them
```

- [ ] **Step 5: Write the cutter**

In `deathward/dungeon.py`, add these methods to `Level`, immediately before `_syrinx_arena` (line 790):

```python
    def is_arena_floor(self):
        """The one check every gate, seal and reveal keys off."""
        return self.depth == config.SYRINX_DEPTH

    def _cut_arena_floor(self, codex):
        """Floor 8 is not a dungeon floor. There is no room generator here, no
        corridors, no loops -- just her hall and the room you steady yourself in
        before you walk into it.

        Cut from LRNG-free arithmetic on purpose: unlike every other floor, this
        geometry does not vary between games. What varies is the hazards, which
        _install_arena_traps deals from lrng exactly as ordinary traps are dealt.
        """
        arena = Room(2 + config.ANTE_W + 1, 2, config.ARENA_W, config.ARENA_H)
        # the two rooms share a centre line, so the mouth is a straight step through
        ante = Room(2, arena.cy - config.ANTE_H // 2, config.ANTE_W, config.ANTE_H)

        self._carve_room(ante)
        self._carve_room(arena)
        self.rooms = [ante, arena]
        self.ante_room, self.arena_room = ante, arena
        # kept in step with the old reserved-room contract: nothing ambient in her hall
        self._reserved_room = arena

        self.mouth = (arena.x - 1, arena.cy)
        self.grid[self.mouth[1]][self.mouth[0]] = FLOOR

        self.gate_room = ante
        self.entrance = (ante.cx, ante.cy)
        self.start = self.entrance
        # the way down sits at the far end of the hall, opposite the mouth
        self.stairs = (arena.x + arena.w - 2, arena.cy)

        self._carve_syrinx_pillars()
        # Task 3 adds the hazard pass here.

    def boss_arrival(self):
        """Where she materialises when you commit: the far end of the hall, ~27 tiles
        from the mouth and far outside FOV_RADIUS. The room shows you its shape when
        the gate falls; it never shows you her."""
        a = self.arena_room
        return (a.x + a.w - 4, a.cy)
```

- [ ] **Step 6: Point the pillar and arena helpers at the lattice**

In `deathward/dungeon.py`, replace `_syrinx_arena` (line 790) and `syrinx_pillars` (line 798) — everything from `def _syrinx_arena` down to the end of `syrinx_pillars`, i.e. lines 790-822 — with:

```python
    def _syrinx_arena(self):
        """Her hall. Name kept because monsters.py leashes her hunt to it
        (`world.level._syrinx_arena().contains(...)`)."""
        return self.arena_room

    def syrinx_pillars(self):
        """The twenty columns: her hiding spots, the surface her emergence telegraph
        paints on, and the only line-of-sight cover you have against her blow.

        A 5x4 lattice on a 6-tile pitch. Sparse on purpose -- twenty columns in a room
        this size is a cathedral, not a thicket. Pillars are WALL tiles and the shove
        stops at the first one, so a tighter pitch would cut every push short and the
        trapped floor she throws you across would never get crossed. It also means she
        has to COMMIT to reach a hiding place, and is exposed while she travels.

        Never the stairs, the mouth, or her own arrival tile.
        """
        a = self.arena_room
        if a is None:
            return []
        xs = [a.x + config.ARENA_MARGIN_X + i * config.ARENA_PILLAR_PITCH
              for i in range(config.ARENA_PILLAR_COLS)]
        ys = [a.y + config.ARENA_MARGIN_Y + j * config.ARENA_PILLAR_PITCH
              for j in range(config.ARENA_PILLAR_ROWS)]
        blocked = {self.stairs, self.mouth, self.boss_arrival()}
        return [(x, y) for y in ys for x in xs if (x, y) not in blocked]
```

Leave `_carve_syrinx_pillars` (line 824) exactly as it is — it iterates `syrinx_pillars()` and so picks up the lattice for free, on both the generate and the restore path.

- [ ] **Step 7: Route floor 8 to the new cutter**

In `deathward/dungeon.py`, at the very top of `_cut_stone` (line 350), insert before `rng = self.lrng`:

```python
        if self.is_arena_floor():
            self._cut_arena_floor(codex)
            return
```

And in `_generate` (line 441), replace the `elif self.depth == config.SYRINX_DEPTH:` branch (lines 450-455) with:

```python
        elif self.is_arena_floor():
            # no ordinary population at all: her hall has no ambient monsters, no
            # chests, no gold. The floor's whole content is her, and its hazards.
            self._populate_syrinx()
```

- [ ] **Step 8: Run the new tests**

Run: `py -3.13 -m unittest deathward.tests.TestArenaFloorGeometry -v`
Expected: PASS, 9 tests.

- [ ] **Step 9: Run the whole suite and fix the existing arena tests**

Run: `py -3.13 -m deathward.tests`

Expect failures in `TestSyrinxArena` (tests.py:9999) and possibly `TestKnowledgeIsNotPower`. Fix them to match the new floor:
- `test_floor_eight_keeps_its_stairs` — still valid, must still pass.
- `test_her_arena_has_no_ambient_monster_or_chest` — still valid and now trivially true.
- `test_only_floor_eight_reserves_a_room` — still valid.
- Any test asserting six pillars must become `config.ARENA_PILLAR_COLS * config.ARENA_PILLAR_ROWS` minus whatever `syrinx_pillars()` excludes; prefer asserting `len(...) == len(set(...))` and that each is a WALL tile rather than a hard count, since `TestArenaFloorGeometry` already pins the count.
- Any test that assumed floor 8 has many rooms or ambient content must be updated to the two-room hall.

Do not weaken an assertion to make it pass — if a test's *intent* no longer applies to this floor, rewrite it to state the new intent, and say so in the commit message.

- [ ] **Step 10: Commit**

```bash
git add deathward/config.py deathward/dungeon.py deathward/tests.py
git commit -m "feat(arena): floor 8 becomes her hall -- bespoke cutter, antechamber, mouth, 20-pillar lattice"
```

---

### Task 3: The hazards

**Files:**
- Modify: `deathward/config.py` (append to the arena block)
- Modify: `deathward/dungeon.py` — `_install_arena_traps` (the stub from Task 2)
- Test: `deathward/tests.py` (new class `TestArenaHazards`)

**Interfaces:**
- Consumes: `Level.arena_room`, `Level.mouth`, `Level.boss_arrival()`, `Level.syrinx_pillars()` from Task 2.
- Produces: `config.ARENA_TRAPS` (int, 50), `dungeon.ARENA_TRAP_POOL` (tuple of 4 trap keys), a filled-in `Level._install_arena_traps()`.

- [ ] **Step 1: Write the failing test**

Add at the end of `deathward/tests.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -3.13 -m unittest deathward.tests.TestArenaHazards -v`
Expected: FAIL — `len(lvl.traps)` is 0, the stub places nothing.

- [ ] **Step 3: Add the constant**

In `deathward/config.py`, append to the arena block from Task 2:

```python
# ~50 hazards across ~690 floor tiles (~7%), so a five-tile shove crosses one about a
# third of the time and occasionally two. The minefield DEPLETES as the fight runs on:
# dart, gas and glyph are one-shot once sprung. The spike pit is not -- it re-fires
# forever and costs you a turn climbing out, which is a turn she is winding up in.
ARENA_TRAPS = 50
```

- [ ] **Step 4: Add the roster and the placement pass**

In `deathward/dungeon.py`, near the top with the other module constants (beside `FILLER_CLASSES`, ~line 55), add:

```python
# Her hall's hazards. No alarm rune: wake_all() in a sealed one-monster room wakes a
# boss who is already hunting you, so it is the one trap that means nothing here.
ARENA_TRAP_POOL = ("dart", "spike", "gas", "glyph")
```

Then, in `_cut_arena_floor`, replace the `# Task 3 adds the hazard pass here.` comment with the call:

```python
        self._install_arena_traps()
```

And add the method itself, immediately after `boss_arrival`:

```python
    def _install_arena_traps(self):
        """Deal her hall's hazards. LRNG, like every other trap in the game: cut into
        the stone once per GAME, so they sit in the same tiles on every re-entry and
        move only when a new dungeon is cut.

        Nothing lands on a pillar, the stairs, the mouth, her arrival tile, or within
        one tile of the threshold -- stepping through the gate straight onto a fire
        glyph is not a fight, it is a coin toss.
        """
        rng = self.lrng
        a = self.arena_room
        forbidden = set(self.syrinx_pillars())
        forbidden |= {self.stairs, self.mouth, self.boss_arrival()}
        tx, ty = a.x, a.cy                       # the tile you step in on
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                forbidden.add((tx + dx, ty + dy))

        taken = set()
        for _ in range(4000):
            if len(taken) >= config.ARENA_TRAPS:
                break
            x = rng.randint(a.x, a.x + a.w - 1)
            y = rng.randint(a.y, a.y + a.h - 1)
            if self.grid[y][x] != FLOOR:
                continue
            if (x, y) in forbidden or (x, y) in taken:
                continue
            taken.add((x, y))
            self.traps.append(Trap(rng.choice(ARENA_TRAP_POOL), x, y))
```

Confirm `Trap` is already imported at the top of `dungeon.py` (it is — `_install_traps` uses it).

- [ ] **Step 5: Run the new tests**

Run: `py -3.13 -m unittest deathward.tests.TestArenaHazards -v`
Expected: PASS, 6 tests.

- [ ] **Step 6: Run the whole suite**

Run: `py -3.13 -m deathward.tests`
Expected: OK.

- [ ] **Step 7: Commit**

```bash
git add deathward/config.py deathward/dungeon.py deathward/tests.py
git commit -m "feat(arena): deal ~50 hazards into her hall, no alarm rune, none on the threshold"
```

---

### Task 4: Gate state and its serialization

**Files:**
- Modify: `deathward/config.py:62` (`RUN_SAVE_VERSION`)
- Modify: `deathward/dungeon.py` — `Level.__init__`, `_cut_arena_floor`, `to_dict` (line 499), `_restore` (line 466)
- Test: `deathward/tests.py` (new class `TestArenaGateState`)

**Interfaces:**
- Consumes: Task 2's `Level.is_arena_floor()`, `Level.mouth`, `Level.arena_room`.
- Produces: `Level.mouth_sealed` (bool), `Level.stairs_locked` (bool), `Level.boss_spawned` (bool), all round-tripping through `to_dict`/`_restore`. `config.RUN_SAVE_VERSION == 4`.

- [ ] **Step 1: Write the failing test**

Add at the end of `deathward/tests.py`:

```python
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
```

Note the restore idiom: this project resumes a floor by constructing a `Level` directly — `Level(depth, rng, codex, restore=blob)` — exactly as `TestSyrinxSerialization` (tests.py:10548) already does. `World.new_level(depth, arrive=...)` has no `restore` parameter.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -3.13 -m unittest deathward.tests.TestArenaGateState -v`
Expected: FAIL with `AttributeError: 'Level' object has no attribute 'mouth_sealed'`.

- [ ] **Step 3: Bump the save version**

In `deathward/config.py` line 62:

```python
RUN_SAVE_VERSION = 4     # 4: floor 8's gate state (mouth_sealed/stairs_locked/boss_spawned)
```

- [ ] **Step 4: Add the flags**

In `deathward/dungeon.py`, in `Level.__init__`, extend the block added in Task 2:

```python
        self.ante_room = None      # the prep room you arrive in
        self.arena_room = None     # her hall
        self.mouth = None          # the one tile joining them
        # the three gates, as state. All false/open elsewhere in the dungeon.
        self.mouth_sealed = False  # has the gate fallen behind you
        self.stairs_locked = False # is the way down barred (until she dies)
        self.boss_spawned = False  # has she arrived
```

In `_cut_arena_floor`, after setting `self.stairs`, add:

```python
        self.stairs_locked = True      # it opens when she does not get up
```

- [ ] **Step 5: Serialize them**

In `deathward/dungeon.py` `to_dict` (line 499), add three entries before the closing brace:

```python
            "mouth_sealed": self.mouth_sealed,
            "stairs_locked": self.stairs_locked,
            "boss_spawned": self.boss_spawned,
```

In `_restore` (line 466), inside the `if self.depth == config.SYRINX_DEPTH:` block that already calls `_carve_syrinx_pillars()`, replace that block with:

```python
        if self.is_arena_floor():
            # her pillar WALL tiles are not part of the stone _cut_stone lays down --
            # they must be re-carved here, exactly as the generate path does, or a
            # resumed floor 8 loses her arena's terrain.
            self._carve_syrinx_pillars()
            self.mouth_sealed = data.get("mouth_sealed", False)
            self.stairs_locked = data.get("stairs_locked", True)
            self.boss_spawned = data.get("boss_spawned", False)
            if self.mouth_sealed:
                # a gate you shut stays shut through a suspend
                mx, my = self.mouth
                self.grid[my][mx] = WALL
```

- [ ] **Step 6: Run the new tests**

Run: `py -3.13 -m unittest deathward.tests.TestArenaGateState -v`
Expected: PASS, 5 tests.

- [ ] **Step 7: Run the whole suite**

Run: `py -3.13 -m deathward.tests`

Expected: OK, except `tests.py:10602` (`assertGreaterEqual(config.RUN_SAVE_VERSION, 3)`) which still passes, and any test asserting the exact version number — update those to 4.

- [ ] **Step 8: Commit**

```bash
git add deathward/config.py deathward/dungeon.py deathward/tests.py
git commit -m "feat(arena): gate state (mouth/stairs/spawn) with save round-trip, RUN_SAVE_VERSION 4"
```

---

### Task 5: The three gates

**Files:**
- Modify: `deathward/world.py` — `ascend` (line 285), `descend` (line 258), `_enter_tile` (line 2181), `kill_monster` (line 814)
- Test: `deathward/tests.py` (new class `TestArenaGates`)

**Interfaces:**
- Consumes: Task 4's `Level.mouth_sealed`, `stairs_locked`, `Level.is_arena_floor()`, `Level.arena_room`, `Level.mouth`.
- Produces: `World._arena_commit()` — called from `_enter_tile`, seals the mouth and reveals the hall's stone the first time the player stands in the arena. Stairs unlock inside `kill_monster` when a `syrinx` dies.

- [ ] **Step 1: Write the failing test**

Add at the end of `deathward/tests.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -3.13 -m unittest deathward.tests.TestArenaGates -v`
Expected: FAIL — `test_the_way_up_is_stone_the_moment_you_arrive` fails because `ascend()` currently returns True on floor 8.

- [ ] **Step 3: Seal the way up**

In `deathward/world.py` `ascend()` (line 285), insert immediately after the "not standing on the way up" check and before `if self.depth <= 1:`:

```python
        if self.level.is_arena_floor():
            # the same rule as floor 1's front gate, one floor deeper: you came down
            # into her hall, and the hall does not give anything back.
            self.log("The gate you came down through is stone. There is no way back.",
                     config.BLOOD)
            return False
```

- [ ] **Step 4: Bar the way down**

In `deathward/world.py` `descend()` (line 258), insert immediately after the "not standing on the stairs" check:

```python
        if self.level.stairs_locked:
            self.log("The way down is barred. Something in this hall is holding it "
                     "shut.", config.BLOOD)
            return False
```

- [ ] **Step 5: Seal the mouth and reveal the hall**

In `deathward/world.py`, add this method immediately before `_enter_tile` (line 2181):

```python
    def _arena_commit(self):
        """The first time you stand in her hall, the gate falls behind you and the
        room shows you what it is.

        The reveal touches `explored` and NEVER `seen`. That distinction is the whole
        game: `explored` is the stone you have seen (a Scroll of Mapping fills it in),
        `seen` is the contents you have laid eyes on, and nothing but your own line of
        sight ever sets it. So you get the shape of the hall entire -- 31x23 of it,
        the columns marching away -- and not one thing that is standing in it. The
        hazards are stone but UNDISCOVERED, and an undiscovered trap draws as clean
        floor, so this defuses nothing: it is a beautifully lit room you still cannot
        cross.
        """
        lvl = self.level
        if not lvl.is_arena_floor() or lvl.mouth_sealed:
            return
        if lvl.arena_room is None or not lvl.arena_room.contains(self.player.x,
                                                                 self.player.y):
            return
        mx, my = lvl.mouth
        lvl.grid[my][mx] = WALL
        lvl.mouth_sealed = True
        self.log("The gate falls behind you. Stone, and no seam.", config.BLOOD)
        self.shake(8)

        a = lvl.arena_room
        for y in range(max(0, a.y - 1), min(lvl.h, a.y + a.h + 1)):
            for x in range(max(0, a.x - 1), min(lvl.w, a.x + a.w + 1)):
                lvl.explored[y][x] = True
        lvl.explored[my][mx] = True
```

`WALL` must be importable here — check the existing imports at the top of `world.py`; `dungeon` symbols are already used (e.g. `player_submerged` compares against `WALL`), so no new import should be needed.

Then, in `_enter_tile`, make it the first thing that happens:

```python
    def _enter_tile(self):
        p = self.player
        self._arena_commit()      # stepping into her hall is the commitment
        t = self.level.trap_at(p.x, p.y)
        if t and not (t.sprung and t.key in ("gas", "alarm", "glyph", "dart")):
            if self.player_hidden():
                self.break_stealth()   # springing a trap gives you away, invisible or not
            t.trigger(self, p)
```

- [ ] **Step 6: Open the way down when she dies**

In `deathward/world.py` `kill_monster` (line 814), immediately after `self.level.monsters.remove(m)`:

```python
        # the gate answers to her death, not to who dealt it -- a fire glyph counts.
        if m.key == "syrinx" and self.level.stairs_locked:
            self.level.stairs_locked = False
            sx, sy = self.level.stairs
            self.log("Somewhere behind you, the way down grinds open.", config.STAIRS)
            self.add_fx("pulse", sx, sy, color=config.STAIRS, life=1.2)
```

- [ ] **Step 7: Run the new tests**

Run: `py -3.13 -m unittest deathward.tests.TestArenaGates -v`
Expected: PASS, 9 tests.

- [ ] **Step 8: Run the whole suite**

Run: `py -3.13 -m deathward.tests`
Expected: OK.

- [ ] **Step 9: Commit**

```bash
git add deathward/world.py deathward/tests.py
git commit -m "feat(arena): three one-way gates -- arrival seals, mouth seals on commit, stairs open on her death"
```

---

### Task 6: She arrives when you commit

**Files:**
- Modify: `deathward/dungeon.py` — `_generate` (the arena branch), remove `_populate_syrinx`'s monster placement
- Modify: `deathward/world.py` — `_arena_commit`
- Modify: `deathward/monsters.py` — `_ai_syrinx` (line 724)
- Test: `deathward/tests.py` (new class `TestArenaBossArrival`; update `TestSyrinxArena.test_floor_eight_places_exactly_one_hidden_syrinx`)

**Interfaces:**
- Consumes: Task 5's `World._arena_commit()`, Task 2's `Level.boss_arrival()`, Task 4's `Level.boss_spawned`.
- Produces: `World._spawn_arena_boss()`. A new `("arrive", x, y)` intent handled at the top of `Monster._ai_syrinx`.

- [ ] **Step 1: Write the failing test**

Add at the end of `deathward/tests.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -3.13 -m unittest deathward.tests.TestArenaBossArrival -v`
Expected: FAIL — `test_the_hall_is_empty_until_you_step_into_it` finds her, because generation still places her.

- [ ] **Step 3: Stop placing her at generation**

In `deathward/dungeon.py`, replace `_populate_syrinx` (line 832) with:

```python
    def _populate_syrinx(self):
        """Nothing but her terrain. She is not in the hall until the player commits to
        it -- World._arena_commit places her, so that a suspend in the antechamber
        resumes to an empty room and a suspend mid-fight resumes to her exactly where
        she stood."""
        self._carve_syrinx_pillars()
```

- [ ] **Step 4: Spawn her on commit**

In `deathward/world.py`, add this method immediately after `_arena_commit`, and call it as the last line of `_arena_commit`:

```python
    def _spawn_arena_boss(self):
        """She materialises at the far end of the hall, visible -- and ~27 tiles away,
        far outside FOV_RADIUS, so 'visible' is a fact about her state and not about
        what you saw. She holds one turn (the "arrive" intent) and then goes to
        ground. The first thing you ever actually learn about her is whatever she
        chooses to show you.
        """
        lvl = self.level
        if lvl.boss_spawned:
            return
        ax, ay = lvl.boss_arrival()
        m = Monster("syrinx", ax, ay)
        m.hidden = False                    # Monster.__init__ starts her hidden
        m.intent = ("arrive", ax, ay)
        m.pillar_x, m.pillar_y = ax, ay
        lvl.monsters.append(m)
        lvl.boss_spawned = True
        self.add_fx("arrive", ax, ay, color=m.t.color, life=0.6)
```

Add the call at the end of `_arena_commit`:

```python
        self._spawn_arena_boss()
```

Confirm `Monster` is already imported in `world.py` (it is — `_populate` and the restore path construct them).

- [ ] **Step 5: Give her the held turn**

In `deathward/monsters.py`, in `_ai_syrinx` (line 724), insert immediately after the `RANGE = 9` line and before `if self.hidden:`:

```python
        if self.intent and self.intent[0] == "arrive":
            # the held beat: she has just come out of nothing at the far end of the
            # hall. One turn standing, then she turns for a column. If the player is
            # somehow close enough to witness it, they have been taught her whole
            # mechanic for the price of one turn.
            self.intent = None
            self.retreating = True
            return
```

Also update the docstring's numbered list: add `0. ARRIVE: one held turn on materialising, then straight to RETREAT.` above item 1.

- [ ] **Step 6: Run the new tests**

Run: `py -3.13 -m unittest deathward.tests.TestArenaBossArrival -v`
Expected: PASS, 7 tests.

- [ ] **Step 7: Run the whole suite and update the old placement test**

Run: `py -3.13 -m deathward.tests`

`TestSyrinxArena.test_floor_eight_places_exactly_one_hidden_syrinx` (tests.py:10000) will now fail — its premise is gone. Replace it with:

```python
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
```

Fix any other test that assumed generation-time placement the same way.

- [ ] **Step 8: Commit**

```bash
git add deathward/dungeon.py deathward/world.py deathward/monsters.py deathward/tests.py
git commit -m "feat(arena): she materialises at the far end when you commit, holds a turn, goes to ground"
```

---

### Task 7: The scrolls stop being an exit

**Files:**
- Modify: `deathward/dungeon.py` — add `Level.tile_is_sealed_off(x, y)`
- Modify: `deathward/world.py` — the `"blink"` effect (line 1896), `valid_teleport` (line 1768)
- Test: `deathward/tests.py` (new class `TestArenaScrollContainment`)

**Interfaces:**
- Consumes: Task 4's `Level.mouth_sealed`, Task 2's `Level.ante_room`.
- Produces: `Level.tile_is_sealed_off(x, y)` -> bool.

- [ ] **Step 1: Write the failing test**

Add at the end of `deathward/tests.py`:

```python
class TestArenaScrollContainment(unittest.TestCase):
    """Escape and Teleport work perfectly well inside her hall -- she shoves you away
    and is vulnerable for exactly one turn after her blow, so an aimed jump is the
    gap-closer that turns her stun into damage. What they are not is an exit. The
    antechamber leaves the destination pool the moment the mouth shuts, because the
    floor has no other way out and stranding the player there is a softlock."""

    def _committed(self):
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=1)
        w.new_level(8)
        a = w.level.arena_room
        w.player.x, w.player.y = a.x, a.cy
        w._enter_tile()
        return w

    def test_escape_never_drops_you_in_the_sealed_antechamber(self):
        w = self._committed()
        ante = w.level.ante_room
        for _ in range(150):
            w.player.x, w.player.y = w.level.arena_room.cx, w.level.arena_room.cy
            w._apply_effect("blink")
            self.assertFalse(ante.contains(w.player.x, w.player.y),
                             "UUL must never roll the sealed room")

    def test_teleport_refuses_the_sealed_antechamber(self):
        w = self._committed()
        ante = w.level.ante_room
        for y in range(ante.y, ante.y + ante.h):
            for x in range(ante.x, ante.x + ante.w):
                w.level.explored[y][x] = True
                self.assertFalse(w.valid_teleport(x, y),
                                 "the gate does not answer")

    def test_teleport_still_works_inside_the_hall(self):
        w = self._committed()
        a = w.level.arena_room
        tx, ty = a.cx, a.cy
        w.level.explored[ty][tx] = True
        self.assertTrue(w.valid_teleport(tx, ty))

    def test_the_antechamber_is_fine_before_you_commit(self):
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=1)
        w.new_level(8)
        ante = w.level.ante_room
        w.level.explored[ante.cy][ante.cx + 1] = True
        w.player.x, w.player.y = ante.x, ante.y
        self.assertTrue(w.valid_teleport(ante.cx + 1, ante.cy))

    def test_ordinary_floors_are_unaffected(self):
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=1)
        w.new_level(5)
        self.assertFalse(w.level.tile_is_sealed_off(w.level.stairs[0],
                                                    w.level.stairs[1]))
```

The scroll-effect dispatcher is `World._apply_effect(effect)` (world.py:1861) — the `elif effect == "blink":` chain at line 1896 lives inside it.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -3.13 -m unittest deathward.tests.TestArenaScrollContainment -v`
Expected: FAIL with `AttributeError: 'Level' object has no attribute 'tile_is_sealed_off'`.

- [ ] **Step 3: Add the query**

In `deathward/dungeon.py`, beside `is_arena_floor`, add:

```python
    def tile_is_sealed_off(self, x, y):
        """Somewhere the player must never be put once the mouth has shut. Floor 8's
        only exits are the way up (stone on arrival) and the way down (barred, and
        inside the hall) -- so a scroll that dropped you back in the antechamber would
        leave no legal move at all. That is a softlock, and this game guarantees the
        dungeon is always completable."""
        return (self.mouth_sealed and self.ante_room is not None
                and self.ante_room.contains(x, y))
```

- [ ] **Step 4: Contain the Escape scroll**

In `deathward/world.py`, in the `elif effect == "blink":` branch (line 1896), add the check inside the retry loop, right after the tile is picked:

```python
            for _ in range(200):
                r = self.rng.choice(self.level.rooms)
                x = self.rng.randint(r.x, r.x + r.w - 1)
                y = self.rng.randint(r.y, r.y + r.h - 1)
                if self.level.tile_is_sealed_off(x, y):
                    continue          # never back through a gate that has shut
                if self.walkable(x, y) and not self.monster_at(x, y):
```

(the rest of the branch is unchanged)

- [ ] **Step 5: Contain the Teleport scroll**

In `deathward/world.py`, `valid_teleport` (line 1768):

```python
    def valid_teleport(self, x, y):
        """A spot you may jump to: somewhere you have SEEN, that is open floor, that
        has nothing standing on it -- and that is not on the far side of a gate that
        has already shut behind you."""
        return (self.in_bounds(x, y) and self.level.explored[y][x]
                and self.walkable(x, y) and not self.monster_at(x, y)
                and not self.vendor_at(x, y)
                and not self.level.tile_is_sealed_off(x, y)
                and (x, y) != (self.player.x, self.player.y))
```

- [ ] **Step 6: Close the commit bypass — arriving in the hall by ANY means commits you**

Added after Task 5's review found it. `_arena_commit()` hangs solely off `_enter_tile()`, and **three movement paths never call it**: `teleport_to` (ZEPH), the `"blink"` effect (UUL), and the descent scroll that drops the player onto `level.stairs`. So today you can arrive inside the hall with the mouth still open, walk back out, and — once Task 6 lands — never trigger her spawn. None of these skip the fight (`descend` still refuses while she lives), but they defeat the seal and let you skip the trapped crossing that is her actual damage.

The rule: **standing in her hall is the commitment, however you got there.** Move the call so it fires on every player turn rather than only on tile entry.

In `deathward/world.py`, find `_end_player_turn` and add the call as its first statement:

```python
    def _end_player_turn(self):
        # Standing in her hall IS the commitment, however you arrived -- walked
        # through the mouth, or dropped in by scroll. Hanging this on _enter_tile
        # alone left three ways in (ZEPH, UUL, the descent scroll) that never fire
        # it, and a gate that only shuts for players who use the door is not a gate.
        self._arena_commit()
```

Then remove the now-redundant call from the top of `_enter_tile` (added in Task 5), leaving `_enter_tile` as it was before that task:

```python
    def _enter_tile(self):
        p = self.player
        t = self.level.trap_at(p.x, p.y)
```

`_arena_commit` already early-returns unless the player is standing in `arena_room` with `mouth_sealed` false, so calling it every turn is cheap and still fires exactly once per level.

Add these tests to `TestArenaScrollContainment`:

```python
    def test_teleporting_into_the_hall_commits_you(self):
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=1)
        w.new_level(8)
        a = w.level.arena_room
        for y in range(a.y, a.y + a.h):
            for x in range(a.x, a.x + a.w):
                w.level.explored[y][x] = True
        self.assertTrue(w.teleport_to(a.cx, a.cy))
        self.assertTrue(w.level.mouth_sealed,
                        "the gate shuts for scrolls too, not just for the door")

    def test_blinking_into_the_hall_commits_you(self):
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=1)
        w.new_level(8)
        a = w.level.arena_room
        w.player.x, w.player.y = a.cx, a.cy
        w._end_player_turn()
        self.assertTrue(w.level.mouth_sealed)

    def test_standing_in_the_antechamber_never_commits_you(self):
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=1)
        w.new_level(8)
        for _ in range(5):
            w._end_player_turn()
        self.assertFalse(w.level.mouth_sealed,
                         "the prep room is yours for as long as you want it")
```

- [ ] **Step 7: Run the new tests**

Run: `py -3.13 -m unittest deathward.tests.TestArenaScrollContainment -v`
Expected: PASS, 8 tests.

- [ ] **Step 8: Run the whole suite**

Run: `py -3.13 -m deathward.tests`

Task 5's `TestArenaGates` must still pass — its `_commit` helper sets the player's position and calls `_enter_tile()`, which no longer commits. If those tests fail, update that helper to call `w._end_player_turn()` instead, and say so in your report. Do not weaken any assertion.

- [ ] **Step 9: Commit**

```bash
git add deathward/dungeon.py deathward/world.py deathward/tests.py
git commit -m "feat(arena): scrolls reposition inside her hall, never leave it -- and arriving commits you"
```

---

### Task 8: The gates are visible

A sealed doorway drawn as plain wall reads as a bug. `sprites.entrance()` is **already a shut portcullis** — it is what floor 1's front gate uses — so this needs no new art.

**Files:**
- Modify: `deathward/render.py:150-160` (the "way in and the way down" block)
- Test: `deathward/tests.py` (new class `TestArenaGateRendering`)

**Interfaces:**
- Consumes: Task 4's `Level.mouth_sealed`, `stairs_locked`; Task 2's `Level.mouth`, `Level.is_arena_floor()`.
- Produces: no new API — rendering only.

- [ ] **Step 1: Write the failing test**

This project renders to a real surface, so test the *decision*, not the pixels. Add at the end of `deathward/tests.py`:

```python
class TestArenaGateRendering(unittest.TestCase):
    """A gate the player cannot see is a bug report. All three draw as the portcullis
    that floor 1's front gate already uses."""

    # `render` is not imported at tests.py module level; these tests import it.

    def _world(self):
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=1)
        w.new_level(8)
        return w

    def test_the_way_up_on_her_floor_draws_as_a_shut_gate(self):
        w = self._world()
        self.assertTrue(render.entrance_is_barred(w))

    def test_an_ordinary_floors_way_up_is_stairs(self):
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=1)
        w.new_level(7)
        self.assertFalse(render.entrance_is_barred(w))

    def test_floor_one_is_still_barred(self):
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=1)
        w.new_level(1)
        self.assertTrue(render.entrance_is_barred(w))

    def test_the_barred_gates_are_exactly_the_shut_ones(self):
        w = self._world()
        self.assertEqual(render.barred_gates(w), [], "nothing is shut yet")
        a = w.level.arena_room
        w.player.x, w.player.y = a.x, a.cy
        w._enter_tile()
        gates = render.barred_gates(w)
        self.assertIn(w.level.mouth, gates)
        self.assertIn(w.level.stairs, gates)

    def test_the_way_down_stops_being_barred_when_she_dies(self):
        w = self._world()
        a = w.level.arena_room
        w.player.x, w.player.y = a.x, a.cy
        w._enter_tile()
        w.level.stairs_locked = False
        self.assertNotIn(w.level.stairs, render.barred_gates(w))
```

`render` is **not** imported at tests.py module level (only `config`, `codex`, `items`, `world` are). Add it to the module imports beside them:

```python
from . import config  # noqa: E402
from . import render  # noqa: E402
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -3.13 -m unittest deathward.tests.TestArenaGateRendering -v`
Expected: FAIL with `AttributeError: module 'deathward.render' has no attribute 'entrance_is_barred'`.

- [ ] **Step 3: Add the two decision helpers**

In `deathward/render.py`, at module level above the draw function, add:

```python
def entrance_is_barred(world):
    """Floor 1's entrance is a shut portcullis, and so is her hall's: you came down
    into it and the way back is stone. Every other floor's entrance is a way up."""
    return world.depth <= 1 or world.level.is_arena_floor()


def barred_gates(world):
    """The gates that are currently SHUT and want a portcullis drawn over them: the
    mouth once you have committed, and the way down until she is dead. Pure decision,
    so it can be tested without a surface."""
    lvl = world.level
    if not lvl.is_arena_floor():
        return []
    gates = []
    if lvl.mouth_sealed and lvl.mouth:
        gates.append(lvl.mouth)
    if lvl.stairs_locked and lvl.stairs:
        gates.append(lvl.stairs)
    return gates
```

- [ ] **Step 4: Draw them**

In `deathward/render.py`, in the "way in and the way down" block (lines ~150-160), replace the entrance condition and add the gate pass:

```python
    # --- the way in and the way down -------------------------------------
    if lvl.entrance and lvl.explored[lvl.entrance[1]][lvl.entrance[0]]:
        ex, ey = lvl.entrance
        dim = not lvl.visible[ey][ex]
        # floor 1's entrance is a shut portcullis, and so is her hall's. every other
        # floor's is a way back up.
        img = (sprites.entrance(dim=dim) if entrance_is_barred(world)
               else sprites.stairs_up(dim=dim))
        surf.blit(img, topleft(ex, ey))
    if lvl.stairs and lvl.explored[lvl.stairs[1]][lvl.stairs[0]]:
        sx_, sy_ = lvl.stairs
        surf.blit(sprites.stairs(dim=not lvl.visible[sy_][sx_]), topleft(sx_, sy_))

    # a shut gate is a WALL tile for movement, line of sight and pathing -- but it
    # must LOOK like a gate, or a sealed doorway reads as a bug.
    for gx, gy in barred_gates(world):
        if not lvl.explored[gy][gx] or not cam.on_screen(gx, gy):
            continue
        surf.blit(sprites.entrance(dim=not lvl.visible[gy][gx]), topleft(gx, gy))
```

- [ ] **Step 5: Run the new tests**

Run: `py -3.13 -m unittest deathward.tests.TestArenaGateRendering -v`
Expected: PASS, 5 tests.

- [ ] **Step 6: Run the whole suite**

Run: `py -3.13 -m deathward.tests`
Expected: OK.

- [ ] **Step 7: Commit**

```bash
git add deathward/render.py deathward/tests.py
git commit -m "feat(arena): draw all three gates as the portcullis floor 1 already uses"
```

---

### Task 9: The floor is always completable

The load-bearing proof. This project formally guarantees the dungeon can always be finished, and this feature adds the first floor in the game with two barred exits — exactly the shape that can strand a player.

**Files:**
- Test: `deathward/tests.py` (new class `TestArenaIsAlwaysCompletable`)
- Modify: whatever the tests find broken.

**Interfaces:**
- Consumes: everything from Tasks 1-8.
- Produces: no new API.

- [ ] **Step 1: Write the tests**

Add at the end of `deathward/tests.py`:

```python
class TestArenaIsAlwaysCompletable(unittest.TestCase):
    """Floor 8 is the first floor with two barred exits. There must be no reachable
    state in which the player has no legal move left."""

    def _committed(self, world_seed=3):
        codex = FakeSave(); codex.world_seed = world_seed
        w = World(codex, seed=1)
        w.new_level(8)
        a = w.level.arena_room
        w.player.x, w.player.y = a.x, a.cy
        w._enter_tile()
        return w

    def _reachable(self, lvl, start):
        seen, stack = {start}, [start]
        while stack:
            x, y = stack.pop()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (x + dx, y + dy)
                if n in seen or not lvl.in_bounds(*n):
                    continue
                if lvl.grid[n[1]][n[0]] != 1:
                    continue
                seen.add(n)
                stack.append(n)
        return seen

    def test_the_way_down_is_reachable_from_where_you_are_sealed_in(self):
        for seed in range(10):
            w = self._committed(world_seed=seed)
            reach = self._reachable(w.level, (w.player.x, w.player.y))
            self.assertIn(w.level.stairs, reach,
                          "seed %d: she can be reached and so can the stairs" % seed)

    def test_every_pillar_leaves_the_hall_connected(self):
        for seed in range(10):
            w = self._committed(world_seed=seed)
            a = w.level.arena_room
            floor = {(x, y) for (x, y) in a.tiles() if w.level.grid[y][x] == 1}
            reach = self._reachable(w.level, (w.player.x, w.player.y))
            self.assertTrue(floor <= reach,
                            "seed %d: the columns must not wall anything off" % seed)

    def test_the_antechamber_is_reachable_until_you_commit(self):
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=1)
        w.new_level(8)
        reach = self._reachable(w.level, w.level.entrance)
        self.assertIn(w.level.stairs, reach)
        self.assertIn(w.level.mouth, reach)

    def test_the_full_run_through_her_floor(self):
        """Arrive, prepare, commit, kill her, take the stairs. End to end."""
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=1)
        w.new_level(8)
        # 1. you arrive in the antechamber and cannot go back
        self.assertTrue(w.level.ante_room.contains(w.player.x, w.player.y))
        w.player.x, w.player.y = w.level.entrance
        self.assertFalse(w.ascend())
        # 2. you commit
        a = w.level.arena_room
        w.player.x, w.player.y = a.x, a.cy
        w._enter_tile()
        self.assertTrue(w.level.mouth_sealed)
        # 3. the way down is shut
        w.player.x, w.player.y = w.level.stairs
        self.assertFalse(w.descend())
        # 4. she dies
        m = [x for x in w.level.monsters if x.key == "syrinx"][0]
        w.kill_monster(m)
        # 5. and it opens
        self.assertTrue(w.descend())
        self.assertEqual(w.depth, 9)

    def test_a_suspend_at_every_stage_resumes_legally(self):
        from .dungeon import Level
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=1)
        w.new_level(8)
        a = w.level.arena_room
        stages = [(w.level.entrance, w.level.to_dict())]       # in the antechamber
        w.player.x, w.player.y = a.x, a.cy
        w._enter_tile()
        stages.append(((a.x, a.cy), w.level.to_dict()))        # mid-fight
        m = [x for x in w.level.monsters if x.key == "syrinx"][0]
        w.kill_monster(m)
        stages.append(((a.x, a.cy), w.level.to_dict()))        # she is dead
        for i, (where, data) in enumerate(stages):
            restored = Level(8, w.rng, w.codex, restore=data)
            reach = self._reachable(restored, where)
            self.assertGreater(len(reach), 1,
                               "stage %d: the player can still move" % i)
            if not restored.stairs_locked:
                self.assertIn(restored.stairs, reach,
                              "stage %d: and can still reach the way down" % i)

    def test_your_own_corpse_lands_in_the_hall_and_can_be_reached(self):
        """The corpse system needs no change here: it puts your body on the exact tile
        you fell on, and this floor's stone is fixed, so the tile is still there next
        run. Die to her and your gold lies in her hall -- getting it back means
        crossing the mouth and fighting her again."""
        codex = FakeSave(); codex.world_seed = 3
        probe = World(codex, seed=1)
        probe.new_level(8)
        a = probe.level.arena_room
        grave = (a.cx, a.cy)
        # the corpse store is a plain dict keyed by depth-as-string; tests write it
        # directly (see tests.py:1388 for the same idiom).
        codex.corpses["8"] = {"x": grave[0], "y": grave[1], "gold": 40,
                              "weapon": None}

        w = World(codex, seed=2)
        w.new_level(8)
        self.assertIsNotNone(w.level.corpse, "your body is down there")
        self.assertEqual((w.level.corpse.x, w.level.corpse.y), grave)
        reach = self._reachable(w.level, (a.x, a.cy))
        self.assertIn(grave, reach, "and you can walk back to it -- through her")
```

- [ ] **Step 2: Run them**

Run: `py -3.13 -m unittest deathward.tests.TestArenaIsAlwaysCompletable -v`
Expected: PASS, 6 tests. **If any fails, that is a real bug in Tasks 2-8 — fix the code, never the assertion.** The likeliest failure is `test_every_pillar_leaves_the_hall_connected`: with a 6-tile pitch and single-tile columns nothing can be walled off, so a failure means the lattice arithmetic is wrong.

- [ ] **Step 3: Run the whole suite**

Run: `py -3.13 -m deathward.tests`
Expected: OK, and the count should be roughly 718 + ~50 new.

- [ ] **Step 4: Commit**

```bash
git add deathward/tests.py
git commit -m "test(arena): prove her floor is always completable, at every stage of the fight"
```

---

## After the plan

**Do not merge on green tests.** The user playtests a branch themselves before merge, even after automated and agent verification have passed. Hand the branch over and say what to look for:

- Does the hall land as *vast* when the gate falls?
- Are ~50 hazards too many, too few? (`config.ARENA_TRAPS`)
- Does a 5-tile shove across a trapped floor kill too fast? (`config.SYRINX_PUSH_DIST`)
- With 20 columns instead of 6, does she re-hide too easily to ever pin down?

**Three difficulty increases land together here** — the longer shove, the trapped floor, and her pillar count going 6 → 20. Expect the first playtest to feel like too much, and know which dial to reach for. They are all `config.py` constants, deliberately untested, meant to be moved by playing.

**Useful cheats for testing:** CTRL+78 warps down a floor (`warp_down`), CTRL+12 grants gear.
