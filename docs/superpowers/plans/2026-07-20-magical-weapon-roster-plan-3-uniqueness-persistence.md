# Magical Weapon Roster — Plan 3: Uniqueness & Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make magical weapons **absolutely unique across a whole game** and **persist where they lie** (ground or corpse) across every life — a draw *without replacement* where dying is a tactic. Add the **collector's achievement** (all findable magicals) and the **Planescape respawn homage**.

**Architecture:** A **magical-weapon ledger** on the codex, made of three persistent sets: `magical_generated` (every magical ever placed into the world this game — the exclude set that makes generation unique), `magical_ground` (magicals currently lying on the floor, keyed by weapon → `{depth,x,y,bonus}` — re-placed each life so they persist), and `magical_collected` (magicals the player has ever picked up — drives the achievement). Generation *reads* the ledger (run-history, not Kodex — so bit-identicality holds) to exclude already-generated magicals and to replay the ground-lying ones. Pickup/drop keep the ledger in step. This is a deliberate, documented exception to the "everything on a floor is re-dealt each life" rule (only corpses persisted before; now magicals do too).

**Tech Stack:** Python 3.11+ standard library; Pygame; `unittest`. Run with `py -3.13` (NOT `python`/`py`).

## Global Constraints

- **Standard library + Pygame only** — no new dependencies.
- **Knowledge is information, never power:** generation may read the *ledger* (run-history, identical for a blind and an omniscient hero) but **must never read the Kodex `known` set**. `roll_magical`/`roll_floor_weapons`/`_populate`/the ground-replay must not branch on what facts are known. The load-bearing proof is `TestKnowledgeIsNotPower` (tests.py:323) — it runs the same seed and keystrokes for a blind and an all-knowing codex and asserts bit-identical traces. **Every task must keep it green.**
- **Determinism:** all generation randomness draws from the per-run world RNG (`rng`); the ledger's exclude set is the same for both runs, so any RNG-consumption difference it causes is identical across them.
- **GPLv3 header:** every source file carries it; do not remove it. No new files.
- **Test commands:** full suite `py -3.13 -m deathward.tests` (baseline 462 green); one test `py -3.13 -m unittest deathward.tests.<Class>.<method> -v`.
- **Scope fence:** Plans 1 (roster+combat) and 2 (deep economy) are merged. This plan is uniqueness + persistence + the achievement + the homage. The two mini-boss weapons (`windfang`, `void_scimitar`) are not findable and are out of scope (a future mini-boss task drops them); "all magical weapons" for the achievement means the **11 findable** ones.

---

### Task 1: The ledger state on the codex

Add the three persistent sets, an `is_magical` helper, save/load round-tripping, reset on new-dungeon, and the codex methods that mutate the ledger.

**Files:**
- Modify: `deathward/items.py` (add `is_magical`, `FINDABLE_MAGICAL_KEYS`)
- Modify: `deathward/codex.py` (`__init__` fields ~617-670; `save` ~703-719; `load` ~673-701; `new_dungeon` ~788-805; add ledger methods)
- Test: `deathward/tests.py` (new `TestMagicalLedgerState`)

**Interfaces:**
- Produces: `items.is_magical(key) -> bool` (`key in WEAPONS and WEAPONS[key].tier >= 4`); `items.FINDABLE_MAGICAL_KEYS: set[str]` (the 11 findable keys). On `Codex`: `self.magical_generated: list[str]`, `self.magical_ground: dict[str, dict]`, `self.magical_collected: list[str]`; `codex.record_magical_placed(key, depth, x, y, bonus)`; `codex.magical_picked_up(key) -> bool` (records collection, drops from ground, returns True if this completed the findable set for the first time); `codex.drop_magical_to_ground(key, depth, x, y, bonus)`.

- [ ] **Step 1: Write the failing test**

```python
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
```

*(The test uses two small seams — `_save_dict()` and `_load_from(dict)` — refactored out of `save`/`load` in Step 3 so serialization is testable without touching disk.)*

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m unittest deathward.tests.TestMagicalLedgerState -v`
Expected: FAIL — `is_magical`/`FINDABLE_MAGICAL_KEYS`/ledger fields/methods absent.

- [ ] **Step 3: Implement the helpers, fields, methods, and serialization**

In `deathward/items.py`, after `FINDABLE_MAGICAL` (~line 389), add:

```python
FINDABLE_MAGICAL_KEYS = set(FINDABLE_MAGICAL[4]) | set(FINDABLE_MAGICAL[5])


def is_magical(key):
    """A magical weapon (tier 4 or 5). The single source of truth for the ledger."""
    return key in WEAPONS and WEAPONS[key].tier >= 4
```

In `deathward/codex.py` `__init__`, alongside `self.corpses = {}` (~line 635), add:

```python
        # the magical-weapon ledger (Plan 3). generated = every magical ever placed this
        # GAME (the uniqueness exclude set); ground = the ones currently lying on a floor,
        # key -> {"depth","x","y","bonus"} (re-placed each life so they persist); collected
        # = magicals the player has ever picked up (drives the collector's award).
        self.magical_generated = []
        self.magical_ground = {}
        self.magical_collected = []
```

Refactor `save`/`load` to route through testable seams. Replace the body of `save` (codex.py ~703-719) with:

```python
    def _save_dict(self):
        return {
            "known": self.known, "gear_seen": self.gear_seen,
            "appearance": self.appearance,
            "telemetry": self.telemetry, "deaths": self.deaths,
            "best_depth": self.best_depth, "runs": self.runs, "wins": self.wins,
            "corpses": self.corpses, "gifts": self.gifts, "maps": self.maps,
            "gift_item": self.gift_item,
            "layout_version": config.LAYOUT_VERSION,
            "found_traps": self.found_traps,
            "world_seed": self.world_seed, "stats": self.stats,
            "magical_generated": self.magical_generated,
            "magical_ground": self.magical_ground,
            "magical_collected": self.magical_collected,
        }

    def save(self):
        try:
            with open(config.SAVE_PATH, "w", encoding="utf-8") as fh:
                json.dump(self._save_dict(), fh, indent=1)
        except OSError:
            pass
```

In `load`, replace the block that assigns from `data` with a call to a new `_load_from`, and add the ledger reads. Add this method and route `load` through it:

```python
    def _load_from(self, data):
        self.known = [k for k in data.get("known", []) if k in FACTS]
        self.gear_seen = data.get("gear_seen", [])
        self.appearance = data.get("appearance", {})
        self.telemetry = data.get("telemetry", [])
        self.deaths = data.get("deaths", 0)
        self.best_depth = data.get("best_depth", 0)
        self.runs = data.get("runs", 0)
        self.wins = data.get("wins", 0)
        self.corpses = data.get("corpses", {})
        self.gifts = data.get("gifts", [])
        self.gift_item = data.get("gift_item")
        self.maps = data.get("maps", {})
        self.found_traps = data.get("found_traps", {})
        self.world_seed = data.get("world_seed")
        self.stats.update(data.get("stats", {}))
        self.magical_generated = data.get("magical_generated", [])
        self.magical_ground = data.get("magical_ground", {})
        self.magical_collected = data.get("magical_collected", [])
        if data.get("layout_version", 1) != config.LAYOUT_VERSION:
            self.new_dungeon()
            self.layout_migrated = True
```

And in `load`, after reading the file into `data`, replace the inline assignments with `self._load_from(data)`.

In `new_dungeon` (codex.py ~788-805), add the reset alongside `self.corpses = {}`:

```python
        self.magical_generated = []
        self.magical_ground = {}
        self.magical_collected = []
```

Add the three ledger methods near `write_corpse` (codex.py ~882):

```python
    def record_magical_placed(self, key, depth, x, y, bonus):
        """A magical weapon has entered the world (rolled at generation). It never rolls
        again (uniqueness) and lies where it was placed until picked up."""
        if key not in self.magical_generated:
            self.magical_generated.append(key)
        self.magical_ground[key] = {"depth": depth, "x": x, "y": y, "bonus": bonus}

    def drop_magical_to_ground(self, key, depth, x, y, bonus):
        """The hero left a magical on the bare floor; it stays there across lives."""
        if key not in self.magical_generated:
            self.magical_generated.append(key)
        self.magical_ground[key] = {"depth": depth, "x": x, "y": y, "bonus": bonus}

    def magical_picked_up(self, key):
        """The hero has a magical in hand: mark it collected, take it off the ground.
        Returns True the first time the findable set is completed (for the award)."""
        from .items import FINDABLE_MAGICAL_KEYS
        self.magical_ground.pop(key, None)
        if key not in self.magical_generated:
            self.magical_generated.append(key)
        was_complete = FINDABLE_MAGICAL_KEYS <= set(self.magical_collected)
        if key not in self.magical_collected:
            self.magical_collected.append(key)
        now_complete = FINDABLE_MAGICAL_KEYS <= set(self.magical_collected)
        return now_complete and not was_complete
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.13 -m unittest deathward.tests.TestMagicalLedgerState -v` then `py -3.13 -m deathward.tests`
Expected: PASS. (`wipe()` re-runs `__init__`, so a new game clears the ledger for free.)

- [ ] **Step 5: Commit**

```bash
git add deathward/items.py deathward/codex.py deathward/tests.py
git commit -m "Add the magical-weapon ledger state + is_magical (codex persistence)"
```

---

### Task 2: Uniqueness — generation excludes already-generated magicals

Thread an `exclude` set through `roll_floor_weapons`/`roll_magical`, pass `codex.magical_generated` at generation, and record each freshly-placed magical into the ledger.

**Files:**
- Modify: `deathward/items.py` (`roll_magical`, `roll_floor_weapons` gain `exclude`)
- Modify: `deathward/dungeon.py` (`_populate` passes the exclude set and records placements)
- Test: `deathward/tests.py` (new `TestMagicalUniqueness`)

**Interfaces:**
- Consumes: `codex.record_magical_placed` (Task 1), `is_magical`.
- Produces: `roll_magical(rng, depth, exclude=())`; `roll_floor_weapons(rng, depth, exclude=())`. When the crossover-chosen tier's pool is fully excluded, `roll_magical` returns `None` (so once all magicals exist, the slot goes dormant).

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m unittest deathward.tests.TestMagicalUniqueness -v`
Expected: FAIL — `roll_magical`/`roll_floor_weapons` take no `exclude`; generation records nothing, so a magical can repeat across floors.

- [ ] **Step 3: Add `exclude` to the rollers**

In `deathward/items.py`, replace `roll_magical` with:

```python
def roll_magical(rng, depth, exclude=()):
    """The rare magical slot for floors 8-20. `exclude` is the set of magical keys already
    generated this game (absolute uniqueness): the chosen tier is filtered to its still-in-
    pool weapons, and if that tier is exhausted no magical drops. Draws only from
    (rng, depth) and `exclude` -- run-history, never the Kodex -- so blind and omniscient
    runs stay bit-identical."""
    present = 0.18 if depth <= 11 else 0.15 if depth <= 15 else 0.12
    if rng.random() >= present:
        return None
    t5_share = 0.20 if depth <= 11 else 0.40 if depth <= 15 else 0.65
    tier = 5 if rng.random() < t5_share else 4
    pool = [k for k in FINDABLE_MAGICAL[tier] if k not in exclude]
    if not pool:
        return None
    return (rng.choice(pool), 0)
```

And `roll_floor_weapons`:

```python
def roll_floor_weapons(rng, depth, exclude=()):
    """Every weapon a floor places at generation, as a list of (key, bonus). `exclude` is
    the already-generated magical set, threaded to the magical slot for uniqueness."""
    if depth <= 7:
        w = roll_ordinary(rng, depth)
        return [w] if w else []
    out = []
    steel = roll_deep_steel(rng, depth)
    if steel:
        out.append(steel)
    magical = roll_magical(rng, depth, exclude=exclude)
    if magical:
        out.append(magical)
    return out
```

- [ ] **Step 4: Pass the exclude set and record placements in `_populate`**

In `deathward/dungeon.py`, update the import (line 29) to include `is_magical`:

```python
from .items import gear_pool, is_magical, roll_chest, roll_floor_weapons, roll_loot
```

Replace the weapon-placement loop in `_populate` with:

```python
        for wkey, wbonus in roll_floor_weapons(rng, d, exclude=codex.magical_generated):
            spot = self._far_room_spot() if d == 1 else None
            if spot is None:
                spot = self._free_tile(avoid_start=True)
            if spot:
                self.drops.append(Drop(spot[0], spot[1], "gear", wkey, bonus=wbonus))
                if is_magical(wkey):
                    # it now EXISTS: never rolls again, and lies here until picked up.
                    codex.record_magical_placed(wkey, d, spot[0], spot[1], wbonus)
```

- [ ] **Step 5: Run tests + full suite (bit-identical is the key gate)**

Run: `py -3.13 -m unittest deathward.tests.TestMagicalUniqueness deathward.tests.TestKnowledgeIsNotPower -v` then `py -3.13 -m deathward.tests`
Expected: PASS. **`TestKnowledgeIsNotPower` must stay green** — the exclude set is `magical_generated`, which is identical for a blind and an omniscient codex (both start empty and evolve identically under the same keystrokes), so no divergence. If it fails, something read `known` — it must not.

- [ ] **Step 6: Commit**

```bash
git add deathward/items.py deathward/dungeon.py deathward/tests.py
git commit -m "Magical weapons are unique per game: generation excludes the already-placed"
```

---

### Task 3: Persistence — replay ground-lying magicals each life

Magicals lie where they were left, across lives. In `_generate`, snapshot the ground ledger before `_populate` (so this life's fresh rolls aren't double-placed), then re-place the persisted ones for this depth, clearing their tiles like a corpse. Update the "re-dealt each life" invariant tests to carve out magicals.

**Files:**
- Modify: `deathward/dungeon.py` (`_generate` — snapshot + replay; add `_replay_magicals`)
- Test: `deathward/tests.py` — new `TestMagicalPersistence`; update `test_the_living_are_re_dealt_every_respawn` / `test_a_new_run_wipes_the_floors_clean`

**Interfaces:**
- Consumes: `codex.magical_ground` (Task 1).
- Produces: `Level._replay_magicals(persisted: dict)` places each persisted magical whose `depth == self.depth` at its saved `(x,y,bonus)`, clearing conflicting living from the tile.

- [ ] **Step 1: Write the failing test**

```python
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
```

*(If the first test can't reliably find a natural magical to seed, it records one directly via `record_magical_placed` as shown — that's the ledger contract this task must honor.)*

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m unittest deathward.tests.TestMagicalPersistence -v`
Expected: FAIL — nothing replays the ground ledger, so the Kris is gone next life.

- [ ] **Step 3: Snapshot + replay in `_generate`**

In `deathward/dungeon.py` `_generate`, capture the ground ledger BEFORE `_populate` and replay it AFTER (place near the existing corpse-restore block). Find the `self._populate(codex)` call and wrap it:

```python
        # snapshot the persisted ground magicals BEFORE this floor's fresh rolls, so a
        # weapon rolled THIS life (which _populate records into codex.magical_ground) is
        # not also replayed as if it were an heirloom.
        persisted_magicals = dict(codex.magical_ground)
        if self.depth >= config.DEPTH_MAX:
            self._populate_boss()
        else:
            self._populate(codex)
        self._replay_magicals(persisted_magicals)
```

Add the `_replay_magicals` method to `Level` (near the corpse-restore logic):

```python
    def _replay_magicals(self, persisted):
        """Magical weapons persist where they lie, across every life -- the trophies of
        your past selves, salted through the dungeon. Re-place this floor's, clearing
        whatever the fresh deal put on their tiles, exactly like a corpse."""
        for key, loc in persisted.items():
            if loc["depth"] != self.depth:
                continue
            mx, my = loc["x"], loc["y"]
            if not self.walkable(mx, my):
                continue
            self.monsters = [m for m in self.monsters if (m.x, m.y) != (mx, my)]
            self.drops = [d for d in self.drops if (d.x, d.y) != (mx, my)]
            self.chests = [ch for ch in self.chests if (ch.x, ch.y) != (mx, my)]
            self.drops.append(Drop(mx, my, "gear", key, bonus=loc["bonus"]))
```

- [ ] **Step 4: Carve magicals out of the "re-dealt every life" invariant**

The existing tests assert the living (drops etc.) are wiped each life. Magicals are now the exception. Find `test_the_living_are_re_dealt_every_respawn` (tests.py ~1028) and `test_a_new_run_wipes_the_floors_clean` (tests.py ~2991). Update each so its "drops are gone / re-dealt" assertion **excludes magical drops** — e.g. change a check like `self.assertFalse(w2.level.drops ...)` to ignore gear drops that are magical:

```python
        from .items import is_magical
        living_drops = [d for d in w2.level.drops
                        if not (d.kind == "gear" and is_magical(d.payload))]
        # ... assert living_drops are re-dealt / differ, as the test did before ...
```

Read each test and make the minimal change that preserves its intent (the *living* is still re-dealt) while allowing persisted magicals. Note the change in the commit.

- [ ] **Step 5: Run tests + full suite**

Run: `py -3.13 -m unittest deathward.tests.TestMagicalPersistence deathward.tests.TestKnowledgeIsNotPower -v` then `py -3.13 -m deathward.tests`
Expected: PASS. Bit-identical holds (the replay reads `magical_ground`, identical for both codices).

- [ ] **Step 6: Commit**

```bash
git add deathward/dungeon.py deathward/tests.py
git commit -m "Magical weapons persist where they lie: replay the ground ledger each life"
```

---

### Task 4: Pickup and drop keep the ledger honest

Picking up a magical marks it collected and takes it off the ground; dropping one to the bare floor records it. A magical displaced into a container loot-list is redirected to the ground so it can't be lost to the ephemeral living.

**Files:**
- Modify: `deathward/world.py` (`_take` ~1035, `_put_back` ~1266, `drop_gear_near` ~1135)
- Test: `deathward/tests.py` (new `TestLedgerPickupDrop`)

**Interfaces:**
- Consumes: `codex.magical_picked_up`, `codex.drop_magical_to_ground`, `is_magical` (Task 1); returns True from `magical_picked_up` on completion (used by Task 5).
- Produces: pickup of a magical calls `magical_picked_up`; a magical dropped to the ground calls `drop_magical_to_ground`; a magical never lands in a container loot-list.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m unittest deathward.tests.TestLedgerPickupDrop -v`
Expected: FAIL — pickup/drop don't touch the ledger.

- [ ] **Step 3: Hook `_take`, `_put_back`, `drop_gear_near`**

In `deathward/world.py` `_take`, in the `kind == "gear"` branch, right after `self.codex.see_gear(payload)`, add:

```python
            if is_magical(payload):
                self.codex.magical_picked_up(payload)   # collected + off the ground
```

*(Task 5 extends this same hook to fire the collector's award using `magical_picked_up`'s return value; for now it just records the collection.)*

In `_put_back`, redirect a magical away from a container loot-list and record every ground drop of a magical. Replace the method body with:

```python
    def _put_back(self, gear, sink):
        p = self.player
        magical = is_magical(gear.key)
        # a magical must never go into a container's ephemeral loot list -- it would be
        # re-dealt away. it always goes to the persistent bare ground instead.
        if sink is not None and hasattr(sink, "loot") and not magical:
            sink.loot.append(("gear", gear.key))
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
```

In `drop_gear_near` (the cheat), record a magical dropped near the player. After the `self.level.drops.append(Drop(spot[0], spot[1], "gear", gear_key))` line, add:

```python
        if is_magical(gear_key):
            self.codex.record_magical_placed(gear_key, self.depth, spot[0], spot[1], 0)
```

Ensure `is_magical` is imported in `world.py` (add to the `from .items import ...` line at the top).

- [ ] **Step 4: Run tests + full suite**

Run: `py -3.13 -m unittest deathward.tests.TestLedgerPickupDrop -v` then `py -3.13 -m deathward.tests`
Expected: PASS. (A magical you die holding still goes onto your **corpse** via the existing `leave_corpse` — the corpse system persists it, and it stays in `magical_generated`, so it never regenerates. No ledger change needed there.)

- [ ] **Step 5: Commit**

```bash
git add deathward/world.py deathward/tests.py
git commit -m "Pickup/drop keep the magical ledger honest (collected, ground, no loot-list)"
```

---

### Task 5: The collector's achievement

When the player first collects every findable magical, grant a permanent Kodex lore fact ("two gold stars") and a stat. The completion signal comes from `magical_picked_up` (Task 1) surfaced through `_take` (Task 4).

**Files:**
- Modify: `deathward/codex.py` (a `Fact` in `FACT_LIST`; a `award_collection()` method; a stat)
- Modify: `deathward/world.py` (fire the award when `completed_collection` is set)
- Test: `deathward/tests.py` (new `TestCollectorAward`)

**Interfaces:**
- Consumes: the completion return of `magical_picked_up` via `world.completed_collection`.
- Produces: fact key `"self.magical_collector"` granted once; `codex.stats["magical_collected_all"] = 1`.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m unittest deathward.tests.TestCollectorAward -v`
Expected: FAIL — no fact, no `award_collection`.

- [ ] **Step 3: Add the fact, the award, and the stat**

In `deathward/codex.py`, add to `FACT_LIST` (near the other `"self"`/lore facts) a `_f(...)`:

```python
    _f("self.magical_collector", "self", "secret",
       "EVERY BLADE THE DEEP STILL HOLDS",
       "You have drawn every magical weapon this dungeon will yield -- the whole rare "
       "roster, gathered by one hand across many deaths. Two gold stars. There is nothing "
       "left down there to find that you have not already held."),
```

Add `"magical_collected_all": 0` to the `self.stats` dict (codex.py ~656-670). Add the award method near `_grant`:

```python
    def award_collection(self):
        """Grant the collector's Kodex fact once. The fact is permanent (survives a new
        dungeon); the collected-set that earns it is per-game."""
        self.stats["magical_collected_all"] = 1
        if "self.magical_collector" not in self.known:
            self._grant("self.magical_collector")
            self.save()
```

In `deathward/world.py`, extend Task 4's `_take` pickup hook to use `magical_picked_up`'s completion return and fire the award. Replace the Task-4 hook lines with:

```python
            if is_magical(payload):
                if self.codex.magical_picked_up(payload):
                    self.codex.award_collection()
                    self.log("EVERY BLADE THE DEEP STILL HOLDS is yours. Two gold stars.",
                             config.GOLD)
```

*(`magical_picked_up` still records the collection and takes the weapon off the ground as in Task 4; the only change is acting on its `True` return — the moment the findable set is first completed.)*

- [ ] **Step 4: Run tests + full suite**

Run: `py -3.13 -m unittest deathward.tests.TestCollectorAward -v` then `py -3.13 -m deathward.tests`
Expected: PASS. If a Kodex-completeness test (`test_the_whole_codex_is_reachable_by_dying`, tests.py ~130) trips on the new fact, confirm it's reachable via the award path (it is granted by collecting) and adjust that test's expectation if it enumerates a fixed grantable set — note it in the commit.

- [ ] **Step 5: Commit**

```bash
git add deathward/codex.py deathward/world.py deathward/tests.py
git commit -m "Collector's award: a permanent Kodex fact for gathering every findable magical"
```

---

### Task 6: The Planescape respawn homage

On every respawn after a death, greet the hero — *"You wake, again, and the deep is patient."* — and record a lore fact the first time.

**Files:**
- Modify: `deathward/game.py` (`new_run` ~105-138)
- Modify: `deathward/codex.py` (a lore `Fact`)
- Test: `deathward/tests.py` (new `TestRespawnHomage`)

**Interfaces:**
- Produces: fact key `"self.the_deep_is_patient"`; the homage line logged on each death-respawn (not on a fresh new game or a victory-keep).

- [ ] **Step 1: Write the failing test**

```python
class TestRespawnHomage(unittest.TestCase):
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
```

*(Confirm the shape of `codex.messages` / the log API from `World.log` and adapt the message-scan accordingly; the assertion is "the homage text was logged".)*

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m unittest deathward.tests.TestRespawnHomage -v`
Expected: FAIL — no fact, no homage.

- [ ] **Step 3: Add the fact and speak it on respawn**

In `deathward/codex.py`, add to `FACT_LIST`:

```python
    _f("self.the_deep_is_patient", "self", "secret",
       "YOU WAKE, AGAIN",
       "Death is not the end of the descent -- it is how you go on. You wake on the same "
       "cold stone you woke on last time, and the time before, and the deep waits with "
       "the patience of something that has never once been in a hurry."),
```

In `deathward/game.py` `new_run`, after `self.world = World(self.codex)` and before the state is set, add the respawn homage (gated so it fires only on a death-respawn — not a victory-keep, not a brand-new game):

```python
        if keep is None and not fresh_dungeon and self.codex.deaths > 0:
            self.world.log("You wake, again, and the deep is patient.", config.MANA)
            if "self.the_deep_is_patient" not in self.codex.known:
                self.codex._grant("self.the_deep_is_patient")
```

- [ ] **Step 4: Run tests + full suite**

Run: `py -3.13 -m unittest deathward.tests.TestRespawnHomage -v` then `py -3.13 -m deathward.tests`
Expected: PASS. Same Kodex-completeness note as Task 5 if it trips — the fact is granted on any death-respawn, so it is reachable.

- [ ] **Step 5: Commit**

```bash
git add deathward/game.py deathward/codex.py deathward/tests.py
git commit -m "Planescape homage: 'You wake, again, and the deep is patient' on respawn"
```

---

### Task 7: Integration — bit-identical, persistence & uniqueness across lives, playtest

**Files:**
- Verify only (fix fallout where found); add cross-life integration tests.

- [ ] **Step 1: Run the whole suite**

Run: `py -3.13 -m deathward.tests`
Expected: all green. Fix any failure — do not silence it.

- [ ] **Step 2: The bit-identical invariant (the load-bearing gate)**

Run: `py -3.13 -m unittest deathward.tests.TestKnowledgeIsNotPower -v`
Expected: PASS — the ledger is read by generation but is identical for a blind and an omniscient codex, so their traces still match. If it fails, a generation/replay path is reading `known` or otherwise diverging on knowledge.

- [ ] **Step 3: Cross-life integration test**

Append to `deathward/tests.py`:

```python
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
```

Run: `py -3.13 -m unittest deathward.tests.TestUniquenessAcrossLives -v`
Expected: PASS.

- [ ] **Step 4: Manual playtest checklist (record in the PR description)**

Run: `py run_deathward.py` and verify:
- Find a magical, leave it on the floor, die, come back down — it's still lying exactly where you left it.
- Pick one up, die holding it — it's on your corpse; reclaim it. The dungeon never spawns a second of that weapon.
- Over several dive-and-die cycles, the magical pool visibly narrows (you fish toward the ones you lack).
- Collect all findable magicals → the "EVERY BLADE THE DEEP STILL HOLDS" Kodex line appears (once).
- Every respawn after a death shows "You wake, again, and the deep is patient."

- [ ] **Step 5: Final commit (if any fixes were needed)**

```bash
git add -A
git commit -m "Integration fixes for magical uniqueness & persistence"
```

## Self-Review Notes (author)

- **Spec coverage (Plan-3 slice):** absolute per-game uniqueness (Task 2) ✓; world-persistence of ground magicals via the ledger (Tasks 1,3) ✓; pickup/drop ledger upkeep + no-loss-to-loot-list (Task 4) ✓; corpse-carried magicals persist via the existing corpse system + stay in `magical_generated` (Task 4 note) ✓; collector's two-star award (Task 5) ✓; Planescape homage (Task 6) ✓; ledger resets per game (new_dungeon/wipe) but survives death (Task 1) ✓; the bit-identical invariant preserved throughout (Tasks 2,3,7) ✓.
- **The determinism argument:** generation reads the ledger (`magical_generated`, `magical_ground`), which is run-history — identical for a blind and an omniscient codex — never the Kodex `known` set. This is the same category of state as `corpses`, which generation already reads. `TestKnowledgeIsNotPower` is the gate on every task that touches generation.
- **Deliberate invariant change:** magical weapons are now the one thing besides corpses that persists across lives; the "living is re-dealt" tests are updated to carve them out (Task 3).
- **Out of scope:** the two mini-boss weapons (not findable); their drop wiring + adding them to `magical_generated` on a boss kill belongs to the mini-boss task, along with the second gold star for the full 13.
