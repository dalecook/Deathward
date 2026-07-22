# Suspend/Resume — Phase 1: Serialization Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `Player`, `Monster`, the level records (`Chest`/`Drop`/`Trap`/`Slain`/`Vendor`), `Level`, and `World` faithful `to_dict()` / `from_dict()` round-trips, plus a `Level`/`World` *restore* construction path — a pure serialization layer, round-trip-tested in isolation, with no wiring into the save file or game loop yet.

**Architecture:** Each object gains a `to_dict()` that emits JSON-safe primitives and a reconstruction path. `Player`/`Monster`/the records use `@classmethod from_dict(data)`. `Level` and `World` reconstruct through an optional `restore=` argument on `__init__`: the *stone* (layout) always regenerates deterministically from the codex seed, and the *dynamic* run state (monsters, drops, chests, sprung traps, the fog of contents seen, the RNG state) overlays from the saved dict. Nothing that already lives in the codex (the explored map, past-run corpses) is duplicated.

**Tech Stack:** Python 3.13, `unittest`. Tests live in the single file `deathward/tests.py`.

## Global Constraints

- **Test command:** `py -3.13 -m deathward.tests` (NOT `python`/`py` — those resolve to 3.14, which lacks pygame). Single test: `py -3.13 -m deathward.tests <Class>.<method> -v`.
- **No behavior change.** This phase adds methods and an *optional* `restore=` construction path. The existing generate path (`restore=None`) must remain byte-identical in behavior. The full suite (currently green) must stay green.
- **JSON-safe output.** Every `to_dict()` must be `json.dumps`-able: only `dict`/`list`/`str`/`int`/`float`/`bool`/`None`. No tuples, no objects. Tuples in the model (`intent`, loot entries, `stock`, `color`) serialize as lists and are rebuilt as tuples on load.
- **Determinism invariant untouched.** The run save is per-run state, never read during generation. `TestKnowledgeIsNotPower` (tests.py) must stay green.
- **Gear reconstruction goes through `ALL_GEAR`** (`deathward/items.py`), keyed by `.key`. The weapon carries a per-instance `.bonus` and is rebuilt with `ALL_GEAR[key].copy(bonus=n)`; armour/boots are shared references (`ALL_GEAR[key]`), matching how `Player.__init__` assigns them.
- **The stone is cut from `codex.layout_seed(depth)` only.** The restore path must NOT re-deal contents (`_populate`) and must NOT consume the run RNG.

---

## File Structure

- `deathward/player.py` — add `Player.to_dict` / `Player.from_dict` and a module-level `_PLAYER_STATE` field tuple. Add `ALL_GEAR` to the existing items import.
- `deathward/monsters.py` — add `Monster.to_dict` / `Monster.from_dict` and a module-level `_MONSTER_STATE` field tuple.
- `deathward/dungeon.py` — add `to_dict`/`from_dict` to `Chest`, `Drop`, `Trap`, `Slain`; refactor `Level._generate` into `_cut_stone` + `_place_corpse`; add `Level.to_dict`, a `restore=` path on `Level.__init__`, and `Level._restore`.
- `deathward/vendor.py` — add `Vendor.to_dict` / `Vendor.from_dict`.
- `deathward/world.py` — add `World.to_dict`, a `restore=` path on `World.__init__`, `World._resume`, and the RNG-state helpers `_rng_to_list` / `_rng_from_list`.
- `deathward/tests.py` — one new `TestCase` per task, each round-tripping the unit in isolation.

---

## Task 1: Player serialization

**Files:**
- Modify: `deathward/player.py` (import line ~19; add methods to `Player`)
- Test: `deathward/tests.py` (new `TestPlayerSerialization`)

**Interfaces:**
- Consumes: `deathward.items.ALL_GEAR` (key → gear object; `.copy(bonus=n)` on weapons).
- Produces:
  - `Player.to_dict(self) -> dict` — JSON-safe snapshot of all mutable player state + equipped gear keys.
  - `Player.from_dict(cls, data) -> Player` (classmethod) — rebuilds a `Player` from that dict.

- [ ] **Step 1: Write the failing test**

Add to `deathward/tests.py`:

```python
class TestPlayerSerialization(unittest.TestCase):
    """A player survives a round-trip through a plain dict with every field intact."""

    def test_player_round_trips_through_a_dict(self):
        import json
        from .player import Player
        from .items import ALL_GEAR
        p = Player()
        p.x, p.y = 7, 11
        p.hp, p.max_hp = 13, 20
        p.gold = 42
        p.energy = 3
        p.depth = 5
        p.kills = 9
        p.poison = 4
        p.haste = 2
        p.berserk = 6
        p.phoenix = True
        p.invisible = 3
        p.frozen = 1
        p.slipstep_hits = 3
        p.blade_coat = "weak"
        p.gift = "a_gift_key"
        p.enchants = {"plate": 2}
        p.slots = [["a potion", 3], None, ["a scroll", 1], None, None, None]
        p.weapon = ALL_GEAR["kris"].copy(bonus=2)
        p.boots = ALL_GEAR["boots_plate"]

        blob = p.to_dict()
        json.dumps(blob)                      # must be JSON-safe
        q = Player.from_dict(blob)

        for k in ("x", "y", "hp", "max_hp", "gold", "energy", "depth", "kills",
                  "poison", "haste", "berserk", "phoenix", "invisible", "frozen",
                  "slipstep_hits", "blade_coat", "gift"):
            self.assertEqual(getattr(q, k), getattr(p, k), k)
        self.assertEqual(q.weapon.key, "kris")
        self.assertEqual(q.weapon.bonus, 2)
        self.assertEqual(q.armour.key, p.armour.key)
        self.assertEqual(q.boots.key, "boots_plate")
        self.assertEqual(q.enchants, {"plate": 2})
        self.assertEqual(q.slots, [["a potion", 3], None,
                                   ["a scroll", 1], None, None, None])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m deathward.tests TestPlayerSerialization -v`
Expected: FAIL — `AttributeError: 'Player' object has no attribute 'to_dict'`.

- [ ] **Step 3: Write minimal implementation**

In `deathward/player.py`, extend the items import (line ~19) to include `ALL_GEAR`:

```python
from .items import ALL_GEAR, ARMOURS, BOOTS, CONSUMABLES, STARTING, WEAPONS
```

Add this module-level tuple just above `class Player:` (after the `EFFECTS` list):

```python
# Every plain scalar (int / bool / None / str) field that round-trips verbatim
# through the save. Gear, enchants, and the pack slots are handled specially.
_PLAYER_STATE = (
    "x", "y", "max_hp", "hp", "gold", "energy", "depth", "kills",
    "poison", "stuck", "haste", "might", "stoneskin", "regen", "vigor",
    "vigor_t", "weak", "berserk", "resist", "levitate", "invisible",
    "confused", "heroism", "sanctuary", "phoenix", "frozen",
    "slipstep_hits", "blade_coat", "gift",
)
```

Add these two methods inside `class Player` (e.g. after `gear_display`):

```python
    # --- serialization --------------------------------------------------
    def to_dict(self):
        """A JSON-safe snapshot of everything a suspended run must restore."""
        d = {k: getattr(self, k) for k in _PLAYER_STATE}
        d["weapon"] = {"key": self.weapon.key, "bonus": self.weapon.bonus}
        d["armour"] = self.armour.key
        d["boots"] = self.boots.key
        d["enchants"] = dict(self.enchants)
        d["slots"] = [None if s is None else [s[0], s[1]] for s in self.slots]
        return d

    @classmethod
    def from_dict(cls, data):
        p = cls()
        for k in _PLAYER_STATE:
            setattr(p, k, data[k])
        w = data["weapon"]
        p.weapon = ALL_GEAR[w["key"]].copy(bonus=w["bonus"])
        p.armour = ALL_GEAR[data["armour"]]
        p.boots = ALL_GEAR[data["boots"]]
        p.enchants = dict(data["enchants"])
        p.slots = [None if s is None else [s[0], s[1]] for s in data["slots"]]
        return p
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.13 -m deathward.tests TestPlayerSerialization -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `py -3.13 -m deathward.tests`
Expected: all green (no behavior change).

- [ ] **Step 6: Commit**

```bash
git add deathward/player.py deathward/tests.py
git commit -m "Player.to_dict/from_dict: a run-save round-trip for the hero"
```

---

## Task 2: Monster serialization

**Files:**
- Modify: `deathward/monsters.py` (add methods to `Monster`)
- Test: `deathward/tests.py` (new `TestMonsterSerialization`)

**Interfaces:**
- Consumes: `Monster(key, x, y)` (the existing constructor).
- Produces:
  - `Monster.to_dict(self) -> dict` — key + every dynamic field.
  - `Monster.from_dict(cls, data) -> Monster` (classmethod).
- Note: `intent` is `None` or a tuple like `("smash", x, y)` — serializes as a list, rebuilds as a tuple. `warden_last` is `None` or a plain string (`"smash"`/`"spit"`), so it round-trips verbatim. `speed`/`t`/`name` are derived from `key` and are NOT stored.

- [ ] **Step 1: Write the failing test**

Add to `deathward/tests.py`:

```python
class TestMonsterSerialization(unittest.TestCase):
    """A monster's live state — wounds, wakefulness, a telegraphed intent, every
    status timer — survives a round-trip through a dict."""

    def test_monster_round_trips_with_all_dynamic_state(self):
        import json
        from .monsters import Monster
        m = Monster("brute", 5, 6)
        m.hp = 7
        m.energy = 1
        m.awake = True
        m.intent = ("smash", 5, 7)
        m.stunned = 2
        m.burning = 3
        m.poisoned = 1
        m.weak = 2
        m.feared = 4
        m.confused = 1
        m.hammer_hits = 2
        m.enraged = 3
        m.recharge = 1
        m.ray_armed = True
        m.fled = True
        m.warden_last = "spit"
        m.feed = 0.5

        blob = m.to_dict()
        json.dumps(blob)                      # JSON-safe
        n = Monster.from_dict(blob)

        self.assertEqual(n.key, "brute")
        self.assertEqual((n.x, n.y), (5, 6))
        self.assertEqual(n.max_hp, m.max_hp)
        for k in ("hp", "energy", "awake", "stunned", "burning", "poisoned",
                  "weak", "feared", "confused", "hammer_hits", "enraged",
                  "recharge", "ray_armed", "fled", "warden_last", "feed"):
            self.assertEqual(getattr(n, k), getattr(m, k), k)
        self.assertEqual(n.intent, ("smash", 5, 7))
        self.assertIsInstance(n.intent, tuple)

    def test_a_sleeping_monster_with_no_intent_round_trips(self):
        from .monsters import Monster
        m = Monster("rat", 2, 2)          # starts asleep, intent None
        n = Monster.from_dict(m.to_dict())
        self.assertFalse(n.awake)
        self.assertIsNone(n.intent)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m deathward.tests TestMonsterSerialization -v`
Expected: FAIL — `AttributeError: 'Monster' object has no attribute 'to_dict'`.

- [ ] **Step 3: Write minimal implementation**

In `deathward/monsters.py`, add this module-level tuple just above `class Monster:`:

```python
# Every plain scalar field of a live monster that round-trips verbatim. `key`
# rebuilds the derived template (t/speed/name); `intent` is handled specially.
_MONSTER_STATE = (
    "x", "y", "hp", "max_hp", "energy", "awake", "stunned", "burning",
    "poisoned", "fled", "disguised", "warden_last", "feed", "recharge",
    "ray_armed", "weak", "feared", "confused", "hammer_hits", "enraged",
)
```

Add these methods inside `class Monster` (e.g. after the `dist` method):

```python
    # --- serialization --------------------------------------------------
    def to_dict(self):
        d = {k: getattr(self, k) for k in _MONSTER_STATE}
        d["key"] = self.key
        d["intent"] = list(self.intent) if self.intent is not None else None
        return d

    @classmethod
    def from_dict(cls, data):
        m = cls(data["key"], data["x"], data["y"])
        for k in _MONSTER_STATE:
            setattr(m, k, data[k])
        m.intent = tuple(data["intent"]) if data["intent"] is not None else None
        return m
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.13 -m deathward.tests TestMonsterSerialization -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `py -3.13 -m deathward.tests`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add deathward/monsters.py deathward/tests.py
git commit -m "Monster.to_dict/from_dict: a live monster round-trips its whole state"
```

---

## Task 3: Level-record and vendor serialization

**Files:**
- Modify: `deathward/dungeon.py` (add methods to `Chest`, `Drop`, `Trap`, `Slain`)
- Modify: `deathward/vendor.py` (add methods to `Vendor`)
- Test: `deathward/tests.py` (new `TestRecordSerialization`)

**Interfaces:**
- Produces (each a `to_dict(self) -> dict` + `from_dict(cls, data)` classmethod):
  - `Chest` — `{x, y, loot, opened}`; `loot` is a list of `("gold", n)`/`("item", flavor)`/`("gear", key)`, stored as lists, rebuilt as tuples.
  - `Drop` — `{x, y, kind, payload, gift, bonus}`.
  - `Trap` — `{key, x, y, sprung}`.
  - `Slain` — `{x, y, key, color, loot}`; `color` is an `(r,g,b)` tuple stored as a list.
  - `Vendor` — `{x, y, depth, stock}`; `stock` is a list of `(kind, payload)`, stored as lists, rebuilt as tuples. `from_dict` bypasses `__init__` so it does NOT re-roll stock.

- [ ] **Step 1: Write the failing test**

Add to `deathward/tests.py`:

```python
class TestRecordSerialization(unittest.TestCase):
    """The small floor records — chests, drops, traps, bodies, the vendor — each
    survive a round-trip, with their tuple payloads rebuilt as tuples."""

    def test_chest_round_trips(self):
        import json
        from .dungeon import Chest
        c = Chest(4, 5, [("gold", 30), ("gear", "kris")])
        c.opened = True
        blob = c.to_dict()
        json.dumps(blob)
        d = Chest.from_dict(blob)
        self.assertEqual((d.x, d.y), (4, 5))
        self.assertTrue(d.opened)
        self.assertEqual(d.loot, [("gold", 30), ("gear", "kris")])
        self.assertIsInstance(d.loot[0], tuple)

    def test_drop_round_trips(self):
        from .dungeon import Drop
        d = Drop(2, 3, "gear", "windfang", gift="windfang", bonus=2)
        e = Drop.from_dict(d.to_dict())
        self.assertEqual((e.x, e.y, e.kind, e.payload, e.gift, e.bonus),
                         (2, 3, "gear", "windfang", "windfang", 2))

    def test_trap_round_trips_its_sprung_flag(self):
        from .traps import Trap
        t = Trap("dart", 6, 7)
        t.sprung = True
        u = Trap.from_dict(t.to_dict())
        self.assertEqual((u.key, u.x, u.y), ("dart", 6, 7))
        self.assertTrue(u.sprung)

    def test_slain_round_trips(self):
        from .dungeon import Slain
        s = Slain(3, 3, "brute", (200, 40, 40), loot=[("gold", 5)])
        t = Slain.from_dict(s.to_dict())
        self.assertEqual((t.x, t.y, t.key), (3, 3, "brute"))
        self.assertEqual(t.color, (200, 40, 40))
        self.assertEqual(t.loot, [("gold", 5)])

    def test_vendor_round_trips_without_rerolling_stock(self):
        import json, random
        from .vendor import Vendor
        v = Vendor(8, 9, depth=6, rng=random.Random(1))
        stock_before = list(v.stock)
        blob = v.to_dict()
        json.dumps(blob)
        w = Vendor.from_dict(blob)
        self.assertEqual((w.x, w.y, w.depth), (8, 9, 6))
        self.assertEqual(w.stock, stock_before)
        self.assertTrue(all(isinstance(s, tuple) for s in w.stock))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m deathward.tests TestRecordSerialization -v`
Expected: FAIL — `AttributeError: 'Chest' object has no attribute 'to_dict'`.

- [ ] **Step 3: Write minimal implementation**

In `deathward/dungeon.py`, add to `class Chest`:

```python
    def to_dict(self):
        return {"x": self.x, "y": self.y,
                "loot": [list(t) for t in self.loot], "opened": self.opened}

    @classmethod
    def from_dict(cls, data):
        c = cls(data["x"], data["y"], [tuple(t) for t in data["loot"]])
        c.opened = data["opened"]
        return c
```

Add to `class Drop`:

```python
    def to_dict(self):
        return {"x": self.x, "y": self.y, "kind": self.kind,
                "payload": self.payload, "gift": self.gift, "bonus": self.bonus}

    @classmethod
    def from_dict(cls, data):
        return cls(data["x"], data["y"], data["kind"], data["payload"],
                   gift=data["gift"], bonus=data["bonus"])
```

Add to `class Slain`:

```python
    def to_dict(self):
        return {"x": self.x, "y": self.y, "key": self.key,
                "color": list(self.color),
                "loot": [list(t) for t in self.loot]}

    @classmethod
    def from_dict(cls, data):
        return cls(data["x"], data["y"], data["key"], tuple(data["color"]),
                   loot=[tuple(t) for t in data["loot"]])
```

In `deathward/traps.py`, add to `class Trap`:

```python
    def to_dict(self):
        return {"key": self.key, "x": self.x, "y": self.y, "sprung": self.sprung}

    @classmethod
    def from_dict(cls, data):
        t = cls(data["key"], data["x"], data["y"])
        t.sprung = data["sprung"]
        return t
```

In `deathward/vendor.py`, add to `class Vendor`:

```python
    def to_dict(self):
        return {"x": self.x, "y": self.y, "depth": self.depth,
                "stock": [list(s) for s in self.stock]}

    @classmethod
    def from_dict(cls, data):
        v = cls.__new__(cls)      # bypass __init__: do NOT re-roll the stock
        v.x, v.y = data["x"], data["y"]
        v.depth = data["depth"]
        v.stock = [tuple(s) for s in data["stock"]]
        return v
```

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3.13 -m deathward.tests TestRecordSerialization -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `py -3.13 -m deathward.tests`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add deathward/dungeon.py deathward/traps.py deathward/vendor.py deathward/tests.py
git commit -m "Floor records round-trip: chest, drop, trap, slain, vendor"
```

---

## Task 4: Level serialization + restore construction path

**Files:**
- Modify: `deathward/dungeon.py` (`Level.__init__`; refactor `_generate`; add `_cut_stone`, `_place_corpse`, `_restore`, `to_dict`)
- Test: `deathward/tests.py` (new `TestLevelSerialization`)

**Interfaces:**
- Consumes: `Monster.from_dict`, `Drop.from_dict`, `Chest.from_dict`, `Slain.from_dict`, `Trap` records, `Vendor.from_dict` (Tasks 2–3); `codex.layout_seed(depth)`.
- Produces:
  - `Level.__init__(self, depth, rng, codex, restore=None)` — `restore=None` keeps today's generate path; a dict triggers the restore path.
  - `Level._cut_stone(self, codex)` — the deterministic layout (halls, rooms, corridors, entrance, stairs, `gate_room`, traps). Extracted verbatim from the top of `_generate`.
  - `Level._place_corpse(self, codex)` — the past-run corpse placement. Extracted verbatim from the bottom of `_generate`.
  - `Level._restore(self, codex, data)` — cut stone, overlay saved dynamic state, place corpse.
  - `Level.to_dict(self) -> dict` — `{depth, monsters, drops, chests, slain, vendor, traps, hoard, seen}`.
- Note: `explored` is NOT serialized here — it already persists via `codex.recall_map` and is rebuilt in `__init__`. The layout regenerates from the stone; only dynamic state overlays. The restore path must not call `_populate`/`_populate_boss` and must not touch the run `rng`.

- [ ] **Step 1: Refactor `_generate` into `_cut_stone` + `_place_corpse` (no behavior change)**

In `deathward/dungeon.py`, split the existing `Level._generate(self, codex)`. Move its **stone** section (from `# --- the stone` through the `self._install_traps()` call) into a new method `_cut_stone`, and its **corpse** section (from the `c = codex.corpse_at(self.depth)` block to the end) into `_place_corpse`. The result:

```python
    def _cut_stone(self, codex):
        # --- the stone: cut once per GAME, identical on every respawn ----
        rng = self.lrng
        self._place_halls(rng)

        want = 9 + min(5, self.depth)
        attempts = 400
        while len(self.rooms) < want and attempts > 0:
            attempts -= 1
            r = self._try_room(rng, rng.choice(FILLER_CLASSES))
            if r is None:
                continue
            self._carve_room(r)
            self.rooms.append(r)

        if self.rooms:
            order = [self.rooms[0]]
            rest = self.rooms[1:]
            while rest:
                a = order[-1]
                b = min(rest, key=lambda r: (r.cx - a.cx) ** 2 + (r.cy - a.cy) ** 2)
                rest.remove(b)
                order.append(b)
            self.rooms = order

        for i in range(1, len(self.rooms)):
            a, b = self.rooms[i - 1], self.rooms[i]
            if rng.random() < 0.5:
                self._carve_h(a.cx, b.cx, a.cy)
                self._carve_v(a.cy, b.cy, b.cx)
            else:
                self._carve_v(a.cy, b.cy, a.cx)
                self._carve_h(a.cx, b.cx, b.cy)
        for _ in range(2):
            a, b = rng.sample(self.rooms, 2) if len(self.rooms) >= 2 else (None, None)
            if a and b:
                self._carve_h(a.cx, b.cx, a.cy)
                self._carve_v(a.cy, b.cy, b.cx)

        modest = [r for r in self.rooms if not r.hall] or self.rooms
        gate_room = min(modest, key=lambda r: r.cx + r.cy)
        self.entrance = (gate_room.cx, gate_room.cy)
        self.start = self.entrance
        self.gate_room = gate_room
        self.stairs = self._place_stairs(rng)
        self._install_traps()

    def _place_corpse(self, codex):
        c = codex.corpse_at(self.depth)
        if c:
            cx, cy = c.get("x", 0), c.get("y", 0)
            if not self.walkable(cx, cy):
                spot = self._free_tile()
                cx, cy = spot if spot else self.entrance
            self.corpse = Corpse(cx, cy, c.get("gold", 0), c.get("weapon"),
                                 c.get("gift"), c.get("loot"),
                                 weapon_bonus=c.get("weapon_bonus", 0))
            self.monsters = [m for m in self.monsters if (m.x, m.y) != (cx, cy)]
            self.drops = [d for d in self.drops if (d.x, d.y) != (cx, cy)]
            self.chests = [ch for ch in self.chests if (ch.x, ch.y) != (cx, cy)]

    def _generate(self, codex):
        self._cut_stone(codex)
        # snapshot the persisted ground magicals BEFORE this floor's fresh rolls
        persisted_magicals = dict(codex.magical_ground)
        persisted_boots = dict(codex.boots_ground)
        if self.depth >= config.DEPTH_MAX:
            self._populate_boss()
        else:
            self._populate(codex)
        self._replay_magicals(persisted_magicals)
        self._replay_magicals(persisted_boots)
        self._place_corpse(codex)
```

> Copy the bodies of `_cut_stone`/`_place_corpse` verbatim from the current `_generate` — keep the existing comments. The three snippets above show the target structure; do not paraphrase the logic.

- [ ] **Step 2: Run the full suite to confirm the refactor changed nothing**

Run: `py -3.13 -m deathward.tests`
Expected: all green (pure extraction — identical behavior).

- [ ] **Step 3: Commit the refactor**

```bash
git add deathward/dungeon.py
git commit -m "Extract Level._cut_stone and _place_corpse from _generate (no behavior change)"
```

- [ ] **Step 4: Write the failing test for the restore path**

Add to `deathward/tests.py`:

```python
class TestLevelSerialization(unittest.TestCase):
    """A floor's dynamic state — dealt monsters, taken loot, a sprung trap, the
    contents you've laid eyes on — round-trips, while its stone regenerates
    identically from the seed."""

    def test_level_restores_dynamic_state_over_regenerated_stone(self):
        import json
        from .world import World
        from .dungeon import Level, Drop
        codex = FakeSave()
        w = World(codex, seed=4)
        lv = w.level

        # perturb the live state: wound & wake a monster, drop loot, spring a
        # trap, mark a tile's contents seen.
        if lv.monsters:
            lv.monsters[0].hp = 1
            lv.monsters[0].awake = True
        lv.drops.append(Drop(lv.entrance[0], lv.entrance[1], "gold", 7))
        if lv.traps:
            lv.traps[0].sprung = True
        lv.seen[lv.entrance[1]][lv.entrance[0]] = True

        blob = lv.to_dict()
        json.dumps(blob)
        restored = Level(lv.depth, w.rng, codex, restore=blob)

        # stone is identical (same seed) ...
        self.assertEqual(restored.grid, lv.grid)
        self.assertEqual(restored.entrance, lv.entrance)
        self.assertEqual(restored.stairs, lv.stairs)
        # ... dynamic state overlays faithfully
        self.assertEqual(len(restored.monsters), len(lv.monsters))
        if lv.monsters:
            self.assertEqual(restored.monsters[0].hp, 1)
            self.assertTrue(restored.monsters[0].awake)
        self.assertTrue(any(d.kind == "gold" and d.payload == 7
                            for d in restored.drops))
        sprung = {(t.x, t.y) for t in restored.traps if t.sprung}
        self.assertEqual(sprung, {(t.x, t.y) for t in lv.traps if t.sprung})
        self.assertTrue(restored.seen[lv.entrance[1]][lv.entrance[0]])

    def test_restore_does_not_consume_the_run_rng(self):
        from .world import World
        from .dungeon import Level
        codex = FakeSave()
        w = World(codex, seed=4)
        before = w.rng.getstate()
        Level(w.level.depth, w.rng, codex, restore=w.level.to_dict())
        self.assertEqual(w.rng.getstate(), before,
                         "restoring a floor must not deal from the run RNG")
```

- [ ] **Step 5: Run test to verify it fails**

Run: `py -3.13 -m deathward.tests TestLevelSerialization -v`
Expected: FAIL — `Level.__init__() got an unexpected keyword argument 'restore'` (or `to_dict` missing).

- [ ] **Step 6: Implement `restore=` on `__init__`, `_restore`, and `to_dict`**

In `deathward/dungeon.py`, change `Level.__init__`'s signature and its final dispatch. The last line of `__init__` is currently `self._generate(codex)`; replace it:

```python
    def __init__(self, depth, rng, codex, restore=None):
        # ... all existing field setup, unchanged, through self.seen = ...
        if restore is None:
            self._generate(codex)
        else:
            self._restore(codex, restore)
```

Add `_restore` and `to_dict` to `class Level`:

```python
    def _restore(self, codex, data):
        """Parallel to _generate: cut the same stone, then overlay the saved
        dynamic state instead of dealing a fresh floor. The run RNG is untouched."""
        from .monsters import Monster
        from .vendor import Vendor
        self._cut_stone(codex)
        self.monsters = [Monster.from_dict(m) for m in data["monsters"]]
        self.drops = [Drop.from_dict(d) for d in data["drops"]]
        self.chests = [Chest.from_dict(c) for c in data["chests"]]
        self.slain = [Slain.from_dict(s) for s in data["slain"]]
        self.vendor = Vendor.from_dict(data["vendor"]) if data["vendor"] else None
        # traps were re-cut by _cut_stone (same stone); restore which have sprung
        sprung = {(t["key"], t["x"], t["y"]) for t in data["traps"] if t["sprung"]}
        for tr in self.traps:
            if (tr.key, tr.x, tr.y) in sprung:
                tr.sprung = True
        # the fog of CONTENTS you had laid eyes on this run
        self.seen = [row[:] for row in data["seen"]]
        # the hoard marker: re-link to the room at the saved centre
        self.hoard = None
        if data["hoard"] is not None:
            hx, hy = data["hoard"]
            for r in self.rooms:
                if (r.cx, r.cy) == (hx, hy):
                    self.hoard = r
                    break
        self._place_corpse(codex)

    def to_dict(self):
        return {
            "depth": self.depth,
            "monsters": [m.to_dict() for m in self.monsters],
            "drops": [d.to_dict() for d in self.drops],
            "chests": [c.to_dict() for c in self.chests],
            "slain": [s.to_dict() for s in self.slain],
            "vendor": self.vendor.to_dict() if self.vendor else None,
            "traps": [t.to_dict() for t in self.traps],
            "hoard": [self.hoard.cx, self.hoard.cy] if self.hoard else None,
            "seen": [row[:] for row in self.seen],
        }
```

- [ ] **Step 7: Run test to verify it passes**

Run: `py -3.13 -m deathward.tests TestLevelSerialization -v`
Expected: PASS.

- [ ] **Step 8: Run the full suite**

Run: `py -3.13 -m deathward.tests`
Expected: all green.

- [ ] **Step 9: Commit**

```bash
git add deathward/dungeon.py deathward/tests.py
git commit -m "Level.to_dict + restore path: stone regenerates, dynamic state overlays"
```

---

## Task 5: World serialization + resume construction path

**Files:**
- Modify: `deathward/world.py` (`World.__init__`; add `_resume`, `to_dict`, module-level `_rng_to_list`/`_rng_from_list`)
- Test: `deathward/tests.py` (new `TestWorldSerialization`)

**Interfaces:**
- Consumes: `Player.from_dict` (Task 1); `Level(depth, rng, codex, restore=...)` and `Level.to_dict` (Task 4); `level.compute_fov(px, py)`.
- Produces:
  - `World.__init__(self, codex, seed=None, restore=None)` — `restore=None` keeps today's fresh-run path; a dict resumes.
  - `World.to_dict(self) -> dict` — `{seed, depth, tick, vendor_pct, run_kills, region_alerted, player_region, rng, player, levels}`. `levels` keys are stringified depths (JSON object keys must be strings).
  - `World._resume(self, data)` — restore RNG, player, counters, every visited level, current level, region, and FOV.
  - module-level `_rng_to_list(rng) -> list` / `_rng_from_list(data) -> tuple` — convert `random.Random.getstate()` to/from a JSON-safe form.
- Note: only alive runs are ever serialized, so `dead`/`won`/`death_cause` are not stored (they default in `__init__`). `player_region` serializes as the `(cx, cy)` of its room, or `None`, and re-links against the restored current level's rooms.

- [ ] **Step 1: Write the failing test**

Add to `deathward/tests.py`:

```python
class TestWorldSerialization(unittest.TestCase):
    """A whole run — position, gear, floor state, and the exact RNG cursor —
    survives a round-trip, and the restored run deals its next floor identically."""

    def test_world_round_trips_position_gear_and_rng(self):
        import json
        from .world import World
        codex = FakeSave()
        w = World(codex, seed=4)
        w.player.x, w.player.y = w.level.entrance
        w.player.gold = 55
        w.tick = 12
        w.vendor_pct = 30
        w.run_kills = 3

        blob = w.to_dict()
        json.dumps(blob)
        w2 = World(codex, restore=blob)

        self.assertEqual(w2.depth, w.depth)
        self.assertEqual((w2.player.x, w2.player.y), (w.player.x, w.player.y))
        self.assertEqual(w2.player.gold, 55)
        self.assertEqual(w2.tick, 12)
        self.assertEqual(w2.vendor_pct, 30)
        self.assertEqual(w2.run_kills, 3)
        self.assertEqual(w2.player.weapon.key, w.player.weapon.key)
        self.assertEqual(w2.level.grid, w.level.grid)
        # the RNG cursor is exactly where it was: the next draw matches
        self.assertEqual(w2.rng.getstate(), w.rng.getstate())
        self.assertEqual(w2.rng.random(), w.rng.random())

    def test_resumed_run_descends_into_an_identical_next_floor(self):
        # RNG continuity: a floor first entered AFTER a suspend/resume has the
        # same contents it would have had without the interruption.
        from .world import World
        codex = FakeSave()
        w = World(codex, seed=4)
        w2 = World(codex, restore=w.to_dict())

        w.new_level(2)
        w2.new_level(2)
        self.assertEqual([m.key for m in w2.level.monsters],
                         [m.key for m in w.level.monsters])
        self.assertEqual([(d.x, d.y, d.kind) for d in w2.level.drops],
                         [(d.x, d.y, d.kind) for d in w.level.drops])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m deathward.tests TestWorldSerialization -v`
Expected: FAIL — `World.__init__() got an unexpected keyword argument 'restore'`.

- [ ] **Step 3: Add the RNG-state helpers**

In `deathward/world.py`, add at module level (near the top, after imports):

```python
def _rng_to_list(rng):
    """random.Random.getstate() is (version, tuple-of-ints, gauss-or-None).
    Flatten the inner tuple to a list so it survives json.dump."""
    version, state, gauss = rng.getstate()
    return [version, list(state), gauss]


def _rng_from_list(data):
    version, state, gauss = data
    return (version, tuple(state), gauss)
```

- [ ] **Step 4: Add `restore=` to `World.__init__` and implement `_resume` + `to_dict`**

In `deathward/world.py`, restructure `World.__init__` so the common setup runs for both paths and only the *fresh-run* tail is guarded. Change the signature to `def __init__(self, codex, seed=None, restore=None):` and set the seed from the restore block when present:

```python
    def __init__(self, codex, seed=None, restore=None):
        self.codex = codex
        if restore is not None:
            self.seed = restore["seed"]
        else:
            self.seed = seed if seed is not None else random.randrange(1 << 30)
        self.rng = random.Random(self.seed)
        if codex.world_seed is None:
            codex.world_seed = random.randrange(1 << 30)
        if not codex.appearance:
            codex.roll_appearances(codex.world_seed)
        # --- fields common to a fresh run and a resumed one ---
        self.tick = 0
        self.dead = False
        self.won = False
        self.death_cause = None
        self.shake_t = 0
        self.depth = 1
        self.level = None
        self.levels = {}
        self.vendor_pct = 0
        self.run_kills = 0
        self.learned = None
        self.trading = False
        self.aiming = None
        self.aiming_flavor = None
        self.player_region = None
        self.region_alerted = False
        self.fx = []
        if restore is not None:
            self._resume(restore)
        else:
            self.player = Player()
            for g in (self.player.weapon, self.player.armour, self.player.boots):
                self.codex.see_gear(g.key)
            self.new_level(1)
            self.log("You descend to floor 1.", config.STAIRS)
```

> Preserve every comment and any lines the current `__init__` has that aren't shown here (e.g. the explanatory block comments) — this step reorganizes the existing body around the `if restore` guard; it does not drop fields. Compare against the current `__init__` (world.py ~73–117) and keep the fresh-run branch behaviorally identical.

Add `_resume` and `to_dict` to `class World`:

```python
    def _resume(self, data):
        self.rng.setstate(_rng_from_list(data["rng"]))
        self.player = Player.from_dict(data["player"])
        self.tick = data["tick"]
        self.vendor_pct = data["vendor_pct"]
        self.run_kills = data["run_kills"]
        self.region_alerted = data["region_alerted"]
        self.depth = data["depth"]
        for sd, lvd in data["levels"].items():
            d = int(sd)
            self.levels[d] = Level(d, self.rng, self.codex, restore=lvd)
        self.level = self.levels[self.depth]
        self.player_region = None
        if data["player_region"] is not None:
            rx, ry = data["player_region"]
            for r in self.level.rooms:
                if (r.cx, r.cy) == (rx, ry):
                    self.player_region = r
                    break
        self.level.compute_fov(self.player.x, self.player.y)

    def to_dict(self):
        return {
            "seed": self.seed,
            "depth": self.depth,
            "tick": self.tick,
            "vendor_pct": self.vendor_pct,
            "run_kills": self.run_kills,
            "region_alerted": self.region_alerted,
            "player_region": ([self.player_region.cx, self.player_region.cy]
                              if self.player_region is not None else None),
            "rng": _rng_to_list(self.rng),
            "player": self.player.to_dict(),
            "levels": {str(d): lv.to_dict() for d, lv in self.levels.items()},
        }
```

Confirm `Level` and `Player` are already imported in `world.py` (they are used by `__init__` today). If `Level` is not yet imported at module scope, add it to the existing dungeon import.

- [ ] **Step 5: Run test to verify it passes**

Run: `py -3.13 -m deathward.tests TestWorldSerialization -v`
Expected: PASS.

- [ ] **Step 6: Run the full suite**

Run: `py -3.13 -m deathward.tests`
Expected: all green — the fresh-run path is unchanged, and the determinism invariant (`TestKnowledgeIsNotPower`) holds.

- [ ] **Step 7: Commit**

```bash
git add deathward/world.py deathward/tests.py
git commit -m "World.to_dict + resume path: a whole run round-trips, RNG cursor intact"
```

---

## Self-Review Notes (for the executor)

- **RNG continuity is the load-bearing test** (`test_resumed_run_descends_into_an_identical_next_floor`). If it fails, the resume path consumed or mis-restored the run RNG — check that `Level(restore=...)` never calls `_populate` and that `_rng_from_list` rebuilds the exact `(version, tuple, gauss)` shape.
- **This phase does NOT wire anything into the save file or the game loop.** No `codex.py`, `game.py`, or `config.py` changes here — those are Phase 2. `to_dict`/`from_dict` are dead code until Phase 2 calls them; that is intended.
- **Scope note vs. spec:** the spec's floor-state list did not name `slain` (killed bodies with loot) explicitly; it is included here because it is dynamic run-state of the same category as drops/chests, and omitting it would silently lose looted corpses across a suspend. Flagged for the controller to confirm.
- **`explored` is deliberately not in `Level.to_dict`** — it already persists via `codex.recall_map` and is restored in `Level.__init__`. Only per-run `seen` is serialized.
