# Death Reveals Only The Killer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A death teaches you about the thing that killed you, or it teaches you nothing — and damage-over-time stops losing the identity of its source.

**Architecture:** Three code changes in dependency-safe order. First poison remembers what applied it, so the killer is nameable. Then the autopsy learns to render an empty lesson, *before* an empty lesson is possible. Only then does `reveal_on_death`'s fallback cascade collapse to the killer alone, taking three now-unreachable helpers with it.

**Tech Stack:** Python 3.13, pygame 2.6.1, `unittest`.

**Spec:** `docs/superpowers/specs/2026-09-03-death-reveals-only-the-killer-design.md`

## Global Constraints

- Branch is `fix/death-reveals-only-the-killer`, already created off `main` at `3198867`. Never work on `main`.
- **Task order is load-bearing.** Task 2 (the UI tolerating no fact) MUST land before Task 3 (the cascade collapsing). Reversing them leaves a commit where any death by an exhausted killer crashes the autopsy.
- The new signature is exactly `def reveal_on_death(self, cause):` — one argument.
- `reveal_on_death` keeps step 1 (`self.corpse`) and steps 2-4 (the killer's tiers in `TIER_ORDER`). Steps 5-9 are deleted. It returns a `Fact` or `None`.
- **No `RUN_SAVE_VERSION` bump.** `Player.from_dict` uses `data.get(k, getattr(p, k))`, so old saves default the new field. Do not bump; doing so needlessly discards every suspended run.
- `SELF_SECRETS` and `DUNGEON_SECRETS` (`codex.py:637-638`) stay defined but unreferenced, with a comment. Do not delete them.
- The five secret facts stay in `FACTS` untouched. They become unobtainable; that is expected and accepted, and is the next piece of work.
- Autopsy copy is fixed and approved: heading **`NOTHING NEW`**, body **`You have learned everything this one has to teach. It killed you anyway.`**
- No new Kodex subjects, no new facts, no change to `"shade"`.
- Full suite: `py -3.13 -m deathward.tests`. Single class: `py -3.13 -m unittest deathward.tests.<ClassName> -v`. Plain `python` is NOT on PATH.
- The suite is safe to run: `setUpModule` repoints `config.SAVE_PATH` at a tempdir scratch file.
- **Clear `deathward/__pycache__` between any mutation and its restore.** A same-length edit made in the same second reuses stale bytecode, and a restored file will keep testing as mutated.
- 842 tests green at branch point.

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `deathward/player.py` | Modify | Gains `poison_source` (field + `_PLAYER_STATE`), reports it from the tick, clears it when poison ends. Loses `carried_flavors()` in Task 3. |
| `deathward/traps.py` | Modify (`_gas`, ~line 151) | The gas vent signs its work. |
| `deathward/world.py` | Modify | Venom potion sets no source (~line 1982). Loses `floor_subjects()` in Task 3. |
| `deathward/ui.py` | Modify (`draw_autopsy`, line 637) | Renders the no-lesson card. |
| `deathward/game.py` | Modify | Guards the typewriter (line ~473); drops the two dead call arguments (line ~194). |
| `deathward/codex.py` | Modify | The cascade collapses; `_telemetry_fact` goes. |
| `deathward/tests.py` | Modify | New poison-source class; autopsy smoke test; `TestEveryDeathTeaches` rebuilt. |
| `README.md` | Modify (line 212) | Stops advertising the retired guarantee. |

---

### Task 1: Poison remembers where it came from

**Files:**
- Modify: `deathward/player.py` (`__init__` ~line 70, `_PLAYER_STATE` ~line 46, `tick_effects` ~line 202)
- Modify: `deathward/traps.py` (`_gas`, ~line 151)
- Modify: `deathward/world.py` (venom potion, ~line 1982)
- Test: `deathward/tests.py` — new class

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `Player.poison_source` — a `str` Kodex subject key, or `None` for self-inflicted/unknown. Task 3 relies on the cause reaching `reveal_on_death` as `"gas"` rather than `"poison"`.

- [ ] **Step 1: Write the failing tests**

Add this class to `deathward/tests.py`, immediately before `class TestEveryDeathTeaches`:

```python
class TestPoisonRemembersItsSource(unittest.TestCase):
    """A gas vent does no damage where you stand -- it sets a counter, and the
    per-turn tick does the killing several turns later. The tick used to report
    the generic status "poison", so the vent's identity was lost: the death was
    filed under a word that is not a Kodex subject, and the autopsy could not
    name what killed you."""

    def _world(self):
        return World(FakeSave(), seed=11)

    def test_the_gas_vent_signs_its_work(self):
        from .traps import Trap
        w = self._world()
        Trap("gas", w.player.x, w.player.y).trigger(w, w.player)
        self.assertEqual(w.player.poison_source, "gas")
        self.assertGreater(w.player.poison, 0, "the vent must actually poison")

    def test_a_fatal_tick_names_the_vent_not_the_status(self):
        w = self._world()
        w.player.hp = 1
        w.player.poison = 3
        w.player.poison_source = "gas"
        w.player.tick_effects(w)
        self.assertEqual(w.death_cause, "gas",
                         "the killing tick must name the vent, not 'poison'")

    def test_self_inflicted_venom_has_no_source(self):
        """The Potion of Venom is something you did to yourself. There is no Kodex
        subject for it, so it deliberately leaves the source unset -- and under the
        new rule that means such a death teaches nothing, with no special case.
        The residue from an earlier vent must not be allowed to sign for it."""
        w = self._world()
        w.player.poison_source = "gas"
        w._apply_effect("poison")
        self.assertGreater(w.player.poison, 0)
        self.assertIsNone(w.player.poison_source)

    def test_the_source_clears_when_the_poison_burns_out(self):
        w = self._world()
        w.player.poison = 1
        w.player.poison_source = "gas"
        w.player.tick_effects(w)
        self.assertEqual(w.player.poison, 0)
        self.assertIsNone(w.player.poison_source,
                          "a spent poison must not sign the next one")

    def test_the_source_survives_a_suspended_run(self):
        from .player import Player
        w = self._world()
        w.player.poison = 4
        w.player.poison_source = "gas"
        restored = Player.from_dict(w.player.to_dict())
        self.assertEqual(restored.poison_source, "gas")

    def test_a_save_written_before_this_field_still_loads(self):
        """Player.from_dict reads data.get(k, default), so no save version bump
        was needed. This pins that -- a bump would discard every suspended run."""
        from .player import Player
        w = self._world()
        old = w.player.to_dict()
        del old["poison_source"]
        restored = Player.from_dict(old)
        self.assertIsNone(restored.poison_source)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -3.13 -m unittest deathward.tests.TestPoisonRemembersItsSource -v`

Expected: FAIL. `AttributeError: 'Player' object has no attribute 'poison_source'` on most
of them, and `test_a_fatal_tick_names_the_vent_not_the_status` failing with
`'poison' != 'gas'`.

- [ ] **Step 3: Add the field**

In `deathward/player.py` `__init__`, the line `self.poison = 0` (~line 70) becomes:

```python
        self.poison = 0
        self.poison_source = None   # the Kodex subject that poisoned you, if any
```

In `_PLAYER_STATE` (~line 46), add `"poison_source"` directly after `"poison"`:

```python
    "poison", "poison_source", "stuck", "haste", "might", "stoneskin", "regen", "vigor",
```

(The tuple's existing line breaks may need adjusting to stay under the line length used by
the file — keep the ordering, wrap wherever the file's style requires.)

- [ ] **Step 4: Report the source from the tick, and clear it when spent**

In `deathward/player.py` `tick_effects`, replace this block:

```python
        if self.poison > 0:
            self.poison -= 1
            world.hurt_player(1, "poison", silent=True)
            if self.poison == 0 and self.hp > 0:
                world.log("The poison burns itself out.", config.DIM)
```

with:

```python
        if self.poison > 0:
            self.poison -= 1
            world.hurt_player(1, self.poison_source or "poison", silent=True)
            if self.poison == 0:
                if self.hp > 0:
                    world.log("The poison burns itself out.", config.DIM)
                self.poison_source = None
```

- [ ] **Step 5: Make the gas vent sign its work**

In `deathward/traps.py` `_gas` (~line 151), replace:

```python
            world.player.poison = max(world.player.poison, 8)
```

with:

```python
            world.player.poison = max(world.player.poison, 8)
            world.player.poison_source = "gas"
```

- [ ] **Step 6: Make self-inflicted venom leave no source**

In `deathward/world.py`, the Potion of Venom branch (~line 1982), replace:

```python
        elif effect == "poison":
            p.poison = max(p.poison, 10)
```

with:

```python
        elif effect == "poison":
            p.poison = max(p.poison, 10)
            p.poison_source = None      # you did this to yourself; nothing to teach
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `py -3.13 -m unittest deathward.tests.TestPoisonRemembersItsSource -v`
Expected: `Ran 6 tests ... OK`

The venom test calls `World._apply_effect(effect)` (`deathward/world.py:1967`), which is the
method holding the `elif effect == "poison":` branch. It takes the effect string and nothing
else, so it can be driven directly.

- [ ] **Step 8: Prove the tests can fail**

Temporarily revert the tick in `player.py` to the hardcoded `world.hurt_player(1, "poison", silent=True)`, clear the bytecode cache, and re-run:

```bash
rm -rf deathward/__pycache__
py -3.13 -m unittest deathward.tests.TestPoisonRemembersItsSource -v
```

Expected: `test_a_fatal_tick_names_the_vent_not_the_status` goes red with `'poison' != 'gas'`.

Restore the correct line, `rm -rf deathward/__pycache__` again, and confirm green. Do not commit the reverted version.

- [ ] **Step 9: Run the full suite**

Run: `py -3.13 -m deathward.tests`
Expected: `Ran 848 tests ... OK` (842 + 6). A single
`skipped 'no clear line on this seed'` in `TestFireIsVisible` is pre-existing and
seed-dependent.

- [ ] **Step 10: Commit**

```bash
git add deathward/player.py deathward/traps.py deathward/world.py deathward/tests.py
git commit -m "poison remembers what applied it, so the gas vent can be named"
```

---

### Task 2: The autopsy can say nothing

**Files:**
- Modify: `deathward/ui.py` (`draw_autopsy`, line 637)
- Modify: `deathward/game.py` (AUTOPSY key handling, ~line 473)
- Test: `deathward/tests.py` — new class

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `ui.draw_autopsy(surf, world, codex, fact, cause, reveal_t)` accepts `fact=None`. Task 3 depends on this already being true.

- [ ] **Step 1: Write the failing test**

Add this class to `deathward/tests.py`, immediately after `class TestPoisonRemembersItsSource`:

```python
class TestAutopsyWithNothingToTeach(unittest.TestCase):
    """When the killer has nothing left to teach, reveal_on_death returns None.
    The autopsy card used to read fact.tier and fact.text unconditionally, so an
    empty lesson would have crashed the death screen -- the one screen a player
    cannot avoid."""

    def test_the_card_renders_with_no_fact(self):
        pygame.init()
        surf = pygame.Surface((config.W, config.H))
        w = World(FakeSave(), seed=12)
        w.player.gold = 40
        ui.draw_autopsy(surf, w, w.codex, None, "rat", 99.0)   # must not raise

    def test_the_card_still_renders_with_a_fact(self):
        pygame.init()
        surf = pygame.Surface((config.W, config.H))
        w = World(FakeSave(), seed=12)
        fact = FACTS["rat.rule"]
        ui.draw_autopsy(surf, w, w.codex, fact, "rat", 99.0)   # must not raise
```

`ui` and `FACTS` must be importable in the test module. `FACTS` is already imported at the
top of `tests.py`. If `ui` is not, add `from . import ui` to the module's imports beside the
existing `from . import render` — do not import it inside the test methods.

- [ ] **Step 2: Run the test to verify it fails**

Run: `py -3.13 -m unittest deathward.tests.TestAutopsyWithNothingToTeach -v`
Expected: `test_the_card_renders_with_no_fact` fails with
`AttributeError: 'NoneType' object has no attribute 'tier'`.
`test_the_card_still_renders_with_a_fact` should already pass.

- [ ] **Step 3: Teach the card to say nothing**

In `deathward/ui.py` `draw_autopsy`, replace everything from the `tag = ...` line through the
end of the function (the current body from `tag = "TELEMETRY RECOVERED" if ...` down to and
including the `ENTER go back down` block) with:

```python
    tag = ("NOTHING NEW" if fact is None
           else "TELEMETRY RECOVERED" if fact.tier == "telemetry"
           else "NEW KODEX ENTRY")
    head = pygame.Surface((card.w, 26), pygame.SRCALPHA)
    head.fill((*config.PLAYER, 26))
    surf.blit(head, card.topleft)
    text(surf, tag, (card.left + 16, card.top + 6), 13, config.PLAYER, bold=True)
    known, total = codex.progress()
    text(surf, "%d/%d" % (known, total), (card.right - 16, card.top + 13), 13,
         config.DIM, right=True)

    if fact is None:
        # nothing to reveal, so nothing to type out -- the card is complete at once
        y = card.top + 90
        for ln in wrap("You have learned everything this one has to teach. "
                       "It killed you anyway.", 15, card.w - 44):
            text(surf, ln, (card.left + 22, y), 15, config.INK)
            y += 22
        done = True
    else:
        text(surf, fact_title(fact, codex), (card.left + 22, card.top + 46), 23,
             config.INK, bold=True)
        body = fact.text
        n = int(min(len(body), reveal_t * 95))
        y = card.top + 90
        for ln in wrap(body[:n], 15, card.w - 44):
            text(surf, ln, (card.left + 22, y), 15, config.INK)
            y += 22
        done = n >= len(body)

    if done:
        text(surf, "the dungeon is unchanged.  you are not.",
             (cx, card.bottom + 30), 15, config.CORPSE, center=True)
        text(surf, "ENTER  go back down        K  kodex",
             (cx, card.bottom + 66), 17, config.PLAYER, center=True, bold=True)
```

- [ ] **Step 4: Guard the typewriter skip**

In `deathward/game.py`, the AUTOPSY branch (~line 473) reads:

```python
                if self.reveal_t * 95 < len(self.fact.text):
```

Replace with:

```python
                if self.fact is not None and self.reveal_t * 95 < len(self.fact.text):
```

so the first ENTER on a no-lesson card goes straight to the next run instead of raising.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `py -3.13 -m unittest deathward.tests.TestAutopsyWithNothingToTeach -v`
Expected: `Ran 2 tests ... OK`

- [ ] **Step 6: Run the full suite**

Run: `py -3.13 -m deathward.tests`
Expected: `Ran 850 tests ... OK` (848 + 2).

- [ ] **Step 7: Commit**

```bash
git add deathward/ui.py deathward/game.py deathward/tests.py
git commit -m "the autopsy can report an empty lesson without crashing"
```

---

### Task 3: The cascade collapses to the killer

**Files:**
- Modify: `deathward/codex.py` (`reveal_on_death` line 1110; delete `_telemetry_fact` line 1190; comment `SELF_SECRETS`/`DUNGEON_SECRETS` lines 637-638)
- Modify: `deathward/game.py` (~line 194)
- Modify: `deathward/world.py` (delete `floor_subjects`, line 2617)
- Modify: `deathward/player.py` (delete `carried_flavors`, ~line 288)
- Test: `deathward/tests.py` — `TestEveryDeathTeaches` rebuilt, plus two call sites elsewhere

**Interfaces:**
- Consumes: `Player.poison_source` from Task 1 (so `"gas"` reaches this code); `draw_autopsy(fact=None)` from Task 2 (so returning `None` is safe).
- Produces: `Codex.reveal_on_death(cause)` → `Fact` or `None`.

- [ ] **Step 1: Rewrite the death tests**

In `deathward/tests.py`, replace the entire `class TestEveryDeathTeaches` (starts ~line 490,
ends immediately before `class TestLearningByKilling`) with:

```python
class TestDeathTeachesItsKiller(unittest.TestCase):
    """A death teaches about the thing that killed you, or it teaches nothing.

    It used to cascade: if the killer had nothing left to give, the Kodex handed
    over the "nearest" unlearned thing on the floor instead -- which was never
    actually nearest, just first in the level's spawn list, anywhere on the map,
    seen or not. That is why a gas-vent death could hand you a fact about a
    kobold you had never met."""

    def test_first_death_explains_death(self):
        codex = FakeSave()
        codex.record_death("rat")
        self.assertEqual(codex.reveal_on_death("rat").key, "self.corpse")

    def test_the_killer_is_what_you_learn(self):
        codex = FakeSave()
        codex.known.append("self.corpse")
        codex.record_death("brute")
        self.assertEqual(codex.reveal_on_death("brute").key, "brute.rule")

    def test_the_tiers_arrive_in_order(self):
        codex = FakeSave()
        codex.known.append("self.corpse")
        got = []
        for _ in range(3):
            codex.record_death("brute")
            got.append(codex.reveal_on_death("brute").key)
        self.assertEqual(got, ["brute.rule", "brute.tell", "brute.counter"])

    def test_an_exhausted_killer_teaches_nothing(self):
        """The regression guard for the deleted cascade. This codex knows
        everything about brutes and almost nothing about anything else, so any
        surviving fallback would have plenty to reach for."""
        codex = FakeSave()
        codex.known.append("self.corpse")
        for tier in ("rule", "tell", "counter"):
            codex.known.append("brute.%s" % tier)
        codex.record_death("brute")
        self.assertIsNone(codex.reveal_on_death("brute"))
        self.assertLess(len(codex.known), TOTAL_FACTS,
                        "the guard is void unless facts remain unlearned")

    def test_a_cause_the_kodex_has_never_heard_of_teaches_nothing(self):
        """Self-inflicted venom reports the bare status "poison", which is not a
        Kodex subject. It teaches nothing, with no special case -- that is the
        new rule doing the work an exception used to."""
        codex = FakeSave()
        codex.known.append("self.corpse")
        codex.record_death("poison")
        self.assertIsNone(codex.reveal_on_death("poison"))

    def test_a_gas_vent_death_teaches_the_gas_vent(self):
        codex = FakeSave()
        codex.known.append("self.corpse")
        codex.record_death("gas")
        self.assertEqual(codex.reveal_on_death("gas").key, "gas.rule")

    def test_deaths_never_repeat_a_lesson(self):
        """The surviving half of the old load-bearing proof. A lesson is never
        handed out twice; the difference now is that a death may hand out none."""
        rng = random.Random(20260713)
        codex = FakeSave()
        seen = set()
        taught = 0
        for i in range(500):
            cause = rng.choice(CAUSES)
            codex.record_death(cause)
            codex.runs = i // 3 + 1
            codex.best_depth = min(8, 1 + i // 40)
            fact = codex.reveal_on_death(cause)
            if fact is None:
                continue
            taught += 1
            ident = fact.title + fact.text
            self.assertNotIn(ident, seen,
                             "death %d repeated a lesson: %r" % (i, fact.title))
            seen.add(ident)
            self.assertTrue(fact.key == "self.corpse"
                            or fact.key.startswith(cause + "."),
                            "death %d taught %r, which is not about %r"
                            % (i, fact.key, cause))
        self.assertGreater(taught, 0, "500 deaths must teach something")
        self.assertLess(taught, 500,
                        "with 13 causes and 3 tiers each, most of 500 deaths "
                        "must run out of things to teach")
```

Then fix the two call sites outside that class:

`test_dying_is_faster_than_killing` (~line 662) — change
`dier.reveal_on_death("brute", ["brute"], [])` to `dier.reveal_on_death("brute")`.

The test around line 721 that asserts a death never repeats a kill's lesson dereferences
`fact.title` unconditionally. Change:

```python
            fact = codex.reveal_on_death(cause, rng.sample(SUBJECTS, 4),
                                         rng.sample(FLAVORS, 2))
            ident = fact.title + fact.text
            self.assertNotIn(ident, seen,
                             "death %d taught something already known from a kill" % i)
            seen.add(ident)
```

to:

```python
            fact = codex.reveal_on_death(cause)
            if fact is None:
                continue
            ident = fact.title + fact.text
            self.assertNotIn(ident, seen,
                             "death %d taught something already known from a kill" % i)
            seen.add(ident)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -3.13 -m unittest deathward.tests.TestDeathTeachesItsKiller -v`
Expected: FAIL. `reveal_on_death` still requires three arguments, so most tests raise
`TypeError: reveal_on_death() missing 2 required positional arguments`.

- [ ] **Step 3: Collapse the cascade**

In `deathward/codex.py`, replace the whole of `reveal_on_death` (from its `def` line through
the `return self._telemetry_fact()` line) with:

```python
    def reveal_on_death(self, cause):
        """The Fact this death teaches, or None if it teaches nothing.

        A death explains the thing that killed you. When that thing has nothing
        left to give -- every tier already known, or a cause the Kodex has no
        subject for -- the death teaches NOTHING. It does not substitute a lesson
        about something else; a lesson you did not earn from the thing that killed
        you is not a lesson, it is noise.

        cause -- what killed them (monster/trap key)
        """
        # the first death explains death itself
        if "self.corpse" not in self.known:
            return self._grant("self.corpse")

        # then the thing that killed you, in tier order -- and nothing else
        for tier in TIER_ORDER:
            key = "%s.%s" % (cause, tier)
            if key in FACTS and key not in self.known:
                return self._grant(key)

        return None
```

- [ ] **Step 4: Delete `_telemetry_fact`**

In `deathward/codex.py`, delete the entire `_telemetry_fact` method (starts `def _telemetry_fact(self):` ~line 1190, ends at the final `return Fact("telemetry.%d" % len(self.telemetry), ...)` line before the next `def`).

Do NOT touch `self.telemetry` itself — it is initialised (`codex.py:661`), loaded (`:735`), saved (`:777`), consulted by `has_progress` (`:803`) and rendered in the Kodex's Lore tab. Entries already in a player's save must keep displaying.

- [ ] **Step 5: Mark the orphaned secret lists**

In `deathward/codex.py`, the lines defining `SELF_SECRETS` and `DUNGEON_SECRETS` (~637-638) keep their values and gain a comment above them:

```python
# Granted by nothing, for now. reveal_on_death used to hand these out when a death
# had nothing else to teach -- but they are system tutorials, not lore about your
# killer, so they left with the cascade. They are waiting on experience triggers of
# their own (take the stairs down, watch armour absorb a blow), which is its own
# piece of work. Until then these five are unobtainable and sit sealed in the Kodex.
SELF_SECRETS = ["self.energy", "self.armour", "self.stairs"]
DUNGEON_SECRETS = ["dungeon.hoard", "dungeon.deep"]
```

- [ ] **Step 6: Update the call site and delete the two dead helpers**

In `deathward/game.py` (~line 194), replace:

```python
        self.fact = self.codex.reveal_on_death(
            cause, w.floor_subjects(), w.player.carried_flavors())
```

with:

```python
        self.fact = self.codex.reveal_on_death(cause)
```

Then delete `World.floor_subjects` (`deathward/world.py`, starts `def floor_subjects(self):` ~line 2617, ends at its `return subs`) and `Player.carried_flavors` (`deathward/player.py`, ~line 288, the two-line method returning `list(self.pack)`).

Before deleting each one, confirm it has no other caller:

```bash
grep -rn "floor_subjects\|carried_flavors" deathward/
```

Expected after your edits: no hits at all. If anything else still calls them, STOP and report rather than deleting.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `py -3.13 -m unittest deathward.tests.TestDeathTeachesItsKiller -v`
Expected: `Ran 7 tests ... OK`

- [ ] **Step 8: Prove the guard has teeth**

The point of this task is that no fallback survives. Temporarily add a fallback back into
`reveal_on_death`, immediately before `return None`:

```python
        for f in FACT_LIST:
            if f.key not in self.known:
                return self._grant(f.key)
```

Then `rm -rf deathward/__pycache__` and re-run:

Run: `py -3.13 -m unittest deathward.tests.TestDeathTeachesItsKiller -v`
Expected: FAIL — `test_an_exhausted_killer_teaches_nothing`,
`test_a_cause_the_kodex_has_never_heard_of_teaches_nothing` and
`test_deaths_never_repeat_a_lesson` must all go red.

Remove the fallback, `rm -rf deathward/__pycache__` again, confirm green. Do not commit the fallback.

- [ ] **Step 9: Run the full suite**

Run: `py -3.13 -m deathward.tests`
Expected: OK. The count drops — three tests were deleted with the old class
(`test_dying_with_an_unknown_potion_can_name_it`, `test_the_whole_codex_is_reachable_by_dying`,
`test_telemetry_is_inexhaustible`) and seven added. Report the exact number you see.

If a failure names a test outside the classes this task touches, STOP and report it — that is
a real consequence of the rule change and is the user's call, not yours to paper over.

- [ ] **Step 10: Commit**

```bash
git add deathward/codex.py deathward/game.py deathward/world.py deathward/player.py deathward/tests.py
git commit -m "a death teaches its killer, or it teaches nothing"
```

---

### Task 4: The README stops advertising the retired guarantee

**Files:**
- Modify: `README.md:212`

**Interfaces:**
- Consumes: nothing. Reviewable and rejectable on its own.
- Produces: nothing.

- [ ] **Step 1: Reword the claim**

`README.md:212` currently opens the Tests section's prose with:

```markdown
842 tests, including the two load-bearing proofs: hundreds of consecutive deaths
never repeat a lesson (and the telemetry tier is inexhaustible), and
blind-vs-omniscient runs of the same seed produce identical dungeons. Plus: the
```

Replace those three lines with:

```markdown
842 tests, including the two load-bearing proofs: a death teaches you about the
thing that killed you or it teaches you nothing, and never repeats a lesson; and
blind-vs-omniscient runs of the same seed produce identical dungeons. Plus: the
```

Leave the rest of the paragraph untouched — everything after "Plus:" is still accurate.

**Do not update the test count in this step.** Task 3's commit changes it; use the number
its Step 9 actually printed, and if that differs from 842, correct it here as part of this
edit.

- [ ] **Step 2: Verify no other README claim contradicts the new rule**

Run: `grep -n -i "every death\|always teaches\|inexhaustible\|telemetry" README.md`

Expected: no surviving claim that every death teaches something. If one is found outside
line 212, report it and fix it in the same commit.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: deaths teach their killer or nothing, and the README says so"
```

---

## Verification

Automated coverage ends at Task 3 Step 9. The rest is the user's:

- Die to a monster whose Kodex entries are complete → the **NOTHING NEW** card, and ENTER
  goes straight back down.
- Die to a gas vent → the autopsy names "a gas vent" and teaches a `gas` entry, not a
  stranger.
- The Kodex's Lore tab shows five permanently sealed entries and completion caps at 93/98.
  **This is expected**, is the accepted cost of splitting the work, and is fixed by the
  secret-facts trigger task that follows this one.
