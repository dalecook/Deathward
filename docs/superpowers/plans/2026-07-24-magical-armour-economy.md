# Magical Armour Economy (Plan C) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give magical armour the same deep economy as weapons and boots — persistence across death, a full-set collection gold star — and retune the drop rates to a genuine multi-run grind.

**Architecture:** Mirror the existing boots economy (a 1:1 mirror of the weapon economy). Codex gains parallel `armour_ground` / `armour_collected` ledgers; `Level._replay_magicals` (already generalized) re-places persisted armour each life; `World` wires pickup/displacement into the same three sites the boots use. The drop roll is rewritten to a one-piece-per-floor / T5-first-dibs model whose rates live in `config.py`.

**Tech Stack:** Python 3.13 (pygame). Test cmd: `py -3.13 -m deathward.tests` (NOT 3.14 — no pygame).

## Global Constraints

- **Determinism (`TestKnowledgeIsNotPower`) must stay green.** All armour rolls and ledger writes read only `(rng, depth, exclude=armour_generated)` — never the Kodex. `armour_generated` is placement-driven, identical between a blind and an omniscient run of the same seed.
- **The collection star is over `FINDABLE_MAGICAL_ARMOUR_KEYS` (the 12 findable pieces).** Boss-reserved `nightcloak` and `shade` are excluded from the findable set; they neither block nor are required for the star.
- **Armour ground entries carry a `bonus`** (like weapons, unlike boots) so a DWEN-enchanted magical armour survives death at its enchanted value.
- **No save-format version bump.** `armour_ground` / `armour_collected` are codex save keys loaded tolerantly (`data.get(..., default)`); an older codex save reads back empty ledgers.
- **One magical piece per floor.** The magical slot is independent of the ordinary-armour slot but yields at most one magical piece itself.
- Reference implementation to mirror throughout: the boots economy (`record_magical_boot_placed`, `drop_magical_boot_to_ground`, `magical_boot_picked_up`, `award_boots_collection`, `boots_ground`, `boots_collected`) and its tests (`tests.py:8037-8164`).

---

### Task 1: Distribution retune (config bands + one-per-floor / T5-first-dibs roll)

**Files:**
- Modify: `deathward/config.py` (add band constants)
- Modify: `deathward/items.py:34` (add `from . import config`), `deathward/items.py:524-538` (rewrite `roll_floor_armour_magical`, add `_band_chance` helper)
- Test: `deathward/tests.py` (new `TestArmourMagicalDistribution`)

**Interfaces:**
- Consumes: `FINDABLE_MAGICAL_ARMOUR` (dict `{4: [...], 5: [...]}`) — unchanged.
- Produces: `roll_floor_armour_magical(rng, depth, exclude=())` — same signature; new internal model. `config.ARMOUR_MAGICAL_T4_BANDS`, `config.ARMOUR_MAGICAL_T5_BANDS` (each a list of `(lo, hi, chance)`).

**Model:** On a floor at depth *d* ≥ 8, T5 is rolled first (its own band), then T4 only if T5 missed — so at most one magical piece, P(any) = p₅ + (1−p₅)·p₄. If a rolled tier's pool is exhausted by `exclude`, fall through to the other tier (avoids dead slots once a tier is fully collected). Floor 20 is the boss floor and never calls this (populate_boss).

**⚠️ Risk this task carries:** the new roll consumes a different number of run-rng draws per floor than the old one (floors 10–19 can now draw twice). That deterministically shifts other run-rng placements on floors 8–19. Existing seed-pinned deep-floor tests may legitimately shift — re-run the FULL suite and adapt any shifted assertions honestly (the determinism invariant, blind==omniscient, must still hold; only absolute positions may move).

- [ ] **Step 1: Write the failing test**

Add to `deathward/tests.py` (module level, near the other helpers):

```python
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
```

Ensure `roll_floor_armour_magical` is imported at the top of `tests.py` (it is already used/importable via the `from .items import ...` block — add it there if missing).

- [ ] **Step 2: Run the test to verify it fails**

Run: `py -3.13 -m deathward.tests TestArmourMagicalDistribution -v`
Expected: FAIL (behaviour differs — old roll uses a single present-chance then a t5_share split; `_SeqRng` sequences won't map, and `config.ARMOUR_MAGICAL_*` don't exist yet).

- [ ] **Step 3: Add the config band constants**

In `deathward/config.py` (near the other tuning constants, e.g. after `DEPTH_MAX = 20`):

```python
# --- Magical-armour drop bands (Plan C) -------------------------------------
# At most ONE magical-armour piece per floor. T5 is rolled first (its own,
# deep-weighted band); only if it misses is T4 rolled. Each entry is
# (lo_floor, hi_floor, present_chance). Floors 8-9 give T4 a higher chance
# because T5 does not start until floor 10 (no early dead zone).
ARMOUR_MAGICAL_T4_BANDS = [(8, 9, 0.20), (10, 11, 0.12), (12, 15, 0.10), (16, 20, 0.06)]
ARMOUR_MAGICAL_T5_BANDS = [(10, 13, 0.08), (14, 17, 0.12), (18, 20, 0.20)]
```

- [ ] **Step 4: Rewrite the roll (and add the band helper)**

In `deathward/items.py`, add the config import at the top (after `import random`, line 34):

```python
from . import config
```

Replace `roll_floor_armour_magical` (currently `items.py:524-538`) and add the helper just above it:

```python
def _band_chance(bands, depth):
    """The present-chance for `depth` from a list of (lo, hi, chance) bands, or 0.0."""
    for lo, hi, chance in bands:
        if lo <= depth <= hi:
            return chance
    return 0.0


def roll_floor_armour_magical(rng, depth, exclude=()):
    """The rare magical-armour slot for floors 8-19: at most ONE piece per floor.
    T5 is rolled first (its own deep-weighted band); only if it misses is T4 rolled --
    so P(any) = p5 + (1-p5)*p4. One-per-game unique (exclude the already-generated); a
    rolled tier whose pool is exhausted falls through to the other tier. Draws only from
    (rng, depth, exclude) -- never the Kodex -- so blind and omniscient runs stay
    bit-identical. Returns an armour key, or None."""
    if depth < 8:
        return None
    for tier, bands in ((5, config.ARMOUR_MAGICAL_T5_BANDS),
                        (4, config.ARMOUR_MAGICAL_T4_BANDS)):
        chance = _band_chance(bands, depth)
        if chance <= 0.0:
            continue
        if rng.random() < chance:
            pool = [k for k in FINDABLE_MAGICAL_ARMOUR[tier] if k not in exclude]
            if pool:
                return rng.choice(pool)
            # tier present but exhausted -- fall through to the other tier
    return None
```

- [ ] **Step 5: Run the new test to verify it passes**

Run: `py -3.13 -m deathward.tests TestArmourMagicalDistribution -v`
Expected: PASS (all 6).

- [ ] **Step 6: Run the FULL suite and determinism check; adapt shifted assertions honestly**

Run: `py -3.13 -m deathward.tests`
Expected: OK. If any seed-pinned deep-floor test fails, confirm it is a legitimate rng-shift (the new roll consumes different draw counts on floors 8-19), update the expected value to the new deterministic result, and re-run. Then explicitly:
Run: `py -3.13 -m deathward.tests TestKnowledgeIsNotPower -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add deathward/config.py deathward/items.py deathward/tests.py
git commit -m "Plan C Task 1: retune magical-armour drops (one/floor, T5 first-dibs, config bands)"
```

---

### Task 2: Persistence (armour_ground ledger + replay each life)

**Files:**
- Modify: `deathward/codex.py` — `__init__` (after `armour_generated`, ~662), `_load_from` (after ~735), `_save_dict` (after ~770), `new_dungeon` (after ~871), `record_magical_armour_placed` (~965), add `drop_magical_armour_to_ground`
- Modify: `deathward/dungeon.py:_generate` (~444-451: snapshot + replay)
- Test: `deathward/tests.py` (new `TestArmourPersistence`)

**Interfaces:**
- Consumes: `codex.armour_generated` (exists), `Level._replay_magicals(persisted)` (exists, already reads `loc.get("bonus", 0)`).
- Produces: `codex.armour_ground` (`key -> {"depth","x","y","bonus"}`); `codex.record_magical_armour_placed(key, depth, x, y)` now also grounds (bonus 0); `codex.drop_magical_armour_to_ground(key, depth, x, y, bonus)`.

- [ ] **Step 1: Write the failing test**

Add to `deathward/tests.py`:

```python
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
```

(If `Drop` exposes its bonus under a different attribute than `.bonus`, check `dungeon.Drop` and adjust the last assertion — `_replay_magicals` constructs `Drop(mx, my, "gear", key, bonus=loc.get("bonus", 0))`.)

- [ ] **Step 2: Run to verify it fails**

Run: `py -3.13 -m deathward.tests TestArmourPersistence -v`
Expected: FAIL (`AttributeError: 'FakeSave' object has no attribute 'armour_ground'`).

- [ ] **Step 3: Add the `armour_ground` ledger to Codex state**

In `deathward/codex.py`:

`__init__`, right after `self.armour_generated = []` (~line 662):
```python
        self.armour_ground = {}        # magical armour lying on a floor (re-placed each life)
```

`_load_from`, right after `self.armour_generated = data.get("armour_generated", [])` (~line 735):
```python
        self.armour_ground = data.get("armour_ground", {})
```

`_save_dict`, right after `"armour_generated": self.armour_generated,` (~line 770):
```python
            "armour_ground": self.armour_ground,
```

`new_dungeon`, right after `self.armour_generated = []` (~line 871):
```python
        self.armour_ground = {}
```

- [ ] **Step 4: Extend `record_magical_armour_placed` and add `drop_magical_armour_to_ground`**

Replace `record_magical_armour_placed` (`codex.py:965-970`):
```python
    def record_magical_armour_placed(self, key, depth, x, y):
        """A magical armour has entered the world (rolled at generation). It never rolls
        again this game (uniqueness) and lies where it was placed until picked up
        (persistence) -- re-placed each life by Level._replay_magicals. Fresh generation
        is never masterworked, so it grounds at bonus 0."""
        if key not in self.armour_generated:
            self.armour_generated.append(key)
        self.armour_ground[key] = {"depth": depth, "x": x, "y": y, "bonus": 0}

    def drop_magical_armour_to_ground(self, key, depth, x, y, bonus):
        """The hero left a magical armour on the bare floor; it stays there across lives,
        at whatever bonus it was enchanted to."""
        if key not in self.armour_generated:
            self.armour_generated.append(key)
        self.armour_ground[key] = {"depth": depth, "x": x, "y": y, "bonus": bonus}
```

- [ ] **Step 5: Snapshot + replay armour ground in `Level._generate`**

In `deathward/dungeon.py:_generate` (~444-451), add the armour snapshot beside the others and replay it after populate:

```python
        persisted_magicals = dict(codex.magical_ground)
        persisted_boots = dict(codex.boots_ground)
        persisted_armours = dict(codex.armour_ground)
        if self.depth >= config.DEPTH_MAX:
            self._populate_boss()
        else:
            self._populate(codex)
        self._replay_magicals(persisted_magicals)
        self._replay_magicals(persisted_boots)
        self._replay_magicals(persisted_armours)
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `py -3.13 -m deathward.tests TestArmourPersistence -v`
Expected: PASS (all 5).

- [ ] **Step 7: Full suite + determinism**

Run: `py -3.13 -m deathward.tests`
Expected: OK.
Run: `py -3.13 -m deathward.tests TestKnowledgeIsNotPower -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add deathward/codex.py deathward/dungeon.py deathward/tests.py
git commit -m "Plan C Task 2: magical-armour persistence (armour_ground + replay each life)"
```

---

### Task 3: Collection (armour_collected ledger + gold star + Kodex fact)

**Files:**
- Modify: `deathward/codex.py` — `__init__` (after `armour_ground`), `stats` init (~698-699), `_load_from` (after `armour_ground`), `_save_dict` (after `armour_ground`), `new_dungeon` (after `armour_ground`), FACTS table (after `magical_boot_collector`, ~96); add `magical_armour_picked_up`, `award_armour_collection`
- Test: `deathward/tests.py` (new `TestArmourCollection`)

**Interfaces:**
- Consumes: `items.FINDABLE_MAGICAL_ARMOUR_KEYS` (exists), `codex.armour_ground` (Task 2), `codex._grant` / `codex.known` / `codex.stats`.
- Produces: `codex.armour_collected` (list); `codex.magical_armour_picked_up(key) -> bool` (True the first time the 12 findable are all collected); `codex.award_armour_collection()`; stat `magical_armours_collected_all`; Kodex fact `self.magical_armour_collector`.

- [ ] **Step 1: Write the failing test**

Add to `deathward/tests.py`:

```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `py -3.13 -m deathward.tests TestArmourCollection -v`
Expected: FAIL (`AttributeError: ... 'magical_armour_picked_up'`).

- [ ] **Step 3: Add the `armour_collected` ledger + stat**

In `deathward/codex.py`:

`__init__`, right after `self.armour_ground = {}` (Task 2):
```python
        self.armour_collected = []     # magical armour ever picked up (drives the armour award)
```

`stats` init, add after `"magical_boots_collected_all": 0,` (~line 699):
```python
            "magical_armours_collected_all": 0,
```

`_load_from`, after `self.armour_ground = data.get("armour_ground", {})`:
```python
        self.armour_collected = data.get("armour_collected", [])
```

`_save_dict`, after `"armour_ground": self.armour_ground,`:
```python
            "armour_collected": self.armour_collected,
```

`new_dungeon`, after `self.armour_ground = {}`:
```python
        self.armour_collected = []
```

- [ ] **Step 4: Register the collector Kodex fact**

In `deathward/codex.py`, in the FACTS list, right after the `self.magical_boot_collector` entry (~lines 92-96):
```python
    _f("self.magical_armour_collector", "self", "secret",
       "EVERY WARD THE DEEP STILL KEEPS",
       "You have worn every magical armour this dungeon will yield -- the whole rare "
       "roster, gathered by one hand across many deaths. A gold star of its own, for the "
       "back that has borne every ward the deep still keeps."),
```

(Headline/body are placeholders; the user may reword — same as the boots/weapon lines.)

- [ ] **Step 5: Add `magical_armour_picked_up` and `award_armour_collection`**

In `deathward/codex.py`, alongside the boots equivalents:
```python
    def magical_armour_picked_up(self, key):
        """The hero has a magical armour on their back: mark it collected, take it off the
        ground. Returns True the first time the 12 findable armours are all collected."""
        from .items import FINDABLE_MAGICAL_ARMOUR_KEYS
        self.armour_ground.pop(key, None)
        if key not in self.armour_generated:
            self.armour_generated.append(key)
        was_complete = FINDABLE_MAGICAL_ARMOUR_KEYS <= set(self.armour_collected)
        if key not in self.armour_collected:
            self.armour_collected.append(key)
        now_complete = FINDABLE_MAGICAL_ARMOUR_KEYS <= set(self.armour_collected)
        return now_complete and not was_complete

    def award_armour_collection(self):
        """Grant the armour collector's Kodex fact once. Permanent (survives a new dungeon);
        the collected-set that earns it is per-game."""
        self.stats["magical_armours_collected_all"] = 1
        if "self.magical_armour_collector" not in self.known:
            self._grant("self.magical_armour_collector")
            self.save()
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `py -3.13 -m deathward.tests TestArmourCollection -v`
Expected: PASS (all 4).

- [ ] **Step 7: Full suite**

Run: `py -3.13 -m deathward.tests`
Expected: OK. (If a test asserts a total FACTS count or renders every fact, update it for the one new fact.)

- [ ] **Step 8: Commit**

```bash
git add deathward/codex.py deathward/tests.py
git commit -m "Plan C Task 3: magical-armour collection (armour_collected + gold star + Kodex fact)"
```

---

### Task 4: World wiring (pickup on equip, bench, and drop-to-ground on displacement)

**Files:**
- Modify: `deathward/world.py:37-38` (import `is_magical_armour`), `world.py:1327-1331` (`_take` equip path), `world.py:1442-1446` (`cheat_equip_armour`), `world.py:1599-1614` (`_put_back`)
- Test: `deathward/tests.py` (new `TestArmourEconomyWiring`)

**Interfaces:**
- Consumes: `codex.magical_armour_picked_up`, `codex.award_armour_collection`, `codex.drop_magical_armour_to_ground` (Tasks 2-3); `items.is_magical_armour` (exists).
- Produces: full lifecycle — equipping a magical armour collects it; completing the set awards the star; a displaced magical armour goes to bare ground (never a container) and re-grounds.

- [ ] **Step 1: Write the failing test**

Add to `deathward/tests.py`:

```python
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
```

(Check `dungeon.Chest`'s constructor signature — mirror how the boots test at `tests.py:8158` builds its sink; if `Chest(x, y, loot)` differs, adjust. If a simpler sink is available, use it — the assertion that matters is "not in `chest.loot`, yes on the ground + in `armour_ground`".)

- [ ] **Step 2: Run to verify it fails**

Run: `py -3.13 -m deathward.tests TestArmourEconomyWiring -v`
Expected: FAIL (magical armour not yet collected on equip; `_put_back` currently sends it to the container or the ground without recording `armour_ground`).

- [ ] **Step 3: Import `is_magical_armour` in world.py**

`deathward/world.py:37-38`, add `is_magical_armour` to the items import:
```python
from .items import (ALL_GEAR, CONSUMABLES, is_magical, is_magical_armour, is_magical_boot,
                     roll_loot, roll_monster_loot)
```

- [ ] **Step 4: Collect on the `_take` equip path**

In `deathward/world.py`, right after the `is_magical_boot(payload)` block (~1327-1331), add:
```python
            if is_magical_armour(payload):
                if self.codex.magical_armour_picked_up(payload):
                    self.codex.award_armour_collection()
                    self.log("EVERY WARD THE DEEP STILL KEEPS is yours. A gold star of "
                             "its own, for the back that bore every ward.", config.GOLD)
```
(Placeholder log line — user may reword.)

- [ ] **Step 5: Collect on the CTRL+34 bench**

In `cheat_equip_armour` (`world.py:1442-1446`), right after `self.codex.see_gear(key)`:
```python
        if is_magical_armour(key):
            if self.codex.magical_armour_picked_up(key):
                self.codex.award_armour_collection()
                self.log("EVERY WARD THE DEEP STILL KEEPS is yours. A gold star of its own.",
                         config.GOLD)
```

- [ ] **Step 6: Route a displaced magical armour to bare ground**

In `_put_back` (`world.py:1599-1614`), extend the magical detection and both branches:
```python
        magical = is_magical(gear.key)
        magical_boot = is_magical_boot(gear.key)
        magical_armour = is_magical_armour(gear.key)
        if sink is not None and hasattr(sink, "loot") and not (magical or magical_boot
                                                               or magical_armour):
            sink.loot.append(("gear", gear.key, getattr(gear, "bonus", 0)))
            where = ("chest" if isinstance(sink, Chest)
                     else "body" if isinstance(sink, Slain)
                     else "your own body")
            self.log("You leave the %s in the %s." % (gear.name, where), config.DIM)
        else:
            bonus = getattr(gear, "bonus", 0)
            self.level.drops.append(Drop(p.x, p.y, "gear", gear.key, bonus=bonus))
            self.log("You drop the %s at your feet." % gear.name, config.DIM)
            if magical:
                self.codex.drop_magical_to_ground(gear.key, self.depth, p.x, p.y, bonus)
            elif magical_boot:
                self.codex.drop_magical_boot_to_ground(gear.key, self.depth, p.x, p.y)
            elif magical_armour:
                self.codex.drop_magical_armour_to_ground(gear.key, self.depth,
                                                         p.x, p.y, bonus)
```

- [ ] **Step 7: Run the test to verify it passes**

Run: `py -3.13 -m deathward.tests TestArmourEconomyWiring -v`
Expected: PASS (all 3).

- [ ] **Step 8: Full suite + determinism**

Run: `py -3.13 -m deathward.tests`
Expected: OK.
Run: `py -3.13 -m deathward.tests TestKnowledgeIsNotPower -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add deathward/world.py deathward/tests.py
git commit -m "Plan C Task 4: wire magical-armour pickup/award/displacement (equip, bench, _put_back)"
```

---

## Self-Review notes (author)

- **Spec coverage:** distribution retune (Task 1), persistence (Task 2), collection (Task 3), wiring (Task 4) — all four spec sections mapped. Serialization + tolerant load folded into Tasks 2/3. Out-of-scope items (vendor, per-piece balance, boss-drop wiring) intentionally absent.
- **Type consistency:** ground entries are `{"depth","x","y","bonus"}` everywhere (record grounds bonus 0; drop grounds actual bonus); `_replay_magicals` reads `bonus` with default 0 — consistent. `magical_armour_picked_up` returns `bool`, gated by `FINDABLE_MAGICAL_ARMOUR_KEYS <= set(...)`, mirroring boots exactly.
- **Placeholder wording** (Kodex fact + two log lines) is called out for the user in every place it appears.
- **Determinism** re-checked as an explicit step in Tasks 1, 2, and 4; Task 1 flags the legitimate rng-shift risk for seed-pinned deep-floor tests.
