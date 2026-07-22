# Magical Boots — Phase 2 (Stealth Subsystem) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the stealth boots — Padded Soles (redefined: halve the monster wake radius) and Whisperstep (new T5: wake radius 2) — with the room-alert latch that turns stealth off once a monster in your region is awake.

**Architecture:** A monster wakes when it is in the player's FOV *and* within a wake radius — today a fixed 9 (`monster_can_see_player`). Stealth boots shrink that radius via a new `player_wake_radius()`. A room-alert latch (`region_of` + `player_region`/`region_alerted`, updated each tick in `advance`) reverts the radius to normal once any monster in the player's current region is awake, until the player leaves that region. Corridors are one region (Option A).

**Tech Stack:** Python 3 standard library, `pygame`, `unittest` (`deathward/tests.py`).

## Global Constraints

- **No new dependencies.** Standard library + existing `pygame`.
- **Determinism:** the stealth logic reads only monster positions/`awake` flags and the player's position — never the Kodex, never the RNG. The blind-vs-omniscient bit-identical invariant (`TestKnowledgeIsNotPower`, tests.py:323) must stay green.
- **Do not touch the GPL header** in any file.
- **Scope fence:** only the stealth boots + their subsystem. Do NOT touch the other magical boots, weapons, armour, ordinary boots, or distribution.
- **`softsole` is retired.** Padded Soles loses its pressure-plate skip (Featherfall already covers all-trap immunity, Phase 1). No boot has trait `softsole` after this plan; the traps.py `softsole` branch and its two tests go with it.
- **Wake gate is one function.** `monster_can_see_player` (world.py:311) is the sole caller-facing wake check (called only from `Monster.take_turn`, monsters.py:230). Change the radius there; leave the spitter's separate `d <= 9` line-of-fire (monsters.py:629) alone.
- **Running tests — use `py -3.13`, NOT `python`** (3.14 lacks pygame). Whole suite: `py -3.13 -m deathward.tests` (baseline: 502 green). One test: `py -3.13 -m deathward.tests <ClassName>.<test_method> -v`.

## Shared references

- `Boots(key, name, tier, speed, trait=None, note="", defense=0)` — items.py:87. The magical `BOOTS` entries are after the ordinary ones (items.py:171-199).
- `_boots_sprite(key, s, S)` — sprites.py:1146, an `if/elif key == ...` chain; local `boot(col, sole=None)` helper + primitives `_poly`/`_line`/`_circ`/`_shade`.
- `monster_can_see_player` (world.py:311-318): `return self.level.visible[m.y][m.x] and m.dist(self.player.x, self.player.y) <= 9`.
- `advance()` (world.py:1843): the tick loop; monsters take turns inside it. `Room.contains(x, y)` (dungeon.py:90); `self.level.rooms` is the room list.
- New tests go in a new `TestBootsStealth(unittest.TestCase)` at the END of `deathward/tests.py`, before `if __name__ == "__main__":`. `World(FakeSave(), seed=N)`, `BOOTS[...]`, `from .monsters import Monster`, `from .dungeon import FLOOR`.

---

### Task 1: Stealth wake-radius + the stealth boots (retire softsole)

**Files:**
- Modify: `deathward/config.py` (constant), `deathward/items.py` (`Boots` + `soft`/new `whisperstep`), `deathward/sprites.py` (`_boots_sprite`), `deathward/world.py` (`monster_can_see_player` + new `player_wake_radius`), `deathward/traps.py` (drop the softsole branch)
- Test: `deathward/tests.py` — new `TestBootsStealth`; repurpose one softsole test to Featherfall and delete the other.

**Interfaces:**
- Produces: `Boots.wake_radius` (int, default 0 = "not stealth"); `BOOTS["soft"]` (Padded Soles, T4, +10, `wake_radius=4`, no trait); `BOOTS["whisperstep"]` (T5, +10, `wake_radius=2`) + sprite; `World.player_wake_radius()` returns the boots' `wake_radius` or `config.MONSTER_SIGHT`. Task 2 folds the room-alert into `player_wake_radius`.

- [ ] **Step 1: Write the failing tests**

Add this new class at the end of `deathward/tests.py`, before `if __name__ == "__main__":`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -3.13 -m deathward.tests TestBootsStealth -v`
Expected: FAIL — `AttributeError: 'Boots' object has no attribute 'wake_radius'` (and `KeyError: 'whisperstep'`).

- [ ] **Step 3: Add the config constant**

In `deathward/config.py`, near the other combat/sight constants (e.g. after `FOV_RADIUS`):

```python
MONSTER_SIGHT = 9         # how close (in tiles, within FOV) a monster notices the player
```

- [ ] **Step 4: Give `Boots` a wake radius; redefine Padded Soles; add Whisperstep**

In `deathward/items.py`, add `wake_radius` to `Boots.__init__`:

```python
    def __init__(self, key, name, tier, speed, trait=None, note="", defense=0,
                 wake_radius=0):
        self.key, self.name, self.tier = key, name, tier
        self.speed, self.trait, self.note = speed, trait, note
        self.defense = defense            # armoured boots (mail/plate); 0 for the rest
        self.wake_radius = wake_radius    # stealth boots: tiles a monster wakes within; 0 = normal
```

Then in the magical `BOOTS` section, replace the `soft` entry and add `whisperstep` (place `whisperstep` beside the other T5 boots, e.g. after `slipstep`):

```python
    "soft":     Boots("soft", "Padded Soles", 4, 10,
                      note="so quiet that monsters notice you only up close", wake_radius=4),
```

```python
    "whisperstep": Boots("whisperstep", "Whisperstep", 5, 10,
                         note="you pass like a rumour -- nothing wakes until you are on it",
                         wake_radius=2),
```

- [ ] **Step 5: Add the Whisperstep sprite**

In `deathward/sprites.py`, add an `elif` branch inside `_boots_sprite` (after the existing boots):

```python
    elif key == "whisperstep":              # muffled grey-violet, a soft hush
        boot((120, 116, 140), (78, 74, 96))
        for i in range(3):                  # faint sound-rings fading off the heel
            r = S * (0.10 + i * 0.06)
            pygame.draw.arc(s, (176, 170, 200), (cx - S * 0.36, S * 0.34, r * 2, r * 2),
                            0.6, 2.5, max(1, int(S * 0.015)))
```

- [ ] **Step 6: Add `player_wake_radius` and use it in the wake check**

In `deathward/world.py`, add the method near `monster_can_see_player` (e.g. just above it, ~line 311):

```python
    def player_wake_radius(self):
        """How close a monster must be (within FOV) to notice the player. Stealth boots
        shrink it; everything else uses the normal MONSTER_SIGHT."""
        return self.player.boots.wake_radius or config.MONSTER_SIGHT
```

Then change the wake check (world.py:318):

```python
        return (self.level.visible[m.y][m.x]
                and m.dist(self.player.x, self.player.y) <= self.player_wake_radius())
```

- [ ] **Step 7: Retire the softsole branch in traps.py**

In `deathward/traps.py`'s `Trap.trigger`, delete the `softsole` branch inside the `PRESSURE` block (leave the `levitate` branch that follows it):

```python
        if is_player and self.key in PRESSURE:
            # you are not on it at all (levitation). the pit and the dart wait for
            # someone heavier.
            if world.player.levitate > 0:
                world.log("You drift over the plate. Your feet never touch it.",
                          config.MANA)
                return
```

- [ ] **Step 8: Remove the now-obsolete softsole test**

In `deathward/tests.py`, delete `test_soft_soles_do_not_press_plates_but_do_not_stop_fire` (around line 5525) entirely — softsole's "skip the plate but still burn" behavior no longer exists (Padded Soles no longer skips plates; Featherfall skips everything). Also delete the old `test_a_trap_you_cannot_see_still_teaches_you_nothing` (around line 5497) — its "no learning from an unfired trap" coverage now lives in `TestBootsStealth.test_featherfall_still_teaches_nothing_from_a_trap_it_never_springs`.

- [ ] **Step 9: Run the tests to verify they pass**

Run: `py -3.13 -m deathward.tests TestBootsStealth -v`
Expected: PASS. Then the full suite:
Run: `py -3.13 -m deathward.tests`
Expected: green (the two deleted softsole tests are gone; the sprite-distinctness test covers the new Whisperstep sprite).

- [ ] **Step 10: Commit**

```bash
git add deathward/config.py deathward/items.py deathward/sprites.py deathward/world.py deathward/traps.py deathward/tests.py
git commit -m "Stealth boots: Padded Soles (halve wake radius) + Whisperstep (radius 2); retire softsole"
```

---

### Task 2: The region model + room-alert latch

**Files:**
- Modify: `deathward/world.py` (`region_of`, stealth state in `__init__` + reset in `new_level`, `_update_stealth_alert`, the `advance` call, `player_wake_radius`)
- Test: `deathward/tests.py` (`TestBootsStealth`)

**Interfaces:**
- Consumes: `player_wake_radius` (Task 1), `Room.contains`.
- Produces: `World.region_of(x, y)` → the `Room` containing the tile, or `None` for the corridors (Option A: the whole corridor network is one region). `World.player_region` / `World.region_alerted`; `World._update_stealth_alert()`. `player_wake_radius` now returns `MONSTER_SIGHT` while the region is alerted.

- [ ] **Step 1: Write the failing tests**

Add these methods to `TestBootsStealth` in `deathward/tests.py`:

```python
    def test_region_of_is_the_room_or_the_corridors(self):
        w = World(FakeSave(), seed=3)
        room = w.level.rooms[0]
        self.assertIs(w.region_of(room.cx, room.cy), room, "a room tile -> that Room")
        # a monster in the same room shares the region; the corridors are one region (None)
        self.assertIs(w.region_of(room.cx, room.cy), w.region_of(room.x, room.y))

    def test_a_waking_monster_in_your_region_raises_the_alarm(self):
        from .items import BOOTS
        from .monsters import Monster
        w = World(FakeSave(), seed=3)
        w.player.boots = BOOTS["whisperstep"]         # wake radius 2
        room = w.level.rooms[0]
        w.player.x, w.player.y = room.cx, room.cy
        m = Monster("rat", room.cx, room.cy)          # same region, and it has spotted you
        m.awake = True
        w.level.monsters = [m]
        w._update_stealth_alert()
        self.assertTrue(w.region_alerted, "an awake monster in your region raises the alarm")
        self.assertEqual(w.player_wake_radius(), config.MONSTER_SIGHT,
                         "alerted -> stealth is off, monsters wake at the normal range")

    def test_a_sleeping_region_keeps_you_hidden(self):
        from .items import BOOTS
        from .monsters import Monster
        w = World(FakeSave(), seed=3)
        w.player.boots = BOOTS["whisperstep"]
        room = w.level.rooms[0]
        w.player.x, w.player.y = room.cx, room.cy
        m = Monster("rat", room.cx, room.cy); m.awake = False
        w.level.monsters = [m]
        w._update_stealth_alert()
        self.assertFalse(w.region_alerted)
        self.assertEqual(w.player_wake_radius(), 2, "no alarm -> your stealth radius holds")

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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -3.13 -m deathward.tests TestBootsStealth.test_a_waking_monster_in_your_region_raises_the_alarm -v`
Expected: FAIL — `AttributeError: 'World' object has no attribute 'region_of'` (or `_update_stealth_alert`).

- [ ] **Step 3: Initialise the stealth state**

In `deathward/world.py`'s `World.__init__`, add beside the other run state:

```python
        self.player_region = None      # which region the player is in (a Room, or None=corridors)
        self.region_alerted = False    # stealth latch: a monster in the region has spotted you
```

And in `new_level` (where a floor loads, after `self.level` is set), reset it so a fresh floor starts un-alerted (the corridor region `None` is shared across floors, so this reset is load-bearing):

```python
        self.player_region = None
        self.region_alerted = False
```

- [ ] **Step 4: Add `region_of` and `_update_stealth_alert`**

In `deathward/world.py`, near `player_wake_radius`, add:

```python
    def region_of(self, x, y):
        """The stealth region a tile belongs to: the Room that contains it, or None for
        the corridors -- Option A treats the whole corridor network as a single region."""
        for r in self.level.rooms:
            if r.contains(x, y):
                return r
        return None

    def _update_stealth_alert(self):
        """Maintain the room-alert latch. On entering a new region the alarm is off; while
        the player is in a region, any awake monster IN that region raises it (and it stays
        raised until the player leaves the region). Cheap, deterministic -- no RNG, no Kodex."""
        region = self.region_of(self.player.x, self.player.y)
        if region is not self.player_region:
            self.player_region = region
            self.region_alerted = False
        if not self.region_alerted and any(
                m.awake and self.region_of(m.x, m.y) is region
                for m in self.level.monsters):
            self.region_alerted = True
```

- [ ] **Step 5: Fold the alert into `player_wake_radius`**

In `deathward/world.py`, replace `player_wake_radius` (from Task 1) with:

```python
    def player_wake_radius(self):
        """How close a monster must be (within FOV) to notice the player. Stealth boots
        shrink it -- but only until a monster in the player's region raises the alarm, after
        which stealth is off (the normal MONSTER_SIGHT) until the player leaves the region."""
        r = self.player.boots.wake_radius
        if not r or self.region_alerted:
            return config.MONSTER_SIGHT
        return r
```

- [ ] **Step 6: Update the latch each tick in `advance`**

In `deathward/world.py`'s `advance()`, call the updater once per tick, before the monsters take their turns. Insert it just before the monster take-turn loop (the second `for m in list(self.level.monsters):`):

```python
            self._update_stealth_alert()
            for m in list(self.level.monsters):
                inner = 0
                while (m.energy >= config.ACT_COST and m.alive and not self.dead
                       and inner < 5):
                    inner += 1
                    m.energy -= config.ACT_COST
                    m.take_turn(self)
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `py -3.13 -m deathward.tests TestBootsStealth -v`
Expected: PASS (all stealth tests). Then the full suite:
Run: `py -3.13 -m deathward.tests`
Expected: green — including `TestKnowledgeIsNotPower` (the latch reads only positions/`awake`, never the Kodex, so blind and omniscient runs stay bit-identical).

- [ ] **Step 8: Commit**

```bash
git add deathward/world.py deathward/tests.py
git commit -m "Stealth room-alert: an awake monster in your region drops your cover until you leave it"
```

---

## Notes for the implementer

- **Read tasks in order.** Task 2 builds on `player_wake_radius` from Task 1.
- **`config` is already imported in world.py.** `Room` is used via `self.level.rooms` (no import needed).
- **Regions compared by identity** (`is`/`is not`): `Room` objects are stable within a floor; the `new_level` reset (Task 2 Step 3) handles the corridor `None` region being shared across floors.
- If the Whisperstep sprite trips `test_every_piece_of_gear_has_its_own_sprite` (clash/blank), nudge its RGB/detail while keeping the muffled grey-violet motif.
- If a single test reports "no tests ran", run the class (`py -3.13 -m deathward.tests TestBootsStealth -v`) or the whole file.
