# Magical Boots — Phase 3 Plan B (Persistence + Collection Award) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make magical boots survive death (a boot lies where it fell, replayed every life until picked up) and grant a permanent gold star for gathering all 12 — completing the boots economy, mirroring the magical weapons.

**Architecture:** A parallel boots ledger (`boots_ground` for persistence, `boots_collected` for the set), the codex methods that maintain it (`record_magical_boot_placed` now records the floor position; `drop_magical_boot_to_ground`; `magical_boot_picked_up`; `award_boots_collection`), the dungeon replaying `boots_ground` each life (reusing the weapon replay), and world.py firing the pickup/drop/award hooks — each a 1:1 mirror of the weapon path.

**Tech Stack:** Python 3 standard library, `pygame`, `unittest` (`deathward/tests.py`).

## Global Constraints

- **No new dependencies.** Standard library + existing `pygame`.
- **Determinism:** unchanged — persistence reads only run-history (`boots_ground`), never the Kodex. `TestKnowledgeIsNotPower` (tests.py:323) must stay green.
- **Do not touch the GPL header** in any file.
- **Scope fence:** only magical-boots persistence + collection. Do NOT touch weapons, armour, ordinary boots, boot stats/mechanics, or the rarity/uniqueness from Plan A.
- **The award:** gathering all 12 findable magical boots (`FINDABLE_MAGICAL_BOOT_KEYS`, from Plan A) fires `award_boots_collection` — sets `stats["magical_boots_collected_all"] = 1` (its own gold star) and grants the permanent Kodex fact `self.magical_boot_collector`. The weapon equivalents are `award_collection` / `self.magical_collector` / `stats["magical_collected_all"]`.
- **Running tests — use `py -3.13`, NOT `python`** (3.14 lacks pygame). Whole suite: `py -3.13 -m deathward.tests` (baseline: 513 green). One test: `py -3.13 -m deathward.tests <ClassName>.<test_method> -v`.

## Shared references (the weapon template)

- Codex methods to mirror: `record_magical_placed` (codex.py:919, writes `magical_ground`), `drop_magical_to_ground` (932), `magical_picked_up` (938, returns completion), `award_collection` (1055). The collector fact `_f("self.magical_collector", ...)` at codex.py:86.
- Ledger wiring spots: init (codex.py:653-654, `boots_generated` already there), `load` (codex.py:722), `_save_dict` (codex.py:741), `new_dungeon` reset (codex.py:836), stats default (codex.py:689).
- Dungeon replay: `_replay_magicals` (dungeon.py:407-420) + its snapshot/call (dungeon.py:381, 386).
- World hooks: `_take`'s magical block (world.py:1143-1147), `cheat_equip_boots` (world.py:1229), `_put_back` (world.py:1388-1400).
- New tests go in the existing `TestMagicalBootsEconomy` class (end of tests.py). `FakeSave()` is a `Codex` subclass; `_save_dict()`, `new_dungeon()`, `record_magical_boot_placed`, `boots_generated` all exist from Plan A.

---

### Task 1: The codex persistence + collection layer

**Files:**
- Modify: `deathward/codex.py` — `boots_ground`/`boots_collected` ledgers (init/load/save/reset), `stats["magical_boots_collected_all"]`, extend `record_magical_boot_placed`, add `drop_magical_boot_to_ground` / `magical_boot_picked_up` / `award_boots_collection`, and the `self.magical_boot_collector` Kodex fact.
- Test: `deathward/tests.py` (`TestMagicalBootsEconomy`)

**Interfaces:**
- Produces: `codex.boots_ground` (dict `key -> {depth, x, y}`), `codex.boots_collected` (list); `record_magical_boot_placed(key, depth, x, y)` now also records the floor position; `drop_magical_boot_to_ground(key, depth, x, y)`; `magical_boot_picked_up(key)` (pops ground, marks collected, returns True the first time all 12 are collected); `award_boots_collection()`. Tasks 2–3 consume these.

- [ ] **Step 1: Write the failing tests**

Add to `TestMagicalBootsEconomy` in `deathward/tests.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -3.13 -m deathward.tests TestMagicalBootsEconomy.test_record_grounds_the_boot_and_pickup_takes_it_off -v`
Expected: FAIL — `AttributeError: 'FakeSave' object has no attribute 'boots_ground'`.

- [ ] **Step 3: Add the two ledgers (init, load, save, reset) + the stat default**

In `deathward/codex.py`:

- After `self.boots_generated = []` (init, codex.py:654), add:
```python
        self.boots_ground = {}         # magical boots lying on a floor (re-placed each life)
        self.boots_collected = []      # magical boots ever picked up (drives the boots award)
```
- In `load`, after `self.boots_generated = data.get("boots_generated", [])`, add:
```python
        self.boots_ground = data.get("boots_ground", {})
        self.boots_collected = data.get("boots_collected", [])
```
- In `_save_dict`'s returned dict, after `"boots_generated": self.boots_generated,`, add:
```python
            "boots_ground": self.boots_ground,
            "boots_collected": self.boots_collected,
```
- In `new_dungeon`, after `self.boots_generated = []`, add:
```python
        self.boots_ground = {}
        self.boots_collected = []
```
- In the `stats` default dict (codex.py:689, beside `"magical_collected_all": 0,`), add:
```python
            "magical_boots_collected_all": 0,
```

- [ ] **Step 4: Extend `record_magical_boot_placed`; add the three new methods**

In `deathward/codex.py`, replace `record_magical_boot_placed` (from Plan A) so it also records the floor position, and add the three methods after it:

```python
    def record_magical_boot_placed(self, key, depth, x, y):
        """A magical boot has entered the world (rolled at generation). It never rolls again
        (uniqueness) and lies where it was placed until picked up (persistence)."""
        if key not in self.boots_generated:
            self.boots_generated.append(key)
        self.boots_ground[key] = {"depth": depth, "x": x, "y": y}

    def drop_magical_boot_to_ground(self, key, depth, x, y):
        """The hero left a magical boot on the bare floor; it stays there across lives."""
        if key not in self.boots_generated:
            self.boots_generated.append(key)
        self.boots_ground[key] = {"depth": depth, "x": x, "y": y}

    def magical_boot_picked_up(self, key):
        """The hero has a magical boot on their feet: mark it collected, take it off the
        ground. Returns True the first time the 12 findable boots are all collected."""
        from .items import FINDABLE_MAGICAL_BOOT_KEYS
        self.boots_ground.pop(key, None)
        if key not in self.boots_generated:
            self.boots_generated.append(key)
        was_complete = FINDABLE_MAGICAL_BOOT_KEYS <= set(self.boots_collected)
        if key not in self.boots_collected:
            self.boots_collected.append(key)
        now_complete = FINDABLE_MAGICAL_BOOT_KEYS <= set(self.boots_collected)
        return now_complete and not was_complete

    def award_boots_collection(self):
        """Grant the boots collector's Kodex fact once. Permanent (survives a new dungeon);
        the collected-set that earns it is per-game."""
        self.stats["magical_boots_collected_all"] = 1
        if "self.magical_boot_collector" not in self.known:
            self._grant("self.magical_boot_collector")
```

- [ ] **Step 5: Add the collector's Kodex fact**

In `deathward/codex.py`, immediately after the `self.magical_collector` fact (the `_f(...)` block ending ~line 91), add (wording is a starting point — tunable):

```python
    _f("self.magical_boot_collector", "self", "secret",
       "EVERY STEP THE DEEP STILL HIDES",
       "You have laced on every magical boot this dungeon will yield -- the whole rare "
       "roster, gathered by one hand across many deaths. A gold star of its own, for the "
       "feet that have walked every hidden path the deep still keeps."),
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `py -3.13 -m deathward.tests TestMagicalBootsEconomy -v`
Expected: PASS. Then the full suite:
Run: `py -3.13 -m deathward.tests`
Expected: green. (Adding a Kodex fact raises `TOTAL_FACTS` by 1; the "learn every fact" test loops `TOTAL_FACTS` times so it self-adjusts. If any test hard-codes the fact count, update it to the new total.)

- [ ] **Step 7: Commit**

```bash
git add deathward/codex.py deathward/tests.py
git commit -m "Codex: magical-boots persistence (boots_ground) + collection award (gold star + fact)"
```

---

### Task 2: Replay persisted magical boots each life

**Files:**
- Modify: `deathward/dungeon.py:407-420` (`_replay_magicals`), `deathward/dungeon.py:381` + `386` (snapshot + call)
- Test: `deathward/tests.py` (`TestMagicalBootsEconomy`)

**Interfaces:**
- Consumes: `codex.boots_ground` (Task 1).
- Produces: a magical boot recorded in `boots_ground` is re-placed on its tile every life (until picked up), exactly like a magical weapon.

- [ ] **Step 1: Write the failing test**

Add to `TestMagicalBootsEconomy`:

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `py -3.13 -m deathward.tests TestMagicalBootsEconomy.test_a_magical_boot_survives_death_and_replays_where_it_fell -v`
Expected: FAIL — `thors` is empty (nothing replays `boots_ground`).

- [ ] **Step 3: Let `_replay_magicals` handle a boot's bonus-less ground record**

In `deathward/dungeon.py`, in `_replay_magicals` (line 420), change the `Drop` so a ground record without a `bonus` (boots) defaults to 0:

```python
            self.drops.append(Drop(mx, my, "gear", key, bonus=loc.get("bonus", 0)))
```

Also update the method's docstring first line to reflect it now replays weapons and boots:

```python
    def _replay_magicals(self, persisted):
        """Magical weapons AND boots persist where they lie, across every life -- the
        trophies of your past selves, salted through the dungeon. Re-place this floor's,
        clearing whatever the fresh deal put on their tiles, exactly like a corpse."""
```

- [ ] **Step 4: Snapshot and replay `boots_ground`**

In `deathward/dungeon.py`, beside the weapon snapshot (line 381) add the boots snapshot:

```python
        persisted_magicals = dict(codex.magical_ground)
        persisted_boots = dict(codex.boots_ground)
```

And after the weapon replay (line 386) add the boots replay:

```python
        self._replay_magicals(persisted_magicals)
        self._replay_magicals(persisted_boots)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `py -3.13 -m deathward.tests TestMagicalBootsEconomy.test_a_magical_boot_survives_death_and_replays_where_it_fell -v`
Expected: PASS. Then the full suite:
Run: `py -3.13 -m deathward.tests`
Expected: green — including `TestKnowledgeIsNotPower` (replay reads only `boots_ground`, no Kodex/RNG) and the weapon persistence tests (the `_replay_magicals` change is a no-op for weapons — their ground records still carry `bonus`).

- [ ] **Step 6: Commit**

```bash
git add deathward/dungeon.py deathward/tests.py
git commit -m "Replay persisted magical boots each life (reusing the weapon replay)"
```

---

### Task 3: Wire the pickup / drop / award hooks in world.py

**Files:**
- Modify: `deathward/world.py` — the `.items` import (add `is_magical_boot`); `_take` (~1143); `cheat_equip_boots` (~1238); `_put_back` (~1388-1400)
- Test: `deathward/tests.py` (`TestMagicalBootsEconomy`)

**Interfaces:**
- Consumes: `is_magical_boot` (Plan A) and the Task 1 codex methods.
- Produces: picking up / bench-equipping a magical boot marks it collected (and fires the award on the 12th); displacing a magical boot onto the floor persists it via `drop_magical_boot_to_ground` (and never into a container's loot list).

- [ ] **Step 1: Write the failing tests**

Add to `TestMagicalBootsEconomy`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -3.13 -m deathward.tests TestMagicalBootsEconomy.test_boots_bench_collects_and_awards_at_all_twelve -v`
Expected: FAIL — `boots_collected` stays empty / the star stat stays 0 (no hooks fire yet).

- [ ] **Step 3: Import `is_magical_boot` in world.py**

In `deathward/world.py`, add `is_magical_boot` to the `.items` import (the line that already imports `is_magical`).

- [ ] **Step 4: Fire the collection hook when a magical boot is picked up (`_take`)**

In `deathward/world.py` `_take`, right after the weapon magical block (after the `is_magical(payload)` block, before `name, desc = p.gear_display(g.slot)`, ~line 1148), add:

```python
            if is_magical_boot(payload):
                if self.codex.magical_boot_picked_up(payload):
                    self.codex.award_boots_collection()
                    self.log("EVERY STEP THE DEEP STILL HIDES is yours. A gold star of its "
                             "own, for the feet that walked every hidden path.", config.GOLD)
```

- [ ] **Step 5: Fire it from the boots-bench cheat too (`cheat_equip_boots`)**

In `deathward/world.py` `cheat_equip_boots`, right after `self.codex.see_gear(key)` (~line 1238), add:

```python
        if is_magical_boot(key):
            if self.codex.magical_boot_picked_up(key):
                self.codex.award_boots_collection()
                self.log("EVERY STEP THE DEEP STILL HIDES is yours. A gold star of its own.",
                         config.GOLD)
```

- [ ] **Step 6: Persist a displaced magical boot (`_put_back`)**

In `deathward/world.py` `_put_back`, extend the magical guard so a magical boot also never enters a container's loot list and is recorded on the ground. Replace the block (lines ~1388-1400):

```python
        p = self.player
        magical = is_magical(gear.key)
        magical_boot = is_magical_boot(gear.key)
        if sink is not None and hasattr(sink, "loot") and not (magical or magical_boot):
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
            elif magical_boot:
                self.codex.drop_magical_boot_to_ground(gear.key, self.depth, p.x, p.y)
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `py -3.13 -m deathward.tests TestMagicalBootsEconomy -v`
Expected: PASS (all economy tests). Then the full suite:
Run: `py -3.13 -m deathward.tests`
Expected: green.

- [ ] **Step 8: Commit**

```bash
git add deathward/world.py deathward/tests.py
git commit -m "Wire magical-boots pickup/drop/award hooks: collect, persist, gold star"
```

---

## Notes for the implementer

- **Read tasks in order.** Task 2 and Task 3 depend on Task 1's ledger + methods.
- **The full boot lifecycle** after this plan: generated (rare, unique) → placed & recorded on the ground → survives death via replay → picked up (collected, off the ground) or displaced (re-persisted) → all 12 → gold star. Confirm a boot picked up removes it from `boots_ground` so it does not replay next life (Task 1's `magical_boot_picked_up` pops it; Task 3 wires the pickup).
- The `_replay_magicals` change (`loc.get("bonus", 0)`) is a no-op for weapons — verify the weapon persistence tests stay green.
- If a single test reports "no tests ran", run the class or the whole file.
