# Magical Armour — Phase 1 (Roster + Reused-Mechanic Pieces) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the 11 magical armour pieces whose mechanics reuse existing engine systems — thorns, wraithsilk, the retaliation trio (venom/cinder/glacial), Lifeweaver regen, Bastion hit-cap, Last Breath death-refusal, Blinding Light, Stone Golem's Chest, Robe of Hades — plus their distribution and the Firestorm-scroll self-burn fix.

**Architecture:** Every reactive piece triggers on the existing on-struck point (`monster_attacks_player`) and is gated by a single per-player cooldown (`player.armour_cd`), since only one armour is worn at a time. The elemental pieces apply the same monster statuses (`m.burning`/`m.poisoned`/`m.stunned`) that weapons already apply and that already tick + serialize. Passive pieces hook the damage calc (Bastion), the per-turn tick (Lifeweaver), and `kill_player` (Last Breath, mirroring the phoenix). Magical armour inherits the merged per-instance bonus model (found unenhanced, DWEN-enchantable).

**Tech Stack:** Python 3.13, stdlib `unittest`, `pygame` (sprites only). No new dependencies.

## Global Constraints

- **Test command:** `py -3.13 -m deathward.tests` (Python 3.13 — 3.14 has no pygame).
- **Determinism:** reactive triggers are deterministic counters (no RNG); the only RNG is the Robe/Firestorm damage, which draws the world RNG (`self.rng`), never the Kodex. `TestKnowledgeIsNotPower` must stay green.
- **One armour at a time:** all reactive runtime state is a couple of scalars on the Player (`armour_cd`, `lastbreath_used`), serialized with the run.
- **Keys:** the `thorn` and `silk` keys are reclaimed (Plan A removed them from `ARMOURS`); all magical keys live in the flat `ALL_GEAR` namespace — no collisions.
- **Bonus model:** magical armour is found unenhanced (`bonus=0`) and DWEN-enchantable via the existing per-instance `Armour.bonus`.
- **Phase 1 excludes** Fadecloak, Shademail, Nightcloak (the invisibility + wall-walk subsystems are Phase 2).
- Ship the exact values in this plan; numbers are playtest-tunable.

---

### Task 1: Reactive-armour infrastructure + config constants

The per-player reactive state and the tunables every later task consumes.

**Files:**
- Modify: `deathward/config.py` (add constants near the other combat constants, e.g. after `POISON_TURNS`/`FREEZE_TURNS`)
- Modify: `deathward/player.py` (`__init__` ~86–98; `_PLAYER_STATE` 46–52; `from_dict` ~174–185; `tick_effects` ~188)
- Test: `deathward/tests.py`

**Interfaces:**
- Produces: `player.armour_cd` (int, default 0 — the reactive on-struck cooldown), `player.lastbreath_used` (bool, default False). Both in `_PLAYER_STATE`. `player.tick_effects` decrements `armour_cd`. Config: `ARMOUR_RETAL_RECHARGE=3`, `ARMOUR_CAPSTONE_RECHARGE=4`, `CINDER_BURN_TURNS=2`, `VENOM_POISON_TURNS=3`, `BASTION_CAP=8`, `LIFEWEAVE_HEAL=2`, `BLINDING_RADIUS=2`, `BLINDING_STUN_TURNS=2`, `LASTBREATH_SANCTUARY=1`.

- [ ] **Step 1: Write the failing test**

```python
class TestReactiveArmourInfra(unittest.TestCase):
    def test_new_reactive_state_defaults_and_ticks(self):
        from .player import Player
        p = Player()
        self.assertEqual(p.armour_cd, 0)
        self.assertFalse(p.lastbreath_used)

    def test_armour_cd_ticks_down_each_turn(self):
        codex = FakeSave()
        w = World(codex, seed=6)
        w.player.armour_cd = 3
        w.player.tick_effects(w)
        self.assertEqual(w.player.armour_cd, 2)

    def test_reactive_state_round_trips_and_old_saves_default(self):
        import json
        from .items import ALL_GEAR
        from .player import Player
        p = Player()
        p.armour_cd = 2
        p.lastbreath_used = True
        blob = p.to_dict()
        q = Player.from_dict(json.loads(json.dumps(blob)))
        self.assertEqual(q.armour_cd, 2)
        self.assertTrue(q.lastbreath_used)
        # an OLD save that predates these fields must load with defaults, not crash
        old = p.to_dict()
        del old["armour_cd"]
        del old["lastbreath_used"]
        r = Player.from_dict(old)
        self.assertEqual(r.armour_cd, 0)
        self.assertFalse(r.lastbreath_used)
```

- [ ] **Step 2: Run to verify it fails**

Run: `py -3.13 -m deathward.tests`
Expected: FAIL — `armour_cd`/`lastbreath_used` don't exist; `from_dict` does `data[k]` and would `KeyError` on the missing-field case.

- [ ] **Step 3: Add the config constants** (`deathward/config.py`)

```python
# --- magical armour (Phase 1) ---
ARMOUR_RETAL_RECHARGE = 3      # retaliation trio: turns between on-struck triggers
ARMOUR_CAPSTONE_RECHARGE = 4   # Blinding Light / Robe of Hades
CINDER_BURN_TURNS = 2          # Cinderplate: attacker burns this many turns
VENOM_POISON_TURNS = 3         # Venomweave: attacker poisoned this many turns
BASTION_CAP = 8                # Bastion: no single hit exceeds this
LIFEWEAVE_HEAL = 2             # Lifeweaver: hp knitted per turn while worn
BLINDING_RADIUS = 2            # Blinding Light: stun radius (tiles)
BLINDING_STUN_TURNS = 2        # Blinding Light: stun duration
LASTBREATH_SANCTUARY = 1       # Last Breath: turns untouchable after the save
```

- [ ] **Step 4: Add the player state** (`deathward/player.py`)

In `__init__` (after `self.slipstep_hits = 0` / near the other reactive fields), add:

```python
        self.armour_cd = 0          # magical armour: on-struck reactive cooldown
        self.lastbreath_used = False # Last Breath: the once-per-life save, spent
```

Extend `_PLAYER_STATE` (append the two new field names):

```python
    "slipstep_hits", "blade_coat", "gift", "armour_cd", "lastbreath_used",
)
```

Make `from_dict` tolerant so a save that predates a field loads with the fresh default instead of `KeyError` (this is the backward-compat migration — no version bump needed):

```python
        for k in _PLAYER_STATE:
            setattr(p, k, data.get(k, getattr(p, k)))
```

In `tick_effects`, decrement the cooldown (near the top, with the other timers):

```python
        if self.armour_cd > 0:
            self.armour_cd -= 1
```

- [ ] **Step 5: Run to verify it passes**

Run: `py -3.13 -m deathward.tests`
Expected: PASS (full suite green, incl. `TestKnowledgeIsNotPower`).

- [ ] **Step 6: Commit**

```bash
git add deathward/config.py deathward/player.py deathward/tests.py
git commit -m "Magical armour infra: reactive cooldown + last-breath flag + tunables"
```

---

### Task 2: The magical armour roster table + sprites

Add the 11 pieces to `ARMOURS` (traits + stats + notes) and a sprite each. Mechanics are wired in later tasks; here the pieces just exist and carry their trait strings.

**Files:**
- Modify: `deathward/items.py` (`ARMOURS`, after the ordinary four rungs, ~line 178)
- Modify: `deathward/sprites.py` (`gear()`, add a branch per new key; `thorn`/`silk`/`scale`/`chain` branches already exist and can be reused/repurposed)
- Test: `deathward/tests.py`

**Interfaces:**
- Produces: `ARMOURS` gains `thorn`, `silk`, `venom`, `cinder`, `glacial`, `lifeweave` (T4), `bastion`, `lastbreath`, `blinding`, `stonegolem`, `hades` (T5), each with the stats/traits below. `sprites.gear(key)` renders each.

- [ ] **Step 1: Write the failing test**

```python
class TestMagicalArmourRoster(unittest.TestCase):
    def test_the_eleven_phase1_pieces_have_the_agreed_stats(self):
        from .items import ARMOURS
        # key: (tier, defense, speed_mod, trait)
        expected = {
            "thorn":      (4, 3, -5,  "thorns"),
            "silk":       (4, 2, 10,  "wraithsilk"),
            "venom":      (4, 3, -5,  "venom"),
            "cinder":     (4, 3, -5,  "cinder"),
            "glacial":    (4, 3, -5,  "glacial"),
            "lifeweave":  (4, 3, -5,  "lifeweave"),
            "bastion":    (5, 4, -15, "bastion"),
            "lastbreath": (5, 4, -10, "lastbreath"),
            "blinding":   (5, 3, -5,  "blinding"),
            "stonegolem": (5, 5, 0,   None),
            "hades":      (5, 3, 0,   "hades"),
        }
        for key, (tier, defense, spd, trait) in expected.items():
            a = ARMOURS[key]
            self.assertEqual((a.tier, a.defense, a.speed_mod, a.trait),
                             (tier, defense, spd, trait), key)

    def test_magical_armour_sprites_render(self):
        from . import sprites
        for key in ("thorn", "silk", "venom", "cinder", "glacial", "lifeweave",
                    "bastion", "lastbreath", "blinding", "stonegolem", "hades"):
            self.assertIsNotNone(sprites.gear(key), key)
```

- [ ] **Step 2: Run to verify it fails**

Run: `py -3.13 -m deathward.tests`
Expected: FAIL — the keys aren't in `ARMOURS`.

- [ ] **Step 3: Add the roster entries** (`deathward/items.py`, inside `ARMOURS`, after the `plate` rung)

```python
    # --- magical (floors 8+): found unenhanced, DWEN-enchantable. Each a survival
    # identity, not a bigger number. thorn + silk return from the graduated ordinary
    # pieces. Reactive pieces trigger on being struck, gated by player.armour_cd.
    "thorn":   Armour("thorn", "Thorned Cuirass", 4, 3, -5, "thorns",
                      "returns 2 damage to anything that hits you"),
    "silk":    Armour("silk", "Wraithsilk", 4, 2, 10, "wraithsilk",
                      "a wraith's touch cannot find you -- light, fast, ethereal"),
    "venom":   Armour("venom", "Venomweave", 4, 3, -5, "venom",
                      "an attacker is envenomed"),
    "cinder":  Armour("cinder", "Cinderplate", 4, 3, -5, "cinder",
                      "an attacker is set alight"),
    "glacial": Armour("glacial", "Glacial Mail", 4, 3, -5, "glacial",
                      "an attacker freezes solid"),
    "lifeweave": Armour("lifeweave", "Lifeweaver", 4, 3, -5, "lifeweave",
                        "it knits your wounds, turn after turn"),
    "bastion": Armour("bastion", "Bastion", 5, 4, -15, "bastion",
                      "no single blow lands harder than it allows"),
    "lastbreath": Armour("lastbreath", "Last Breath", 5, 4, -10, "lastbreath",
                         "the first killing blow is refused, once"),
    "blinding": Armour("blinding", "Blinding Light", 5, 3, -5, "blinding",
                       "struck, it flares -- everything near you reels"),
    "stonegolem": Armour("stonegolem", "Stone Golem's Chest", 5, 5, 0, None,
                         "heavy as stone, yet it never slows you"),
    "hades":   Armour("hades", "Robe of Hades", 5, 3, 0, "hades",
                      "struck, it answers in fire that will not touch you"),
```

- [ ] **Step 4: Add a sprite per piece** (`deathward/sprites.py`, in `gear()`)

`thorn` and `silk` branches already exist (Plan A left them dormant) — keep them; they render the graduated pieces. For the nine new keys, add a branch each after the existing armour branches, using the existing `cuirass(base, edge)` helper with a distinct colour + motif so the sprite test's presence check passes and each reads distinctly on screen. Recipe per piece (follow the pattern of the `mail`/`plate` branches):

```python
    elif key == "venom":                    # sickly green
        cuirass((92, 150, 96), (54, 96, 60))
    elif key == "cinder":                   # ember red-orange
        cuirass((176, 84, 56), (110, 48, 34))
    elif key == "glacial":                  # pale ice blue
        cuirass((150, 196, 226), (96, 140, 178))
    elif key == "lifeweave":                # living green-gold
        cuirass((120, 168, 96), (78, 120, 62))
    elif key == "bastion":                  # heavy dark steel
        cuirass((96, 104, 118), (56, 62, 74))
    elif key == "lastbreath":               # ashen white
        cuirass((210, 214, 220), (150, 156, 168))
    elif key == "blinding":                 # radiant gold-white
        cuirass((236, 224, 150), (196, 176, 96))
    elif key == "stonegolem":               # grey stone
        cuirass((140, 134, 124), (92, 86, 78))
    elif key == "hades":                    # dark robe, ember trim
        cuirass((70, 54, 66), (150, 70, 50))
```

> If `cuirass` isn't in scope for `gear()` the same way it is for the `mail`/`plate` branches you added in Plan A, mirror whatever those branches call. The presence test only requires a non-None surface; the colours are for legibility and are tunable.

- [ ] **Step 5: Run to verify it passes**

Run: `py -3.13 -m deathward.tests`
Expected: PASS. If `gear_catalog`/`top_tier_gear` tests trip on the larger `ARMOURS`, update them to the new reality the same way Plan A did (they recompute from the table, so they should hold).

- [ ] **Step 6: Commit**

```bash
git add deathward/items.py deathward/sprites.py deathward/tests.py
git commit -m "Magical armour roster: 11 Phase-1 pieces + sprites (thorn/silk re-homed)"
```

---

### Task 3: Re-homed traits — thorns + wraithsilk

Both reuse dormant hooks that key off `armour.trait`; Task 2 gave the pieces those traits, so this task confirms they fire and locks it with tests.

**Files:**
- Verify: `deathward/world.py:816` (thorns), `deathward/monsters.py:603` (wraithsilk) — no code change expected
- Test: `deathward/tests.py`

**Interfaces:** consumes `ARMOURS["thorn"]`/`["silk"]` (Task 2).

- [ ] **Step 1: Write the failing/GREEN test** (thorns already active for the equipped piece; wraithsilk likewise — these confirm the re-homed pieces work)

```python
class TestRehomedArmourTraits(unittest.TestCase):
    def test_thorned_cuirass_returns_damage(self):
        from .items import ALL_GEAR
        from .monsters import Monster
        codex = FakeSave()
        w = World(codex, seed=6)
        w.player.armour = ALL_GEAR["thorn"].copy()
        m = Monster("kobold", w.player.x + 1, w.player.y)
        w.level.monsters = [m]
        before = m.hp
        w.monster_attacks_player(m, 3)
        self.assertLess(m.hp, before, "thorns must bite an attacker back")

    def test_wraithsilk_negates_a_wraith_touch(self):
        from .items import ALL_GEAR
        from .monsters import Monster
        codex = FakeSave()
        w = World(codex, seed=6)
        w.player.armour = ALL_GEAR["silk"].copy()
        m = Monster("wraith", w.player.x + 1, w.player.y)
        w.level.monsters = [m]
        hp = w.player.hp
        m._ai_wraith(w, w.player)          # the adjacency-touch path
        self.assertEqual(w.player.hp, hp, "wraithsilk must eat the wraith's touch")
```

- [ ] **Step 2: Run**

Run: `py -3.13 -m deathward.tests`
Expected: PASS (the hooks already read `armour.trait`; Task 2 supplied the traits). If either fails, the dormant branch was removed/altered — restore it to read `p.armour.trait == "thorns"` / `"wraithsilk"`.

- [ ] **Step 3: Commit**

```bash
git add deathward/tests.py
git commit -m "Confirm re-homed thorns + wraithsilk fire on their magical pieces"
```

---

### Task 4: Retaliation trio — Venomweave / Cinderplate / Glacial Mail

On being struck, if the armour's cooldown is ready, afflict the attacker with the matching status, then start the recharge.

**Files:**
- Modify: `deathward/world.py` (`monster_attacks_player`, after the thorns block ~816–821)
- Test: `deathward/tests.py`

**Interfaces:**
- Consumes: `player.armour_cd` (Task 1), the config recharges/durations (Task 1), `ARMOURS` traits (Task 2).
- Produces: the reactive on-struck dispatch block (also the anchor for Tasks 7's Blinding/Robe).

- [ ] **Step 1: Write the failing test**

```python
class TestRetaliationArmour(unittest.TestCase):
    def _hit(self, key):
        from .items import ALL_GEAR
        from .monsters import Monster
        codex = FakeSave()
        w = World(codex, seed=6)
        w.player.armour = ALL_GEAR[key].copy()
        m = Monster("kobold", w.player.x + 1, w.player.y)
        w.level.monsters = [m]
        w.monster_attacks_player(m, 3)
        return w, m

    def test_cinderplate_burns_the_attacker_then_recharges(self):
        from . import config
        w, m = self._hit("cinder")
        self.assertEqual(m.burning, config.CINDER_BURN_TURNS)
        self.assertEqual(w.player.armour_cd, config.ARMOUR_RETAL_RECHARGE)

    def test_venomweave_poisons_the_attacker(self):
        from . import config
        w, m = self._hit("venom")
        self.assertEqual(m.poisoned, config.VENOM_POISON_TURNS)

    def test_glacial_mail_freezes_the_attacker(self):
        from . import config
        w, m = self._hit("glacial")
        self.assertEqual(m.stunned, config.FREEZE_TURNS)

    def test_it_does_not_fire_again_while_recharging(self):
        from .monsters import Monster
        w, m = self._hit("cinder")
        m.burning = 0                       # clear the mark; cooldown is now > 0
        w.monster_attacks_player(m, 3)
        self.assertEqual(m.burning, 0, "must not re-trigger mid-recharge")
```

- [ ] **Step 2: Run to verify it fails**

Run: `py -3.13 -m deathward.tests`
Expected: FAIL — no reactive dispatch yet.

- [ ] **Step 3: Add the reactive dispatch** (`deathward/world.py`, in `monster_attacks_player`, immediately after the thorns block near line 821)

```python
        # Reactive magical armour: on being struck (raw > 0), if the piece's cooldown
        # is ready, it answers, then recharges. One armour is worn, so one cooldown.
        if raw > 0 and p.armour_cd == 0 and m.alive:
            t = p.armour.trait
            if t == "cinder":
                m.burning = max(m.burning, config.CINDER_BURN_TURNS)
                self.log("Your armour flares -- the %s catches fire." % self._mname(m),
                         (255, 150, 80))
                self.add_fx("burning", m.x, m.y, life=0.7, tiles=[(m.x, m.y)])
                p.armour_cd = config.ARMOUR_RETAL_RECHARGE
            elif t == "venom":
                m.poisoned = max(m.poisoned, config.VENOM_POISON_TURNS)
                self.log("Your armour weeps venom -- the %s is envenomed."
                         % self._mname(m), (150, 220, 130))
                self.add_fx("impact", m.x, m.y, color=(150, 220, 130), radius=0.9, life=0.4)
                p.armour_cd = config.ARMOUR_RETAL_RECHARGE
            elif t == "glacial":
                m.stunned = max(m.stunned, config.FREEZE_TURNS)
                self.log("Your armour rimes over -- the %s freezes solid."
                         % self._mname(m), (150, 210, 255))
                self.add_fx("freeze", m.x, m.y, color=(150, 210, 255), life=0.5)
                p.armour_cd = config.ARMOUR_RETAL_RECHARGE
```

- [ ] **Step 4: Run to verify it passes**

Run: `py -3.13 -m deathward.tests`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deathward/world.py deathward/tests.py
git commit -m "Retaliation armour: Venomweave/Cinderplate/Glacial Mail afflict attackers"
```

---

### Task 5: Bastion (hit-cap) + Lifeweaver (regen)

Two small passives at two sites: clamp incoming damage; heal each turn.

**Files:**
- Modify: `deathward/world.py` (`monster_attacks_player`, the damage line ~788)
- Modify: `deathward/player.py` (`tick_effects`)
- Test: `deathward/tests.py`

**Interfaces:** consumes `config.BASTION_CAP`, `config.LIFEWEAVE_HEAL`, `ARMOURS` traits.

- [ ] **Step 1: Write the failing test**

```python
class TestBastionAndLifeweaver(unittest.TestCase):
    def test_bastion_caps_a_big_hit(self):
        from .items import ALL_GEAR
        from .monsters import Monster
        from . import config
        codex = FakeSave()
        w = World(codex, seed=6)
        w.player.armour = ALL_GEAR["bastion"].copy()
        m = Monster("brute", w.player.x + 1, w.player.y)
        w.level.monsters = [m]
        hp = w.player.hp
        w.monster_attacks_player(m, 40)     # a huge hit
        lost = hp - w.player.hp
        self.assertLessEqual(lost, config.BASTION_CAP,
                             "no single hit may exceed Bastion's cap")

    def test_lifeweaver_knits_hp_each_turn(self):
        from .items import ALL_GEAR
        from . import config
        codex = FakeSave()
        w = World(codex, seed=6)
        w.player.armour = ALL_GEAR["lifeweave"].copy()
        w.player.hp = w.player.max_hp - 5
        w.player.tick_effects(w)
        self.assertEqual(w.player.hp, w.player.max_hp - 5 + config.LIFEWEAVE_HEAL)

    def test_lifeweaver_never_overheals(self):
        from .items import ALL_GEAR
        codex = FakeSave()
        w = World(codex, seed=6)
        w.player.armour = ALL_GEAR["lifeweave"].copy()
        w.player.hp = w.player.max_hp
        w.player.tick_effects(w)
        self.assertEqual(w.player.hp, w.player.max_hp)
```

- [ ] **Step 2: Run to verify it fails**

Run: `py -3.13 -m deathward.tests`
Expected: FAIL.

- [ ] **Step 3: Bastion** (`deathward/world.py`, `monster_attacks_player`, right after `dmg = max(0, dmg - p.defense)` at ~788)

```python
        if not ignore_armour:
            dmg = max(0, dmg - p.defense)
            if p.armour.trait == "bastion":
                dmg = min(dmg, config.BASTION_CAP)
```

- [ ] **Step 4: Lifeweaver** (`deathward/player.py`, in `tick_effects`, near the regen-potion block ~200)

```python
        if self.armour.trait == "lifeweave" and self.hp < self.max_hp:
            self.heal(config.LIFEWEAVE_HEAL)
```

> Confirm `player.py` imports `config` (it does — `tick_effects` already references `config.DIM`). Confirm `self.heal(n)` clamps to `max_hp` (the regen potion uses it the same way at line 202).

- [ ] **Step 5: Run to verify it passes**

Run: `py -3.13 -m deathward.tests`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add deathward/world.py deathward/player.py deathward/tests.py
git commit -m "Bastion caps a single hit; Lifeweaver knits 2 hp per turn"
```

---

### Task 6: Last Breath — refuse one killing blow

Mirror the phoenix death-refusal, plus a 1-turn untouchable window.

**Files:**
- Modify: `deathward/world.py` (`kill_player`, ~849–861, beside the phoenix block)
- Test: `deathward/tests.py`

**Interfaces:** consumes `player.lastbreath_used` (Task 1), `config.LASTBREATH_SANCTUARY`, `p.sanctuary` (existing).

- [ ] **Step 1: Write the failing test**

```python
class TestLastBreath(unittest.TestCase):
    def test_it_refuses_the_first_killing_blow_and_grants_a_window(self):
        from .items import ALL_GEAR
        from . import config
        codex = FakeSave()
        w = World(codex, seed=6)
        w.player.armour = ALL_GEAR["lastbreath"].copy()
        w.kill_player("brute")
        self.assertFalse(w.dead, "Last Breath must refuse the first killing blow")
        self.assertEqual(w.player.hp, 1)
        self.assertTrue(w.player.lastbreath_used)
        self.assertGreaterEqual(w.player.sanctuary, config.LASTBREATH_SANCTUARY)

    def test_it_only_works_once_per_life(self):
        from .items import ALL_GEAR
        codex = FakeSave()
        w = World(codex, seed=6)
        w.player.armour = ALL_GEAR["lastbreath"].copy()
        w.player.lastbreath_used = True         # already spent
        w.kill_player("brute")
        self.assertTrue(w.dead, "a spent Last Breath cannot save you again")
```

- [ ] **Step 2: Run to verify it fails**

Run: `py -3.13 -m deathward.tests`
Expected: FAIL.

- [ ] **Step 3: Implement** (`deathward/world.py`, in `kill_player`, immediately after the `if p.phoenix:` block so it is checked before `self.dead = True`)

```python
        if p.armour.trait == "lastbreath" and not p.lastbreath_used:
            p.lastbreath_used = True
            p.hp = 1
            p.poison = p.frozen = p.confused = p.weak = 0
            p.sanctuary = max(p.sanctuary, config.LASTBREATH_SANCTUARY)
            self.log("Your armour draws one last breath for you. Not yet.", config.GOLD)
            self.add_fx("flash", color=(230, 234, 240), life=0.6)
            self.add_fx("pulse", p.x, p.y, color=(230, 234, 240), life=0.8)
            self.shake(7)
            return
```

- [ ] **Step 4: Run to verify it passes**

Run: `py -3.13 -m deathward.tests`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deathward/world.py deathward/tests.py
git commit -m "Last Breath: refuse one killing blow per life + a 1-turn untouchable window"
```

---

### Task 7: Blinding Light + Robe of Hades + the Firestorm-scroll fix

The two reactive-AoE capstones, plus factoring the fire into one caster-sparing routine that VORN and the Robe share.

**Files:**
- Modify: `deathward/world.py` (add `_firestorm`; the reactive dispatch in `monster_attacks_player`; the VORN `effect == "fire"` branch ~1655–1670)
- Test: `deathward/tests.py`

**Interfaces:** consumes the reactive dispatch (Task 4), `config.ARMOUR_CAPSTONE_RECHARGE`, `config.BLINDING_RADIUS`, `config.BLINDING_STUN_TURNS`.

- [ ] **Step 1: Write the failing test**

```python
class TestArmourCapstones(unittest.TestCase):
    def test_firestorm_scroll_no_longer_burns_the_caster(self):
        from .monsters import Monster
        codex = FakeSave()
        w = World(codex, seed=6)
        w.level.monsters = [Monster("kobold", w.player.x + 1, w.player.y)]
        hp = w.player.hp
        w._apply_effect("fire")
        self.assertEqual(w.player.hp, hp, "VORN must not cook its own caster")

    def test_robe_of_hades_burns_the_room_and_spares_you(self):
        from .items import ALL_GEAR
        from .monsters import Monster
        from . import config
        codex = FakeSave()
        w = World(codex, seed=6)
        w.player.armour = ALL_GEAR["hades"].copy()
        m = Monster("kobold", w.player.x + 1, w.player.y)
        w.level.monsters = [m]
        hp, mhp = w.player.hp, m.hp
        w.monster_attacks_player(m, 3)
        self.assertLess(m.hp, mhp, "the Robe answers in fire")
        self.assertEqual(w.player.hp, hp + 0, "the Robe's fire spares the wearer "
                         "(barring the incoming hit already applied)")
        self.assertEqual(w.player.armour_cd, config.ARMOUR_CAPSTONE_RECHARGE)

    def test_blinding_light_stuns_the_ring_and_wipes_windups(self):
        from .items import ALL_GEAR
        from .monsters import Monster
        from . import config
        codex = FakeSave()
        w = World(codex, seed=6)
        w.player.armour = ALL_GEAR["blinding"].copy()
        near = Monster("kobold", w.player.x + 1, w.player.y)
        near.intent = ("smash", w.player.x, w.player.y)
        w.level.monsters = [near]
        w.monster_attacks_player(near, 3)
        self.assertEqual(near.stunned, config.BLINDING_STUN_TURNS)
        self.assertIsNone(near.intent, "a wiped windup")
```

> Note: in `test_robe...`, `monster_attacks_player(m, 3)` applies the incoming hit first (reducing `w.player.hp` by the post-armour amount) and *then* fires the Robe. Assert the Robe adds no *further* self-damage by comparing player hp before/after against only the incoming hit — simplest is to give the player armour that fully absorbs 3 (e.g. leave default) or assert `m.hp` dropped and the player took no *fire*. Adjust the exact hp assertion to the incoming-hit reality when you implement; the load-bearing checks are `m.hp` fell and `armour_cd` was set.

- [ ] **Step 2: Run to verify it fails**

Run: `py -3.13 -m deathward.tests`
Expected: FAIL — VORN still self-burns; no Robe/Blinding dispatch.

- [ ] **Step 3: Add the shared firestorm helper** (`deathward/world.py`, near the combat helpers)

```python
    def _firestorm(self):
        """Fire through everything visible; the CASTER/WEARER is spared. Shared by the
        VORN scroll and the Robe of Hades. Damage draws the world RNG (deterministic)."""
        hit = [m for m in list(self.level.monsters) if self.visible(m.x, m.y)]
        self.add_fx("flash", color=(255, 150, 70), life=0.55)
        self.add_fx("burning", life=1.1, tiles=self.visible_floor())
        for m in hit:
            self.add_fx("burst", m.x, m.y, radius=0.6, color=(255, 170, 70), life=0.6)
            self.hurt_monster(m, self.rng.randint(8, 14), source="scroll")
        return len(hit)
```

- [ ] **Step 4: Point VORN at the helper** (`deathward/world.py`, `effect == "fire"` branch)

Replace the body of the `elif effect == "fire":` branch with:

```python
        elif effect == "fire":
            self.log("Fire roars through everything you can see.", (255, 140, 70))
            self.shake(10)
            self._firestorm()
```

(The old branch's per-monster loop and the `hurt_player(2–5, "glyph")` self-burn are removed — the helper does the damage and spares the caster.)

- [ ] **Step 5: Add the Robe + Blinding dispatch** (`deathward/world.py`, in `monster_attacks_player`, appended to the reactive block from Task 4 — same `if raw > 0 and p.armour_cd == 0` gate)

```python
            elif t == "blinding":
                for mm in self.level.monsters:
                    if mm.alive and mm.dist(p.x, p.y) <= config.BLINDING_RADIUS:
                        mm.stunned = max(mm.stunned, config.BLINDING_STUN_TURNS)
                        mm.intent = None
                self.log("Your armour ERUPTS with light. Everything near you reels.",
                         config.GOLD)
                self.add_fx("flash", color=(255, 250, 210), life=0.5)
                p.armour_cd = config.ARMOUR_CAPSTONE_RECHARGE
            elif t == "hades":
                self.log("Struck, your robe answers in fire.", (255, 140, 70))
                self._firestorm()
                p.armour_cd = config.ARMOUR_CAPSTONE_RECHARGE
```

- [ ] **Step 6: Run to verify it passes**

Run: `py -3.13 -m deathward.tests`
Expected: PASS. Update any existing VORN test that asserted the old self-burn (grep `test.*fire`/`glyph` in the firestorm area) to the new "spares the caster" reality — do not weaken a real assertion, adapt it.

- [ ] **Step 7: Commit**

```bash
git add deathward/world.py deathward/tests.py
git commit -m "Blinding Light + Robe of Hades; Firestorm scroll no longer burns its caster"
```

---

### Task 8: Distribution — magical armour on floors 8+

Place magical armour like magical boots/weapons: a rare generation-placed slot on floors 8+, one-per-game unique, drawn only from run history.

**Files:**
- Modify: `deathward/items.py` (`FINDABLE_MAGICAL_ARMOUR` + `FINDABLE_MAGICAL_ARMOUR_KEYS` + `is_magical_armour` + `roll_floor_armour_magical`, near the boots equivalents ~435–463)
- Modify: `deathward/dungeon.py` (a magical-armour placement loop, mirroring the magical-boot loop ~620–629)
- Test: `deathward/tests.py`

**Interfaces:**
- Produces: `roll_floor_armour_magical(rng, depth, exclude=()) -> key|None` (draws only `(rng, depth, exclude)`); `is_magical_armour(key)`.

- [ ] **Step 1: Write the failing test**

```python
class TestMagicalArmourDistribution(unittest.TestCase):
    def test_never_before_floor_eight(self):
        import random
        from .items import roll_floor_armour_magical
        for depth in (1, 5, 7):
            for s in range(60):
                self.assertIsNone(roll_floor_armour_magical(random.Random(s), depth))

    def test_only_phase1_findable_keys_appear(self):
        import random
        from .items import roll_floor_armour_magical, FINDABLE_MAGICAL_ARMOUR_KEYS
        seen = set()
        for depth in range(8, 21):
            for s in range(400):
                k = roll_floor_armour_magical(random.Random(s), depth)
                if k:
                    seen.add(k)
        self.assertTrue(seen <= FINDABLE_MAGICAL_ARMOUR_KEYS)
        # boss-reserved / Phase-2 pieces never drop
        for boss in ("shade", "nightcloak", "fade"):
            self.assertNotIn(boss, seen)

    def test_uniqueness_via_exclude_and_determinism(self):
        import random
        from .items import roll_floor_armour_magical
        for s in range(50):
            self.assertEqual(roll_floor_armour_magical(random.Random(s), 12),
                             roll_floor_armour_magical(random.Random(s), 12))
        # excluding the whole pool yields nothing
        from .items import FINDABLE_MAGICAL_ARMOUR_KEYS
        got = [roll_floor_armour_magical(random.Random(s), 12,
               exclude=FINDABLE_MAGICAL_ARMOUR_KEYS) for s in range(200)]
        self.assertTrue(all(g is None for g in got))
```

- [ ] **Step 2: Run to verify it fails**

Run: `py -3.13 -m deathward.tests`
Expected: FAIL — `roll_floor_armour_magical` undefined.

- [ ] **Step 3: Implement** (`deathward/items.py`, mirroring `FINDABLE_MAGICAL_BOOTS`/`roll_floor_boots_magical`)

```python
# The magical armour a floor can DROP. Phase 1 excludes the invisibility/wall-walk
# pieces (fade -> Phase 2; shade/nightcloak -> boss-reserved, like Windfang/Void).
FINDABLE_MAGICAL_ARMOUR = {
    4: ["thorn", "silk", "venom", "cinder", "glacial", "lifeweave"],
    5: ["bastion", "lastbreath", "blinding", "stonegolem", "hades"],
}
FINDABLE_MAGICAL_ARMOUR_KEYS = (set(FINDABLE_MAGICAL_ARMOUR[4])
                                | set(FINDABLE_MAGICAL_ARMOUR[5]))


def is_magical_armour(key):
    """A magical armour (tier 4 or 5). Single source of truth for the armour ledger."""
    return key in ARMOURS and ARMOURS[key].tier >= 4


def roll_floor_armour_magical(rng, depth, exclude=()):
    """The rare magical-armour slot for floors 8-20: at most one per floor, one-per-game
    unique. Draws only from (rng, depth, exclude) -- never the Kodex -- so blind and
    omniscient runs stay bit-identical. Returns an armour key, or None."""
    if depth < 8:
        return None
    present = 0.14 if depth <= 11 else 0.12 if depth <= 15 else 0.10
    if rng.random() >= present:
        return None
    t5_share = 0.20 if depth <= 11 else 0.40 if depth <= 15 else 0.65
    tier = 5 if rng.random() < t5_share else 4
    pool = [k for k in FINDABLE_MAGICAL_ARMOUR[tier] if k not in exclude]
    if not pool:
        return None
    return rng.choice(pool)
```

- [ ] **Step 4: Place it at generation** (`deathward/dungeon.py`, after the magical-boot loop ~629, mirroring it)

First extend the `.items` import to add `is_magical_armour, roll_floor_armour_magical`. Then:

```python
        # THE FLOOR'S MAGICAL ARMOUR (floors 8+). The rare slot, like the magical boots:
        # scarce, one-per-game unique, generation-placed. Boss-reserved pieces are excluded.
        makey = roll_floor_armour_magical(rng, d, exclude=codex.armour_generated)
        if makey:
            spot = self._free_tile(avoid_start=True)
            if spot:
                self.drops.append(Drop(spot[0], spot[1], "gear", makey))
                codex.record_magical_armour_placed(makey, d, spot[0], spot[1])
```

> This needs a `codex.armour_generated` ledger + `record_magical_armour_placed` mirroring `boots_generated`/`record_magical_boot_placed`. If those don't yet exist, add them to `codex.py` the same way the boots ones were added (a list initialised in `__init__`/`_save_dict`/`_load_from`/`new_dungeon`, appended on placement) — this is the minimal uniqueness ledger, NOT the full economy (persistence/collection is Plan C). Keep it draw-free of the Kodex during the *roll* (only `exclude` is passed in), preserving determinism.

- [ ] **Step 5: Run to verify it passes**

Run: `py -3.13 -m deathward.tests`
Expected: PASS, `TestKnowledgeIsNotPower` green (the roll reads only `rng`/`depth`/`exclude`).

- [ ] **Step 6: Commit**

```bash
git add deathward/items.py deathward/dungeon.py deathward/codex.py deathward/tests.py
git commit -m "Magical armour distribution: rare floor-8+ slot, one-per-game unique"
```

---

### Task 9: Integration + determinism sweep

End-to-end through a real `World`, and confirm the invariant.

**Files:**
- Test: `deathward/tests.py`

- [ ] **Step 1: Write the integration test**

```python
class TestMagicalArmourEndToEnd(unittest.TestCase):
    def test_a_found_magical_armour_equips_and_its_trait_fires(self):
        from .items import ALL_GEAR
        from .dungeon import Drop
        from .monsters import Monster
        from . import config
        codex = FakeSave()
        w = World(codex, seed=6)
        p = w.player
        w.level.drops.append(Drop(p.x, p.y, "gear", "cinder"))
        p.armour = ALL_GEAR["rags"].copy()          # swap is an upgrade over the starter
        w.take_all()
        self.assertEqual(p.armour.key, "cinder")
        m = Monster("kobold", p.x + 1, p.y)
        w.level.monsters = [m]
        w.monster_attacks_player(m, 3)
        self.assertEqual(m.burning, config.CINDER_BURN_TURNS)
```

- [ ] **Step 2: Run the integration test + full determinism sweep**

Run: `py -3.13 -m deathward.tests`
Expected: PASS, including `TestKnowledgeIsNotPower::test_blind_and_omniscient_dungeons_are_identical`. Confirm the total test count rose and nothing is unexpectedly skipped (one known pre-existing conditional skip is fine).

- [ ] **Step 3: Commit**

```bash
git add deathward/tests.py
git commit -m "Magical armour Phase 1: end-to-end integration + determinism sweep"
```

---

## Self-Review

**Spec coverage (Phase 1 of the roster spec):**
- Reactive infra (one cooldown, last-stand flag) → Task 1. ✓
- Roster table (11 pieces) + sprites → Task 2. ✓
- Re-homed thorns + wraithsilk → Task 3. ✓
- Retaliation trio (monster status reuse + recharge) → Task 4. ✓
- Bastion cap + Lifeweaver regen → Task 5. ✓
- Last Breath (phoenix pattern + sanctuary window) → Task 6. ✓
- Blinding Light + Robe of Hades + Firestorm self-burn fix (shared `_firestorm`) → Task 7. ✓
- Distribution (FINDABLE_MAGICAL_ARMOUR + roll + placement + uniqueness ledger) → Task 8. ✓
- Determinism invariant → Tasks 4/8 tests + Task 9 sweep. ✓
- Stone Golem's Chest (pure stat) → Task 2 table entry (no mechanic). ✓

**Placeholder scan:** no TBD/TODO; every code step shows complete code. Three steps carry explicit *verification* notes (sprite helper scope, `heal` clamp, the Robe hp assertion, the codex ledger) with the fallback action stated — real checks, not placeholders.

**Type consistency:** `armour_cd`/`lastbreath_used` defined in Task 1, consumed by Tasks 4–7; `_firestorm()` defined in Task 7 Step 3 and called by both VORN (Step 4) and the Robe (Step 5); `roll_floor_armour_magical`/`is_magical_armour` defined in Task 8 and used in the dungeon loop; the reactive dispatch block from Task 4 is extended (not duplicated) in Task 7.

**Known risk flagged for the implementer:** Task 8's codex uniqueness ledger (`armour_generated`/`record_magical_armour_placed`) mirrors the boots ledger; if the boots pattern differs from what's described, follow the actual boots code in `codex.py` — the load-bearing requirement is only that the *roll* stays Kodex-free for determinism.
