# Magical Boots — Phase 1 (Roster + Reused-Mechanic Boots) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rework the magical boots roster's non-stealth half — rename Swift, and add six new boots (Featherfall, Thor's, Slipstep, Emberstride, Rimewalkers, Phantom) whose mechanics reuse existing engine systems — each with a sprite.

**Architecture:** Each boot is a `BOOTS` entry with a `trait` string; the mechanic is wired at the one engine hook that owns it (traps trigger, the attack resolution, the player-damage path, the freeze function). Parameters (dodge %, Slipstep cadence) are `config` constants, so `Boots` needs no new fields this phase. Every new boot gets a distinct sprite in `_boots_sprite`.

**Tech Stack:** Python 3 standard library, `pygame`, `unittest` (`deathward/tests.py`).

## Global Constraints

- **No new dependencies.** Standard library + existing `pygame`.
- **Determinism:** any combat RNG draws from `world.rng` only, never the Kodex. The blind-vs-omniscient bit-identical invariant (`TestKnowledgeIsNotPower`, tests.py:323) must stay green.
- **Do not touch the GPL header** in any file.
- **Scope fence:** only the magical boots named here. Do NOT implement the **stealth** boots (Padded Soles redefinition + Whisperstep) — that is Phase 2. Leave `soft` (Padded Soles) exactly as it is today (softsole). Do not touch weapons, armour, ordinary boots, or the magical-boot *distribution*.
- **Boot keys/tiers:** new boots — `featherfall`(T5), `thor`(T5), `slipstep`(T5), `emberstride`(T4), `rimewalkers`(T4), `phantom`(T4). `swift` stays T4 (rename only).
- **Every gear key needs a distinct, non-blank sprite** or `test_every_piece_of_gear_has_its_own_sprite` fails — so each new boot is added together with its sprite in the same task.
- **Running tests — use `py -3.13`, NOT `python`** (plain `python`/`py` are 3.14 without pygame). Whole suite: `py -3.13 -m deathward.tests` (baseline: 492 green). One test: `py -3.13 -m deathward.tests <ClassName>.<test_method> -v`.

## Shared references (for every task)

- `BOOTS` table: `deathward/items.py:171-188`. The magical boots are the entries after the ordinary ones. `Boots(key, name, tier, speed, trait=None, note="", defense=0)`.
- `_boots_sprite(key, s, S)`: `deathward/sprites.py:1146`, an `if/elif key == ...` chain ending before `_GEAR_DRAW`. It has a local `boot(col, sole=None)` helper and module primitives `_poly`, `_line`, `_circ`, `_shade` (and `math`, `pygame`).
- Put new tests in a new `TestMagicalBoots(unittest.TestCase)` class at the END of `deathward/tests.py`, before `if __name__ == "__main__":`. `World(FakeSave(), seed=N)`, `BOOTS[...]`, and `from .monsters import Monster` are the standard fixtures.

---

### Task 1: Rename Swift Boots → Sandals of Mercury

**Files:**
- Modify: `deathward/items.py:180` (the `swift` entry's name)
- Test: `deathward/tests.py` (new `TestMagicalBoots` class)

**Interfaces:**
- Produces: `BOOTS["swift"].name == "Sandals of Mercury"` (key, tier 4, speed +25 unchanged).

- [ ] **Step 1: Write the failing test**

Add this new class at the end of `deathward/tests.py`, before `if __name__ == "__main__":`:

```python
class TestMagicalBoots(unittest.TestCase):
    def test_swift_is_renamed_sandals_of_mercury(self):
        from .items import BOOTS
        b = BOOTS["swift"]
        self.assertEqual(b.name, "Sandals of Mercury")
        self.assertEqual((b.tier, b.speed), (4, 25), "stats unchanged, rename only")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `py -3.13 -m deathward.tests TestMagicalBoots.test_swift_is_renamed_sandals_of_mercury -v`
Expected: FAIL — name is still "Swift Boots".

- [ ] **Step 3: Rename**

In `deathward/items.py:180`, change the `swift` entry:

```python
    "swift":    Boots("swift", "Sandals of Mercury", 4, 25),
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `py -3.13 -m deathward.tests TestMagicalBoots.test_swift_is_renamed_sandals_of_mercury -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deathward/items.py deathward/tests.py
git commit -m "Rename Swift Boots to Sandals of Mercury"
```

---

### Task 2: Featherfall — triggers no trap

**Files:**
- Modify: `deathward/items.py` (`BOOTS`: add `featherfall`), `deathward/sprites.py` (`_boots_sprite`), `deathward/traps.py:65-78` (`Trap.trigger`)
- Test: `deathward/tests.py` (`TestMagicalBoots`)

**Interfaces:**
- Produces: `BOOTS["featherfall"]` (T5, +25, trait `"featherfall"`). While worn, `Trap.trigger` on the player returns without firing for **any** trap key.

- [ ] **Step 1: Write the failing test**

Add to `TestMagicalBoots`:

```python
    def test_featherfall_springs_no_trap_of_any_kind(self):
        from .items import BOOTS
        from .traps import Trap, TRAP_POOL
        w = World(FakeSave(), seed=5)
        w.level.monsters = []
        w.player.boots = BOOTS["featherfall"]
        for kind in set(TRAP_POOL):                 # dart, spike, gas, alarm, glyph
            hp = w.player.hp
            t = Trap(kind, w.player.x, w.player.y)
            t.trigger(w, w.player)
            self.assertEqual(w.player.hp, hp,
                             "featherfall must not spring the %s" % kind)
            self.assertFalse(t.sprung, "the %s should not go off" % kind)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `py -3.13 -m deathward.tests TestMagicalBoots.test_featherfall_springs_no_trap_of_any_kind -v`
Expected: FAIL — `KeyError: 'featherfall'` (the boot does not exist yet).

- [ ] **Step 3: Add the boot**

In `deathward/items.py`, add to the magical section of `BOOTS` (after `wind`):

```python
    "featherfall": Boots("featherfall", "Featherfall", 5, 25, "featherfall",
                         "you drift above the floor -- no trap can find your feet"),
```

- [ ] **Step 4: Add the sprite**

In `deathward/sprites.py`, add an `elif` branch inside `_boots_sprite` (after the `wind` branch):

```python
    elif key == "featherfall":              # pale sky-blue, floating feathers
        boot((150, 196, 236), (96, 140, 190))
        for i in range(3):                  # feathers rising off the heel
            y = S * (0.30 + i * 0.06)
            _poly(s, (214, 234, 250), [(cx - S * 0.22, y), (cx - S * 0.40, y - S * 0.02),
                                       (cx - S * 0.20, y + S * 0.05)])
        _circ(s, (230, 244, 255), cx + S * 0.10, S * 0.30, S * 0.03)
```

- [ ] **Step 5: Skip all traps under Featherfall**

In `deathward/traps.py`, at the TOP of `Trap.trigger` (right after `is_player = victim is world.player`, before the `PRESSURE` block at line 68), add:

```python
        if is_player and world.player.boots.trait == "featherfall":
            world.log("You drift above the %s -- your feet never touch it." % self.name,
                      config.MANA)
            return
```

(This sits before the `self.key in PRESSURE` check, so it covers weight *and* magical traps. `config` is already imported in traps.py.)

- [ ] **Step 6: Run the tests to verify they pass**

Run: `py -3.13 -m deathward.tests TestMagicalBoots.test_featherfall_springs_no_trap_of_any_kind -v`
Expected: PASS. Then the full suite (the sprite-distinctness test must stay green):
Run: `py -3.13 -m deathward.tests`
Expected: green.

- [ ] **Step 7: Commit**

```bash
git add deathward/items.py deathward/sprites.py deathward/traps.py deathward/tests.py
git commit -m "Featherfall boots: drift above every trap (T5)"
```

---

### Task 3: Thor's Boots — knock back all adjacent enemies

**Files:**
- Modify: `deathward/items.py` (`BOOTS`), `deathward/sprites.py` (`_boots_sprite`), `deathward/world.py:571-572` (the kick block in the attack resolution)
- Test: `deathward/tests.py` (`TestMagicalBoots`)

**Interfaces:**
- Consumes: `_knockback(m)` (world.py:574, shoves one monster a tile away).
- Produces: `BOOTS["thor"]` (T5, +10, trait `"thor"`). On a player strike, every adjacent monster is knocked back.

- [ ] **Step 1: Write the failing test**

Add to `TestMagicalBoots`:

```python
    def test_thor_knocks_back_every_adjacent_enemy(self):
        from .items import BOOTS
        from .monsters import Monster
        from .dungeon import FLOOR
        w = World(FakeSave(), seed=7)
        w.level.monsters = []
        w.player.boots = BOOTS["thor"]
        px, py = w.player.x, w.player.y
        for dy in range(-2, 3):                        # carve open room to be shoved into
            for dx in range(-2, 3):
                w.level.grid[py + dy][px + dx] = FLOOR
        placed = []
        for (dx, dy) in ((1, 0), (0, 1), (1, 1)):
            m = Monster("rat", px + dx, py + dy)
            m.hp = m.max_hp = 999                       # they survive the blow, so they can be shoved
            w.level.monsters.append(m)
            placed.append(((px + dx, py + dy), m))
        w.player_attack(placed[0][1])                   # strike the eastern rat
        for orig, m in placed:
            self.assertNotEqual((m.x, m.y), orig,
                                "every adjacent enemy should be shoved, not just the target")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `py -3.13 -m deathward.tests TestMagicalBoots.test_thor_knocks_back_every_adjacent_enemy -v`
Expected: FAIL — `KeyError: 'thor'`.

- [ ] **Step 3: Add the boot**

In `deathward/items.py` magical `BOOTS`:

```python
    "thor":     Boots("thor", "Thor's Boots", 5, 10, "thor",
                      "every blow scatters all that stands near you"),
```

- [ ] **Step 4: Add the sprite**

In `deathward/sprites.py` `_boots_sprite`:

```python
    elif key == "thor":                     # storm-slate, a yellow bolt
        boot((86, 96, 120), (52, 60, 82))
        bolt = (250, 224, 90)
        _poly(s, bolt, [(cx - S * 0.02, S * 0.28), (cx - S * 0.14, S * 0.50),
                        (cx - S * 0.02, S * 0.48), (cx - S * 0.10, S * 0.68),
                        (cx + S * 0.12, S * 0.42), (cx + S * 0.00, S * 0.44)])
```

- [ ] **Step 5: Knock back all adjacent enemies**

In `deathward/world.py`, replace the kick block (lines 571-572):

```python
        if p.boots.trait == "kick" and m.alive:
            self._knockback(m)
        if p.boots.trait == "thor":
            for dx, dy in DIRS8:
                o = self.monster_at(p.x + dx, p.y + dy)
                if o and o.alive:
                    self._knockback(o)
```

(`DIRS8` is already used just above for cleave. `_knockback(o)` shoves each `o` directly away from the player; if the tile behind it is blocked it simply doesn't move — same rule as the single kick.)

- [ ] **Step 6: Run the tests to verify they pass**

Run: `py -3.13 -m deathward.tests TestMagicalBoots.test_thor_knocks_back_every_adjacent_enemy -v`
Expected: PASS. Then:
Run: `py -3.13 -m deathward.tests`
Expected: green.

- [ ] **Step 7: Commit**

```bash
git add deathward/items.py deathward/sprites.py deathward/world.py deathward/tests.py
git commit -m "Thor's Boots: each strike knocks back all adjacent enemies (T5)"
```

---

### Task 4: Slipstep — every 4th hit, blink away and stun the attacker

**Files:**
- Modify: `deathward/config.py` (constants), `deathward/player.py` (a hit counter field), `deathward/items.py` (`BOOTS`), `deathward/sprites.py` (`_boots_sprite`), `deathward/world.py:664-694` (`monster_attacks_player`)
- Test: `deathward/tests.py` (`TestMagicalBoots`)

**Interfaces:**
- Consumes: `blink_tile_near(cx, cy, lo, hi)` (world.py:373), `self.level.compute_fov(x, y)` (FOV refresh), `m.stunned`.
- Produces: `BOOTS["slipstep"]` (T5, +10, trait `"slipstep"`). `Player.slipstep_hits` counter. On the 4th damaging monster hit, the player relocates 2 tiles and the attacker is stunned 1 turn.

- [ ] **Step 1: Write the failing test**

Add to `TestMagicalBoots`:

```python
    def test_slipstep_blinks_and_stuns_on_the_fourth_hit(self):
        from .items import BOOTS, ARMOURS
        from .monsters import Monster
        from .dungeon import FLOOR
        w = World(FakeSave(), seed=9)
        w.level.monsters = []
        w.player.boots = BOOTS["slipstep"]
        w.player.armour = ARMOURS["rags"]              # 0 def: every blow lands in full
        w.player.hp = 50                               # survive four hits
        px, py = w.player.x, w.player.y
        for dy in range(-2, 3):                         # open room to blink into
            for dx in range(-2, 3):
                w.level.grid[py + dy][px + dx] = FLOOR
        m = Monster("rat", px + 1, py)                  # adjacent, not on the player
        w.level.monsters = [m]
        start = (px, py)
        for _ in range(3):                              # first three damaging hits: no blink
            w.monster_attacks_player(m, 3)
            self.assertEqual((w.player.x, w.player.y), start, "no blink before the 4th hit")
            self.assertEqual(m.stunned, 0, "no stun before the 4th hit")
        w.monster_attacks_player(m, 3)                  # the fourth hit: blink + stun
        self.assertNotEqual((w.player.x, w.player.y), start,
                            "the 4th hit blinks the player away")
        self.assertGreaterEqual(m.stunned, 1, "the 4th hit stuns the attacker")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `py -3.13 -m deathward.tests TestMagicalBoots.test_slipstep_blinks_and_stuns_on_the_fourth_hit -v`
Expected: FAIL — `KeyError: 'slipstep'`.

- [ ] **Step 3: Add config constants**

In `deathward/config.py`, near the other combat constants (after `FREEZE_TURNS`, line 116):

```python
SLIPSTEP_HIT_CADENCE = 4          # every Nth damaging hit taken triggers the escape
SLIPSTEP_BLINK_DIST  = 2          # chebyshev tiles the escape leaps
```

- [ ] **Step 4: Add the player counter**

In `deathward/player.py`, in `Player.__init__` beside the other status fields (near `self.frozen = 0`, line 76), add:

```python
        self.slipstep_hits = 0    # Slipstep boots: damaging hits taken, for the every-4th escape
```

- [ ] **Step 5: Add the boot**

In `deathward/items.py` magical `BOOTS`:

```python
    "slipstep": Boots("slipstep", "Slipstep", 5, 10, "slipstep",
                      "every fourth wound flings you clear and staggers the striker"),
```

- [ ] **Step 6: Add the sprite**

In `deathward/sprites.py` `_boots_sprite`:

```python
    elif key == "slipstep":                 # teal, with a motion afterimage
        boot((80, 180, 150), (48, 120, 100))
        ghost = (150, 226, 206)
        for i in range(3):                  # trailing streak behind the heel
            x = cx - S * (0.24 + i * 0.06)
            _line(s, ghost, (x, S * 0.40), (x, S * 0.70), S * 0.02)
```

- [ ] **Step 7: Wire the escape into the attack**

In `deathward/world.py` `monster_attacks_player`, replace the `else:` branch that lands a hit (the block that logs the hit and calls `self.hurt_player(dmg, m.key)`, lines ~681-688) so it appends the Slipstep reaction after the damage:

```python
        else:
            self.log("The %s %s you for %d.%s"
                     % (self._mname(m), verb, dmg,
                        "  (armour ignored)" if ignore_armour and p.defense else ""),
                     config.BLOOD)
            self.add_fx("impact", p.x, p.y, color=config.BLOOD,
                        radius=0.7 + min(0.8, dmg / 14.0), life=0.38)
            self.hurt_player(dmg, m.key)
            if p.boots.trait == "slipstep" and not self.dead:
                p.slipstep_hits += 1
                if p.slipstep_hits % config.SLIPSTEP_HIT_CADENCE == 0:
                    spot = self.blink_tile_near(p.x, p.y, config.SLIPSTEP_BLINK_DIST,
                                                config.SLIPSTEP_BLINK_DIST)
                    if spot:
                        p.x, p.y = spot
                        self.level.compute_fov(p.x, p.y)
                        self.log("Your boots wrench you clear!", config.MANA)
                        self.add_fx("freeze", p.x, p.y, color=(150, 226, 206), life=0.5)
                    if m.alive:
                        m.stunned = max(m.stunned, config.HAMMER_STUN_TURNS)
```

(The relocation deliberately does NOT re-enter the tile — it just moves and refreshes FOV, so a mid-combat reflex can't recursively spring a trap or open a loot menu. The random leap can still drop you into a worse spot — the intended wildcard.)

- [ ] **Step 8: Run the tests to verify they pass**

Run: `py -3.13 -m deathward.tests TestMagicalBoots.test_slipstep_blinks_and_stuns_on_the_fourth_hit -v`
Expected: PASS. Then:
Run: `py -3.13 -m deathward.tests`
Expected: green (including `TestKnowledgeIsNotPower` — the blink draws `world.rng`, not the Kodex).

- [ ] **Step 9: Commit**

```bash
git add deathward/config.py deathward/player.py deathward/items.py deathward/sprites.py deathward/world.py deathward/tests.py
git commit -m "Slipstep boots: every 4th wound blinks you clear and stuns the striker (T5)"
```

---

### Task 5: Emberstride — immune to freezing (+2 def)

**Files:**
- Modify: `deathward/items.py` (`BOOTS`), `deathward/sprites.py` (`_boots_sprite`), `deathward/world.py:360-371` (`freeze_player`)
- Test: `deathward/tests.py` (`TestMagicalBoots`)

**Interfaces:**
- Produces: `BOOTS["emberstride"]` (T4, +0, +2 def, trait `"emberstride"`). While worn, `freeze_player` never sets `player.frozen`.

- [ ] **Step 1: Write the failing test**

Add to `TestMagicalBoots`:

```python
    def test_emberstride_is_never_frozen_and_wards_two(self):
        from .items import BOOTS
        w = World(FakeSave(), seed=11)
        w.player.boots = BOOTS["emberstride"]
        self.assertEqual(BOOTS["emberstride"].defense, 2, "Emberstride wards +2")
        w.freeze_player(2)
        self.assertEqual(w.player.frozen, 0, "Emberstride's heat shrugs off the gaze")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `py -3.13 -m deathward.tests TestMagicalBoots.test_emberstride_is_never_frozen_and_wards_two -v`
Expected: FAIL — `KeyError: 'emberstride'`.

- [ ] **Step 3: Add the boot**

In `deathward/items.py` magical `BOOTS`:

```python
    "emberstride": Boots("emberstride", "Emberstride", 4, 0, "emberstride",
                         "the ice cannot take feet that smoulder", defense=2),
```

- [ ] **Step 4: Add the sprite**

In `deathward/sprites.py` `_boots_sprite`:

```python
    elif key == "emberstride":              # dark boot, ember glow
        boot((104, 66, 58), (66, 40, 36))
        for (dx, dy, r) in ((-0.10, 0.42, 0.05), (0.10, 0.54, 0.04), (-0.02, 0.64, 0.03)):
            _circ(s, (255, 150, 60), cx + S * dx, S * dy, S * r)
            _circ(s, (255, 216, 120), cx + S * dx, S * dy, S * r * 0.45)
```

- [ ] **Step 5: Negate the freeze**

In `deathward/world.py` `freeze_player`, after the `sanctuary` guard (line 366) and before `p.frozen = ...` (line 368), add:

```python
        if p.boots.trait == "emberstride":
            self.log("The gaze reaches your feet -- and the heat there melts it.",
                     config.MANA)
            return
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `py -3.13 -m deathward.tests TestMagicalBoots.test_emberstride_is_never_frozen_and_wards_two -v`
Expected: PASS. Then:
Run: `py -3.13 -m deathward.tests`
Expected: green.

- [ ] **Step 7: Commit**

```bash
git add deathward/items.py deathward/sprites.py deathward/world.py deathward/tests.py
git commit -m "Emberstride boots: immune to freezing, +2 def (T4)"
```

---

### Task 6: Rimewalkers — immune to fire damage (+2 def)

**Files:**
- Modify: `deathward/items.py` (`BOOTS`), `deathward/sprites.py` (`_boots_sprite`), `deathward/world.py:696-715` (`hurt_player`)
- Test: `deathward/tests.py` (`TestMagicalBoots`)

**Interfaces:**
- Produces: `BOOTS["rimewalkers"]` (T4, +0, +2 def, trait `"rimewalkers"`). `hurt_player` with a fire `cause` deals 0 while worn. Fire cause today is the fire glyph (`cause == "glyph"`).

- [ ] **Step 1: Write the failing test**

Add to `TestMagicalBoots`:

```python
    def test_rimewalkers_shrug_off_fire_but_not_a_dart(self):
        from .items import BOOTS
        w = World(FakeSave(), seed=13)
        w.player.boots = BOOTS["rimewalkers"]
        self.assertEqual(BOOTS["rimewalkers"].defense, 2, "Rimewalkers ward +2")
        hp = w.player.hp
        w.hurt_player(6, "glyph")                    # a fire glyph blast
        self.assertEqual(w.player.hp, hp, "rimewalkers take no fire damage")
        w.hurt_player(4, "dart")                     # a non-fire source still bites
        self.assertLess(w.player.hp, hp, "only fire is warded, not everything")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `py -3.13 -m deathward.tests TestMagicalBoots.test_rimewalkers_shrug_off_fire_but_not_a_dart -v`
Expected: FAIL — `KeyError: 'rimewalkers'`.

- [ ] **Step 3: Add the boot**

In `deathward/items.py` magical `BOOTS`:

```python
    "rimewalkers": Boots("rimewalkers", "Rimewalkers", 4, 0, "rimewalkers",
                         "frost-shod -- fire finds no purchase", defense=2),
```

- [ ] **Step 4: Add the sprite**

In `deathward/sprites.py` `_boots_sprite`:

```python
    elif key == "rimewalkers":              # pale ice-blue, frost crystals
        boot((180, 210, 230), (120, 152, 180))
        rime = (232, 246, 255)
        for (dx, dy) in ((-0.12, 0.36), (0.08, 0.46), (-0.02, 0.60)):
            _line(s, rime, (cx + S * dx, S * (dy - 0.05)), (cx + S * dx, S * (dy + 0.05)),
                  S * 0.02)
            _line(s, rime, (cx + S * (dx - 0.05), S * dy), (cx + S * (dx + 0.05), S * dy),
                  S * 0.02)
```

- [ ] **Step 5: Negate fire damage**

In `deathward/world.py` `hurt_player`, define a fire-cause set at module level near the top of world.py (below the imports) if one doesn't exist:

```python
FIRE_CAUSES = frozenset({"glyph"})   # sources Rimewalkers ward against (fire/burn)
```

Then at the very top of `hurt_player` (before the `berserk` line, line 698), add:

```python
        if cause in FIRE_CAUSES and p.boots.trait == "rimewalkers":
            if not silent:
                self.log("The flame washes over your frost-shod feet and dies.",
                         config.MANA)
            return
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `py -3.13 -m deathward.tests TestMagicalBoots.test_rimewalkers_shrug_off_fire_but_not_a_dart -v`
Expected: PASS. Then:
Run: `py -3.13 -m deathward.tests`
Expected: green.

- [ ] **Step 7: Commit**

```bash
git add deathward/items.py deathward/sprites.py deathward/world.py deathward/tests.py
git commit -m "Rimewalkers boots: immune to fire damage, +2 def (T4)"
```

---

### Task 7: Phantom Boots — 25% chance to dodge any hit

**Files:**
- Modify: `deathward/config.py` (constant), `deathward/items.py` (`BOOTS`), `deathward/sprites.py` (`_boots_sprite`), `deathward/world.py:664-670` (`monster_attacks_player`)
- Test: `deathward/tests.py` (`TestMagicalBoots`)

**Interfaces:**
- Produces: `BOOTS["phantom"]` (T4, +0, trait `"phantom"`). At the top of `monster_attacks_player`, a `config.PHANTOM_DODGE_CHANCE` roll (world.rng) fully negates the blow.

- [ ] **Step 1: Write the failing test**

Add to `TestMagicalBoots`:

```python
    def test_phantom_dodges_about_a_quarter_of_blows(self):
        from .items import BOOTS, ARMOURS
        from .monsters import Monster
        w = World(FakeSave(), seed=15)
        w.level.monsters = []
        w.player.boots = BOOTS["phantom"]
        w.player.armour = ARMOURS["rags"]            # 0 def, so any negation is a dodge
        m = Monster("rat", w.player.x, w.player.y)
        landed = 0
        trials = 3000
        for _ in range(trials):
            before = w.player.hp
            w.monster_attacks_player(m, 3)
            if w.player.hp < before:
                landed += 1
            w.player.hp = 50                         # keep the player alive across trials
        rate = landed / trials
        self.assertGreater(rate, 0.68, "≈75%% of blows land (got %.3f)" % rate)
        self.assertLess(rate, 0.82, "≈75%% of blows land (got %.3f)" % rate)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `py -3.13 -m deathward.tests TestMagicalBoots.test_phantom_dodges_about_a_quarter_of_blows -v`
Expected: FAIL — `KeyError: 'phantom'`.

- [ ] **Step 3: Add the config constant**

In `deathward/config.py`, near the combat constants:

```python
PHANTOM_DODGE_CHANCE = 0.25       # Phantom Boots: chance to sidestep an incoming blow
```

- [ ] **Step 4: Add the boot**

In `deathward/items.py` magical `BOOTS`:

```python
    "phantom":  Boots("phantom", "Phantom Boots", 4, 0, "phantom",
                      "sometimes the blow finds only the ghost of you"),
```

- [ ] **Step 5: Add the sprite**

In `deathward/sprites.py` `_boots_sprite`:

```python
    elif key == "phantom":                  # faded grey, a shifted ghost double
        boot((170, 175, 190), (120, 124, 140))
        ghost = (206, 210, 224)
        _poly(s, ghost, [(cx - S * 0.14, S * 0.24), (cx + S * 0.10, S * 0.24),
                         (cx + S * 0.10, S * 0.62), (cx + S * 0.36, S * 0.62),
                         (cx + S * 0.36, S * 0.78), (cx - S * 0.14, S * 0.78)])
```

- [ ] **Step 6: Wire the dodge**

In `deathward/world.py` `monster_attacks_player`, right after the `sanctuary` guard (the block that returns at line 670) and before `raw = dmg` (line 671), add:

```python
        if p.boots.trait == "phantom" and self.rng.random() < config.PHANTOM_DODGE_CHANCE:
            self.log("The %s strikes -- and you are not quite there." % self._mname(m),
                     config.DIM)
            self.add_fx("impact", p.x, p.y, color=(200, 204, 220), radius=0.6, life=0.25)
            return
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `py -3.13 -m deathward.tests TestMagicalBoots.test_phantom_dodges_about_a_quarter_of_blows -v`
Expected: PASS. Then:
Run: `py -3.13 -m deathward.tests`
Expected: green (including `TestKnowledgeIsNotPower` — the dodge draws `world.rng`).

- [ ] **Step 8: Commit**

```bash
git add deathward/config.py deathward/items.py deathward/sprites.py deathward/world.py deathward/tests.py
git commit -m "Phantom Boots: 25% chance to dodge any blow (T4)"
```

---

## Notes for the implementer

- **Read tasks in order** and add each new boot together with its sprite (the every-gear-has-a-sprite test fails otherwise). Sprite colours are chosen to stay distinct; if `test_every_piece_of_gear_has_its_own_sprite` reports a clash/blank, nudge the RGB or add a detail line, keeping the motif.
- **`DIRS8`** and **`config`** are already imported in `world.py`; `config` is already imported in `traps.py`.
- **Do not touch `soft` (Padded Soles)** — its stealth redefinition and the new Whisperstep boot are Phase 2.
- If a single test reports "no tests ran", run the class (`py -3.13 -m deathward.tests TestMagicalBoots -v`) or the whole file.
