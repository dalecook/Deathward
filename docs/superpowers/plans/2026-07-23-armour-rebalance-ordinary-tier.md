# Armour Rebalance — Ordinary Tier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean-slate armour into a four-rung leather/mail/plate ladder that shares the speed budget with boots, move it to generation-placed found-only gear with a masterwork bonus on deep floors, rework floor 1 into a coin-flip gift, and narrow the vendor to consumables.

**Architecture:** Armour joins weapons' per-instance `bonus` model (a `bonus` field + `copy()`), so `player.defense` reads it, the DWEN scroll raises it, and deep floors (8–15) can layer a masterwork +1/+2 onto the piece `roll_floor_armour` places. Armour leaves `gear_pool()` entirely (like weapons and boots), so all three slots are generation-placed and containers hold only gold and consumables. Loot tuples widen to `("gear", key, bonus)` with tolerant unpacking, closing the long-deferred bonus-loss edge.

**Tech Stack:** Python 3.13, stdlib `unittest`, `pygame` (sprites only). No new dependencies.

## Global Constraints

- **Test command:** `py -3.13 -m deathward.tests` (Python 3.13 — 3.14 has no pygame). Every task's verify steps use this.
- **Determinism invariant:** every `roll_*` function draws only from `(rng, depth)` — never the Kodex — so a seed's floors are bit-identical for a blind and an omniscient hero (`TestKnowledgeIsNotPower`). Never read Kodex state inside a roll.
- **Armour keys are bare** (`leather`/`mail`/`plate`); boots keep their `boots_`-prefix. No clobber in the flat `ALL_GEAR` namespace.
- **Boots carry no bonus** — only weapons and (now) armour have a per-instance `bonus`.
- **Masterwork caps at +2** (never +3). The DWEN scroll stays uncapped.
- **Numbers are playtest-tunable** but ship at the exact values in this plan.

---

### Task 1: Armour joins the per-instance bonus model

Pull armour off the player-side `enchants` dict onto a per-instance `Armour.bonus`, mirroring `Weapon`. This is the enabling refactor for masterwork armour and the loot-tuple closure.

**Files:**
- Modify: `deathward/items.py` (the `Armour` class, ~lines 70–81)
- Modify: `deathward/player.py` (`__init__` 64–66/86, `defense` 114–122, `equip` 136–144, `gear_display` 150–161, `to_dict` 164–172, `from_dict` 174–185)
- Modify: `deathward/world.py` (`enchant_armour`, ~lines 1887–1892)
- Modify: `deathward/config.py` (`RUN_SAVE_VERSION`, line 46)
- Test: `deathward/tests.py` (rewrite the player-serialization test ~7779/7796; add a new bonus test)

**Interfaces:**
- Produces: `Armour.bonus` (int, default 0); `Armour.copy(bonus=None) -> Armour`; `Armour.desc(bonus=None) -> str` reading `self.bonus` when `bonus is None`. `player.defense` includes `self.armour.bonus`. `Player.to_dict()["armour"] == {"key": str, "bonus": int}`. The `enchants` attribute and dict are removed.

- [ ] **Step 1: Write the failing test** — replace the `enchants` block in the existing player round-trip test and add a defense/DWEN test.

In `deathward/tests.py`, find the player serialization test (around line 7779). Replace the two `enchants` lines:

```python
        p.enchants = {"plate": 2}
```
with:
```python
        p.armour = ALL_GEAR["plate"].copy(bonus=2)
```
and replace (around line 7796):
```python
        self.assertEqual(q.enchants, {"plate": 2})
```
with:
```python
        self.assertEqual(q.armour.key, "plate")
        self.assertEqual(q.armour.bonus, 2)
```

Then add a new test class near the other player tests:

```python
class TestArmourBonusModel(unittest.TestCase):
    def test_defense_reads_the_per_instance_armour_bonus(self):
        from .items import ALL_GEAR
        from .player import Player
        p = Player()
        p.armour = ALL_GEAR["plate"].copy(bonus=2)     # Full Plate +2
        self.assertEqual(p.defense, ALL_GEAR["plate"].defense + 2)

    def test_enchant_armour_scroll_raises_the_bonus(self):
        from .items import ALL_GEAR
        codex = FakeSave()
        w = World(codex, seed=3)
        w.player.armour = ALL_GEAR["plate"].copy()      # +0
        before = w.player.defense
        w._apply_effect("enchant_armour")
        self.assertEqual(w.player.armour.bonus, 1)
        self.assertEqual(w.player.defense, before + 1)
```

> Note: confirm the scroll-effect entry point is named `_apply_effect`. Grep `deathward/world.py` for `def _apply_effect` (the method containing the `elif effect == "enchant_armour":` arm at ~line 1882). If it differs, call the correct method with the effect string.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -3.13 -m deathward.tests`
Expected: FAIL — `Armour` has no `copy`/`bonus`; `enchants` still referenced.

- [ ] **Step 3: Give `Armour` a per-instance bonus** (`deathward/items.py`)

Replace the `Armour` class body:

```python
class Armour:
    slot = "armour"

    def __init__(self, key, name, tier, defense, speed_mod=0, trait=None, note="",
                 bonus=0):
        self.key, self.name, self.tier = key, name, tier
        self.defense, self.speed_mod, self.trait, self.note = defense, speed_mod, trait, note
        self.bonus = bonus                # masterwork + scroll enchant, per-instance

    def copy(self, bonus=None):
        return Armour(self.key, self.name, self.tier, self.defense, self.speed_mod,
                      self.trait, self.note,
                      self.bonus if bonus is None else bonus)

    def desc(self, bonus=None):
        b = self.bonus if bonus is None else bonus
        s = "%d def" % (self.defense + b)
        if self.speed_mod:
            s += ", %+d spd" % self.speed_mod
        return s + ("  |  " + self.note if self.note else "")
```

- [ ] **Step 4: Wire the player** (`deathward/player.py`)

In `__init__`, make the starter armour a per-instance copy and delete the `enchants` line:

```python
        self.armour = ARMOURS[STARTING[1]].copy()
```
Delete:
```python
        self.enchants = {}        # gear-key -> permanent +bonus (enchant scrolls)
```

In `defense` (property), drop the `enchants` term:

```python
    @property
    def defense(self):
        d = self.armour.defense + self.armour.bonus + self.boots.defense
        if self.stoneskin > 0:
            d += self.STONESKIN_DEF
        if self.heroism > 0:
            d += 3
        return d
```

In `equip`, copy armour like the weapon so the equipped instance is private:

```python
        elif gear.slot == "armour":
            old, self.armour = self.armour, gear.copy()
```

In `gear_display`, read `armour.bonus` (unify with the weapon path):

```python
    def gear_display(self, slot):
        """(name, desc) for an equipped slot. Weapon and armour keep their +n on the
        instance; boots carry no bonus."""
        g = {"weapon": self.weapon, "armour": self.armour, "boots": self.boots}[slot]
        if slot == "boots":
            return g.name, g.desc()
        n = g.bonus
        name = "%s +%d" % (g.name, n) if n else g.name
        return name, g.desc()
```

In `to_dict`, store armour as key+bonus and drop the enchants line:

```python
        d["armour"] = {"key": self.armour.key, "bonus": self.armour.bonus}
```
Delete:
```python
        d["enchants"] = dict(self.enchants)
```

In `from_dict`, rebuild the armour instance and drop the enchants line:

```python
        a = data["armour"]
        p.armour = ALL_GEAR[a["key"]].copy(bonus=a["bonus"])
```
Delete:
```python
        p.enchants = dict(data["enchants"])
```

- [ ] **Step 5: Point the DWEN scroll at the instance** (`deathward/world.py`, ~1887)

```python
        elif effect == "enchant_armour":
            p.armour.bonus += 1
            self.log("Your %s hardens with a light of its own. +%d defence, for good."
                     % (p.armour.name, p.armour.bonus), config.GOLD)
            self.add_fx("pulse", p.x, p.y, color=config.GOLD, life=0.6)
```

- [ ] **Step 6: Bump the run-save version** (`deathward/config.py`, line 46)

```python
RUN_SAVE_VERSION = 2
```
The load guard (suspend-resume Phase 2) already discards a run block whose version does not match, so a pre-change suspended run is dropped gracefully — the armour save-shape change and the removed keys (Task 2) are both covered by this one bump.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `py -3.13 -m deathward.tests`
Expected: PASS (full suite green — grep first for any other `.enchants` references with `grep -rn "enchants" deathward/` and confirm none remain outside comments).

- [ ] **Step 8: Commit**

```bash
git add deathward/items.py deathward/player.py deathward/world.py deathward/config.py deathward/tests.py
git commit -m "Armour joins the per-instance bonus model (retire the enchants dict)"
```

---

### Task 2: The ordinary ladder — rewrite ARMOURS + mail sprite

Replace the seven-piece table with the four-rung ladder and give the new Mail Shirt a sprite. `thorn`/`silk` trait-handling code stays dormant for the future magical roster.

**Files:**
- Modify: `deathward/items.py` (`ARMOURS`, lines 161–171)
- Modify: `deathward/sprites.py` (add a `"mail"` branch in `gear()`, near line 1108)
- Test: `deathward/tests.py` (rewrite the silk-swap test ~1312 and the scale-sprite test ~1443; add ladder-stat tests)

**Interfaces:**
- Produces: `ARMOURS` keys `rags`/`leather`/`mail`/`plate` only. `leather` = +2 def/0 spd (tier 1), `mail` = +3/−10 (tier 2), `plate` = +4/−20 (tier 3), `rags` = 0/0 (tier 0). `sprites.gear("mail")` renders grey.

- [ ] **Step 1: Write the failing tests**

Add a ladder-stat test class in `deathward/tests.py`:

```python
class TestArmourLadder(unittest.TestCase):
    def test_the_four_rungs_have_the_agreed_stats(self):
        from .items import ARMOURS
        expected = {
            "rags":    (0, 0, 0),
            "leather": (1, 2, 0),
            "mail":    (2, 3, -10),
            "plate":   (3, 4, -20),
        }
        self.assertEqual(set(ARMOURS), set(expected), "exactly the four-rung ladder")
        for key, (tier, defense, speed) in expected.items():
            a = ARMOURS[key]
            self.assertEqual((a.tier, a.defense, a.speed_mod), (tier, defense, speed), key)

    def test_the_trait_armours_are_gone(self):
        from .items import ARMOURS
        for gone in ("scale", "chain", "thorn", "silk"):
            self.assertNotIn(gone, ARMOURS, "%s graduated / retired" % gone)
```

Rewrite the explicit-downgrade test (around line 1312) — `silk` is gone, so use a real tradeoff downgrade (Full Plate → Leather Jerkin):

```python
    def test_an_explicit_choice_may_downgrade_you_if_you_insist(self):
        from .items import ALL_GEAR
        codex = FakeSave()
        w = World(codex, seed=6)
        w.player.armour = ALL_GEAR["plate"].copy()        # +4 def, heavy
        self._chest_under_player(w, [("gear", "leather")])  # +2 def, but fast
        w.take_option(0)
        self.assertEqual(w.player.armour.key, "leather",
                         "if the player picks it deliberately, give it to them")
```

Repoint the sprite test (around line 1443) from `scale` to the new `mail`:

```python
        r, g, b = average(sprites.gear("mail"))
        self.assertLess(max(r, g, b) - min(r, g, b), 22,
                        "mail must be GREY: its channels should be near-equal "
                        "(got %.0f/%.0f/%.0f)" % (r, g, b))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -3.13 -m deathward.tests`
Expected: FAIL — `mail`/`leather` stats wrong, `scale`/`chain`/`thorn`/`silk` still present, `sprites.gear("mail")` unhandled.

- [ ] **Step 3: Rewrite the ARMOURS table** (`deathward/items.py`)

```python
ARMOURS = {
    # A clean four-rung leather/mail/plate ladder sharing the material vocabulary of
    # ordinary boots. A sidegrade tradeoff, not a power ladder: more defense costs more
    # speed, and armour + boots spend from the SAME speed budget. No traits -- thorns and
    # wraithsilk graduate to the magical roster.
    "rags":    Armour("rags", "Padded Rags", 0, 0),
    "leather": Armour("leather", "Leather Jerkin", 1, 2, 0),
    "mail":    Armour("mail", "Mail Shirt", 2, 3, -10),
    "plate":   Armour("plate", "Full Plate", 3, 4, -20),
}
```

- [ ] **Step 4: Add the Mail Shirt sprite** (`deathward/sprites.py`)

The `"chain"` branch (grey rings) is the right visual for a mail shirt. Add a `"mail"` branch immediately after the `"leather"` branch (around line 1100), reusing the rings pattern in a grey steel:

```python
    elif key == "mail":                     # grey chainmail rings
        steel = (138, 144, 156)
        cuirass(steel, _shade(steel, 0.6))
        for row in range(5):
            for col in range(5):
                x = cx - S * 0.18 + col * S * 0.09 + (S * 0.045 if row % 2 else 0)
                y = S * 0.34 + row * S * 0.10
                pygame.draw.circle(s, _shade(steel, 1.3), (int(x), int(y)),
                                   int(S * 0.028), int(S * 0.012))
```

Leave the dead `scale`/`chain`/`thorn`/`silk` branches in place — `thorn`/`silk` sprites will be reused when those graduate to the magical roster.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `py -3.13 -m deathward.tests`
Expected: PASS. If the run flags an unrelated armour-key reference, grep `grep -rn '"scale"\|"chain"\|"thorn"\|"silk"' deathward/` and confirm the only remaining live references are the dormant sprite/trait branches and the `codex.py` lore line (all harmless).

- [ ] **Step 6: Commit**

```bash
git add deathward/items.py deathward/sprites.py deathward/tests.py
git commit -m "Ordinary armour ladder: rags/leather/mail/plate, four rungs, + mail sprite"
```

---

### Task 3: Floor 1 — the coin-flip gift, and retire the Bone Axe

Floor 1 places no random gear; its one guaranteed gift is a 50/50 Bone Sword or Leather Jerkin.

**Files:**
- Modify: `deathward/items.py` (`roll_ordinary`, lines 502–515)
- Modify: `deathward/dungeon.py` (floor-1 gift block, lines 631–643; import line 29)
- Test: `deathward/tests.py` (rewrite the three bone-axe floor-1 tests ~5924/5963/6005; add a coin-flip test)

**Interfaces:**
- Produces: `roll_ordinary(rng, 1) is None` (floor 1 places no random weapon). Floor 1's only gear is a `Drop(kind="gear", payload in {"bone_sword","leather"}, gift="floor1")`.

- [ ] **Step 1: Write the failing tests**

Rewrite `test_floor_one_is_always_an_unenhanced_bone_axe` (around line 5924):

```python
    def test_floor_one_places_no_random_weapon(self):
        import random
        from .items import roll_floor_weapons
        for seed in range(50):
            self.assertEqual(roll_floor_weapons(random.Random(seed), 1), [],
                             "floor 1's only gear is the coin-flip gift")
```

Rewrite `test_floor_one_is_a_single_bone_axe` (around line 5963):

```python
    def test_floor_one_places_no_random_weapon(self):
        import random
        from .items import roll_floor_weapons
        for s in range(30):
            self.assertEqual(roll_floor_weapons(random.Random(s), 1), [])
```

Rewrite `test_floor_one_always_has_exactly_one_bone_axe` (around line 6005):

```python
    def test_floor_one_has_no_bone_axe_only_the_gift(self):
        for seed in range(20):
            codex = FakeSave()
            codex.world_seed = seed
            w = World(codex, seed=seed)
            drops = self._weapon_drops(w.level)
            # the only weapon that can be on floor 1 is a Bone Sword gift (never the axe)
            self.assertLessEqual(len(drops), 1, "at most the coin-flip gift's sword")
            for d in drops:
                self.assertEqual(d.payload, "bone_sword")
                self.assertEqual(d.gift, "floor1")
```

Add a coin-flip test to `TestFloorOne`:

```python
    def test_the_floor_one_gift_is_a_bone_sword_or_leather_jerkin(self):
        seen = set()
        for ws in range(120):
            codex = FakeSave()
            codex.world_seed = ws
            w = World(codex, seed=1)
            gift = [d for d in w.level.drops if d.gift == "floor1"]
            self.assertEqual(len(gift), 1, "world %d has no gift" % ws)
            self.assertIn(gift[0].payload, ("bone_sword", "leather"))
            seen.add(gift[0].payload)
        self.assertEqual(seen, {"bone_sword", "leather"},
                         "both sides of the coin must appear across 120 worlds")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -3.13 -m deathward.tests`
Expected: FAIL — floor 1 still yields a Bone Axe; the gift is still pool-drawn armour.

- [ ] **Step 3: Retire the guaranteed Bone Axe** (`deathward/items.py`, `roll_ordinary`)

```python
def roll_ordinary(rng, depth):
    """Floors 2-7: the one ordinary weapon a floor may hold. Floor 1 places NO random
    weapon -- its only gear is the coin-flip gift (Bone Sword or Leather Jerkin), placed
    in dungeon.py. Returns (key, bonus) or None."""
    if depth == 1:
        return None
    if rng.random() >= 0.80:
        return None
    material = "bone" if depth <= 2 else "bronze" if depth <= 4 else "steel"
    wtype = rng.choice(["sword", "axe", "hammer"])
    bonus = 0
    if rng.random() < (depth - 1) * 0.10:          # 10% on 2 ... 60% on 7
        bonus = 2 if rng.random() < 0.25 else 1
    return ("%s_%s" % (material, wtype), bonus)
```

- [ ] **Step 4: Replace the floor-1 gift block** (`deathward/dungeon.py`, lines 631–643)

```python
        # FLOOR 1 PAYS FOR CURIOSITY -- ONCE. Exactly one guaranteed gift, placed as far
        # from the gate as the level allows, so it is a reward for exploring rather than a
        # handout at the door. It is a 50/50 coin-flip: a Bone Sword (start better at
        # killing) or a Leather Jerkin (start better at surviving) -- the whole triad
        # thesis in the first pickup. Claimed once per GAME: it must not regrow on every
        # respawn, or death becomes a way to farm it.
        if d == 1 and not codex.gift_claimed("floor1"):
            spot = self._far_room_spot()
            if spot:
                gkey = "bone_sword" if rng.random() < 0.5 else "leather"
                self.drops.append(Drop(spot[0], spot[1], "gear", gkey, gift="floor1"))
```

Then update the import on line 29 — remove `gear_pool` (its only dungeon use was this block; Task 5 adds `roll_floor_armour`):

```python
from .items import (is_magical, roll_chest, roll_floor_boots,
                    roll_floor_boots_magical, roll_floor_weapons, roll_loot)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `py -3.13 -m deathward.tests`
Expected: PASS. `TestFloorOne`'s existing guard tests (claimed-once / far-from-gate / tier ≥ 1) still hold — both `bone_sword` and `leather` are tier 1 and placed via `_far_room_spot()`.

- [ ] **Step 6: Commit**

```bash
git add deathward/items.py deathward/dungeon.py deathward/tests.py
git commit -m "Floor 1: one coin-flip gift (Bone Sword or Leather Jerkin); retire the Bone Axe"
```

---

### Task 4: `roll_floor_armour` — bands, present-ramp, and masterwork

The distribution function, tested standalone. `gear_pool` is left untouched here; the cutover is Task 5.

**Files:**
- Modify: `deathward/items.py` (add `ARMOUR_BANDS`, `_armour_present_chance`, `_armour_masterwork_bonus`, `roll_floor_armour`, near `roll_floor_boots` ~line 550)
- Test: `deathward/tests.py` (new distribution + masterwork + determinism tests)

**Interfaces:**
- Produces: `roll_floor_armour(rng, depth) -> list[tuple[str, int]]` of length 0 or 1: `[(key, bonus)]` where `key in {"leather","mail","plate"}` and `bonus in {0,1,2}` (only nonzero on floors 8–15). Draws only from `(rng, depth)`.

- [ ] **Step 1: Write the failing tests**

```python
class TestFloorArmourRoll(unittest.TestCase):
    def test_never_on_floor_one_or_past_fifteen(self):
        import random
        from .items import roll_floor_armour
        for depth in (1, 16, 17, 20):
            for s in range(60):
                self.assertEqual(roll_floor_armour(random.Random(s), depth), [],
                                 "no ordinary armour on floor %d" % depth)

    def test_places_at_most_one(self):
        import random
        from .items import roll_floor_armour
        for depth in range(1, 21):
            for s in range(60):
                self.assertLessEqual(len(roll_floor_armour(random.Random(s), depth)), 1)

    def test_respects_the_bands(self):
        import random
        from .items import roll_floor_armour
        def seen(depth):
            out = set()
            for s in range(500):
                out |= {k for k, _ in roll_floor_armour(random.Random(s), depth)}
            return out
        self.assertEqual(seen(2), {"leather"})
        self.assertEqual(seen(4), {"leather", "mail"})
        self.assertEqual(seen(5), {"leather", "mail", "plate"})
        self.assertEqual(seen(10), {"leather", "mail", "plate"})
        self.assertEqual(seen(11), {"mail", "plate"})     # leather gone after 10
        self.assertEqual(seen(15), {"mail", "plate"})
        self.assertEqual(seen(16), set())

    def test_present_ramp_and_determinism(self):
        import random
        from .items import roll_floor_armour
        def rate(depth):
            return sum(1 for s in range(4000)
                       if roll_floor_armour(random.Random(s), depth)) / 4000
        self.assertGreater(rate(2), 0.49); self.assertLess(rate(2), 0.61)    # ~55%
        self.assertGreater(rate(12), 0.69); self.assertLess(rate(12), 0.81)  # ~75%
        for s in range(50):
            for depth in (2, 6, 12, 15):
                self.assertEqual(roll_floor_armour(random.Random(s), depth),
                                 roll_floor_armour(random.Random(s), depth))

    def test_masterwork_only_deep_and_capped_at_two(self):
        import random
        from .items import roll_floor_armour
        # floors below 8 are never masterwork
        for depth in range(2, 8):
            for s in range(300):
                for _, b in roll_floor_armour(random.Random(s), depth):
                    self.assertEqual(b, 0, "no masterwork before floor 8")
        # floors 8-15 produce +1 and +2 but never +3
        bonuses = set()
        for depth in range(8, 16):
            for s in range(600):
                for _, b in roll_floor_armour(random.Random(s), depth):
                    bonuses.add(b)
        self.assertTrue({1, 2} <= bonuses, "deep armour should roll +1 and +2")
        self.assertEqual(max(bonuses), 2, "masterwork must cap at +2, never +3")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -3.13 -m deathward.tests`
Expected: FAIL — `roll_floor_armour` is not defined.

- [ ] **Step 3: Implement the roll** (`deathward/items.py`, near `roll_floor_boots`)

```python
# The ordinary armour a floor may place: at most ONE, found-only, generation-placed like
# the weapons and boots (never from the generic loot pool). Uniform among valid pieces --
# armour is a defense<->speed tradeoff sharing the speed budget with boots, not a power
# ladder. Banded by depth: none on floor 1 (the coin-flip gift) or past 15 (magical
# territory). Deep floors (8-15) layer a MASTERWORK +1/+2 (never +3) onto the piece.
ARMOUR_BANDS = (
    ("leather", 2, 10),
    ("mail", 3, 15),
    ("plate", 5, 15),
)


def _armour_present_chance(depth):
    """A gentle upward ramp, more generous than boots' flat 50%."""
    if depth <= 4:
        return 0.55
    if depth <= 8:
        return 0.65
    if depth <= 12:
        return 0.75
    return 0.80


def _armour_masterwork_bonus(rng, depth):
    """Floors 8-15: a chance the found armour is masterwork. +1 or +2, NEVER +3 (a +3
    Full Plate plus Plate Boots is virtually invulnerable). Below floor 8, always +0, and
    NO rng is drawn (determinism: shallow floors must not consume a masterwork draw)."""
    if depth < 8:
        return 0
    if rng.random() >= 0.25 + (depth - 8) * 0.05:      # 25% at 8 ... 60% at 15
        return 0
    return 2 if rng.random() < 0.15 + (depth - 8) * 0.05 else 1   # +2 share 15%..50%


def roll_floor_armour(rng, depth):
    """The floor's single ordinary armour, or none -- a list of 0 or 1 (key, bonus) pairs.
    Present-chance ramps with depth; the piece is chosen uniformly among those valid at
    this depth; deep floors layer a masterwork bonus. Deterministic on (rng, depth); reads
    nothing else, so blind and omniscient runs of a seed stay bit-identical."""
    valid = [key for key, lo, hi in ARMOUR_BANDS if lo <= depth <= hi]
    if not valid or rng.random() >= _armour_present_chance(depth):
        return []
    key = rng.choice(valid)
    return [(key, _armour_masterwork_bonus(rng, depth))]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `py -3.13 -m deathward.tests`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deathward/items.py deathward/tests.py
git commit -m "roll_floor_armour: bands, present-ramp, deep masterwork +1/+2"
```

---

### Task 5: Cutover — generation-placed armour, empty `gear_pool`, starter-only auto-swap

Wire `roll_floor_armour` into generation, remove armour from `gear_pool`, teach the take-all sweep and the swap to respect armour's tradeoff and carry its bonus. Atomic: armour leaves the pool and becomes generation-placed in the same task.

**Files:**
- Modify: `deathward/items.py` (`gear_pool`, lines 403–415)
- Modify: `deathward/dungeon.py` (import line 29; add placement loop after the boots loops ~line 618)
- Modify: `deathward/world.py` (`_consume_option` auto-swap ~1043–1057; `_take` bonus ~1193–1197)
- Test: `deathward/tests.py` (update the gear_pool test ~7119; add placement + auto-swap tests)

**Interfaces:**
- Consumes: `roll_floor_armour` (Task 4); `Armour.copy(bonus=)` (Task 1).
- Produces: `gear_pool(depth) == []` for all depths. Ordinary armour appears only as generation-placed `Drop`s. Auto-swap (`take_all`) equips armour only over the `rags` starter.

- [ ] **Step 1: Write the failing tests**

Update the gear_pool test (around line 7119). Replace the `assertIn("leather"...)` / `assertIn("plate"...)` tail so it asserts the pool is now empty, and rename it:

```python
    def test_gear_pool_is_empty_all_gear_is_generation_placed(self):
        from .items import gear_pool
        for depth in range(1, 21):
            self.assertEqual(gear_pool(depth), [],
                             "weapons, boots AND armour are all generation-placed now "
                             "(floor %d)" % depth)
```

Add placement + auto-swap tests:

```python
class TestFloorArmourPlacement(unittest.TestCase):
    def _armour_drops(self, lvl):
        from .items import ARMOURS
        return [d for d in lvl.drops if d.kind == "gear" and d.payload in ARMOURS]

    def test_at_most_one_ordinary_armour_per_floor(self):
        for seed in range(40):
            for depth in (3, 6, 9, 14):
                codex = FakeSave()
                codex.world_seed = seed
                w = World(codex, seed=seed)
                w.player.depth = depth
                lvl = w._build_level(depth) if hasattr(w, "_build_level") else None
                # fall back to constructing a Level directly
                from .dungeon import Level
                lvl = Level(depth, __import__("random").Random(seed), codex)
                self.assertLessEqual(len(self._armour_drops(lvl)), 1)

    def test_take_all_will_not_swap_armour_off_a_real_piece(self):
        from .items import ALL_GEAR
        codex = FakeSave()
        w = World(codex, seed=6)
        w.player.armour = ALL_GEAR["leather"].copy()      # a real (non-starter) piece
        self._chest_under_player(w, [("gear", "plate")])
        w.take_all()
        self.assertEqual(w.player.armour.key, "leather",
                         "'all' must not silently swap armour once off the starter")

    def test_take_all_auto_equips_armour_over_the_rags_starter(self):
        from .items import ALL_GEAR
        codex = FakeSave()
        w = World(codex, seed=6)
        w.player.armour = ALL_GEAR["rags"].copy()         # the T0 starter
        self._chest_under_player(w, [("gear", "leather")])
        w.take_all()
        self.assertEqual(w.player.armour.key, "leather",
                         "the first armour still auto-equips over the starter")
```

> Note: `test_at_most_one_ordinary_armour_per_floor` constructs a `Level` directly (mirror how other placement tests build floors — see `TestFloorWeaponPlacement`). Drop the `_build_level` line if `World` has no such helper; the direct `Level(...)` construction is the reliable path.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -3.13 -m deathward.tests`
Expected: FAIL — armour still in `gear_pool`; no placement loop; auto-swap still tier-based for armour.

- [ ] **Step 3: Empty `gear_pool`** (`deathward/items.py`)

```python
def gear_pool(depth):
    """Empty. Weapons, boots AND armour are all generation-placed now (roll_floor_weapons
    / roll_floor_boots / roll_floor_boots_magical / roll_floor_armour), scarce and
    one-per-floor. Kept as a hook so roll_loot's gear branch falls back to gold."""
    return []
```

- [ ] **Step 4: Place armour at generation** (`deathward/dungeon.py`)

Update the import on line 29 to add `roll_floor_armour`:

```python
from .items import (is_magical, roll_chest, roll_floor_armour, roll_floor_boots,
                    roll_floor_boots_magical, roll_floor_weapons, roll_loot)
```

Add a placement loop immediately after the magical-boot loop (after line 629, before the floor-1 gift block):

```python
        # THE FLOOR'S ORDINARY ARMOUR. Like the boots: scarce, generation-placed, at most
        # one per floor -- never from the generic loot pool, never sold or gifted. Banded to
        # floors 2-15 by roll_floor_armour; deep floors may make it masterwork (+1/+2).
        for akey, abonus in roll_floor_armour(rng, d):
            spot = self._free_tile(avoid_start=True)
            if spot:
                self.drops.append(Drop(spot[0], spot[1], "gear", akey, bonus=abonus))
```

- [ ] **Step 5: Auto-swap and bonus in the swap** (`deathward/world.py`)

In `_consume_option` (around line 1046), fold armour into the boots branch so both respect the tradeoff:

```python
            if g.slot in ("boots", "armour"):
                # Boots and armour trade speed for defense, so a higher tier is a different
                # choice, not a strict upgrade. The 'all' sweep only auto-equips over the
                # bare starter; past that a found piece is left for a deliberate pickup.
                if cur.tier > 0:
                    self.log("You step over the %s -- %s are a choice; take it by hand."
                             % (g.name, "boots" if g.slot == "boots" else "armour"),
                             config.DIM)
                    return False
            elif g.tier <= cur.tier:
                self.log("You leave the %s -- your %s is better." % (g.name, cur.name),
                         config.DIM)
                return False
```

In `_take` (around line 1195), carry the bonus onto armour as well as weapons:

```python
        elif kind == "gear":
            g = ALL_GEAR[payload]
            if g.slot in ("weapon", "armour") and bonus:
                g = g.copy(bonus=bonus)          # carry the found/kept +n into the swap
            old = p.equip(g)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `py -3.13 -m deathward.tests`
Expected: PASS. (The vendor's gear branch now reads an empty `gear_pool` and silently stocks no gear; Task 6 removes the dead branch. `test_vendor_never_stocks_a_magical_boot` still passes.)

- [ ] **Step 7: Commit**

```bash
git add deathward/items.py deathward/dungeon.py deathward/world.py deathward/tests.py
git commit -m "Armour goes found-only: generation-placed, gear_pool emptied, starter-only auto-swap"
```

---

### Task 6: Vendor — consumables only

Remove the now-dead gear branch from the vendor and lock the behaviour with a test.

**Files:**
- Modify: `deathward/vendor.py` (`_stock_up`, lines 64–74)
- Test: `deathward/tests.py` (new consumables-only test)

**Interfaces:**
- Produces: `Vendor.stock` contains only `("item", flavor)` entries — never `("gear", ...)`.

- [ ] **Step 1: Write the failing test**

```python
class TestVendorConsumablesOnly(unittest.TestCase):
    def test_the_vendor_never_stocks_gear(self):
        import random
        from .vendor import Vendor
        for depth in (5, 8, 12, 19):
            for s in range(40):
                v = Vendor(0, 0, depth, random.Random(s))
                kinds = {k for k, _ in v.stock}
                self.assertNotIn("gear", kinds,
                                 "the vendor deals in potions and scrolls only "
                                 "(floor %d)" % depth)
                self.assertTrue(v.stock, "it must still stock something")
```

- [ ] **Step 2: Run the test to verify it fails or passes-by-accident**

Run: `py -3.13 -m deathward.tests`
Expected: PASS-by-accident is possible (gear_pool is already empty), but proceed to remove the dead branch so the intent is explicit and future-proof.

- [ ] **Step 3: Remove the gear branch** (`deathward/vendor.py`, `_stock_up`)

```python
    def _stock_up(self, rng, depth):
        # Consumables only. Gear (weapons, boots, armour) is all found-only now -- none of
        # it enters gear_pool, so the vendor deals in potions and scrolls. (The eventual
        # richer vendor economy -- magical items at a high price -- is a later task.)
        for _ in range(rng.randint(2, 3)):
            self.stock.append(("item", rng.choice(POTION_POOL)))
        for _ in range(rng.randint(1, 2)):
            self.stock.append(("item", rng.choice(SCROLL_POOL)))
```

Then prune the now-unused imports on lines 28–29 — `_stock_up` no longer references `ALL_GEAR` or `gear_pool`. Confirm no other function in `vendor.py` uses them (grep `grep -n "ALL_GEAR\|gear_pool" deathward/vendor.py`); `price_of` imports `ALL_GEAR` locally at its own call site (line 42), so the top-level import can drop `ALL_GEAR` and `gear_pool`:

```python
from .items import (BOOTS, CONSUMABLES, POTION_POOL, SCROLL_POOL, WEAPONS)
```

> If the grep shows `ALL_GEAR`/`gear_pool`/`BOOTS`/`WEAPONS` are unused anywhere in the module after this change, trim them from the import too — leave only what the file references.

- [ ] **Step 4: Run the test to verify it passes**

Run: `py -3.13 -m deathward.tests`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deathward/vendor.py deathward/tests.py
git commit -m "Vendor stocks consumables only (gear is all found-only now)"
```

---

### Task 7: Loot-tuple widening — close the bonus-loss edge

Widen gear loot tuples to `("gear", key, bonus)` with tolerant unpacking, so a displaced masterwork (weapon or armour) put back into a container keeps its `+n`.

**Files:**
- Modify: `deathward/world.py` (`loot_options` corpse/slain/chest loops ~967/977/989; `_consume_option` corpse_loot/slain/chest branches ~1079/1099/1106; `_put_back` container branch ~1456–1461, and its docstring)
- Test: `deathward/tests.py` (new edge-closure test)

**Interfaces:**
- Consumes: `_take(..., bonus=)` (Task 5). Container loot lists may hold 2-wide (`gold`/`item`, and legacy `gear`) or 3-wide (`gear` with bonus) tuples; all read sites unpack tolerantly.

- [ ] **Step 1: Write the failing test**

```python
class TestDisplacedMasterworkKeepsBonus(unittest.TestCase):
    def test_a_swapped_off_masterwork_armour_keeps_its_plus_in_a_chest(self):
        from .items import ALL_GEAR
        codex = FakeSave()
        w = World(codex, seed=6)
        w.player.armour = ALL_GEAR["plate"].copy(bonus=2)     # Full Plate +2
        self._chest_under_player(w, [("gear", "leather")])
        w.take_option(0)                                       # equip leather; plate -> chest
        self.assertEqual(w.player.armour.key, "leather")
        ch = w.level.chest_at(w.player.x, w.player.y)
        back = [t for t in ch.loot if t[0] == "gear" and t[1] == "plate"]
        self.assertTrue(back, "the plate must return to the chest")
        self.assertEqual(back[0][2] if len(back[0]) > 2 else 0, 2,
                         "the displaced masterwork plate kept its +2")
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `py -3.13 -m deathward.tests`
Expected: FAIL — the plate returns as `("gear", "plate")` (2-wide), losing the +2.

- [ ] **Step 3: Tolerant unpacking in `loot_options`** (`deathward/world.py`)

Replace the corpse-loot loop (around line 967):

```python
            for i, t in enumerate(c.loot):
                kind, payload = t[0], t[1]
                opts.append({"kind": kind, "payload": payload,
                             "bonus": t[2] if len(t) > 2 else 0,
                             "label": self.loot_label(kind, payload),
                             "src": ("corpse_loot", c, i)})
```

Replace the slain loop (around line 977):

```python
            for i, t in enumerate(s.loot):
                kind, payload = t[0], t[1]
                opts.append({"kind": kind, "payload": payload,
                             "bonus": t[2] if len(t) > 2 else 0,
                             "label": self.loot_label(kind, payload),
                             "src": ("slain", s, i)})
```

Replace the chest loop (around line 989):

```python
            for i, t in enumerate(ch.loot):
                kind, payload = t[0], t[1]
                opts.append({"kind": kind, "payload": payload,
                             "bonus": t[2] if len(t) > 2 else 0,
                             "label": self.loot_label(kind, payload),
                             "src": ("chest", ch, i)})
```

- [ ] **Step 4: Pass the bonus through `_consume_option`** (`deathward/world.py`)

Corpse-loot branch (around line 1079):

```python
        elif src[0] == "corpse_loot":
            c, i = src[1], src[2]
            if i >= len(c.loot):
                return False
            t = c.loot.pop(i)
            self._take(t[0], t[1], sink=c, bonus=t[2] if len(t) > 2 else 0)
            self._settle_corpse(c)
```

Slain branch (around line 1099):

```python
        elif src[0] == "slain":
            s, i = src[1], src[2]
            if i >= len(s.loot):
                return False
            t = s.loot.pop(i)
            self._take(t[0], t[1], sink=s, bonus=t[2] if len(t) > 2 else 0)
```

Chest branch (around line 1106):

```python
        elif src[0] == "chest":
            ch, i = src[1], src[2]
            if i >= len(ch.loot):
                return False
            t = ch.loot.pop(i)
            self._take(t[0], t[1], sink=ch, bonus=t[2] if len(t) > 2 else 0)
            if not ch.loot:
                ch.opened = True
```

- [ ] **Step 5: Write the bonus when putting gear back** (`deathward/world.py`, `_put_back`)

Replace the container branch (around line 1456) and refresh the docstring:

```python
    def _put_back(self, gear, sink):
        """The gear you took off. Back into the container you looted, or onto the ground.
        Gear returned to a container's loot list keeps its +n: the list holds 3-wide
        ("gear", key, bonus) tuples, unpacked tolerantly everywhere (2-wide legacy tuples
        read as bonus 0).

        A magical never goes into a container's loot list -- it would be re-dealt away as
        an ephemeral chest/body drop and lost to the Kodex ledger. It always lands on the
        persistent bare ground instead, and that drop is recorded."""
        p = self.player
        magical = is_magical(gear.key)
        magical_boot = is_magical_boot(gear.key)
        if sink is not None and hasattr(sink, "loot") and not (magical or magical_boot):
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
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `py -3.13 -m deathward.tests`
Expected: PASS. The `Chest`/`Slain`/`Corpse` serializers already convert loot via `list(t)`/`tuple(t)`, so variable-width tuples round-trip through save with no change.

- [ ] **Step 7: Commit**

```bash
git add deathward/world.py deathward/tests.py
git commit -m "Close the loot-tuple bonus-loss edge: gear tuples carry +n"
```

---

### Task 8: Final regression, determinism sweep, and integration

Confirm the whole suite is green, the determinism invariant holds, and armour works end-to-end through a real `World`.

**Files:**
- Test: `deathward/tests.py` (one integration test)

**Interfaces:** none new.

- [ ] **Step 1: Write an integration test**

```python
class TestArmourEndToEnd(unittest.TestCase):
    def test_a_deep_masterwork_armour_equips_with_its_bonus(self):
        from .items import ALL_GEAR
        codex = FakeSave()
        w = World(codex, seed=6)
        # a masterwork Full Plate lying on the floor, picked up off bare ground
        from .dungeon import Drop
        p = w.player
        w.level.drops.append(Drop(p.x, p.y, "gear", "plate", bonus=2))
        p.armour = ALL_GEAR["rags"].copy()          # so the swap is an upgrade over starter
        base = ALL_GEAR["plate"].defense
        w.take_all()
        self.assertEqual(p.armour.key, "plate")
        self.assertEqual(p.armour.bonus, 2)
        self.assertEqual(p.defense, base + 2 + p.boots.defense)

    def test_full_plate_and_plate_boots_share_the_speed_budget(self):
        from .items import ALL_GEAR
        from .player import Player
        from . import config
        p = Player()
        p.armour = ALL_GEAR["plate"].copy()         # -20 spd
        p.boots = ALL_GEAR["boots_plate"]           # -10 spd
        self.assertEqual(p.speed(), max(30, config.BASE_SPEED - 30))
        self.assertEqual(p.defense, 4 + 2)          # +4 armour, +2 boots
```

- [ ] **Step 2: Run the integration test to verify it fails then passes**

Run: `py -3.13 -m deathward.tests`
Expected: PASS (all prior tasks make this green immediately; if it fails, the failure pinpoints a wiring gap).

- [ ] **Step 3: Full determinism + suite sweep**

Run: `py -3.13 -m deathward.tests`
Expected: PASS, with `TestKnowledgeIsNotPower::test_blind_and_omniscient_dungeons_are_identical` green — proof the armour roll never reads the Kodex. Confirm the total test count went UP (new tests) and nothing is skipped.

- [ ] **Step 4: Commit**

```bash
git add deathward/tests.py
git commit -m "Armour rebalance: end-to-end integration + determinism sweep"
```

---

## Self-Review

**Spec coverage:**
- Ordinary ladder (rags/leather/mail/plate, +2/+3/+4, 0/−10/−20) → Task 2. ✓
- Shared speed budget → Task 8 integration test. ✓
- Per-instance bonus model (Armour.bonus/copy, defense, DWEN, serialization, retire enchants) → Task 1. ✓
- Masterwork +1/+2 layered on floors 8–15, never +3, climbing odds → Task 4. ✓
- Generation-placed, ≤1/floor, uniform, present-ramp, leaves gear_pool → Tasks 4 + 5. ✓
- Auto-swap starter-only → Task 5. ✓
- Floor-1 coin-flip gift, retire Bone Axe → Task 3. ✓
- Vendor consumables only → Task 6. ✓
- Loot-tuple widening / edge closure → Task 7. ✓
- Migration (RUN_SAVE_VERSION bump) → Task 1 Step 6. ✓
- Determinism invariant → Task 4 tests + Task 8 sweep. ✓
- thorns/wraithsilk trait code left dormant → Task 2 Step 4 note. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code. Two steps carry explicit *verification* notes (grep for `_apply_effect`, grep for unused imports) rather than placeholders — these are real checks, with the fallback action stated.

**Type consistency:** `roll_floor_armour -> list[(key, bonus)]` consumed identically in Task 5's placement loop. `Armour.copy(bonus=None)` and `.desc(bonus=None)` used consistently. `_take(..., bonus=)` extended in Task 5, relied on in Task 7. Loot tuples read tolerantly (`t[2] if len(t) > 2 else 0`) at every site touched in Task 7. `gift="floor1"` guard preserved across Task 3.

**Known risk flagged for the implementer:** Task 5's placement test builds a `Level` directly (mirroring `TestFloorWeaponPlacement`); if a `World` build helper is absent, use the direct `Level(depth, random.Random(seed), codex)` construction shown.
