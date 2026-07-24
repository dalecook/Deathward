# Magical Armour — Phase 2 (Invisibility Rework + Novel Subsystems) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the three novel magical armour pieces — Fadecloak (reactive invisibility), Nightcloak (permanent invisibility), Shademail (walk-into-walls) — on a reworked, shared invisibility model, and fix the Potion/Scroll of Invisibility in the same stroke.

**Architecture:** One invisibility model for every source: it hides you from *mundane* monsters only (ethereal — wraiths/poltergeists — always see you), and it breaks on any turn-ending action except walking, waiting, and taking stairs. `player_hidden()` is the single gate; a shared `break_stealth()` hook clears it from attack/loot/use-item. Sources differ only in maintenance: the potion is untimed (a `invis_hold` flag), Fadecloak is a 2-turn timer (`player.invisible`), Nightcloak is "hidden unless exposed" with an aggro-based re-cloak. Shademail lets the wearer stand on in-bounds stone, bounded by a submerge limit + crush damage + a re-enter cooldown.

**Tech Stack:** Python 3.13, stdlib `unittest`, `pygame` (sprites only). No new dependencies.

## Global Constraints

- **Test command:** `py -3.13 -m deathward.tests` (Python 3.13 — 3.14 has no pygame).
- **Determinism:** no new RNG in the invisibility/Nightcloak/Shademail paths (Shademail's auto-eject may use `blink_tile_near`, which draws the world `rng` — that's fine, world rng only, never the Kodex). `TestKnowledgeIsNotPower` must stay green.
- **Ethereal = `is_incorporeal(m.key)`** (wraith today; poltergeist when added). This is the single "can see through invisibility / can reach into stone" test.
- **One armour at a time** — all new runtime state is scalars on the Player, serialized (Phase 1's tolerant `from_dict` already defaults absent fields, so no version bump).
- **Boss-reserved:** Nightcloak + Shademail are defined and cheat-reachable (they appear in the CTRL+34 armour bench automatically) but EXCLUDED from `FINDABLE_MAGICAL_ARMOUR`. Fadecloak IS findable.
- Ship the exact values here; numbers are playtest-tunable.

---

### Task 1: Invisibility foundation — ethereal bypass + break-on-action + Phase-2 state

The shared model, plus all the new Player fields the later tasks consume.

**Files:**
- Modify: `deathward/config.py` (new constants)
- Modify: `deathward/player.py` (`__init__` ~88, `_PLAYER_STATE` ~51)
- Modify: `deathward/world.py` (`player_hidden` ~365, `monster_can_see_player` ~403, a new `break_stealth`; call it from `player_attack` ~588, the take/loot path, `use_item`)
- Test: `deathward/tests.py`

**Interfaces:**
- Produces: `player.invis_hold` (bool), `player.nightcloak_exposed` (bool), `player.fade_hits` (int), `player.submerged` (int), `player.shade_cd` (int) — all default 0/False, in `_PLAYER_STATE`. `World.break_stealth()` clears invisibility. `player_hidden()` = `invisible > 0 or invis_hold` (Nightcloak folded in at Task 4). `monster_can_see_player` lets ethereal see through hiding. Config: `FADE_INVIS_TURNS=2`, `FADE_HIT_CADENCE=4`, `SHADE_SUBMERGE_MAX=10`, `SHADE_CRUSH_DMG=2`, `SHADE_REENTER_CD=5`.

- [ ] **Step 1: Write the failing test**

```python
class TestInvisibilityModel(unittest.TestCase):
    def _setup_invis(self, seed=6):
        codex = FakeSave()
        w = World(codex, seed=seed)
        w.player.invis_hold = True          # hidden via the (Task 2) untimed potion state
        return w

    def test_ethereal_sees_through_invisibility_mundane_does_not(self):
        from .monsters import Monster
        w = self._setup_invis()
        kobold = Monster("kobold", w.player.x + 2, w.player.y)
        wraith = Monster("wraith", w.player.x + 2, w.player.y)
        w.level.monsters = [kobold, wraith]
        w.level.compute_fov(w.player.x, w.player.y)
        self.assertFalse(w.monster_can_see_player(kobold), "mundane loses an invisible player")
        self.assertTrue(w.monster_can_see_player(wraith), "ethereal see through invisibility")

    def test_looting_and_using_break_invisibility_but_moving_does_not(self):
        from .dungeon import Drop
        w = self._setup_invis()
        w.player.x, w.player.y = w.level.start
        # moving does NOT break it
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if w.walkable(w.player.x + dx, w.player.y + dy):
                w.player_move(dx, dy); break
        self.assertTrue(w.player_hidden(), "sneaking past keeps you hidden")
        # taking something DOES break it
        w.break_stealth()                    # the hook loot/use call; asserted directly here
        self.assertFalse(w.player_hidden(), "an action drops the cloak")
```

> Note: the second test asserts `break_stealth()` clears hiding directly, plus that a move didn't. The wiring of `break_stealth` into the real loot/use paths is covered in Step 4 + Task 2's tests; keep this test focused on the primitive.

- [ ] **Step 2: Run to verify it fails**

Run: `py -3.13 -m deathward.tests`
Expected: FAIL — `invis_hold`/`break_stealth` don't exist; `monster_can_see_player` has no ethereal bypass.

- [ ] **Step 3: Config + Player fields**

`deathward/config.py` (near the Phase-1 magical-armour block):

```python
# --- magical armour (Phase 2) ---
FADE_INVIS_TURNS = 2       # Fadecloak: turns of vanish on the 4th hit
FADE_HIT_CADENCE = 4       # Fadecloak: every Nth hit taken triggers it
SHADE_SUBMERGE_MAX = 10    # Shademail: max turns you may stay in stone
SHADE_CRUSH_DMG = 2        # Shademail: damage/turn when submerged with no exit
SHADE_REENTER_CD = 5       # Shademail: turns before you may dive again
```

`deathward/player.py` `__init__` (with the other reactive fields, after `self.lastbreath_used`):

```python
        self.invis_hold = False     # untimed invisibility (Potion/Scroll) -- until you act
        self.nightcloak_exposed = False  # Nightcloak: visible after acting, until the hunt clears
        self.fade_hits = 0          # Fadecloak: hits taken, for the every-4th vanish
        self.submerged = 0          # Shademail: consecutive turns standing in stone
        self.shade_cd = 0           # Shademail: re-enter cooldown
```

Append them to `_PLAYER_STATE`:

```python
    "slipstep_hits", "blade_coat", "gift", "armour_cd", "lastbreath_used",
    "invis_hold", "nightcloak_exposed", "fade_hits", "submerged", "shade_cd",
)
```

- [ ] **Step 4: The shared model** (`deathward/world.py`)

`player_hidden()` (the single gate — Nightcloak's clause is added in Task 4):

```python
    def player_hidden(self):
        """True while MUNDANE monsters cannot see or track the player. Ethereal monsters
        (is_incorporeal) see through it -- handled in monster_can_see_player."""
        p = self.player
        return p.invisible > 0 or p.invis_hold
```

`monster_can_see_player` — ethereal bypass (replace the hidden gate):

```python
        if self.player_hidden() and not is_incorporeal(m.key):
            return False
```

Add the shared break hook (near the combat helpers):

```python
    def break_stealth(self):
        """Any turn-ending action except move/wait/stairs drops invisibility. Attacking,
        looting, and using an item call this; move/wait/descend deliberately do not."""
        p = self.player
        p.invisible = 0
        p.invis_hold = False
        p.nightcloak_exposed = True     # Nightcloak: now exposed until the hunt clears (Task 4)
```

Wire it in:
- `player_attack` (world.py:587–589): replace `p.invisible = 0` with `self.break_stealth()` (keep the "You break cover to strike." log).
- The take/loot path: call `self.break_stealth()` at the top of `_consume_option` (so every pickup/loot breaks it). Confirm `take_all`/`take_option` route through `_consume_option`.
- `use_item` (world.py:1566): call `self.break_stealth()` when an item is actually consumed (after the slot is confirmed non-empty), so drinking/reading breaks it.
- Do NOT call it in `player_move`, `player_wait`, `descend`, `ascend`.

> `is_incorporeal` is already imported in world.py (used in `player_attack`'s shock branch). Confirm the import; add it if the linter flags it.

- [ ] **Step 5: Run to verify it passes**

Run: `py -3.13 -m deathward.tests`
Expected: PASS. If an existing invisibility test asserts the old "16 turns" behavior, leave it for Task 2 (which reworks the potion); if it breaks here, note it and adapt minimally.

- [ ] **Step 6: Commit**

```bash
git add deathward/config.py deathward/player.py deathward/world.py deathward/tests.py
git commit -m "Invisibility model: ethereal bypass + break-on-action + Phase-2 state"
```

---

### Task 2: Untimed Invisibility potion/scroll + de-aggro

Rework the shared `"invisible"` effect: persistent (untimed), and de-aggro the mundane hunt on use.

**Files:**
- Modify: `deathward/world.py` (`_apply_effect`, `effect == "invisible"` ~1975; a `_deaggro_mundane` helper)
- Test: `deathward/tests.py`

**Interfaces:** consumes `player.invis_hold` (Task 1). Produces `_deaggro_mundane()` (reused by Fadecloak, Task 3).

- [ ] **Step 1: Write the failing test**

```python
class TestUntimedInvisibility(unittest.TestCase):
    def test_potion_is_untimed_and_deaggros_mundane_not_ethereal(self):
        from .monsters import Monster
        codex = FakeSave()
        w = World(codex, seed=6)
        kob = Monster("kobold", w.player.x + 1, w.player.y); kob.awake = True
        kob.intent = ("smash", w.player.x, w.player.y)
        wr = Monster("wraith", w.player.x + 1, w.player.y); wr.awake = True
        w.level.monsters = [kob, wr]
        w._apply_effect("invisible")
        self.assertTrue(w.player.invis_hold, "the potion sets untimed invisibility")
        # untimed: a turn tick does not end it
        w.player.tick_effects(w)
        self.assertTrue(w.player_hidden(), "invisibility does not tick away")
        # de-aggro hit the mundane, not the ethereal
        self.assertFalse(kob.awake, "the mundane hunter loses you")
        self.assertIsNone(kob.intent, "and its windup is wiped")
        self.assertTrue(wr.awake, "the wraith keeps hunting")
```

- [ ] **Step 2: Run to verify it fails**

Run: `py -3.13 -m deathward.tests`
Expected: FAIL — the effect still sets `p.invisible = 16`; no de-aggro.

- [ ] **Step 3: Implement** (`deathward/world.py`)

Add the helper:

```python
    def _deaggro_mundane(self):
        """Every awake MUNDANE monster loses the player and its windup. Ethereal monsters
        (is_incorporeal) are unaffected -- invisibility never shakes them."""
        for m in self.level.monsters:
            if m.alive and m.awake and not is_incorporeal(m.key):
                m.awake = False
                m.intent = None
```

Rewrite the `effect == "invisible"` branch:

```python
        elif effect == "invisible":
            p.invis_hold = True
            self._deaggro_mundane()
            self.log("The light bends around you. The hunt loses your trail -- and nothing "
                     "mundane will find you again until you act.", (190, 200, 220))
            self.add_fx("pulse", p.x, p.y, color=(190, 200, 220), life=0.7)
```

- [ ] **Step 4: Run to verify it passes**

Run: `py -3.13 -m deathward.tests`
Expected: PASS. Update any existing "invisibility lasts 16 turns" / "invisibility wears off" test to the new untimed reality (do not weaken — adapt to "persists until an action"); report any touched.

- [ ] **Step 5: Commit**

```bash
git add deathward/world.py deathward/tests.py
git commit -m "Invisibility potion/scroll: untimed + de-aggro the mundane hunt on use"
```

---

### Task 3: Fadecloak — reactive invisibility (found)

**Files:**
- Modify: `deathward/items.py` (`ARMOURS` add `fade`; `FINDABLE_MAGICAL_ARMOUR[4]` add `fade`)
- Modify: `deathward/sprites.py` (`gear()` add `fade`)
- Modify: `deathward/world.py` (`monster_attacks_player` — the on-struck hit counter)
- Test: `deathward/tests.py`

**Interfaces:** consumes `player.fade_hits`, `config.FADE_*`, `_deaggro_mundane` (Task 2).

- [ ] **Step 1: Write the failing test**

```python
class TestFadecloak(unittest.TestCase):
    def test_every_fourth_hit_vanishes_and_deaggros(self):
        from .items import ALL_GEAR
        from .monsters import Monster
        from . import config
        codex = FakeSave()
        w = World(codex, seed=6)
        w.player.armour = ALL_GEAR["fade"].copy()
        m = Monster("kobold", w.player.x + 1, w.player.y); m.awake = True
        w.level.monsters = [m]
        for _ in range(3):
            w.monster_attacks_player(m, 1)
        self.assertFalse(w.player_hidden(), "not yet -- three hits")
        w.monster_attacks_player(m, 1)      # the 4th
        self.assertEqual(w.player.invisible, config.FADE_INVIS_TURNS)
        self.assertTrue(w.player_hidden(), "the 4th hit drops the cloak of shadow")
        self.assertFalse(m.awake, "and shakes the mundane hunt")
```

- [ ] **Step 2: Run to verify it fails**

Run: `py -3.13 -m deathward.tests`
Expected: FAIL — no `fade` piece / no counter.

- [ ] **Step 3: Roster entry + sprite**

`deathward/items.py` `ARMOURS` (with the other magical pieces):

```python
    "fade":    Armour("fade", "Fadecloak", 4, 2, 10, "fade",
                      "every fourth blow, you are simply not there"),
```

`FINDABLE_MAGICAL_ARMOUR[4]` — append `"fade"`.

`deathward/sprites.py` `gear()`:

```python
    elif key == "fade":                     # dim violet-grey, half-there
        cuirass((132, 120, 150), (84, 76, 100))
```

- [ ] **Step 4: The hit counter** (`deathward/world.py`, in `monster_attacks_player`, after the reactive dispatch block, still under `raw > 0` / not dead)

```python
        if raw > 0 and not self.dead and p.armour.trait == "fade":
            p.fade_hits += 1
            if p.fade_hits % config.FADE_HIT_CADENCE == 0:
                p.invisible = max(p.invisible, config.FADE_INVIS_TURNS)
                self._deaggro_mundane()
                self.log("The cloak drinks the light -- you vanish.", (190, 200, 220))
                self.add_fx("pulse", p.x, p.y, color=(190, 200, 220), life=0.6)
```

> This is deterministic (a counter, no RNG). `_deaggro_mundane` also clears the windups (the spec's "wipe un-struck windups"). The 2-turn vanish ticks down via the existing `player.invisible` decrement, and the shared `break_stealth` ends it early if the player acts.

- [ ] **Step 5: Run to verify it passes**

Run: `py -3.13 -m deathward.tests`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add deathward/items.py deathward/sprites.py deathward/world.py deathward/tests.py
git commit -m "Fadecloak: every 4th hit -> vanish 2 turns + shake the mundane hunt"
```

---

### Task 4: Nightcloak — permanent invisibility (boss-reserved)

**Files:**
- Modify: `deathward/items.py` (`ARMOURS` add `nightcloak`; NOT in FINDABLE)
- Modify: `deathward/sprites.py` (`gear()` add `nightcloak`)
- Modify: `deathward/world.py` (`player_hidden` fold-in; the per-turn re-cloak check)
- Test: `deathward/tests.py`

**Interfaces:** consumes `player.nightcloak_exposed` (Task 1), `break_stealth` (Task 1).

- [ ] **Step 1: Write the failing test**

```python
class TestNightcloak(unittest.TestCase):
    def _wear(self, w):
        from .items import ALL_GEAR
        w.player.armour = ALL_GEAR["nightcloak"].copy()

    def test_worn_hides_you_until_you_act_then_recloaks_when_clear(self):
        from .monsters import Monster
        codex = FakeSave()
        w = World(codex, seed=6); w.level.monsters = []
        self._wear(w)
        self.assertTrue(w.player_hidden(), "Nightcloak hides you while worn")
        w.break_stealth()                                # simulate an action
        self.assertFalse(w.player_hidden(), "acting exposes you")
        w.recloak_check()                                # no monsters -> re-cloak
        self.assertTrue(w.player_hidden(), "with nothing hunting, you vanish again")

    def test_a_living_nearby_hunter_keeps_you_exposed(self):
        from .monsters import Monster
        codex = FakeSave()
        w = World(codex, seed=6)
        self._wear(w)
        m = Monster("kobold", w.player.x + 1, w.player.y); m.awake = True
        w.level.monsters = [m]
        w.break_stealth()
        w.recloak_check()
        self.assertFalse(w.player_hidden(), "an awake mundane hunter nearby blocks the re-cloak")
        m.hp = 0                                          # kill it
        w.recloak_check()
        self.assertTrue(w.player_hidden(), "clear the hunters -> re-cloak")
```

- [ ] **Step 2: Run to verify it fails**

Run: `py -3.13 -m deathward.tests`
Expected: FAIL — no `nightcloak` / no `recloak_check` / no fold-in.

- [ ] **Step 3: Roster entry + sprite** (`deathward/items.py`, `ARMOURS`; do NOT add to FINDABLE)

```python
    "nightcloak": Armour("nightcloak", "Nightcloak", 5, 3, 0, "nightcloak",
                         "the dark keeps you until you break it"),
```

`deathward/sprites.py` `gear()`:

```python
    elif key == "nightcloak":               # near-black, star-flecked
        cuirass((34, 32, 48), (12, 12, 22))
```

- [ ] **Step 4: Fold into `player_hidden` + the re-cloak check** (`deathward/world.py`)

`player_hidden()` gains the Nightcloak clause:

```python
        return (p.invisible > 0 or p.invis_hold
                or (p.armour.trait == "nightcloak" and not p.nightcloak_exposed))
```

Add the per-turn re-cloak check and call it at the end of the player's turn (in `_end_player_turn`, after `_update_stealth_alert` or the advance):

```python
    def recloak_check(self):
        """Nightcloak re-cloaks the moment no mundane monster is hunting the wearer -- every
        hunter dead or out of sight range. Deterministic; no RNG."""
        p = self.player
        if p.armour.trait != "nightcloak" or not p.nightcloak_exposed:
            return
        hunting = any(m.alive and m.awake and not is_incorporeal(m.key)
                      and m.dist(p.x, p.y) <= config.MONSTER_SIGHT
                      for m in self.level.monsters)
        if not hunting:
            p.nightcloak_exposed = False
```

> Call `recloak_check()` once per player turn (end of `_end_player_turn`). "Hunting" is *awake mundane within sight range* — so killing them, or getting far enough that awake mundane aren't near, re-cloaks you; a momentary line-of-sight break while a hunter is still awake and close does not.

- [ ] **Step 5: Run to verify it passes**

Run: `py -3.13 -m deathward.tests`
Expected: PASS. (The Task 2 potion de-aggro empties the hunt-set, so a Nightcloak wearer drinking Invisibility re-cloaks for free at the next `recloak_check` — add a test if you like.)

- [ ] **Step 6: Commit**

```bash
git add deathward/items.py deathward/sprites.py deathward/world.py deathward/tests.py
git commit -m "Nightcloak: permanent invis, breaks on action, re-cloaks when the hunt clears"
```

---

### Task 5: Shademail — wall-walk (boss-reserved)

The novel movement piece. Read the surrounding code carefully — this touches movement, FOV, monster reach, and the turn loop.

**Files:**
- Modify: `deathward/items.py` (`ARMOURS` add `shade`; NOT in FINDABLE)
- Modify: `deathward/sprites.py` (`gear()` add `shade`)
- Modify: `deathward/world.py` (`player_move` stone-step; a `player_submerged()` helper; the per-turn submerge/eject/crush + `shade_cd` tick; guard mundane attacks / traps / loot / stairs while submerged; FOV in stone)
- Test: `deathward/tests.py`

**Interfaces:** consumes `player.submerged`, `player.shade_cd`, `config.SHADE_*`. Produces `player_submerged()` (player on a stone tile while wearing shade).

- [ ] **Step 1: Write the failing test**

```python
class TestShademail(unittest.TestCase):
    def _wear(self, w):
        from .items import ALL_GEAR
        w.player.armour = ALL_GEAR["shade"].copy()

    def _adjacent_wall(self, w):
        from .dungeon import WALL
        px, py = w.player.x, w.player.y
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            x, y = px + dx, py + dy
            if w.level.in_bounds(x, y) and w.level.grid[y][x] == WALL:
                return dx, dy
        return None

    def test_shademail_lets_you_step_into_stone_others_cannot(self):
        codex = FakeSave(); w = World(codex, seed=6); w.level.monsters = []
        d = self._adjacent_wall(w)
        self.assertIsNotNone(d, "seed has an adjacent wall")
        # without Shademail: blocked
        px, py = w.player.x, w.player.y
        w.player_move(*d)
        self.assertEqual((w.player.x, w.player.y), (px, py), "stone is solid without Shademail")
        # with Shademail: you step in
        self._wear(w)
        w.player_move(*d)
        self.assertEqual((w.player.x, w.player.y), (px + d[0], py + d[1]), "you enter the stone")
        self.assertTrue(w.player_submerged())

    def test_submerge_limit_ejects_and_starts_the_cooldown(self):
        from . import config
        codex = FakeSave(); w = World(codex, seed=6); w.level.monsters = []
        self._wear(w)
        d = self._adjacent_wall(w)
        w.player_move(*d)                          # into the stone
        for _ in range(config.SHADE_SUBMERGE_MAX + 1):
            w.player_wait()
        self.assertFalse(w.player_submerged(), "the limit surfaces you")
        self.assertGreater(w.player.shade_cd, 0, "and starts the re-enter cooldown")
```

- [ ] **Step 2: Run to verify it fails**

Run: `py -3.13 -m deathward.tests`
Expected: FAIL — no `shade` piece / no wall-walk / no submerge logic.

- [ ] **Step 3: Roster entry + sprite** (`deathward/items.py`, `ARMOURS`; NOT in FINDABLE)

```python
    "shade":   Armour("shade", "Shademail", 4, 3, 0, "shade",
                      "the stone parts for you -- for a while"),
```

`deathward/sprites.py` `gear()`:

```python
    elif key == "shade":                    # slate grey, stone-toned
        cuirass((96, 96, 104), (52, 52, 60))
```

- [ ] **Step 4: Wall-walk in `player_move`** (`deathward/world.py`, the `if not self.walkable(nx, ny): return False` at ~965)

```python
        if not self.walkable(nx, ny):
            # Shademail: step INTO in-bounds stone (never off-map), if not on cooldown.
            if (p.armour.trait == "shade" and p.shade_cd == 0
                    and self.in_bounds(nx, ny)
                    and self.level.grid[ny][nx] == WALL):
                p.x, p.y = nx, ny
                self.codex.stats["steps"] += 1
                self.level.compute_fov(p.x, p.y, radius=1)   # only the immediate stone
                return self._end_player_turn()
            return False
```

> `WALL` must be importable in world.py (import from `.dungeon`). If FOV from a stone tile misbehaves (rays start in solid rock), a radius-1 reveal of the immediate ring is the intended "shows the immediate surroundings" — verify `compute_fov` tolerates a wall origin; if not, reveal the 8 neighbours directly.

- [ ] **Step 5: The submerge lifecycle** (`deathward/world.py`)

Add the helper and a per-turn tick, called from `_end_player_turn` (once per player turn):

```python
    def player_submerged(self):
        p = self.player
        return p.armour.trait == "shade" and self.level.grid[p.y][p.x] == WALL

    def _shade_tick(self):
        """Per player turn: count time in stone, surface at the limit (or crush if boxed in),
        and tick the re-enter cooldown while on floor."""
        p = self.player
        if self.player_submerged():
            p.submerged += 1
            if p.submerged >= config.SHADE_SUBMERGE_MAX:
                spot = self.blink_tile_near(p.x, p.y, 1, 1)   # a free adjacent FLOOR tile
                if spot:
                    p.x, p.y = spot
                    self.level.compute_fov(p.x, p.y)
                    p.submerged = 0
                    p.shade_cd = config.SHADE_REENTER_CD
                    self.log("The stone spits you out.", config.DIM)
                else:
                    self.hurt_player(config.SHADE_CRUSH_DMG, "shade")   # boxed in: the rock crushes
                    self.log("The stone closes on you. There is nowhere to surface.", config.BLOOD)
        else:
            if p.submerged:                       # just stepped back onto floor
                p.submerged = 0
                p.shade_cd = config.SHADE_REENTER_CD
            if p.shade_cd > 0:
                p.shade_cd -= 1
```

Call `self._shade_tick()` in `_end_player_turn` (after the move resolves, before/with the other per-turn upkeep).

- [ ] **Step 6: Guards while submerged** (`deathward/world.py`)

- **Mundane monsters cannot reach you in stone.** In the monster attack resolution (where a monster adjacent to the player strikes), skip the strike when `self.player_submerged() and not is_incorporeal(m.key)` — only wraiths/poltergeists reach into stone. (Find the adjacency-attack call in the monster AI / `monster_attacks_player` caller and gate it.)
- **No traps / loot / stairs while submerged.** `_enter_tile` already only fires on the tile you step onto — confirm it does nothing on a stone tile (no drops/traps live in stone). `loot_options` returns nothing on a stone tile (no chest/corpse/drop there). `descend`/`ascend` require standing on the stairs tile (floor), so they're naturally unavailable — confirm they no-op while submerged.

> These are verification-heavy: read the monster-attack caller and confirm the three "no interaction in stone" properties hold, adding a guard only where one is actually reachable. Cite what you checked in your report.

- [ ] **Step 7: Run to verify it passes**

Run: `py -3.13 -m deathward.tests`
Expected: PASS, `TestKnowledgeIsNotPower` green.

- [ ] **Step 8: Commit**

```bash
git add deathward/items.py deathward/sprites.py deathward/world.py deathward/tests.py
git commit -m "Shademail: walk into stone, 10-turn submerge, crush if boxed, re-enter cooldown"
```

---

### Task 6: Distribution, bench reachability, integration + determinism

**Files:**
- Test: `deathward/tests.py` (mostly assertions; small items.py check if needed)

- [ ] **Step 1: Write the tests**

```python
class TestPhase2Distribution(unittest.TestCase):
    def test_fade_is_findable_but_boss_pieces_are_not(self):
        from .items import FINDABLE_MAGICAL_ARMOUR_KEYS
        self.assertIn("fade", FINDABLE_MAGICAL_ARMOUR_KEYS)
        self.assertNotIn("shade", FINDABLE_MAGICAL_ARMOUR_KEYS)
        self.assertNotIn("nightcloak", FINDABLE_MAGICAL_ARMOUR_KEYS)

    def test_the_bench_now_reaches_all_three_new_pieces(self):
        from .game import Game
        from .items import ARMOURS
        g = Game.__new__(Game)
        g.open_armour_cheat()
        covered = set().union(*g.weapon_pages)
        for key in ("fade", "shade", "nightcloak"):
            self.assertIn(key, covered, key)
        self.assertEqual(covered, set(ARMOURS))

    def test_a_found_fadecloak_works_end_to_end(self):
        from .items import ALL_GEAR
        from .dungeon import Drop
        from .monsters import Monster
        from . import config
        codex = FakeSave(); w = World(codex, seed=6)
        p = w.player
        w.level.drops.append(Drop(p.x, p.y, "gear", "fade"))
        p.armour = ALL_GEAR["rags"].copy()
        w.take_all()
        self.assertEqual(p.armour.key, "fade")
        m = Monster("kobold", p.x + 1, p.y); m.awake = True
        w.level.monsters = [m]
        for _ in range(config.FADE_HIT_CADENCE):
            w.monster_attacks_player(m, 1)
        self.assertTrue(w.player_hidden())
```

- [ ] **Step 2: Run + full determinism sweep**

Run: `py -3.13 -m deathward.tests`
Expected: PASS, including `TestKnowledgeIsNotPower::test_blind_and_omniscient_dungeons_are_identical`. Confirm the total test count rose and nothing is unexpectedly skipped.

- [ ] **Step 3: Commit**

```bash
git add deathward/tests.py
git commit -m "Magical armour Phase 2: distribution + bench reachability + determinism sweep"
```

---

## Self-Review

**Spec coverage (Phase 2 of the roster spec):**
- Shared invisibility model — mundane-only/ethereal bypass + break-on-action → Task 1. ✓
- Untimed Invisibility potion/scroll + de-aggro → Task 2. ✓
- Fadecloak (every-4th vanish + de-aggro) → Task 3. ✓
- Nightcloak (permanent, break-on-action, aggro-based re-cloak) → Task 4. ✓
- Shademail (wall-walk, 10-turn submerge, crush, ethereal-reach, re-enter cd) → Task 5. ✓
- Distribution (fade findable; shade/nightcloak boss-reserved + bench-reachable) → Tasks 3/4/5 + 6. ✓
- Determinism invariant → Task 6 sweep + no-RNG mechanics. ✓

**Placeholder scan:** every code step shows complete code. Task 5 carries explicit *verification* notes (FOV from a wall origin; the mundane-can't-attack-submerged guard; the no-loot/traps/stairs-in-stone properties) — these are real checks with the fallback stated, not placeholders, because they depend on existing code the implementer must read (the monster-attack caller, `compute_fov`, `_enter_tile`).

**Type consistency:** the five Player fields defined in Task 1 are consumed by Tasks 2–5; `break_stealth`/`_deaggro_mundane`/`player_submerged`/`recloak_check` defined once and reused; `player_hidden` extended (not duplicated) in Task 4; `is_incorporeal` used as the single ethereal test throughout.

**Known risk flagged:** Task 5 (Shademail) is the highest-risk — the submerge/attack/FOV interactions live in code the plan can't fully inline. The implementer must read the monster-attack caller and `compute_fov`, and the reviewer should scrutinize the three "no interaction in stone" guards and the mundane-attack block specifically.
