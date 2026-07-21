# Boots Rebalance — Ordinary Tier & Magical Relocation (Plan 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give boots a mundane ordinary tier (leather/mail/plate, a speed↔defense tradeoff) on floors 1–7, and relocate the five existing exotic boots to the magical floors (8+) as found-only gear — mirroring the weapon rebalance.

**Architecture:** `Boots` gains a `defense` field that folds into the single `player.defense` property (so it stacks with armour and is ignored by wraiths for free). The `BOOTS` table is rebuilt: three new ordinary boots at tiers 1–3, the five existing boots re-tiered to 4/5. `gear_pool` gates the magical boots to floor 8+; the vendor filters its stock to ordinary boots; the "take-all" sweep stops auto-swapping boots once you're off the starter, because a higher-tier boot is a different tradeoff, not a strict upgrade.

**Tech Stack:** Python 3 standard library, `pygame` (already a dependency), `unittest` (tests live in `deathward/tests.py`).

## Global Constraints

- **No new dependencies.** Standard library + existing `pygame` only.
- **Determinism / knowledge-is-information invariant:** gear generation must draw only from `(rng, depth)`, never from the Kodex, so a blind and an omniscient run of the same seed stay bit-identical. All changes here are depth-only; none may read Kodex state.
- **Do not touch the GPL license header** at the top of any file.
- **Do not touch weapons or armour** — only the boots slot and its distribution. Leather/mail/plate as *armour* is a future task.
- **Interim magical tier is throwaway:** the T4/T5 split of the existing five boots is provisional; keep their current stats and traits exactly as they are. The creative rework is Plan 2.
- **Running tests:** whole suite `python -m deathward.tests` (run from the repo root); a single test `python -m deathward.tests <ClassName>.<test_method> -v`.

---

### Task 1: Boots gain a `defense` field

**Files:**
- Modify: `deathward/items.py:84-93` (the `Boots` class)
- Modify: `deathward/player.py:102-109` (the `defense` property)
- Test: `deathward/tests.py` (new `TestBootsRebalance` class, appended before the `if __name__ == "__main__":` block at the end of the file)

**Interfaces:**
- Consumes: nothing (first task).
- Produces: `Boots(key, name, tier, speed, trait=None, note="", defense=0)` — `defense` is a new trailing keyword arg (default `0`), exposed as `Boots.defense`. `player.defense` now includes `self.boots.defense`.

- [ ] **Step 1: Write the failing test**

Append this new class at the very end of `deathward/tests.py`, immediately **before** the `if __name__ == "__main__":` line:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m deathward.tests TestBootsRebalance -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'defense'`.

- [ ] **Step 3: Add the `defense` field to `Boots`**

In `deathward/items.py`, replace the `Boots` class body (lines 84–93):

```python
class Boots:
    slot = "boots"

    def __init__(self, key, name, tier, speed, trait=None, note="", defense=0):
        self.key, self.name, self.tier = key, name, tier
        self.speed, self.trait, self.note = speed, trait, note
        self.defense = defense            # armoured boots (mail/plate); 0 for the rest

    def desc(self):
        s = "%+d spd" % self.speed
        if self.defense:
            s += ", %+d def" % self.defense
        return s + ("  |  " + self.note if self.note else "")
```

(`defense` is a *trailing* keyword arg so every existing positional `Boots(...)` call — including those passing `trait` and `note` positionally — still binds correctly.)

- [ ] **Step 4: Fold boots defense into `player.defense`**

In `deathward/player.py`, replace the `defense` property (lines 102–109):

```python
    @property
    def defense(self):
        d = (self.armour.defense + self.enchants.get(self.armour.key, 0)
             + self.boots.defense)
        if self.stoneskin > 0:
            d += self.STONESKIN_DEF
        if self.heroism > 0:
            d += 3
        return d
```

The wraith path in `world.py:672` skips the whole `dmg - p.defense` subtraction when `ignore_armour=True`, so folding boots defense into this one property means wraiths ignore it automatically — no other change needed.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m deathward.tests TestBootsRebalance -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add deathward/items.py deathward/player.py deathward/tests.py
git commit -m "Boots gain a defense field, folded into player.defense"
```

---

### Task 2: Rebuild the `BOOTS` table — ordinary tier + magical relocation

**Files:**
- Modify: `deathward/items.py:168-178` (the `BOOTS` dict)
- Modify: `deathward/tests.py:1696` (an existing assertion that hard-codes the best-boots tier)
- Test: `deathward/tests.py` (add methods to `TestBootsRebalance`)

**Interfaces:**
- Consumes: `Boots(..., defense=…)` from Task 1.
- Produces: the final `BOOTS` roster — ordinary `leather`(T1,+10/0), `mail`(T2,0/+1), `plate`(T3,−10/+2); magical `swift`/`soft`/`blink`/`ironshod`(T4), `wind`(T5). `sandals`(T0) unchanged. Later tasks rely on these tiers.

- [ ] **Step 1: Write the failing tests**

Add these two methods to `TestBootsRebalance` in `deathward/tests.py`:

```python
    def test_ordinary_boots_are_a_speed_defense_tradeoff(self):
        from .items import BOOTS
        expect = {           # key: (tier, speed, defense)
            "sandals": (0,   0, 0),
            "leather": (1,  10, 0),
            "mail":    (2,   0, 1),
            "plate":   (3, -10, 2),
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
        self.assertEqual(BOOTS["soft"].trait, "softsole")
        self.assertEqual(BOOTS["ironshod"].trait, "kick")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m deathward.tests TestBootsRebalance.test_ordinary_boots_are_a_speed_defense_tradeoff TestBootsRebalance.test_the_five_exotic_boots_relocate_to_magical_tiers_intact -v`
Expected: FAIL — `KeyError: 'leather'` (and the tier assertions fail).

- [ ] **Step 3: Rebuild the `BOOTS` dict**

In `deathward/items.py`, replace the `BOOTS` dict (lines 168–178):

```python
BOOTS = {
    # --- ordinary (floors 1-7): a fast<->tanky tradeoff, no traits -----------
    "sandals":  Boots("sandals", "Worn Sandals", 0, 0),
    "leather":  Boots("leather", "Leather Boots", 1, 10),
    "mail":     Boots("mail", "Mail Boots", 2, 0, defense=1),
    "plate":    Boots("plate", "Plate Boots", 3, -10, defense=2),
    # --- magical (floors 8+): the exotic five, relocated intact (Plan 2 reworks)
    "swift":    Boots("swift", "Swift Boots", 4, 25),
    "soft":     Boots("soft", "Padded Soles", 4, 10, "softsole",
                      "too light to set off a pressure plate"),
    "blink":    Boots("blink", "Boots of Blinking", 4, 15, "blink",
                      "SHIFT+dir to leap three tiles"),
    "ironshod": Boots("ironshod", "Ironshod Boots", 4, 5, "kick",
                      "your blows knock the struck thing back"),
    "wind":     Boots("wind", "Windwalkers", 5, 40),
}
```

- [ ] **Step 4: Fix the existing best-boots assertion**

Re-tiering Windwalkers from 3 to 5 breaks one existing test. In `deathward/tests.py:1696`, change the hard-coded tier:

```python
        self.assertEqual(w.player.boots.tier, 5, "the best boots in the game")
```

(Lines 1697–1699, which compare against `max(g.tier for g in BOOTS.values())` and assert the key is `"wind"`, remain correct.)

- [ ] **Step 5: Run the new tests and the touched existing test to verify they pass**

Run: `python -m deathward.tests TestBootsRebalance.test_ordinary_boots_are_a_speed_defense_tradeoff TestBootsRebalance.test_the_five_exotic_boots_relocate_to_magical_tiers_intact -v`
Expected: PASS (2 tests).

Then re-run the grant-cheat test that owns line 1696 (its class is `TestGrantCheat`; if unsure of the class name, run the whole file):

Run: `python -m deathward.tests`
Expected: the full suite passes (no regressions from the re-tier).

- [ ] **Step 6: Commit**

```bash
git add deathward/items.py deathward/tests.py
git commit -m "Ordinary boots tier (leather/mail/plate); relocate the five exotic boots to T4/T5"
```

---

### Task 3: Gate magical boots to floor 8+ in `gear_pool`

**Files:**
- Modify: `deathward/items.py:365-379` (the `gear_pool` function)
- Test: `deathward/tests.py` (add a method to `TestBootsRebalance`)

**Interfaces:**
- Consumes: the re-tiered `BOOTS` from Task 2.
- Produces: `gear_pool(depth)` includes tier-4/5 boots only when `depth >= 8`; ordinary boots keep their 1+/3+/5+ gates.

- [ ] **Step 1: Write the failing test**

Add this method to `TestBootsRebalance` in `deathward/tests.py`:

```python
    def test_gear_pool_keeps_magical_boots_out_of_the_shallows(self):
        from .items import gear_pool
        magical = {"swift", "blink", "soft", "ironshod", "wind"}
        for depth in (1, 3, 5, 7):
            pool = set(gear_pool(depth))
            self.assertFalse(pool & magical,
                             "no magical boots on floor %d" % depth)
        # ordinary gates: leather from 1, mail from 3, plate from 5
        self.assertIn("leather", gear_pool(1))
        self.assertNotIn("mail", gear_pool(1))
        self.assertIn("mail", gear_pool(3))
        self.assertIn("plate", gear_pool(5))
        # deep floors make the magical boots findable again
        self.assertTrue(set(gear_pool(8)) & magical,
                        "magical boots are reachable on floor 8")
        self.assertIn("wind", gear_pool(10))
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m deathward.tests TestBootsRebalance.test_gear_pool_keeps_magical_boots_out_of_the_shallows -v`
Expected: FAIL — `AssertionError: ... magical boots are reachable on floor 8` (tier-4/5 boots are currently never added to the pool).

- [ ] **Step 3: Add the tier-4/5 depth gate**

In `deathward/items.py`, replace the `gear_pool` function (lines 365–379):

```python
def gear_pool(depth):
    """Armour and boots that can drop at a given depth. Weapons are NOT here -- they are
    placed at generation time (see roll_floor_weapons). Ordinary boots (tier 1-3) follow
    the same shallow gates as armour; magical boots (tier 4-5) surface only on floor 8+,
    mirroring the ordinary/magical split the weapons use."""
    pool = []
    for table in (ARMOURS, BOOTS):
        for key, g in table.items():
            if g.tier == 0:
                continue
            if g.tier == 1 and depth >= 1:
                pool.append(key)
            elif g.tier == 2 and depth >= 3:
                pool.append(key)
            elif g.tier == 3 and depth >= 5:
                pool.append(key)
            elif g.tier >= 4 and depth >= 8:
                pool.append(key)
    return pool
```

(Only the new `elif g.tier >= 4 and depth >= 8` line is added; `ARMOURS` has no tier-4/5 entries, so this affects boots alone.)

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m deathward.tests TestBootsRebalance.test_gear_pool_keeps_magical_boots_out_of_the_shallows -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deathward/items.py deathward/tests.py
git commit -m "gear_pool: magical boots surface only on floor 8+"
```

---

### Task 4: Vendor stocks ordinary boots only

**Files:**
- Modify: `deathward/vendor.py:28-29` (imports) and `deathward/vendor.py:64-72` (`_stock_up`)
- Test: `deathward/tests.py` (add a method to `TestBootsRebalance`)

**Interfaces:**
- Consumes: `gear_pool` from Task 3; the re-tiered `BOOTS`.
- Produces: `Vendor.stock` never contains a gear entry with tier ≥ 4.

- [ ] **Step 1: Write the failing test**

Add this method to `TestBootsRebalance` in `deathward/tests.py`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m deathward.tests TestBootsRebalance.test_vendor_never_stocks_a_magical_boot -v`
Expected: FAIL — a deep vendor stocks a tier-4/5 boot from `gear_pool(depth)` on at least one seed.

- [ ] **Step 3: Filter the vendor's gear pool to ordinary tiers**

In `deathward/vendor.py`, add `ALL_GEAR` to the items import (line 28–29):

```python
from .items import (ALL_GEAR, ARMOURS, BOOTS, CONSUMABLES, POTION_POOL, SCROLL_POOL,
                    WEAPONS, gear_pool)
```

Then in `_stock_up` (lines 64–72), filter the pool to tier ≤ 3:

```python
    def _stock_up(self, rng, depth):
        # ordinary gear only -- magical boots are found, never bought (as with weapons)
        pool = [k for k in gear_pool(depth) if ALL_GEAR[k].tier <= 3]
        if pool:
            for _ in range(rng.randint(1, 2)):
                self.stock.append(("gear", rng.choice(pool)))
        for _ in range(rng.randint(2, 3)):
            self.stock.append(("item", rng.choice(POTION_POOL)))
        for _ in range(rng.randint(1, 2)):
            self.stock.append(("item", rng.choice(SCROLL_POOL)))
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m deathward.tests TestBootsRebalance.test_vendor_never_stocks_a_magical_boot -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deathward/vendor.py deathward/tests.py
git commit -m "Vendor stocks ordinary boots only; magical boots are found-only"
```

---

### Task 5: The take-all sweep respects the boots tradeoff

**Files:**
- Modify: `deathward/world.py:911-917` (the `auto` gear branch in `_consume_option`)
- Test: `deathward/tests.py` (add a method to `TestBootsRebalance`)

**Interfaces:**
- Consumes: the re-tiered `BOOTS`; `World.take_all`, `World.drop_gear_near` (both existing).
- Produces: under the `auto=True` sweep, a found boot is equipped only when the current boots are the T0 starter; weapons/armour behaviour is unchanged.

- [ ] **Step 1: Write the failing test**

Add this method to `TestBootsRebalance` in `deathward/tests.py`:

```python
    def test_the_sweep_takes_a_boot_over_the_starter_but_never_downgrades_a_choice(self):
        from .items import BOOTS
        w = World(FakeSave(), seed=4)
        w.player.boots = BOOTS["sandals"]                # the bare starter (T0)
        spot = w.drop_gear_near("leather")
        self.assertIsNotNone(spot)
        w.player.x, w.player.y = spot
        w.take_all()
        self.assertEqual(w.player.boots.key, "leather",
                         "the first boot is auto-equipped over the bare starter")
        # now wearing a chosen boot: the sweep must NOT swap in a heavier plate
        spot = w.drop_gear_near("plate")
        self.assertIsNotNone(spot)
        w.player.x, w.player.y = spot
        w.take_all()
        self.assertEqual(w.player.boots.key, "leather",
                         "the all-sweep never trades a chosen boot behind your back")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m deathward.tests TestBootsRebalance.test_the_sweep_takes_a_boot_over_the_starter_but_never_downgrades_a_choice -v`
Expected: FAIL — the second `take_all` swaps leather (T1) for plate (T3) because `g.tier > cur.tier`, so `w.player.boots.key == "plate"`.

- [ ] **Step 3: Special-case boots in the auto sweep**

In `deathward/world.py`, replace the `auto` gear branch (lines 911–917):

```python
        if kind == "gear" and auto:
            g = ALL_GEAR[payload]
            cur = {"weapon": p.weapon, "armour": p.armour, "boots": p.boots}[g.slot]
            if g.slot == "boots":
                # Boots trade speed for defense, so a higher tier is a different choice,
                # not a strict upgrade. The 'all' sweep only auto-equips a boot over the
                # bare starter; past that a found boot is left for a deliberate pickup.
                if cur.tier > 0:
                    self.log("You step over the %s -- boots are a choice; take them "
                             "by hand." % g.name, config.DIM)
                    return False
            elif g.tier <= cur.tier:
                self.log("You leave the %s -- your %s is better." % (g.name, cur.name),
                         config.DIM)
                return False
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m deathward.tests TestBootsRebalance.test_the_sweep_takes_a_boot_over_the_starter_but_never_downgrades_a_choice -v`
Expected: PASS.

- [ ] **Step 5: Run the whole suite to confirm no regressions**

Run: `python -m deathward.tests`
Expected: the full suite passes.

- [ ] **Step 6: Commit**

```bash
git add deathward/world.py deathward/tests.py
git commit -m "Take-all sweep leaves boots as a manual choice once off the starter"
```

---

## Notes for the implementer

- **Read tasks in order.** Each builds on the last; the `BOOTS` table is final after Task 2, distribution after Task 3.
- **The `config` module** is already imported in `world.py` (used for `config.DIM`); no new import is needed in Task 5.
- **`FakeSave`** (defined at `deathward/tests.py:44`, a `Codex` subclass) and `World(FakeSave(), seed=N)` are the standard test fixtures — reuse them as shown.
- If `python -m deathward.tests <Class>.<method>` reports "no tests ran" for a single method, run the whole class (`python -m deathward.tests TestBootsRebalance -v`) or the whole file (`python -m deathward.tests`).
