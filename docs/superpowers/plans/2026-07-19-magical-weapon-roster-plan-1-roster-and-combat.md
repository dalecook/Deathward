# Magical Weapon Roster — Plan 1: Roster & Combat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make all thirteen magical weapons exist and behave correctly when wielded — the new damage bands, the retuned trio, and every trait (crit, burn, lifesteal, cleave, stun, freeze, fear, poison DoT, enrage, anti-incorporeal, void instakill) — reachable for testing via the CTRL+12 weapon bench.

**Architecture:** `Weapon` moves from a single `trait` string to a `traits` tuple so weapons can combine effects (e.g. Pyroclast = `("cleave","burn")`). Combat resolution in `world.player_attack` reads that tuple; the four *spreadable* elemental statuses (burn/freeze/fear/lifesteal) are factored into one helper applied to the primary target and — for a cleave weapon — to every adjacent enemy. Three genuinely new mechanics are added: a `poisoned` monster DoT, an `enraged` monster state that turns a monster on its neighbours, and a void instakill that deletes a monster with no body and no loot. Generation, the deep economy, uniqueness and persistence are **out of scope** for this plan (Plans 2 and 3).

**Tech Stack:** Python 3.11+ standard library; Pygame for rendering; `unittest`. Run with `py -3.13` (NOT `python`/`py` — those are 3.14 without pygame).

## Global Constraints

- **Standard library + Pygame only** — no new dependencies.
- **Knowledge is information, never power:** all combat randomness (crit, freeze, fear, enrage, void, poison ticks) draws from the per-run world RNG (`self.rng`) at a fixed point, never from the Kodex, `random.*` module-level, or time. Blind and omniscient runs of a seed stay bit-identical (`TestKnowledgeIsNotPower`).
- **Determinism:** an effect that does not fire must not draw RNG in a way that perturbs order for other weapons — only draw when the weapon actually carries that trait.
- **No enchant cap:** `damage_roll`, `Weapon.desc`, and `gear_display` must render an arbitrary `+n` (inherited from phase 1).
- **GPLv3 header:** every source file carries it; do not remove it. No new files are created in this plan.
- **Test commands:** full suite `py -3.13 -m deathward.tests` (baseline 424 green); one test `py -3.13 -m unittest deathward.tests.<Class>.<method> -v`.
- **Scope fence:** this plan is weapons-behaviour only. Do NOT touch `roll_floor_weapon`, `dungeon.py` placement, the loot economy, corpse/ledger persistence, the Kodex achievement, or the respawn homage — those are Plans 2 and 3.

---

### Task 1: `Weapon` gains a `traits` tuple and flat-damage display

Move `Weapon` from one `trait` to a `traits` tuple so weapons can combine effects, keeping a read-only `trait` property so existing single-trait code and tests still work. Also render `lo == hi` as a single number ("5 dmg", not "5-5 dmg") for the flat-damage weapons.

**Files:**
- Modify: `deathward/items.py` (the `Weapon` class, ~lines 37–49, and the `_ordinary` helper, ~lines 92–101)
- Test: `deathward/tests.py` (new `TestWeaponTraits` class, append near `TestWeaponInstance`)

**Interfaces:**
- Produces: `Weapon(key, name, tier, lo, hi, traits=(), note="", speed_mod=0, bonus=0)`; `Weapon.traits: tuple[str, ...]`; `Weapon.has(t: str) -> bool`; `Weapon.trait` read-only property returning `traits[0]` or `None`; `Weapon.copy(bonus=None)` preserves `traits`; `Weapon.desc()` renders "N dmg" when `lo+bonus == hi+bonus`.

- [ ] **Step 1: Write the failing test**

Append to `deathward/tests.py`:

```python
class TestWeaponTraits(unittest.TestCase):
    def test_traits_tuple_and_has(self):
        from .items import Weapon
        w = Weapon("k", "N", 4, 5, 8, traits=("cleave", "burn"))
        self.assertEqual(w.traits, ("cleave", "burn"))
        self.assertTrue(w.has("burn"))
        self.assertFalse(w.has("freeze"))

    def test_trait_property_is_the_first_trait(self):
        from .items import Weapon
        self.assertEqual(Weapon("k", "N", 1, 1, 5, traits=("cleave",)).trait, "cleave")
        self.assertIsNone(Weapon("k", "N", 1, 1, 5).trait)

    def test_copy_preserves_traits(self):
        from .items import Weapon
        c = Weapon("k", "N", 5, 5, 8, traits=("cleave", "burn")).copy(bonus=2)
        self.assertEqual(c.traits, ("cleave", "burn"))
        self.assertEqual(c.bonus, 2)

    def test_flat_damage_renders_a_single_number(self):
        from .items import Weapon
        self.assertEqual(Weapon("k", "N", 5, 5, 5).desc(), "5 dmg")
        self.assertEqual(Weapon("k", "N", 4, 3, 6).desc(), "3-6 dmg")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m unittest deathward.tests.TestWeaponTraits -v`
Expected: FAIL — `Weapon()` got an unexpected keyword `traits`.

- [ ] **Step 3: Rewrite the `Weapon` class**

Replace the `Weapon` class body in `deathward/items.py` (the `__init__`, `roll`, `copy`, `desc`) with:

```python
class Weapon:
    slot = "weapon"

    def __init__(self, key, name, tier, lo, hi, traits=(), note="",
                 speed_mod=0, bonus=0):
        self.key, self.name, self.tier = key, name, tier
        self.lo, self.hi, self.note = lo, hi, note
        self.traits = tuple(traits)       # e.g. ("cleave", "burn"); () for a plain blade
        self.speed_mod = speed_mod        # a swing tax (or, negative, a quickening)
        self.bonus = bonus                # masterwork + scroll enchant, per-instance

    @property
    def trait(self):
        """Back-compat: the primary trait, or None. New code reads self.traits."""
        return self.traits[0] if self.traits else None

    def has(self, t):
        return t in self.traits

    def roll(self, rng):
        return rng.randint(self.lo, self.hi) + self.bonus

    def copy(self, bonus=None):
        return Weapon(self.key, self.name, self.tier, self.lo, self.hi, self.traits,
                      self.note, self.speed_mod,
                      self.bonus if bonus is None else bonus)

    def desc(self):
        lo, hi = self.lo + self.bonus, self.hi + self.bonus
        s = "%d dmg" % lo if lo == hi else "%d-%d dmg" % (lo, hi)
        return s + ("  |  " + self.note if self.note else "")
```

Then update the ordinary-weapon builder `_ordinary` so it passes a tuple. Replace the `out[key] = Weapon(...)` line inside `_ordinary` with:

```python
        out[key] = Weapon(key, name, mat_tier, mat_lo, 5,
                          traits=(trait,) if trait else (), note=note, speed_mod=tax)
```

And the shiv line stays valid (`Weapon("shiv", "Rusted Shiv", 0, 1, 3)` — no traits).

- [ ] **Step 4: Update the existing magical trio to the tuple form (keep them compiling)**

Replace the three magical entries in `deathward/items.py` (the `WEAPONS.update({...})` block, ~lines 108–115) with the `traits=` form (Task 2 retunes them fully; this just keeps the module importable):

```python
WEAPONS.update({
    "rapier": Weapon("rapier", "Steel Rapier", 4, 4, 6, traits=("crit",),
                     note="1 in 4 strikes doubles"),
    "brand":  Weapon("brand", "Flame Brand", 4, 5, 10, traits=("burn",),
                     note="sets the struck thing alight"),
    "kris":   Weapon("kris", "Vampiric Kris", 4, 3, 7, traits=("lifesteal",),
                     note="you heal for half of what you deal"),
})
```

- [ ] **Step 5: Run the new test and the full suite**

Run: `py -3.13 -m unittest deathward.tests.TestWeaponTraits -v`
Expected: PASS (4 tests).
Run: `py -3.13 -m deathward.tests`
Expected: PASS — all 424 still green (the `trait` property keeps `TestWeaponRoster` and `player_attack` working unchanged).

- [ ] **Step 6: Commit**

```bash
git add deathward/items.py deathward/tests.py
git commit -m "Weapon gains a traits tuple and flat-damage display"
```

---

### Task 2: Tier 5 and the thirteen-weapon magical roster

Replace the magical trio with the full roster: retune the three reused keys (`rapier`/`brand`/`kris`) and add ten new keys, at tiers 4 and 5.

**Files:**
- Modify: `deathward/items.py` (the magical `WEAPONS.update({...})` block from Task 1, Step 4)
- Test: `deathward/tests.py` (new `TestMagicalRoster` class)

**Interfaces:**
- Consumes: `Weapon` with `traits` (Task 1).
- Produces: `WEAPONS` gains keys `betrayers_edge`, `fulgurite`, `winters_edge`, `sacrificial_dagger`, `windfang`, `basilisk_maul`, `pyroclast`, `reapers_whisper`, `glacial_flail`, `void_scimitar`; retunes `rapier`, `brand`, `kris`. Tier 4 keys have `tier == 4`, Tier 5 keys `tier == 5`.

- [ ] **Step 1: Write the failing test**

```python
class TestMagicalRoster(unittest.TestCase):
    T4 = {
        "rapier":             (4, 6, ("crit",), 0),
        "brand":              (4, 8, ("burn",), 0),
        "betrayers_edge":     (4, 6, ("enrage",), 0),
        "fulgurite":          (4, 6, ("cleave", "shock"), 0),
        "winters_edge":       (3, 6, ("freeze",), 0),
        "sacrificial_dagger": (3, 5, ("lifesteal",), 0),
        "windfang":           (5, 5, (), 20),
    }
    T5 = {
        "basilisk_maul":   (5, 9, ("poison", "stun"), 0),
        "pyroclast":       (5, 8, ("cleave", "burn"), 0),
        "reapers_whisper": (5, 8, ("cleave", "fear"), 0),
        "kris":            (4, 7, ("cleave", "lifesteal"), 0),
        "glacial_flail":   (4, 7, ("cleave", "freeze"), 0),
        "void_scimitar":   (7, 7, ("void",), 0),
    }

    def test_tier4_weapons(self):
        from .items import WEAPONS
        for key, (lo, hi, traits, tax) in self.T4.items():
            w = WEAPONS[key]
            self.assertEqual((w.lo, w.hi), (lo, hi), key)
            self.assertEqual(w.traits, traits, key)
            self.assertEqual(w.speed_mod, tax, key)
            self.assertEqual(w.tier, 4, key)

    def test_tier5_weapons(self):
        from .items import WEAPONS
        for key, (lo, hi, traits, tax) in self.T5.items():
            w = WEAPONS[key]
            self.assertEqual((w.lo, w.hi), (lo, hi), key)
            self.assertEqual(w.traits, traits, key)
            self.assertEqual(w.speed_mod, tax, key)
            self.assertEqual(w.tier, 5, key)

    def test_all_thirteen_present(self):
        from .items import WEAPONS
        magical = [k for k, w in WEAPONS.items() if w.tier >= 4]
        self.assertEqual(len(magical), 13)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m unittest deathward.tests.TestMagicalRoster -v`
Expected: FAIL — new keys absent; `rapier`/`brand`/`kris` still at old stats.

- [ ] **Step 3: Write the roster**

Replace the magical `WEAPONS.update({...})` block in `deathward/items.py` with:

```python
# --- magical (floors 8+): found unenhanced, enchantable by scroll ------------
# Tier 4 = the effect FOCUSED (single target / fast). Tier 5 = the effect UNLEASHED
# (borrows an ordinary attack shape -- usually cleave -- so it lands on a crowd).
WEAPONS.update({
    # Tier 4 -----------------------------------------------------------------
    "rapier": Weapon("rapier", "Razor Sharp Rapier", 4, 4, 6, traits=("crit",),
                     note="1 in 4 strikes doubles"),
    "brand":  Weapon("brand", "Flame Brand", 4, 4, 8, traits=("burn",),
                     note="sets the struck thing alight"),
    "betrayers_edge": Weapon("betrayers_edge", "Betrayer's Edge", 4, 4, 6,
                             traits=("enrage",),
                             note="the struck thing turns on its own"),
    "fulgurite": Weapon("fulgurite", "Fulgurite", 4, 4, 6, traits=("cleave", "shock"),
                        note="cleaves; scours the incorporeal"),
    "winters_edge": Weapon("winters_edge", "Winter's Edge", 4, 3, 6, traits=("freeze",),
                           note="a chance to freeze where it cuts"),
    "sacrificial_dagger": Weapon("sacrificial_dagger", "Sacrificial Dagger", 4, 3, 5,
                                 traits=("lifesteal",),
                                 note="you heal for half of what you deal"),
    "windfang": Weapon("windfang", "Windfang", 4, 5, 5, traits=(),
                       note="so light it quickens you", speed_mod=20),
    # Tier 5 -----------------------------------------------------------------
    "basilisk_maul": Weapon("basilisk_maul", "Basilisk Maul", 5, 5, 9,
                            traits=("poison", "stun"),
                            note="venom that stiffens the blood"),
    "pyroclast": Weapon("pyroclast", "Pyroclast", 5, 5, 8, traits=("cleave", "burn"),
                        note="cleaves and ignites all it touches"),
    "reapers_whisper": Weapon("reapers_whisper", "Reaper's Whisper", 5, 5, 8,
                             traits=("cleave", "fear"),
                             note="the reaped scatter in terror"),
    "kris": Weapon("kris", "Vampiric Kris", 5, 4, 7, traits=("cleave", "lifesteal"),
                   note="light enough to carry through, and it drinks from each"),
    "glacial_flail": Weapon("glacial_flail", "Glacial Flail", 5, 4, 7,
                            traits=("cleave", "freeze"),
                            note="freezes every adjacent foe"),
    "void_scimitar": Weapon("void_scimitar", "Scimitar of the Void", 5, 7, 7,
                            traits=("void",),
                            note="a chance to unmake what it strikes"),
})
```

- [ ] **Step 4: Run the roster test and full suite**

Run: `py -3.13 -m unittest deathward.tests.TestMagicalRoster -v`
Expected: PASS (3 tests).
Run: `py -3.13 -m deathward.tests`
Expected: PASS. If any test hard-coded the old magical stats (e.g. Rapier 4–6 was already 4–6, Brand was 5–10 now 4–8), update it to the new band and note it in the commit. Search: `grep -n 'brand\|rapier\|kris' deathward/tests.py` and check any damage assertions.

- [ ] **Step 5: Commit**

```bash
git add deathward/items.py deathward/tests.py
git commit -m "Add Tier 5 and the full thirteen-weapon magical roster"
```

---

### Task 3: Combat reads `traits`, not a single `trait`

Behaviour-preserving migration: `player_attack` currently branches on `trait == "crit"` etc. Make it branch on membership in `p.weapon.traits`, so a weapon like Vampiric Kris (`("cleave","lifesteal")`) fires both effects. No effect logic changes yet.

**Files:**
- Modify: `deathward/world.py` (`player_attack`, ~lines 444–532)
- Test: `deathward/tests.py` (new `TestCombinedTraits` class)

**Interfaces:**
- Consumes: `Weapon.traits` (Task 1).
- Produces: `player_attack(m)` resolves each of crit/lifesteal/stun/burn/cleave when its name is in `traits`.

- [ ] **Step 1: Write the failing test**

```python
class TestCombinedTraits(unittest.TestCase):
    def _world(self):
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=3)
        w.level.monsters = []
        return w

    def test_vampiric_kris_both_cleaves_and_lifesteals(self):
        from .items import WEAPONS
        from .monsters import Monster
        w = self._world()
        p = w.player
        p.weapon = WEAPONS["kris"].copy()      # ("cleave", "lifesteal")
        p.hp = max(1, p.max_hp - 20)
        target = Monster("brute", p.x + 1, p.y); target.hp = target.max_hp = 999
        bystander = Monster("brute", p.x + 1, p.y + 1); bystander.hp = bystander.max_hp = 999
        w.level.monsters = [target, bystander]
        hp0, by0 = p.hp, bystander.hp
        w.player_attack(target)
        self.assertGreater(p.hp, hp0, "lifesteal healed you")
        self.assertLess(bystander.hp, by0, "cleave carried into the bystander")
```

- [ ] **Step 2: Run test to verify it fails or errors**

Run: `py -3.13 -m unittest deathward.tests.TestCombinedTraits -v`
Expected: FAIL — with `trait = p.weapon.trait` (== "cleave", the first), lifesteal never fires, so `p.hp` does not rise.

- [ ] **Step 3: Migrate the branches**

In `deathward/world.py` `player_attack`, replace `trait = p.weapon.trait` with:

```python
        traits = p.weapon.traits
```

Then update each branch to membership tests:
- `if trait == "crit" and self.rng.random() < 0.25:` → `if "crit" in traits and self.rng.random() < 0.25:`
- `if trait == "lifesteal":` → `if "lifesteal" in traits:`
- `if trait == "stun" and m.alive:` → `if "stun" in traits and m.alive:`
- `if trait == "burn" and m.alive:` → `if "burn" in traits and m.alive:`
- `if trait == "cleave":` → `if "cleave" in traits:`

Leave every effect body exactly as it is.

- [ ] **Step 4: Run the new test and full suite**

Run: `py -3.13 -m unittest deathward.tests.TestCombinedTraits -v`
Expected: PASS.
Run: `py -3.13 -m deathward.tests`
Expected: PASS — existing crit/burn/lifesteal/stun/cleave tests unaffected.

- [ ] **Step 5: Commit**

```bash
git add deathward/world.py deathward/tests.py
git commit -m "Combat resolves each weapon trait from the traits tuple"
```

---

### Task 4: The elemental on-hit helper — freeze and fear

Factor the spreadable elemental statuses (burn, freeze, fear, lifesteal) into one helper applied to the primary target, and add the two new ones — **freeze** (reuses the hardened `stunned` system, themed as cold) and **fear** (reuses the `feared` flee state). Chances live in `config`.

**Files:**
- Modify: `deathward/config.py` (add constants after `HAMMER_STUN_TURNS`, ~line 113)
- Modify: `deathward/world.py` (`player_attack` — replace the inline burn and lifesteal with the helper; add the helper)
- Test: `deathward/tests.py` (new `TestElementalStatuses` class)

**Interfaces:**
- Consumes: `config.FREEZE_CHANCE`, `config.FREEZE_TURNS`, `config.FEAR_CHANCE`, `config.FEAR_TURNS`.
- Produces: `World._weapon_status_on(m, dmg) -> int` — applies burn/freeze/fear/lifesteal from the equipped weapon to monster `m`, returns HP healed by lifesteal (0 otherwise). Called for the primary target here; for cleaved targets in Task 5.

- [ ] **Step 1: Add the config constants**

In `deathward/config.py`, after the `HAMMER_STUN_TURNS` line, add:

```python
FREEZE_CHANCE       = 0.25        # Winter's Edge / Glacial Flail: chance to freeze on hit
FREEZE_TURNS        = 1           # a freeze is one player turn of the stun system
FEAR_CHANCE         = 0.25        # Reaper's Whisper: chance to rout on hit
FEAR_TURNS          = 6           # turns a frightened thing flees
```

- [ ] **Step 2: Write the failing test**

```python
class TestElementalStatuses(unittest.TestCase):
    def _world(self):
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=3)
        w.level.monsters = []
        return w

    def _target(self, w):
        from .monsters import Monster
        m = Monster("brute", w.player.x + 1, w.player.y)
        m.hp = m.max_hp = 999
        w.level.monsters.append(m)
        return m

    def test_winters_edge_freezes(self):
        from . import config
        from .items import WEAPONS
        w = self._world(); m = self._target(w)
        w.player.weapon = WEAPONS["winters_edge"].copy()
        old = config.FREEZE_CHANCE
        config.FREEZE_CHANCE = 1.0
        try:
            w.player_attack(m)
            self.assertGreater(m.stunned, 0, "the frost froze it")
        finally:
            config.FREEZE_CHANCE = old

    def test_reapers_whisper_frightens_the_primary(self):
        from . import config
        from .items import WEAPONS
        w = self._world(); m = self._target(w)
        w.player.weapon = WEAPONS["reapers_whisper"].copy()
        old = config.FEAR_CHANCE
        config.FEAR_CHANCE = 1.0
        try:
            w.player_attack(m)
            self.assertGreater(m.feared, 0, "the reaped one is routed")
        finally:
            config.FEAR_CHANCE = old

    def test_plain_weapon_freezes_nothing(self):
        from .items import WEAPONS
        w = self._world(); m = self._target(w)
        w.player.weapon = WEAPONS["steel_sword"].copy()
        w.player_attack(m)
        self.assertEqual(m.stunned, 0)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `py -3.13 -m unittest deathward.tests.TestElementalStatuses -v`
Expected: FAIL — freeze/fear not implemented; `_weapon_status_on` absent.

- [ ] **Step 4: Add the helper and route the primary through it**

In `deathward/world.py`, add the helper method just above `player_attack`:

```python
    def _weapon_status_on(self, m, dmg):
        """Apply the equipped weapon's spreadable on-hit statuses to one struck
        monster. Burn/freeze/fear/lifesteal ride a cleave onto neighbours (Task 5),
        so this is called for the primary target and for each cleaved target.
        Returns HP healed by lifesteal (0 otherwise)."""
        p = self.player
        traits = p.weapon.traits
        if "burn" in traits and m.alive:
            m.burning = max(m.burning, 3)
            self.log("The %s catches fire." % self._mname(m), (255, 150, 80))
            self.add_fx("burning", m.x, m.y, life=0.8, tiles=[(m.x, m.y)])
        if "freeze" in traits and m.alive and self.rng.random() < config.FREEZE_CHANCE:
            m.stunned = max(m.stunned, config.FREEZE_TURNS)
            self.log("The %s freezes solid for a beat." % self._mname(m),
                     (150, 210, 255))
            self.add_fx("freeze", m.x, m.y, color=(150, 210, 255), life=0.5)
        if "fear" in traits and m.alive and self.rng.random() < config.FEAR_CHANCE:
            m.feared = max(m.feared, config.FEAR_TURNS)
            m.awake = True
            self.log("The %s recoils in terror." % self._mname(m), (120, 100, 190))
        if "lifesteal" in traits:
            got = p.heal(dmg // 2)
            if got:
                self.log("The blade drinks. You recover %d." % got, config.HEAL)
                self.add_fx("drain", p.x, p.y, color=(226, 74, 96), life=0.5,
                            tiles=[(m.x, m.y)])
            return got
        return 0
```

Then in `player_attack`, **delete** the inline `if "lifesteal" in traits:` block and the inline `if "burn" in traits and m.alive:` block, and replace them with a single call right after `self.hurt_monster(m, dmg, source="player")`:

```python
        self._weapon_status_on(m, dmg)
```

(Keep the `crit`, `stun`, and `cleave` blocks exactly where they are — freeze and fear now live in the helper; stun stays inline because it is the deterministic hammer cadence, not a spreadable roll.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -3.13 -m unittest deathward.tests.TestElementalStatuses deathward.tests.TestCombinedTraits -v`
Expected: PASS.
Run: `py -3.13 -m deathward.tests`
Expected: PASS — burn and lifesteal still work (now via the helper).

- [ ] **Step 6: Commit**

```bash
git add deathward/config.py deathward/world.py deathward/tests.py
git commit -m "Elemental on-hit helper; add freeze and fear traits"
```

---

### Task 5: A cleave carries its element to the whole crowd

The "unleashed" rule: a Tier-5 cleave weapon applies its element to every enemy it cleaves — Pyroclast ignites the crowd, Glacial Flail freezes it, Reaper's Whisper routs it, Vampiric Kris drinks from each body.

**Files:**
- Modify: `deathward/world.py` (`player_attack`, the `if "cleave" in traits:` loop)
- Test: `deathward/tests.py` (new `TestCleaveCarriesElement` class)

**Interfaces:**
- Consumes: `World._weapon_status_on(m, dmg)` (Task 4).
- Produces: the cleave loop calls `_weapon_status_on` on each adjacent enemy after damaging it.

- [ ] **Step 1: Write the failing test**

```python
class TestCleaveCarriesElement(unittest.TestCase):
    def _world(self):
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=3)
        w.level.monsters = []
        return w

    def _mob(self, w, dx, dy):
        from .monsters import Monster
        m = Monster("brute", w.player.x + dx, w.player.y + dy)
        m.hp = m.max_hp = 999
        w.level.monsters.append(m)
        return m

    def test_pyroclast_ignites_every_cleaved_body(self):
        from .items import WEAPONS
        w = self._world()
        primary = self._mob(w, 1, 0)
        neighbour = self._mob(w, 0, 1)
        w.player.weapon = WEAPONS["pyroclast"].copy()   # ("cleave", "burn")
        w.player_attack(primary)
        self.assertGreater(primary.burning, 0, "primary is alight")
        self.assertGreater(neighbour.burning, 0, "the cleaved neighbour is alight too")

    def test_glacial_flail_freezes_the_cleaved(self):
        from . import config
        from .items import WEAPONS
        w = self._world()
        primary = self._mob(w, 1, 0)
        neighbour = self._mob(w, 0, 1)
        w.player.weapon = WEAPONS["glacial_flail"].copy()  # ("cleave", "freeze")
        old = config.FREEZE_CHANCE
        config.FREEZE_CHANCE = 1.0
        try:
            w.player_attack(primary)
            self.assertGreater(neighbour.stunned, 0, "the cleaved neighbour froze")
        finally:
            config.FREEZE_CHANCE = old
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m unittest deathward.tests.TestCleaveCarriesElement -v`
Expected: FAIL — the cleave loop damages neighbours but applies no status.

- [ ] **Step 3: Apply the element inside the cleave loop**

In `deathward/world.py` `player_attack`, inside the `if "cleave" in traits:` loop, after `self.hurt_monster(o, extra, source="player")`, add:

```python
                    self._weapon_status_on(o, extra)
```

So each cleaved neighbour takes the carry-through damage and then the weapon's element.

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.13 -m unittest deathward.tests.TestCleaveCarriesElement -v`
Expected: PASS.
Run: `py -3.13 -m deathward.tests`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deathward/world.py deathward/tests.py
git commit -m "A cleave weapon carries its element to every cleaved body"
```

---

### Task 6: Poison — a lingering DoT (Basilisk Maul)

Add a `poisoned` monster status that ticks damage each of the monster's turns, modelled on `burning`. Basilisk Maul (`("poison","stun")`) applies it.

**Files:**
- Modify: `deathward/config.py` (`POISON_TURNS`, `POISON_DMG`)
- Modify: `deathward/monsters.py` (`Monster.__init__` add `self.poisoned = 0`; `take_turn` add the tick)
- Modify: `deathward/world.py` (`_weapon_status_on` — apply poison)
- Test: `deathward/tests.py` (new `TestPoison` class)

**Interfaces:**
- Consumes: `config.POISON_TURNS`, `config.POISON_DMG`.
- Produces: `Monster.poisoned: int`; poison ticks `config.POISON_DMG` per monster turn via `hurt_monster(self, POISON_DMG, source="poison")`.

- [ ] **Step 1: Add the config constants**

In `deathward/config.py`, after the freeze/fear constants from Task 4:

```python
POISON_TURNS        = 3           # Basilisk Maul: turns the venom keeps eating
POISON_DMG          = 2           # damage per poisoned turn
```

- [ ] **Step 2: Write the failing test**

```python
class TestPoison(unittest.TestCase):
    def _world(self):
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=3)
        w.level.monsters = []
        return w

    def test_basilisk_maul_poisons_and_it_ticks(self):
        from . import config
        from .items import WEAPONS
        from .monsters import Monster
        w = self._world()
        m = Monster("brute", w.player.x + 1, w.player.y); m.hp = m.max_hp = 999
        m.awake = True
        w.level.monsters.append(m)
        w.player.weapon = WEAPONS["basilisk_maul"].copy()
        w.player_attack(m)
        self.assertEqual(m.poisoned, config.POISON_TURNS, "the venom takes hold")
        hp = m.hp
        m.take_turn(w)                        # a poisoned turn
        self.assertEqual(m.hp, hp - config.POISON_DMG, "the venom bites each turn")
        self.assertEqual(m.poisoned, config.POISON_TURNS - 1)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `py -3.13 -m unittest deathward.tests.TestPoison -v`
Expected: FAIL — `Monster` has no `poisoned`; nothing applies or ticks it.

- [ ] **Step 4: Add the status field and the tick**

In `deathward/monsters.py` `Monster.__init__`, next to `self.burning = 0`, add:

```python
        self.poisoned = 0         # a venom DoT (Basilisk Maul), ticks like burning
```

In `Monster.take_turn`, right after the `burning` block (before the `weak` block), add:

```python
        if self.poisoned > 0:
            self.poisoned -= 1
            world.hurt_monster(self, config.POISON_DMG, source="poison")
            if not self.alive:
                return
```

Ensure `config` is imported in `monsters.py` (it is — `HAMMER_STUN_CADENCE` is already read there; if not, add `from . import config`).

In `deathward/world.py` `_weapon_status_on`, add a poison branch (after the `fear` branch, before `lifesteal`):

```python
        if "poison" in traits and m.alive:
            m.poisoned = max(m.poisoned, config.POISON_TURNS)
            self.log("The %s is envenomed." % self._mname(m), (150, 220, 130))
            self.add_fx("impact", m.x, m.y, color=(150, 220, 130), radius=0.9, life=0.4)
```

(Basilisk Maul's `stun` half already resolves via the existing inline `stun` cadence block.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -3.13 -m unittest deathward.tests.TestPoison -v`
Expected: PASS.
Run: `py -3.13 -m deathward.tests`
Expected: PASS. If `MONSTER_SOURCES` or `TRAP_SOURCES` happen to contain `"poison"` (they should not — they are `{"orc"}` and the trap set), a poison kill would be miscredited; verify with `grep -n 'MONSTER_SOURCES\|TRAP_SOURCES' deathward/world.py` that `"poison"` is in neither.

- [ ] **Step 6: Commit**

```bash
git add deathward/config.py deathward/monsters.py deathward/world.py deathward/tests.py
git commit -m "Add a poisoned DoT; Basilisk Maul applies it"
```

---

### Task 7: Enrage — turn a monster on its neighbours (Betrayer's Edge)

An `enraged` monster spends its turns attacking the nearest creature — another monster, or the player. Betrayer's Edge applies it.

**Files:**
- Modify: `deathward/config.py` (`ENRAGE_CHANCE`, `ENRAGE_TURNS`)
- Modify: `deathward/monsters.py` (`Monster.__init__` add `self.enraged = 0`; `take_turn` add the enrage branch; add `_rampage`)
- Modify: `deathward/world.py` (`MONSTER_SOURCES` gains `"enrage"`; `_weapon_status_on` applies enrage)
- Test: `deathward/tests.py` (new `TestEnrage` class)

**Interfaces:**
- Consumes: `config.ENRAGE_CHANCE`, `config.ENRAGE_TURNS`; `Monster._hit`, `Monster._step_toward`, `Monster.dist`; `World.hurt_monster`.
- Produces: `Monster.enraged: int`; `Monster._rampage(world)` — attacks/moves toward the nearest creature, hitting a monster with `source="enrage"` or the player via `_hit`.

- [ ] **Step 1: Add the config constants**

In `deathward/config.py`:

```python
ENRAGE_CHANCE       = 0.20        # Betrayer's Edge: chance to send the struck thing berserk
ENRAGE_TURNS        = 6           # turns it attacks whatever is nearest
```

- [ ] **Step 2: Write the failing test**

```python
class TestEnrage(unittest.TestCase):
    def _world(self):
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=3)
        w.level.monsters = []
        return w

    def test_betrayers_edge_enrages(self):
        from . import config
        from .items import WEAPONS
        from .monsters import Monster
        w = self._world()
        m = Monster("brute", w.player.x + 1, w.player.y); m.hp = m.max_hp = 999
        w.level.monsters.append(m)
        w.player.weapon = WEAPONS["betrayers_edge"].copy()
        old = config.ENRAGE_CHANCE
        config.ENRAGE_CHANCE = 1.0
        try:
            w.player_attack(m)
            self.assertEqual(m.enraged, config.ENRAGE_TURNS)
        finally:
            config.ENRAGE_CHANCE = old

    def test_an_enraged_monster_strikes_its_neighbour(self):
        from .monsters import Monster
        w = self._world()
        p = w.player
        rager = Monster("brute", p.x + 3, p.y); rager.hp = rager.max_hp = 999
        rager.awake = True
        victim = Monster("brute", p.x + 4, p.y); victim.hp = victim.max_hp = 999
        w.level.monsters = [rager, victim]
        rager.enraged = 3
        vhp = victim.hp
        rager.take_turn(w)          # adjacent to victim -> hits it
        self.assertLess(victim.hp, vhp, "the enraged one turned on its neighbour")
        self.assertEqual(rager.enraged, 2, "and the rage ticks down")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `py -3.13 -m unittest deathward.tests.TestEnrage -v`
Expected: FAIL — no `enraged` field / `_rampage`.

- [ ] **Step 4: Implement the state, the branch, and the rampage**

In `deathward/world.py`, change the `MONSTER_SOURCES` line (~line 44) to:

```python
MONSTER_SOURCES = {"orc", "enrage"}
```

In `deathward/monsters.py` `Monster.__init__`, next to `self.confused = 0`, add:

```python
        self.enraged = 0          # turns spent attacking whatever is nearest (Betrayer's Edge)
```

In `Monster.take_turn`, add the enrage branch right after the `confused` block (before the `fn = getattr(...)` dispatch):

```python
        # Betrayer's Edge: it lashes at the nearest thing -- another monster, or you.
        if self.enraged > 0:
            self.enraged -= 1
            self.intent = None
            self._rampage(world)
            return
```

Add the `_rampage` method near `_wander`:

```python
    def _rampage(self, world):
        """Enraged: strike the nearest creature. Another monster if one is closer than
        the player (no kill credit -- source 'enrage'); otherwise lash at the player."""
        p = world.player
        pd = self.dist(p.x, p.y)
        best, bd = None, 10 ** 9
        for o in world.level.monsters:
            if o is self or not o.alive:
                continue
            d = self.dist(o.x, o.y)
            if d < bd:
                best, bd = o, d
        if best is not None and bd <= pd:
            if bd <= 1:
                dmg = int(round(world.rng.randint(self.t.lo, self.t.hi)))
                world.log("The %s turns on the %s!"
                          % (world._mname(self), world._mname(best)), (176, 120, 132))
                world.hurt_monster(best, dmg, source="enrage")
            else:
                self._step_toward(world, best.x, best.y)
            return
        if pd <= 1:
            self._hit(world, verb="lashes wildly at")
        else:
            self._step_toward(world, p.x, p.y)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -3.13 -m unittest deathward.tests.TestEnrage -v`
Expected: PASS.
Run: `py -3.13 -m deathward.tests`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add deathward/config.py deathward/monsters.py deathward/world.py deathward/tests.py
git commit -m "Add the enraged state; Betrayer's Edge turns a monster on its own"
```

---

### Task 8: Anti-incorporeal — Fulgurite scours ghosts

Mark wraith and poltergeist as incorporeal; Fulgurite (`("cleave","shock")`) deals ×1.5 damage to them, on the primary and on each cleaved ghost.

**Files:**
- Modify: `deathward/config.py` (`FULGURITE_INCORP_MULT`)
- Modify: `deathward/monsters.py` (module-level `INCORPOREAL` set + `is_incorporeal` helper)
- Modify: `deathward/world.py` (`player_attack` — apply the multiplier on the primary and in the cleave loop)
- Test: `deathward/tests.py` (new `TestAntiIncorporeal` class)

**Interfaces:**
- Consumes: `config.FULGURITE_INCORP_MULT`.
- Produces: `monsters.INCORPOREAL: set[str]` == `{"wraith", "poltergeist"}`; `monsters.is_incorporeal(key) -> bool`.

- [ ] **Step 1: Add the constant**

In `deathward/config.py`:

```python
FULGURITE_INCORP_MULT = 1.5       # Fulgurite's bonus vs wraith/poltergeist
```

- [ ] **Step 2: Write the failing test**

```python
class TestAntiIncorporeal(unittest.TestCase):
    def _world(self):
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=3)
        w.level.monsters = []
        return w

    def test_incorporeal_set(self):
        from .monsters import is_incorporeal
        self.assertTrue(is_incorporeal("wraith"))
        self.assertTrue(is_incorporeal("poltergeist"))
        self.assertFalse(is_incorporeal("brute"))

    def test_fulgurite_hits_ghosts_harder(self):
        from .items import WEAPONS
        from .monsters import Monster
        # a fixed roll: pin both attacks to the same base damage, compare corporeal vs not
        w = self._world()
        w.player.weapon = WEAPONS["fulgurite"].copy()
        brute = Monster("brute", w.player.x + 1, w.player.y); brute.hp = brute.max_hp = 999
        wraith = Monster("wraith", w.player.x - 1, w.player.y); wraith.hp = wraith.max_hp = 999
        w.level.monsters = [brute, wraith]
        # drive damage_roll deterministically by pinning the weapon band to a flat value
        w.player.weapon.lo = w.player.weapon.hi = 4
        b0, g0 = brute.hp, wraith.hp
        w.player_attack(brute)
        w.player_attack(wraith)
        self.assertEqual(b0 - brute.hp, 4, "brute takes the flat 4")
        self.assertEqual(g0 - wraith.hp, 6, "the wraith takes 4 x 1.5 = 6")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `py -3.13 -m unittest deathward.tests.TestAntiIncorporeal -v`
Expected: FAIL — `is_incorporeal` missing; the multiplier not applied.

- [ ] **Step 4: Add the marker and the multiplier**

In `deathward/monsters.py`, near the top-level definitions (after `TEMPLATES` or near `damage_multiplier`), add:

```python
INCORPOREAL = {"wraith", "poltergeist"}     # walk through walls, ignore armour


def is_incorporeal(key):
    return key in INCORPOREAL
```

In `deathward/world.py`, import the helper — change the monsters import line (~line 38) to include it:

```python
from .monsters import DIRS8, Monster, TEMPLATES, damage_multiplier, is_incorporeal
```

In `player_attack`, apply the multiplier to the **primary** damage just before `self.hurt_monster(m, dmg, source="player")`:

```python
        if "shock" in traits and is_incorporeal(m.key):
            dmg = int(round(dmg * config.FULGURITE_INCORP_MULT))
```

And in the `if "cleave" in traits:` loop, replace the `extra = max(1, dmg // 2)` line with:

```python
                    extra = max(1, dmg // 2)
                    if "shock" in traits and is_incorporeal(o.key):
                        extra = int(round(extra * config.FULGURITE_INCORP_MULT))
```

(Note: `dmg` at the cleave point is already the primary's possibly-boosted value; halving it is fine — the per-neighbour boost is re-applied for ghost neighbours.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -3.13 -m unittest deathward.tests.TestAntiIncorporeal -v`
Expected: PASS.
Run: `py -3.13 -m deathward.tests`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add deathward/config.py deathward/monsters.py deathward/world.py deathward/tests.py
git commit -m "Fulgurite deals x1.5 to incorporeal monsters (wraith, poltergeist)"
```

---

### Task 9: Void instakill (Scimitar of the Void)

A chance on hit to delete a monster outright — no body, no loot. Bosses are immune (the Warden, and any future mini-boss key).

**Files:**
- Modify: `deathward/config.py` (`VOID_KILL_CHANCE`)
- Modify: `deathward/world.py` (`BOSS_KEYS` set; `_void_immune`; `void_monster`; the void branch in `player_attack`)
- Test: `deathward/tests.py` (new `TestVoidScimitar` class)

**Interfaces:**
- Consumes: `config.VOID_KILL_CHANCE`.
- Produces: `World.BOSS_KEYS`-style guard via `World._void_immune(m) -> bool`; `World.void_monster(m)` removes `m` with kill credit but no `Slain` body and no loot.

- [ ] **Step 1: Add the constant**

In `deathward/config.py`:

```python
VOID_KILL_CHANCE    = 0.10        # Scimitar of the Void: chance to unmake outright
```

- [ ] **Step 2: Write the failing test**

```python
class TestVoidScimitar(unittest.TestCase):
    def _world(self):
        codex = FakeSave(); codex.world_seed = 3
        w = World(codex, seed=3)
        w.level.monsters = []
        w.level.slain = []
        return w

    def test_void_deletes_with_no_body_or_loot(self):
        from . import config
        from .items import WEAPONS
        from .monsters import Monster
        w = self._world()
        m = Monster("brute", w.player.x + 1, w.player.y); m.hp = m.max_hp = 999
        w.level.monsters = [m]
        w.player.weapon = WEAPONS["void_scimitar"].copy()
        old = config.VOID_KILL_CHANCE
        config.VOID_KILL_CHANCE = 1.0
        try:
            w.player_attack(m)
        finally:
            config.VOID_KILL_CHANCE = old
        self.assertNotIn(m, w.level.monsters, "the monster is gone")
        self.assertEqual(len(w.level.slain), 0, "no body, no loot")

    def test_the_warden_is_void_immune(self):
        from . import config
        from .items import WEAPONS
        from .monsters import Monster
        w = self._world()
        boss = Monster("warden", w.player.x + 1, w.player.y); boss.hp = boss.max_hp = 999
        w.level.monsters = [boss]
        w.player.weapon = WEAPONS["void_scimitar"].copy()
        old = config.VOID_KILL_CHANCE
        config.VOID_KILL_CHANCE = 1.0
        try:
            w.player_attack(boss)
        finally:
            config.VOID_KILL_CHANCE = old
        self.assertIn(boss, w.level.monsters, "you cannot void the Warden")
        self.assertLess(boss.hp, 999, "it takes ordinary damage instead")
```

- [ ] **Step 3: Run test to verify it fails**

Run: `py -3.13 -m unittest deathward.tests.TestVoidScimitar -v`
Expected: FAIL — no void handling.

- [ ] **Step 4: Implement the void path**

In `deathward/world.py`, near the top-level constants (next to `MONSTER_SOURCES`), add:

```python
BOSS_KEYS = {"warden"}      # void-immune; the mini-boss task adds its keys here
```

Add two methods to `World` (near `kill_monster`):

```python
    def _void_immune(self, m):
        """The void cannot swallow a boss (the Warden, or a mini-boss)."""
        return m.key in BOSS_KEYS

    def void_monster(self, m):
        """Unmake a monster: removed outright, no body, no loot -- the cost that
        balances the Scimitar. Still counts as your kill."""
        if m not in self.level.monsters:
            return
        self.level.monsters.remove(m)
        self.player.kills += 1
        self.run_kills += 1
        self.codex.stats["kills"] += 1
        self.codex.stats["kills_by"][m.key] = self.codex.stats["kills_by"].get(m.key, 0) + 1
        self.log("The %s is unmade -- the void takes it whole. Nothing remains."
                 % self._mname(m), config.MANA)
        self.add_fx("vanish", m.x, m.y, color=(120, 100, 190), life=0.5)
```

In `player_attack`, add the void roll immediately after the `coat` handling and before the "You hit" log (so a voided monster is never logged as merely hit). Place it right after the `p.blade_coat = None` line:

```python
        if ("void" in traits and m.alive and not self._void_immune(m)
                and self.rng.random() < config.VOID_KILL_CHANCE):
            self.log("The Scimitar passes through the %s and it is simply gone."
                     % self._mname(m), config.MANA)
            self.add_fx("vanish", m.x, m.y, color=(120, 100, 190), life=0.5)
            self.void_monster(m)
            return
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -3.13 -m unittest deathward.tests.TestVoidScimitar -v`
Expected: PASS.
Run: `py -3.13 -m deathward.tests`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add deathward/config.py deathward/world.py deathward/tests.py
git commit -m "Add the void instakill; Scimitar of the Void, bosses immune"
```

---

### Task 10: Sprites for the ten new weapons

Give every new key a `_weapon_sprite` branch so the Gear tab and floor drops render them, tinted to their element. The acceptance test is that every `WEAPONS` key renders without raising.

**Files:**
- Modify: `deathward/sprites.py` (`_weapon_sprite` — add ten branches before the trailing `rapier`/`brand`/`kris` branches)
- Modify: `deathward/tests.py` (`TestWeaponSprites` — iterate all `WEAPONS` keys)

**Interfaces:**
- Consumes: existing sprite helpers `_line(s, color, (x1,y1), (x2,y2), width)`, `_poly(s, color, points)`, `_circ(s, color, x, y, r)`, `_shade(color, factor)`, `_w_blade(s, S, blade, hilt, guard)`, and `pygame.draw.rect`.
- Produces: a rendered surface for each of the ten new keys.

- [ ] **Step 1: Make the sprite test cover every roster key**

Replace the body of `TestWeaponSprites.test_every_weapon_key_renders_without_error` in `deathward/tests.py` with a loop over the roster:

```python
class TestWeaponSprites(unittest.TestCase):
    def test_every_weapon_key_renders_without_error(self):
        import pygame
        from .items import WEAPONS
        from .sprites import _weapon_sprite
        pygame.init()
        S = 48
        for key in WEAPONS:
            surf = pygame.Surface((S, S), pygame.SRCALPHA)
            _weapon_sprite(key, surf, S)   # must not raise
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3.13 -m unittest deathward.tests.TestWeaponSprites -v`
Expected: FAIL — the ten new keys hit no branch; if `_weapon_sprite` has no default it draws nothing (pass) or raises. If it passes trivially (silent blank), still add the branches in Step 3 so the weapons are legible, then the test stays green.

- [ ] **Step 3: Add the ten sprite branches**

In `deathward/sprites.py`, inside `_weapon_sprite`, just before the existing `if key == "rapier":` branch, add these branches. They reuse the element tints and the existing helpers:

```python
    ELEM = {
        "fire":  ((236, 120, 60), (120, 50, 30)),      # (bright, dark)
        "ice":   ((170, 220, 255), (70, 110, 160)),
        "blood": ((200, 60, 70), (90, 25, 35)),
        "venom": ((150, 220, 130), (50, 110, 60)),
        "storm": ((240, 226, 120), (150, 120, 40)),
        "void":  ((150, 120, 200), (40, 25, 70)),
        "steel": ((216, 224, 236), (60, 62, 72)),
    }
    cx = S * 0.5

    if key == "brand":                       # fire sword
        bright, dark = ELEM["fire"]
        _w_blade(s, S, bright, dark, _shade(bright, 0.8))
        _line(s, _shade(bright, 1.2), (cx, S * 0.20), (cx, S * 0.60), S * 0.02)
        return
    if key == "winters_edge":                # ice sword
        bright, dark = ELEM["ice"]
        _w_blade(s, S, bright, dark, _shade(bright, 0.8))
        return
    if key == "sacrificial_dagger":          # short blood dagger
        bright, dark = ELEM["blood"]
        _poly(s, bright, [(cx, S * 0.18), (cx + S * 0.06, S * 0.55),
                          (cx, S * 0.62), (cx - S * 0.06, S * 0.55)])
        _line(s, dark, (cx, S * 0.62), (cx, S * 0.82), S * 0.05)
        _line(s, dark, (cx - S * 0.10, S * 0.66), (cx + S * 0.10, S * 0.66), S * 0.04)
        return
    if key == "betrayers_edge":              # dark serrated sword
        bright, dark = ELEM["void"]
        _w_blade(s, S, _shade(bright, 1.1), dark, _shade(bright, 0.7))
        return
    if key == "fulgurite":                   # storm axe
        bright, dark = ELEM["storm"]
        _line(s, dark, (cx - S * 0.02, S * 0.16), (cx - S * 0.02, S * 0.90), S * 0.055)
        head = [(cx - S * 0.06, S * 0.16), (cx + S * 0.10, S * 0.13),
                (cx + S * 0.30, S * 0.24), (cx + S * 0.34, S * 0.40),
                (cx + S * 0.06, S * 0.36), (cx - S * 0.06, S * 0.34)]
        _poly(s, bright, head)
        _line(s, _shade(bright, 1.3), (cx + S * 0.10, S * 0.18),
              (cx + S * 0.30, S * 0.30), S * 0.02)
        return
    if key == "windfang":                    # light, swift blade
        bright, dark = ELEM["steel"]
        _w_blade(s, S, bright, _shade(dark, 1.4), _shade(bright, 0.85))
        _line(s, _shade(bright, 1.2), (cx - S * 0.12, S * 0.30),
              (cx - S * 0.22, S * 0.24), S * 0.02)
        return
    if key == "pyroclast":                   # molten greataxe (double head)
        bright, dark = ELEM["fire"]
        _line(s, dark, (cx, S * 0.14), (cx, S * 0.92), S * 0.06)
        _poly(s, bright, [(cx, S * 0.16), (cx + S * 0.34, S * 0.26),
                          (cx + S * 0.30, S * 0.44), (cx, S * 0.40)])
        _poly(s, _shade(bright, 0.8), [(cx, S * 0.16), (cx - S * 0.34, S * 0.26),
                                       (cx - S * 0.30, S * 0.44), (cx, S * 0.40)])
        return
    if key == "glacial_flail":               # ice flail (chain + head)
        bright, dark = ELEM["ice"]
        _line(s, _shade(dark, 1.3), (cx, S * 0.88), (cx, S * 0.42), S * 0.04)
        _circ(s, bright, cx, S * 0.30, S * 0.16)
        _circ(s, _shade(bright, 1.3), cx - S * 0.05, S * 0.25, S * 0.04)
        return
    if key == "reapers_whisper":             # scythe
        bright, dark = ELEM["void"]
        _line(s, dark, (cx + S * 0.10, S * 0.14), (cx - S * 0.06, S * 0.92), S * 0.05)
        _poly(s, bright, [(cx + S * 0.10, S * 0.16), (cx - S * 0.28, S * 0.20),
                          (cx - S * 0.10, S * 0.30), (cx + S * 0.10, S * 0.28)])
        return
    if key == "basilisk_maul":               # venom mace
        bright, dark = ELEM["venom"]
        _line(s, _shade(dark, 1.2), (cx, S * 0.90), (cx, S * 0.42), S * 0.06)
        _circ(s, bright, cx, S * 0.30, S * 0.17)
        for a in (0.0, 0.25, 0.5, 0.75):
            import math
            ang = a * 2 * 3.14159
            _circ(s, _shade(bright, 0.7),
                  cx + math.cos(ang) * S * 0.17, S * 0.30 + math.sin(ang) * S * 0.17,
                  S * 0.03)
        return
    if key == "void_scimitar":               # curved void blade
        bright, dark = ELEM["void"]
        _poly(s, bright, [(cx - S * 0.10, S * 0.20), (cx + S * 0.26, S * 0.34),
                          (cx + S * 0.18, S * 0.52), (cx - S * 0.12, S * 0.44)])
        _line(s, dark, (cx - S * 0.12, S * 0.44), (cx - S * 0.16, S * 0.84), S * 0.05)
        return
```

(If a helper name differs in the current `sprites.py`, adjust to the real one — the surrounding branches show the exact signatures. Keep each branch to the helpers already used by `rapier`/`brand`/`kris`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.13 -m unittest deathward.tests.TestWeaponSprites -v`
Expected: PASS — all thirteen magical keys (and the ordinary ones) render without raising.
Run: `py -3.13 -m deathward.tests`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deathward/sprites.py deathward/tests.py
git commit -m "Sprites for the ten new magical weapons"
```

---

### Task 11: Expose the roster on the CTRL+12 weapon bench

The bench (`cheat_equip_weapon`) already accepts any `WEAPONS` key — so this task is about the picker UI listing the magical weapons. Confirm the backend, then extend the on-screen key list.

**Files:**
- Modify: `deathward/ui.py` (the weapon-cheat picker's key list — search for `draw_weapon_cheat`)
- Test: `deathward/tests.py` (extend `TestWeaponBench` with a magical pick)

**Interfaces:**
- Consumes: `World.cheat_equip_weapon(key, bonus=0)` (already accepts any `WEAPONS` key).
- Produces: the CTRL+12 picker offers all thirteen magical keys in addition to the nine ordinary ones.

- [ ] **Step 1: Write the failing test**

```python
    def test_bench_equips_a_magical_weapon(self):     # add inside TestWeaponBench
        w = self._world()
        w.cheat_equip_weapon("void_scimitar", 0)
        self.assertEqual(w.player.weapon.key, "void_scimitar")
        self.assertEqual(w.player.weapon.traits, ("void",))
```

- [ ] **Step 2: Run test to verify it passes at the backend already**

Run: `py -3.13 -m unittest deathward.tests.TestWeaponBench.test_bench_equips_a_magical_weapon -v`
Expected: PASS — `cheat_equip_weapon` is key-agnostic. (If it fails, the backend filters to ordinary keys; remove that filter.)

- [ ] **Step 3: Add the magical keys to the picker UI**

Find the key list the picker renders. In `deathward/ui.py`, `draw_weapon_cheat` (and wherever the CTRL+12 handler builds the candidate keys — search `weapon_cheat` in `deathward/game.py`), extend the list so it includes the magical roster. Locate the ordinary list, e.g.:

```python
keys = ["%s_%s" % (m, t) for m in ("bone", "bronze", "steel")
        for t in ("sword", "axe", "hammer")]
```

and append the magical keys after it:

```python
keys += ["rapier", "brand", "betrayers_edge", "fulgurite", "winters_edge",
         "sacrificial_dagger", "windfang", "basilisk_maul", "pyroclast",
         "reapers_whisper", "kris", "glacial_flail", "void_scimitar"]
```

Apply the same change in both the UI render list and the input handler's selection list so the on-screen order and the keypress mapping match. Verify by reading both sites.

- [ ] **Step 4: Run the bench UI test and full suite**

Run: `py -3.13 -m unittest deathward.tests.TestWeaponBench deathward.tests.TestWeaponBenchUI -v`
Expected: PASS.
Run: `py -3.13 -m deathward.tests`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deathward/ui.py deathward/game.py deathward/tests.py
git commit -m "Weapon bench (CTRL+12) offers the full magical roster for testing"
```

---

### Task 12: Integration — full suite, bit-identical proof, and a playtest checklist

**Files:**
- Verify only (fix fallout where found): all of the above.

- [ ] **Step 1: Run the whole suite**

Run: `py -3.13 -m deathward.tests`
Expected: all green. Investigate and fix any failure — do not silence it. Likely spots: a test that hard-coded the old magical damage bands.

- [ ] **Step 2: Confirm the knowledge-is-information invariant explicitly**

Run: `py -3.13 -m unittest deathward.tests.TestKnowledgeIsNotPower -v`
Expected: PASS — the new combat RNG draws (freeze, fear, enrage, void) only happen when the wielded weapon carries that trait, at a fixed point, so blind and omniscient runs of a seed stay bit-identical. (If it fails, an effect is drawing RNG unconditionally or reading Kodex state.)

- [ ] **Step 3: Manual playtest checklist (record results in the PR description)**

Run: `py run_deathward.py`, open the CTRL+12 bench, and verify:
- Each magical weapon equips and shows its name and band; Windfang and the Void Scimitar read as flat ("5 dmg" / "7 dmg").
- Pyroclast/Glacial Flail/Reaper's Whisper/Vampiric Kris hit a clustered group and the element lands on every body (fire/freeze/rout/heal-per-body).
- Winter's Edge sometimes freezes; Basilisk Maul poisons (damage ticks after the blow) and staggers.
- Betrayer's Edge sends a monster berserk — it attacks its neighbours.
- Fulgurite visibly hits wraiths/poltergeists harder.
- Scimitar of the Void occasionally deletes a monster with no body left behind; it never deletes the Warden.
- All ten new sprites read distinctly in the Gear tab.

- [ ] **Step 4: Final commit (if any fixes were needed)**

```bash
git add -A
git commit -m "Integration fixes for the magical roster and combat"
```

## Self-Review Notes (author)

- **Spec coverage (Plan-1 slice):** Tier 5 + power ordering (Task 2) ✓; the 13 weapons with bands/traits/shapes (Task 2) ✓; the focused-vs-unleashed cleave-carries-element rule (Task 5) ✓; reused traits crit/burn/lifesteal/cleave/stun (Tasks 3–4) ✓; the new mechanics freeze (Task 4), fear (Task 4), poison DoT (Task 6), enrage (Task 7), anti-incorporeal (Task 8), void (Task 9) ✓; flat-damage display (Task 1) ✓; sprites (Task 10) ✓; cheat-bench exposure (Task 11) ✓; bit-identical invariant (Task 12) ✓.
- **Deferred to later plans (not here):** `roll_floor_weapon`/two-slot generation, the rarity curve, enhanced-Steel-deep, enchant-scroll weighting → **Plan 2**. The magical-weapon ledger, absolute uniqueness, world-persistence, the collector's achievement, and the Planescape respawn homage → **Plan 3**. Richer Kodex mechanic-facts also ride with Plan 3's Kodex work; this plan relies on the existing Gear-tab discovery (`see_gear`) for the weapons to appear.
- **Type consistency:** `Weapon.traits` (tuple) and `Weapon.has()` defined in Task 1 are used by every combat task; `_weapon_status_on(m, dmg)` defined in Task 4 is reused in Task 5; `is_incorporeal` (Task 8), `void_monster`/`_void_immune` (Task 9) match their call sites.
- **Known tunables (playtest):** every `config` constant added here (freeze/fear/enrage chances & durations, poison turns/damage, Fulgurite ×1.5, void 10%) and every damage band.
