# Magical Boots — Phase 3 Plan A (Rarity + Uniqueness + Placement) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pull the 12 magical boots out of the generic loot pool into a rare, one-per-floor, one-per-game-unique generation slot on floors 8+ — mirroring the magical weapons.

**Architecture:** A new `roll_floor_boots_magical(rng, depth, exclude)` (parallel to `roll_magical`) places at most one magical boot per floor 8+, excluding keys already generated this game (a new `codex.boots_generated` ledger). Magical boots are removed from `gear_pool`, and the slot is placed at floor generation in `dungeon.py`. Persistence (survives death) and the collection award are Plan B.

**Tech Stack:** Python 3 standard library, `pygame`, `unittest` (`deathward/tests.py`).

## Global Constraints

- **No new dependencies.** Standard library + existing `pygame`.
- **Determinism:** `roll_floor_boots_magical` draws only from `(rng, depth, exclude)` where `exclude` is run-history (`boots_generated`), never the Kodex. `TestKnowledgeIsNotPower` (tests.py:323) must stay green.
- **Do not touch the GPL header** in any file.
- **Scope fence:** only the magical-boots *distribution/uniqueness*. Do NOT touch weapons, armour, ordinary boots (`roll_floor_boots`), boot stats/mechanics, or persistence/collection (Plan B).
- **The 12 findable magical boots** (all findable — no mini-boss-reserved boots): T4 = `swift`, `soft`, `blink`, `ironshod`, `emberstride`, `rimewalkers`, `phantom`; T5 = `wind`, `featherfall`, `thor`, `slipstep`, `whisperstep`.
- **Rarity numbers:** present-chance 14% (depth ≤ 11), 12% (≤ 15), 10% (16–20); T5-share 20% / 40% / 65% over the same bands. Floors < 8: none.
- **Running tests — use `py -3.13`, NOT `python`** (3.14 lacks pygame). Whole suite: `py -3.13 -m deathward.tests` (baseline: 507 green). One test: `py -3.13 -m deathward.tests <ClassName>.<test_method> -v`.

## Shared references

- `roll_magical` (items.py:439) is the template for `roll_floor_boots_magical`. `FINDABLE_MAGICAL`/`is_magical` (items.py:425-436) are the weapon parallels.
- `gear_pool` (items.py:403-419) currently appends magical boots (`tier >= 4 and depth >= 8`).
- The weapon generation slot in `dungeon.py:512-522` and the ordinary-boots slot at `dungeon.py:527-530` are the placement template. `codex.record_magical_placed` (codex.py:915) is the ledger template.
- Codex ledger wiring: init (codex.py:651), `load` (codex.py:718), `_save_dict` (codex.py:739), `new_dungeon` reset (codex.py:834).
- New tests go in a new `TestMagicalBootsEconomy(unittest.TestCase)` at the END of `deathward/tests.py`, before `if __name__ == "__main__":`. `World(FakeSave(), seed=N)`, `FakeSave()` (a `Codex` subclass).

---

### Task 1: `roll_floor_boots_magical` + the findable set + `is_magical_boot`

**Files:**
- Modify: `deathward/items.py` (add near `FINDABLE_MAGICAL`/`roll_magical`, ~line 425-453)
- Test: `deathward/tests.py` (new `TestMagicalBootsEconomy`)

**Interfaces:**
- Produces: `FINDABLE_MAGICAL_BOOTS` (`{4: [...7], 5: [...5]}`), `FINDABLE_MAGICAL_BOOT_KEYS` (all 12), `is_magical_boot(key) -> bool`, `roll_floor_boots_magical(rng, depth, exclude=()) -> str | None`. Tasks 2–4 consume these.

- [ ] **Step 1: Write the failing tests**

Add this new class at the end of `deathward/tests.py`, before `if __name__ == "__main__":`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -3.13 -m deathward.tests TestMagicalBootsEconomy -v`
Expected: FAIL — `ImportError: cannot import name 'FINDABLE_MAGICAL_BOOT_KEYS'` (and `is_magical_boot`/`roll_floor_boots_magical` don't exist).

- [ ] **Step 3: Add the findable set + `is_magical_boot`**

In `deathward/items.py`, after the `is_magical` function (~line 436), add:

```python
# The magical boots a floor can DROP -- all 12 are findable (no mini-boss-reserved boots).
FINDABLE_MAGICAL_BOOTS = {
    4: ["swift", "soft", "blink", "ironshod", "emberstride", "rimewalkers", "phantom"],
    5: ["wind", "featherfall", "thor", "slipstep", "whisperstep"],
}
FINDABLE_MAGICAL_BOOT_KEYS = set(FINDABLE_MAGICAL_BOOTS[4]) | set(FINDABLE_MAGICAL_BOOTS[5])


def is_magical_boot(key):
    """A magical boot (tier 4 or 5). The single source of truth for the boots ledger."""
    return key in BOOTS and BOOTS[key].tier >= 4
```

- [ ] **Step 4: Add `roll_floor_boots_magical`**

In `deathward/items.py`, add (near `roll_magical`, after the block above):

```python
def roll_floor_boots_magical(rng, depth, exclude=()):
    """The rare magical-boots slot for floors 8-20: at most one magical boot per floor,
    one-per-game unique. `exclude` (the already-generated boot keys) filters the chosen
    tier's pool; if that tier is exhausted, none drops. Draws only from (rng, depth, exclude)
    -- run-history, never the Kodex -- so blind and omniscient runs stay bit-identical.
    Returns a boot key, or None. Boots carry no enhancement, so there is no bonus."""
    if depth < 8:
        return None
    present = 0.14 if depth <= 11 else 0.12 if depth <= 15 else 0.10
    if rng.random() >= present:
        return None
    t5_share = 0.20 if depth <= 11 else 0.40 if depth <= 15 else 0.65
    tier = 5 if rng.random() < t5_share else 4
    pool = [k for k in FINDABLE_MAGICAL_BOOTS[tier] if k not in exclude]
    if not pool:
        return None
    return rng.choice(pool)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `py -3.13 -m deathward.tests TestMagicalBootsEconomy -v`
Expected: PASS (3 tests). Then the full suite:
Run: `py -3.13 -m deathward.tests`
Expected: still green (nothing calls the new function yet).

- [ ] **Step 6: Commit**

```bash
git add deathward/items.py deathward/tests.py
git commit -m "Magical boots: is_magical_boot, findable set, and the rare roll_floor_boots_magical"
```

---

### Task 2: Remove magical boots from `gear_pool`

**Files:**
- Modify: `deathward/items.py:403-419` (`gear_pool`)
- Test: `deathward/tests.py` — replace the now-false `test_gear_pool_excludes_ordinary_boots_and_still_gates_magical` (tests.py:7079)

**Interfaces:**
- Produces: `gear_pool(depth)` contains **no boots** at any depth (armour only). Magical boots now come solely from the generation slot (Task 4).

- [ ] **Step 1: Write the failing test**

Replace `test_gear_pool_excludes_ordinary_boots_and_still_gates_magical` (tests.py:7079-7096) with:

```python
    def test_gear_pool_holds_no_boots_at_all_only_armour(self):
        from .items import gear_pool, BOOTS
        all_boots = set(BOOTS)
        for depth in range(1, 21):
            pool = set(gear_pool(depth))
            self.assertFalse(pool & all_boots,
                             "no boots in gear_pool -- every boot is generation-placed "
                             "(floor %d)" % depth)
        # armour is untouched -- the Leather Jerkin (key 'leather') is armour, not a boot
        self.assertIn("leather", gear_pool(1))
        self.assertIn("plate", gear_pool(5))
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `py -3.13 -m deathward.tests TestBootsRebalance.test_gear_pool_holds_no_boots_at_all_only_armour -v`
Expected: FAIL — magical boots (tier ≥ 4) are still in `gear_pool` at depth 8+, so `pool & all_boots` is non-empty on the deep floors.

- [ ] **Step 3: Drop the magical-boots branch from `gear_pool`**

In `deathward/items.py`, replace `gear_pool` (lines 403–419):

```python
def gear_pool(depth):
    """Armour that the generic loot tables and the vendor may surface at a given depth.
    Weapons and ALL boots are placed at generation (roll_floor_weapons / roll_floor_boots /
    roll_floor_boots_magical), scarce and one-per-floor -- none come from this pool."""
    pool = []
    for key, g in ARMOURS.items():
        if g.tier == 1 and depth >= 1:
            pool.append(key)
        elif g.tier == 2 and depth >= 3:
            pool.append(key)
        elif g.tier == 3 and depth >= 5:
            pool.append(key)
    return pool
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `py -3.13 -m deathward.tests TestBootsRebalance.test_gear_pool_holds_no_boots_at_all_only_armour -v`
Expected: PASS. Then the full suite:
Run: `py -3.13 -m deathward.tests`
Expected: green — the vendor test (`test_vendor_never_stocks_a_magical_boot`) still passes (the pool has no boots at all now), and the floor-1 gift tests still pass (armour keeps the pool non-empty).

- [ ] **Step 5: Commit**

```bash
git add deathward/items.py deathward/tests.py
git commit -m "Magical boots leave gear_pool -- now generation-placed only"
```

---

### Task 3: The `boots_generated` uniqueness ledger

**Files:**
- Modify: `deathward/codex.py` — init (~651), `load` (~718), `_save_dict` (~739), `new_dungeon` reset (~834), and a new `record_magical_boot_placed` method (near `record_magical_placed`, ~915)
- Test: `deathward/tests.py` (`TestMagicalBootsEconomy`)

**Interfaces:**
- Produces: `codex.boots_generated` (list of keys generated this game); `codex.record_magical_boot_placed(key, depth, x, y)` adds the key to `boots_generated` (idempotent). It round-trips save/load and resets on a new game. (`depth, x, y` are accepted now for the persistence ledger Plan B adds to this method; unused this task.)

- [ ] **Step 1: Write the failing test**

Add to `TestMagicalBootsEconomy`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `py -3.13 -m deathward.tests TestMagicalBootsEconomy.test_boots_generated_ledger_records_uniquely_and_persists -v`
Expected: FAIL — `AttributeError: 'FakeSave' object has no attribute 'boots_generated'`.

- [ ] **Step 3: Add the ledger field (init, load, save, reset)**

In `deathward/codex.py`:

- After `self.magical_collected = []` (line 653), add:
```python
        self.boots_generated = []      # magical-boot keys generated this GAME (uniqueness set)
```
- In `load`, after `self.magical_collected = data.get("magical_collected", [])` (line 720):
```python
        self.boots_generated = data.get("boots_generated", [])
```
- In `_save_dict`'s returned dict, after `"magical_collected": self.magical_collected,` (line 741):
```python
            "boots_generated": self.boots_generated,
```
- In `new_dungeon`, after `self.magical_collected = []` (line 836), add:
```python
        self.boots_generated = []
```

- [ ] **Step 4: Add `record_magical_boot_placed`**

In `deathward/codex.py`, near `record_magical_placed` (~line 921), add:

```python
    def record_magical_boot_placed(self, key, depth, x, y):
        """A magical boot has entered the world (rolled at generation). It never rolls again
        (uniqueness). (Phase 3 Plan B records its floor position here for death-persistence.)"""
        if key not in self.boots_generated:
            self.boots_generated.append(key)
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `py -3.13 -m deathward.tests TestMagicalBootsEconomy.test_boots_generated_ledger_records_uniquely_and_persists -v`
Expected: PASS. Then the full suite:
Run: `py -3.13 -m deathward.tests`
Expected: green (save/load round-trips the new field; nothing else affected).

- [ ] **Step 6: Commit**

```bash
git add deathward/codex.py deathward/tests.py
git commit -m "Codex: boots_generated uniqueness ledger + record_magical_boot_placed"
```

---

### Task 4: Place the floor's magical boot at generation

**Files:**
- Modify: `deathward/dungeon.py:29` (import), `deathward/dungeon.py:524-530` (after the ordinary-boots slot)
- Test: `deathward/tests.py` (`TestMagicalBootsEconomy`)

**Interfaces:**
- Consumes: `roll_floor_boots_magical` (Task 1), `codex.boots_generated` + `record_magical_boot_placed` (Task 3).
- Produces: a generated `Level`'s `.drops` holds at most one magical boot (floors 8+), each recorded in `codex.boots_generated`; a key is never placed twice across a game.

- [ ] **Step 1: Write the failing tests**

Add to `TestMagicalBootsEconomy`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -3.13 -m deathward.tests TestMagicalBootsEconomy.test_magical_boots_appear_deep_recorded_and_never_shallow -v`
Expected: FAIL — `appeared` stays False (magical boots are placed nowhere now that they left `gear_pool` and the generation slot isn't wired).

- [ ] **Step 3: Import the roll in dungeon.py**

In `deathward/dungeon.py`, add `roll_floor_boots_magical` to the items import (line 29):

```python
from .items import (gear_pool, is_magical, roll_chest, roll_floor_boots,
                    roll_floor_boots_magical, roll_floor_weapons, roll_loot)
```

- [ ] **Step 4: Place the floor's magical boot after the ordinary-boots slot**

In `deathward/dungeon.py`, immediately after the ordinary-boots loop (after line 530, before the floor-1 gift block), add:

```python
        # THE FLOOR'S MAGICAL BOOT (floors 8+). The rare slot, like the magical weapons:
        # scarce, one-per-game unique (exclude the already-generated), generation-placed --
        # never from the generic loot pool.
        mbkey = roll_floor_boots_magical(rng, d, exclude=codex.boots_generated)
        if mbkey:
            spot = self._free_tile(avoid_start=True)
            if spot:
                self.drops.append(Drop(spot[0], spot[1], "gear", mbkey))
                # it now EXISTS: never rolls again this game (persistence lands in Plan B).
                codex.record_magical_boot_placed(mbkey, d, spot[0], spot[1])
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `py -3.13 -m deathward.tests TestMagicalBootsEconomy -v`
Expected: PASS (all economy tests). Then the full suite:
Run: `py -3.13 -m deathward.tests`
Expected: green — including `TestKnowledgeIsNotPower` (the new roll draws only `(rng, depth, boots_generated)` — run-history, never the Kodex).

- [ ] **Step 6: Commit**

```bash
git add deathward/dungeon.py deathward/tests.py
git commit -m "Place the floor's rare magical boot at generation (floors 8+, one-per-game)"
```

---

## Notes for the implementer

- **Read tasks in order.** Task 4 depends on Tasks 1 and 3.
- **`Drop`** is already used in dungeon.py; its signature is `Drop(x, y, kind, payload, gift=None, bonus=0)` — the magical boot needs no bonus, so `Drop(x, y, "gear", mbkey)`.
- A floor 8–15 can now hold up to a weapon + an ordinary boot + a magical boot (+ armour from generic loot) — the same "several gear pieces, one per category-slot" shape the weapons already use. That is intended.
- Persistence (survives death, replayed each life) and the collection gold star are **Plan B** — do not implement them here.
- If a single test reports "no tests ran", run the class or the whole file.
