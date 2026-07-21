# Ordinary Boots Distribution (Generation-Placed, Found-Only) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make ordinary boots scarce, found-only, one-per-floor generation-placed finds (like weapons) — removed from the vendor/gift/generic loot, banded across floors 2–15, none on floor 1 or past 15.

**Architecture:** Ordinary boots leave the shared `gear_pool` (one change that strips them from vendor, floor-1 gift, and the generic multi-source loot at once). A new `roll_floor_boots(rng, depth)` places at most one ordinary boot per floor at generation time in `dungeon.py`, right after the weapons-placement loop, drawing only from `(rng, depth)`.

**Tech Stack:** Python 3 standard library, `pygame` (existing dependency), `unittest` (tests in `deathward/tests.py`).

## Global Constraints

- **No new dependencies.** Standard library + existing `pygame`.
- **Determinism / knowledge-is-information invariant:** `roll_floor_boots` and all generation must draw only from `(rng, depth)`, never the Kodex `known` set. A blind and an omniscient run of the same seed must stay bit-identical (guarded by `TestKnowledgeIsNotPower`, tests.py:323).
- **Do not touch the GPL license header** in any file.
- **Scope fence:** only ordinary boots' *distribution* changes. Do NOT change boot stats/tiers/sprites/keys (Plan 1), weapons, armour, or the **magical** boots' distribution (magical boots stay in `gear_pool` on floors 8+ — "one per floor" is for *ordinary* boots).
- **Boot keys** are `boots_leather` (T1), `boots_mail` (T2), `boots_plate` (T3) — the `boots_`-prefixed keys from Plan 1. The armour of the same material keeps the bare keys (`leather`, `plate`).
- **Running tests — use `py -3.13`, NOT `python`** (plain `python`/`py` are Python 3.14 without pygame). Whole suite: `py -3.13 -m deathward.tests` (baseline before this plan: 486 green). One test: `py -3.13 -m deathward.tests <ClassName>.<test_method> -v`.

---

### Task 1: `roll_floor_boots` + ordinary boots leave `gear_pool`

**Files:**
- Modify: `deathward/items.py:375-393` (`gear_pool`); add `roll_floor_boots` + its band table (after `roll_floor_weapons`, ~line 467).
- Test: `deathward/tests.py` — rewrite the Plan 1 method `test_gear_pool_keeps_magical_boots_out_of_the_shallows` (tests.py:7113) and add `roll_floor_boots` tests to the same `TestBootsRebalance` class.

**Interfaces:**
- Consumes: the `BOOTS` table + `boots_`-prefixed keys (Plan 1).
- Produces: `roll_floor_boots(rng, depth) -> list[str]` (0 or 1 ordinary-boot keys). `gear_pool(depth)` no longer contains any ordinary boot (tier 1–3 boots); it still contains all armour and magical boots (tier ≥ 4 at depth ≥ 8). Task 2 calls `roll_floor_boots`.

- [ ] **Step 1: Write the failing tests**

Replace the existing method `test_gear_pool_keeps_magical_boots_out_of_the_shallows` (tests.py:7113–7128) with the following, and add the four new `roll_floor_boots` methods, all in the `TestBootsRebalance` class:

```python
    def test_gear_pool_excludes_ordinary_boots_and_still_gates_magical(self):
        from .items import gear_pool
        ordinary = {"boots_leather", "boots_mail", "boots_plate"}
        magical = {"swift", "blink", "soft", "ironshod", "wind"}
        for depth in range(1, 21):
            pool = set(gear_pool(depth))
            self.assertFalse(pool & ordinary,
                             "ordinary boots are found-only, never in gear_pool "
                             "(floor %d)" % depth)
        # magical boots: still absent shallow, present deep (Plan 1 behaviour, unchanged)
        for depth in (1, 3, 5, 7):
            self.assertFalse(set(gear_pool(depth)) & magical,
                             "no magical boots on floor %d" % depth)
        self.assertTrue(set(gear_pool(8)) & magical, "magical boots reachable on floor 8")
        self.assertIn("wind", gear_pool(10))
        # armour is untouched -- the pool is not empty, and the Leather Jerkin (armour,
        # key 'leather') is still there, distinct from the boot key 'boots_leather'
        self.assertIn("leather", gear_pool(1))

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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -3.13 -m deathward.tests TestBootsRebalance -v`
Expected: FAIL — `ImportError: cannot import name 'roll_floor_boots'`, and the rewritten `gear_pool` test fails because ordinary boots are still in the pool.

- [ ] **Step 3: Rewrite `gear_pool` to drop ordinary boots**

In `deathward/items.py`, replace `gear_pool` (lines 375–393):

```python
def gear_pool(depth):
    """Armour and MAGICAL boots that the generic loot tables and the vendor may surface at a
    given depth. Weapons and ORDINARY boots are NOT here -- both are placed once at floor
    generation (roll_floor_weapons / roll_floor_boots), scarce and one-per-floor. Armour keeps
    its tier 1/2/3 shallow gates; magical boots (tier 4-5) surface only on floor 8+."""
    pool = []
    for key, g in ARMOURS.items():
        if g.tier == 1 and depth >= 1:
            pool.append(key)
        elif g.tier == 2 and depth >= 3:
            pool.append(key)
        elif g.tier == 3 and depth >= 5:
            pool.append(key)
    for key, g in BOOTS.items():
        if g.tier >= 4 and depth >= 8:       # magical boots only; ordinary boots are found-only
            pool.append(key)
    return pool
```

- [ ] **Step 4: Add `roll_floor_boots` and its band table**

In `deathward/items.py`, immediately after the `roll_floor_weapons` function (after line 467), add:

```python
# The ordinary boots a floor may place: at most ONE, found-only, generation-placed like the
# weapons (never from the generic loot pool). Banded by depth -- lower unlocks carried from the
# ordinary tier, upper cutoffs so the deep floors are magical territory: none on floor 1 or past
# floor 15. When several are valid the choice is UNIFORM -- ordinary boots are a speed<->defense
# tradeoff, not a power ladder, so you find one of the currently-available options and decide.
ORDINARY_BOOT_BANDS = (
    ("boots_leather", 2, 10),
    ("boots_mail", 3, 15),
    ("boots_plate", 5, 15),
)


def roll_floor_boots(rng, depth):
    """The floor's single ordinary boot, or none -- a list of 0 or 1 boot keys. 50% present-
    chance on a floor with any valid boot (floors 2-15); the boot is chosen uniformly among
    those valid at this depth. Deterministic on (rng, depth); reads nothing else, so blind and
    omniscient runs of a seed stay bit-identical."""
    valid = [key for key, lo, hi in ORDINARY_BOOT_BANDS if lo <= depth <= hi]
    if not valid or rng.random() >= 0.50:
        return []
    return [rng.choice(valid)]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `py -3.13 -m deathward.tests TestBootsRebalance -v`
Expected: PASS (the rewritten gear_pool test + the four new roll_floor_boots tests, alongside the existing Plan 1 boots tests).

- [ ] **Step 6: Run the full suite (no regressions)**

Run: `py -3.13 -m deathward.tests`
Expected: green. In particular the floor-1 gift tests (`test_floor_one_always_has_a_guaranteed_gear_upgrade` and siblings) still pass — `gear_pool(1)` keeps the tier-1 Leather Jerkin/Scale armour, so the gift is still placed, just never a boot.

- [ ] **Step 7: Commit**

```bash
git add deathward/items.py deathward/tests.py
git commit -m "Ordinary boots leave gear_pool; add roll_floor_boots (one per floor, banded 2-15)"
```

---

### Task 2: Place the floor's ordinary boot at generation

**Files:**
- Modify: `deathward/dungeon.py:29` (import), `deathward/dungeon.py:503-535` (add the boots loop after the weapons loop; fix the floor-1 gift comment).
- Test: `deathward/tests.py` — add integration tests to `TestBootsRebalance`.

**Interfaces:**
- Consumes: `roll_floor_boots(rng, depth)` from Task 1.
- Produces: a generated `Level`'s `.drops` contains at most one ordinary-boot gear drop, only on floors 2–15.

- [ ] **Step 1: Write the failing tests**

Add these two methods to `TestBootsRebalance` in `deathward/tests.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -3.13 -m deathward.tests TestBootsRebalance.test_every_ordinary_boot_is_findable_across_the_mid_floors -v`
Expected: FAIL — no ordinary boots are placed yet (the found set is empty), so the equality assertion fails.

- [ ] **Step 3: Import `roll_floor_boots` in dungeon.py**

In `deathward/dungeon.py`, update the items import (line 29):

```python
from .items import (gear_pool, is_magical, roll_chest, roll_floor_boots,
                    roll_floor_weapons, roll_loot)
```

- [ ] **Step 4: Place the floor's boot after the weapons loop**

In `deathward/dungeon.py`, immediately after the weapons-placement loop (after line 521, the `codex.record_magical_placed(...)` block) and before the floor-1 gift block (line 523), add:

```python
        # THE FLOOR'S ORDINARY BOOT. Like the weapons: scarce, generation-placed, at most one
        # per floor -- never from the generic loot pool, never sold or gifted. Banded to floors
        # 2-15 by roll_floor_boots; placed on any free tile away from the gate.
        for bkey in roll_floor_boots(rng, d):
            spot = self._free_tile(avoid_start=True)
            if spot:
                self.drops.append(Drop(spot[0], spot[1], "gear", bkey))
```

- [ ] **Step 5: Fix the stale floor-1 gift comment**

In `deathward/dungeon.py`, in the floor-1 gift block (around line 527), update the parenthetical so it reflects that ordinary boots are now generation-placed too:

```python
        # once per GAME: it must not regrow on every respawn, or death becomes a way
        # to farm it. (Armour only now -- gear_pool excludes weapons and ordinary boots,
        # both generation-placed above; the floor's weapon is placed unconditionally.)
```

(Only the parenthetical wording changes; the `if d == 1 and not codex.gift_claimed("floor1"):` logic is untouched.)

- [ ] **Step 6: Run the tests to verify they pass**

Run: `py -3.13 -m deathward.tests TestBootsRebalance.test_generated_floors_hold_at_most_one_ordinary_boot_and_none_shallow_or_deep TestBootsRebalance.test_every_ordinary_boot_is_findable_across_the_mid_floors -v`
Expected: PASS.

- [ ] **Step 7: Run the full suite (determinism + no regressions)**

Run: `py -3.13 -m deathward.tests`
Expected: green — including `TestKnowledgeIsNotPower` (tests.py:323), which proves the added `roll_floor_boots` call (drawing only from `(rng, depth)`) keeps blind and omniscient runs of a seed bit-identical.

- [ ] **Step 8: Commit**

```bash
git add deathward/dungeon.py deathward/tests.py
git commit -m "Place the floor's single ordinary boot at generation (found-only, floors 2-15)"
```

---

## Notes for the implementer

- **Read tasks in order.** Task 2 depends on `roll_floor_boots` from Task 1.
- **`Level(depth, rng, codex)`** (dungeon.py:167) generates its `.drops` at construction; `FakeSave()` (tests.py:44, a `Codex` subclass) is a valid `codex` argument and supplies `layout_seed`/`magical_generated`.
- **`Drop`** is already imported/used in dungeon.py (see the weapons loop). Its signature is `Drop(x, y, kind, payload, gift=None, bonus=0)`; boots need no bonus/gift, so `Drop(x, y, "gear", bkey)` is correct.
- If a single test reports "no tests ran", run the whole class (`py -3.13 -m deathward.tests TestBootsRebalance -v`) or the whole file (`py -3.13 -m deathward.tests`).
