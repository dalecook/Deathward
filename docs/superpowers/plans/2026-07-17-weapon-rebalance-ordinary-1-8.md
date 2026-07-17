# Ordinary-Weapon Rebalance (Floors 1–8) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the front-loaded 7-weapon roster with a scarce, generation-placed
ordinary tier (bone/bronze/steel × sword/axe/hammer) whose only power axis early on is
a speed tax and a masterwork bonus, and make that bonus a per-instance number that
survives death on the corpse, the victory-keep and the save.

**Architecture:** The weapon's `+n` moves off the player-side `enchants` dict onto the
`Weapon` instance itself (`Weapon.bonus`); the player's equipped weapon becomes a
private copy so scroll-enchant can mutate it safely. Weapons leave the generic loot
tables entirely and are placed once per floor at dungeon-generation time via a new
`roll_floor_weapon(rng, depth)`. The bonus rides with the weapon through the floor
Drop, the death-corpse's weapon slot, and the victory-keep.

**Tech Stack:** Python 3.11+ standard library only; Pygame for rendering; `unittest`
(run via `python -m deathward.tests`).

## Global Constraints

- **Standard library only** — no new dependencies. Pygame is the sole third-party import, already present.
- **Knowledge is information, never power:** weapon generation must read only `(rng, depth)`, never the Kodex, so blind and omniscient runs of the same seed stay bit-identical. The existing proof is `TestKnowledgeIsInformation` in `deathward/tests.py`.
- **Determinism:** all weapon randomness draws from the per-run `Level.rng` (aka `world.rng`) at a fixed point in `_populate`. Never use `random.random()` module-level or `Date`/time.
- **No enchant cap:** `damage_roll`, `Weapon.desc`, and `gear_display` must render an arbitrary `+n`.
- **GPLv3 header:** every source file already carries it; do not remove it. New files (none planned) would need it.
- **Scope fence:** this phase touches **weapons only**. Armour keeps the `enchants` dict for Scroll of Enchant Armour; boots are untouched. The magical roster stays the existing three (Rapier/Brand/Kris) on floors 8+.
- Run the full suite after every task: `python -m deathward.tests`. A single test: `python -m unittest deathward.tests.<Class>.<method> -v`.

## File Structure

- `deathward/items.py` — `Weapon` gains `speed_mod`, `bonus`, `copy()`; `WEAPONS` becomes the new roster; `gear_pool` drops weapons; new `roll_floor_weapon`.
- `deathward/player.py` — `speed()` adds `weapon.speed_mod`; `damage_roll`/`gear_display` read `weapon.bonus`; `equip` copies the weapon.
- `deathward/world.py` — enchant-weapon scroll mutates the instance; `_take`/`_consume_option`/`_put_back`/`drop_gear_near` thread the bonus; `leave_corpse`/`_settle_corpse`/`loot_options` carry it; `grant_cheat` key fix.
- `deathward/dungeon.py` — `Drop`/`Corpse` gain a bonus field; `_populate` places the floor weapon; floor-1 bone axe; corpse restore reads the bonus.
- `deathward/codex.py` — corpse record stores/loads `weapon_bonus`; "better weapon" keeps the bonus.
- `deathward/game.py` — `victory_gear` records the weapon bonus; `new_run(keep=...)` restores it.
- `deathward/sprites.py` — `_weapon_sprite` dispatches by type, tinted by material, for the 9 new keys.
- `deathward/tests.py` — new tests per task; mechanical rename of old weapon keys.

---

### Task 1: `Weapon` gains speed tax, per-instance bonus, and a copy

**Files:**
- Modify: `deathward/items.py:37-49` (the `Weapon` class)
- Test: `deathward/tests.py` (new `TestWeaponInstance` class, append near the other item tests)

**Interfaces:**
- Produces: `Weapon(key, name, tier, lo, hi, trait=None, note="", speed_mod=0, bonus=0)`; `Weapon.copy(bonus=None) -> Weapon`; `Weapon.roll(rng) -> int` (unchanged); `Weapon.desc() -> str` (now folds `self.bonus`, no argument); `Weapon.speed_mod: int`; `Weapon.bonus: int`.

- [ ] **Step 1: Write the failing test**

Append to `deathward/tests.py`:

```python
class TestWeaponInstance(unittest.TestCase):
    def test_bonus_raises_both_ends_of_the_band(self):
        from .items import Weapon
        import random
        w = Weapon("steel_sword", "Steel Sword", 3, 3, 5, bonus=2)
        rolls = [w.roll(random.Random(i)) for i in range(200)]
        self.assertEqual(min(rolls), 5, "floor raised by +2")
        self.assertEqual(max(rolls), 7, "ceiling raised by +2")

    def test_desc_folds_the_bonus(self):
        from .items import Weapon
        self.assertEqual(Weapon("bronze_sword", "Bronze Sword", 2, 2, 5).desc(),
                         "2-5 dmg")
        self.assertEqual(Weapon("bronze_sword", "Bronze Sword", 2, 2, 5, bonus=3).desc(),
                         "5-8 dmg")

    def test_copy_is_independent(self):
        from .items import Weapon
        base = Weapon("bone_axe", "Bone Axe", 1, 1, 5, trait="cleave", speed_mod=-15)
        c = base.copy(bonus=2)
        self.assertEqual(c.bonus, 2)
        self.assertEqual(base.bonus, 0, "copying does not touch the template")
        self.assertEqual(c.trait, "cleave")
        self.assertEqual(c.speed_mod, -15)

    def test_speed_mod_defaults_to_zero(self):
        from .items import Weapon
        self.assertEqual(Weapon("k", "n", 1, 1, 5).speed_mod, 0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest deathward.tests.TestWeaponInstance -v`
Expected: FAIL — `Weapon()` got an unexpected keyword `bonus` / `speed_mod`.

- [ ] **Step 3: Write minimal implementation**

Replace `deathward/items.py:37-49` with:

```python
class Weapon:
    slot = "weapon"

    def __init__(self, key, name, tier, lo, hi, trait=None, note="",
                 speed_mod=0, bonus=0):
        self.key, self.name, self.tier = key, name, tier
        self.lo, self.hi, self.trait, self.note = lo, hi, trait, note
        self.speed_mod = speed_mod        # a swing tax, same units as boots/armour speed
        self.bonus = bonus                # masterwork + scroll enchant, per-instance

    def roll(self, rng):
        return rng.randint(self.lo, self.hi) + self.bonus

    def copy(self, bonus=None):
        return Weapon(self.key, self.name, self.tier, self.lo, self.hi, self.trait,
                      self.note, self.speed_mod,
                      self.bonus if bonus is None else bonus)

    def desc(self):
        lo, hi = self.lo + self.bonus, self.hi + self.bonus
        s = "%d-%d dmg" % (lo, hi)
        return s + ("  |  " + self.note if self.note else "")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest deathward.tests.TestWeaponInstance -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add deathward/items.py deathward/tests.py
git commit -m "Weapon gains speed_mod, per-instance bonus, and copy()"
```

---

### Task 2: Player reads `weapon.bonus`/`weapon.speed_mod`; enchant mutates the instance

Moves the weapon `+n` off the `enchants` dict. `roll(rng)` already adds `self.bonus`
(Task 1), so `damage_roll` must **stop** adding the dict value for the weapon to avoid
double-counting.

**Files:**
- Modify: `deathward/player.py:89-97` (`speed`), `:110-120` (`damage_roll`), `:122-130` (`equip`), `:136-143` (`gear_display`)
- Modify: `deathward/world.py:1602-1607` (enchant_weapon scroll)
- Test: update `deathward/tests.py:4427-4460` (the two enchant tests) + a new speed-tax test

**Interfaces:**
- Consumes: `Weapon.copy`, `Weapon.bonus`, `Weapon.speed_mod`, `Weapon.desc()` (Task 1).
- Produces: `Player.equip(gear)` stores a **copy** for the weapon slot and returns the displaced instance; `Player.weapon.bonus` is the single source of the weapon `+n`; `player.speed()` includes `weapon.speed_mod`.

- [ ] **Step 1: Write the failing test**

Append to `deathward/tests.py` (new class):

```python
class TestWeaponSpeedTaxAndInstanceBonus(unittest.TestCase):
    def _p(self):
        from .player import Player
        return Player()

    def test_speed_includes_the_weapon_tax(self):
        from .items import WEAPONS
        p = self._p()
        base = p.speed()
        p.weapon = WEAPONS["bone_hammer"].copy()   # -30 tax
        self.assertEqual(p.speed(), base - 30)

    def test_equip_gives_a_private_copy(self):
        from .items import WEAPONS
        p = self._p()
        p.equip(WEAPONS["steel_sword"])
        p.weapon.bonus = 4
        self.assertEqual(WEAPONS["steel_sword"].bonus, 0,
                         "enchanting the equipped weapon never touches the template")

    def test_gear_display_reads_instance_bonus(self):
        from .items import WEAPONS
        p = self._p()
        p.weapon = WEAPONS["bronze_sword"].copy(bonus=3)
        self.assertEqual(p.gear_display("weapon"), ("Bronze Sword +3", "5-8 dmg"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest deathward.tests.TestWeaponSpeedTaxAndInstanceBonus -v`
Expected: FAIL — `WEAPONS["bone_hammer"]` KeyError (roster not built yet) **or** speed unchanged. (KeyError is expected until Task 3; if so, temporarily assert against an existing key is unnecessary — proceed to implement, and this task's tests go green after Task 3. To keep this task self-verifying now, substitute a hand-built weapon: `from .items import Weapon; p.weapon = Weapon("h","H",1,1,5,speed_mod=-30)`.)

Use this self-contained variant so the task verifies without depending on Task 3:

```python
    def test_speed_includes_the_weapon_tax(self):
        from .items import Weapon
        p = self._p()
        base = p.speed()
        p.weapon = Weapon("h", "H", 1, 1, 5, speed_mod=-30)
        self.assertEqual(p.speed(), base - 30)

    def test_gear_display_reads_instance_bonus(self):
        from .items import Weapon
        p = self._p()
        p.weapon = Weapon("bronze_sword", "Bronze Sword", 2, 2, 5, bonus=3)
        self.assertEqual(p.gear_display("weapon"), ("Bronze Sword +3", "5-8 dmg"))
```

Expected now: FAIL — `speed()` ignores `speed_mod`; `gear_display` reads the `enchants` dict, not `weapon.bonus`.

- [ ] **Step 3: Write minimal implementation**

In `deathward/player.py`, `speed()` — add the weapon tax:

```python
    def speed(self):
        s = (config.BASE_SPEED + self.boots.speed + self.armour.speed_mod
             + self.weapon.speed_mod)
        if self.haste > 0:
            s += 50
        if self.berserk > 0:
            s += 40
        if self.heroism > 0:
            s += 40
        return max(30, s)
```

In `damage_roll`, drop the weapon entry from the `enchants` lookup (roll already adds `bonus`):

```python
    def damage_roll(self, rng):
        d = self.weapon.roll(rng)
        if self.might > 0:
            d += 3
        if self.berserk > 0:
            d += 6
        if self.heroism > 0:
            d += 5
        if self.weak > 0:
            d = max(1, d - 3)
        return d
```

In `equip`, store a **copy** for the weapon so it is private and enchantable:

```python
    def equip(self, gear):
        old = None
        if gear.slot == "weapon":
            old, self.weapon = self.weapon, gear.copy()
        elif gear.slot == "armour":
            old, self.armour = self.armour, gear
        elif gear.slot == "boots":
            old, self.boots = self.boots, gear
        return old
```

In `gear_display`, read the weapon bonus from the instance (armour still uses the dict):

```python
    def gear_display(self, slot):
        """(name, desc) for an equipped slot. The weapon's +n lives on the instance;
        armour's still lives on the enchants dict until the armour rework."""
        g = {"weapon": self.weapon, "armour": self.armour, "boots": self.boots}[slot]
        if slot == "weapon":
            n = g.bonus
            name = "%s +%d" % (g.name, n) if n else g.name
            return name, g.desc()
        n = self.enchants.get(g.key, 0)
        name = "%s +%d" % (g.name, n) if n else g.name
        desc = g.desc(n) if slot == "armour" else g.desc()
        return name, desc
```

In `deathward/world.py:1602-1607`, enchant-weapon mutates the equipped instance:

```python
        elif effect == "enchant_weapon":
            p.weapon.bonus += 1
            self.log("Your %s drinks the light and keeps it. +%d damage, for good."
                     % (p.weapon.name, p.weapon.bonus), config.GOLD)
            self.add_fx("pulse", p.x, p.y, color=config.GOLD, life=0.6)
```

- [ ] **Step 4: Update the two existing enchant tests to the instance model**

In `deathward/tests.py`, `test_enchant_weapon_adds_permanent_damage_and_stacks` — replace the dict assertion:

```python
        self.assertEqual(w.player.weapon.bonus, 1, "the enchant lives on the weapon")
```

In `test_enchanting_updates_the_displayed_name_and_stats` — replace `WEAPONS["sword"]` with `WEAPONS["bronze_sword"].copy()` and the dict poke with an instance poke:

```python
        w.player.weapon = WEAPONS["bronze_sword"].copy()   # Bronze Sword, 2-5 dmg
        w.player.armour = ARMOURS["leather"]
        self.assertEqual(w.player.gear_display("weapon"), ("Bronze Sword", "2-5 dmg"))

        self._use(w, "krav")                               # enchant the weapon +1
        self.assertEqual(w.player.gear_display("weapon"),
                         ("Bronze Sword +1", "3-6 dmg"), "name and stats both update")

        w.player.weapon.bonus = 3
        self.assertEqual(w.player.gear_display("weapon"),
                         ("Bronze Sword +3", "5-8 dmg"), "and it stacks")
```

(The armour half of that test is unchanged — armour keeps the dict.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m unittest deathward.tests.TestWeaponSpeedTaxAndInstanceBonus deathward.tests.TestWaveTwoBuffs -v`
Expected: PASS. (`TestWaveTwoBuffs` holds the two edited enchant tests.)

- [ ] **Step 6: Commit**

```bash
git add deathward/player.py deathward/world.py deathward/tests.py
git commit -m "Weapon +n and speed tax move onto the equipped instance"
```

---

### Task 3: The new ordinary roster, tiers, sprites, and reference rename

Replaces `WEAPONS` with the 9-weapon ordinary matrix + shiv + the magical trio. Tiers
now encode power ordering (shiv 0 < bone 1 < bronze 2 < steel 3 < magical 4) for the
"keep the better weapon" and no-downgrade logic. Sprites dispatch by type, tinted by
material. All old-key references are renamed.

**Files:**
- Modify: `deathward/items.py:78-91` (`WEAPONS`)
- Modify: `deathward/sprites.py:934-999` (`_weapon_sprite`)
- Modify: `deathward/world.py:1011` (`grant_cheat` — `WEAPONS["kris"]` is still valid; no change needed, verify)
- Modify: `deathward/tests.py` — rename old keys (enumerated below)
- Test: new `TestWeaponRoster`

**Interfaces:**
- Produces: `WEAPONS` keys `shiv`, `bone_sword`, `bone_axe`, `bone_hammer`, `bronze_sword`, `bronze_axe`, `bronze_hammer`, `steel_sword`, `steel_axe`, `steel_hammer`, `rapier`, `brand`, `kris`. Tiers: shiv 0; bone_* 1; bronze_* 2; steel_* 3; rapier/brand/kris 4. Speed tax: `*_sword` 0, `*_axe` −15, `*_hammer` −30.

- [ ] **Step 1: Write the failing test**

```python
class TestWeaponRoster(unittest.TestCase):
    def test_matrix_shape_and_stats(self):
        from .items import WEAPONS
        bands = {"bone": (1, 5), "bronze": (2, 5), "steel": (3, 5)}
        taxes = {"sword": 0, "axe": -15, "hammer": -30}
        traits = {"sword": None, "axe": "cleave", "hammer": "stun"}
        tiers = {"bone": 1, "bronze": 2, "steel": 3}
        for mat, (lo, hi) in bands.items():
            for typ, tax in taxes.items():
                w = WEAPONS["%s_%s" % (mat, typ)]
                self.assertEqual((w.lo, w.hi), (lo, hi))
                self.assertEqual(w.speed_mod, tax)
                self.assertEqual(w.trait, traits[typ])
                self.assertEqual(w.tier, tiers[mat])

    def test_shiv_is_the_starter_and_lowest(self):
        from .items import WEAPONS, STARTING
        self.assertEqual(STARTING[0], "shiv")
        self.assertEqual(WEAPONS["shiv"].tier, 0)

    def test_magical_trio_is_top_tier(self):
        from .items import WEAPONS
        for k in ("rapier", "brand", "kris"):
            self.assertEqual(WEAPONS[k].tier, 4)

    def test_iron_warhammer_is_retired(self):
        from .items import WEAPONS
        self.assertNotIn("sword", WEAPONS)
        self.assertNotIn("hammer", WEAPONS)   # the old Iron Warhammer key is gone
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest deathward.tests.TestWeaponRoster -v`
Expected: FAIL — new keys absent.

- [ ] **Step 3: Write the roster**

Replace `deathward/items.py:78-91` (`WEAPONS = {...}`) with:

```python
# Ordinary weapons: TYPE sets the attack shape and a speed tax, MATERIAL raises the
# damage floor (holding the ceiling at 5, so a better material means fewer whiffs, not
# a bigger top end). Tier encodes the power ordering used to keep the better of two
# weapons on a corpse: shiv < bone < bronze < steel < magical.
def _ordinary(mat, mat_tier, mat_lo):
    out = {}
    for typ, tax, trait, note in (
            ("sword", 0, None, ""),
            ("axe", -15, "cleave", "cleaves every adjacent enemy"),
            ("hammer", -30, "stun", "1 in 4 strikes stuns for a turn")):
        key = "%s_%s" % (mat, typ)
        name = "%s %s" % (mat.capitalize(), typ.capitalize())
        out[key] = Weapon(key, name, mat_tier, mat_lo, 5, trait, note, speed_mod=tax)
    return out

WEAPONS = {"shiv": Weapon("shiv", "Rusted Shiv", 0, 1, 3)}
WEAPONS.update(_ordinary("bone", 1, 1))
WEAPONS.update(_ordinary("bronze", 2, 2))
WEAPONS.update(_ordinary("steel", 3, 3))
# --- magical (floors 8+): found unenhanced, enchantable by scroll -----------
WEAPONS.update({
    "rapier": Weapon("rapier", "Steel Rapier", 4, 4, 6, "crit",
                     "1 in 4 strikes doubles"),
    "brand":  Weapon("brand", "Flame Brand", 4, 5, 10, "burn",
                     "sets the struck thing alight"),
    "kris":   Weapon("kris", "Vampiric Kris", 4, 3, 7, "lifesteal",
                     "you heal for half of what you deal"),
})
```

- [ ] **Step 4: Give the new keys sprites**

Replace `deathward/sprites.py:934-979` (the `def _weapon_sprite` head through the end of the `hammer` branch) with a type-dispatch tinted by material. Keep the `rapier`/`brand`/`kris` branches that follow (lines 980+) untouched:

```python
_MATERIAL = {                       # (blade, hilt, guard) per material
    "bone":   ((236, 230, 212), (172, 150, 118), (200, 190, 168)),
    "bronze": ((206, 150, 74), (120, 84, 52), (162, 116, 60)),
    "steel":  ((216, 224, 236), (60, 62, 72), (176, 182, 196)),
}


def _weapon_sprite(key, s, S):
    cx = S * 0.5
    if key == "shiv":                       # rusted, short, pitiful
        rust = (150, 106, 78)
        _w_blade(s, S, rust, (86, 70, 60), (110, 92, 74), length=0.30, width=0.07,
                 tip=0.28)
        _circ(s, _shade(rust, 0.7), cx + S * 0.02, S * 0.45, S * 0.02)
        _circ(s, _shade(rust, 0.7), cx - S * 0.02, S * 0.55, S * 0.015)
        return
    if "_" in key and key.split("_")[0] in _MATERIAL:
        mat, typ = key.split("_")
        blade, hilt, guard = _MATERIAL[mat]
        if typ == "sword":
            _w_blade(s, S, blade, hilt, guard)
        elif typ == "axe":
            haft = hilt
            _line(s, haft, (cx - S * 0.10, S * 0.16), (cx - S * 0.02, S * 0.90), S * 0.055)
            head = [(cx - S * 0.08, S * 0.16), (cx + S * 0.10, S * 0.13),
                    (cx + S * 0.30, S * 0.24), (cx + S * 0.34, S * 0.40),
                    (cx + S * 0.20, S * 0.34), (cx + S * 0.04, S * 0.36),
                    (cx - S * 0.06, S * 0.34)]
            _poly(s, blade, head)
            pygame.draw.lines(s, _shade(blade, 0.72), True,
                              [(int(x), int(y)) for x, y in head], int(S * 0.018))
            _line(s, _shade(blade, 1.25), (cx + S * 0.12, S * 0.16),
                  (cx + S * 0.31, S * 0.27), S * 0.022)
        elif typ == "hammer":
            _line(s, hilt, (cx, S * 0.30), (cx, S * 0.90), S * 0.07)
            pygame.draw.rect(s, blade, (cx - S * 0.28, S * 0.14, S * 0.56, S * 0.26),
                             border_radius=int(S * 0.04))
            pygame.draw.rect(s, _shade(blade, 0.7),
                             (cx - S * 0.28, S * 0.14, S * 0.56, S * 0.26),
                             int(S * 0.025), border_radius=int(S * 0.04))
            _line(s, _shade(blade, 1.25), (cx - S * 0.22, S * 0.20),
                  (cx + S * 0.22, S * 0.20), S * 0.02)
        return
    if key == "rapier":                     # long, thin, bright steel; swept guard
```

(The line immediately after this block is the existing `rapier` body — leave it and everything below it as-is. The old `sword`/`axe`/`hammer` `elif` branches are now replaced by the material dispatch above.)

- [ ] **Step 5: Rename old weapon keys in the tests**

These test sites reference retired/renamed keys. Apply this exact mapping (old → new):
`"sword"` → `"bronze_sword"`; `"axe"` → `"bone_axe"`. `brand`, `rapier`, `kris`, `shiv` are unchanged. Sites (from grep) in `deathward/tests.py`:

- `:1200`, `:1221`, `:1232`, `:1234`, `:1245`, `:1249` — `("gear", "axe")` → `("gear", "bone_axe")`, and the `weapon.key == "axe"` assertions → `"bone_axe"`.
- `:1260`, `:3106`, `:3109`, `:3259-3265`, `:3277-3284`, `:3336`, `:3341`, `:4450` — `"sword"`/`WEAPONS["sword"]` → `"bronze_sword"`/`WEAPONS["bronze_sword"]`.
- `:3260`, `:3278` chest holds `("gear","brand")` — unchanged (brand still tier-top; still "the better weapon"). The paired `sword` becomes `bronze_sword`.
- `:1226` `weapon.key == "shiv"` unchanged.
- All `brand`/`rapier`/`kris`/`shiv` assertions unchanged.

After editing, verify none remain:

Run: `grep -nE '"(sword|axe|hammer)"' deathward/tests.py`
Expected: no output (the retired bare keys are gone; only `bone_axe`/`bronze_sword`/etc. remain).

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m unittest deathward.tests.TestWeaponRoster -v` then `python -m deathward.tests`
Expected: `TestWeaponRoster` PASS; full suite PASS except any weapon-generation tests not yet written (there are none yet) — investigate any other failure before continuing.

- [ ] **Step 7: Commit**

```bash
git add deathward/items.py deathward/sprites.py deathward/tests.py
git commit -m "New ordinary weapon roster (bone/bronze/steel x sword/axe/hammer) + sprites"
```

---

### Task 4: Weapon generation function; weapons leave the loot tables

**Files:**
- Modify: `deathward/items.py:283-296` (`gear_pool`), and add `roll_floor_weapon`
- Test: new `TestWeaponGeneration`

**Interfaces:**
- Produces: `roll_floor_weapon(rng, depth) -> (key: str, bonus: int) | None`. Deterministic on `(rng, depth)`. `gear_pool(depth)` now returns armour+boots keys only.

- [ ] **Step 1: Write the failing test**

```python
class TestWeaponGeneration(unittest.TestCase):
    def test_floor_one_is_always_an_unenhanced_bone_axe(self):
        import random
        from .items import roll_floor_weapon
        for seed in range(50):
            self.assertEqual(roll_floor_weapon(random.Random(seed), 1),
                             ("bone_axe", 0))

    def test_material_bands(self):
        import random
        from .items import roll_floor_weapon
        def mats(depth):
            out = set()
            for seed in range(400):
                r = roll_floor_weapon(random.Random(seed), depth)
                if r:
                    out.add(r[0].split("_")[0])
            return out
        self.assertEqual(mats(2), {"bone"})
        self.assertEqual(mats(3) | mats(4), {"bronze"})
        self.assertEqual(mats(6), {"steel"})

    def test_floor_eight_plus_is_magical(self):
        import random
        from .items import roll_floor_weapon
        got = set()
        for seed in range(400):
            r = roll_floor_weapon(random.Random(seed), 8)
            if r:
                self.assertEqual(r[1], 0, "magical weapons are found unenhanced")
                got.add(r[0])
        self.assertTrue(got <= {"rapier", "brand", "kris"})

    def test_present_probability_falls_with_depth(self):
        import random
        from .items import roll_floor_weapon
        def rate(depth):
            hits = sum(roll_floor_weapon(random.Random(s), depth) is not None
                       for s in range(2000))
            return hits / 2000.0
        self.assertAlmostEqual(rate(5), 0.80, delta=0.04)
        self.assertAlmostEqual(rate(12), 0.70, delta=0.04)
        self.assertAlmostEqual(rate(18), 0.60, delta=0.04)

    def test_enhancement_chance_climbs(self):
        import random
        from .items import roll_floor_weapon
        def enh_rate(depth):
            present = [r for r in (roll_floor_weapon(random.Random(s), depth)
                                   for s in range(4000)) if r]
            return sum(1 for _, b in present if b > 0) / len(present)
        self.assertLess(enh_rate(2), 0.16)     # ~10%
        self.assertGreater(enh_rate(7), 0.50)  # ~60%

    def test_gear_pool_has_no_weapons(self):
        from .items import gear_pool, WEAPONS
        for depth in (1, 5, 10, 20):
            self.assertFalse(any(k in WEAPONS for k in gear_pool(depth)),
                             "weapons are generation-placed, never in the gear pool")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest deathward.tests.TestWeaponGeneration -v`
Expected: FAIL — `roll_floor_weapon` undefined; `gear_pool` still yields weapons.

- [ ] **Step 3: Write the implementation**

In `deathward/items.py`, change `gear_pool` to skip weapons (it iterates `WEAPONS, ARMOURS, BOOTS`):

```python
def gear_pool(depth):
    """Armour and boots that can drop at a given depth. Weapons are NOT here -- they are
    placed one-per-floor at generation time (see roll_floor_weapon)."""
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
    return pool
```

Add `roll_floor_weapon` (place it just after `gear_pool`):

```python
def roll_floor_weapon(rng, depth):
    """The one weapon a floor may hold, decided at generation. Returns (key, bonus) or
    None. Depends only on (rng, depth) -- never on the Kodex -- so blind and omniscient
    runs of a seed stay bit-identical.

    Floor 1 always yields an unenhanced Bone Axe (the safety valve + the cleave lesson).
    Floors 2-7 are ordinary, material banded by depth, with a depth-scaled masterwork
    chance. Floors 8+ are magical, always unenhanced.
    """
    if depth == 1:
        return ("bone_axe", 0)
    present = 0.80 if depth <= 8 else 0.70 if depth <= 15 else 0.60
    if rng.random() >= present:
        return None
    if depth <= 7:
        material = "bone" if depth <= 2 else "bronze" if depth <= 4 else "steel"
        wtype = rng.choice(["sword", "axe", "hammer"])
        bonus = 0
        if rng.random() < (depth - 1) * 0.10:      # 10% on 2 ... 60% on 7
            bonus = 2 if rng.random() < 0.25 else 1
        return ("%s_%s" % (material, wtype), bonus)
    return (rng.choice(["rapier", "brand", "kris"]), 0)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest deathward.tests.TestWeaponGeneration -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add deathward/items.py deathward/tests.py
git commit -m "Add roll_floor_weapon; remove weapons from the gear pool"
```

---

### Task 5: Place the floor weapon at generation; `Drop` carries a bonus

**Files:**
- Modify: `deathward/dungeon.py:100-107` (`Drop`), `:445-483` (`_populate`, weapon block + floor-1)
- Modify: `deathward/dungeon.py:29` (import `roll_floor_weapon`)
- Test: new `TestFloorWeaponPlacement`

**Interfaces:**
- Consumes: `roll_floor_weapon` (Task 4).
- Produces: `Drop(x, y, kind, payload, gift=None, bonus=0)`; each generated `Level` has at most one `Drop` whose `payload in WEAPONS`, and exactly one (a `bone_axe`) on depth 1.

- [ ] **Step 1: Write the failing test**

```python
class TestFloorWeaponPlacement(unittest.TestCase):
    def _weapon_drops(self, lvl):
        from .items import WEAPONS
        return [d for d in lvl.drops if d.kind == "gear" and d.payload in WEAPONS]

    def test_floor_one_always_has_exactly_one_bone_axe(self):
        for seed in range(20):
            codex = FakeSave()
            codex.world_seed = seed
            w = World(codex, seed=seed)
            drops = self._weapon_drops(w.level)
            self.assertEqual(len(drops), 1, "one weapon on floor 1")
            self.assertEqual(drops[0].payload, "bone_axe")
            self.assertEqual(drops[0].bonus, 0)

    def test_no_floor_holds_more_than_one_weapon(self):
        from .dungeon import Level
        import random
        for depth in range(1, 21):
            for seed in range(15):
                codex = FakeSave()
                codex.world_seed = seed
                lvl = Level(depth, random.Random(seed * 31 + depth), codex)
                self.assertLessEqual(len(self._weapon_drops(lvl)), 1,
                                     "at most one weapon per floor at depth %d" % depth)

    def test_weapons_no_longer_come_from_chests(self):
        from .dungeon import Level
        from .items import WEAPONS
        import random
        for depth in range(1, 21):
            for seed in range(15):
                codex = FakeSave()
                codex.world_seed = seed
                lvl = Level(depth, random.Random(seed), codex)
                for ch in lvl.chests:
                    for kind, payload in ch.loot:
                        self.assertFalse(kind == "gear" and payload in WEAPONS,
                                         "no weapon in a chest")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest deathward.tests.TestFloorWeaponPlacement -v`
Expected: FAIL — `Drop` has no `bonus`; floor-1 may hold random gear, not a guaranteed bone axe.

- [ ] **Step 3: Add `bonus` to `Drop`**

Replace `deathward/dungeon.py:100-107` (`Drop.__init__`):

```python
class Drop:
    """An item lying on the floor."""

    def __init__(self, x, y, kind, payload, gift=None, bonus=0):
        self.x, self.y = x, y
        self.kind = kind          # "gold" | "item" | "gear"
        self.payload = payload
        self.gift = gift          # a one-time-per-GAME reward, spent on pickup
        self.bonus = bonus        # a weapon's masterwork/enchant +n, for placed weapons
```

- [ ] **Step 4: Import the roller and place the floor weapon**

In `deathward/dungeon.py:29`, extend the items import:

```python
from .items import gear_pool, roll_chest, roll_floor_weapon, roll_loot
```

In `_populate`, replace the floor-1 guaranteed-gear block (`deathward/dungeon.py:466-483`) with the floor-weapon placement. This supersedes the old `d == 1` random-gear gift for the weapon slot (armour/boots still have their own gift path via `gear_pool`, unchanged elsewhere):

```python
        # THE FLOOR'S ONE WEAPON. Scarce and generation-placed: at most one per floor,
        # sometimes none, decided by roll_floor_weapon. Floor 1 is a guaranteed Bone Axe,
        # placed as far from the gate as the level allows -- a reward for exploring, and
        # the safety valve against a run of empty floors stranding you on the shiv.
        wp = roll_floor_weapon(rng, d)
        if wp:
            wkey, wbonus = wp
            spot = None
            if d == 1:
                far_rooms = sorted(
                    (r for r in self.rooms if r is not self.gate_room),
                    key=lambda r: -(abs(r.cx - self.entrance[0]) +
                                    abs(r.cy - self.entrance[1])))
                for room in far_rooms:
                    spot = self._free_tile(avoid_start=True, room=room)
                    if spot:
                        break
            if spot is None:
                spot = self._free_tile(avoid_start=True)
            if spot:
                self.drops.append(Drop(spot[0], spot[1], "gear", wkey, bonus=wbonus))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m unittest deathward.tests.TestFloorWeaponPlacement -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Run the full suite**

Run: `python -m deathward.tests`
Expected: PASS. If the floor-1 gift test (`test_floor_one_guaranteed_upgrade` or similar) fails because it expected a random gear gift, update it to assert the bone axe. Search: `grep -n "floor1\|guaranteed" deathward/tests.py`.

- [ ] **Step 7: Commit**

```bash
git add deathward/dungeon.py deathward/tests.py
git commit -m "Place the floor's one weapon at generation; floor 1 = Bone Axe"
```

---

### Task 6: Thread the bonus through pickup, equip, and drop

Picking up a placed weapon must equip it **with its bonus**; swapping it out onto bare
ground must preserve the displaced weapon's bonus.

**Files:**
- Modify: `deathward/world.py:966-997` (`_take`), `:878-888` (`_consume_option` "drop" branch), `:1177-1189` (`_put_back`), `:784-787` (`loot_options` drop branch)
- Test: new `TestWeaponBonusPickup`

**Interfaces:**
- Consumes: `Drop.bonus` (Task 5), `Player.equip` (Task 2).
- Produces: `_take(kind, payload, sink=None, bonus=0)`; a "drop" loot option carries `bonus`; a displaced weapon returned to bare ground becomes a `Drop` with its `bonus`.

- [ ] **Step 1: Write the failing test**

```python
class TestWeaponBonusPickup(unittest.TestCase):
    def _world(self):
        codex = FakeSave()
        codex.world_seed = 5
        w = World(codex, seed=5)
        w.level.monsters = []
        return w

    def test_picking_up_an_enhanced_weapon_equips_the_bonus(self):
        from .dungeon import Drop
        w = self._world()
        w.level.drops.append(Drop(w.player.x, w.player.y, "gear", "steel_sword", bonus=2))
        opts = w.loot_options()
        idx = next(i for i, o in enumerate(opts)
                   if o["kind"] == "gear" and o["payload"] == "steel_sword")
        w._consume_option(opts[idx])
        self.assertEqual(w.player.weapon.key, "steel_sword")
        self.assertEqual(w.player.weapon.bonus, 2)

    def test_swapping_preserves_the_old_weapons_bonus_on_the_floor(self):
        from .dungeon import Drop
        from .items import WEAPONS
        w = self._world()
        w.player.weapon = WEAPONS["bronze_axe"].copy(bonus=3)
        w.level.drops.append(Drop(w.player.x, w.player.y, "gear", "steel_sword", bonus=0))
        opts = w.loot_options()
        idx = next(i for i, o in enumerate(opts)
                   if o["kind"] == "gear" and o["payload"] == "steel_sword")
        w._consume_option(opts[idx])
        dropped = [d for d in w.level.drops if d.payload == "bronze_axe"]
        self.assertEqual(len(dropped), 1)
        self.assertEqual(dropped[0].bonus, 3, "the +3 rides down onto the floor")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest deathward.tests.TestWeaponBonusPickup -v`
Expected: FAIL — bonus not threaded; equipped weapon is +0; dropped weapon loses its bonus.

- [ ] **Step 3: Thread the bonus**

In `loot_options`, the drop branch (`deathward/world.py:784-787`) — carry the drop's bonus:

```python
        for d in lvl.drops_at(p.x, p.y):
            opts.append({"kind": d.kind, "payload": d.payload, "bonus": d.bonus,
                         "label": self.loot_label(d.kind, d.payload),
                         "src": ("drop", d)})
```

In `_consume_option`, the "drop" branch (`deathward/world.py:878-888`) — pass the bonus into `_take`:

```python
        elif src[0] == "drop":
            d = src[1]
            if d in lvl.drops:
                lvl.drops.remove(d)
            if d.gift:
                self.codex.claim_gift(d.gift)
                self.codex.gift_item = d.payload
                p.gift = d.payload
                self.codex.save()
            self._take(d.kind, d.payload, sink=None, bonus=d.bonus)
```

In `_take` (`deathward/world.py:966-997`) — accept `bonus` and equip a bonused copy for weapons:

```python
    def _take(self, kind, payload, sink=None, bonus=0):
        """Put one thing into the hero's hands. Gear is a SWAP, not a purchase: whatever
        comes off goes back where the new thing came from. `bonus` is a placed weapon's
        masterwork/enchant +n; it rides onto the equipped instance."""
        p = self.player
        if kind == "gold":
            p.gold += payload
            self.log("You pocket %d gold." % payload, config.GOLD)
        elif kind == "item":
            p.pack_add(payload)
            c = CONSUMABLES[payload]
            self.log("You take the %s." % c.name(self.codex), config.ITEM)
        elif kind == "gear":
            g = ALL_GEAR[payload]
            if g.slot == "weapon" and bonus:
                g = g.copy(bonus=bonus)          # carry the found/kept +n into the swap
            old = p.equip(g)
            self.codex.see_gear(payload)
            name, desc = p.gear_display(g.slot)
            self.log("You put on the %s.  (%s)" % (name, desc), config.ITEM)
            if old and p.gift == old.key:
                p.gift = None
            if payload == self.codex.gift_item:
                p.gift = payload
            if old:
                self._put_back(old, sink)
```

In `_put_back` (`deathward/world.py:1177-1189`) — a displaced weapon returned to bare ground keeps its bonus (the loot-list path is the documented edge case and keeps dropping to +0 this phase):

```python
    def _put_back(self, gear, sink):
        """The gear you took off. Back into the container you looted, or onto the ground.
        NOTE: a weapon returned to a container's loot LIST loses its +n this phase (the
        loot-tuple format is 2-wide); a weapon returned to bare GROUND keeps it. The
        death-corpse's own weapon slot preserves +n (see leave_corpse). The loot-list
        edge is closed when armour/boots join the per-instance model."""
        if sink is not None and hasattr(sink, "loot"):
            sink.loot.append(("gear", gear.key))
            where = ("chest" if isinstance(sink, Chest)
                     else "body" if isinstance(sink, Slain)
                     else "your own body")
            self.log("You leave the %s in the %s." % (gear.name, where), config.DIM)
        else:
            p = self.player
            bonus = getattr(gear, "bonus", 0)
            self.level.drops.append(Drop(p.x, p.y, "gear", gear.key, bonus=bonus))
            self.log("You drop the %s at your feet." % gear.name, config.DIM)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest deathward.tests.TestWeaponBonusPickup -v` then `python -m deathward.tests`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deathward/world.py deathward/tests.py
git commit -m "Thread weapon bonus through pickup, equip, and floor drops"
```

---

### Task 7: The bonus survives death on the corpse

**Files:**
- Modify: `deathward/dungeon.py:134-146` (`Corpse`), `:391-392` (corpse restore)
- Modify: `deathward/codex.py:882-915` (`write_corpse`, `leave_corpse`)
- Modify: `deathward/world.py:1773-1777` (`leave_corpse`), `:907-919` (`_settle_corpse`), `:759-768` (`loot_options` corpse-weapon branch), `:853-868` (`_consume_option` corpse branch)
- Test: new `TestWeaponBonusSurvivesDeath`

**Interfaces:**
- Consumes: `Corpse`, `codex.write_corpse`, `codex.leave_corpse`.
- Produces: corpse record dict gains `"weapon_bonus": int` (defaults to 0 when absent); `Corpse.weapon_bonus`; `codex.write_corpse(depth, x, y, gold, weapon_key, gift_key, loot, weapon_bonus=0)`; `codex.leave_corpse(depth, x, y, gold, weapon_key, gift_key=None, weapon_bonus=0)`.

- [ ] **Step 1: Write the failing test**

```python
class TestWeaponBonusSurvivesDeath(unittest.TestCase):
    def test_corpse_record_stores_and_reloads_the_bonus(self):
        codex = FakeSave()
        codex.leave_corpse(3, 5, 5, 120, "steel_axe", weapon_bonus=2)
        c = codex.corpse_at(3)
        self.assertEqual(c["weapon"], "steel_axe")
        self.assertEqual(c["weapon_bonus"], 2)

    def test_old_corpse_without_bonus_loads_as_zero(self):
        codex = FakeSave()
        codex.corpses["4"] = {"x": 1, "y": 1, "gold": 0, "weapon": "brand",
                              "gift": None, "loot": []}          # a pre-bonus save
        self.assertEqual(codex.corpse_at(4).get("weapon_bonus", 0), 0)

    def test_better_weapon_keeps_its_bonus_across_a_second_death(self):
        codex = FakeSave()
        codex.leave_corpse(2, 4, 4, 50, "steel_sword", weapon_bonus=1)
        codex.leave_corpse(2, 8, 8, 10, "bone_axe", weapon_bonus=0)   # died again, worse
        c = codex.corpse_at(2)
        self.assertEqual(c["weapon"], "steel_sword")
        self.assertEqual(c["weapon_bonus"], 1, "the better weapon keeps its +n")

    def test_reclaiming_your_body_re_equips_the_bonus(self):
        codex = FakeSave()
        codex.world_seed = 7
        codex.leave_corpse(1, 0, 0, 0, "bronze_hammer", weapon_bonus=2)
        w = World(codex, seed=7)
        c = w.level.corpse
        self.assertIsNotNone(c)
        w.player.x, w.player.y = c.x, c.y
        opts = w.loot_options()
        idx = next(i for i, o in enumerate(opts)
                   if o["kind"] == "gear" and o["payload"] == "bronze_hammer")
        w._consume_option(opts[idx])
        self.assertEqual(w.player.weapon.key, "bronze_hammer")
        self.assertEqual(w.player.weapon.bonus, 2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest deathward.tests.TestWeaponBonusSurvivesDeath -v`
Expected: FAIL — `leave_corpse` has no `weapon_bonus`; corpse restore/pickup ignore it.

- [ ] **Step 3: Store the bonus in the codex corpse record**

Replace `deathward/codex.py:882-915` (`write_corpse` + `leave_corpse`):

```python
    def write_corpse(self, depth, x, y, gold, weapon_key, gift_key, loot,
                     weapon_bonus=0):
        """Overwrite the saved body on this floor, exactly as it now stands."""
        self.corpses[str(depth)] = {
            "x": x, "y": y, "gold": gold, "weapon": weapon_key,
            "weapon_bonus": weapon_bonus, "gift": gift_key,
            "loot": [list(t) for t in loot],
        }

    def leave_corpse(self, depth, x, y, gold, weapon_key, gift_key=None,
                     weapon_bonus=0):
        """The body stays where it fell and keeps what it was carrying. Dying twice on a
        floor piles the gold, keeps the better weapon (with its +n), and never loses the
        gift."""
        from .items import ALL_GEAR

        loot = []
        old = self.corpses.get(str(depth))
        if old:
            gold += old.get("gold", 0)
            old_w = old.get("weapon")
            old_b = old.get("weapon_bonus", 0)
            if old_w in ALL_GEAR and weapon_key in ALL_GEAR:
                # keep the better weapon: higher tier wins, +n breaks the tie
                if (ALL_GEAR[old_w].tier, old_b) > (ALL_GEAR[weapon_key].tier,
                                                    weapon_bonus):
                    weapon_key, weapon_bonus = old_w, old_b
            elif old_w and not weapon_key:
                weapon_key, weapon_bonus = old_w, old_b
            gift_key = gift_key or old.get("gift")
            loot = [tuple(t) for t in old.get("loot", [])]
        self.write_corpse(depth, x, y, gold, weapon_key, gift_key, loot, weapon_bonus)
```

- [ ] **Step 4: Carry the bonus onto the in-memory `Corpse` and back to the save**

Replace `deathward/dungeon.py:134-146` (`Corpse.__init__`):

```python
class Corpse:
    """You, from a previous run. Still lying exactly where you fell, still holding
    everything you were holding."""

    def __init__(self, x, y, gold, weapon, gift=None, loot=None, weapon_bonus=0):
        self.x, self.y = x, y
        self.gold = gold
        self.weapon = weapon
        self.weapon_bonus = weapon_bonus
        self.gift = gift
        self.loot = [tuple(t) for t in (loot or [])]
        self.taken = False
```

In `deathward/dungeon.py:391-392`, pass the stored bonus when rebuilding the corpse:

```python
            self.corpse = Corpse(cx, cy, c.get("gold", 0), c.get("weapon"),
                                 c.get("gift"), c.get("loot"),
                                 weapon_bonus=c.get("weapon_bonus", 0))
```

- [ ] **Step 5: Pass the player's live bonus into `leave_corpse`, offer it on the menu, and re-save it**

In `deathward/world.py:1773-1777` (`World.leave_corpse`):

```python
    def leave_corpse(self):
        p = self.player
        self.codex.leave_corpse(self.depth, p.x, p.y, p.gold, p.weapon.key,
                                gift_key=p.gift, weapon_bonus=p.weapon.bonus)
        self.codex.stats["gold_lost"] += p.gold
```

In `loot_options`, the corpse field loop (`deathward/world.py:759-768`) — attach the bonus to the weapon option so pickup can equip it:

```python
            seen = set()
            for field in ("weapon", "gift"):
                key = getattr(c, field)
                if key and key in ALL_GEAR and key not in seen and ALL_GEAR[key].tier > 0:
                    seen.add(key)
                    label = self.loot_label("gear", key)
                    if field == "gift":
                        label += "   [the gift]"
                    bonus = c.weapon_bonus if field == "weapon" else 0
                    opts.append({"kind": "gear", "payload": key, "label": label,
                                 "bonus": bonus, "src": ("corpse", field)})
```

In `_consume_option`, the corpse branch (`deathward/world.py:862-868`) — thread the bonus into `_take` and clear it off the body when the weapon is taken:

```python
            else:
                key = getattr(c, field)
                bonus = c.weapon_bonus if field == "weapon" else 0
                setattr(c, field, None)
                if field == "weapon":
                    c.weapon_bonus = 0
                self.log("You prise the %s from your own fingers."
                         % ALL_GEAR[key].name, config.CORPSE)
                self._take("gear", key, sink=c, bonus=bonus)
            self._settle_corpse(c)
```

In `_settle_corpse` (`deathward/world.py:917-919`) — persist the bonus:

```python
        else:
            self.codex.write_corpse(self.depth, c.x, c.y, c.gold, c.weapon, c.gift,
                                    c.loot, weapon_bonus=c.weapon_bonus)
```

- [ ] **Step 6: Make the corpse-weapon loot options carry a default bonus everywhere they are built**

Search for other option dicts that omit `"bonus"` but feed `_take` for gear. The `_take` call reads `bonus` only from its argument (default 0), and every gear-bearing `_consume_option` branch that must preserve a bonus (drop, corpse-weapon) now passes it explicitly. Chest/slain/corpse_loot gear stays +0 by design (documented). No further change needed — verify by reading `_consume_option`.

Run: `grep -n '"bonus"' deathward/world.py`
Expected: entries in the drop branch (Task 6) and the corpse weapon branch (this task).

- [ ] **Step 7: Run tests to verify they pass**

Run: `python -m unittest deathward.tests.TestWeaponBonusSurvivesDeath -v` then `python -m deathward.tests`
Expected: PASS. If a pre-existing corpse test calls `leave_corpse(...)` positionally without a bonus, it still works (the param defaults to 0).

- [ ] **Step 8: Commit**

```bash
git add deathward/codex.py deathward/dungeon.py deathward/world.py deathward/tests.py
git commit -m "Weapon +n survives death: stored on the corpse, restored on reclaim"
```

---

### Task 8: The bonus survives the Warden-victory keep

**Files:**
- Modify: `deathward/game.py:152-154` (victory capture), `:116-123` (`new_run` keep)
- Test: new `TestVictoryKeepBonus`

**Interfaces:**
- Consumes: `Weapon.copy`, `Player.equip`.
- Produces: `victory_gear` gains `"weapon_bonus"`; `new_run(keep="weapon")` re-equips the kept weapon with that bonus.

- [ ] **Step 1: Write the failing test**

```python
class TestVictoryKeepBonus(unittest.TestCase):
    def test_kept_weapon_keeps_its_bonus_into_the_next_run(self):
        from .game import Game
        from .items import WEAPONS
        g = Game.__new__(Game)          # bypass pygame init; drive the run loop directly
        codex = FakeSave()
        codex.world_seed = 9
        g.codex = codex
        g.world = World(codex, seed=9)
        g.world.player.weapon = WEAPONS["steel_axe"].copy(bonus=3)
        g.victory_gear = {"weapon": g.world.player.weapon.key,
                          "weapon_bonus": g.world.player.weapon.bonus,
                          "armour": g.world.player.armour.key,
                          "boots": g.world.player.boots.key}
        g.banner = None
        g.banner_age = 0.0
        g.new_run(keep="weapon", fresh_dungeon=True)
        self.assertEqual(g.world.player.weapon.key, "steel_axe")
        self.assertEqual(g.world.player.weapon.bonus, 3)
```

(If constructing `Game` this way proves brittle, the existing victory tests around
`deathward/tests.py:1444-1471` show the project's real harness — mirror that setup and
add `weapon_bonus` to the expected `victory_gear` dict there instead.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest deathward.tests.TestVictoryKeepBonus -v`
Expected: FAIL — `new_run` re-equips `ALL_GEAR[key]` (+0), and `victory_gear` has no `weapon_bonus`.

- [ ] **Step 3: Capture and restore the bonus**

In `deathward/game.py:152-154` (victory capture, in `on_victory`/`win` handler):

```python
        self.victory_gear = {"weapon": p.weapon.key, "weapon_bonus": p.weapon.bonus,
                             "armour": p.armour.key, "boots": p.boots.key}
```

In `new_run`, the keep block (`deathward/game.py:116-123`):

```python
        if keep and self.victory_gear:
            from .items import ALL_GEAR
            key = self.victory_gear.get(keep)
            if key and key in ALL_GEAR:
                g = ALL_GEAR[key]
                if keep == "weapon" and self.victory_gear.get("weapon_bonus"):
                    g = g.copy(bonus=self.victory_gear["weapon_bonus"])
                self.world.player.equip(g)
                self.codex.see_gear(key)
                self.world.log("You kept the %s. Everything else, the dungeon took "
                               "back." % ALL_GEAR[key].name, config.GOLD)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest deathward.tests.TestVictoryKeepBonus -v`
Expected: PASS. Then check the existing victory test still matches the new `victory_gear` shape: `python -m unittest deathward.tests.TestVictory -v` (update its expected dict at `:1462` to include `"weapon_bonus": 0` if it asserts equality on the whole dict).

- [ ] **Step 5: Commit**

```bash
git add deathward/game.py deathward/tests.py
git commit -m "Kept weapon carries its +n through the Warden-victory keep"
```

---

### Task 9: Integration — full suite, the bit-identical proof, and a playtest checklist

**Files:**
- Verify only (fix fallout where found): all of the above.

- [ ] **Step 1: Run the whole suite**

Run: `python -m deathward.tests`
Expected: all green. Investigate and fix any failure — do not silence it. Likely spots: tests that hard-coded the old `WEAPONS["sword"]`/`"axe"` power ordering, or the floor-1 gift.

- [ ] **Step 2: Confirm the knowledge-is-information invariant explicitly**

Run: `python -m unittest deathward.tests.TestKnowledgeIsInformation -v`
Expected: PASS — blind and omniscient runs of a seed are still bit-identical. (If it fails, weapon generation is reading Kodex state or drawing rng out of order; `roll_floor_weapon` must depend only on `(rng, depth)` and be called at a fixed point in `_populate`.)

- [ ] **Step 3: Confirm the corpse/persistence proofs still hold**

Run: `python -m unittest deathward.tests.TestCorpse deathward.tests.TestWeaponBonusSurvivesDeath -v`
Expected: PASS (adjust the class name if the corpse suite is named differently — `grep -n "class Test.*[Cc]orpse" deathward/tests.py`).

- [ ] **Step 4: Manual playtest checklist (record results in the PR description)**

Run: `python run_deathward.py` and verify:
- Floor 1 always has a Bone Axe to find, away from the entrance; sprite reads as a bone axe.
- Swinging a hammer feels slower than a sword; the HUD speed/behaviour reflects the tax.
- A found "+1"/"+2" weapon shows its `+n` in the name and a wider damage band; enchanting it with KRAV climbs with no cap.
- Die holding an enhanced weapon, respawn, walk back to your body, reclaim it — the `+n` is intact.
- All nine ordinary sprites render distinctly (bone/bronze/steel × sword/axe/hammer) in the Kodex Gear tab.

- [ ] **Step 5: Final commit (if any fixes were needed)**

```bash
git add -A
git commit -m "Integration fixes for the ordinary-weapon rebalance"
```

## Self-Review Notes (author)

- **Spec coverage:** two classes (Task 3) ✓; matrix + shared bands (Tasks 1,3) ✓; speed tax (Tasks 1,2) ✓; material floor (Task 1) ✓; banding (Task 4) ✓; enhancement +1/+2 with depth-scaled chance (Task 4) ✓; unified per-instance bonus (Tasks 1,2) ✓; persistence on corpse (Task 7), victory-keep (Task 8), save (Task 7) ✓; rarity/generation-placement + present-probability + removed from chests/bodies (Tasks 4,5) ✓; floor-1 guarantee (Tasks 4,5) ✓; reconciling existing weapons / retiring Iron Warhammer (Task 3) ✓; sprites for new keys (Task 3) ✓.
- **Documented scope limits:** a displaced *enhanced* weapon returned into a container's generic loot LIST drops to +0 (Task 6) — the death-corpse weapon slot, floor drops, and victory-keep all preserve it. Armour keeps the `enchants` dict this phase.
- **Known tunables (playtest):** hammer tax −30 vs −25; +1/+2 split 75/25; hard material bands; present-probability numbers.
