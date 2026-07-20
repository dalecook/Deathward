# Magical Weapon Roster — Plan 2: Deep-Floor Economy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the deep floors (8–20) deliver weapons at the designed rarity: floors 8–15 get up to **two** finds — an *enhanced Steel* weapon (never +0) whose chance decays to 0 at floor 15, plus a **rare magical** weapon whose tier follows a depth crossover (Tier 4 → Tier 5) drawn from the findable pool (the two mini-boss weapons excluded); floors 16–20 get the rare magical only. Keep the enchant scrolls (`krav`/`dwen`) reliably in reach deep.

**Architecture:** `roll_floor_weapon` (returns one weapon) becomes `roll_floor_weapons` (returns a **list** of 0–2 weapons). Floors 1–7 keep the existing ordinary logic, factored into `roll_ordinary`. Two new pure functions decide the deep slots: `roll_deep_steel(rng, depth)` and `roll_magical(rng, depth)`. `dungeon._populate` places each weapon in the returned list. A small bias in `roll_consumable` keeps enchant scrolls available on floors 8+. Everything draws only from `(rng, depth)`, never the Kodex.

**Tech Stack:** Python 3.11+ standard library; Pygame; `unittest`. Run with `py -3.13` (NOT `python`/`py`).

## Global Constraints

- **Standard library + Pygame only** — no new dependencies.
- **Knowledge is information, never power:** all generation randomness draws from the per-run world RNG (`rng`, aka `world.rng`) in a fixed order, independent of the Kodex, so blind and omniscient runs of a seed stay **bit-identical** (`TestKnowledgeIsNotPower`). Never use module-level `random`/time.
- **Determinism:** the deep slots draw in a fixed order (steel slot, then magical slot). A slot that does not fire must still draw its presence roll at the same point (do not conditionally skip a draw based on anything but `(rng, depth)`).
- **GPLv3 header:** every source file carries it; do not remove it. No new files are created.
- **Test commands:** full suite `py -3.13 -m deathward.tests` (baseline 449 green); one test `py -3.13 -m unittest deathward.tests.<Class>.<method> -v`.
- **Scope fence:** this plan is *generation/economy only*. The weapons and combat are Plan 1 (done). Do NOT implement uniqueness, the magical-weapon ledger, world-persistence of magicals, the collector's achievement, or the respawn homage — those are **Plan 3**. In this plan a magical slot simply draws from the findable pool each floor (repeats are allowed; Plan 3 makes them unique).

---

### Task 1: The findable magical pool and `roll_magical`

The rare magical slot for floors 8–20: a low, depth-declining present-chance; if present, the tier is a depth crossover (Tier-5 share rises with depth); the specific weapon comes from the *findable* pool, which excludes the two mini-boss-locked weapons (`windfang`, `void_scimitar`).

**Files:**
- Modify: `deathward/items.py` (add `FINDABLE_MAGICAL` and `roll_magical` near `roll_floor_weapon`, ~line 378)
- Test: `deathward/tests.py` (new `TestRollMagical` class)

**Interfaces:**
- Produces: `FINDABLE_MAGICAL: dict[int, list[str]]` with keys 4 and 5; `roll_magical(rng, depth) -> tuple[str, int] | None` returning `(key, 0)` or `None`. Present-chance 18% (8–11) / 15% (12–15) / 12% (16–20); Tier-5 share 20% / 40% / 65% over the same bands.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m unittest deathward.tests.TestRollMagical -v`
Expected: FAIL — `FINDABLE_MAGICAL` / `roll_magical` undefined.

- [ ] **Step 3: Write the pool and the roller**

In `deathward/items.py`, immediately above `def roll_floor_weapon`, add:

```python
# The magical weapons a floor can actually DROP. The two mini-boss rewards -- Windfang
# (T4) and the Scimitar of the Void (T5) -- are excluded: they come only from beating a
# mini-boss, never from the floor.
FINDABLE_MAGICAL = {
    4: ["rapier", "brand", "betrayers_edge", "fulgurite", "winters_edge",
        "sacrificial_dagger"],
    5: ["basilisk_maul", "pyroclast", "reapers_whisper", "kris", "glacial_flail"],
}


def roll_magical(rng, depth):
    """The rare magical slot for floors 8-20. Returns (key, 0) or None. Present-chance is
    low and declines with depth (fewer adventurers died this deep); if a magical is
    present, its tier is a depth crossover -- Tier-5's share rises with depth -- and the
    specific weapon is drawn from the findable pool. Draws only from (rng, depth), never
    the Kodex, so blind and omniscient runs stay bit-identical."""
    present = 0.18 if depth <= 11 else 0.15 if depth <= 15 else 0.12
    if rng.random() >= present:
        return None
    t5_share = 0.20 if depth <= 11 else 0.40 if depth <= 15 else 0.65
    tier = 5 if rng.random() < t5_share else 4
    return (rng.choice(FINDABLE_MAGICAL[tier]), 0)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.13 -m unittest deathward.tests.TestRollMagical -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add deathward/items.py deathward/tests.py
git commit -m "Add the findable magical pool and roll_magical (rarity + T4/T5 crossover)"
```

---

### Task 2: `roll_deep_steel` — the enhanced-Steel deep find

The non-magical slot on floors 8–14: an **enhanced** Steel weapon (never +0) left by a strong adventurer who died deep. Present-chance decays from 70% at floor 8 to 0 at floor 15; the +3 masterwork chance climbs with depth.

**Files:**
- Modify: `deathward/items.py` (add `roll_deep_steel` after `roll_magical`)
- Test: `deathward/tests.py` (new `TestRollDeepSteel` class)

**Interfaces:**
- Produces: `roll_deep_steel(rng, depth) -> tuple[str, int] | None` returning `("steel_<type>", bonus)` with `bonus in (1, 2, 3)`, or `None`. Present 70% at depth 8, −10%/floor, 0 at depth 15+. Never returns +0. Draws only from `(rng, depth)`.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m unittest deathward.tests.TestRollDeepSteel -v`
Expected: FAIL — `roll_deep_steel` undefined.

- [ ] **Step 3: Write the roller**

In `deathward/items.py`, immediately after `roll_magical`, add:

```python
def roll_deep_steel(rng, depth):
    """The non-magical slot on floors 8-14: an ENHANCED Steel weapon (never +0), the
    masterwork a strong adventurer carried down before dying. Present-chance decays from
    70% at floor 8 to 0 at floor 15; the +3 chance climbs with depth. Returns
    ("steel_<type>", bonus) with bonus in (1, 2, 3), or None. Draws only from (rng, depth)."""
    if depth >= 15:
        return None
    present = 0.70 * (15 - depth) / 7.0          # 70% at 8 ... 10% at 14 ... 0 at 15
    if rng.random() >= present:
        return None
    wtype = rng.choice(["sword", "axe", "hammer"])
    if rng.random() < (depth - 7) * 0.05:        # +3 masterwork: 5% at 8 ... 35% at 14
        bonus = 3
    else:
        bonus = 2 if rng.random() < 0.35 else 1
    return ("steel_%s" % wtype, bonus)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.13 -m unittest deathward.tests.TestRollDeepSteel -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add deathward/items.py deathward/tests.py
git commit -m "Add roll_deep_steel: the enhanced-Steel deep find (decays to 0 at floor 15)"
```

---

### Task 3: `roll_floor_weapons` orchestrator + rewire generation

Replace `roll_floor_weapon` (one weapon) with `roll_floor_weapons` (a **list**): floors 1–7 keep the ordinary logic (factored into `roll_ordinary`); floors 8+ combine the enhanced-Steel and magical slots. Rewire `dungeon._populate` to place each weapon in the list. This is one atomic task so the suite never goes red between the rename and the rewire.

**Files:**
- Modify: `deathward/items.py` (factor `roll_ordinary`; replace `roll_floor_weapon` with `roll_floor_weapons`)
- Modify: `deathward/dungeon.py:29` (import), `:490-497` (the placement block in `_populate`)
- Test: `deathward/tests.py` — update `TestWeaponGeneration` to the new interface; add `TestFloorWeaponsList`

**Interfaces:**
- Consumes: `roll_magical` (Task 1), `roll_deep_steel` (Task 2).
- Produces: `roll_ordinary(rng, depth) -> tuple[str,int] | None` (floors 1–7 only, behaviour-identical to the old `roll_floor_weapon` for those floors); `roll_floor_weapons(rng, depth) -> list[tuple[str,int]]` (0–2 entries). `roll_floor_weapon` no longer exists.

- [ ] **Step 1: Write the failing test**

```python
class TestFloorWeaponsList(unittest.TestCase):
    def test_floor_one_is_a_single_bone_axe(self):
        import random
        from .items import roll_floor_weapons
        for s in range(30):
            self.assertEqual(roll_floor_weapons(random.Random(s), 1), [("bone_axe", 0)])

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m unittest deathward.tests.TestFloorWeaponsList -v`
Expected: FAIL — `roll_floor_weapons` undefined.

- [ ] **Step 3: Factor `roll_ordinary` and write `roll_floor_weapons`**

In `deathward/items.py`, replace the entire `def roll_floor_weapon(rng, depth): ...` function (currently ~lines 378–399) with these two functions:

```python
def roll_ordinary(rng, depth):
    """Floors 1-7: the one ordinary weapon a floor may hold (Plan 1 of the rebalance).
    Floor 1 is a guaranteed unenhanced Bone Axe. Returns (key, bonus) or None. Unchanged
    behaviour from the original roll_floor_weapon for these floors."""
    if depth == 1:
        return ("bone_axe", 0)
    if rng.random() >= 0.80:
        return None
    material = "bone" if depth <= 2 else "bronze" if depth <= 4 else "steel"
    wtype = rng.choice(["sword", "axe", "hammer"])
    bonus = 0
    if rng.random() < (depth - 1) * 0.10:          # 10% on 2 ... 60% on 7
        bonus = 2 if rng.random() < 0.25 else 1
    return ("%s_%s" % (material, wtype), bonus)


def roll_floor_weapons(rng, depth):
    """Every weapon a floor places at generation, as a list of (key, bonus) -- 0, 1, or 2.
    Floors 1-7: the single ordinary weapon. Floors 8-14: an enhanced-Steel find AND a rare
    magical (up to two). Floors 15-20: the rare magical only (the steel slot is spent by
    15). Deterministic on (rng, depth), never the Kodex, so a seed's floors are identical
    for a blind and an omniscient hero."""
    if depth <= 7:
        w = roll_ordinary(rng, depth)
        return [w] if w else []
    out = []
    steel = roll_deep_steel(rng, depth)            # None on floors 15+
    if steel:
        out.append(steel)
    magical = roll_magical(rng, depth)
    if magical:
        out.append(magical)
    return out
```

(`roll_deep_steel` and `roll_magical` are defined just above from Tasks 1–2.)

- [ ] **Step 4: Rewire `dungeon._populate`**

In `deathward/dungeon.py:29`, change the import:

```python
from .items import gear_pool, roll_chest, roll_floor_weapons, roll_loot
```

In `deathward/dungeon.py`, replace the weapon-placement block (currently `wp = roll_floor_weapon(rng, d)` through the `self.drops.append(...)`, ~lines 490–497) with:

```python
        for wkey, wbonus in roll_floor_weapons(rng, d):
            # floor 1's single Bone Axe goes as far from the gate as the level allows (a
            # reward for exploring); the deep floors' finds land on any free tile.
            spot = self._far_room_spot() if d == 1 else None
            if spot is None:
                spot = self._free_tile(avoid_start=True)
            if spot:
                self.drops.append(Drop(spot[0], spot[1], "gear", wkey, bonus=wbonus))
```

(The comment block above it can stay; only the `wp = ...`/`if wp:` logic is replaced. The Warden floor uses `_populate_boss`, which does not call this — so floor 20 still places no found weapon, as the spec intends.)

- [ ] **Step 5: Update `TestWeaponGeneration` to the new interface**

The old `TestWeaponGeneration` calls `roll_floor_weapon` and asserts the *old* deep behaviour. Update it:

- Rename every `roll_floor_weapon(` call to `roll_floor_weapons(` and adapt each assertion to the list return. For the floor-1 and material-band tests (floors 1–7), read the single entry: replace `roll_floor_weapon(rng, d) == ("bone_axe", 0)` with `roll_floor_weapons(rng, d) == [("bone_axe", 0)]`, and in `test_material_bands` gather materials with:

```python
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
```

- **Delete** the now-obsolete deep-floor tests that asserted the OLD rates/pool — `test_floor_eight_plus_is_magical`, `test_present_probability_falls_with_depth`, and `test_enhancement_chance_climbs` if it asserts anything about depth ≥ 8. The deep behaviour is now covered by `TestRollMagical`, `TestRollDeepSteel`, and `TestFloorWeaponsList`. Keep `test_gear_pool_has_no_weapons` unchanged. Keep the floors-2–7 portion of `test_enhancement_chance_climbs` if present by scoping it to depths ≤ 7.

After editing, verify no stale reference remains:

Run: `grep -n "roll_floor_weapon\b" deathward/`
Expected: no output (only `roll_floor_weapons`, plural, remains). If `TestFloorWeaponPlacement` (in the existing suite) references `roll_floor_weapon` or asserts one-weapon-per-floor, update it: floors 8–14 may now hold two weapons (see Task 4's tests); floor 1 still holds exactly one Bone Axe.

- [ ] **Step 6: Run the focused tests and the full suite**

Run: `py -3.13 -m unittest deathward.tests.TestFloorWeaponsList deathward.tests.TestWeaponGeneration -v` then `py -3.13 -m deathward.tests`
Expected: PASS. Investigate any failure — likely a test that hard-coded one-weapon-per-floor or the old deep rates.

- [ ] **Step 7: Commit**

```bash
git add deathward/items.py deathward/dungeon.py deathward/tests.py
git commit -m "roll_floor_weapons returns a list; deep floors place up to two weapons"
```

---

### Task 4: Keep enchant scrolls reachable deep

The enchant scrolls (`krav` weapon, `dwen` armour) are the deep-game scaling path (Plan 3's design leans on them). They are already "uncommon" and reachable from floor 8, but ensure a reliable floor: a small direct chance that a deep scroll drop *is* an enchant scroll.

**Files:**
- Modify: `deathward/items.py` (`roll_consumable`, ~line 351)
- Test: `deathward/tests.py` (new `TestEnchantScrollAvailability` class)

**Interfaces:**
- Consumes: nothing new.
- Produces: `roll_consumable(rng, depth, "scroll")` on `depth >= 8` returns `krav`/`dwen` at least ~15% of the time.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m unittest deathward.tests.TestEnchantScrollAvailability -v`
Expected: FAIL — the enchant rate deep is below 13% (krav/dwen are only 2 of ~6 uncommon scrolls at a 30% uncommon gate ≈ ~10%).

- [ ] **Step 3: Add the deep enchant-scroll floor**

In `deathward/items.py`, at the top of `roll_consumable`, add the bias (before the tier roll):

```python
def roll_consumable(rng, depth, kind):
    """One potion (kind='potion') or scroll (kind='scroll'), rarity gated by depth.
    Falls back to the common pool for any tier that has nothing in it yet."""
    common = POTION_POOL if kind == "potion" else SCROLL_POOL
    # the enchant scrolls are the deep-game scaling path -- keep them reliably in reach
    # from floor 8. drawn from (rng, depth) only, so it does not break bit-identicality.
    if kind == "scroll" and depth >= 8 and rng.random() < 0.15:
        return rng.choice(["krav", "dwen"])
    tier = _consumable_tier(rng, depth)
    if tier == "common":
        return rng.choice(common)
    return rng.choice(_TIER_POOLS.get((kind, tier)) or common)
```

- [ ] **Step 4: Run tests and the full suite**

Run: `py -3.13 -m unittest deathward.tests.TestEnchantScrollAvailability -v` then `py -3.13 -m deathward.tests`
Expected: PASS. If a consumable-distribution test (e.g. in `TestWaveThreeScrolls`/`TestWaveTwoControl`) asserts an exact deep-scroll mix that this bias shifts, update it to allow the enchant floor and note it in the commit.

- [ ] **Step 5: Commit**

```bash
git add deathward/items.py deathward/tests.py
git commit -m "Keep enchant scrolls (krav/dwen) reliably available on floors 8+"
```

---

### Task 5: Integration — bit-identical proof, distribution sanity, playtest

**Files:**
- Verify only (fix fallout where found); optional: a headless distribution check in `deathward/tests.py`.

- [ ] **Step 1: Run the whole suite**

Run: `py -3.13 -m deathward.tests`
Expected: all green. Fix any failure — do not silence it.

- [ ] **Step 2: Confirm the knowledge-is-information invariant**

Run: `py -3.13 -m unittest deathward.tests.TestKnowledgeIsNotPower -v`
Expected: PASS — all new generation draws from `(rng, depth)` at a fixed point, so a blind and an omniscient run of a seed still produce identical floors.

- [ ] **Step 3: Add a headless distribution sanity test**

Append to `deathward/tests.py` (a coarse guard that the run-level economy matches the design's ~1.9 magical / ~2.8 steel per run and the ~12% "no magical" tail):

```python
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
```

Run: `py -3.13 -m unittest deathward.tests.TestDeepEconomyDistribution -v`
Expected: PASS. If the counts are off, the design's tunables (§7) can be nudged — but first confirm the roll functions match Tasks 1–2 exactly.

- [ ] **Step 4: Manual playtest checklist (record in the PR description)**

Run: `py run_deathward.py` (use CTRL+78 to descend quickly) and verify on floors 8–20:
- Floors 8–14 sometimes hold *two* weapons — an enhanced Steel (+1/+2, occasionally +3) and a magical; often just one; sometimes none.
- Magical finds are rare and skew Tier-5 the deeper you go; you never find Windfang or the Void Scimitar on the floor.
- No enhanced Steel appears at floor 15 or below (deeper); floors 16–19 hold only the rare magical; the Warden floor holds no found weapon.
- Enchant scrolls (`krav`) show up often enough deep to keep a carried weapon growing.

- [ ] **Step 5: Final commit (if any fixes were needed)**

```bash
git add -A
git commit -m "Integration fixes for the deep-floor weapon economy"
```

## Self-Review Notes (author)

- **Spec coverage (Plan-2 slice):** two-slot floors 8–15 (Task 3) ✓; enhanced-Steel-only deep with decay-to-0-at-15 + climbing +3 (Task 2) ✓; rare magical with declining presence + T4/T5 crossover (Task 1) ✓; findable pool excludes the two boss weapons (Task 1) ✓; floors 16–20 magical-only (Task 3) ✓; enchant-scroll deep availability (Task 4) ✓; bit-identical invariant (Task 5) ✓; run-level distribution matches the design (Task 5) ✓.
- **Deferred to Plan 3 (not here):** absolute uniqueness, the magical-weapon ledger, world-persistence of dropped magicals, the collector's achievement, the Planescape respawn homage. In this plan the magical slot draws from the findable pool each floor with repeats allowed — Plan 3 layers uniqueness on top.
- **Type consistency:** `roll_magical`/`roll_deep_steel` (Tasks 1–2) return `(key,bonus)|None`; `roll_floor_weapons` (Task 3) returns `list[(key,bonus)]` and is the only weapon roller `dungeon._populate` calls; `roll_floor_weapon` (singular) is removed.
- **Known tunables (playtest):** every rate here — magical 18/15/12%, T5 share 20/40/65%, steel 70%→0 decay and +3 climb, the 15% enchant-scroll floor.
