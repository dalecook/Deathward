# The Kodex Stops Lying About Itself — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete the five tutorial facts nothing can grant, and replace the one sealed-entry hint with six that are actually true.

**Architecture:** Task 1 is deletion in `codex.py` — five facts and the two constants that named them; `TOTAL_FACTS` follows automatically. Task 2 replaces a hard-coded string in `ui.py` with a helper that selects a hint by category. Nothing that grants a fact changes.

**Tech Stack:** Python 3.13, pygame 2.6.1, `unittest`.

**Spec:** `docs/superpowers/specs/2026-09-04-kodex-honest-about-itself-design.md`

## Global Constraints

- Branch is `fix/kodex-honest-about-itself`, already checked out at `cff9435`. Never work on `main`.
- The six sealed hints are approved copy. Reproduce them character for character, full stops included:
  - monsters — `this entry is written by dying to it, or by killing enough of them.`
  - traps — `this entry is written by springing it, or by dying to it.`
  - scrolls — `this entry is written by reading it.`
  - potions — `this entry is written by drinking it.`
  - lore, the three collector awards — `this entry is written by collecting every one.`
  - lore, everything else — `this entry is written by dying.`
- The five deleted keys are exactly `self.energy`, `self.armour`, `self.stairs`, `dungeon.hoard`, `dungeon.deep`. Delete no others.
- `TOTAL_FACTS` must end at **93**. It is `len(FACT_LIST)` and must stay derived — never hard-code it.
- Nothing that grants a fact changes: no edits to `reveal_on_death`, `reveal_on_kill`, `reveal_on_trap`, `reveal_random`, `identify` or the `award_*` methods.
- The Gear tab has its own sealed branch with its own hint (`this entry is written by finding it.`). Leave it alone.
- No save migration. `TOTAL_FACTS` derives from `FACT_LIST`, and the only live save has learned none of the five.
- Python is `py -3.13`. Plain `python` is NOT on PATH. Full suite: `py -3.13 -m deathward.tests`. Single class: `py -3.13 -m unittest deathward.tests.<ClassName> -v`.
- The suite is safe to run: `setUpModule` redirects the save path to a tempdir.
- **Clear `deathward/__pycache__` between any mutation and its restore.** A same-length edit made in the same second reuses stale bytecode, and a restored file keeps testing as mutated.
- 862 tests green at branch point. This plan adds 6, for 868.

## File Structure

| File | Change | Responsibility |
|---|---|---|
| `deathward/codex.py` | Modify | Loses five fact definitions and the `SELF_SECRETS` / `DUNGEON_SECRETS` constants. |
| `deathward/ui.py` | Modify (`_kodex_sealed_label` ~line 700, `draw_codex` ~line 786) | Gains `_kodex_sealed_how`; the sealed hint stops being one hard-coded string. |
| `deathward/tests.py` | Modify | Two new classes: the deletion is deliberate, and each category's hint is correct. |

---

### Task 1: Cut the five tutorials

**Files:**
- Modify: `deathward/codex.py` (three `_f` blocks in the SELF section ~lines 71-83; the DUNGEON section ~lines 562-571; the constants ~lines 638-644)
- Test: `deathward/tests.py` — new class

**Interfaces:**
- Consumes: nothing.
- Produces: `TOTAL_FACTS == 93`. Task 2 does not depend on it, but its own tests run against the reduced catalogue.

- [ ] **Step 1: Write the failing tests**

First, `deathward/tests.py` line 41 currently reads:

```python
from .codex import FACTS, TOTAL_FACTS, Codex  # noqa: E402
```

Change it to add `FACT_LIST`:

```python
from .codex import FACT_LIST, FACTS, TOTAL_FACTS, Codex  # noqa: E402
```

Then add this class immediately before `class TestSubjectCompletion`:

```python
class TestTheCutTutorials(unittest.TestCase):
    """Five facts -- TURNS ARE A CURRENCY, ARMOUR IS SUBTRACTION, DOWN IS FREE,
    THE HOARDS ARE GUARDED, WHY YOU CANNOT SEE -- were cut on 2026-09-04.

    They were not lost by accident. They were system tutorials granted only by
    the fallback cascade that a death used to run when it had nothing else to
    teach; when that cascade was deleted they became unobtainable. The choice
    was between giving them experience triggers and dropping them, and they
    explain genre conventions a roguelike player already arrives with. Do not
    restore them without asking."""

    def test_the_five_tutorials_are_gone(self):
        for key in ("self.energy", "self.armour", "self.stairs",
                    "dungeon.hoard", "dungeon.deep"):
            self.assertNotIn(key, FACTS, "%s was cut deliberately" % key)

    def test_the_kodex_is_ninety_three_entries(self):
        """Pinned so an accidental re-add is caught. What matters is not the
        number but that it is REACHABLE: every remaining fact has a live grant
        path -- 36 item identities by using the item, 52 monster and trap tiers
        by dying, killing or springing, self.corpse on a first death,
        self.the_deep_is_patient on waking after one, and three collector awards
        by completing a set. Before this change five entries had no path at all
        and the Kodex could not be finished."""
        self.assertEqual(TOTAL_FACTS, 93)
        self.assertEqual(len(FACT_LIST), 93)

    def test_the_dungeon_subject_is_gone_entirely(self):
        """dungeon.hoard and dungeon.deep were the only two facts about the
        dungeon itself, so the whole subject left with them."""
        self.assertEqual([f.key for f in FACT_LIST if f.subject == "dungeon"], [])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -3.13 -m unittest deathward.tests.TestTheCutTutorials -v`
Expected: FAIL — all three. `self.energy was cut deliberately`, `98 != 93`, and the dungeon list comes back with two keys.

- [ ] **Step 3: Delete the three SELF tutorials**

In `deathward/codex.py`, delete these three `_f(...)` entries in full. They sit between the `self.corpse` entry and the `self.magical_collector` entry:

```python
    _f("self.energy", "self", "secret", "TURNS ARE A CURRENCY",
       "Nothing here moves in real time. Everything -- you, the rats, the thing in "
       "the dark -- spends the same currency: turns. Boots are not a cosmetic. Fast "
       "boots literally buy you extra actions between a monster's swings. Heavy "
       "armour sells them back."),
    _f("self.armour", "self", "secret", "ARMOUR IS SUBTRACTION",
       "Armour does not reduce damage by a fraction. It subtracts a flat number from "
       "EVERY hit. Against one big monster it barely matters. Against six small ones "
       "it is the difference between a scratch and a grave. Plate is for swarms."),
    _f("self.stairs", "self", "secret", "DOWN IS FREE",
       "The stairs never ask for a toll. You may leave any floor at any moment, with "
       "any fraction of it explored. Greed is the only thing that keeps you on a "
       "floor -- and greed is a choice, not a rule."),
```

Leave `self.corpse` above them and `self.magical_collector` below them exactly as they are.

- [ ] **Step 4: Delete the DUNGEON section**

Still in `deathward/codex.py`, delete the section comment and both entries — the whole block, including the blank line above the comment:

```python

    # --- DUNGEON ---------------------------------------------------------
    _f("dungeon.hoard", "dungeon", "secret", "THE HOARDS ARE GUARDED",
       "Rooms that glitter are not gifts. The dungeon puts its gold where its teeth are "
       "-- the denser the treasure, the worse the thing sleeping on it. If a room looks "
       "generous, count the exits before you take a step into it."),
    _f("dungeon.deep", "dungeon", "secret", "WHY YOU CANNOT SEE",
       "The dark down here is not a lack of torches. It is a lack of understanding. The "
       "dungeon draws exactly as much of itself as you have earned -- a thing you do not "
       "know is drawn as a hole, a trap you have never triggered is drawn as clean "
       "floor. You are not lighting this place up. You are learning it."),
```

This block ends the `FACT_LIST` literal, so after deleting it the list's closing `]` follows the entry that came before. Check the file still parses before moving on.

- [ ] **Step 5: Delete the two constants that named them**

Still in `deathward/codex.py`, delete this comment and both assignments in full:

```python
# Granted by nothing, for now. reveal_on_death used to hand these out when a death
# had nothing else to teach -- but they are system tutorials, not lore about your
# killer, so they left with the cascade. They are waiting on experience triggers of
# their own (take the stairs down, watch armour absorb a blow), which is its own
# piece of work. Until then these five are unobtainable and sit sealed in the Kodex.
SELF_SECRETS = ["self.energy", "self.armour", "self.stairs"]
DUNGEON_SECRETS = ["dungeon.hoard", "dungeon.deep"]
```

Confirm nothing referenced them:

```bash
grep -rn "SELF_SECRETS\|DUNGEON_SECRETS" deathward/
```

Expected: no output. If anything comes back, STOP and report rather than deleting its caller.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `py -3.13 -m unittest deathward.tests.TestTheCutTutorials -v`
Expected: `Ran 3 tests ... OK`

- [ ] **Step 7: Prove the tests can fail**

Temporarily paste the `self.stairs` entry back into `FACT_LIST` (it is in Step 3 above), then:

```bash
rm -rf deathward/__pycache__
py -3.13 -m unittest deathward.tests.TestTheCutTutorials -v
```

Expected: FAIL — `test_the_five_tutorials_are_gone` and `test_the_kodex_is_ninety_three_entries` both go red (`94 != 93`).

Remove it again, `rm -rf deathward/__pycache__`, confirm green. Do not commit the restored fact.

- [ ] **Step 8: Run the full suite**

Run: `py -3.13 -m deathward.tests`
Expected: `Ran 865 tests ... OK` (862 + 3). A single `skipped 'no clear line on this seed'` in `TestFireIsVisible` is pre-existing and seed-dependent.

If a failure names a test outside this class, STOP and report it — something depended on the deleted facts and that is worth knowing rather than papering over.

- [ ] **Step 9: Commit**

```bash
git add deathward/codex.py deathward/tests.py
git commit -m "cut five tutorials the game does not need to teach"
```

---

### Task 2: Every sealed entry says how to earn it

**Files:**
- Modify: `deathward/ui.py` (`_kodex_sealed_label` ~line 700; the sealed hint line in `draw_codex` ~line 786)
- Test: `deathward/tests.py` — new class

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `ui._kodex_sealed_how(fact, cat) -> str`.

- [ ] **Step 1: Write the failing tests**

Add this class to `deathward/tests.py`, immediately after `class TestTheCutTutorials`:

```python
class TestSealedEntriesSayHowToEarnThem(unittest.TestCase):
    """Every sealed entry used to read "this entry is written by dying." That was
    true when a death could hand you anything on the floor. Since a death teaches
    only its killer, it is false for the 36 scroll and potion identities -- those
    are earned solely by reading or drinking the thing -- and it was already false
    for the three collector awards."""

    def test_each_category_gets_its_own_hint(self):
        cases = [
            (FACTS["kobold.rule"], "monsters",
             "this entry is written by dying to it, or by killing enough of them."),
            (FACTS["gas.rule"], "traps",
             "this entry is written by springing it, or by dying to it."),
            (FACTS["id.kesh"], "scrolls", "this entry is written by reading it."),
            (FACTS["id.ochre"], "potions", "this entry is written by drinking it."),
            (FACTS["self.magical_collector"], "lore",
             "this entry is written by collecting every one."),
            (FACTS["self.corpse"], "lore", "this entry is written by dying."),
        ]
        for fact, cat, expected in cases:
            self.assertEqual(ui._kodex_sealed_how(fact, cat), expected,
                             "wrong hint for %s in the %s tab" % (fact.key, cat))

    def test_all_three_collector_awards_ask_you_to_collect(self):
        for key in ("self.magical_collector", "self.magical_boot_collector",
                    "self.magical_armour_collector"):
            self.assertEqual(ui._kodex_sealed_how(FACTS[key], "lore"),
                             "this entry is written by collecting every one.")

    def test_no_item_identity_tells_you_to_die_for_it(self):
        """The specific regression: one shared hint sent 36 entries to their death
        for something only using the item can teach."""
        for cat in ("scrolls", "potions"):
            self.assertNotIn("dying", ui._kodex_sealed_how(FACTS["id.ochre"], cat))
```

`ui` and `FACTS` are already imported at the top of `tests.py`. Do not add module-level imports.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `py -3.13 -m unittest deathward.tests.TestSealedEntriesSayHowToEarnThem -v`
Expected: FAIL — all three error with
`AttributeError: module 'deathward.ui' has no attribute '_kodex_sealed_how'`.

- [ ] **Step 3: Add the helper**

In `deathward/ui.py`, add this function immediately after `_kodex_sealed_label`:

```python
def _kodex_sealed_how(f, cat):
    """How to earn this entry -- printed under every sealed one.

    This used to be one hard-coded "this entry is written by dying", which was
    true when a death could hand you anything. Now that a death teaches only its
    killer, an item's true name is earned solely by using the item, and the
    collector awards by completing a set. A Kodex that tells you the wrong way to
    fill it in is worse than one that says nothing.
    """
    if cat == "scrolls":
        return "this entry is written by reading it."
    if cat == "potions":
        return "this entry is written by drinking it."
    if cat == "traps":
        return "this entry is written by springing it, or by dying to it."
    if cat == "lore":
        if f.key.startswith("self.magical"):
            return "this entry is written by collecting every one."
        return "this entry is written by dying."
    return "this entry is written by dying to it, or by killing enough of them."
```

- [ ] **Step 4: Use it at the call site**

Still in `deathward/ui.py`, inside `draw_codex`, this line:

```python
                line("this entry is written by dying.", 13, (52, 56, 70), indent=18)
```

becomes:

```python
                line(_kodex_sealed_how(f, cat), 13, (52, 56, 70), indent=18)
```

Leave the `[ SEALED ]` line above it, the size, the colour and the indent exactly as they are.

- [ ] **Step 5: Retire a branch that can no longer fire**

Still in `deathward/ui.py`, `_kodex_sealed_label` currently reads:

```python
    if cat == "lore":
        return "yourself" if f.subject == "self" else "the dungeon"
```

Task 1 deleted the only two facts whose subject was `dungeon`, so the second half is unreachable. Replace it with:

```python
    if cat == "lore":
        return "yourself"       # the dungeon subject went with dungeon.hoard/.deep
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `py -3.13 -m unittest deathward.tests.TestSealedEntriesSayHowToEarnThem -v`
Expected: `Ran 3 tests ... OK`

- [ ] **Step 7: Prove the tests can fail**

Temporarily make the helper return the old single line for everything — put `return "this entry is written by dying."` as its first statement — then:

```bash
rm -rf deathward/__pycache__
py -3.13 -m unittest deathward.tests.TestSealedEntriesSayHowToEarnThem -v
```

Expected: FAIL — all three go red, `test_no_item_identity_tells_you_to_die_for_it` among them. That is precisely the bug being fixed, so a green suite here would mean the tests are not measuring it.

Remove the early return, `rm -rf deathward/__pycache__`, confirm green. Do not commit the disabled version.

- [ ] **Step 8: Run the full suite**

Run: `py -3.13 -m deathward.tests`
Expected: `Ran 868 tests ... OK` (865 + 3).

- [ ] **Step 9: Commit**

```bash
git add deathward/ui.py deathward/tests.py
git commit -m "every sealed entry now says how to earn that entry"
```

---

## Verification

Automated coverage ends at Task 2 Step 8. The rest is the user's:

- Open the Kodex with `K`. The **Scrolls** and **Potions** tabs should tell you to read and drink, not to die. The **Lore** tab's three collector awards should ask you to collect every one; THE DEAD DO NOT LEAVE should still say dying.
- The **Monsters** and **Traps** tabs should now mention killing and springing alongside dying.
- The Lore tab should hold five entries, not ten, and the progress counter on a death or banner card should read out of **93**.
